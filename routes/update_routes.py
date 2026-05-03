"""Routes de mise à jour — vérification et application depuis le frontend."""
import logging
import os
import time as _t
import threading
from flask import Blueprint, jsonify, request
from core.updater import check_update, prepare_update_script
from core.version import RODIA_VERSION
from core.paths import LOG_PATH

log = logging.getLogger(__name__)

bp = Blueprint("update", __name__, url_prefix="/api")


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


@bp.route("/apply-update", methods=["POST", "GET"])
def apply_update():
    """Lance le script PowerShell puis ferme RODIA 5 secondes plus tard.

    Les 5 secondes laissent le temps au JS de recevoir la réponse 200,
    afficher le compte à rebours et préparer l'utilisateur à la fermeture.
    Le script PowerShell attend 6 secondes avant de télécharger — il démarre
    donc le téléchargement 1 seconde après la fermeture de RODIA.
    """
    _log(f"apply-update appelé — method={request.method}")

    # Support JSON body (POST) ou query param ?url= (GET/POST)
    url = request.args.get("url", "")
    if not url:
        data = request.get_json(force=True, silent=True) or {}
        url  = data.get("download_url", "")
    if not url:
        _log("URL manquante — 400")
        return jsonify({"error": "URL de téléchargement manquante"}), 400

    _log(f"Préparation script PowerShell — url={url[:80]}")
    ok = prepare_update_script(url)
    if not ok:
        _log("Échec lancement script PowerShell — 500")
        return jsonify({"error": "Impossible de lancer le script de mise à jour"}), 500

    # Fermeture différée : 5s pour que le JS reçoive la réponse et affiche le message.
    def _deferred_exit():
        _t.sleep(5)
        _log("Fermeture RODIA — le wizard d'installation va s'ouvrir")
        os._exit(0)

    threading.Thread(target=_deferred_exit, daemon=True).start()
    _log("Script PowerShell lancé — fermeture RODIA dans 5s")
    return jsonify({"success": True})
