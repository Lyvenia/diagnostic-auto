"""
Décodage VIN — pipeline intelligent EU/US + base locale enrichie + validation.

Pipeline par ordre de priorité :
  VIN européen → Local WMI → NHTSA → Claude Sonnet
  VIN américain → NHTSA → Local WMI → Claude Sonnet
  VIN invalide  → erreur explicite immédiate (pas d'appel API inutile)
"""
import json
import os
import re
import time as _t
import anthropic
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from core.paths import data_path, LOG_PATH

_client = None


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [vin] {msg}\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Client Anthropic
# ─────────────────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    config_path = data_path("config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("anthropic_api_key", "").strip()
            if key:
                return key
        except Exception:
            pass
    raise ValueError(
        "Clé API Anthropic non trouvée. "
        "Définissez ANTHROPIC_API_KEY dans l'environnement "
        "ou dans le champ 'anthropic_api_key' de config.json."
    )


def _get_client():
    global _client
    if _client is None:
        try:
            from core.variant import CLIENT_BUILD
        except ImportError:
            CLIENT_BUILD = False
        if CLIENT_BUILD:
            from core.lyvenia_client import LyveniaAIClient
            _client = LyveniaAIClient()
        else:
            _client = anthropic.Anthropic(api_key=_get_api_key())
    return _client


# ─────────────────────────────────────────────────────────────────────────────
# Validation VIN
# ─────────────────────────────────────────────────────────────────────────────

# Caractères interdits dans un VIN standard (I, O, Q)
_VIN_FORBIDDEN = set("IOQ")
# Caractères autorisés : A-Z (sauf IOQ) + 0-9
_VIN_VALID_CHARS = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')

def validate_vin(vin: str) -> tuple[bool, str]:
    """
    Valide le format du VIN.
    Retourne (True, '') si valide, (False, raison) sinon.
    """
    if not vin:
        return False, "VIN vide"
    vin = vin.strip().upper()
    if len(vin) < 11:
        return False, f"VIN trop court ({len(vin)} caractères, minimum 11)"
    if len(vin) != 17:
        # On accepte les VINs < 17 chars pour les vieux véhicules (avant 1980)
        if len(vin) < 11:
            return False, f"VIN invalide ({len(vin)} caractères)"
        return True, ""   # tolérance pour véhicules anciens
    if not _VIN_VALID_CHARS.match(vin):
        invalid = [c for c in vin if c in _VIN_FORBIDDEN or not c.isalnum()]
        return False, f"VIN contient des caractères invalides : {', '.join(set(invalid))}"
    return True, ""


def _clean_vin(vin: str) -> str:
    """Nettoie le VIN : strip, majuscules, supprime espaces parasites."""
    return vin.strip().upper().replace(" ", "").replace("\x00", "")


# ─────────────────────────────────────────────────────────────────────────────
# Détection origine VIN (EU / US / Asie)
# ─────────────────────────────────────────────────────────────────────────────

# Premier caractère du VIN → région de fabrication
_VIN_REGION = {
    # Amérique du Nord
    '1': 'US', '2': 'Canada', '3': 'Mexico',
    '4': 'US', '5': 'US',
    # Europe
    'S': 'EU',  # UK
    'T': 'EU',  # Hongrie, Rep. Tchèque
    'U': 'EU',  # Roumanie, Pologne
    'V': 'EU',  # France, Espagne, Pays-Bas
    'W': 'EU',  # Allemagne
    'X': 'EU',  # Russie
    'Y': 'EU',  # Suède, Finlande, Belgique
    'Z': 'EU',  # Italie
    # Asie
    'J': 'Japan', 'K': 'Korea', 'L': 'China',
    'M': 'Asia',  'N': 'Asia',
    # Afrique / Australie / Reste
    '6': 'Australia', '7': 'NZ', '8': 'Argentina', '9': 'Brazil',
    'A': 'Africa',
}

def _is_european_vin(vin: str) -> bool:
    return _VIN_REGION.get(vin[0].upper(), '') == 'EU'

def _is_american_vin(vin: str) -> bool:
    return _VIN_REGION.get(vin[0].upper(), '') in ('US', 'Canada', 'Mexico')


# ─────────────────────────────────────────────────────────────────────────────
# Base de données WMI — Marques (3 caractères)
# ─────────────────────────────────────────────────────────────────────────────

