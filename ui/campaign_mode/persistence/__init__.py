from pathlib import Path
from typing import Any, Dict
import json
import logging
import os
import streamlit as st

logger = logging.getLogger(__name__)

from core import supabase_store
from core import auth
from core.settings_manager import _has_supabase_config, is_streamlit_cloud


DATA_DIR = Path("data")
BOSSES_PATH = DATA_DIR / "bosses.json"
INVADERS_PATH = DATA_DIR / "invaders.json"
CAMPAIGNS_PATH = DATA_DIR / "campaigns.json"

class CampaignsUnavailable(RuntimeError):
    """The campaign store could not be reached.

    Distinct from "the user has no saved campaigns": callers must surface this
    as an error rather than rendering an empty list, which is indistinguishable
    from the user's saves having been deleted.
    """


# Simple in-memory cache for JSON files keyed by absolute path string.
# Modules can call with `reload=True` to force re-read from disk.
_JSON_CACHE: Dict[str, Any] = {}
# (mtime_ns, size) recorded per cached path, so an external write invalidates.
_JSON_CACHE_STAMPS: Dict[str, Any] = {}


def _file_stamp(path: Path):
    """(mtime_ns, size) for `path`, or None when it does not exist."""
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _load_json_object(path: Path, *, reload: bool = False) -> Dict[str, Any]:
    """Load a JSON object from path. Return cached value unless `reload`.

    The cache is also invalidated when the file changes on disk, so an edit
    made outside this process is picked up instead of being masked by a stale
    entry for the lifetime of the process.

    Raises ValueError if the file exists but is not a JSON object.
    Returns empty dict if file does not exist.
    """
    key = str(path)
    stamp = _file_stamp(path)
    if not reload and key in _JSON_CACHE and _JSON_CACHE_STAMPS.get(key) == stamp:
        return _JSON_CACHE[key]

    if not path.exists():
        _JSON_CACHE[key] = {}
        _JSON_CACHE_STAMPS[key] = stamp
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")

    _JSON_CACHE[key] = data
    _JSON_CACHE_STAMPS[key] = stamp
    return data


def load_json_file(path: Path, *, reload: bool = False):
    """Load arbitrary JSON from `path`. Uses the same in-memory cache.

    Returns parsed JSON (any JSON type). If the file does not exist, returns None.
    """
    key = str(path)
    stamp = _file_stamp(path)
    if not reload and key in _JSON_CACHE and _JSON_CACHE_STAMPS.get(key) == stamp:
        return _JSON_CACHE[key]

    if not path.exists():
        _JSON_CACHE[key] = None
        _JSON_CACHE_STAMPS[key] = stamp
        return None

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    _JSON_CACHE[key] = data
    _JSON_CACHE_STAMPS[key] = stamp
    return data


_CLOUD_CACHE_KEY = "_campaigns_cloud_cache_v1"


def _cloud_cache_get(user_id: str):
    """Return this session's cached cloud campaigns for `user_id`, or None."""
    try:
        cached = st.session_state.get(_CLOUD_CACHE_KEY)
    except Exception:
        return None
    if isinstance(cached, dict) and cached.get("user_id") == user_id:
        data = cached.get("data")
        if isinstance(data, dict):
            return data
    return None


def _cloud_cache_set(user_id: str, data: Dict[str, Any]) -> None:
    try:
        st.session_state[_CLOUD_CACHE_KEY] = {"user_id": user_id, "data": data}
    except Exception:
        pass


def invalidate_cloud_campaign_cache() -> None:
    """Drop this session's cached cloud campaign listing."""
    try:
        st.session_state.pop(_CLOUD_CACHE_KEY, None)
    except Exception:
        pass


