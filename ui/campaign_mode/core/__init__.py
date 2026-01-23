#ui/campaign_mode/core.py
from __future__ import annotations

import json
import streamlit as st
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from ui.event_mode.logic import V2_EXPANSIONS


ASSETS_DIR = Path("assets")
PARTY_TOKEN_PATH = ASSETS_DIR / "party_token.png"
SOULS_TOKEN_PATH = ASSETS_DIR / "souls_token.png"
BONFIRE_ICON_PATH = ASSETS_DIR / "bonfire.gif"
CHARACTERS_DIR = ASSETS_DIR / "characters"
V2_EXPANSIONS_SET = set(V2_EXPANSIONS)


_GRAVESTONES_PATH = Path("data/campaign_mode/encounter_gravestones.json")


@lru_cache(maxsize=16)
def _load_json_cached(path_str: str, mtime: float) -> Any:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _gravestones_mtime() -> float:
    try:
        return _GRAVESTONES_PATH.stat().st_mtime
    except FileNotFoundError:
        return -1.0


def _load_gravestones() -> dict[str, int]:
    mtime = _gravestones_mtime()
    if mtime < 0:
        return {}

    data = _load_json_cached(str(_GRAVESTONES_PATH), mtime)
    if not isinstance(data, dict):
        return {}

    out: dict[str, int] = {}
    for k, v in data.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            continue
    return out


class _LazyGravestonesMapping(Mapping[str, int]):
    def __getitem__(self, key: str) -> int:
        return _load_gravestones()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(_load_gravestones())

    def __len__(self) -> int:
        return len(_load_gravestones())

    def get(self, key: str, default: int = 0) -> int:  # noqa: A003
        return int(_load_gravestones().get(key, default) or 0)


ENCOUNTER_GRAVESTONES: Mapping[str, int] = _LazyGravestonesMapping()


def _card_w() -> int:
    s = st.session_state.get("user_settings") or {}
    w = int(st.session_state.get("ui_card_width", s.get("ui_card_width", 360)))
    return max(240, min(560, w))


# Persistence helpers (load/save paths) are provided by
# `ui.campaign_mode.persistence` and imported at module top.


def _default_sparks_max(player_count: int) -> int:
    # Campaign rule: party starts with (6 - player_num) sparks, clamped to at least 1.
    return max(1, 6 - player_count)


