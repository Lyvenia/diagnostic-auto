"""Configuration ELM327 — chargement et sauvegarde."""
import json
import os
import sys
from core.paths import data_path, get_base_dir

CONFIG_FILE = data_path("config.json")

_DEFAULT = {"port": "COM3", "baudrate": 9600, "timeout": 10, "simulation_mode": True}


def _migrate_legacy():
    """
    Si on est en mode exe et qu'un config.json existe à côté du .exe (ancienne
    location), on le copie vers %APPDATA%\\RODIA\\ puis on le supprime pour éviter
    qu'il soit relu la prochaine fois.
    """
    if not getattr(sys, "frozen", False):
        return
    legacy = os.path.join(get_base_dir(), "config.json")
    if os.path.exists(legacy) and not os.path.exists(CONFIG_FILE):
        try:
            with open(legacy, encoding="utf-8") as f:
                data = json.load(f)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.remove(legacy)
        except Exception:
            pass


# Migration automatique au premier import
_migrate_legacy()


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            # Migration : les anciens builds forçaient simulation_mode=False même sans
            # adaptateur OBD. Si la config n'a jamais enregistré une connexion OBD
            # réelle, on réinitialise à True pour éviter un crash au démarrage.
            if not cfg.get("simulation_mode", True) and not cfg.get("obd_ever_connected", False):
                cfg["simulation_mode"] = True
                try:
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            return cfg
        except Exception:
            pass
    return dict(_DEFAULT)


def save_config(config: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
