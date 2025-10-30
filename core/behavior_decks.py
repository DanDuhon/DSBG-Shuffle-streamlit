# core/behavior_decks.py
from __future__ import annotations
import json, random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

ASSETS_DIR = Path("assets") / "behavior cards"
DATA_DIR = Path("data") / "behaviors"

@dataclass
class Entity:
    id: str
    label: str
    hp_max: int
    hp: int
    heatup_thresholds: List[int] = field(default_factory=list)
    crossed: List[int] = field(default_factory=list)  # thresholds already crossed

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
    display_cards: List[str]        # up to 4 auxiliary cards to show (data/move/attack/always on)
    deck: List[str]                 # initial draw pile source before shuffle
    heatup: Optional[Heatup] = None

def _path(img_rel: str) -> str:
    # helper to resolve "behavior cards/Whatever.jpg" under assets
    return str(Path("assets") / img_rel)

def list_behavior_files() -> List[Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.json"))

def load_behavior(fname: Path) -> BehaviorConfig:
    with open(fname, "r", encoding="utf-8") as f:
        raw = json.load(f)

    entities = [
        Entity(
            id=e["id"],
            label=e.get("label", e["id"]),
            hp_max=int(e["hp"]),
            hp=int(e["hp"]),
            heatup_thresholds=sorted(map(int, e.get("heatup_thresholds", [])), reverse=True),
            crossed=[]
        )
        for e in raw.get("entities", [])
    ]

    display_cards = [_path(dc["image"]) for dc in raw.get("display_cards", [])]

    # Expand the deck with copies
    deck = []
    for item in raw.get("deck", []):
        img = _path(item["image"])
        copies = int(item.get("copies", 1))
        deck.extend([img] * copies)

    heatup = None
    if "heatup" in raw:
        h = raw["heatup"]
        heatup = Heatup(
            mode=h.get("mode", "add_random"),
            pool=[_path(x["image"]) for x in h.get("pool", []) for _ in range(int(x.get("copies", 1)))],
            per_trigger=int(h.get("per_trigger", 1)),
            manual_only=bool(h.get("manual_only", False)),
        )

    return BehaviorConfig(
        name=raw["name"],
        tier=raw.get("tier", "main_boss"),
        entities=entities,
        display_cards=display_cards[:4],
        deck=deck,
        heatup=heatup
    )

def build_draw_pile(cfg: BehaviorConfig, rng: random.Random) -> List[str]:
    pile = cfg.deck[:]
    rng.shuffle(pile)
    return pile

def apply_heatup(state: Dict[str, Any], cfg: BehaviorConfig, rng: random.Random, reason: str = "auto") -> None:
    """Modify draw_pile/discard_pile per cfg.heatup, in place."""
    if not cfg.heatup or not cfg.heatup.pool:
        return
    if cfg.heatup.manual_only and reason == "auto":
        return

    mode = cfg.heatup.mode
    per_n = cfg.heatup.per_trigger
    pool_copy = cfg.heatup.pool[:]
    rng.shuffle(pool_copy)

    if mode == "add_random":
        # Take N random from pool and add to draw pile bottom (or shuffle in)
        picks = pool_copy[:per_n]
        state["draw_pile"].extend(picks)

    elif mode == "add_specific":
        # deterministic first N (after shuffle above, still "randomized")
        picks = pool_copy[:per_n]
        state["draw_pile"].extend(picks)

    elif mode == "replace":
        # replace top N of draw pile (if fewer, replace what exists)
        picks = pool_copy[:per_n]
        for i, card in enumerate(picks):
            if i < len(state["draw_pile"]):
                state["draw_pile"][i] = card
            else:
                state["draw_pile"].append(card)

    # optional: reshuffle the draw pile slightly to avoid predictability
    rng.shuffle(state["draw_pile"])

def check_and_trigger_heatup(prev_hp: int, new_hp: int, ent: Entity, state: Dict[str, Any],
                             cfg: BehaviorConfig, rng: random.Random) -> List[int]:
    """Return thresholds crossed this update and mutate state via apply_heatup."""
    crossed_now = []
    for th in ent.heatup_thresholds:
        if th in ent.crossed:
            continue
        # threshold is 'when HP <= th'
        if prev_hp > th >= new_hp:
            crossed_now.append(th)

    for th in crossed_now:
        ent.crossed.append(th)
        apply_heatup(state, cfg, rng, reason="auto")
    return crossed_now

def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    # keep it JSON-safe
    return {
        "selected_file": state.get("selected_file"),
        "seed": state.get("seed", 0),
        "draw_pile": state.get("draw_pile", []),
        "discard_pile": state.get("discard_pile", []),
        "display_cards": state.get("display_cards", []),
        "entities": [
            {
                "id": e["id"],
                "label": e["label"],
                "hp": e["hp"],
                "hp_max": e["hp_max"],
                "heatup_thresholds": e.get("heatup_thresholds", []),
                "crossed": e.get("crossed", []),
            } for e in state.get("entities", [])
        ]
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
