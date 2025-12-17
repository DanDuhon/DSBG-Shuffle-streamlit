# ui/boss_mode/executioners_chariot_death_race.py
from __future__ import annotations

import io
import random
from typing import Dict, List, Sequence, Tuple

from PIL import Image

from core.behavior.generation import render_behavior_card_cached
from core.behavior.assets import BEHAVIOR_CARDS_PATH
from ui.boss_mode.aoe_pattern_utils import (
    NODE_COORDS,
    is_adjacent,
    is_diagonal,
    connected_under,
    candidate_nodes_for_dest,
    _aoe_node_to_xy,
)

Coord = Tuple[int, int]

EXECUTIONERS_CHARIOT_NAME = "Executioner's Chariot"
DEATH_RACE_BEHAVIOR_NAME = "Death Race"  # name in cfg.behaviors
DEATH_RACE_DECK_SIZE = 4

# ---------------------------------------------------------------------------
# EC tile grid: shared node grid minus the missing (3, 3) node
# ---------------------------------------------------------------------------

EC_NODE_COORDS: List[Coord] = [c for c in NODE_COORDS if c != (3, 3)]

# ---------------------------------------------------------------------------
# Base printed patterns (one per destination)
#
# Your spec:
#   [{"pattern": [(1,1),(2,0),(4,0),(3,1),(5,1)], "start": (5,1), "destination": (1,1)},
#    {"pattern": [(1,1),(0,2),(1,3),(0,4),(1,5)], "start": (1,1), "destination": (1,5)},
#    {"pattern": [(1,5),(2,6),(3,5),(4,6),(5,5)], "start": (1,5), "destination": (5,5)},
#    {"pattern": [(5,1),(6,2),(5,3),(6,4),(5,5)], "start": (5,5), "destination": (5,1)}]
# ---------------------------------------------------------------------------

EC_STANDARD_PATTERNS: List[Dict[str, object]] = [
    {
        "dest": (1, 1),
        "start": (5, 1),
        "aoe": [(1, 1), (2, 0), (4, 0), (3, 1), (5, 1)],
    },
    {
        "dest": (1, 5),
        "start": (1, 1),
        "aoe": [(1, 1), (0, 2), (1, 3), (0, 4), (1, 5)],
    },
    {
        "dest": (5, 5),
        "start": (1, 5),
        "aoe": [(1, 5), (2, 6), (3, 5), (4, 6), (5, 5)],
    },
    {
        "dest": (5, 1),
        "start": (5, 5),
        "aoe": [(5, 1), (6, 2), (5, 3), (6, 4), (5, 5)],
    },
]


# ---------------------------------------------------------------------------
# Validity rules
#   - All AoE nodes form a single connected group under is_adjacent
#   - Start node is always an AoE node
#   - Destination node is always an AoE node
#   - All AoE nodes form a single connected group under diagonal adjacency
#     (you can walk between any two AoE nodes using only diagonal steps)
# ---------------------------------------------------------------------------

def _ec_pattern_is_valid(dest: Coord, start: Coord, aoe_nodes: Sequence[Coord]) -> bool:
    aoe = set(aoe_nodes)
    if not aoe:
        return False

    # Start and dest must be in the AoE.
    if start not in aoe or dest not in aoe:
        return False

    # Single connected group under the usual adjacency rule
    # (your "distance < 4" style via is_adjacent).
    if not connected_under(aoe, adjacency_fn=is_adjacent):
        return False

    # Also require that the AoE is a single group under *diagonal* adjacency.
    # This is what kills shapes like:
    #   [(0, 2), (1, 1), (2, 0), (4, 0), (5, 1)]
    # which split into two diagonal clusters.
    if not connected_under(aoe, adjacency_fn=is_diagonal):
        return False

    return True


# ---------------------------------------------------------------------------
# Random AoE generation for a given (start, dest)
#   - Uses EC_NODE_COORDS (no (3,3))
#   - Keeps AoE size the same as the printed pattern
#   - Ensures validity rules and tries not to exactly match the base pattern
# ---------------------------------------------------------------------------

def _ec_generate_random_pattern_for_dest(
    dest: Coord,
    start: Coord,
    base_pattern: Dict[str, object],
    rng: random.Random | None = None,
    max_attempts: int = 2000,
    max_dist: int = 6,
) -> Dict[str, object]:
    if rng is None:
        rng = random.Random()

    base_aoe = list(base_pattern["aoe"])  # type: ignore
    base_set = set(base_aoe)
    aoe_size = len(base_aoe)

    if aoe_size <= 0:
        return {
            "dest": dest,
            "start": start,
            "aoe": base_aoe,
        }

    # Candidate nodes near the destination (excluding dest by default)
    candidates = candidate_nodes_for_dest(
        dest,
        node_coords=EC_NODE_COORDS,
        max_dist=max_dist,
    )

    # Ensure the start is in the candidate list.
    if start not in candidates and start in EC_NODE_COORDS:
        candidates.append(start)

    # We'll always include dest + start; we only sample the remaining nodes.
    mandatory = {dest, start}
    pool = [n for n in candidates if n not in mandatory]

    remaining = aoe_size - len(mandatory)
    if remaining < 0:
        # If base pattern somehow has fewer than 2 nodes, just use it.
        return {
            "dest": dest,
            "start": start,
            "aoe": base_aoe,
        }

    if remaining > len(pool):
        # Not enough candidates to build a full pattern; fall back to base.
        return {
            "dest": dest,
            "start": start,
            "aoe": base_aoe,
        }

    for _ in range(max_attempts):
        extra = rng.sample(pool, remaining)
        aoe = list(mandatory) + extra

        # Avoid exactly reproducing the printed pattern if we can.
        if set(aoe) == base_set:
            continue

        if _ec_pattern_is_valid(dest, start, aoe):
            return {
                "dest": dest,
                "start": start,
                "aoe": sorted(aoe),
            }

    # If we couldn't find a valid alternative, fall back to the printed pattern.
    return {
        "dest": dest,
        "start": start,
        "aoe": base_aoe,
    }


