"""Stockage du JWT Lyvenia dans config.json (clé lyvenia_jwt)."""
import time

from core.config import load_config, save_config

_JWT_KEY = "lyvenia_jwt"


def get_jwt() -> str | None:
    """Retourne le JWT stocké, ou None s'il n'existe pas."""
    return load_config().get(_JWT_KEY)


def set_jwt(token: str | None):
    """Sauvegarde (ou efface) le JWT dans config.json."""
    cfg = load_config()
    if token:
        cfg[_JWT_KEY] = token
    else:
        cfg.pop(_JWT_KEY, None)
    save_config(cfg)


def clear_jwt():
    """Supprime le JWT (déconnexion)."""
    set_jwt(None)


def is_jwt_locally_valid() -> bool:
    """Vérifie l'expiration du JWT sans contacter le serveur (mode offline).

    Retourne True si le token existe et n'est pas expiré selon son payload.
    """
    token = get_jwt()
    if not token:
        return False
    try:
        import base64, json as _json
        # Decode payload sans vérification de signature
        parts = token.split(".")
        if len(parts) < 2:
            return False
        padding = 4 - len(parts[1]) % 4
        payload_bytes = base64.urlsafe_b64decode(parts[1] + "=" * padding)
        payload = _json.loads(payload_bytes)
        exp = payload.get("exp", 0)
        return exp > time.time()
    except Exception:
        return False
