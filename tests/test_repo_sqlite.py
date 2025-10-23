# tests/test_repo_sqlite.py
# -*- coding: utf-8 -*-
"""
Tests d'intégration pour la couche persistence (SQLite/SQLAlchemy).

Ce fichier couvre :
- initialisation d'une base temporaire par exécution (DB_URL -> tmp file),
- création utilisateur, unicité email, mise à jour du statut premium,
- CRUD des enregistrements journaliers,
- contrainte 1 record par jour,
- requêtes par plage, ordre, derniers N,
- moyenne sur 7 jours,
- normalisation des dates (date, datetime, string ISO).

Architecture ciblée :
app/persistence/db.py
app/persistence/models.py
app/persistence/repositories/users_repo.py
app/persistence/repositories/records_repo.py
"""

import datetime as dt
import importlib
import os
from dataclasses import dataclass

import pytest
from sqlalchemy.exc import IntegrityError


# ---------------------------------------------------------------------
# FIXTURE PRINCIPALE : repos initialisés sur une DB temporaire
# ---------------------------------------------------------------------

@dataclass
class Repos:
    users: object
    records: object


@pytest.fixture
def repos(tmp_path, monkeypatch) -> Repos:
    """
    Prépare un environnement propre :
    - crée une base SQLite temporaire (ex: /tmp/pytest-xxxx/test_quantifyme.db)
    - définit DB_URL AVANT de (re)charger les modules
    - (re)charge db/models pour régénérer l'engine et les tables
    - instancie les repositories Users/Records
    """
    db_path = tmp_path / "test_quantifyme.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")

    # (Re)charger les modules d'infra et de modèles
    import app.persistence.db as db
    import app.persistence.models as models
    importlib.reload(db)
    importlib.reload(models)

    # Créer (ou recréer) les tables
    db.init_db(models.Base, drop_and_recreate=True)

    # (Re)charger les repos (pour qu'ils utilisent bien le db.engine courant)
    import app.persistence.repositories.users_repo as users_repo
    import app.persistence.repositories.records_repo as records_repo
    importlib.reload(users_repo)
    importlib.reload(records_repo)

    return Repos(
        users=users_repo.UserRepository(),
        records=records_repo.RecordRepository(),
    )


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def add_days(date: dt.date, n: int) -> dt.date:
    return date + dt.timedelta(days=n)


# ---------------------------------------------------------------------
# TESTS UTILISATEURS
# ---------------------------------------------------------------------

def test_create_and_get_user(repos: Repos):
    u = repos.users.create("User@Example.com", is_premium=False)
    assert u.id > 0
    # get_by_email normalise en lower()
    got = repos.users.get_by_email("user@example.com")
    assert got is not None
    assert got.id == u.id
    assert got.is_premium is False

def test_get_or_create_user(repos: Repos):
    u1 = repos.users.get_or_create("a@b.com", is_premium=True)
    u2 = repos.users.get_or_create("A@B.com", is_premium=False)  # même email (case-insensitive)
    assert u1.id == u2.id
    assert repos.users.get_by_email("a@b.com").is_premium is True  # reste sur la 1re création

def test_unique_email_enforced(repos: Repos):
    repos.users.create("dup@example.com")
    # Le doublon doit lever une IntegrityError à la validation de la transaction
    with pytest.raises(IntegrityError):
        repos.users.create("dup@example.com")

def test_set_premium(repos: Repos):
    repos.users.create("p@x.com")
    repos.users.set_premium("p@x.com", True)
    assert repos.users.get_by_email("p@x.com").is_premium is True


# ---------------------------------------------------------------------
# TESTS RECORDS : CRUD & CONTRAINTES
# ---------------------------------------------------------------------

def test_add_record_and_get_records(repos: Repos):
    u = repos.users.create("r@example.com")
    today = dt.date(2025, 1, 1)

    rec = repos.records.add(
        u.id, today,
        humeur=7, sommeil=6.5, stress=3, concentration=7.5,
        scj=5.0, interpretation="OK"
    )
    assert rec.id > 0
    rows = repos.records.get_range(u.id)
    assert len(rows) == 1
    assert rows[0].date == today
    assert rows[0].scj == 5.0

def test_add_record_uniqueness_per_day(repos: Repos):
    u = repos.users.create("once@day.com")
    d = dt.date(2025, 2, 2)

    repos.records.add(u.id, d, humeur=5, sommeil=7, stress=3, concentration=6, scj=4.8)
    # 2e insert sur le même (user, date) doit échouer côté repo avec ValueError
    with pytest.raises(ValueError):
        repos.records.add(u.id, d, humeur=6, sommeil=7, stress=3, concentration=6, scj=5.2)

