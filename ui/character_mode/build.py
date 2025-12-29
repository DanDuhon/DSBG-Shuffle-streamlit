from typing import Any, Dict, List, Set
from ui.character_mode.constants import TIERS, CLASS_TIERS, STAT_LABEL
from ui.character_mode.item_fields import _item_expansions, _item_requirements, _name, _upgrade_slots, _slot_cost, _extra_upgrade_slots


def _tier_index(label: str) -> int:
    return TIERS.index(label)


def _build_stats(class_name: str, tier_indices: Dict[str, int]) -> Dict[str, int]:
    cfg = CLASS_TIERS[class_name]
    out: Dict[str, int] = {}
    for k in ("str", "dex", "itl", "fth"):
        idx = int(tier_indices.get(k, 0) or 0)
        idx = 0 if idx < 0 else 3 if idx > 3 else idx
        out[k] = int(cfg[k][idx])
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