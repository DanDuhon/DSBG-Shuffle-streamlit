import json
from copy import deepcopy
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
        "Executioner's Chariot",
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
    "selected_characters": [],
    "edited_toggles": {},

    # Max allowed invaders in a shuffled encounter, by encounter level.
    # JSON keys are strings.
    "max_invaders_per_level": {
        "1": 2,
        "2": 3,
        "3": 5,
        "4": 4,
    },
}

def load_settings():
    """Load saved user settings, merged with defaults."""
    merged = deepcopy(DEFAULT_SETTINGS)
    if not SETTINGS_FILE.exists():
        return merged

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:
        return merged

    if not isinstance(loaded, dict):
        return merged

    # Merge top-level keys; merge known nested dicts.
    for k, v in loaded.items():
        if k in ("edited_toggles", "max_invaders_per_level") and isinstance(v, dict):
            merged.setdefault(k, {})
            merged[k].update(v)
        else:
            merged[k] = v

    # Clamp the invader limits to the supported maxima.
    clamps = {"1": 2, "2": 3, "3": 5, "4": 4}
    mip = merged.get("max_invaders_per_level")
    if not isinstance(mip, dict):
        mip = {}
    out = {}
    for lvl, mx in clamps.items():
        raw = mip.get(lvl, mx)
        try:
            val = int(raw)
        except Exception:
            val = mx
        out[lvl] = max(0, min(val, mx))
    merged["max_invaders_per_level"] = out

    return merged

def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
