"""
Analyse IA via l'API Anthropic.
"""
import json
import os

import anthropic
import requests

from base_path import data_path

_client = None


def _get_api_key() -> str:
    """Lit la clé Anthropic depuis l'env ou config.json."""
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


# ---------------------------------------------------------------------------
# NHTSA APIs
# ---------------------------------------------------------------------------

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
    info = {
        "vin":    vin,
        "marque": marque.capitalize(),
        "modele": modele,
        "annee":  annee,
    }
    extras = []
    if moteur: extras.append(f"{moteur} cyl.")
    if carbu:  extras.append(carbu)
    if carross:extras.append(carross)
    if extras: info["details_techniques"] = " — ".join(extras)
    return info


def get_recalls_nhtsa(make: str, model: str, year: str) -> list:
    """Récupère les rappels officiels NHTSA pour un véhicule (timeout 5s)."""
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


# ---------------------------------------------------------------------------
# VIN decoding (basic — fallback sans API externe)
# ---------------------------------------------------------------------------

WMI_MAP = {
    # ── France ──────────────────────────────────────────────
    "VF1": "Renault", "VF2": "Renault", "VF3": "Peugeot",
    "VF4": "Talbot",  "VF6": "Renault", "VF7": "Citroën",
    "VF8": "Matra",   "VFA": "Renault", "VFB": "Renault",
    "VFC": "Citroën", "VFD": "Peugeot", "VFE": "Peugeot",
    "VFF": "Citroën", "VFG": "Alpine",  "VFH": "Citroën",
    "VFJ": "Peugeot", "VFN": "Renault", "VFP": "Renault",
    "VFR": "Renault", "VFS": "Citroën", "VFT": "Citroën",
    "VFU": "Citroën", "VFV": "Peugeot", "VFX": "Peugeot",
    "VFY": "Citroën", "VF3": "Peugeot", "VS7": "DS Automobiles",
    "VR1": "Alpine",  "VRE": "Alpine",
    # ── Allemagne ───────────────────────────────────────────
    "WBA": "BMW", "WBS": "BMW M", "WBY": "BMW i",
    "WDB": "Mercedes-Benz", "WDC": "Mercedes-Benz",
    "WDD": "Mercedes-Benz", "WDF": "Mercedes-Benz",
    "WEB": "Mercedes-Benz EQ",
    "WVW": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen",
    "WAU": "Audi", "WUA": "Audi RS",
    "WAP": "Porsche", "WP0": "Porsche",
    "WMA": "MAN", "WMW": "MINI", "WME": "Smart",
    "TRU": "Audi Hungrie",
    # ── Espagne ─────────────────────────────────────────────
    "VSS": "SEAT", "VS6": "SEAT", "VS7": "SEAT",
    "VNE": "SEAT", "VN1": "SEAT",
    # ── République Tchèque / Slovaquie ──────────────────────
    "TMB": "Škoda", "TMA": "Škoda",
    "TM9": "Škoda", "TMK": "Škoda",
    # ── Italie ──────────────────────────────────────────────
    "ZAR": "Alfa Romeo", "ZAM": "Maserati",
    "ZFF": "Ferrari",    "ZHW": "Lamborghini",
    "ZLA": "Lancia",     "ZFA": "Fiat",
    "ZFC": "Fiat",       "ZFB": "Fiat",
    "ZAA": "Fiat",
    # ── Royaume-Uni ─────────────────────────────────────────
    "SAJ": "Jaguar",      "SAL": "Land Rover",
    "SCF": "Aston Martin","SFD": "Bentley",
    "SCC": "Lotus",       "SAB": "Saab (UK)",
    "SBM": "McLaren",
    # ── Suède ───────────────────────────────────────────────
    "YV1": "Volvo", "YV2": "Volvo", "YV3": "Volvo",
    "YS2": "Scania", "YS3": "Saab", "YS4": "Saab",
    "XL9": "Spyker",
    # ── Pays-Bas ────────────────────────────────────────────
    "XLR": "DAF", "XL8": "Donkervoort",
    # ── Roumanie ────────────────────────────────────────────
    "UU1": "Dacia", "UU2": "Dacia",
    # ── Turquie ─────────────────────────────────────────────
    "NMT": "Toyota Türkiye",
    # ── Japon ───────────────────────────────────────────────
    "JHM": "Honda",  "JH4": "Acura",
    "JTD": "Toyota", "JTH": "Lexus", "JTE": "Toyota",
    "JN1": "Nissan", "JN6": "Nissan",
    "JS1": "Suzuki", "JS2": "Suzuki", "JS3": "Suzuki",
    "JM1": "Mazda",  "JM3": "Mazda",
    "JA3": "Mitsubishi", "JA4": "Mitsubishi",
    "JF1": "Subaru", "JF2": "Subaru",
    # ── Corée ───────────────────────────────────────────────
    "KMH": "Hyundai", "KMF": "Hyundai",
    "KNA": "Kia",     "KNB": "Kia",
    "KPT": "SsangYong",
    # ── USA ─────────────────────────────────────────────────
    "1G1": "Chevrolet", "1G6": "Cadillac",
    "1FT": "Ford",      "1FA": "Ford", "1FM": "Ford",
    "1HG": "Honda USA", "1J4": "Jeep",
    "1C4": "Chrysler",  "2T1": "Toyota Canada",
    # ── Chine ───────────────────────────────────────────────
    "LVS": "Ford China", "LFV": "Volkswagen China",
    "LSG": "General Motors China",
}

