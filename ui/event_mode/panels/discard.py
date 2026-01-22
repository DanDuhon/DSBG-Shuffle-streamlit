from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable

import streamlit as st

from core.image_cache import get_image_data_uri_cached


def render_discard_pile(
    discard_pile: Iterable[str],
    *,
    card_width: int = 100,
    offset: int = 22,
    max_iframe_height: int = 300,
) -> None:
    """Display a discard pile stack in HTML for layered visualization."""

    discard_list = list(discard_pile or [])
    if not discard_list:
        st.caption("Empty")
        return

    aspect_w, aspect_h = 498, 745
    card_h = int(card_width * (aspect_h / aspect_w))
    total_h = card_h + offset * (len(discard_list) - 1)

    cards_html: list[str] = []
    for i, path in enumerate(discard_list):
        top = i * offset
        title = os.path.splitext(os.path.basename(path))[0]
        src = get_image_data_uri_cached(path)
        if not src:
            raise RuntimeError(f"Empty data uri for discard card: {path}")
        cards_html.append(
            f'<img src="{src}" '
            f'style="position:absolute; top:{top}px; left:0; '
            f'width:{card_width}px; border-radius:8px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);" '
            f'title="{title}">'
        )

    stack_html = (
        f"<div style='position:relative; width:{card_width}px; height:{total_h}px;'>"
        f"{''.join(cards_html)}"
        "</div>"
    )
    container_html = (
        f"<div style='max-height:{max_iframe_height}px; overflow-y:auto; padding-right:5px;'>"
        f"{stack_html}"
        "</div>"
    )
    st.components.v1.html(container_html, height=max_iframe_height)


def render_discard_container(
    deck_state: Dict[str, Any],
    *,
    card_width: int = 100,
    offset: int = 22,
    max_iframe_height: int = 300,
) -> None:
    discard = list(deck_state.get("discard_pile") or [])
    if not discard:
        with st.container(border=True):
            st.caption("Empty.")
        return

    with st.container(border=True):
        i_col, t_col = st.columns([1, 1])
        with i_col:
            render_discard_pile(
                discard,
                card_width=card_width,
                offset=offset,
                max_iframe_height=max_iframe_height,
            )
        with t_col:
            st.caption(
                "  \n".join(
                    [
                        Path(str(path)).stem.replace("_", " ")
                        for path in reversed(discard)
                    ]
                )
            )


def render_discard_titles(deck_state: Dict[str, Any], *, limit: int = 50) -> None:
    """Lightweight discard list (newest-first), suitable for Encounter Mode."""

    discard = list(deck_state.get("discard_pile") or [])
    if not discard:
        st.caption("Empty")
        return

    for path in reversed(discard[-limit:]):
        st.caption(Path(str(path)).stem.replace("_", " "))
