from flask import Blueprint, jsonify, request
from shared import obd, fleet
from datetime import datetime

bp = Blueprint('fleet', __name__)


@bp.route("/api/fleet", methods=["GET"])
def api_fleet():
    return jsonify(fleet.get_all_vehicles())


@bp.route("/api/fleet/vehicle/<vin>", methods=["GET"])
def api_fleet_get_vehicle(vin):
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    return jsonify(vehicle)


@bp.route("/api/fleet/vehicle", methods=["POST"])
def api_fleet_create_vehicle():
    data = request.get_json() or {}
    vin = data.get("vin")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400
    vin_info = data.get("vin_info", {})
    vehicle, is_new = fleet.create_or_get_vehicle(vin, vin_info, simulated=obd.simulation_mode)
    # Mettre à jour la motorisation même si le véhicule existait déjà
    if not is_new and vin_info.get("motorisation"):
        fleet.update_vehicle_info(vin, {"motorisation": vin_info["motorisation"]})
        vehicle = fleet.fleet.get(vin, vehicle)
    return jsonify({"vehicle": vehicle, "is_new": is_new})


@bp.route("/api/fleet/diagnostic", methods=["POST"])
def api_fleet_save_diagnostic():
    data = request.get_json() or {}
    vin = data.get("vin")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400

    analyse_ia_raw = data.get("analyse_ia", {})
    if isinstance(analyse_ia_raw, str):
        analyse_ia_raw = {}
    vin_info = analyse_ia_raw.get("vin_info", {})
    _, is_new = fleet.create_or_get_vehicle(vin, vin_info, simulated=obd.simulation_mode)

    entry = fleet.save_diagnostic(vin, data)
    return jsonify({"success": True, "entry": entry, "is_new": is_new})


@bp.route("/api/fleet/vehicle/<vin>/history", methods=["GET"])
def api_fleet_history(vin):
    return jsonify(fleet.get_history(vin))


@bp.route("/api/fleet/vehicle/<vin>/diagnostic/<diag_id>/suivi", methods=["PUT"])
def api_fleet_diagnostic_suivi(vin, diag_id):
    data = request.get_json() or {}
    statut = data.get("statut_suivi", "ouvert")
    notes  = data.get("notes_reparation")
    if statut not in ("ouvert", "en_cours", "resolu"):
        return jsonify({"error": "Statut invalide"}), 400
    ok = fleet.update_diagnostic_suivi(vin, diag_id, statut, notes)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Diagnostic non trouvé"}), 404


@bp.route("/api/fleet/vehicle/<vin>", methods=["DELETE"])
def api_fleet_delete_vehicle(vin):
    ok = fleet.delete_vehicle(vin)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@bp.route("/api/fleet/vehicle/<vin>/notes", methods=["PUT"])
def api_fleet_notes(vin):
    data = request.get_json() or {}
    notes = data.get("notes", "")
    if fleet.update_notes(vin, notes):
        return jsonify({"success": True})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@bp.route("/api/fleet/vehicle/<vin>/km", methods=["PUT"])
def api_fleet_update_km(vin):
    data = request.get_json() or {}
    km_raw = data.get("km_manuel")
    if km_raw is None:
        return jsonify({"error": "km_manuel manquant"}), 400
    try:
        km = int(km_raw)
        if km < 0 or km > 9_999_999:
            raise ValueError("hors plage")
    except (ValueError, TypeError):
        return jsonify({"error": "km_manuel invalide (entier positif attendu)"}), 400
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    fleet.update_vehicle_info(vin, {"km_manuel": km})
    return jsonify({"success": True})


@bp.route("/api/fleet/vehicle/<vin>/info", methods=["PUT"])
def api_fleet_update_vehicle_info(vin):
    data = request.get_json() or {}
    code   = data.get("code", "")
    surnom = data.get("surnom", "")
    groupe = data.get("groupe", "")
    updated = fleet.update_vehicle_fleet_info(vin, code, surnom, groupe)
    if updated:
        return jsonify(updated)
    return jsonify({"error": "Véhicule non trouvé"}), 404


@bp.route("/api/fleet/groups", methods=["GET"])
def api_fleet_groups():
    return jsonify(fleet.get_groups())


@bp.route("/api/fleet/vehicle/<vin>/repairs", methods=["GET"])
def api_fleet_get_repairs(vin):
    return jsonify(fleet.get_repairs(vin))


@bp.route("/api/fleet/vehicle/<vin>/repairs", methods=["POST"])
def api_fleet_add_repair(vin):
    data = request.get_json() or {}
    entry = fleet.add_repair(vin, data)
    if entry:
        return jsonify({"success": True, "entry": entry})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@bp.route("/api/fleet/vehicle/<vin>/alerts", methods=["GET"])