# Décodage modèle par WMI étendu (4 caractères) pour marques FR courantes
WMI_MODEL_MAP = {
    # Renault
    "VF1A": "Twingo", "VF1B": "Clio", "VF1C": "Mégane",
    "VF1D": "Laguna", "VF1E": "Espace", "VF1F": "Kangoo",
    "VF1G": "Scenic", "VF1H": "Vel Satis", "VF1J": "Trafic",
    "VF1K": "Koleos", "VF1L": "Clio", "VF1M": "Mégane",
    "VF1N": "Mégane", "VF1P": "Scenic", "VF1R": "Laguna",
    "VF1S": "Master", "VF1T": "Trafic", "VF1U": "Modus",
    "VF1W": "Fluence", "VF1X": "Zoe", "VF1Y": "Captur",
    # Peugeot
    "VF3A": "106", "VF3B": "206", "VF3C": "307",
    "VF3D": "405", "VF3E": "406", "VF3F": "407",
    "VF3G": "607", "VF3H": "807", "VF3J": "2008",
    "VF3K": "3008", "VF3L": "5008", "VF3M": "508",
    "VF3N": "308", "VF3P": "108", "VF3R": "208",
    "VF3T": "Boxer", "VF3U": "Expert", "VF3V": "Partner",
    # Citroën
    "VF7A": "C1", "VF7B": "C2", "VF7C": "C3",
    "VF7D": "C4", "VF7E": "C5", "VF7F": "C6",
    "VF7G": "C8", "VF7H": "Berlingo", "VF7J": "Dispatch",
    "VF7K": "Jumper", "VF7L": "Jumpy", "VF7M": "C-Elysée",
    "VF7N": "C3 Picasso", "VF7P": "C4 Picasso", "VF7R": "C4 Cactus",
    "VF7S": "C3 Aircross", "VF7T": "C5 Aircross",
    # Dacia
    "UU1A": "Sandero", "UU1B": "Logan", "UU1C": "Duster",
    "UU1D": "Lodgy", "UU1E": "Dokker", "UU1F": "Spring",
}

YEAR_CODES = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984,
    "F": 1985, "G": 1986, "H": 1987, "J": 1988, "K": 1989,
    "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994,
    "S": 1995, "T": 1996, "V": 1997, "W": 1998, "X": 1999,
    "Y": 2000, "1": 2001, "2": 2002, "3": 2003, "4": 2004,
    "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

# Post-2009: letters restart A-H, J-N, P, R-T, V-Y (skip I, O, Q, U, Z)
_post_2009 = {
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014,
    "F": 2015, "G": 2016, "H": 2017, "J": 2018, "K": 2019,
    "L": 2020, "M": 2021, "N": 2022, "P": 2023, "R": 2024,
    "S": 2025, "T": 2026,
}


def decode_vin_local(vin: str) -> dict:
    info = {
        "vin": vin,
        "marque": "Inconnu",
        "modele": "Inconnu",
        "annee": "Inconnu",
    }
    if not vin or len(vin) < 3:
        return info

    wmi = vin[:3].upper()
    wmi4 = vin[:4].upper()

    # Tenter d'abord le modèle via WMI 4 caractères
    if wmi4 in WMI_MODEL_MAP:
        info["modele"] = WMI_MODEL_MAP[wmi4]

    # Puis la marque via WMI 3 caractères
    for prefix, brand in WMI_MAP.items():
        if wmi.startswith(prefix):
            info["marque"] = brand
            break

    if len(vin) >= 10:
        yc = vin[9].upper()
        try:
            y = int(yc)
            if 1 <= y <= 9:
                info["annee"] = str(2000 + y)
        except ValueError:
            year_80_00 = YEAR_CODES.get(yc)
            year_10_plus = _post_2009.get(yc)
            if year_10_plus:
                info["annee"] = str(year_10_plus if len(vin) == 17 else (year_80_00 or year_10_plus))
            elif year_80_00:
                info["annee"] = str(year_80_00)

    return info


def decode_vin_ai(vin: str) -> dict | None:
    """Décode le VIN via Claude IA — pour les véhicules européens non reconnus par NHTSA."""
    import re
    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"Identifie ce véhicule à partir de son VIN : {vin}\n"
                    "Réponds UNIQUEMENT avec un JSON sur une ligne, format exact :\n"
                    '{"marque": "...", "modele": "...", "annee": "..."}\n'
                    "Si tu ne sais pas, mets \"Inconnu\". Aucun texte autour du JSON."
                )
            }]
        )
        text = response.content[0].text.strip()
        m = re.search(r'\{[^}]+\}', text)
        if m:
            data = json.loads(m.group())
            return {
                "vin": vin,
                "marque": data.get("marque", "Inconnu"),
                "modele": data.get("modele", "Inconnu"),
                "annee":  str(data.get("annee", "Inconnu")),
            }
    except Exception:
        pass
    return None


