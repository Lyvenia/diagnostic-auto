"""Routes d'authentification Lyvenia pour le serveur local RODIA.

Expose :
  GET  /api/auth/status       — état de la session (authentifié / non / offline)
  POST /api/auth/login        — connexion email+password → stocke le JWT
  POST /api/auth/logout       — efface le JWT
  POST /api/auth/forgot       — demande de réinitialisation de mot de passe
"""
import requests
from flask import Blueprint, jsonify, request

from core.auth_store import clear_jwt, get_jwt, is_jwt_locally_valid, set_jwt
from core.machine_id import get_machine_id
from core.variant import CLIENT_BUILD

bp = Blueprint("lyvenia_auth", __name__)

LYVENIA_API_URL = "https://api.lyvenia.fr"
_TIMEOUT_SHORT = 10  # secondes pour les appels rapides (login, status)


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/auth/status
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/auth/status")
def auth_status():
    """Retourne l'état de la session Lyvenia.

    Auth désactivée temporairement — api.lyvenia.fr pas encore déployé.
    À réactiver quand le backend Lyvenia est opérationnel.
    """
    if not CLIENT_BUILD:
        return jsonify({"authenticated": True, "needs_login": False})

    token = get_jwt()
    if not token:
        return jsonify({"authenticated": False, "needs_login": True})

    # Tente de valider auprès du serveur
    try:
        resp = requests.post(
            f"{LYVENIA_API_URL}/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT_SHORT,
        )
        if resp.ok:
            data = resp.json()
            new_token = data.get("token")
            if new_token:
                set_jwt(new_token)
            return jsonify({
                "authenticated": True,
                "needs_login": False,
                "offline": False,
                "user": data.get("user"),
            })
        # Token invalide côté serveur
        clear_jwt()
        return jsonify({"authenticated": False, "needs_login": True})

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Serveur injoignable → mode offline
        if is_jwt_locally_valid():
            return jsonify({
                "authenticated": True,
                "needs_login": False,
                "offline": True,
            })
        clear_jwt()
        return jsonify({"authenticated": False, "needs_login": True})


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/auth/login
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"success": False, "error": "Email et mot de passe requis"}), 400

    machine_id = get_machine_id()

    try:
        resp = requests.post(
            f"{LYVENIA_API_URL}/auth/login",
            json={"email": email, "password": password, "machine_id": machine_id},
            timeout=_TIMEOUT_SHORT,
        )
        result = resp.json()

        if resp.ok and result.get("token"):
            set_jwt(result["token"])
            return jsonify({"success": True, "user": result.get("user")})

        error_msg = result.get("error", "Identifiants incorrects")
        return jsonify({"success": False, "error": error_msg}), 401

    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Impossible de contacter le serveur Lyvenia. Vérifiez votre connexion internet.",
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Le serveur Lyvenia ne répond pas. Réessayez.",
        }), 503


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/auth/logout
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/auth/logout", methods=["POST"])
def logout():
    clear_jwt()
    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/auth/forgot
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/auth/forgot", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"success": False, "error": "Email requis"}), 400

    try:
        requests.post(
            f"{LYVENIA_API_URL}/auth/forgot-password",
            json={"email": email},
            timeout=_TIMEOUT_SHORT,
        )
    except Exception:
        pass  # Toujours retourner OK pour ne pas révéler si l'email existe

    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/auth/change-password
# ─────────────────────────────────────────────────────────────────────────────

@bp.route("/api/auth/change-password", methods=["POST"])
def change_password():
    """Change le mot de passe de l'utilisateur connecté.

    Proxifie vers api.lyvenia.fr/auth/change-password avec le JWT stocké localement.
    Body attendu : {"old_password": "...", "new_password": "..."}
    """
    data         = request.get_json(silent=True) or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return jsonify({"success": False, "error": "Ancien et nouveau mot de passe requis"}), 400
    if len(new_password) < 8:
        return jsonify({"success": False, "error": "Le nouveau mot de passe doit contenir au moins 8 caractères"}), 400

    token = get_jwt()
    if not token:
        return jsonify({"success": False, "error": "Non authentifié — reconnectez-vous"}), 401

    try:
        resp = requests.post(
            f"{LYVENIA_API_URL}/auth/change-password",
            json={"old_password": old_password, "new_password": new_password},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT_SHORT,
        )
        result = resp.json()
        if resp.ok and result.get("success"):
            return jsonify({"success": True})
        return jsonify({
            "success": False,
            "error": result.get("error", "Échec du changement de mot de passe"),
        }), resp.status_code

    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Impossible de contacter le serveur Lyvenia. Vérifiez votre connexion internet.",
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Le serveur Lyvenia ne répond pas. Réessayez.",
        }), 503
