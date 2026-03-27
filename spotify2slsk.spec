# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for spotify2slsk

Build with: pyinstaller spotify2slsk.spec
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all rich submodules (it has many)
hidden_imports = collect_submodules('rich')
hidden_imports += [
    'requests',
    'urllib3',
    'charset_normalizer',
    'certifi',
    'idna',
    'unidecode',
]

# Try to include optional tray/notification packages if installed
try:
    import pystray
    hidden_imports += collect_submodules('pystray')
    hidden_imports += ['PIL', 'PIL.Image', 'PIL.ImageDraw']
    print("Including pystray (system tray support)")
except ImportError:
    print("pystray not installed - system tray disabled")

try:
    import win10toast
    hidden_imports += ['win10toast']
    print("Including win10toast (Windows notifications)")
except ImportError:
    pass

try:
    import plyer
    hidden_imports += collect_submodules('plyer')
    print("Including plyer (cross-platform notifications)")
except ImportError:
    pass

# Exclude large unnecessary packages
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    'cv2',
    'scipy',
    'test',
    'tests',
    'cryptography',  # no longer needed — HTTP loopback for OAuth
]

# Only exclude PIL if pystray is not being used
try:
    import pystray
except ImportError:
    excludes.append('PIL')

a = Analysis(
    ['downloader.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    a.zipfiles,
    a.datas,
    [],
    name='spotify2slsk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for our Rich UI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
