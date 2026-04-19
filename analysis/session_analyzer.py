import json
import os
from analysis.vin_decoder import _get_client
from core.paths import data_path


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
            model="claude-sonnet-4-5",   # Sonnet suffit pour l'analyse de session
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
            model="claude-sonnet-4-5",   # Sonnet : rapide et suffisant pour le monitoring
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
