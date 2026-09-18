import azure.functions as func
import json
import logging
import os
import pickle
import io

import numpy as np
from azure.storage.blob import BlobServiceClient

app = func.FunctionApp()

CONTAINER = "models"
_cache = {}


def charger():
    """Télécharge les modèles depuis le blob, une seule fois par instance."""
    if _cache:
        return _cache

    conn = os.environ["STORAGE_CONNECTION"]
    client = BlobServiceClient.from_connection_string(conn)
    container = client.get_container_client(CONTAINER)

    def lire(nom):
        return container.download_blob(nom).readall()

    _cache["emb"] = np.load(io.BytesIO(lire("emb_pca50.npy")))
    _cache["hist"] = pickle.loads(lire("hist_users.pkl"))
    _cache["pop"] = pickle.loads(lire("top_popular.pkl"))
    _cache["uf"] = np.load(io.BytesIO(lire("als_user_factors.npy")))
    _cache["if"] = np.load(io.BytesIO(lire("als_item_factors.npy")))

    maps = pickle.loads(lire("als_mappings.pkl"))
    _cache["users"] = maps["users"]
    _cache["items"] = maps["items"]
    _cache["u_idx"] = {u: i for i, u in enumerate(maps["users"])}

    logging.info("Modèles chargés.")
    return _cache


def top_k(scores, exclure, k):
    scores = scores.copy()
    if len(exclure):
        scores[exclure] = -np.inf
    idx = np.argpartition(-scores, k)[:k]
    return idx[np.argsort(-scores[idx])]


def reco_collaboratif(m, user_id, k):
    ui = m["u_idx"][user_id]
    scores = m["if"] @ m["uf"][ui]
    lus = m["hist"].get(user_id, [])
    exclure = [i for i, a in enumerate(m["items"]) if a in set(lus)]
    top = top_k(scores, np.array(exclure, dtype=int), k)
    return [int(m["items"][i]) for i in top]


def reco_content(m, user_id, k):
    lus = m["hist"][user_id]
    profil = m["emb"][lus].mean(axis=0)
    profil = profil / np.linalg.norm(profil)
    scores = m["emb"] @ profil
    top = top_k(scores, np.array(lus, dtype=int), k)
    return [int(i) for i in top]


@app.route(route="recommend", auth_level=func.AuthLevel.ANONYMOUS)
def recommend(req: func.HttpRequest) -> func.HttpResponse:
    user_id = req.params.get("user_id")
    if not user_id:
        try:
            user_id = req.get_json().get("user_id")
        except ValueError:
            pass

    if user_id is None:
        return func.HttpResponse(
            json.dumps({"erreur": "Paramètre user_id manquant"}),
            status_code=400, mimetype="application/json")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return func.HttpResponse(
            json.dumps({"erreur": "user_id doit être un entier"}),
            status_code=400, mimetype="application/json")

    try:
        m = charger()

        if user_id in m["u_idx"]:
            articles, methode = reco_collaboratif(m, user_id, 5), "collaboratif"
        elif user_id in m["hist"]:
            articles, methode = reco_content(m, user_id, 5), "content_based"
        else:
            articles, methode = [int(a) for a in m["pop"][:5]], "popularite"

        return func.HttpResponse(
            json.dumps({"user_id": user_id, "articles": articles, "methode": methode}),
            status_code=200, mimetype="application/json")

    except Exception as e:
        logging.exception("Erreur de recommandation")
        return func.HttpResponse(
            json.dumps({"erreur": str(e)}),
            status_code=500, mimetype="application/json")
