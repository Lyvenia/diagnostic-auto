"""
release.py — Pipeline de release RODIA en une commande.

Usage :
    python release.py            # affiche la version courante + plan
    python release.py --build    # build PyInstaller + Inno Setup + SHA-256
    python release.py --bump-patch    # 1.1.0 → 1.1.1 puis build
    python release.py --bump-minor    # 1.1.0 → 1.2.0 puis build
    python release.py --bump-major    # 1.1.0 → 2.0.0 puis build

À la fin du build :
    - dist/RODIA/                    contient l'app prête (PyInstaller)
    - installer/RODIA-Setup-vX.Y.Z.exe   l'installeur Inno Setup signable
    - installer/RODIA-Setup-vX.Y.Z.sha256   hash pour vérifier l'intégrité
    - release-info.json                  prêt à coller dans api.lyvenia.fr

Étapes finales (manuelles, le script affiche les commandes) :
    1. git tag vX.Y.Z && git push origin vX.Y.Z
    2. Créer la release GitHub avec RELEASE_NOTES_vX.Y.Z.md + uploader l'installateur
    3. Vérifier que api.lyvenia.fr/version pointe vers la nouvelle release
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 sur la console Windows (sinon cp1252 explose sur ✓ → ! etc)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent
VERSION_PY = ROOT / "core" / "version.py"
ISS_FILE   = ROOT / "RODIA-Setup.iss"
SPEC_FILE  = ROOT / "RODIA.spec"
DIST_DIR   = ROOT / "dist" / "RODIA"
INSTALLER_DIR = ROOT / "installer"

# Chemins probables d'Inno Setup Compiler (testés dans cet ordre).
# `_LOCAL` = install user-only sans admin (cas le plus courant sur Windows récents).
_LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")
ISCC_CANDIDATES = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    os.path.join(_LOCAL, "Inno Setup 6", "ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
    os.path.join(_LOCAL, "Inno Setup 5", "ISCC.exe"),
]

GH_REPO = "Lyvenia/diagnostic-auto"

# ────────────────────────────────────────────────────────────────────────────
#  Helpers : couleurs ANSI + utilitaires
# ────────────────────────────────────────────────────────────────────────────
def _supports_ansi() -> bool:
    return os.environ.get("TERM", "") != "dumb" and (sys.stdout.isatty() or os.environ.get("FORCE_COLOR"))

C_BOLD  = "\033[1m"  if _supports_ansi() else ""
C_DIM   = "\033[2m"  if _supports_ansi() else ""
C_OK    = "\033[32m" if _supports_ansi() else ""
C_WARN  = "\033[33m" if _supports_ansi() else ""
C_ERR   = "\033[31m" if _supports_ansi() else ""
C_INFO  = "\033[36m" if _supports_ansi() else ""
C_END   = "\033[0m"  if _supports_ansi() else ""

def step(n: int, total: int, msg: str) -> None:
    print(f"\n{C_BOLD}[{n}/{total}]{C_END} {C_INFO}{msg}{C_END}")

def ok(msg: str)   -> None: print(f"  {C_OK}✓{C_END} {msg}")
def warn(msg: str) -> None: print(f"  {C_WARN}!{C_END} {msg}")
def err(msg: str)  -> None: print(f"  {C_ERR}✗ {msg}{C_END}")

# ────────────────────────────────────────────────────────────────────────────
#  Lecture / écriture de la version
# ────────────────────────────────────────────────────────────────────────────
VERSION_RE_PY  = re.compile(r'RODIA_VERSION\s*=\s*"([^"]+)"')
VERSION_RE_ISS = re.compile(r'#define\s+AppVersion\s+"([^"]+)"')

def read_version() -> str:
    txt = VERSION_PY.read_text(encoding="utf-8")
    m   = VERSION_RE_PY.search(txt)
    if not m:
        raise SystemExit(f"{C_ERR}Impossible de lire la version dans {VERSION_PY}{C_END}")
    return m.group(1)

def write_version(new_version: str) -> None:
    """Met à jour les 2 fichiers de version (version.py + RODIA-Setup.iss)."""
    # version.py
    txt = VERSION_PY.read_text(encoding="utf-8")
    txt = VERSION_RE_PY.sub(f'RODIA_VERSION = "{new_version}"', txt, count=1)
    VERSION_PY.write_text(txt, encoding="utf-8")
    ok(f"core/version.py        → {new_version}")
    # RODIA-Setup.iss
    txt = ISS_FILE.read_text(encoding="utf-8")
    txt = VERSION_RE_ISS.sub(f'#define AppVersion   "{new_version}"', txt, count=1)
    ISS_FILE.write_text(txt, encoding="utf-8")
    ok(f"RODIA-Setup.iss        → {new_version}")

def bump_version(current: str, kind: str) -> str:
    parts = [int(x) for x in current.split(".")]
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[:3]
    if kind == "major":
        major += 1; minor = 0; patch = 0
    elif kind == "minor":
        minor += 1; patch = 0
    elif kind == "patch":
        patch += 1
    return f"{major}.{minor}.{patch}"

# ────────────────────────────────────────────────────────────────────────────
#  Pipeline build
# ────────────────────────────────────────────────────────────────────────────
def find_iscc() -> str | None:
    """Trouve ISCC.exe (compilateur Inno Setup) sur la machine.
    Cherche dans les chemins connus + scan dynamique de LOCALAPPDATA\\Programs
    et Program Files pour repérer les installs versions 5/6/7+.
    """
    # 1. Chemins explicites
    for path in ISCC_CANDIDATES:
        if path and Path(path).is_file():
            return path
    # 2. Dans le PATH système
    found = shutil.which("ISCC")
    if found:
        return found
    # 3. Scan dynamique : tout dossier "Inno Setup *" dans les emplacements probables
    for root in (_LOCAL, r"C:\Program Files", r"C:\Program Files (x86)"):
        if not root or not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                if entry.lower().startswith("inno setup"):
                    candidate = os.path.join(root, entry, "ISCC.exe")
                    if os.path.isfile(candidate):
                        return candidate
        except OSError:
            continue
    return None

def clean_build():
    for d in [ROOT / "dist", ROOT / "build"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            ok(f"Nettoyé : {d.relative_to(ROOT)}")

def run_pyinstaller():
    print(f"  {C_DIM}→ pyinstaller {SPEC_FILE.name} (peut prendre 2-5 min)…{C_END}")
    res = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"],
        cwd=ROOT,
    )
    if res.returncode != 0:
        raise SystemExit(f"{C_ERR}PyInstaller a échoué (code {res.returncode}){C_END}")
    if not (DIST_DIR / "RODIA.exe").is_file():
        raise SystemExit(f"{C_ERR}dist/RODIA/RODIA.exe introuvable après PyInstaller{C_END}")
    size_mb = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    ok(f"PyInstaller OK — dist/RODIA/ ({size_mb:.1f} MB)")

def run_inno_setup(version: str) -> Path:
    iscc = find_iscc()
    if not iscc:
        raise SystemExit(
            f"{C_ERR}Inno Setup Compiler (ISCC.exe) introuvable.{C_END}\n"
            "Installe Inno Setup 6 depuis https://jrsoftware.org/isinfo.php\n"
            "ou ajoute son dossier au PATH système."
        )
    ok(f"Inno Setup trouvé : {iscc}")
    print(f"  {C_DIM}→ ISCC RODIA-Setup.iss…{C_END}")
    res = subprocess.run([iscc, str(ISS_FILE)], cwd=ROOT)
    if res.returncode != 0:
        raise SystemExit(f"{C_ERR}Inno Setup a échoué (code {res.returncode}){C_END}")
    expected = INSTALLER_DIR / f"RODIA-Setup-v{version}.exe"
    if not expected.is_file():
        raise SystemExit(f"{C_ERR}Installeur attendu introuvable : {expected}{C_END}")
    size_mb = expected.stat().st_size / (1024 * 1024)
    ok(f"Installeur créé — {expected.relative_to(ROOT)} ({size_mb:.1f} MB)")
    return expected

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    sha_file = path.with_suffix(path.suffix + ".sha256")
    sha_file.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    ok(f"SHA-256 : {digest[:16]}…{digest[-8:]}")
    ok(f"Hash écrit : {sha_file.name}")
    return digest

def write_release_info(version: str, installer: Path, sha256: str):
    notes_file = ROOT / f"RELEASE_NOTES_v{version}.md"
    notes = notes_file.read_text(encoding="utf-8") if notes_file.is_file() else f"Version {version}"
    info = {
        "version":       version,
        "download_url":  f"https://github.com/{GH_REPO}/releases/download/v{version}/{installer.name}",
        "release_notes": notes,
        "sha256":        sha256,
        "installer":     installer.name,
        "size_bytes":    installer.stat().st_size,
    }
    out = ROOT / "release-info.json"
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(f"release-info.json prêt à coller dans api.lyvenia.fr")

def show_publish_steps(version: str, installer: Path, sha256: str):
    download_url = f"https://github.com/{GH_REPO}/releases/download/v{version}/{installer.name}"
    print(f"\n{C_BOLD}{'═' * 70}{C_END}")
    print(f"{C_BOLD}  Build terminé pour la v{version}{C_END}")
    print(f"{C_BOLD}{'═' * 70}{C_END}\n")
    print(f"{C_BOLD}Étapes pour publier :{C_END}\n")
    print(f"  {C_BOLD}1.{C_END} Tag git + push :")
    print(f"     {C_DIM}git add core/version.py RODIA-Setup.iss RELEASE_NOTES_v{version}.md{C_END}")
    print(f"     {C_DIM}git commit -m \"Release v{version}\"{C_END}")
    print(f"     {C_DIM}git tag v{version}{C_END}")
    print(f"     {C_DIM}git push origin main --tags{C_END}\n")
    print(f"  {C_BOLD}2.{C_END} Créer la release GitHub :")
    print(f"     {C_DIM}https://github.com/{GH_REPO}/releases/new?tag=v{version}{C_END}")
    print(f"     - Title : RODIA v{version}")
    print(f"     - Description : copier RELEASE_NOTES_v{version}.md")
    print(f"     - Attach : {installer.relative_to(ROOT)}\n")
    print(f"  {C_BOLD}3.{C_END} Mettre à jour api.lyvenia.fr/version (Railway) avec :")
    print(f"     {C_DIM}{{{C_END}")
    print(f"     {C_DIM}  \"version\": \"{version}\",{C_END}")
    print(f"     {C_DIM}  \"download_url\": \"{download_url}\",{C_END}")
    print(f"     {C_DIM}  \"release_notes\": \"...(voir RELEASE_NOTES_v{version}.md)\"{C_END}")
    print(f"     {C_DIM}}}{C_END}")
    print(f"     {C_DIM}(le JSON complet est dans release-info.json){C_END}\n")
    print(f"  {C_BOLD}4.{C_END} Vérifier sur un poste avec une version antérieure :")
    print(f"     - lancer RODIA → bandeau de mise à jour doit apparaître")
    print(f"     - cliquer « Installer maintenant » → install + relance")
    print(f"\n{C_BOLD}{'═' * 70}{C_END}\n")

# ────────────────────────────────────────────────────────────────────────────
#  Entry point
# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pipeline de release RODIA")
    parser.add_argument("--bump-patch", action="store_true", help="bump version patch (X.Y.Z → X.Y.Z+1) puis build")
    parser.add_argument("--bump-minor", action="store_true", help="bump version minor (X.Y → X.Y+1) puis build")
    parser.add_argument("--bump-major", action="store_true", help="bump version major (X → X+1) puis build")
    parser.add_argument("--build", action="store_true", help="build sans bump")
    parser.add_argument("--skip-clean", action="store_true", help="ne pas nettoyer dist/ et build/ (debug)")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="passer PyInstaller (debug)")
    parser.add_argument("--skip-inno", action="store_true", help="passer Inno Setup (debug)")
    args = parser.parse_args()

    cur_version = read_version()
    new_version = cur_version

    do_build = args.build or args.bump_patch or args.bump_minor or args.bump_major
    if not do_build:
        # Mode info seul
        print(f"{C_BOLD}RODIA — Pipeline de release{C_END}")
        print(f"  Version locale : {C_BOLD}{cur_version}{C_END}")
        print(f"  Repo GitHub    : {GH_REPO}")
        print(f"  Inno Setup     : {find_iscc() or 'NON TROUVÉ — installe-le'}\n")
        print(f"Usage :")
        print(f"  {C_DIM}python release.py --build{C_END}        # build sans bump")
        print(f"  {C_DIM}python release.py --bump-minor{C_END}   # {cur_version} → {bump_version(cur_version, 'minor')} puis build")
        print(f"  {C_DIM}python release.py --bump-patch{C_END}   # {cur_version} → {bump_version(cur_version, 'patch')} puis build")
        print(f"  {C_DIM}python release.py --bump-major{C_END}   # {cur_version} → {bump_version(cur_version, 'major')} puis build")
        return

    # ── Bump si demandé ────────────────────────────────────
    if args.bump_patch: new_version = bump_version(cur_version, "patch")
    if args.bump_minor: new_version = bump_version(cur_version, "minor")
    if args.bump_major: new_version = bump_version(cur_version, "major")

    print(f"\n{C_BOLD}Pipeline release RODIA{C_END}")
    print(f"  Version locale : {cur_version} → {C_BOLD}{new_version}{C_END}")

    total_steps = 5
    cur_step = 0

    if new_version != cur_version:
        cur_step += 1
        step(cur_step, total_steps, "Bump version (version.py + RODIA-Setup.iss)")
        write_version(new_version)
    else:
        total_steps -= 1

    # ── Clean ──
    if not args.skip_clean:
        cur_step += 1
        step(cur_step, total_steps, "Nettoyage des builds précédents")
        clean_build()

    # ── PyInstaller ──
    if not args.skip_pyinstaller:
        cur_step += 1
        step(cur_step, total_steps, "Build PyInstaller (dist/RODIA/)")
        run_pyinstaller()

    # ── Inno Setup ──
    installer = INSTALLER_DIR / f"RODIA-Setup-v{new_version}.exe"
    if not args.skip_inno:
        cur_step += 1
        step(cur_step, total_steps, "Compilation Inno Setup (installer/)")
        installer = run_inno_setup(new_version)

    # ── SHA-256 + release-info.json ──
    if installer.is_file():
        cur_step += 1
        step(cur_step, total_steps, "Hash SHA-256 + release-info.json")
        sha256 = compute_sha256(installer)
        write_release_info(new_version, installer, sha256)
        show_publish_steps(new_version, installer, sha256)
    else:
        warn(f"Installeur introuvable ({installer.name}) — étape SHA-256 / release-info.json sautée")

if __name__ == "__main__":
    main()