WMI_MAP = {
    # ── France ──────────────────────────────────────────────────────────────
    "VF1": "Renault",       "VF2": "Renault",       "VF3": "Peugeot",
    "VF4": "Talbot",        "VF6": "Renault",        "VF7": "Citroën",
    "VF8": "Matra",         "VFA": "Renault",        "VFB": "Renault",
    "VFC": "Citroën",       "VFD": "Peugeot",        "VFE": "Peugeot",
    "VFF": "Citroën",       "VFG": "Alpine",         "VFH": "Citroën",
    "VFJ": "Peugeot",       "VFK": "Citroën",        "VFN": "Renault",
    "VFP": "Renault",       "VFR": "Renault",        "VFS": "Citroën",
    "VFT": "Citroën",       "VFU": "Citroën",        "VFV": "Peugeot",
    "VFX": "Peugeot",       "VFY": "Citroën",        "VF3": "Peugeot",
    "VS7": "DS Automobiles","VSA": "DS Automobiles", "VR1": "Alpine",
    "VRE": "Alpine",        "VNA": "Renault",        "VNB": "Renault",
    "VNE": "Renault",
    # ── Allemagne ────────────────────────────────────────────────────────────
    "WBA": "BMW",           "WBS": "BMW M",          "WBY": "BMW i",
    "WBX": "BMW X",
    "WDB": "Mercedes-Benz", "WDC": "Mercedes-Benz",
    "WDD": "Mercedes-Benz", "WDF": "Mercedes-Benz",
    "WEB": "Mercedes-Benz EQ",
    "WVW": "Volkswagen",    "WV1": "Volkswagen",     "WV2": "Volkswagen",
    "WV3": "Volkswagen",
    "WAU": "Audi",          "WUA": "Audi RS",        "WAP": "Porsche",
    "WP0": "Porsche",       "WP1": "Porsche",
    "WMA": "MAN",           "WMW": "MINI",           "WME": "Smart",
    "W0L": "Opel",          "W0V": "Opel",
    "TRU": "Audi Hongrie",  "TBN": "MAN",
    # ── Espagne ──────────────────────────────────────────────────────────────
    "VSS": "SEAT",          "VS6": "SEAT",           "VS7": "SEAT",
    "VNE": "SEAT",          "VN1": "SEAT",           "VSK": "SEAT",
    # ── Belgique ─────────────────────────────────────────────────────────────
    "YV4": "Volvo Cars Belgique",
    # ── Pays-Bas ─────────────────────────────────────────────────────────────
    "XLR": "DAF",           "XL8": "Donkervoort",   "XLE": "Spijkstaal",
    # ── République Tchèque / Slovaquie ───────────────────────────────────────
    "TMB": "Škoda",         "TMA": "Škoda",
    "TM9": "Škoda",         "TMK": "Škoda",
    "TM8": "Škoda",
    # ── Hongrie ──────────────────────────────────────────────────────────────
    "TRU": "Audi Hongrie",  "AAV": "Suzuki Hongrie",
    # ── Pologne ──────────────────────────────────────────────────────────────
    "SUF": "Fiat Pologne",  "SBF": "Fiat Pologne",
    # ── Roumanie ─────────────────────────────────────────────────────────────
    "UU1": "Dacia",         "UU2": "Dacia",          "UU3": "Dacia",
    # ── Turquie ──────────────────────────────────────────────────────────────
    "NMT": "Toyota Türkiye","TMT": "Tofaş (Fiat TR)","TMA": "Oyak Renault TR",
    # ── Italie ───────────────────────────────────────────────────────────────
    "ZAR": "Alfa Romeo",    "ZAM": "Maserati",
    "ZFF": "Ferrari",       "ZHW": "Lamborghini",
    "ZLA": "Lancia",        "ZFA": "Fiat",
    "ZFC": "Fiat",          "ZFB": "Fiat",
    "ZAA": "Fiat",          "ZAP": "Fiat",
    "ZCA": "Fiat",          "ZCF": "Fiat",
    # ── Royaume-Uni ──────────────────────────────────────────────────────────
    "SAJ": "Jaguar",        "SAL": "Land Rover",     "SAR": "Range Rover",
    "SCF": "Aston Martin",  "SFD": "Bentley",
    "SCC": "Lotus",         "SAB": "Saab (UK)",
    "SBM": "McLaren",       "SDB": "Jaguar",
    # ── Suède ────────────────────────────────────────────────────────────────
    "YV1": "Volvo",         "YV2": "Volvo",          "YV3": "Volvo",
    "YV4": "Volvo",         "YS2": "Scania",
    "YS3": "Saab",          "YS4": "Saab",
    "XL9": "Spyker",
    # ── Russie ───────────────────────────────────────────────────────────────
    "XTA": "Lada (AvtoVAZ)","XTT": "GAZ",
    # ── Japon ────────────────────────────────────────────────────────────────
    "JHM": "Honda",         "JH4": "Acura",
    "JTD": "Toyota",        "JTH": "Lexus",          "JTE": "Toyota",
    "JTK": "Toyota",        "JTJ": "Lexus",
    "JN1": "Nissan",        "JN6": "Nissan",         "JN8": "Nissan",
    "JS1": "Suzuki",        "JS2": "Suzuki",         "JS3": "Suzuki",
    "JM1": "Mazda",         "JM3": "Mazda",          "JM0": "Mazda",
    "JA3": "Mitsubishi",    "JA4": "Mitsubishi",     "JA9": "Mitsubishi",
    "JF1": "Subaru",        "JF2": "Subaru",
    # ── Corée ────────────────────────────────────────────────────────────────
    "KMH": "Hyundai",       "KMF": "Hyundai",        "KMJ": "Hyundai",
    "KNA": "Kia",           "KNB": "Kia",            "KNC": "Kia",
    "KPT": "SsangYong",     "KL1": "Chevrolet Korea",
    # ── USA ──────────────────────────────────────────────────────────────────
    "1G1": "Chevrolet",     "1G6": "Cadillac",       "1G4": "Buick",
    "1FT": "Ford",          "1FA": "Ford",           "1FM": "Ford",
    "1FD": "Ford",          "1FC": "Ford",
    "1HG": "Honda USA",     "1J4": "Jeep",           "1C4": "Chrysler",
    "1C3": "Chrysler",      "1B3": "Dodge",          "2T1": "Toyota Canada",
    "1N4": "Nissan USA",    "1N6": "Nissan USA",
    "2HG": "Honda Canada",  "3VW": "Volkswagen Mexique",
    # ── Chine ────────────────────────────────────────────────────────────────
    "LVS": "Ford Chine",    "LFV": "Volkswagen Chine",
    "LSG": "General Motors Chine", "LHG": "Honda Chine",
    "LNB": "Toyota Chine",
}


