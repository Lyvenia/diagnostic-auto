"""
Package hardware — OBDReader reconstituée depuis les sous-modules.
Chaque sous-module contient des fonctions standalone avec self en premier paramètre.
"""
import threading
from core.config import load_config
from core.variant import CLIENT_BUILD, DEMO_BUILD, REAL_CLIENT

import hardware.connection as _conn
import hardware.dtc as _dtc
import hardware.realtime as _rt
import hardware.monitoring as _mon
import hardware.simulation as _sim
import hardware.odometer as _odo

ANOMALY_THRESHOLDS = {
    "temp_warning": 95,
    "temp_critical": 105,
    "voltage_low": 11.5,
    "voltage_high": 15.5,
    "rpm_drop": 600,
}

class OBDReader:
    def __init__(self):
        config = load_config()
        self.port = config.get("port", "COM3")
        self.baudrate = config.get("baudrate", 9600)
        self.timeout = config.get("timeout", 10)
        # Client réel : jamais de simulation au démarrage (connect() tente toujours
        # l'adaptateur, et affiche un message si absent — pas de fausses données).
        # Dev / démo : simulation activée par défaut (toggle dispo en dev, repli en démo).
        if REAL_CLIENT:
            self.simulation_mode = False
        else:
            self.simulation_mode = config.get("simulation_mode", True)
        self.connection = None
        self._rt_cache: dict = {}
        self._rt_lock = threading.Lock()
        self._cache_thread_running = False
        self._sim_vin = None
        self._sim_dtc = None

    # ── Connexion ──────────────────────────────────────────
    connect              = _conn.connect
    disconnect           = _conn.disconnect
    get_status           = _conn.get_status
    toggle_simulation    = _conn.toggle_simulation
    test_connection      = _conn.test_connection
    _start_cache_thread  = _conn._start_cache_thread
    _cache_loop          = _conn._cache_loop
    _log_vin_error       = _conn._log_vin_error

    # ── DTC ────────────────────────────────────────────────
    read_dtc  = _dtc.read_dtc
    clear_dtc = _dtc.clear_dtc

    # ── Temps réel ─────────────────────────────────────────
    read_vin           = _rt.read_vin
    read_realtime      = _rt.read_realtime
    read_freeze_frame  = _rt.read_freeze_frame
    _simulate_freeze_frame = _rt._simulate_freeze_frame

    # ── Kilométrage ────────────────────────────────────────
    read_odometer      = _odo.read_odometer

    # ── Monitoring ─────────────────────────────────────────
    start_monitoring    = _mon.start_monitoring
    stop_monitoring     = _mon.stop_monitoring
    get_session_status  = _mon.get_session_status
    _monitor_loop       = _mon._monitor_loop
    _add_anomaly        = _mon._add_anomaly
    _compute_stats      = _mon._compute_stats

    # ── Simulation ─────────────────────────────────────────
    reset_simulation   = _sim.reset_simulation
    _simulate_vin      = _sim._simulate_vin
    _simulate_dtc      = _sim._simulate_dtc
    _simulate_realtime = _sim._simulate_realtime
    _get_fleet_vins    = _sim._get_fleet_vins
