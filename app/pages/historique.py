# app/pages/2_Historique.py
# -*- coding: utf-8 -*-

# --- bootstrap import path (page streamlit dans app/pages) ---
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -------------------------------------------------------------

import datetime as dt
import io
import pandas as pd
import streamlit as st
import altair as alt


from app.persistence.db import init_db
from app.persistence.models import Base
from app.persistence.repositories.users_repo import UserRepository
from app.persistence.repositories.records_repo import RecordRepository

# Boot DB
init_db(Base, drop_and_recreate=False)
users = UserRepository()
records = RecordRepository()

st.set_page_config(page_title="Historique — QuantifyMe", page_icon="📜", layout="wide")
st.title("📜 Historique")

# User courant ou fallback
default_email = "demo@example.com"
if "user_id" not in st.session_state or "user_email" not in st.session_state:
    u = users.get_or_create(default_email, is_premium=False)
    st.session_state["user_id"] = u.id
    st.session_state["user_email"] = u.email

user_id = st.session_state["user_id"]
user_email = st.session_state["user_email"]
st.caption(f"Connecté en tant que **{user_email}** (id={user_id})")

# --- Filtres ---
st.sidebar.header("Filtres")
today = dt.date.today()
default_start = today - dt.timedelta(days=30)

start = st.sidebar.date_input("Du", value=default_start)
end = st.sidebar.date_input("Au", value=today)
asc = st.sidebar.toggle("Ordre chronologique (ascendant)", value=True)

# Chargement des données filtrées
rows = records.get_range(user_id, start=start, end=end, asc=asc)

if not rows:
    st.info("Aucune donnée dans cette période.")
else:
    df = pd.DataFrame([{
        "date": r.date,
        "humeur": r.humeur,
        "sommeil_h": r.sommeil,
        "stress": r.stress,
        "concentration": r.concentration,
        "SCJ": r.scj,
        "interpretation": r.interpretation,
    } for r in rows]).sort_values("date")

    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Nb. jours", len(df))
    with col2:
        st.metric("SCJ moyen période", f"{df['SCJ'].mean():.2f}")
    with col3:
        st.metric("SCJ max", f"{df['SCJ'].max():.2f}")

# Agrégation par jour pour un affichage clair
df_day = df.copy()
df_day["day"] = pd.to_datetime(df_day["date"])  # s'assure du type datetime
df_day["day"] = df_day["day"].dt.normalize()    # force 00:00:00 (pas obligatoire mais propre)

# Si jamais plusieurs enregistrements le même jour → on moyenne
df_day_agg = (
    df_day.groupby("day", as_index=False)[["SCJ", "humeur", "stress", "concentration"]]
        .mean()
        .sort_values("day")
)

# Chart SCJ (par jour) — on fige l'unité de temps à "date" (sans heures)
scj_chart = (
    alt.Chart(df_day_agg)
    .mark_line(point=True)
    .encode(
        x=alt.X("yearmonthdate(day):T",
                title="Jour",
                axis=alt.Axis(format="%Y-%m-%d", labelAngle=-45)),
        y=alt.Y("SCJ:Q", title="SCJ"),
        tooltip=[alt.Tooltip("day:T", title="Jour", format="%Y-%m-%d"),
                 alt.Tooltip("SCJ:Q", format=".2f")]
    )
    .properties(height=280)
)

st.subheader("Évolution du SCJ (par jour)")
st.altair_chart(scj_chart, use_container_width=True)

# Chart Humeur/Stress/Concentration (par jour)
hsc_long = df_day_agg.melt(id_vars="day", value_vars=["humeur", "stress", "concentration"],
                            var_name="métrique", value_name="valeur")

hsc_chart = (
    alt.Chart(hsc_long)
    .mark_bar()
    .encode(
        x=alt.X("yearmonthdate(day):T",
                title="Jour",
                axis=alt.Axis(format="%Y-%m-%d", labelAngle=-45)),
        y=alt.Y("valeur:Q", title="Valeur moyenne"),
        color=alt.Color("métrique:N", title=""),
        tooltip=[alt.Tooltip("day:T", title="Jour", format="%Y-%m-%d"),
                 "métrique:N", alt.Tooltip("valeur:Q", format=".2f")]
    )
    .properties(height=280)
)

st.subheader("Humeur / Stress / Concentration (par jour)")
st.altair_chart(hsc_chart, use_container_width=True)

# Export CSV
csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
st.download_button("⬇️ Export CSV", data=csv_buf.getvalue(), file_name="historique_quantifyme.csv", mime="text/csv")

# =========================
# 🔀 Comparaison de périodes
# =========================
st.header("🔀 Comparaison de périodes")

