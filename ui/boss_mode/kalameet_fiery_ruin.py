# ui/boss_mode/kalameet_aoe.py
from __future__ import annotations

import io
import random
from PIL import Image
from typing import Dict, List, Sequence, Tuple

from core.behavior.generation import render_behavior_card_cached
from core.behavior.assets import BEHAVIOR_CARDS_PATH, _behavior_image_path
from ui.boss_mode.aoe_pattern_utils import (
    NODE_COORDS,
    is_adjacent,
    is_diagonal,
    connected_under,
    _aoe_node_to_xy
)

Coord = Tuple[int, int]

BLACK_DRAGON_KALAMEET_NAME = "Black Dragon Kalameet"
KALAMEET_HELLFIRE_PREFIX = "Hellfire"
KALAMEET_FIERY_RUIN_NAME = "Fiery Ruin"

# ---------------------------------------------------------------------------
# Standard AoE patterns
#   Coords are (x, y) with 0-based rows & columns:
#     - "Rows 1–3" => x in {1, 2, 3}
#     - "Columns 1–3" => y in {1, 2, 3}
# ---------------------------------------------------------------------------

_KALAMEET_PATTERN_1: List[Coord] = [
    (0, 0),
    (1, 1),
    (0, 2),
    (2, 2),
    (1, 3),
    (3, 3),
    (0, 4),
    (2, 4),
    (4, 4),
    (1, 5),
    (3, 5),
    (5, 5),
    (2, 6),
    (4, 6),
    (6, 6),
]

_KALAMEET_PATTERN_2: List[Coord] = [
    (0, 0),
    (2, 0),
    (4, 0),
    (1, 1),
    (1, 3),
    (1, 5),
    (2, 2),
    (2, 4),
    (2, 6),
    (3, 3),
    (5, 3),
    (4, 4),
    (4, 6),
    (5, 5),
    (6, 6),
]


def _row_index(node: Coord) -> int:
    """Row index (0-based) == x coordinate."""
    return node[0]


def _col_index(node: Coord) -> int:
    """Column index (0-based) == y coordinate."""
    return node[1]


# 3) Rows 1–3  (x in {1, 2, 3})
_KALAMEET_PATTERN_ROWS_1_3: List[Coord] = [
    n for n in NODE_COORDS if 1 <= _row_index(n) <= 3
]

# 4) Rows 2–4  (x in {2, 3, 4})
_KALAMEET_PATTERN_ROWS_2_4: List[Coord] = [
    n for n in NODE_COORDS if 2 <= _row_index(n) <= 4
]

# 5) Rows 3–5  (x in {3, 4, 5})
_KALAMEET_PATTERN_ROWS_3_5: List[Coord] = [
    n for n in NODE_COORDS if 3 <= _row_index(n) <= 5
]

# 6) Columns 1–3  (y in {1, 2, 3})
_KALAMEET_PATTERN_COLS_1_3: List[Coord] = [
    n for n in NODE_COORDS if 1 <= _col_index(n) <= 3
]

# 7) Columns 2,4  (y in {2, 4})
_KALAMEET_PATTERN_COLS_2_4: List[Coord] = [
    n for n in NODE_COORDS if _col_index(n) in (2, 4)
]

# 8) Columns 3–5  (y in {3, 4, 5})
_KALAMEET_PATTERN_COLS_3_5: List[Coord] = [
    n for n in NODE_COORDS if 3 <= _col_index(n) <= 5
]

KALAMEET_STANDARD_PATTERNS: List[Dict[str, List[Coord]]] = [
    {"aoe": sorted(_KALAMEET_PATTERN_1)},
    {"aoe": sorted(_KALAMEET_PATTERN_2)},
    {"aoe": sorted(_KALAMEET_PATTERN_ROWS_1_3)},
    {"aoe": sorted(_KALAMEET_PATTERN_ROWS_2_4)},
    {"aoe": sorted(_KALAMEET_PATTERN_ROWS_3_5)},
    {"aoe": sorted(_KALAMEET_PATTERN_COLS_1_3)},
    {"aoe": sorted(_KALAMEET_PATTERN_COLS_2_4)},
    {"aoe": sorted(_KALAMEET_PATTERN_COLS_3_5)},
]


# ---------------------------------------------------------------------------
# Validity rules for generated patterns
#   - Single connected group (under is_adjacent)
#   - Each node has >= 2 adjacent AoE neighbours
#   - Each node has >= 1 diagonally-adjacent AoE neighbour
# ---------------------------------------------------------------------------

def _kalameet_pattern_is_valid(aoe_nodes: Sequence[Coord]) -> bool:
    aoe = set(aoe_nodes)
    if not aoe:
        return False

    # Per-node neighbour rules
    for n in aoe:
        adj_count = sum(
            1 for m in aoe
            if m is not n and is_adjacent(n, m)
        )
        diag_count = sum(
            1 for m in aoe
            if m is not n and is_diagonal(n, m)
        )
        if adj_count < 2 or diag_count < 1:
            return False

    # Single connected group
    if not connected_under(aoe, adjacency_fn=is_adjacent):
        return False

    return True


# ---------------------------------------------------------------------------
# Random AoE generation per slot (preserves node count)
# ---------------------------------------------------------------------------

