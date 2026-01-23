from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from ui.behavior_viewer.models import BehaviorPickerModel, DATA_CARD_SENTINEL


def render_card_picker(
    *,
    model: BehaviorPickerModel,
    compact: bool,
    left_col: Any,
    priscilla_entry_name: str,
) -> str:
    """Render the left-column picker (radio/selectbox) and Priscilla toggle.

    Preserves existing widget/session keys:
      - behavior_viewer_card_choice
      - behavior_viewer_card_choice_compact
      - behavior_viewer_priscilla_invisible

    Returns the selected value (either DATA_CARD_SENTINEL, a display label, a behavior name, or a header row).
    """

    options = model.options
    options_compact = model.options_compact
    display_map = model.display_map

    # Try to preserve previous selection across mode changes
    prev = st.session_state.get("behavior_viewer_card_choice") or st.session_state.get(
        "behavior_viewer_card_choice_compact"
    )

    if compact:
        default_index = options_compact.index(prev) if prev in options_compact else 0
    else:
        if prev in options:
            default_index = options.index(prev)
        else:
            # If previous was stored as the original behavior name, find its display label
            found_label: Optional[str] = None
            for lbl, orig in display_map.items():
                if orig == prev:
                    found_label = lbl
                    break
            default_index = (
                options.index(found_label)
                if found_label and found_label in options
                else 0
            )

    with left_col:
        if compact:
            choice = st.selectbox(
                "Card",
                options_compact,
                index=default_index,
                key="behavior_viewer_card_choice_compact",
            )
        else:
            choice = st.radio(
                "Card",
                options,
                index=default_index,
                key="behavior_viewer_card_choice",
            )

        # Priscilla invisibility toggle
        priscilla_invis_key = "behavior_viewer_priscilla_invisible"
        if priscilla_entry_name == "Crossbreed Priscilla":
            # `st.checkbox` will set `st.session_state[priscilla_invis_key]` itself;
            # avoid assigning into session_state after widget creation.
            st.checkbox(
                "Show invisibility version",
                value=False,
                key=priscilla_invis_key,
            )

    return choice
