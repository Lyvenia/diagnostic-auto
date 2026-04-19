import json
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
from analysis.vin_decoder import decode_vin, get_recalls_nhtsa, _get_client
from core.config import load_config

def _get_models() -> tuple[str, str]:
    """Retourne (model_rapide, model_complet) depuis config ou valeurs par défaut."""
    cfg = load_config()
    return (
        cfg.get("model_rapide",  "claude-sonnet-4-5"),
        cfg.get("model_complet", "claude-opus-4-5"),
    )

# ── Fallback offline : descriptions locales pour les codes DTC courants ────────
_OFFLINE_DTC = {
    "P0100": "Débitmètre d'air (MAF) — circuit défaillant",
    "P0101": "Débitmètre d'air (MAF) — plage/performance",
    "P0110": "Capteur température d'air admission — circuit",
    "P0115": "Capteur température liquide refroidissement — circuit",
    "P0120": "Capteur position papillon (TPS) A — circuit",
    "P0128": "Thermostat défaillant — température trop basse",
    "P0130": "Sonde lambda amont banc 1 — circuit",
    "P0171": "Mélange appauvri banc 1 — correction maximale atteinte",
    "P0172": "Mélange enrichi banc 1 — correction maximale atteinte",
    "P0174": "Mélange appauvri banc 2",
    "P0175": "Mélange enrichi banc 2",
    "P0200": "Circuit injecteur — défaut général",
    "P0300": "Ratés d'allumage aléatoires — plusieurs cylindres",
    "P0301": "Ratés d'allumage — cylindre 1",
    "P0302": "Ratés d'allumage — cylindre 2",
    "P0303": "Ratés d'allumage — cylindre 3",
    "P0304": "Ratés d'allumage — cylindre 4",
    "P0340": "Capteur position arbre à cames — circuit",
    "P0400": "Recyclage gaz d'échappement (EGR) — débit",
    "P0401": "Débit EGR insuffisant",
    "P0402": "Débit EGR excessif",
    "P0420": "Efficacité catalyseur insuffisante — banc 1",
    "P0430": "Efficacité catalyseur insuffisante — banc 2",
    "P0440": "Système EVAP — défaut général",
    "P0442": "Fuite EVAP — petite fuite détectée",
    "P0455": "Fuite EVAP — fuite importante",
    "P0500": "Capteur de vitesse véhicule — circuit",
    "P0600": "Bus série — défaut de communication",
    "P0700": "Système de contrôle boîte de vitesses — défaut",
    "P1000": "Cycle de conduite OBD2 non complété",
}


def _offline_fallback(vin_info: dict, dtc_codes: list) -> dict:
    """Retourne une analyse minimale basée sur la base locale si l'IA est indisponible."""
    analyses = []
    for code in dtc_codes:
        desc = _OFFLINE_DTC.get(code, f"Code {code} — description non disponible hors ligne")
        analyses.append({
            "code": code,
            "description": desc,
            "systeme": "Inconnu",
            "urgence": "SURVEILLER",
            "causes_probables": ["Diagnostic IA indisponible — analyse hors ligne"],
            "action": "Connectez-vous à internet pour une analyse complète",
            "fourchette_prix": "N/A",
            "defaut_constructeur_connu": False,
            "rappel_constructeur": False,
            "faux_positif_probable": False,
        })
    return {
        "vin_info": vin_info,
        "analyse": analyses,
        "resume": f"Analyse hors ligne — {len(dtc_codes)} code(s) DTC détecté(s). Connexion internet requise pour le diagnostic complet.",
        "statut_global": "SURVEILLER",
        "offline": True,
    }


