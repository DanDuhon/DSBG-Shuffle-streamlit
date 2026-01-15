# ui/boss_mode/guardian_dragon_fiery_breath.py
import io
import random
from typing import Sequence, Tuple

from PIL import Image

from core.behavior.generation import render_behavior_card_cached
from core.behavior.assets import BEHAVIOR_CARDS_PATH, _behavior_image_path
from ui.boss_mode.aoe_pattern_utils import (
    NODE_COORDS,
    is_adjacent,
    is_diagonal,
    connected_under,
    generate_random_pattern_for_dest,
    _aoe_node_to_xy
)


Coord = Tuple[int, int]

GUARDIAN_DRAGON_NAME = "Guardian Dragon"
GUARDIAN_FIERY_BREATH_NAME = "Fiery Breath"
GUARDIAN_CAGE_PREFIX = "Cage Grasp Inferno"
GUARDIAN_FIERY_DECK_SIZE = 4

# Same 4 standard printed patterns as before.
GUARDIAN_STANDARD_PATTERNS = [
    {
        "dest": (0, 0),
        "aoe": [
            (2, 0),
            (1, 1),
            (0, 2),
            (1, 3),
            (2, 2),
            (3, 1),
            (3, 3),
        ],
    },
    {
        "dest": (6, 0),
        "aoe": [
            (4, 0),
            (3, 1),
            (5, 1),
            (4, 2),
            (6, 2),
            (3, 3),
            (5, 3),
        ],
    },
    {
        "dest": (6, 6),
        "aoe": [
            (4, 6),
            (3, 5),
            (5, 5),
            (4, 4),
            (6, 4),
            (3, 3),
            (5, 3),
        ],
    },
    {
        "dest": (0, 6),
        "aoe": [
            (2, 6),
            (1, 5),
            (3, 5),
            (0, 4),
            (2, 4),
            (1, 3),
            (3, 3),
        ],
    },
]


def _guardian_pattern_is_valid(dest: Coord, aoe_nodes: Sequence[Coord]) -> bool:
    """
    Guardian-specific global rules for a Fiery Breath AoE pattern:

    1. Destination node is not part of AoE.
    2. Each AoE node has at least 2 adjacent AoE neighbors.
    3. Each AoE node has at least 1 diagonally-adjacent AoE neighbor.
    4. At least 2 AoE nodes are adjacent to the destination node.
    5. All AoE nodes form a single connected group under adjacency.
    """
    aoe = set(aoe_nodes)

    # 1. Destination node can't be AoE.
    if dest in aoe:
        return False

    # 4. At least 2 AoE nodes adjacent to destination.
    adj_to_dest = sum(1 for n in aoe if is_adjacent(dest, n))
    if adj_to_dest < 2:
        return False

    # 2 & 3. Per-node neighbor rules.
    for n in aoe:
        adj_count = sum(
            1 for m in aoe
            if m != n and is_adjacent(n, m)
        )
        diag_count = sum(
            1 for m in aoe
            if m != n and is_diagonal(n, m)
        )
        if adj_count < 2 or diag_count < 1:
            return False

    # 5. Single connected group under adjacency.
    if not aoe:
        return False

    if not connected_under(aoe, adjacency_fn=is_adjacent):
        # There is more than one disconnected AoE blob.
        return False

    return True


def _guardian_generate_random_pattern_for_dest(dest, base_pattern, rng=None, max_attempts: int = 2000):
    """
    Build a full AoE pattern from scratch for the given destination.

    - Uses the shared grid (NODE_COORDS).
    - Uses Guardian-specific validity rules.
    - Avoids exactly matching the printed base pattern when possible.
    """
    return generate_random_pattern_for_dest(
        dest=dest,
        base_pattern=base_pattern,
        validate_fn=_guardian_pattern_is_valid,
        node_coords=NODE_COORDS,
        aoe_size=len(base_pattern["aoe"]),
        max_dist=6,
        rng=rng,
        max_attempts=max_attempts,
        avoid_base=True,
    )


def _guardian_fiery_init_sequence(state: dict):
    """
    Choose and freeze the destination order for the whole fight.
    This order loops but never changes until the fight is reset.
    """
    rng = random.Random()

    indices = list(range(len(GUARDIAN_STANDARD_PATTERNS)))  # 0,1,2,3
    rng.shuffle(indices)

    state["guardian_fiery_sequence"] = indices
    state["guardian_fiery_index"] = 0


