import time


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
