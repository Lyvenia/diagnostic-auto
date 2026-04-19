"""Singletons partagés entre tous les blueprints Flask.

obd   → instance unique de OBDReader (connexion OBD2, DTC, temps réel)
fleet → instance unique de FleetManager (flotte.json)
"""
from hardware import OBDReader
from fleet.manager import FleetManager

obd   = OBDReader()
fleet = FleetManager()
