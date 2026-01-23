from typing import Any, Dict, List, Optional, Set
from ui.character_mode.attacks import _attack_has_dice
from ui.character_mode.item_fields import (
    _armor_dodge_int,
    _armor_has_special_rules,
    _armor_upgrade_slots_int,
    _hand_dodge_int,
    _hand_hands_required_int,
    _hand_range_str,
    _hand_upgrade_slots_int,
    _immunities_set,
    _is_legendary,
    _item_expansions,
    _item_requirements,
    _meets_requirements,
    _src_str
)


def _hand_has_attacks_with_dice(item: Dict[str, Any]) -> bool:
    atks = item.get("attacks") or []
    if not isinstance(atks, list) or not atks:
        return False
    return any(_attack_has_dice(a or {}) for a in atks)


def _hand_any_attack_pred(item: Dict[str, Any], pred) -> bool:
    for atk in (item.get("attacks") or []):
        if pred(atk):
            return True
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



def _hand_has_ignore_block(item: Dict[str, Any]) -> bool:
    if bool(item.get("ignore_block")):
        return True
    return _hand_any_attack_pred(item, lambda a: bool((a or {}).get("ignore_block")))

def _hand_has_shift_before(item: Dict[str, Any]) -> bool:
    return _hand_any_attack_pred(
        item,
        lambda a: int(a.get("shift_before") or 0) != 0,
    )


def _hand_has_shift_after(item: Dict[str, Any]) -> bool:
    return _hand_any_attack_pred(
        item,
        lambda a: int(a.get("shift_after") or 0) != 0,
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


def _apply_hand_item_filters(
    items: List[Dict[str, Any]],
    *,
    categories: Optional[Set[str]],
    hands_required: Optional[Set[int]],
    only_twohand_compatible_shields: bool,
    dodge: Optional[Set[int]],
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

        if dodge is not None and _hand_dodge_int(it) not in dodge:
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


_HAND_FEATURE_PRED = {
    "magic": _hand_has_magic,
    "node_attack": _hand_has_node_attack,
    "push": _hand_has_push,
    "shaft": _hand_has_shaft,
    "shift_before": _hand_has_shift_before,
    "shift_after": _hand_has_shift_after,
    "repeat": _hand_has_repeat,
    "stamina_recovery": _hand_has_stamina_recovery,
    "heal": _hand_has_heal,
    "ignore_block": _hand_has_ignore_block,
}