# tests/test_ai_service.py
# -*- coding: utf-8 -*-
"""
Tests complets et documentés pour app/services/ai_service.py

Ce fichier couvre :
1) StubProvider :
   - messages par tranches de score
   - affinement en fonction des inputs (stress, sommeil, concentration)
2) AIService (façade) :
   - choix du provider par variables d'environnement (stub par défaut, hf si demandé)
   - fallback automatique vers stub si la config HF est absente/incomplète
   - clamp du score (SCJ < 0 -> 0 ; SCJ > 10 -> 10)
   - injection d'un provider custom (pour tester le clamp sans introspection interne)
3) HuggingFaceProvider :
   - fonctionnement sans réseau via mock de `httpx`
   - parsing de plusieurs formats de réponses (liste avec 'generated_text', dict variante)
   - propagation des erreurs réseau si on utilise directement le provider

Notes :
- AUCUN appel réseau réel : on monkey-patche `ai_service.httpx` avec une implémentation factice.
- Les variables d'environnement sont gérées via `monkeypatch` pour garantir l'isolation.
"""

from __future__ import annotations

import os
import types
import json

import pytest

# On importe les classes/fonctions à tester
import app.services.ai_service as ai_svc
from app.services.ai_service import (
    AIService,
    StubProvider,
    HuggingFaceProvider,
    DailyInputsLite,
)

