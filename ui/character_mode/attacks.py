from typing import Any, Dict, List, Set

from ui.character_mode.constants import DICE_ICON
from ui.character_mode.dice_math import _dice_count
from ui.character_mode.item_fields import _id, _name


def _attack_int(atk: Dict[str, Any], k: str, default: int = 0) -> int:
    return int((atk or {}).get(k) or default)


def _attack_dice_counts(atk: Dict[str, Any]) -> Dict[str, int]:
    d = (atk or {}).get("dice") or {}
    if not isinstance(d, dict):
        return {"black": 0, "blue": 0, "orange": 0}
    return {
        "black": _dice_count(d, "black"),
        "blue": _dice_count(d, "blue"),
        "orange": _dice_count(d, "orange"),
    }


def _attack_flat_mod(atk: Dict[str, Any]) -> int:
    return _attack_int(atk, "flat_mod", 0)


def _attack_has_dice(atk: Dict[str, Any]) -> bool:
    d = atk.get("dice") or {}
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        if int(v) != 0:
            return True
    return False
