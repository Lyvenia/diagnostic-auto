"""
Serveur Flask — point d'entrée principal de l'outil de diagnostic OBD2.
Lancer : python app.py
Accès  : http://localhost:5000
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from ai_analyzer import analyze_dtc, analyze_session, analyze_with_session, analyze_full_diagnostic
from base_path import data_path, LOG_PATH
from excel_exporter import export_fleet_excel
from fleet_manager import FleetManager
from obd_reader import OBDReader, load_config, save_config
from pdf_exporter import export_diagnostic_pdf, export_monthly_report


# ── Logger ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    """Log horodaté dans le fichier d'erreur de l'application."""
    import time as _t
    try:
        ts = _t.strftime("%H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── Export helper ────────────────────────────────────────────────────────────

def save_export(file_bytes: bytes, filename: str) -> str:
    """Sauvegarde un fichier exporté dans exports/ et retourne le chemin absolu."""
    export_dir = data_path("exports")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


# ── App setup ────────────────────────────────────────────────────────────────

# Quand packagé en .exe (PyInstaller), les ressources bundlées sont dans sys._MEIPASS
def _find_static_folder() -> str:
    """Trouve le dossier frontend/ en testant plusieurs chemins possibles."""
    candidates = []
    if getattr(sys, "frozen", False):
        # Chemin principal : _internal/frontend (onedir)
        candidates.append(os.path.join(sys._MEIPASS, "frontend"))
        # Chemin alternatif : à côté de l'exe
        candidates.append(os.path.join(os.path.dirname(sys.executable), "frontend"))
        # Chemin explicite : exe/_internal/frontend
        candidates.append(os.path.join(os.path.dirname(sys.executable), "_internal", "frontend"))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend"))

    # Log pour diagnostic
    log_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)), "DiagnosticAuto_error.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            for c in candidates:
                f.write(f"[app.py] frontend candidate: {c} → {'OK' if os.path.isdir(c) else 'MISSING'}\n")
    except Exception:
        pass

    for c in candidates:
        if os.path.isdir(c):
            return c
    # Aucun trouvé — retourner le premier quand même (Flask dira 404 explicitement)
    return candidates[0]

_static_folder = _find_static_folder()

app = Flask(__name__, static_folder=_static_folder, static_url_path="")
CORS(app)

obd = OBDReader()
fleet = FleetManager()

# ── Chargement en mémoire des fichiers frontend au démarrage ─────────────────
# Protection antivirus : les fichiers sont lus une seule fois au lancement
# et servis depuis la RAM même si l'antivirus les supprime ensuite.
_frontend_cache: dict = {}

def _load_frontend_cache():
    files = {
        "index.html":  "text/html; charset=utf-8",
        "app.js":      "application/javascript; charset=utf-8",
        "style.css":   "text/css; charset=utf-8",
    }
    for filename, mime in files.items():
        for folder in [_static_folder,
                       os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)), "_internal", "frontend")]:
            path = os.path.join(folder, filename)
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        _frontend_cache[filename] = (f.read(), mime)
                    break
                except Exception:
                    pass

_load_frontend_cache()

# ── Frontend ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "index.html" in _frontend_cache:
        content, mime = _frontend_cache["index.html"]
        return content, 200, {"Content-Type": mime}
    return app.send_static_file("index.html")

@app.route("/app.js")
def serve_js():
    if "app.js" in _frontend_cache:
        content, mime = _frontend_cache["app.js"]
        return content, 200, {"Content-Type": mime}
    return app.send_static_file("app.js")

@app.route("/style.css")
def serve_css():
    if "style.css" in _frontend_cache:
        content, mime = _frontend_cache["style.css"]
        return content, 200, {"Content-Type": mime}
    return app.send_static_file("style.css")


# ── OBD2 / Connexion ─────────────────────────────────────────────────────────

APP_VERSION = "1.0.0"

@app.route("/health")
def health():
    """Endpoint léger utilisé par main.py pour confirmer que Flask est prêt."""
    return "OK", 200

@app.route("/api/version")
def api_version():
    """Retourne la version et les infos éditeur du logiciel."""
    return jsonify({"version": APP_VERSION, "name": "RODIA", "editor": "Lyvenia"})


@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    """Reçoit un ping JS toutes les 5s — main.py surveille ce fichier pour savoir si la fenêtre est ouverte."""
    import time as _t
    try:
        hb_file = data_path(".heartbeat")
        with open(hb_file, "w") as f:
            f.write(str(_t.time()))
    except Exception:
        pass
    return "", 204


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(obd.get_status())


@app.route("/api/connect", methods=["POST"])
def api_connect():
    return jsonify(obd.connect())


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    return jsonify(obd.disconnect())


@app.route("/api/simulation/toggle", methods=["POST"])
def api_simulation_toggle():
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    return jsonify(obd.toggle_simulation(enabled))


@app.route("/api/read", methods=["POST"])
def api_read():
    """Lit VIN, codes DTC et données temps réel."""
    data = request.get_json() or {}
    forced_vin = data.get("forced_vin")
    obd.reset_simulation(forced_vin=forced_vin)
    vin = obd.read_vin()
    _log(f"[read] VIN lu : {vin!r} (simulation={obd.simulation_mode})")
    dtc_codes = obd.read_dtc()
    realtime = obd.read_realtime()
    freeze_frame = obd.read_freeze_frame() if dtc_codes else {}
    return jsonify({
        "vin": vin,
        "vin_available": vin is not None and len(vin) >= 11,
        "dtc_codes": dtc_codes,
        "realtime": realtime,
        "freeze_frame": freeze_frame,
        "simulation": obd.simulation_mode,
    })


@app.route("/api/dtc/clear", methods=["POST"])
def api_dtc_clear():
    return jsonify(obd.clear_dtc())


# ── Analyse IA ───────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json() or {}
    vin = data.get("vin", "")
    dtc_codes = data.get("dtc_codes", [])
    realtime = data.get("realtime", {})
    kilometrage = int(data.get("kilometrage", 0))

    if not vin:
        return jsonify({"error": "VIN manquant"}), 400

    historique  = fleet.get_history(vin)[:3]  if vin else []
    reparations = fleet.get_repairs(vin)[:10] if vin else []
    result = analyze_dtc(vin, dtc_codes, realtime, kilometrage, historique=historique, reparations=reparations)
    return jsonify(result)


@app.route("/api/analyze-session", methods=["POST"])
def api_analyze_session():
    """Analyse enrichie croisant DTC + données de session surveillance continue."""
    data = request.get_json() or {}
    dtc_codes = data.get("dtc_codes", [])
    vehicle_info = data.get("vehicle_info", {})
    session_data = data.get("session_data", {})

    try:
        result = analyze_with_session(dtc_codes, vehicle_info, session_data)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/analyze-full", methods=["POST"])
def api_analyze_full():
    """Analyse complète : DTC + sessions + anamnèse + freeze frame + historique flotte."""
    data = request.get_json() or {}
    vin = data.get("vin", "")
    dtc_codes = data.get("dtc_codes", [])
    km = int(data.get("kilometrage", 0))
    session_ralenti = data.get("session_ralenti") or None
    session_roulant = data.get("session_roulant") or None
    anamnese        = data.get("anamnese") or None
    freeze_frame    = data.get("freeze_frame") or None
    realtime        = data.get("realtime") or {}
    vehicle_manual  = data.get("vehicle_manual") or None

    if not vin and not vehicle_manual:
        return jsonify({"error": "VIN ou informations véhicule manquants"}), 400

    _log(f"[analyze-full] VIN={vin!r} anamnese={bool(anamnese)} vehicle_manual={bool(vehicle_manual)} dtc={dtc_codes}")

    # Enrichissement automatique depuis la flotte
    historique  = fleet.get_history(vin)[:5]  if vin else []
    reparations = fleet.get_repairs(vin)[:10] if vin else []

    try:
        result = analyze_full_diagnostic(
            vin, dtc_codes, km,
            session_ralenti, session_roulant,
            anamnese=anamnese,
            freeze_frame=freeze_frame,
            realtime=realtime,
            historique=historique,
            reparations=reparations,
            vehicle_manual=vehicle_manual,
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Flotte ───────────────────────────────────────────────────────────────────

@app.route("/api/fleet", methods=["GET"])
def api_fleet():
    return jsonify(fleet.get_all_vehicles())


@app.route("/api/fleet/vehicle/<vin>", methods=["GET"])
def api_fleet_get_vehicle(vin):
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    return jsonify(vehicle)


@app.route("/api/fleet/vehicle", methods=["POST"])
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


@app.route("/api/fleet/diagnostic", methods=["POST"])
def api_fleet_save_diagnostic():
    data = request.get_json() or {}
    vin = data.get("vin")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400

    analyse_ia_raw = data.get("analyse_ia", {})
    if isinstance(analyse_ia_raw, str):
        analyse_ia_raw = {}
    vin_info = analyse_ia_raw.get("vin_info", {})
    fleet.create_or_get_vehicle(vin, vin_info, simulated=obd.simulation_mode)

    entry = fleet.save_diagnostic(vin, data)
    return jsonify({"success": True, "entry": entry})


@app.route("/api/fleet/vehicle/<vin>/history", methods=["GET"])
def api_fleet_history(vin):
    return jsonify(fleet.get_history(vin))


@app.route("/api/fleet/vehicle/<vin>", methods=["DELETE"])
def api_fleet_delete_vehicle(vin):
    ok = fleet.delete_vehicle(vin)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@app.route("/api/fleet/vehicle/<vin>/notes", methods=["PUT"])
def api_fleet_notes(vin):
    data = request.get_json() or {}
    notes = data.get("notes", "")
    if fleet.update_notes(vin, notes):
        return jsonify({"success": True})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@app.route("/api/fleet/vehicle/<vin>/info", methods=["PUT"])
def api_fleet_update_vehicle_info(vin):
    data = request.get_json() or {}
    code   = data.get("code", "")
    surnom = data.get("surnom", "")
    groupe = data.get("groupe", "")
    updated = fleet.update_vehicle_fleet_info(vin, code, surnom, groupe)
    if updated:
        return jsonify(updated)
    return jsonify({"error": "Véhicule non trouvé"}), 404


@app.route("/api/fleet/groups", methods=["GET"])
def api_fleet_groups():
    return jsonify(fleet.get_groups())


# ── Export PDF ───────────────────────────────────────────────────────────────

@app.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    data = request.get_json() or {}
    vin = data.get("vin")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400

    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        # Créer un véhicule minimal si absent (ex: après analyse de session sans sauvegarde)
        vin_info = data.get("diagnostic", {}).get("analyse_ia", {}).get("vin_info", {})
        vehicle, _ = fleet.create_or_get_vehicle(vin, vin_info, simulated=obd.simulation_mode)

    diagnostic = None
    diag_id = data.get("diagnostic_id")
    if diag_id:
        for d in vehicle.get("historique", []):
            if d.get("id") == diag_id:
                diagnostic = d
                break
    if not diagnostic:
        diagnostic = data.get("diagnostic")

    if not diagnostic:
        return jsonify({"error": "Diagnostic non trouvé"}), 404

    try:
        pdf_bytes = export_diagnostic_pdf(vehicle, diagnostic)
        filename = f"diagnostic_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = save_export(pdf_bytes, filename)
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        return jsonify({"error": f"Erreur génération PDF : {exc}"}), 500


# ── Réparations ──────────────────────────────────────────────────────────────

@app.route("/api/fleet/vehicle/<vin>/repairs", methods=["GET"])
def api_fleet_get_repairs(vin):
    return jsonify(fleet.get_repairs(vin))


@app.route("/api/fleet/vehicle/<vin>/repairs", methods=["POST"])
def api_fleet_add_repair(vin):
    data = request.get_json() or {}
    entry = fleet.add_repair(vin, data)
    if entry:
        return jsonify({"success": True, "entry": entry})
    return jsonify({"error": "Véhicule non trouvé"}), 404


# ── Alertes kilométrage ───────────────────────────────────────────────────────

@app.route("/api/fleet/vehicle/<vin>/alerts", methods=["GET"])
def api_fleet_get_alerts(vin):
    return jsonify(fleet.get_km_alerts(vin))


@app.route("/api/fleet/vehicle/<vin>/alerts", methods=["POST"])
def api_fleet_add_alert(vin):
    data = request.get_json() or {}
    entry = fleet.add_km_alert(vin, data)
    if entry:
        return jsonify({"success": True, "entry": entry})
    return jsonify({"error": "Véhicule non trouvé"}), 404


@app.route("/api/fleet/vehicle/<vin>/alerts/<alert_id>", methods=["DELETE"])
def api_fleet_delete_alert(vin, alert_id):
    ok = fleet.delete_km_alert(vin, alert_id)
    if ok:
        return jsonify({"success": True})
    return jsonify({"error": "Alerte non trouvée"}), 404


@app.route("/api/fleet/alerts", methods=["GET"])
def api_fleet_all_alerts():
    return jsonify(fleet.get_all_alerts_status())


# ── Health & maintenance ──────────────────────────────────────────────────────

@app.route("/api/fleet/vehicle/<vin>/health", methods=["GET"])
def api_fleet_health(vin):
    return jsonify(fleet.get_health_score(vin))


@app.route("/api/fleet/vehicle/<vin>/maintenance", methods=["GET"])
def api_fleet_maintenance(vin):
    return jsonify(fleet.get_maintenance_schedule(vin))


@app.route("/api/fleet/health", methods=["GET"])
def api_fleet_all_health():
    result = {}
    for v in fleet.get_all_vehicles():
        vin = v.get("vin", "")
        if vin:
            result[vin] = fleet.get_health_score(vin)
    return jsonify(result)


# ── Maintenance avancée ───────────────────────────────────────────────────────

@app.route("/api/maintenance/template", methods=["GET"])
def api_maint_template():
    from maintenance_manager import get_template
    return jsonify(get_template())


@app.route("/api/maintenance/template", methods=["POST"])
def api_maint_template_add():
    from maintenance_manager import add_custom_item
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


@app.route("/api/maintenance/template/<item_id>", methods=["DELETE"])
def api_maint_template_delete(item_id):
    from maintenance_manager import delete_custom_item
    ok = delete_custom_item(item_id)
    return jsonify({"ok": ok}), (200 if ok else 404)


@app.route("/api/maintenance/vehicle/<vin>", methods=["GET"])
def api_maint_vehicle(vin):
    from maintenance_manager import get_vehicle_maintenance
    vehicle = fleet.get_vehicle(vin)
    hist = vehicle.get("historique", []) if vehicle else []
    km = hist[0].get("kilometrage", 0) if hist else 0
    return jsonify(get_vehicle_maintenance(vin, km))


@app.route("/api/maintenance/vehicle/<vin>/done/<item_id>", methods=["POST"])
def api_maint_done(vin, item_id):
    from maintenance_manager import mark_done
    d = request.get_json() or {}
    result = mark_done(vin, item_id, d.get("date", datetime.now().strftime("%Y-%m-%d")), int(d.get("km", 0)))
    if result is None:
        return jsonify({"error": "Item introuvable"}), 404
    return jsonify(result)


@app.route("/api/maintenance/vehicle/<vin>/wear/<item_id>", methods=["PUT"])
def api_maint_wear(vin, item_id):
    from maintenance_manager import update_wear
    d = request.get_json() or {}
    result = update_wear(vin, item_id, d.get("wear_state", ""), d.get("km"))
    return jsonify(result)


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    from maintenance_manager import get_fleet_summary
    vehicles = fleet.get_all_vehicles()
    # Health scores
    health = {}
    for v in vehicles:
        vin = v.get("vin", "")
        if vin:
            health[vin] = fleet.get_health_score(vin)
    # Average score
    scores = [h["score"] for h in health.values() if "score" in h]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    # Recent diagnostics (last 10 across all vehicles)
    all_diags = []
    for v in vehicles:
        vin = v.get("vin", "")
        label = f"{v.get('marque','')} {v.get('modele','')}".strip() or vin
        for entry in v.get("historique", [])[:5]:
            all_diags.append({
                "vin": vin,
                "label": label,
                "date": entry.get("date", ""),
                "date_affichage": entry.get("date_affichage", ""),
                "kilometrage": entry.get("kilometrage", 0),
                "dtc_codes": entry.get("dtc_codes", []),
                "statut": entry.get("statut", "OK"),
                "analyse_ia": entry.get("analyse_ia", {}),
            })
    all_diags.sort(key=lambda x: x["date"], reverse=True)
    recent_diags = all_diags[:10]
    # Maintenance summary
    vins_km = {}
    for v in vehicles:
        vin = v.get("vin", "")
        if vin:
            hist = v.get("historique", [])
            vins_km[vin] = hist[0].get("kilometrage", 0) if hist else 0
    maint_summary = get_fleet_summary(vins_km)
    return jsonify({
        "avg_score": avg_score,
        "health": health,
        "vehicles": [{"vin": v.get("vin"), "marque": v.get("marque"), "modele": v.get("modele"), "annee": v.get("annee")} for v in vehicles],
        "recent_diags": recent_diags,
        "maintenance_summary": maint_summary,
    })


# ── Patterns flotte ───────────────────────────────────────────────────────────

@app.route("/api/fleet/patterns", methods=["GET"])
def api_fleet_patterns():
    return jsonify(fleet.get_fleet_patterns())


# ── Backup ───────────────────────────────────────────────────────────────────

@app.route("/api/backup", methods=["POST"])
def api_backup():
    import shutil
    backup_dir = data_path("backups")
    os.makedirs(backup_dir, exist_ok=True)
    src = data_path("flotte.json")
    if not os.path.exists(src):
        return jsonify({"error": "Aucune donnée à sauvegarder"}), 404
    dst = os.path.join(backup_dir, f"flotte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy2(src, dst)
    backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("flotte_")], reverse=True)
    for old in backups[10:]:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass
    return jsonify({"success": True, "file": os.path.basename(dst), "count": len(backups[:10])})


# ── Client PDF ────────────────────────────────────────────────────────────────

@app.route("/api/export/client-pdf", methods=["POST"])
def api_export_client_pdf():
    from pdf_exporter import export_client_pdf
    data = request.get_json() or {}
    vin = data.get("vin")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    diagnostic = data.get("diagnostic")
    if not diagnostic:
        return jsonify({"error": "Diagnostic manquant"}), 400
    try:
        pdf_bytes = export_client_pdf(vehicle, diagnostic)
        filename = f"fiche_client_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = save_export(pdf_bytes, filename)
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        return jsonify({"error": f"Erreur PDF : {exc}"}), 500


# ── Technicians config ────────────────────────────────────────────────────────

@app.route("/api/config/technicians", methods=["GET"])
def api_get_technicians():
    return jsonify(load_config().get("technicians", ["Technicien 1"]))


@app.route("/api/config/technicians", methods=["PUT"])
def api_set_technicians():
    data = request.get_json() or {}
    config = load_config()
    config["technicians"] = data.get("technicians", [])
    save_config(config)
    return jsonify({"success": True})


# ── Rapport mensuel PDF ──────────────────────────────────────────────────────

@app.route("/api/export/monthly-report", methods=["GET"])
def api_export_monthly_report():
    try:
        month = int(request.args.get("month", datetime.now().month))
        year  = int(request.args.get("year",  datetime.now().year))
    except ValueError:
        return jsonify({"error": "Paramètres invalides"}), 400

    vehicles = fleet.get_all_vehicles()
    try:
        pdf_bytes = export_monthly_report(vehicles, month, year)
        filename = f"rapport_flotte_{year}_{month:02d}.pdf"
        path = save_export(pdf_bytes, filename)
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        return jsonify({"error": f"Erreur génération rapport : {exc}"}), 500


# ── Export Excel flotte ───────────────────────────────────────────────────────

@app.route("/api/export/excel", methods=["GET"])
def api_export_excel():
    vehicles = fleet.get_all_vehicles()
    try:
        xlsx_bytes = export_fleet_excel(vehicles)
        filename = f"flotte_{datetime.now().strftime('%Y%m%d')}.xlsx"
        path = save_export(xlsx_bytes, filename)
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        return jsonify({"error": f"Erreur export Excel : {exc}"}), 500


# ── Ouvrir dossier exports ───────────────────────────────────────────────────

@app.route("/api/open-exports", methods=["POST"])
def api_open_exports():
    export_dir = data_path("exports")
    os.makedirs(export_dir, exist_ok=True)
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", export_dir])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", export_dir])
        else:
            subprocess.Popen(["xdg-open", export_dir])
        return jsonify({"success": True, "path": export_dir})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Surveillance continue ─────────────────────────────────────────────────────

@app.route("/api/monitoring/start", methods=["POST"])
def api_monitoring_start():
    ok = obd.start_monitoring()
    if ok:
        return jsonify({"success": True, "message": "Surveillance démarrée"})
    return jsonify({"success": False, "message": "Surveillance déjà active"})


@app.route("/api/monitoring/stop", methods=["POST"])
def api_monitoring_stop():
    session = obd.stop_monitoring()
    if session:
        return jsonify({"success": True, "session": session})
    return jsonify({"success": False, "message": "Aucune session active"})


@app.route("/api/monitoring/status", methods=["GET"])
def api_monitoring_status():
    return jsonify(obd.get_session_status())


@app.route("/api/monitoring/analyze", methods=["POST"])
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


# ── Chat IA ───────────────────────────────────────────────────────────────────

@app.route("/api/audio/analyze", methods=["POST"])
def api_audio_analyze():
    """Analyse audio : décode WAV, calcule les stats + FFT, envoie à Claude (texte seul, sans scipy/matplotlib)."""
    import traceback as _tb
    import base64 as _b64, io, wave, math, struct
    try:
        from ai_analyzer import _get_client

        data = request.get_json(force=True, silent=True) or {}
        wav_b64 = data.get("wav", "")
        vehicle_ctx = data.get("vehicle_context", "véhicule inconnu")

        if not wav_b64:
            return jsonify({"error": "Pas de données audio"}), 400

        # ── Décoder WAV ──────────────────────────────────────────────────────
        try:
            wav_bytes = _b64.b64decode(wav_b64)
            with wave.open(io.BytesIO(wav_bytes)) as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_ch = wf.getnchannels()
                raw = wf.readframes(n_frames)
        except Exception as e:
            _log(f"[audio] Décodage WAV échoué : {e}")
            return jsonify({"error": f"Fichier audio invalide : {e}"}), 400

        # Convertir en float [-1, 1] (mono 16 bits)
        fmt = f"<{n_frames * n_ch}h"
        try:
            pcm = struct.unpack(fmt, raw)
        except struct.error:
            count = len(raw) // 2
            pcm = struct.unpack(f"<{count}h", raw[:count * 2])
        # Mixdown mono si stéréo
        if n_ch == 2:
            pcm = [(pcm[i] + pcm[i+1]) / 2 for i in range(0, len(pcm)-1, 2)]
        samples = [s / 32768.0 for s in pcm]
        n = len(samples)
        duration = n / sr if sr > 0 else 0

        if n < 512:
            return jsonify({"error": "Enregistrement trop court"}), 400

        # ── Statistiques de base ──────────────────────────────────────────────
        rms = math.sqrt(sum(s*s for s in samples) / n)
        peak = max(abs(s) for s in samples)
        db_rms = 20 * math.log10(rms + 1e-9)
        db_peak = 20 * math.log10(peak + 1e-9)

        # ── Énergie par bande via sous-échantillonnage (O(n), pur Python) ──────
        # Principe : la bande [0..f] se mesure sur le signal sous-échantillonné à 2f
        # On calcule la RMS de chaque sous-bande par différence
        band_labels = ["0-250Hz", "250-500Hz", "500-1kHz", "1k-2kHz", "2k-4kHz", "4k+Hz"]

        def rms_band(s, sr_in, lo, hi):
            """Énergie RMS du signal dans [lo, hi] Hz par filtrage moyenneur récursif."""
            # Filtre passe-bas simple (IIR 1er ordre) à la fréquence hi
            if hi >= sr_in / 2:
                hi_sig = list(s)
            else:
                alpha = math.exp(-2 * math.pi * hi / sr_in)
                hi_sig, y = [], 0.0
                for x in s:
                    y = (1 - alpha) * x + alpha * y
                    hi_sig.append(y)
            # Filtre passe-bas à lo → basse fréquence à soustraire
            if lo <= 0:
                lo_sig = [0.0] * len(s)
            else:
                alpha2 = math.exp(-2 * math.pi * lo / sr_in)
                lo_sig, y2 = [], 0.0
                for x in s:
                    y2 = (1 - alpha2) * x + alpha2 * y2
                    lo_sig.append(y2)
            band = [h - l for h, l in zip(hi_sig, lo_sig)]
            return math.sqrt(sum(v*v for v in band) / len(band)) if band else 0.0

        limits = [(0, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, sr // 2)]
        band_energy = [rms_band(samples, sr, lo, hi) for lo, hi in limits]
        total_e = sum(band_energy) or 1.0
        band_pct = [round(e / total_e * 100, 1) for e in band_energy]
        dominant_band = band_labels[band_pct.index(max(band_pct))]

        # ── Préparer le résumé acoustique pour Claude ─────────────────────────
        bands_str = "\n".join(f"  - {band_labels[i]}: {band_pct[i]}%" for i in range(len(band_labels)))
        audio_desc = f"""Durée : {duration:.1f}s | Fréquence d'échantillonnage : {sr} Hz
