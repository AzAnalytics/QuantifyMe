# tests/test_score_engine.py
# -*- coding: utf-8 -*-
"""
Tests unitaires complets et pédagogiques pour app/services/score_engine.py

Ce fichier couvre :
- la validation des entrées (bornes, messages d'erreur),
- le calcul nominal du SCJ (formule par défaut),
- des propriétés de monotonie (↑ concentration => SCJ ne ↓ pas ; ↑ stress => SCJ ne ↑ pas),
- la personnalisation des poids et l'effet du dénominateur,
- l'arrondi et le (dé)clampage de la sortie,
- l'interprétation textuelle (buckets),
- l'idempotence (mêmes entrées => même résultat).
"""

import math
import pytest

from app.services.score_engine import (
    DailyInput,
    compute_scj,
    interpret_scj,
    InputValidationError,
    DEFAULT_WEIGHTS,
    MAX_SLEEP_HOURS,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    """Comparaison flottante tolérante (évite les faux négatifs liés aux arrondis)."""
    return abs(a - b) <= tol


# -----------------------------------------------------------------------------
# Validation des entrées
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "humeur,sommeil,stress,concentration",
    [
        (0, 0, 0, 0),                          # bornes basses OK
        (10, MAX_SLEEP_HOURS, 10, 10),         # bornes hautes OK
        (5.5, 6.75, 3.25, 8.8),                # valeurs décimales OK
    ],
)
def test_validate_input_ok(humeur, sommeil, stress, concentration):
    """
    Doit accepter des valeurs dans les bornes prévues :
    - humeur, stress, concentration ∈ [0..10]
    - sommeil ∈ [0..MAX_SLEEP_HOURS] (cap "raisonnable")
    """
    d = DailyInput(humeur=humeur, sommeil=sommeil, stress=stress, concentration=concentration)
    # compute_scj appelle validate_input en interne : ne doit pas lever
    _ = compute_scj(d)


@pytest.mark.parametrize(
    "humeur,sommeil,stress,concentration,field_name",
    [
        (-0.1, 6, 3, 7, "humeur"),
        (11, 6, 3, 7, "humeur"),
        (7, -0.1, 3, 7, "sommeil"),
        (7, MAX_SLEEP_HOURS + 0.01, 3, 7, "sommeil"),
        (7, 6, -0.1, 7, "stress"),
        (7, 6, 10.0001, 7, "stress"),
        (7, 6, 3, -0.01, "concentration"),
        (7, 6, 3, 10.1, "concentration"),
    ],
)
def test_validate_input_raises_with_field_name(humeur, sommeil, stress, concentration, field_name):
    """
    Hors bornes => doit lever InputValidationError avec le nom du champ fautif dans le message.
    """
    d = DailyInput(humeur=humeur, sommeil=sommeil, stress=stress, concentration=concentration)
    with pytest.raises(InputValidationError) as exc:
        compute_scj(d)
    assert field_name in str(exc.value)


def test_sleep_upper_bound_allowed():
    """
    Le max sommeil (MAX_SLEEP_HOURS) doit être accepté.
    """
    d = DailyInput(humeur=5, sommeil=MAX_SLEEP_HOURS, stress=5, concentration=5)
    res = compute_scj(d)
    assert 0.0 <= res.scj <= 10.0


# -----------------------------------------------------------------------------
# Calcul nominal (formule par défaut) et propriétés
# -----------------------------------------------------------------------------

def test_compute_scj_default_formula_simple_case():
    """
    Formule par défaut annoncée :
        SCJ = (2*concentration + humeur + sommeil - stress) / somme(|poids|)
    Avec DEFAULT_WEIGHTS = {'concentration':2, 'humeur':1, 'sommeil':1, 'stress':-1}
    => dénominateur = 2 + 1 + 1 + 1 = 5
    Exemple : humeur=7, sommeil=6.5, stress=3, concentration=7.5
        num = (2*7.5) + 7 + 6.5 - 3 = 25.0
        SCJ = 25.0 / 5 = 5.0
    (NB : la valeur dépend de tes nombres ; ajuste si tu modifies l'exemple)
    """
    d = DailyInput(humeur=7, sommeil=6.5, stress=3, concentration=7.5)
    res = compute_scj(d)
    # Calcule attendu précis :
    numerator = (2 * 7.5) + 7 + 6.5 - 3
    expected_raw = numerator / (abs(2) + abs(1) + abs(1) + abs(-1))  # = /5
    assert approx_equal(res.raw, expected_raw)
    assert res.scj == round(min(max(expected_raw, 0.0), 10.0), 2)  # clamp + arrondi par défaut


def test_monotonicity_concentration_non_decreasing():
    """
    Si on augmente la concentration (ceteris paribus), le SCJ ne doit pas diminuer.
    """
    base = DailyInput(humeur=6, sommeil=7, stress=4, concentration=5)
    higher = DailyInput(humeur=6, sommeil=7, stress=4, concentration=7)

    scj_base = compute_scj(base).scj
    scj_higher = compute_scj(higher).scj

    assert scj_higher >= scj_base


def test_monotonicity_stress_non_increasing():
    """
    Si on augmente le stress (ceteris paribus), le SCJ ne doit pas augmenter.
    """
    base = DailyInput(humeur=6, sommeil=7, stress=2, concentration=6)
    more_stress = DailyInput(humeur=6, sommeil=7, stress=5, concentration=6)

    scj_base = compute_scj(base).scj
    scj_more = compute_scj(more_stress).scj

    assert scj_more <= scj_base