def analyze_dtc(
    vin: str,
    dtc_codes: list,
    realtime_data: dict,
    kilometrage: int,
    historique: list = None,
    reparations: list = None,
) -> dict:
    # ── VIN decode + rappels NHTSA en parallèle ─────────────────────────────
    vin_info = {}
    recalls  = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_vin     = pool.submit(decode_vin, vin)
        fut_recalls = pool.submit(lambda: None)  # placeholder, lancé après vin_info disponible
        try:
            vin_info = fut_vin.result(timeout=8)
        except Exception:
            vin_info = {"marque": "Inconnu", "modele": "Inconnu", "annee": ""}
        try:
            recalls = get_recalls_nhtsa(
                vin_info.get("marque", ""),
                vin_info.get("modele", ""),
                vin_info.get("annee", "")
            )
        except Exception:
            recalls = []

    if not dtc_codes:
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": "Aucun code de défaut détecté. Le véhicule semble en bon état de fonctionnement.",
            "statut_global": "OK",
        }

    rt = realtime_data or {}
    engine_running = rt.get("engine_running")
    engine_ctx = (
        "⚠️ Moteur ÉTEINT au moment du diagnostic (contact mis, RPM = 0) — certains codes peuvent être provisoires."
        if engine_running is False else
        "✅ Moteur TOURNANT au moment du diagnostic."
        if engine_running is True else
        "État moteur inconnu."
    )
    realtime_str = "\n".join([
        f"  - {engine_ctx}",
        f"  - Vitesse : {rt.get('speed', 'N/A')} km/h",
        f"  - Régime moteur : {rt.get('rpm', 'N/A')} tr/min",
        f"  - Température liquide refroidissement : {rt.get('coolant_temp', 'N/A')} °C",
        f"  - Tension batterie : {rt.get('battery_voltage', 'N/A')} V",
        f"  - Pression admission : {rt.get('intake_pressure', 'N/A')} kPa",
    ])
    dtc_str = ", ".join(dtc_codes)

    # recalls already fetched above in parallel
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
        model_rapide, _ = _get_models()
        response = client.messages.create(
            model=model_rapide,
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

        start = raw.find("{")
        if start == -1:
            raise ValueError("Aucun objet JSON trouvé dans la réponse")
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
        # Fallback offline si l'IA est indisponible
        err_str = str(exc).lower()
        if any(k in err_str for k in ("connection", "timeout", "rate", "overload", "api")):
            return _offline_fallback(vin_info, dtc_codes)
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": f"Erreur lors de l'analyse : {exc}",
            "statut_global": "SURVEILLER",
            "error": str(exc),
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
    # ── VIN decode + rappels en parallèle pour réduire le temps d'attente ──
    if vin and not vin.startswith("MANUEL_"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_vin = pool.submit(decode_vin, vin)
            try:
                vin_info = fut_vin.result(timeout=10)
            except Exception:
                vin_info = {"marque": "Inconnu", "modele": "Inconnu", "annee": "", "motorisation": ""}
    else:
        vin_info = {"marque": "Inconnu", "modele": "Inconnu", "annee": "", "motorisation": ""}

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

    # ── Rappels NHTSA (appel réseau, déjà fait en // si possible) ───────────
    try:
        recalls = get_recalls_nhtsa(marque, modele, annee)
    except Exception:
        recalls = []
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
  "correlations": "Corrélations clés entre mesures, codes, anamnèse et historique",
  "pieces_necessaires": [
    {{
      "nom": "Nom commercial de la pièce en français",
      "reference_probable": "Référence OEM ou aftermarket probable (ex: 0280142460) ou null si inconnue",
      "marques_compatibles": "Bosch, Delphi, NGK… (2-3 marques aftermarket courantes) ou null",
      "type_piece": "capteur|filtre|pompe|joint|courroie|sonde|vanne|injecteur|autre",
      "etape_plan": 2,
      "urgence": "URGENT|IMPORTANT|SI NÉCESSAIRE"
    }}
  ]
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
- pieces_necessaires : UNIQUEMENT les pièces physiques à remplacer (pas les diagnostics ni les tests), 0-6 pièces max — laisser [] si aucune pièce à remplacer (ex: simple reset ou test)
- pieces_necessaires.reference_probable : référence OEM fabricant d'origine OU aftermarket probable — null si vraiment inconnue, NE PAS inventer une référence aléatoire
- Toutes les réponses en FRANÇAIS uniquement
- Ne jamais inventer de données — si une analyse n'a pas été réalisée, l'indiquer explicitement
- Si aucun code DTC : baser le diagnostic uniquement sur les symptômes, l'anamnèse et les sessions — utiliser "codes" = [] et mettre toute la valeur dans root_cause_analysis et plan_action
- Exploite TOUTES les données disponibles — ne laisse aucune preuve non analysée"""

    try:
        client = _get_client()
        _, model_complet = _get_models()
        response = client.messages.create(
            model=model_complet,
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
            "pieces_necessaires":    parsed.get("pieces_necessaires", []),
            "analyse_ralenti":       parsed.get("analyse_ralenti", ""),
            "analyse_roulant":       parsed.get("analyse_roulant", ""),
            "correlations":          parsed.get("correlations", ""),
        }
    except Exception as exc:
        # Fallback offline si l'IA est indisponible
        err_str = str(exc).lower()
        if any(k in err_str for k in ("connection", "timeout", "rate", "overload", "api")):
            return _offline_fallback(vin_info, dtc_codes)
        return {
            "vin_info": vin_info,
            "analyse": [],
            "resume": f"Erreur : {exc}",
            "statut_global": "SURVEILLER",
            "error": str(exc),
        }