preset = st.radio(
    "Choix rapide",
    options=["7 derniers vs précédents", "30 derniers vs précédents", "Personnalisé"],
    horizontal=True,
)

def fetch_df_by_range(uid: int, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    rows_rng = records.get_range(uid, start=start_date, end=end_date, asc=True)
    if not rows_rng:
        return pd.DataFrame(columns=["day", "SCJ", "humeur", "stress", "concentration"])
    df_rng = pd.DataFrame([{
        "date": r.date,
        "SCJ": r.scj,
        "humeur": r.humeur,
        "stress": r.stress,
        "concentration": r.concentration,
    } for r in rows_rng]).sort_values("date")
    df_rng["day"] = pd.to_datetime(df_rng["date"]).dt.normalize()
    # agrégation par jour
    return (df_rng.groupby("day", as_index=False)[["SCJ", "humeur", "stress", "concentration"]]
                    .mean()
                    .sort_values("day"))

today = dt.date.today()

if preset == "7 derniers vs précédents":
    end_A = today
    start_A = end_A - dt.timedelta(days=6)
    end_B = start_A - dt.timedelta(days=1)
    start_B = end_B - dt.timedelta(days=6)
elif preset == "30 derniers vs précédents":
    end_A = today
    start_A = end_A - dt.timedelta(days=29)
    end_B = start_A - dt.timedelta(days=1)
    start_B = end_B - dt.timedelta(days=29)
else:
    colA, colB = st.columns(2)
    with colA:
        start_A = st.date_input("Période A — début", value=today - dt.timedelta(days=6), key="cmp_A_start")
        end_A   = st.date_input("Période A — fin",   value=today, key="cmp_A_end")
    with colB:
        start_B = st.date_input("Période B — début", value=today - dt.timedelta(days=13), key="cmp_B_start")
        end_B   = st.date_input("Période B — fin",   value=today - dt.timedelta(days=7), key="cmp_B_end")
    if start_A > end_A or start_B > end_B:
        st.warning("Vérifie les bornes : la date de début doit être ≤ à la date de fin.")
        st.stop()

df_A = fetch_df_by_range(user_id, start_A, end_A)
df_B = fetch_df_by_range(user_id, start_B, end_B)

if df_A.empty or df_B.empty:
    st.info("Données insuffisantes pour l’une des périodes sélectionnées.")
else:
    # Aligner sur un axe 'Jour 1..N' pour comparaison
    df_A = df_A.reset_index(drop=True).copy()
    df_B = df_B.reset_index(drop=True).copy()
    df_A["rank_day"] = df_A.index + 1
    df_B["rank_day"] = df_B.index + 1
    df_A["période"] = f"A ({start_A} → {end_A})"
    df_B["période"] = f"B ({start_B} → {end_B})"

    # Concat pour chart
    df_cmp = pd.concat([df_A[["rank_day", "SCJ", "période"]],
                        df_B[["rank_day", "SCJ", "période"]]], ignore_index=True)

    st.subheader("SCJ moyen — comparaison alignée (Jour 1…N)")
    chart = (
        alt.Chart(df_cmp)
        .mark_line(point=True)
        .encode(
            x=alt.X("rank_day:O", title="Jour (aligné)"),
            y=alt.Y("SCJ:Q", title="SCJ"),
            color=alt.Color("période:N", title=""),
            tooltip=["période:N", alt.Tooltip("rank_day:O", title="Jour"), alt.Tooltip("SCJ:Q", format=".2f")],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, use_container_width=True)

    # KPIs comparatives
    col1, col2, col3 = st.columns(3)
    avg_A = float(df_A["SCJ"].mean()) if not df_A.empty else float("nan")
    avg_B = float(df_B["SCJ"].mean()) if not df_B.empty else float("nan")
    max_A = float(df_A["SCJ"].max())  if not df_A.empty else float("nan")
    max_B = float(df_B["SCJ"].max())  if not df_B.empty else float("nan")
    delta = avg_A - avg_B

    with col1:
        st.metric("Moyenne A", f"{avg_A:.2f}")
    with col2:
        st.metric("Moyenne B", f"{avg_B:.2f}")
    with col3:
        st.metric("Δ A vs B", f"{delta:+.2f}")

    # Optionnel : table de synthèse
    with st.expander("Voir les détails des périodes"):
        st.write("**Période A**", f"({start_A} → {end_A})")
        st.dataframe(df_A[["day", "SCJ", "humeur", "stress", "concentration"]], use_container_width=True)
        st.write("**Période B**", f"({start_B} → {end_B})")
        st.dataframe(df_B[["day", "SCJ", "humeur", "stress", "concentration"]], use_container_width=True)