def decode_vin(vin: str) -> dict:
    """NHTSA → WMI local → Claude IA comme dernier recours."""
    # 1. NHTSA (base US/internationale) — retourne seulement si marque ET modèle trouvés
    try:
        result = decode_vin_nhtsa(vin)
        if (result.get("marque", "Inconnu") not in ("Inconnu", "")
                and result.get("modele", "Inconnu") not in ("Inconnu", "")):
            return result
    except Exception:
        pass

    # 2. Décodage local via WMI
    result = decode_vin_local(vin)

    # 3. Si modèle toujours inconnu → Claude IA (connaît les VINs européens)
    if result.get("modele", "Inconnu") in ("Inconnu", ""):
        ai_result = decode_vin_ai(vin)
        if ai_result:
            if ai_result.get("marque", "Inconnu") not in ("Inconnu", ""):
                result["marque"] = ai_result["marque"]
            if ai_result.get("modele", "Inconnu") not in ("Inconnu", ""):
                result["modele"] = ai_result["modele"]
            if ai_result.get("annee", "Inconnu") not in ("Inconnu", ""):
                result["annee"] = ai_result["annee"]

    return result


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_dtc(
    vin: str,
    dtc_codes: list,
    realtime_data: dict,
    kilometrage: int,
    historique: list = None,
    reparations: list = None,
) -> dict:
    vin_info = decode_vin(vin)

    if not dtc_codes:
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": "Aucun code de défaut détecté. Le véhicule semble en bon état de fonctionnement.",
            "statut_global": "OK",
        }

    rt = realtime_data or {}
    realtime_str = "\n".join([
        f"  - Vitesse : {rt.get('speed', 'N/A')} km/h",
        f"  - Régime moteur : {rt.get('rpm', 'N/A')} tr/min",
        f"  - Température liquide refroidissement : {rt.get('coolant_temp', 'N/A')} °C",
        f"  - Tension batterie : {rt.get('battery_voltage', 'N/A')} V",
        f"  - Pression admission : {rt.get('intake_pressure', 'N/A')} kPa",
    ])
    dtc_str = ", ".join(dtc_codes)

    # Fetch official NHTSA recalls
    recalls = get_recalls_nhtsa(vin_info.get("marque",""), vin_info.get("modele",""), vin_info.get("annee",""))
    recalls_str = ""
    if recalls:
        recall_lines = []
        for rec in recalls[:5]:
            comp = rec.get("Component", "")
            desc = rec.get("Summary", rec.get("Consequence", ""))[:120]
            recall_lines.append(f"  - {comp} : {desc}")
        recalls_str = "\n**Rappels constructeurs NHTSA officiels :**\n" + "\n".join(recall_lines)

    # Comparaison avec réparations précédentes
    repair_str = ""
    if reparations:
        matched = []
        for rep in reparations[:10]:
            rep_desc = rep.get("description", "").lower()
            rep_date = rep.get("date_affichage", rep.get("date", ""))
            for code in dtc_codes:
                if code.lower() in rep_desc or any(
                    part in rep_desc for part in ["egr", "cat", "lambda", "sonde", "vanne", "injecteur", "allumage"]
                ):
                    matched.append(f"  - Réparation du {rep_date} : {rep.get('description','')} (coût : {rep.get('cout','')} €)")
                    break
        if matched:
            repair_str = (
                "\n**⚠️ ATTENTION — Codes similaires déjà réparés :**\n"
                + "\n".join(matched)
                + "\n=> Si le même code réapparaît après réparation, mentionne 'récidive après réparation' dans ton analyse."
            )

    # Build historical context
    hist_str = ""
    if historique:
        hist_entries = historique[:3]
        lines = []
        for i, h in enumerate(hist_entries, 1):
            codes = ", ".join(h.get("dtc_codes", [])) or "Aucun"
            km = h.get("kilometrage", 0)
            date = h.get("date_affichage", "")
            lines.append(f"  Diagnostic {i} ({date}, {km} km) : {codes}")
        hist_str = "\n**Historique des 3 derniers diagnostics :**\n" + "\n".join(lines)

    details_tech = vin_info.get("details_techniques", "")
    prompt = f"""Tu es un expert en diagnostic automobile OBD2 avec 20 ans d'expérience. \
Analyse les codes de défaut suivants pour ce véhicule avec une analyse approfondie en 5 niveaux.

**Informations véhicule :**
- VIN : {vin}
- Marque : {vin_info['marque']}
- Modèle : {vin_info['modele']}
- Année : {vin_info['annee']}
{f"- Détails techniques : {details_tech}" if details_tech else ""}- Kilométrage actuel : {kilometrage} km

**Codes DTC détectés :** {dtc_str}

**Données temps réel au moment du diagnostic :**
{realtime_str}
{recalls_str}
{repair_str}
{hist_str}

Pour chaque code DTC, effectue une analyse en 5 niveaux :
1. DÉCODAGE : description claire + système concerné (moteur, transmission, échappement, électrique, dépollution...)
2. CAUSES PROBABLES : liste de 3 à 5 causes probables ordonnées par fréquence (de la plus fréquente à la moins fréquente)
3. DÉFAUTS CONSTRUCTEURS CONNUS : ce code est-il un défaut récurrent connu sur CE modèle/génération ? Si oui, explique pourquoi c'est fréquent sur ce véhicule spécifiquement.
4. RAPPELS CONSTRUCTEURS : existe-t-il un rappel constructeur officiel lié à ce code sur ce véhicule ? Si oui, indique la nature du rappel.
5. DÉTECTION FAUX POSITIFS : croise batterie faible (<12V), plusieurs codes sans lien, kilométrage élevé, codes intermittents dans l'historique. Si faux positif probable, explique la cause (batterie, connecteur oxydé, pic électrique...).
6. VERDICT FINAL : urgence + action courte + test recommandé après effacement.

Réponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans commentaires) :

{{
  "codes": [
    {{
      "code": "P0XXX",
      "description": "Description claire en français",
      "systeme": "Système concerné",
      "causes_probables": ["Cause 1 (la plus fréquente)", "Cause 2", "Cause 3", "Cause 4"],
      "defaut_constructeur_connu": false,
      "detail_defaut_constructeur": null,
      "rappel_constructeur": false,
      "detail_rappel": null,
      "faux_positif_probable": false,
      "raison_faux_positif": null,
      "urgence": "SURVEILLER",
      "action": "Aller au garage dans la semaine",
      "test_recommande": "Effacer le code, rouler 20 min, relancer le diagnostic",
      "fourchette_prix": "150€ - 400€ (pièce 80-200€ + 1-2h main d'œuvre)"
    }}
  ],
  "analyse_globale": "Résumé en 2-3 phrases du diagnostic complet",
  "urgence_globale": "SURVEILLER"
}}

Règles strictes :
- "urgence" doit être exactement "URGENT", "SURVEILLER" ou "NON URGENT"
- "urgence_globale" doit être exactement "URGENT", "SURVEILLER" ou "OK"
- "fourchette_prix" doit être une estimation réaliste en €, format "X€ - Y€ (détail)"
- "action" doit être une phrase courte et concrète
- "causes_probables" doit être un tableau de 3 à 5 chaînes de caractères, chaque cause étant concise (max 10 mots)
- "defaut_constructeur_connu" et "rappel_constructeur" sont des booléens (true/false)
- "faux_positif_probable" est un booléen — mets true si tension batterie < 12.2V, ou si codes multiples sans lien, ou si code intermittent dans l'historique
- Toutes les réponses en FRANÇAIS
- Si l'historique montre ce même code en récurrence, mentionner "code récurrent" dans description
"""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        for fence in ("```json", "```"):
            if raw.startswith(fence):
                raw = raw[len(fence):]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        # Extraire uniquement le premier objet JSON complet (ignore tout texte après)
        start = raw.find("{")
        if start == -1:
            raise ValueError("Aucun objet JSON trouvé dans la réponse")
        # Trouver la fermeture correcte par comptage des accolades
        depth = 0
        end = start
        for i, ch in enumerate(raw[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        raw = raw[start:end + 1]

        parsed = json.loads(raw)
        return {
            "vin_info": vin_info,
            "analyse": parsed.get("codes", []),
            "resume": parsed.get("analyse_globale", ""),
            "statut_global": parsed.get("urgence_globale", "SURVEILLER"),
        }

    except Exception as exc:
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": f"Erreur lors de l'analyse : {exc}",
            "statut_global": "SURVEILLER",
            "error": str(exc),
        }


def analyze_with_session(dtc_codes: list, vehicle_info: dict, session_data: dict) -> dict:
    """Analyse enrichie croisant les codes DTC avec les données de session de surveillance continue."""
    cfg = {}
    config_path = data_path("config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass

    # Formater les stats de session
    stats = session_data.get("stats", {})
    anomalies = session_data.get("anomalies", [])
    duration = session_data.get("duration_seconds", 0)
    readings = session_data.get("readings_count", 0)

    def fmt_stat(key, unit):
        s = stats.get(key, {})
        if not s or s.get("max", 0) == 0:
            return "Non disponible"
        return f"min={s.get('min',0)}{unit} / max={s.get('max',0)}{unit} / moy={s.get('avg',0)}{unit}"

    anomalies_text = "\n".join([
        f"  - [{a.get('timestamp','')[-8:-3]}] {a.get('message','')}"
        for a in anomalies
    ]) or "  Aucune anomalie détectée"

    dtc_text = ", ".join(dtc_codes) if dtc_codes else "Aucun code DTC"

    marque = vehicle_info.get("marque", "Inconnu")
    modele = vehicle_info.get("modele", "")
    annee = vehicle_info.get("annee", "")
    vin = vehicle_info.get("vin", "")
    km = vehicle_info.get("km", "N/A")

    prompt = f"""Tu es un expert en diagnostic automobile avec 20 ans d'expérience. Analyse ce véhicule en croisant les codes DTC avec les données de la session de surveillance continue.

VÉHICULE : {marque} {modele} {annee} — VIN: {vin} — {km} km

═══ CODES DTC ═══
{dtc_text}

═══ DONNÉES SESSION DE SURVEILLANCE ═══
Durée : {duration}s | Points de mesure : {readings}

RPM moteur     : {fmt_stat('rpm', ' tr/min')}
Température    : {fmt_stat('temp', '°C')}
Vitesse        : {fmt_stat('speed', ' km/h')}
Tension batt.  : {fmt_stat('voltage', 'V')}

═══ ANOMALIES DÉTECTÉES EN TEMPS RÉEL ═══
{anomalies_text}

═══ DEMANDE D'ANALYSE ═══
Fournis une analyse CROISÉE et APPROFONDIE :

1. **Diagnostic principal** : Explique ce que révèle la COMBINAISON des codes DTC ET des données de session (corrélations, causes probables)
2. **Analyse des anomalies** : Pour chaque anomalie détectée, explique ce qu'elle signifie dans le contexte global
3. **Corrélations clés** : Identifie les liens entre les valeurs (ex: temp haute + RPM instables = suspect joint de culasse)
4. **Niveau d'urgence** : OK / SURVEILLER / URGENT avec justification basée sur les données réelles
5. **Actions prioritaires** : Liste ordonnée des interventions recommandées avec urgence
6. **RÉSUMÉ** : Termine OBLIGATOIREMENT par une ligne commençant exactement par "RÉSUMÉ:" suivie d'une ou deux phrases synthétisant le diagnostic et l'action principale à faire.

Réponds en français, de manière professionnelle et structurée. Sois précis et technique."""

    try:
        client = _get_client()
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = msg.content[0].text

        # Détecter le statut global
        statut = "SURVEILLER"
        if "URGENT" in raw.upper():
            statut = "URGENT"
        elif "OK" in raw and "URGENT" not in raw.upper() and "SURVEILLER" not in raw.upper():
            statut = "OK"

        return {
            "analyse": raw,
            "statut_global": statut,
            "source": "surveillance_continue",
            "anomalies_count": len(anomalies),
            "duration": duration
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "analyse": "",
            "statut_global": "SURVEILLER",
            "source": "surveillance_continue",
            "anomalies_count": len(anomalies),
            "duration": duration
        }


def analyze_full_diagnostic(
    vin: str,
    dtc_codes: list,
    km: int,
    session_ralenti: dict | None,
    session_roulant: dict | None,
    anamnese: dict | None = None,
    freeze_frame: dict | None = None,
    realtime: dict | None = None,
    historique: list | None = None,
    reparations: list | None = None,
    vehicle_manual: dict | None = None,
) -> dict:
    """Analyse complète croisant DTC + session ralenti + session roulant."""
    vin_info = decode_vin(vin) if vin and not vin.startswith("MANUEL_") else {
        "marque": "Inconnu", "modele": "Inconnu", "annee": "", "motorisation": ""
    }

    # Enrichir vin_info avec les infos manuelles si fournies
    if vehicle_manual:
        if vehicle_manual.get("marque"):  vin_info["marque"]       = vehicle_manual["marque"]
        if vehicle_manual.get("modele"):  vin_info["modele"]       = vehicle_manual["modele"]
        if vehicle_manual.get("annee"):   vin_info["annee"]        = vehicle_manual["annee"]
        if vehicle_manual.get("motorisation"): vin_info["motorisation"] = vehicle_manual["motorisation"]

    has_symptoms = bool(
        anamnese and (
            (isinstance(anamnese.get("symptomes"), list) and len(anamnese["symptomes"]) > 0) or
            anamnese.get("sons_decrits", "").strip() or
            anamnese.get("apres_intervention", "").strip() or
            anamnese.get("infos_libres", "").strip() or
            anamnese.get("frequence", "").strip() or
            anamnese.get("depuis_quand", "").strip() or
            anamnese.get("interventions_recentes", "").strip() or
            (isinstance(anamnese.get("moments"), list) and len(anamnese["moments"]) > 0)
        )
    )
    if not dtc_codes and not has_symptoms and not session_ralenti and not session_roulant:
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": "Aucun code de défaut détecté. Le véhicule semble en bon état.",
            "statut_global": "OK",
        }

    def fmt_session(session: dict | None, label: str) -> str:
        if not session or session.get("readings_count", 0) == 0:
            return f"═══ {label} ═══\nNon réalisé"
        stats = session.get("stats", {})
        anomalies = session.get("anomalies", [])
        duration = session.get("duration_seconds", 0)
        readings = session.get("readings_count", 0)

        def fs(key, unit):
            s = stats.get(key, {})
            if not s or s.get("max", 0) == 0:
                return "N/A"
            return f"min={s['min']}{unit} / max={s['max']}{unit} / moy={s['avg']}{unit}"

        anom_text = "\n".join(
            f"  [{a.get('timestamp','')[11:19]}] {a.get('message','')}"
            for a in anomalies
        ) or "  Aucune anomalie"

        return (
            f"═══ {label} — {duration}s · {readings} mesures ═══\n"
            f"RPM         : {fs('rpm',' tr/min')}\n"
            f"Température : {fs('temp','°C')}\n"
            f"Vitesse     : {fs('speed',' km/h')}\n"
            f"Batterie    : {fs('voltage','V')}\n"
            f"Anomalies :\n{anom_text}"
        )

    marque      = vin_info.get("marque", "Inconnu")
    modele      = vin_info.get("modele", "")
    annee       = vin_info.get("annee", "")
    motorisation = vin_info.get("motorisation", "")
    dtc_str = ", ".join(dtc_codes)

    section_ralenti = fmt_session(session_ralenti, "DONNÉES AU RALENTI")
    section_roulant = fmt_session(session_roulant, "DONNÉES EN ROULANT")

    # ── Anamnèse ────────────────────────────────────────────
    anamnese_str = ""
    if anamnese:
        parts = []
        depuis = anamnese.get("depuis_quand", "")
        if depuis: parts.append(f"Depuis quand : {depuis}")
        apres = anamnese.get("apres_intervention", "").strip()
        if apres: parts.append(f"⚠️ Panne apparue APRÈS l'intervention : {apres}")
        freq = anamnese.get("frequence", "")
        if freq: parts.append(f"Fréquence : {freq}")
        moments = anamnese.get("moments", [])
        if moments: parts.append(f"Conditions d'apparition : {', '.join(moments)}")
        symptomes = anamnese.get("symptomes", [])
        if symptomes: parts.append(f"Symptômes rapportés : {', '.join(symptomes)}")
        sons = anamnese.get("sons_decrits", "").strip()
        if sons: parts.append(f"Description acoustique : {sons}")
        # Données spectrogramme si disponibles
        audio_peaks = anamnese.get("audio_peaks")
        audio_interps = anamnese.get("audio_interpretations")
        if audio_peaks:
            peaks_str = ", ".join(f"{p.get('freq')} Hz (intensité {p.get('magnitude')})" for p in audio_peaks[:5])
            parts.append(f"🎵 Analyse spectrogramme — Fréquences dominantes : {peaks_str}")
        if audio_interps:
            parts.append(f"🔬 Interprétation fréquentielle : {' | '.join(audio_interps)}")
        interventions = anamnese.get("interventions_recentes", "").strip()
        if interventions: parts.append(f"Interventions récentes (< 6 mois) : {interventions}")
        infos = anamnese.get("infos_libres", "").strip()
        if infos: parts.append(f"Infos complémentaires : {infos}")
        if parts:
            anamnese_str = (
                "\n═══ ANAMNÈSE CLIENT ═══\n"
                + "\n".join(f"  • {p}" for p in parts) + "\n"
            )

    # ── Freeze frame ────────────────────────────────────────
    ff_str = ""
    if freeze_frame and any(v is not None for v in freeze_frame.values()):
        ff_lines = []
        ff_map = {
            "speed_ff":           ("Vitesse au déclenchement", "km/h"),
            "rpm_ff":             ("RPM au déclenchement", "tr/min"),
            "coolant_temp_ff":    ("Température au déclenchement", "°C"),
            "engine_load_ff":     ("Charge moteur", "%"),
            "fuel_trim_short_ff": ("Correction carburant CT", "%"),
            "fuel_trim_long_ff":  ("Correction carburant LT", "%"),
            "throttle_ff":        ("Position papillon", "%"),
        }
        for k, (label, unit) in ff_map.items():
            if freeze_frame.get(k) is not None:
                ff_lines.append(f"  {label} : {freeze_frame[k]} {unit}")
        if ff_lines:
            ff_str = "\n═══ FREEZE FRAME — DONNÉES AU MOMENT DU DÉCLENCHEMENT DTC ═══\n" + "\n".join(ff_lines) + "\n"

    # ── Données temps réel ──────────────────────────────────
    rt_str = ""
    if realtime and any(v is not None for v in realtime.values()):
        rt = realtime
        rt_str = (
            "\n═══ DONNÉES TEMPS RÉEL AU DIAGNOSTIC ═══\n"
            f"  RPM : {rt.get('rpm', 'N/A')} tr/min | Vitesse : {rt.get('speed', 'N/A')} km/h\n"
            f"  Température liquide : {rt.get('coolant_temp', 'N/A')} °C | Batterie : {rt.get('battery_voltage', 'N/A')} V\n"
            f"  Pression admission : {rt.get('intake_pressure', 'N/A')} kPa\n"
        )

    # ── Historique diagnostics précédents ───────────────────
    hist_str = ""
    if historique:
        lines = []
        for i, h in enumerate(historique[:5], 1):
            codes = ", ".join(h.get("dtc_codes", [])) or "Aucun"
            km_h = h.get("kilometrage", 0)
            date = h.get("date_affichage", "")
            statut_h = h.get("statut", "")
            lines.append(f"  Diag {i} — {date} ({km_h} km) : {codes} [{statut_h}]")
        hist_str = "\n═══ HISTORIQUE DIAGNOSTICS (5 derniers) ═══\n" + "\n".join(lines) + "\n"

    # ── Réparations passées ─────────────────────────────────
    repair_str = ""
    if reparations:
        lines = []
        for rep in reparations[:10]:
            d = rep.get("date_affichage", rep.get("date", ""))
            desc = rep.get("description", "")
            cout = rep.get("cout", "")
            lines.append(f"  {d} : {desc}" + (f" ({cout}€)" if cout else ""))
        repair_str = "\n═══ RÉPARATIONS ENREGISTRÉES ═══\n" + "\n".join(lines) + "\n⚠️ Les composants déjà remplacés peuvent être EXCLUS ou signalent une RÉCIDIVE.\n"

    # ── Rappels NHTSA ────────────────────────────────────────
    recalls = get_recalls_nhtsa(marque, modele, annee)
    recalls_str = ""
    if recalls:
        lines = [f"  - {r.get('Component','')}: {r.get('Summary',r.get('Consequence',''))[:100]}" for r in recalls[:3]]
        recalls_str = "\n═══ RAPPELS CONSTRUCTEURS NHTSA ═══\n" + "\n".join(lines) + "\n"

    # ── Résumé des analyses disponibles ─────────────────────────────────────
    has_ralenti  = bool(session_ralenti and session_ralenti.get("readings_count", 0) > 0)
    has_roulant  = bool(session_roulant and session_roulant.get("readings_count", 0) > 0)
    has_audio    = bool(anamnese and (
        anamnese.get("sons_decrits", "").strip() or anamnese.get("audio_peaks")
    ))
    ne_demarre   = anamnese.get("demarre", "") == "non" if anamnese else False

    analyses_str = (
        "\n═══ ANALYSES DISPONIBLES ═══\n"
        f"  • Lecture OBD statique (DTC + freeze frame) : OUI\n"
        f"  • Moteur tournant au ralenti              : {'OUI — données collectées' if has_ralenti else 'NON — non réalisé'}\n"
        f"  • Analyse en conduite                    : {'NON — véhicule ne démarrant pas' if ne_demarre else ('OUI — données collectées' if has_roulant else 'NON — non réalisé')}\n"
        f"  • Description acoustique client          : {'OUI — exploiter en section dédiée' if has_audio else 'NON — non fournie'}\n"
    )
    if ne_demarre:
        analyses_str += "  ⚠️ Contrainte : le véhicule ne démarre pas — adapter le diagnostic en conséquence.\n"

    prompt = f"""Tu es un expert en diagnostic automobile avec 20 ans d'expérience, spécialisé en diagnostic différentiel.
Tu dois produire un rapport de diagnostic professionnel, structuré, argumenté et directement exploitable.

VÉHICULE : {marque} {modele} {annee}{f" — {motorisation}" if motorisation else ""} — {f"VIN: {vin}" if vin and not vin.startswith("MANUEL_") else "VIN non lu"} — {km} km
CODES DTC : {dtc_str if dtc_codes else "AUCUN CODE DTC — diagnostic basé sur les symptômes et le contexte client"}
{analyses_str}
{anamnese_str}{ff_str}{rt_str}{section_ralenti}
{section_roulant}
{hist_str}{repair_str}{recalls_str}

═══════════════════════════════════════════════════════
MÉTHODE DE DIAGNOSTIC — APPLIQUE CES 4 PHASES :
═══════════════════════════════════════════════════════

PHASE 1 — INVENTAIRE DES PREUVES
Pèse chaque source disponible (DTC, anamnèse, freeze frame, sessions, historique, réparations, rappels NHTSA).
Pour chaque source : ce qu'elle révèle, ce qu'elle exclut, son poids dans le diagnostic.

PHASE 2 — CORRÉLATIONS ET INDICES CAUSAUX
▸ Code apparu APRÈS une intervention → lien causal probable
▸ Panne intermittente + aléatoire → exclut panne mécanique permanente
▸ Batterie < 12V + codes multiples sans lien → faux positifs probables
▸ RPM 258 + démarreur libre → refus injection logiciel, pas mécanique
▸ Freeze frame sous charge élevée → panne sous charge
▸ Même code récurrent après réparation → mauvais diagnostic initial
▸ Description acoustique → corréler avec système concerné

PHASE 3 — DIAGNOSTIC DIFFÉRENTIEL
Pour chaque code : classer suspects 🔴 (le plus probable) → 🟠 → 🟡 → ⚫ (écarté avec justification).
Scores cohérents, somme = 100. Identifier cause racine vs codes secondaires.

PHASE 4 — VERDICT ET PLAN D'ACTION CONCRET
Cause racine + codes secondaires expliqués + plan ordonné par priorité/coût.
Pour chaque étape du plan : action précise, durée estimée, coût estimé, priorité.

═══════════════════════════════════════════════════════

Fournis la réponse au format JSON strict (sans markdown) :
{{
  "codes": [
    {{
      "code": "P0XXX",
      "description": "Description claire",
      "systeme": "Système concerné",
      "est_cause_principale": true,
      "code_secondaire_de": null,
      "urgence": "URGENT|SURVEILLER|NON URGENT",
      "causes_probables": [
        {{"cause": "Cause 1 — explication concise max 15 mots", "score": 65, "niveau": "ROUGE", "explication_technique": "Mécanisme précis reliant cette cause aux données disponibles"}},
        {{"cause": "Cause 2", "score": 25, "niveau": "ORANGE", "explication_technique": "..."}},
        {{"cause": "Cause 3", "score": 10, "niveau": "JAUNE", "explication_technique": "..."}}
      ],
      "causes_exclues": [
        {{"cause": "Cause écartée", "raison": "Pourquoi écartée précisément"}},
        {{"cause": "Cause 2 écartée", "raison": "..."}}
      ],
      "action": "Action recommandée concrète",
      "test_recommande": "Test ou mesure à effectuer pour confirmer",
      "fourchette_prix": "X€ - Y€ (pièce + main d'œuvre)",
      "defaut_constructeur_connu": false,
      "detail_defaut_constructeur": null,
      "rappel_constructeur": false,
      "detail_rappel": null,
      "faux_positif_probable": false,
      "raison_faux_positif": null
    }}
  ],
  "root_cause_analysis": "Raisonnement causal complet : cause racine identifiée, pourquoi les autres codes sont secondaires, preuves utilisées.",
  "analyse_acoustique": {{
    "applicable": true,
    "type_bruit": "Type de bruit détecté ou 'Aucune description fournie'",
    "interpretation": "Interprétation mécanique ou électronique du bruit",
    "coherence": "Cohérence avec les codes DTC et les autres données"
  }},
  "causes_exclues_globales": [
    {{"cause": "Cause globale écartée", "raison": "Justification"}},
    {{"cause": "Cause 2", "raison": "..."}}
  ],
  "plan_action": [
    {{"etape": 1, "action": "Action précise et concrète", "duree_estimee": "30 min", "cout_estime": "Gratuit", "priorite": "URGENT"}},
    {{"etape": 2, "action": "...", "duree_estimee": "1h", "cout_estime": "30-60€", "priorite": "IMPORTANT"}},
    {{"etape": 3, "action": "...", "duree_estimee": "2h", "cout_estime": "200-400€", "priorite": "SI NÉCESSAIRE"}}
  ],
  "analyse_globale": "Résumé 2-3 phrases du diagnostic complet",
  "urgence_globale": "URGENT|SURVEILLER|OK",
  "diagnostic_confidence": 78,
  "confidence_limite_par": "Ce qui limite la précision (données manquantes, symptômes ambigus…)",
  "analyse_ralenti": "Analyse ralenti en 1-2 phrases ou N/A",
  "analyse_roulant": "Analyse conduite en 1-2 phrases ou Non réalisé / Non applicable",
  "correlations": "Corrélations clés entre mesures, codes, anamnèse et historique"
}}

RÈGLES STRICTES :
- causes_probables : niveau = "ROUGE" (>50%), "ORANGE" (20-50%), "JAUNE" (<20%) — somme scores = 100
- causes_exclues par code : objets avec "cause" et "raison" — max 4
- causes_exclues_globales : même format — hypothèses globales écartées
- plan_action : priorite = "URGENT", "IMPORTANT" ou "SI NÉCESSAIRE" — ordonné par priorité puis coût croissant
- analyse_acoustique.applicable = false si aucune description acoustique fournie
- est_cause_principale : true = cause racine, false = code secondaire/conséquence
- code_secondaire_de : null ou code parent (ex: "P0300")
- diagnostic_confidence : 0-100 (>80 très confiant, 60-80 confiant, <60 incertain)
- urgence_globale : exactement "URGENT", "SURVEILLER" ou "OK"
- Toutes les réponses en FRANÇAIS uniquement
- Ne jamais inventer de données — si une analyse n'a pas été réalisée, l'indiquer explicitement
- Si aucun code DTC : baser le diagnostic uniquement sur les symptômes, l'anamnèse et les sessions — utiliser "codes" = [] et mettre toute la valeur dans root_cause_analysis et plan_action
- Exploite TOUTES les données disponibles — ne laisse aucune preuve non analysée"""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        for fence in ("```json", "```"):
            if raw.startswith(fence):
                raw = raw[len(fence):]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        # Extraire uniquement le premier objet JSON complet
        start = raw.find("{")
        if start != -1:
            depth = 0
            end = start
            for i, ch in enumerate(raw[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            raw = raw[start:end + 1]
        parsed = json.loads(raw)
        return {
            "vin_info":              vin_info,
            "analyse":               parsed.get("codes", []),
            "resume":                parsed.get("analyse_globale", ""),
            "statut_global":         parsed.get("urgence_globale", "SURVEILLER"),
            "diagnostic_confidence": parsed.get("diagnostic_confidence", None),
            "confidence_limite_par": parsed.get("confidence_limite_par", ""),
            "root_cause_analysis":   parsed.get("root_cause_analysis", ""),
            "analyse_acoustique":    parsed.get("analyse_acoustique", None),
            "causes_exclues_globales": parsed.get("causes_exclues_globales", []),
            "plan_action":           parsed.get("plan_action", []),
            "analyse_ralenti":       parsed.get("analyse_ralenti", ""),
            "analyse_roulant":       parsed.get("analyse_roulant", ""),
            "correlations":          parsed.get("correlations", ""),
        }
    except Exception as exc:
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": f"Erreur : {exc}",
            "statut_global": "SURVEILLER",
            "error": str(exc),
        }


def analyze_session(vehicle: dict, session_data: dict) -> dict:
    """Analyse enrichie d'une session de monitoring avec corrélations et patterns."""
    stats = session_data.get("stats", {})
    anomalies = session_data.get("anomalies", [])
    dtcs = session_data.get("dtc_codes", [])
    duration = session_data.get("duration_seconds", 0)
    readings_count = session_data.get("readings_count", 0)

    def fmt_stat(key, unit):
        s = stats.get(key, {})
        if not s or s.get("max", 0) == 0:
            return "N/A"
        return f"min={s['min']}{unit} / max={s['max']}{unit} / moy={s['avg']}{unit}"

    anomalies_text = "\n".join([f"  - [{a['timestamp'][11:19]}] {a['message']}" for a in anomalies]) if anomalies else "  Aucune anomalie détectée"
    dtc_text = ", ".join(dtcs) if dtcs else "Aucun"

    prompt = f"""Tu es un expert en diagnostic automobile avec 20 ans d'expérience. Analyse cette session de conduite et fournis un diagnostic complet.

VÉHICULE : {vehicle.get('marque', 'N/A')} {vehicle.get('modele', 'N/A')} ({vehicle.get('annee', 'N/A')}) — VIN: {vehicle.get('vin', 'N/A')} — {vehicle.get('km', 'N/A')} km

SESSION : {duration}s de surveillance, {readings_count} relevés toutes les 2 secondes

STATISTIQUES MOTEUR :
- RPM          : {fmt_stat('rpm', ' tr/min')}
- Température  : {fmt_stat('temp', '°C')}
- Vitesse      : {fmt_stat('speed', ' km/h')}
- Batterie     : {fmt_stat('voltage', 'V')}

ANOMALIES DÉTECTÉES ({len(anomalies)}) :
{anomalies_text}

CODES DTC APPARUS : {dtc_text}

Fournis une analyse structurée en JSON valide (sans markdown) :

{{
  "bilan_sante": "Résumé de l'état moteur pendant cette session (2-3 phrases)",
  "analyse_anomalies": [
    {{
      "anomalie": "nom de l'anomalie",
      "interpretation": "ce que ça signifie concrètement",
      "cause_probable": "cause la plus probable",
      "lien_avec_autres": "corrélation avec d'autres mesures de la session si pertinent"
    }}
  ],
  "correlations": "Analyse des corrélations entre les mesures (ex: temp haute + rpm instables = suspect joint de culasse)",
  "diagnostic_probable": "Diagnostic global le plus probable basé sur l'ensemble des données",
  "actions": [
    {{"priorite": 1, "action": "action concrète", "urgence": "URGENT"}},
    {{"priorite": 2, "action": "action concrète", "urgence": "SURVEILLER"}}
  ],
  "urgence_globale": "URGENT",
  "conseil_conduite": "Conseil immédiat pour le conducteur (peut-il continuer à conduire ?)"
}}

Règles : urgence_globale = "URGENT" / "SURVEILLER" / "OK". Réponse en français uniquement."""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        for fence in ("```json", "```"):
            if raw.startswith(fence):
                raw = raw[len(fence):]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        start = raw.find("{")
        if start != -1:
            depth = 0
            end = start
            for i, ch in enumerate(raw[start:], start=start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            raw = raw[start:end + 1]
        return {"success": True, "result": json.loads(raw), "session": session_data}
    except Exception as exc:
        return {"success": False, "error": str(exc), "session": session_data}
