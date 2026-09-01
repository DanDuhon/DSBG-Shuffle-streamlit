# ui/boss_mode/aoe_pattern_utils.py
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple

from PIL import Image

from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.image_cache import load_pil_image_cached

Coord = Tuple[int, int]

# AoE overlay icons are fixed-size and identical across all four AoE bosses.
# Each renderer used to re-open both PNGs and LANCZOS-resize them on EVERY
# rerun — including HP-slider ticks and sidebar changes, not just new draws.
_AOE_ICON_SIZE: Coord = (250, 250)
_DEST_ICON_SIZE: Coord = (122, 122)


@lru_cache(maxsize=4)
def _resized_overlay_icon(name: str, size: Coord) -> Image.Image:
    path = Path(BEHAVIOR_CARDS_PATH).parent / "behavior icons" / name
    return load_pil_image_cached(str(path), convert="RGBA").resize(
        size, Image.Resampling.LANCZOS
    )


def get_aoe_overlay_icons() -> Tuple[Image.Image, Image.Image]:
    """Return the (aoe, destination) overlay icons, decoded and resized once.

    Read-only: callers composite these onto their own base image and must not
    mutate them.
    """
    return (
        _resized_overlay_icon("aoe_node.png", _AOE_ICON_SIZE),
        _resized_overlay_icon("destination_node.png", _DEST_ICON_SIZE),
    )

# Shared grid used by Guardian Dragon, Kalameet, etc.
NODE_COORDS: List[Coord] = [
    (0, 0),
    (0, 2),
    (0, 4),
    (0, 6),
    (1, 1),
    (1, 3),
    (1, 5),
    (2, 0),
    (2, 2),
    (2, 4),
    (2, 6),
    (3, 1),
    (3, 3),
    (3, 5),
    (4, 0),
    (4, 2),
    (4, 4),
    (4, 6),
    (5, 1),
    (5, 3),
    (5, 5),
    (6, 0),
    (6, 2),
    (6, 4),
    (6, 6),
]


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_adjacent(a: Coord, b: Coord, max_dist: int = 3) -> bool:
    """
    Adjacency rule currently used by Guardian Dragon:
    sum of absolute diffs <= max_dist (so 3 == your old "< 4").
    """
    return manhattan(a, b) <= max_dist


def is_diagonal(a: Coord, b: Coord) -> bool:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return dx == 1 and dy == 1


def _aoe_node_to_xy(coord: Coord, dest: bool = False):
    col, row = coord

    if dest:
        x = round(29 + 107 * col)
        y = round(123 + 110 * row)
    else:
        x = round(-42 + 107.5 * col)
        y = round(55 + 110.5 * row)
    return x, y


def candidate_nodes_for_dest(
    dest: Coord,
    node_coords: Sequence[Coord] | None = None,
    max_dist: int = 6,
) -> List[Coord]:
    """
    Nodes allowed to be in the AoE for this destination.

    max_dist keeps things similar-ish to the printed patterns,
    while allowing multiple valid configurations.
    """
    if node_coords is None:
        node_coords = NODE_COORDS

    return [
        n
        for n in node_coords
        if n != dest and manhattan(n, dest) <= max_dist
    ]


def connected_under(
    nodes: Iterable[Coord],
    adjacency_fn: Callable[[Coord, Coord], bool] | None = None,
) -> bool:
    """
    Generic connectivity check under an arbitrary adjacency function.
    """
    node_set = set(nodes)
    if not node_set:
        return False

    if adjacency_fn is None:
        adjacency_fn = is_adjacent

    start = next(iter(node_set))
    visited = set()
    stack: List[Coord] = [start]

    while stack:
        v = stack.pop()
        if v in visited:
            continue
        visited.add(v)
        for m in node_set:
            if m not in visited and adjacency_fn(v, m):
                stack.append(m)

    return len(visited) == len(node_set)


def generate_random_pattern_for_dest(
    dest: Coord,
    base_pattern: dict,
    validate_fn: Callable[[Coord, Sequence[Coord]], bool],
    node_coords: Sequence[Coord] | None = None,
    aoe_size: int | None = None,
    max_dist: int = 6,
    rng: random.Random | None = None,
    max_attempts: int = 2000,
    avoid_base: bool = True,
) -> dict:
    """
    Generic "shuffle until valid" builder for an AoE pattern:

    - Uses a shared grid (or custom `node_coords`).
    - Lets each boss supply its own `validate_fn`.
    - Optionally avoids exactly matching the printed base pattern.
    """
    if rng is None:
        rng = random.Random()

    base_aoe = set(base_pattern["aoe"])
    if aoe_size is None:
        aoe_size = len(base_aoe)

    if node_coords is None:
        node_coords = NODE_COORDS

    candidates = candidate_nodes_for_dest(dest, node_coords=node_coords, max_dist=max_dist)

    if len(candidates) < aoe_size:
        # Not enough candidates to build a pattern; fall back to the base.
        return {"dest": dest, "aoe": list(base_aoe)}

    for _ in range(max_attempts):
        aoe = rng.sample(candidates, aoe_size)

        if avoid_base and set(aoe) == base_aoe:
            continue

        if validate_fn(dest, aoe):
            return {"dest": dest, "aoe": sorted(aoe)}

    # If we somehow fail to find anything valid, fall back to the base pattern.
    return {"dest": dest, "aoe": list(base_aoe)}
