# app/services/score_engine.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

# Échelles par défaut
MIN_SCALE = 0.0
MAX_SCALE = 10.0
MAX_SLEEP_HOURS = 14.0  # cap "raisonnable" pour éviter de fausser le score

# Poids par défaut (doivent totaliser 5 en valeur absolue pour garder l'échelle 0..10)
DEFAULT_WEIGHTS: Dict[str, float] = {
    "concentration": 2.0,
    "humeur": 1.0,
    "sommeil": 1.0,
    "stress": -1.0,  # négatif => le stress fait baisser le score
}


@dataclass(frozen=True)
class DailyInput:
    """Entrées d'une journée utilisateur."""
    humeur: float           # 0..10
    sommeil: float          # 0..14 (heures, cap)
    stress: float           # 0..10
    concentration: float    # 0..10


@dataclass(frozen=True)
class ScoreResult:
    """Résultat du calcul du score."""
    scj: float              # Score Cognitif Journalier (0..10)
    raw: float              # valeur avant arrondi
    weights: Dict[str, float]


class InputValidationError(ValueError):
    """Erreur de validation des données d'entrée."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def validate_input(d: DailyInput) -> None:
    """Valide les bornes des entrées. Lève InputValidationError si invalide."""
    errors = []

    def _check(name: str, v: float, lo: float, hi: float):
        if not (lo <= v <= hi):
            errors.append(f"{name} hors bornes: {v} (attendu {lo}..{hi})")

    _check("humeur", d.humeur, MIN_SCALE, MAX_SCALE)
    _check("stress", d.stress, MIN_SCALE, MAX_SCALE)
    _check("concentration", d.concentration, MIN_SCALE, MAX_SCALE)
    _check("sommeil (heures)", d.sommeil, 0.0, MAX_SLEEP_HOURS)

    if errors:
        raise InputValidationError("; ".join(errors))


def compute_scj(
    d: DailyInput,
    weights: Optional[Dict[str, float]] = None,
    rounding: int = 2,
    clamp_output: bool = True,
) -> ScoreResult:
    """
    Calcule le Score Cognitif Journalier (SCJ) sur une échelle ~0..10.

    Formule par défaut (cohérente avec le README) :
        SCJ = (2*concentration + humeur + sommeil - stress) / 5

    - Les poids sont configurables. Le dénominateur est la somme des valeurs absolues des poids,
      pour conserver naturellement une échelle comparable (0..10 environ).
    - Les entrées sont validées et "clampées" en amont via validate_input (erreur si hors bornes).

    Args:
        d: DailyInput
        weights: dict facultatif {"concentration":2, "humeur":1, "sommeil":1, "stress":-1}
        rounding: décimales d'arrondi
        clamp_output: si True, borne le résultat final à [0, 10]

    Returns:
        ScoreResult(scj, raw, weights)
    """
    validate_input(d)

    w = dict(DEFAULT_WEIGHTS if weights is None else weights)

    # Numérateur (pondérations signées)
    numerator = (
        w.get("concentration", 0.0) * d.concentration
        + w.get("humeur", 0.0) * d.humeur
        + w.get("sommeil", 0.0) * d.sommeil
        + w.get("stress", 0.0) * d.stress
    )

    # Dénominateur = somme des poids en valeur absolue (préserve l'échelle)
    denom = sum(abs(x) for x in w.values()) or 1.0

    raw_score = numerator / denom

    # Optionnel : borne le score final entre 0 et 10
    final = _clamp(raw_score, MIN_SCALE, MAX_SCALE) if clamp_output else raw_score
    final = round(final, rounding)

    return ScoreResult(scj=final, raw=raw_score, weights=w)


def interpret_scj(scj: float) -> str:
    """
    Retourne une interprétation courte du score.
    (Tu pourras plus tard la remplacer par la génération IA.)
    """
    s = _clamp(scj, MIN_SCALE, MAX_SCALE)
    if s >= 8.5:
        return "Énergie mentale très élevée. Profite de ce pic pour les tâches complexes."
    if s >= 7.0:
        return "Bonne clarté d'esprit. Planifie 1–2 blocs de deep work."
    if s >= 5.5:
        return "État correct. Garde des pauses régulières pour rester stable."
    if s >= 4.0:
        return "Baisse de régime. Privilégie les tâches simples et récupère."
    return "Fatigue cognitive marquée. Sommeil, hydratation et pause longue recommandés."


# --- Démo locale (facultative) ---
if __name__ == "__main__":
    # Exemple d'usage rapide
    day = DailyInput(humeur=8, sommeil=7, stress=0, concentration=9)
    res = compute_scj(day)
    print(f"SCJ={res.scj} (raw={res.raw:.3f})  |  {interpret_scj(res.scj)}")
# app/services/score_engine.py