def test_idempotence_same_input_same_output():
    """
    Même entrée => même résultat (déterminisme).
    """
    d = DailyInput(humeur=6, sommeil=6, stress=4, concentration=6)
    r1 = compute_scj(d)
    r2 = compute_scj(d)
    assert approx_equal(r1.scj, r2.scj)
    assert approx_equal(r1.raw, r2.raw)
    assert r1.weights == r2.weights == DEFAULT_WEIGHTS


# -----------------------------------------------------------------------------
# Personnalisation des poids, dénominateur, arrondi et clampage
# -----------------------------------------------------------------------------

def test_custom_weights_change_score_and_denominator():
    """
    Avec des poids custom, la valeur du score change et le dénominateur
    = somme des valeurs absolues des poids.
    """
    d = DailyInput(humeur=5, sommeil=8, stress=3, concentration=6)

    # Cas par défaut
    res_def = compute_scj(d)

    # Poids personnalisés : on surpondère le sommeil
    custom_w = {"concentration": 1.0, "humeur": 1.0, "sommeil": 3.0, "stress": -1.0}
    res_custom = compute_scj(d, weights=custom_w, rounding=6)  # plus de décimales pour observer la diff

    # Déterminisme du dénominateur
    denom = abs(1) + abs(1) + abs(3) + abs(-1)  # = 6
    numerator = (1 * d.concentration) + (1 * d.humeur) + (3 * d.sommeil) + (-1 * d.stress)
    expected_raw = numerator / denom

    assert approx_equal(res_custom.raw, expected_raw)
    # Et le score custom doit différer du score par défaut (dans la plupart des cas)
    assert not approx_equal(res_custom.raw, res_def.raw)


def test_no_clamp_allows_values_above_10_if_weights_allow():
    """
    clamp_output=False : on peut dépasser 10 si l'une des features est > 10
    (ex: sommeil <= 14h). Ici on donne tout le poids au sommeil pour illustrer.
    """
    d = DailyInput(humeur=0, sommeil=12.0, stress=0, concentration=0)
    w = {"sommeil": 1.0, "humeur": 0.0, "concentration": 0.0, "stress": 0.0}

    res_clamped = compute_scj(d, weights=w, clamp_output=True)   # par défaut => clampé à 10
    res_unclamped = compute_scj(d, weights=w, clamp_output=False)

    assert res_clamped.scj == 10.0
    assert res_unclamped.scj == 12.0  # pas de clamp => > 10 autorisé


def test_rounding_parameter_changes_display_not_raw():
    """
    'rounding' n'affecte que la valeur présentée (scj), pas la valeur brute (raw).
    """
    d = DailyInput(humeur=7, sommeil=6, stress=2, concentration=7)
    res_r2 = compute_scj(d, rounding=2)
    res_r4 = compute_scj(d, rounding=4)

    # Même valeur brute
    assert approx_equal(res_r2.raw, res_r4.raw)
    # Valeur arrondie différente (potentiellement)
    assert res_r2.scj == round(res_r2.raw if res_r2.scj <= 10 else 10.0, 2)
    assert res_r4.scj == round(res_r4.raw if res_r4.scj <= 10 else 10.0, 4)


# -----------------------------------------------------------------------------
# Interprétation textuelle
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score,expected_snippet",
    [
        (9.0, "Énergie mentale très élevée"),
        (8.0, "Bonne clarté d'esprit"),
        (6.0, "État correct"),
        (4.5, "Baisse de régime"),
        (3.0, "Fatigue cognitive marquée"),
    ],
)
def test_interpret_scj_buckets(score, expected_snippet):
    """
    Les tranches définies dans interpret_scj() doivent renvoyer un message cohérent.
    On vérifie par inclusion de sous-chaînes (robuste à de petites reformulations).
    """
    msg = interpret_scj(score)
    assert expected_snippet in msg


def test_interpret_scj_clamps_input():
    """
    Même si on passe un score <0 ou >10, interpret_scj() borne en interne.
    """
    assert "Fatigue cognitive" in interpret_scj(-5.0)   # clamp -> bas
    assert "Énergie mentale très élevée" in interpret_scj(25.0)  # clamp -> haut


# -----------------------------------------------------------------------------
# Tests de non-régression simples
# -----------------------------------------------------------------------------

def test_regression_guard_default_example():
    """
    Test de non-régression sur l'exemple documenté dans la docstring de compute_scj().
    """
    d = DailyInput(humeur=6.5, sommeil=7.0, stress=4.0, concentration=6.8)
    # Valeurs issues du calcul manuel
    res = compute_scj(d)
    expected_raw = ((2*6.8) + 6.5 + 7.0 - 4.0) / 5.0  # = 4.62
    assert abs(res.raw - expected_raw) < 1e-9
    assert res.scj == round(min(max(expected_raw, 0.0), 10.0), 2)

# -----------------------------------------------------------------------------
# --- Démo locale (facultative) ---
if __name__ == "__main__":
    # Exemple d'usage rapide
    day = DailyInput(humeur=8, sommeil=7, stress=0, concentration=9)
    res = compute_scj(day)
    print(f"SCJ={res.scj} (raw={res.raw:.3f})  |  {interpret_scj(res.scj)}")
# app/services/score_engine.py