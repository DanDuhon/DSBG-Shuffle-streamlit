"""Encounter card special-rule icon placement tables.

Backed by cached JSON so coordinates can be tweaked without touching Python.

Expected JSON shape (see data/encounter_mode/special_rule_icons.json):
{
  "SPECIAL_RULE_ENEMY_ICON_SLOTS": {
    "<Expansion>": {"<Encounter>": [{"enemy_index":0,"x":0,"y":0,"size":25}, ...]}
  },
  "EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS": { ... same shape ... },
  "GANG_TEXT_POSITIONS": {
    "<Expansion>": {"<Encounter>": [x, y, size]}
  }
}

Note: this module is intentionally data-only (no Streamlit imports).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class SpecialRuleEnemyIcon:
    """One enemy icon stamped into the *special rules* area."""

    enemy_index: int
    x: int
    y: int
    size: int = 25


_SPECIAL_RULE_ICONS_PATH = Path("data/encounter_mode/special_rule_icons.json")


@lru_cache(maxsize=16)
def _load_json_cached(path_str: str, mtime: float) -> dict:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _mtime() -> float:
    try:
        return _SPECIAL_RULE_ICONS_PATH.stat().st_mtime
    except FileNotFoundError:
        return -1.0


@lru_cache(maxsize=32)
def _decode_icon_slots(payload_key: str, mtime: float) -> Dict[Tuple[str, str], List[SpecialRuleEnemyIcon]]:
    if mtime < 0:
        return {}

    payload = _load_json_cached(str(_SPECIAL_RULE_ICONS_PATH), mtime)
    raw = payload.get(payload_key, {})

    out: Dict[Tuple[str, str], List[SpecialRuleEnemyIcon]] = {}
    if not isinstance(raw, dict):
        return out

    for expansion_name, encounters in raw.items():
        if not isinstance(encounters, dict):
            continue
        for encounter_name, icons in encounters.items():
            if not isinstance(icons, list):
                continue
            decoded: List[SpecialRuleEnemyIcon] = []
            for icon in icons:
                if not isinstance(icon, dict):
                    continue
                decoded.append(
                    SpecialRuleEnemyIcon(
                        enemy_index=int(icon.get("enemy_index", 0)),
                        x=int(icon.get("x", 0)),
                        y=int(icon.get("y", 0)),
                        size=int(icon.get("size", 25)),
                    )
                )
            out[(encounter_name, expansion_name)] = decoded

    return out


@lru_cache(maxsize=32)
def _decode_gang_positions(mtime: float) -> Dict[Tuple[str, str], Tuple[int, int, int]]:
    if mtime < 0:
        return {}

    payload = _load_json_cached(str(_SPECIAL_RULE_ICONS_PATH), mtime)
    raw = payload.get("GANG_TEXT_POSITIONS", {})

    out: Dict[Tuple[str, str], Tuple[int, int, int]] = {}
    if not isinstance(raw, dict):
        return out

    for expansion_name, encounters in raw.items():
        if not isinstance(encounters, dict):
            continue
        for encounter_name, triple in encounters.items():
            if not (isinstance(triple, list) and len(triple) == 3):
                continue
            out[(encounter_name, expansion_name)] = (int(triple[0]), int(triple[1]), int(triple[2]))

    return out


class _LazySpecialRuleMapping(Mapping[Tuple[str, str], object]):
    def __init__(self, kind: str):
        self._kind = kind

    def _data(self):
        mtime = _mtime()
        if self._kind == "GANG_TEXT_POSITIONS":
            return _decode_gang_positions(mtime)
        return _decode_icon_slots(self._kind, mtime)

    def __getitem__(self, key: Tuple[str, str]):
        return self._data()[key]

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def get(self, key: Tuple[str, str], default=None):  # noqa: A003
        return self._data().get(key, default)


# Public API: keep names unchanged for import compatibility.
SPECIAL_RULE_ENEMY_ICON_SLOTS: Mapping[Tuple[str, str], List[SpecialRuleEnemyIcon]] = _LazySpecialRuleMapping(
    "SPECIAL_RULE_ENEMY_ICON_SLOTS"
)
EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS: Mapping[Tuple[str, str], List[SpecialRuleEnemyIcon]] = _LazySpecialRuleMapping(
    "EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS"
)
GANG_TEXT_POSITIONS: Mapping[Tuple[str, str], Tuple[int, int, int]] = _LazySpecialRuleMapping(
    "GANG_TEXT_POSITIONS"
)
