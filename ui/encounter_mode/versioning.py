"""Encounter version helpers.

Encounters can be treated as V1- or V2-style based on explicit version fields
or inferred from their expansion.
"""

from __future__ import annotations

from core.expansions import V2_EXPANSIONS

V2_EXPANSIONS_SET = set(V2_EXPANSIONS)


def is_v2_encounter(encounter: dict) -> bool:
    """Return True if the encounter should be treated as a V2 card."""
    version = (
        encounter.get("version")
        or encounter.get("encounter_version")
        or ""
    ).upper()

    if version.startswith("V1"):
        return False
    if version.startswith("V2"):
        return True

    expansion = encounter.get("expansion")
    return expansion in V2_EXPANSIONS_SET


def is_v1_encounter(encounter: dict) -> bool:
    """Return True if the encounter should be treated as a V1 card."""
    return not is_v2_encounter(encounter)
