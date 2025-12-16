# ui/character_mode/render.py
from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable

import streamlit as st

TIERS = ["Base", "Tier 1", "Tier 2", "Tier 3"]
STAT_KEYS = ("str", "dex", "itl", "fth")
STAT_LABEL = {"str": "STR", "dex": "DEX", "itl": "INT", "fth": "FAI"}
HAND_FEATURE_OPTIONS = [
    "magic",
    "node_attack",
    "push",
    "shaft",
    "shift",
    "repeat",
    "stamina_recovery",
    "heal",
]
HAND_CONDITION_OPTIONS = ["bleed", "poison", "frostbite", "stagger"]

# Stats are the first number in each LookupTable tier entry.
# Stored as tiered stat arrays: [Base, T1, T2, T3]
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

# Icons chosen to stay visible in light/dark themes:
# black uses an outlined glyph rather than a pure black square.
DICE_ICON = {
    "black": "⬛",
    "blue": "🟦",
    "orange": "🟧",
    "dodge": "🟩",
}


def _dice_count(d: Dict[str, Any], key: str) -> int:
    try:
        return int((d or {}).get(key) or 0)
    except Exception:
        return 0
    

def _flat_mod(d: Dict[str, Any]) -> int:
    try:
        return int((d or {}).get("flat_mod") or 0)
    except Exception:
        return 0


def _sum_rolls(parts: list[tuple[int, int, float]]) -> tuple[int, int, float]:
    mn = sum(p[0] for p in parts)
    mx = sum(p[1] for p in parts)
    avg = sum(p[2] for p in parts)
    return mn, mx, avg


def _roll_min_max_avg(die: str, n: int) -> tuple[int, int, float]:
    if n <= 0:
        return (0, 0, 0.0)
    s = DIE_STATS[die]
    return (s["min"] * n, s["max"] * n, s["avg"] * n)

def _fmt_roll(mn: int, mx: int, avg: float) -> str:
    return f"{mn}–{mx} ({avg:.2f})"

def _dice_icons(block_or_resist: Dict[str, Any]) -> str:
    b = _dice_count(block_or_resist, "black")
    u = _dice_count(block_or_resist, "blue")
    o = _dice_count(block_or_resist, "orange")
    parts = []
    if b: parts.append(DICE_ICON["black"] * b)
    if u: parts.append(DICE_ICON["blue"] * u)
    if o: parts.append(DICE_ICON["orange"] * o)
    return "".join(parts)

def _dodge_icons(n: int) -> str:
    return DICE_ICON["dodge"] * max(int(n or 0), 0)



def _armor_dodge_int(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("dodge_dice") or 0)
    except Exception:
        return 0

def _armor_upgrade_slots_int(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("upgrade_slots") or 0)
    except Exception:
        return 0

def _armor_has_special_rules(item: Dict[str, Any]) -> bool:
    return ("text" in item) and bool(str(item.get("text") or "").strip())

