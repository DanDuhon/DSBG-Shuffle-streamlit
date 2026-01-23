"""Encounter behavior modifier tables.

Backed by cached JSON so tables can be edited without touching Python.

Expected JSON shape (see data/encounter_mode/behavior_modifiers.json):
{
  "ENCOUNTER_BEHAVIOR_MODIFIERS": {"<encounter_key>": [ ... ], ...},
  "ENCOUNTER_BEHAVIOR_MODIFIERS_EDITED": {"<encounter_key>": [ ... ], ...}
}
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any


_BEHAVIOR_MODIFIERS_PATH = Path("data/encounter_mode/behavior_modifiers.json")


@lru_cache(maxsize=16)
def _load_json_cached(path_str: str, mtime: float) -> dict[str, Any]:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _mtime() -> float:
    try:
        return _BEHAVIOR_MODIFIERS_PATH.stat().st_mtime
    except FileNotFoundError:
        return -1.0


def _load_payload() -> dict[str, Any]:
    mtime = _mtime()
    if mtime < 0:
        return {
            "ENCOUNTER_BEHAVIOR_MODIFIERS": {},
            "ENCOUNTER_BEHAVIOR_MODIFIERS_EDITED": {},
        }
    return _load_json_cached(str(_BEHAVIOR_MODIFIERS_PATH), mtime)


class _LazyBehaviorModifierMapping(Mapping[str, Any]):
    def __init__(self, payload_key: str):
        self._payload_key = payload_key

    def _data(self) -> dict[str, Any]:
        payload = _load_payload()
        value = payload.get(self._payload_key, {})
        return value if isinstance(value, dict) else {}

    def __getitem__(self, key: str) -> Any:
        return self._data()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def get(self, key: str, default: Any = None) -> Any:  # noqa: A003
        return self._data().get(key, default)

    def items(self):
        return self._data().items()


# Public API: keep names unchanged for import compatibility.
ENCOUNTER_BEHAVIOR_MODIFIERS: Mapping[str, Any] = _LazyBehaviorModifierMapping(
    "ENCOUNTER_BEHAVIOR_MODIFIERS"
)
ENCOUNTER_BEHAVIOR_MODIFIERS_EDITED: Mapping[str, Any] = _LazyBehaviorModifierMapping(
    "ENCOUNTER_BEHAVIOR_MODIFIERS_EDITED"
)