Niveau RMS : {db_rms:.1f} dBFS | Niveau crête : {db_peak:.1f} dBFS
Bande dominante : {dominant_band}

Répartition de l'énergie par bande de fréquence :
{bands_str}

Remarques :
- Niveau RMS > -20 dBFS = bruit fort/continu
- Niveau RMS < -40 dBFS = bruit léger ou intermittent
- Dominance basses fréquences (0-500Hz) = vibration mécanique grave (roulement, vilebrequin, détonation)
- Dominance moyennes fréquences (500-2kHz) = claquement soupapes, courroie, alternateur
- Dominance hautes fréquences (2kHz+) = sifflement (turbo, pneu, roulement usé)"""

        prompt = f"""Tu es un expert en diagnostic automobile et acoustique mécanique.

Voici l'analyse acoustique d'un bruit enregistré sur : {vehicle_ctx}

{audio_desc}

En te basant UNIQUEMENT sur ces données acoustiques, fournis un diagnostic :

1. 🔊 **Type de bruit probable** : claquement, grincement, frottement, vibration, sifflement, détonation...
2. 🔧 **Causes mécaniques probables** (ordonnées par probabilité selon les fréquences dominantes)
3. ⏱️ **Caractère du bruit** : continu / intermittent / rythmique / aléatoire (déduit du niveau RMS et des bandes)
4. ⚠️ **Urgence** : peut-on continuer à rouler ou faut-il stopper immédiatement ?
5. 🛠️ **Prochaine action** : quel diagnostic physique faire en priorité ?

