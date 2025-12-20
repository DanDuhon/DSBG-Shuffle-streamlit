from typing import Any, Dict, List

from ui.character_mode.dice_math import _dice_icons, _dodge_icons
from ui.character_mode.item_fields import (
    _armor_upgrade_slots_int,
    _hand_hands_required_int,
    _hand_range_str,
    _hand_upgrade_slots_int,
    _item_expansions,
    _item_requirements,
    _name,
)


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
        block = it.get("block_dice") or {}
        resist = it.get("resist_dice") or {}
        rows.append(
            {
                "Name": _name(it),
                "Category": str(it.get("hand_category") or it.get("item_type") or ""),
                "Hands": _hand_hands_required_int(it),
                "Range": _hand_range_str(it),
                "Block": _dice_icons(block),
                "Resist": _dice_icons(resist),
                "Dodge": _dodge_icons(int(it.get("dodge_dice") or 0)),
                "Upg Slots": _hand_upgrade_slots_int(it),
                "Text": str(it.get("text") or ""),
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "INT": req.get("itl", 0),
                "FAI": req.get("fth", 0),
                "Legendary": bool(it.get("legendary") or False),
                "Expansions": ", ".join(_item_expansions(it)),
                "Source Type": str(src.get("type") or ""),
                "Source Entity": str(src.get("entity") or ""),
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

        rows.append(
            {
                "Name": _name(it),
                "Block": _dice_icons(block),
                "Resist": _dice_icons(resist),
                "Dodge": _dodge_icons(dodge_n),
                "Upg Slots": _armor_upgrade_slots_int(it),
                "Text": str(it.get("text") or ""),
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "INT": req.get("itl", 0),
                "FAI": req.get("fth", 0),
                "Legendary": bool(it.get("legendary") or False),
                "Expansions": ", ".join(_item_expansions(it)),
                "Source Type": str(src.get("type") or ""),
                "Source Entity": str(src.get("entity") or ""),
            }
        )
    return rows