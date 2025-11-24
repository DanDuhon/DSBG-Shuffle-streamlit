from __future__ import annotations
import json, random, os, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

ASSETS_DIR = Path("assets") / "behavior cards"
DATA_DIR = Path("data") / "behaviors"
DECK_SETUP_RULES = {}
NG_MAX_LEVEL = 5
_DAMAGE_BONUS_BY_LEVEL = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
_HEALTH_LEVEL_BY_LEVEL = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
_DODGE_BONUS_BY_LEVEL = {
    0: 0,
    1: 0,
    2: 1,
    3: 1,
    4: 2,
    5: 2,
}


@dataclass
class Entity:
    id: str
    label: str
    hp_max: int
    hp: int
    heatup_thresholds: List[int] = field(default_factory=list)
    crossed: List[int] = field(default_factory=list)


@dataclass
class Heatup:
    mode: str                # "add_random" | "add_specific" | "replace"
    pool: List[str]          # image paths
    per_trigger: int = 1
    manual_only: bool = False


@dataclass
class BehaviorConfig:
    name: str
    tier: str
    entities: List[Entity]
    cards: int                      # number of cards in the initial deck
    display_cards: List[str]        # always-visible cards (e.g. Data card)
    deck: List[str]                 # initial draw pile
    raw: dict
    heatup: Optional[Heatup] = None
    behaviors: dict = field(default_factory=dict)
    is_invader: bool = False

    @property
    def data_cards(self) -> list[str]:
        """
        Return a list of 'data' cards (always visible). For bosses/invaders,
        this will usually be '<Name> - data.jpg'. Regular enemies still use the same logic.
        """
        cards = []
        # For bosses/invaders: always have at least one data card image
        data_name = f"{self.name} - data.jpg"
        cards.append(data_name)

        # Special case: dual entities (e.g., Ornstein & Smough)
        if "&" in self.name:
            parts = [p.strip() for p in self.name.split("&")]
            for p in parts:
                cards.append(f"{p} - data.jpg")

        return cards

    @classmethod
    def from_json(cls, name: str, raw: dict, tier: str = "boss") -> "BehaviorConfig":
        """
        Factory for creating a BehaviorConfig from a raw JSON dictionary.
        Automatically handles flat vs structured formats.
        """
        # Determine behavior list
        if "behaviors" in raw:
            deck = list(raw["behaviors"].keys())
        else:
            # Flat structure: use all top-level dict entries except config fields
            deck = [
                os.path.splitext(os.path.basename(c))[0] if isinstance(c, str) else c
                for c in deck
            ]

        # Build entities (if defined)
        entities = raw.get("entities", [])

        # Determine number of cards
        cards = raw.get("cards", len(deck))

        # Determine heatup threshold
        heatup_val = raw.get("heatup")
        heatup = Heatup(value=heatup_val) if heatup_val else None

        # Return a complete config
        return cls(
            name=name,
            tier=tier,
            entities=entities,
            cards=cards,
            display_cards=[f"{name} - data.jpg"],
            deck=deck,
            raw=raw,
            heatup=heatup,
        )


# ------------------------
# Helpers
# ------------------------
def _path(img_rel: str) -> str:
    return str(Path("assets") / "behavior cards" / img_rel)


