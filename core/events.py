import json
import random
import base64
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional
import streamlit as st

# -----------------------
# Paths
# -----------------------
DATA_DIR = Path("data/events")
ASSETS_DIR = Path("assets/events")

# Standard preset (V2 combined)
V2_EXPANSIONS = [
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City",
]

# Optional special-cased group (left here for future use)
rendezvousEvents = {
    "Big Pilgrim's Key",
    "Bleak Bonfire Ascetic",
    "Bloodstained Bonfire Ascetic",
    "Cracked Bonfire Ascetic",
    "Frozen Bonfire Ascetic",
    "Hearty Bonfire Ascetic",
    "Lost Envoy",
    "Martial Bonfire Ascetic",
    "Rare Vagrant",
    "Scout Ahead",
    "Trustworthy Promise",
    "Undead Merchant",
    "Virulent Bonfire Ascetic",
}

# -----------------------
# Cached helpers
# -----------------------
@st.cache_data(show_spinner=False)
def load_event_configs(active_expansions: Optional[List[str]] = None) -> Dict[str, dict]:
    """Load event configs grouped by expansion. Cached across reruns."""
    configs: Dict[str, dict] = {}
    for json_file in DATA_DIR.glob("*.json"):
        expansion = json_file.stem
        if active_expansions and expansion not in active_expansions:
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                configs[expansion] = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load {json_file}: {e}")
    return configs


@st.cache_resource(show_spinner=False)
def img_to_base64(path: str) -> str:
    """Read an image file as base64 (cached across reruns)."""
    p = Path(path)
    with open(p, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii")


# -----------------------
# Deck builders (pure)
# -----------------------
def build_deck(configs: Dict[str, dict]) -> List[str]:
    """Build a shuffled deck from configs."""
    deck: List[str] = []
    for expansion, conf in configs.items():
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
    if preset == "Mixed V2":
        return build_mixed_v2_deck(configs)
    else:
        return build_deck({preset: configs[preset]})


# -----------------------
# Persistent deck state API (session-based)
# -----------------------
DECK_STATE_KEY = "event_deck"


def _ensure_deck_state():
    if DECK_STATE_KEY not in st.session_state:
        st.session_state[DECK_STATE_KEY] = {
            "draw_pile": [],
            "discard_pile": [],
            "current_card": None,
            "preset": None,
        }


def initialize_event_deck(preset: str, configs: Optional[Dict[str, dict]] = None):
    """Initialize or reset the deck in session_state for a given preset."""
    _ensure_deck_state()
    if configs is None:
        configs = load_event_configs()

    deck = build_deck_for_preset(preset, configs)
    random.shuffle(deck)

    st.session_state[DECK_STATE_KEY].update({
        "draw_pile": deck,
        "discard_pile": [],
        "current_card": None,
        "preset": preset,
    })


def _auto_reshuffle_if_needed():
    """Reshuffle discard into draw when draw pile is empty."""
    state = st.session_state[DECK_STATE_KEY]
    if not state["draw_pile"] and state["discard_pile"]:
        state["draw_pile"] = state["discard_pile"]
        state["discard_pile"] = []
        random.shuffle(state["draw_pile"])


def draw_event_card() -> Optional[str]:
    """Draw the top card; reshuffle if needed."""
    _ensure_deck_state()
    state = st.session_state[DECK_STATE_KEY]

    # Move current to discard (if any)
    if state["current_card"]:
        state["discard_pile"].append(state["current_card"])
        state["current_card"] = None

    # If draw pile is empty, attempt auto-reshuffle now
    if not state["draw_pile"]:
        _auto_reshuffle_if_needed()

    if not state["draw_pile"]:
        return None

    # Draw from top
    card = state["draw_pile"].pop(0)
    state["current_card"] = card
    return card


def put_current_on_top():
    """Put the current card back on top of the draw pile."""
    _ensure_deck_state()
    state = st.session_state[DECK_STATE_KEY]
    if state["current_card"]:
        state["draw_pile"].insert(0, state["current_card"])
        state["current_card"] = None


def put_current_on_bottom():
    """Put the current card on bottom of the draw pile."""
    _ensure_deck_state()
    state = st.session_state[DECK_STATE_KEY]
    if state["current_card"]:
        state["draw_pile"].append(state["current_card"])
        state["current_card"] = None


def reset_event_deck():
    """Reset the deck, preserving the current preset."""
    _ensure_deck_state()
    preset = st.session_state[DECK_STATE_KEY].get("preset") or "Mixed V2"
    initialize_event_deck(preset)


__all__ = [
    "load_event_configs",
    "build_deck",
    "build_mixed_v2_deck",
    "img_to_base64",
    "initialize_event_deck",
    "draw_event_card",
    "put_current_on_top",
    "put_current_on_bottom",
    "reset_event_deck",
    "build_deck_for_preset",
    "V2_EXPANSIONS",
]
