from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import streamlit as st


def render_discard_container(
    deck_state: Dict[str, Any],
    *,
    card_width: int = 100,
    offset: int = 22,
    max_iframe_height: int = 300,
) -> None:
    """Legacy compatibility.

    The app no longer renders a stacked discard pile preview (which required
    data-URI images in a custom HTML iframe). This wrapper keeps existing
    call sites working by rendering a lightweight titles-only list.
    """

    _ = card_width, offset, max_iframe_height
    with st.container(border=True):
        render_discard_titles(deck_state)


def render_discard_titles(deck_state: Dict[str, Any], *, limit: int = 50) -> None:
    """Lightweight discard list (newest-first), suitable for Encounter Mode."""

    discard = list(deck_state.get("discard_pile") or [])
    if not discard:
        st.caption("Empty")
        return

    for path in reversed(discard[-limit:]):
        st.caption(Path(str(path)).stem.replace("_", " "))
