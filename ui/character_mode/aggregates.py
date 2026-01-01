from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ui.character_mode.dice_math import _dice_icons, _dice_min_max_avg, _expected_remaining_damage, _dodge_success_prob
from ui.character_mode.item_fields import _hand_dodge_int, _id, _name
import json
import streamlit as st


DiceDict = Dict[str, int]  # keys: black, blue, orange, flat_mod


def _int(v: Any, default: int = 0) -> int:
    if v is None:
        return int(default)
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(str(v))
        except Exception:
            return int(default)


def _as_dice_dict(obj: Any) -> DiceDict:
    if not isinstance(obj, dict):
        return {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}
    return {
        "black": _int(obj.get("black"), 0),
        "blue": _int(obj.get("blue"), 0),
        "orange": _int(obj.get("orange"), 0),
        "flat_mod": _int(obj.get("flat_mod"), 0),
    }


def _dice_add(a: DiceDict, b: DiceDict) -> DiceDict:
    out = {
        "black": _int(a.get("black"), 0) + _int(b.get("black"), 0),
        "blue": _int(a.get("blue"), 0) + _int(b.get("blue"), 0),
        "orange": _int(a.get("orange"), 0) + _int(b.get("orange"), 0),
        "flat_mod": _int(a.get("flat_mod"), 0) + _int(b.get("flat_mod"), 0),
    }
    # clamp dice counts (flat_mod can be negative)
    out["black"] = max(out["black"], 0)
    out["blue"] = max(out["blue"], 0)
    out["orange"] = max(out["orange"], 0)
    return out


def _str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple, set)):
        out: List[str] = []
        for x in v:
            if x is None:
                continue
            sx = str(x).strip()
            if sx:
                out.append(sx)
        return out
    s = str(v).strip()
    return [s] if s else []


def _get_nested(d: Any, path: str) -> Any:
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _first_present_dict(obj: Dict[str, Any], keys: Iterable[str]) -> Optional[Dict[str, Any]]:
    for k in keys:
        v = _get_nested(obj, k)
        if isinstance(v, dict):
            return v
    return None


def _first_present_int(obj: Dict[str, Any], keys: Iterable[str]) -> Optional[int]:
    for k in keys:
        v = _get_nested(obj, k)
        if v is None:
            continue
        return int(v)
    return None


def _first_present_bool(obj: Dict[str, Any], keys: Iterable[str]) -> Optional[bool]:
    for k in keys:
        v = _get_nested(obj, k)
        if v is None:
            continue
        return bool(v)
    return None


# ---- Mod extraction (tolerant to multiple schema styles) ----

_ATTACK_DICE_KEYS = (
    # v2 schema (canonical)
    "mods.attack.dice",
    "mods.damage.dice",

    # legacy / transitional
    "attack_dice_mod",
    "damage_dice_mod",
    "dice_mod",
    "attack_mod",  # sometimes a dict
    "damage_mod",  # sometimes a dict
    "mods.attack",  # only works if it's already a dice dict
    "mods.damage",
    "effects.damage_mod",  # older upgrade schema
)

_ATTACK_FLAT_KEYS = (
    "attack_flat_mod",
    "damage_flat_mod",
    "attack_mod",          # sometimes stored as an int
    "damage_mod",          # sometimes stored as an int
    "mod",                 # generic flat modifier
    "flat_mod",            # generic flat modifier
    "mods.attack.mod",
    "mods.damage.mod",
)


_ATTACK_STAM_KEYS = (
    "stamina_mod",
    "stamina_delta",
    "mods.attack.stamina_mod",
    "mods.attack.stamina",
)

_COND_KEYS = (
    "condition",
    "conditions",
    "adds_condition",
    "adds_conditions",
    "mods.conditions",
    "mods.attack.conditions",
)

_IGNORE_BLOCK_KEYS = (
    "ignore_block",
    "ignores_block",
    "mods.ignore_block",
    "mods.attack.ignore_block",
)

_BLOCK_DICE_KEYS = (
    "block_dice_mod",
    "block_mod",
    "mods.block",
    "mods.defense.block",
)

_RESIST_DICE_KEYS = (
    "resist_dice_mod",
    "resist_mod",
    "mods.resist",
    "mods.defense.resist",
)

