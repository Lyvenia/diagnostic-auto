; ══════════════════════════════════════════════════════════════════════════════
;  RODIA — Script d'installation Inno Setup 6+
;  Éditeur : Lyvenia / Bastien Rodrigues de Souza Meireles
;  Prérequis : Inno Setup 6 — https://jrsoftware.org/isinfo.php
;
;  Usage :
;    1. Construire RODIA avec PyInstaller (pyinstaller DiagnosticAuto.spec)
;    2. Ouvrir ce fichier dans Inno Setup Compiler
;    3. Build → l'installateur est généré dans installer\RODIA-Setup-v1.0.1.exe
; ══════════════════════════════════════════════════════════════════════════════

#define AppName      "RODIA"
#define AppVersion   "1.1.5"
#define AppPublisher "Lyvenia"
#define AppURL       "https://lyvenia.fr/rodia.html"
#define AppExeName   "RODIA.exe"
#define SourceDir    "dist\RODIA"

; ── Paramètres généraux ────────────────────────────────────────────────────────
[Setup]
; GUID unique — ne jamais changer après la première publication
AppId={{F3A8B2C1-4D7E-4F9A-B6C3-2E1D5A8F7B90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:contact@lyvenia.fr
AppUpdatesURL=https://lyvenia.fr/telecharger.html

; Dossier d'installation par défaut (pas besoin d'admin)
DefaultDirName={autopf}\Lyvenia\RODIA
DefaultGroupName=Lyvenia\RODIA

; Sortie
OutputDir=installer
OutputBaseFilename=RODIA-Setup-v{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes

; Interface moderne
WizardStyle=modern
WizardResizable=no

; Pas besoin d'être administrateur — installe dans AppData si sans droits
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Inno Setup ferme automatiquement RODIA avant l'install (sans rien demander
; à l'utilisateur). Évite l'erreur "fichier en cours d'utilisation" lors
; d'une mise à jour. RestartApplications=no : on laisse [Run] postinstall
; lancer RODIA — sinon l'app se lance 2 fois.
CloseApplications=yes
RestartApplications=no

; Infos désinstallateur
UninstallDisplayName={#AppName} by {#AppPublisher}
UninstallDisplayIcon={app}\{#AppExeName}

; ── Langue ────────────────────────────────────────────────────────────────────
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

; ── Messages personnalisés ─────────────────────────────────────────────────────
[CustomMessages]
french.WelcomeLabel1=Bienvenue dans l'assistant d'installation de [name]
french.WelcomeLabel2=Ce programme va installer [name/ver] sur votre ordinateur.%n%nVous aurez besoin de vos identifiants Lyvenia pour vous connecter au premier lancement.%n%nCliquez sur Suivant pour continuer.
french.FinishedLabel=L'installation de [name] est terminée.%n%nCliquez sur Terminer pour quitter l'assistant.

; ── Tâches optionnelles ────────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; \
  Description: "Créer un raccourci sur le Bureau"; \
  GroupDescription: "Raccourcis :"

Name: "startmenuicon"; \
  Description: "Créer un raccourci dans le menu Démarrer"; \
  GroupDescription: "Raccourcis :"

; ── Fichiers à installer ───────────────────────────────────────────────────────
[Files]
; Tout le dossier dist\RODIA\ (exe + _internal/)
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ── Raccourcis ────────────────────────────────────────────────────────────────
[Icons]
; Menu Démarrer
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  Tasks: startmenuicon

Name: "{group}\Désinstaller {#AppName}"; \
  Filename: "{uninstallexe}"; \
  Tasks: startmenuicon

; Bureau
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

; ── Lancement après installation ───────────────────────────────────────────────
[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "Lancer {#AppName} maintenant"; \
  Flags: nowait postinstall skipifsilent

; ── Avant désinstallation : ferme RODIA si ouvert ─────────────────────────────
[UninstallRun]
Filename: "taskkill.exe"; \
  Parameters: "/f /im {#AppExeName}"; \
  Flags: runhidden; \
  RunOnceId: "KillRODIA"

; ── Nettoyage à la désinstallation ────────────────────────────────────────────
[UninstallDelete]
; Supprime le dossier RODIA dans AppData (config, logs, flotte)
; Note : config.json n'est PAS supprimé à chaque install (il contient le JWT de session).
; La migration Python dans core/config.py corrige simulation_mode au démarrage si besoin.
Type: filesandordirs; Name: "{userappdata}\RODIA"
