import json
import hashlib
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from core import supabase_store

SETTINGS_FILE = Path("data/user_settings.json")

DEFAULT_SETTINGS = {
    "ngplus_level": 0,
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
    "selected_characters": ["Assassin"],
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


EDITED_ENCOUNTER_CARDS_DIR = Path("assets/edited encounter cards")


def _discover_edited_encounter_toggle_keys() -> set[str]:
    """Return the set of valid `edited_toggles` keys based on assets on disk.

    Keys are stored in settings as: "<Encounter Name>|<Expansion>".

    Edited encounter card filenames are expected in the form:
        <Expansion>_<level>_<Encounter Name>.<ext>
    """

    if not EDITED_ENCOUNTER_CARDS_DIR.exists():
        return set()

    valid: set[str] = set()
    try:
        for p in EDITED_ENCOUNTER_CARDS_DIR.iterdir():
            if not p.is_file():
                continue
            parts = p.stem.split("_", 2)
            if len(parts) < 3:
                continue
            expansion, _level, encounter_name = parts
            expansion = expansion.strip()
            encounter_name = encounter_name.strip()
            if expansion and encounter_name:
                valid.add(f"{encounter_name}|{expansion}")
    except Exception:
        # If discovery fails for any reason, fail open (do not prune).
        return set()

    return valid


def _prune_edited_toggles(settings: dict) -> None:
    """In-place: drop `edited_toggles` entries for encounters without edits."""

    toggles = settings.get("edited_toggles")
    if not isinstance(toggles, dict) or not toggles:
        return

    valid = _discover_edited_encounter_toggle_keys()
    if not valid:
        return

    pruned = {k: bool(v) for k, v in toggles.items() if k in valid}
    settings["edited_toggles"] = pruned


def _prune_stray_top_level_edited_toggle_keys(settings: dict) -> None:
    """In-place: remove old/bad top-level encounter toggle keys.

    Historically, some UI code accidentally wrote per-encounter edited flags
    at the top-level of the settings dict using keys like
    "<Encounter Name>|<Expansion>". These are supposed to live under
    settings["edited_toggles"].
    """

    if not isinstance(settings, dict) or not settings:
        return

    # Only delete keys that look like encounter toggle keys and are simple bools.
    # This keeps the cleanup conservative.
    bad_keys = [k for k, v in settings.items() if isinstance(k, str) and "|" in k and isinstance(v, bool)]
    for k in bad_keys:
        # Never delete the actual nested dict key.
        if k == "edited_toggles":
            continue
        del settings[k]


def _maybe_streamlit():
    """Return the imported streamlit module if available, else None.

    Keeping this optional allows non-Streamlit scripts/tools to import this module
    without hard-depending on Streamlit.
    """

    try:
        import streamlit as st  # type: ignore

        return st
    except Exception:
        return None


def _parse_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "yes", "y", "on"):
            return True
        if v in ("0", "false", "no", "n", "off"):
            return False
    return None


def get_config_value(key: str, default: object = None) -> object:
    """Return a config value from Streamlit secrets (preferred) or env vars.

    This keeps Streamlit Cloud configuration in Secrets, while still allowing
    scripts/Docker to override via environment variables.
    """

    st = _maybe_streamlit()
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets.get(key)
        except Exception:
            pass

    if key in os.environ:
        return os.environ.get(key)

    return default


def get_config_bool(key: str, default: bool = False) -> bool:
    v = get_config_value(key, default=None)
    parsed = _parse_bool(v)
    if parsed is None:
        return bool(default)
    return parsed


def get_config_str(key: str, default: str | None = None) -> str | None:
    v = get_config_value(key, default=None)
    if v is None:
        return default
    try:
        return str(v)
    except Exception:
        return default


def is_streamlit_cloud() -> bool:
    """Return True when explicitly configured as Streamlit Cloud.

    This uses Streamlit Cloud Secrets (recommended) via:
      - DSBG_DEPLOYMENT = "cloud"

    Falls back to env var for non-Streamlit contexts.
    """

    deployment = (get_config_str("DSBG_DEPLOYMENT") or "").strip().lower()
    return deployment in {"cloud", "streamlit_cloud", "streamlitcloud"}


