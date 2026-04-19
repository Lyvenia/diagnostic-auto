# -*- mode: python ; coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════
#  RODIA.spec — Build CLIENT (simulation désactivée)
#  Nom de l'exe : RODIA.exe
#  Marqueur     : RODIA_CLIENT (bundlé dans _internal/) → active
#                 core.variant.CLIENT_BUILD = True au démarrage
# ══════════════════════════════════════════════════════════════════
from PyInstaller.utils.hooks import collect_all

datas = [
    ('frontend',     'frontend'),
    ('icon.ico',     '.'),
    ('RODIA_CLIENT', '.'),      # ← Marqueur build client
]
binaries = []
hiddenimports = [
    'flask', 'flask_cors', 'flask.templating',
    'anthropic',
    'obd', 'obd.commands', 'obd.protocols', 'obd.utils', 'obd.elm327', 'obd.decoders',
    'serial', 'serial.tools', 'serial.tools.list_ports',
    'reportlab', 'reportlab.lib', 'reportlab.platypus', 'reportlab.pdfbase',
    'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
    'pint', 'requests', 'tkinter', 'clr',
]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RODIA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RODIA',
)
