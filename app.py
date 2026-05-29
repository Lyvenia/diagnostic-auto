"""
RODIA Diagnostic — Serveur Flask v2 (architecture restructurée).
"""
import os
import sys
import traceback as _tb
from flask import Flask, jsonify
from flask_cors import CORS
from core.paths import data_path, LOG_PATH
import time as _t


def _log(msg: str):
    try:
        ts = _t.strftime("%H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _find_static_folder() -> str:
    # COPIE EXACTE depuis l'ancien app.py
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(sys._MEIPASS, "frontend"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "frontend"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "_internal", "frontend"))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend"))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


_static_folder = _find_static_folder()
app = Flask(__name__, static_folder=_static_folder, static_url_path="")
CORS(app)

# ── Cache frontend ────────────────────────────────────────────────────────────
_frontend_cache: dict = {}

def _load_frontend_cache():
    files = {
        "index.html": "text/html; charset=utf-8",
        "app.js":     "application/javascript; charset=utf-8",
        "style.css":  "text/css; charset=utf-8",
    }
    for filename, mime in files.items():
        for folder in [
            _static_folder,
            os.path.join(
                os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)),
                "_internal", "frontend"
            )
        ]:
            path = os.path.join(folder, filename)
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        _frontend_cache[filename] = (f.read(), mime)
                    break
                except Exception:
                    pass

_load_frontend_cache()


# Headers anti-cache : Edge cache trop agressivement sous --user-data-dir stable
# → un app.js mis à jour n'est jamais rechargé. On force un fetch à chaque load.
_NO_CACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma":        "no-cache",
    "Expires":       "0",
}

def _with_no_cache(content: str, mime: str):
    return content, 200, {"Content-Type": mime, **_NO_CACHE}


@app.route("/")
def index():
    if "index.html" in _frontend_cache:
        content, mime = _frontend_cache["index.html"]
        return _with_no_cache(content, mime)
    return app.send_static_file("index.html")


@app.route("/app.js")
def serve_js():
    if "app.js" in _frontend_cache:
        content, mime = _frontend_cache["app.js"]
        return _with_no_cache(content, mime)
    return app.send_static_file("app.js")


@app.route("/style.css")
def serve_css():
    if "style.css" in _frontend_cache:
        content, mime = _frontend_cache["style.css"]
        return _with_no_cache(content, mime)
    return app.send_static_file("style.css")


# ── Blueprints ────────────────────────────────────────────────────────────────
from api.obd_routes import bp as obd_bp
from api.analysis_routes import bp as analysis_bp
from api.fleet_routes import bp as fleet_bp
from api.export_routes import bp as export_bp
from api.config_routes import bp as config_bp
from api.support_routes import bp as support_bp
from routes.lyvenia_auth import bp as lyvenia_auth_bp
from routes.update_routes import bp as update_bp

app.register_blueprint(obd_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(fleet_bp)
app.register_blueprint(export_bp)
app.register_blueprint(config_bp)
app.register_blueprint(support_bp)
app.register_blueprint(lyvenia_auth_bp)
app.register_blueprint(update_bp)


# ── Error handlers globaux ────────────────────────────────────────────────────
# Attrape TOUTES les exceptions non gérées dans n'importe quelle route.
# Sans ceci, une exception dans une route peut tuer le thread Werkzeug (crash silencieux).
@app.errorhandler(Exception)
def handle_uncaught_exception(exc):
    """Catch-all : log + JSON 500 propre, empêche Flask de mourir."""
    from werkzeug.exceptions import HTTPException
    # Laisse passer les erreurs HTTP normales (404, 400, etc.)
    if isinstance(exc, HTTPException):
        return exc
    try:
        _log(f"[GLOBAL_ERROR] {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
    except Exception:
        pass
    return jsonify({
        "error": "Erreur serveur interne",
        "type": type(exc).__name__,
        "message": str(exc)[:300],
    }), 500


if __name__ == "__main__":
    _log("[app] Démarrage RODIA v2 (architecture restructurée)")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)
