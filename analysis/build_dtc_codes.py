"""
Générateur de la base DTC locale (analysis/dtc_codes.json).

Ce script est lancé manuellement (ou via CI) pour produire le JSON bundlé.
Il définit les codes par patterns (boucles) ou explicitement, avec leurs
métadonnées : libellé FR, family, severity, vehicles, mil.

Pour ajouter/corriger des codes : éditer ce fichier puis exécuter
    python analysis/build_dtc_codes.py
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "dtc_codes.json")

# Toutes essence + diesel (cas par défaut)
ALL_THERM = ["essence", "diesel"]
ESSENCE   = ["essence"]
DIESEL    = ["diesel"]
HYBRIDE   = ["hybride"]
ELECTRIQUE = ["electrique"]
THERM_HYB = ["essence", "diesel", "hybride"]
ALL_VEH   = ["essence", "diesel", "hybride", "electrique"]

CODES: dict[str, dict] = {}

def add(code: str, fr: str, family: str, severity: str = "warn",
        vehicles=None, mil: bool = True):
    """Enregistre un code DTC."""
    if vehicles is None:
        vehicles = ALL_THERM
    CODES[code] = {
        "fr": fr,
        "family": family,
        "severity": severity,
        "vehicles": vehicles,
        "mil": mil,
    }

# ════════════════════════════════════════════════════════════════════════════
#  FAMILLES (libellés humains, sert pour l'affichage groupé dans le rapport)
# ════════════════════════════════════════════════════════════════════════════
FAMILIES = {
    "moteur_carburant_air":            "Moteur — mélange air / carburant (MAF, MAP, TPS, mélanges)",
    "moteur_allumage_rates":           "Moteur — allumage et ratés d'allumage",
    "moteur_injection_hp":             "Moteur — injection haute pression / rampe / injecteurs",
    "moteur_distribution":             "Moteur — distribution (arbre à cames, vilebrequin, calage)",
    "moteur_lubrification_temperature":"Moteur — refroidissement et lubrification",
    "antipollution_egr":               "Antipollution — recirculation gaz d'échappement (EGR)",
    "antipollution_fap_dpf":           "Antipollution — filtre à particules (FAP / DPF)",
    "antipollution_scr_adblue":        "Antipollution — SCR / AdBlue (réduction NOx diesel)",
    "antipollution_nox":               "Antipollution — capteurs NOx",
    "antipollution_evap":              "Antipollution — vapeurs essence (EVAP)",
    "antipollution_catalyseur":        "Antipollution — catalyseur d'oxydation",
    "antipollution_lambda":            "Antipollution — sondes lambda (O2)",
    "antipollution_air_secondaire":    "Antipollution — injection air secondaire",
    "turbo_suralimentation":           "Suralimentation — turbo, géométrie variable, intercooler",
    "prechauffage_diesel":             "Préchauffage diesel — bougies, module",
    "transmission_boite":              "Transmission — boîte de vitesses / convertisseur",
    "transmission_embrayage":          "Transmission — embrayage / double embrayage",
    "freinage_abs":                    "Freinage — ABS / capteurs roue",
    "esp_stabilite_traction":          "ESP — stabilité / antipatinage",
    "direction_assistee":              "Direction assistée",
    "climatisation_chauffage":         "Climatisation / chauffage habitacle",
    "carrosserie_eclairage_confort":   "Carrosserie — éclairage / confort",
    "electronique_ecm_pcm":            "Électronique — calculateur moteur (ECM/PCM)",
    "electronique_reseau_can":         "Électronique — réseau CAN / communication",
    "electronique_alimentation":       "Électronique — alimentation / batterie 12 V",
    "securite_airbags":                "Sécurité — airbags et prétensionneurs",
    "hybride_batterie_hv":             "Hybride — batterie haute tension",
    "hybride_moteur_electrique":       "Hybride — moteur électrique / générateur",
    "hybride_recuperation_freinage":   "Hybride — récupération au freinage",
    "electrique_bms":                  "Électrique — gestion batterie (BMS)",
    "electrique_charge":               "Électrique — système de charge (AC/DC)",
    "electrique_inverter":             "Électrique — onduleur / convertisseur DC-DC",
    "non_classe":                      "Non classé / informationnel",
}

# ════════════════════════════════════════════════════════════════════════════
#  P00xx — ALIMENTATION CARBURANT / AIR : fuel system circuit problems
# ════════════════════════════════════════════════════════════════════════════
add("P0001", "Régulateur volume carburant — circuit ouvert", "moteur_injection_hp")
add("P0002", "Régulateur volume carburant — plage/performance", "moteur_injection_hp")
add("P0003", "Régulateur volume carburant — circuit bas", "moteur_injection_hp")
add("P0004", "Régulateur volume carburant — circuit haut", "moteur_injection_hp")
add("P0005", "Vanne d'arrêt carburant — circuit ouvert", "moteur_injection_hp", vehicles=DIESEL)
add("P0006", "Vanne d'arrêt carburant — circuit bas", "moteur_injection_hp", vehicles=DIESEL)
add("P0007", "Vanne d'arrêt carburant — circuit haut", "moteur_injection_hp", vehicles=DIESEL)
add("P0008", "Synchronisation moteur banc 1 — performance", "moteur_distribution")
add("P0009", "Synchronisation moteur banc 2 — performance", "moteur_distribution")
add("P000A", "Position arbre à cames admission banc 1 — réponse lente", "moteur_distribution")
add("P000B", "Position arbre à cames échappement banc 1 — réponse lente", "moteur_distribution")
add("P000C", "Position arbre à cames admission banc 2 — réponse lente", "moteur_distribution")
add("P000D", "Position arbre à cames échappement banc 2 — réponse lente", "moteur_distribution")
add("P0010", "Actionneur position AAC admission banc 1 — circuit", "moteur_distribution")
add("P0011", "Position AAC admission banc 1 — performance/calage", "moteur_distribution")
add("P0012", "Position AAC admission banc 1 — retardée", "moteur_distribution")
add("P0013", "Actionneur position AAC échappement banc 1 — circuit", "moteur_distribution")
add("P0014", "Position AAC échappement banc 1 — performance/calage", "moteur_distribution")
add("P0015", "Position AAC échappement banc 1 — retardée", "moteur_distribution")
add("P0016", "Corrélation vilebrequin / AAC admission banc 1", "moteur_distribution", "critical")
add("P0017", "Corrélation vilebrequin / AAC échappement banc 1", "moteur_distribution", "critical")
add("P0018", "Corrélation vilebrequin / AAC admission banc 2", "moteur_distribution", "critical")
add("P0019", "Corrélation vilebrequin / AAC échappement banc 2", "moteur_distribution", "critical")
add("P0020", "Actionneur AAC admission banc 2 — circuit", "moteur_distribution")
add("P0021", "Position AAC admission banc 2 — performance/calage", "moteur_distribution")
add("P0022", "Position AAC admission banc 2 — retardée", "moteur_distribution")
add("P0023", "Actionneur AAC échappement banc 2 — circuit", "moteur_distribution")
add("P0024", "Position AAC échappement banc 2 — performance/calage", "moteur_distribution")
add("P0025", "Position AAC échappement banc 2 — retardée", "moteur_distribution")
add("P0030", "Chauffage sonde lambda banc 1 capteur 1 — circuit", "antipollution_lambda")
add("P0031", "Chauffage sonde lambda banc 1 capteur 1 — circuit bas", "antipollution_lambda")
add("P0032", "Chauffage sonde lambda banc 1 capteur 1 — circuit haut", "antipollution_lambda")
add("P0036", "Chauffage sonde lambda banc 1 capteur 2 — circuit", "antipollution_lambda")
add("P0037", "Chauffage sonde lambda banc 1 capteur 2 — circuit bas", "antipollution_lambda")
add("P0038", "Chauffage sonde lambda banc 1 capteur 2 — circuit haut", "antipollution_lambda")
add("P0050", "Chauffage sonde lambda banc 2 capteur 1 — circuit", "antipollution_lambda")
add("P0051", "Chauffage sonde lambda banc 2 capteur 1 — circuit bas", "antipollution_lambda")
add("P0052", "Chauffage sonde lambda banc 2 capteur 1 — circuit haut", "antipollution_lambda")
add("P0056", "Chauffage sonde lambda banc 2 capteur 2 — circuit", "antipollution_lambda")
add("P0060", "Chauffage sonde lambda banc 2 capteur 2 — résistance hors plage", "antipollution_lambda")
add("P0068", "MAP / Débit MAF — corrélation incohérente avec position papillon", "moteur_carburant_air")
add("P0069", "Pression atmosphérique / MAP — corrélation", "moteur_carburant_air")
add("P0070", "Capteur température ambiante — circuit", "electronique_ecm_pcm", "info")
add("P0071", "Capteur température ambiante — performance", "electronique_ecm_pcm", "info")
add("P0072", "Capteur température ambiante — circuit bas", "electronique_ecm_pcm", "info")
add("P0073", "Capteur température ambiante — circuit haut", "electronique_ecm_pcm", "info")
add("P0087", "Pression rampe HP / système — pression trop basse", "moteur_injection_hp", "critical", vehicles=DIESEL)
add("P0088", "Pression rampe HP / système — pression trop haute", "moteur_injection_hp", "critical", vehicles=DIESEL)
add("P0089", "Régulateur pression carburant — performance", "moteur_injection_hp", "warn", vehicles=DIESEL)
add("P0090", "Régulateur pression carburant — circuit", "moteur_injection_hp", vehicles=DIESEL)
add("P0091", "Régulateur pression carburant 1 — circuit bas", "moteur_injection_hp", vehicles=DIESEL)
add("P0092", "Régulateur pression carburant 1 — circuit haut", "moteur_injection_hp", vehicles=DIESEL)
add("P0093", "Fuite système carburant — grosse fuite détectée", "moteur_injection_hp", "critical")
add("P0094", "Fuite système carburant — petite fuite détectée", "moteur_injection_hp")
add("P0095", "Capteur température air admission 2 — circuit", "moteur_carburant_air")
add("P0097", "Capteur température air admission 2 — circuit bas", "moteur_carburant_air")
add("P0098", "Capteur température air admission 2 — circuit haut", "moteur_carburant_air")

# ════════════════════════════════════════════════════════════════════════════
#  P01xx — MÉLANGE AIR / CARBURANT : MAF, MAP, IAT, TPS, mélanges, lambdas
# ════════════════════════════════════════════════════════════════════════════
add("P0100", "Débitmètre MAF — circuit défaillant", "moteur_carburant_air")
add("P0101", "Débitmètre MAF — plage/performance", "moteur_carburant_air")
add("P0102", "Débitmètre MAF — circuit bas", "moteur_carburant_air")
add("P0103", "Débitmètre MAF — circuit haut", "moteur_carburant_air")
add("P0104", "Débitmètre MAF — circuit intermittent", "moteur_carburant_air")
add("P0105", "Capteur pression admission (MAP) — circuit", "moteur_carburant_air")
add("P0106", "Capteur MAP — plage/performance", "moteur_carburant_air")
add("P0107", "Capteur MAP — circuit bas", "moteur_carburant_air")
add("P0108", "Capteur MAP — circuit haut", "moteur_carburant_air")
add("P0109", "Capteur MAP — circuit intermittent", "moteur_carburant_air")
add("P0110", "Capteur température air admission — circuit", "moteur_carburant_air")
add("P0111", "Capteur température air admission — plage/performance", "moteur_carburant_air")
add("P0112", "Capteur température air admission — circuit bas", "moteur_carburant_air")
add("P0113", "Capteur température air admission — circuit haut", "moteur_carburant_air")
add("P0114", "Capteur température air admission — circuit intermittent", "moteur_carburant_air")
add("P0115", "Capteur température liquide refroidissement — circuit", "moteur_lubrification_temperature", vehicles=THERM_HYB)
add("P0116", "Capteur température liquide refroidissement — plage/performance", "moteur_lubrification_temperature", vehicles=THERM_HYB)
add("P0117", "Capteur température liquide refroidissement — circuit bas", "moteur_lubrification_temperature", vehicles=THERM_HYB)
add("P0118", "Capteur température liquide refroidissement — circuit haut", "moteur_lubrification_temperature", vehicles=THERM_HYB)
add("P0119", "Capteur température liquide refroidissement — circuit intermittent", "moteur_lubrification_temperature", vehicles=THERM_HYB)
add("P0120", "Capteur position papillon (TPS) A — circuit", "moteur_carburant_air")
add("P0121", "TPS A — plage/performance", "moteur_carburant_air")
add("P0122", "TPS A — circuit bas", "moteur_carburant_air")
add("P0123", "TPS A — circuit haut", "moteur_carburant_air")
add("P0124", "TPS A — circuit intermittent", "moteur_carburant_air")
add("P0125", "Température liquide refroidissement insuffisante pour boucle fermée", "moteur_lubrification_temperature")
add("P0126", "Température liquide refroidissement insuffisante", "moteur_lubrification_temperature")
add("P0127", "Température air admission trop haute", "moteur_carburant_air")
add("P0128", "Thermostat — température sous régulation thermostatique", "moteur_lubrification_temperature")
# Sondes lambda P0130-P0167 (banc 1/2, capteur 1/2/3/4) — patterns
LAMBDA_LABELS = {
    0: "Sonde lambda — circuit",
    1: "Sonde lambda — défaut amplitude/courant",
    2: "Sonde lambda — basse tension",
    3: "Sonde lambda — haute tension",
    4: "Sonde lambda — réponse lente",
    5: "Sonde lambda — pas de réponse",
    6: "Chauffage sonde lambda — circuit",
    7: "Chauffage sonde lambda — bas/haut",
    8: "Chauffage sonde lambda — performance",
    9: "Sonde lambda — circuit intermittent",
}
# P0130-P0159 : banc 1 capteur 1-2-3-4 puis banc 2 capteur 1-2-3-4
LAMBDA_POS = [
    (0x130, "amont banc 1"),
    (0x136, "aval banc 1"),
    (0x13C, "banc 1 capteur 3"),
    (0x142, "banc 1 capteur 4"),
    (0x150, "amont banc 2"),
    (0x156, "aval banc 2"),
    (0x15C, "banc 2 capteur 3"),
    (0x162, "banc 2 capteur 4"),
]
for base, label in LAMBDA_POS:
    for offset, suffix in [(0, "circuit"), (1, "amplitude/courant"),
                           (2, "basse tension"), (3, "haute tension"),
                           (4, "réponse lente"), (5, "pas de réponse")]:
        code = f"P0{base+offset:03X}"
        add(code, f"Sonde lambda {label} — {suffix}", "antipollution_lambda")

add("P0170", "Mélange carburant banc 1 — défaut", "moteur_carburant_air", vehicles=ESSENCE)
add("P0171", "Mélange appauvri banc 1 — correction max atteinte", "moteur_carburant_air", vehicles=ESSENCE)
add("P0172", "Mélange enrichi banc 1 — correction max atteinte", "moteur_carburant_air", vehicles=ESSENCE)
add("P0173", "Mélange carburant banc 2 — défaut", "moteur_carburant_air", vehicles=ESSENCE)
add("P0174", "Mélange appauvri banc 2 — correction max atteinte", "moteur_carburant_air", vehicles=ESSENCE)
add("P0175", "Mélange enrichi banc 2 — correction max atteinte", "moteur_carburant_air", vehicles=ESSENCE)
add("P0176", "Capteur composition carburant — circuit", "moteur_injection_hp")
add("P0180", "Capteur température carburant A — circuit", "moteur_injection_hp")
add("P0181", "Capteur température carburant A — plage/performance", "moteur_injection_hp")
add("P0182", "Capteur température carburant A — circuit bas", "moteur_injection_hp")
add("P0183", "Capteur température carburant A — circuit haut", "moteur_injection_hp")
add("P0190", "Capteur pression rampe carburant — circuit", "moteur_injection_hp", "critical", vehicles=DIESEL)
add("P0191", "Capteur pression rampe — plage/performance", "moteur_injection_hp", vehicles=DIESEL)
add("P0192", "Capteur pression rampe — circuit bas", "moteur_injection_hp", vehicles=DIESEL)
add("P0193", "Capteur pression rampe — circuit haut", "moteur_injection_hp", vehicles=DIESEL)
add("P0194", "Capteur pression rampe — circuit intermittent", "moteur_injection_hp", vehicles=DIESEL)
add("P0195", "Capteur température huile moteur — circuit", "moteur_lubrification_temperature")
add("P0196", "Capteur température huile moteur — plage/performance", "moteur_lubrification_temperature")
add("P0197", "Capteur température huile moteur — circuit bas", "moteur_lubrification_temperature")
add("P0198", "Capteur température huile moteur — circuit haut", "moteur_lubrification_temperature")

# ════════════════════════════════════════════════════════════════════════════
#  P02xx — INJECTEURS et fuel metering
# ════════════════════════════════════════════════════════════════════════════
add("P0200", "Circuit injecteur — défaut général", "moteur_injection_hp")
# Injecteurs par cylindre 1-12 : P0201-P020C
for cyl in range(1, 13):
    code = f"P02{cyl:02X}" if cyl > 9 else f"P020{cyl}"
    if cyl <= 9:
        code = f"P020{cyl}"
    elif cyl == 10:
        code = "P020A"
    elif cyl == 11:
        code = "P020B"
    elif cyl == 12:
        code = "P020C"
    add(code, f"Injecteur cylindre {cyl} — circuit", "moteur_injection_hp")

add("P0217", "Surchauffe moteur", "moteur_lubrification_temperature", "critical")
add("P0218", "Surchauffe boîte de vitesses", "transmission_boite", "critical")
add("P0219", "Sur-régime moteur", "electronique_ecm_pcm", "warn")
add("P0220", "TPS B — circuit", "moteur_carburant_air")
add("P0221", "TPS B — plage/performance", "moteur_carburant_air")
add("P0222", "TPS B — circuit bas", "moteur_carburant_air")
add("P0223", "TPS B — circuit haut", "moteur_carburant_air")
add("P0230", "Pompe carburant primaire — circuit", "moteur_injection_hp", "critical")
add("P0231", "Pompe carburant secondaire — circuit bas", "moteur_injection_hp")
add("P0232", "Pompe carburant secondaire — circuit haut", "moteur_injection_hp")
add("P0234", "Turbocompresseur — surpression (overboost)", "turbo_suralimentation", "critical")
add("P0235", "Capteur pression suralimentation A — circuit", "turbo_suralimentation")
add("P0236", "Capteur pression suralimentation A — plage/performance", "turbo_suralimentation")
add("P0237", "Capteur pression suralimentation A — circuit bas", "turbo_suralimentation")
add("P0238", "Capteur pression suralimentation A — circuit haut", "turbo_suralimentation")
add("P0240", "Capteur pression suralimentation B — plage/performance", "turbo_suralimentation")
add("P0243", "Solénoïde wastegate turbo A — circuit", "turbo_suralimentation")
add("P0245", "Solénoïde wastegate turbo A — circuit bas", "turbo_suralimentation")
add("P0246", "Solénoïde wastegate turbo A — circuit haut", "turbo_suralimentation")
add("P0247", "Solénoïde wastegate turbo B — circuit", "turbo_suralimentation")
add("P0248", "Solénoïde wastegate turbo B — circuit bas", "turbo_suralimentation")
add("P0249", "Solénoïde wastegate turbo B — circuit haut", "turbo_suralimentation")
add("P0261", "Cylindre 1 — injecteur circuit bas", "moteur_injection_hp")
add("P0262", "Cylindre 1 — injecteur circuit haut", "moteur_injection_hp")
add("P0264", "Cylindre 2 — injecteur circuit bas", "moteur_injection_hp")
add("P0265", "Cylindre 2 — injecteur circuit haut", "moteur_injection_hp")
add("P0267", "Cylindre 3 — injecteur circuit bas", "moteur_injection_hp")
add("P0268", "Cylindre 3 — injecteur circuit haut", "moteur_injection_hp")
add("P0270", "Cylindre 4 — injecteur circuit bas", "moteur_injection_hp")
add("P0271", "Cylindre 4 — injecteur circuit haut", "moteur_injection_hp")
add("P0299", "Turbocompresseur — sous-pression (underboost)", "turbo_suralimentation", "critical")

# ════════════════════════════════════════════════════════════════════════════
#  P03xx — ALLUMAGE / RATÉS / CAPTEURS ROTATION
# ════════════════════════════════════════════════════════════════════════════
add("P0300", "Ratés d'allumage aléatoires — plusieurs cylindres", "moteur_allumage_rates", "critical")
for cyl in range(1, 13):
    if cyl <= 9:
        code = f"P030{cyl}"
    elif cyl == 10:
        code = "P030A"
    elif cyl == 11:
        code = "P030B"
    elif cyl == 12:
        code = "P030C"
    add(code, f"Ratés d'allumage — cylindre {cyl}", "moteur_allumage_rates")

add("P0313", "Ratés d'allumage — niveau carburant bas", "moteur_allumage_rates", "info")
add("P0315", "Position vilebrequin — non apprise", "moteur_distribution")
add("P0316", "Ratés d'allumage détectés au démarrage", "moteur_allumage_rates")
add("P0320", "Capteur RPM / position d'allumage — circuit", "moteur_distribution")
add("P0321", "Capteur RPM — plage/performance", "moteur_distribution")
add("P0322", "Capteur RPM — pas de signal", "moteur_distribution", "critical")
add("P0325", "Capteur cliquetis 1 — circuit", "moteur_allumage_rates", vehicles=ESSENCE)
add("P0326", "Capteur cliquetis 1 — plage/performance", "moteur_allumage_rates", vehicles=ESSENCE)
add("P0327", "Capteur cliquetis 1 — circuit bas", "moteur_allumage_rates", vehicles=ESSENCE)
add("P0328", "Capteur cliquetis 1 — circuit haut", "moteur_allumage_rates", vehicles=ESSENCE)
add("P0330", "Capteur cliquetis 2 — circuit", "moteur_allumage_rates", vehicles=ESSENCE)
add("P0335", "Capteur position vilebrequin A — circuit", "moteur_distribution", "critical")
add("P0336", "Capteur vilebrequin A — plage/performance", "moteur_distribution")
add("P0337", "Capteur vilebrequin A — circuit bas", "moteur_distribution")
add("P0338", "Capteur vilebrequin A — circuit haut", "moteur_distribution")
add("P0339", "Capteur vilebrequin A — circuit intermittent", "moteur_distribution")
add("P0340", "Capteur position AAC A banc 1 — circuit", "moteur_distribution")
add("P0341", "Capteur AAC A banc 1 — plage/performance", "moteur_distribution")
add("P0342", "Capteur AAC A banc 1 — circuit bas", "moteur_distribution")
add("P0343", "Capteur AAC A banc 1 — circuit haut", "moteur_distribution")
add("P0344", "Capteur AAC A banc 1 — circuit intermittent", "moteur_distribution")
add("P0345", "Capteur AAC A banc 2 — circuit", "moteur_distribution")
add("P0346", "Capteur AAC A banc 2 — plage/performance", "moteur_distribution")
# Bobines d'allumage par cylindre P0350-P0362 (essence)
for cyl in range(1, 13):
    code = f"P035{cyl-1:01X}" if cyl <= 10 else (f"P036{cyl-11}" if cyl <= 12 else None)
    if cyl <= 9:
        code = f"P035{cyl}"
    elif cyl == 10:
        code = "P035A"  # certains constructeurs
    elif cyl == 11:
        code = "P0361"
    elif cyl == 12:
        code = "P0362"
    add(code, f"Bobine d'allumage cylindre {cyl} — primaire/secondaire", "moteur_allumage_rates", vehicles=ESSENCE)

add("P0365", "Capteur AAC B banc 1 — circuit", "moteur_distribution")
add("P0366", "Capteur AAC B banc 1 — plage/performance", "moteur_distribution")
add("P0370", "Signal référence de calage A — performance", "moteur_distribution")

# ════════════════════════════════════════════════════════════════════════════
#  P04xx — ANTIPOLLUTION : EGR, EVAP, catalyseur, air secondaire
# ════════════════════════════════════════════════════════════════════════════
add("P0400", "Recyclage gaz d'échappement (EGR) — débit", "antipollution_egr")
add("P0401", "Débit EGR insuffisant détecté", "antipollution_egr")
add("P0402", "Débit EGR excessif détecté", "antipollution_egr")
add("P0403", "EGR — circuit défaillant", "antipollution_egr")
add("P0404", "EGR — plage/performance circuit ouvert", "antipollution_egr")
add("P0405", "Capteur position EGR A — circuit bas", "antipollution_egr")
add("P0406", "Capteur position EGR A — circuit haut", "antipollution_egr")
add("P0407", "Capteur position EGR B — circuit bas", "antipollution_egr")
add("P0408", "Capteur position EGR B — circuit haut", "antipollution_egr")
add("P0409", "Capteur EGR A — circuit", "antipollution_egr")
add("P040A", "Capteur température EGR — circuit", "antipollution_egr")
add("P040B", "Capteur température EGR — performance", "antipollution_egr")
add("P040C", "Capteur température EGR A — circuit bas", "antipollution_egr")
add("P040D", "Capteur température EGR A — circuit haut", "antipollution_egr")
add("P040E", "Capteur température EGR B — circuit bas", "antipollution_egr")
add("P040F", "Capteur température EGR B — circuit haut", "antipollution_egr")
add("P0410", "Système air secondaire — défaut", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0411", "Air secondaire — débit insuffisant détecté", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0412", "Air secondaire vanne A — circuit", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0413", "Air secondaire vanne A — circuit ouvert", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0414", "Air secondaire vanne A — circuit court", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0418", "Air secondaire relais A — circuit", "antipollution_air_secondaire", vehicles=ESSENCE)
add("P0420", "Catalyseur banc 1 — efficacité insuffisante", "antipollution_catalyseur", "critical", vehicles=ESSENCE)
add("P0421", "Catalyseur banc 1 — efficacité chauffe insuffisante", "antipollution_catalyseur", vehicles=ESSENCE)
add("P0422", "Catalyseur principal banc 1 — efficacité insuffisante", "antipollution_catalyseur", "critical", vehicles=ESSENCE)
add("P0423", "Catalyseur chauffé banc 1 — efficacité", "antipollution_catalyseur", vehicles=ESSENCE)
add("P0424", "Catalyseur chauffé banc 1 — température basse", "antipollution_catalyseur", vehicles=ESSENCE)
add("P0430", "Catalyseur banc 2 — efficacité insuffisante", "antipollution_catalyseur", "critical", vehicles=ESSENCE)
add("P0431", "Catalyseur banc 2 — efficacité chauffe insuffisante", "antipollution_catalyseur", vehicles=ESSENCE)
add("P0432", "Catalyseur principal banc 2 — efficacité insuffisante", "antipollution_catalyseur", "critical", vehicles=ESSENCE)
add("P0440", "Système EVAP — défaut général", "antipollution_evap", vehicles=ESSENCE)
add("P0441", "EVAP — débit purge incorrect", "antipollution_evap", vehicles=ESSENCE)
add("P0442", "EVAP — petite fuite détectée", "antipollution_evap", vehicles=ESSENCE)
add("P0443", "EVAP — vanne purge — circuit", "antipollution_evap", vehicles=ESSENCE)
add("P0444", "EVAP — vanne purge — circuit ouvert", "antipollution_evap", vehicles=ESSENCE)
add("P0445", "EVAP — vanne purge — circuit court", "antipollution_evap", vehicles=ESSENCE)
add("P0446", "EVAP — circuit contrôle ventilation", "antipollution_evap", vehicles=ESSENCE)
add("P0447", "EVAP — ventilation — circuit ouvert", "antipollution_evap", vehicles=ESSENCE)
add("P0448", "EVAP — ventilation — circuit court", "antipollution_evap", vehicles=ESSENCE)
add("P0449", "EVAP — vanne ventilation — circuit", "antipollution_evap", vehicles=ESSENCE)
add("P0450", "EVAP — capteur pression — circuit", "antipollution_evap", vehicles=ESSENCE)
add("P0451", "EVAP — capteur pression — plage/performance", "antipollution_evap", vehicles=ESSENCE)
add("P0452", "EVAP — capteur pression — circuit bas", "antipollution_evap", vehicles=ESSENCE)
add("P0453", "EVAP — capteur pression — circuit haut", "antipollution_evap", vehicles=ESSENCE)
add("P0455", "EVAP — grosse fuite détectée", "antipollution_evap", "critical", vehicles=ESSENCE)
add("P0456", "EVAP — très petite fuite détectée", "antipollution_evap", vehicles=ESSENCE)
add("P0457", "EVAP — fuite (bouchon réservoir détaché ?)", "antipollution_evap", vehicles=ESSENCE)
add("P0461", "Capteur niveau carburant A — plage/performance", "moteur_injection_hp", "info")
add("P0462", "Capteur niveau carburant A — circuit bas", "moteur_injection_hp", "info")
add("P0463", "Capteur niveau carburant A — circuit haut", "moteur_injection_hp", "info")
add("P0470", "Capteur pression échappement — circuit", "moteur_carburant_air")
add("P0471", "Capteur pression échappement — plage/performance", "moteur_carburant_air")
add("P0480", "Relais ventilateur refroidissement 1 — circuit", "moteur_lubrification_temperature")
add("P0481", "Relais ventilateur refroidissement 2 — circuit", "moteur_lubrification_temperature")
add("P0488", "EGR — vanne papillon position — plage/performance", "antipollution_egr")
add("P0489", "EGR — circuit bas A", "antipollution_egr")
add("P048A", "EGR refroidisseur — défaut performance", "antipollution_egr", vehicles=DIESEL)

# ════════════════════════════════════════════════════════════════════════════
#  P05xx — Vitesse véhicule, régulateur, ralenti
# ════════════════════════════════════════════════════════════════════════════
add("P0500", "Capteur vitesse véhicule — circuit", "electronique_ecm_pcm")
add("P0501", "Capteur vitesse véhicule — plage/performance", "electronique_ecm_pcm")
add("P0502", "Capteur vitesse véhicule — circuit bas", "electronique_ecm_pcm")
add("P0503", "Capteur vitesse véhicule — circuit intermittent", "electronique_ecm_pcm")
add("P0505", "Régulation ralenti — défaut", "moteur_carburant_air")
add("P0506", "Régulation ralenti — régime trop bas", "moteur_carburant_air")
add("P0507", "Régulation ralenti — régime trop haut", "moteur_carburant_air")
add("P0508", "Régulation ralenti — circuit bas", "moteur_carburant_air")
add("P0509", "Régulation ralenti — circuit haut", "moteur_carburant_air")
add("P0511", "Vanne IAC — circuit", "moteur_carburant_air")
add("P0520", "Capteur pression huile moteur — circuit", "moteur_lubrification_temperature", "critical")
add("P0521", "Capteur pression huile — plage/performance", "moteur_lubrification_temperature", "critical")
add("P0522", "Capteur pression huile — tension basse", "moteur_lubrification_temperature", "critical")
add("P0523", "Capteur pression huile — tension haute", "moteur_lubrification_temperature", "critical")
add("P0524", "Pression huile moteur trop basse", "moteur_lubrification_temperature", "critical")
add("P0532", "Capteur pression climatisation — circuit bas", "climatisation_chauffage", "info")
add("P0533", "Capteur pression climatisation — circuit haut", "climatisation_chauffage", "info")
add("P0560", "Tension système électrique — circuit", "electronique_alimentation")
add("P0562", "Tension système — basse", "electronique_alimentation")
add("P0563", "Tension système — haute", "electronique_alimentation")
add("P0571", "Contacteur de frein A — circuit", "freinage_abs")
add("P0579", "Régulateur de vitesse — circuit", "electronique_ecm_pcm")
add("P0590", "Régulateur de vitesse — interrupteur ON — circuit", "electronique_ecm_pcm")

# ════════════════════════════════════════════════════════════════════════════
#  P06xx — CALCULATEUR ECM/PCM
# ════════════════════════════════════════════════════════════════════════════
add("P0600", "Communication CAN bus série — défaut", "electronique_reseau_can", "critical")
add("P0601", "ECM/PCM — erreur de checksum mémoire", "electronique_ecm_pcm", "critical")
add("P0602", "ECM/PCM — erreur de programmation", "electronique_ecm_pcm", "critical")
add("P0603", "ECM/PCM — erreur mémoire RAM (KAM)", "electronique_ecm_pcm")
add("P0604", "ECM/PCM — erreur mémoire RAM interne", "electronique_ecm_pcm")
add("P0605", "ECM/PCM — erreur mémoire ROM interne", "electronique_ecm_pcm")
add("P0606", "ECM/PCM — défaut processeur", "electronique_ecm_pcm", "critical")
add("P0607", "ECM/PCM — performance module", "electronique_ecm_pcm")
add("P0608", "ECM/PCM — module VSS A — sortie", "electronique_ecm_pcm")
add("P060A", "ECM/PCM — module surveillance interne — performance", "electronique_ecm_pcm")
add("P060B", "ECM/PCM — convertisseur A/N — performance", "electronique_ecm_pcm")
add("P062F", "ECM/PCM — erreur EEPROM interne", "electronique_ecm_pcm", "critical")
add("P0641", "Référence tension capteur A — circuit ouvert", "electronique_ecm_pcm")
add("P0651", "Référence tension capteur B — circuit ouvert", "electronique_ecm_pcm")
add("P0670", "Module bougies préchauffage — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0671", "Bougie préchauffage cylindre 1 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0672", "Bougie préchauffage cylindre 2 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0673", "Bougie préchauffage cylindre 3 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0674", "Bougie préchauffage cylindre 4 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0675", "Bougie préchauffage cylindre 5 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0676", "Bougie préchauffage cylindre 6 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0677", "Bougie préchauffage cylindre 7 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0678", "Bougie préchauffage cylindre 8 — circuit", "prechauffage_diesel", vehicles=DIESEL)
add("P0683", "Bougies préchauffage — communication PCM", "prechauffage_diesel", vehicles=DIESEL)
add("P0685", "ECM/PCM — relais alimentation — circuit", "electronique_alimentation")
add("P0686", "ECM/PCM — relais alimentation — circuit bas", "electronique_alimentation")
add("P0687", "ECM/PCM — relais alimentation — circuit haut", "electronique_alimentation")
add("P0689", "ECM/PCM — relais alimentation — performance", "electronique_alimentation")

# ════════════════════════════════════════════════════════════════════════════
#  P07xx — TRANSMISSION (boîte de vitesses) — MIL souvent OFF (voyant séparé)
# ════════════════════════════════════════════════════════════════════════════
add("P0700", "Système contrôle BV — défaut", "transmission_boite", mil=False, vehicles=THERM_HYB)
add("P0701", "BV — plage/performance", "transmission_boite", mil=False, vehicles=THERM_HYB)
add("P0702", "BV — circuit électrique", "transmission_boite", mil=False, vehicles=THERM_HYB)
add("P0703", "Contacteur de frein B — circuit", "freinage_abs", mil=False)
add("P0705", "Capteur position levier (PRNDL) — circuit", "transmission_boite", mil=False)
add("P0706", "Capteur position levier — plage/performance", "transmission_boite", mil=False)
add("P0710", "Capteur température ATF (huile BV) — circuit", "transmission_boite", mil=False)
add("P0715", "Capteur vitesse entrée turbine — circuit", "transmission_boite", mil=False)
add("P0720", "Capteur vitesse sortie BV — circuit", "transmission_boite", mil=False)
add("P0725", "Capteur régime moteur — circuit BV", "transmission_boite", mil=False)
add("P0730", "Mauvais rapport de boîte", "transmission_boite", "warn", mil=False)
add("P0731", "Mauvais rapport — vitesse 1", "transmission_boite", mil=False)
add("P0732", "Mauvais rapport — vitesse 2", "transmission_boite", mil=False)
add("P0733", "Mauvais rapport — vitesse 3", "transmission_boite", mil=False)
add("P0734", "Mauvais rapport — vitesse 4", "transmission_boite", mil=False)
add("P0735", "Mauvais rapport — vitesse 5", "transmission_boite", mil=False)
add("P0736", "Mauvais rapport — marche arrière", "transmission_boite", mil=False)
add("P0740", "Convertisseur de couple — solénoïde verrouillage", "transmission_boite", mil=False)
add("P0741", "Convertisseur — performance verrouillage", "transmission_boite", mil=False)
add("P0750", "Solénoïde shift A — circuit", "transmission_boite", mil=False)
add("P0755", "Solénoïde shift B — circuit", "transmission_boite", mil=False)
add("P0760", "Solénoïde shift C — circuit", "transmission_boite", mil=False)

# ════════════════════════════════════════════════════════════════════════════
#  P0Axx — HYBRIDES (batterie HV, moteur électrique, inverter)
# ════════════════════════════════════════════════════════════════════════════
add("P0A00", "Système hybride — défaut général", "hybride_moteur_electrique", "critical", vehicles=HYBRIDE)
add("P0A01", "Système hybride — système refroidissement HV — défaut", "hybride_batterie_hv", vehicles=HYBRIDE)
add("P0A02", "Pompe refroidissement moteur électrique — performance", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A03", "Pompe refroidissement moteur électrique — circuit", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A04", "Pompe refroidissement moteur électrique — bas", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A05", "Pompe refroidissement moteur électrique — haut", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A09", "Système DC/DC — défaut", "electrique_inverter", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A0A", "Système haute tension verrouillage — défaut", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A0B", "Système haute tension — circuit bas", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A0C", "Système haute tension — circuit haut", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A0D", "Système haute tension verrouillage — circuit ouvert", "hybride_batterie_hv", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A10", "Capteur courant batterie HV — performance", "electrique_bms", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A1A", "Module moteur générateur A — défaut", "hybride_moteur_electrique", "critical", vehicles=HYBRIDE)
add("P0A1B", "Module moteur générateur A — performance", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A1F", "Capteur batterie HV — performance", "electrique_bms", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A2A", "Température moteur électrique A — circuit", "hybride_moteur_electrique", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A2B", "Température moteur électrique A — plage/performance", "hybride_moteur_electrique", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A2D", "Température moteur électrique A — circuit bas", "hybride_moteur_electrique", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A2E", "Température moteur électrique A — circuit haut", "hybride_moteur_electrique", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A3A", "Module générateur B — défaut", "hybride_moteur_electrique", vehicles=HYBRIDE)
add("P0A3F", "Refroidissement onduleur — performance", "electrique_inverter", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A7A", "Batterie HV — module défaillant", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A7C", "Batterie HV — capacité de charge faible", "hybride_batterie_hv", "warn", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A7D", "Batterie HV — performance dégradée", "hybride_batterie_hv", "warn", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A7F", "Batterie HV — dégradation cellule détectée", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A80", "Pack batterie HV — remplacement requis", "hybride_batterie_hv", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A93", "Onduleur A — refroidissement performance", "electrique_inverter", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A94", "Onduleur A DC/DC — performance", "electrique_inverter", vehicles=HYBRIDE+ELECTRIQUE)
add("P0A95", "Onduleur A — défaut", "electrique_inverter", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0AA1", "Système haute tension — détection isolation", "electrique_bms", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0AA6", "Capteur isolation HV — défaut", "electrique_bms", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0ABF", "Capteur courant batterie HV B — circuit", "electrique_bms", vehicles=HYBRIDE+ELECTRIQUE)

# ════════════════════════════════════════════════════════════════════════════
#  P0Bxx / P0Cxx — VÉHICULES ÉLECTRIQUES (BMS, charge, moteur)
# ════════════════════════════════════════════════════════════════════════════
add("P0B23", "Capteur tension batterie HV — circuit", "electrique_bms", vehicles=ELECTRIQUE)
add("P0B3A", "Bus communication batterie HV — défaut", "electrique_bms", "critical", vehicles=HYBRIDE+ELECTRIQUE)
add("P0BBF", "Capteur température batterie HV — plage/performance", "electrique_bms", vehicles=HYBRIDE+ELECTRIQUE)
add("P0C50", "Système de charge AC — défaut", "electrique_charge", vehicles=HYBRIDE+ELECTRIQUE)
add("P0C57", "Système de charge AC — circuit communication", "electrique_charge", vehicles=HYBRIDE+ELECTRIQUE)
add("P0C58", "Système de charge AC — perte de signal", "electrique_charge", vehicles=HYBRIDE+ELECTRIQUE)
add("P0C73", "Verrouillage prise de charge — circuit", "electrique_charge", vehicles=HYBRIDE+ELECTRIQUE)
add("P0CD1", "Système 12V — non maintenu par DC/DC", "electrique_inverter", vehicles=HYBRIDE+ELECTRIQUE)

# ════════════════════════════════════════════════════════════════════════════
#  P1xxx — Cycle de conduite + manufacturer-specific samples
# ════════════════════════════════════════════════════════════════════════════
add("P1000", "Cycle de conduite OBD2 non complété", "non_classe", "info", mil=False)
# Renault — codes courants (échantillon)
add("P1471", "Pression atmosphérique — capteur (Renault)", "moteur_carburant_air", vehicles=THERM_HYB)
add("P1480", "FAP — défaut additif (Renault/PSA)", "antipollution_fap_dpf", "warn", vehicles=DIESEL)
add("P1495", "Additif FAP Eolys — réservoir niveau (PSA)", "antipollution_fap_dpf", "warn", vehicles=DIESEL)
add("P11D9", "Système AdBlue — performance (Mercedes)", "antipollution_scr_adblue", "critical", vehicles=DIESEL)
add("P1351", "Préchauffage — circuit (Renault)", "prechauffage_diesel", vehicles=DIESEL)

# ════════════════════════════════════════════════════════════════════════════
#  P20xx — Diesel : SCR / AdBlue / NOx / FAP
# ════════════════════════════════════════════════════════════════════════════
add("P2002", "Filtre à particules (FAP) banc 1 — efficacité insuffisante", "antipollution_fap_dpf", "critical", vehicles=DIESEL)
add("P2003", "Filtre à particules banc 2 — efficacité insuffisante", "antipollution_fap_dpf", "critical", vehicles=DIESEL)
add("P200A", "Vanne EGR papillon — circuit", "antipollution_egr", vehicles=DIESEL)
add("P200B", "Vanne EGR papillon — performance", "antipollution_egr", vehicles=DIESEL)
add("P200C", "Vanne EGR papillon — circuit bas", "antipollution_egr", vehicles=DIESEL)
add("P200D", "Vanne EGR papillon — circuit haut", "antipollution_egr", vehicles=DIESEL)
add("P204F", "SCR — efficacité réduction NOx insuffisante", "antipollution_scr_adblue", "critical", vehicles=DIESEL)
add("P2051", "SCR — capteur niveau réducteur (AdBlue) — circuit", "antipollution_scr_adblue", vehicles=DIESEL)
add("P2052", "SCR — capteur niveau réducteur — performance", "antipollution_scr_adblue", vehicles=DIESEL)
add("P2053", "SCR — capteur niveau réducteur — circuit bas", "antipollution_scr_adblue", vehicles=DIESEL)
add("P2054", "SCR — capteur niveau réducteur — circuit haut", "antipollution_scr_adblue", vehicles=DIESEL)
add("P2055", "SCR — capteur niveau réducteur — intermittent", "antipollution_scr_adblue", vehicles=DIESEL)
add("P207F", "Qualité réducteur (AdBlue) — incorrecte", "antipollution_scr_adblue", "critical", vehicles=DIESEL)
add("P2080", "Capteur température échappement banc 1 capt. 1 — circuit", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2081", "Capteur température échappement banc 1 capt. 1 — plage", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2084", "Capteur température échappement banc 2 capt. 1 — circuit", "antipollution_fap_dpf", vehicles=DIESEL)
add("P20E8", "Pression réducteur (AdBlue) — trop basse", "antipollution_scr_adblue", "critical", vehicles=DIESEL)
add("P20E9", "Pression réducteur (AdBlue) — trop haute", "antipollution_scr_adblue", "warn", vehicles=DIESEL)
add("P20EE", "SCR — efficacité catalyseur banc 1 sous seuil", "antipollution_scr_adblue", "critical", vehicles=DIESEL)
add("P2122", "Capteur position pédale accélérateur D — circuit bas", "moteur_carburant_air")
add("P2123", "Capteur position pédale accélérateur D — circuit haut", "moteur_carburant_air")
add("P2127", "Capteur position pédale accélérateur E — circuit bas", "moteur_carburant_air")
add("P2128", "Capteur position pédale accélérateur E — circuit haut", "moteur_carburant_air")
add("P2138", "Pédale accélérateur D/E — corrélation tensions", "moteur_carburant_air")
add("P2191", "Mélange trop pauvre banc 1 — pleine charge", "moteur_carburant_air", vehicles=ESSENCE)
add("P2192", "Mélange trop riche banc 1 — pleine charge", "moteur_carburant_air", vehicles=ESSENCE)
add("P2201", "Capteur NOx banc 1 capteur 1 — circuit", "antipollution_nox", vehicles=DIESEL)
add("P2202", "Capteur NOx banc 1 capteur 1 — performance", "antipollution_nox", vehicles=DIESEL)
add("P2203", "Capteur NOx banc 1 capteur 1 — circuit bas", "antipollution_nox", vehicles=DIESEL)
add("P2204", "Capteur NOx banc 1 capteur 1 — circuit haut", "antipollution_nox", vehicles=DIESEL)
add("P2205", "Capteur NOx banc 1 capteur 1 — intermittent", "antipollution_nox", vehicles=DIESEL)
add("P2228", "Capteur pression atmosphérique — circuit bas", "moteur_carburant_air")
add("P2229", "Capteur pression atmosphérique — circuit haut", "moteur_carburant_air")
add("P229E", "Capteur NOx amont — performance", "antipollution_nox", vehicles=DIESEL)
add("P229F", "Capteur NOx aval — performance", "antipollution_nox", vehicles=DIESEL)
add("P22A0", "Capteur NOx aval — circuit", "antipollution_nox", vehicles=DIESEL)
add("P22A1", "Capteur NOx aval — circuit bas", "antipollution_nox", vehicles=DIESEL)
add("P22A2", "Capteur NOx aval — circuit haut", "antipollution_nox", vehicles=DIESEL)
add("P2336", "Cliquetis cylindre 1 — sur-limite", "moteur_allumage_rates", vehicles=ESSENCE)
add("P2337", "Cliquetis cylindre 2 — sur-limite", "moteur_allumage_rates", vehicles=ESSENCE)
add("P2338", "Cliquetis cylindre 3 — sur-limite", "moteur_allumage_rates", vehicles=ESSENCE)
add("P2339", "Cliquetis cylindre 4 — sur-limite", "moteur_allumage_rates", vehicles=ESSENCE)
add("P2400", "EVAP — pompe détection fuite — circuit", "antipollution_evap", vehicles=ESSENCE)
add("P242F", "FAP — accumulation cendres (filtre colmaté)", "antipollution_fap_dpf", "critical", vehicles=DIESEL)
add("P2452", "FAP — capteur pression différentielle banc 1 — circuit", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2453", "FAP — capteur pression différentielle banc 1 — performance", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2454", "FAP — capteur pression différentielle banc 1 — circuit bas", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2455", "FAP — capteur pression différentielle banc 1 — circuit haut", "antipollution_fap_dpf", vehicles=DIESEL)
add("P2458", "FAP — durée de régénération", "antipollution_fap_dpf", "warn", vehicles=DIESEL)
add("P2459", "FAP — fréquence de régénération", "antipollution_fap_dpf", "warn", vehicles=DIESEL)
add("P2463", "FAP — accumulation suies excessive", "antipollution_fap_dpf", "critical", vehicles=DIESEL)
add("P2464", "FAP — capteur température aval — performance", "antipollution_fap_dpf", vehicles=DIESEL)
add("P246C", "FAP — régénération limitée par mauvaises conditions", "antipollution_fap_dpf", "warn", vehicles=DIESEL)
add("P246F", "FAP — régénération impossible (mode dégradé)", "antipollution_fap_dpf", "critical", vehicles=DIESEL)
add("P2509", "ECM/PCM — alimentation interrompue", "electronique_alimentation", "critical")
add("P2563", "Capteur position turbo — circuit", "turbo_suralimentation")
add("P2BAD", "Capteur NOx aval — défaut", "antipollution_nox", vehicles=DIESEL)
add("P2BAE", "Limite régénération FAP atteinte — couple moteur réduit", "antipollution_fap_dpf", "critical", vehicles=DIESEL)

# ════════════════════════════════════════════════════════════════════════════
#  U0xxx — RÉSEAU CAN / Communication
# ════════════════════════════════════════════════════════════════════════════
add("U0001", "Bus CAN haute vitesse — défaut", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0002", "Bus CAN haute vitesse — performance", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0073", "Bus communication module — désactivé", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0100", "Perte communication avec ECM/PCM A", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0101", "Perte communication avec TCM (boîte)", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0121", "Perte communication avec ABS", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0140", "Perte communication avec module BCM", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0151", "Perte communication avec module airbags (SRS)", "electronique_reseau_can", "critical", vehicles=ALL_VEH)
add("U0155", "Perte communication avec combiné d'instruments", "electronique_reseau_can", "warn", vehicles=ALL_VEH)
add("U0167", "Perte communication avec module antidémarrage", "electronique_reseau_can", "critical", vehicles=ALL_VEH)

# ════════════════════════════════════════════════════════════════════════════
#  C0xxx — Châssis : ABS, ESP
# ════════════════════════════════════════════════════════════════════════════
add("C0035", "Capteur roue avant gauche (ABS) — circuit", "freinage_abs", "warn", mil=False, vehicles=ALL_VEH)
add("C0040", "Capteur roue avant droit (ABS) — circuit", "freinage_abs", "warn", mil=False, vehicles=ALL_VEH)
add("C0045", "Capteur roue arrière gauche (ABS) — circuit", "freinage_abs", "warn", mil=False, vehicles=ALL_VEH)
add("C0050", "Capteur roue arrière droit (ABS) — circuit", "freinage_abs", "warn", mil=False, vehicles=ALL_VEH)
add("C0061", "ABS — défaut pompe", "freinage_abs", "critical", mil=False, vehicles=ALL_VEH)
add("C0110", "ABS — moteur pompe — défaut", "freinage_abs", "critical", mil=False, vehicles=ALL_VEH)
add("C0196", "ABS — capteur lacet — circuit", "esp_stabilite_traction", mil=False, vehicles=ALL_VEH)
add("C0210", "ESP — désactivation système", "esp_stabilite_traction", mil=False, vehicles=ALL_VEH)
add("C0265", "ABS/EBCM — circuit", "freinage_abs", "critical", mil=False, vehicles=ALL_VEH)

# ════════════════════════════════════════════════════════════════════════════
#  B0xxx — Carrosserie : airbags
# ════════════════════════════════════════════════════════════════════════════
add("B0001", "Airbag conducteur — circuit déploiement", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)
add("B0002", "Airbag conducteur — circuit court masse", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)
add("B0010", "Airbag passager — circuit déploiement", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)
add("B0020", "Airbag latéral conducteur — défaut", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)
add("B0021", "Airbag latéral passager — défaut", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)
add("B0050", "Capteur impact frontal — défaut", "securite_airbags", "critical", mil=False, vehicles=ALL_VEH)

# ════════════════════════════════════════════════════════════════════════════
#  EXTENSIONS — couverture étendue (P0/P2/P0A/P0B/P0C/U0/P1 constructeurs)
# ════════════════════════════════════════════════════════════════════════════

# ── P00xx complément — chauffages lambda banc 1 capt. 3/4 et banc 2 capt. 3/4 ──
for code, lbl in [
    ("P0040", "Permutation sondes lambda amont — corrélation banc 1/banc 2"),
    ("P0041", "Permutation sondes lambda aval — corrélation banc 1/banc 2"),
    ("P0042", "Chauffage sonde lambda banc 1 capteur 3 — circuit"),
    ("P0043", "Chauffage sonde lambda banc 1 capteur 3 — circuit bas"),
    ("P0044", "Chauffage sonde lambda banc 1 capteur 3 — circuit haut"),
    ("P0045", "Solénoïde wastegate turbo — circuit"),
    ("P0046", "Solénoïde wastegate turbo — performance"),
    ("P0047", "Solénoïde wastegate turbo — circuit bas"),
    ("P0048", "Solénoïde wastegate turbo — circuit haut"),
    ("P0049", "Survitesse turbocompresseur"),
]:
    if code.startswith("P004"):
        add(code, lbl, "turbo_suralimentation" if "turbo" in lbl.lower() else "antipollution_lambda")
    else:
        add(code, lbl, "antipollution_lambda")

# ── P00xx — Pression carburant secondaire / capteurs additionnels ──
for code, lbl, fam, sev in [
    ("P0080", "Vanne échappement banc 1 — circuit", "moteur_distribution", "warn"),
    ("P0081", "Vanne échappement banc 1 — performance", "moteur_distribution", "warn"),
    ("P0082", "Vanne échappement banc 1 — circuit bas", "moteur_distribution", "warn"),
    ("P0083", "Vanne échappement banc 1 — circuit haut", "moteur_distribution", "warn"),
    ("P0084", "Vanne échappement banc 2 — circuit", "moteur_distribution", "warn"),
    ("P0085", "Vanne échappement banc 2 — circuit bas", "moteur_distribution", "warn"),
    ("P0086", "Vanne échappement banc 2 — circuit haut", "moteur_distribution", "warn"),
]:
    add(code, lbl, fam, sev)

# ── P01xx complément — IAC + capteurs MAP additionnels ──
for code, lbl, fam in [
    ("P0129", "Pression barométrique trop basse", "moteur_carburant_air"),
    ("P0177", "Capteur composition carburant — performance", "moteur_injection_hp"),
    ("P0178", "Capteur composition carburant — circuit bas", "moteur_injection_hp"),
    ("P0179", "Capteur composition carburant — circuit haut", "moteur_injection_hp"),
    ("P0186", "Capteur température carburant B — performance", "moteur_injection_hp"),
    ("P0187", "Capteur température carburant B — circuit bas", "moteur_injection_hp"),
    ("P0188", "Capteur température carburant B — circuit haut", "moteur_injection_hp"),
    ("P0199", "Capteur température huile moteur — intermittent", "moteur_lubrification_temperature"),
]:
    add(code, lbl, fam)

# ── P02xx — Suite injecteurs + capteurs carburant ──
for code, lbl in [
    ("P0205", "Injecteur cylindre 5 — circuit"),
    ("P0206", "Injecteur cylindre 6 — circuit"),
    ("P0207", "Injecteur cylindre 7 — circuit"),
    ("P0208", "Injecteur cylindre 8 — circuit"),
    ("P0209", "Injecteur cylindre 9 — circuit"),
    ("P020A", "Injecteur cylindre 10 — circuit"),
    ("P020B", "Injecteur cylindre 11 — circuit"),
    ("P020C", "Injecteur cylindre 12 — circuit"),
    ("P0213", "Injecteur démarrage froid 1 — circuit"),
    ("P0214", "Injecteur démarrage froid 2 — circuit"),
    ("P0215", "Solénoïde arrêt moteur — circuit"),
    ("P0216", "Solénoïde calage injection — circuit"),
]:
    add(code, lbl, "moteur_injection_hp")

for code, lbl in [
    ("P0225", "TPS C — circuit"),
    ("P0226", "TPS C — performance"),
    ("P0227", "TPS C — circuit bas"),
    ("P0228", "TPS C — circuit haut"),
]:
    add(code, lbl, "moteur_carburant_air")

# Injecteurs par cylindre - circuits bas/haut détaillés P0250-P0291
for i, cyl in enumerate(range(1, 11)):
    base = 0x261 + (cyl - 1) * 3
    add(f"P{base:04X}", f"Cylindre {cyl} — injecteur circuit bas", "moteur_injection_hp")
    add(f"P{base+1:04X}", f"Cylindre {cyl} — injecteur circuit haut", "moteur_injection_hp")
    add(f"P{base+2:04X}", f"Cylindre {cyl} — contribution/équilibre", "moteur_injection_hp")

# ── P03xx complément — bobines cylindres + AAC ──
for code, lbl in [
    ("P0347", "Capteur AAC A banc 2 — circuit bas"),
    ("P0348", "Capteur AAC A banc 2 — circuit haut"),
    ("P0349", "Capteur AAC A banc 2 — intermittent"),
    ("P0367", "Capteur AAC B banc 1 — circuit bas"),
    ("P0368", "Capteur AAC B banc 1 — circuit haut"),
    ("P0369", "Capteur AAC B banc 1 — intermittent"),
    ("P0385", "Capteur position vilebrequin B — circuit"),
    ("P0386", "Capteur vilebrequin B — plage/performance"),
    ("P0387", "Capteur vilebrequin B — circuit bas"),
    ("P0388", "Capteur vilebrequin B — circuit haut"),
]:
    add(code, lbl, "moteur_distribution")

# ── P04xx complément — EGR avancé + EVAP fin ──
for code, lbl, fam, sev in [
    ("P0415", "Air secondaire vanne B — circuit ouvert", "antipollution_air_secondaire", "warn"),
    ("P0416", "Air secondaire vanne B — circuit court", "antipollution_air_secondaire", "warn"),
    ("P0417", "Air secondaire vanne B — circuit", "antipollution_air_secondaire", "warn"),
    ("P0425", "Capteur température catalyseur banc 1 — circuit", "antipollution_catalyseur", "warn"),
    ("P0426", "Capteur température catalyseur banc 1 — plage", "antipollution_catalyseur", "warn"),
    ("P0427", "Capteur température catalyseur banc 1 — bas", "antipollution_catalyseur", "warn"),
    ("P0428", "Capteur température catalyseur banc 1 — haut", "antipollution_catalyseur", "warn"),
    ("P0433", "Catalyseur chauffé banc 2 — efficacité", "antipollution_catalyseur", "warn"),
    ("P0458", "EVAP — vanne purge — circuit bas", "antipollution_evap", "warn"),
    ("P0459", "EVAP — vanne purge — circuit haut", "antipollution_evap", "warn"),
    ("P0460", "Capteur niveau carburant A — circuit", "moteur_injection_hp", "info"),
    ("P0464", "Capteur niveau carburant A — intermittent", "moteur_injection_hp", "info"),
    ("P0472", "Capteur pression échappement — circuit bas", "moteur_carburant_air", "warn"),
    ("P0473", "Capteur pression échappement — circuit haut", "moteur_carburant_air", "warn"),
    ("P0482", "Relais ventilateur refroidissement 3 — circuit", "moteur_lubrification_temperature", "warn"),
    ("P0483", "Ventilateur refroidissement — rationalité", "moteur_lubrification_temperature", "warn"),
    ("P0490", "EGR — circuit haut A", "antipollution_egr", "warn"),
    ("P0491", "Air secondaire banc 1 — flux insuffisant", "antipollution_air_secondaire", "warn"),
    ("P0492", "Air secondaire banc 2 — flux insuffisant", "antipollution_air_secondaire", "warn"),
]:
    add(code, lbl, fam, sev)

# ── P05xx complément — régulateur, climatisation, charge ──
for code, lbl, fam, sev in [
    ("P0510", "Interrupteur position fermée papillon — circuit", "moteur_carburant_air", "warn"),
    ("P0513", "Incorrect clé immobilizer", "carrosserie_eclairage_confort", "warn"),
    ("P0530", "Capteur pression réfrigérant clim — circuit", "climatisation_chauffage", "info"),
    ("P0531", "Capteur pression réfrigérant clim — performance", "climatisation_chauffage", "info"),
    ("P0534", "Perte charge réfrigérant clim", "climatisation_chauffage", "info"),
    ("P0537", "Capteur température évaporateur clim — circuit bas", "climatisation_chauffage", "info"),
    ("P0538", "Capteur température évaporateur clim — circuit haut", "climatisation_chauffage", "info"),
    ("P0540", "Chauffage admission A — circuit", "moteur_carburant_air", "warn"),
    ("P0545", "Capteur température échappement banc 1 — circuit", "antipollution_fap_dpf", "warn"),
    ("P0546", "Capteur température échappement banc 1 — plage", "antipollution_fap_dpf", "warn"),
    ("P0547", "Capteur température échappement banc 2 — circuit", "antipollution_fap_dpf", "warn"),
    ("P0550", "Capteur pression direction assistée — circuit", "direction_assistee", "warn"),
    ("P0551", "Capteur pression direction assistée — performance", "direction_assistee", "warn"),
    ("P0552", "Capteur pression direction assistée — circuit bas", "direction_assistee", "warn"),
    ("P0553", "Capteur pression direction assistée — circuit haut", "direction_assistee", "warn"),
    ("P0561", "Tension système — instable", "electronique_alimentation", "warn"),
    ("P0564", "Régulateur de vitesse multifonction — circuit A", "electronique_ecm_pcm", "warn"),
    ("P0565", "Régulateur de vitesse — signal ON", "electronique_ecm_pcm", "info"),
    ("P0566", "Régulateur de vitesse — signal OFF", "electronique_ecm_pcm", "info"),
    ("P0567", "Régulateur de vitesse — signal RESUME", "electronique_ecm_pcm", "info"),
    ("P0568", "Régulateur de vitesse — signal SET", "electronique_ecm_pcm", "info"),
    ("P0569", "Régulateur de vitesse — signal COAST", "electronique_ecm_pcm", "info"),
    ("P0572", "Contacteur de frein A — circuit bas", "freinage_abs", "warn"),
    ("P0573", "Contacteur de frein A — circuit haut", "freinage_abs", "warn"),
    ("P0575", "Régulateur de vitesse — circuit entrée", "electronique_ecm_pcm", "info"),
    ("P0581", "Régulateur de vitesse — signal multi-fonction A", "electronique_ecm_pcm", "info"),
]:
    add(code, lbl, fam, sev)

# ── P06xx complément — ECM/PCM + relais ──
for code, lbl, fam in [
    ("P0609", "ECM/PCM — module VSS B sortie", "electronique_ecm_pcm"),
    ("P060C", "ECM/PCM — processeur principal — performance", "electronique_ecm_pcm"),
    ("P060D", "ECM/PCM — module position papillon — performance", "electronique_ecm_pcm"),
    ("P060E", "ECM/PCM — module position pédale — performance", "electronique_ecm_pcm"),
    ("P0610", "ECM — options véhicule erronées", "electronique_ecm_pcm"),
    ("P0611", "Module commande injecteur — performance", "moteur_injection_hp"),
    ("P0615", "Relais démarreur — circuit", "electronique_alimentation"),
    ("P0616", "Relais démarreur — circuit bas", "electronique_alimentation"),
    ("P0617", "Relais démarreur — circuit haut", "electronique_alimentation"),
    ("P0620", "Circuit contrôle alternateur", "electronique_alimentation"),
    ("P0621", "Lampe alternateur — circuit", "electronique_alimentation"),
    ("P0622", "Alternateur — terminal champ — circuit", "electronique_alimentation"),
    ("P0625", "Alternateur — terminal champ — circuit bas", "electronique_alimentation"),
    ("P0626", "Alternateur — terminal champ — circuit haut", "electronique_alimentation"),
    ("P0627", "Pompe carburant — circuit ouvert", "moteur_injection_hp"),
    ("P0628", "Pompe carburant — circuit bas", "moteur_injection_hp"),
    ("P0629", "Pompe carburant — circuit haut", "moteur_injection_hp"),
    ("P0630", "VIN non programmé / non concordant", "electronique_ecm_pcm"),
    ("P0633", "Clé immobilizer non programmée", "carrosserie_eclairage_confort"),
    ("P0642", "Référence tension capteur A — circuit bas", "electronique_ecm_pcm"),
    ("P0643", "Référence tension capteur A — circuit haut", "electronique_ecm_pcm"),
    ("P0645", "Embrayage compresseur clim — circuit", "climatisation_chauffage"),
    ("P0646", "Embrayage compresseur clim — circuit bas", "climatisation_chauffage"),
    ("P0647", "Embrayage compresseur clim — circuit haut", "climatisation_chauffage"),
    ("P0652", "Référence tension capteur B — circuit bas", "electronique_ecm_pcm"),
    ("P0653", "Référence tension capteur B — circuit haut", "electronique_ecm_pcm"),
    ("P0660", "Vanne admission air collecteur banc 1 — circuit", "moteur_carburant_air"),
    ("P0691", "Ventilateur 1 — circuit bas", "moteur_lubrification_temperature"),
    ("P0692", "Ventilateur 1 — circuit haut", "moteur_lubrification_temperature"),
    ("P0693", "Ventilateur 2 — circuit bas", "moteur_lubrification_temperature"),
    ("P0694", "Ventilateur 2 — circuit haut", "moteur_lubrification_temperature"),
]:
    add(code, lbl, fam)

# ── P07xx-P08xx complément — Transmission détaillée ──
for code, lbl in [
    ("P0707", "Capteur position levier — circuit bas"),
    ("P0708", "Capteur position levier — circuit haut"),
    ("P0709", "Capteur position levier — intermittent"),
    ("P0711", "Capteur température ATF — performance"),
    ("P0712", "Capteur température ATF — circuit bas"),
    ("P0713", "Capteur température ATF — circuit haut"),
    ("P0716", "Capteur vitesse entrée turbine — performance"),
    ("P0717", "Capteur vitesse entrée turbine — pas de signal"),
    ("P0721", "Capteur vitesse sortie BV — performance"),
    ("P0722", "Capteur vitesse sortie BV — pas de signal"),
    ("P0731", "Mauvais rapport — vitesse 1"),
    ("P0742", "Convertisseur — verrouillage permanent"),
    ("P0743", "Convertisseur — solénoïde — électrique"),
    ("P0751", "Solénoïde shift A — fonctionnement"),
    ("P0752", "Solénoïde shift A — bloqué ON"),
    ("P0756", "Solénoïde shift B — fonctionnement"),
    ("P0757", "Solénoïde shift B — bloqué ON"),
    ("P0761", "Solénoïde shift C — fonctionnement"),
    ("P0766", "Solénoïde shift D — fonctionnement"),
    ("P0775", "Solénoïde pression — performance"),
    ("P0780", "Shift — défaut"),
    ("P0781", "Shift 1-2 — défaut"),
    ("P0782", "Shift 2-3 — défaut"),
    ("P0783", "Shift 3-4 — défaut"),
    ("P0784", "Shift 4-5 — défaut"),
    ("P0785", "Solénoïde shift/timing — défaut"),
    ("P0791", "Capteur vitesse intermédiaire — circuit"),
    ("P0795", "Solénoïde pression C — circuit"),
    ("P0796", "Solénoïde pression C — performance"),
]:
    add(code, lbl, "transmission_boite", mil=False, vehicles=THERM_HYB)

for code, lbl in [
    ("P0810", "Capteur position embrayage — circuit"),
    ("P0815", "Switch upshift — circuit"),
    ("P0816", "Switch downshift — circuit"),
    ("P0830", "Switch pédale embrayage — circuit"),
    ("P0850", "Switch parking/neutre — circuit"),
    ("P0863", "Communication TCM — défaut"),
    ("P0868", "Pression transmission basse"),
    ("P0869", "Pression transmission haute"),
    ("P0871", "Capteur pression circuit C — circuit"),
    ("P0882", "Module commande BV — alimentation basse"),
    ("P0883", "Module commande BV — alimentation haute"),
    ("P0884", "Module commande BV — intermittent"),
    ("P0890", "Module commande BV — relais alim. — circuit"),
    ("P0891", "Module commande BV — relais alim. — performance"),
    ("P0894", "Patinage convertisseur excessif"),
]:
    add(code, lbl, "transmission_boite", mil=False, vehicles=THERM_HYB)

# Embrayage
for code, lbl in [
    ("P0900", "Actionneur embrayage — circuit ouvert"),
    ("P0901", "Actionneur embrayage — performance"),
    ("P0902", "Actionneur embrayage — circuit bas"),
    ("P0903", "Actionneur embrayage — circuit haut"),
    ("P0904", "Capteur position fourchette embrayage — circuit"),
    ("P0907", "Solénoïde sélecteur vitesse — circuit"),
    ("P0908", "Solénoïde sélecteur vitesse — performance"),
    ("P090C", "Actionneur embrayage 2 — circuit ouvert"),
    ("P0961", "Solénoïde pression A — performance"),
    ("P0962", "Solénoïde pression A — circuit bas"),
    ("P0963", "Solénoïde pression A — circuit haut"),
    ("P0973", "Solénoïde shift A — circuit bas"),
    ("P0974", "Solénoïde shift A — circuit haut"),
]:
    add(code, lbl, "transmission_embrayage", mil=False, vehicles=THERM_HYB)

# ── P0Axx complément hybrides (couverture étendue) ──
HYB_VEH = HYBRIDE + ELECTRIQUE
for code, lbl, fam, sev in [
    ("P0A06", "Système refroidissement haute tension — performance basse", "hybride_batterie_hv", "warn"),
    ("P0A07", "Système refroidissement HV — performance basse", "hybride_batterie_hv", "warn"),
    ("P0A08", "Tension auxiliaire DC/DC — basse", "electrique_inverter", "critical"),
    ("P0A0E", "Système haute tension verrouillage — circuit haut", "hybride_batterie_hv", "critical"),
    ("P0A0F", "Système haute tension verrouillage — circuit court", "hybride_batterie_hv", "critical"),
    ("P0A11", "Capteur courant batterie HV — circuit bas", "electrique_bms", "warn"),
    ("P0A12", "Capteur courant batterie HV — circuit haut", "electrique_bms", "warn"),
    ("P0A13", "Capteur tension batterie HV — performance", "electrique_bms", "warn"),
    ("P0A14", "Capteur tension batterie HV — circuit bas", "electrique_bms", "warn"),
    ("P0A15", "Capteur tension batterie HV — circuit haut", "electrique_bms", "warn"),
    ("P0A16", "Position moteur électrique A — performance", "hybride_moteur_electrique", "warn"),
    ("P0A17", "Capteur position moteur électrique A — circuit", "hybride_moteur_electrique", "warn"),
    ("P0A1C", "Module moteur générateur A — circuit ouvert", "hybride_moteur_electrique", "warn"),
    ("P0A1D", "Module moteur générateur A — bas", "hybride_moteur_electrique", "warn"),
    ("P0A1E", "Module moteur générateur A — haut", "hybride_moteur_electrique", "warn"),
    ("P0A20", "Module moteur générateur B — circuit ouvert", "hybride_moteur_electrique", "warn"),
    ("P0A21", "Module moteur générateur B — performance", "hybride_moteur_electrique", "warn"),
    ("P0A22", "Module moteur générateur B — bas", "hybride_moteur_electrique", "warn"),
    ("P0A23", "Module moteur générateur B — haut", "hybride_moteur_electrique", "warn"),
    ("P0A30", "Désactivation transmission — perte mode hybride", "hybride_moteur_electrique", "critical"),
    ("P0A31", "Capteur température moteur électrique B — circuit", "hybride_moteur_electrique", "warn"),
    ("P0A40", "Onduleur courant inversé — détecté", "electrique_inverter", "critical"),
    ("P0A41", "Refroidissement DC/DC — performance", "electrique_inverter", "warn"),
    ("P0A42", "Onduleur — surchauffe protection active", "electrique_inverter", "critical"),
    ("P0A44", "Capteur température DC/DC — circuit", "electrique_inverter", "warn"),
    ("P0A50", "Capteur courant générateur A — circuit", "hybride_moteur_electrique", "warn"),
    ("P0A60", "Capteur courant moteur électrique A — circuit", "hybride_moteur_electrique", "warn"),
    ("P0A72", "Régulation moteur électrique — couple insuffisant", "hybride_moteur_electrique", "warn"),
    ("P0A78", "Onduleur moteur électrique — performance", "electrique_inverter", "warn"),
    ("P0A79", "Onduleur électrique — circuit ouvert", "electrique_inverter", "warn"),
    ("P0A7B", "Batterie HV — courant excessif détecté", "hybride_batterie_hv", "critical"),
    ("P0A7E", "Batterie HV — surchauffe", "hybride_batterie_hv", "critical"),
    ("P0A81", "Pompe refroidissement batterie HV — performance", "hybride_batterie_hv", "warn"),
    ("P0A82", "Pompe refroidissement batterie HV — circuit ouvert", "hybride_batterie_hv", "warn"),
    ("P0A83", "Pompe refroidissement batterie HV — circuit bas", "hybride_batterie_hv", "warn"),
    ("P0A84", "Pompe refroidissement batterie HV — circuit haut", "hybride_batterie_hv", "warn"),
    ("P0A85", "Ventilateur refroidissement batterie HV — performance", "hybride_batterie_hv", "warn"),
    ("P0A8A", "Câble HV positif — détection isolation", "electrique_bms", "critical"),
    ("P0A8C", "Câble HV négatif — détection isolation", "electrique_bms", "critical"),
    ("P0A90", "Moteur entraînement A — performance", "hybride_moteur_electrique", "critical"),
    ("P0A91", "Moteur entraînement A — circuit ouvert", "hybride_moteur_electrique", "critical"),
    ("P0A96", "Capteur température onduleur A — circuit", "electrique_inverter", "warn"),
    ("P0A98", "Capteur température onduleur A — circuit bas", "electrique_inverter", "warn"),
    ("P0A99", "Capteur température onduleur A — circuit haut", "electrique_inverter", "warn"),
    ("P0AA0", "Système haute tension — pré-charge contacteur", "hybride_batterie_hv", "critical"),
    ("P0AA4", "Contacteur batterie HV — circuit ouvert", "hybride_batterie_hv", "critical"),
    ("P0AA7", "Capteur isolation HV — bas", "electrique_bms", "critical"),
    ("P0AA8", "Capteur isolation HV — haut", "electrique_bms", "critical"),
    ("P0ABF", "Capteur courant batterie HV B — circuit ouvert", "electrique_bms", "warn"),
    ("P0AC0", "Capteur courant batterie HV B — bas", "electrique_bms", "warn"),
    ("P0AC1", "Capteur courant batterie HV B — haut", "electrique_bms", "warn"),
    ("P0AC2", "Compteur capacité charge batterie HV — défaut", "electrique_bms", "warn"),
    ("P0AC4", "Système précharge — défaut séquence", "hybride_batterie_hv", "critical"),
    ("P0ACC", "Capteur température batterie HV — corrélation", "electrique_bms", "warn"),
    ("P0AD0", "Capteur courant batterie HV C — circuit", "electrique_bms", "warn"),
    ("P0AE6", "Système hybride — perte propulsion", "hybride_moteur_electrique", "critical"),
    ("P0AF0", "Module commande batterie HV — perte communication", "electrique_bms", "critical"),
    ("P0AF6", "Coupure ouverte HV — défaut", "hybride_batterie_hv", "critical"),
    ("P0AFA", "Tension isolation batterie HV — basse", "electrique_bms", "critical"),
]:
    add(code, lbl, fam, sev, vehicles=HYB_VEH)

# ── P0B/P0C — Électriques (BMS, charge, moteur entraînement) ──
EV_VEH = HYB_VEH
for code, lbl, fam, sev in [
    ("P0B05", "Tension cellule batterie HV — déséquilibre", "electrique_bms", "warn"),
    ("P0B0F", "Tension cellule batterie HV — surcharge", "electrique_bms", "critical"),
    ("P0B11", "Tension cellule batterie HV — sous-charge", "electrique_bms", "warn"),
    ("P0B22", "Tension cellule batterie HV — déconnexion détectée", "electrique_bms", "critical"),
    ("P0B24", "Capteur tension batterie HV — performance", "electrique_bms", "warn"),
    ("P0B2B", "Capteur courant batterie HV — corrélation", "electrique_bms", "warn"),
    ("P0B30", "Module batterie HV — défaut", "electrique_bms", "critical"),
    ("P0B3D", "Bus communication batterie HV — circuit ouvert", "electrique_bms", "critical"),
    ("P0B43", "Sonde température batterie HV 1 — circuit", "electrique_bms", "warn"),
    ("P0B45", "Sonde température batterie HV 1 — bas", "electrique_bms", "warn"),
    ("P0B46", "Sonde température batterie HV 1 — haut", "electrique_bms", "warn"),
    ("P0B4A", "Sonde température batterie HV 2 — circuit", "electrique_bms", "warn"),
    ("P0B60", "Sonde température batterie HV 3 — circuit", "electrique_bms", "warn"),
    ("P0B80", "Capteur isolement batterie HV — défaut", "electrique_bms", "critical"),
    ("P0B95", "Refroidissement liquide batterie HV — performance", "hybride_batterie_hv", "warn"),
    ("P0BA0", "Refroidissement liquide batterie HV — sous-pression", "hybride_batterie_hv", "warn"),
    ("P0BC0", "Capteur température fluide refroidissement HV — circuit", "hybride_batterie_hv", "warn"),
    ("P0BDB", "Refroidissement batterie HV — module désactivé", "hybride_batterie_hv", "warn"),
    ("P0C00", "Système entraînement A — performance", "hybride_moteur_electrique", "critical"),
    ("P0C10", "Tension AC chargeur — détectée hors plage", "electrique_charge", "warn"),
    ("P0C12", "Courant AC chargeur — anormal", "electrique_charge", "warn"),
    ("P0C25", "Câble charge AC — verrouillage forcé impossible", "electrique_charge", "warn"),
    ("P0C29", "Capteur température chargeur AC — circuit", "electrique_charge", "warn"),
    ("P0C32", "Capteur courant chargeur AC — circuit", "electrique_charge", "warn"),
    ("P0C45", "Pilote charge — communication défaut", "electrique_charge", "warn"),
    ("P0C50", "Système charge AC — défaut général", "electrique_charge", "warn"),
    ("P0C51", "Système charge AC — performance", "electrique_charge", "warn"),
    ("P0C55", "Système charge DC rapide — défaut", "electrique_charge", "warn"),
    ("P0C56", "Système charge DC — circuit ouvert", "electrique_charge", "warn"),
    ("P0C57", "Bus communication chargeur — défaut", "electrique_charge", "warn"),
    ("P0C58", "Chargeur — perte communication", "electrique_charge", "warn"),
    ("P0C60", "Câble charge — détection chaleur excessive", "electrique_charge", "critical"),
    ("P0C70", "Cordon de charge — circuit identification", "electrique_charge", "warn"),
    ("P0C73", "Verrouillage prise de charge — circuit", "electrique_charge", "warn"),
    ("P0C74", "Verrouillage prise de charge — bloqué fermé", "electrique_charge", "warn"),
    ("P0C75", "Verrouillage prise de charge — bloqué ouvert", "electrique_charge", "warn"),
    ("P0C76", "Capteur courant charge DC — circuit", "electrique_charge", "warn"),
    ("P0C7F", "Échec authentification charge", "electrique_charge", "info"),
    ("P0C80", "Système charge — surtension détectée", "electrique_charge", "critical"),
    ("P0C8A", "Onduleur charge — défaut", "electrique_charge", "warn"),
    ("P0C95", "Convertisseur DC/DC auxiliaire 12V — circuit", "electrique_inverter", "critical"),
    ("P0CA0", "Capteur courant DC/DC sortie 12V — circuit", "electrique_inverter", "warn"),
    ("P0CD1", "Système 12V — non maintenu par DC/DC", "electrique_inverter", "warn"),
    ("P0CE0", "Système de chauffage HV — circuit", "climatisation_chauffage", "warn", ),
]:
    add(code, lbl, fam, sev, vehicles=EV_VEH)

# ── P2xxx — Suite (auxiliaire émission, pédale, capteurs) ──
for code, lbl, fam, sev in [
    ("P2006", "Vanne admission air collecteur banc 1 — bloquée fermée", "moteur_carburant_air", "warn"),
    ("P2007", "Vanne admission air collecteur banc 2 — bloquée fermée", "moteur_carburant_air", "warn"),
    ("P2008", "Vanne admission air collecteur banc 1 — circuit ouvert", "moteur_carburant_air", "warn"),
    ("P2009", "Vanne admission air collecteur banc 1 — circuit bas", "moteur_carburant_air", "warn"),
    ("P2010", "Vanne admission air collecteur banc 1 — circuit haut", "moteur_carburant_air", "warn"),
    ("P2015", "Vanne admission air collecteur banc 1 — capteur position — performance", "moteur_carburant_air", "warn"),
    ("P2017", "Vanne admission air collecteur banc 1 — capteur position — circuit haut", "moteur_carburant_air", "warn"),
    ("P2023", "Vanne admission air collecteur banc 2 — capteur position — circuit haut", "moteur_carburant_air", "warn"),
    ("P2030", "Chauffage admission carburant — circuit", "moteur_carburant_air", "warn", ),
    ("P2031", "Chauffage admission carburant — performance", "moteur_carburant_air", "warn"),
    ("P2032", "Chauffage admission carburant — circuit bas", "moteur_carburant_air", "warn"),
    ("P2033", "Chauffage admission carburant — circuit haut", "moteur_carburant_air", "warn"),
    ("P2068", "Capteur niveau carburant B — performance", "moteur_injection_hp", "info"),
    ("P2070", "Vanne admission air collecteur banc 1 — bloquée ouverte", "moteur_carburant_air", "warn"),
    ("P2080", "Capteur température échappement banc 1 capt. 1 — circuit", "antipollution_fap_dpf", "warn"),
    ("P2088", "Solénoïde vanne arbre à cames échappement banc 1 — circuit bas", "moteur_distribution", "warn"),
    ("P2089", "Solénoïde vanne arbre à cames échappement banc 1 — circuit haut", "moteur_distribution", "warn"),
    ("P2096", "Post-cat fuel trim banc 1 — trop pauvre", "antipollution_catalyseur", "warn"),
    ("P2097", "Post-cat fuel trim banc 1 — trop riche", "antipollution_catalyseur", "warn"),
    ("P2098", "Post-cat fuel trim banc 2 — trop pauvre", "antipollution_catalyseur", "warn"),
    ("P2099", "Post-cat fuel trim banc 2 — trop riche", "antipollution_catalyseur", "warn"),
    ("P2100", "Actionneur papillon — circuit", "moteur_carburant_air", "warn"),
    ("P2101", "Actionneur papillon — performance", "moteur_carburant_air", "warn"),
    ("P2102", "Actionneur papillon — circuit bas", "moteur_carburant_air", "warn"),
    ("P2103", "Actionneur papillon — circuit haut", "moteur_carburant_air", "warn"),
    ("P2104", "Actionneur papillon — verrouillé en sécurité", "moteur_carburant_air", "critical"),
    ("P2105", "Actionneur papillon — verrouillé moteur arrêté", "moteur_carburant_air", "critical"),
    ("P2106", "Actionneur papillon — puissance limitée", "moteur_carburant_air", "warn"),
    ("P2107", "Actionneur papillon — défaut processeur", "moteur_carburant_air", "warn"),
    ("P2108", "Actionneur papillon — performance", "moteur_carburant_air", "warn"),
    ("P2109", "Capteur position papillon A — minimum verrouillé", "moteur_carburant_air", "warn"),
    ("P2110", "Actionneur papillon — limite forcée", "moteur_carburant_air", "warn"),
    ("P2111", "Actionneur papillon — bloqué ouvert", "moteur_carburant_air", "critical"),
    ("P2112", "Actionneur papillon — bloqué fermé", "moteur_carburant_air", "critical"),
    ("P2118", "Actionneur papillon courant moteur — plage", "moteur_carburant_air", "warn"),
    ("P2119", "Actionneur papillon corps — plage", "moteur_carburant_air", "warn"),
    ("P2120", "Capteur position pédale D — circuit", "moteur_carburant_air", "warn"),
    ("P2121", "Capteur position pédale D — performance", "moteur_carburant_air", "warn"),
    ("P2125", "Capteur position pédale E — circuit", "moteur_carburant_air", "warn"),
    ("P2126", "Capteur position pédale E — performance", "moteur_carburant_air", "warn"),
    ("P2135", "Papillon A/B — corrélation tensions", "moteur_carburant_air", "warn"),
    ("P2139", "Pédale F/G — corrélation tensions", "moteur_carburant_air", "warn"),
    ("P2176", "Position papillon — non apprise", "moteur_carburant_air", "warn"),
    ("P2177", "Mélange banc 1 — trop pauvre à régime stable", "moteur_carburant_air", "warn"),
    ("P2178", "Mélange banc 1 — trop riche à régime stable", "moteur_carburant_air", "warn"),
    ("P2186", "Capteur température admission B — circuit bas", "moteur_carburant_air", "warn"),
    ("P2187", "Mélange banc 1 — trop pauvre au ralenti", "moteur_carburant_air", "warn"),
    ("P2188", "Mélange banc 1 — trop riche au ralenti", "moteur_carburant_air", "warn"),
    ("P2189", "Mélange banc 2 — trop pauvre au ralenti", "moteur_carburant_air", "warn"),
    ("P2190", "Mélange banc 2 — trop riche au ralenti", "moteur_carburant_air", "warn"),
    ("P2195", "Sonde lambda banc 1 capt. 1 — signal collé pauvre", "antipollution_lambda", "warn"),
    ("P2196", "Sonde lambda banc 1 capt. 1 — signal collé riche", "antipollution_lambda", "warn"),
    ("P2197", "Sonde lambda banc 2 capt. 1 — signal collé pauvre", "antipollution_lambda", "warn"),
    ("P2198", "Sonde lambda banc 2 capt. 1 — signal collé riche", "antipollution_lambda", "warn"),
    ("P2237", "Sonde lambda A/F banc 1 capt. 1 — courant pompe — circuit", "antipollution_lambda", "warn"),
    ("P2238", "Sonde lambda A/F banc 1 capt. 1 — courant pompe — bas", "antipollution_lambda", "warn"),
    ("P2239", "Sonde lambda A/F banc 1 capt. 1 — courant pompe — haut", "antipollution_lambda", "warn"),
    ("P2243", "Sonde lambda A/F banc 1 capt. 1 — référence — circuit", "antipollution_lambda", "warn"),
    ("P2251", "Sonde lambda A/F banc 1 capt. 1 — masse négative — circuit", "antipollution_lambda", "warn"),
    ("P2270", "Sonde lambda banc 1 capt. 2 — collé pauvre", "antipollution_lambda", "warn"),
    ("P2271", "Sonde lambda banc 1 capt. 2 — collé riche", "antipollution_lambda", "warn"),
    ("P2299", "Frein/Accélérateur — pédales simultanées", "moteur_carburant_air", "warn"),
    ("P2300", "Bobine d'allumage A primaire — circuit bas", "moteur_allumage_rates", "warn", ),
    ("P2301", "Bobine d'allumage A primaire — circuit haut", "moteur_allumage_rates", "warn"),
    ("P2303", "Bobine B primaire — circuit bas", "moteur_allumage_rates", "warn"),
    ("P2304", "Bobine B primaire — circuit haut", "moteur_allumage_rates", "warn"),
    ("P2402", "EVAP — pompe détection fuite — circuit bas", "antipollution_evap", "warn", ),
    ("P2403", "EVAP — pompe détection fuite — circuit haut", "antipollution_evap", "warn", ),
    ("P2404", "EVAP — pompe détection fuite — détection fuite", "antipollution_evap", "warn", ),
    ("P2407", "EVAP — pompe — circuit intermittent", "antipollution_evap", "warn"),
    ("P2418", "EVAP — vanne ventilation — circuit bas", "antipollution_evap", "warn"),
    ("P2419", "EVAP — vanne ventilation — circuit haut", "antipollution_evap", "warn"),
    ("P2422", "EVAP — vanne ventilation — bloquée fermée", "antipollution_evap", "warn"),
    ("P2440", "Air secondaire vanne A banc 1 — bloquée ouverte", "antipollution_air_secondaire", "warn"),
    ("P2441", "Air secondaire vanne A banc 1 — bloquée fermée", "antipollution_air_secondaire", "warn"),
    ("P2444", "Air secondaire pompe banc 1 — bloquée ON", "antipollution_air_secondaire", "warn"),
    ("P2445", "Air secondaire pompe banc 1 — bloquée OFF", "antipollution_air_secondaire", "warn"),
    ("P2502", "Système alternateur — tension hors plage", "electronique_alimentation", "critical"),
    ("P2503", "Système alternateur — basse tension", "electronique_alimentation", "critical"),
    ("P2504", "Système alternateur — haute tension", "electronique_alimentation", "critical"),
    ("P2510", "Relais alimentation PCM — performance", "electronique_alimentation", "warn"),
    ("P2533", "Allumage clé — interrupteur — circuit", "electronique_alimentation", "warn"),
    ("P2544", "Demande couple transmission — circuit", "transmission_boite", "warn"),
    ("P2562", "Capteur position turbo — performance", "turbo_suralimentation", "warn"),
    ("P2564", "Capteur position turbo — circuit bas", "turbo_suralimentation", "warn"),
    ("P2565", "Capteur position turbo — circuit haut", "turbo_suralimentation", "warn"),
    ("P2566", "Capteur position turbo — intermittent", "turbo_suralimentation", "warn"),
    ("P2580", "Vanne contrôle turbo — circuit", "turbo_suralimentation", "warn"),
    ("P2599", "Vanne wastegate B — bloquée fermée", "turbo_suralimentation", "warn"),
    ("P2610", "ECM/PCM — timer interne — performance", "electronique_ecm_pcm", "warn"),
    ("P2700", "Solénoïde shift A — performance/bloqué OFF", "transmission_boite", "warn"),
    ("P2714", "Solénoïde pression D — bloqué OFF", "transmission_boite", "warn"),
    ("P2723", "Solénoïde pression E — bloqué OFF", "transmission_boite", "warn"),
    ("P2740", "Capteur température BV B — circuit", "transmission_boite", "warn"),
    ("P2762", "Embrayage convertisseur couple — circuit ouvert", "transmission_boite", "warn"),
    ("P2763", "Embrayage convertisseur couple — circuit haut", "transmission_boite", "warn"),
    ("P2764", "Embrayage convertisseur couple — circuit bas", "transmission_boite", "warn"),
    ("P2787", "Embrayage convertisseur — surchauffe", "transmission_boite", "critical"),
    ("P2800", "Capteur position levier sélecteur — circuit", "transmission_boite", "warn"),
    ("P28EF", "Capteur niveau réducteur (AdBlue) — niveau bas", "antipollution_scr_adblue", "warn", ),
]:
    add(code, lbl, fam, sev)

# ── U0xxx — Réseau CAN étendu ──
for code, lbl in [
    ("U0003", "Bus CAN haute vitesse — circuit bas"),
    ("U0004", "Bus CAN haute vitesse — circuit haut"),
    ("U0007", "Bus CAN basse vitesse — circuit"),
    ("U0010", "Bus CAN médium vitesse — circuit"),
    ("U0023", "Bus CAN B — circuit"),
    ("U0028", "Bus CAN B — défaut intermittent"),
    ("U0029", "Bus CAN B — défaut performance"),
    ("U0074", "Bus communication module — désactivé partiellement"),
    ("U0078", "Bus CAN — registre erreur"),
    ("U0102", "Perte communication avec module transfert"),
    ("U0103", "Perte communication avec module sélecteur shift"),
    ("U0104", "Perte communication avec module régulateur vitesse"),
    ("U0109", "Perte communication avec pompe carburant"),
    ("U0110", "Perte communication avec module commande hybride"),
    ("U0111", "Perte communication avec module commande batterie"),
    ("U0112", "Perte communication avec module monitoring batterie"),
    ("U0114", "Perte communication avec module 4WD"),
    ("U0122", "Perte communication avec module dynamique véhicule (VDM)"),
    ("U0123", "Perte communication avec capteur lacet"),
    ("U0124", "Perte communication avec capteur accélération latérale"),
    ("U0125", "Perte communication avec capteur accélération multi-axes"),
    ("U0126", "Perte communication avec angle volant"),
    ("U0128", "Perte communication avec module frein de stationnement"),
    ("U0129", "Perte communication avec module freinage"),
    ("U0130", "Perte communication avec module direction assistée"),
    ("U0131", "Perte communication avec module direction assistée"),
    ("U0136", "Perte communication avec module suspension"),
    ("U0140", "Perte communication avec BCM (module carrosserie)"),
    ("U0141", "Perte communication avec BCM A"),
    ("U0142", "Perte communication avec BCM B"),
    ("U0146", "Perte communication avec gateway A"),
    ("U0151", "Perte communication avec module airbag (SRS)"),
    ("U0152", "Perte communication avec module détection occupant"),
    ("U0156", "Perte communication avec module info-affichage"),
    ("U0158", "Perte communication avec compteur de bord"),
    ("U0159", "Perte communication avec module navigation"),
    ("U0164", "Perte communication avec HVAC (clim)"),
    ("U0166", "Perte communication avec module chauffage auxiliaire"),
    ("U0168", "Perte communication avec module immobilizer"),
    ("U0184", "Perte communication avec module audio"),
    ("U0186", "Perte communication avec amplificateur audio"),
    ("U0194", "Perte communication avec radio satellite"),
    ("U0212", "Perte communication avec module verrouillage colonne direction"),
    ("U0235", "Perte communication avec capteur radar de stationnement"),
    ("U0245", "Perte communication avec module multimédia DVD"),
    ("U0246", "Perte communication avec module ouverture portes"),
    ("U0293", "Perte communication avec module commande hybride pwr"),
    ("U0300", "Module internal — incompatibilité version"),
    ("U0401", "Données invalides reçues du ECM/PCM"),
    ("U0402", "Données invalides reçues du TCM (BV)"),
    ("U0415", "Données invalides reçues du module ABS"),
    ("U0418", "Données invalides reçues du module freinage"),
    ("U0422", "Données invalides reçues du BCM"),
    ("U0428", "Données invalides reçues de la direction assistée"),
]:
    add(code, lbl, "electronique_reseau_can",
        "critical" if "Perte communication" in lbl else "warn",
        vehicles=ALL_VEH)

# ── B0xxx — Carrosserie / airbags étendu ──
for code, lbl in [
    ("B0003", "Airbag conducteur — circuit court +12V"),
    ("B0004", "Airbag conducteur — circuit ouvert"),
    ("B0005", "Airbag conducteur — résistance hors plage"),
    ("B0011", "Airbag passager — circuit court masse"),
    ("B0012", "Airbag passager — circuit court +12V"),
    ("B0013", "Airbag passager — circuit ouvert"),
    ("B0022", "Airbag rideau latéral conducteur — défaut"),
    ("B0024", "Airbag rideau latéral passager — défaut"),
    ("B0026", "Prétensionneur ceinture conducteur — défaut"),
    ("B0028", "Prétensionneur ceinture passager — défaut"),
    ("B0030", "Capteur impact latéral conducteur — défaut"),
    ("B0035", "Capteur impact latéral passager — défaut"),
    ("B0040", "Capteur ceinture conducteur — défaut"),
    ("B0045", "Capteur ceinture passager — défaut"),
    ("B0051", "Capteur impact arrière — défaut"),
    ("B0055", "Capteur impact frontal central — défaut"),
    ("B0070", "Calculateur airbag — performance"),
    ("B0080", "Calculateur airbag — défaut interne"),
    ("B0081", "Calculateur airbag — tension d'alimentation"),
    ("B0083", "Calculateur airbag — communication"),
    ("B1000", "ECM — défaut interne ECM (Ford)"),
    ("B1001", "Module commande carrosserie — défaut"),
    ("B1318", "Tension batterie basse"),
    ("B1325", "Tension auxiliaire — circuit ouvert"),
    ("B1342", "ECM — défaut programme"),
    ("B1601", "Code clé PATS — non valide"),
    ("B2103", "Antenne immobilizer — circuit"),
    ("B2139", "Antenne immobilizer — données invalides"),
    ("B2603", "Verrouillage capot ouvert"),
]:
    add(code, lbl, "securite_airbags" if "Airbag" in lbl or "ceinture" in lbl.lower() or "impact" in lbl.lower() else "carrosserie_eclairage_confort",
        "critical" if "Airbag" in lbl or "Prétensionneur" in lbl else "warn",
        mil=False, vehicles=ALL_VEH)

# ── C0xxx — Châssis / ABS / ESP étendu ──
for code, lbl, fam in [
    ("C0036", "Capteur roue AVG — performance", "freinage_abs"),
    ("C0037", "Capteur roue AVG — circuit bas", "freinage_abs"),
    ("C0038", "Capteur roue AVG — circuit haut", "freinage_abs"),
    ("C0039", "Capteur roue AVG — intermittent", "freinage_abs"),
    ("C0041", "Capteur roue AVD — performance", "freinage_abs"),
    ("C0042", "Capteur roue AVD — circuit bas", "freinage_abs"),
    ("C0043", "Capteur roue AVD — circuit haut", "freinage_abs"),
    ("C0046", "Capteur roue ARG — performance", "freinage_abs"),
    ("C0047", "Capteur roue ARG — circuit bas", "freinage_abs"),
    ("C0048", "Capteur roue ARG — circuit haut", "freinage_abs"),
    ("C0051", "Capteur roue ARD — performance", "freinage_abs"),
    ("C0052", "Capteur roue ARD — circuit bas", "freinage_abs"),
    ("C0053", "Capteur roue ARD — circuit haut", "freinage_abs"),
    ("C0060", "Pompe ABS — circuit", "freinage_abs"),
    ("C0062", "Valve isolation roue AVG — circuit", "freinage_abs"),
    ("C0063", "Valve isolation roue AVD — circuit", "freinage_abs"),
    ("C0064", "Valve isolation roue ARG — circuit", "freinage_abs"),
    ("C0065", "Valve isolation roue ARD — circuit", "freinage_abs"),
    ("C0068", "Valve de dump roue AVG — circuit", "freinage_abs"),
    ("C0070", "Valve de dump roue AVD — circuit", "freinage_abs"),
    ("C0072", "Valve de dump roue ARG — circuit", "freinage_abs"),
    ("C0074", "Valve de dump roue ARD — circuit", "freinage_abs"),
    ("C0121", "Valve relais ABS — circuit", "freinage_abs"),
    ("C0131", "Pression frein — circuit", "freinage_abs"),
    ("C0186", "Capteur accélération latérale — circuit", "esp_stabilite_traction"),
    ("C0198", "Capteur angle volant — circuit", "esp_stabilite_traction"),
    ("C0199", "Capteur angle volant — performance", "esp_stabilite_traction"),
    ("C0205", "ABS — perte fonctionnalité", "freinage_abs"),
    ("C0220", "ESP — Désactivation système (utilisateur)", "esp_stabilite_traction"),
    ("C0241", "Contacteur frein — circuit", "freinage_abs"),
    ("C0245", "Capteur vitesse — variation excessive", "freinage_abs"),
    ("C0271", "Calculateur EBCM — performance interne", "freinage_abs"),
    ("C0286", "Régulateur vitesse adaptatif — défaut", "esp_stabilite_traction"),
    ("C0561", "ESP — système désactivé par dégradation", "esp_stabilite_traction"),
    ("C0710", "Direction assistée — circuit", "direction_assistee"),
    ("C0800", "Module — tension alimentation basse", "freinage_abs"),
    ("C1095", "Pompe ABS — surcharge moteur", "freinage_abs"),
    ("C1145", "Capteur roue AVG — fréquence anormale", "freinage_abs"),
    ("C1188", "Capteur lacet — performance", "esp_stabilite_traction"),
]:
    add(code, lbl, fam,
        "critical" if "pompe" in lbl.lower() or "EBCM" in lbl or "perte" in lbl.lower() else "warn",
        mil=False, vehicles=ALL_VEH)

# ── P1xxx — Constructeurs (échantillon élargi) ──
# Renault
for code, lbl in [
    ("P1102", "MAF — tension inférieure à plage attendue"),
    ("P1103", "MAF — tension supérieure à plage attendue"),
    ("P1115", "Capteur température culasse — circuit"),
    ("P1116", "Capteur température culasse — plage"),
    ("P1126", "Capteur pression admission — défaut"),
    ("P1133", "Sonde lambda banc 1 capteur 1 — basculement insuffisant"),
    ("P1135", "Sonde lambda banc 1 capteur 1 — chauffage circuit"),
    ("P1141", "Sonde lambda banc 1 capteur 2 — pas basculement"),
    ("P1196", "Pompe carburant — performance"),
    ("P1213", "Injecteur cylindre 1 — circuit court à +"),
    ("P1235", "Pompe carburant primaire — désactivée"),
    ("P1259", "Capteur position embrayage — performance"),
    ("P1313", "Allumage cylindre 1 — perte primaire"),
    ("P1335", "Capteur vilebrequin — pas de signal — moteur tournant"),
    ("P1336", "Capteur vilebrequin — apprentissage hors plage"),
    ("P1338", "Capteur pression différentielle FAP — corrélation"),
    ("P1339", "Capteur position vilebrequin — phasage déphasé"),
    ("P1351", "Préchauffage — circuit ouvert"),
    ("P1352", "Préchauffage — circuit court masse"),
    ("P1391", "Capteur vilebrequin — variation glitch"),
    ("P1402", "EGR vanne — signal sortie hors plage"),
    ("P1410", "Pompe carburant — circuit court à masse"),
    ("P1471", "Pression atmosphérique — capteur"),
    ("P1480", "FAP — additif Eolys — niveau bas"),
    ("P1481", "FAP — actuateur additif — circuit"),
    ("P1490", "FAP — vanne EGR — défaut"),
    ("P1495", "FAP — additif Eolys — concentration"),
    ("P1496", "FAP — additif Eolys — fuite"),
    ("P1497", "FAP — additif Eolys — défaut conditionnement"),
    ("P1498", "FAP — capteur température aval — corrélation"),
    ("P1547", "Réchauffeur intercooler — circuit"),
    ("P1611", "Calculateur — défaut interne mémoire"),
    ("P1620", "Carte SIM module télématique — défaut"),
    ("P1693", "Préchauffage — bougie cylindre 1"),
    ("P1694", "Préchauffage — bougie cylindre 2"),
    ("P1695", "Préchauffage — bougie cylindre 3"),
    ("P1696", "Préchauffage — bougie cylindre 4"),
]:
    add(code, f"{lbl} (Renault)", "moteur_carburant_air" if "MAF" in lbl else
                                  "antipollution_lambda" if "lambda" in lbl.lower() else
                                  "antipollution_fap_dpf" if "FAP" in lbl else
                                  "prechauffage_diesel" if "Préchauffage" in lbl or "préchauffage" in lbl else
                                  "moteur_injection_hp" if "injecteur" in lbl.lower() or "pompe carburant" in lbl.lower() else
                                  "moteur_distribution" if "vilebrequin" in lbl.lower() else
                                  "antipollution_egr" if "EGR" in lbl else
                                  "moteur_allumage_rates" if "Allumage" in lbl else
                                  "electronique_ecm_pcm",
        vehicles=THERM_HYB)

# PSA (Peugeot Citroën)
for code, lbl, fam in [
    ("P1351", "Préchauffage — circuit (PSA)", "prechauffage_diesel"),
    ("P1352", "Préchauffage — relais (PSA)", "prechauffage_diesel"),
    ("P1397", "Capteur AAC — signal hors plage (PSA)", "moteur_distribution"),
    ("P1400", "EGR — solénoïde — circuit (PSA)", "antipollution_egr"),
    ("P1408", "EGR — capteur pression différentielle (PSA)", "antipollution_egr"),
    ("P1500", "Relais pompe carburant — circuit (PSA)", "moteur_injection_hp"),
    ("P1531", "Solénoïde turbo — bloqué (PSA)", "turbo_suralimentation"),
    ("P1561", "Régulateur pression carburant — circuit (PSA)", "moteur_injection_hp"),
    ("P1611", "Calculateur — défaut interne (PSA)", "electronique_ecm_pcm"),
    ("P1635", "Bus CAN — défaut (PSA)", "electronique_reseau_can"),
    ("P1640", "Calculateur — erreur EEPROM (PSA)", "electronique_ecm_pcm"),
]:
    add(code, lbl, fam, vehicles=THERM_HYB)

# Mercedes
for code, lbl, fam, sev in [
    ("P11AB", "AdBlue — capteur qualité (Mercedes)", "antipollution_scr_adblue", "critical"),
    ("P11AC", "AdBlue — capteur qualité — circuit (Mercedes)", "antipollution_scr_adblue", "warn"),
    ("P11D9", "AdBlue — performance système (Mercedes)", "antipollution_scr_adblue", "critical"),
    ("P11DA", "AdBlue — module dosage performance (Mercedes)", "antipollution_scr_adblue", "warn"),
    ("P11E0", "AdBlue — chauffage réservoir circuit (Mercedes)", "antipollution_scr_adblue", "warn"),
    ("P1402", "EGR — vanne — performance (Mercedes)", "antipollution_egr", "warn"),
    ("P1420", "Catalyseur SCR — efficacité insuffisante (Mercedes)", "antipollution_scr_adblue", "critical"),
    ("P1430", "FAP — colmaté (Mercedes)", "antipollution_fap_dpf", "critical"),
]:
    add(code, lbl, fam, sev, vehicles=DIESEL)

# VW / Audi / Skoda / Seat
for code, lbl, fam in [
    ("P1128", "Mélange banc 1 — limite contrôlée (VAG)", "moteur_carburant_air"),
    ("P1136", "Mélange banc 1 — pauvre détecté (VAG)", "moteur_carburant_air"),
    ("P1137", "Mélange banc 1 — riche détecté (VAG)", "moteur_carburant_air"),
    ("P1297", "Suralimentation — différentiel pression (VAG)", "turbo_suralimentation"),
    ("P1340", "AAC / vilebrequin — corrélation (VAG)", "moteur_distribution"),
    ("P1381", "Préchauffage — circuit (VAG)", "prechauffage_diesel"),
    ("P1556", "Suralimentation — vanne de régulation (VAG)", "turbo_suralimentation"),
    ("P1602", "Tension batterie alim. terminal 30 — basse (VAG)", "electronique_alimentation"),
    ("P1611", "Lampe MIL — circuit défaillant (VAG)", "electronique_ecm_pcm"),
    ("P1613", "Lampe MIL — circuit court masse (VAG)", "electronique_ecm_pcm"),
    ("P1626", "Bus CAN — message manquant ABS (VAG)", "electronique_reseau_can"),
    ("P1648", "Bus CAN — défaut interface (VAG)", "electronique_reseau_can"),
    ("P1769", "BV automatique — solénoïde de pression — bloqué (VAG)", "transmission_boite"),
    ("P1788", "BV automatique — solénoïde 2-3 — circuit (VAG)", "transmission_boite"),
]:
    add(code, lbl, fam, vehicles=THERM_HYB,
        mil=fam != "transmission_boite")

# BMW
for code, lbl, fam in [
    ("P1120", "Sonde lambda chauffage A — circuit (BMW)", "antipollution_lambda"),
    ("P1188", "Mélange banc 1 — adaptation valeur appauvri (BMW)", "moteur_carburant_air"),
    ("P1189", "Mélange banc 1 — adaptation valeur enrichi (BMW)", "moteur_carburant_air"),
    ("P1247", "Solénoïde wastegate — défaut (BMW)", "turbo_suralimentation"),
    ("P1396", "Capteur vilebrequin — signal interrompu (BMW)", "moteur_distribution"),
    ("P1432", "Sondes lambda — chauffage parallèle (BMW)", "antipollution_lambda"),
    ("P1518", "Pompe carburant haute pression — pression (BMW)", "moteur_injection_hp"),
    ("P1623", "Lampe MIL — circuit ouvert (BMW)", "electronique_ecm_pcm"),
    ("P1801", "Verrouillage convertisseur — fonctionnement (BMW)", "transmission_boite"),
]:
    add(code, lbl, fam, vehicles=THERM_HYB,
        mil=fam != "transmission_boite")

# Ford
for code, lbl, fam in [
    ("P1131", "Mélange banc 1 — limite carburant pauvre (Ford)", "moteur_carburant_air"),
    ("P1132", "Mélange banc 1 — limite carburant riche (Ford)", "moteur_carburant_air"),
    ("P1138", "Mélange banc 2 — limite carburant riche (Ford)", "moteur_carburant_air"),
    ("P1233", "Pompe carburant — circuit alim (Ford)", "moteur_injection_hp"),
    ("P1391", "Préchauffage — circuit (Ford)", "prechauffage_diesel"),
    ("P1450", "EVAP — pression — défaut (Ford)", "antipollution_evap"),
    ("P1605", "ECM — diagnostic test mode défaillant (Ford)", "electronique_ecm_pcm"),
]:
    add(code, lbl, fam, vehicles=THERM_HYB)

# Fiat
for code, lbl, fam in [
    ("P1107", "Capteur MAP — circuit basse pression (Fiat)", "moteur_carburant_air"),
    ("P1180", "Pression carburant — limite basse (Fiat)", "moteur_injection_hp"),
    ("P1238", "Injecteur cylindre 1 — circuit (Fiat)", "moteur_injection_hp"),
    ("P1408", "EGR — capteur — circuit (Fiat)", "antipollution_egr"),
    ("P1442", "EVAP — vanne ventilation — défaut (Fiat)", "antipollution_evap"),
]:
    add(code, lbl, fam, vehicles=THERM_HYB)

# ── Codes informationnels supplémentaires ──
add("P1500", "Information OBD2 — cycle conduite complété", "non_classe", "info", mil=False)

# ── Post-traitement : les codes transmission/embrayage n'allument PAS le
# voyant antipollution (voyant transmission séparé). On force mil=False
# pour toutes les familles correspondantes.
_NO_MIL_FAMILIES = {"transmission_boite", "transmission_embrayage",
                    "freinage_abs", "esp_stabilite_traction",
                    "direction_assistee", "securite_airbags",
                    "carrosserie_eclairage_confort"}
for _c, _v in CODES.items():
    if _v["family"] in _NO_MIL_FAMILIES:
        _v["mil"] = False

out = {
    "_meta": {
        "version": "1.0",
        "generated_by": "analysis/build_dtc_codes.py",
        "schema": "code: { fr, family, severity, vehicles, mil }",
        "families": FAMILIES,
    },
    "codes": dict(sorted(CODES.items())),
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)

# Stats
from collections import Counter
fam_count = Counter(c["family"] for c in CODES.values())
sev_count = Counter(c["severity"] for c in CODES.values())
veh_count = Counter()
for c in CODES.values():
    for v in c["vehicles"]:
        veh_count[v] += 1

sys.stdout.reconfigure(encoding="utf-8")
print(f"[OK] {len(CODES)} codes ecrits dans {OUT}")
print(f"     Familles utilisees : {len(fam_count)}/{len(FAMILIES)}")
print(f"     Severity : {dict(sev_count)}")
print(f"     Vehicules : {dict(veh_count)}")
print(f"     Top 5 familles : {fam_count.most_common(5)}")
