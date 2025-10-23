# app/main.py
# -*- coding: utf-8 -*-
# --- bootstrap import path (run as script via streamlit) ---
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -----------------------------------------------------------
import datetime as dt
import pandas as pd
import streamlit as st

# DB init (assure que les tables existent)
from app.persistence.db import init_db
from app.persistence.models import Base
from app.persistence.repositories.users_repo import UserRepository
from app.persistence.repositories.records_repo import RecordRepository

# Score engine
from app.services.score_engine import DailyInput, compute_scj, interpret_scj

# IA (facultative, fallback stub si mal configurée)
from app.services.ai_service import AIService, DailyInputsLite

# ---------------------------------------------------------------------
# Bootstrapping
# ---------------------------------------------------------------------
init_db(Base, drop_and_recreate=False)
users_repo = UserRepository()
records_repo = RecordRepository()

st.set_page_config(page_title="QuantifyMe", page_icon="🧠", layout="centered")

# ---------------------------------------------------------------------
# Sidebar – Sélection / création utilisateur
# ---------------------------------------------------------------------
st.sidebar.title("👤 Utilisateur")
default_email = os.getenv("QME_DEFAULT_EMAIL", "demo@example.com")
email = st.sidebar.text_input("Email", value=default_email, help="Créé s'il n'existe pas")
make_premium = st.sidebar.checkbox("Premium ?", value=False)

if st.sidebar.button("Charger/Créer l'utilisateur"):
    u = users_repo.get_or_create(email, is_premium=make_premium)
    st.session_state["user_id"] = u.id
    st.session_state["user_email"] = u.email
    st.sidebar.success(f"OK : {u.email} (id={u.id})")

# état par défaut au premier chargement
if "user_id" not in st.session_state:
    u = users_repo.get_or_create(default_email, is_premium=False)
    st.session_state["user_id"] = u.id
    st.session_state["user_email"] = u.email

user_id = st.session_state["user_id"]
user_email = st.session_state["user_email"]

st.caption(f"Connecté en tant que **{user_email}** (id={user_id})")

# ---------------------------------------------------------------------
# Formulaire de saisie quotidienne
# ---------------------------------------------------------------------
st.title("🧠 QuantifyMe — Journal cognitif")

with st.form("daily_form", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        date = st.date_input("Date", value=dt.date.today())
        humeur = st.slider("Humeur", min_value=0.0, max_value=10.0, value=6.5, step=0.1)
        stress = st.slider("Stress", min_value=0.0, max_value=10.0, value=4.0, step=0.1)
    with col2:
        sommeil = st.slider("Sommeil (h)", min_value=0.0, max_value=14.0, value=7.0, step=0.1)
        concentration = st.slider("Concentration", min_value=0.0, max_value=10.0, value=6.5, step=0.1)

    use_ai = st.checkbox("Générer une interprétation IA", value=True, help="Stub par défaut ; Hugging Face si configuré")
    submitted = st.form_submit_button("Enregistrer la journée")

if submitted:
    # Calcul SCJ
    day = DailyInput(humeur=humeur, sommeil=sommeil, stress=stress, concentration=concentration)
    res = compute_scj(day)

    # Interprétation : IA si coché, sinon règle simple locale
    interpretation = None
    if use_ai:
        try:
            svc = AIService()  # Stub si pas de HF_TOKEN
            interpretation = svc.generate_interpretation(
                scj=res.scj,
                inputs=DailyInputsLite(humeur=humeur, sommeil=sommeil, stress=stress, concentration=concentration),
            )
        except Exception as e:
            interpretation = f"(IA indisponible) {interpret_scj(res.scj)}"
            st.warning(f"IA non configurée ou erreur : {e}")
    else:
        interpretation = interpret_scj(res.scj)

    # Enregistrement (upsert par date)
    rec = records_repo.upsert(
        user_id=user_id,
        date=date,
        humeur=humeur,
        sommeil=sommeil,
        stress=stress,
        concentration=concentration,
        scj=float(res.scj),
        interpretation=interpretation,
    )

    st.success(f"✅ Enregistré pour {date.isoformat()} — SCJ = {res.scj}")
    if interpretation:
        st.info(interpretation)

