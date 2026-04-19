import json
import os
import random
from core.paths import data_path


def reset_simulation(self, forced_vin: str = None):
    """Reset simulation data. If forced_vin is given, use it instead of random."""
    self._sim_vin = forced_vin  # None = pick random, else lock to this VIN
    self._sim_dtc = None


def _simulate_vin(self):
    if self._sim_vin is None:
        vehicles = [
            "VF1RFD00X55000001",  # Renault Mégane
            "VF7KKFHXBEJ000002",  # Citroën C4
            "WBA3A5G59FNS00003",  # BMW Série 3
            "VF3CARHMF67000004",  # Peugeot 308
            "WVWZZZ3CZJE000005",  # Volkswagen Golf
            "VF1LM1B0H44000006",  # Renault Clio
            "WAUDZZF49KA000007",  # Audi A4
            "ZFANL2B14K3000008",  # Alfa Romeo Giulia
            "VF7UC9HP8EJ000009",  # Citroën Berlingo
            "W0L000051T2000010",  # Opel Astra
            "SAJWA0ES7EMV00011",  # Jaguar XF
            "WDDNG7BB0EA000012",  # Mercedes Classe E
            "SB1KW56F07E000013",  # Toyota Yaris
            "VF3GE9HPC8S000014",  # Peugeot 3008
            "TMBJP9NE0H0000015",  # Škoda Octavia
        ]
        # Exclure les VINs déjà dans la flotte pour éviter les doublons
        used = set(self._get_fleet_vins())
        available = [v for v in vehicles if v not in used]
        pool = available if available else vehicles
        self._sim_vin = random.choice(pool)
    return self._sim_vin


def _simulate_dtc(self):
    if self._sim_dtc is None:
        scenarios = [
            [],                              # Pas de panne (fréquent)
            [],
            [],
            ["P0171"],                       # Mélange pauvre banc 1
            ["P0300"],                       # Ratés d'allumage aléatoires
            ["P0420"],                       # Catalyseur inefficace
            ["P0128"],                       # Thermostat défaillant
            ["P0442"],                       # Fuite EVAP mineure
            ["P0401"],                       # Débit EGR insuffisant
            ["P0171", "P0174"],              # Mélange pauvre banc 1 et 2
            ["P0300", "P0301"],              # Ratés cylindre 1
            ["P0171", "P0300"],              # Multiple
        ]
        self._sim_dtc = random.choice(scenarios)
    return self._sim_dtc


def _simulate_realtime(self):
    return {
        "speed": random.randint(0, 130),
        "rpm": random.randint(700, 3800),
        "coolant_temp": random.randint(72, 108),
        "battery_voltage": round(random.uniform(12.1, 14.7), 1),
        "intake_pressure": random.randint(28, 101),
    }


def _get_fleet_vins(self):
    """Retourne la liste des VINs déjà dans la flotte."""
    try:
        fleet_file = data_path("flotte.json")
        if os.path.exists(fleet_file):
            with open(fleet_file, encoding="utf-8") as f:
                data = json.load(f)
            # flotte.json est un dict {VIN: vehicle_dict, ...}
            return list(data.keys())
    except Exception:
        pass
    return []
