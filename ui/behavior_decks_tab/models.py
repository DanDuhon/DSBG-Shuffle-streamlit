#ui/behavior_decks_tab/models.py
import os
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
    name: str           # "Artorias", "Silver Knight Swordsman"
    category: str       # "Regular Enemies", "Main Bosses", etc.
    path: Path          # Path to the JSON file
    tier: str           # "enemy" / "boss"
    is_invader: bool
    order_num: int = 10


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