from __future__ import annotations
import json, random
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


# ------------------------
# Helpers
# ------------------------
def _path(img_rel: str) -> str:
    return str(Path("assets") / "behavior cards" / img_rel)


def list_behavior_files() -> List[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.json"))


# ------------------------
# JSON Importer
# ------------------------
def load_behavior(fname: Path) -> BehaviorConfig:
    """Parse your JSON format (regular enemy or boss)."""
    with open(fname, "r", encoding="utf-8") as f:
        raw = json.load(f)

    name = fname.stem
    hp = int(raw.get("health", 1))
    heatup_threshold = raw.get("heatup", None) if isinstance(raw.get("heatup"), int) else None

    # --- Entity setup
    entities = [
        Entity(
            id=name.lower().replace(" ", "_"),
            label=name,
            hp_max=hp,
            hp=hp,
            heatup_thresholds=[heatup_threshold] if heatup_threshold else [],
            crossed=[]
        )
    ]

    # --- Display cards (always-visible data card)
    display_cards = []
    data_card_path = _path(f"{name} - data.jpg")
    if Path(data_card_path).exists():
        display_cards.append(data_card_path)

    # --- Deck + Heat-up pool
    deck = []
    heatup_pool = []

    for key, val in raw.items():
        if key in ("health", "armor", "resist", "heatup"):
            continue
        if not isinstance(val, dict):
            continue  # skip anything unexpected

        img_path = _path(f"{name} - {key}.jpg")

        if "heatup" not in val:
            # Regular card
            deck.append(img_path)
        else:
            # Heat-up-only card
            heatup_pool.append(img_path)

    # --- Heatup config
    heatup = None
    if heatup_pool:
        heatup = Heatup(
            mode="add_random",   # default; can expand later
            pool=heatup_pool,
            per_trigger=1,
            manual_only=(heatup_threshold is None)
        )

    return BehaviorConfig(
        name=name,
        tier="enemy" if "behavior" in raw else "boss",
        entities=entities,
        display_cards=display_cards,
        cards=raw.get("cards"),
        deck=deck,
        heatup=heatup,
        raw=raw
    )


# ------------------------
# Deck + Heat-up mechanics
# ------------------------
def build_draw_pile(cfg: BehaviorConfig, rng: random.Random) -> list[str]:
    """Build a shuffled pile, respecting any special boss-specific setup rules."""
    # Step 1: Start with normal deck
    base_deck = cfg.deck[:]

    # Step 2: Apply any special rules
    final_deck = apply_special_rules(cfg, rng)

    # Step 3: Shuffle
    rng.shuffle(final_deck)
    return final_deck


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
    """
    Gaping Dragon:
      - Always includes *both* "Stomach Slam" cards (two copies exist).
      - Always includes one random Heat-Up card.
    """

    # Start with all normal behaviors (non-heatup)
    base_deck = [b for b in cfg.deck if not cfg.behaviors[b].get("heatup", False)]

    # Get all heat-up behaviors (marked in JSON)
    heatup_cards = [b for b in cfg.deck if cfg.behaviors[b].get("heatup", False)]

    # Randomly include one heat-up card (if available)
    chosen_heatup = rng.choice(heatup_cards) if heatup_cards else None

    # Always include both "Stomach Slam" cards.
    # If your JSON only has one "Stomach Slam" entry, we’ll just duplicate it manually.
    always_include = ["Stomach Slam", "Stomach Slam"]
    if chosen_heatup:
        always_include.append(chosen_heatup)

    # Enforce deck size limit
    limit = cfg.raw.get("cards", len(cfg.deck))

    # Use the helper to normalize and shuffle
    deck = force_include(
        base_deck,
        include=always_include,
        exclude=[],
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
        "seed": state.get("seed", 0),
        "draw_pile": state.get("draw_pile", []),
        "discard_pile": state.get("discard_pile", []),
        "current_card": state.get("current_card"),
        "display_cards": state.get("display_cards", []),
        "entities": state.get("entities", [])
    }


def state_from_cfg(cfg: BehaviorConfig, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    draw = build_draw_pile(cfg, rng)
    return {
        "selected_file": None,
        "seed": seed,
        "draw_pile": draw,
        "discard_pile": [],
        "current_card": None,
        "display_cards": cfg.display_cards[:],
        "entities": [
            {
                "id": e.id,
                "label": e.label,
                "hp": e.hp,
                "hp_max": e.hp_max,
                "heatup_thresholds": e.heatup_thresholds[:],
                "crossed": [],
            } for e in cfg.entities
        ]
    }
