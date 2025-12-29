from __future__ import annotations

import math
from typing import Any, Dict
from functools import lru_cache

from ui.character_mode.constants import DICE_ICON, DIE_FACES


DiceDict = Dict[str, int]  # keys: black, blue, orange, flat_mod


def _dice_count(d: Dict[str, Any], key: str) -> int:
    return int((d or {}).get(key) or 0)


def _flat_mod(d: Dict[str, Any]) -> int:
    v = (d or {}).get("flat_mod")
    if v is None:
        v = (d or {}).get("mod")
    if v is None:
        v = (d or {}).get("modifier")
    return int(v or 0)

def _dice_icons(block_or_resist: Dict[str, Any]) -> str:
    b = _dice_count(block_or_resist, "black")
    u = _dice_count(block_or_resist, "blue")
    o = _dice_count(block_or_resist, "orange")

    s = ""
    if b:
        s += DICE_ICON["black"] * b
    if u:
        s += DICE_ICON["blue"] * u
    if o:
        s += DICE_ICON["orange"] * o

    flat = _flat_mod(block_or_resist)
    if flat:
        mod = f"{'+' if flat > 0 else ''}{flat}"
        s = f"{s} {mod}" if s else mod

    return s


def _dodge_icons(n: int) -> str:
    return DICE_ICON["dodge"] * max(int(n or 0), 0)


def _norm_dice(d: Any) -> DiceDict:
    if not isinstance(d, dict):
        return {"black": 0, "blue": 0, "orange": 0, "flat_mod": 0}
    return {
        "black": _dice_count(d, "black"),
        "blue": _dice_count(d, "blue"),
        "orange": _dice_count(d, "orange"),
        "flat_mod": _flat_mod(d),
    }


def _dice_min_max_avg(d: Any) -> Dict[str, float]:
    dd = _norm_dice(d)
    b = dd["black"]
    u = dd["blue"]
    o = dd["orange"]
    flat = dd["flat_mod"]

    mn = b * min(DIE_FACES["black"]) + u * min(DIE_FACES["blue"]) + o * min(DIE_FACES["orange"]) + flat
    mx = b * max(DIE_FACES["black"]) + u * max(DIE_FACES["blue"]) + o * max(DIE_FACES["orange"]) + flat

    def _avg(faces):
        return sum(faces) / len(faces)

    av = b * _avg(DIE_FACES["black"]) + u * _avg(DIE_FACES["blue"]) + o * _avg(DIE_FACES["orange"]) + flat
    return {"min": float(mn), "max": float(mx), "avg": float(av)}


def _pmf_for_faces(faces: list[int]) -> Dict[int, float]:
    p = 1.0 / float(len(faces))
    out: Dict[int, float] = {}
    for v in faces:
        out[v] = out.get(v, 0.0) + p
    return out


_PMF_BLACK = _pmf_for_faces(DIE_FACES["black"])
_PMF_BLUE = _pmf_for_faces(DIE_FACES["blue"])
_PMF_ORANGE = _pmf_for_faces(DIE_FACES["orange"])


def _convolve(a: Dict[int, float], b: Dict[int, float]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for va, pa in a.items():
        for vb, pb in b.items():
            out[va + vb] = out.get(va + vb, 0.0) + pa * pb
    return out


def _pmf_sum(dice: Any) -> Dict[int, float]:
    dd = _norm_dice(dice)
    return _pmf_sum_cached(dd["black"], dd["blue"], dd["orange"], dd["flat_mod"])


@lru_cache(maxsize=4096)
def _pmf_sum_cached(black: int, blue: int, orange: int, flat: int) -> Dict[int, float]:
    """Compute PMF for given dice counts; cached for repeated combinations.

    Keys are small integers (counts), so cache is safe and yields large savings
    when the same dice combinations are used repeatedly in UI aggregates.
    """
    dist: Dict[int, float] = {0: 1.0}

    for _ in range(int(black or 0)):
        dist = _convolve(dist, _PMF_BLACK)
    for _ in range(int(blue or 0)):
        dist = _convolve(dist, _PMF_BLUE)
    for _ in range(int(orange or 0)):
        dist = _convolve(dist, _PMF_ORANGE)

    if int(flat or 0):
        f = int(flat or 0)
        dist = {k + f: p for k, p in dist.items()}

    return dist


def _expected_remaining_damage(incoming_damage: int, defense_dice: Any) -> float:
    dd = _norm_dice(defense_dice)
    return _expected_remaining_damage_cached(int(incoming_damage), int(dd["black"]), int(dd["blue"]), int(dd["orange"]), int(dd["flat_mod"]))


@lru_cache(maxsize=8192)
def _expected_remaining_damage_cached(incoming_damage: int, black: int, blue: int, orange: int, flat: int) -> float:
    dmg = int(incoming_damage)
    dist = _pmf_sum_cached(black, blue, orange, flat)
    exp = 0.0
    for defense, p in dist.items():
        exp += p * float(max(0, dmg - int(defense)))
    return exp


def _dodge_success_prob(n_dice: int, difficulty: int) -> float:
    n = max(int(n_dice), 0)
    diff = max(int(difficulty), 0)

    faces = DIE_FACES["dodge"]
    p = float(sum(1 for x in faces if int(x) >= 1)) / float(len(faces)) if faces else 0.0

    if diff <= 0:
        return 1.0
    if n <= 0 or diff > n:
        return 0.0

    out = 0.0
    for k in range(diff, n + 1):
        out += math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))
    return out
