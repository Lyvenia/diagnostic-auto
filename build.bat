@echo off
chcp 65001 >nul
setlocal

echo.
echo  ===============================================
echo    DiagnosticAuto -- Build script
echo  ===============================================
echo.

REM ── Dependances ──────────────────────────────────
echo [1/5] Installation des dependances...
pip install pyinstaller pywebview pillow --quiet
if errorlevel 1 (
    echo ERREUR: pip install a echoue.
    pause & exit /b 1
)
echo      OK

REM ── Icone ────────────────────────────────────────
echo [2/5] Generation de l'icone...
python create_icon.py
if errorlevel 1 (
    echo ERREUR: create_icon.py a echoue.
    pause & exit /b 1
)
echo      OK

REM ── Nettoyage ─────────────────────────────────────
echo [3/5] Nettoyage des builds precedents...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
echo      OK

REM ── PyInstaller ───────────────────────────────────
echo [4/5] Compilation PyInstaller (peut prendre 2-3 min)...
pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name DiagnosticAuto ^
    --icon icon.ico ^
    --add-data "frontend;frontend" ^
    --add-data "icon.ico;." ^
    --collect-all webview ^
    --hidden-import flask ^
    --hidden-import flask_cors ^
    --hidden-import flask.templating ^
    --hidden-import anthropic ^
    --hidden-import obd ^
    --hidden-import obd.commands ^
    --hidden-import obd.protocols ^
    --hidden-import obd.utils ^
    --hidden-import obd.elm327 ^
    --hidden-import obd.decoders ^
    --hidden-import serial ^
    --hidden-import serial.tools ^
    --hidden-import serial.tools.list_ports ^
    --hidden-import reportlab ^
    --hidden-import reportlab.lib ^
    --hidden-import reportlab.platypus ^
    --hidden-import reportlab.pdfbase ^
    --hidden-import openpyxl ^
    --hidden-import openpyxl.styles ^
    --hidden-import openpyxl.utils ^
    --hidden-import pint ^
    --hidden-import requests ^
    --hidden-import tkinter ^
    --hidden-import clr ^
    main.py

if errorlevel 1 (
    echo ERREUR: PyInstaller a echoue. Voir les logs ci-dessus.
    pause & exit /b 1
)
echo      OK

REM ── Fichiers de donnees ───────────────────────────
echo [5/5] Copie des fichiers de configuration...

REM config.json (cle API + port COM) -> a cote du .exe
copy /y config.json "dist\DiagnosticAuto\config.json" >nul

REM flotte.json vide (cree au premier demarrage si absent)
echo {} > "dist\DiagnosticAuto\flotte.json"

REM README
(
echo DiagnosticAuto - Guide de demarrage rapide
echo ==========================================
echo.
echo 1. Brancher l'adaptateur ELM327 sur le port OBD2 du vehicule
echo    puis sur le port USB de l'ordinateur.
echo.
echo 2. Ouvrir config.json avec le Bloc-notes et renseigner :
echo    - "port" : le port COM de l'adaptateur (ex: "COM3", "COM4"...)
echo      Pour le trouver : Gestionnaire de peripheriques > Ports COM et LPT
echo    - "simulation_mode" : true pour tester sans vehicule, false en reel
echo.
echo 3. Double-cliquer sur DiagnosticAuto.exe pour lancer le logiciel.
echo    Une fenetre s'ouvre directement (pas de navigateur necessaire).
echo.
echo REMARQUES :
echo - Les donnees de la flotte sont dans flotte.json (ne pas supprimer).
echo - Les sauvegardes se trouvent dans le sous-dossier backups/.
echo - L'application necessite Microsoft Edge WebView2 Runtime
echo   (pre-installe sur Windows 10 / 11 -- si absent, telecharger sur microsoft.com)
) > "dist\DiagnosticAuto\README.txt"

echo      OK
echo.
echo  ===============================================
echo    Build termine !
echo    Dossier livrable : dist\DiagnosticAuto\
echo  ===============================================
echo.
echo Contenu :
dir /b "dist\DiagnosticAuto\"
echo.
pause
