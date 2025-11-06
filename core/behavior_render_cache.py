
from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List, Optional

import streamlit as st

# Import your existing renderers (no changes needed in those functions)
# behavior_decks.py must be importable on PYTHONPATH
from core.behavior_icons import render_data_card as _render_data_card_raw
from core.behavior_icons import render_behavior_card as _render_behavior_card_raw


def _hash_json(obj: Any) -> str:
    try:
        s = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except TypeError:
        # Fallback for non-JSON-serializable objects: use repr
        s = repr(obj)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Single-card cached renderers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def render_data_card_cached(
    base_path: str,
    raw_json: Dict[str, Any],
    is_boss: bool,
    no_edits: bool = False,
    variant_id: Optional[str] = None,
) -> bytes:
    """
    Cached wrapper for render_data_card(...). Returns PNG bytes.
    Cache key includes a stable hash of raw_json and variant.
    """
    _ = _hash_json(raw_json)  # incorporated into Streamlit cache key by argument value
    _ = variant_id
    return _render_data_card_raw(base_path, raw_json, is_boss, no_edits)


@st.cache_data(show_spinner=False)
def render_behavior_card_cached(
    base_path: str,
    behavior_json: Dict[str, Any],
    is_boss: bool,
    base_card: Optional[bytes] = None,
    variant_id: Optional[str] = None,
) -> bytes:
    """
    Cached wrapper for render_behavior_card(...). Returns PNG bytes.
    Cache key includes a stable hash of behavior_json and variant.
    """
    _ = _hash_json(behavior_json)  # incorporated into Streamlit cache key by argument value
    _ = variant_id
    return _render_behavior_card_raw(base_path, behavior_json, is_boss=is_boss, base_card=base_card)


# ---------------------------------------------------------------------------
# Whole-deck cached renderer
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def render_behavior_deck_cached(deck_key: str, cards: List[Dict[str, Any]]) -> List[bytes]:
    """
    Pre-render and cache a complete deck as a list of PNG bytes, in draw order.

    Each item in 'cards' should be a dict with at least:
      - kind: "data" | "behavior"
      - base_path: str
      - json: dict              (raw_json for data; behavior_json for behavior)
      - is_boss: bool
      - no_edits: bool          (only for kind == "data"; optional otherwise)
      - base_card: Optional[bytes]  (only for kind == "behavior" when using a pre-rendered data card)
      - variant_id: Optional[str]

    The 'deck_key' should be a stable identifier for the deck composition, e.g.:
        f"{boss}_{difficulty}_{heatup}_{seed}"
    Changing the key forces Streamlit to rebuild the deck cache once.
    """
    rendered: List[bytes] = []
    for item in cards:
        kind = item.get("kind")
        base_path = item.get("base_path")
        json_blob = item.get("json", {})
        is_boss = bool(item.get("is_boss", False))
        variant_id = item.get("variant_id")

        if kind == "data":
            no_edits = bool(item.get("no_edits", False))
            img_bytes = render_data_card_cached(base_path, json_blob, is_boss, no_edits, variant_id=variant_id)
        else:
            base_card = item.get("base_card")
            img_bytes = render_behavior_card_cached(base_path, json_blob, is_boss, base_card=base_card, variant_id=variant_id)

        rendered.append(img_bytes)

    return rendered
