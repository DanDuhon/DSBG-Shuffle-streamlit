from __future__ import annotations

import io
import random
from typing import Dict, List, Sequence, Tuple

from PIL import Image
from pathlib import Path

from core.behavior.generation import render_behavior_card_cached
from core.behavior.assets import BEHAVIOR_CARDS_PATH, _behavior_image_path
from ui.boss_mode.aoe_pattern_utils import (
    NODE_COORDS,
    is_adjacent,
    connected_under,
    generate_random_pattern_for_dest,
    _aoe_node_to_xy,
)
import streamlit as st
from ui.boss_mode.aoe_pattern_utils import candidate_nodes_for_dest, manhattan
from core.ngplus import get_current_ngplus_level
from ui.boss_mode.data.json_tables import LazyJsonSequence, boss_mode_data_path

Coord = Tuple[int, int]

OLD_IRON_KING_NAME = "Old Iron King"
OIK_BLASTED_NODES_NAME = "Blasted Nodes"
OIK_FIRE_BEAM_PREFIX = "Fire Beam"
OIK_BLASTED_DECK_SIZE = 6

# ---------------------------------------------------------------------------
# OIK grid: base NODE_COORDS minus the nodes that don't exist on the tile
# ---------------------------------------------------------------------------

_MISSING_OIK_NODES = {
    (2, 0),
    (4, 0),
    (0, 2),
    (6, 2),
    (0, 4),
    (6, 4),
}

OIK_NODE_COORDS: List[Coord] = [
    c for c in NODE_COORDS if c not in _MISSING_OIK_NODES
]

# ---------------------------------------------------------------------------
# Printed Blasted Nodes patterns (JSON-backed)
# Coordinates are (x, y); destination node is included in the AoE list.
# ---------------------------------------------------------------------------

OIK_STANDARD_PATTERNS = LazyJsonSequence(
    boss_mode_data_path("old_iron_king_blasted_nodes_standard_patterns.json")
)

# ---------------------------------------------------------------------------
# Validity rules
#   1) All AoE nodes form a single connected group under is_adjacent
#   2) Destination node is always in the AoE
# ---------------------------------------------------------------------------

def _oik_pattern_is_valid(dest: Coord, aoe_nodes_wo_dest: Sequence[Coord]) -> bool:
    """
    OIK global rule for Blasted Nodes patterns:

    - All AoE nodes + the destination form a single connected group.
    """
    aoe = set(aoe_nodes_wo_dest)
    if not aoe:
        return False

    full = aoe | {dest}
    return connected_under(full, adjacency_fn=is_adjacent)


def _component_from_dest(dest: Coord, nodes: Sequence[Coord]) -> Sequence[Coord]:
    """
    Take the connected component reachable from `dest` under `is_adjacent`.
    Used as a last-resort cleanup to strip out islands like (0, 6).
    """
    node_set = set(nodes)
    if dest not in node_set:
        node_set.add(dest)

    visited = set()
    stack = [dest]

    while stack:
        v = stack.pop()
        if v in visited:
            continue
        visited.add(v)
        for m in node_set:
            if m not in visited and is_adjacent(v, m):
                stack.append(m)

    return sorted(visited)


def _oik_generate_random_pattern_for_dest(
    dest: Coord,
    base_pattern: dict,
    rng: random.Random | None = None,
    max_attempts: int = 2000,
) -> dict:
    """
    Build a Blasted Nodes AoE for Old Iron King:

    - Uses OIK_NODE_COORDS (tile-specific grid).
    - Destination *must* be part of the pattern.
    - AoE nodes must all be in the same group with the dest.
    """
    if rng is None:
        rng = random.Random()

    base_aoe = list(base_pattern["aoe"])
    # For generation, we treat dest as special and keep it out of the sampled list.
    base_aoe_wo_dest = [n for n in base_aoe if n != dest]

    raw = generate_random_pattern_for_dest(
        dest=dest,
        base_pattern={"aoe": base_aoe_wo_dest},
        validate_fn=_oik_pattern_is_valid,
        node_coords=OIK_NODE_COORDS,
        aoe_size=len(base_aoe_wo_dest),
        max_dist=6,
        rng=rng,
        max_attempts=max_attempts,
        avoid_base=True,
    )

    # Rebuild full AoE: sampled nodes + destination
    aoe_wo_dest = list(raw["aoe"])
    full_aoe = set(aoe_wo_dest) | {dest}

    # Final sanity check: if the pattern is somehow still invalid
    # (e.g., we fell back to something with an island), trim to the
    # connected component containing the destination.
    if not connected_under(full_aoe, adjacency_fn=is_adjacent):
        full_aoe = set(_component_from_dest(dest, full_aoe))

    return {
        "dest": dest,
        "aoe": sorted(full_aoe),
    }


# ---------------------------------------------------------------------------
# Deck building & sequencing
#   - 6-card Blasted Nodes deck
#   - Always 2 patterns per destination node (1,3), (5,3), (3,1)
# ---------------------------------------------------------------------------

