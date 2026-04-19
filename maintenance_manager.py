"""
Gestionnaire de maintenance — modèle commun + états d'usure par véhicule.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta

_save_lock = threading.Lock()

from base_path import data_path

MAINTENANCE_FILE = data_path("maintenance.json")

DEFAULT_TEMPLATE = [
    # Scheduled
    {"id": "vidange",      "label": "Vidange moteur",             "category": "Moteur",        "icon": "🛢️",  "type": "scheduled", "interval_km": 10000, "interval_months": 12, "custom": False},
    {"id": "courroie",     "label": "Courroie de distribution",   "category": "Moteur",        "icon": "⚙️",  "type": "scheduled", "interval_km": 60000, "interval_months": 60, "custom": False},
    {"id": "bougies",      "label": "Bougies d'allumage",         "category": "Moteur",        "icon": "⚡",  "type": "scheduled", "interval_km": 30000, "interval_months": 36, "custom": False},
    {"id": "filtre_air",   "label": "Filtre à air",               "category": "Moteur",        "icon": "💨",  "type": "scheduled", "interval_km": 15000, "interval_months": 12, "custom": False},
    {"id": "filtre_carb",  "label": "Filtre à carburant",         "category": "Moteur",        "icon": "⛽",  "type": "scheduled", "interval_km": 30000, "interval_months": 24, "custom": False},
    {"id": "filtre_hab",   "label": "Filtre d'habitacle",         "category": "Habitacle",     "icon": "🌀",  "type": "scheduled", "interval_km": 15000, "interval_months": 12, "custom": False},
    {"id": "liq_frein",    "label": "Liquide de frein",           "category": "Freinage",      "icon": "🔴",  "type": "scheduled", "interval_km": None,  "interval_months": 24, "custom": False},
    {"id": "liq_refroid",  "label": "Liquide de refroidissement", "category": "Moteur",        "icon": "🌡️", "type": "scheduled", "interval_km": 60000, "interval_months": 36, "custom": False},
    {"id": "ct",           "label": "Contrôle technique",         "category": "Administratif", "icon": "📋",  "type": "scheduled", "interval_km": None,  "interval_months": 24, "custom": False},
    # Wear
    {"id": "pneus",        "label": "Pneus",                      "category": "Roues",         "icon": "🔵",  "type": "wear",
     "wear_states": ["Neuf", "Légèrement usé", "Usure avancée", "Usure anormale", "Prévoir changement"], "custom": False},
    {"id": "plaq_av",      "label": "Plaquettes avant",           "category": "Freinage",      "icon": "🛑",  "type": "wear",
     "wear_states": ["Neuf", "Légèrement usé", "Usure avancée", "Usure anormale", "Prévoir changement"], "custom": False},
    {"id": "plaq_ar",      "label": "Plaquettes arrière",         "category": "Freinage",      "icon": "🛑",  "type": "wear",
     "wear_states": ["Neuf", "Légèrement usé", "Usure avancée", "Usure anormale", "Prévoir changement"], "custom": False},
    {"id": "disques_av",   "label": "Disques avant",              "category": "Freinage",      "icon": "⭕",  "type": "wear",
     "wear_states": ["Neuf", "Légèrement usé", "Usure avancée", "Usure anormale", "Prévoir changement"], "custom": False},
    {"id": "disques_ar",   "label": "Disques arrière",            "category": "Freinage",      "icon": "⭕",  "type": "wear",
     "wear_states": ["Neuf", "Légèrement usé", "Usure avancée", "Usure anormale", "Prévoir changement"], "custom": False},
    {"id": "amortisseurs", "label": "Amortisseurs",               "category": "Suspension",    "icon": "🔧",  "type": "wear",
     "wear_states": ["OK", "Début d'usure", "À surveiller", "À changer"], "custom": False},
    {"id": "essuie_gl",    "label": "Essuie-glaces",              "category": "Visibilité",    "icon": "🌧️", "type": "wear",
     "wear_states": ["OK", "Légèrement usé", "Rayures / bruits", "À changer"], "custom": False},
]

_WEAR_URGENT = {"Usure anormale", "Prévoir changement", "À changer"}
_WEAR_WARN   = {"Usure avancée", "À surveiller", "Rayures / bruits", "Début d'usure"}


def _load() -> dict:
    if os.path.exists(MAINTENANCE_FILE):
        try:
            with open(MAINTENANCE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"template": [dict(t) for t in DEFAULT_TEMPLATE], "vehicles": {}}


def _save(data: dict):
    with _save_lock:
        parent = os.path.dirname(MAINTENANCE_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ── Template ─────────────────────────────────────────────────────────────────

def get_template() -> list:
    return _load().get("template", [dict(t) for t in DEFAULT_TEMPLATE])


def add_custom_item(label: str, item_type: str, category: str = "Autre",
                    icon: str = "🔧",
                    interval_km: int = None, interval_months: int = None,
                    wear_states: list = None) -> dict:
    data = _load()
    item = {
        "id": f"custom_{uuid.uuid4().hex[:8]}",
        "label": label, "category": category, "icon": icon,
        "type": item_type, "custom": True,
    }
    if item_type == "scheduled":
        item["interval_km"] = interval_km
        item["interval_months"] = interval_months
    else:
        item["wear_states"] = wear_states or ["OK", "À surveiller", "À changer"]
    data["template"].append(item)
    _save(data)
    return item


def delete_custom_item(item_id: str) -> bool:
    data = _load()
    before = len(data["template"])
    data["template"] = [t for t in data["template"]
                        if not (t["id"] == item_id and t.get("custom"))]
    if len(data["template"]) < before:
        _save(data)
        return True
    return False


# ── Per-vehicle ───────────────────────────────────────────────────────────────

def _wear_status(state: str) -> str:
    if state in _WEAR_URGENT: return "urgent"
    if state in _WEAR_WARN:   return "warning"
    return "ok"


def _scheduled_status(next_date, next_km, current_km: int) -> str:
    ds, ks = "unknown", "unknown"
    if next_date:
        try:
            days = (datetime.fromisoformat(next_date) - datetime.now()).days
            ds = "urgent" if days < 0 else ("warning" if days <= 30 else "ok")
        except Exception:
            pass
    if next_km and current_km:
        rem = next_km - current_km
        ks = "urgent" if rem <= 0 else ("warning" if rem <= 1500 else "ok")
    if "urgent"  in (ds, ks): return "urgent"
    if "warning" in (ds, ks): return "warning"
    if "ok"      in (ds, ks): return "ok"
    return "unknown"


def get_vehicle_maintenance(vin: str, current_km: int = 0) -> list:
    data = _load()
    template = data.get("template", [dict(t) for t in DEFAULT_TEMPLATE])
    vdata = data.get("vehicles", {}).get(vin, {})
    result = []
    for item in template:
        entry = dict(item)
        v = vdata.get(item["id"], {})
        if item["type"] == "scheduled":
            entry["last_date"] = v.get("last_date")
            entry["last_km"]   = v.get("last_km")
            entry["next_date"] = v.get("next_date")
            entry["next_km"]   = v.get("next_km")
            entry["status"]    = _scheduled_status(entry["next_date"], entry["next_km"], current_km)
        else:
            states = item.get("wear_states", ["OK", "À changer"])
            entry["wear_state"]   = v.get("wear_state", states[0])
            entry["updated_date"] = v.get("updated_date")
            entry["updated_km"]   = v.get("updated_km")
            entry["status"]       = _wear_status(entry["wear_state"])
        result.append(entry)
    return result


def mark_done(vin: str, item_id: str, done_date: str, done_km: int) -> dict | None:
    data = _load()
    tpl = {t["id"]: t for t in data.get("template", DEFAULT_TEMPLATE)}
    item = tpl.get(item_id)
    if not item:
        return None
    try:
        done_dt = datetime.fromisoformat(done_date)
    except (ValueError, TypeError):
        done_date = datetime.now().strftime("%Y-%m-%d")
        done_dt = datetime.now()
    entry = {"last_date": done_date, "last_km": done_km}
    if item.get("interval_months"):
        entry["next_date"] = (done_dt + timedelta(days=item["interval_months"] * 30.44)).strftime("%Y-%m-%d")
    else:
        entry["next_date"] = None
    entry["next_km"] = (done_km + item["interval_km"]) if item.get("interval_km") and done_km else None
    data.setdefault("vehicles", {}).setdefault(vin, {})[item_id] = entry
    _save(data)
    return entry


def update_wear(vin: str, item_id: str, wear_state: str, current_km: int = None) -> dict:
    data = _load()
    entry = {
        "wear_state":   wear_state,
        "updated_date": datetime.now().strftime("%Y-%m-%d"),
        "updated_km":   current_km,
    }
    data.setdefault("vehicles", {}).setdefault(vin, {})[item_id] = entry
    _save(data)
    return entry


def get_fleet_summary(vins_km: dict) -> dict:
    """vins_km = {vin: current_km}. Returns urgent/warning lists."""
    urgent, warning = [], []
    for vin, km in vins_km.items():
        for item in get_vehicle_maintenance(vin, km):
            s = item.get("status")
            obj = {"vin": vin, "label": item["label"], "icon": item.get("icon", "")}
            if s == "urgent":   urgent.append(obj)
            elif s == "warning": warning.append(obj)
    return {"urgent": urgent, "warning": warning}
