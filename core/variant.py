"""
Détection de la variante de build : interne (avec simulation) ou client (RODIA).

En build PyInstaller, on détecte la variante via la présence du fichier
'RODIA_CLIENT' dans sys._MEIPASS (bundlé uniquement dans RODIA.spec).
En développement, la variable d'environnement RODIA_CLIENT_BUILD=1 simule
un build client.
"""
import os
import sys


def is_client_build() -> bool:
    """Retourne True si c'est un build client RODIA (simulation désactivée)."""
    if getattr(sys, "frozen", False):
        # Fallback : en mode onedir _MEIPASS = _internal/, en onefile = tmp dir.
        # Si _MEIPASS absent (cas exotique), on cherche à côté de l'exe.
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        for candidate in (
            os.path.join(base, "RODIA_CLIENT"),
            os.path.join(os.path.dirname(sys.executable), "_internal", "RODIA_CLIENT"),
            os.path.join(os.path.dirname(sys.executable), "RODIA_CLIENT"),
        ):
            if os.path.isfile(candidate):
                return True
        return False
    return os.environ.get("RODIA_CLIENT_BUILD", "").lower() in ("1", "true", "yes")


def is_demo_build() -> bool:
    """Retourne True si on est en mode démonstration (simulation autorisée).

    Détecté via la variable d'env RODIA_DEMO_BUILD=1 (dev) ou la présence d'un
    fichier marqueur 'RODIA_DEMO' déposé par le lanceur du paquet démo, soit
    dans le dossier de données (%APPDATA%\\RODIA), soit à côté de l'exe.
    """
    if os.environ.get("RODIA_DEMO_BUILD", "").lower() in ("1", "true", "yes"):
        return True
    candidates = []
    try:
        from core.paths import DATA_DIR
        candidates.append(os.path.join(DATA_DIR, "RODIA_DEMO"))
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates += [
            os.path.join(base, "RODIA_DEMO"),
            os.path.join(os.path.dirname(sys.executable), "_internal", "RODIA_DEMO"),
            os.path.join(os.path.dirname(sys.executable), "RODIA_DEMO"),
        ]
    return any(os.path.isfile(c) for c in candidates)


# Constantes calculées une seule fois au démarrage
CLIENT_BUILD: bool = is_client_build()
DEMO_BUILD:   bool = is_demo_build()
# Client réel = build client SANS marqueur démo → simulation interdite
REAL_CLIENT:  bool = CLIENT_BUILD and not DEMO_BUILD
