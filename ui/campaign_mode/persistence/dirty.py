from __future__ import annotations

import json
from typing import Any, Dict, Optional

import streamlit as st


def _strip_ephemeral(obj: Any) -> Any:
    """Best-effort removal of UI/ephemeral keys for stable signatures."""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            # Convention: private/UI-only keys begin with underscore
            if k.startswith("_"):
                continue
            out[k] = _strip_ephemeral(v)
        return out
    if isinstance(obj, list):
        return [_strip_ephemeral(v) for v in obj]
    return obj


def campaign_signature(state: Dict[str, Any]) -> str:
    """Stable signature for a campaign state dict.

    Used to detect unsaved changes. Removes ephemeral/UI-only keys.
    """
    cleaned = _strip_ephemeral(state)
    try:
        return json.dumps(cleaned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        # Fallback: non-JSON-serializable values shouldn't happen, but don't crash UX.
        return repr(cleaned)


def _baseline_key(version: str) -> str:
    v = (version or "").upper()
    v = "V1" if v.startswith("V1") else "V2"
    return f"_campaign_baseline_sig_{v.lower()}"


def set_campaign_baseline(*, version: str, state: Dict[str, Any]) -> None:
    """Mark current state as saved/clean for the given rules version."""
    st.session_state[_baseline_key(version)] = campaign_signature(state)


def clear_campaign_baseline(*, version: str) -> None:
    """Clear baseline so a loaded/generated campaign is considered unsaved."""
    st.session_state.pop(_baseline_key(version), None)


def campaign_has_unsaved_changes(*, version: str, state: Optional[Dict[str, Any]] = None) -> bool:
    """Return True if a campaign exists and differs from the last saved baseline."""
    v = (version or "").upper()
    state_key = "campaign_v1_state" if v.startswith("V1") else "campaign_v2_state"

    cur = state if isinstance(state, dict) else st.session_state.get(state_key)
    if not isinstance(cur, dict) or not isinstance(cur.get("campaign"), dict):
        return False

    baseline = st.session_state.get(_baseline_key(v))
    if not isinstance(baseline, str) or not baseline:
        # No known saved baseline: treat as unsaved (generated but not saved).
        return True

    return campaign_signature(cur) != baseline


def any_campaign_has_unsaved_changes() -> bool:
    return campaign_has_unsaved_changes(version="V1") or campaign_has_unsaved_changes(version="V2")
