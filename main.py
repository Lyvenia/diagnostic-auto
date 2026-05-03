"""
DiagnosticAuto — Point d'entrée principal.
Lance Flask puis ouvre Edge/Chrome en mode --app (fenêtre native sans onglets).
"""
import os
import sys
import socket
import threading
import time
import webbrowser
import traceback
import subprocess

# ── Répertoire de base ────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Dossier de données utilisateur (%APPDATA%\RODIA en prod, racine projet en dev)
if getattr(sys, "frozen", False):
    _appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    DATA_DIR  = os.path.join(_appdata, "RODIA")
else:
    DATA_DIR = BASE_DIR
os.makedirs(DATA_DIR, exist_ok=True)

LOG_PATH = os.path.join(DATA_DIR, "DiagnosticAuto_error.log")


def _log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# ── Redirection stderr/stdout vers le log (critique pour console=False) ──────
# Sans console, les erreurs C de ReportLab/Pillow sortent dans le vide → crash
# silencieux. On redirige vers un fichier pour ne plus rien rater.
if getattr(sys, "frozen", False):
    try:
        _stderr_path = os.path.join(DATA_DIR, "DiagnosticAuto_stderr.log")
        _stderr_file = open(_stderr_path, "a", encoding="utf-8", buffering=1)
        _stderr_file.write(f"\n=== stderr opened {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        sys.stderr = _stderr_file
        sys.stdout = _stderr_file
    except Exception:
        pass


# ── Safety nets globaux ──────────────────────────────────────────────────────
# Empêche un crash de thread daemon ou une exception non gérée de tuer le process
# silencieusement (observé au moins une fois lors de l'export PDF).

def _global_excepthook(exc_type, exc_value, exc_tb):
    try:
        _log(f"[UNCAUGHT] {exc_type.__name__}: {exc_value}\n"
             f"{''.join(traceback.format_exception(exc_type, exc_value, exc_tb))}")
    except Exception:
        pass

sys.excepthook = _global_excepthook

def _thread_excepthook(args):
    try:
        _log(f"[THREAD_UNCAUGHT] {args.thread.name} {args.exc_type.__name__}: {args.exc_value}\n"
             f"{''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))}")
    except Exception:
        pass

# threading.excepthook n'existe qu'à partir de Python 3.8
if hasattr(threading, "excepthook"):
    threading.excepthook = _thread_excepthook


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Protection single-instance ────────────────────────────────────────────────

def _acquire_instance_lock(data_dir: str, port: int) -> bool:
    """
    Vérifie qu'aucune autre instance de RODIA n'est déjà active.
    Si une instance répond sur son port, on abandonne (retourne False).
    Sinon, on écrit le verrou et on retourne True.
    """
    import urllib.request
    lock_path = os.path.join(data_dir, "instance.lock")

    if os.path.exists(lock_path):
        try:
            with open(lock_path) as f:
                old_port = int(f.read().strip())
            with urllib.request.urlopen(
                f"http://127.0.0.1:{old_port}/health", timeout=2
            ) as r:
                if r.status == 200:
                    _log(f"Instance déjà active sur port {old_port} — abandon")
                    return False
        except Exception:
            pass  # Verrou périmé — on continue
        try:
            os.remove(lock_path)
        except Exception:
            pass

    try:
        with open(lock_path, "w") as f:
            f.write(str(port))
    except Exception:
        pass
    return True


def _release_instance_lock(data_dir: str):
    try:
        os.remove(os.path.join(data_dir, "instance.lock"))
    except Exception:
        pass


def _wait_flask(port: int, timeout: float = 60.0) -> bool:
    """Attend que Flask serve correctement /health ET les fichiers frontend."""
    import urllib.request, urllib.error

    deadline = time.time() + timeout
    attempt = 0

    # Étape 1 : attendre que /health réponde 200
    health_url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    _log(f"Flask /health OK après {attempt} tentatives")
                    break
        except urllib.error.HTTPError as e:
            _log(f"Flask /health HTTPError {e.code} — considéré prêt")
            break
        except Exception as e:
            _log(f"Tentative {attempt}: {type(e).__name__}")
            time.sleep(0.3)
    else:
        _log(f"Flask timeout /health après {attempt} tentatives")
        return False

    # Étape 2 : vérifier que les fichiers frontend sont bien servis
    # (Flask peut répondre à /health avant que le cache frontend soit prêt)
    frontend_urls = [
        f"http://127.0.0.1:{port}/",
        f"http://127.0.0.1:{port}/app.js",
        f"http://127.0.0.1:{port}/style.css",
    ]
    for furl in frontend_urls:
        ok = False
        for _ in range(10):
            try:
                with urllib.request.urlopen(furl, timeout=3) as resp:
                    if resp.status == 200:
                        ok = True
                        break
            except Exception:
                time.sleep(0.3)
        if not ok:
            _log(f"Frontend non disponible: {furl}")
            return False

    _log("Flask + frontend entièrement prêts")
    return True


# ── Flask ─────────────────────────────────────────────────────────────────────

def _run_flask(port: int):
    try:
        _log("Import app...")
        from app import app
        _log(f"app importé — static_folder: {app.static_folder}")
        _log(f"static_folder existe: {os.path.isdir(app.static_folder or '')}")
        if app.static_folder and os.path.isdir(app.static_folder):
            _log(f"contenu: {os.listdir(app.static_folder)}")
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        _log(f"Flask.run() port={port}")
        app.run(host="127.0.0.1", port=port, debug=False,
                use_reloader=False, threaded=True)
    except Exception:
        _log(f"ERREUR Flask:\n{traceback.format_exc()}")


# ── Ouvrir en mode app (fenêtre native sans onglets) ─────────────────────────

def _open_app_window(url: str):
    """Ouvre Edge ou Chrome en mode --app. Retourne le processus ou None.

    Le dossier profil temporaire porte le préfixe "DiagnosticAuto_" —
    ce préfixe est utilisé par update_routes pour cibler et fermer
    les msedge.exe de cette session lors d'une mise à jour.
    """
    import tempfile

    ev = os.path.expandvars
    edge_paths = [
        ev(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ev(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ev(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    chrome_paths = [
        ev(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        ev(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ev(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]

    # Dossier profil temporaire pour forcer une instance dédiée et traçable
    user_data_dir = tempfile.mkdtemp(prefix="DiagnosticAuto_")

    for path in edge_paths + chrome_paths:
        if os.path.exists(path):
            _log(f"Ouverture app mode: {path}")
            proc = subprocess.Popen([
                path,
                f"--app={url}",
                f"--user-data-dir={user_data_dir}",
                "--window-size=1280,800",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            return proc

    _log("Edge/Chrome non trouvé — fallback navigateur système")
    webbrowser.open(url)
    return None


# ── Heartbeat watcher ────────────────────────────────────────────────────────

def _watch_heartbeat(hb_file: str, first_ping_timeout: float = 60.0, idle_timeout: float = 600.0):
    """
    Attend le premier heartbeat JS FRAIS (postérieur au démarrage de la surveillance),
    puis surveille les pings. Retourne quand plus aucun ping n'est reçu pendant
    idle_timeout secondes (= l'utilisateur a fermé la fenêtre).

    idle_timeout à 600s (10 min) pour :
      - survivre aux analyses IA longues (30-120s) pendant lesquelles Edge peut
        throttler le setInterval JS s'il a perdu le focus ;
      - survivre au téléchargement d'une mise à jour (plusieurs Mo) ;
      - éviter les fausses détections de fermeture de fenêtre.
    """
    # Horodatage de démarrage — on n'accepte que les heartbeats créés APRÈS ce moment
    start_time = time.time()

    # Supprimer tout résidu du lancement précédent pour éviter un faux positif
    try:
        os.remove(hb_file)
    except Exception:
        pass

    _log(f"Attente premier heartbeat frais (max {first_ping_timeout}s)…")
    deadline = start_time + first_ping_timeout
    while time.time() < deadline:
        try:
            mtime = os.path.getmtime(hb_file)
            if mtime >= start_time - 1.0:          # heartbeat postérieur au démarrage
                _log(f"Premier heartbeat frais reçu")
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        _log("Aucun heartbeat frais — arrêt du serveur")
        return

    # Surveille les pings suivants
    while True:
        time.sleep(1)
        try:
            mtime = os.path.getmtime(hb_file)
            age = time.time() - mtime
            if age > idle_timeout:
                _log(f"Heartbeat silencieux depuis {age:.1f}s (seuil {idle_timeout}s) — fenêtre fermée")
                return
        except Exception:
            _log("Fichier heartbeat disparu — arrêt")
            return


# ── Splash (tkinter) ──────────────────────────────────────────────────────────

def _splash(flask_ready: threading.Event, start_time: float):
    """Splash tkinter — DOIT tourner dans le main thread.

    ⚠️ Tcl/Tk + threads = crash. Tout objet tkinter (StringVar, Frame, etc.)
    finalisé hors du main thread plante via Tcl_AsyncDelete. Comme Flask tourne
    en threaded=True, on doit FORCER le nettoyage tkinter dans le main thread
    AVANT toute requête API : destroy explicite + suppression des refs + gc.
    """
    import gc
    root = None
    try:
        import tkinter as tk
        BG, ACCENT, WHITE, DIM = "#0c180c", "#e8b4a4", "#f0f0ec", "#5a8a5a"
        root = tk.Tk()
        root.overrideredirect(True)
        root.configure(bg=BG)
        root.resizable(False, False)
        W, H = 480, 260
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        root.lift(); root.attributes("-topmost", True)

        # Refs fortes aux widgets pour empêcher GC pendant mainloop
        widgets = []
        widgets.append(tk.Frame(root, bg=ACCENT, height=3)); widgets[-1].pack(fill="x")
        widgets.append(tk.Frame(root, bg=BG, height=28));    widgets[-1].pack()
        widgets.append(tk.Label(root, text="RODIA", font=("Segoe UI", 34, "bold"),
                                bg=BG, fg=ACCENT)); widgets[-1].pack()
        widgets.append(tk.Label(root, text="by Lyvenia · Diagnostic Connecté",
                                font=("Segoe UI", 11), bg=BG, fg=DIM))
        widgets[-1].pack(pady=(4, 0))
        widgets.append(tk.Frame(root, bg=BG, height=28));    widgets[-1].pack()
        sv = tk.StringVar(master=root, value="Démarrage…")
        widgets.append(tk.Label(root, textvariable=sv, font=("Segoe UI", 10),
                                bg=BG, fg=DIM)); widgets[-1].pack()
        canvas = tk.Canvas(root, width=300, height=4, bg="#1a2e1a",
                           highlightthickness=0, bd=0)
        widgets.append(canvas); canvas.pack(pady=(12, 0))
        bar = canvas.create_rectangle(0, 0, 0, 4, fill=ACCENT, outline="")
        pos = [0]

        def animate():
            try:
                canvas.coords(bar, pos[0], 0, pos[0]+80, 4)
                pos[0] = (pos[0] + 4) % 300
                root.after(30, animate)
            except tk.TclError:
                pass  # root détruit — on sort sans relancer le timer

        def poll():
            try:
                elapsed = time.time() - start_time
                if flask_ready.is_set() and elapsed >= 2.0:
                    root.quit()
                else:
                    sv.set(f"Démarrage… ({int(elapsed)}s)")
                    root.after(100, poll)
            except tk.TclError:
                pass

        root.after(30, animate)
        root.after(100, poll)
        root.mainloop()
    except Exception as e:
        _log(f"Splash ignoré: {e}")
        flask_ready.wait(timeout=30)
    finally:
        # ⚠️ CRITIQUE — nettoyage tkinter dans le main thread.
        # Sans ça, des `tk.Variable` traînent en mémoire et leur __del__ peut
        # être déclenché par GC dans un thread Flask → Tcl_AsyncDelete + crash.
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
        # Supprimer toutes les refs locales tkinter avant gc.collect()
        try:
            del widgets, sv, canvas, bar, pos, animate, poll, root
        except Exception:
            pass
        # Force le GC dans le main thread → __del__ tkinter s'exécute ici, pas
        # dans un thread Flask. Trois passes pour résoudre les cycles.
        for _ in range(3):
            gc.collect()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    _log(f"=== Démarrage {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    _log(f"BASE_DIR: {BASE_DIR}")
    _log(f"DATA_DIR: {DATA_DIR}")

    port = _find_free_port()
    _log(f"Port: {port}")

    # ── Protection single-instance ──────────────────────────────────────────
    # Si une autre instance de RODIA répond déjà, on sort silencieusement.
    # Ceci évite que le 2ème lancement efface le fichier .heartbeat et tue
    # le Flask de la première instance au pire moment (ex. pendant un update).
    if not _acquire_instance_lock(DATA_DIR, port):
        sys.exit(0)

    url = f"http://127.0.0.1:{port}"

    threading.Thread(target=_run_flask, args=(port,), daemon=True).start()

    flask_ready = threading.Event()
    flask_ok = [False]

    def _probe():
        flask_ok[0] = _wait_flask(port, timeout=30)
        flask_ready.set()

    threading.Thread(target=_probe, daemon=True).start()

    _splash(flask_ready, time.time())

    if not flask_ok[0]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Impossible de démarrer.\nConsultez DiagnosticAuto_error.log\nPort: {port}",
                "RODIA", 0x10)
        except Exception:
            pass
        sys.exit(1)

    # Délai de sécurité — laisse Edge/Windows terminer toute initialisation
    time.sleep(1.5)
    _log("Ouverture de la fenêtre application…")
    proc = _open_app_window(url)

    hb_file = os.path.join(DATA_DIR, ".heartbeat")
    # La suppression du résidu est gérée dans _watch_heartbeat (avec vérification freshness)

    if proc is not None:
        # Edge/Chrome lance un processus "launcher" qui se ferme immédiatement
        # en spawant la vraie fenêtre dans un process séparé.
        # On surveille donc le fichier heartbeat plutôt que le process.
        proc_start = time.time()
        proc.wait()
        proc_elapsed = time.time() - proc_start

        if proc_elapsed < 10.0:
            _log(f"Launcher Edge sorti en {proc_elapsed:.1f}s — surveillance heartbeat")
            _watch_heartbeat(hb_file)
        else:
            _log("Fenêtre fermée normalement — arrêt du serveur")
    else:
        # Fallback navigateur système
        _watch_heartbeat(hb_file)

    _release_instance_lock(DATA_DIR)
    os._exit(0)


if __name__ == "__main__":
    main()
