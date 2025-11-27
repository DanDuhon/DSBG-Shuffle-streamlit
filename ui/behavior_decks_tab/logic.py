#ui/behavior_decks_tab/logic.py
import streamlit as st
import random
import json
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Any

from ui.behavior_decks_tab.models import BehaviorConfig, Entity, Heatup
from ui.behavior_decks_tab.assets import _path, _strip_behavior_suffix
from ui.encounters_tab.logic import ENCOUNTER_BEHAVIOR_MODIFIERS
from ui.events_tab.logic import EVENT_BEHAVIOR_MODIFIERS
from ui.ngplus_tab.logic import apply_ngplus_to_raw, get_current_ngplus_level


DATA_DIR = Path("data/behaviors")
DECK_SETUP_RULES = {}


def _ensure_state():
    """Guarantee required Streamlit session_state keys exist."""
    defaults = {
        "behavior_deck": None,
        "behavior_state": None,
        "hp_tracker": {},
        "last_edit": {},
        "deck_reset_id": 0,
        "chariot_heatup_done": False,
        "heatup_done": False,
        "pending_heatup_prompt": False,
        "old_dragonslayer_heatups": 0,
        "old_dragonslayer_pending": False,
        "old_dragonslayer_confirmed": False,
        "vordt_attack_heatup_done": False,
        "vordt_move_heatup_done": False,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _new_state_from_file(fpath: str, cfg: BehaviorConfig | None = None):
    # Reuse a pre-loaded cfg if provided
    if cfg is None:
        cfg = load_behavior(Path(fpath))
    rng = random.Random()

    if cfg.name == "The Four Kings":
        first = _make_king_entity(cfg, 1)
        cfg.entities = [first]

    deck = build_draw_pile(cfg, rng)

    state = {
        "draw_pile": deck,
        "discard_pile": [],
        "current_card": None,
        "selected_file": str(fpath),
        "display_cards": cfg.display_cards,
        "entities": [e.__dict__.copy() for e in cfg.entities],
        "cfg": cfg,
    }

    state["original_behaviors"] = deepcopy(cfg.behaviors)

    if "vordt_move_draw" in cfg.raw:
        state["vordt_move_draw"] = cfg.raw["vordt_move_draw"][:]
        state["vordt_move_discard"] = []
        state["vordt_attack_draw"] = cfg.raw["vordt_attack_draw"][:]
        state["vordt_attack_discard"] = []

    return state, cfg


def _load_cfg_for_state(state):
    if not state or not state.get("selected_file"):
        return None

    # Use cached BehaviorConfig if already stored
    if "cfg" in state and state["cfg"]:
        return state["cfg"]

    # Otherwise, load fresh from disk
    cfg = load_behavior(Path(state["selected_file"]))
    state["cfg"] = cfg
    return cfg


def _clear_heatup_prompt():
    """Fully clear any pending heat-up UI flags."""
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.session_state["pending_heatup_type"] = None
    

def _draw_card(state):
    cfg = _load_cfg_for_state(state)

    # --- Dancer of the Boreal Valley: if the *current* card is a heat-up,
    #     recycle EVERYTHING (current + discard + draw) and shuffle BEFORE any generic recycle.
    if cfg and cfg.name == "Dancer of the Boreal Valley":
        current = state.get("current_card")
        if current:
            beh = cfg.behaviors.get(current, {})
            if beh.get("heatup", False):
                all_cards = [current] + state.get("discard_pile", []) + state.get("draw_pile", [])
                rng = random.Random()
                rng.shuffle(all_cards)
                state["draw_pile"] = all_cards
                state["discard_pile"].clear()
                state["current_card"] = None
                state["dancer_reshuffled"] = True

    # --- Special case: Vordt of the Boreal Valley
    if "vordt_move_draw" in state and "vordt_attack_draw" in state:
        def draw_from(deck_key, discard_key):
            if not state[deck_key]:
                state[deck_key] = state[discard_key][:]
                random.shuffle(state[deck_key])
                state[discard_key].clear()
            card = state[deck_key].pop(0)
            state[discard_key].append(card)
            return card

        move_card = draw_from("vordt_move_draw", "vordt_move_discard")
        atk_card = draw_from("vordt_attack_draw", "vordt_attack_discard")
        state["current_card"] = (move_card, atk_card)
        return

    # Ensure deck availability
    if not state["draw_pile"]:
        if cfg and cfg.name == "The Four Kings":
            summons = state.get("four_kings_summons", 0)
            if summons < 3:
                if not st.session_state.get("four_kings_summon_in_progress", False):
                    st.session_state["four_kings_summon_in_progress"] = True
                    _four_kings_summon(cfg, state, random.Random())
                    st.session_state["four_kings_summon_in_progress"] = False
            else:
                # After third summons, recycle normally
                recycle_deck(state)
        else:
            recycle_deck(state)

    # If still empty, bail cleanly (prevents "played count" from increasing)
    if not state["draw_pile"]:
        return

    # Draw safely: only move current to discard when we have a next card
    next_card = state["draw_pile"].pop(0)
    if state.get("current_card"):
        state["discard_pile"].append(state["current_card"])
    state["current_card"] = next_card
    

def _reset_deck(state, cfg):
    """Reset the current deck and health states for the selected boss."""
    rng = random.Random()

    if "cfg" in state:
        del state["cfg"]  # Force reload of pristine behavior data next run
    
    # Restore original behaviors if saved
    if "original_behaviors" in state:
        cfg.behaviors = deepcopy(state["original_behaviors"])
    
    state["draw_pile"] = build_draw_pile(cfg, rng)
    state["discard_pile"] = []
    state["current_card"] = None
    state["heatup_done"] = False

    # --- Special case: Vordt of the Boreal Valley
    if cfg.name == "Vordt of the Boreal Valley":
        # Let the core deck rule rebuild both decks
        behaviors = cfg.behaviors
        move_cards = [
            b for b in behaviors
            if behaviors[b].get("type") == "move" and not behaviors[b].get("heatup", False)
        ]
        atk_cards = [
            b for b in behaviors
            if behaviors[b].get("type") == "attack" and not behaviors[b].get("heatup", False)
        ]

        rng.shuffle(move_cards)
        rng.shuffle(atk_cards)

        # Reinitialize state decks for UI
        state["vordt_move_draw"] = move_cards[:4]
        state["vordt_move_discard"] = []
        state["vordt_attack_draw"] = atk_cards[:3]
        state["vordt_attack_discard"] = []

        # Sync cfg.raw so that later save/load is consistent
        cfg.raw["vordt_move_draw"] = state["vordt_move_draw"][:]
        cfg.raw["vordt_move_discard"] = []
        cfg.raw["vordt_attack_draw"] = state["vordt_attack_draw"][:]
        cfg.raw["vordt_attack_discard"] = []
    elif cfg.name == "Old Dragonslayer":
        state["old_dragonslayer_heatups"] = 0
        state["old_dragonslayer_pending"] = False
        state["old_dragonslayer_confirmed"] = False
    elif cfg.name == "Crossbreed Priscilla":
        state["priscilla_invisible"] = True
    elif cfg.name == "Great Grey Wolf Sif":
        state["sif_limping"] = False
        st.session_state.pop("sif_limping_triggered", None)
    elif cfg.name == "The Four Kings":
        state["four_kings_summons"] = 0
        st.session_state["enabled_kings"] = 1
        # restore all kings to full hp
        for ent in cfg.entities:
            ent.hp = ent.hp_max
            ent.crossed = []
    elif cfg.name == "Ornstein & Smough":
        for k in [
            "ornstein_dead", "smough_dead",
            "ornstein_dead_pending", "smough_dead_pending",
            "disabled_ornstein", "disabled_smough",
            "ornstein_smough_phase", "os_phase_shuffled_once",
            "pending_heatup_prompt", "pending_heatup_target",
        ]:
            st.session_state.pop(k, None)
        state["ornstein_smough_phase"] = None
    else:
        # Clean up any leftover special keys
        for key in [
            "vordt_move_draw",
            "vordt_move_discard",
            "vordt_attack_draw",
            "vordt_attack_discard",
        ]:
            state.pop(key, None)
            cfg.raw.pop(key, None)
        state["old_dragonslayer_heatups"] = 0
        state["old_dragonslayer_pending"] = False
        state["old_dragonslayer_confirmed"] = False
        state.pop("priscilla_invisible", None)

    # --- Reset entities (UI + cfg)
    for e in state["entities"]:
        if isinstance(e, dict):
            e["hp"] = e.get("hp_max", e.get("hp", 0))
            e["crossed"] = []
        else:
            e.hp = e.hp_max
            e.crossed = []

    for ent in cfg.entities:
        ent.hp = ent.hp_max
        ent.crossed = []
        st.session_state.pop(f"hp_{ent.id}", None)

    # --- Clear UI caches / flags
    st.session_state.pop("hp_tracker", None)
    st.session_state.pop("last_edit", None)
    st.session_state["deck_reset_id"] = st.session_state.get("deck_reset_id", 0) + 1
    st.session_state["chariot_heatup_done"] = False
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["heatup_done"] = False
    st.session_state["behavior_cfg"] = cfg

def _manual_heatup(state):
    cfg = _load_cfg_for_state(state)
    if not cfg:
        return
    rng = random.Random()

    # --- Special case: Executioner Chariot
    if cfg.name == "Executioner Chariot":
        st.session_state["chariot_heatup_done"] = True

        # Rebuild from 4 regular + 1 heat-up card
        base_cards = [b for b in cfg.deck if not cfg.behaviors.get(b, {}).get("heatup", False) and "Death Race" not in b and "Mega Boss Setup" not in b]
        heat_cards = [b for b in cfg.behaviors if cfg.behaviors[b].get("heatup", False)]
        rng.shuffle(base_cards)
        rng.shuffle(heat_cards)
        state["draw_pile"] = base_cards[:4] + heat_cards[:1]
        rng.shuffle(state["draw_pile"])
        state["discard_pile"].clear()
        state["current_card"] = None
    elif cfg.name == "Ornstein & Smough":
        _ornstein_smough_heatup_ui(state, cfg)
    else:
        apply_heatup(state, cfg, rng, reason="manual")
        st.session_state["pending_heatup_prompt"] = False
        st.session_state["pending_heatup_target"] = None
        st.session_state["pending_heatup_type"] = None
        if cfg.name not in {"Old Dragonslayer", "Ornstein & Smough", "Vordt of the Boreal Valley"}:
            st.session_state["heatup_done"] = True
        

def _ornstein_smough_heatup_ui(state, cfg):
    rng = random.Random()

    # Decide who died and who survives, with heal amount
    if st.session_state.get("smough_dead_pending"):
        dead = "Smough"
        survivor_label = "Ornstein"
        heal_amt = 10
        st.session_state["smough_dead_pending"] = False
        st.session_state["smough_dead"] = True
    elif st.session_state.get("ornstein_dead_pending"):
        dead = "Ornstein"
        survivor_label = "Smough"
        heal_amt = 15
        st.session_state["ornstein_dead_pending"] = False
        st.session_state["ornstein_dead"] = True
    else:
        dead = None
        survivor_label = None
        heal_amt = 0

    state = st.session_state["behavior_deck"]

    # --- Heal survivor FIRST, from tracker (source of truth), then sync everywhere
    if survivor_label:
        # find survivor IDs in state/cfg
        surv_state = next((e for e in state["entities"] if survivor_label in e["label"]), None)
        surv_cfg   = next((e for e in cfg.entities        if survivor_label in e.label), None)

        if surv_state and surv_cfg:
            surv_id = surv_state["id"]
            tracker = st.session_state.setdefault("hp_tracker", {})
            # current HP from tracker if present, else from state entity
            cur_hp = int(tracker.get(surv_id, {}).get("hp", surv_state["hp"]))
            new_hp = min(cur_hp + heal_amt, int(surv_state["hp_max"]))

            # write back to tracker (so slider shows it), state, and cfg mirror
            tracker[surv_id] = {"hp": new_hp, "hp_max": surv_state["hp_max"]}
            surv_state["hp"] = new_hp
            surv_cfg.hp = new_hp

    # --- Now switch to the correct phase deck (shuffle once)
    if dead:
        _ornstein_smough_heatup(state, cfg, dead, rng)

    # close the prompt
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.rerun()

def _four_kings_summon(cfg, state, rng):
    """Perform a Royal Summons (max 3)."""
    summons = state.get("four_kings_summons", 0)
    if summons >= 3:
        return

    summons += 1
    state["four_kings_summons"] = summons

    # --- ENABLE next king (persisted in state, mirrored to session)
    enabled_before = state.get("enabled_kings", 1)
    enabled_after = min(enabled_before + 1, 4)
    state["enabled_kings"] = enabled_after
    st.session_state["enabled_kings"] = enabled_after

    # --- combine current + discard back into deck
    draw = state["draw_pile"]
    discard = state["discard_pile"]
    if state.get("current_card"):
        discard.append(state["current_card"])
        state["current_card"] = None
    draw.extend(discard)
    discard.clear()

    # --- remove one random card from the deck
    removed = None
    if draw:
        removed = rng.choice(draw)
        draw.remove(removed)

    # --- pick tier based on the *summons count* (1→2, 2→3, 3→4)
    tier = 1 + summons
    tier_key = str(tier)

    # ensure we match even if JSON encodes numbers as strings
    heatups = [b for b, v in cfg.behaviors.items()
               if str(v.get("heatup", "")) == tier_key]
    rng.shuffle(heatups)
    added = heatups[:2]
    draw.extend(added)

    rng.shuffle(draw)
    
    # --- Persist enabled_kings into state for stable reloads
    state["enabled_kings"] = st.session_state.get("enabled_kings", 1)


def list_behavior_files() -> List[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.json"))


def match_behavior_prefix(behaviors: dict[str, dict], prefix: str) -> list[str]:
    """
    Return all behavior keys that start with the given prefix (case-insensitive).
    Example:
        match_behavior_prefix(cfg.behaviors, "Stomach Slam")
        -> ["Stomach Slam 1", "Stomach Slam 2"]
    """
    prefix_lower = prefix.lower().strip()
    return [k for k in behaviors if k.lower().startswith(prefix_lower)]


def ensure_behavior_state(state):
    if "behavior_state" not in state:
        state["behavior_state"] = {
            "draw_pile": [],
            "discard_pile": [],
            "current_card": None,
            "entities": [],
        }
    return state["behavior_state"]


def _make_king_entity(cfg, idx: int) -> Entity:
    """Create 'King {idx}' as an Entity object."""
    hpmax = int(cfg.raw.get("health", 25))
    label = f"King {idx}"
    return Entity(
        id=f"king_{idx}",
        label=label,
        hp_max=hpmax,
        hp=hpmax,
        heatup_thresholds=[],  # Four Kings don't use standard heat-up thresholds
        crossed=[],
    )


# ------------------------
# JSON Importer
# ------------------------
@st.cache_data
def _read_behavior_json(path_str: str) -> dict:
    with open(path_str, "r", encoding="utf-8") as f:
        return json.load(f)
    
def load_behavior(fname: Path) -> BehaviorConfig:
    # 1) Load base raw config from JSON
    base_raw = deepcopy(_read_behavior_json(str(fname)))  # copy so we can mutate safely
    name = fname.stem

    # 2) Apply NG+ to raw before building entities / thresholds
    level = get_current_ngplus_level()
    raw = apply_ngplus_to_raw(
        base_raw,
        level,
        enemy_name=name,
    )

    hp = int(raw.get("health", 1))
    heatup_threshold = raw.get("heatup", None) if isinstance(raw.get("heatup"), int) else None

    # --- Detect multi-entity bosses dynamically
    def is_entity_block(v: dict) -> bool:
        """Heuristic: looks like a sub-boss data block if it defines health/armor."""
        if not isinstance(v, dict):
            return False
        keys = set(v.keys())
        return (
            "health" in keys
            and "armor" in keys
            and not any(x in keys for x in ("left", "middle", "right"))
        )

    entity_blocks = {
        k: v for k, v in raw.items()
        if is_entity_block(v)
    }

    # --- Special case: The Four Kings (precreate 4 entities)
    if name == "The Four Kings":
        entities = [
            Entity(
                id=f"king_{i}",
                label=f"King {i}",
                hp_max=hp,
                hp=hp,
                heatup_thresholds=[],  # they don't use standard heatup thresholds
                crossed=[],
            )
            for i in range(1, 5)
        ]
    # --- Build entity list
    elif entity_blocks:
        # Multi-entity boss (e.g., Ornstein & Smough, Four Kings)
        entities = []
        for label, data in entity_blocks.items():
            hp_val = int(data.get("health", hp))
            heatup_val = data.get("heatup", None)
            entities.append(
                Entity(
                    id=label.lower().replace(" ", "_"),
                    label=label,
                    hp_max=hp_val,
                    hp=hp_val,
                    heatup_thresholds=[heatup_val] if isinstance(heatup_val, int) else [],
                    crossed=[],
                )
            )
    else:
        # Regular single entity
        entities = [
            Entity(
                id=name.lower().replace(" ", "_"),
                label=name,
                hp_max=hp,
                hp=hp,
                heatup_thresholds=[heatup_threshold] if heatup_threshold else [],
                crossed=[],
            )
        ]

    # --- Determine if this boss uses shared data (e.g., Four Kings)
    data_sharing = bool(raw.get("data_sharing", False))

    # --- Display cards (always-visible data card)
    display_cards = []
    data_card_path = _path(f"{name} - data.jpg")

    if data_sharing:
        # Shared card: use only the group-level data card
        if Path(data_card_path).exists():
            display_cards.append(data_card_path)
    else:
        # Per-entity data cards if they exist (e.g., Ornstein, Smough)
        if entity_blocks:
            for label in entity_blocks:
                per_entity_path = _path(f"{label} - data.jpg")
                if Path(per_entity_path).exists():
                    display_cards.append(per_entity_path)
        elif Path(data_card_path).exists():
            display_cards.append(data_card_path)

    # --- Always-display behavior cards
    for extra in raw.get("always_display", []):
        clean_name = _strip_behavior_suffix(extra)
        extra_path = _path(f"{name} - {clean_name}.jpg")
        if Path(extra_path).exists():
            display_cards.append(extra_path)

    # --- Determine behaviors dict
    if "behavior" in raw:  # regular enemy
        behaviors = {name: raw["behavior"]}
    else:
        behaviors = raw.get("behaviors")
        if behaviors is None:
            meta = {
                "name", "cards", "tier", "heatup", "health",
                "armor", "resist", "entities", "always_display"
            }

            behaviors = {
                k: v for k, v in raw.items()
                if isinstance(v, dict)
                and k not in meta
                and not is_entity_block(v)
            }
 
    # --- Build deck and heat-up pool
    deck = [k for k, v in behaviors.items() if not v.get("heatup", False)]
    heatup_pool = [k for k, v in behaviors.items() if v.get("heatup", False)]

    heatup = None
    if heatup_pool:
        heatup = Heatup(
            mode="add_random",
            pool=heatup_pool,
            per_trigger=1,
            manual_only=(heatup_threshold is None),
        )

    is_invader = bool(raw.get("is_invader", False))
    text = raw.get("text", "")

    return BehaviorConfig(
        name=name,
        tier="enemy" if "behavior" in raw else "boss",
        entities=entities,
        display_cards=display_cards,
        cards=raw.get("cards"),
        deck=deck,
        heatup=heatup,
        raw=raw,
        behaviors=behaviors,
        is_invader=is_invader,
        text=text,
    )


# ------------------------
# Deck + Heat-up mechanics
# ------------------------
def build_draw_pile(cfg: BehaviorConfig, rng: random.Random, no_shuffle: bool=False) -> list[str]:
    """Build a shuffled deck, deterministic for a given seed."""
    # Handle special setup rules
    rule_func = DECK_SETUP_RULES.get(cfg.name.lower())
    if rule_func:
        return rule_func(cfg, rng)

    behaviors = cfg.behaviors

    # Collect normal, non-heatup behaviors
    deck = [b for b in behaviors if not behaviors[b].get("heatup", False)]

    # Shuffle
    rng.shuffle(deck)

    # Respect deck size if specified
    deck_limit = cfg.raw.get("cards")
    if deck_limit:
        deck = deck[: int(deck_limit)]

    return deck


def register_deck_rule(name: str):
    """Decorator for registering a special deck setup rule for a given boss name."""
    def decorator(func):
        DECK_SETUP_RULES[name.lower()] = func
        return func
    return decorator


def apply_special_rules(cfg, rng):
    """Apply any registered special rules to the boss's deck setup."""
    boss_name = cfg.name.lower()
    rule_func = DECK_SETUP_RULES.get(boss_name)
    if rule_func:
        return rule_func(cfg, rng)
    return cfg.deck[:]  # Default: no modification


def build_dual_boss_draw_pile(cfg: BehaviorConfig, rng: random.Random) -> List[str]:
    """Build a shuffled pile of length = cards count, unless cards not specified."""
    count = cfg.raw.get("cards", len(cfg.deck))  # fallback: all cards
    pile = cfg.deck[:count] if len(cfg.deck) >= count else cfg.deck[:]
    rng.shuffle(pile)
    return pile


def force_include(
    deck: list[str],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    limit: int | None = None,
    rng: random.Random | None = None,
    no_shuffle: bool = False,
) -> list[str]:
    """
    Utility function to normalize a deck with inclusion/exclusion rules and limit.

    - include: Cards that must be present in the final deck.
    - exclude: Cards that must be removed from the deck.
    - limit: Maximum deck size (typically from cfg.raw["cards"]).
    - rng: Optional random generator (for trimming extra cards randomly).
    """
    include = include or []
    exclude = exclude or []
    rng = rng or random

    # Remove excluded cards
    filtered = [c for c in deck if c not in exclude]

    # Add always-included cards if missing
    for c in include:
        if c not in filtered:
            filtered.insert(0, c)

    # Deduplicate while preserving order
    seen = set()
    unique_deck = [c for c in filtered if not (c in seen or seen.add(c))]

    # Enforce limit
    if limit and len(unique_deck) > limit:
        optional_cards = [c for c in unique_deck if c not in include]
        while len(unique_deck) > limit and optional_cards:
            drop = rng.choice(optional_cards)
            unique_deck.remove(drop)
            optional_cards.remove(drop)

    # Shuffle final deck
    if not no_shuffle:
        rng.shuffle(unique_deck)
    return unique_deck


@register_deck_rule("Black Dragon Kalameet")
def setup_kalameet(cfg, rng):
    """
    Mark of Calamity and Hellfire Blast are always included.
    """
    deck = cfg.deck[:]
    limit = cfg.raw.get("cards", len(deck))
    return force_include(deck, include=["Mark of Calamity", "Hellfire Blast"], limit=limit, rng=rng)


@register_deck_rule("Old Iron King")
def setup_kalameet(cfg, rng):
    """
    Mark of Calamity and Hellfire Blast are always included.
    """
    always_include = match_behavior_prefix(cfg.behaviors, "Fire Beam")
    deck = cfg.deck[:]
    limit = cfg.raw.get("cards", len(deck))
    return force_include(deck, include=always_include, limit=limit, rng=rng)


@register_deck_rule("Executioner Chariot")
def setup_chariot(cfg, rng):
    """
    The first phase is always Death Race 1-4.
    """
    base_deck = [b for b in cfg.deck if not cfg.behaviors.get(b, {}).get("heatup", False)]
    always_include = match_behavior_prefix(cfg.behaviors, "Death Race")
    deck = force_include(
        base_deck,
        include=always_include,
        limit=4,
        rng=rng,
        no_shuffle=True
    )
    return deck


@register_deck_rule("Great Grey Wolf Sif")
def setup_sif(cfg, rng):
    """
    Limping Strike is always excluded.
    """
    deck = cfg.deck[:]
    limit = cfg.raw.get("cards", len(deck))
    return force_include(deck, exclude=["Limping Strike"], limit=limit, rng=rng)


@register_deck_rule("The Last Giant")
def setup_last_giant(cfg, rng):
    """
    3 normal cards, 3 arm cards, never Falling Slam
    """
    deck = [
        b for b, v in cfg.behaviors.items()
        if not v.get("arm", False)
        and not v.get("heatup", False)
        and b != "Falling Slam"
    ]
    arm_cards = [b for b, v in cfg.behaviors.items() if v.get("arm", False)]
    rng.shuffle(arm_cards)
    limit = cfg.raw.get("cards", len(deck))
    return force_include(deck, exclude=["Falling Slam"], include=arm_cards[:3], limit=limit, rng=rng)


@register_deck_rule("Vordt of the Boreal Valley")
def setup_vordt(cfg, rng):
    """
    Vordt uses two parallel decks: Movement and Attack.
    Movement cards have type 'move', attack cards 'attack'.
    """
    behaviors = cfg.behaviors
    move_cards = [b for b in behaviors if behaviors[b].get("type", None) == "move" and not behaviors[b].get("heatup", False)]
    atk_cards = [b for b in behaviors if behaviors[b].get("type", None) == "attack" and not behaviors[b].get("heatup", False)]

    rng.shuffle(move_cards)
    rng.shuffle(atk_cards)

    # Store both decks in cfg for the UI
    cfg.raw["vordt_move_draw"] = move_cards[:4]
    cfg.raw["vordt_move_discard"] = []
    cfg.raw["vordt_attack_draw"] = atk_cards[:3]
    cfg.raw["vordt_attack_discard"] = []

    # Return a combined list (just for compatibility)
    return move_cards + atk_cards


@register_deck_rule("gaping dragon")
def setup_gaping_dragon(cfg, rng):
    behaviors = cfg.behaviors

    # base deck: non-heatup behaviors
    base_deck   = [b for b, v in behaviors.items() if not v.get("heatup", False)]
    # heatup pool: all behaviors marked heatup
    heatup_pool = [b for b, v in behaviors.items() if v.get("heatup", False)]

    chosen_heatup = rng.choice(heatup_pool) if heatup_pool else None

    # include both Stomach Slam variants if present
    always_include = match_behavior_prefix(cfg.behaviors, "Stomach Slam")
    always_include.append(chosen_heatup)

    limit = cfg.cards or len(base_deck)

    # exclude any you always remove (example kept from your earlier note)
    deck = force_include(
        base_deck,
        exclude=["Crawling Charge"],
        include=always_include,
        limit=limit,
        rng=rng,
    )

    return deck


def _apply_sif_limping_mode(state, cfg):
    """When triggered, replace Sif's deck with only 'Limping Strike'."""
    limp_card = None
    for name in cfg.behaviors.keys():
        if "Limping Strike" in name:
            limp_card = name
            break

    state["draw_pile"] = [limp_card]
    state["discard_pile"] = []
    state["current_card"] = None
    state["sif_limping_active"] = True


def _ornstein_smough_heatup(state, cfg, dead_boss, rng):
    """
    Ornstein & Smough special heat-up triggered when one reaches 0 HP:
      - If Smough dies: Ornstein +10 HP (cap at max), deck = heatup=='Ornstein'
      - If Ornstein dies: Smough +15 HP (cap at max), deck = heatup=='Smough'
      - New deck is shuffled ONCE here; later recycles will not shuffle
    """
    # Decide survivor, heal amount, and tag for heat-up pool
    if dead_boss == "Smough":
        tag = "Ornstein"
        state["disabled_smough"] = True
        state["disabled_ornstein"] = False
    else:  # Ornstein dead
        tag = "Smough"
        state["disabled_ornstein"] = True
        state["disabled_smough"] = False

    # Build the heat-up deck for the survivor tag
    heatup_cards = [name for name, data in cfg.behaviors.items()
                    if data.get("heatup") == tag]

    # Replace deck: shuffle ONCE here
    new_deck = heatup_cards[:]
    rng.shuffle(new_deck)

    state["draw_pile"] = new_deck
    state["discard_pile"] = []
    state["current_card"] = None

    # Mark phase & control future recycle behavior
    state["ornstein_smough_phase"] = tag           # 'Ornstein' or 'Smough'
    state["os_phase_shuffled_once"] = True         # documentation flag
    state["heatup_done"] = True                    # skip standard heat-up afterwards


def _apply_vordt_heatup(cfg, state, rng, which: str) -> None:
    """
    Add one heat-up card to Vordt's attack or move deck.
    """
    if which == "attack":
        draw = state["vordt_attack_draw"]
        discard = state["vordt_attack_discard"]
        target_type = "attack"
    else:
        draw = state["vordt_move_draw"]
        discard = state["vordt_move_discard"]
        target_type = "move"

    # Find candidate heatup cards
    candidates = [
        name for name, data in cfg.behaviors.items()
        if data.get("heatup", False) and data.get("type") == target_type
    ]

    if not candidates:
        return  # no special cards defined; nothing to do

    # Try to avoid duplicates if possible
    available = [c for c in candidates if c not in draw]
    if not available:
        available = candidates

    chosen = rng.choice(available)

    draw.extend(discard)
    discard.clear()
    draw.append(chosen)
    rng.shuffle(draw)


def _apply_last_giant_heatup(cfg, state, rng):
    """The Last Giant: Add Falling Slam, remove arm cards, replace with heat-up cards."""
    draw = state["draw_pile"]
    discard = state["discard_pile"]

    if state.get("current_card"):
        discard.append(state["current_card"])
        state["current_card"] = None
    draw.extend(discard)
    discard.clear()

    if "Falling Slam" not in draw:
        draw.append("Falling Slam")

    arm_cards = [b for b, v in cfg.behaviors.items() if v.get("arm", False)]
    draw[:] = [c for c in draw if c not in arm_cards]

    heatup_cards = [b for b, v in cfg.behaviors.items() if v.get("heatup", False)]
    rng.shuffle(heatup_cards)
    draw.extend(heatup_cards[:3])

    rng.shuffle(draw)

    state["heatup_done"] = True


def _apply_artorias_heatup(cfg, state, rng):
    """
    Artorias special heat-up:
      - Return current card + discard pile to draw pile
      - Remove 2 random (non-heatup) behavior cards
      - Add ALL heat-up cards
      - Shuffle the resulting draw pile
    """
    # Merge back discard and current
    state["draw_pile"].extend(state.get("discard_pile", []))
    state["discard_pile"].clear()

    if state.get("current_card"):
        state["draw_pile"].append(state["current_card"])
        state["current_card"] = None

    # Identify all heat-up cards
    heatup_cards = [b for b, v in cfg.behaviors.items() if v.get("heatup", False)]
    if not heatup_cards:
        return

    # Remove two random *non-heatup* cards if possible
    removable = [b for b in state["draw_pile"] if b not in heatup_cards]
    num_to_remove = min(2, len(removable))
    if num_to_remove > 0:
        to_remove = rng.sample(removable, num_to_remove)
        state["draw_pile"] = [b for b in state["draw_pile"] if b not in to_remove]

    # Add all heat-up cards
    for card in heatup_cards:
        if card not in state["draw_pile"]:
            state["draw_pile"].append(card)

    # Shuffle
    rng.shuffle(state["draw_pile"])

    # Mark completion
    state["heatup_done"] = True


def recycle_deck(state: Dict[str, Any]) -> None:
    """
    If draw pile is empty, recycle discard + current into a new draw pile
    WITHOUT changing order.
    """
    if not state["draw_pile"]:
        new_pile = state["discard_pile"][:]
        if state.get("current_card"):
            new_pile.append(state["current_card"])
            state["current_card"] = None
        state["draw_pile"] = new_pile
        state["discard_pile"] = []
        
    # Try to identify the current boss name from the loaded file
    boss_name = None
    if "selected_file" in state:
        try:
            boss_name = Path(state["selected_file"]).stem
        except Exception:
            boss_name = None

    # --- Crossbreed Priscilla: invisibility flag
    if boss_name == "Crossbreed Priscilla":
        state["priscilla_invisible"] = True
    else:
        state.pop("priscilla_invisible", None)


def apply_heatup(state, cfg, rng, reason="manual"):
    """
    Apply the standard heat-up procedure:
      - Happens only once
      - Discarded and current cards return to the draw pile
      - Add one random heat-up card
      - Shuffle draw pile
    """
    # Prevent multiple heatups
    if state.get("heatup_done", False) and cfg.name not in {"Old Dragonslayer","Vordt of the Boreal Valley"}:
        return

    # Identify available heat-up cards
    heatup_cards = [
        name for name, data in cfg.behaviors.items()
        if data.get("heatup", False)
    ]
    if not cfg.is_invader and not heatup_cards and cfg.name not in {"The Pursuer",}:
        return  # Nothing to do

    # Merge discard pile and current card back into draw pile
    if cfg.name not in {"Old Dragonslayer",}:
        state["draw_pile"].extend(state.get("discard_pile", []))
        state["discard_pile"].clear()

        if state.get("current_card"):
            state["draw_pile"].append(state["current_card"])
            state["current_card"] = None

    chosen = None

    if cfg.is_invader or cfg.name in {"The Pursuer",}:
        if cfg.name not in {"Oliver the Collector",}:
            base_pool = [b for b, v in cfg.behaviors.items() if not v.get("heatup", False)]
            candidates = [b for b in base_pool if b not in state["draw_pile"]]
            if not candidates:
                return  # no unique card to add
            chosen = rng.choice(candidates)
    elif cfg.name == "Guardian Dragon":
        state["draw_pile"] += heatup_cards
    elif cfg.name in {"The Last Giant", "Vordt of the Boreal Valley"}:
        # Don't add a random heat-up card - this is handled in the special rules
        pass
    else:
        # Add one random heat-up card (not already in the deck)
        chosen = rng.choice(heatup_cards)

    if chosen and chosen not in state["draw_pile"] and cfg.name not in {"Old Dragonslayer",}:
        state["draw_pile"].append(chosen)

    # Shuffle new deck
    if cfg.name not in {"Old Dragonslayer",}:
        rng.shuffle(state["draw_pile"])

    # --- Apply special heat-up effects (invaders, etc.)
    _apply_special_heatup_effects(cfg, state, rng, reason=="manual")

    # Mark as complete
    if cfg.name not in {"Old Dragonslayer", "Vordt of the Boreal Valley"}:
        state["heatup_done"] = True


def _apply_special_heatup_effects(cfg, state, rng, manual):
    """Apply boss- or invader-specific heat-up modifications."""
    effects = {
        "Armorer Dennis": _apply_armorer_dennis_heatup,
        "Maldron the Assassin": apply_maldron_heatup,
        "Oliver the Collector": _replace_with_missing_cards,
        "Old Dragonslayer": _old_dragonslayer_heatup,
        "Artorias": _apply_artorias_heatup,
        "Smelter Demon": _apply_smelter_demon_heatup,
        "The Pursuer": _apply_pursuer_heatup,
        "Old Iron King": _apply_old_iron_king_heatup,
        "The Last Giant": _apply_last_giant_heatup,
        "Vordt of the Boreal Valley": _apply_vordt_heatup
    }

    if cfg.name == "Crossbreed Priscilla":
        state["priscilla_invisible"] = True

    func = effects.get(cfg.name)
    if not func:
        return

    # For Old Dragonslayer, handle UI confirmation externally
    if cfg.name == "Old Dragonslayer":
        confirmed = manual or state.get("old_dragonslayer_confirmed", False)
        applied, needs_confirm = func(cfg, state, rng, confirmed=confirmed)

        if needs_confirm:
            # Tell the UI to prompt the player
            state["old_dragonslayer_pending"] = True
            state["old_dragonslayer_confirmed"] = False
        else:
            # If applied or rejected, clear prompt
            state["old_dragonslayer_pending"] = False
            state["old_dragonslayer_confirmed"] = False
        return
    elif cfg.name == "Vordt of the Boreal Valley":
        _apply_vordt_heatup_special(cfg, state, rng, manual=manual)
        return

    # For all others
    func(cfg, state, rng)


def _apply_vordt_heatup_special(cfg, state, rng, manual: bool) -> None:
    """
    Vordt special heatup logic.

    - HP-slider-driven heatups:
        pending_heatup_type is set to "vordt_attack", "vordt_move" or "vordt_both".
    - Manual button heatups:
        we infer which stage(s) to apply based on vordt_*_heatup_done flags.
    """
    pending_type = st.session_state.get("pending_heatup_type")

    attack_done = st.session_state.get("vordt_attack_heatup_done", False)
    move_done   = st.session_state.get("vordt_move_heatup_done", False)

    if manual and not pending_type:
        # Manual heatup with no HP context: choose first unfinished stage(s)
        if not attack_done and not move_done:
            pending_type = "vordt_attack"
        elif attack_done and not move_done:
            pending_type = "vordt_move"
        else:
            # both already done; nothing to do
            return

    # Apply to the appropriate deck(s)
    if pending_type in ("vordt_attack", "vordt_both"):
        _apply_vordt_heatup(cfg, state, rng, which="attack")
        st.session_state["vordt_attack_heatup_done"] = True

    if pending_type in ("vordt_move", "vordt_both"):
        _apply_vordt_heatup(cfg, state, rng, which="move")
        st.session_state["vordt_move_heatup_done"] = True

    # Clear prompt flags (used for HP-driven prompts)
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.session_state["pending_heatup_type"] = None


def apply_maldron_heatup(cfg, state, rng):
    """
    Maldron the Assassin:
      When he heats up, he returns to full health.
    This resets HP on both the BehaviorConfig entities and the state mirror.
    """
    # Reset HP on the BehaviorConfig entities (source of truth)
    for ent in getattr(cfg, "entities", []):
        # Only touch Maldron's own entity; in case the config ever
        # has multiple entities for some reason, this keeps it safe.
        if "Maldron" in ent.label:
            ent.hp = ent.hp_max

    tracker = st.session_state.setdefault("hp_tracker", {})

    for ent in cfg.entities:
        ent_id = ent.id
        # make sure HP is max in the tracker
        tracker[ent_id] = {"hp": ent.hp_max, "hp_max": ent.hp_max}

    # also mirror into the state["entities"] dicts, just to be safe
    for ent_state in state.get("entities", []):
        if "Maldron" in ent_state.get("label", "") and "hp_max" in ent_state:
            ent_state["hp"] = ent_state["hp_max"]


def _apply_armorer_dennis_heatup(cfg, state, rng):
    """Increase dodge on all behaviors by +1."""
    for bdata in cfg.behaviors.values():
        bdata["dodge"] = int(bdata["dodge"]) + 1


def _apply_pursuer_heatup(cfg, state, rng):
    """The Pursuer: buff all damage by +1."""
    # Increase all damage values by +1
    for bdata in cfg.behaviors.values():
        for slot in ["left", "middle", "right"]:
            if slot not in bdata or "damage" not in bdata.get(slot, {}):
                continue
            bdata[slot]["damage"] = int(bdata[slot]["damage"]) + 1


def _apply_old_iron_king_heatup(cfg, state, rng):
    """The Pursuer: buff all damage by +1."""
    # Increase all Fire Beam dodge and damage values by +1
    for b in [b for b in cfg.behaviors if "Fire Beam" in b]:
        cfg.behaviors[b]["dodge"] = int(cfg.behaviors[b]["dodge"]) + 1
        for slot in ["left", "middle", "right"]:
            if slot not in cfg.behaviors[b] or "damage" not in cfg.behaviors[b].get(slot, {}):
                continue
            cfg.behaviors[b][slot]["damage"] = int(cfg.behaviors[b][slot]["damage"]) + 1


def _apply_smelter_demon_heatup(cfg, state, rng):
    """Smelter Demon heat-up: replace deck with 5 random heat-up cards."""
    # find all heat-up cards
    heatup_cards = [
        b for b, info in cfg.behaviors.items()
        if info.get("heatup", False)
    ]

    # pick 5 random ones (or all if fewer than 5)
    rng.shuffle(heatup_cards)
    chosen = heatup_cards[:5]

    # replace deck
    state["draw_pile"] = chosen[:]
    state["discard_pile"] = []
    state["current_card"] = None

    state["heatup_done"] = True


def _replace_with_missing_cards(cfg, state, rng):
    """Replace current draw pile with all cards that were not in it."""
    all_cards = [b for b, v in cfg.behaviors.items() if not v.get("heatup", False)]
    current_deck = set(state.get("draw_pile", []))
    missing = [b for b in all_cards if b not in current_deck]

    if not missing:
        return

    # Clear discard/current cards and use missing set as new deck
    state["draw_pile"] = missing.copy()
    state["discard_pile"].clear()
    state["current_card"] = None
    rng.shuffle(state["draw_pile"])


def _old_dragonslayer_heatup(cfg, state, rng, confirmed=False):
    """
    Handle Old Dragonslayer's special heat-up:
      - Up to 3 times total
      - Each triggered manually or by losing 4+ HP at once
      - Adds a random heat-up card to TOP of deck (no shuffle)
      - Returns a tuple (applied: bool, needs_confirm: bool)
    """
    count = state.get("old_dragonslayer_heatups", 0)
    if count >= 3:
        return False, False  # already maxed out

    if not confirmed:
        return False, True  # needs UI confirmation first

    # Find a random heat-up card
    heatup_cards = [b for b, v in cfg.behaviors.items() if v.get("heatup", False)]
    if not heatup_cards:
        return False, False

    chosen = rng.choice(heatup_cards)
    state["draw_pile"].insert(0, chosen)
    state["old_dragonslayer_heatups"] = count + 1

    return True, False  # applied successfully


def _add_tag(bdata, tag):
    """Example helper: add a tag field to a behavior if not present."""
    tags = bdata.setdefault("tags", [])
    if tag not in tags:
        tags.append(tag)


def check_and_trigger_heatup(prev_hp: int, new_hp: int, ent: Entity, state: Dict[str, Any],
                             cfg: BehaviorConfig, rng: random.Random) -> List[int]:
    """Detect threshold crossing and trigger heat-up."""
    crossed_now = []
    for th in ent.heatup_thresholds:
        if th in ent.crossed:
            continue
        if prev_hp > th >= new_hp:
            crossed_now.append(th)

    for th in crossed_now:
        ent.crossed.append(th)
        apply_heatup(state, cfg, rng, reason="auto")
        
    return crossed_now
