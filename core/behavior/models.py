# ui/behavior_decks_tab/models.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Entity:
    id: str
    label: str
    hp_max: int
    hp: int
    heatup_thresholds: List[int] = field(default_factory=list)
    crossed: List[int] = field(default_factory=list)


@dataclass
class BehaviorEntry:
    name: str  # "Artorias", "Silver Knight Swordsman"
    category: str  # "Regular Enemies", "Main Bosses", etc.
    path: Path  # Path to the JSON file
    tier: str  # "enemy" / "boss"
    is_invader: bool
    order_num: int = 10


@dataclass
class Heatup:
    mode: str  # "add_random" | "add_specific" | "replace"
    pool: List[str]  # image paths
    per_trigger: int = 1
    manual_only: bool = False


@dataclass
class BehaviorConfig:
    name: str
    tier: str
    entities: List[Entity]
    cards: int  # number of cards in the initial deck
    display_cards: List[str]  # always-visible cards (e.g. Data card)
    deck: List[str]  # initial draw pile
    raw: dict
    heatup: Optional[Heatup] = None
    behaviors: dict = field(default_factory=dict)
    is_invader: bool = False
    text: str = ""

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
        # --- Determine behaviors dict ---
        if "behavior" in raw:
            behaviors = {name: raw["behavior"]}
        else:
            behaviors = raw.get("behaviors")
            if behaviors is None:
                meta = {
                    "name",
                    "cards",
                    "tier",
                    "heatup",
                    "health",
                    "armor",
                    "resist",
                    "entities",
                    "always_display",
                    "is_invader",
                    "text",
                }

                def _is_entity_block(v: dict) -> bool:
                    if not isinstance(v, dict):
                        return False
                    keys = set(v.keys())
                    return (
                        "health" in keys
                        and "armor" in keys
                        and not any(x in keys for x in ("left", "middle", "right"))
                    )

                behaviors = {
                    k: v
                    for k, v in raw.items()
                    if isinstance(v, dict) and k not in meta and not _is_entity_block(v)
                }

        deck = list(behaviors.keys())

        # --- Build entities ---
        entities_raw = raw.get("entities")
        entities: list[Entity] = []
        if isinstance(entities_raw, list) and entities_raw:
            for ent in entities_raw:
                if isinstance(ent, dict):
                    hp_max = int(
                        ent.get("hp_max") or ent.get("hp") or raw.get("health", 1)
                    )
                    hp = int(ent.get("hp") or hp_max)
                    heatups = ent.get("heatup_thresholds") or (
                        [] if not ent.get("heatup") else [int(ent.get("heatup"))]
                    )
                    eid = ent.get("id") or str(ent.get("label", "")).lower().replace(
                        " ", "_"
                    )
                    label = ent.get("label") or eid
                    entities.append(
                        Entity(
                            id=eid,
                            label=label,
                            hp_max=hp_max,
                            hp=hp,
                            heatup_thresholds=heatups,
                            crossed=[],
                        )
                    )
        else:
            # Fallback: detect entity-like top-level blocks (e.g., Ornstein/Smough)
            entity_blocks = {
                k: v
                for k, v in raw.items()
                if isinstance(v, dict) and v.get("health") and v.get("armor")
            }
            if entity_blocks:
                for label, data in entity_blocks.items():
                    hp_val = int(data.get("health") or raw.get("health", 1))
                    heatup_val = data.get("heatup")
                    entities.append(
                        Entity(
                            id=str(label).lower().replace(" ", "_"),
                            label=label,
                            hp_max=hp_val,
                            hp=hp_val,
                            heatup_thresholds=[int(heatup_val)]
                            if isinstance(heatup_val, int)
                            else [],
                            crossed=[],
                        )
                    )
            else:
                # Single entity
                hp_val = int(raw.get("health", 1))
                heatup_val = (
                    raw.get("heatup") if isinstance(raw.get("heatup"), int) else None
                )
                entities.append(
                    Entity(
                        id=name.lower().replace(" ", "_"),
                        label=name,
                        hp_max=hp_val,
                        hp=hp_val,
                        heatup_thresholds=[heatup_val] if heatup_val else [],
                        crossed=[],
                    )
                )

        # --- Display cards ---
        display_cards = [f"{name} - data.jpg"]

        # --- Determine cards and heatup pool ---
        cards = int(raw.get("cards", len(deck)))

        heatup = None
        heatup_pool = [
            k
            for k, v in behaviors.items()
            if isinstance(v, dict) and v.get("heatup", False)
        ]
        if heatup_pool:
            heatup = Heatup(
                mode="add_random",
                pool=heatup_pool,
                per_trigger=1,
                manual_only=(raw.get("heatup") is None),
            )

        return cls(
            name=name,
            tier=("enemy" if "behavior" in raw else tier),
            entities=entities,
            cards=cards,
            display_cards=display_cards,
            deck=deck,
            raw=raw,
            heatup=heatup,
            behaviors=behaviors,
            is_invader=bool(raw.get("is_invader", False)),
            text=str(raw.get("text", "")),
        )
