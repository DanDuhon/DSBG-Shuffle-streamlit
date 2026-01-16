#core/ngplus/logic.py
import math
from copy import deepcopy
from typing import Any, Dict, Optional

import streamlit as st

MAX_NGPLUS_LEVEL = 5

# NG+ HP scaling (relative to base HP):
#  - Base HP 1-3: +1 HP per NG+ level
#  - Base HP 4-7: bonuses by level: 0,2,3,5,6,8
#  - Base HP 8-10: +2 HP per NG+ level
#  - Base HP >10: +10% HP per NG+ level (rounded up)
_HP_4_TO_7_BONUS = {
    0: 0,
    1: 2,
    2: 3,
    3: 5,
    4: 6,
    5: 8,
}


def get_current_ngplus_level() -> int:
    """
    Return the currently selected NG+ level from Streamlit state.
    Defaults to 0 (base game).
    """
    level = int(st.session_state.get("ngplus_level", 0))
    return max(0, min(MAX_NGPLUS_LEVEL, level))


def damage_for_level(base_damage: Optional[int], level: int) -> Optional[int]:
    if base_damage is None:
        return None
    return int(base_damage) + max(0, level)


def dodge_bonus_for_level(level: int) -> int:
    """
    NG+ dodge rules:
      - NG+0-1: +0
      - NG+2-3: +1
      - NG+4-5: +2
    """
    if level <= 1:
        return 0
    if 2 <= level <= 3:
        return 1
    return 2


def dodge_for_level(base_dodge: Optional[int], level: int) -> Optional[int]:
    if base_dodge is None:
        return None
    return int(base_dodge) + dodge_bonus_for_level(level)


def _apply_to_card_dict(card: Dict[str, Any], level: int) -> Dict[str, Any]:
    """
    Apply NG+ to a single behavior card.

    Handles:
      - card["dodge"]
      - card["left"/"middle"/"right"]["damage"]
    """
    card = deepcopy(card)

    # Dodge difficulty
    if "dodge" in card and isinstance(card["dodge"], (int, float)):
        card["dodge"] = dodge_for_level(int(card["dodge"]), level)

    # Damage in left/middle/right regions
    for side in ("left", "middle", "right"):
        region = card.get(side)
        if (
            isinstance(region, dict)
            and "damage" in region
            and isinstance(region["damage"], (int, float))
        ):
            region = deepcopy(region)
            region["damage"] = damage_for_level(int(region["damage"]), level)
            card[side] = region
        
        # Also scale numeric push values on the region (some move-attacks
        # encode their push as a numeric `push` field). Preserve boolean
        # `push` flags (they indicate presence rather than amount).
        if isinstance(region, dict) and "push" in region and isinstance(region["push"], (int, float)):
            region = deepcopy(region)
            region["push"] = damage_for_level(int(region["push"]), level)
            card[side] = region

    return card



def apply_ngplus_to_raw(
    raw_cfg: Dict[str, Any], level: Optional[int] = None, enemy_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Return a NG+-adjusted copy of the raw behavior config dict.

    Works with:
      - Regular enemies that have a single card under raw_cfg["behavior"]
      - Bosses/invaders with multiple named behavior cards at the top level
        (like Armorer Dennis, whose JSON has named keys for each card)
    """
    if level is None:
        level = get_current_ngplus_level()
    level = max(0, min(MAX_NGPLUS_LEVEL, int(level)))
    if level == 0:
        # Return a copy so callers can safely mutate
        return deepcopy(raw_cfg)

    raw = deepcopy(raw_cfg)

    # Health on the data card
    base_hp = raw.get("health") if isinstance(raw.get("health"), (int, float)) else None
    hp_bonus = 0
    if base_hp is not None:
        base_hp = int(base_hp)
        hp_bonus = health_bonus_for_level(base_hp, level)
        raw["health"] = base_hp + hp_bonus

    if "heatup" in raw and isinstance(raw["heatup"], (int, float)):
        if enemy_name == "Vordt of the Boreal Valley":
            raw["heatup1"] = int(raw["heatup1"]) + hp_bonus
            raw["heatup2"] = int(raw["heatup2"]) + hp_bonus
        if not enemy_name in {"Old Dragonslayer", "The Four Kings", "Executioner's Chariot"}:
            raw["heatup"] = int(raw["heatup"]) + hp_bonus

    # ----- Paladin Leeroy special rule text -----
    # Only relevant for NG+ levels (>0); X = 2 + HP bonus from NG+.
    if enemy_name == "Paladin Leeroy":
        x = 2 + max(0, hp_bonus)
        raw["text"] = (
            "The first time Leeroy's health would be\n"
            f"reduced to 0, set his health to {x} instead."
        )

    # Single-card enemies (e.g. Alonne Bow Knight)
    if "behavior" in raw and isinstance(raw["behavior"], dict):
        raw["behavior"] = _apply_to_card_dict(raw["behavior"], level)
        return raw

    # Multi-card bosses/invaders (e.g. Armorer Dennis):
    # top-level keys that look like behavior cards have a "middle" dict.
    for key, value in list(raw.items()):
        if isinstance(value, dict) and "middle" in value:
            raw[key] = _apply_to_card_dict(value, level)

    return raw


def health_for_level(base_hp: Optional[int], level: int) -> Optional[int]:
    if base_hp is None:
        return None
    base_hp = int(base_hp)
    level = max(0, min(MAX_NGPLUS_LEVEL, level))
    if level == 0:
        return base_hp

    # 1-3 → +1 per level
    if 1 <= base_hp <= 3:
        return base_hp + level

    # 4-7 → lookup table
    if 4 <= base_hp <= 7:
        bonus = _HP_4_TO_7_BONUS.get(level, _HP_4_TO_7_BONUS[max(_HP_4_TO_7_BONUS)])
        return base_hp + bonus

    # 8-10 → +2 per level
    if 8 <= base_hp <= 10:
        return base_hp + 2 * level

    # >10 → +10% per level, rounded up
    if base_hp > 10:
        factor = 1.0 + 0.10 * level
        return int(math.ceil(base_hp * factor))
    

def health_bonus_for_level(base_hp: Optional[int], level: int) -> int:
    """
    Convenience helper used for:
      - heat-up trigger scaling
      - Paladin Leeroy's 'set health to X' rule
    """
    if base_hp is None:
        return 0
    base_hp = int(base_hp)
    hp_ng = health_for_level(base_hp, level)
    if hp_ng is None:
        return 0
    return int(hp_ng) - base_hp


def dodge_bonus_for_level(level: int) -> int:
    """
    NG+ dodge rules:
      - NG+0-1: +0
      - NG+2-3: +1
      - NG+4-5: +2
    """
    if level <= 1:
        return 0
    if 2 <= level <= 3:
        return 1
    return 2