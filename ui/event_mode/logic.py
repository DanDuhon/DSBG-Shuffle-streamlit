#ui/event_mode/logic.py
import json
import random
import os
import streamlit as st
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict
from datetime import datetime, timezone
from core import supabase_store
from core import auth
from core.settings_manager import _has_supabase_config, is_streamlit_cloud, save_settings
from ui.event_mode.event_card_text import EVENT_CARD_TEXT
from ui.event_mode.event_card_type import EVENT_CARD_TYPE
from ui.event_mode.event_card_meta import (
    get_event_behavior_modifiers_map,
    get_event_draw_rewards_map,
    get_event_rewards_map,
)


DATA_DIR = Path("data/events")
ASSETS_DIR = Path("assets/events")
DECK_STATE_KEY = "event_deck"
V2_EXPANSIONS = [
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City",
]

# --- Custom decks (user-authored) ---
CUSTOM_DECKS_PATH = Path("data/custom_event_decks.json")
CUSTOM_PREFIX = "Custom: "

# Event categories are derived from EVENT_CARD_TYPE to avoid drift.
RENDEZVOUS_EVENTS = {name for name, t in EVENT_CARD_TYPE.items() if t == "Rendezvous"}
CONSUMABLE_EVENTS = {name for name, t in EVENT_CARD_TYPE.items() if t == "Consumable"}
IMMEDIATE_EVENTS = {name for name, t in EVENT_CARD_TYPE.items() if t == "Immediate"}

EVENT_BEHAVIOR_MODIFIERS = get_event_behavior_modifiers_map()
EVENT_REWARDS: Dict[str, List[dict]] = get_event_rewards_map()
EVENT_DRAW_REWARDS: Dict[str, List[dict]] = get_event_draw_rewards_map()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@st.cache_data(show_spinner=False)
def load_custom_event_decks() -> Dict[str, dict]:
    """
    Returns mapping: deck_name -> {"cards": {image_path: copies}, ...}
    File schema:
      { "decks": { "<name>": {"cards": {...}} }, "updated": "..." }
    Legacy support: if file is { "<name>": {...} } treat that as decks mapping.
    """
    # Streamlit Cloud: Supabase-backed (per-account) custom decks.
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            # Logged out: do not read shared local files on Cloud.
            return {}

        out: Dict[str, dict] = {}
        try:
            names = supabase_store.list_documents("event_deck", user_id=user_id, access_token=access_token)
        except Exception:
            names = []

        for n in names:
            try:
                obj = supabase_store.get_document("event_deck", n, user_id=user_id, access_token=access_token)
                if isinstance(obj, dict):
                    out[n] = obj
            except Exception:
                continue
        return out

    # Streamlit Cloud should never read shared local files.
    if is_streamlit_cloud():
        return {}

    if not CUSTOM_DECKS_PATH.exists():
        return {}
    data = json.loads(CUSTOM_DECKS_PATH.read_text(encoding="utf-8"))

    if isinstance(data, dict) and "decks" in data and isinstance(data["decks"], dict):
        return data["decks"]
    if isinstance(data, dict):
        # legacy: the whole object is the decks mapping
        return data
    return {}


def save_custom_event_decks(decks: Dict[str, dict]) -> None:
    # Streamlit Cloud: Supabase-backed (per-account) custom decks.
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            return

        for name, deck in (decks or {}).items():
            try:
                supabase_store.upsert_document("event_deck", name, deck, user_id=user_id, access_token=access_token)
            except Exception:
                pass

        # Remove remote decks that no longer exist locally
        try:
            remote = supabase_store.list_documents("event_deck", user_id=user_id, access_token=access_token)
            for r in remote:
                if r not in decks:
                    try:
                        supabase_store.delete_document("event_deck", r, user_id=user_id, access_token=access_token)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            load_custom_event_decks.clear()
        except Exception:
            pass
        st.rerun()
        return

    # Streamlit Cloud should never persist anonymously to local JSON.
    if is_streamlit_cloud():
        return

    CUSTOM_DECKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"decks": decks, "updated": _utc_now_iso()}
    CUSTOM_DECKS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    # Clear the cached loader so future calls reflect the updated file.
    try:
        load_custom_event_decks.clear()
    except Exception:
        pass
    st.rerun()


