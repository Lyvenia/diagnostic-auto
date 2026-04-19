"""
Gestionnaire de flotte — stockage JSON local (flotte.json).
"""
import json
import os
from collections import defaultdict
from datetime import datetime

from base_path import data_path

FLEET_FILE = data_path("flotte.json")

MAINTENANCE_INTERVALS = [
    {"label": "Vidange moteur",            "km": 10_000, "icon": "🛢️"},
    {"label": "Filtre à air",              "km": 15_000, "icon": "💨"},
    {"label": "Filtre à huile",            "km": 10_000, "icon": "🔧"},
    {"label": "Filtre habitacle",          "km": 15_000, "icon": "🌀"},
    {"label": "Liquide de frein",          "km": 40_000, "icon": "🔴"},
    {"label": "Plaquettes de frein",       "km": 40_000, "icon": "🛑"},
    {"label": "Courroie de distribution",  "km": 60_000, "icon": "⚙️"},
    {"label": "Bougies d'allumage",        "km": 30_000, "icon": "⚡"},
    {"label": "Liquide de refroidissement","km": 60_000, "icon": "🌡️"},
    {"label": "Pneus (vérification)",      "km": 10_000, "icon": "🔵"},
]


class FleetManager:
    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self.fleet: dict = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if os.path.exists(FLEET_FILE):
            try:
                with open(FLEET_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        with self._lock:
            with open(FLEET_FILE, "w", encoding="utf-8") as f:
                json.dump(self.fleet, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Vehicle CRUD
    # ------------------------------------------------------------------

    def get_all_vehicles(self) -> list:
        return list(self.fleet.values())

    def get_vehicle(self, vin: str) -> dict | None:
        return self.fleet.get(vin)

    def delete_vehicle(self, vin: str) -> bool:
        if vin in self.fleet:
            del self.fleet[vin]
            self._save()
            return True
        return False

    def create_or_get_vehicle(self, vin: str, vin_info: dict, simulated: bool = False) -> tuple[dict, bool]:
        """Return (vehicle, is_new). Creates vehicle if not already in fleet."""
        if vin not in self.fleet:
            self.fleet[vin] = {
                "vin": vin,
                "marque": vin_info.get("marque", "Inconnu"),
                "modele": vin_info.get("modele", "Inconnu"),
                "annee": vin_info.get("annee", "Inconnu"),
                "motorisation": vin_info.get("motorisation", ""),
                "premier_diagnostic": datetime.now().isoformat(),
                "historique": [],
                "reparations": [],
                "alertes_km": [],
                "statut_dernier_diagnostic": "OK",
                "notes": "",
                "simulated": simulated,
                "code": "",
                "surnom": "",
                "groupe": "",
            }
            self._save()
            return self.fleet[vin], True
        return self.fleet[vin], False

    def update_vehicle_info(self, vin: str, info: dict):
        if vin in self.fleet:
            self.fleet[vin].update(info)
            self._save()

    def update_vehicle_fleet_info(self, vin: str, code: str, surnom: str, groupe: str) -> dict | None:
        """Update code, surnom and groupe for a vehicle. Returns updated vehicle."""
        if vin not in self.fleet:
            return None
        self.fleet[vin]["code"] = code
        self.fleet[vin]["surnom"] = surnom
        self.fleet[vin]["groupe"] = groupe
        self._save()
        return self.fleet[vin]

    def get_groups(self) -> list:
        """Returns list of unique non-empty group names from all vehicles."""
        groups = set()
        for vehicle in self.fleet.values():
            g = vehicle.get("groupe", "")
            if g:
                groups.add(g)
        return sorted(groups)

    def get_vehicles_by_group(self) -> dict:
        """Returns dict {groupe: [vehicles]}. Vehicles without groupe go under '' key."""
        result = {}
        for vehicle in self.fleet.values():
            g = vehicle.get("groupe", "")
            if g not in result:
                result[g] = []
            result[g].append(vehicle)
        return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def save_diagnostic(self, vin: str, diagnostic: dict) -> dict | None:
        if vin not in self.fleet:
            return None

        now = datetime.now()
        entry = {
            "id": now.strftime("%Y%m%d_%H%M%S"),
            "date": now.isoformat(),
            "date_affichage": now.strftime("%d/%m/%Y à %H:%M"),
            "kilometrage": diagnostic.get("kilometrage", 0),
            "dtc_codes": diagnostic.get("dtc_codes", []),
            "donnees_temps_reel": diagnostic.get("donnees_temps_reel", {}),
            "analyse_ia": diagnostic.get("analyse_ia", {}),
            "statut": diagnostic.get("statut", "OK"),
            "technicien": diagnostic.get("technicien", ""),
        }

        # Most recent first
        self.fleet[vin]["historique"].insert(0, entry)
        self.fleet[vin]["statut_dernier_diagnostic"] = entry["statut"]
        self._save()
        return entry

    def get_history(self, vin: str) -> list:
        vehicle = self.fleet.get(vin)
        if vehicle:
            return vehicle.get("historique", [])
        return []

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def update_notes(self, vin: str, notes: str) -> bool:
        if vin in self.fleet:
            self.fleet[vin]["notes"] = notes
            self._save()
            return True
        return False

    # ------------------------------------------------------------------
    # Réparations
    # ------------------------------------------------------------------

    def add_repair(self, vin: str, repair: dict) -> dict | None:
        if vin not in self.fleet:
            return None
        if "reparations" not in self.fleet[vin]:
            self.fleet[vin]["reparations"] = []
        now = datetime.now()
        entry = {
            "id": now.strftime("%Y%m%d_%H%M%S"),
            "date": now.isoformat(),
            "date_affichage": repair.get("date") or now.strftime("%d/%m/%Y"),
            "description": repair.get("description", ""),
            "pieces": repair.get("pieces", ""),
            "cout": repair.get("cout", ""),
            "technicien": repair.get("technicien", ""),
        }
        self.fleet[vin]["reparations"].insert(0, entry)
        self._save()
        return entry

    def get_repairs(self, vin: str) -> list:
        vehicle = self.fleet.get(vin)
        if vehicle:
            return vehicle.get("reparations", [])
        return []

    # ------------------------------------------------------------------
    # Patterns flotte
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Alertes kilométrage
    # ------------------------------------------------------------------

    def get_km_alerts(self, vin: str) -> list:
        vehicle = self.fleet.get(vin)
        if vehicle:
            return vehicle.get("alertes_km", [])
        return []

    def add_km_alert(self, vin: str, alert: dict) -> dict | None:
        if vin not in self.fleet:
            return None
        if "alertes_km" not in self.fleet[vin]:
            self.fleet[vin]["alertes_km"] = []
        now = datetime.now()
        entry = {
            "id": now.strftime("%Y%m%d_%H%M%S_%f"),
            "label": alert.get("label", "Alerte"),
            "km_seuil": int(alert.get("km_seuil", 0)),
        }
        self.fleet[vin]["alertes_km"].append(entry)
        self._save()
        return entry

    def delete_km_alert(self, vin: str, alert_id: str) -> bool:
        if vin not in self.fleet:
            return False
        before = len(self.fleet[vin].get("alertes_km", []))
        self.fleet[vin]["alertes_km"] = [
            a for a in self.fleet[vin].get("alertes_km", [])
            if a.get("id") != alert_id
        ]
        self._save()
        return len(self.fleet[vin]["alertes_km"]) < before

    def get_all_alerts_status(self) -> list:
        """Returns triggered alerts for each vehicle based on last diagnostic km."""
        result = []
        for vin, vehicle in self.fleet.items():
            alerts = vehicle.get("alertes_km", [])
            if not alerts:
                continue
            hist = vehicle.get("historique", [])
            last_km = hist[0].get("kilometrage", 0) if hist else 0
            triggered = [a for a in alerts if last_km >= a.get("km_seuil", 0)]
            if triggered:
                result.append({
                    "vin": vin,
                    "marque": vehicle.get("marque", ""),
                    "annee": vehicle.get("annee", ""),
                    "km_actuel": last_km,
                    "alertes": triggered,
                })
        return result

    # ------------------------------------------------------------------
    # Health score & maintenance
    # ------------------------------------------------------------------

    def get_health_score(self, vin: str) -> dict:
        vehicle = self.fleet.get(vin)
        if not vehicle:
            return {"score": 0, "label": "Inconnu", "color": "danger", "issues": [], "km_actuel": 0}
        score = 100
        issues = []
        statut = vehicle.get("statut_dernier_diagnostic", "OK")
        if statut == "URGENT":
            score -= 30; issues.append("Codes urgents actifs")
        elif statut == "SURVEILLER":
            score -= 15; issues.append("Codes à surveiller")
        hist = vehicle.get("historique", [])
        last_km = hist[0].get("kilometrage", 0) if hist else 0
        triggered = [a for a in vehicle.get("alertes_km", []) if last_km >= a.get("km_seuil", 0)]
        score -= len(triggered) * 10
        if triggered:
            issues.append(f"{len(triggered)} alerte(s) km déclenchée(s)")
        if hist:
            try:
                days = (datetime.now() - datetime.fromisoformat(hist[0].get("date", ""))).days
                if days > 90:   score -= 15; issues.append(f"Dernier diagnostic : {days} jours")
                elif days > 60: score -= 8;  issues.append(f"Dernier diagnostic : {days} jours")
            except Exception:
                pass
        score = max(0, min(100, score))
        color = "ok" if score >= 80 else ("warn" if score >= 50 else "danger")
        label = "Bon état" if score >= 80 else ("Attention" if score >= 50 else "Critique")
        return {"score": score, "label": label, "color": color, "issues": issues, "km_actuel": last_km}

    def get_maintenance_schedule(self, vin: str) -> list:
        vehicle = self.fleet.get(vin)
        if not vehicle:
            return []
        hist = vehicle.get("historique", [])
        last_km = hist[0].get("kilometrage", 0) if hist else 0
        schedule = []
        for item in MAINTENANCE_INTERVALS:
            interval = item["km"]
            next_km = ((last_km // interval) + 1) * interval if last_km > 0 else interval
            km_remaining = next_km - last_km
            status = "overdue" if km_remaining <= 500 else ("soon" if km_remaining <= 2000 else "ok")
            schedule.append({
                "label": item["label"], "icon": item["icon"],
                "interval_km": interval, "next_km": next_km,
                "km_remaining": km_remaining, "status": status,
            })
        return sorted(schedule, key=lambda x: x["km_remaining"])

    # ------------------------------------------------------------------
    # Patterns flotte
    # ------------------------------------------------------------------

    def get_fleet_patterns(self) -> list:
        """Trouve les codes DTC présents sur 2+ véhicules (5 derniers diagnostics)."""
        code_vehicles: dict = defaultdict(list)
        for vin, vehicle in self.fleet.items():
            marque = vehicle.get("marque", "Inconnu")
            label = f"{marque} (…{vin[-6:]})"
            seen: set = set()
            for entry in vehicle.get("historique", [])[:5]:
                for code in entry.get("dtc_codes", []):
                    if code not in seen:
                        seen.add(code)
                        code_vehicles[code].append(label)
        patterns = [
            {"code": code, "count": len(vehicles), "vehicules": vehicles}
            for code, vehicles in code_vehicles.items()
            if len(vehicles) >= 2
        ]
        return sorted(patterns, key=lambda x: -x["count"])
