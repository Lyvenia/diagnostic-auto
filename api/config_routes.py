from flask import Blueprint, jsonify, request
from shared import obd, fleet
from core.config import load_config, save_config
from core.paths import data_path
from core.version import RODIA_VERSION
from datetime import datetime
import json
import time as _t
import os

bp = Blueprint('config', __name__)

# Source de vérité unique : core/version.py (bumpé par release.py)
APP_VERSION = RODIA_VERSION

# ──────────────────────────────────────────────────────────────────────────────
#  Préférences UI persistées côté serveur (ui_prefs.json dans %APPDATA%\RODIA)
#  Source de vérité pour : nom utilisateur, thème, taille fenêtre, plein écran,
#  visite guidée vue. Le localStorage Edge n'est PAS fiable entre sessions
#  (lock/temp profile selon configuration), donc on persiste côté serveur.
# ──────────────────────────────────────────────────────────────────────────────
_PREFS_FILE = data_path("ui_prefs.json")

def _load_prefs() -> dict:
    try:
        with open(_PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save_prefs(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_PREFS_FILE), exist_ok=True)
        with open(_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


@bp.route("/api/prefs", methods=["GET"])
def api_prefs_get():
    return jsonify(_load_prefs())


@bp.route("/api/prefs", methods=["PUT"])
def api_prefs_put():
    """Merge des préférences entrantes avec celles déjà stockées.
    Body : { "key1": "value1", "key2": null (= delete), ... }"""
    incoming = request.get_json(silent=True) or {}
    if not isinstance(incoming, dict):
        return jsonify({"error": "body must be an object"}), 400
    current = _load_prefs()
    for k, v in incoming.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v
    if not _save_prefs(current):
        return jsonify({"error": "save failed"}), 500
    return jsonify({"ok": True, "prefs": current})


@bp.route("/health")
def health():
    """Endpoint léger utilisé par main.py pour confirmer que Flask est prêt."""
    return "OK", 200


@bp.route("/api/version")
def api_version():
    """Retourne la version et les infos éditeur du logiciel."""
    return jsonify({"version": APP_VERSION, "name": "RODIA", "editor": "Lyvenia"})


@bp.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    """Reçoit un ping JS toutes les 5s — main.py surveille ce fichier pour savoir si la fenêtre est ouverte."""
    try:
        hb_file = data_path(".heartbeat")
        with open(hb_file, "w") as f:
            f.write(str(_t.time()))
    except Exception:
        pass
    return "", 204


@bp.route("/api/config/technicians", methods=["GET"])
def api_get_technicians():
    return jsonify(load_config().get("technicians", ["Technicien 1"]))


@bp.route("/api/config/technicians", methods=["PUT"])
def api_set_technicians():
    data = request.get_json() or {}
    config = load_config()
    config["technicians"] = data.get("technicians", [])
    save_config(config)
    return jsonify({"success": True})


@bp.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    try:
        from fleet.maintenance import get_fleet_summary
        vehicles = fleet.get_all_vehicles()
        # Scores santé : batch pour éviter N acquisitions de lock
        health = fleet.get_all_health_scores()
        scores = [h["score"] for h in health.values() if "score" in h]
        avg_score = round(sum(scores) / len(scores)) if scores else 0
        # Diagnostics récents (10 derniers toutes flottes confondues)
        all_diags = []
        vins_km = {}
        for v in vehicles:
            vin = v.get("vin", "")
            if not vin:
                continue
            label = f"{v.get('marque','')} {v.get('modele','')}".strip() or vin
            hist = v.get("historique", [])
            vins_km[vin] = hist[0].get("kilometrage", 0) if hist else 0
            for entry in hist[:5]:
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
        maint_summary = get_fleet_summary(vins_km)
        return jsonify({
            "avg_score": avg_score,
            "health": health,
            "vehicles": [{"vin": v.get("vin"), "marque": v.get("marque"), "modele": v.get("modele"), "annee": v.get("annee")} for v in vehicles],
            "recent_diags": all_diags[:10],
            "maintenance_summary": maint_summary,
        })
    except Exception as exc:
        import traceback
        try:
            with open(data_path("DiagnosticAuto_error.log"), "a", encoding="utf-8") as f:
                f.write(f"[{_t.strftime('%H:%M:%S')}] [dashboard] ✗ {exc}\n{traceback.format_exc()}\n")
        except Exception:
            pass
        return jsonify({"error": f"Tableau de bord indisponible : {exc}"}), 500


@bp.route("/api/scan-ecus", methods=["POST"])
def api_scan_ecus():
    """Scanne TOUS les modules ECU (ABS, airbag, BCM, boîte…) via ELM327 raw serial."""
    from ecu_scanner import MultiECUScanner

    data    = request.get_json() or {}
    make    = data.get("make", "GENERIC").upper().strip()
    port    = data.get("port") or obd.port

    cfg_baud = int(data.get("baudrate") or obd.baudrate or 9600)
    baudrate = max(cfg_baud, 38400)

    if obd.simulation_mode:
        return jsonify({
            "error": "Scan indisponible en mode simulation — branchez un adaptateur ELM327 réel.",
            "modules": [], "total_dtcs": 0, "modules_found": 0,
        }), 400

    try:
        with open(data_path("DiagnosticAuto_error.log"), "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [scan-ecus] Démarrage : marque={make}, port={port}, baud={baudrate}\n")
    except Exception:
        pass

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
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "modules": [], "total_dtcs": 0, "modules_found": 0}), 500
    finally:
        if was_connected:
            try:
                obd.connect()
            except Exception:
                pass