def _guardian_fiery_build_patterns(state: dict, mode: str, rng=None) -> None:
    """
    Build a 4-card Fiery Breath deck for the current fight.

    - The destination order (guardian_fiery_sequence) is fixed for the fight.
    - For each of the 4 slots we cache a pattern:
        * mode == "deck": use the printed AoE pattern
        * mode == "generated": use a randomly generated valid AoE pattern
    """
    if rng is None:
        rng = random.Random()

    mode = mode.lower()

    # Ensure we have a fixed destination order for this fight
    seq = state.get("guardian_fiery_sequence")
    if not seq or len(seq) != len(GUARDIAN_STANDARD_PATTERNS):
        _guardian_fiery_init_sequence(state)
        seq = state["guardian_fiery_sequence"]

    n_slots = len(GUARDIAN_STANDARD_PATTERNS)
    patterns = [None] * n_slots  # type: ignore

    for slot_index in range(n_slots):
        base = GUARDIAN_STANDARD_PATTERNS[slot_index]
        dest = base["dest"]

        if mode == "deck":
            pattern = {"dest": dest, "aoe": list(base["aoe"])}
        else:
            pattern = _guardian_generate_random_pattern_for_dest(dest, base, rng=rng)

        patterns[slot_index] = pattern

    state["guardian_fiery_patterns"] = patterns
    state["guardian_fiery_mode"] = mode


def _guardian_fiery_next_pattern(state: dict, mode: str):
    """
    Advance to the next destination in the fixed sequence and return a pattern.

    mode == "deck"      -> use printed AoE pattern for that dest
    mode == "generated" -> use a pre-generated 4-card AoE deck
    """
    rng = random.Random()
    mode = mode.lower()

    seq = state.get("guardian_fiery_sequence")
    patterns = state.get("guardian_fiery_patterns")
    current_mode = state.get("guardian_fiery_mode")

    # Build/rebuild the 4-card deck if needed (missing / wrong size / mode changed)
    if (
        not seq
        or not patterns
        or len(patterns) != len(GUARDIAN_STANDARD_PATTERNS)
        or current_mode != mode
    ):
        _guardian_fiery_build_patterns(state, mode, rng=rng)
        seq = state["guardian_fiery_sequence"]
        patterns = state["guardian_fiery_patterns"]

    idx = state.get("guardian_fiery_index", 0)
    pattern_idx = seq[idx]
    pattern = patterns[pattern_idx]

    # Advance index but keep the sequence fixed; loop through 0..3 repeatedly.
    idx = (idx + 1) % len(seq)
    state["guardian_fiery_index"] = idx

    # Return a shallow copy so callers don't accidentally mutate cached state
    return {
        "dest": pattern["dest"],
        "aoe": list(pattern["aoe"]),
    }


def _guardian_render_fiery_breath(cfg, pattern):
    """
    Render the Fiery Breath card with destination + AoE node icons overlaid.

    pattern is {"dest": (x, y), "aoe": [(x, y), ...]} using the shared NODE_COORDS grid.
    """
    base = render_behavior_card_cached(
        _behavior_image_path(cfg, GUARDIAN_FIERY_BREATH_NAME),
        cfg.behaviors.get(GUARDIAN_FIERY_BREATH_NAME, {}),
        is_boss=True,
    )

    # Convert cached output to a PIL Image we can edit.
    if isinstance(base, Image.Image):
        base_img = base.convert("RGBA")
    elif isinstance(base, (bytes, bytearray)):
        base_img = Image.open(io.BytesIO(base)).convert("RGBA")
    elif isinstance(base, str):
        base_img = Image.open(base).convert("RGBA")

    assets_dir = BEHAVIOR_CARDS_PATH.parent

    # Load icons
    aoe_icon_path = assets_dir / "behavior icons" / "aoe_node.png"
    dest_icon_path = assets_dir / "behavior icons" / "destination_node.png"

    aoe_icon = Image.open(aoe_icon_path).convert("RGBA")
    dest_icon = Image.open(dest_icon_path).convert("RGBA")

    resample = Image.Resampling.LANCZOS

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