def test_upsert_record_for_date_insert_then_update(repos: Repos):
    u = repos.users.create("upsert@example.com")
    d = dt.date(2025, 3, 3)

    # Insert
    r1 = repos.records.upsert(
        u.id, d, humeur=5, sommeil=7, stress=3, concentration=6, scj=4.8, interpretation=None
    )
    assert r1.id > 0
    assert repos.records.get_range(u.id)[0].scj == 4.8

    # Update même jour
    r2 = repos.records.upsert(
        u.id, d, humeur=6, sommeil=7, stress=2, concentration=7, scj=6.4, interpretation="Mieux"
    )
    assert r2.id == r1.id  # même ligne
    rows = repos.records.get_range(u.id)
    assert len(rows) == 1
    assert rows[0].scj == 6.4
    assert rows[0].interpretation == "Mieux"

def test_delete_record(repos: Repos):
    u = repos.users.create("del@example.com")
    d = dt.date(2025, 4, 4)

    # Rien à supprimer la 1re fois
    assert repos.records.delete(u.id, d) is False

    repos.records.add(u.id, d, humeur=6, sommeil=7, stress=3, concentration=6, scj=5.2)
    assert repos.records.delete(u.id, d) is True
    # Plus rien derrière
    assert repos.records.delete(u.id, d) is False

def test_record_exists_and_date_normalization(repos: Repos):
    u = repos.users.create("exist@example.com")
    d = dt.date(2025, 5, 5)

    assert repos.records.exists(u.id, d) is False
    repos.records.add(u.id, "2025-05-05", humeur=5, sommeil=7, stress=3, concentration=6, scj=4.8)
    assert repos.records.exists(u.id, dt.datetime(2025, 5, 5, 10, 0)) is True  # accepte datetime aussi


# ---------------------------------------------------------------------
# REQUÊTES : périodes, ordre, derniers N, moyenne 7 jours
# ---------------------------------------------------------------------

def test_get_records_with_date_range_and_order(repos: Repos):
    u = repos.users.create("range@example.com")
    start = dt.date(2025, 1, 1)

    # 5 jours successifs
    for i in range(5):
        day = add_days(start, i)
        repos.records.add(u.id, day, humeur=6, sommeil=7, stress=3, concentration=6, scj=5 + i)

    # Filtre sur [J+1, J+3]
    rows = repos.records.get_range(u.id, start=add_days(start, 1), end=add_days(start, 3), asc=True)
    assert [r.scj for r in rows] == [6, 7, 8]  # 3 éléments

    rows_desc = repos.records.get_range(u.id, start=add_days(start, 1), end=add_days(start, 3), asc=False)
    assert [r.scj for r in rows_desc] == [8, 7, 6]

def test_get_last_n_records(repos: Repos):
    u = repos.users.create("lastn@example.com")
    start = dt.date(2025, 6, 1)
    for i in range(10):
        repos.records.add(u.id, add_days(start, i), humeur=5, sommeil=7, stress=3, concentration=6, scj=float(i))

    last7 = repos.records.last_n(u.id, n=7)
    # Renvoie en ordre chronologique croissant
    assert [r.scj for r in last7] == [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]

def test_get_weekly_average(repos: Repos):
    u = repos.users.create("avg7@example.com")
    end = dt.date(2025, 7, 7)
    # 7 jours consécutifs : SCJ = 1..7 -> moyenne = 4.0
    for i in range(7):
        repos.records.add(u.id, add_days(end, -6 + i), humeur=6, sommeil=7, stress=3, concentration=6, scj=float(i + 1))

    avg = repos.records.weekly_avg(u.id, end_date=end)
    assert avg == pytest.approx(4.0, abs=1e-9)

def test_get_weekly_average_with_missing_days(repos: Repos):
    u = repos.users.create("avg_sparse@example.com")
    end = dt.date(2025, 8, 8)
    # Seulement 3 jours sur la fenêtre : moyenne doit être celle des présents
    repos.records.add(u.id, add_days(end, -6), humeur=6, sommeil=7, stress=3, concentration=6, scj=5.0)
    repos.records.add(u.id, add_days(end, -3), humeur=6, sommeil=7, stress=3, concentration=6, scj=7.0)
    repos.records.add(u.id, add_days(end, -0), humeur=6, sommeil=7, stress=3, concentration=6, scj=9.0)

    avg = repos.records.weekly_avg(u.id, end_date=end)
    assert avg == pytest.approx((5.0 + 7.0 + 9.0) / 3.0, abs=1e-9)