# ─────────────────────────────────────────────────────────────────────────────
# Base de données WMI étendue — Modèles (4 caractères)
# ─────────────────────────────────────────────────────────────────────────────

WMI_MODEL_MAP = {
    # ── Renault (VF1) ────────────────────────────────────────────────────────
    "VF1A": "Twingo",       "VF1B": "Clio",          "VF1C": "Mégane",
    "VF1D": "Laguna",       "VF1E": "Espace",        "VF1F": "Kangoo",
    "VF1G": "Scenic",       "VF1H": "Vel Satis",     "VF1J": "Trafic",
    "VF1K": "Koleos",       "VF1L": "Clio",          "VF1M": "Mégane",
    "VF1N": "Mégane",       "VF1P": "Scenic",        "VF1R": "Laguna",
    "VF1S": "Master",       "VF1T": "Trafic",        "VF1U": "Modus",
    "VF1W": "Fluence",      "VF1X": "Zoe",           "VF1Y": "Captur",
    "VF1Z": "Clio",         "VF15": "Twingo",        "VF16": "Clio",
    "VF17": "Clio",         "VF18": "Kangoo",        "VF19": "Kadjar",
    # Renault récents (VF1 série numérique)
    "VF10": "Kangoo",       "VF11": "Captur",        "VF12": "Arkana",
    "VF13": "Espace",       "VF14": "Rafale",
    # ── Renault (VF6 — véhicules utilitaires) ────────────────────────────────
    "VF6H": "Master",       "VF6N": "Master",        "VF6P": "Trafic",
    "VF6R": "Trafic",       "VF6S": "Trafic",
    # ── Peugeot (VF3) ────────────────────────────────────────────────────────
    "VF3A": "106",          "VF3B": "206",           "VF3C": "307",
    "VF3D": "405",          "VF3E": "406",           "VF3F": "407",
    "VF3G": "607",          "VF3H": "807",           "VF3J": "2008",
    "VF3K": "3008",         "VF3L": "5008",          "VF3M": "508",
    "VF3N": "308",          "VF3P": "108",           "VF3R": "208",
    "VF3T": "Boxer",        "VF3U": "Expert",        "VF3V": "Partner",
    "VF3S": "308",          "VF3X": "408",           "VF3Y": "e-208",
    "VF33": "307",          "VF34": "407",           "VF35": "206",
    "VF36": "206",          "VF37": "207",           "VF38": "308",
    "VF39": "3008",         "VF30": "Boxer",
    # Peugeot récents
    "VF31": "208",          "VF32": "2008",
    # ── Citroën (VF7) ────────────────────────────────────────────────────────
    "VF7A": "C1",           "VF7B": "C2",            "VF7C": "C3",
    "VF7D": "C4",           "VF7E": "C5",            "VF7F": "C6",
    "VF7G": "C8",           "VF7H": "Berlingo",      "VF7J": "Dispatch",
    "VF7K": "Jumper",       "VF7L": "Jumpy",         "VF7M": "C-Elysée",
    "VF7N": "C3 Picasso",   "VF7P": "C4 Picasso",    "VF7R": "C4 Cactus",
    "VF7S": "C3 Aircross",  "VF7T": "C5 Aircross",   "VF7U": "C3",
    "VF7V": "Berlingo",     "VF7W": "C4",            "VF7X": "C5 X",
    "VF75": "C3",           "VF77": "C4",            "VF78": "C5",
    # ── DS Automobiles ───────────────────────────────────────────────────────
    "VS7A": "DS3",          "VS7B": "DS4",           "VS7C": "DS5",
    "VS7D": "DS7",          "VS7E": "DS9",
    # ── Dacia (UU1) ──────────────────────────────────────────────────────────
    "UU1A": "Sandero",      "UU1B": "Logan",         "UU1C": "Duster",
    "UU1D": "Lodgy",        "UU1E": "Dokker",        "UU1F": "Spring",
    "UU1G": "Jogger",       "UU1H": "Bigster",       "UU1J": "Sandero",
    "UU1K": "Logan",        "UU1L": "Duster",
    # ── Volkswagen (WVW) ─────────────────────────────────────────────────────
    "WVWA": "Golf",         "WVWB": "Polo",          "WVWC": "Passat",
    "WVWD": "Tiguan",       "WVWE": "Touareg",       "WVWF": "Phaeton",
    "WVWG": "Sharan",       "WVWH": "Touran",        "WVWJ": "Jetta",
    "WVWK": "New Beetle",   "WVWL": "Caddy",         "WVWM": "T-Roc",
    "WVWN": "Golf",         "WVWP": "Polo",          "WVWZ": "ID.3",
    "WVW1": "ID.4",         "WVW2": "ID.5",
    # ── Audi (WAU) ───────────────────────────────────────────────────────────
    "WAUC": "A4",           "WAUD": "A6",            "WAUE": "A8",
    "WAUHZ": "A3",          "WAUF": "A5",            "WAUG": "A7",
    "WAUJ": "Q5",           "WAUK": "Q3",            "WAUL": "Q7",
    "WAUM": "Q8",           "WAUN": "e-tron",        "WAUP": "TT",
    "WAUR": "R8",           "WAUA": "A1",            "WAUB": "A3",
    # ── BMW (WBA) ────────────────────────────────────────────────────────────
    "WBA1": "Série 1",      "WBA2": "Série 2",       "WBA3": "Série 3",
    "WBA4": "Série 4",      "WBA5": "Série 5",       "WBA6": "Série 6",
    "WBA7": "Série 7",      "WBA8": "Série 8",       "WBAA": "Série 1",
    "WBAB": "Série 2",      "WBAC": "Série 3",       "WBAD": "Série 4",
    "WBAE": "Série 5",      "WBAF": "Série 6",       "WBAG": "Série 7",
    "WBAH": "X1",           "WBAJ": "X2",            "WBAK": "X3",
    "WBAL": "X4",           "WBAM": "X5",            "WBAN": "X6",
    "WBAP": "X7",           "WBAV": "i3",            "WBAW": "i8",
    "WBAX": "iX",
    # ── Mercedes-Benz (WDB/WDD) ──────────────────────────────────────────────
    "WDBA": "Classe A",     "WDBB": "Classe B",      "WDBC": "Classe C",
    "WDBD": "Classe D",     "WDBE": "Classe E",      "WDBF": "Classe G",
    "WDBG": "Classe GL",    "WDBH": "Classe M/GLE",  "WDBJ": "Classe S",
    "WDDA": "Classe A",     "WDDB": "Classe B",      "WDDC": "Classe C",
    "WDDE": "Classe E",     "WDDF": "Classe G",      "WDDG": "GLC",
    "WDDH": "GLE",          "WDDJ": "Classe S",      "WDDK": "GLS",
    "WDDL": "EQC",          "WDDM": "EQA",           "WDDN": "EQB",
    # ── Škoda (TMB) ──────────────────────────────────────────────────────────
    "TMBA": "Octavia",      "TMBB": "Fabia",         "TMBC": "Superb",
    "TMBD": "Rapid",        "TMBE": "Yeti",          "TMBF": "Roomster",
    "TMBG": "Kodiaq",       "TMBH": "Karoq",         "TMBJ": "Scala",
    "TMBK": "Kamiq",        "TMBM": "Enyaq",
    # ── Alfa Romeo (ZAR) ─────────────────────────────────────────────────────
    "ZARA": "147",          "ZARB": "156",           "ZARC": "166",
    "ZARD": "GT",           "ZARE": "Brera",         "ZARF": "Spider",
    "ZARG": "Giulietta",    "ZARH": "MiTo",          "ZARJ": "Giulia",
    "ZARK": "Stelvio",      "ZARL": "Tonale",
    # ── Fiat (ZFA) ───────────────────────────────────────────────────────────
    "ZFAA": "500",          "ZFAB": "Panda",         "ZFAC": "Punto",
    "ZFAD": "Bravo",        "ZFAE": "Tipo",          "ZFAF": "Doblo",
    "ZFAG": "Qubo",         "ZFAH": "Fiorino",       "ZFAJ": "Ducato",
    # ── Volvo (YV1) ──────────────────────────────────────────────────────────
    "YV1A": "S40",          "YV1B": "V40",           "YV1C": "S60",
    "YV1D": "V60",          "YV1E": "S80",           "YV1F": "V70",
    "YV1G": "XC60",         "YV1H": "XC70",          "YV1J": "XC90",
    "YV1K": "S90",          "YV1L": "V90",           "YV1M": "XC40",
    "YV1N": "C40",          "YV1P": "EX40",
    # ── Toyota (JTD/JTE) ─────────────────────────────────────────────────────
    "JTDA": "Yaris",        "JTDB": "Corolla",       "JTDC": "Camry",
    "JTDD": "Avensis",      "JTDE": "Auris",         "JTDF": "RAV4",
    "JTDG": "Land Cruiser", "JTDH": "Prius",         "JTDJ": "C-HR",
    "JTDK": "Aygo",         "JTDL": "Yaris Cross",
    # ── Honda (JHM) ──────────────────────────────────────────────────────────
    "JHMA": "Jazz",         "JHMB": "Civic",         "JHMC": "Accord",
    "JHMD": "CR-V",         "JHME": "HR-V",          "JHMF": "e",
    # ── Nissan (JN1) ─────────────────────────────────────────────────────────
    "JN1A": "Micra",        "JN1B": "Note",          "JN1C": "Juke",
    "JN1D": "Qashqai",      "JN1E": "X-Trail",       "JN1F": "Leaf",
    "JN1G": "Navara",
    # ── Hyundai (KMH) ────────────────────────────────────────────────────────
    "KMHA": "i10",          "KMHB": "i20",           "KMHC": "i30",
    "KMHD": "i40",          "KMHE": "Tucson",        "KMHF": "Santa Fe",
    "KMHG": "Ioniq",        "KMHH": "Kona",          "KMHJ": "Ioniq 5",
    # ── Kia (KNA) ────────────────────────────────────────────────────────────
    "KNAA": "Picanto",      "KNAB": "Rio",           "KNAC": "Ceed",
    "KNAD": "Sportage",     "KNAE": "Sorento",       "KNAF": "EV6",
    "KNAG": "Niro",         "KNAH": "Stonic",
    # ── SEAT (VSS) ───────────────────────────────────────────────────────────
    "VSSA": "Ibiza",        "VSSB": "Leon",          "VSSC": "Altea",
    "VSSD": "Arona",        "VSSE": "Ateca",         "VSSF": "Tarraco",
    "VSSG": "Born",
}


