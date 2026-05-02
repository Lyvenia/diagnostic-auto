from flask import Blueprint, jsonify, request
from shared import obd, fleet
from export.pdf import export_diagnostic_pdf, export_monthly_report, export_client_pdf, export_maintenance_pdf
from export.excel import export_fleet_excel
from core.config import load_config
from core.paths import data_path, LOG_PATH
from datetime import datetime
import os
import sys
import subprocess
import time as _t
import traceback as _tb

bp = Blueprint('export', __name__)


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [export] {msg}\n")
    except Exception:
        pass


def _safe_name(s: str) -> str:
    """Nettoie une chaîne pour en faire un nom de dossier valide."""
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in (s or "")).strip()
    safe = "_".join(safe.split())
    return safe[:40] or "inconnu"


def _build_garage(cfg: dict) -> dict:
    """Extrait les infos garage depuis la config — utilisé par toutes les routes PDF."""
    return {k: cfg.get(f"garage_{k}", "") for k in ("nom", "adresse", "tel", "email", "siret")}


def _open_path(path: str):
    """Ouvre un dossier dans l'explorateur système selon la plateforme."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _folder_name(vin: str) -> str:
    """Retourne 'Code_Marque_Modele_Annee' si dispo, sinon le VIN tronqué."""
    v = fleet.get_vehicle(vin)
    if not v:
        return "".join(c for c in (vin or "") if c.isalnum() or c in "_-")[:20]
    parts = []
    if v.get("code"):
        parts.append(v["code"])
    if v.get("surnom"):
        parts.append(v["surnom"])
    else:
        if v.get("marque"): parts.append(v["marque"])
        if v.get("modele"): parts.append(v["modele"])
        if v.get("annee"):  parts.append(str(v["annee"]))
    return _safe_name(" ".join(parts)) if parts else "".join(c for c in vin if c.isalnum())[:20]


def save_export(file_bytes: bytes, filename: str, vin: str = None) -> str:
    if vin:
        export_dir = data_path(f"exports/{_folder_name(vin)}")
    else:
        export_dir = data_path("exports")
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


@bp.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    t0 = _t.time()
    data = request.get_json() or {}
    vin = data.get("vin")
    _log(f"[pdf] → VIN={vin!r}")
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
        _log(f"[pdf] ✗ diagnostic manquant")
        return jsonify({"error": "Diagnostic non trouvé"}), 404

    try:
        garage    = _build_garage(load_config())
        _log(f"[pdf] génération PDF…")
        pdf_bytes = export_diagnostic_pdf(vehicle, diagnostic, garage=garage)
        _log(f"[pdf] PDF généré : {len(pdf_bytes)} octets en {_t.time()-t0:.1f}s")
        filename  = f"diagnostic_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = save_export(pdf_bytes, filename, vin=vin)
        _log(f"[pdf] ✓ sauvé : {path} (total {_t.time()-t0:.1f}s)")
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        _log(f"[pdf] ✗ CRASH après {_t.time()-t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": f"Erreur génération PDF : {exc}"}), 500


@bp.route("/api/export/client-pdf", methods=["POST"])
def api_export_client_pdf():
    t0 = _t.time()
    data = request.get_json() or {}
    vin = data.get("vin")
    _log(f"[client-pdf] → VIN={vin!r}")
    if not vin:
        return jsonify({"error": "VIN manquant"}), 400
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    diagnostic = data.get("diagnostic")
    if not diagnostic:
        return jsonify({"error": "Diagnostic manquant"}), 400
    try:
        garage    = _build_garage(load_config())
        pdf_bytes = export_client_pdf(vehicle, diagnostic, garage=garage)
        filename = f"fiche_client_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = save_export(pdf_bytes, filename, vin=vin)
        _log(f"[client-pdf] ✓ {path} ({_t.time()-t0:.1f}s)")
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        _log(f"[client-pdf] ✗ CRASH après {_t.time()-t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": f"Erreur PDF : {exc}"}), 500


@bp.route("/api/export/monthly-report", methods=["GET"])
def api_export_monthly_report():
    t0 = _t.time()
    try:
        month = int(request.args.get("month", datetime.now().month))
        year  = int(request.args.get("year",  datetime.now().year))
    except (ValueError, TypeError):
        return jsonify({"error": "Paramètres invalides"}), 400

    _log(f"[monthly] → {year}-{month:02d}")
    try:
        vehicles = fleet.get_all_vehicles()
        pdf_bytes = export_monthly_report(vehicles, month, year)
        filename = f"rapport_flotte_{year}_{month:02d}.pdf"
        path = save_export(pdf_bytes, filename)
        _log(f"[monthly] ✓ {path} ({_t.time()-t0:.1f}s)")
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        _log(f"[monthly] ✗ CRASH après {_t.time()-t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": f"Erreur génération rapport : {exc}"}), 500


@bp.route("/api/export/excel", methods=["GET"])
def api_export_excel():
    t0 = _t.time()
    _log("[excel] →")
    try:
        vehicles = fleet.get_all_vehicles()
        xlsx_bytes = export_fleet_excel(vehicles)
        filename = f"flotte_{datetime.now().strftime('%Y%m%d')}.xlsx"
        path = save_export(xlsx_bytes, filename)
        _log(f"[excel] ✓ {path} ({_t.time()-t0:.1f}s)")
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        _log(f"[excel] ✗ CRASH après {_t.time()-t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": f"Erreur export Excel : {exc}"}), 500


@bp.route("/api/export/maintenance-pdf/<vin>", methods=["POST"])
def api_export_maintenance_pdf(vin):
    t0 = _t.time()
    _log(f"[maint-pdf] → VIN={vin!r}")
    from fleet.maintenance import get_vehicle_maintenance
    vehicle = fleet.get_vehicle(vin)
    if not vehicle:
        return jsonify({"error": "Véhicule non trouvé"}), 404
    try:
        repairs = fleet.get_repairs(vin)
        hist    = vehicle.get("historique") or []
        km_raw  = vehicle.get("km_manuel")
        if km_raw is None and hist and isinstance(hist[0], dict):
            km_raw = hist[0].get("kilometrage", 0)
        try:
            km = int(km_raw) if km_raw is not None else 0
        except (TypeError, ValueError):
            km = 0
        items     = get_vehicle_maintenance(vin, km)
        garage    = _build_garage(load_config())
        pdf_bytes = export_maintenance_pdf(vehicle, items, repairs, garage=garage)
        filename = f"entretien_{vin}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        path = save_export(pdf_bytes, filename, vin=vin)
        _log(f"[maint-pdf] ✓ {path} ({_t.time()-t0:.1f}s)")
        return jsonify({"success": True, "filename": filename, "path": path})
    except Exception as exc:
        _log(f"[maint-pdf] ✗ CRASH après {_t.time()-t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": f"Erreur PDF entretien : {exc}"}), 500


@bp.route("/api/export/documents/<vin>", methods=["GET"])
def api_export_documents(vin):
    export_dir = data_path(f"exports/{_folder_name(vin)}")
    if not os.path.exists(export_dir):
        return jsonify([])
    docs = []
    for fname in sorted(os.listdir(export_dir), reverse=True):
        if fname.lower().endswith(".pdf"):
            fpath = os.path.join(export_dir, fname)
            try:
                stat = os.stat(fpath)
                docs.append({
                    "filename": fname,
                    "path":     fpath,
                    "size_kb":  round(stat.st_size / 1024, 1),
                    "date":     datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y à %H:%M"),
                })
            except OSError:
                pass
    return jsonify(docs)


@bp.route("/api/export/open-vehicle/<vin>", methods=["POST"])
def api_export_open_vehicle(vin):
    export_dir = data_path(f"exports/{_folder_name(vin)}")
    os.makedirs(export_dir, exist_ok=True)
    try:
        _open_path(export_dir)
        return jsonify({"success": True, "path": export_dir})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/open-url", methods=["POST"])
def api_open_url():
    """Ouvre une URL externe dans le navigateur système par défaut."""
    data = request.get_json() or {}
    url  = (data.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL invalide"}), 400
    try:
        import webbrowser
        webbrowser.open(url)
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/open-exports", methods=["POST"])
def api_open_exports():
    export_dir = data_path("exports")
    os.makedirs(export_dir, exist_ok=True)
    try:
        _open_path(export_dir)
        return jsonify({"success": True, "path": export_dir})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/backup", methods=["POST"])
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
