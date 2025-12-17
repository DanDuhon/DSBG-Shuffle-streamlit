from typing import Any, Dict, List
from ui.character_mode.item_fields import _item_requirements, _item_expansions, _name, _hand_hands_required_int, _hand_range_str, _hand_upgrade_slots_int, _armor_upgrade_slots_int
from ui.character_mode.dice_math import _dodge_icons, _roll_min_max_avg, _dice_count, _sum_rolls, _flat_mod, _dice_icons


def _rows_for_table(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for it in items:
        req = _item_requirements(it)
        src = it.get("source") or {}
        rows.append(
            {
                "Name": it.get("name") or it.get("id"),
                "Type": it.get("item_type") or it.get("hand_category") or "",
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "INT": req.get("itl", 0),
                "FAI": req.get("fth", 0),
                "Expansions": ", ".join(_item_expansions(it)),
                "Source Type": src.get("type") or "",
                "Source Entity": src.get("entity") or "",
            }
        )
    return rows


def _rows_for_hand_table(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for it in items:
        req = _item_requirements(it)
        src = it.get("source") or {}
        rows.append(
            {
                "Name": _name(it),
                "Category": str(it.get("hand_category") or it.get("item_type") or ""),
                "Hands": _hand_hands_required_int(it),
                "Range": _hand_range_str(it),
                "Upg Slots": _hand_upgrade_slots_int(it),
                "Dodge": _dodge_icons(int(it.get("dodge_dice") or 0)),
                "Text": str(it.get("text") or ""),
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "INT": req.get("itl", 0),
                "FAI": req.get("fth", 0),
                "Legendary": bool(it.get("legendary") or False),
                "Expansions": ", ".join(_item_expansions(it)),
                "SourceType": str(src.get("type") or ""),
                "SourceEntity": str(src.get("entity") or ""),
            }
        )
    return rows


def _rows_for_armor_table(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for it in items:
        req = _item_requirements(it)
        src = it.get("source") or {}

        block = it.get("block_dice") or {}
        resist = it.get("resist_dice") or {}
        dodge_n = 0
        try:
            dodge_n = int(it.get("dodge_dice") or 0)
        except Exception:
            dodge_n = 0

        b_blk = _roll_min_max_avg("black", _dice_count(block, "black"))
        b_blu = _roll_min_max_avg("blue", _dice_count(block, "blue"))
        b_org = _roll_min_max_avg("orange", _dice_count(block, "orange"))
        block_total = _sum_rolls([b_blk, b_blu, b_org])
        block_flat = _flat_mod(block)
        block_total = (block_total[0] + block_flat, block_total[1] + block_flat, block_total[2] + block_flat)

        r_blk = _roll_min_max_avg("black", _dice_count(resist, "black"))
        r_blu = _roll_min_max_avg("blue", _dice_count(resist, "blue"))
        r_org = _roll_min_max_avg("orange", _dice_count(resist, "orange"))
        resist_total = _sum_rolls([r_blk, r_blu, r_org])
        resist_flat = _flat_mod(resist)
        resist_total = (resist_total[0] + resist_flat, resist_total[1] + resist_flat, resist_total[2] + resist_flat)

        rows.append(
            {
                "Name": _name(it),
                "Block": _dice_icons(block),
                "Resist": _dice_icons(resist),
                "Dodge": _dodge_icons(dodge_n),
                "Block Min": block_total[0],
                "Block Max": block_total[1],
                "Block Avg": round(float(block_total[2]), 2),
                "Resist Min": resist_total[0],
                "Resist Max": resist_total[1],
                "Resist Avg": round(float(resist_total[2]), 2),
                "Upg Slots": _armor_upgrade_slots_int(it),
                "Text": str(it.get("text") or ""),
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "INT": req.get("itl", 0),
                "FAI": req.get("fth", 0),
                "Legendary": bool(it.get("legendary") or False),
                "Expansions": ", ".join(_item_expansions(it)),
                "SourceType": str(src.get("type") or ""),
                "SourceEntity": str(src.get("entity") or ""),
            }
        )
    return rows