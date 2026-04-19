"""
Scanner multi-ECU — adressage direct des modules via ELM327 raw serial.
Lit les codes DTC de TOUS les modules : moteur, ABS, airbag, BCM, boîte, etc.
"""
import time
import re

# ── Base de données ECU par constructeur ──────────────────────────────────────
# tx = adresse d'envoi vers l'ECU, rx = adresse de réponse attendue

ECU_DATABASE = {
    "RENAULT": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "UCH (Carrosserie/BCM)", "tx": "764", "rx": "76C", "module": "bcm"},
        {"name": "Tableau de bord",       "tx": "763", "rx": "76B", "module": "cluster"},
        {"name": "Climatisation",         "tx": "767", "rx": "76F", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "76E", "rx": "776", "module": "eps"},
        {"name": "Injection diesel",      "tx": "7A0", "rx": "7A8", "module": "diesel"},
    ],
    "DACIA": [  # Même groupe Renault
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "UCH (Carrosserie/BCM)", "tx": "764", "rx": "76C", "module": "bcm"},
        {"name": "Climatisation",         "tx": "767", "rx": "76F", "module": "hvac"},
    ],
    "SKODA": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "713", "rx": "77D", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "715", "rx": "77F", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "714", "rx": "77E", "module": "bcm"},
        {"name": "Climatisation",         "tx": "7C4", "rx": "7CC", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "712", "rx": "77C", "module": "eps"},
        {"name": "Tableau de bord",       "tx": "717", "rx": "77B", "module": "cluster"},
        {"name": "Toit ouvrant / Confort","tx": "7C0", "rx": "7C8", "module": "comfort"},
    ],
    "VOLKSWAGEN": [  # Même groupe VAG que Skoda
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "713", "rx": "77D", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "715", "rx": "77F", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "714", "rx": "77E", "module": "bcm"},
        {"name": "Climatisation",         "tx": "7C4", "rx": "7CC", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "712", "rx": "77C", "module": "eps"},
        {"name": "Tableau de bord",       "tx": "717", "rx": "77B", "module": "cluster"},
    ],
    "AUDI": [  # Groupe VAG
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "713", "rx": "77D", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "715", "rx": "77F", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "714", "rx": "77E", "module": "bcm"},
        {"name": "Climatisation",         "tx": "7C4", "rx": "7CC", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "712", "rx": "77C", "module": "eps"},
    ],
    "TOYOTA": [
        {"name": "Moteur (ECM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / VSC",             "tx": "7C0", "rx": "7C8", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "750", "rx": "758", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "740", "rx": "748", "module": "bcm"},
        {"name": "Climatisation",         "tx": "747", "rx": "74F", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "7A0", "rx": "7A8", "module": "eps"},
        {"name": "Hybride (HV Battery)",  "tx": "7E2", "rx": "7EA", "module": "hybrid"},
    ],
    "LEXUS": [  # Même groupe Toyota
        {"name": "Moteur (ECM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / VSC",             "tx": "7C0", "rx": "7C8", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "750", "rx": "758", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "740", "rx": "748", "module": "bcm"},
        {"name": "Climatisation",         "tx": "747", "rx": "74F", "module": "hvac"},
    ],
    "SUZUKI": [
        {"name": "Moteur (ECM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS",                   "tx": "7B0", "rx": "7B8", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "720", "rx": "728", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "740", "rx": "748", "module": "bcm"},
        {"name": "Climatisation",         "tx": "7C0", "rx": "7C8", "module": "hvac"},
    ],
    "FIAT": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "764", "rx": "76C", "module": "bcm"},
        {"name": "Climatisation",         "tx": "767", "rx": "76F", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "76E", "rx": "776", "module": "eps"},
    ],
    "ALFA ROMEO": [  # Groupe FCA comme Fiat
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "764", "rx": "76C", "module": "bcm"},
    ],
    "PEUGEOT": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "BSI (Carrosserie)",     "tx": "764", "rx": "76C", "module": "bcm"},
        {"name": "Climatisation",         "tx": "767", "rx": "76F", "module": "hvac"},
        {"name": "Direction assistée",    "tx": "76E", "rx": "776", "module": "eps"},
    ],
    "CITROEN": [  # Même groupe PSA que Peugeot
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "760", "rx": "768", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "762", "rx": "76A", "module": "airbag"},
        {"name": "BSI (Carrosserie)",     "tx": "764", "rx": "76C", "module": "bcm"},
        {"name": "Climatisation",         "tx": "767", "rx": "76F", "module": "hvac"},
    ],
    "OPEL": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "7B0", "rx": "7B8", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "7D0", "rx": "7D8", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "7A0", "rx": "7A8", "module": "bcm"},
    ],
    "FORD": [
        {"name": "Moteur (PCM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS",                   "tx": "7D0", "rx": "7D8", "module": "abs"},
        {"name": "Airbag / SRS (RCM)",   "tx": "7D3", "rx": "7DB", "module": "airbag"},
        {"name": "BCM (Carrosserie)",     "tx": "726", "rx": "72E", "module": "bcm"},
        {"name": "Climatisation",         "tx": "733", "rx": "73B", "module": "hvac"},
    ],
    "BMW": [
        {"name": "Moteur (DME)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses (EGS)","tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / DSC",             "tx": "7B0", "rx": "7B8", "module": "abs"},
        {"name": "Airbag / SRS (ACSM)",  "tx": "7D0", "rx": "7D8", "module": "airbag"},
        {"name": "Carrosserie (FEM/BDC)", "tx": "7A0", "rx": "7A8", "module": "bcm"},
        {"name": "Climatisation (IHKA)",  "tx": "760", "rx": "768", "module": "hvac"},
    ],
    "MERCEDES": [
        {"name": "Moteur (ME/CDI)",       "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS / ESP",             "tx": "7A8", "rx": "7B0", "module": "abs"},
        {"name": "Airbag / SRS",          "tx": "7D0", "rx": "7D8", "module": "airbag"},
        {"name": "Carrosserie (SAM)",     "tx": "7A0", "rx": "7A8", "module": "bcm"},
    ],
    "GENERIC": [
        {"name": "Moteur (ECM)",          "tx": "7E0", "rx": "7E8", "module": "engine"},
        {"name": "Boîte de vitesses",     "tx": "7E1", "rx": "7E9", "module": "transmission"},
        {"name": "ABS",                   "tx": "7B0", "rx": "7B8", "module": "abs"},
        {"name": "Airbag",                "tx": "7D0", "rx": "7D8", "module": "airbag"},
        {"name": "Carrosserie (BCM)",     "tx": "7A0", "rx": "7A8", "module": "bcm"},
        {"name": "Climatisation",         "tx": "760", "rx": "768", "module": "hvac"},
    ],
}