# ─────────────────────────────────────────────────────────────────────────────
# Codes années VIN
# ─────────────────────────────────────────────────────────────────────────────

YEAR_CODES = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984,
    "F": 1985, "G": 1986, "H": 1987, "J": 1988, "K": 1989,
    "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994,
    "S": 1995, "T": 1996, "V": 1997, "W": 1998, "X": 1999,
    "Y": 2000, "1": 2001, "2": 2002, "3": 2003, "4": 2004,
    "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

_post_2009 = {
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014,
    "F": 2015, "G": 2016, "H": 2017, "J": 2018, "K": 2019,
    "L": 2020, "M": 2021, "N": 2022, "P": 2023, "R": 2024,
    "S": 2025, "T": 2026,
}

# Seuil : si WMI suggère un véhicule moderne, on préfère post-2009
_MODERN_THRESHOLD = 2009


def _decode_year(vin: str) -> str:
    """
    Décode l'année depuis la position 10 du VIN (index 9).
    Résout l'ambiguïté 1980-2009 vs 2010+ en s'appuyant sur le WMI.
    """
    if len(vin) < 10:
        return "Inconnu"
    yc = vin[9].upper()

    # Chiffres 1-9 → 2001-2009 (non ambigu)
    try:
        y = int(yc)
        if 1 <= y <= 9:
            return str(2000 + y)
    except ValueError:
        pass

    # Lettre → peut être 1980-2000 OU 2010-2026
    old_year  = YEAR_CODES.get(yc)
    new_year  = _post_2009.get(yc)

    if new_year and not old_year:
        return str(new_year)
    if old_year and not new_year:
        return str(old_year)
    if new_year and old_year:
        # Ambiguïté : utiliser le WMI pour trancher
        # Les WMI EU/Asie avec lettre = quasi toujours post-2010 pour les véhicules récents
        # On privilégie post-2009 sauf si l'année serait > année courante
        import datetime
        current_year = datetime.datetime.now().year
        if new_year <= current_year + 1:
            return str(new_year)
        return str(old_year)

    return "Inconnu"


