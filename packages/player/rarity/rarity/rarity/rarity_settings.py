"""
settings cuz why not
"""

from __future__ import annotations

import os

SETTINGS_FILE = "/code/admin_panel/config/rarity_settings.txt"

DEFAULTS = {
    "embed_color": "",       
    "style": "container",    
    "buttons_inside": "true", 
}


def load_settings() -> dict[str, str]:
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key in DEFAULTS:
                    data[key] = value.strip()
    except FileNotFoundError:
        pass
    return data


def save_settings(data: dict[str, str]) -> None:
    merged = load_settings()
    merged.update(data)
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        for key, value in merged.items():
            f.write(f"{key}={value}\n")


def get_embed_color() -> str:
    return load_settings()["embed_color"]


def get_style() -> str:
    return load_settings()["style"]


def get_buttons_inside() -> bool:
    return load_settings()["buttons_inside"] == "true"
