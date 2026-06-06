from flask import Blueprint, jsonify, request
from shared import obd, fleet
from analysis.dtc_analyzer import analyze_dtc, analyze_full_diagnostic
from analysis.session_analyzer import analyze_with_session
from analysis.vin_decoder import _get_client, decode_vin
from core.paths import LOG_PATH
import time as _t
import traceback as _tb
import base64 as _b64
import io
import wave
import math
import struct

bp = Blueprint('analysis', __name__)


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


@bp.route("/api/decode-vin", methods=["POST"])
def api_decode_vin():
    """Décode un VIN. Cascade :
      1. Base VIN partagée Lyvenia (crowdsourcée, indexée par préfixe 11 chars)
         → effet réseau : 1 Trafic 2020 contribué = TOUS les Trafic 2020 identifiés
      2. WMI local + NHTSA (fallback hors-ligne)
      3. IA Claude (fallback ultime)
    """
    import requests as _req
    from core.auth_store import get_jwt as _get_jwt

    data = request.get_json() or {}
    vin = (data.get("vin") or "").strip().upper()
    if not vin or len(vin) < 11:
        return jsonify({"error": "VIN invalide"}), 400

    # ── 1. Base communautaire Lyvenia (préfixe extrait côté serveur) ──
    if len(vin) >= 11:
        try:
            headers = {}
            tok = _get_jwt()
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
            # On envoie le VIN complet ; le serveur extrait le préfixe 11 et ignore le suffixe
            r = _req.get(f"https://api.lyvenia.fr/vin/{vin}", headers=headers, timeout=5)
            if r.status_code == 200:
                shared = r.json()
                if shared.get("found"):
                    return jsonify({
                        "vin":          vin,
                        "marque":       shared.get("marque", "Inconnu"),
                        "modele":       shared.get("modele", "Inconnu"),
                        "annee":        str(shared.get("annee") or ""),
                        "motorisation": shared.get("motorisation", ""),
                        "source":       "community",
                        "shared_status":       shared.get("status"),
                        "shared_contributors": shared.get("contributions_count"),
                        "match_type":          shared.get("match_type", "prefix"),
                    })
        except Exception:
            pass  # silencieux — on retombe sur le décodage local

    # ── 2. Décodage local (WMI + NHTSA + Claude en dernier) ──
    try:
        result = decode_vin(vin)
        result["source"] = "local"
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json() or {}
    vin = data.get("vin", "")
    dtc_codes = data.get("dtc_codes") or []
    realtime = data.get("realtime") or {}
    try:
        kilometrage = int(data.get("kilometrage") or 0)
    except (TypeError, ValueError):
        kilometrage = 0

    if not vin:
        return jsonify({"error": "VIN manquant"}), 400

    _t0 = _t.time()
    try:
        historique  = fleet.get_history(vin)[:3]  if vin else []
        reparations = fleet.get_repairs(vin)[:10] if vin else []
        result = analyze_dtc(vin, dtc_codes, realtime, kilometrage,
                             historique=historique, reparations=reparations)
        _log(f"[analyze] ✓ {_t.time()-_t0:.1f}s VIN={vin!r}")
        return jsonify(result)
    except Exception as exc:
        _log(f"[analyze] ✗ CRASH {_t.time()-_t0:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/analyze-session", methods=["POST"])
def api_analyze_session():
    """Analyse enrichie croisant DTC + données de session surveillance continue."""
    data = request.get_json() or {}
    dtc_codes = data.get("dtc_codes", [])
    vehicle_info = data.get("vehicle_info", {})
    session_data = data.get("session_data", {})

    try:
        result = analyze_with_session(dtc_codes, vehicle_info, session_data)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/analyze-full", methods=["POST"])
