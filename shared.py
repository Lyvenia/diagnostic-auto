"""
Singletons partagés entre app.py et les blueprints API.
Importé une seule fois — évite de créer plusieurs instances.
"""
import atexit

from hardware import OBDReader
from fleet.manager import FleetManager

obd   = OBDReader()
fleet = FleetManager()

# Garantit que les données en mémoire sont bien écrites sur disque à l'arrêt
atexit.register(fleet.flush)
