from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Iterable


# Tracemalloc is optional and only enabled when explicitly requested.
try:  # pragma: no cover
    import tracemalloc
except Exception:  # pragma: no cover
    tracemalloc = None  # type: ignore


_TRACE_STARTED = False
_TRACE_BASELINE_SNAPSHOT = None


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


def _utc_now_iso() -> str:
    try:
        # Avoid importing datetime on the hot path unless needed.
        import datetime as _dt

        return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return ""


def memlog_clear(state: Any) -> None:
    """Clear the in-memory memlog stored in `state` (e.g. st.session_state)."""

    if not isinstance(state, MutableMapping):
        return
    state.pop("_memdbg_events", None)
    state.pop("_memdbg_last_rss", None)
    state.pop("_memdbg_seq", None)


def memlog_get_events(state: Any) -> list[dict]:
    if not isinstance(state, MutableMapping):
        return []
    ev = state.get("_memdbg_events")
    if isinstance(ev, list):
        # Only return JSON-safe dicts.
        out: list[dict] = []
        for e in ev:
            if isinstance(e, dict):
                out.append(e)
        return out
    return []


def memlog_export_json(state: Any) -> str:
    """Export memlog events as a JSON string (safe for st.download_button)."""
    payload = {
        "exported_at": _utc_now_iso(),
        "events": memlog_get_events(state),
    }
    try:
        return json.dumps(payload, indent=2, sort_keys=False)
    except Exception:
        return json.dumps({"events": []})


def memtrace_arm(state: Any) -> None:
    """Arm a short tracemalloc window.

    When armed and trace logging is enabled, the *next* checkpoint will start
    tracemalloc and record a baseline snapshot. The *following* checkpoint will
    compute a diff from that baseline, record it on the event, then stop
    tracemalloc.

    This avoids leaving tracemalloc running across normal Streamlit reruns,
    which can dramatically increase RSS on Streamlit Cloud.
    """

    if not isinstance(state, MutableMapping):
        return
    state["_memdbg_trace_armed"] = True


def memtrace_disarm(state: Any) -> None:
    if not isinstance(state, MutableMapping):
        return
    state.pop("_memdbg_trace_armed", None)
    state.pop("_memdbg_trace_active", None)


def _to_cache_info_dict(ci: Any) -> dict:
    try:
        # functools.lru_cache cache_info() returns a namedtuple.
        return {
            "hits": int(getattr(ci, "hits")),
            "misses": int(getattr(ci, "misses")),
            "maxsize": getattr(ci, "maxsize"),
            "currsize": int(getattr(ci, "currsize")),
        }
    except Exception:
        return {}


def memlog_checkpoint(
    state: Any,
    label: str,
    *,
    extra: dict | None = None,
    force: bool = False,
    max_events: int = 500,
    do_gc: bool | None = None,
    do_trace: bool | None = None,
    trace_top_n: int = 12,
    trace_group_by: str = "lineno",
) -> dict | None:
    """Append a memory checkpoint entry into `state`.

    Intended storage: `st.session_state`.

    Behavior:
    - Records RSS (MB) and delta since last checkpoint.
    - Optionally runs `gc.collect()` and/or `tracemalloc` snapshot diffs.
    - Caps log size to `max_events` to avoid becoming a memory problem.
    """

    if not isinstance(state, MutableMapping):
        return None

    enabled = bool(state.get("_memdbg_log_enabled", False))
    if not enabled and not force:
        return None

    # Sampling control (optional).
    try:
        sample_every = int(state.get("_memdbg_sample_every", 1) or 1)
    except Exception:
        sample_every = 1
    sample_every = max(1, sample_every)

    seq = int(state.get("_memdbg_seq", 0) or 0) + 1
    state["_memdbg_seq"] = seq
    if not force and sample_every > 1 and (seq % sample_every) != 0:
        return None

    rss_now = get_process_rss_mb()
    last_rss = state.get("_memdbg_last_rss")
    try:
        last_rss_f = float(last_rss) if last_rss is not None else None
    except Exception:
        last_rss_f = None
    delta = (float(rss_now) - float(last_rss_f)) if (rss_now is not None and last_rss_f is not None) else None
    if rss_now is not None:
        state["_memdbg_last_rss"] = float(rss_now)

    # Optional GC
    if do_gc is None:
        do_gc = bool(state.get("_memdbg_log_gc", False))
    gc_ms = None
    gc_counts = None
    if do_gc:
        try:
            import gc

            gc_counts = list(gc.get_count())
            t0 = time.perf_counter()
            gc.collect()
            gc_ms = (time.perf_counter() - t0) * 1000.0
        except Exception:
            pass

    # Optional tracemalloc (armed window mode).
    # IMPORTANT: leaving tracemalloc running continuously in Streamlit Cloud can
    # blow up RSS. We only trace within a short window between two checkpoints.
    if do_trace is None:
        do_trace = bool(state.get("_memdbg_log_trace", False))

    trace_top = None
    if do_trace and tracemalloc is not None:
        global _TRACE_STARTED, _TRACE_BASELINE_SNAPSHOT
        try:
            armed = bool(state.get("_memdbg_trace_armed", False))
            active = bool(state.get("_memdbg_trace_active", False))

            if armed and not active:
                # Start tracing and capture baseline.
                if not _TRACE_STARTED:
                    tracemalloc.start(25)
                    _TRACE_STARTED = True
                _TRACE_BASELINE_SNAPSHOT = tracemalloc.take_snapshot()
                state["_memdbg_trace_active"] = True
                state["_memdbg_trace_armed"] = False
                trace_top = ["(trace armed: baseline captured; next checkpoint records diff)"]

            elif active:
                # Capture diff and stop tracing.
                snap = tracemalloc.take_snapshot()
                base = _TRACE_BASELINE_SNAPSHOT
                if base is not None:
                    stats = snap.compare_to(base, trace_group_by)
                    top = []
                    for s in list(stats)[: max(1, int(trace_top_n))]:
                        try:
                            top.append(str(s))
                        except Exception:
                            continue
                    trace_top = top

                # Stop tracemalloc to release overhead.
                try:
                    tracemalloc.stop()
                except Exception:
                    pass
                _TRACE_STARTED = False
                _TRACE_BASELINE_SNAPSHOT = None
                state.pop("_memdbg_trace_active", None)

        except Exception:
            trace_top = None

    entry = {
        "t": time.time(),
        "ts": _utc_now_iso(),
        "seq": int(seq),
        "label": str(label),
        "rss_mb": float(rss_now) if rss_now is not None else None,
        "delta_mb": float(delta) if delta is not None else None,
        "gc_ms": float(gc_ms) if gc_ms is not None else None,
        "gc_counts": gc_counts,
        "trace_top": trace_top,
        "extra": extra if isinstance(extra, dict) else None,
    }

    events = state.get("_memdbg_events")
    if not isinstance(events, list):
        events = []
        state["_memdbg_events"] = events

    events.append(entry)
    try:
        max_n = max(50, int(max_events))
    except Exception:
        max_n = 500
    if len(events) > max_n:
        # Trim from the front.
        del events[0 : len(events) - max_n]

    return entry
