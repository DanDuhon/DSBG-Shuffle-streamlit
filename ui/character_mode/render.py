# ui/character_mode/render.py
from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import streamlit as st

TIERS = ["Base", "Tier 1", "Tier 2", "Tier 3"]
STAT_KEYS = ("str", "dex", "itl", "fth")
STAT_LABEL = {"str": "STR", "dex": "DEX", "itl": "INT", "fth": "FAI"}

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

    two_handed = [hid for hid in hand_ids if _hands_required(hand_by_id.get(hid) or {}) == 2]
    if len(two_handed) >= 2 and len(hand_ids) == 3:
        third = [hid for hid in hand_ids if hid not in set(two_handed)]
        if third:
            third_item = hand_by_id.get(third[0]) or {}
            if not _is_twohand_compatible_shield(third_item):
                errs.append("Two 2-handed items selected: the third item must be a shield usable with a 2-handed weapon.")

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
) -> List[str]:
    if not items:
        st.dataframe([], width="stretch", hide_index=True)
        return []

    rows = _rows_for_table(items)
    for i, row in enumerate(rows):
        row["Select"] = _id(items[i]) in set(selected_ids)
    df = pd.DataFrame(rows)

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
) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for it in items:
        exps = _item_expansions(it)
        if exps and not (set(exps) & active_expansions):
            continue

        req = _item_requirements(it)
        if not _meets_requirements(stats, req):
            continue

        if q:
            name = str(it.get("name") or it.get("id") or "").lower()
            if q not in name:
                continue

        out.append(it)
    out.sort(key=lambda x: str(x.get("name") or x.get("id") or ""))
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
                "ITL": req.get("itl", 0),
                "FTH": req.get("fth", 0),
                "Expansions": ", ".join(_item_expansions(it)),
                "SourceType": src.get("type") or "",
                "Class/Invader/Boss": src.get("entity") or "",
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
        c3.metric("ITL", stats["itl"])
        c4.metric("FTH", stats["fth"])

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

    hand_by_id = {_id(x): x for x in hand_items}
    armor_by_id = {_id(x): x for x in armor_items}
    wu_by_id = {_id(x): x for x in weapon_upgrades}
    au_by_id = {_id(x): x for x in armor_upgrades}

    # Filtered lists
    filtered_hand = _filter_items(
        hand_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
    )
    filtered_armor = _filter_items(
        armor_items,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
    )
    filtered_wu = _filter_items(
        weapon_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
    )
    filtered_au = _filter_items(
        armor_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
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

    if ss.get("cm_selected_armor_id") not in set(armor_order):
        ss["cm_selected_armor_id"] = ""
        ss["cm_selected_armor_upgrade_ids"] = []

    armor_id = ss.get("cm_selected_armor_id") or ""
    armor_obj = armor_by_id.get(armor_id) if armor_id else None
    armor_capacity = _upgrade_slots(armor_obj or {})

    if not armor_obj:
        ss["cm_selected_armor_upgrade_ids"] = []
    else:
        desired = [x for x in ss.get("cm_selected_armor_upgrade_ids", []) if x in set(au_order)]
        ss["cm_selected_armor_upgrade_ids"] = _clamp_by_slot_cost(
            desired_ids=desired,
            prev_ids=list(ss.get("cm_selected_armor_upgrade_ids", [])),
            capacity=armor_capacity,
            items_by_id=au_by_id,
            stable_order=au_order,
        )

    # Weapon upgrades per hand item
    wu_map: Dict[str, List[str]] = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
    # remove entries for hands no longer selected
    for hid in list(wu_map.keys()):
        if hid not in set(ss["cm_selected_hand_ids"]):
            wu_map.pop(hid, None)
    for hid in ss["cm_selected_hand_ids"]:
        hobj = hand_by_id.get(hid) or {}
        cap = _upgrade_slots(hobj)
        if cap <= 0:
            wu_map[hid] = []
            continue
        desired = [x for x in (wu_map.get(hid) or []) if x in set(wu_order)]
        wu_map[hid] = _clamp_by_slot_cost(
            desired_ids=desired,
            prev_ids=list(wu_map.get(hid) or []),
            capacity=cap,
            items_by_id=wu_by_id,
            stable_order=wu_order,
        )
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
        normalized = _normalize_hand_selection(
            chosen,
            items_by_id=hand_by_id,
            stable_order=hand_order,
        )
        ss["cm_selected_hand_ids"] = normalized

    with tab_armor:
        st.caption(f"{len(filtered_armor)} item(s)")
        prev_armor_id = ss.get("cm_selected_armor_id") or ""
        chosen = _render_selection_table(
            items=filtered_armor,
            selected_ids=[prev_armor_id] if prev_armor_id else [],
            single_select=True,
            key="cm_armor_table",
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
