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
        marker = os.path.join(sys._MEIPASS, "RODIA_CLIENT")
        return os.path.isfile(marker)
    return os.environ.get("RODIA_CLIENT_BUILD", "").lower() in ("1", "true", "yes")


# Constante calculée une seule fois au démarrage
CLIENT_BUILD: bool = is_client_build()
