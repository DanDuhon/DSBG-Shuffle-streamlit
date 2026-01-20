import json
import os
from copy import deepcopy
from pathlib import Path

from core import supabase_store

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

    # Choose storage backend: Supabase when configured, otherwise local JSON.
    if _has_supabase_config():
        loaded = supabase_store.get_document("user_settings", "default")
    else:
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            loaded = None

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
        val = int(raw)
        out[lvl] = max(0, min(val, mx))
    merged["max_invaders_per_level"] = out

    return merged

def save_settings(settings: dict):
    """Persist settings to Supabase if configured, otherwise to local JSON."""
    if _has_supabase_config():
        return supabase_store.upsert_document("user_settings", "default", settings)

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return True


def _has_supabase_config() -> bool:
    """Return True when SUPABASE_URL and SUPABASE_KEY are available via
    environment variables or Streamlit secrets (when running under Streamlit).
    This lets Docker/local runs (without secrets) continue using JSON files.
    """
    # Prefer environment variables for non-Streamlit runs (scripts, Docker)
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        return True
    try:
        import streamlit as st

        if st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_KEY"):
            return True
    except Exception:
        # streamlit may not be available in some contexts
        pass
    return False