# ---------------------------------------------------------------------------
# Deck building and iteration
#
# - There are exactly 4 Death Race cards.
# - The card order is fixed and matches EC_STANDARD_PATTERNS as written:
#
#   Card 1: start (5,1) -> dest (1,1)
#   Card 2: start (1,1) -> dest (1,5)
#   Card 3: start (1,5) -> dest (5,5)
#   Card 4: start (5,5) -> dest (5,1)
#
# - Mode "deck": use the printed AoE pattern for each card.
# - Mode "generated": generate a valid random AoE for each card, but
#   keep the *card order* fixed.
#
# The generated patterns are frozen for the fight (like Guardian/Kalameet)
# and reused each time you loop through the 4 cards.
# ---------------------------------------------------------------------------

def _ec_death_race_build_patterns(
    state: dict,
    mode: str,
    rng: random.Random | None = None,
) -> None:
    if rng is None:
        rng = random.Random()

    mode = mode.lower()

    n_dests = len(EC_STANDARD_PATTERNS)  # should be 4
    deck_size = n_dests                  # 1 pattern per card
    patterns: List[Dict[str, object]] = [None] * deck_size  # type: ignore

    for slot_index, base in enumerate(EC_STANDARD_PATTERNS):
        dest = base["dest"]  # type: ignore
        start = base["start"]  # type: ignore
        base_pattern = {
            "dest": dest,
            "start": start,
            "aoe": list(base["aoe"]),  # type: ignore
        }

        if mode == "deck":
            # Use the printed AoE pattern for this card.
            patterns[slot_index] = base_pattern
        else:
            # generated mode: random valid AoE for this card (fixed start/dest).
            patterns[slot_index] = _ec_generate_random_pattern_for_dest(
                dest,
                start,
                base_pattern,
                rng=rng,
            )

    # Fixed, non-random card order: [0, 1, 2, 3]
    indices = list(range(deck_size))

    state["ec_death_race_patterns"] = patterns
    state["ec_death_race_sequence"] = indices
    state["ec_death_race_index"] = 0
    state["ec_death_race_mode"] = mode


def _ec_death_race_next_pattern(state: dict, mode: str = "generated") -> Dict[str, object]:
    """
    Get the next AoE pattern for Executioner's Chariot's Death Race.

    mode:
        "deck"      -> 4-card deck using the printed AoE patterns, in fixed order.
        "generated" -> 4-card deck with randomly generated valid patterns for
                      each card, but still in the same fixed order.
    """
    rng = random.Random()
    mode = mode.lower()

    seq = state.get("ec_death_race_sequence")
    patterns = state.get("ec_death_race_patterns")
    current_mode = state.get("ec_death_race_mode")

    # Build or rebuild the 4-card deck if missing / mismatched
    if (
        not seq
        or not patterns
        or len(patterns) != DEATH_RACE_DECK_SIZE
        or current_mode != mode
    ):
        _ec_death_race_build_patterns(state, mode, rng=rng)
        seq = state["ec_death_race_sequence"]
        patterns = state["ec_death_race_patterns"]

    idx = state.get("ec_death_race_index", 0)
    slot_index = seq[idx]  # 0,1,2,3 in order

    pattern = patterns[slot_index]

    # Advance pointer for next time (loops 0→1→2→3→0→...)
    state["ec_death_race_index"] = (idx + 1) % len(seq)

    # Return a shallow copy so callers don’t mutate cached state.
    return {
        "dest": pattern["dest"],
        "aoe": list(pattern["aoe"]),
    }


# ---------------------------------------------------------------------------
# Rendering: Death Race AoE card with node overlays
# ---------------------------------------------------------------------------

def _ec_render_death_race_aoe(cfg, pattern: Dict[str, object]) -> Image.Image:
    """
    Render the Death Race AoE card with destination + AoE node icons overlaid.

    pattern is {"dest": (x, y), "aoe": [(x, y), ...]} using the shared grid.
    """
    # Use the first Death Race AoE image as the base.
    # File: "assets/behavior cards/Executioner's Chariot - Death Race AoE.jpg"
    base_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - Death Race AoE.jpg"

    base = render_behavior_card_cached(
        base_path,
        {},  # no JSON rules to apply; this is a pure AoE reference card
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
