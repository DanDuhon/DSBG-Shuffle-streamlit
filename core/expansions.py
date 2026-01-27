"""Shared expansion metadata.

This module is intentionally dependency-free so it can be imported from both
`core` and `ui` without creating circular imports.
"""

from __future__ import annotations

from typing import Optional


# Expansions that use the V2 ruleset. All other expansions are treated as V1.
V2_EXPANSIONS: list[str] = [
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City",
]

V2_EXPANSIONS_SET: set[str] = set(V2_EXPANSIONS)


def is_v2_expansion(expansion: Optional[str]) -> bool:
    """Return True if the expansion name is in the V2 ruleset list."""
    if not expansion:
        return False
    return str(expansion).strip() in V2_EXPANSIONS_SET
