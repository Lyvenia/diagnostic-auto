"""
Résolution des chemins compatibles PyInstaller + dev.

Quand l'app est packagée en .exe, sys.frozen est True et les fichiers
de données (config.json, flotte.json, backups/) doivent être à côté
du .exe, pas dans le répertoire temporaire d'extraction PyInstaller.
"""
import os
import sys


def get_base_dir() -> str:
    """Retourne le répertoire de base : dossier du .exe ou du script."""
    if getattr(sys, "frozen", False):
        # Exécution via PyInstaller : utiliser le dossier du .exe
        return os.path.dirname(sys.executable)
    # Exécution normale : dossier du fichier source
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
LOG_PATH = os.path.join(BASE_DIR, "DiagnosticAuto_error.log")


def data_path(filename: str) -> str:
    """Chemin absolu vers un fichier de données (config, flotte, backups…)."""
    return os.path.join(BASE_DIR, filename)
