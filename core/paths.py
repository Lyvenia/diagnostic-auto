"""
Résolution des chemins compatibles PyInstaller + dev.

Les fichiers de données utilisateur (config.json, flotte.json, backups, exports…)
sont stockés dans %APPDATA%\RODIA\ sur Windows, ou à côté du script en dev.
Cela garantit qu'ils survivent aux mises à jour et aux rebuilds PyInstaller.
"""
import os
import sys


def get_data_dir() -> str:
    """
    Retourne le dossier de données utilisateur :
    - En production (exe) : %APPDATA%\\RODIA\\
    - En développement   : dossier du script (core/)
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        data_dir = os.path.join(appdata, "RODIA")
    else:
        # Dev : utiliser le répertoire racine du projet (parent de core/)
        data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_base_dir() -> str:
    """Retourne le répertoire de base (exe ou script) — pour les ressources statiques."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR  = get_base_dir()
DATA_DIR  = get_data_dir()
LOG_PATH  = os.path.join(DATA_DIR, "DiagnosticAuto_error.log")


def data_path(filename: str) -> str:
    """Chemin absolu vers un fichier de données utilisateur (config, flotte, backups…)."""
    return os.path.join(DATA_DIR, filename)