def _kalameet_generate_random_aoe_for_slot(
    slot_index: int,
    rng: random.Random | None = None,
    max_attempts: int = 3000,
) -> List[Coord]:
    """
    Build a new AoE pattern for the given slot, preserving the number of nodes
    from the corresponding standard pattern.

    - Uses the shared NODE_COORDS grid.
    - Enforces _kalameet_pattern_is_valid.
    - Avoids exactly matching that slot's standard pattern.
    """
    if rng is None:
        rng = random.Random()

    base_aoe = KALAMEET_STANDARD_PATTERNS[slot_index]["aoe"]
    base_set = set(base_aoe)
    aoe_size = len(base_aoe)

    if aoe_size > len(NODE_COORDS):
        # Sanity fallback
        return list(base_aoe)

    for _ in range(max_attempts):
        aoe = rng.sample(NODE_COORDS, aoe_size)
        aoe_set = set(aoe)

        # Avoid exactly reproducing the printed pattern
        if aoe_set == base_set:
            continue

        if _kalameet_pattern_is_valid(aoe):
            return sorted(aoe)

    # Could not find anything valid; fall back to the base pattern
    return list(base_aoe)


# ---------------------------------------------------------------------------
# Public API for Boss Mode
#   Returns {"dest": (x, y), "aoe": [(x, y), ...]}
#   Destination node is always a randomly chosen AoE node.
# ---------------------------------------------------------------------------
def _kalameet_build_patterns(
    state: dict,
    mode: str,
    rng: random.Random | None = None,
) -> None:
    if rng is None:
        rng = random.Random()

    mode = mode.lower()

    n_slots = len(KALAMEET_STANDARD_PATTERNS)

    # Sequence: shuffled order of slots 0..7
    indices = list(range(n_slots))
    rng.shuffle(indices)
    state["kalameet_aoe_sequence"] = indices
    state["kalameet_aoe_index"] = 0

    # Build 8 patterns, one per standard slot
    patterns: List[Dict[str, List[Coord]]] = [None] * n_slots  # type: ignore

    for slot_index in range(n_slots):
        base_aoe = KALAMEET_STANDARD_PATTERNS[slot_index]["aoe"]

        if mode == "deck":
            aoe = list(base_aoe)
        else:
            aoe = _kalameet_generate_random_aoe_for_slot(slot_index, rng=rng)

        # Destination node is a randomly chosen AoE node (decided once per pattern)
        dest = rng.choice(aoe)
        patterns[slot_index] = {
            "dest": dest,
            "aoe": sorted(aoe),
        }

    state["kalameet_aoe_patterns"] = patterns
    state["kalameet_aoe_mode"] = mode


def _kalameet_next_pattern(state: dict, mode: str = "generated") -> Dict[str, object]:
    """
    Get the next AoE pattern Kalameet should use.

    mode:
        "deck"      -> use printed AoE patterns (with random dest per pattern)
        "generated" -> use pre-generated random AoE patterns

    On first use or when mode changes, it (re)builds the 8-pattern deck,
    then cycles through those patterns in a shuffled order.
    """
    rng = random.Random()
    mode = mode.lower()

    seq = state.get("kalameet_aoe_sequence")
    patterns = state.get("kalameet_aoe_patterns")
    current_mode = state.get("kalameet_aoe_mode")

    # Build or rebuild deck if missing / mismatched
    if (
        not seq
        or not patterns
        or len(patterns) != len(KALAMEET_STANDARD_PATTERNS)
        or current_mode != mode
    ):
        _kalameet_build_patterns(state, mode, rng=rng)
        seq = state["kalameet_aoe_sequence"]
        patterns = state["kalameet_aoe_patterns"]

    idx = state.get("kalameet_aoe_index", 0)
    slot_index = seq[idx]

    pattern = patterns[slot_index]

    # Advance pointer for next time
    state["kalameet_aoe_index"] = (idx + 1) % len(seq)

    # pattern already has both "dest" and "aoe"
    return {
        "dest": pattern["dest"],
        "aoe": list(pattern["aoe"]),
    }


def _kalameet_render_fiery_ruin(cfg, pattern):
    """
    Render the Fiery Ruin card with destination + AoE node icons overlaid.

    pattern is {"dest": (x, y), "aoe": [(x, y), ...]} using the shared NODE_COORDS grid.
    """
    base = render_behavior_card_cached(
        _behavior_image_path(cfg, KALAMEET_FIERY_RUIN_NAME),
        cfg.behaviors.get(KALAMEET_FIERY_RUIN_NAME, {}),
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
        # Last-ditch fallback: try to treat it as a file-like object
        base_img = Image.open(base).convert("RGBA")

    # Figure out where the assets directory is (parent of behavior cards)
    try:
        assets_dir = BEHAVIOR_CARDS_PATH.parent
    except Exception:
        from pathlib import Path
        assets_dir = Path(BEHAVIOR_CARDS_PATH).parent

    # Load icons
    aoe_icon_path = assets_dir / "behavior icons" / "aoe_node.png"
    dest_icon_path = assets_dir / "behavior icons" / "destination_node.png"

    aoe_icon = Image.open(aoe_icon_path).convert("RGBA")
    dest_icon = Image.open(dest_icon_path).convert("RGBA")

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    aoe_icon = aoe_icon.resize((250, 250), resample)
    dest_icon = dest_icon.resize((122, 122), resample)

    # Overlay destination node first
    dest = pattern.get("dest")
    if dest:
        x, y = _aoe_node_to_xy(dest, True)
        base_img.alpha_composite(dest_icon, dest=(x, y))

    # Overlay AoE nodes
    for coord in pattern.get("aoe", []):
        x, y = _aoe_node_to_xy(coord)
        base_img.alpha_composite(aoe_icon, dest=(x, y))

    return base_img
