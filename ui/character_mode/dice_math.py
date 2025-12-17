from typing import Any, Dict
from ui.character_mode.constants import DIE_STATS, DICE_ICON


def _dice_count(d: Dict[str, Any], key: str) -> int:
    try:
        return int((d or {}).get(key) or 0)
    except Exception:
        return 0
    

def _flat_mod(d: Dict[str, Any]) -> int:
    try:
        return int((d or {}).get("flat_mod") or 0)
    except Exception:
        return 0


def _sum_rolls(parts: list[tuple[int, int, float]]) -> tuple[int, int, float]:
    mn = sum(p[0] for p in parts)
    mx = sum(p[1] for p in parts)
    avg = sum(p[2] for p in parts)
    return mn, mx, avg


def _roll_min_max_avg(die: str, n: int) -> tuple[int, int, float]:
    if n <= 0:
        return (0, 0, 0.0)
    s = DIE_STATS[die]
    return (s["min"] * n, s["max"] * n, s["avg"] * n)


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

    flat = _flat_mod(block_or_resist)  # uses your existing helper
    if flat:
        mod = f"{'+' if flat > 0 else ''}{flat}"
        s = f"{s} {mod}" if s else mod

    return s


def _dodge_icons(n: int) -> str:
    return DICE_ICON["dodge"] * max(int(n or 0), 0)