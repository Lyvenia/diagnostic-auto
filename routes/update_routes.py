"""Routes de mise à jour — vérification et application depuis le frontend."""
import logging
import threading
from flask import Blueprint, jsonify, request
from core.updater import check_update, download_and_apply
from core.version import RODIA_VERSION

log = logging.getLogger(__name__)

bp = Blueprint("update", __name__, url_prefix="/api")

# État partagé du téléchargement en cours
_status: dict = {"downloading": False, "progress": 0, "error": None}


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
    """Lance le téléchargement et l'application de la mise à jour en arrière-plan."""
    global _status
    if _status["downloading"]:
        return jsonify({"error": "Téléchargement déjà en cours"}), 409

    data = request.get_json(force=True, silent=True) or {}
    url  = data.get("download_url", "")
    if not url:
        return jsonify({"error": "URL de téléchargement manquante"}), 400

    log.info(f"apply-update demandé — url={url[:60]}...")
    _status = {"downloading": True, "progress": 0, "error": None}

    def _run():
        global _status
        def on_progress(pct):
            _status["progress"] = pct
        try:
            download_and_apply(url, on_progress=on_progress)
        except Exception as exc:
            _status["error"]       = str(exc)
            _status["downloading"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True})


@bp.route("/update-status", methods=["GET"])
def update_status():
    """Progression du téléchargement en cours."""
    return jsonify(_status)
