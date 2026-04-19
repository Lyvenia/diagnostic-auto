import re
import time

# Regex stricte : P/B/C/U + 4 chiffres exactement
_CODE_RE = re.compile(r'^[PBCU][0-9]{4}$')

# Adresses ECU CAN standards (tx_addr, label)
# 7DF = broadcast fonctionnel (OBD2 standard, interroge tous les ECUs conformes)
# 7E0..7E3 = adressage direct par ECU pour capturer les non-conformes
_ECU_ADDRESSES = [
    ("7E0", "Moteur/PCM"),
    ("7E1", "Boîte de vitesses/TCM"),
    ("7E2", "ABS/ESC"),
    ("7E3", "Airbag/SRS"),
]


def _normalize_code(raw) -> str | None:
    """Nettoie et valide un code DTC brut.

    Accepte : 'P0300', 'p0300', 'P 0300', 'P0300 ', b'P0300'…
    Rejette : chaînes vides, codes mal formés, octets non décodables.
    Retourne le code normalisé (str majuscule) ou None si invalide.
    """
    try:
        code = str(raw).strip().upper().replace(" ", "")
        if _CODE_RE.match(code):
            return code
    except Exception:
        pass
    return None


def _bus_flush(connection, obd_lib) -> None:
    """Envoie une commande légère (tension batterie) pour vider le bus ELM327.

    ELM_VOLTAGE est une commande AT directe (pas OBD) : très rapide,
    universellement supportée, ne perturbe pas l'ECU.
    """
    try:
        connection.query(obd_lib.commands.ELM_VOLTAGE)
    except Exception:
        pass


def _at_command(connection, obd_lib, cmd_str: str):
    """Envoie une commande AT brute via python-obd (ex: 'ATSH7E2')."""
    try:
        import obd as _obd
        at_cmd = _obd.OBDCommand(
            cmd_str, cmd_str,
            cmd_str.encode(),
            0,
            lambda messages: messages
        )
        connection.query(at_cmd)
    except Exception:
        pass


def _read_dtc_broadcast(connection, obd_lib) -> tuple[set, str]:
    """Mode 03 standard en broadcast 7DF — 3 tentatives avec délai adaptatif.

    Retourne (codes: set, status: str).
    """
    codes: set = set()
    status = "no_response"

    for attempt in range(3):
        try:
            r = connection.query(obd_lib.commands.GET_DTC)
            if not r.is_null() and r.value is not None:
                status = "ok"
                for item in r.value:
                    try:
                        code = _normalize_code(item[0])
                        if code:
                            codes.add(code)
                    except Exception:
                        pass
                break
            time.sleep(0.3 + attempt * 0.15)
        except Exception:
            status = "error"
            time.sleep(0.3 + attempt * 0.15)

    return codes, status


def _read_dtc_ecu_scan(connection, obd_lib, known_codes: set) -> set:
    """Scan multi-ECU : interroge chaque ECU par adressage CAN direct.

    Cible les ECUs qui ne répondent pas au broadcast standard (ABS, airbag…).
    Nettoie le header après chaque tentative pour ne pas polluer les lectures suivantes.
    Retourne uniquement les nouveaux codes (non déjà trouvés par broadcast).
    """
    new_codes: set = set()

    for tx_addr, label in _ECU_ADDRESSES:
        try:
            # Changer le header d'émission vers cet ECU
            _at_command(connection, obd_lib, f"ATSH{tx_addr}")
            time.sleep(0.05)

            r = connection.query(obd_lib.commands.GET_DTC)
            if not r.is_null() and r.value:
                for item in r.value:
                    try:
                        code = _normalize_code(item[0])
                        if code and code not in known_codes:
                            new_codes.add(code)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            # Toujours restaurer le header broadcast après chaque ECU
            _at_command(connection, obd_lib, "ATSH7DF")
            time.sleep(0.05)

    return new_codes


def _read_dtc_mode07(connection, obd_lib) -> set:
    """Mode 07 : DTC en attente (1 seul cycle de détection) — complètement isolé.

    Si Mode 07 échoue (véhicule pré-2003 ou non supporté), aucun effet
    sur les codes Mode 03 déjà collectés.
    """
    codes: set = set()
    try:
        r7 = connection.query(obd_lib.commands.GET_CURRENT_DTC)
        if not r7.is_null() and r7.value:
            for item in r7.value:
                try:
                    code = _normalize_code(item[0])
                    if code:
                        codes.add(code)
                except Exception:
                    pass
    except Exception:
        pass  # Mode 07 non supporté → silencieux
    return codes


