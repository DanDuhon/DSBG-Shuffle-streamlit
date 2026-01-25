import json
import hashlib
import os
import uuid
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


def _runtime_client_id() -> str | None:
    """Best-effort client id lookup.

    Order:
    - env var (for scripts): DSBG_CLIENT_ID
    - Streamlit session_state["client_id"] when running in Streamlit
    """

    cid = os.environ.get("DSBG_CLIENT_ID")
    if cid:
        return cid

    st = _maybe_streamlit()
    if st is None:
        return None
    try:
        return st.session_state.get("client_id")
    except Exception:
        return None


def get_runtime_client_id() -> str | None:
    """Return a stable UUID string for the current client (best-effort).

    When running under Streamlit, this will attempt to create/persist the id
    (via query params/localStorage) using `core.client_id.get_or_create_client_id()`.

    Returns None when Streamlit isn't available and no env var is set.
    """

    # 1) Environment override (scripts/tools)
    cid = os.environ.get("DSBG_CLIENT_ID")
    if cid:
        try:
            uuid.UUID(str(cid))
            return str(cid)
        except Exception:
            return None

    st = _maybe_streamlit()
    if st is None:
        return None

    # 2) Session state (already established)
    try:
        cid = st.session_state.get("client_id")
    except Exception:
        cid = None
    if cid:
        try:
            uuid.UUID(str(cid))
            return str(cid)
        except Exception:
            cid = None

    # 3) Ask the browser bridge / query params helper to establish one
    try:
        from core import client_id as client_id_module

        cid = client_id_module.get_or_create_client_id()
    except Exception:
        cid = None

    if cid:
        try:
            uuid.UUID(str(cid))
        except Exception:
            cid = None

    if cid:
        try:
            st.session_state["client_id"] = str(cid)
        except Exception:
            pass
        return str(cid)

    return None

def load_settings():
    """Load persisted user settings and merge them onto DEFAULT_SETTINGS.

    Persistence precedence:
    - If Supabase is configured, prefer per-client settings when a client id is available:
        1) `DSBG_CLIENT_ID` env var (scripts/tools), else
        2) Streamlit `st.session_state["client_id"]` (app runtime)
      If no per-client doc exists, fall back to the global (NULL user_id) document.
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

    # Choose storage backend: Supabase when configured, otherwise local JSON.
    if _has_supabase_config():
        # Supabase schema requires user_id NOT NULL; always use per-client documents.
        client_id = get_runtime_client_id()

        loaded = None
        if client_id:
            loaded = supabase_store.get_document("user_settings", "default", user_id=client_id)
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
    - When Supabase is enabled, attempts a per-client upsert (creating a UUID
      `client_id` in the settings dict if needed).

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

    if _has_supabase_config():
        # Determine or create a client_id to persist per-client documents.
        client_id = settings.get("client_id")
        if client_id:
            try:
                uuid.UUID(str(client_id))
            except Exception:
                client_id = None

        if not client_id:
            client_id = get_runtime_client_id()

        if not client_id:
            # Last resort: generate one (but try to also mirror into Streamlit session)
            client_id = str(uuid.uuid4())
            st = _maybe_streamlit()
            if st is not None:
                try:
                    st.session_state["client_id"] = client_id
                except Exception:
                    pass

        settings["client_id"] = client_id

        # Attempt to persist to Supabase using the per-client id.
        try:
            res = supabase_store.upsert_document("user_settings", "default", settings, user_id=client_id)
            _update_streamlit_last_saved_metadata(settings)
            return res
        except Exception as exc:
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
