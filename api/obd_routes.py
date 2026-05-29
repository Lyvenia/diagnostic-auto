"""Routes OBD2 — connexion, lecture DTC, surveillance continue."""
from flask import Blueprint, jsonify, request
from shared import obd, fleet
from analysis.session_analyzer import analyze_session
from core.paths import LOG_PATH
from core.variant import CLIENT_BUILD
import time as _t

bp = Blueprint('obd', __name__)


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


@bp.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(obd.get_status())


@bp.route("/api/connect", methods=["POST"])
def api_connect():
    return jsonify(obd.connect())


@bp.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    return jsonify(obd.disconnect())


@bp.route("/api/simulation/toggle", methods=["POST"])
def api_simulation_toggle():
    if CLIENT_BUILD:
        return jsonify({"success": False, "error": "Indisponible sur cette version"}), 403
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    return jsonify(obd.toggle_simulation(enabled))


@bp.route("/api/read", methods=["POST"])
def api_read():
    """Lit VIN, codes DTC et données temps réel."""
    from analysis.dtc_analyzer import get_dtc_info, _DTC_FAMILIES  # base DTC locale (1100+ codes)

    data = request.get_json() or {}
    forced_vin = data.get("forced_vin")
    obd.reset_simulation(forced_vin=forced_vin)
    vin = obd.read_vin()
    _log(f"[read] VIN lu : {vin!r} (simulation={obd.simulation_mode})")
    dtc_result    = obd.read_dtc()
    dtc_codes     = dtc_result.get("codes", [])
    dtc_status    = dtc_result.get("status", "ok")
    mil_on        = dtc_result.get("mil_on")
    dtc_count     = dtc_result.get("dtc_count")

    # Enrichissement par code depuis la base locale (libellé FR + family +
    # severity + mil + vehicles). Permet l'affichage groupé par famille et la
    # couleur de gravité côté frontend sans appel supplémentaire.
    dtc_info = {}
    families_used = set()
    for code in dtc_codes:
        info = get_dtc_info(code)
        if info:
            dtc_info[code] = info
            families_used.add(info.get("family", "non_classe"))
    # Libellés humains des familles présentes dans ce diagnostic
    dtc_families = {f: _DTC_FAMILIES.get(f, f) for f in families_used}

    # Si PID 01 indispo (mil_on=None) mais qu'au moins un code stocké est
    # MIL=true dans la base, on en déduit que le voyant est allumé.
    if mil_on is None and dtc_codes:
        mil_on = any(dtc_info.get(c, {}).get("mil") for c in dtc_codes)

    _log(f"[read] DTC status={dtc_status!r} codes={dtc_codes} mil={mil_on}")
    realtime      = obd.read_realtime()
    engine_running = realtime.get("engine_running")  # True/False/None
    freeze_frame  = obd.read_freeze_frame() if dtc_codes else {}
    return jsonify({
        "vin":            vin,
        "vin_available":  vin is not None and len(vin) >= 11,
        "dtc_codes":      dtc_codes,
        "dtc_status":     dtc_status,
        "dtc_info":       dtc_info,
        "dtc_families":   dtc_families,
        "mil_on":         mil_on,
        "dtc_count":      dtc_count,
        "engine_running": engine_running,
        "realtime":       realtime,
        "freeze_frame":   freeze_frame,
        "simulation":     obd.simulation_mode,
    })


@bp.route("/api/dtc/clear", methods=["POST"])
def api_dtc_clear():
    return jsonify(obd.clear_dtc())


@bp.route("/api/monitoring/start", methods=["POST"])
def api_monitoring_start():
    ok = obd.start_monitoring()
    if ok:
        return jsonify({"success": True, "message": "Surveillance démarrée"})
    return jsonify({"success": False, "message": "Surveillance déjà active"})


@bp.route("/api/monitoring/stop", methods=["POST"])
def api_monitoring_stop():
    session = obd.stop_monitoring()
    if session:
        return jsonify({"success": True, "session": session})
    return jsonify({"success": False, "message": "Aucune session active"})


@bp.route("/api/monitoring/status", methods=["GET"])
def api_monitoring_status():
    return jsonify(obd.get_session_status())


@bp.route("/api/monitoring/analyze", methods=["POST"])
def api_monitoring_analyze():
    data = request.get_json() or {}
    vin = data.get("vin")
    session_data = data.get("session")
    if not session_data:
        return jsonify({"error": "Données de session manquantes"}), 400
    vehicle = fleet.get_vehicle(vin) if vin else {}
    if not vehicle:
        vehicle = {"vin": vin or "INCONNU", "marque": "N/A", "modele": "N/A", "annee": "N/A", "km": 0}
    else:
        # Enrichir avec le km réel depuis l'historique
        vehicle = dict(vehicle)
        hist = vehicle.get("historique", [])
        vehicle["km"] = hist[0].get("kilometrage", 0) if hist else 0
    try:
        result = analyze_session(vehicle, session_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "analyse_ia": {"statut": "ERREUR", "resume": str(e), "actions": [], "conseils": []}}), 500
