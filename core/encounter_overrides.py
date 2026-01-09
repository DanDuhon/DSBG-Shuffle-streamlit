"""Encounter overrides loader and helpers.

This module provides a lightweight JSON-driven mechanism for placing
small, dynamic enemy icons and simple text overrides on encounter cards.

JSON schema (example):

{
  "Painted World of Ariamis_1_Cloak and Feathers": {
    "placements": [
      { "enemy_index": 0, "pos": [220, 48], "size": 28 }
    ],
    "text": [
      { "mode": "insert", "pos": [36, 48], "text": "Kill the " }
    ],
    "notes": "Place a small enemy icon in the blank in the sentence."
  }
}

Rules / behaviour:
- Keys are encounter identifiers (use the same key you pass to
  `ui.encounter_mode.logic.load_encounter`, e.g. "Painted World of Ariamis_1_Cloak and Feathers").
- `placements` is a list of placement directives. Each directive may contain:
  - `enemy_index` (int): index into the shuffled `enemies` list for this encounter.
  - `pos` (x,y): pixel coordinates on the card where the (small) icon should be placed.
  - `size` (int, optional): rendered size in pixels for the icon.
  - `asset` (optional): explicit asset path instead of using the enemy lookup.
- `text` is an optional list of text directives with `mode`, `pos`, and `text`.

This module intentionally does not depend on PIL or UI modules — it resolves
placements and (optionally) icon asset paths and attaches them to the
encounter data for downstream rendering code to consume.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import logging

_overrides: Dict[str, Any] = {}
_overrides_path: Path = Path("data/encounter_overrides.json")

logger = logging.getLogger(__name__)


def load_overrides(path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load overrides from JSON and cache them in-module.

    Returns the parsed dict (may be empty if file missing).
    """
    global _overrides, _overrides_path
    if path:
        _overrides_path = Path(path)

    if not _overrides_path.exists():
        raise FileNotFoundError(f"Encounter overrides file not found: {_overrides_path}")

    with _overrides_path.open("r", encoding="utf-8") as fh:
        _overrides = json.load(fh)

    return _overrides


def get_override(encounter_key: str) -> Optional[Dict[str, Any]]:
    """Return the raw override entry for `encounter_key`, or None."""
    if not _overrides:
        load_overrides()
    return _overrides.get(encounter_key)


def _default_enemy_icon_resolver(enemy: Any) -> Optional[str]:
    """Best-effort resolver for an enemy -> asset path.

    If `enemy` is a dict with a `name` key the returned path will be
    `assets/enemy icons/{name}.png`. If `enemy` is a string it's used
    directly as a filename. If a resolver can't be determined, returns None.
    """
    if isinstance(enemy, dict):
        name = enemy.get("name") or enemy.get("enemy")
        if not name:
            return None
        return f"assets/enemy icons/{name}.png"
    if isinstance(enemy, str):
        return f"assets/enemy icons/{enemy}.png"
    # fallback to string conversion
    try:
        return f"assets/enemy icons/{str(enemy)}.png"
    except Exception:
        return None


def apply_override_to_encounter(
    encounter_key: str,
    encounter_data: Dict[str, Any],
    enemies: List[Any],
    enemy_icon_resolver: Optional[Callable[[Any], Optional[str]]] = None,
) -> Dict[str, Any]:
    """Attach override info to `encounter_data` and resolve icon assets.

    - `enemy_icon_resolver` is a callable that accepts an element from
      the `enemies` list and returns an asset path (or None).
    - The function mutates `encounter_data` in-place and also returns it.
    - It adds these optional keys to `encounter_data`:
      - `_override_raw`: the raw JSON entry
      - `_override_placements`: list of resolved placement dicts
      - `_override_texts`: list of override text directives
    """
    ov = get_override(encounter_key)
    if not ov:
        return encounter_data

    resolver = enemy_icon_resolver or _default_enemy_icon_resolver

    # attach raw entry
    encounter_data.setdefault("_meta", {})
    encounter_data["_meta"]["_override_raw"] = deepcopy(ov)

    placements: List[Dict[str, Any]] = []
    for p in ov.get("placements", []) or []:
        pc = deepcopy(p)
        ei = pc.get("enemy_index")
        resolved = None

        # allow some semantic aliases
        if isinstance(ei, str):
            if ei == "primary":
                ei = 0
            elif ei == "secondary":
                ei = 1
            else:
                logger.warning(
                    "Unknown enemy_index alias %r in override for %s; ignoring index",
                    ei,
                    encounter_key,
                )
                ei = None

        # If we have an integer index, try to resolve it; otherwise fall back to explicit asset
        if isinstance(ei, int):
            if 0 <= ei < len(enemies):
                try:
                    resolved = resolver(enemies[ei])
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Enemy resolver failed for %s index %s: %s",
                        encounter_key,
                        ei,
                        exc,
                    )
                    resolved = None
                # If resolver returned None but an explicit asset is provided, prefer the asset
                if not resolved and pc.get("asset"):
                    resolved = pc.get("asset")
                if not resolved:
                    logger.warning(
                        "Skipping placement for %s: enemy_index %s resolved to no asset",
                        encounter_key,
                        ei,
                    )
                    continue
            else:
                if pc.get("asset"):
                    logger.warning(
                        "enemy_index %s out of range for %s; using explicit asset",
                        ei,
                        encounter_key,
                    )
                    resolved = pc.get("asset")
                else:
                    logger.warning(
                        "Skipping placement for %s: enemy_index %s out of range",
                        encounter_key,
                        ei,
                    )
                    continue
        else:
            # No integer index provided; require an explicit asset to proceed
            if pc.get("asset"):
                resolved = pc.get("asset")
            else:
                logger.warning(
                    "Skipping placement for %s: no valid enemy_index and no explicit asset",
                    encounter_key,
                )
                continue

        pc["resolved_asset"] = resolved
        placements.append(pc)

    encounter_data["_meta"]["_override_placements"] = placements
    encounter_data["_meta"]["_override_texts"] = deepcopy(ov.get("text", []))

    return encounter_data


if __name__ == "__main__":
    # quick smoke when run directly
    print("Loaded overrides:", load_overrides())
