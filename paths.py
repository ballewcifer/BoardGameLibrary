"""Central path definitions for Board Game Library.

When running as a PyInstaller frozen executable, user data (database,
images, settings) is stored in %APPDATA%\\BoardGameLibrary so that
the app works correctly even when installed to Program Files (which is
read-only for non-admin users).

When running from source, data lives next to the script files so the
development workflow is unchanged.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller bundle: store data in the platform-appropriate user data folder.
    if sys.platform == "win32":
        # Windows: %APPDATA%\BoardGameLibrary
        DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "BoardGameLibrary"
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/BoardGameLibrary
        DATA_DIR = Path.home() / "Library" / "Application Support" / "BoardGameLibrary"
    else:
        # Linux / other: $XDG_DATA_HOME/BoardGameLibrary  (default ~/.local/share)
        DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "BoardGameLibrary"
else:
    # Development: store data next to the source files
    DATA_DIR = Path(__file__).parent

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH     = DATA_DIR / "library.db"
CONFIG_PATH = DATA_DIR / "settings.json"
IMAGES_DIR  = DATA_DIR / "images"
