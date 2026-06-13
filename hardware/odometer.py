"""Lecture du kilométrage via OBD2.

Phase 1 (implémentée) — PID standard 0xA6 (`obd.commands.ODOMETER`)
    Disponible sur les véhicules ~2019+ (obligatoire Euro 6d).
    Si supporté, lecture fiable. Sinon, retourne None et le frontend
    bascule sur la saisie manuelle.

Phase 2 (à venir) — Mode 22 constructeur (DIDs propriétaires)
    Pour les véhicules muets sur PID A6. Nécessite une table de mapping
    WMI → requêtes, à valider modèle par modèle sur la flotte réelle.

Format de retour de `read_odometer(self)` :
    {
        "km":         145320,           # entier, en kilomètres
        "source":     "obd_pid_a6",     # ou "simulation"
        "confidence": "high",           # high | medium | low
    }
    ou None si le véhicule ne répond pas.
"""
import random


def read_odometer(self):
    """Tentative de lecture du kilométrage via OBD2 PID 0xA6.

    Retourne dict ou None. Ne lève jamais d'exception : tout échec
    (PID non supporté, timeout, parsing) se traduit par un None propre.
    """
    # ── Simulation : retourne un km plausible et stable dans la session ──
    if self.simulation_mode:
        # Stocke un km simulé fixe par session pour ne pas que la valeur
        # change à chaque appel (sinon le garde-fou anti-décroissance déclenche).
        if not hasattr(self, "_sim_odometer") or self._sim_odometer is None:
            self._sim_odometer = random.randint(45_000, 195_000)
        return {
            "km":         self._sim_odometer,
            "source":     "simulation",
            "confidence": "high",
        }

    if not self.connection:
        return None

    # ── Lecture réelle via PID A6 ────────────────────────────────────
    try:
        import obd
    except ImportError:
        return None

    # Le PID ODOMETER a été ajouté à python-OBD 0.7+ — on vérifie sa présence
    # par sécurité (ne pas casser si la lib est plus vieille).
    cmd = getattr(obd.commands, "ODOMETER", None)
    if cmd is None:
        return None

    try:
        response = self.connection.query(cmd)
    except Exception:
        return None

    if response is None or response.is_null():
        return None

    # python-OBD renvoie typiquement un objet Pint (Quantity) avec unité km.
    # On extrait la magnitude et on arrondit à l'entier.
    try:
        val = response.value
        if hasattr(val, "to") and hasattr(val, "magnitude"):
            # Force en kilomètres au cas où l'unité serait différente
            km = int(round(float(val.to("kilometer").magnitude)))
        elif hasattr(val, "magnitude"):
            km = int(round(float(val.magnitude)))
        else:
            km = int(round(float(val)))
    except Exception:
        return None

    # Garde-fou : un km négatif ou aberrant (> 2 millions) → on rejette
    if km < 0 or km > 2_000_000:
        return None

    return {
        "km":         km,
        "source":     "obd_pid_a6",
        "confidence": "high",
    }
