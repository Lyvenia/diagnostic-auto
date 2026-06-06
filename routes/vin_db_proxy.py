"""Proxy base VIN partagée — RODIA -> api.lyvenia.fr/vin/*

Le frontend de RODIA appelle des URLs relatives /api/vin/*. Ce proxy les
forward au backend Lyvenia avec le JWT du user. Pattern identique à
lyvenia_auth.py et au proxy AI.

Endpoints exposés :
  GET  /api/vin/lookup/<vin>     → forward GET  /vin/<vin>
  POST /api/vin/contribute       → forward POST /vin/contribute
"""
import logging
import requests
from flask import Blueprint, jsonify, request

from core.auth_store import get_jwt

log = logging.getLogger(__name__)

bp = Blueprint("vin_db_proxy", __name__)

LYVENIA_API_URL = "https://api.lyvenia.fr"


@bp.route("/api/vin/lookup/<vin>", methods=["GET"])
def vin_lookup_proxy(vin):
    """Lookup d'un VIN dans la base partagée Lyvenia. Pas de JWT requis côté
    backend, mais on l'envoie quand même si dispo pour log/stats serveur."""
    headers = {}
    token = get_jwt()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"{LYVENIA_API_URL}/vin/{vin}",
            headers=headers,
            timeout=8,
        )
        if resp.status_code == 404:
            return jsonify({"found": False}), 200  # 200 + found=false pour le front
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException as e:
        log.warning(f"[vin_db_proxy] lookup failed: {e}")
        return jsonify({"found": False, "error": "lookup_unavailable"}), 200


@bp.route("/api/vin/contribute", methods=["POST"])
def vin_contribute_proxy():
    """Forward une contribution VIN au backend Lyvenia. JWT obligatoire."""
    token = get_jwt()
    if not token:
        return jsonify({"error": "Connexion Lyvenia requise"}), 401

    body = request.get_json(silent=True) or {}
    try:
        resp = requests.post(
            f"{LYVENIA_API_URL}/vin/contribute",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException as e:
        log.warning(f"[vin_db_proxy] contribute failed: {e}")
        return jsonify({"error": "Service indisponible"}), 503


@bp.route("/api/vin/extract-cartegrise", methods=["POST"])
def vin_extract_cartegrise_proxy():
    """Forward la photo de carte grise pour extraction Claude Vision.
    L'image est envoyée en base64 (champ image_base64) au backend Lyvenia
    qui appelle Claude. RODIA ne stocke pas l'image en local."""
    token = get_jwt()
    if not token:
        return jsonify({"error": "Connexion Lyvenia requise"}), 401

    body = request.get_json(silent=True) or {}
    try:
        # Timeout plus long pour Vision : Claude met 5-15s
        resp = requests.post(
            f"{LYVENIA_API_URL}/vin/extract-cartegrise",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException as e:
        log.warning(f"[vin_db_proxy] extract-cartegrise failed: {e}")
        return jsonify({"error": "Service IA temporairement indisponible"}), 503
