"""Shared helpers for `ui.encounter_mode`.

Place small, UI-agnostic helpers here so they can be imported by multiple
modules without duplication (e.g., `play_panels` and `play_tab`).
"""
from __future__ import annotations

from typing import List
import streamlit as st

from ui.encounter_mode.assets import enemyNames


def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. Matching the previous behavior from
    `play_panels.py` so callers stay compatible.
    """
    # 1) Encounter dict itself
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    # 2) Session state override (if you set one from Setup)
    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    # 3) Settings-level toggle keyed by encounter key
    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def _get_enemy_display_names(encounter: dict) -> List[str]:
    """
    Return human-readable names for the shuffled enemies in this encounter.

    Assumes Setup stored the shuffled list on encounter["enemies"].
    Each entry may be a dict with `name`/`id` or an index/id that maps into
    `enemyNames` from the assets module.
    """
    enemy_ids = encounter.get("enemies") or []

    names: List[str] = []
    for eid in enemy_ids:
        if isinstance(eid, dict):
            names.append(eid.get("name") or eid.get("id") or str(eid))
        else:
            # Lookup from the global enemyNames mapping (may raise KeyError
            # if data is malformed; callers previously assumed this).
            names.append(enemyNames[eid])

    return names
