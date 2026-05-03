"""
Reproduit le crash PDF en local (sans PyInstaller).
faulthandler dump le stack C même en cas de segfault.
"""
import faulthandler
faulthandler.enable()

import json
import os
import sys
import traceback
import io

# Force UTF-8 sur stdout (Windows cp1252 plante sur les emojis)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
FLOTTE_PATH = os.path.join(appdata, "RODIA", "flotte.json")
TARGET_VIN = "VF3CARHMF67000004"

with open(FLOTTE_PATH, encoding="utf-8") as f:
    flotte = json.load(f)

# La structure est {VIN: vehicle_dict}
vehicle = flotte.get(TARGET_VIN)
if not vehicle:
    print(f"[X] VIN {TARGET_VIN} introuvable")
    print(f"    VIN dispos : {list(flotte.keys())}")
    sys.exit(1)

hist = vehicle.get("historique") or []
print(f"[OK] Vehicule {TARGET_VIN} : {vehicle.get('marque')} {vehicle.get('modele')} {vehicle.get('annee')}")
print(f"[OK] Historique : {len(hist)} entree(s)")

if not hist:
    print("[X] Pas d'historique - ce vehicule n'a jamais ete diagnostique")
    print(f"    Cles du vehicule : {list(vehicle.keys())}")
    sys.exit(1)

diagnostic = hist[0]
print(f"[OK] Diag le plus recent : {diagnostic.get('date_affichage', '?')}")
print(f"[OK] DTC : {diagnostic.get('dtc_codes', [])}")

analyse_ia = diagnostic.get("analyse_ia") or {}
plan_action = analyse_ia.get("plan_action") or []
print(f"[OK] plan_action : {len(plan_action)} etape(s)")

# Dump chaque étape pour voir le contenu
print("\n--- DUMP PLAN_ACTION ---")
for i, step in enumerate(plan_action, 1):
    if isinstance(step, dict):
        print(f"\n#{i} keys={list(step.keys())}")
        for k, v in step.items():
            s = str(v) if v is not None else ""
            print(f"   {k}: len={len(s)} preview={s[:150]!r}")
    else:
        print(f"#{i} [!] pas un dict : {type(step).__name__} = {step!r}")

print("\n--- APPEL export_diagnostic_pdf ---")
try:
    from export.pdf import export_diagnostic_pdf
    garage = {"nom": "Test", "adresse": "", "tel": "", "email": "", "siret": ""}
    pdf_bytes = export_diagnostic_pdf(vehicle, diagnostic, garage=garage)
    out = os.path.join(os.path.dirname(__file__), "test_output.pdf")
    with open(out, "wb") as f:
        f.write(pdf_bytes)
    print(f"[OK] PDF genere : {len(pdf_bytes)} octets -> {out}")
except Exception as exc:
    print(f"[X] EXCEPTION : {type(exc).__name__}: {exc}")
    traceback.print_exc()
    sys.exit(2)
