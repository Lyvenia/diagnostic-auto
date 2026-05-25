import time
import threading
from core.config import load_config, save_config
from core.paths import data_path, LOG_PATH
from core.variant import CLIENT_BUILD, DEMO_BUILD, REAL_CLIENT


def connect(self):
    """Établit la connexion OBD2. Trois comportements selon la variante :

      - DEV (hors build client) : le flag simulation_mode pilote (toggle dispo).
      - DÉMO (DEMO_BUILD)        : tente l'adaptateur réel, repli simulation si absent.
      - CLIENT RÉEL (REAL_CLIENT): tente l'adaptateur réel, AUCUNE simulation —
                                   message clair « branchez l'adaptateur » si absent.
    """
    # Dev : simulation explicite demandée → on simule directement (sans toucher au port).
    if self.simulation_mode and not CLIENT_BUILD and not DEMO_BUILD:
        return {
            "success": True,
            "message": "Mode simulation activé",
            "simulation": True,
        }

    try:
        import obd
    except ImportError:
        if REAL_CLIENT:
            self.simulation_mode = False
            return {
                "success": False,
                "simulation": False,
                "error": "Module OBD indisponible sur cette machine. Contactez le support.",
            }
        # Dev / démo → repli simulation
        self.simulation_mode = True
        return {
            "success": True,
            "message": "Bibliothèque OBD non disponible — mode simulation activé",
            "simulation": True,
        }

    try:
        self.connection = obd.OBD(
            portstr=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout,
            fast=False,
        )
        if self.connection.status() == obd.utils.OBDStatus.CAR_CONNECTED:
            # Connexion réelle établie → on bascule tout l'app en mode réel
            self.simulation_mode = False
            self._start_cache_thread()
            # Mémorise qu'une connexion OBD réelle a fonctionné (évite la migration auto)
            try:
                cfg = load_config()
                cfg["obd_ever_connected"] = True
                save_config(cfg)
            except Exception:
                pass
            return {
                "success": True,
                "message": f"Connecté sur {self.port}",
                "simulation": False,
            }
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
        self.connection = None
    except Exception:
        self.connection = None

    # Aucun adaptateur détecté
    if REAL_CLIENT:
        # Client réel : pas de fausses données → on guide l'utilisateur
        self.simulation_mode = False
        return {
            "success": False,
            "simulation": False,
            "no_adapter": True,
            "error": "Aucun adaptateur OBD2 détecté. Branchez votre boîtier ELM327 "
                     "sur la prise OBD du véhicule, mettez le contact, puis réessayez.",
        }
    # Dev / démo → repli simulation automatique
    self.simulation_mode = True
    return {
        "success": True,
        "message": "Aucun adaptateur OBD2 détecté — mode simulation activé",
        "simulation": True,
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
    """Lit les PIDs temps réel en boucle cadencée et met les valeurs en cache (thread-safe).

    Reconnexion automatique : si >12 cycles consécutifs sans aucune réponse valide,
    tente une reconnexion silencieuse (max 3 tentatives, backoff 10s).
    """
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

    null_cycles = 0          # cycles consécutifs sans réponse valide
    reconnect_attempts = 0   # nombre de tentatives de reconnexion depuis le dernier succès

    while self._cache_thread_running and self.connection:
        cycle_got_data = False
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
                    cycle_got_data = True
                else:
                    with self._rt_lock:
                        self._rt_cache.setdefault(key, None)
            except Exception:
                with self._rt_lock:
                    self._rt_cache.setdefault(key, None)
            time.sleep(0.05)   # 50ms entre chaque PID → évite de saturer le bus CAN

        if cycle_got_data:
            null_cycles = 0
            reconnect_attempts = 0
        else:
            null_cycles += 1

        # ── Reconnexion automatique ──────────────────────────────────────
        # Après 12 cycles sans données (~18s) et max 3 tentatives
        if null_cycles >= 12 and reconnect_attempts < 3:
            null_cycles = 0
            reconnect_attempts += 1
            try:
                self._cache_thread_running = False
                if self.connection:
                    try:
                        self.connection.close()
                    except Exception:
                        pass
                    self.connection = None

                # Attente avant de retenter (backoff : 5s, 10s, 20s)
                time.sleep(5 * reconnect_attempts)

                result = self.connect()
                if result.get("success"):
                    # connect() démarre déjà le cache thread → on sort proprement
                    return
                else:
                    # Reconnexion échouée → pause et on réessaiera au prochain seuil
                    self.connection = None
            except Exception:
                pass

        time.sleep(0.5)        # 500ms entre chaque cycle complet


def toggle_simulation(self, enabled: bool):
    if CLIENT_BUILD:
        # Build client : simulation définitivement verrouillée
        return {"success": False, "simulation_mode": False, "error": "Indisponible sur cette version"}
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
        return {"connected": True, "simulation": True, "port": "SIMULATION", "client_build": CLIENT_BUILD}
    try:
        import obd
        if self.connection and self.connection.status() == obd.utils.OBDStatus.CAR_CONNECTED:
            return {"connected": True, "simulation": False, "port": self.port, "client_build": CLIENT_BUILD}
    except Exception:
        pass
    return {"connected": False, "simulation": False, "port": self.port, "client_build": CLIENT_BUILD}


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


def _log_vin_error(self, msg: str):
    """Log les erreurs VIN dans le fichier de log principal."""
    try:
        import time as _t
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [OBD] {msg}\n")
    except Exception:
        pass