# ─────────────────────────────────────────────────────────────────────────────
# Décodage local (WMI)
# ─────────────────────────────────────────────────────────────────────────────

def decode_vin_local(vin: str) -> dict:
    """Décode marque, modèle et année via les tables WMI locales."""
    info = {
        "vin":    vin,
        "marque": "Inconnu",
        "modele": "Inconnu",
        "annee":  "Inconnu",
    }
    if not vin or len(vin) < 3:
        return info

    vin_up = vin.upper()
    wmi3   = vin_up[:3]
    wmi4   = vin_up[:4]
    wmi5   = vin_up[:5]

    # 1. Modèle précis sur 5 caractères (le plus spécifique)
    if wmi5 in WMI_MODEL_MAP:
        info["modele"] = WMI_MODEL_MAP[wmi5]
    # 2. Modèle sur 4 caractères
    elif wmi4 in WMI_MODEL_MAP:
        info["modele"] = WMI_MODEL_MAP[wmi4]

    # 3. Marque via WMI 3 caractères (correspondance exacte en priorité)
    if wmi3 in WMI_MAP:
        info["marque"] = WMI_MAP[wmi3]
    else:
        # Correspondance par préfixe (fallback)
        for prefix, brand in WMI_MAP.items():
            if wmi3.startswith(prefix) or prefix.startswith(wmi3):
                info["marque"] = brand
                break

    # 4. Année
    info["annee"] = _decode_year(vin_up)

    return info


