import json
import streamlit as st
import os
import uuid
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
        # If the session has a client id, prefer per-client settings
        client_id = None
        try:
            client_id = st.session_state.get("client_id")
        except Exception:
            client_id = None

        loaded = None
        if client_id:
            loaded = supabase_store.get_document("user_settings", "default", user_id=client_id)
        # Fallback to global (NULL user_id) document
        if loaded is None:
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
        # Determine or create a client_id to persist per-client documents.
        client_id = None
        try:
            client_id = st.session_state.get("client_id")
        except Exception:
            client_id = None

        if not client_id:
            client_id = settings.get("client_id")

        if not client_id:
            client_id = str(uuid.uuid4())
            settings["client_id"] = client_id
            try:
                st.session_state["client_id"] = client_id
            except Exception:
                pass

        # Attempt to persist to Supabase using the per-client id and surface a one-time UI message.
        try:
            res = supabase_store.upsert_document("user_settings", "default", settings, user_id=client_id)
            # Avoid repeated notifications in the same Streamlit session
            try:
                if st and not st.session_state.get("supabase_tested"):
                    st.success("Settings saved to Supabase successfully.")
                    st.session_state["supabase_tested"] = True
            except Exception:
                pass
            return res
        except Exception as exc:
            try:
                if st:
                    st.error(f"Failed to save settings to Supabase: {exc}")
            except Exception:
                pass
            return False

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
