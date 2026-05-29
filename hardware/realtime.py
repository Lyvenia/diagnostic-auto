import time

# Caractères autorisés par la norme VIN (ISO 3779) — I, O, Q exclus.
_VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def is_valid_vin(vin: str) -> bool:
    """Vérifie qu'un VIN est correctement formé : exactement 17 caractères
    de l'alphabet VIN (ISO 3779).

    NB : on ne valide PAS le checksum ISO 3779. La plupart des constructeurs
    européens (Renault, PSA…) ne le respectent pas — un rejet sur checksum
    ferait beaucoup de faux négatifs.
    """
    return len(vin) == 17 and all(c in _VIN_CHARS for c in vin)


def clean_vin_value(raw) -> str:
    """Normalise une valeur VIN renvoyée par python-obd en VIN ASCII propre.

    python-obd renvoie parfois le VIN sous forme de `bytes`/`bytearray`. Faire
    `str()` dessus produit la repr Python (« bytearray(b'VF1...') »), ce qui
    casse le décodage ET l'UI (les ' ( ) cassent les onclick inline et les URLs
    API). On décode donc proprement, puis on ne garde que les caractères VIN
    valides.
    """
    if isinstance(raw, (bytes, bytearray)):
        s = raw.decode("ascii", errors="ignore")
    else:
        s = str(raw)
    return "".join(c for c in s.upper() if c in _VIN_CHARS)


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

    # Tentatives multiples avec délais croissants : le VIN OBD est en multi-frame
    # ISO-TP, lent à l'init, et certains ELM327 droppent des octets. On exige
    # une lecture STRICTEMENT valide (17 caractères + alphabet ISO 3779). Si
    # rien de valide après N tentatives, on rend None → le frontend bascule
    # sur la saisie manuelle (couche 2 du filet de sécurité).
    best_invalid = None  # garde le meilleur candidat invalide pour le log
    try:
        import obd
        delays = [0.3, 0.6, 1.0, 1.5]
        for attempt, delay in enumerate(delays):
            try:
                response = self.connection.query(obd.commands.VIN)
                if not response.is_null():
                    vin = clean_vin_value(response.value)
                    if is_valid_vin(vin):
                        return vin
                    if vin and (best_invalid is None or len(vin) > len(best_invalid)):
                        best_invalid = vin
                        self._log_vin_error(
                            f"VIN tentative {attempt+1} invalide "
                            f"(longueur={len(vin)}) : {vin!r}"
                        )
            except Exception as e:
                self._log_vin_error(f"VIN tentative {attempt+1} échouée : {e}")
            time.sleep(delay)
    finally:
        if was_running and self.connection:
            self._start_cache_thread()

    if best_invalid:
        self._log_vin_error(
            f"VIN abandonné après {len(delays)} tentatives — "
            f"meilleur candidat invalide : {best_invalid!r}"
        )
    return None


def _enrich_realtime(data: dict) -> dict:
    """Ajoute le flag engine_running basé sur le RPM.

    engine_running = True  → moteur tournant (RPM > 400)
    engine_running = False → contact mis mais moteur éteint (0 < RPM ≤ 400)
    engine_running = None  → RPM non lu (impossible de déterminer)
    """
    rpm = data.get("rpm")
    if rpm is not None:
        data["engine_running"] = (rpm > 400)
    else:
        data["engine_running"] = None
    return data


def read_realtime(self):
    if self.simulation_mode:
        return _enrich_realtime(self._simulate_realtime())
    if not self.connection:
        return {}
    # Retourne le cache mis à jour par le thread de fond (thread-safe)
    with self._rt_lock:
        if self._rt_cache:
            return _enrich_realtime(dict(self._rt_cache))
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
    return _enrich_realtime(data)


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
    import random
    return {
        "speed_ff":           random.randint(0, 120),
        "rpm_ff":             random.randint(700, 4000),
        "coolant_temp_ff":    random.randint(60, 115),
        "engine_load_ff":     round(random.uniform(20.0, 85.0), 1),
        "fuel_trim_short_ff": round(random.uniform(-15.0, 15.0), 1),
        "fuel_trim_long_ff":  round(random.uniform(-10.0, 10.0), 1),
        "throttle_ff":        round(random.uniform(10.0, 80.0), 1),
    }
