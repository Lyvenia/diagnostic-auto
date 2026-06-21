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
        # PS 5.1 négocie TLS 1.0 par défaut → GitHub rejette (connexion coupée).
        # On force TLS 1.2 (+1.3 si dispo) sinon Invoke-WebRequest échoue.
        "try { [Net.ServicePointManager]::SecurityProtocol = "
        "[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}\n"
        "try { [Net.ServicePointManager]::SecurityProtocol = "
        "[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls13 } catch {}\n"
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
        "    # ── 1. Téléchargement (TLS 1.2 forcé ci-dessus) ──\n"
        "    try { Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing } catch {}\n"
        "    # Fallback curl.exe (Windows 10 1803+) — gère TLS nativement\n"
        "    if ((-not (Test-Path $installer)) -or ((Get-Item $installer -ErrorAction SilentlyContinue).Length -lt 1MB)) {\n"
        "        & curl.exe -L -s --tlsv1.2 -o $installer $url 2>&1 | Out-Null\n"
        "    }\n"
        "    if ((-not (Test-Path $installer)) -or ((Get-Item $installer -ErrorAction SilentlyContinue).Length -lt 1MB)) {\n"
        "        \"[$(Get-Date)] Téléchargement échoué — fichier absent ou tronqué\" | Out-File -FilePath $logPath -Append\n"
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
        "        # Relance RODIA — /VERYSILENT + skipifsilent empêchent le [Run]\n"
        "        # postinstall du .iss, on relance donc explicitement l'exe installé.\n"
        "        $appExe = $null\n"
        "        foreach ($root in 'HKCU:','HKLM:') {\n"
        "            $k = \"$root\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{F3A8B2C1-4D7E-4F9A-B6C3-2E1D5A8F7B90}_is1\"\n"
        "            try {\n"
        "                $loc = (Get-ItemProperty -Path $k -ErrorAction Stop).InstallLocation\n"
        "                if ($loc) { $c = Join-Path $loc 'RODIA.exe'; if (Test-Path $c) { $appExe = $c; break } }\n"
        "            } catch {}\n"
        "        }\n"
        "        if (-not $appExe) {\n"
        "            $c = Join-Path $env:LOCALAPPDATA 'Programs\\Lyvenia\\RODIA\\RODIA.exe'\n"
        "            if (Test-Path $c) { $appExe = $c }\n"
        "        }\n"
        "        if ($appExe) { Start-Process -FilePath $appExe }\n"
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
        # UTF-8 AVEC BOM : PowerShell 5.1 lance les .ps1 sans BOM en ANSI
        # (cp1252) → les accents/tirets cadratins cassent la syntaxe.
        # Le BOM force la détection UTF-8 et un parsing fiable.
        with open(ps1_path, "w", encoding="utf-8-sig") as f:
            f.write(ps1)

        # Flags Windows pour que le script PowerShell SURVIVE à la mort de
        # RODIA (le user peut fermer la fenêtre brutalement) :
        #
        # - CREATE_NO_WINDOW        : pas de console visible (hidden)
        # - CREATE_BREAKAWAY_FROM_JOB : sort du job object parent (Edge) →
        #   ne meurt pas avec lui
        #
        # ⚠️ NE PAS ajouter DETACHED_PROCESS : combiné à `-NonInteractive`,
        # PowerShell sort immédiatement sans console — l'install ne démarre
        # même pas. Bug découvert le 21/06/2026 (Bastien — logs vides + .ps1
        # non auto-supprimé). CREATE_BREAKAWAY_FROM_JOB suffit pour la survie
        # au kill de RODIA, c'était lui le fix utile de v1.1.13.
        CREATE_BREAKAWAY_FROM_JOB  = 0x01000000
        _flags = subprocess.CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-File", ps1_path,
            ],
            creationflags=_flags,
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
