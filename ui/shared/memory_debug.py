from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SizedEntry:
    key: str
    bytes: int
    type_name: str


def format_bytes(num_bytes: int) -> str:
    try:
        n = int(num_bytes)
    except Exception:
        return str(num_bytes)

    if n < 0:
        return str(n)
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    unit_idx = 0
    while size >= 1024.0 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    if unit_idx == 0:
        return f"{int(size)} {units[unit_idx]}"
    return f"{size:.2f} {units[unit_idx]}"


def _iter_limited(items: Iterable[Any], limit: int) -> Iterable[Any]:
    if limit <= 0:
        return []
    out = []
    for i, v in enumerate(items):
        if i >= limit:
            break
        out.append(v)
    return out


def deep_sizeof(
    obj: Any,
    *,
    max_depth: int = 6,
    max_children: int = 2_000,
    _seen: set[int] | None = None,
) -> int:
    """Best-effort deep size of an object graph.

    This is intentionally approximate and bounded to avoid huge CPU costs.
    """

    if _seen is None:
        _seen = set()

    oid = id(obj)
    if oid in _seen:
        return 0
    _seen.add(oid)

    try:
        total = sys.getsizeof(obj)
    except Exception:
        total = 0

    if max_depth <= 0:
        return total

    # Common leaf types
    if obj is None or isinstance(obj, (bool, int, float, complex)):
        return total

    if isinstance(obj, (bytes, bytearray, memoryview)):
        return total

    if isinstance(obj, str):
        return total

    # Containers
    try:
        if isinstance(obj, dict):
            items = list(_iter_limited(obj.items(), max_children))
            for k, v in items:
                total += deep_sizeof(k, max_depth=max_depth - 1, max_children=max_children, _seen=_seen)
                total += deep_sizeof(v, max_depth=max_depth - 1, max_children=max_children, _seen=_seen)
            return total

        if isinstance(obj, (list, tuple, set, frozenset)):
            items = list(_iter_limited(obj, max_children))
            for v in items:
                total += deep_sizeof(v, max_depth=max_depth - 1, max_children=max_children, _seen=_seen)
            return total
    except Exception:
        return total

    # Objects with attributes
    try:
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict) and d:
            total += deep_sizeof(d, max_depth=max_depth - 1, max_children=max_children, _seen=_seen)
            return total
    except Exception:
        pass

    # Slots objects
    try:
        slots = getattr(obj, "__slots__", None)
        if slots:
            if isinstance(slots, str):
                slots = [slots]
            for name in _iter_limited(slots, max_children):
                try:
                    v = getattr(obj, name)
                except Exception:
                    continue
                total += deep_sizeof(v, max_depth=max_depth - 1, max_children=max_children, _seen=_seen)
            return total
    except Exception:
        pass

    return total


def summarize_mapping(
    mapping: Any,
    *,
    top_n: int = 20,
    max_depth: int = 6,
    max_children: int = 2_000,
) -> tuple[int, list[SizedEntry]]:
    """Compute deep size totals for a mapping (e.g., st.session_state)."""

    # Try to get stable items view without copying huge things unnecessarily.
    try:
        items = list(mapping.items())  # type: ignore[attr-defined]
    except Exception:
        try:
            items = [(k, mapping[k]) for k in list(mapping.keys())]  # type: ignore[index]
        except Exception:
            items = []

    entries: list[SizedEntry] = []
    total = 0

    for key, value in items:
        key_str = str(key)
        sz = deep_sizeof(value, max_depth=max_depth, max_children=max_children)
        entries.append(SizedEntry(key=key_str, bytes=sz, type_name=type(value).__name__))
        total += sz

    entries.sort(key=lambda e: e.bytes, reverse=True)
    return total, entries[: max(0, int(top_n))]


def get_process_rss_mb() -> float | None:
    """Best-effort RSS in MB.

    Uses psutil when available, else tries /proc/self/status.
    """

    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        return float(proc.memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        pass

    # Linux fallback
    try:
        p = "/proc/self/status"
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = float(parts[1])
                        return kb / 1024.0
    except Exception:
        return None

    return None