def read_dtc(self) -> dict:
    """Lit les codes DTC sur tous les ECUs accessibles.

    Pipeline :
    1. Bus flush (vide le bus ELM327)
    2. Mode 03 broadcast 7DF (ECU standard OBD2)
    3. Scan multi-ECU 7E0-7E3 (ABS, airbag, boîte — non-OBD2 natif)
    4. Mode 07 (DTC en attente, 1 cycle de détection)

    Retourne :
      {
        "codes":  ["P0300", "C0040", ...],  # liste normalisée, triée
        "status": "ok"                       # "ok" | "no_response" | "error"
      }
    """
    if self.simulation_mode:
        return {"codes": list(self._simulate_dtc()), "status": "ok"}

    if not self.connection:
        return {"codes": [], "status": "error"}

    # Stopper le thread cache pour libérer le bus ELM327
    was_running = self._cache_thread_running
    if was_running:
        self._cache_thread_running = False
        time.sleep(0.4)

    try:
        import obd as obd_lib
    except ImportError:
        return {"codes": [], "status": "error"}

    all_codes: set = set()
    final_status = "no_response"

    try:
        # 1. Bus flush
        _bus_flush(self.connection, obd_lib)
        time.sleep(0.1)

        # 2. Mode 03 broadcast (ECU principal + tous les ECUs OBD2 conformes)
        broadcast_codes, final_status = _read_dtc_broadcast(self.connection, obd_lib)
        all_codes.update(broadcast_codes)

        # 3. Scan multi-ECU (ABS, airbag, boîte) — seulement si connexion établie
        if final_status in ("ok", "no_response"):
            extra = _read_dtc_ecu_scan(self.connection, obd_lib, all_codes)
            if extra:
                all_codes.update(extra)
                final_status = "ok"  # Des codes ont été trouvés même si le broadcast avait échoué

        # 4. Mode 07 (DTC en attente) — isolé
        pending = _read_dtc_mode07(self.connection, obd_lib)
        all_codes.update(pending)
        if pending and final_status == "no_response":
            final_status = "ok"

    finally:
        if was_running and self.connection:
            self._start_cache_thread()

    return {"codes": sorted(all_codes), "status": final_status}


def clear_dtc(self):
    if self.simulation_mode:
        cleared = list(self._sim_dtc or [])
        self._sim_dtc = []
        return {
            "success": True, "partial": False,
            "message": "Codes DTC effacés (simulation)",
            "cleared": cleared, "remaining": [], "permanent": []
        }
    if not self.connection:
        return {"success": False, "message": "Non connecté à un véhicule",
                "cleared": [], "remaining": [], "permanent": []}
    try:
        import obd

        was_running = self._cache_thread_running
        if was_running:
            self._cache_thread_running = False
            time.sleep(0.5)

        try:
            # Lire les codes AVANT effacement
            codes_before = []
            try:
                r = self.connection.query(obd.commands.GET_DTC)
                if not r.is_null():
                    codes_before = [
                        c for c in (_normalize_code(x[0]) for x in r.value if x[0])
                        if c
                    ]
            except Exception:
                pass

            time.sleep(0.3)
            self.connection.query(obd.commands.CLEAR_DTC)
            time.sleep(2.0)

            # Première vérification post-effacement
            codes_after = []
            try:
                r = self.connection.query(obd.commands.GET_DTC)
                if not r.is_null():
                    codes_after = [
                        c for c in (_normalize_code(x[0]) for x in r.value if x[0])
                        if c
                    ]
            except Exception:
                pass

            # Deuxième vérification anti-faux positif
            time.sleep(1.0)
            try:
                r2 = self.connection.query(obd.commands.GET_DTC)
                if not r2.is_null():
                    codes_after2 = [
                        c for c in (_normalize_code(x[0]) for x in r2.value if x[0])
                        if c
                    ]
                    codes_after = [c for c in codes_after if c in codes_after2]
            except Exception:
                pass

        finally:
            if was_running and self.connection:
                self._start_cache_thread()

        cleared   = [c for c in codes_before if c not in codes_after]
        remaining = list(codes_after)

        if not remaining:
            msg = "Tous les codes effacés avec succès" if cleared else "Aucun code à effacer"
            return {"success": True, "partial": False,
                    "message": msg, "cleared": cleared,
                    "remaining": [], "permanent": []}
        elif cleared:
            return {
                "success": True, "partial": True,
                "message": (f"{len(cleared)} code(s) effacé(s) — "
                            f"{len(remaining)} code(s) non effaçable(s) "
                            f"(défaut actif ou code permanent)"),
                "cleared": cleared, "remaining": remaining, "permanent": remaining
            }
        else:
            return {
                "success": False, "partial": False,
                "message": (f"{len(remaining)} code(s) non effaçable(s) — "
                            f"défaut toujours actif ou code OBD permanent (PDTC)"),
                "cleared": [], "remaining": remaining, "permanent": remaining
            }

    except Exception as exc:
        if self._cache_thread_running is False and self.connection:
            self._start_cache_thread()
        return {"success": False, "message": str(exc),
                "cleared": [], "remaining": [], "permanent": []}
