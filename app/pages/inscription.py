# app/pages/3_Inscription.py
# -*- coding: utf-8 -*-

# --- bootstrap import path (pages Streamlit) ---
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# ------------------------------------------------

import pandas as pd
import streamlit as st

from app.persistence.db import init_db
from app.persistence.models import Base
from app.persistence.repositories.users_repo import UserRepository

# DB ready
init_db(Base, drop_and_recreate=False)
users = UserRepository()

st.set_page_config(page_title="Inscription / Premium — QuantifyMe", page_icon="⭐", layout="centered")
st.title("⭐ Devenir Premium")

# Récupération utilisateur courant (depuis la session), fallback si besoin
default_email = "demo@example.com"
if "user_id" not in st.session_state or "user_email" not in st.session_state:
    u = users.get_or_create(default_email, is_premium=False)
    st.session_state["user_id"] = u.id
    st.session_state["user_email"] = u.email

user_id = st.session_state["user_id"]
user_email = st.session_state["user_email"]
u = users.get_by_email(user_email)

st.caption(f"Connecté en tant que **{user_email}** (id={user_id})")

# --- Hero / pitch ---
st.markdown(
    """
    Boostez votre **clarté mentale** et vos **résultats** avec **QuantifyMe Premium**.  
    Accédez à des analyses avancées, à des recommandations intelligentes (IA) et à des comparaisons de périodes automatiques.
    """
)

# --- Tableau des avantages ---
features = [
    ("Journal quotidien illimité", True, True),
    ("Graphiques par jour (Altair)", True, True),
    ("Comparaison de périodes (A vs B)", False, True),
    ("Interprétations IA personnalisées", False, True),
    ("Moyenne glissante et tendances avancées", False, True),
    ("Export CSV / future API d’export", False, True),
    ("Support prioritaire", False, True),
]
df = pd.DataFrame(features, columns=["Fonctionnalité", "Gratuit", "Premium"])
df["Gratuit"] = df["Gratuit"].map(lambda x: "✅" if x else "—")
df["Premium"] = df["Premium"].map(lambda x: "✅" if x else "—")

st.subheader("📦 Avantages")
st.table(df)

# --- Tarifs (exemple / placeholder) ---
colA, colB = st.columns(2)
with colA:
    st.markdown(
        """
        ### Gratuit
        - 0€/mois
        - Journal + graphiques de base
        - Données locales
        """
    )
with colB:
    st.markdown(
        """
        ### Premium
        - **7€/mois** (exemple)
        - IA, comparaisons, export, support
        - Mises à jour en priorité
        """
    )

st.divider()

# --- CTA / Abonnement ---
if u.is_premium:
    st.success("🎉 Vous êtes déjà **Premium**. Merci pour votre soutien !")
else:
    st.info("Passez à **Premium** pour débloquer les fonctionnalités avancées.")
    # Dans un vrai flux, ici on redirigerait vers un checkout (Stripe/Paypal).
    # Pour le MVP : on bascule directement le statut.
    if st.button("S’abonner maintenant"):
        try:
            users.set_premium(user_email, True)
            st.success("✅ Abonnement activé. Vous êtes maintenant **Premium**.")
            # met à jour l'état local et rafraîchit la page
            st.session_state["premium"] = True
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d’activer l’abonnement : {e}")

st.caption("💡 Astuce : vous pouvez à tout moment revenir sur le **Profil** pour vérifier votre statut.")
