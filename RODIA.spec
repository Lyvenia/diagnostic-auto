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
    'flask.templating',  # collect_all('flask') ne capture pas toujours ce sous-module
    'flask_cors',
    'tkinter',
    'shared',
]

# ── Libs avec ressources lazy-loadées (data files, plugins, fonts, certs) ────
# Toute lib qui charge des ressources via __file__ ou qui a des plugins
# dynamiques DOIT passer par collect_all. Sinon → crash silencieux en frozen.
for _pkg in (
    'webview',         # pywebview
    'obd',             # PIDs, decoders, protocoles
    'reportlab',       # fonts Vera/DarkGarden + metrics _fontdata_*
    'PIL',             # plugins image (PNG, JPEG, etc.)
    'anthropic',       # SDK Claude (httpx + JSON schemas)
    'httpx',           # transport HTTP de anthropic
    'certifi',         # bundle CA cacert.pem (HTTPS sans ça → SSLError)
    'requests',        # idem, + charset_normalizer/idna/urllib3
    'openpyxl',        # XSD schemas + templates XLSX
    'flask',           # Werkzeug/Jinja2 includes
    'jinja2',          # templates Flask
    'serial',          # pyserial (list_ports_windows backend)
):
    _d, _b, _h = collect_all(_pkg)
    datas += _d; binaries += _b; hiddenimports += _h


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclusions critiques : ces libs sont dans le venv (deps d'autres projets)
    # mais RODIA ne les utilise pas. Sans excludes, collect_all('anthropic') &
    # consorts les tirent quand même → +1.5 Go inutile dans dist/.
    excludes=[
        # ML / data science (1.5+ Go combiné)
        'tensorflow', 'tensorflow_*', 'tensorboard', 'tensorboard_*',
        'torch', 'torchvision', 'torchaudio', 'torch_*',
        'sklearn', 'scikit-learn', 'scikit_learn',
        'scipy', 'pandas',
        # Vision / vidéo
        'cv2', 'opencv-python', 'opencv_python',
        'imageio', 'imageio_ffmpeg', 'av',
        # Plot / viz
        'matplotlib', 'seaborn', 'plotly', 'bokeh',
        # Compilation / runtime ML
        'llvmlite', 'numba',
        # Big data formats
        'h5py', 'tables',  # PyTables
        'lxml',            # ReportLab/openpyxl peuvent fonctionner sans
        'pyarrow',
        # gRPC (pas utilisé)
        'grpc', 'grpcio',
        # Transformers / NLP (si présents dans le venv)
        'transformers', 'tokenizers', 'sentencepiece', 'safetensors',
        # Notebook / dev
        'IPython', 'ipykernel', 'ipython', 'jupyter', 'jupyter_*',
        'notebook', 'jupyterlab', 'qtconsole',
        # Tests
        'pytest', 'pytest_*', '_pytest', 'hypothesis',
        # Doc
        'sphinx', 'sphinx_*', 'docutils',
    ],
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
    # UPX casse fréquemment les DLL C-extensions (ReportLab _rl_accel, Pillow
    # _imaging, crypto/SSL, sockets) → crash silencieux au premier appel.
    upx_exclude=[
        # ReportLab + Pillow
        '_rl_accel*.pyd',
        '_imaging*.pyd',
        '_imagingft*.pyd',
        '_imagingcms*.pyd',
        '_imagingmath*.pyd',
        '_imagingmorph*.pyd',
        '_imagingtk*.pyd',
        # Crypto / SSL / sockets — critique pour requests, anthropic, lyvenia
        '_ssl*.pyd',
        '_hashlib*.pyd',
        '_socket*.pyd',
        '_cffi*.pyd',
        'libssl-*.dll',
        'libcrypto-*.dll',
        # Runtime
        'vcruntime140*.dll',
        'python3*.dll',
    ],
    name='RODIA',
)