def api_analyze_full():
    """Analyse complète : DTC + sessions + anamnèse + freeze frame + historique flotte."""
    data = request.get_json() or {}
    vin = data.get("vin", "")
    dtc_codes = data.get("dtc_codes") or []
    try:
        km = int(data.get("kilometrage") or 0)
    except (TypeError, ValueError):
        km = 0
    session_ralenti = data.get("session_ralenti") or None
    session_roulant = data.get("session_roulant") or None
    anamnese        = data.get("anamnese") or None
    freeze_frame    = data.get("freeze_frame") or None
    realtime        = data.get("realtime") or {}
    vehicle_manual  = data.get("vehicle_manual") or None

    if not vin and not vehicle_manual:
        return jsonify({"error": "VIN ou informations véhicule manquants"}), 400

    _log(f"[analyze-full] VIN={vin!r} anamnese={bool(anamnese)} vehicle_manual={bool(vehicle_manual)} dtc={dtc_codes}")
    _t0 = _t.time()

    # Enrichissement automatique depuis la flotte
    historique  = fleet.get_history(vin)[:5]  if vin else []
    reparations = fleet.get_repairs(vin)[:10] if vin else []

    try:
        _log(f"[analyze-full] → appel analyze_full_diagnostic (Lyvenia)")
        result = analyze_full_diagnostic(
            vin, dtc_codes, km,
            session_ralenti, session_roulant,
            anamnese=anamnese,
            freeze_frame=freeze_frame,
            realtime=realtime,
            historique=historique,
            reparations=reparations,
            vehicle_manual=vehicle_manual,
        )
        elapsed = _t.time() - _t0
        has_err = bool(result.get("error"))
        _log(f"[analyze-full] ← terminé en {elapsed:.1f}s error={has_err} analyses={len(result.get('analyse', []))}")
        return jsonify(result)
    except Exception as exc:
        elapsed = _t.time() - _t0
        _log(f"[analyze-full] ✗ CRASH après {elapsed:.1f}s : {exc}\n{_tb.format_exc()}")
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/audio/analyze", methods=["POST"])
def api_audio_analyze():
    """Analyse audio : décode WAV, calcule les stats + FFT, envoie à Claude (texte seul, sans scipy/matplotlib)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        wav_b64 = data.get("wav", "")
        vehicle_ctx = data.get("vehicle_context", "véhicule inconnu")

        if not wav_b64:
            return jsonify({"error": "Pas de données audio"}), 400

        # ── Décoder WAV ──────────────────────────────────────────────────────
        try:
            wav_bytes = _b64.b64decode(wav_b64)
            with wave.open(io.BytesIO(wav_bytes)) as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                n_ch = wf.getnchannels()
                raw = wf.readframes(n_frames)
        except Exception as e:
            _log(f"[audio] Décodage WAV échoué : {e}")
            return jsonify({"error": f"Fichier audio invalide : {e}"}), 400

        # Convertir en float [-1, 1] (mono 16 bits)
        fmt = f"<{n_frames * n_ch}h"
        try:
            pcm = struct.unpack(fmt, raw)
        except struct.error:
            count = len(raw) // 2
            pcm = struct.unpack(f"<{count}h", raw[:count * 2])
        # Mixdown mono si stéréo
        if n_ch == 2:
            pcm = [(pcm[i] + pcm[i+1]) / 2 for i in range(0, len(pcm)-1, 2)]
        samples = [s / 32768.0 for s in pcm]
        n = len(samples)
        duration = n / sr if sr > 0 else 0

        if n < 512:
            return jsonify({"error": "Enregistrement trop court"}), 400

        # ── Statistiques de base ──────────────────────────────────────────────
        rms = math.sqrt(sum(s*s for s in samples) / n)
        peak = max(abs(s) for s in samples)
        db_rms = 20 * math.log10(rms + 1e-9)
        db_peak = 20 * math.log10(peak + 1e-9)

        # ── Énergie par bande via sous-échantillonnage (O(n), pur Python) ──────
        band_labels = ["0-250Hz", "250-500Hz", "500-1kHz", "1k-2kHz", "2k-4kHz", "4k+Hz"]

        def rms_band(s, sr_in, lo, hi):
            """Énergie RMS du signal dans [lo, hi] Hz par filtrage moyenneur récursif."""
            if hi >= sr_in / 2:
                hi_sig = list(s)
            else:
                alpha = math.exp(-2 * math.pi * hi / sr_in)
                hi_sig, y = [], 0.0
                for x in s:
                    y = (1 - alpha) * x + alpha * y
                    hi_sig.append(y)
            if lo <= 0:
                lo_sig = [0.0] * len(s)
            else:
                alpha2 = math.exp(-2 * math.pi * lo / sr_in)
                lo_sig, y2 = [], 0.0
                for x in s:
                    y2 = (1 - alpha2) * x + alpha2 * y2
                    lo_sig.append(y2)
            band = [h - l for h, l in zip(hi_sig, lo_sig)]
            return math.sqrt(sum(v*v for v in band) / len(band)) if band else 0.0

        limits = [(0, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, sr // 2)]
        band_energy = [rms_band(samples, sr, lo, hi) for lo, hi in limits]
        total_e = sum(band_energy) or 1.0
        band_pct = [round(e / total_e * 100, 1) for e in band_energy]
        dominant_band = band_labels[band_pct.index(max(band_pct))]

        # ── Préparer le résumé acoustique pour Claude ─────────────────────────
        bands_str = "\n".join(f"  - {band_labels[i]}: {band_pct[i]}%" for i in range(len(band_labels)))
        audio_desc = f"""Durée : {duration:.1f}s | Fréquence d'échantillonnage : {sr} Hz
Niveau RMS : {db_rms:.1f} dBFS | Niveau crête : {db_peak:.1f} dBFS
Bande dominante : {dominant_band}

Répartition de l'énergie par bande de fréquence :
{bands_str}

Remarques :
- Niveau RMS > -20 dBFS = bruit fort/continu
- Niveau RMS < -40 dBFS = bruit léger ou intermittent
- Dominance basses fréquences (0-500Hz) = vibration mécanique grave (roulement, vilebrequin, détonation)
- Dominance moyennes fréquences (500-2kHz) = claquement soupapes, courroie, alternateur
- Dominance hautes fréquences (2kHz+) = sifflement (turbo, pneu, roulement usé)"""

        prompt = f"""Tu es un expert en diagnostic automobile et acoustique mécanique.

Voici l'analyse acoustique d'un bruit enregistré sur : {vehicle_ctx}

{audio_desc}

En te basant UNIQUEMENT sur ces données acoustiques, fournis un diagnostic :

1. 🔊 **Type de bruit probable** : claquement, grincement, frottement, vibration, sifflement, détonation...
2. 🔧 **Causes mécaniques probables** (ordonnées par probabilité selon les fréquences dominantes)
3. ⏱️ **Caractère du bruit** : continu / intermittent / rythmique / aléatoire (déduit du niveau RMS et des bandes)
4. ⚠️ **Urgence** : peut-on continuer à rouler ou faut-il stopper immédiatement ?
5. 🛠️ **Prochaine action** : quel diagnostic physique faire en priorité ?

Sois concis, précis et pratique. Si les données sont insuffisantes (bruit trop faible, silence), dis-le clairement."""

        client = _get_client()
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )

        return jsonify({
            "analysis": resp.content[0].text,
            "spectrogram": None,
            "duration": round(duration, 1),
            "sample_rate": sr,
            "bands": dict(zip(band_labels, band_pct)),
            "db_rms": round(db_rms, 1),
        })

    except Exception as e:
        _log(f"[audio] Erreur : {e}\n{_tb.format_exc()}")
        return jsonify({"error": str(e)}), 500