def api_fleet_get_alerts(vin):
    return jsonify(fleet.get_km_alerts(vin))


@bp.route("/api/fleet/vehicle/<vin>/alerts", methods=["POST"])
def api_fleet_add_alert(vin):
    data = request.get_json() or {}
    entry = fleet.add_km_alert(vin, data)
    if entry:
        return jsonify({"success": True, "entry": entry})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@bp.route("/api/fleet/vehicle/<vin>/alerts/<alert_id>", methods=["DELETE"])
def api_fleet_delete_alert(vin, alert_id):
    ok = fleet.delete_km_alert(vin, alert_id)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Alerte non trouvée"}), 404


@bp.route("/api/fleet/alerts", methods=["GET"])
def api_fleet_all_alerts():
    return jsonify(fleet.get_all_alerts_status())


@bp.route("/api/fleet/vehicle/<vin>/health", methods=["GET"])
def api_fleet_health(vin):
    return jsonify(fleet.get_health_score(vin))


@bp.route("/api/fleet/vehicle/<vin>/maintenance", methods=["GET"])
def api_fleet_maintenance(vin):
    return jsonify(fleet.get_maintenance_schedule(vin))


@bp.route("/api/fleet/health", methods=["GET"])
def api_fleet_all_health():
    return jsonify(fleet.get_all_health_scores())


@bp.route("/api/maintenance/template", methods=["GET"])
def api_maint_template():
    from fleet.maintenance import get_template
    return jsonify(get_template())


@bp.route("/api/maintenance/template", methods=["POST"])
def api_maint_template_add():
    from fleet.maintenance import add_custom_item
    d = request.get_json() or {}
    item = add_custom_item(
        label=d.get("label", ""),
        item_type=d.get("type", "scheduled"),
        category=d.get("category", "Autre"),
        icon=d.get("icon", "🔧"),
        interval_km=d.get("interval_km"),
        interval_months=d.get("interval_months"),
        wear_states=d.get("wear_states"),
    )
    return jsonify(item), 201


@bp.route("/api/maintenance/template/<item_id>", methods=["DELETE"])
def api_maint_template_delete(item_id):
    from fleet.maintenance import delete_custom_item
    ok = delete_custom_item(item_id)
    return jsonify({"ok": ok}), (200 if ok else 404)


@bp.route("/api/maintenance/vehicle/<vin>", methods=["GET"])
def api_maint_vehicle(vin):
    from fleet.maintenance import get_vehicle_maintenance
    vehicle = fleet.get_vehicle(vin)
    hist = vehicle.get("historique", []) if vehicle else []
    km = hist[0].get("kilometrage", 0) if hist else 0
    return jsonify(get_vehicle_maintenance(vin, km))


@bp.route("/api/maintenance/vehicle/<vin>/done/<item_id>", methods=["POST"])
def api_maint_done(vin, item_id):
    from fleet.maintenance import mark_done
    d = request.get_json() or {}
    try:
        km_done = int(d.get("km", 0))
    except (ValueError, TypeError):
        km_done = 0
    result = mark_done(vin, item_id, d.get("date", datetime.now().strftime("%Y-%m-%d")), km_done)
    if result is None:
        return jsonify({"error": "Item introuvable"}), 404
    return jsonify(result)


@bp.route("/api/maintenance/vehicle/<vin>/wear/<item_id>", methods=["PUT"])
def api_maint_wear(vin, item_id):
    from fleet.maintenance import update_wear
    d = request.get_json() or {}
    result = update_wear(vin, item_id, d.get("wear_state", ""), d.get("km"))
    return jsonify(result)


@bp.route("/api/fleet/next-code", methods=["GET"])
def api_fleet_next_code():
    """Retourne le prochain numéro disponible pour un préfixe donné (ex: V → V3)."""
    prefix = (request.args.get("type") or "V").upper().strip()
    vehicles = fleet.get_all_vehicles()
    nums = []
    for v in vehicles:
        code = (v.get("code") or "").upper()
        if code.startswith(prefix):
            tail = code[len(prefix):]
            try:
                nums.append(int(tail))
            except (ValueError, IndexError):
                pass
    next_num = max(nums) + 1 if nums else 1
    return jsonify({"prefix": prefix, "next": next_num, "suggestion": f"{prefix}{next_num}"})


@bp.route("/api/fleet/patterns", methods=["GET"])
def api_fleet_patterns():
    return jsonify(fleet.get_fleet_patterns())