_DODGE_KEYS = (
    "dodge_dice_mod",
    "dodge_mod",
    "mods.dodge",
    "mods.defense.dodge",
)


@dataclass(frozen=True)
class AttackMods:
    dice: DiceDict
    stamina_delta: int
    conditions: Tuple[str, ...]
    ignore_block: bool


@dataclass(frozen=True)
class DefenseTotals:
    block: DiceDict
    resist: DiceDict
    dodge_armor: int
    dodge_hand_max: int


@dataclass
class AttackState:
    """Mutable per-attack state while applying v2 rules."""

    dice: DiceDict
    stamina: int
    range_str: str
    range_int: Optional[int]
    magic: bool
    node: bool
    shaft: bool
    push: int
    ignore_block: bool
    conditions: List[str]
    text: str


def _extract_attack_mods(obj: Dict[str, Any]) -> AttackMods:
    # Some upgrades/items store dice mods as dicts (e.g. {"black":1,"flat_mod":-1})
    # and others store a flat modifier as an int (e.g. attack_mod: +1).
    # We support both without double-counting nested flat_mod.
    dice_total: DiceDict = {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}

    # Sum all dict-valued dice mods across supported keys (not just the first match)
    for k in _ATTACK_DICE_KEYS:
        v = _get_nested(obj, k)
        if isinstance(v, dict):
            dice_total = _dice_add(dice_total, _as_dice_dict(v))

    # Sum scalar flat modifiers (ints) across supported keys
    flat_total = 0
    for k in _ATTACK_FLAT_KEYS:
        v = _get_nested(obj, k)
        if v is None:
            continue
        if isinstance(v, dict) or isinstance(v, (list, tuple, set)):
            continue
        flat_total += int(v)

    if flat_total:
        dice_total = dict(dice_total)
        dice_total["flat_mod"] = _int(dice_total.get("flat_mod"), 0) + int(flat_total)

    stam = _first_present_int(obj, _ATTACK_STAM_KEYS) or 0

    conds: List[str] = []
    for k in _COND_KEYS:
        v = _get_nested(obj, k)
        if v is None:
            continue
        conds.extend(_str_list(v))

    ign = _first_present_bool(obj, _IGNORE_BLOCK_KEYS)
    return AttackMods(dice=dice_total, stamina_delta=int(stam), conditions=tuple(dict.fromkeys(conds)), ignore_block=bool(ign))


def _extract_defense_mods(obj: Dict[str, Any]) -> Tuple[DiceDict, DiceDict, int]:
    block = _as_dice_dict(_first_present_dict(obj, _BLOCK_DICE_KEYS) or {})
    resist = _as_dice_dict(_first_present_dict(obj, _RESIST_DICE_KEYS) or {})
    dodge = _first_present_int(obj, _DODGE_KEYS) or 0
    return block, resist, int(dodge)


def _attack_base_dice(atk: Dict[str, Any]) -> DiceDict:
    d = _as_dice_dict(atk.get("dice") or {})
    # support flat_mod being stored at the attack root
    d = dict(d)
    d["flat_mod"] = _int(d.get("flat_mod"), 0) + _int(atk.get("flat_mod"), 0)
    return d


def _attack_base_condition(atk: Dict[str, Any]) -> str:
    return str(atk.get("condition") or "").strip()


def _attack_base_ignore_block(item: Dict[str, Any], atk: Dict[str, Any]) -> bool:
    return bool(atk.get("ignore_block") or atk.get("ignores_block") or item.get("ignore_block") or item.get("ignores_block"))


def _attack_base_stamina(atk: Dict[str, Any]) -> int:
    return _int(atk.get("stamina"), 0)


def _weapon_source_type(weapon: Dict[str, Any]) -> str:
    src = weapon.get("source") or {}
    s = str(src.get("type") or "").strip().lower()
    return s


def _attack_base_range_str(item: Dict[str, Any], atk: Dict[str, Any]) -> str:
    r = atk.get("range")
    if r is None or str(r).strip() == "":
        r = item.get("range")
    return "" if r is None else str(r).strip()


def _range_to_int(r: str) -> Optional[int]:
    s = str(r or "").strip()
    if not s:
        return None
    if s == "∞":
        return None
    return int(s)


def _collapse_conditions(*parts: Iterable[str]) -> str:
    out: List[str] = []
    for p in parts:
        for x in p:
            s = str(x).strip()
            if not s:
                continue
            out.append(s)
    return ", ".join(dict.fromkeys(out))