@bp.route("/api/config/garage", methods=["GET"])
def api_config_garage_get():
    config = load_config()
    return jsonify({
        "nom":      config.get("garage_nom", ""),
        "adresse":  config.get("garage_adresse", ""),
        "tel":      config.get("garage_tel", ""),
        "email":    config.get("garage_email", ""),
        "siret":    config.get("garage_siret", ""),
        "logo_b64": config.get("garage_logo_b64", ""),
    })


@bp.route("/api/config/garage", methods=["PUT"])
def api_config_garage_put():
    data   = request.get_json() or {}
    config = load_config()
    for field in ("nom", "adresse", "tel", "email", "siret", "logo_b64"):
        key = f"garage_{field}"
        if field in data:
            config[key] = data[field]
    save_config(config)
    return jsonify({"success": True})


@bp.route("/api/config", methods=["GET"])
def api_config_get():
    config = load_config()
    import os as _os
    api_key_ok = bool(_os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key"))
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


@bp.route("/api/config/apikey", methods=["PUT"])
def api_config_set_apikey():
    data = request.get_json() or {}
    key = data.get("api_key", "").strip()
    if not key:
        return jsonify({"error": "Clé vide"}), 400
    config = load_config()
    config["anthropic_api_key"] = key
    save_config(config)
    # Reset cached client so next call uses the new key
    import analysis.vin_decoder as _vd
    _vd._client = None
    return jsonify({"success": True})


@bp.route("/api/config", methods=["PUT"])
def api_config_put():
    data = request.get_json() or {}
    config = load_config()
    if "port"     in data: config["port"]     = data["port"];     obd.port     = data["port"]
    if "baudrate" in data: config["baudrate"] = int(data["baudrate"]); obd.baudrate = int(data["baudrate"])
    if "timeout"  in data: config["timeout"]  = int(data["timeout"]);  obd.timeout  = int(data["timeout"])
    save_config(config)
    return jsonify({"success": True, "config": config})


@bp.route("/api/config/detect-port", methods=["POST"])
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

    config = load_config()
    config["port"] = found["port"]
    config["baudrate"] = found["baudrate"]
    save_config(config)
    obd.port = found["port"]
    obd.baudrate = found["baudrate"]
    return jsonify({"found": True, "port": found["port"], "baudrate": found["baudrate"], "desc": found["desc"]})


@bp.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    return jsonify(obd.test_connection())


@bp.route("/api/vin/<vin>", methods=["GET"])
def api_decode_vin(vin):
    """Décode un VIN via NHTSA et retourne marque/modèle/année."""
    try:
        from analysis.vin_decoder import decode_vin
        info = decode_vin(vin.upper().strip())
        return jsonify(info)
    except Exception as e:
        return jsonify({"vin": vin, "marque": "Inconnu", "modele": "", "annee": ""}), 200


@bp.route("/api/chat", methods=["POST"])
def api_chat():
    from analysis.vin_decoder import _get_client, decode_vin
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
