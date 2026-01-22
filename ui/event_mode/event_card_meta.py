from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import streamlit as st


DEFAULT_META_PATH = Path("data/event_card_meta.json")
_ALLOWED_TYPES = {"Rendezvous", "Consumable", "Immediate"}


@st.cache_data(show_spinner=False)
def _load_event_card_meta_cached(meta_path: str, meta_mtime: float) -> Dict[str, Any]:
    """Load event card metadata from JSON.

    The cache key includes file mtime so edits invalidate cleanly in dev.
    """
    p = Path(meta_path)
    if not p.exists():
        return {"schema_version": 1, "cards": {}}

    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"schema_version": 1, "cards": {}}

    cards = data.get("cards")
    if not isinstance(cards, dict):
        data["cards"] = {}

    # Ensure schema_version exists.
    if "schema_version" not in data:
        data["schema_version"] = 1

    return data


def load_event_card_meta(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, Any]:
    try:
        mtime = meta_path.stat().st_mtime if meta_path.exists() else 0.0
    except Exception:
        mtime = 0.0

    try:
        return _load_event_card_meta_cached(str(meta_path), float(mtime))
    except Exception:
        return {"schema_version": 1, "cards": {}}


def get_event_cards_meta(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, Dict[str, Any]]:
    data = load_event_card_meta(meta_path=meta_path)
    cards = data.get("cards")
    if isinstance(cards, dict):
        # mypy: values are Any, we validate downstream.
        return cards  # type: ignore[return-value]
    return {}


def build_event_card_text_map(cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
    return {k: str(v.get("text", "")).strip() for k, v in cards.items() if v.get("text") is not None}


def build_event_card_type_map(cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
    return {k: str(v.get("type", "")).strip() for k, v in cards.items() if v.get("type") is not None}


def build_event_behavior_modifiers_map(cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for k, v in cards.items():
        mods = v.get("behavior_modifiers")
        if isinstance(mods, list):
            out[k] = mods  # type: ignore[assignment]
    return out


def build_event_encounter_rewards_map(cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for k, v in cards.items():
        rewards = v.get("encounter_rewards")
        if isinstance(rewards, list):
            out[k] = rewards  # type: ignore[assignment]
    return out


def build_event_draw_rewards_map(cards: Mapping[str, Mapping[str, Any]]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for k, v in cards.items():
        rewards = v.get("draw_rewards")
        if isinstance(rewards, list):
            out[k] = rewards  # type: ignore[assignment]
    return out


def get_event_card_text_map(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, str]:
    cards = get_event_cards_meta(meta_path=meta_path)
    return build_event_card_text_map(cards)


def get_event_card_type_map(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, str]:
    cards = get_event_cards_meta(meta_path=meta_path)
    return build_event_card_type_map(cards)


def get_event_behavior_modifiers_map(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, List[dict]]:
    cards = get_event_cards_meta(meta_path=meta_path)
    return build_event_behavior_modifiers_map(cards)


def get_event_rewards_map(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, List[dict]]:
    cards = get_event_cards_meta(meta_path=meta_path)
    return build_event_encounter_rewards_map(cards)


def get_event_draw_rewards_map(*, meta_path: Path = DEFAULT_META_PATH) -> Dict[str, List[dict]]:
    cards = get_event_cards_meta(meta_path=meta_path)
    return build_event_draw_rewards_map(cards)


def validate_event_card_meta(
    *,
    cards: Mapping[str, Mapping[str, Any]],
    known_card_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    """Return human-readable validation warnings."""
    warnings: List[str] = []

    for card_id, meta in cards.items():
        if not isinstance(meta, Mapping):
            warnings.append(f"{card_id}: metadata is not an object")
            continue

        t = meta.get("type")
        if t is None:
            warnings.append(f"{card_id}: missing 'type'")
        elif str(t) not in _ALLOWED_TYPES:
            warnings.append(f"{card_id}: unknown type '{t}'")

        txt = meta.get("text")
        if txt is not None and not isinstance(txt, str):
            warnings.append(f"{card_id}: 'text' must be a string")

        for field in ("behavior_modifiers", "encounter_rewards", "draw_rewards"):
            v = meta.get(field)
            if v is not None and not isinstance(v, list):
                warnings.append(f"{card_id}: '{field}' must be a list")

    if known_card_ids is not None:
        known = {str(x) for x in known_card_ids}
        missing = sorted([cid for cid in known if cid not in cards])
        extra = sorted([cid for cid in cards.keys() if cid not in known])
        if missing:
            warnings.append(
                "Missing metadata for event cards: " + ", ".join(missing)
            )
        if extra:
            warnings.append(
                "Metadata entries with no known card image: " + ", ".join(extra)
            )

    return warnings