def list_event_deck_options(configs: Optional[Dict[str, dict]] = None) -> List[str]:
    """
    Built-ins come from available event config JSONs + the synthetic 'Mixed V2'.
    Customs are appended as 'Custom: <name>'.
    """
    if configs is None:
        configs = load_event_configs()

    builtins = sorted(configs.keys())
    if "Mixed V2" not in builtins:
        builtins.append("Mixed V2")

    customs = sorted(load_custom_event_decks().keys())
    custom_opts = [f"{CUSTOM_PREFIX}{name}" for name in customs]
    return builtins + custom_opts


def _parse_custom_preset(preset: str) -> Optional[str]:
    if isinstance(preset, str) and preset.startswith(CUSTOM_PREFIX):
        name = preset[len(CUSTOM_PREFIX):].strip()
        return name or None
    return None


def list_all_event_cards(
    configs: Optional[Dict[str, dict]] = None,
    *,
    expansions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    One entry per card image in configs.
    Returns: [{"expansion","id","image_path","default_copies"}...]
    """
    if configs is None:
        configs = load_event_configs()
    wanted = set(expansions) if expansions else None

    # Dedupe by image_path; collect expansions for the same card image.
    by_img: Dict[str, Dict[str, Any]] = {}
    for exp, conf in (configs or {}).items():
        if wanted is not None and exp not in wanted:
            continue
        for ev in conf.get("events", []) or []:
            img_rel = ev.get("image")
            if not img_rel:
                continue
            img_path = (ASSETS_DIR / img_rel).as_posix()
            card_id = Path(str(img_rel)).stem

            card_text = EVENT_CARD_TEXT.get(card_id)
            card_type = EVENT_CARD_TYPE.get(card_id)

            entry = by_img.get(img_path)
            if entry is None:
                by_img[img_path] = {
                    "_expansions": {exp},
                    "id": card_id,
                    "image_path": img_path,
                    "default_copies": int(ev.get("copies", 1) or 1),
                    "text": card_text,
                    "type": card_type,
                }
            else:
                entry["_expansions"].add(exp)
                entry["default_copies"] = max(int(entry.get("default_copies") or 1), int(ev.get("copies", 1) or 1))
                if not entry.get("text") and card_text:
                    entry["text"] = card_text

    out: List[Dict[str, Any]] = []
    for entry in by_img.values():
        exps = sorted(list(entry.pop("_expansions", set())))
        entry["expansion"] = ", ".join(exps)
        out.append(entry)

    out.sort(key=lambda d: (str(d.get("id","")), str(d.get("expansion",""))))
    return out


def compute_draw_rewards_for_card(card_path: str, *, player_count: int = 1) -> Dict[str, int]:
    """
    Return numeric draw-time rewards for this event card.

    Currently only 'souls' and 'treasure' entries are aggregated. Text-only
    effects are represented on the card itself and resolved manually.
    """
    base = os.path.splitext(os.path.basename(str(card_path)))[0]
    entries = EVENT_DRAW_REWARDS.get(base)
    totals: Dict[str, int] = {"souls": 0, "treasure": 0}

    if not entries:
        return totals

    for entry in entries:
        kind = entry.get("type")
        if kind == "souls":
            per_player = int(entry.get("per_player") or 0)
            flat = int(entry.get("flat") or 0)
            totals["souls"] += flat + per_player * player_count
        elif kind == "treasure":
            flat = int(entry.get("flat") or 0)
            totals["treasure"] += flat

    return totals


# --- Loaders ---
@st.cache_data(show_spinner=False)
def load_event_configs(active_expansions: Optional[List[str]] = None) -> Dict[str, dict]:
    """Load event configuration JSONs for available expansions."""
    configs: Dict[str, dict] = {}
    for json_file in DATA_DIR.glob("*.json"):
        expansion = json_file.stem
        if active_expansions and expansion not in active_expansions:
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            configs[expansion] = json.load(f)
    return configs


# --- Deck logic ---
def build_deck(configs: Dict[str, dict]) -> List[str]:
    """Build a shuffled deck from configs."""
    deck: List[str] = []
    for _, conf in configs.items():
        for ev in conf.get("events", []):
            image = ASSETS_DIR / ev["image"]
            copies = ev.get("copies", 1)
            deck.extend([str(image)] * copies)
    random.shuffle(deck)
    return deck


def build_mixed_v2_deck(configs: Dict[str, dict]) -> List[str]:
    """Build a combined V2 deck."""
    counts: Dict[str, int] = defaultdict(int)

    for exp in V2_EXPANSIONS:
        if exp not in configs:
            continue
        for ev in configs[exp].get("events", []):
            image = ASSETS_DIR / ev["image"]
            copies = ev.get("copies", 1)
            key = str(image)
            if copies > counts[key]:
                counts[key] = copies

    deck: List[str] = []
    for image, copies in counts.items():
        deck.extend([image] * copies)

    random.shuffle(deck)
    return deck


def build_deck_for_preset(preset: str, configs: Dict[str, dict]) -> List[str]:
    """Build a draw pile based on selected preset."""
    if not preset:
        return []

    if preset == "Mixed V2":
        return build_mixed_v2_deck(configs)

    custom_name = _parse_custom_preset(preset)
    if custom_name:
        decks = load_custom_event_decks()
        deck_def = decks.get(custom_name) or {}
        cards = (deck_def.get("cards") or {}) if isinstance(deck_def, dict) else {}
        draw: List[str] = []
        for img_path, copies in (cards.items() if isinstance(cards, dict) else []):
            n = int(copies)
            if n > 0 and img_path:
                draw.extend([str(img_path)] * n)
        random.shuffle(draw)
        return draw

    # built-in expansion
    conf = configs.get(preset)
    if not conf:
        return []
    return build_deck({preset: conf})


def initialize_event_deck(preset: str, configs: Optional[Dict[str, dict]] = None):
    """Create and shuffle an event deck."""
    if configs is None:
        configs = load_event_configs()

    draw_pile = build_deck_for_preset(preset, configs)
    random.shuffle(draw_pile)

    st.session_state[DECK_STATE_KEY] = {
        "draw_pile": draw_pile,
        "discard_pile": [],
        "current_card": None,
        "preset": preset,
    }


def _ensure_deck_state(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the event deck state exists in `st.session_state` and return it.

    This mirrors the local helpers used by UI renderers and centralizes
    deck state initialization so callers don't duplicate logic.
    """
    state = st.session_state.get(DECK_STATE_KEY)
    if isinstance(state, dict):
        return state

    saved = settings.get("event_deck")
    if isinstance(saved, dict):
        st.session_state[DECK_STATE_KEY] = saved
        return saved

    state = {"draw_pile": [], "discard_pile": [], "current_card": None, "preset": None}
    st.session_state[DECK_STATE_KEY] = state
    return state


def ensure_event_deck_ready(
    settings: Dict[str, Any],
    *,
    configs: Optional[Dict[str, Any]] = None,
    preset: Optional[str] = None,
) -> Optional[str]:
    """Ensure an initialized event deck exists and is persisted.

    Used by non-Event-Mode flows (e.g. Campaign/Encounter) that need to draw
    events without rendering the full simulator UI.

    - Ensures a deck state exists in `st.session_state`
    - Chooses a preset (argument > session > settings > first available)
    - Initializes deck if preset changed or draw pile empty
    - Persists `settings['event_deck']` via `save_settings`

    Keeps behavior consistent with Event Mode and avoids duplicated init code.
    """

    if configs is None:
        configs = load_event_configs()

    deck_state = _ensure_deck_state(settings)
    saved_deck_cfg = settings.get("event_deck") or {}

    chosen = (
        preset
        or deck_state.get("preset")
        or (saved_deck_cfg.get("preset") if isinstance(saved_deck_cfg, dict) else None)
    )

    if not chosen:
        opts = list_event_deck_options(configs=configs)
        chosen = opts[0] if opts else None

    if not chosen:
        return None

    if deck_state.get("preset") != chosen or not list(deck_state.get("draw_pile") or []):
        initialize_event_deck(chosen, configs=configs)

    settings["event_deck"] = st.session_state.get(DECK_STATE_KEY)
    save_settings(settings)
    return chosen


def _attach_event_to_current_encounter(*args) -> None:
    """Attach an event to the current encounter.

    Flexible signature for backward compatibility:
      - `_attach_event_to_current_encounter(card_path)`
      - `_attach_event_to_current_encounter(event_name, card_path)`

    The function normalizes the provided name (if any) and enforces the
    rendezvous rule (only one rendezvous event at a time).
    """
    # Parse flexible args
    event_name = None
    card_path = None
    if len(args) == 1:
        card_path = args[0]
    elif len(args) >= 2:
        event_name = args[0]
        card_path = args[1]

    if not card_path and not event_name:
        return

    # Determine a display name for the event
    if event_name:
        name = str(event_name or "").strip()
    else:
        name = os.path.splitext(os.path.basename(str(card_path)))[0]

    name_norm = str(name or "").strip()
    name_norm_lower = name_norm.lower()
    rendezvous_lower = {n.lower() for n in RENDEZVOUS_EVENTS}
    is_rendezvous = name_norm_lower in rendezvous_lower

    events = st.session_state.get("encounter_events")
    if not isinstance(events, list):
        events = []

    # If rendezvous, drop existing rendezvous events
    if is_rendezvous:
        events = [e for e in events if not (isinstance(e, dict) and bool(e.get("is_rendezvous")))]

    base = Path(str(card_path)).stem if card_path else name_norm
    event_obj = {
        "id": base,
        "name": name_norm,
        "path": str(card_path) if card_path else None,
        "card_path": str(card_path) if card_path else None,
        "image_path": str(card_path) if card_path else None,
        "is_rendezvous": is_rendezvous,
    }

    events.append(event_obj)
    st.session_state["encounter_events"] = events
    # Refresh UI so attached events are visible immediately in callers.
    try:
        st.rerun()
    except Exception:
        pass


def draw_event_card():
    """Draw a card from the deck, move previous to discard."""
    state = st.session_state[DECK_STATE_KEY]
    if state["current_card"]:
        state["discard_pile"].append(state["current_card"])
    if not state["draw_pile"] and state["discard_pile"]:
        state["draw_pile"] = state["discard_pile"]
        state["discard_pile"] = []
        random.shuffle(state["draw_pile"])
    if not state["draw_pile"]:
        return None
    card = state["draw_pile"].pop(0)
    state["current_card"] = card
    return card


def put_current_on_top():
    """Put the current card back on top of the draw pile."""
    state = st.session_state[DECK_STATE_KEY]
    if state["current_card"]:
        state["draw_pile"].insert(0, state["current_card"])
        state["current_card"] = None


def put_current_on_bottom():
     """Put the current card on bottom of the draw pile."""
     state = st.session_state[DECK_STATE_KEY]
     if state["current_card"]:
         state["draw_pile"].append(state["current_card"])
         state["current_card"] = None
 
 
def reset_event_deck(configs: Optional[Dict[str, dict]] = None, *, preset: Optional[str] = None) -> bool:
    """
    Rebuild the deck from its preset definition and shuffle it.
    This restores any temporarily-removed cards because it rebuilds from source.
    """
    state = st.session_state.get(DECK_STATE_KEY)
    if not isinstance(state, dict):
        return False
    use_preset = preset or state.get("preset")
    if not use_preset:
        return False
    initialize_event_deck(use_preset, configs=configs)
    return True


def shuffle_current_into_deck() -> bool:
    """
    Move the current card into the draw pile and shuffle.
    If the draw pile is empty, recycle discard -> draw first (then shuffle).
    """
    state = st.session_state.get(DECK_STATE_KEY)
    if not isinstance(state, dict):
        return False

    cur = state.get("current_card")
    if not cur:
        return False

    draw = list(state.get("draw_pile") or [])
    discard = list(state.get("discard_pile") or [])

    if not draw and discard:
        draw = discard
        discard = []

    draw.append(cur)
    random.shuffle(draw)

    state["draw_pile"] = draw
    state["discard_pile"] = discard
    state["current_card"] = None
    return True


def remove_card_from_deck(card_path: Optional[str] = None) -> int:
    """
    Remove all copies of a card from draw+discard and clear it if it's current.
    Non-permanent: reset_event_deck/initialize_event_deck restores it.
    Returns number of removed copies (including current, if applicable).
    """
    state = st.session_state.get(DECK_STATE_KEY)
    if not isinstance(state, dict):
        return 0

    target = card_path or state.get("current_card")
    if not target:
        return 0

    target_str = str(target)
    target_base = os.path.splitext(os.path.basename(target_str))[0]

    def _matches(x: Any) -> bool:
        xs = str(x)
        if xs == target_str:
            return True
        return os.path.splitext(os.path.basename(xs))[0] == target_base

    removed = 0

    cur = state.get("current_card")
    if cur and _matches(cur):
        state["current_card"] = None
        removed += 1

    draw = list(state.get("draw_pile") or [])
    new_draw = []
    for x in draw:
        if _matches(x):
            removed += 1
        else:
            new_draw.append(x)
    state["draw_pile"] = new_draw

    discard = list(state.get("discard_pile") or [])
    new_discard = []
    for x in discard:
        if _matches(x):
            removed += 1
        else:
            new_discard.append(x)
    state["discard_pile"] = new_discard

    return removed