# Mapping noms NHTSA → clés base de données
MAKE_ALIASES = {
    "RENAULT": "RENAULT", "DACIA": "DACIA",
    "SKODA": "SKODA", "VOLKSWAGEN": "VOLKSWAGEN", "VW": "VOLKSWAGEN",
    "AUDI": "AUDI", "SEAT": "SKODA",
    "TOYOTA": "TOYOTA", "LEXUS": "LEXUS",
    "SUZUKI": "SUZUKI",
    "FIAT": "FIAT", "ALFA ROMEO": "ALFA ROMEO", "ALFA": "ALFA ROMEO",
    "PEUGEOT": "PEUGEOT", "CITROEN": "CITROEN", "CITROËN": "CITROEN", "DS": "CITROEN",
    "OPEL": "OPEL", "VAUXHALL": "OPEL",
    "FORD": "FORD", "BMW": "BMW", "MERCEDES": "MERCEDES", "MERCEDES-BENZ": "MERCEDES",
}

# Icônes par module
MODULE_ICONS = {
    "engine":       "🔧",
    "transmission": "⚙️",
    "abs":          "🛑",
    "airbag":       "💥",
    "bcm":          "🚗",
    "cluster":      "📊",
    "hvac":         "❄️",
    "eps":          "🔄",
    "diesel":       "⛽",
    "hybrid":       "⚡",
    "comfort":      "🪟",
}


def get_ecu_list(make: str) -> list:
    """Retourne la liste des ECUs pour un constructeur donné."""
    make_key = MAKE_ALIASES.get(make.upper().strip(), "GENERIC")
    return ECU_DATABASE.get(make_key, ECU_DATABASE["GENERIC"])


def decode_dtc(b1: int, b2: int) -> str:
    """Décode 2 octets OBD2 en code DTC (P/C/B/U + 4 chiffres)."""
    cats = ['P', 'C', 'B', 'U']
    cat = cats[(b1 >> 6) & 0x03]
    d1 = (b1 >> 4) & 0x03   # premier chiffre (0-3)
    d2 = b1 & 0x0F           # deuxième chiffre (0-F)
    d3 = (b2 >> 4) & 0x0F   # troisième chiffre (0-F)
    d4 = b2 & 0x0F           # quatrième chiffre (0-F)
    return f"{cat}{d1}{d2:X}{d3:X}{d4:X}"


