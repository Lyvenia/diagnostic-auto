import time
import threading
from datetime import datetime as _dt

ANOMALY_THRESHOLDS = {
    "temp_warning": 95,
    "temp_critical": 105,
    "voltage_low": 11.5,
    "voltage_high": 15.5,
    "rpm_drop": 600,
}


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
                dtc_result = self.read_dtc()
                dtcs = dtc_result.get("codes", []) if isinstance(dtc_result, dict) else list(dtc_result)
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
