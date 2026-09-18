import json
from pathlib import Path

import requests
import streamlit as st

API_URL = "https://reco-articles-klt56.azurewebsites.net/api/recommend"
API_LOCAL = "http://localhost:7071/api/recommend"

st.set_page_config(page_title="My Content — Recommandations", layout="centered")
st.title("My Content")
st.caption("Système de recommandation d'articles — MVP")

ids = json.loads((Path(__file__).parent / "user_ids.json").read_text())

col1, col2 = st.columns([2, 1])
with col1:
    source = st.radio("API", ["Azure", "Local"], horizontal=True)
with col2:
    st.write("")

url = API_URL if source == "Azure" else API_LOCAL

mode = st.radio(
    "Choix de l'utilisateur",
    ["Liste", "Saisie libre"],
    horizontal=True,
)

if mode == "Liste":
    user_id = st.selectbox("Identifiant utilisateur", ids)
else:
    user_id = st.number_input(
        "Identifiant utilisateur",
        min_value=0,
        value=3,
        step=1,
        help="Essayez 3, 5 ou 6 (content-based), ou 999999999 (popularité)",
    )

if st.button("Obtenir 5 recommandations", type="primary"):
    with st.spinner("Appel en cours…"):
        try:
            r = requests.get(url, params={"user_id": int(user_id)}, timeout=120)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            st.error(f"Erreur d'appel : {e}")
            st.stop()

    if "erreur" in data:
        st.error(data["erreur"])
        st.stop()

    libelles = {
        "collaboratif": "Filtrage collaboratif (ALS)",
        "content_based": "Content-based (similarité des embeddings)",
        "popularite": "Popularité (utilisateur inconnu)",
    }
    st.info(f"Méthode employée : {libelles.get(data['methode'], data['methode'])}")

    st.subheader("Articles recommandés")
    for i, art in enumerate(data["articles"], 1):
        st.write(f"**{i}.** Article n° {art}")