def _oik_blasted_build_patterns(
    state: dict,
    mode: str,
    rng: random.Random | None = None,
) -> None:
    if rng is None:
        rng = random.Random()

    mode = mode.lower()

    n_slots = len(OIK_STANDARD_PATTERNS)
    patterns: List[Dict[str, object]] = [None] * n_slots  # type: ignore

    for slot_index, base in enumerate(OIK_STANDARD_PATTERNS):
        dest: Coord = base["dest"]
        base_aoe: List[Coord] = base["aoe"]

        if mode == "deck":
            # Use printed pattern as-is (if you really want that)
            pattern = {"dest": dest, "aoe": list(base_aoe)}
        else:
            pattern = _oik_generate_random_pattern_for_dest(dest, base, rng=rng)

        patterns[slot_index] = pattern

    # Sequence: shuffled order of the 6 slots; still 2 per dest.
    indices = list(range(n_slots))
    rng.shuffle(indices)

    state["oik_blasted_patterns"] = patterns
    state["oik_blasted_sequence"] = indices
    state["oik_blasted_index"] = 0
    state["oik_blasted_mode"] = mode


def _oik_blasted_next_pattern(state: dict, mode: str = "generated") -> Dict[str, object]:
    """
    Get the next Blasted Nodes pattern for Old Iron King.

    mode:
        "deck"      -> use printed Blasted Nodes patterns
        "generated" -> use pre-generated random AoE patterns
    """
    rng = random.Random()
    mode = mode.lower()

    seq = state.get("oik_blasted_sequence")
    patterns = state.get("oik_blasted_patterns")
    current_mode = state.get("oik_blasted_mode")

    if (
        not seq
        or not patterns
        or len(patterns) != len(OIK_STANDARD_PATTERNS)
        or current_mode != mode
    ):
        _oik_blasted_build_patterns(state, mode, rng=rng)
        seq = state["oik_blasted_sequence"]
        patterns = state["oik_blasted_patterns"]

    idx = state.get("oik_blasted_index", 0)
    slot_index = seq[idx]

    pattern = patterns[slot_index]

    # advance pointer for next time
    state["oik_blasted_index"] = (idx + 1) % len(seq)

    # shallow copy so callers can't mutate cached state
    return {
        "dest": pattern["dest"],
        "aoe": list(pattern["aoe"]),
    }


# ---------------------------------------------------------------------------
# Rendering Blasted Nodes with overlay
# ---------------------------------------------------------------------------

def _oik_render_blasted_nodes(cfg, pattern: Dict[str, object]) -> Image.Image:
    """
    Render the Blasted Nodes card with destination + AoE node icons overlaid.

    pattern is {"dest": (x, y), "aoe": [(x, y), ...]}
    """
    base = render_behavior_card_cached(
        _behavior_image_path(cfg, OIK_BLASTED_NODES_NAME),
        cfg.behaviors.get(OIK_BLASTED_NODES_NAME, {}),
        is_boss=True,
    )

    # Convert cached output to a PIL Image we can edit.
    if isinstance(base, Image.Image):
        base_img = base.convert("RGBA")
    elif isinstance(base, (bytes, bytearray)):
        base_img = Image.open(io.BytesIO(base)).convert("RGBA")
    elif isinstance(base, str):
        base_img = Image.open(base).convert("RGBA")
    else:
        base_img = Image.open(base).convert("RGBA")

    assets_dir = Path(BEHAVIOR_CARDS_PATH).parent

    # Load icons
    aoe_icon_path = assets_dir / "behavior icons" / "aoe_node.png"
    dest_icon_path = assets_dir / "behavior icons" / "destination_node.png"

    aoe_icon = Image.open(aoe_icon_path).convert("RGBA")
    dest_icon = Image.open(dest_icon_path).convert("RGBA")

    resample = Image.Resampling.LANCZOS

    aoe_icon = aoe_icon.resize((250, 250), resample)
    dest_icon = dest_icon.resize((122, 122), resample)

    # Destination node
    dest = pattern.get("dest")
    if dest:
        x, y = _aoe_node_to_xy(dest, True)
        base_img.alpha_composite(dest_icon, dest=(x, y))

    aoe_nodes = list(pattern.get("aoe", []))
    ng_level = get_current_ngplus_level()
    increase_enabled = bool(st.session_state.get("ngplus_increase_nodes", False))
    if increase_enabled and ng_level > 0:
        # NG+ extra nodes mapping for levels 1..5: [1,1,2,2,3]
        extra_map = [0, 1, 1, 2, 2, 3]
        lvl = max(0, min(int(ng_level), len(extra_map) - 1))
        extra = extra_map[lvl]
        target = len(aoe_nodes) + extra
        candidates = candidate_nodes_for_dest(pattern.get("dest"), node_coords=OIK_NODE_COORDS)
        candidates = [c for c in candidates if c not in aoe_nodes and c != pattern.get("dest")]
        candidates.sort(key=lambda n: min(manhattan(n, a) for a in aoe_nodes) if aoe_nodes else 0)
        for c in candidates:
            if len(aoe_nodes) >= target:
                break
            new_set = set(aoe_nodes) | {c}
            if connected_under(new_set, adjacency_fn=is_adjacent):
                aoe_nodes.append(c)

    for coord in aoe_nodes:
        x, y = _aoe_node_to_xy(coord)
        base_img.alpha_composite(aoe_icon, dest=(x, y))

    return base_img
