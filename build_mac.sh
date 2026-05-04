#!/usr/bin/env bash
# build_mac.sh — Build Board Game Library for macOS.
#
# Produces:  dist/BoardGameLibraryInstaller-v1.0.dmg
#
# Prerequisites (install once):
#   brew install create-dmg
#   pip install pyinstaller pillow

set -euo pipefail

VERSION="1.0"
APP_NAME="Board Game Library"
APP_BUNDLE="dist/BoardGameLibrary.app"
DMG_OUT="dist/BoardGameLibraryInstaller-v${VERSION}.dmg"

echo "==> Generating macOS icon (icon.icns)..."
python create_icon_mac.py

echo "==> Building .app bundle with PyInstaller..."
python -m PyInstaller BoardGameLibrary-mac.spec --clean -y

if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: $APP_BUNDLE not found after PyInstaller build."
    exit 1
fi

echo "==> Packaging .dmg..."
rm -f "$DMG_OUT"

# create-dmg produces a polished installer disk image with:
#   • custom window size & icon positions
#   • an Applications symlink so users can drag-to-install
#   • the app icon displayed prominently
create-dmg \
    --volname "$APP_NAME" \
    --volicon "icon.icns" \
    --window-pos 200 120 \
    --window-size 600 380 \
    --icon-size 120 \
    --icon "BoardGameLibrary.app" 165 185 \
    --hide-extension "BoardGameLibrary.app" \
    --app-drop-link 430 185 \
    --no-internet-enable \
    "$DMG_OUT" \
    "$APP_BUNDLE"

echo ""
echo "Done! Installer: $DMG_OUT"
