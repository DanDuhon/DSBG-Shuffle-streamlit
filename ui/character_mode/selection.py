from typing import Any, Dict, List


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