def _aggregate_attack_mods(
    *,
    armor_obj: Optional[Dict[str, Any]],
    armor_upgrade_objs: List[Dict[str, Any]],
    weapon_upgrade_objs: List[Dict[str, Any]],
) -> AttackMods:
    # global + weapon/armor upgrades; per-attack mods are handled separately elsewhere
    total_dice: DiceDict = {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}
    total_stam = 0
    conds: List[str] = []
    ign = False

    objs = []
    if armor_obj:
        objs.append(armor_obj)
    objs.extend(armor_upgrade_objs)
    objs.extend(weapon_upgrade_objs)

    for o in objs:
        am = _extract_attack_mods(o)
        total_dice = _dice_add(total_dice, am.dice)
        total_stam += int(am.stamina_delta)
        conds.extend(list(am.conditions))
        ign = ign or bool(am.ignore_block)

    return AttackMods(dice=total_dice, stamina_delta=total_stam, conditions=tuple(dict.fromkeys(conds)), ignore_block=ign)


def _per_attack_mod_from_upgrade(up: Dict[str, Any], attack_index: int) -> AttackMods:
    # Supported shapes:
    # - attack_mods: [ {dice_mod...}, ...]
    # - mods.attack_lines: [ {attack_dice_mod...}, ...]
    candidates = []
    v1 = up.get("attack_mods")
    if isinstance(v1, list):
        candidates = v1
    v2 = _get_nested(up, "mods.attack_lines")
    if isinstance(v2, list):
        candidates = v2

    if 0 <= attack_index < len(candidates):
        obj = candidates[attack_index]
        if isinstance(obj, dict):
            return _extract_attack_mods(obj)
    return AttackMods(dice={"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}, stamina_delta=0, conditions=tuple(), ignore_block=False)


def _iter_v2_attack_rules(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules = obj.get("rules") or []
    if not isinstance(rules, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in rules:
        if isinstance(r, dict) and str(r.get("scope") or "").strip().lower() == "attack":
            out.append(r)
    return out


def _rule_targets(
    rule: Dict[str, Any],
    *,
    base_stamina: List[int],
    base_range_int: List[Optional[int]],
) -> List[int]:
    sel = rule.get("select") or {}
    if not isinstance(sel, dict):
        return list(range(len(base_stamina)))

    kind = str(sel.get("kind") or "all").strip().lower()
    if kind == "all":
        return list(range(len(base_stamina)))

    if kind == "range":
        want = int(sel.get("value"))
        return [i for i, r in enumerate(base_range_int) if r is not None and int(r) == want]

    if kind == "max":
        field = str(sel.get("field") or "").strip().lower()
        if field != "stamina" or not base_stamina:
            return []
        mx = max(base_stamina)
        idxs = [i for i, v in enumerate(base_stamina) if v == mx]
        if not idxs:
            return []
        tiebreak = str(sel.get("tiebreak") or "").strip().lower()
        if tiebreak in ("lowest_index", "first"):
            return [min(idxs)]
        return [idxs[0]]

    return []


def _rule_when_ok(
    when: Any,
    *,
    weapon: Dict[str, Any],
    state: AttackState,
) -> bool:
    if when is None:
        return True
    if not isinstance(when, dict):
        return True

    w = when.get("weapon")
    if isinstance(w, dict):
        st = w.get("source_type")
        if st is not None:
            if _weapon_source_type(weapon) != str(st).strip().lower():
                return False

    a = when.get("attack")
    if isinstance(a, dict):
        if "magic" in a:
            if bool(a.get("magic")) != bool(state.magic):
                return False

    return True


def build_attack_totals_rows(
    *,
    hand_items: List[Dict[str, Any]],
    selected_hand_ids: Set[str],
    armor_obj: Optional[Dict[str, Any]],
    armor_upgrade_objs: List[Dict[str, Any]],
    weapon_upgrades_by_hand: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for it in hand_items:
        iid = _id(it)
        name = _name(it)
        atks = it.get("attacks") or []
        if not isinstance(atks, list) or not atks:
            continue

        wups = list(weapon_upgrades_by_hand.get(iid) or [])

        # Global mods apply to all attacks on this weapon.
        global_mods = _aggregate_attack_mods(
            armor_obj=armor_obj,
            armor_upgrade_objs=armor_upgrade_objs,
            weapon_upgrade_objs=wups,
        )

        # Optional range delta (v2 supports mods.attack.range, but most range tweaks live in rules).
        global_range_delta = 0
        for src in ([armor_obj] if armor_obj else []) + list(armor_upgrade_objs) + list(wups):
            if not isinstance(src, dict):
                continue
            v = _get_nested(src, "mods.attack.range")
            if v is None:
                continue
            global_range_delta += int(v)

        # Base arrays used for v2 rule targeting (stable, order-independent).
        base_stamina: List[int] = []
        base_range_str: List[str] = []
        base_range_int: List[Optional[int]] = []
        for atk in atks:
            atk = atk or {}
            base_stamina.append(_attack_base_stamina(atk))
            rs = _attack_base_range_str(it, atk)
            base_range_str.append(rs)
            base_range_int.append(_range_to_int(rs))

        # Build initial per-attack states (base + global mods + legacy per-attack mods).
        states: List[AttackState] = []
        base_dice_by_idx: List[DiceDict] = []
        for idx, atk in enumerate(atks):
            atk = atk or {}
            base_dice = _attack_base_dice(atk)
            base_dice_by_idx.append(base_dice)

            dice = _dice_add(base_dice, global_mods.dice)
            stam = int(base_stamina[idx]) + int(global_mods.stamina_delta)

            r_str = base_range_str[idx]
            r_int = base_range_int[idx]
            if global_range_delta and r_int is not None:
                r_int = max(int(r_int) + int(global_range_delta), 0)
                r_str = str(r_int)

            magic = bool(atk.get("magic") or it.get("magic"))
            node = bool(atk.get("node_attack") or it.get("node_attack"))
            shaft = bool(atk.get("shaft") or it.get("shaft"))
            push = _int(atk.get("push"), 0)

            ignore_block = _attack_base_ignore_block(it, atk) or bool(global_mods.ignore_block)

            conds: List[str] = []
            bc = _attack_base_condition(atk)
            if bc:
                conds.append(bc)
            conds.extend(list(global_mods.conditions))

            text = str(atk.get("text") or "").strip()

            # legacy per-attack mods from upgrades (attack_mods / mods.attack_lines)
            for up in wups:
                pam = _per_attack_mod_from_upgrade(up, idx)
                dice = _dice_add(dice, pam.dice)
                stam += int(pam.stamina_delta)
                conds.extend(list(pam.conditions))
                ignore_block = ignore_block or bool(pam.ignore_block)

            states.append(
                AttackState(
                    dice=dice,
                    stamina=stam,
                    range_str=r_str,
                    range_int=r_int,
                    magic=magic,
                    node=node,
                    shaft=shaft,
                    push=push,
                    ignore_block=ignore_block,
                    conditions=conds,
                    text=text,
                )
            )

        # v2 rules (deterministic targeting based on base arrays; conditions evaluated on current state).
        rule_sources: List[Dict[str, Any]] = []
        if isinstance(armor_obj, dict):
            rule_sources.append(armor_obj)
        rule_sources.extend([x for x in armor_upgrade_objs if isinstance(x, dict)])
        rule_sources.extend([x for x in wups if isinstance(x, dict)])

        all_rules: List[Dict[str, Any]] = []
        for src in rule_sources:
            all_rules.extend(_iter_v2_attack_rules(src))

        # Pass 1: apply all "set" effects so later "when" clauses can see them (e.g., magic).
        for rule in all_rules:
            set_eff = rule.get("set")
            if not isinstance(set_eff, dict) or not set_eff:
                continue
            targets = _rule_targets(rule, base_stamina=base_stamina, base_range_int=base_range_int)
            for i in targets:
                if i < 0 or i >= len(states):
                    continue
                st = states[i]
                if not _rule_when_ok(rule.get("when"), weapon=it, state=st):
                    continue
                if "magic" in set_eff:
                    st.magic = bool(set_eff.get("magic"))
                if "push" in set_eff:
                    st.push = max(int(st.push), 1) if bool(set_eff.get("push")) else 0
                if "ignore_block" in set_eff:
                    st.ignore_block = bool(set_eff.get("ignore_block"))

        # Pass 2: apply all "add" effects (dice/stamina/range).
        for rule in all_rules:
            add_eff = rule.get("add")
            if not isinstance(add_eff, dict) or not add_eff:
                continue
            targets = _rule_targets(rule, base_stamina=base_stamina, base_range_int=base_range_int)
            for i in targets:
                if i < 0 or i >= len(states):
                    continue
                st = states[i]
                if not _rule_when_ok(rule.get("when"), weapon=it, state=st):
                    continue

                if "stamina" in add_eff:
                    st.stamina += int(add_eff.get("stamina"))

                if "range" in add_eff:
                    if st.range_int is not None:
                        st.range_int = max(int(st.range_int) + int(add_eff.get("range")), 0)
                        st.range_str = str(st.range_int)

                dice_eff = add_eff.get("dice")
                if isinstance(dice_eff, dict):
                    st.dice = _dice_add(st.dice, _as_dice_dict(dice_eff))

                cond_eff = add_eff.get("conditions")
                if cond_eff is not None:
                    st.conditions.extend(_str_list(cond_eff))

        # Emit rows
        for idx, atk in enumerate(atks):
            atk = atk or {}
            st = states[idx]

            conds = list(st.conditions)
            if st.ignore_block:
                conds.append("ignore block")
            total_cond = _collapse_conditions(conds)

            stats = _dice_min_max_avg(st.dice)

            rows.append(
                {
                    "RowId": f"{iid}::atk::{idx}",
                    "Select": iid in selected_hand_ids,
                    "Item": name,
                    "Atk#": idx + 1,
                    "Stam": int(base_stamina[idx]),
                    "TotStam": int(st.stamina),
                    "Dice": _dice_icons(base_dice_by_idx[idx]),
                    "TotDice": _dice_icons(st.dice),
                    "TotMin": stats["min"],
                    "TotMax": stats["max"],
                    "TotAvg": stats["avg"],
                    "Cond": str(atk.get("condition") or "").strip(),
                    "TotCond": total_cond,
                    "Ign Blk": bool(st.ignore_block),
                    "Magic": bool(st.magic),
                    "Node": bool(st.node),
                    "Shaft": bool(st.shaft),
                    "Push": int(st.push),
                    "Range": st.range_str,
                    "Repeat": "" if _int(atk.get("repeat"), 0) == 0 else _int(atk.get("repeat"), 0),
                    "Text": st.text,
                }
            )

    return rows


def build_defense_totals(
    *,
    armor_obj: Optional[Dict[str, Any]],
    armor_upgrade_objs: List[Dict[str, Any]],
    hand_objs: List[Dict[str, Any]],
    weapon_upgrade_objs: List[Dict[str, Any]],
) -> DefenseTotals:
    block: DiceDict = {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}
    resist: DiceDict = {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}
    dodge_armor = 0

    if armor_obj:
        block = _dice_add(block, _as_dice_dict(armor_obj.get("block_dice") or {}))
        resist = _dice_add(resist, _as_dice_dict(armor_obj.get("resist_dice") or {}))
        dodge_armor = _int(armor_obj.get("dodge_dice"), 0)

    # equipped hand items contribute defense dice (mostly shields)
    for h in hand_objs:
        block = _dice_add(block, _as_dice_dict(h.get("block_dice") or {}))
        resist = _dice_add(resist, _as_dice_dict(h.get("resist_dice") or {}))

    # defense mods from armor upgrades + weapon upgrades (if present)
    dodge_mod = 0
    for o in list(armor_upgrade_objs) + list(weapon_upgrade_objs):
        bmod, rmod, dmod = _extract_defense_mods(o)
        block = _dice_add(block, bmod)
        resist = _dice_add(resist, rmod)
        dodge_mod += int(dmod)

    dodge_armor = max(dodge_armor + dodge_mod, 0)

    dodge_hand_max = 0
    for h in hand_objs:
        dodge_hand_max = max(dodge_hand_max, _hand_dodge_int(h))

    return DefenseTotals(block=block, resist=resist, dodge_armor=dodge_armor, dodge_hand_max=dodge_hand_max)


def expected_damage_taken(
    *,
    incoming_damage: int,
    dodge_dice: int,
    dodge_difficulty: int,
    defense_dice: DiceDict,
) -> Dict[str, float]:
    dmg = int(incoming_damage)
    n = max(int(dodge_dice), 0)
    diff = max(int(dodge_difficulty), 0)

    p_dodge = _dodge_success_prob(n, diff)
    exp_after_def = _expected_remaining_damage(dmg, defense_dice)
    exp_taken = (1.0 - p_dodge) * exp_after_def
    return {
        "p_dodge": float(p_dodge),
        "exp_after_def": float(exp_after_def),
        "exp_taken": float(exp_taken),
    }


# --- Cached wrappers (serialize inputs for stable cache keys) ---
def _to_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


@st.cache_data(show_spinner=False)
def _build_attack_totals_rows_cached_key(hand_items_json: str, selected_hand_ids_tuple: Tuple[str, ...], armor_json: str, armor_upgrade_json: str, weapon_upgrades_by_hand_json: str) -> List[Dict[str, Any]]:
    hand_items = json.loads(hand_items_json)
    selected_hand_ids = set(list(selected_hand_ids_tuple))
    armor_obj = json.loads(armor_json) if armor_json else None
    armor_upgrade_objs = json.loads(armor_upgrade_json) if armor_upgrade_json else []
    weapon_upgrades_by_hand = json.loads(weapon_upgrades_by_hand_json) if weapon_upgrades_by_hand_json else {}
    return build_attack_totals_rows(
        hand_items=hand_items,
        selected_hand_ids=selected_hand_ids,
        armor_obj=armor_obj,
        armor_upgrade_objs=armor_upgrade_objs,
        weapon_upgrades_by_hand=weapon_upgrades_by_hand,
    )


def build_attack_totals_rows_cached(
    *,
    hand_items: List[Dict[str, Any]],
    selected_hand_ids: Set[str],
    armor_obj: Optional[Dict[str, Any]],
    armor_upgrade_objs: List[Dict[str, Any]],
    weapon_upgrades_by_hand: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    return _build_attack_totals_rows_cached_key(
        _to_json(hand_items),
        tuple(sorted(list(selected_hand_ids or []))),
        _to_json(armor_obj) if armor_obj is not None else "",
        _to_json(armor_upgrade_objs),
        _to_json(weapon_upgrades_by_hand),
    )


@st.cache_data(show_spinner=False)
def _build_defense_totals_cached_key(armor_json: str, armor_upgrade_json: str, hand_objs_json: str, weapon_upgrades_json: str) -> Dict[str, Any]:
    armor_obj = json.loads(armor_json) if armor_json else None
    armor_upgrade_objs = json.loads(armor_upgrade_json) if armor_upgrade_json else []
    hand_objs = json.loads(hand_objs_json) if hand_objs_json else []
    weapon_upgrade_objs = json.loads(weapon_upgrades_json) if weapon_upgrades_json else []
    dt = build_defense_totals(
        armor_obj=armor_obj,
        armor_upgrade_objs=armor_upgrade_objs,
        hand_objs=hand_objs,
        weapon_upgrade_objs=weapon_upgrade_objs,
    )
    # Return serializable dict
    return {
        "block": dt.block,
        "resist": dt.resist,
        "dodge_armor": dt.dodge_armor,
        "dodge_hand_max": dt.dodge_hand_max,
    }


def build_defense_totals_cached(
    *,
    armor_obj: Optional[Dict[str, Any]],
    armor_upgrade_objs: List[Dict[str, Any]],
    hand_objs: List[Dict[str, Any]],
    weapon_upgrade_objs: List[Dict[str, Any]],
) -> DefenseTotals:
    res = _build_defense_totals_cached_key(
        _to_json(armor_obj) if armor_obj is not None else "",
        _to_json(armor_upgrade_objs),
        _to_json(hand_objs),
        _to_json(weapon_upgrade_objs),
    )
    return DefenseTotals(block=res["block"], resist=res["resist"], dodge_armor=int(res["dodge_armor"]), dodge_hand_max=int(res["dodge_hand_max"]))


@st.cache_data(show_spinner=False)
def expected_damage_taken_cached(incoming_damage: int, dodge_dice: int, dodge_difficulty: int, defense_dice_json: str) -> Dict[str, float]:
    defense_dice = json.loads(defense_dice_json) if defense_dice_json else {}
    return expected_damage_taken(
        incoming_damage=incoming_damage,
        dodge_dice=dodge_dice,
        dodge_difficulty=dodge_difficulty,
        defense_dice=defense_dice,
    )
