# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the macOS build of Board Game Library.
# Build with (on a Mac):
#   pyinstaller BoardGameLibrary-mac.spec -y

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
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='BoardGameLibrary',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='BoardGameLibrary.app',
    icon='icon.icns',
    bundle_identifier='com.ballewcifer.boardgamelibrary',
    info_plist={
        'CFBundleName':             'Board Game Library',
        'CFBundleDisplayName':      'Board Game Library',
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion':          '1.0.0',
        'NSPrincipalClass':         'NSApplication',
        'NSHighResolutionCapable':  True,
        'NSHumanReadableCopyright': 'Copyright © 2026 Ballewcifer',
    },
)