# ---------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """
    Nettoie les variables d'environnement pertinentes AVANT chaque test.
    Cela garantit que les tests ne se contaminent pas entre eux.
    """
    for key in [
        "AI_PROVIDER",
        "HF_TOKEN",
        "HF_MODEL",
        "HF_API_URL",
        "HF_MAX_TOKENS",
        "HF_TEMPERATURE",
        "HF_TOP_P",
        "HF_TIMEOUT_SEC",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------
# 1) Tests StubProvider
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "scj, expected_snippet",
    [
        (9.0, "Énergie mentale très élevée"),
        (7.5, "Bonne clarté d'esprit"),
        (6.0, "État correct"),
        (4.2, "Baisse de régime"),
        (3.9, "Fatigue cognitive marquée"),
    ],
)
def test_stubprovider_buckets(scj, expected_snippet):
    """
    Le StubProvider renvoie un message cohérent par tranche de SCJ.
    On teste par inclusion de sous-chaînes (robuste à de petites reformulations).
    """
    stub = StubProvider()
    txt = stub.generate(scj=scj, inputs=None)
    assert expected_snippet in txt


def test_stubprovider_refinements_with_inputs():
    """
    Le StubProvider ajoute des conseils additionnels selon les inputs :
      - stress élevé -> mention respiration / marche
      - sommeil court -> mention sieste / hydratation
      - concentration élevée + bon SCJ -> mention deep work
    """
    stub = StubProvider()
    inputs = DailyInputsLite(humeur=6.0, sommeil=5.0, stress=8.0, concentration=8.5)
    txt = stub.generate(scj=7.2, inputs=inputs)

    assert "stress est élevé" in txt
    assert "Sommeil court" in txt
    assert "Fenêtre de focus" in txt


# ---------------------------------------------------------------------
# 2) Tests AIService (façade)
# ---------------------------------------------------------------------

def test_aiservice_default_is_stub():
    """
    Sans variable d'environnement, AIService doit choisir le StubProvider.
    """
    svc = AIService()
    assert isinstance(svc._provider, StubProvider)  # attribut interne OK à tester ici


def test_aiservice_env_forces_stub(monkeypatch):
    """
    Même si AI_PROVIDER est 'stub', on vérifie qu'on obtient bien le StubProvider.
    """
    monkeypatch.setenv("AI_PROVIDER", "stub")
    svc = AIService()
    assert isinstance(svc._provider, StubProvider)


def test_aiservice_env_hf_without_token_fallbacks_to_stub(monkeypatch):
    """
    Si AI_PROVIDER=hf mais HF_TOKEN est absent, la façade doit retomber sur le stub.
    (Le constructeur HF lève, AIService fallback silencieusement.)
    """
    monkeypatch.setenv("AI_PROVIDER", "hf")
    svc = AIService()
    assert isinstance(svc._provider, StubProvider)


def test_aiservice_clamps_scj_for_any_provider(monkeypatch):
    """
    AIService doit borner le SCJ entre 0 et 10 AVANT d'appeler le provider.
    On injecte un "provider espion" qui capture la valeur reçue.
    """
    class SpyProvider:
        def __init__(self):
            self.last_scj = None

        def generate(self, *, scj: float, inputs=None) -> str:
            self.last_scj = scj
            return f"SCJ capturé: {scj}"

    spy = SpyProvider()
    svc = AIService(provider=spy)

    # score trop haut -> clamp à 10
    out = svc.generate_interpretation(scj=23.7, inputs=None)
    assert "SCJ capturé: 10.0" in out
    assert spy.last_scj == 10.0

    # score trop bas -> clamp à 0
    out = svc.generate_interpretation(scj=-5.0, inputs=None)
    assert "SCJ capturé: 0.0" in out
    assert spy.last_scj == 0.0


# ---------------------------------------------------------------------
# 3) Tests HuggingFaceProvider (avec mock httpx, SANS réseau)
# ---------------------------------------------------------------------

class _FakeResponse:
    """
    Réponse factice qui imite l'API httpx.Response nécessaire à notre usage :
      - .json()
      - .raise_for_status() (no-op si statut OK)
    """
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None  # no-op


class _FakeClient:
    """
    Client factice utilisé via le context manager "with httpx.Client(...) as client:"
    """
    def __init__(self, *, payload_to_return):
        self.payload_to_return = payload_to_return

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False  # ne supprime pas les exceptions

    def post(self, url, headers=None, json=None):
        # On pourrait vérifier ici les headers/token si besoin
        return _FakeResponse(self.payload_to_return)


def test_hf_provider_parses_list_format(monkeypatch):
    """
    HuggingFaceProvider doit extraire 'generated_text' quand la réponse est une liste
    de dicts [{'generated_text': '...'}].
    """
    # On force la config HF
    monkeypatch.setenv("AI_PROVIDER", "hf")
    monkeypatch.setenv("HF_TOKEN", "dummy_token")
    monkeypatch.setenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")

    # On monkey-patche le module httpx dans ai_service en un module factice
    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout=None: _FakeClient(payload_to_return=[{"generated_text": "Texte HF"}])
    )
    monkeypatch.setattr(ai_svc, "httpx", fake_httpx, raising=True)

    # AIService doit construire le HuggingFaceProvider cette fois
    svc = AIService()
    assert isinstance(svc._provider, HuggingFaceProvider)

    txt = svc.generate_interpretation(scj=7.1, inputs=DailyInputsLite(6, 7, 3, 7))
    assert "Texte HF" == txt


def test_hf_provider_parses_dict_variants(monkeypatch):
    """
    HuggingFaceProvider doit aussi savoir traiter un dict simple avec un des champs connus.
    """
    monkeypatch.setenv("AI_PROVIDER", "hf")
    monkeypatch.setenv("HF_TOKEN", "dummy_token")

    # Variante: la réponse renvoie un dict avec 'text'
    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout=None: _FakeClient(payload_to_return={"text": "Réponse variante"})
    )
    monkeypatch.setattr(ai_svc, "httpx", fake_httpx, raising=True)

    svc = AIService()
    assert isinstance(svc._provider, HuggingFaceProvider)

    out = svc.generate_interpretation(scj=8.0, inputs=None)
    assert out == "Réponse variante"


def test_hf_provider_raises_when_used_directly_and_http_fails(monkeypatch):
    """
    Si on utilise directement HuggingFaceProvider (sans passer par AIService),
    et que l'appel réseau échoue, l'exception doit être propagée (comportement voulu).
    """
    # On fabrique un faux httpx qui lève à l'appel .post()
    class _FailingClient:
        def __init__(self): ...
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, *args, **kwargs):
            raise RuntimeError("échec réseau simulé")

    fake_httpx = types.SimpleNamespace(Client=lambda timeout=None: _FailingClient())
    monkeypatch.setattr(ai_svc, "httpx", fake_httpx, raising=True)

    # Prépare les env pour permettre l'init HF
    monkeypatch.setenv("HF_TOKEN", "token")
    provider = HuggingFaceProvider()

    with pytest.raises(RuntimeError):
        provider.generate(scj=7.0, inputs=None)
