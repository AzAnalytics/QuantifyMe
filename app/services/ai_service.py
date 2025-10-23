# app/services/ai_service.py
# -*- coding: utf-8 -*-
"""
Service d'interprétation IA pour QuantifyMe.

Deux providers :
- StubProvider : offline, déterministe, idéal pour tests/MVP.
- HuggingFaceProvider : utilise l'Inference API (si HF_TOKEN présent).

Usage:
    from app.services.ai_service import AIService
    from app.services.score_engine import DailyInput, compute_scj

    day = DailyInput(humeur=7, sommeil=6.5, stress=3, concentration=7.5)
    scj = compute_scj(day).scj

    svc = AIService()  # auto: stub si pas de token
    txt = svc.generate_interpretation(scj=scj, inputs=day)
    print(txt)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import json
import math

try:
    # httpx est plus robuste pour les timeouts ; installe-le si tu actives HF
    import httpx  # type: ignore
except Exception:  # pragma: no cover - httpx optionnel si stub only
    httpx = None  # type: ignore


# -----------------------------------------------------------------------------
# Modèle d'entrée (réutilisable depuis score_engine)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class DailyInputsLite:
    """
    Version minimale pour éviter le couplage fort avec score_engine.DailyInput
    (si tu préfères, importe directement DailyInput du module score_engine).
    """
    humeur: float
    sommeil: float
    stress: float
    concentration: float


# -----------------------------------------------------------------------------
# Provider: Stub (déterministe, offline)
# -----------------------------------------------------------------------------

class StubProvider:
    """
    Génère un texte court en fonction de SCJ et des entrées, sans aucun appel réseau.
    Déterministe -> parfait pour tests/unit et usage local.
    """

    def generate(self, *, scj: float, inputs: DailyInputsLite | None = None) -> str:
        parts = []

        # Tranche principale sur le score
        if scj >= 8.5:
            parts.append("Énergie mentale très élevée. Vise tes tâches les plus complexes.")
        elif scj >= 7.0:
            parts.append("Bonne clarté d'esprit. Programme 1–2 blocs de deep work.")
        elif scj >= 5.5:
            parts.append("État correct. Garde des pauses régulières pour rester stable.")
        elif scj >= 4.0:
            parts.append("Baisse de régime. Favorise les tâches simples aujourd'hui.")
        else:
            parts.append("Fatigue cognitive marquée. Priorise récupération et sommeil.")

        # Affinage rapide si inputs fournis
        if inputs is not None:
            if inputs.stress >= 7:
                parts.append("Ton stress est élevé: respiration 4-7-8 et courte marche conseillées.")
            if inputs.sommeil <= 5.5:
                parts.append("Sommeil court: évite le multitâche, hydrate-toi, sieste courte si possible.")
            if inputs.concentration >= 8 and scj >= 7:
                parts.append("Fenêtre de focus: essaye 60–90 min de travail profond.")

        return " ".join(parts)


# -----------------------------------------------------------------------------
# Provider: Hugging Face Inference API
# -----------------------------------------------------------------------------

class HuggingFaceProvider:
    """
    Client simple pour l'Inference API de Hugging Face.

    Variables d'environnement supportées:
        HF_TOKEN           : token secret (obligatoire)
        HF_MODEL           : ex. 'mistralai/Mistral-7B-Instruct-v0.2'
        HF_API_URL         : URL override; sinon déduite du modèle
        HF_MAX_TOKENS      : int (par défaut 200)
        HF_TEMPERATURE     : float (par défaut 0.3)
        HF_TOP_P           : float (par défaut 0.9)
        HF_TIMEOUT_SEC     : int/float (par défaut 12)

    Notes:
        - Nécessite `httpx` installé.
        - S'il y a la moindre erreur réseau, on relèvera l'exception afin
          que l'appelant puisse fallback vers le Stub selon sa politique.
    """

    def __init__(self) -> None:
        if httpx is None:
            raise RuntimeError("httpx n'est pas installé. `pip install httpx` pour utiliser HuggingFaceProvider.")

        self.token = os.getenv("HF_TOKEN", "").strip()
        if not self.token:
            raise RuntimeError("HF_TOKEN manquant pour HuggingFaceProvider.")

        self.model = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2").strip()
        self.api_url = os.getenv("HF_API_URL", f"https://api-inference.huggingface.co/models/{self.model}").strip()
        self.max_tokens = int(os.getenv("HF_MAX_TOKENS", "200"))
        self.temperature = float(os.getenv("HF_TEMPERATURE", "0.3"))
        self.top_p = float(os.getenv("HF_TOP_P", "0.9"))
        self.timeout_sec = float(os.getenv("HF_TIMEOUT_SEC", "12"))

        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _build_prompt(self, *, scj: float, inputs: DailyInputsLite | None) -> str:
        base = (
            "Tu es un coach bienveillant. En une à deux phrases, donne un conseil concret, "
            "clair et non médical, basé sur le score cognitif et les mesures du jour."
        )
        if inputs is None:
            return f"{base}\n\nScore cognitif (SCJ): {scj:.2f}.\nRéponds en français."

        return (
            f"{base}\n\n"
            f"Score cognitif (SCJ): {scj:.2f}\n"
            f"Humeur: {inputs.humeur:.1f}/10, Stress: {inputs.stress:.1f}/10, "
            f"Sommeil: {inputs.sommeil:.1f}h, Concentration: {inputs.concentration:.1f}/10\n"
            "Réponds en français, 2 phrases maximum."
        )

    def generate(self, *, scj: float, inputs: DailyInputsLite | None = None) -> str:
        payload = {
            "inputs": self._build_prompt(scj=scj, inputs=inputs),
            "parameters": {
                "max_new_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "return_full_text": False,
                # Pour certains endpoints, c'est "do_sample"; l'Inference API est permissive
                "do_sample": True,
            },
            "options": {"wait_for_model": True},
        }

        # Appel réseau
        with httpx.Client(timeout=self.timeout_sec) as client:
            resp = client.post(self.api_url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Formats possibles : liste de dicts [{"generated_text": "..."}] ou autre
        if isinstance(data, list) and data and "generated_text" in data[0]:
            return str(data[0]["generated_text"]).strip()

        # Cas d'API TGI ou variantes : champs différents
        # On tente de trouver une string dans la réponse
        if isinstance(data, dict):
            for key in ("generated_text", "text", "content"):
                if key in data and isinstance(data[key], str):
                    return data[key].strip()

        # Fallback: renvoyer du JSON brut lisible
        return json.dumps(data, ensure_ascii=False)[:500].strip()


# -----------------------------------------------------------------------------
# Façade principale
# -----------------------------------------------------------------------------

class AIService:
    """
    Façade qui choisit automatiquement le provider selon l'environnement :
      - AI_PROVIDER=hf  -> HuggingFaceProvider (si HF_TOKEN présent)
      - sinon           -> StubProvider (par défaut)

    Tu peux forcer un provider en passant `provider=...` dans __init__.
    """

    def __init__(self, provider: Optional[object] = None) -> None:
        if provider is not None:
            self._provider = provider
            return

        prov = os.getenv("AI_PROVIDER", "stub").strip().lower()
        if prov == "hf":
            try:
                self._provider = HuggingFaceProvider()
            except Exception:
                # Fallback silencieux vers le stub si la config HF est incomplète
                self._provider = StubProvider()
        else:
            self._provider = StubProvider()

    def generate_interpretation(
        self,
        *,
        scj: float,
        inputs: Optional[DailyInputsLite] = None,
    ) -> str:
        """
        Génère un texte court d'interprétation (2 phrases max idéalement).

        Args:
            scj: score cognitif journalier (0..10 typiquement)
            inputs: mesures brutes utiles pour contextualiser le conseil

        Returns:
            str: message court prêt à afficher dans l'UI
        """
        # garde-fou : borne un minimum le score
        scj_safe = float(max(0.0, min(10.0, scj)))
        return self._provider.generate(scj=scj_safe, inputs=inputs)