def _load_campaigns(*, reload: bool = False) -> Dict[str, Any]:
    """Load all saved campaigns as a mapping name -> payload, cached by default.

    When Supabase is configured, campaigns are stored as individual rows
    with `doc_type = 'campaign'` and `key_name = <campaign name>`.
    """
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            return {}

        # Without this, every rerun costs 1 list + N get round trips, and the
        # Setup and Manage tabs each call this once — so ~2*(N+1) requests per
        # interaction. Writes invalidate it.
        if not reload:
            cached = _cloud_cache_get(user_id)
            if cached is not None:
                return cached

        try:
            names = supabase_store.list_documents("campaign", user_id=user_id, access_token=access_token)
        except Exception:
            logger.warning("Could not list remote campaigns.", exc_info=True)
            # Do NOT cache or return {} as if the user had none: a transient
            # failure would look exactly like "all your saves are gone".
            raise CampaignsUnavailable("Could not reach the campaign store.")

        out: Dict[str, Any] = {}
        for n in names:
            try:
                obj = supabase_store.get_document("campaign", n, user_id=user_id, access_token=access_token)
                if obj is not None:
                    out[n] = obj
            except Exception:
                logger.warning("Could not fetch remote campaign %r.", n, exc_info=True)
                continue

        _cloud_cache_set(user_id, out)
        return out

    # Streamlit Cloud should never read shared local files.
    if is_streamlit_cloud():
        return {}

    return _load_json_object(CAMPAIGNS_PATH, reload=reload)


def _save_campaigns(campaigns: Dict[str, Any]) -> bool:
    """Persist all campaigns. Returns True only if everything was written.

    Callers MUST check the result before marking the campaign clean or telling
    the user it saved: a silent failure here previously left the dirty flag
    cleared, so the user got a success message and lost their progress with no
    warning.
    """
    # Supabase-backed persistence: upsert each campaign as a separate row.
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            logger.warning("Campaign save skipped: not authenticated.")
            return False

        ok = True
        for name, obj in (campaigns or {}).items():
            try:
                supabase_store.upsert_document("campaign", name, obj, user_id=user_id, access_token=access_token)
            except Exception:
                logger.warning("Campaign upsert failed for %r.", name, exc_info=True)
                ok = False

        # Delete remote campaigns not present locally
        try:
            remote = supabase_store.list_documents("campaign", user_id=user_id, access_token=access_token)
            for r in remote:
                if r not in campaigns:
                    try:
                        if not supabase_store.delete_document(
                            "campaign", r, user_id=user_id, access_token=access_token
                        ):
                            logger.warning("Campaign delete reported failure for %r.", r)
                            ok = False
                    except Exception:
                        logger.warning("Campaign delete failed for %r.", r, exc_info=True)
                        ok = False
        except Exception:
            logger.warning("Could not reconcile remote campaign list.", exc_info=True)
            ok = False

        # The listing this session cached is now stale either way.
        invalidate_cloud_campaign_cache()
        return ok

    # Streamlit Cloud should never persist anonymously to local JSON.
    if is_streamlit_cloud():
        logger.warning("Campaign save skipped: no Supabase config on Cloud.")
        return False

    CAMPAIGNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file and atomically replace the target to
    # avoid corrupting the campaigns file on interruption.
    tmp_path = CAMPAIGNS_PATH.with_suffix(".tmp")

    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(campaigns, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                # os.fsync may not be available on all platforms/FS — ignore if it fails
                pass
        # Atomic replace
        os.replace(str(tmp_path), str(CAMPAIGNS_PATH))
        # Update cache, and re-stamp so our own write is not seen as external.
        _JSON_CACHE[str(CAMPAIGNS_PATH)] = campaigns
        _JSON_CACHE_STAMPS[str(CAMPAIGNS_PATH)] = _file_stamp(CAMPAIGNS_PATH)
    except Exception:
        logger.exception("Campaign save to %s failed.", CAMPAIGNS_PATH)
        # Cleanup temp file on failure
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            logger.warning("Could not remove temp file %s.", tmp_path, exc_info=True)
        return False

    return True


def clear_json_cache() -> None:
    """Clear the in-memory JSON cache."""
    _JSON_CACHE.clear()
    _JSON_CACHE_STAMPS.clear()


def get_bosses(*, reload: bool = False) -> Dict[str, Any]:
    return _load_json_object(BOSSES_PATH, reload=reload)


def get_invaders(*, reload: bool = False) -> Dict[str, Any]:
    return _load_json_object(INVADERS_PATH, reload=reload)


def get_campaigns(*, reload: bool = False) -> Dict[str, Any]:
    return _load_campaigns(reload=reload)

