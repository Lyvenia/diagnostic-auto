"""Routes de mise à jour — vérification et application depuis le frontend."""
import logging
import os
import time as _t
import threading
from urllib.parse import urlparse
from flask import Blueprint, jsonify, request
from core.updater import check_update, prepare_update_script
from core.version import RODIA_VERSION
from core.paths import LOG_PATH

log = logging.getLogger(__name__)

bp = Blueprint("update", __name__, url_prefix="/api")


# Hôtes autorisés pour télécharger un installeur RODIA. GitHub redirige souvent
# le download direct vers objects.githubusercontent.com → on whitelist les deux.
# Le `/Lyvenia/` dans le path empêche un attaquant de pointer vers le repo
# d'un autre user GitHub.
_ALLOWED_UPDATE_HOSTS = {"github.com", "objects.githubusercontent.com"}


def _is_trusted_url(url: str) -> bool:
    """True si l'URL est un download HTTPS vers une release de l'org Lyvenia."""
    try:
        p = urlparse(url)
        return (
            p.scheme == "https"
            and p.netloc in _ALLOWED_UPDATE_HOSTS
            and "/Lyvenia/" in p.path
        )
    except Exception:
        return False


def _log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [update] {msg}\n")
    except Exception:
        pass


@bp.route("/version-info", methods=["GET"])
def version_info():
    """Retourne la version locale + infos de mise à jour si disponible."""
    update = check_update()
    return jsonify({
        "current_version": RODIA_VERSION,
        "update_available": update is not None,
        **(update or {}),
    })


@bp.route("/apply-update", methods=["POST"])
def apply_update():
    """Lance le script PowerShell d'installation silencieuse puis ferme RODIA 5s plus tard.

    Body JSON (POST uniquement — GET refusé pour éviter qu'un lien malveillant
    déclenche l'install via une simple navigation) :
        {
            "download_url": "https://github.com/Lyvenia/.../RODIA-Setup-vX.Y.Z.exe",
            "sha256":       "abc123…" (optionnel — vérification d'intégrité),
            "version":      "1.1.4" (optionnel — affichée dans le toast Windows)
        }

    Le script :
      - télécharge l'installateur (URL whitelistée à github.com / Lyvenia/*)
      - vérifie le SHA-256 si fourni
      - kill RODIA + WebView Edge
      - lance Inno Setup en /VERYSILENT (aucune fenêtre)
      - affiche un toast Windows à la fin
    """
    _log(f"apply-update appelé — method={request.method}")

    data    = request.get_json(force=True, silent=True) or {}
    url     = data.get("download_url", "")
    sha256  = data.get("sha256", "") or ""
    version = data.get("version", "") or ""
    if not url:
        _log("URL manquante — 400")
        return jsonify({"error": "URL de téléchargement manquante"}), 400

    # Garde-fou anti-SSRF / supply-chain : seules les URLs de release officielles
    # Lyvenia sur GitHub sont autorisées. Empêche un attaquant qui aurait le CSRF
    # de pointer vers un .exe malveillant.
    if not _is_trusted_url(url):
        _log(f"URL REFUSÉE (non whitelistée) : {url[:120]}")
        return jsonify({"error": "URL de mise à jour non autorisée"}), 403

    _log(f"Préparation script PowerShell — url={url[:80]} sha256={(sha256 or '')[:12]}… version={version!r}")
    ok = prepare_update_script(url, sha256=sha256 or None, version=version or None)
    if not ok:
        _log("Échec lancement script PowerShell — 500")
        return jsonify({"error": "Impossible de lancer le script de mise à jour"}), 500

    # Fermeture différée : 5s pour que le JS reçoive la réponse et affiche le message.
    def _deferred_exit():
        _t.sleep(5)
        _log("Fermeture RODIA — l'installation silencieuse continue en arrière-plan")
        os._exit(0)

    threading.Thread(target=_deferred_exit, daemon=True).start()
    _log("Script PowerShell lancé — fermeture RODIA dans 5s")
    return jsonify({"success": True})
