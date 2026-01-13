from typing import Set

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
    "ignore_block",
]
HAND_CONDITION_OPTIONS = ["bleed", "poison", "frostbite", "stagger"]

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
