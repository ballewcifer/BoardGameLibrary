# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Board Game Library
# Build with:  pyinstaller BoardGameLibrary.spec

block_cipher = None

a = Analysis(
    ['app.pyw'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ImageTk',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim heavy packages we never import
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'IPython', 'notebook', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BoardGameLibrary',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX off: avoids AV false-positives
    console=False,      # No console window (matches .pyw behaviour)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BoardGameLibrary',
)
