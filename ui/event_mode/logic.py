#ui/event_mode/logic.py
import json
import random
import os
import streamlit as st
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict
from datetime import datetime, timezone
from ui.event_mode.event_card_text import EVENT_CARD_TEXT
from ui.event_mode.event_card_type import EVENT_CARD_TYPE


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

RENDEZVOUS_EVENTS = {
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
    "Virulent Bonfire Ascetic"
}

CONSUMABLE_EVENTS = {
    "Alluring Skull",
    "Blacksmith's Trial",
    "Fleeting Glory",
    "Green Blossom",
    "Lifegem",
    "Pine Resin",
    "Princess Guard",
    "Repair Powder",
    "Rite of Rekindling"
}

IMMEDIATE_EVENTS = {
    "Firekeeper's Boon",
    "Forgotten Supplies",
    "Lost to Time",
    "Obscured Knowledge",
    "Scrying Stone",
    "Skeletal Reforging",
    "Stolen Artifact",
    "Unhallowed Offering"
}

EVENT_BEHAVIOR_MODIFIERS = {
    "Bleak Bonfire Ascetic": [
        {
            "id": "bleak_bonfire_ascetic_effect",
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
            "id": "bloodstained_bonfire_ascetic_effect",
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
            "id": "cracked_bonfire_ascetic_effect",
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
            "id": "frozen_bonfire_ascetic_effect",
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
            "id": "hearty_bonfire_ascetic_effect",
            "source": "event",
            "source_id": "hearty_bonfire_ascetic",
            "target": "all_enemies",
            "stat": "health",
            "op": "add",
            "value": 1,
            "description": "+1 max HP from Hearty Bonfire Ascetic event"
        }
    ],
    "Martial Bonfire Ascetic": [
        {
            "id": "martial_bonfire_ascetic_effect",
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
            "id": "virulent_bonfire_ascetic_effect",
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
    "Big Pilgrim's Key": [
        {
            "type": "shortcut",
        }
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
}

# Rewards that resolve immediately when an event card is drawn
# (before the encounter is played). These are separate from
# EVENT_REWARDS, which are applied as part of the encounter’s
# end-of-fight reward calculation.
#
# Keys MUST match the card's base filename / event id:
#   base = os.path.splitext(os.path.basename(card_path))[0]
# which is exactly what _attach_event_to_current_encounter uses
# for "id"/"name", and what EVENT_REWARDS is keyed on.
#
# Schema for each entry (same as EVENT_REWARDS):
#   {
#       "type": "souls" | "treasure" | "text" | "shortcut",
#       # For "souls":
#       "per_player": int,    # optional, souls per character
#       "flat": int,          # optional, flat souls
#       # For "treasure":
#       "flat": int,          # number of treasure cards to draw
#       # For "text":
#       "text": str,          # descriptive/manual effect
#   }
#
# Example entries; replace with real data.
EVENT_DRAW_REWARDS: Dict[str, List[dict]] = {
    "Firekeeper's Boon": [
        {
            "type": "text",
            "text": "Choose a character. That character can upgrade a stat without spending souls."
        }
    ],
    "Forgotten Supplies": [
        {
            "type": "text",
            "text": "Choose a character. That character can upgrade a stat without spending souls."
        }
    ],
    "Lost to Time": [
        {
            "type": "text",
            "text": "One at a time, roll 1 black die for each card in the inventory. The first time a blank result is rolled, discard the treasure card."
        }
    ],
    "Obscured Knowledge": [
        {
            "type": "text",
            "text": "Choose a character. This character can immediately equip a card in the inventory, ignoring the card's minimum stat requirements."
        }
    ],
    "Rite of Rekindling": [
        {
            "type": "text",
            "text": "The next time the party returns to the bonfire, each character can undo any number of their upgraded stats, and return the number of souls spent upgrading them to the soul cache."
        }
    ],
    "Scrying Stone": [
        {
            "type": "text",
            "text": "Look at the top three cards from the event deck, return each to either the top or bottom of the deck in an order of your choosing."
        }
    ],
    "Skeletal Reforging": [
        {
            "type": "text",
            "text": "Discard up to three cards from the inventory. Gain one soul for each card discarded."
        }
    ],
    "Stolen Artifact": [
        {
            "type": "text",
            "text": "Draw five treasure cards from the treasure deck. Place one card in the inventory, then return the remaining cards to the bottom of the deck."
        }
    ],
    "Undead Merchant": [
        {
            "type": "text",
            "text": "The party can purchase treasure."
        }
    ],
    "Unhallowed Offering": [
        {
            "type": "text",
            "text": "Each character can flip any number of their player tokens to their used face. Add a soul to the soul cache for each token that was flipped."
        }
    ],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


from core import supabase_store
from core.settings_manager import _has_supabase_config


@st.cache_data(show_spinner=False)
def load_custom_event_decks() -> Dict[str, dict]:
    """
    Returns mapping: deck_name -> {"cards": {image_path: copies}, ...}
    File schema:
      { "decks": { "<name>": {"cards": {...}} }, "updated": "..." }
    Legacy support: if file is { "<name>": {...} } treat that as decks mapping.
    """
    # Supabase-backed: one row per deck with doc_type='event_deck'
    if _has_supabase_config():
        client_id = None
        try:
            client_id = st.session_state.get("client_id")
        except Exception:
            client_id = None

        out: Dict[str, dict] = {}
        try:
            names = supabase_store.list_documents("event_deck", user_id=client_id)
        except Exception:
            names = []

        for n in names:
            try:
                obj = supabase_store.get_document("event_deck", n, user_id=client_id)
                if isinstance(obj, dict):
                    out[n] = obj
            except Exception:
                continue
        return out

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
    # Supabase-backed: upsert each deck as its own document
    if _has_supabase_config():
        client_id = None
        try:
            client_id = st.session_state.get("client_id")
        except Exception:
            client_id = None

        for name, deck in (decks or {}).items():
            try:
                supabase_store.upsert_document("event_deck", name, deck, user_id=client_id)
            except Exception:
                pass

        # Remove remote decks that no longer exist locally
        try:
            remote = supabase_store.list_documents("event_deck", user_id=client_id)
            for r in remote:
                if r not in decks:
                    try:
                        supabase_store.delete_document("event_deck", r, user_id=client_id)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            load_custom_event_decks.clear()
        except Exception:
            pass
        st.rerun()

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


def get_card_width(layout_width=700, col_ratio=2, total_ratio=4, max_width=350) -> int:
    """Calculate appropriate image display width."""
    col_w = int(layout_width * (col_ratio / total_ratio))
    return min(col_w - 20, max_width)
