from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from core.behavior.assets import CATEGORY_ORDER


def render_selector(*, catalog: Dict[str, List[Any]]) -> Tuple[Optional[str], Optional[Any]]:
    """Render the category/entity selector row.

    Preserves existing session keys:
      - behavior_viewer_category
      - behavior_viewer_choice
      - behavior_viewer_choice_name

    Returns (category, entry) or (None, None) if no selection is possible.
    """

    categories = [c for c in CATEGORY_ORDER if c in catalog] or list(catalog.keys())
    if not categories:
        st.info("No behavior categories found.")
        return None, None

    col_cat, col_ent = st.columns([1, 2])
    with col_cat:
        default_cat = st.session_state.get("behavior_viewer_category", categories[0])
        category = st.selectbox(
            "Category",
            categories,
            index=categories.index(default_cat) if default_cat in categories else 0,
            key="behavior_viewer_category",
        )

    entries = catalog.get(category, [])
    # Filter out internal-only or stray entries (e.g., priscilla_arcs)
    entries = [e for e in entries if getattr(e, "name", None) != "priscilla_arcs"]
    if not entries:
        with col_ent:
            st.info("No behavior entries found for this category.")
        return category, None

    with col_ent:
        last = st.session_state.get("behavior_viewer_choice_name")
        names = [e.name for e in entries]
        idx = names.index(last) if last in names else 0
        entry = st.selectbox(
            "Choose entity",
            entries,
            index=idx,
            key="behavior_viewer_choice",
            format_func=lambda e: e.name,
        )
        if entry is not None:
            st.session_state["behavior_viewer_choice_name"] = entry.name

    return category, entry
