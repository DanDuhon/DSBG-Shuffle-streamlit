#ui/events_tab/logic.py
import json
import random
import os
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

RENDEZVOUS_EVENTS = {
    "Bleak Bonfire Ascetic",
    "Bloodstained Bonfire Ascetic",
    "Cracked Bonfire Ascetic",
    "Frozen Bonfire Ascetic",
    "Hearty Bonfire Ascetic",
    "Martial Bonfire Ascetic",
    "Rare Vagrant",
    "Scout Ahead",
    "Trustworthy Promise",
    "Undead Merchant",
    "Virulent Bonfire Ascetic",
}

EVENT_BEHAVIOR_MODIFIERS = {
    "Bleak Bonfire Ascetic": [
        {
            "id": "bleak_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "bleak_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "dodge_difficulty",
            "op": "add",
            "value": 1,
            "description": "+1 dodge difficulty from Bleak Bonfire Ascetic event"
        }
    ],
    "Bloodstained Bonfire Ascetic": [
        {
            "id": "bloodstained_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "bloodstained_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "bleed",
            "op": "flag",
            "value": True,
            "description": "Bleed from Bloodstained Bonfire Ascetic event"
        }
    ],
    "Cracked Bonfire Ascetic": [
        {
            "id": "cracked_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "cracked_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "stagger",
            "op": "flag",
            "value": True,
            "description": "Stagger from Cracked Bonfire Ascetic event"
        }
    ],
    "Frozen Bonfire Ascetic": [
        {
            "id": "frozen_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "frozen_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "frostbite",
            "op": "flag",
            "value": True,
            "description": "Frostbite from Frozen Bonfire Ascetic event"
        }
    ],
    "Hearty Bonfire Ascetic": [
        {
            "id": "hearty_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "hearty_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "max_hp",
            "op": "add",
            "value": 1,
            "description": "+1 max HP from Hearty Bonfire Ascetic event"
        }
    ],
    "Martial Bonfire Ascetic": [
        {
            "id": "martial_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "martial_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 1,
            "description": "+1 damage from Martial Bonfire Ascetic event"
        }
    ],
    "Virulent Bonfire Ascetic": [
        {
            "id": "virulent_bonfire_ascetic_dodge",
            "source": "event",
            "source_id": "virulent_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "poison",
            "op": "flag",
            "value": True,
            "description": "Poison from Virulent Bonfire Ascetic event"
        }
    ],
}

EVENT_REWARDS: Dict[str, List[dict]] = {
    "Blacksmith's Trial": [
        {
            "type": "text",
            "text": "Search the treasure deck until an upgrade card is revealed, then either add it to the inventory or use it to upgrade a card. Then, shuffle the treasure deck."
        },
    ],
    "Bleak Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Bloodstained Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Cracked Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Frozen Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Hearty Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Martial Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Virulent Bonfire Ascetic": [
        {
            "type": "souls",
            "per_player": 1,
            "flat": 2
        },
    ],
    "Trustworthy Promise": [
        {
            "type": "text",
            "text": "Toss the Patches token. If it lands bright side face up, double the amount of souls the characters earn from the encounter. If it lands with the corroded side face up, the characters do not earn any souls from the encounter."
        },
    ],
    "Undead Merchant": [
        {
            "type": "text",
            "text": "The party can purchase treasure."
        },
    ],
    "Fleeting Glory": [
        {
            "type": "souls_multiplier",
            "multiplier": 2
        },
    ],
    # # Example: an event that just gives extra souls
    # "Bloodstained Bonfire Ascetic": [
    #     {
    #         "type": "souls",
    #         "per_player": 1,
    #         "text": "Event reward: each character gains 1 extra soul.",
    #     },
    # ],

    # # Example: event that grants treasure and a descriptive string
    # "Corvian Spoils": [
    #     {
    #         "type": "treasure",
    #         "flat": 1,
    #         "text": "Event reward: draw 1 treasure card.",
    #     },
    #     {
    #         "type": "text",
    #         "text": "If you cleared the encounter without any characters dying, draw 1 additional treasure card.",  # text-only condition
    #     },
    # ],

    # # Example: lore-only event with no numeric reward
    # "Mysterious Painting Fragment": [
    #     {
    #         "type": "text",
    #         "text": "You discover a cryptic clue. (No mechanical reward.)",
    #     },
    # ],
}


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


def _attach_event_to_current_encounter(card_path: str) -> None:
    """Attach an event card image to the current encounter, enforcing the rendezvous rule."""
    if not card_path:
        return

    if "encounter_events" not in st.session_state:
        st.session_state.encounter_events = []

    base = os.path.splitext(os.path.basename(str(card_path)))[0]
    is_rendezvous = base in RENDEZVOUS_EVENTS

    events = st.session_state.encounter_events

    # If this is a rendezvous card, drop any existing rendezvous
    if is_rendezvous:
        events = [ev for ev in events if not ev.get("is_rendezvous")]

    event_obj = {
        "id": base,
        "name": base,
        "path": str(card_path),
        "is_rendezvous": is_rendezvous,
    }

    events.append(event_obj)
    st.session_state.encounter_events = events
    st.rerun()


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