class MultiECUScanner:
    """Scanner multi-ECU via ELM327 en mode serial brut (pyserial)."""

    INIT_CMDS = [
        ("ATZ",   2.5),   # Reset complet ELM327
        ("ATE0",  0.5),   # Echo OFF
        ("ATL0",  0.5),   # Linefeeds OFF
        ("ATH0",  0.5),   # Headers OFF (réponse plus simple à parser)
        ("ATSP0", 1.5),   # Auto-détection protocole véhicule
        ("ATAT1", 0.5),   # Adaptive timing ON (adaptatif)
    ]

    def __init__(self, port: str, baudrate: int = 38400, timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def scan_all(self, make: str, progress_cb=None) -> dict:
        """
        Scanne tous les ECUs connus pour ce constructeur.
        progress_cb(module_name, idx, total) appelé à chaque ECU scanné.
        """
        ecus = get_ecu_list(make)
        results = {
            "make": make,
            "modules": [],
            "total_dtcs": 0,
            "modules_found": 0,
            "error": None,
        }

        try:
            import serial as _ser_mod
        except ImportError:
            results["error"] = "pyserial non disponible"
            return results

        try:
            self._ser = _ser_mod.Serial(
                self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=8, parity='N', stopbits=1,
                xonxoff=False, rtscts=False,
            )
            time.sleep(0.5)

            ok, err = self._init_elm327()
            if not ok:
                results["error"] = f"Init ELM327 échouée : {err}"
                return results

            total = len(ecus)
            for idx, ecu in enumerate(ecus):
                if progress_cb:
                    progress_cb(ecu["name"], idx + 1, total)
                mod = self._scan_ecu(ecu)
                results["modules"].append(mod)
                if mod["status"] == "ok":
                    results["modules_found"] += 1
                results["total_dtcs"] += len(mod.get("dtcs", []))
                time.sleep(0.15)  # petit délai entre modules

        except Exception as e:
            results["error"] = str(e)
        finally:
            try:
                if self._ser and self._ser.is_open:
                    self._ser.close()
            except Exception:
                pass

        return results

    def _init_elm327(self):
        """Initialise l'ELM327. Retourne (True, None) ou (False, erreur)."""
        for cmd, wait in self.INIT_CMDS:
            resp = self._send_raw(cmd, wait)
            if resp is None:
                return False, f"Pas de réponse à {cmd}"
        return True, None

    def _scan_ecu(self, ecu: dict) -> dict:
        """Scanne un ECU et retourne ses DTC."""
        result = {
            "name":    ecu["name"],
            "module":  ecu.get("module", "unknown"),
            "address": ecu["tx"],
            "icon":    MODULE_ICONS.get(ecu.get("module", ""), "🔧"),
            "status":  "no_response",
            "dtcs":    [],
        }

        tx = ecu["tx"]
        try:
            # Cibler l'ECU
            self._send_raw(f"AT SH {tx}", 0.3)
            # Requête Mode 03 — lecture des DTC
            raw = self._send_raw("03", 2.5)

            if not raw:
                return result

            raw_up = raw.upper().replace(" ", "")

            # Réponse vide ou ECU absent
            if any(x in raw_up for x in ("NODATA", "ERROR", "UNABLE", "BUSBUSY", "CANERROR", "?")):
                return result  # status reste "no_response"

            # Parser la réponse Mode 03
            dtcs = self._parse_mode03(raw_up)
            result["dtcs"] = dtcs
            result["status"] = "ok"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _parse_mode03(self, raw_clean: str) -> list:
        """
        Parse la réponse brute Mode 03 (sans espaces, sans headers).
        Format attendu : 43 [count] [B1 B2] [B1 B2] ...
        """
        dtcs = []

        # Trouver le marqueur de réponse Mode 03 (0x43)
        idx = raw_clean.find("43")
        if idx == -1:
            return dtcs

        payload = raw_clean[idx:]

        # Minimum : "43" + "00" (0 DTCs) = 4 chars
        if len(payload) < 4:
            return dtcs

        try:
            num = int(payload[2:4], 16)
        except ValueError:
            return dtcs

        if num == 0:
            return dtcs

        # Lire les paires d'octets
        pos = 4
        for _ in range(num):
            if pos + 4 > len(payload):
                break
            try:
                b1 = int(payload[pos:pos+2], 16)
                b2 = int(payload[pos+2:pos+4], 16)
                if b1 != 0x00 or b2 != 0x00:  # ignorer les bytes de padding
                    dtc = decode_dtc(b1, b2)
                    if dtc not in dtcs:
                        dtcs.append(dtc)
            except ValueError:
                pass
            pos += 4

        return dtcs

    def _send_raw(self, cmd: str, wait: float = 1.0) -> str | None:
        """Envoie une commande et attend la réponse jusqu'au prompt '>'."""
        if not self._ser or not self._ser.is_open:
            return None
        try:
            self._ser.reset_input_buffer()
            self._ser.write(f"{cmd}\r".encode("ascii"))
            buf = b""
            deadline = time.time() + wait
            while time.time() < deadline:
                chunk = self._ser.read(512)
                if chunk:
                    buf += chunk
                    if b">" in buf:
                        break
                else:
                    time.sleep(0.02)
            return buf.decode("ascii", errors="ignore").strip()
        except Exception:
            return None
