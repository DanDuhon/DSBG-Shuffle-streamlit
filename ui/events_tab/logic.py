import json
import random
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

DATA_DIR = Path("data/events")
ASSETS_DIR = Path("assets/events")
DECK_STATE_KEY = "event_deck"
V2_EXPANSIONS = [
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City",
]


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
    if preset == "Mixed V2":
        return build_mixed_v2_deck(configs)
    else:
        return build_deck({preset: configs[preset]})


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


def get_card_width(layout_width=700, col_ratio=2, total_ratio=4, max_width=350) -> int:
    """Calculate appropriate image display width."""
    col_w = int(layout_width * (col_ratio / total_ratio))
    return min(col_w - 20, max_width)