def list_behavior_files() -> List[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.json"))


def card_image_path(boss_name: str, behavior_name: str) -> str:
    """Map a behavior name to its card image path."""
    return _path(f"{boss_name} - {behavior_name}.jpg")


def match_behavior_prefix(behaviors: dict[str, dict], prefix: str) -> list[str]:
    """
    Return all behavior keys that start with the given prefix (case-insensitive).
    Example:
        match_behavior_prefix(cfg.behaviors, "Stomach Slam")
        -> ["Stomach Slam 1", "Stomach Slam 2"]
    """
    prefix_lower = prefix.lower().strip()
    return [k for k in behaviors if k.lower().startswith(prefix_lower)]


def _strip_behavior_suffix(name: str) -> str:
    """
    Strip numeric or trailing copy markers from behavior names.
    Example:
        "Stomach Slam 1" -> "Stomach Slam"
        "Stomach Slam 2" -> "Stomach Slam"
        "Death Race 4"   -> "Death Race"
    """
    return re.sub(r"\s+\d+$", "", name.strip())


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


def _health_extra_for_level(base_hp: int, health_level: int) -> int:
    """
    Compute extra max health for a given base HP and health bonus level.

    Rules:
      - base HP 1-2:   +health_level
      - base HP 3-7:   2,3,5,6,8 for levels 1-5
      - base HP 8-10:  +2 * health_level
      - base HP > 10:  +10% of base (rounded up) per level
    """
    if health_level <= 0 or base_hp <= 0:
        return 0

    # 1-2 HP: +level
    if base_hp <= 2:
        return health_level

    # 3-7 HP: sequence 2,3,5,6,8
    if 3 <= base_hp <= 7:
        seq = [0, 2, 3, 5, 6, 8]  # index by health_level
        return seq[health_level]

    # 8-10 HP: +2 * level
    if 8 <= base_hp <= 10:
        return 2 * health_level

    # > 10 HP: +10% of base (rounded up) per level
    per_level = (base_hp + 9) // 10  # ceil(base_hp * 0.1)
    return per_level * health_level


def _apply_ng_plus_to_entities(cfg: BehaviorConfig, health_level: int) -> None:
    """Adjust entity and raw health fields in-place based on NG+ health rules."""
    if health_level <= 0:
        return

    raw = cfg.raw

    def adjust_block(block: dict) -> int:
        base_hp = int(block.get("health", 0))
        extra = _health_extra_for_level(base_hp, health_level)
        new_hp = base_hp + extra
        block["health"] = new_hp
        return new_hp

    # Regular enemy: "behavior" key lives in raw
    if "behavior" in raw:
        new_hp = adjust_block(raw)
        # Single entity representing this enemy
        for ent in cfg.entities:
            ent.hp_max = new_hp
            ent.hp = new_hp
        return

    # Boss / invader: may have group health + per-entity blocks (Ornstein & Smough, etc.)
    base_top_hp = raw.get("health")
    new_top_hp = None
    if base_top_hp is not None:
        new_top_hp = adjust_block(raw)

    for ent in cfg.entities:
        block = raw.get(ent.label)
        if isinstance(block, dict) and "health" in block:
            new_hp = adjust_block(block)
            ent.hp_max = new_hp
            ent.hp = new_hp
        elif new_top_hp is not None:
            ent.hp_max = new_top_hp
            ent.hp = new_top_hp


def _apply_ng_plus_to_behaviors(cfg: BehaviorConfig, damage_bonus: int, dodge_bonus: int) -> None:
    """Adjust damage and dodge on behavior cards in-place."""
    if damage_bonus <= 0 and dodge_bonus <= 0:
        return

    for _, bdata in cfg.behaviors.items():
        # Dodge bonus applies to top-level "dodge" on behavior cards
        if dodge_bonus and "dodge" in bdata:
            bdata["dodge"] = int(bdata["dodge"]) + dodge_bonus

        # Damage bonus applies to left/middle/right slots if they have "damage"
        if damage_bonus:
            for slot in ("left", "middle", "right"):
                slot_data = bdata.get(slot)
                if not isinstance(slot_data, dict):
                    continue
                if "damage" not in slot_data:
                    continue
                try:
                    dmg_val = int(slot_data["damage"])
                except (TypeError, ValueError):
                    continue
                slot_data["damage"] = dmg_val + damage_bonus


def apply_ng_plus(cfg: BehaviorConfig, level: int) -> None:
    """
    Apply New Game+ modifiers in-place to a loaded BehaviorConfig.

    Summary:
      - NG+N: +N damage
      - Health bonus level = N (scaled by base HP via _health_extra_for_level)
      - Dodge bonus: +0 at 1, +1 at 2-3, +2 at 4-5
    """
    if not level or level <= 0:
        return

    level = max(0, min(int(level), NG_MAX_LEVEL))

    health_level = _HEALTH_LEVEL_BY_LEVEL.get(level, level)
    damage_bonus = _DAMAGE_BONUS_BY_LEVEL.get(level, level)
    dodge_bonus = _DODGE_BONUS_BY_LEVEL.get(level, 0)

    _apply_ng_plus_to_entities(cfg, health_level)
    _apply_ng_plus_to_behaviors(cfg, damage_bonus, dodge_bonus)


# ------------------------
# JSON Importer
# ------------------------
def load_behavior(fname: Path) -> BehaviorConfig:
    with open(fname, "r", encoding="utf-8") as f:
        raw = json.load(f)

    name = fname.stem
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
    if state.get("heatup_done", False) and cfg.name not in {"Old Dragonslayer",}:
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
    elif cfg.name == "The Last Giant":
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
    if cfg.name not in {"Old Dragonslayer",}:
        state["heatup_done"] = True


def _apply_special_heatup_effects(cfg, state, rng, manual):
    """Apply boss- or invader-specific heat-up modifications."""
    effects = {
        "Armorer Dennis": _apply_armorer_dennis_heatup,
        "Oliver the Collector": _replace_with_missing_cards,
        "Old Dragonslayer": _old_dragonslayer_heatup,
        "Artorias": _apply_artorias_heatup,
        "Smelter Demon": _apply_smelter_demon_heatup,
        "The Pursuer": _apply_pursuer_heatup,
        "Old Iron King": _apply_old_iron_king_heatup,
        "The Last Giant": _apply_last_giant_heatup
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

    # For all others
    func(cfg, state, rng)


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


# ------------------------
# State management
# ------------------------
def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "selected_file": state.get("selected_file"),
        "draw_pile": state.get("draw_pile", []),
        "discard_pile": state.get("discard_pile", []),
        "current_card": state.get("current_card"),
        "display_cards": state.get("display_cards", []),
        "entities": state.get("entities", [])
    }
