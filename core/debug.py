import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json
import time
from typing import Any


def setup_logging(log_dir: str = "logs", log_file: str = "campaign_debug.log") -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dsbg")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(Path(log_dir) / log_file, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Mirror to stdout for developer convenience
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def dump_session_state(session_state: Any, out_dir: str = "data/debug") -> str:
    """Write a serialized snapshot of `session_state` to a timestamped JSON file.

    This is resilient to Streamlit's `SessionState` object which isn't a plain
    dict. It will attempt several strategies to extract key/value pairs.

    Returns the path written.
    """
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = Path(out_dir) / f"session_dump_{ts}.json"

    def _clean(obj: Any):
        try:
            # Ensure primitive serializability first
            json.dumps(obj)
            return obj
        except Exception:
            try:
                return str(obj)
            except Exception:
                return "<unserializable>"

    # Try common mappings in order: dict-like, .items(), __dict__, vars()
    serializable = {}
    try:
        if isinstance(session_state, dict):
            iterator = session_state.items()
        elif hasattr(session_state, "items") and callable(getattr(session_state, "items")):
            iterator = session_state.items()
        elif hasattr(session_state, "__dict__"):
            iterator = session_state.__dict__.items()
        else:
            iterator = vars(session_state).items()
    except Exception:
        iterator = []

    for k, v in iterator:
        serializable[str(k)] = _clean(v)

    # Fallback: if nothing extracted, try to stringify the whole object
    if not serializable:
        serializable = {"session_state": _clean(session_state)}

    # Write robustly to avoid empty-file edge cases.
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump({"ts": ts, "state": serializable}, fh, indent=2, ensure_ascii=False)
    except Exception:
        # As a last resort, attempt to write a simple text representation.
        try:
            with path.open("w", encoding="utf-8") as fh:
                fh.write(str({"ts": ts, "state": serializable}))
        except Exception:
            # If writing also fails, re-raise to let caller handle/log.
            raise

    return str(path)


def serialize_session_state_to_json(session_state: Any) -> str:
    """Return a JSON string representation of `session_state` suitable for logging.

    This uses the same cleaning strategy as `dump_session_state` but returns a
    compact JSON string instead of writing a file.
    """
    def _clean(obj: Any):
        try:
            return obj
        except Exception:
            try:
                return str(obj)
            except Exception:
                return "<unserializable>"

    serializable = {}
    try:
        if isinstance(session_state, dict):
            iterator = session_state.items()
        elif hasattr(session_state, "items") and callable(getattr(session_state, "items")):
            iterator = session_state.items()
        elif hasattr(session_state, "__dict__"):
            iterator = session_state.__dict__.items()
        else:
            iterator = vars(session_state).items()
    except Exception:
        iterator = []

    for k, v in iterator:
        # Keep values small: if large, replace with type/name
        try:
            json.dumps(v)
            serializable[str(k)] = v
        except Exception:
            serializable[str(k)] = _clean(v)

    if not serializable:
        serializable = {"session_state": _clean(session_state)}

    try:
        return json.dumps(serializable, default=str, ensure_ascii=False)
    except Exception:
        return str(serializable)


def make_light_campaign(campaign: Any) -> Any:
    """Produce a compact, JSON-friendly snapshot of a campaign.

    This selects a few common, essential fields (if present) and
    returns a shallow dict suitable for keeping as an in-session
    fallback that is less likely to be swept by cloud low-memory
    sanitizers.
    """
    if not isinstance(campaign, dict):
        return campaign

    keys = [
        "name",
        "bosses",
        "nodes",
        "encounters",
        "seed",
        "player_count",
        "current_node_id",
        "version",
        "rules",
    ]
    compact: dict = {}
    for k in keys:
        try:
            if k in campaign:
                compact[k] = campaign[k]
        except Exception:
            continue

    # If none of the canonical keys were present, fall back to a shallow copy
    if not compact:
        try:
            return dict(campaign)
        except Exception:
            return str(campaign)

    return compact


def write_last_frozen(version: str, compact_campaign: Any, out_dir: str = "data") -> str:
    """Write compact campaign JSON to `data/last_frozen_V{N}.json`.

    Returns the path written.
    """
    try:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        fn = Path(out_dir) / f"last_frozen_{str(version).lower()}.json"
        with fn.open("w", encoding="utf-8") as fh:
            json.dump({"version": version, "campaign": compact_campaign}, fh, ensure_ascii=False, indent=2)
        return str(fn)
    except Exception:
        raise


def read_last_frozen(version: str, in_dir: str = "data") -> Any:
    """Read compact campaign JSON previously written by `write_last_frozen`.

    Returns the compact campaign dict or None if missing/unreadable.
    """
    try:
        fn = Path(in_dir) / f"last_frozen_{str(version).lower()}.json"
        if not fn.exists():
            return None
        with fn.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload.get("campaign")
    except Exception:
        return None


def make_compact_dump(session_state: Any, out_path: str = "logs/compact_dump.json") -> str:
    """Write a compact JSON dump containing only keys useful for debugging cloud reclaim.

    Keys included: cloud_low_memory, campaign_v1_state, campaign_v2_state,
    campaign_v1_last_frozen, campaign_v2_last_frozen, pending_campaign_snapshot,
    campaign_load_notice, campaign_rules_version, campaign_rules_version_widget.

    Returns the path written.
    """
    keys = [
        "cloud_low_memory",
        "campaign_v1_state",
        "campaign_v2_state",
        "campaign_v1_last_frozen",
        "campaign_v2_last_frozen",
        "pending_campaign_snapshot",
        "campaign_load_notice",
        "campaign_rules_version",
        "campaign_rules_version_widget",
    ]

    def _clean_val(v: Any):
        try:
            json.dumps(v)
            return v
        except Exception:
            try:
                return str(v)
            except Exception:
                return None

    # Extract serializable snapshot
    serial: dict = {}
    try:
        if isinstance(session_state, dict):
            ss_iter = session_state.items()
        elif hasattr(session_state, "items") and callable(getattr(session_state, "items")):
            ss_iter = session_state.items()
        elif hasattr(session_state, "__dict__"):
            ss_iter = session_state.__dict__.items()
        else:
            ss_iter = vars(session_state).items()
    except Exception:
        ss_iter = []

    src = {k: v for k, v in ss_iter}
    for k in keys:
        if k in src:
            serial[k] = _clean_val(src.get(k))
        else:
            serial[k] = None

    Path(Path(out_path).parent).mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"ts": int(time.time()), "compact": serial}, fh, indent=2, ensure_ascii=False)
        return out_path
    except Exception:
        # Fallback: try to write a minimal text file
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(str({"ts": int(time.time()), "compact": serial}))
        return out_path