def load_settings():
    """Load persisted user settings and merge them onto DEFAULT_SETTINGS.

    Persistence precedence:
        - Streamlit Cloud: if Supabase is configured and the user is authenticated,
            load the per-account settings document.
        - Otherwise, read local JSON from `data/user_settings.json`.
    - If nothing can be loaded, returns a deepcopy of DEFAULT_SETTINGS.

    Merge / cleanup rules:
    - Top-level keys from the loaded payload overwrite defaults.
    - Known nested dicts are merged rather than replaced:
        - "edited_toggles"
        - "max_invaders_per_level"
    - Clamp "max_invaders_per_level" to supported maxima and non-negative values.
    - Prune/normalize edited-encounter flags:
        - remove accidental top-level "<Encounter>|<Expansion>" bool keys
        - keep only `edited_toggles` entries that still have an edited card on disk
    """
    merged = deepcopy(DEFAULT_SETTINGS)

    # Choose storage backend:
    # - Streamlit Cloud: Supabase per-account settings when logged in.
    # - Streamlit Cloud without Supabase: do not read shared local files.
    # - Otherwise: local JSON.
    if is_streamlit_cloud() and _has_supabase_config():
        try:
            from core import auth

            user_id = auth.get_user_id()
            access_token = auth.get_access_token()
        except Exception:
            user_id = None
            access_token = None

        loaded = None
        if user_id and access_token:
            loaded = supabase_store.get_document(
                "user_settings",
                "default",
                user_id=user_id,
                access_token=access_token,
            )
    elif is_streamlit_cloud():
        loaded = None
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

    # Avoid carrying stale per-encounter edited flags for encounters that have
    # no edited card on disk.
    _prune_stray_top_level_edited_toggle_keys(merged)
    _prune_edited_toggles(merged)

    return merged

def save_settings(settings: dict):
    """Persist settings (Supabase when configured, otherwise local JSON).

    Behavior:
    - Applies the same cleanup as `load_settings()` before writing:
        - remove stray top-level edited-toggle keys
        - prune `settings["edited_toggles"]` to encounters that have edited assets
    - Avoids redundant writes:
        - under Streamlit, returns early if `_settings_last_saved_fp` matches
        - for local JSON, skips rewriting the file if the fingerprint is unchanged
        - In Streamlit Cloud with Supabase configured, saving requires an authenticated
            account; when logged out, this returns False without persisting.

    Streamlit metadata keys (best-effort):
    - `_settings_last_saved_fp`: fingerprint of the last payload persisted
    - `_settings_last_saved_at`: ISO timestamp (UTC) of the last save
    These are used by the sidebar Save UI to compute "dirty" state and show
    last-saved time even when saves happen outside the sidebar.
    """

    # Keep the persisted payload tidy: only store per-encounter edited flags
    # for encounters that actually have edited cards available.
    _prune_stray_top_level_edited_toggle_keys(settings)
    _prune_edited_toggles(settings)

    new_fp = settings_fingerprint(settings)

    # Fast-path: if running under Streamlit and we know these settings were
    # already persisted, avoid touching any backend (prevents unnecessary
    # file mtime churn and redundant Supabase writes on reruns).
    st = _maybe_streamlit()
    if st is not None:
        try:
            if st.session_state.get("_settings_last_saved_fp") == new_fp:
                return True
        except Exception:
            pass

    if is_streamlit_cloud() and _has_supabase_config():
        # Cloud persistence requires an authenticated account.
        try:
            from core import auth

            user_id = auth.get_user_id()
            access_token = auth.get_access_token()
        except Exception:
            user_id = None
            access_token = None

        if not user_id or not access_token:
            return False

        # Attempt to persist to Supabase using the authenticated user id.
        try:
            res = supabase_store.upsert_document(
                "user_settings",
                "default",
                settings,
                user_id=user_id,
                access_token=access_token,
            )
            _update_streamlit_last_saved_metadata(settings)
            return res
        except Exception:
            return False

    # Streamlit Cloud should never persist anonymously to local JSON files.
    # If Supabase isn't configured, fail closed.
    if is_streamlit_cloud():
        return False

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Avoid rewriting the JSON file if the payload is identical.
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict) and settings_fingerprint(existing) == new_fp:
                return True
    except Exception:
        # If the file can't be read/parsed, fall back to rewriting it.
        pass

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    _update_streamlit_last_saved_metadata(settings)
    return True


def settings_fingerprint(settings: dict) -> str:
    """Return a stable fingerprint for a settings dict."""

    try:
        payload = json.dumps(
            settings,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
    except Exception:
        payload = repr(settings)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _update_streamlit_last_saved_metadata(settings: dict) -> None:
    """Best-effort Streamlit-only bookkeeping for the sidebar Save UI.

    Writes:
    - `st.session_state["_settings_last_saved_fp"]`
    - `st.session_state["_settings_last_saved_at"]` (UTC ISO string)

    This is intentionally non-critical: failures are swallowed so tools/scripts
    can call settings_manager without requiring Streamlit.
    """

    st = _maybe_streamlit()
    if st is None:
        return
    try:
        st.session_state["_settings_last_saved_fp"] = settings_fingerprint(settings)
        st.session_state["_settings_last_saved_at"] = datetime.now(timezone.utc).isoformat()
    except Exception:
        return


def _has_supabase_config() -> bool:
    """Return True when SUPABASE_URL and a Supabase API key are available via
    environment variables or Streamlit secrets (when running under Streamlit).
    This lets Docker/local runs (without secrets) continue using JSON files.
    """
    # Prefer environment variables for non-Streamlit runs (scripts, Docker)
    if os.environ.get("SUPABASE_URL") and (os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")):
        return True
    try:
        import streamlit as st

        if st.secrets.get("SUPABASE_URL") and (st.secrets.get("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_KEY")):
            return True
    except Exception:
        # streamlit may not be available in some contexts
        pass
    return False
