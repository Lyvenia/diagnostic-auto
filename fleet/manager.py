"""
Gestionnaire de flotte — stockage JSON local (flotte.json).
"""
import json
import os
import threading
from collections import defaultdict
from datetime import datetime

from core.paths import data_path

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
    _DEBOUNCE_DELAY = 1.5  # secondes avant l'écriture effective

    def __init__(self):
        self._lock         = threading.Lock()
        self._save_timer: threading.Timer | None = None
        self.fleet: dict   = self._load()

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
        """Planifie une écriture disque avec débounce (1,5 s).
        Doit être appelé DANS un bloc with self._lock."""
        if self._save_timer is not None:
            self._save_timer.cancel()
        # Capturer un snapshot pour éviter les mutations pendant l'écriture
        snapshot = json.dumps(self.fleet, ensure_ascii=False, indent=2)
        def _write():
            try:
                with open(FLEET_FILE, "w", encoding="utf-8") as f:
                    f.write(snapshot)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._save_timer = None
        self._save_timer = threading.Timer(self._DEBOUNCE_DELAY, _write)
        self._save_timer.daemon = True
        self._save_timer.start()

    def flush(self):
        """Force l'écriture immédiate (à appeler à l'arrêt de l'app)."""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            snapshot = json.dumps(self.fleet, ensure_ascii=False, indent=2)
        with open(FLEET_FILE, "w", encoding="utf-8") as f:
            f.write(snapshot)

    # ------------------------------------------------------------------
    # Vehicle CRUD
    # ------------------------------------------------------------------

    def get_all_vehicles(self) -> list:
        with self._lock:
            return list(self.fleet.values())

    def get_vehicle(self, vin: str) -> dict | None:
        with self._lock:
            return self.fleet.get(vin)

    def delete_vehicle(self, vin: str) -> bool:
        with self._lock:
            if vin in self.fleet:
                del self.fleet[vin]
                self._save()
                return True
            return False

    def create_or_get_vehicle(self, vin: str, vin_info: dict, simulated: bool = False) -> tuple[dict, bool]:
        """Return (vehicle, is_new). Creates vehicle if not already in fleet."""
        with self._lock:
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
        with self._lock:
            if vin in self.fleet:
                self.fleet[vin].update(info)
                self._save()

    def update_vehicle_fleet_info(self, vin: str, code: str, surnom: str, groupe: str) -> dict | None:
        """Update code, surnom and groupe for a vehicle. Returns updated vehicle."""
        with self._lock:
            if vin not in self.fleet:
                return None
            self.fleet[vin]["code"] = code
            self.fleet[vin]["surnom"] = surnom
            self.fleet[vin]["groupe"] = groupe
            self._save()
            return self.fleet[vin]

    def get_groups(self) -> list:
        """Returns list of unique non-empty group names from all vehicles."""
        with self._lock:
            groups = {v.get("groupe", "") for v in self.fleet.values() if v.get("groupe")}
            return sorted(groups)

    def get_vehicles_by_group(self) -> dict:
        """Returns dict {groupe: [vehicles]}. Vehicles without groupe go under '' key."""
        with self._lock:
            result = {}
            for vehicle in self.fleet.values():
                g = vehicle.get("groupe", "")
                result.setdefault(g, []).append(vehicle)
            return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def save_diagnostic(self, vin: str, diagnostic: dict) -> dict | None:
        with self._lock:
            if vin not in self.fleet:
                return None

            now = datetime.now()
            analyse_ia = diagnostic.get("analyse_ia") or {}
            entry = {
                "id": now.strftime("%Y%m%d_%H%M%S"),
                "date": now.isoformat(),
                "date_affichage": now.strftime("%d/%m/%Y à %H:%M"),
                "kilometrage": diagnostic.get("kilometrage", 0),
                "dtc_codes": diagnostic.get("dtc_codes", []),
                "donnees_temps_reel": diagnostic.get("donnees_temps_reel", {}),
                "analyse_ia": analyse_ia,
                "statut": diagnostic.get("statut", "OK"),
                "technicien": diagnostic.get("technicien", ""),
                "session_ralenti": diagnostic.get("session_ralenti"),
                "session_roulant": diagnostic.get("session_roulant"),
                # Type de diagnostic : "panne" (curatif) ou "controle" (bilan préventif)
                "type": diagnostic.get("type", "panne"),
                # Suivi de panne
                "statut_suivi": "ouvert",
                # Données enrichies depuis l'analyse IA
                "pieces_necessaires": analyse_ia.get("pieces_necessaires", []),
                "plan_action":        analyse_ia.get("plan_action", []),
            }

            # ── Détection régression kilométrique (compteur trafiqué) ──
            hist    = self.fleet[vin].get("historique", [])
            new_km  = entry["kilometrage"]
            prev_km = hist[0].get("kilometrage", 0) if hist else 0
            if new_km > 0 and prev_km > 0 and new_km < prev_km:
                entry["km_alerte_fraude"] = True
                entry["km_prev"]          = prev_km

            # Most recent first
            self.fleet[vin]["historique"].insert(0, entry)
            self.fleet[vin]["statut_dernier_diagnostic"] = entry["statut"]
            self._save()
            return entry

    def get_history(self, vin: str) -> list:
        with self._lock:
            vehicle = self.fleet.get(vin)
            return list(vehicle.get("historique", [])) if vehicle else []

    def update_diagnostic_suivi(self, vin: str, diag_id: str, statut_suivi: str, notes_reparation: str = None) -> bool:
        """Met à jour le statut de suivi d'un diagnostic (ouvert/en_cours/resolu) et les notes."""
        with self._lock:
            vehicle = self.fleet.get(vin)
            if not vehicle:
                return False
            for entry in vehicle.get("historique", []):
                if entry.get("id") == diag_id:
                    entry["statut_suivi"] = statut_suivi
                    if notes_reparation is not None:
                        entry["notes_reparation"] = notes_reparation
                    self._save()
                    return True
            return False

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def update_notes(self, vin: str, notes: str) -> bool:
        with self._lock:
            if vin in self.fleet:
                self.fleet[vin]["notes"] = notes
                self._save()
                return True
            return False

    # ------------------------------------------------------------------
    # Réparations
    # ------------------------------------------------------------------

    def add_repair(self, vin: str, repair: dict) -> dict | None:
        with self._lock:
            if vin not in self.fleet:
                return None
            self.fleet[vin].setdefault("reparations", [])
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
        with self._lock:
            vehicle = self.fleet.get(vin)
            return list(vehicle.get("reparations", [])) if vehicle else []

    # ------------------------------------------------------------------
    # Alertes kilométrage
    # ------------------------------------------------------------------

    def get_km_alerts(self, vin: str) -> list:
        with self._lock:
            vehicle = self.fleet.get(vin)
            return list(vehicle.get("alertes_km", [])) if vehicle else []

    def add_km_alert(self, vin: str, alert: dict) -> dict | None:
        with self._lock:
            if vin not in self.fleet:
                return None
            self.fleet[vin].setdefault("alertes_km", [])
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
        with self._lock:
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
        with self._lock:
            result = []
            for vin, vehicle in self.fleet.items():
                alerts = vehicle.get("alertes_km", [])
                if not alerts:
                    continue
                last_km = self._last_km(vehicle)
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

    @staticmethod
    def _last_km(vehicle: dict) -> int:
        """Retourne le kilométrage actuel : km_manuel prioritaire, sinon dernier historique."""
        if vehicle.get("km_manuel") is not None:
            return int(vehicle["km_manuel"])
        hist = vehicle.get("historique", [])
        return hist[0].get("kilometrage", 0) if hist else 0

    def _compute_health(self, vehicle: dict) -> dict:
        """Calcule le score de santé d'un véhicule (sans verrou — appelé depuis méthodes verrouillées)."""
        score = 100
        issues = []
        statut = vehicle.get("statut_dernier_diagnostic", "OK")
        if statut == "URGENT":
            score -= 30; issues.append("Codes urgents actifs")
        elif statut == "SURVEILLER":
            score -= 15; issues.append("Codes à surveiller")
        last_km = self._last_km(vehicle)
        triggered = [a for a in vehicle.get("alertes_km", []) if last_km >= a.get("km_seuil", 0)]
        score -= len(triggered) * 10
        if triggered:
            issues.append(f"{len(triggered)} alerte(s) km déclenchée(s)")
        hist = vehicle.get("historique", [])
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

    def get_health_score(self, vin: str) -> dict:
        with self._lock:
            vehicle = self.fleet.get(vin)
            if not vehicle:
                return {"score": 0, "label": "Inconnu", "color": "danger", "issues": [], "km_actuel": 0}
            return self._compute_health(vehicle)

    def get_all_health_scores(self) -> dict:
        """Calcule les scores de santé de toute la flotte en une seule passe (batch)."""
        with self._lock:
            return {vin: self._compute_health(v) for vin, v in self.fleet.items()}

    def get_maintenance_schedule(self, vin: str) -> list:
        with self._lock:
            vehicle = self.fleet.get(vin)
            if not vehicle:
                return []
            last_km = self._last_km(vehicle)
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
        with self._lock:
            snapshot = {vin: v.get("historique", [])[:5] for vin, v in self.fleet.items()
                        if v.get("historique")}
            marques  = {vin: v.get("marque", "Inconnu") for vin, v in self.fleet.items()}
        code_vehicles: dict = defaultdict(list)
        for vin, hist in snapshot.items():
            label = f"{marques[vin]} (…{vin[-6:]})"
            seen: set = set()
            for entry in hist:
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