# ─────────────────────────────────────────────────────────────────────────────
# API NHTSA (base US officielle)
# ─────────────────────────────────────────────────────────────────────────────

def decode_vin_nhtsa(vin: str) -> dict:
    """Décode le VIN via l'API officielle NHTSA (timeout 5s)."""
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    results = r.json().get("Results", [{}])[0]
    marque  = results.get("Make", "").strip() or "Inconnu"
    modele  = results.get("Model", "").strip() or "Inconnu"
    annee   = results.get("ModelYear", "").strip() or "Inconnu"
    moteur  = results.get("EngineCylinders", "").strip()
    carbu   = results.get("FuelTypePrimary", "").strip()
    carross = results.get("BodyClass", "").strip()
    manuf   = results.get("Manufacturer", "").strip()

    # NHTSA retourne parfois le fabricant mais pas la marque commerciale
    if marque in ("Inconnu", "") and manuf:
        marque = manuf.split(",")[0].strip()

    info = {"vin": vin, "marque": marque.capitalize(), "modele": modele, "annee": annee}
    extras = []
    if moteur:  extras.append(f"{moteur} cyl.")
    if carbu:   extras.append(carbu)
    if carross: extras.append(carross)
    if extras:  info["details_techniques"] = " — ".join(extras)
    return info


