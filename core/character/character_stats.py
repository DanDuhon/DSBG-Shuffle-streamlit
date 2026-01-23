from typing import Any, Dict, List, Optional, Tuple

# Tier labels
TIERS: List[str] = ["Base", "Tier 1", "Tier 2", "Tier 3"]
STAT_KEYS = ("str", "dex", "itl", "fth")

# Per-character stat values at each tier
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

# Souls cost per single-tier upgrade
UPGRADE_COSTS = [2, 4, 8]  # base->1, 1->2, 2->3


def _normalize_stat_key(k: str) -> str:
    k = (k or "").strip().lower()
    if k in ("strength", "str"):
        return "str"
    if k in ("dexterity", "dex"):
        return "dex"
    if k in ("intelligence", "itl", "int"):
        return "itl"
    if k in ("faith", "fth"):
        return "fth"
    raise KeyError(f"Unknown stat key: {k}")


def souls_to_upgrade(from_tier: int, to_tier: int) -> int:
    """Return total souls required to upgrade from from_tier to to_tier (exclusive of from_tier).

    Example: from 0 to 2 = cost for 0->1 + 1->2 (2 + 4 = 6)
    """
    if to_tier <= from_tier:
        return 0
    total = 0
    for i in range(from_tier, to_tier):
        if i < 0 or i >= len(UPGRADE_COSTS):
            continue
        total += UPGRADE_COSTS[i]
    return total


def souls_needed_for_value(class_name: str, stat: str, current_tier: int, required_value: int) -> Optional[Tuple[int, int]]:
    """Compute minimal souls needed to reach at least `required_value` for `stat` on `class_name`.

    Returns a tuple (souls_required, resulting_tier_index). If requirement already met returns (0, current_tier).
    If requirement cannot be met (even at Tier 3) returns None.
    """
    sk = _normalize_stat_key(stat)
    cfg = CLASS_TIERS.get(class_name)
    if not cfg:
        return None
    arr = cfg.get(sk)
    if not arr:
        return None
    current_tier = max(0, min(current_tier, len(arr) - 1))
    # If already sufficient
    if arr[current_tier] >= required_value:
        return 0, current_tier
    # Find minimal tier that meets requirement
    target_tier = None
    for ti in range(current_tier + 1, len(arr)):
        if arr[ti] >= required_value:
            target_tier = ti
            break
    if target_tier is None:
        return None
    cost = souls_to_upgrade(current_tier, target_tier)
    return cost, target_tier


def souls_needed_for_item_for_character(class_name: str, tier_indices: Dict[str, int], item_requirements: Dict[str, int]) -> Optional[int]:
    """Compute total souls required for a character to meet all stat requirements of an item.

    - `tier_indices` maps stat keys ('str','dex','itl','fth') to current tier indices (0-3).
    - `item_requirements` maps stat names (e.g. 'strength' or 'str') to required numeric values.

    Returns total souls required (sum across stats) or None if any requirement is unreachable.
    """
    total = 0
    for k, req in (item_requirements or {}).items():
        sk = _normalize_stat_key(k)
        cur_t = int(tier_indices.get(sk, 0))
        res = souls_needed_for_value(class_name, sk, cur_t, int(req))
        if res is None:
            return None
        cost, _ = res
        total += cost
    return total


def average_souls_to_equip(party: List[Dict[str, Any]], item_requirements: Dict[str, int]) -> Dict[str, Any]:
    """Given a party (list of members) compute per-member and average souls to equip item.

    Each party member should be a dict containing at least:
      - 'class_name': str
      - 'tier_indices': dict mapping 'str','dex','itl','fth' to ints

    Returns dict with keys:
      - 'per_member': list of tuples (class_name, souls_or_None)
      - 'average': float or None (None if no member can equip)
      - 'sum': int sum of souls for reachable members
    """
    per = []
    total = 0
    count = 0
    for m in party:
        cn = m.get("class_name")
        tiers = m.get("tier_indices", {})
        cost = souls_needed_for_item_for_character(cn, tiers, item_requirements)
        per.append((cn, cost))
        if cost is not None:
            total += cost
            count += 1
    avg = (total / count) if count > 0 else None
    return {"per_member": per, "average": avg, "sum": total}
