from __future__ import annotations
import json, random, os, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

ASSETS_DIR = Path("assets") / "behavior cards"
DATA_DIR = Path("data") / "behaviors"
DECK_SETUP_RULES = {}


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

    # --- Build entity list
    if entity_blocks:
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
    )


# ------------------------
# Deck + Heat-up mechanics
# ------------------------
def build_draw_pile(cfg: BehaviorConfig, rng: random.Random) -> list[str]:
    """Build a shuffled deck, deterministic for a given seed."""
    rule_func = DECK_SETUP_RULES.get(cfg.name.lower())
    if rule_func:
        return rule_func(cfg, rng)
    deck = cfg.deck[:]
    rng.shuffle(deck)
    return deck


def register_deck_rule(name: str):
    """Decorator for registering a special deck setup rule for a given boss name."""
    def decorator(func):
        DECK_SETUP_RULES[name.lower()] = func
        return func
    return decorator


def apply_special_rules(cfg, rng):
    """Apply any registered special rules to the boss’s deck setup."""
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


@register_deck_rule("gaping dragon")
def setup_gaping_dragon(cfg, rng):
    behaviors = cfg.behaviors

    # base deck: non-heatup behaviors
    base_deck   = [b for b, v in behaviors.items() if not v.get("heatup", False)]
    # heatup pool: all behaviors marked heatup
    heatup_pool = [b for b, v in behaviors.items() if v.get("heatup", False)]

    chosen_heatup = rng.choice(heatup_pool) if heatup_pool else None

    # include both Stomach Slam variants if present
    slam_cards = [b for b in behaviors.keys() if b.lower().startswith("stomach slam")]
    always_include = list(slam_cards)
    if chosen_heatup:
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


def apply_heatup(state: Dict[str, Any], cfg: BehaviorConfig, rng: random.Random, reason: str = "auto") -> None:
    """Add/replace heat-up cards when triggered."""
    if not cfg.heatup or not cfg.heatup.pool:
        return
    if cfg.heatup.manual_only and reason == "auto":
        return

    mode = cfg.heatup.mode
    picks = cfg.heatup.pool[:cfg.heatup.per_trigger]
    rng.shuffle(picks)

    if mode == "add_random":
        state["draw_pile"].extend(picks)
    elif mode == "add_specific":
        state["draw_pile"].extend(picks)
    elif mode == "replace":
        for i, card in enumerate(picks):
            if i < len(state["draw_pile"]):
                state["draw_pile"][i] = card
            else:
                state["draw_pile"].append(card)

    rng.shuffle(state["draw_pile"])


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
