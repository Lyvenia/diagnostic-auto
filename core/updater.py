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


def prepare_update_script(
    download_url: str,
    sha256: str | None = None,
    version: str | None = None,
) -> bool:
    """Génère un script PowerShell autonome qui télécharge et installe RODIA.

    Mise à jour silencieuse style Chrome/VSCode :
      - Aucune fenêtre Inno Setup visible (flags /VERYSILENT /SUPPRESSMSGBOXES /NORESTART)
      - Vérification SHA-256 du fichier téléchargé (si fourni) — abort si mismatch
      - Toast Windows à la fin pour confirmer la mise à jour
      - L'app se relance automatiquement via [Run] postinstall du .iss

    Args:
        download_url: URL de l'installateur (.exe Inno Setup).
        sha256: Hash SHA-256 attendu pour vérification d'intégrité (optionnel).
        version: Version cible (ex: "1.1.4") pour le toast de notification.

    Returns:
        True si le script PowerShell a pu être démarré, False sinon.
        Ne fait rien (retourne True) en mode développement (non-frozen).
    """
    if not getattr(sys, "frozen", False):
        return True  # En dev, on ne fait rien — le test passe directement

    import tempfile
    tmp_dir        = tempfile.gettempdir()
    installer_path = os.path.join(tmp_dir, "RODIA-Update-Setup.exe")
    ps1_path       = os.path.join(tmp_dir, "rodia_update.ps1")
    log_path       = os.path.join(tmp_dir, "rodia_update_error.txt")

    # Hash + version échappés pour intégration sûre dans le script
    sha256_safe  = (sha256 or "").lower().strip()
    version_safe = (version or "nouvelle version").replace("'", "")

    # Script PowerShell autonome — workflow silencieux complet :
    #   1. Attend 4s pour que RODIA s'auto-ferme (os._exit Python)
    #   2. Télécharge l'installateur depuis GitHub Releases
    #   3. Vérifie le SHA-256 si fourni (sécurité — abort si mismatch)
    #   4. Force la fermeture de RODIA + WebView Edge orpheline (boucle 5s)
    #   5. Lance l'installateur en /VERYSILENT (aucune fenêtre)
    #   6. Affiche un toast Windows "RODIA mis à jour"
    #   7. Se supprime
    ps1 = (
        "$ProgressPreference = 'SilentlyContinue'\n"
        "$ErrorActionPreference = 'Continue'\n"
        "Start-Sleep -Seconds 4\n"
        f"$installer    = '{installer_path}'\n"
        f"$url          = '{download_url}'\n"
        f"$expectedSha  = '{sha256_safe}'\n"
        f"$version      = '{version_safe}'\n"
        f"$logPath      = '{log_path}'\n"
        "\n"
        "function Show-Toast([string]$title, [string]$message) {\n"
        "    try {\n"
        "        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]\n"
        "        $template = '<toast><visual><binding template=\"ToastGeneric\"><text>' + $title + '</text><text>' + $message + '</text></binding></visual></toast>'\n"
        "        $xml = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime]::new()\n"
        "        $xml.LoadXml($template)\n"
        "        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
        "        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('RODIA').Show($toast)\n"
        "    } catch { }  # toast facultatif — pas bloquant\n"
        "}\n"
        "\n"
        "try {\n"
        "    # ── 1. Téléchargement ──\n"
        "    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing\n"
        "    if (-not (Test-Path $installer)) {\n"
        "        \"[$(Get-Date)] Téléchargement échoué — fichier absent\" | Out-File -FilePath $logPath -Append\n"
        "        Show-Toast 'RODIA — Mise à jour échouée' 'Le téléchargement a échoué. Réessayez plus tard.'\n"
        "        exit 1\n"
        "    }\n"
        "\n"
        "    # ── 2. Vérification SHA-256 (si fourni) ──\n"
        "    if ($expectedSha) {\n"
        "        $actualSha = (Get-FileHash -Path $installer -Algorithm SHA256).Hash.ToLower()\n"
        "        if ($actualSha -ne $expectedSha) {\n"
        "            \"[$(Get-Date)] SHA-256 mismatch : attendu $expectedSha / obtenu $actualSha\" | Out-File -FilePath $logPath -Append\n"
        "            Remove-Item -Path $installer -Force -ErrorAction SilentlyContinue\n"
        "            Show-Toast 'RODIA — Mise à jour rejetée' 'Le fichier téléchargé est corrompu ou altéré. Mise à jour annulée par sécurité.'\n"
        "            exit 2\n"
        "        }\n"
        "    }\n"
        "\n"
        "    # ── 3. Kill RODIA + WebView en boucle jusqu'à 5s ──\n"
        "    $deadline = (Get-Date).AddSeconds(5)\n"
        "    while ((Get-Date) -lt $deadline) {\n"
        "        $alive = Get-Process | Where-Object {\n"
        "            ($_.ProcessName -eq 'RODIA') -or\n"
        "            ($_.MainWindowTitle -like '*RODIA*')\n"
        "        }\n"
        "        if (-not $alive) { break }\n"
        "        $alive | Stop-Process -Force -ErrorAction SilentlyContinue\n"
        "        Start-Sleep -Milliseconds 300\n"
        "    }\n"
        "    taskkill /F /T /IM RODIA.exe 2>&1 | Out-Null\n"
        "    Start-Sleep -Milliseconds 500\n"
        "\n"
        "    # ── 4. Installation silencieuse Inno Setup ──\n"
        "    # /VERYSILENT       : aucune fenêtre d'install visible\n"
        "    # /SUPPRESSMSGBOXES : pas de popup d'erreur Inno (les vraies erreurs vont en exit code)\n"
        "    # /NORESTART        : pas de prompt reboot Windows\n"
        "    $proc = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru\n"
        "    if ($proc.ExitCode -ne 0) {\n"
        "        \"[$(Get-Date)] Inno Setup exit code : $($proc.ExitCode)\" | Out-File -FilePath $logPath -Append\n"
        "        Show-Toast 'RODIA — Mise à jour échouée' \"Erreur d'installation (code $($proc.ExitCode)). Relancez RODIA pour réessayer.\"\n"
        "    } else {\n"
        "        Show-Toast 'RODIA mis à jour' \"Version $version installée avec succès.\"\n"
        "    }\n"
        "    Remove-Item -Path $installer -Force -ErrorAction SilentlyContinue\n"
        "\n"
        "} catch {\n"
        "    \"[$(Get-Date)] Exception : $_\" | Out-File -FilePath $logPath -Append\n"
        "    Show-Toast 'RODIA — Mise à jour échouée' 'Une erreur est survenue. Consultez les logs.'\n"
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
