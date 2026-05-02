"""
Endpoint /api/support/* — Diagnostic d'environnement pour le bouton
« Signaler un problème » du frontend.

Le frontend appelle /api/support/diagnostic pour obtenir un blob texte
combinant : version RODIA, OS, taille flotte, dernier diagnostic, et
les N dernières lignes du fichier de log. Aucun envoi automatique :
le contenu est juste retourné au front qui l'inclut dans un mailto:
ou le copie dans le presse-papier.
"""
from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from flask import Blueprint, jsonify

from core.paths import DATA_DIR
from core.version import RODIA_VERSION
from core.variant import CLIENT_BUILD

bp = Blueprint("support", __name__, url_prefix="/api/support")

# Limite : on n'embarque pas tout le log (privacy + taille mailto:).
# 80 lignes ~= 8-12 Ko, large assez pour identifier le bug récent.
LOG_TAIL_LINES = 80


def _read_log_tail(log_path: str, n_lines: int = LOG_TAIL_LINES) -> str:
    """Retourne les N dernières lignes du log, ou '' si fichier absent/vide.

    Lecture en mode binaire pour gérer encodages mixtes (Windows produit
    parfois du cp1252 dans le log error). Décodage tolérant (errors=replace).
    """
    try:
        if not os.path.isfile(log_path):
            return ""
        with open(log_path, "rb") as f:
            # Lecture par chunk depuis la fin pour ne pas charger tout le fichier
            size = f.seek(0, 2)
            if size == 0:
                return ""
            chunk = min(size, 64 * 1024)  # max 64 Ko depuis la fin
            f.seek(size - chunk)
            data = f.read(chunk).decode("utf-8", errors="replace")
        lines = data.splitlines()
        return "\n".join(lines[-n_lines:])
    except Exception as exc:
        return f"[Lecture log impossible : {exc}]"


def _flotte_summary() -> dict:
    """Retourne un mini-résumé de la flotte (compte uniquement, pas de PII)."""
    try:
        from shared import fleet
        vehs = fleet.get_all_vehicles() or []
        last_date = ""
        for v in vehs:
            for h in (v.get("historique") or []):
                d = h.get("date") or ""
                if d > last_date:
                    last_date = d
        return {
            "vehicles_count": len(vehs),
            "last_diag_date": last_date,
        }
    except Exception:
        return {"vehicles_count": "?", "last_diag_date": "?"}


@bp.get("/diagnostic")
def support_diagnostic():
    """Renvoie un blob texte décrivant l'environnement, prêt à coller dans un mail.

    Réponse :
    {
        "report": "...texte multi-lignes...",
        "summary": {"version": "...", "os": "...", ...}
    }
    """
    summary = {
        "version":   RODIA_VERSION,
        "build":     "CLIENT" if CLIENT_BUILD else "DEV",
        "os":        f"{platform.system()} {platform.release()}",
        "python":    sys.version.split()[0],
        "frozen":    bool(getattr(sys, "frozen", False)),
        "data_dir":  str(DATA_DIR),
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    summary.update(_flotte_summary())

    log_path = os.path.join(str(DATA_DIR), "DiagnosticAuto_error.log")
    log_tail = _read_log_tail(log_path)

    # Format texte plain — directement lisible quand collé dans un mail
    lines = [
        "═══════════════════════════════════════",
        "  RODIA — Rapport système",
        "═══════════════════════════════════════",
        f"Version       : {summary['version']} ({summary['build']})",
        f"OS            : {summary['os']}",
        f"Python        : {summary['python']}",
        f"Mode          : {'frozen (PyInstaller)' if summary['frozen'] else 'développement'}",
        f"Date          : {summary['timestamp']}",
        f"Véhicules     : {summary.get('vehicles_count')}",
        f"Dernier diag  : {summary.get('last_diag_date') or '—'}",
        f"Dossier data  : {summary['data_dir']}",
        "",
    ]
    if log_tail:
        lines += [
            "─── Dernières lignes du log ───",
            log_tail,
            "─── Fin du log ───",
        ]
    else:
        lines.append("─── Aucun log d'erreur disponible ───")

    return jsonify({
        "report":  "\n".join(lines),
        "summary": summary,
    })


@bp.post("/erase-all")
def support_erase_all():
    """Zone de danger : efface flotte, configuration, et fichiers utilisateur.
    Requiert un appel POST explicite. Pas de paramètre = on efface tout.
    """
    erased = []
    errors = []

    targets = [
        os.path.join(str(DATA_DIR), "flotte.json"),
        os.path.join(str(DATA_DIR), "config.json"),
        os.path.join(str(DATA_DIR), "DiagnosticAuto_error.log"),
    ]
    for path in targets:
        try:
            if os.path.isfile(path):
                os.remove(path)
                erased.append(os.path.basename(path))
        except Exception as exc:
            errors.append(f"{os.path.basename(path)} : {exc}")

    # Recharge la flotte côté serveur (recrée un fichier vide)
    try:
        from shared import fleet
        if hasattr(fleet, "_load"):
            fleet._data = {"vehicules": [], "groupes": []}
            if hasattr(fleet, "_save"):
                fleet._save()
    except Exception as exc:
        errors.append(f"reset_fleet : {exc}")

    return jsonify({
        "ok":     not errors,
        "erased": erased,
        "errors": errors,
    })
