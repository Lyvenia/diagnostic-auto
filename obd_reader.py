"""
OBD2 Reader — connexion ELM327 + mode simulation complet.
"""
import json
import os
import random
import threading
import time
from datetime import datetime as _dt

from base_path import data_path

ANOMALY_THRESHOLDS = {
    "temp_warning": 95,
    "temp_critical": 105,
    "voltage_low": 11.5,
    "voltage_high": 15.5,
    "rpm_drop": 600,
}

CONFIG_FILE = data_path("config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"port": "COM3", "baudrate": 9600, "timeout": 10, "simulation_mode": False}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


class OBDReader:
    def __init__(self):
        config = load_config()
        self.port = config.get("port", "COM3")
        self.baudrate = config.get("baudrate", 9600)
        self.timeout = config.get("timeout", 10)
        self.simulation_mode = config.get("simulation_mode", False)
        self.connection = None
        self._rt_cache: dict = {}
        self._rt_lock = threading.Lock()
        self._cache_thread_running = False
        self._sim_vin = None
        self._sim_dtc = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self):
        if self.simulation_mode:
            return {
                "success": True,
                "message": "Mode simulation activé",
                "simulation": True,
            }
        try:
            import obd
            self.connection = obd.OBD(
                portstr=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                fast=False,
            )
            if self.connection.status() == obd.utils.OBDStatus.CAR_CONNECTED:
                self._start_cache_thread()
                return {
                    "success": True,
                    "message": f"Connecté sur {self.port}",
                    "simulation": False,
                }
            self.connection = None
            return {
                "success": False,
                "simulation": False,
                "error": f"Aucun véhicule détecté sur {self.port}. Vérifiez que le contact est allumé et que l'adaptateur ELM327 est bien branché.",
            }
        except Exception as exc:
            return {
                "success": False,
                "simulation": False,
                "error": f"Connexion impossible sur {self.port} : {exc}",
            }

    def disconnect(self):
        self._cache_thread_running = False
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None
        self._rt_cache = {}
        return {"success": True}

    def _start_cache_thread(self):
        """Démarre un thread de fond qui lit les PIDs temps réel en continu."""
        self._cache_thread_running = True
        self._rt_cache = {}
        t = threading.Thread(target=self._cache_loop, daemon=True)
        t.start()

    def _cache_loop(self):
        """Lit les PIDs temps réel en boucle cadencée et met les valeurs en cache (thread-safe)."""
        try:
            import obd as obd_lib
        except ImportError:
            return
        commands = {
            "speed":           obd_lib.commands.SPEED,
            "rpm":             obd_lib.commands.RPM,
            "coolant_temp":    obd_lib.commands.COOLANT_TEMP,
            "battery_voltage": obd_lib.commands.ELM_VOLTAGE,
            "intake_pressure": obd_lib.commands.INTAKE_PRESSURE,
        }
        while self._cache_thread_running and self.connection:
            for key, cmd in commands.items():
                if not self._cache_thread_running:
                    break
                try:
                    response = self.connection.query(cmd)
                    if not response.is_null():
                        val = response.value
                        v = round(float(val.magnitude if hasattr(val, "magnitude") else val), 2)
                        with self._rt_lock:
                            self._rt_cache[key] = v
                    else:
                        with self._rt_lock:
                            self._rt_cache.setdefault(key, None)
                except Exception:
                    with self._rt_lock:
                        self._rt_cache.setdefault(key, None)
                time.sleep(0.05)   # 50ms entre chaque PID → évite de saturer le bus CAN
            time.sleep(0.5)        # 500ms entre chaque cycle complet

    def toggle_simulation(self, enabled: bool):
        self.simulation_mode = enabled
        if enabled and self.connection:
            if getattr(self, '_cache_thread_running', False):
                self._cache_thread_running = False
                import time; time.sleep(0.3)
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None
        # Reset simulation data so a new "vehicle" is generated
        self._sim_vin = None
        self._sim_dtc = None
        config = load_config()
        config["simulation_mode"] = enabled
        save_config(config)
        return {"success": True, "simulation_mode": enabled}

    def get_status(self):
        if self.simulation_mode:
            return {"connected": True, "simulation": True, "port": "SIMULATION"}
        try:
            import obd
            if self.connection and self.connection.status() == obd.utils.OBDStatus.CAR_CONNECTED:
                return {"connected": True, "simulation": False, "port": self.port}
        except Exception:
            pass
        return {"connected": False, "simulation": False, "port": self.port}

    # ------------------------------------------------------------------
    # Data reading
    # ------------------------------------------------------------------

    def read_vin(self):
        if self.simulation_mode:
            return self._simulate_vin()
        if not self.connection:
            return None

        # Stopper le cache pour éviter les collisions sur le bus ELM327
        was_running = self._cache_thread_running
        if was_running:
            self._cache_thread_running = False
            time.sleep(0.3)

        try:
            import obd
            # 2 tentatives pour le VIN (multi-frame, parfois lent)
            for attempt in range(2):
                try:
                    response = self.connection.query(obd.commands.VIN)
                    if not response.is_null():
                        vin = str(response.value).strip()
                        if vin and len(vin) >= 11:
                            return vin
                except Exception as e:
                    self._log_vin_error(f"VIN tentative {attempt+1} échouée : {e}")
                time.sleep(0.3)
        finally:
            if was_running and self.connection:
                self._start_cache_thread()

        return None

    def _log_vin_error(self, msg: str):
        """Log les erreurs VIN dans le fichier de log principal."""
        try:
            from base_path import LOG_PATH
            import time as _t
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{_t.strftime('%H:%M:%S')}] [OBD] {msg}\n")
        except Exception:
            pass

    def read_dtc(self):
        if self.simulation_mode:
            return self._simulate_dtc()
        if not self.connection:
            return []

        # ── CRITIQUE : stopper le thread cache pour libérer le bus ELM327 ──
        # Sans ça, le cache envoie des requêtes PID en parallèle et l'ELM327
        # retourne null sur le mode 03, même si des codes existent.
        was_running = self._cache_thread_running
        if was_running:
            self._cache_thread_running = False
            time.sleep(0.4)   # laisser le bus se stabiliser

        all_codes: set = set()

        try:
            import obd as obd_lib
        except ImportError:
            return []

        try:
            # ── Mode 03 : DTC stockés confirmés (MIL allumé) — 3 tentatives ──
            for attempt in range(3):
                try:
                    r = self.connection.query(obd_lib.commands.GET_DTC)
                    if not r.is_null() and r.value is not None:
                        for item in r.value:
                            try:
                                code = str(item[0]).strip()
                                if code and len(code) >= 4 and code[0] in "PBCU":
                                    all_codes.add(code)
                            except Exception:
                                pass
                        break   # succès — pas besoin de réessayer
                    time.sleep(0.35)
                except Exception:
                    time.sleep(0.35)

            # ── Mode 07 : DTC en attente (1 seul cycle de détection) ──────────
            # Ces codes allument le MIL sans encore être stockés en mode 03.
            try:
                r7 = self.connection.query(obd_lib.commands.GET_CURRENT_DTC)
                if not r7.is_null() and r7.value:
                    for item in r7.value:
                        try:
                            code = str(item[0]).strip()
                            if code and len(code) >= 4 and code[0] in "PBCU":
                                all_codes.add(code)
                        except Exception:
                            pass
            except Exception:
                pass

        finally:
            # Toujours redémarrer le cache, même si une exception survient
            if was_running and self.connection:
                self._start_cache_thread()

        return list(all_codes)

    def clear_dtc(self):
        if self.simulation_mode:
            cleared = list(self._sim_dtc or [])
            self._sim_dtc = []
            return {
                "success": True, "partial": False,
                "message": "Codes DTC effacés (simulation)",
                "cleared": cleared, "remaining": [], "permanent": []
            }
        if not self.connection:
            return {"success": False, "message": "Non connecté à un véhicule",
                    "cleared": [], "remaining": [], "permanent": []}
        try:
            import obd

            # ── 1. Arrêter le cache pour libérer le bus CAN ─────────────
            was_running = self._cache_thread_running
            if was_running:
                self._cache_thread_running = False
                time.sleep(0.5)  # laisser le bus se stabiliser

            try:
                # ── 2. Lire les codes AVANT effacement ──────────────────
                codes_before = []
                try:
                    r = self.connection.query(obd.commands.GET_DTC)
                    if not r.is_null():
                        codes_before = [str(c[0]) for c in r.value if c[0]]
                except Exception:
                    pass

                # ── 3. Pause avant d'envoyer la commande ────────────────
                time.sleep(0.3)

                # ── 4. Commande d'effacement standard (Mode 04) ─────────
                self.connection.query(obd.commands.CLEAR_DTC)

                # ── 5. Attendre que l'ECU traite et réinitialise ─────────
                time.sleep(2.0)

                # ── 6. Première vérification ─────────────────────────────
                codes_after = []
                try:
                    r = self.connection.query(obd.commands.GET_DTC)
                    if not r.is_null():
                        codes_after = [str(c[0]) for c in r.value if c[0]]
                except Exception:
                    pass

                # ── 7. Deuxième vérification 1s plus tard (anti-faux positif) ─
                time.sleep(1.0)
                try:
                    r2 = self.connection.query(obd.commands.GET_DTC)
                    if not r2.is_null():
                        codes_after2 = [str(c[0]) for c in r2.value if c[0]]
                        # On ne garde comme "restants" que ceux présents aux 2 lectures
                        codes_after = [c for c in codes_after if c in codes_after2]
                except Exception:
                    pass

            finally:
                # ── 8. Toujours redémarrer le cache, même en cas d'erreur ─
                if was_running and self.connection:
                    self._start_cache_thread()

            cleared   = [c for c in codes_before if c not in codes_after]
            remaining = list(codes_after)

            if not remaining:
                msg = "Tous les codes effacés avec succès" if cleared else "Aucun code à effacer"
                return {"success": True, "partial": False,
                        "message": msg, "cleared": cleared,
                        "remaining": [], "permanent": []}
            elif cleared:
                return {
                    "success": True, "partial": True,
                    "message": (f"{len(cleared)} code(s) effacé(s) — "
                                f"{len(remaining)} code(s) non effaçable(s) "
                                f"(défaut actif ou code permanent)"),
                    "cleared": cleared, "remaining": remaining, "permanent": remaining
                }
            else:
                return {
                    "success": False, "partial": False,
                    "message": (f"{len(remaining)} code(s) non effaçable(s) — "
                                f"défaut toujours actif ou code OBD permanent (PDTC)"),
                    "cleared": [], "remaining": remaining, "permanent": remaining
                }

        except Exception as exc:
            # Sécurité : redémarrer le cache si une exception non gérée survient
            if self._cache_thread_running is False and self.connection:
                self._start_cache_thread()
            return {"success": False, "message": str(exc),
                    "cleared": [], "remaining": [], "permanent": []}

    def read_realtime(self):
        if self.simulation_mode:
            return self._simulate_realtime()
        if not self.connection:
            return {}
        # Retourne le cache mis à jour par le thread de fond (thread-safe)
        with self._rt_lock:
            if self._rt_cache:
                return dict(self._rt_cache)
        # Première lecture synchrone si le cache est encore vide
        try:
            import obd
        except ImportError:
            return {}
        commands = {
            "speed":           obd.commands.SPEED,
            "rpm":             obd.commands.RPM,
            "coolant_temp":    obd.commands.COOLANT_TEMP,
            "battery_voltage": obd.commands.ELM_VOLTAGE,
            "intake_pressure": obd.commands.INTAKE_PRESSURE,
        }
        data = {}
        for key, cmd in commands.items():
            try:
                response = self.connection.query(cmd)
                if not response.is_null():
                    val = response.value
                    if hasattr(val, "magnitude"):
                        data[key] = round(float(val.magnitude), 2)
                    else:
                        data[key] = round(float(val), 2)
                else:
                    data[key] = None
            except Exception:
                data[key] = None
        return data

    # ------------------------------------------------------------------
    # Simulation helpers
    # ------------------------------------------------------------------

    def reset_simulation(self, forced_vin: str = None):
        """Reset simulation data. If forced_vin is given, use it instead of random."""
        self._sim_vin = forced_vin  # None = pick random, else lock to this VIN
        self._sim_dtc = None

    def _simulate_vin(self):
        if self._sim_vin is None:
            vehicles = [
                "VF1RFD00X55000001",  # Renault Mégane
                "VF7KKFHXBEJ000002",  # Citroën C4
                "WBA3A5G59FNS00003",  # BMW Série 3
                "VF3CARHMF67000004",  # Peugeot 308
                "WVWZZZ3CZJE000005",  # Volkswagen Golf
                "VF1LM1B0H44000006",  # Renault Clio
                "WAUDZZF49KA000007",  # Audi A4
                "ZFANL2B14K3000008",  # Alfa Romeo Giulia
                "VF7UC9HP8EJ000009",  # Citroën Berlingo
                "W0L000051T2000010",  # Opel Astra
                "SAJWA0ES7EMV00011",  # Jaguar XF
                "WDDNG7BB0EA000012",  # Mercedes Classe E
                "SB1KW56F07E000013",  # Toyota Yaris
                "VF3GE9HPC8S000014",  # Peugeot 3008
                "TMBJP9NE0H0000015",  # Škoda Octavia
            ]
            # Exclure les VINs déjà dans la flotte pour éviter les doublons
            used = set(self._get_fleet_vins())
            available = [v for v in vehicles if v not in used]
            pool = available if available else vehicles
            self._sim_vin = random.choice(pool)
        return self._sim_vin

    def _get_fleet_vins(self):
        """Retourne la liste des VINs déjà dans la flotte."""
        try:
            from base_path import data_path
            import json
            fleet_file = data_path("flotte.json")
            if os.path.exists(fleet_file):
                with open(fleet_file, encoding="utf-8") as f:
                    data = json.load(f)
                # flotte.json est un dict {VIN: vehicle_dict, ...}
                return list(data.keys())
        except Exception:
            pass
        return []

    def _simulate_dtc(self):
        if self._sim_dtc is None:
            scenarios = [
                [],                              # Pas de panne (fréquent)
                [],
                [],
                ["P0171"],                       # Mélange pauvre banc 1
                ["P0300"],                       # Ratés d'allumage aléatoires
                ["P0420"],                       # Catalyseur inefficace
                ["P0128"],                       # Thermostat défaillant
                ["P0442"],                       # Fuite EVAP mineure
                ["P0401"],                       # Débit EGR insuffisant
                ["P0171", "P0174"],              # Mélange pauvre banc 1 et 2
                ["P0300", "P0301"],              # Ratés cylindre 1
                ["P0171", "P0300"],              # Multiple
            ]
            self._sim_dtc = random.choice(scenarios)
        return self._sim_dtc

    def _simulate_realtime(self):
        return {
            "speed": random.randint(0, 130),
            "rpm": random.randint(700, 3800),
            "coolant_temp": random.randint(72, 108),
            "battery_voltage": round(random.uniform(12.1, 14.7), 1),
            "intake_pressure": random.randint(28, 101),
        }

    # ------------------------------------------------------------------
    # Test de connexion (diagnostic pas-à-pas)
    # ------------------------------------------------------------------

    def test_connection(self) -> dict:
        """Teste la connexion OBD2 étape par étape et retourne un rapport détaillé."""
        steps = []

        if self.simulation_mode:
            vin = self._sim_vin or self._simulate_vin()
            rt  = self._simulate_realtime()
            return {
                "success": True,
                "mode": "simulation",
                "steps": [
                    {"label": "Mode simulation",      "status": "ok",      "detail": "Aucun adaptateur requis"},
                    {"label": "Génération VIN",        "status": "ok",      "detail": vin},
                    {"label": "Données temps réel",    "status": "ok",      "detail": f"RPM {rt['rpm']} · {rt['speed']} km/h · {rt['battery_voltage']} V"},
                    {"label": "Codes DTC",             "status": "ok",      "detail": "Simulation active"},
                ],
                "vin": vin,
                "realtime": rt,
            }

        # ── Mode réel ──────────────────────────────────────────────────
        try:
            import obd
        except ImportError:
            return {
                "success": False,
                "mode": "reel",
                "steps": [{"label": "Bibliothèque python-obd", "status": "error",
                            "detail": "Non installée — exécutez : pip install obd"}],
            }

        # Étape 1 : ouverture du port
        steps.append({"label": f"Port {self.port}", "status": "pending", "detail": "Tentative…"})
        try:
            conn = obd.OBD(portstr=self.port, baudrate=self.baudrate,
                           timeout=self.timeout, fast=False)
        except Exception as exc:
            steps[-1].update({"status": "error", "detail": str(exc)})
            return {"success": False, "mode": "reel", "steps": steps}

        obd_status = conn.status()

        if obd_status == obd.utils.OBDStatus.NOT_CONNECTED:
            steps[-1].update({"status": "error",
                               "detail": f"Port {self.port} inaccessible ou adaptateur non reconnu"})
            return {"success": False, "mode": "reel", "steps": steps}

        steps[-1].update({"status": "ok", "detail": f"Port {self.port} ouvert"})

        # Étape 2 : détection ELM327
        if obd_status == obd.utils.OBDStatus.ELM_CONNECTED:
            steps.append({"label": "Adaptateur ELM327", "status": "ok",
                           "detail": "ELM327 détecté"})
            steps.append({"label": "Véhicule", "status": "warning",
                           "detail": "Aucun véhicule détecté — contact allumé ?"})
            conn.close()
            return {"success": False, "mode": "reel", "steps": steps}

        steps.append({"label": "Adaptateur ELM327", "status": "ok", "detail": "ELM327 détecté"})
        steps.append({"label": "Véhicule", "status": "ok", "detail": "Véhicule connecté et répond"})

        # Étape 3 : lecture VIN
        vin = None
        try:
            r = conn.query(obd.commands.VIN)
            if not r.is_null():
                vin = str(r.value)
                steps.append({"label": "Lecture VIN", "status": "ok", "detail": vin})
            else:
                steps.append({"label": "Lecture VIN", "status": "warning",
                               "detail": "VIN non disponible sur ce véhicule"})
        except Exception as exc:
            steps.append({"label": "Lecture VIN", "status": "warning", "detail": str(exc)})

        # Étape 4 : données temps réel
        rt = {}
        test_cmds = {
            "RPM":      obd.commands.RPM,
            "Vitesse":  obd.commands.SPEED,
            "Batterie": obd.commands.ELM_VOLTAGE,
            "Température": obd.commands.COOLANT_TEMP,
        }
        rt_parts = []
        for name, cmd in test_cmds.items():
            try:
                r = conn.query(cmd)
                if not r.is_null():
                    val = r.value
                    if hasattr(val, "magnitude"):
                        val = round(float(val.magnitude), 1)
                    rt[name] = val
                    rt_parts.append(f"{name} : {val}")
            except Exception:
                pass

        if rt_parts:
            steps.append({"label": "Données temps réel", "status": "ok",
                           "detail": " · ".join(rt_parts)})
        else:
            steps.append({"label": "Données temps réel", "status": "warning",
                           "detail": "Aucune donnée lue (véhicule en veille ?)"})

        conn.close()
        return {
            "success": True,
            "mode": "reel",
            "steps": steps,
            "vin":      vin,
            "realtime": rt,
        }

    # ------------------------------------------------------------------
    # Freeze frame (données au moment du déclenchement du DTC)
    # ------------------------------------------------------------------

    def read_freeze_frame(self) -> dict:
        """Lit les données freeze frame (mode 02). En simulation, génère des données synthétiques."""
        if self.simulation_mode:
            dtc = self._sim_dtc or []
            if not dtc:
                return {}
            return self._simulate_freeze_frame()
        # Mode réel : python-obd ne supporte pas directement le mode 02
        return {}

    def _simulate_freeze_frame(self) -> dict:
        """Données figées au moment où le code DTC a été mémorisé."""
        return {
            "speed_ff":           random.randint(0, 120),
            "rpm_ff":             random.randint(700, 4000),
            "coolant_temp_ff":    random.randint(60, 115),
            "engine_load_ff":     round(random.uniform(20.0, 85.0), 1),
            "fuel_trim_short_ff": round(random.uniform(-15.0, 15.0), 1),
            "fuel_trim_long_ff":  round(random.uniform(-10.0, 10.0), 1),
            "throttle_ff":        round(random.uniform(10.0, 80.0), 1),
        }

    # ------------------------------------------------------------------
    # Surveillance continue
    # ------------------------------------------------------------------

    def start_monitoring(self):
        """Lance la surveillance continue en arrière-plan."""
        if getattr(self, '_monitoring', False):
            return False
        self._monitoring = True
        self._session = {
            "start_time": _dt.now().isoformat(),
            "readings": [],
            "anomalies": [],
            "dtc_set": set(),
            "last_anomaly_type": {},
        }
        self._pending_anomalies = []
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()
        return True

    def stop_monitoring(self):
        """Arrête la surveillance et retourne le résumé de session."""
        self._monitoring = False
        session = self._session if hasattr(self, '_session') else None
        if not session:
            return None
        session = dict(session)
        session["end_time"] = _dt.now().isoformat()
        readings = session.get("readings", [])
        session["readings_count"] = len(readings)
        session["stats"] = self._compute_stats(readings)
        session["dtc_codes"] = list(session.pop("dtc_set", set()))
        session.pop("last_anomaly_type", None)
        duration = 0
        try:
            start = _dt.fromisoformat(session["start_time"])
            end = _dt.fromisoformat(session["end_time"])
            duration = int((end - start).total_seconds())
        except Exception:
            pass
        session["duration_seconds"] = duration
        self._session = None
        return session

    def get_session_status(self):
        """Retourne l'état actuel de la session de monitoring."""
        if not getattr(self, '_monitoring', False) or not getattr(self, '_session', None):
            return {"active": False}
        s = self._session
        readings = s.get("readings", [])
        last = readings[-1] if readings else {}
        # Consume pending anomalies
        new_anomalies = list(getattr(self, '_pending_anomalies', []))
        self._pending_anomalies = []
        return {
            "active": True,
            "start_time": s["start_time"],
            "readings_count": len(readings),
            "anomalies_count": len(s.get("anomalies", [])),
            "new_anomalies": new_anomalies,
            "anomalies": s.get("anomalies", [])[-10:],
            "current": last,
            "dtc_count": len(s.get("dtc_set", set())),
            "stats": self._compute_stats(readings),
        }

    def _monitor_loop(self):
        prev_rpm = None
        _dtc_read_counter = 0  # Lire les DTC toutes les 15 itérations (15s) seulement
        while getattr(self, '_monitoring', False):
            try:
                data = self.read_realtime()
                _dtc_read_counter += 1
                # Les DTC sont lents à lire (~2s) → on ne lit que toutes les 15s
                if _dtc_read_counter >= 15:
                    dtcs = self.read_dtc()
                    _dtc_read_counter = 0
                else:
                    dtcs = list(self._session.get("dtc_set", set()))
                reading = {
                    "timestamp": _dt.now().isoformat(),
                    "rpm": data.get("rpm") or 0,
                    "temp": data.get("coolant_temp") or 0,
                    "speed": data.get("speed") or 0,
                    "voltage": data.get("battery_voltage") or 0,
                }
                self._session["readings"].append(reading)

                # Detect new DTC codes
                for code in dtcs:
                    if code not in self._session["dtc_set"]:
                        self._session["dtc_set"].add(code)
                        self._add_anomaly({"type": "new_dtc", "code": code,
                                           "timestamp": reading["timestamp"],
                                           "message": f"Nouveau code DTC : {code}"})

                temp = reading["temp"]
                volt = reading["voltage"]
                rpm = reading["rpm"]

                if temp and temp >= ANOMALY_THRESHOLDS["temp_critical"]:
                    self._add_anomaly({"type": "temp_critical", "value": temp,
                                       "timestamp": reading["timestamp"],
                                       "message": f"Température critique : {temp}°C"})
                elif temp and temp >= ANOMALY_THRESHOLDS["temp_warning"]:
                    self._add_anomaly({"type": "temp_warning", "value": temp,
                                       "timestamp": reading["timestamp"],
                                       "message": f"Température élevée : {temp}°C"})

                if volt and volt <= ANOMALY_THRESHOLDS["voltage_low"]:
                    self._add_anomaly({"type": "voltage_low", "value": volt,
                                       "timestamp": reading["timestamp"],
                                       "message": f"Tension batterie faible : {volt}V"})
                elif volt and volt >= ANOMALY_THRESHOLDS["voltage_high"]:
                    self._add_anomaly({"type": "voltage_high", "value": volt,
                                       "timestamp": reading["timestamp"],
                                       "message": f"Tension batterie élevée : {volt}V"})

                if prev_rpm and prev_rpm > 1000 and rpm and rpm < prev_rpm - ANOMALY_THRESHOLDS["rpm_drop"]:
                    self._add_anomaly({"type": "rpm_drop", "value": rpm,
                                       "prev": prev_rpm,
                                       "timestamp": reading["timestamp"],
                                       "message": f"Chute RPM soudaine : {prev_rpm} → {rpm} tr/min"})

                if rpm and rpm > 0:
                    prev_rpm = rpm

            except Exception:
                pass
            time.sleep(1)

    def _add_anomaly(self, anomaly):
        """Ajoute une anomalie en évitant les doublons dans les 30 secondes."""
        atype = anomaly["type"]
        last = self._session["last_anomaly_type"].get(atype)
        if last:
            try:
                diff = (_dt.fromisoformat(anomaly["timestamp"]) - _dt.fromisoformat(last)).total_seconds()
                if diff < 30:
                    return
            except Exception:
                pass
        self._session["last_anomaly_type"][atype] = anomaly["timestamp"]
        self._session["anomalies"].append(anomaly)
        self._pending_anomalies.append(anomaly)

    def _compute_stats(self, readings):
        if not readings:
            return {}
        stats = {}
        for key in ["rpm", "temp", "speed", "voltage"]:
            vals = [r[key] for r in readings if r.get(key, 0) and r[key] > 0]
            if vals:
                stats[key] = {"min": min(vals), "max": max(vals), "avg": round(sum(vals) / len(vals), 1)}
            else:
                stats[key] = {"min": 0, "max": 0, "avg": 0}
        return stats
