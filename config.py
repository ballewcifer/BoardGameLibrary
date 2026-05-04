"""Tiny JSON-backed settings store."""
from __future__ import annotations

import json
from pathlib import Path

from paths import CONFIG_PATH

DEFAULTS: dict = {
    "bgg_username": "Ballewcifer",
    "bgg_token": "",
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    out = dict(DEFAULTS)
    out.update(data)
    return out


def save(settings: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
