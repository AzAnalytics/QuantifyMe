# app/pages/1_Profil.py
# -*- coding: utf-8 -*-

# --- bootstrap import path (page streamlit dans app/pages) ---
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -------------------------------------------------------------

import datetime as dt
import pandas as pd
import streamlit as st

from app.persistence.db import init_db
from app.persistence.models import Base
from app.persistence.repositories.users_repo import UserRepository
from app.persistence.repositories.records_repo import RecordRepository

# Boot DB (no drop)
init_db(Base, drop_and_recreate=False)
users = UserRepository()
records = RecordRepository()

st.set_page_config(page_title="Profil — QuantifyMe", page_icon="👤", layout="centered")
st.title("👤 Profil")

# Récup user courant (depuis main) ou fallback
default_email = "demo@example.com"
if "user_id" not in st.session_state or "user_email" not in st.session_state:
    u = users.get_or_create(default_email, is_premium=False)
    st.session_state["user_id"] = u.id
    st.session_state["user_email"] = u.email

user_id = st.session_state["user_id"]
user_email = st.session_state["user_email"]

st.caption(f"Connecté en tant que **{user_email}** (id={user_id})")

# --- Carte d'infos utilisateur ---
u = users.get_by_email(user_email)
colA, colB = st.columns(2)
with colA:
    st.subheader("Informations")
    st.write(f"**Email :** {u.email}")
    st.write(f"**Créé le :** {u.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(u,'created_at') else '—'}")

with colB:
    st.subheader("Statut")
    premium = st.toggle("Premium", value=bool(u.is_premium))
    if premium != bool(u.is_premium):
        users.set_premium(u.email, premium)
        st.success(f"Statut premium mis à jour → {premium}")
        st.rerun()