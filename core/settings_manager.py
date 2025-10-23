# core/settings_manager.py
import json
from pathlib import Path

SETTINGS_FILE = Path("data/user_settings.json")

DEFAULT_SETTINGS = {
    "active_expansions": [
        "Painted World of Ariamis",
        "The Sunless City",
        "Tomb of Giants",
        "Dark Souls The Board Game",
        "Darkroot",
        "Explorers",
        "Iron Keep",
        "Characters Expansion",
        "Phantoms",
        "Executioner Chariot",
        "Asylum Demon",
        "Black Dragon Kalameet",
        "Gaping Dragon",
        "Guardian Dragon",
        "Manus, Father of the Abyss",
        "Old Iron King",
        "The Four Kings",
        "The Last Giant",
        "Vordt of the Boreal Valley"
    ],
    "selected_characters": []
}

def load_settings():
    """Load saved user settings or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    """Save current settings to file."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
