"""Auto-updater RODIA — vérifie, télécharge et applique les mises à jour.

Fonctionnement :
  1. check_update()      → compare la version locale avec api.lyvenia.fr/version
  2. download_and_apply() → télécharge le nouvel exe, génère un .bat de remplacement,
                            lance le .bat et quitte RODIA (Windows remplace ensuite l'exe)
"""
import os
import sys
import subprocess

import requests

from core.version import RODIA_VERSION

LYVENIA_API = "https://api.lyvenia.fr"


def _parse_version(v: str) -> tuple[int, ...]:
    """Convertit '1.2.3' en (1, 2, 3) pour comparaison."""
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0,)


def check_update() -> dict | None:
    """Retourne les infos de mise à jour si une version plus récente existe, sinon None."""
    try:
        r = requests.get(f"{LYVENIA_API}/version", timeout=5)
        if not r.ok:
            return None
        data = r.json()
        remote_v = data.get("version", "0")
        if _parse_version(remote_v) > _parse_version(RODIA_VERSION):
            return data
    except Exception:
        pass
    return None


def download_and_apply(download_url: str, on_progress=None) -> None:
    """Télécharge le nouvel exe et déclenche le remplacement via un script batch.

    on_progress(pct: int) est appelé pendant le téléchargement (0-100).
    La fonction quitte le processus RODIA une fois le script batch lancé.
    Ne fait rien en mode développement (non-frozen).
    """
    if not getattr(sys, "frozen", False):
        # Mode dev — simuler sans quitter
        if on_progress:
            on_progress(100)
        return

    current_exe = sys.executable                        # ex: C:\...\RODIA.exe
    new_exe     = current_exe.replace(".exe", "_update.exe")
    bat_path    = current_exe.replace(".exe", "_update.bat")

    # ── Téléchargement ──────────────────────────────────────────────────────
    r = requests.get(download_url, stream=True, timeout=300)
    r.raise_for_status()

    total      = int(r.headers.get("content-length", 0))
    downloaded = 0

    with open(new_exe, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if on_progress and total:
                on_progress(int(downloaded / total * 100))

    if on_progress:
        on_progress(100)

    # ── Script de remplacement ───────────────────────────────────────────────
    # Le .bat attend que RODIA soit fermé, remplace l'exe, puis relance.
    bat = (
        "@echo off\n"
        "timeout /t 2 /nobreak > nul\n"
        f'move /y "{new_exe}" "{current_exe}"\n'
        f'start "" "{current_exe}"\n'
        "del \"%~f0\"\n"
    )
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat)

    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    sys.exit(0)
