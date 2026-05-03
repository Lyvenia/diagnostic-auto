"""Auto-updater RODIA — vérifie et prépare les mises à jour.

Fonctionnement :
  1. check_update()           → compare la version locale avec api.lyvenia.fr/version
  2. prepare_update_script()  → génère le script PowerShell qui télécharge ET installe
                                 RODIA après la fermeture de l'application.
                                 L'exit du process est géré par la route /api/exit-now.
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


def prepare_update_script(download_url: str) -> bool:
    """Génère un script PowerShell autonome qui télécharge et installe RODIA.

    Le script est lancé en arrière-plan. Il attend 6 secondes (pour que RODIA se ferme),
    télécharge l'installateur, l'exécute silencieusement, puis relance RODIA.
    Retourne True si le script a pu être démarré, False sinon.
    Ne fait rien (retourne True) en mode développement (non-frozen).
    """
    if not getattr(sys, "frozen", False):
        return True  # En dev, on ne fait rien — le test passe directement

    import tempfile
    tmp_dir        = tempfile.gettempdir()
    installer_path = os.path.join(tmp_dir, "RODIA-Update-Setup.exe")
    ps1_path       = os.path.join(tmp_dir, "rodia_update.ps1")

    # Script PowerShell autonome :
    #   - Attend 4s que RODIA ait pu se fermer (via os._exit côté Python)
    #   - Télécharge l'installateur
    #   - Force la fermeture de RODIA s'il reste ouvert (pywebview + os._exit
    #     ne libère pas toujours la fenêtre Edge → écrasement du .exe bloqué)
    #   - Lance l'installateur Inno Setup
    #   - Se supprime
    ps1 = (
        "$ProgressPreference = 'SilentlyContinue'\n"
        "Start-Sleep -Seconds 4\n"
        f"$installer = '{installer_path}'\n"
        f"$url       = '{download_url}'\n"
        "try {\n"
        "    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing\n"
        "    if (Test-Path $installer) {\n"
        # Force la fermeture de RODIA avant d'écraser les fichiers.
        # Stop-Process kill le process + ses enfants (la WebView Edge).
        # ErrorAction SilentlyContinue : si RODIA est déjà fermé, on ignore.
        "        Stop-Process -Name RODIA -Force -ErrorAction SilentlyContinue\n"
        "        Start-Sleep -Milliseconds 500\n"
        # Lance le wizard Inno Setup normalement — l'utilisateur voit la progression
        # et clique Suivant. Pas de /VERYSILENT : plus simple, plus fiable.
        "        Start-Process -FilePath $installer -Wait\n"
        "        Remove-Item -Path $installer -Force -ErrorAction SilentlyContinue\n"
        "    }\n"
        "} catch {\n"
        "    $_ | Out-File -FilePath \"$env:TEMP\\rodia_update_error.txt\" -Append\n"
        "}\n"
        f"Remove-Item -LiteralPath '{ps1_path}' -Force -ErrorAction SilentlyContinue\n"
    )

    try:
        with open(ps1_path, "w", encoding="utf-8") as f:
            f.write(ps1)

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-File", ps1_path,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


# Alias de compatibilité — les anciens appels via download_and_apply continuent de fonctionner
def download_and_apply(download_url: str, on_progress=None) -> None:
    """Compatibilité : délègue à prepare_update_script."""
    prepare_update_script(download_url)
    if on_progress:
        on_progress(100)
