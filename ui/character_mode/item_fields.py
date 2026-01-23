from typing import Any, Dict, List, Set


def _armor_dodge_int(item: Dict[str, Any]) -> int:
    return int(item.get("dodge_dice") or 0)


def _armor_upgrade_slots_int(item: Dict[str, Any]) -> int:
    return int(item.get("upgrade_slots") or 0)


def _armor_has_special_rules(item: Dict[str, Any]) -> bool:
    return ("text" in item) and bool(str(item.get("text") or "").strip())


def _immunities_set(item: Dict[str, Any]) -> Set[str]:
    imms = item.get("immunities") or []
    if isinstance(imms, str):
        imms = [imms]
    return {str(x).strip().lower() for x in imms if str(x).strip()}


def _hand_range_str(item: Dict[str, Any]) -> str:
    # ranges are stored as "0".."4" or "∞"
    v = item.get("range")
    return str(v) if v is not None else "0"


def _hand_upgrade_slots_int(item: Dict[str, Any]) -> int:
    return int(item.get("upgrade_slots") or 0)


def _hand_dodge_int(item: Dict[str, Any]) -> int:
    return int(item.get("dodge_dice") or 0)


def _hand_hands_required_int(item: Dict[str, Any]) -> int:
    return int(item.get("hands_required") or 1)
    

def _id(item: Dict[str, Any]) -> str:
    return str(item.get("id") or item.get("name") or "")


def _name(item: Dict[str, Any]) -> str:
    return str(item.get("name") or item.get("id") or "")


def _slot_cost(item: Dict[str, Any]) -> int:
    return int(item.get("slot_cost") or 1)


def _extra_upgrade_slots(item: Dict[str, Any]) -> int:
    # Legacy v1 field
    v1 = int(item.get("upgrade_slot_mod") or 0)

    # v2 canonical field: mods.meta.upgrade_slots
    v2 = 0
    mods = item.get("mods") or {}
    if isinstance(mods, dict):
        meta = mods.get("meta") or {}
        if isinstance(meta, dict):
            v2 = int(meta.get("upgrade_slots") or 0)

    return int(v1) + int(v2)


def _upgrade_slots(item: Dict[str, Any]) -> int:
    return int(item.get("upgrade_slots") or 0)


def _hands_required(item: Dict[str, Any]) -> int:
    return int(item.get("hands_required") or 1)


def _is_twohand_compatible_shield(item: Dict[str, Any]) -> bool:
    return (
        str(item.get("hand_category") or "").lower() == "shield"
        and bool(item.get("usable_with_two_hander"))
    )


def _item_expansions(item: Dict[str, Any]) -> Set[str]:
    src = item.get("source") or {}
    exps = src.get("expansion") or []
    if isinstance(exps, str):
        exps = [exps]
    return {str(x) for x in exps if x}


def _src_str(item: Dict[str, Any], field: str) -> str:
    src = item.get("source") or {}
    v = src.get(field)
    s = "" if v is None else str(v).strip()
    return s if s else "(none)"


def _is_legendary(item: Dict[str, Any]) -> bool:
    return bool(item.get("legendary"))


def _sorted_with_none_first(values: Set[str]) -> List[str]:
    vals = sorted(values)
    if "(none)" in vals:
        vals = ["(none)"] + [x for x in vals if x != "(none)"]
    return vals


def _item_requirements(item: Dict[str, Any]) -> Dict[str, int]:
    raw = item.get("requirements") or {}
    if not isinstance(raw, dict):
        return {}
    out = {"str": 0, "dex": 0, "itl": 0, "fth": 0}
    for k, v in raw.items():
        kk = str(k).strip().lower()
        if kk in ("strength",):
            kk = "str"
        elif kk in ("dexterity",):
            kk = "dex"
        elif kk in ("intelligence", "int"):
            kk = "itl"
        elif kk in ("faith",):
            kk = "fth"
        if kk not in out:
            continue
        out[kk] = int(v)
    return out


def _meets_requirements(stats: Dict[str, int], req: Dict[str, int]) -> bool:
    for k in ("str", "dex", "itl", "fth"):
        if int(stats.get(k, 0)) < int(req.get(k, 0)):
            return False
    return True