def get_recalls_nhtsa(make: str, model: str, year: str) -> list:
    """Récupère les rappels officiels NHTSA (timeout 5s)."""
    if not make or make == "Inconnu":
        return []
    try:
        url = (
            f"https://api.nhtsa.gov/recalls/recallsByVehicle"
            f"?make={requests.utils.quote(make)}"
            f"&model={requests.utils.quote(model)}"
            f"&modelYear={year}"
        )
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Claude Sonnet (anti-hallucination renforcé)
# ─────────────────────────────────────────────────────────────────────────────

_VIN_AI_TIMEOUT = 12  # secondes — garde-fou strict (le SDK Anthropic n'a pas de timeout Python)


def decode_vin_ai(vin: str) -> dict | None:
    """
    Décode le VIN via Claude Sonnet.
    Anti-hallucination : règles strictes + confirmation WMI obligatoire.
    Timeout strict (12s) pour éviter les hangs : si Claude ne répond pas, on abandonne
    et le thread de fond finit silencieusement.
    """
    _log(f"[decode_vin_ai] START vin={vin}")
    t0 = _t.time()
    try:
        # On fournit à Claude les infos WMI déjà connues pour ancrer sa réponse
        local_hint = decode_vin_local(vin)
        wmi_context = ""
        if local_hint["marque"] != "Inconnu":
            wmi_context = f"Le WMI '{vin[:3]}' correspond à la marque '{local_hint['marque']}'."

        def _call_claude():
            client = _get_client()
            return client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Identifie ce véhicule à partir de son VIN : {vin}\n"
                        f"{wmi_context}\n"
                        "RÈGLES STRICTES :\n"
                        "- Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour\n"
                        '- Format exact : {"marque": "...", "modele": "...", "annee": "YYYY"}\n'
                        "- L'année doit être un nombre à 4 chiffres (ex: 2018)\n"
                        "- Si tu n'es PAS certain à plus de 80%, mets \"Inconnu\" pour ce champ\n"
                        "- Ne JAMAIS inventer une marque ou un modèle sans être certain\n"
                        "- La marque doit correspondre au WMI fourni si disponible\n"
                    )
                }]
            )

        # Enforcement timeout strict via pool daemon : si Claude hang, on abandonne.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(_call_claude)
            try:
                response = fut.result(timeout=_VIN_AI_TIMEOUT)
            except FutureTimeout:
                _log(f"[decode_vin_ai] ✗ TIMEOUT {_VIN_AI_TIMEOUT}s → None")
                return None
        finally:
            pool.shutdown(wait=False)

        text = response.content[0].text.strip()
        m = re.search(r'\{[^}]+\}', text)
        if m:
            data = json.loads(m.group())
            marque = str(data.get("marque", "Inconnu")).strip()
            modele = str(data.get("modele", "Inconnu")).strip()
            annee  = str(data.get("annee",  "Inconnu")).strip()
            # Validation : si Claude contredit le WMI local sur la marque → on ignore
            if (local_hint["marque"] != "Inconnu"
                    and marque != "Inconnu"
                    and local_hint["marque"].lower() not in marque.lower()
                    and marque.lower() not in local_hint["marque"].lower()):
                marque = local_hint["marque"]   # on fait confiance au WMI
            _log(f"[decode_vin_ai] ✓ {marque} {modele} {annee} en {_t.time()-t0:.1f}s")
            return {"vin": vin, "marque": marque, "modele": modele, "annee": annee}
    except Exception as exc:
        _log(f"[decode_vin_ai] ✗ ERREUR après {_t.time()-t0:.1f}s : {exc}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline principal — ordre intelligent EU vs US
# ─────────────────────────────────────────────────────────────────────────────

def decode_vin(vin: str) -> dict:
    """
    Pipeline de décodage VIN intelligent.

    Véhicule européen  → Local WMI → NHTSA (complément) → Claude Sonnet
    Véhicule américain → NHTSA     → Local WMI           → Claude Sonnet
    VIN invalide       → retourne immédiatement avec message d'erreur
    """
    if not vin:
        return {"vin": "", "marque": "Inconnu", "modele": "Inconnu", "annee": "Inconnu",
                "erreur": "VIN vide"}

    vin = _clean_vin(vin)

    # ── Validation format ─────────────────────────────────────────────────────
    valid, reason = validate_vin(vin)
    if not valid:
        return {"vin": vin, "marque": "Inconnu", "modele": "Inconnu", "annee": "Inconnu",
                "erreur": f"VIN invalide : {reason}"}

    is_eu = _is_european_vin(vin)

    # ── Véhicule EUROPÉEN : local d'abord ─────────────────────────────────────
    if is_eu:
        result = decode_vin_local(vin)

        # Si la marque ET le modèle sont trouvés localement → on s'arrête là
        if result["marque"] != "Inconnu" and result["modele"] != "Inconnu":
            return result

        # Sinon on complète avec NHTSA (peut avoir le modèle même pour les EU)
        try:
            nhtsa = decode_vin_nhtsa(vin)
            # On ne prend de NHTSA que ce qui manque localement
            if result["marque"] == "Inconnu" and nhtsa["marque"] not in ("Inconnu", ""):
                result["marque"] = nhtsa["marque"]
            if result["modele"] == "Inconnu" and nhtsa["modele"] not in ("Inconnu", ""):
                result["modele"] = nhtsa["modele"]
            if result["annee"] == "Inconnu" and nhtsa["annee"] not in ("Inconnu", ""):
                result["annee"] = nhtsa["annee"]
            if "details_techniques" in nhtsa:
                result["details_techniques"] = nhtsa["details_techniques"]
        except Exception:
            pass

        # Encore des inconnues → Claude Sonnet
        if result["modele"] == "Inconnu":
            ai = decode_vin_ai(vin)
            if ai:
                if result["marque"] == "Inconnu" and ai["marque"] != "Inconnu":
                    result["marque"] = ai["marque"]
                if result["modele"] == "Inconnu" and ai["modele"] != "Inconnu":
                    result["modele"] = ai["modele"]
                if result["annee"] == "Inconnu" and ai["annee"] != "Inconnu":
                    result["annee"] = ai["annee"]

        return result

    # ── Véhicule AMÉRICAIN / AUTRE : NHTSA d'abord ────────────────────────────
    try:
        result = decode_vin_nhtsa(vin)
        if result["marque"] not in ("Inconnu", "") and result["modele"] not in ("Inconnu", ""):
            return result
    except Exception:
        result = {"vin": vin, "marque": "Inconnu", "modele": "Inconnu", "annee": "Inconnu"}

    # Complément local si NHTSA incomplet
    local = decode_vin_local(vin)
    if result["marque"] == "Inconnu" and local["marque"] != "Inconnu":
        result["marque"] = local["marque"]
    if result["modele"] == "Inconnu" and local["modele"] != "Inconnu":
        result["modele"] = local["modele"]
    if result["annee"] == "Inconnu" and local["annee"] != "Inconnu":
        result["annee"] = local["annee"]

    # Dernier recours → Claude Sonnet
    if result["modele"] == "Inconnu":
        ai = decode_vin_ai(vin)
        if ai:
            if result["marque"] == "Inconnu" and ai["marque"] != "Inconnu":
                result["marque"] = ai["marque"]
            if result["modele"] == "Inconnu" and ai["modele"] != "Inconnu":
                result["modele"] = ai["modele"]
            if result["annee"] == "Inconnu" and ai["annee"] != "Inconnu":
                result["annee"] = ai["annee"]

    return result
