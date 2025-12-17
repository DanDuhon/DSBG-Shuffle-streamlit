from typing import Any, Dict, List, Set
from ui.character_mode.constants import DICE_ICON
from ui.character_mode.dice_math import _dice_count, _roll_min_max_avg, _sum_rolls
from ui.character_mode.item_fields import _id, _name


def _attack_int(atk: Dict[str, Any], k: str, default: int = 0) -> int:
    try:
        return int((atk or {}).get(k) or default)
    except Exception:
        return default


def _attack_bool(atk: Dict[str, Any], k: str) -> bool:
    return bool((atk or {}).get(k))


def _attack_str(atk: Dict[str, Any], k: str) -> str:
    v = (atk or {}).get(k)
    s = "" if v is None else str(v).strip()
    return s


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


def _attack_dice_string(atk: Dict[str, Any]) -> str:
    c = _attack_dice_counts(atk)
    s = (DICE_ICON["black"] * c["black"]) + (DICE_ICON["blue"] * c["blue"]) + (DICE_ICON["orange"] * c["orange"])
    flat = _attack_flat_mod(atk)
    if flat:
        s = f"{s} {'+' if flat > 0 else ''}{flat}"
    return s


def _attack_min_max_avg(atk: Dict[str, Any]) -> tuple[int, int, float]:
    c = _attack_dice_counts(atk)
    parts = [
        _roll_min_max_avg("black", c["black"]),
        _roll_min_max_avg("blue", c["blue"]),
        _roll_min_max_avg("orange", c["orange"]),
    ]
    mn, mx, avg = _sum_rolls(parts)
    flat = _attack_flat_mod(atk)
    return (mn + flat, mx + flat, avg + float(flat))


def _attack_range(it: Dict[str, Any], atk: Dict[str, Any]) -> str:
    r = (atk or {}).get("range")
    if r is None or str(r).strip() == "":
        r = it.get("range")
    return str(r) if r is not None else ""


def _attack_has_dice(atk: Dict[str, Any]) -> bool:
    d = atk.get("dice") or {}
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        try:
            if int(v) != 0:
                return True
        except Exception:
            # non-numeric but present counts as dice
            return True
    return False


def _rows_for_attacks_table(items: List[Dict[str, Any]], selected_item_ids: Set[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for it in items:
        iid = _id(it)
        name = _name(it)
        atks = it.get("attacks") or []
        if not isinstance(atks, list):
            continue
        for idx, atk in enumerate(atks):
            atk = atk or {}
            mn, mx, avg = _attack_min_max_avg(atk)
            rows.append(
                {
                    "RowId": f"{iid}::atk::{idx}",
                    "Select": iid in selected_item_ids,
                    "Item": name,
                    "Atk#": idx + 1,
                    "Stam": _attack_int(atk, "stamina", 0),
                    "Dice": _attack_dice_string(atk),
                    "Heal": _attack_int(atk, "heal", 0),
                    "StamRec": _attack_int(atk, "stamina_recovery", 0),
                    "Cond": _attack_str(atk, "condition"),
                    "Text": _attack_str(atk, "text"),
                    "Magic": _attack_bool(atk, "magic") or _attack_bool(it, "magic"),
                    "Shift Before": _attack_int(atk, "shift_before", 0),
                    "Shift After": _attack_int(atk, "shift_after", 0),
                    "Node": _attack_bool(atk, "node_attack") or _attack_bool(it, "node_attack"),
                    "Push": _attack_int(atk, "push", 0),
                    "Range": _attack_range(it, atk),
                    "Shaft": _attack_bool(atk, "shaft") or _attack_bool(it, "shaft"),
                    "Repeat": "" if _attack_int(atk, "repeat", 0) == 0 else _attack_int(atk, "repeat", 0),
                    "Min": mn,
                    "Max": mx,
                    "Avg": round(avg, 2),
                    "Avg/Stam": "" if _attack_int(atk, "stamina", 0) == 0 else round(avg/_attack_int(atk, "stamina", 0),2)
                }
            )
    return rows