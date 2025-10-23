# scripts/seed_local_data.py
# -*- coding: utf-8 -*-
"""
Seed local pour QuantifyMe : crée des utilisateurs et des enregistrements journaliers réalistes.

Caractéristiques :
- Idempotent : réexécutable sans doublons (upsert par date + user)
- Paramétrable via CLI : nb d'utilisateurs, nb de jours, date de fin/début, gaps aléatoires
- Génération des SCJ via score_engine (cohérente avec le projet)
- Option (--with-ai) pour produire une interprétation (par défaut StubProvider)
- Option (--wipe) pour drop+recreate le schéma (utile en dev)

Utilise :
- app/persistence/db.py            -> init_db()
- app/persistence/models.py        -> Base
- app/persistence/repositories/... -> UserRepository, RecordRepository
- app/services/score_engine.py     -> DailyInput, compute_scj
- app/services/ai_service.py       -> AIService, DailyInputsLite (si --with-ai)

Exemples :
    # 3 users, 14 jours jusqu’à aujourd’hui, sans interprétation IA
    python scripts/seed_local_data.py

    # 5 users, 30 jours, quelques trous de données, avec IA (stub/HF selon env)
    python scripts/seed_local_data.py --users 5 --days 30 --gap-rate 0.15 --with-ai

    # Spécifier l'email et recommencer à zéro
    python scripts/seed_local_data.py --users 1 --email-prefix demo --domain example.org --wipe

    # Définir une date de fin (YYYY-MM-DD)
    python scripts/seed_local_data.py --end 2025-10-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
from typing import Optional

# Persistance & modèles
from app.persistence.db import init_db
from app.persistence.models import Base
from app.persistence.repositories.users_repo import UserRepository
from app.persistence.repositories.records_repo import RecordRepository

# Moteur de score
from app.services.score_engine import DailyInput, compute_scj

# Service IA (optionnel si --with-ai)
from app.services.ai_service import AIService, DailyInputsLite


# -------------------------------------------------------------------
# Utils
# -------------------------------------------------------------------

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def rand_in_range(lo: float, hi: float) -> float:
    """Uniforme [lo, hi]."""
    return random.uniform(lo, hi)


def sample_day_inputs() -> DailyInput:
    """
    Génère un jeu d'inputs "réaliste" pour une journée.
    - humeur, stress, concentration : 0..10
    - sommeil : 4..9h (on reste raisonnable)
    """
    humeur = clamp(random.gauss(6.5, 1.6), 0.0, 10.0)
    stress = clamp(random.gauss(4.0, 2.0), 0.0, 10.0)
    concentration = clamp(random.gauss(6.0, 1.8), 0.0, 10.0)
    sommeil = clamp(random.gauss(7.0, 1.2), 4.0, 9.0)  # heures
    return DailyInput(
        humeur=round(humeur, 1),
        sommeil=round(sommeil, 1),
        stress=round(stress, 1),
        concentration=round(concentration, 1),
    )


def daterange(end: dt.date, days: int):
    """Génère des dates [end - (days-1) .. end] incluses, en ordre croissant."""
    for i in range(days):
        yield end - dt.timedelta(days=(days - 1 - i))


# -------------------------------------------------------------------
# Seeding
# -------------------------------------------------------------------

def seed(
    *,
    users: int,
    days: int,
    end_date: dt.date,
    email_prefix: str,
    domain: str,
    gap_rate: float,
    with_ai: bool,
) -> None:
    """
    Remplit la base avec `users` utilisateurs, chacun ayant jusqu'à `days` enregistrements,
    avec des trous éventuels (gap_rate). Les enregistrements sont upsertés : réentrant.
    """
    user_repo = UserRepository()
    rec_repo = RecordRepository()
    ai = AIService() if with_ai else None

    print(f"➡️  Seeding {users} user(s), {days} jour(s), fin au {end_date.isoformat()}"
          f" | gaps ~{int(gap_rate*100)}% | AI={'on' if with_ai else 'off'}")

    total_records = 0
    for i in range(1, users + 1):
        email = f"{email_prefix}{i}@{domain}".lower()
        u = user_repo.get_or_create(email, is_premium=(i % 3 == 0))  # 1/3 premium pour varier
        print(f"   • User {u.id:>3}  {u.email:<30}  premium={u.is_premium}")

        for day in daterange(end=end_date, days=days):
            # Probabilité de "jour manquant" pour simuler des trous dans les séries
            if random.random() < gap_rate:
                continue

            inputs = sample_day_inputs()
            scj = compute_scj(inputs).scj

            interpretation: Optional[str] = None
            if ai is not None:
                interpretation = ai.generate_interpretation(
                    scj=scj,
                    inputs=DailyInputsLite(
                        humeur=inputs.humeur,
                        sommeil=inputs.sommeil,
                        stress=inputs.stress,
                        concentration=inputs.concentration,
                    ),
                )

            rec_repo.upsert(
                user_id=u.id,
                date=day,
                humeur=inputs.humeur,
                sommeil=inputs.sommeil,
                stress=inputs.stress,
                concentration=inputs.concentration,
                scj=float(scj),
                interpretation=interpretation,
            )
            total_records += 1

    print(f"✅ Terminé : {users} user(s), {total_records} record(s) créés/mis à jour.")


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed local data for QuantifyMe")
    p.add_argument("--users", type=int, default=3, help="Nombre d'utilisateurs (défaut: 3)")
    p.add_argument("--days", type=int, default=14, help="Nombre de jours (défaut: 14)")
    p.add_argument("--end", type=str, default=None, help="Date de fin (YYYY-MM-DD). Défaut: aujourd'hui")
    p.add_argument("--email-prefix", type=str, default="user", help="Préfixe email (défaut: 'user')")
    p.add_argument("--domain", type=str, default="example.com", help="Domaine email (défaut: example.com)")
    p.add_argument("--gap-rate", type=float, default=0.1, help="Probabilité de sauter un jour (0..1, défaut: 0.1)")
    p.add_argument("--seed", type=int, default=None, help="Seed du générateur aléatoire pour reproductibilité")
    p.add_argument("--with-ai", action="store_true", help="Générer une interprétation IA (Stub/HF selon env)")
    p.add_argument("--wipe", action="store_true", help="Drop + recreate la base avant seeding")
    return p.parse_args()


def main():
    args = parse_args()

    # Seed random si demandé
    if args.seed is not None:
        random.seed(args.seed)

    # Date de fin
    end_date = dt.date.fromisoformat(args.end) if args.end else dt.date.today()

    # (Optionnel) wipe total
    if args.wipe:
        print("⚠️  Wipe : drop & recreate le schéma…")

    # Init DB schema
    init_db(Base, drop_and_recreate=bool(args.wipe))

    # Effectuer le seed
    seed(
        users=max(1, args.users),
        days=max(1, args.days),
        end_date=end_date,
        email_prefix=args.email_prefix,
        domain=args.domain,
        gap_rate=clamp(args.gap_rate, 0.0, 0.9),
        with_ai=bool(args.with_ai),
    )


if __name__ == "__main__":
    main()