Sois concis, précis et pratique. Si les données sont insuffisantes (bruit trop faible, silence), dis-le clairement."""

        client = _get_client()
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({
            "analysis": resp.content[0].text,
            "spectrogram": None,
            "duration": round(duration, 1),
            "sample_rate": sr,
            "bands": dict(zip(band_labels, band_pct)),
            "db_rms": round(db_rms, 1),
        })

    except Exception as e:
        _log(f"[audio] Erreur : {e}\n{_tb.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/vin/<vin>", methods=["GET"])
def api_decode_vin(vin):
    """Décode un VIN via NHTSA et retourne marque/modèle/année."""
    try:
        from ai_analyzer import decode_vin
        info = decode_vin(vin.upper().strip())
        return jsonify(info)
    except Exception as e:
        return jsonify({"vin": vin, "marque": "Inconnu", "modele": "", "annee": ""}), 200


@app.route("/api/chat", methods=["POST"])
def api_chat():
    from ai_analyzer import _get_client, decode_vin
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    history = data.get("history", [])
    vin = data.get("vin", "")
    context = data.get("context", {})

    if not message:
        return jsonify({"error": "Message vide"}), 400

    try:
        client = _get_client()
        vin_info = decode_vin(vin) if vin else {}

        ctx_lines = []
        if vin_info.get("marque") not in (None, "Inconnu"):
            ctx_lines.append(f"Véhicule : {vin_info['marque']} {vin_info.get('annee', '')}")
        if context.get("resume"):
            ctx_lines.append(f"Dernier diagnostic : {context['resume']}")
        # analyse peut être une liste (analyse classique) ou une string (session continue)
        analyse_data = context.get("analyse", [])
        if isinstance(analyse_data, str):
            if analyse_data.strip():
                ctx_lines.append(f"Analyse de session : {analyse_data[:500]}")
            codes = []
        else:
            codes = [a.get("code", "") for a in analyse_data if isinstance(a, dict) and a.get("code")]
        if codes:
            ctx_lines.append(f"Codes DTC : {', '.join(codes)}")

        system_prompt = (
            "Tu es un expert en diagnostic automobile OBD2 avec 20 ans d'expérience. "
            "Tu assistes un technicien dans son diagnostic. "
            "Réponds de manière concise et pratique, en français."
        )
        if ctx_lines:
            system_prompt += "\n\nContexte : " + " | ".join(ctx_lines)

        messages = []
        for h in history[-10:]:
            if h.get("role") in ("user", "assistant"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return jsonify({"response": response.content[0].text})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Configuration ────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    config = load_config()
    api_key_ok = bool(os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key"))
    # Return masked key prefix for display
    stored_key = config.get("anthropic_api_key", "")
    key_preview = (stored_key[:12] + "…") if len(stored_key) > 12 else ("" if not stored_key else stored_key)
    return jsonify({
        "port":            config.get("port", "COM3"),
        "baudrate":        config.get("baudrate", 9600),
        "timeout":         config.get("timeout", 10),
        "simulation_mode": obd.simulation_mode,
        "api_key_ok":      api_key_ok,
        "api_key_preview": key_preview,
    })


@app.route("/api/config/apikey", methods=["PUT"])
def api_config_set_apikey():
    data = request.get_json() or {}
    key = data.get("api_key", "").strip()
    if not key:
        return jsonify({"error": "Clé vide"}), 400
    config = load_config()
    config["anthropic_api_key"] = key
    save_config(config)
    # Reset cached client so next call uses the new key
    import ai_analyzer
    ai_analyzer._client = None
    return jsonify({"success": True})


@app.route("/api/config", methods=["PUT"])
def api_config_put():
    data = request.get_json() or {}
    config = load_config()
    if "port"     in data: config["port"]     = data["port"];     obd.port     = data["port"]
    if "baudrate" in data: config["baudrate"] = int(data["baudrate"]); obd.baudrate = int(data["baudrate"])
    if "timeout"  in data: config["timeout"]  = int(data["timeout"]);  obd.timeout  = int(data["timeout"])
    save_config(config)
    return jsonify({"success": True, "config": config})


# ── Détection automatique port OBD2 ──────────────────────────────────────────

@app.route("/api/config/detect-port", methods=["POST"])
def api_detect_port():
    """Scanne tous les ports COM et cherche un adaptateur ELM327."""
    import serial
    import serial.tools.list_ports
    import time

    BAUDRATES = [115200, 38400, 57600, 9600]
    found = None

    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        for baud in BAUDRATES:
            try:
                s = serial.Serial(p.device, baud, timeout=2)
                time.sleep(1.5)
                s.reset_input_buffer()
                s.write(b'ATZ\r')
                time.sleep(1.2)
                resp = s.read(200).decode('ascii', errors='replace')
                s.close()
                if 'ELM327' in resp or 'ELM' in resp or 'OK' in resp.upper():
                    found = {"port": p.device, "baudrate": baud, "desc": p.description}
                    break
            except Exception:
                pass
            if found:
                break
        if found:
            break

    if not found:
        return jsonify({"found": False, "message": "Aucun adaptateur ELM327 détecté. Vérifiez le branchement du câble."})

    # Sauvegarder automatiquement
    config = load_config()
    config["port"] = found["port"]
    config["baudrate"] = found["baudrate"]
    save_config(config)
    obd.port = found["port"]
    obd.baudrate = found["baudrate"]
    return jsonify({"found": True, "port": found["port"], "baudrate": found["baudrate"], "desc": found["desc"]})


# ── Test connexion OBD2 ───────────────────────────────────────────────────────

@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    return jsonify(obd.test_connection())


# ── Scan multi-ECU ────────────────────────────────────────────────────────────

@app.route("/api/scan-ecus", methods=["POST"])
def api_scan_ecus():
    """Scanne TOUS les modules ECU (ABS, airbag, BCM, boîte…) via ELM327 raw serial."""
    from ecu_scanner import MultiECUScanner

    data    = request.get_json() or {}
    make    = data.get("make", "GENERIC").upper().strip()
    port    = data.get("port") or obd.port

    # ELM327 nécessite au moins 38400 baud pour le scan multi-ECU
    # (9600 = défaut config OBD, trop lent pour les réponses CAN)
    cfg_baud = int(data.get("baudrate") or obd.baudrate or 9600)
    baudrate = max(cfg_baud, 38400)

    # Bloquer si mode simulation (pas de port série réel)
    if obd.simulation_mode:
        return jsonify({
            "error": "Scan indisponible en mode simulation — branchez un adaptateur ELM327 réel.",
            "modules": [], "total_dtcs": 0, "modules_found": 0,
        }), 400

    _log(f"[scan-ecus] Démarrage : marque={make}, port={port}, baud={baudrate}")

    # Déconnecter l'OBD standard si actif pour libérer le port série
    was_connected = bool(
        obd.connection and
        hasattr(obd.connection, "is_connected") and
        obd.connection.is_connected()
    )
    if was_connected:
        try:
            obd.connection.close()
            obd.connection = None
        except Exception:
            pass

    try:
        scanner = MultiECUScanner(port, baudrate=baudrate, timeout=3.0)
        results = scanner.scan_all(make)
        _log(f"[scan-ecus] Terminé : {results.get('modules_found',0)} modules actifs, "
             f"{results.get('total_dtcs',0)} DTCs total")
        return jsonify(results)
    except Exception as e:
        _log(f"[scan-ecus] Erreur : {e}")
        return jsonify({"error": str(e), "modules": [], "total_dtcs": 0, "modules_found": 0}), 500
    finally:
        # Reconnecter si nécessaire
        if was_connected:
            try:
                obd.connect()
            except Exception:
                pass


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import threading
    import webbrowser

    api_key = os.environ.get("ANTHROPIC_API_KEY") or load_config().get("anthropic_api_key")

    print("=" * 55)
    print("  Outil de diagnostic automobile OBD2")
    print("=" * 55)
    print(f"  Acces : http://localhost:5000")
    print(f"  Cle API IA : {'OK' if api_key else 'Non definie — saisir dans Parametres > Cle API'}")
    print(f"  Port OBD2  : {obd.port}")
    print(f"  Simulation : {'Activee' if obd.simulation_mode else 'Desactivee'}")
    print("=" * 55)

    # Ouvre le navigateur automatiquement après 1 seconde
    def open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser, daemon=True).start()

    app.run(debug=False, host="0.0.0.0", port=5000)