def _campaign_find_next_encounter_node(
    campaign: Dict[str, Any],
    from_node_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Find the next encounter node in campaign order after from_node_id.
    Skips bosses automatically by selecting only kind == "encounter".
    Returns the node dict (live reference inside campaign["nodes"]).
    """
    nodes = campaign.get("nodes") or []
    if not nodes or not from_node_id:
        return None

    start_idx = None
    for i, n in enumerate(nodes):
        if n.get("id") == from_node_id:
            start_idx = i
            break

    if start_idx is None:
        # If we can't find it, treat as "before start"
        start_idx = -1

    for n in nodes[start_idx + 1 :]:
        if n.get("kind") == "encounter":
            return n
    return None


def _describe_v1_node_label(campaign: Dict[str, Any], node: Dict[str, Any]) -> str:
    """
    Human-readable label for a campaign node.

    - Encounters: "Unknown Level X Encounter" until revealed, then show name.
    - Random bosses: "Unknown Mini/Main/Mega Boss" until revealed.
    - Fixed bosses: show their name immediately.
    """
    kind = node.get("kind")
    if kind == "bonfire":
        return "Bonfire"

    if kind == "encounter":
        level = node.get("level")
        frozen = node.get("frozen") or {}
        name = frozen.get("encounter_name")
        revealed = bool(node.get("revealed"))
        if revealed and name:
            return f"Level {level} Encounter: {name}"
        return f"Unknown Level {level} Encounter"

    if kind == "boss":
        stage = node.get("stage")
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name")
        was_random = bool(bosses_info.get("was_random"))
        revealed = bool(node.get("revealed")) or (boss_name and not was_random)

        prefix_map = {
            "mini": "Mini Boss",
            "main": "Main Boss",
            "mega": "Mega Boss",
        }
        prefix = prefix_map.get(stage, "Boss")

        if not boss_name:
            return f"{prefix}: None"

        if was_random and not revealed:
            if stage == "mini":
                return "Unknown Mini Boss"
            if stage == "main":
                return "Unknown Main Boss"
            if stage == "mega":
                return "Unknown Mega Boss"

        return f"{prefix}: {boss_name}"

    return "Unknown node"
 

def _describe_v2_node_label(campaign: Dict[str, Any], node: Dict[str, Any]) -> str:
    """
    Human-readable label for a V2 campaign node.

    - Encounters: show "Encounter Choice (Level X)" until a choice is made,
      then show the chosen encounter name.
    - Bosses / bonfire: same semantics as V1.
    """
    kind = node.get("kind")
    if kind == "bonfire":
        return "Bonfire"

    if kind == "encounter":
        level = node.get("level")
        options = node.get("options") or []
        choice_idx = node.get("choice_index")

        if (
            isinstance(choice_idx, int)
            and 0 <= choice_idx < len(options)
        ):
            frozen = options[choice_idx] or {}
            name = frozen.get("encounter_name") or "Unknown Encounter"
            return f"Level {level} Encounter: {name}"

        return f"Encounter Choice (Level {level})"

    if kind == "boss":
        stage = node.get("stage")
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name")
        was_random = bool(bosses_info.get("was_random"))
        revealed = bool(node.get("revealed")) or (boss_name and not was_random)

        prefix_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
        prefix = prefix_map.get(stage, "Boss")

        if not boss_name:
            return f"{prefix}: None"
        if was_random and not revealed:
            return f"Unknown {prefix}"
        return f"{prefix}: {boss_name}"

    return "Unknown node"


def _v2_get_current_stage(campaign: Dict[str, Any]) -> Optional[str]:
    """
    Determine the 'current chapter' (stage) for a V2 campaign.

    Priority:
      1. If the current node has a stage, use that.
      2. Otherwise, pick the first stage in (mini, main, mega) whose boss
         is not complete.
      3. If all bosses are complete, fall back to the last stage that exists.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    stage_order = ("mini", "main", "mega")

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    # If we're currently on an encounter or boss, use its stage directly
    if current_node is not None:
        stage = current_node.get("stage")
        if stage in stage_order:
            return stage

    # Otherwise, choose the first stage whose boss is not complete
    for stage in stage_order:
        boss = next(
            (
                n
                for n in nodes
                if n.get("stage") == stage and n.get("kind") == "boss"
            ),
            None,
        )
        if boss is None:
            continue
        if boss.get("status") != "complete":
            return stage

    # All bosses complete; fall back to the last stage that exists
    for stage in reversed(stage_order):
        if any(n.get("stage") == stage for n in nodes):
            return stage

    return None


def _record_dropped_souls(
    state: Dict[str, Any],
    failed_node_id: Optional[str],
    current_souls: int,
) -> None:
    """
    Record or clear a dropped-souls token in the campaign state.

    Only one node can have dropped souls at a time:
      - If failed_node_id is truthy and current_souls > 0, store the token there.
      - Otherwise clear any existing token.
    """
    if failed_node_id and current_souls > 0:
        state["souls_token_node_id"] = failed_node_id
        state["souls_token_amount"] = current_souls
    else:
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0


def _reset_all_encounters_on_bonfire_return(campaign: Dict[str, Any]) -> None:
    """
    Clear completion state from all encounter nodes when the party returns
    to the Bonfire.

    This does NOT touch shortcuts; flags such as 'shortcut_unlocked' stay
    in place so shortcuts remain valid on future runs.
    """
    nodes = campaign.get("nodes") or []
    for node in nodes:
        if node.get("kind") == "encounter" and node.get("status") == "complete":
            node["status"] = "incomplete"


def _v2_compute_allowed_destinations(campaign: Dict[str, Any]) -> Optional[set[str]]:
    """
    For V2 campaigns, compute the set of legal destinations under the movement rules.

    When standing on an encounter node:
      - you may always return to the bonfire
      - you may move to the next encounter/boss in the same stage,
        but only if the current encounter has been marked as complete

    When standing on the bonfire:
      - you may move only to the first encounter in the current chapter
      - or to any encounter in that chapter that has a shortcut unlocked

    For any other current node, return None to indicate no extra restrictions.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    if not current_node:
        return None

    kind = current_node.get("kind")

    # Case 1: standing on an encounter space
    if kind == "encounter":
        # Always allow returning to the bonfire
        allowed: set[str] = {"bonfire"}

        # If the encounter hasn't been marked complete yet, stop here
        if current_node.get("status") != "complete":
            return allowed

        # Otherwise, we can also go to the next encounter/boss in the same stage
        stage = current_node.get("stage")
        current_index = int(current_node.get("index"))

        next_node_id: Optional[str] = None
        next_index: Optional[int] = None

        for node in nodes:
            if node.get("stage") != stage:
                continue

            # Boss nodes have no "index"; treat them as coming after all encounters
            if node.get("kind") == "boss":
                idx = current_index + 1_000_000
            else:
                idx = int(node.get("index"))

            if idx <= current_index:
                continue

            if next_index is None or idx < next_index:
                next_index = idx
                next_node_id = node.get("id")

        if next_node_id:
            allowed.add(next_node_id)

        return allowed

    # Case 2: standing on the bonfire
    if kind == "bonfire":
        stage = _v2_get_current_stage(campaign)
        if stage is None:
            return None

        # Collect encounters in this stage with their index
        encounters: list[tuple[int, Dict[str, Any]]] = []
        for node in nodes:
            if node.get("kind") != "encounter" or node.get("stage") != stage:
                continue
            idx = int(node.get("index"))
            encounters.append((idx, node))

        if not encounters:
            return None

        # First encounter in the chapter
        encounters.sort(key=lambda t: t[0])
        first_encounter_node = encounters[0][1]
        allowed: set[str] = set()
        first_id = first_encounter_node.get("id")
        if first_id:
            allowed.add(first_id)

        # Any encounter in the current chapter that has an unlocked shortcut
        for idx, node in encounters[1:]:
            if not node.get("shortcut_unlocked"):
                continue
            node_id = node.get("id")
            if node_id:
                allowed.add(node_id)

        return allowed or None

    # Any other current node (e.g., boss): do not add extra restrictions
    return None
