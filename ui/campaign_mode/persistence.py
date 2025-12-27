from pathlib import Path
from typing import Any, Dict
import json
import os


DATA_DIR = Path("data")
BOSSES_PATH = DATA_DIR / "bosses.json"
INVADERS_PATH = DATA_DIR / "invaders.json"
CAMPAIGNS_PATH = DATA_DIR / "campaigns.json"

# Simple in-memory cache for JSON files keyed by absolute path string.
# Modules can call with `reload=True` to force re-read from disk.
_JSON_CACHE: Dict[str, Any] = {}


def _load_json_object(path: Path, *, reload: bool = False) -> Dict[str, Any]:
    """Load a JSON object from path. Return cached value unless `reload`.

    Raises ValueError if the file exists but is not a JSON object.
    Returns empty dict if file does not exist.
    """
    key = str(path)
    if not reload and key in _JSON_CACHE:
        return _JSON_CACHE[key]

    if not path.exists():
        _JSON_CACHE[key] = {}
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")

    _JSON_CACHE[key] = data
    return data


def load_json_file(path: Path, *, reload: bool = False):
    """Load arbitrary JSON from `path`. Uses the same in-memory cache.

    Returns parsed JSON (any JSON type). If the file does not exist, returns None.
    """
    key = str(path)
    if not reload and key in _JSON_CACHE:
        return _JSON_CACHE[key]

    if not path.exists():
        _JSON_CACHE[key] = None
        return None

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    _JSON_CACHE[key] = data
    return data


def _load_campaigns(*, reload: bool = False) -> Dict[str, Any]:
    """Load all saved campaigns as a mapping name -> payload, cached by default."""
    return _load_json_object(CAMPAIGNS_PATH, reload=reload)


def _save_campaigns(campaigns: Dict[str, Any]) -> None:
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
        # Update cache
        _JSON_CACHE[str(CAMPAIGNS_PATH)] = campaigns
    except Exception:
        # Cleanup temp file on failure
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


def clear_json_cache() -> None:
    """Clear the in-memory JSON cache."""
    _JSON_CACHE.clear()


def get_bosses(*, reload: bool = False) -> Dict[str, Any]:
    return _load_json_object(BOSSES_PATH, reload=reload)


def get_invaders(*, reload: bool = False) -> Dict[str, Any]:
    return _load_json_object(INVADERS_PATH, reload=reload)


def get_campaigns(*, reload: bool = False) -> Dict[str, Any]:
    return _load_campaigns(reload=reload)

