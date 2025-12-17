from typing import Any, Dict, Set


TIERS = ["Base", "Tier 1", "Tier 2", "Tier 3"]
STAT_KEYS = ("str", "dex", "itl", "fth")
STAT_LABEL = {"str": "STR", "dex": "DEX", "itl": "INT", "fth": "FAI"}
HAND_FEATURE_OPTIONS = [
    "magic",
    "node_attack",
    "push",
    "shaft",
    "shift_before",
    "shift_after",
    "repeat",
    "stamina_recovery",
    "heal",
]
HAND_CONDITION_OPTIONS = ["bleed", "poison", "frostbite", "stagger"]

CLASS_TIERS: Dict[str, Dict[str, Any]] = {
    "Assassin": {
        "expansions": {"Dark Souls The Board Game"},
        "str": [10, 16, 25, 34],
        "dex": [14, 22, 31, 40],
        "itl": [11, 18, 27, 36],
        "fth": [9, 14, 22, 30],
    },
    "Cleric": {
        "expansions": {"Tomb of Giants", "Characters Expansion"},
        "str": [12, 18, 27, 37],
        "dex": [8, 15, 24, 33],
        "itl": [7, 14, 22, 30],
        "fth": [16, 23, 32, 40],
    },
    "Deprived": {
        "expansions": {"Tomb of Giants", "Characters Expansion"},
        "str": [10, 20, 30, 40],
        "dex": [10, 20, 30, 40],
        "itl": [10, 20, 30, 40],
        "fth": [10, 20, 30, 40],
    },
    "Herald": {
        "expansions": {"Dark Souls The Board Game", "The Sunless City"},
        "str": [12, 19, 28, 37],
        "dex": [11, 17, 26, 34],
        "itl": [8, 12, 20, 29],
        "fth": [13, 22, 31, 40],
    },
    "Knight": {
        "expansions": {"Dark Souls The Board Game"},
        "str": [13, 21, 30, 40],
        "dex": [12, 19, 29, 38],
        "itl": [9, 15, 23, 31],
        "fth": [9, 15, 23, 31],
    },
    "Mercenary": {
        "expansions": {"Painted World of Ariamis", "Characters Expansion"},
        "str": [10, 17, 26, 35],
        "dex": [16, 22, 32, 40],
        "itl": [10, 17, 26, 35],
        "fth": [8, 14, 21, 30],
    },
    "Pyromancer": {
        "expansions": {"Tomb of Giants", "Characters Expansion", "The Sunless City"},
        "str": [12, 17, 26, 35],
        "dex": [9, 13, 20, 27],
        "itl": [14, 21, 31, 40],
        "fth": [14, 19, 28, 38],
    },
    "Sorcerer": {
        "expansions": {"Painted World of Ariamis", "Characters Expansion"},
        "str": [7, 14, 22, 31],
        "dex": [12, 18, 27, 36],
        "itl": [16, 23, 32, 40],
        "fth": [7, 15, 24, 33],
    },
    "Thief": {
        "expansions": {"Tomb of Giants", "Characters Expansion"},
        "str": [9, 16, 24, 33],
        "dex": [13, 21, 31, 40],
        "itl": [10, 18, 27, 36],
        "fth": [8, 15, 23, 31],
    },
    "Warrior": {
        "expansions": {"Dark Souls The Board Game", "The Sunless City"},
        "str": [16, 23, 32, 40],
        "dex": [9, 16, 25, 35],
        "itl": [8, 15, 23, 30],
        "fth": [9, 16, 25, 35],
    },
}

CLASS_NAMES: Set[str] = set(CLASS_TIERS.keys())

DIE_FACES = {
    "black":  [0, 1, 1, 1, 2, 2],
    "blue":   [1, 1, 2, 2, 2, 3],
    "orange": [1, 2, 2, 3, 3, 4],
    "dodge":  [0, 0, 0, 1, 1, 1],
}

DIE_STATS = {}
for k, faces in DIE_FACES.items():
    DIE_STATS[k] = {
        "min": min(faces),
        "max": max(faces),
        "avg": sum(faces) / len(faces),
    }

DICE_ICON = {
    "black": "⬛",
    "blue": "🟦",
    "orange": "🟧",
    "dodge": "🟩",
}
