# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Frontend (HTML/CSS/JS) bundlé dans le .exe
        ('frontend', 'frontend'),
    ],
    hiddenimports=[
        'obd',
        'obd.commands',
        'obd.protocols',
        'obd.protocols.protocol',
        'obd.protocols.elm_protocols',
        'obd.protocols.obd_protocols',
        'obd.utils',
        'obd.OBDResponse',
        'obd.decoders',
        'obd.elm327',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'anthropic',
        'flask',
        'flask_cors',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.colors',
        'reportlab.platypus',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'requests',
        'pint',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DiagnosticAuto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # console visible = utile pour voir les erreurs en phase de test
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