def _apply_armor_filters(
    items: List[Dict[str, Any]],
    *,
    dodge_dice: Optional[Set[int]],
    upgrade_slots: Optional[Set[int]],
    any_immunities: Set[str],     # OR semantics
    special_rules_mode: str,      # Any | Has special rules | No special rules
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        if dodge_dice is not None and _armor_dodge_int(it) not in dodge_dice:
            continue

        if upgrade_slots is not None and _armor_upgrade_slots_int(it) not in upgrade_slots:
            continue

        if any_immunities:
            if _immunities_set(it).isdisjoint(any_immunities):
                continue

        has_rules = _armor_has_special_rules(it)
        if special_rules_mode == "Has special rules" and not has_rules:
            continue
        if special_rules_mode == "No special rules" and has_rules:
            continue

        out.append(it)
    return out


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
    try:
        return int(item.get("upgrade_slots") or 0)
    except Exception:
        return 0


def _hand_hands_required_int(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("hands_required") or 1)
    except Exception:
        return 1


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


def _hand_has_attacks_with_dice(item: Dict[str, Any]) -> bool:
    atks = item.get("attacks") or []
    if not isinstance(atks, list) or not atks:
        return False
    return any(_attack_has_dice(a or {}) for a in atks)


def _hand_any_attack_pred(item: Dict[str, Any], pred) -> bool:
    for atk in (item.get("attacks") or []):
        try:
            if pred(atk):
                return True
        except Exception:
            continue
    return False


def _hand_has_magic(item: Dict[str, Any]) -> bool:
    if bool(item.get("magic")):
        return True
    return _hand_any_attack_pred(item, lambda a: bool(a.get("magic")))


def _hand_has_node_attack(item: Dict[str, Any]) -> bool:
    if bool(item.get("node_attack")):
        return True
    return _hand_any_attack_pred(item, lambda a: bool(a.get("node_attack")))


def _hand_has_push(item: Dict[str, Any]) -> bool:
    if item.get("push"):
        return True
    return _hand_any_attack_pred(item, lambda a: int(a.get("push") or 0) != 0)


def _hand_has_shaft(item: Dict[str, Any]) -> bool:
    if bool(item.get("shaft")):
        return True
    return _hand_any_attack_pred(item, lambda a: bool(a.get("shaft")))


def _hand_has_shift(item: Dict[str, Any]) -> bool:
    return _hand_any_attack_pred(
        item,
        lambda a: int(a.get("shift_before") or 0) != 0 or int(a.get("shift_after") or 0) != 0,
    )


def _hand_has_repeat(item: Dict[str, Any]) -> bool:
    return _hand_any_attack_pred(item, lambda a: int(a.get("repeat") or 0) != 0)


def _hand_has_stamina_recovery(item: Dict[str, Any]) -> bool:
    return _hand_any_attack_pred(item, lambda a: int(a.get("stamina_recovery") or 0) > 0)


def _hand_has_heal(item: Dict[str, Any]) -> bool:
    # heal is numeric; positive is healing
    return _hand_any_attack_pred(item, lambda a: int(a.get("heal") or 0) > 0)


def _hand_has_condition(item: Dict[str, Any], cond: str) -> bool:
    c = (cond or "").strip().lower()
    return _hand_any_attack_pred(item, lambda a: str(a.get("condition") or "").strip().lower() == c)


_HAND_FEATURE_PRED = {
    "magic": _hand_has_magic,
    "node_attack": _hand_has_node_attack,
    "push": _hand_has_push,
    "shaft": _hand_has_shaft,
    "shift": _hand_has_shift,
    "repeat": _hand_has_repeat,
    "stamina_recovery": _hand_has_stamina_recovery,
    "heal": _hand_has_heal,
}


def _apply_hand_item_filters(
    items: List[Dict[str, Any]],
    *,
    categories: Optional[Set[str]],
    hands_required: Optional[Set[int]],
    only_twohand_compatible_shields: bool,
    ranges: Optional[Set[str]],
    upgrade_slots: Optional[Set[int]],
    attack_lines_mode: str,           # Any | Attacks with dice | No attacks with dice
    required_features: Set[str],      # AND semantics
    any_conditions: Set[str],         # OR semantics
    any_immunities: Set[str],         # OR semantics
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        if categories is not None and str(it.get("hand_category") or "") not in categories:
            continue

        if hands_required is not None and _hand_hands_required_int(it) not in hands_required:
            continue

        if only_twohand_compatible_shields:
            if str(it.get("hand_category") or "").lower() != "shield":
                continue
            if not bool(it.get("usable_with_two_hander")):
                continue

        if ranges is not None and _hand_range_str(it) not in ranges:
            continue

        if upgrade_slots is not None and _hand_upgrade_slots_int(it) not in upgrade_slots:
            continue

        has_dice_attacks = _hand_has_attacks_with_dice(it)
        if attack_lines_mode == "Attacks with dice" and not has_dice_attacks:
            continue
        if attack_lines_mode == "No attacks with dice" and has_dice_attacks:
            continue

        ok = True
        for feat in required_features:
            pred = _HAND_FEATURE_PRED.get(feat)
            if pred and not pred(it):
                ok = False
                break
        if not ok:
            continue

        if any_conditions:
            if not any(_hand_has_condition(it, c) for c in any_conditions):
                continue

        if any_immunities:
            if _immunities_set(it).isdisjoint(any_immunities):
                continue

        out.append(it)

    return out


def _ordered_unique(ids: List[str], stable_order: List[str]) -> List[str]:
    order = {iid: i for i, iid in enumerate(stable_order)}
    unique = [x for x in dict.fromkeys(ids) if x]
    return sorted(unique, key=lambda x: order.get(x, 10**9))

def _merge_visible_selection(
    *,
    prev_ids: List[str],
    chosen_visible_ids: List[str],
    visible_order: List[str],
) -> List[str]:
    visible = set(visible_order)
    hidden = [x for x in prev_ids if x not in visible]
    return _ordered_unique(hidden + chosen_visible_ids, stable_order=visible_order)


def _id(item: Dict[str, Any]) -> str:
    return str(item.get("id") or item.get("name") or "")


def _name(item: Dict[str, Any]) -> str:
    return str(item.get("name") or item.get("id") or "")


def _slot_cost(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("slot_cost") or 1)
    except Exception:
        return 1


def _extra_upgrade_slots(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("upgrade_slot_mod") or 0)
    except Exception:
        return 0


def _upgrade_slots(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("upgrade_slots") or 0)
    except Exception:
        return 0


def _hands_required(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("hands_required") or 1)
    except Exception:
        return 1


def _is_twohand_compatible_shield(item: Dict[str, Any]) -> bool:
    return (
        str(item.get("hand_category") or "").lower() == "shield"
        and bool(item.get("usable_with_two_hander"))
    )


def _clamp_by_slot_cost(
    *,
    desired_ids: List[str],
    prev_ids: List[str],
    capacity: int,
    items_by_id: Dict[str, Dict[str, Any]],
    stable_order: List[str],
) -> List[str]:
    """Keep as much of prev_ids as possible, then fill from desired_ids, without exceeding slot capacity."""

    def _ordered(ids: List[str]) -> List[str]:
        order = {iid: i for i, iid in enumerate(stable_order)}
        return sorted(dict.fromkeys(ids), key=lambda x: order.get(x, 10**9))

    desired = set(desired_ids)
    kept: List[str] = []
    used = 0

    for iid in _ordered([x for x in prev_ids if x in desired]):
        cost = _slot_cost(items_by_id.get(iid) or {})
        if used + cost <= capacity:
            kept.append(iid)
            used += cost

    for iid in _ordered(desired_ids):
        if iid in kept:
            continue
        cost = _slot_cost(items_by_id.get(iid) or {})
        if used + cost <= capacity:
            kept.append(iid)
            used += cost

    return kept


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
    req = item.get("requirements") or {}
    out: Dict[str, int] = {}
    for k in STAT_KEYS:
        try:
            v = int(req.get(k) or 0)
        except Exception:
            v = 0
        if v > 0:
            out[k] = v
    return out


def _eligibility_issues(item: Dict[str, Any], *, stats: Dict[str, int], active: Set[str]) -> List[str]:
    issues: List[str] = []
    exps = set(_item_expansions(item) or [])
    if exps and exps.isdisjoint(active):
        issues.append("disabled expansion")
    req = _item_requirements(item)
    short = []
    for k, need in req.items():
        have = int(stats.get(k) or 0)
        if have < need:
            short.append(f"{STAT_LABEL[k]} {have}/{need}")
    if short:
        issues.append("requirements not met: " + ", ".join(short))
    return issues


def _validate_build(
    *,
    stats: Dict[str, int],
    active: Set[str],
    armor_id: str,
    armor_upgrade_ids: List[str],
    hand_ids: List[str],
    weapon_upgrade_ids_by_hand: Dict[str, List[str]],
    armor_by_id: Dict[str, Dict[str, Any]],
    au_by_id: Dict[str, Dict[str, Any]],
    hand_by_id: Dict[str, Dict[str, Any]],
    wu_by_id: Dict[str, Dict[str, Any]],
) -> List[str]:
    errs: List[str] = []

    # Hand count / 2H rule
    if len(hand_ids) > 3:
        errs.append(f"Too many hand items selected ({len(hand_ids)}/3).")

    # Armor + armor upgrades
    armor_obj = armor_by_id.get(armor_id) if armor_id else None
    if armor_id and not armor_obj:
        errs.append(f"Selected armor id not found: {armor_id}")
    if armor_obj:
        a_issues = _eligibility_issues(armor_obj, stats=stats, active=active)
        if a_issues:
            errs.append(f"Armor '{_name(armor_obj)}' is not equippable ({'; '.join(a_issues)}).")

        cap = _upgrade_slots(armor_obj)
        used = sum(_slot_cost(au_by_id.get(uid) or {}) for uid in armor_upgrade_ids)
        if used > cap:
            errs.append(f"Armor upgrades exceed slots ({used}/{cap}).")

    for uid in armor_upgrade_ids:
        u = au_by_id.get(uid)
        if not u:
            errs.append(f"Selected armor upgrade id not found: {uid}")
            continue
        u_issues = _eligibility_issues(u, stats=stats, active=active)
        if u_issues:
            errs.append(f"Armor upgrade '{_name(u)}' is not usable ({'; '.join(u_issues)}).")

    # Hand items + weapon upgrades
    for hid in hand_ids:
        h = hand_by_id.get(hid)
        if not h:
            errs.append(f"Selected hand item id not found: {hid}")
            continue
        h_issues = _eligibility_issues(h, stats=stats, active=active)
        if h_issues:
            errs.append(f"Hand item '{_name(h)}' is not equippable ({'; '.join(h_issues)}).")

        cap = _upgrade_slots(h)
        ups = list(weapon_upgrade_ids_by_hand.get(hid) or [])
        cap += sum(_extra_upgrade_slots(wu_by_id.get(uid) or {}) for uid in ups)
        used = sum(_slot_cost(wu_by_id.get(uid) or {}) for uid in ups)
        if used > cap:
            errs.append(f"Weapon upgrades on '{_name(h)}' exceed slots ({used}/{cap}).")

        for uid in ups:
            u = wu_by_id.get(uid)
            if not u:
                errs.append(f"Selected weapon upgrade id not found: {uid}")
                continue
            u_issues = _eligibility_issues(u, stats=stats, active=active)
            if u_issues:
                errs.append(f"Weapon upgrade '{_name(u)}' is not usable ({'; '.join(u_issues)}).")

    return errs


def _normalize_hand_selection(
    selected_ids: List[str],
    *,
    items_by_id: Dict[str, Dict[str, Any]],
    stable_order: List[str],
) -> List[str]:
    # No legality enforcement here. Keep the user's selection; just de-dupe and stabilize ordering.
    order = {iid: i for i, iid in enumerate(stable_order)}
    unique = [x for x in dict.fromkeys(selected_ids) if x]
    # Items not in the current table stay at the end (stable sort preserves their relative order).
    return sorted(unique, key=lambda x: order.get(x, 10**9))


def _dynamic_data_editor(data: pd.DataFrame, *, key: str, **kwargs) -> pd.DataFrame:
    changed_key = f"{key}__changed"
    initial_key = f"{key}__initial_data"

    def _on_change():
        st.session_state[changed_key] = True

    if st.session_state.get(changed_key, False):
        data_to_pass = st.session_state.get(initial_key, data)
        st.session_state[changed_key] = False
    else:
        st.session_state[initial_key] = data
        data_to_pass = data

    return st.data_editor(data_to_pass, key=key, on_change=_on_change, **kwargs)


def _render_selection_table(
    *,
    items: List[Dict[str, Any]],
    selected_ids: List[str],
    single_select: bool,
    key: str,
    extra_columns: Optional[Dict[str, List[Any]]] = None,
    rows_fn: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
) -> List[str]:
    if not items:
        st.dataframe([], width="stretch", hide_index=True)
        return []

    rows = rows_fn(items) if rows_fn else _rows_for_table(items)
    for i, row in enumerate(rows):
        row["Select"] = _id(items[i]) in set(selected_ids)
    df = pd.DataFrame(rows)

    # Put Select first
    if "Select" in df.columns:
        df = df[["Select"] + [c for c in df.columns if c != "Select"]]

    kwargs: Dict[str, Any] = {
        "hide_index": True,
        "width": "stretch",
        "disabled": [c for c in df.columns if c != "Select"],
        "num_rows": "fixed",
    }
    if getattr(st, "column_config", None) is not None:
        kwargs["column_config"] = {"Select": st.column_config.CheckboxColumn("Select")}

    try:
        edited = _dynamic_data_editor(df, key=key, **kwargs)
    except TypeError:
        kwargs.pop("num_rows", None)
        kwargs.pop("column_config", None)
        edited = _dynamic_data_editor(df, key=key, **kwargs)

    chosen = [_id(items[i]) for i, v in enumerate(list(edited["Select"])) if bool(v)]
    return chosen[:1] if single_select else chosen


def _tier_index(label: str) -> int:
    try:
        return TIERS.index(label)
    except ValueError:
        return 0


def _build_stats(class_name: str, tier_indices: Dict[str, int]) -> Dict[str, int]:
    cfg = CLASS_TIERS[class_name]
    out: Dict[str, int] = {}
    for k in ("str", "dex", "itl", "fth"):
        idx = int(tier_indices.get(k, 0) or 0)
        idx = 0 if idx < 0 else 3 if idx > 3 else idx
        out[k] = int(cfg[k][idx])
    return out


def _find_data_file(filename: str) -> Optional[Path]:
    candidates = [
        Path("data") / filename,
        Path("data") / "items" / filename,
        Path(filename),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


@st.cache_data(show_spinner=False)
def _load_json_list(path_str: str) -> List[Dict[str, Any]]:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list in {path}, got {type(data).__name__}")
    return data


def _item_expansions(item: Dict[str, Any]) -> List[str]:
    src = item.get("source") or {}
    raw = src.get("expansion") or []
    if isinstance(raw, str):
        raw = [raw]
    out: List[str] = []
    for x in raw:
        if not x:
            continue
        out.append(str(x))
    return out


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
        try:
            out[kk] = int(v)
        except Exception:
            out[kk] = 0
    return out


def _meets_requirements(stats: Dict[str, int], req: Dict[str, int]) -> bool:
    for k in ("str", "dex", "itl", "fth"):
        if int(stats.get(k, 0)) < int(req.get(k, 0)):
            return False
    return True


def _filter_items(
    items: List[Dict[str, Any]],
    *,
    active_expansions: Set[str],
    class_name: str,
    stats: Dict[str, int],
    query: str,
    expansion_filter: Optional[Set[str]] = None,
    source_type_filter: Optional[Set[str]] = None,
    source_entity_filter: Optional[Set[str]] = None,
    legendary_mode: str = "Any",  # Any | Legendary only | Non-legendary only
) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    out: List[Dict[str, Any]] = []

    for it in items:
        exps = _item_expansions(it)
        exps_set = set(exps)

        # settings-level expansion enablement (existing behavior)
        if exps and exps_set.isdisjoint(active_expansions):
            continue

        # global expansion filter (new)
        if expansion_filter is not None:
            if exps and exps_set.isdisjoint(expansion_filter):
                continue
            if not exps and len(expansion_filter) > 0:
                continue

        # global source.type filter (new)
        if source_type_filter is not None:
            if _src_str(it, "type") not in source_type_filter:
                continue

        # global source.entity filter (new)
        if source_entity_filter is not None:
            if _src_str(it, "entity") not in source_entity_filter:
                continue

        # global legendary filter (new)
        if legendary_mode == "Legendary only" and not _is_legendary(it):
            continue
        if legendary_mode == "Non-legendary only" and _is_legendary(it):
            continue

        # requirements (existing behavior)
        req = _item_requirements(it)
        if not _meets_requirements(stats, req):
            continue

        # query (existing behavior)
        if q:
            name = str(it.get("name") or it.get("id") or "").lower()
            if q not in name:
                continue

        out.append(it)

    return out


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
                "Name": it.get("name") or it.get("id"),
                "STR": req.get("str", 0),
                "DEX": req.get("dex", 0),
                "ITL": req.get("itl", 0),
                "FTH": req.get("fth", 0),
                "Block": _dice_icons(block),
                "Resist": _dice_icons(resist),
                "Dodge": _dodge_icons(dodge_n),
                "Block Min": block_total[0],
                "Block Max": block_total[1],
                "Block Avg": block_total[2],
                "Resist Min": resist_total[0],
                "Resist Max": resist_total[1],
                "Resist Avg": resist_total[2],
                "UpgSlots": it.get("upgrade_slots") or 0,
                "Expansions": ", ".join(_item_expansions(it)),
                "Legendary": bool(it.get("legendary")),
                "Source Type": src.get("type") or "",
                "Source Entity": src.get("entity") or "",
            }
        )
    return rows


def render(settings: Dict[str, Any]) -> None:
    st.markdown("## Character Mode")

    active = set(x for x in (settings.get("active_expansions") or []))

    # Selection state
    ss = st.session_state
    ss.setdefault("cm_selected_armor_id", "")
    ss.setdefault("cm_selected_armor_upgrade_ids", [])
    ss.setdefault("cm_selected_hand_ids", [])
    ss.setdefault("cm_selected_weapon_upgrade_ids_by_hand", {})

    left, right = st.columns([1, 1])

    with left:
        eligible_classes = sorted(
            [c for c, cfg in CLASS_TIERS.items() if set(cfg.get("expansions") or set()) & active]
        )
        if not eligible_classes:
            st.error("No classes are available for the enabled expansions.")
            return

        current_class = ss.get("character_mode_class")
        if current_class not in eligible_classes:
            ss["character_mode_class"] = eligible_classes[0]

        class_name = st.selectbox(
            "Class",
            options=eligible_classes,
            key="character_mode_class",
        )

        cfg = CLASS_TIERS[class_name]
        class_exps = sorted(x for x in cfg["expansions"])
        enabled_for_class = sorted(set(class_exps) & active)
        st.caption(
            "Class expansions: "
            + (", ".join(class_exps) if class_exps else "(none)")
            + " | Enabled for class: "
            + (", ".join(enabled_for_class) if enabled_for_class else "(none)")
        )

        tier_opts = [0, 1, 2, 3]

        def _fmt(stat_key: str):
            arr = cfg[stat_key]
            return lambda i: f"{TIERS[i]} ({arr[i]})"

        tier_indices = {
            "str": st.radio("Strength tier", options=tier_opts, index=0, format_func=_fmt("str"), horizontal=True, key="cm_tier_str_i"),
            "dex": st.radio("Dexterity tier", options=tier_opts, index=0, format_func=_fmt("dex"), horizontal=True, key="cm_tier_dex_i"),
            "itl": st.radio("Intelligence tier", options=tier_opts, index=0, format_func=_fmt("itl"), horizontal=True, key="cm_tier_itl_i"),
            "fth": st.radio("Faith tier", options=tier_opts, index=0, format_func=_fmt("fth"), horizontal=True, key="cm_tier_fth_i"),
        }

        stats = _build_stats(class_name, tier_indices)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("STR", stats["str"])
        c2.metric("DEX", stats["dex"])
        c3.metric("INT", stats["itl"])
        c4.metric("FAI", stats["fth"])

    with right:
        summary_slot = st.empty()

    st.markdown("---")
    query = st.text_input("Filter items by name", value="", key="character_mode_item_query")

    # Load item data (best-effort path resolution)
    paths = {
        "hand_items.json": _find_data_file("hand_items.json"),
        "armor.json": _find_data_file("armor.json"),
        "weapon_upgrades.json": _find_data_file("weapon_upgrades.json"),
        "armor_upgrades.json": _find_data_file("armor_upgrades.json"),
    }

    missing = [k for k, v in paths.items() if v is None]
    if missing:
        st.error("Missing item data files: " + ", ".join(missing))
        return

    hand_items = _load_json_list(str(paths["hand_items.json"]))
    armor_items = _load_json_list(str(paths["armor.json"]))
    weapon_upgrades = _load_json_list(str(paths["weapon_upgrades.json"]))
    armor_upgrades = _load_json_list(str(paths["armor_upgrades.json"]))

    all_items = hand_items + armor_items + weapon_upgrades + armor_upgrades

    # Build options from items that are in enabled expansions
    enabled_items = []
    present_exps: Set[str] = set()
    src_types: Set[str] = set()
    src_entities: Set[str] = set()

    for it in all_items:
        exps = set(_item_expansions(it))
        if exps and exps.isdisjoint(active):
            continue
        enabled_items.append(it)
        present_exps |= exps
        src_types.add(_src_str(it, "type"))
        src_entities.add(_src_str(it, "entity"))

    expansion_options = sorted(present_exps & active)
    type_options = _sorted_with_none_first(src_types)
    entity_options = _sorted_with_none_first(src_entities)

    # --- Global filter defaults (must exist before any filtered_* computations) ---
    gf_expansion = st.session_state.get("cm_gf_expansion")
    gf_source_type = st.session_state.get("cm_gf_source_type")
    gf_source_entity = st.session_state.get("cm_gf_source_entity")
    gf_legendary = st.session_state.get("cm_gf_legendary") or "Any"

    gf_expansion = [x for x in (gf_expansion or expansion_options) if x in expansion_options]
    gf_source_type = [x for x in (gf_source_type or type_options) if x in type_options]
    gf_source_entity = [x for x in (gf_source_entity or entity_options) if x in entity_options]

    expansion_filter = set(gf_expansion)
    source_type_filter = set(gf_source_type)
    source_entity_filter = set(gf_source_entity)
    legendary_mode = gf_legendary if gf_legendary in {"Any", "Legendary only", "Non-legendary only"} else "Any"

    with st.expander("Global filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            prev = st.session_state.get("cm_gf_expansion") or expansion_options
            default = [x for x in prev if x in expansion_options] or expansion_options
            gf_expansion = st.multiselect(
                "Expansion",
                options=expansion_options,
                default=default,
                key="cm_gf_expansion",
            )
        with c2:
            gf_legendary = st.selectbox(
                "Legendary",
                options=["Any", "Legendary only", "Non-legendary only"],
                index=0,
                key="cm_gf_legendary",
            )

        c3, c4 = st.columns(2)
        with c3:
            prev = st.session_state.get("cm_gf_source_type") or type_options
            default = [x for x in prev if x in type_options] or type_options
            gf_source_type = st.multiselect(
                "Source Type",
                options=type_options,
                default=default,
                key="cm_gf_source_type",
            )
        with c4:
            prev = st.session_state.get("cm_gf_source_entity") or entity_options
            default = [x for x in prev if x in entity_options] or entity_options
            gf_source_entity = st.multiselect(
                "Source Entity",
                options=entity_options,
                default=default,
                key="cm_gf_source_entity",
            )

    expansion_filter = set(gf_expansion)
    source_type_filter = set(gf_source_type)
    source_entity_filter = set(gf_source_entity)
    legendary_mode = gf_legendary

    # --- Hand item filters (applies only to hand items table) ---
    hand_pool_for_options = _filter_items(
        hand_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query="",  # options should not collapse due to name search
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )

    cat_opts = sorted({str(x.get("hand_category") or "") for x in hand_pool_for_options})
    hands_opts = sorted({_hand_hands_required_int(x) for x in hand_pool_for_options})
    range_opts = sorted({_hand_range_str(x) for x in hand_pool_for_options}, key=lambda s: (s == "∞", int(s) if s != "∞" else 999))
    slot_opts = sorted({_hand_upgrade_slots_int(x) for x in hand_pool_for_options})
    hand_immunity_opts = sorted({x for it in hand_pool_for_options for x in _immunities_set(it)})

    with st.expander("Hand item filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            hf_categories = st.multiselect(
                "Category",
                options=cat_opts,
                default=cat_opts,
                key="cm_hf_categories",
            )
            hf_hands = st.multiselect(
                "Hands required",
                options=hands_opts,
                default=hands_opts,
                key="cm_hf_hands",
            )
            hf_only_twohand_shields = st.checkbox(
                "Only shields usable with a 2-hander",
                value=False,
                key="cm_hf_only_twohand_shields",
            )
        with c2:
            hf_ranges = st.multiselect(
                "Range",
                options=range_opts,
                default=range_opts,
                key="cm_hf_ranges",
            )
            hf_upgrade_slots = st.multiselect(
                "Upgrade slots",
                options=slot_opts,
                default=slot_opts,
                key="cm_hf_upgrade_slots",
            )
            _attack_mode_opts = ["Any", "Attacks with dice", "No attacks with dice"]
            hf_attack_lines_mode = st.radio(
                "Attacks with dice",
                options=_attack_mode_opts,
                index=_attack_mode_opts.index(st.session_state.get("cm_hf_attack_lines_mode") or "Any"),
                horizontal=True,
                key="cm_hf_attack_lines_mode",
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            hf_required_features = st.multiselect(
                "Required properties (must match all)",
                options=HAND_FEATURE_OPTIONS,
                default=st.session_state.get("cm_hf_required_features") or [],
                key="cm_hf_required_features",
            )
        with c4:
            hf_any_conditions = st.multiselect(
                "Conditions (match any)",
                options=HAND_CONDITION_OPTIONS,
                default=st.session_state.get("cm_hf_any_conditions") or [],
                key="cm_hf_any_conditions",
            )
        with c5:
            hf_any_immunities = st.multiselect(
                "Immunities (match any)",
                options=hand_immunity_opts,
                default=st.session_state.get("cm_hf_any_immunities") or [],  # empty = show everything
                key="cm_hf_any_immunities",
            )

    hand_filter_categories = set(hf_categories) if hf_categories else None
    hand_filter_hands = set(int(x) for x in hf_hands) if hf_hands else None
    hand_filter_ranges = set(hf_ranges) if hf_ranges else None
    hand_filter_slots = set(int(x) for x in hf_upgrade_slots) if hf_upgrade_slots else None
    hand_required_features = set(hf_required_features or [])
    hand_any_conditions = set(hf_any_conditions or [])
    hand_any_immunities = set(hf_any_immunities or [])

    armor_pool_for_options = _filter_items(
        armor_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query="",
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )

    armor_dodge_opts = sorted({_armor_dodge_int(x) for x in armor_pool_for_options})
    armor_slot_opts = sorted({_armor_upgrade_slots_int(x) for x in armor_pool_for_options})
    armor_immunity_opts = sorted({x for it in armor_pool_for_options for x in _immunities_set(it)})

    with st.expander("Armor filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            af_dodge = st.multiselect("Dodge dice", options=armor_dodge_opts, default=armor_dodge_opts, key="cm_af_dodge")
            af_slots = st.multiselect("Upgrade slots", options=armor_slot_opts, default=armor_slot_opts, key="cm_af_slots")

        with c2:
            af_immunities = st.multiselect(
                "Immunities (match any)",
                options=armor_immunity_opts,
                default=st.session_state.get("cm_af_immunities") or [],  # empty = show everything
                key="cm_af_immunities",
            )
            _sr_opts = ["Any", "Has special rules", "No special rules"]
            af_special = st.radio(
                "Special rules",
                options=_sr_opts,
                index=_sr_opts.index(st.session_state.get("cm_af_special") or "Any"),
                horizontal=True,
                key="cm_af_special",
            )

    armor_filter_dodge = set(int(x) for x in af_dodge) if af_dodge else None
    armor_filter_slots = set(int(x) for x in af_slots) if af_slots else None
    armor_any_immunities = set(af_immunities or [])
    armor_special_mode = af_special

    expansion_filter = set(gf_expansion)
    source_type_filter = set(gf_source_type)
    source_entity_filter = set(gf_source_entity)
    legendary_mode = gf_legendary

    hand_by_id = {_id(x): x for x in hand_items}
    armor_by_id = {_id(x): x for x in armor_items}
    wu_by_id = {_id(x): x for x in weapon_upgrades}
    au_by_id = {_id(x): x for x in armor_upgrades}

    # Filtered lists
    filtered_hand_base = _filter_items(
        hand_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )

    filtered_hand = _apply_hand_item_filters(
        filtered_hand_base,
        categories=hand_filter_categories,
        hands_required=hand_filter_hands,
        only_twohand_compatible_shields=bool(hf_only_twohand_shields),
        ranges=hand_filter_ranges,
        upgrade_slots=hand_filter_slots,
        attack_lines_mode=hf_attack_lines_mode,
        required_features=hand_required_features,
        any_conditions=hand_any_conditions,
        any_immunities=hand_any_immunities,
    )
    filtered_armor_base = _filter_items(
        armor_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )
    filtered_armor = _apply_armor_filters(
        filtered_armor_base,
        dodge_dice=armor_filter_dodge,
        upgrade_slots=armor_filter_slots,
        any_immunities=armor_any_immunities,
        special_rules_mode=armor_special_mode,
    )
    filtered_wu = _filter_items(
        weapon_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )
    filtered_au = _filter_items(
        armor_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )

    hand_order = [_id(x) for x in filtered_hand]
    armor_order = [_id(x) for x in filtered_armor]
    wu_order = [_id(x) for x in filtered_wu]
    au_order = [_id(x) for x in filtered_au]

    # Normalize build selections against current filters
    ss["cm_selected_hand_ids"] = _normalize_hand_selection(
        [x for x in ss.get("cm_selected_hand_ids", []) if x in hand_by_id],
        items_by_id=hand_by_id,
        stable_order=hand_order,
    )

    # Normalize build selections (state hygiene only; do not enforce legality)
    ss["cm_selected_hand_ids"] = _normalize_hand_selection(
        [x for x in ss.get("cm_selected_hand_ids", []) if x in hand_by_id],
        items_by_id=hand_by_id,
        stable_order=hand_order,
    )

    armor_id = ss.get("cm_selected_armor_id") or ""
    if armor_id and armor_id not in armor_by_id:
        ss["cm_selected_armor_id"] = ""
        ss["cm_selected_armor_upgrade_ids"] = []

    ss["cm_selected_armor_upgrade_ids"] = [x for x in ss.get("cm_selected_armor_upgrade_ids", []) if x in au_by_id]

    armor_obj = armor_by_id.get(ss.get("cm_selected_armor_id") or "")
    armor_capacity = _upgrade_slots(armor_obj or {})

    wu_map: Dict[str, List[str]] = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
    selected_hands = set(ss["cm_selected_hand_ids"])
    for hid in list(wu_map.keys()):
        if hid not in selected_hands:
            wu_map.pop(hid, None)
    for hid in selected_hands:
        wu_map[hid] = [x for x in (wu_map.get(hid) or []) if x in wu_by_id]

    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

    tab_hand, tab_armor, tab_wu, tab_au = st.tabs(
        ["Hand Items", "Armor", "Weapon Upgrades", "Armor Upgrades"]
    )

    with tab_hand:
        st.caption(f"{len(filtered_hand)} item(s)")
        prev = list(ss.get("cm_selected_hand_ids", []))
        chosen = _render_selection_table(
            items=filtered_hand,
            selected_ids=prev,
            single_select=False,
            key="cm_table_hand",
        )
        merged = _merge_visible_selection(
            prev_ids=prev,
            chosen_visible_ids=chosen,
            visible_order=hand_order,
        )
        ss["cm_selected_hand_ids"] = _normalize_hand_selection(
            merged,
            items_by_id=hand_by_id,
            stable_order=hand_order,
        )

    with tab_armor:
        st.caption(f"{len(filtered_armor)} item(s)")
        prev_armor_id = ss.get("cm_selected_armor_id") or ""
        chosen = _render_selection_table(
            items=filtered_armor,
            selected_ids=[ss.get("cm_selected_armor_id") or ""],
            single_select=True,
            key="cm_table_armor",
            rows_fn=_rows_for_armor_table,
        )

        if chosen:
            new_armor_id = chosen[0]
        else:
            # Preserve hidden selection
            new_armor_id = prev_armor_id if prev_armor_id and prev_armor_id not in set(armor_order) else ""

        if new_armor_id != prev_armor_id:
            ss["cm_selected_armor_id"] = new_armor_id
            ss["cm_selected_armor_upgrade_ids"] = []

    with tab_wu:
        st.caption(f"{len(filtered_wu)} item(s)")
        if not ss["cm_selected_hand_ids"]:
            st.info("Select hand items to attach weapon upgrades.")
        else:
            for hid in ss["cm_selected_hand_ids"]:
                h = hand_by_id.get(hid) or {}
                cap = _upgrade_slots(h)
                if cap <= 0:
                    continue
                with st.expander(f"{_name(h)} (upgrade slots: {cap})", expanded=False):
                    prev = list(wu_map.get(hid) or [])
                    chosen = _render_selection_table(
                        items=filtered_wu,
                        selected_ids=prev,
                        single_select=False,
                        key=f"cm_weapon_up_{hid}",
                    )

                    wu_map[hid] = _merge_visible_selection(
                        prev_ids=prev,
                        chosen_visible_ids=chosen,
                        visible_order=wu_order,
                    )

    with tab_au:
        st.caption(f"{len(filtered_au)} item(s)")
        if not ss.get("cm_selected_armor_id"):
            st.info("Select an armor to attach armor upgrades.")
        else:
            cap = armor_capacity
            st.caption(f"Armor upgrade slots: {cap}")
            prev = list(ss.get("cm_selected_armor_upgrade_ids") or [])
            chosen = _render_selection_table(
                items=filtered_au,
                selected_ids=prev,
                single_select=False,
                key="cm_armor_upgrades_table",
            )

            ss["cm_selected_armor_upgrade_ids"] = _merge_visible_selection(
                prev_ids=prev,
                chosen_visible_ids=chosen,
                visible_order=au_order,
            )

    # --- Final reconcile (no legality enforcement) ---
    ss["cm_selected_hand_ids"] = _normalize_hand_selection(
        list(ss.get("cm_selected_hand_ids") or []),
        items_by_id=hand_by_id,
        stable_order=hand_order,
    )

    ss["cm_selected_armor_upgrade_ids"] = _ordered_unique(
        list(ss.get("cm_selected_armor_upgrade_ids") or []),
        stable_order=au_order,
    )

    wu_map: Dict[str, List[str]] = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
    selected_hand_set = set(ss["cm_selected_hand_ids"])

    # prune upgrades for removed hands (state hygiene, not legality)
    for hid in list(wu_map.keys()):
        if hid not in selected_hand_set:
            wu_map.pop(hid, None)

    for hid in ss["cm_selected_hand_ids"]:
        wu_map[hid] = _ordered_unique(list(wu_map.get(hid) or []), stable_order=wu_order)

    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

    # --- Selected Items + validation (right column) ---
    validation_errors = _validate_build(
        stats=stats,
        active=active,
        armor_id=ss.get("cm_selected_armor_id") or "",
        armor_upgrade_ids=list(ss.get("cm_selected_armor_upgrade_ids") or []),
        hand_ids=list(ss.get("cm_selected_hand_ids") or []),
        weapon_upgrade_ids_by_hand=dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {}),
        hand_by_id=hand_by_id,
        armor_by_id=armor_by_id,
        wu_by_id=wu_by_id,
        au_by_id=au_by_id,
    )

    with summary_slot.container():
        st.markdown("### Selected Items")

        if validation_errors:
            st.warning("Build is invalid:")
            for e in validation_errors:
                st.markdown(f"- {e}")

        # Armor
        armor_id = ss.get("cm_selected_armor_id") or ""
        armor_obj = armor_by_id.get(armor_id) if armor_id else None
        armor_capacity = _upgrade_slots(armor_obj or {})

        if armor_obj:
            arow = st.columns([8, 2])
            arow[0].markdown(f"**Armor:** {_name(armor_obj)}")
            if arow[1].button("Remove", key="cm_remove_armor"):
                ss["cm_selected_armor_id"] = ""
                ss["cm_selected_armor_upgrade_ids"] = []
                st.rerun()

            if ss["cm_selected_armor_upgrade_ids"]:
                used = sum(_slot_cost(au_by_id.get(x) or {}) for x in ss["cm_selected_armor_upgrade_ids"])
                st.caption(f"Armor upgrade slots: {armor_capacity} (used {used})")
                for uid in list(ss["cm_selected_armor_upgrade_ids"]):
                    u = au_by_id.get(uid) or {}
                    urow = st.columns([8, 2])
                    urow[0].markdown(f"- {_name(u)} (cost {_slot_cost(u)})")
                    if urow[1].button("Remove", key=f"cm_remove_armor_up_{uid}"):
                        ss["cm_selected_armor_upgrade_ids"] = [x for x in ss["cm_selected_armor_upgrade_ids"] if x != uid]
                        st.rerun()
        else:
            st.markdown("**Armor:** (none)")

        # Hand items
        if ss["cm_selected_hand_ids"]:
            st.markdown("**Hand Items:**")
            for hid in list(ss["cm_selected_hand_ids"]):
                h = hand_by_id.get(hid) or {}
                hrow = st.columns([8, 2])
                hrow[0].markdown(
                    f"- {_name(h)} (hands {_hands_required(h)}, slot cost {_slot_cost(h)}, upgrade slots {_upgrade_slots(h)})"
                )
                if hrow[1].button("Remove", key=f"cm_remove_hand_{hid}"):
                    ss["cm_selected_hand_ids"] = [x for x in ss["cm_selected_hand_ids"] if x != hid]
                    wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
                    wu_map.pop(hid, None)
                    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map
                    st.rerun()

                ups = list((ss["cm_selected_weapon_upgrade_ids_by_hand"].get(hid) or []))
                for uid in ups:
                    u = wu_by_id.get(uid) or {}
                    urow = st.columns([8, 2])
                    urow[0].markdown(f"  - {_name(u)} (cost {_slot_cost(u)})")
                    if urow[1].button("Remove", key=f"cm_remove_wu_{hid}_{uid}"):
                        wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
                        wu_map[hid] = [x for x in (wu_map.get(hid) or []) if x != uid]
                        ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map
                        st.rerun()
        else:
            st.markdown("**Hand Items:** (none)")
