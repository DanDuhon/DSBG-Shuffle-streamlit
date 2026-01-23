from __future__ import annotations

from typing import Any

import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import (
    render_behavior_card_cached,
    render_data_card_cached,
    render_dual_boss_behavior_card,
    render_dual_boss_data_cards,
)
from core.behavior.priscilla_overlay import overlay_priscilla_arcs

from ui.behavior_viewer.models import BehaviorPickerModel, DATA_CARD_SENTINEL


def render_card_display(
    *,
    entry: Any,
    cfg: Any,
    model: BehaviorPickerModel,
    compact: bool,
    choice: str,
    card_width: int,
) -> None:
    """Render the right-column card display."""

    display_map = model.display_map

    if choice == DATA_CARD_SENTINEL:
        if entry.name == "Ornstein & Smough":
            o_img, s_img = render_dual_boss_data_cards(cfg.raw)
            c1, c2 = st.columns(2)
            with c1:
                st.image(o_img, width=card_width)
            with c2:
                st.image(s_img, width=card_width)
            return

        # Special-case: always show skeletal horse data card for Executioner's Chariot
        if entry.name == "Executioner's Chariot":
            img_bytes = render_data_card_cached(
                "assets/behavior cards/Executioner's Chariot - Skeletal Horse.jpg",
                cfg.raw,
                is_boss=(entry.tier != "enemy"),
            )
            st.image(img_bytes, width=card_width)
            return

        if cfg.display_cards:
            img_bytes = render_data_card_cached(
                cfg.display_cards[0],
                cfg.raw,
                is_boss=(entry.tier != "enemy"),
            )
            st.image(img_bytes, width=card_width)
        return

    # Map display label back to original behavior name for non-compact mode
    if compact:
        sel = choice
    else:
        sel = display_map.get(choice, choice)

    # Headers in compact mode (strings starting with '—') are just labels
    if compact and isinstance(sel, str) and sel.strip().startswith("—"):
        st.info("Select a behavior card — header rows are labels in compact mode.")
        return

    beh = cfg.behaviors.get(sel, {})

    # Dual Ornstein & Smough cards need the special dual-boss renderer
    if entry.name == "Ornstein & Smough" and isinstance(sel, str) and "&" in sel:
        img_bytes = render_dual_boss_behavior_card(cfg.raw, sel, boss_name=entry.name)
    else:
        img_path = _behavior_image_path(cfg, sel)
        img_bytes = render_behavior_card_cached(
            img_path,
            beh,
            is_boss=(entry.tier != "enemy"),
        )
        # Apply Priscilla overlay when requested
        priscilla_invis_key = "behavior_viewer_priscilla_invisible"
        if entry.name == "Crossbreed Priscilla" and st.session_state.get(
            priscilla_invis_key, True
        ):
            img_bytes = overlay_priscilla_arcs(img_bytes, sel, beh)

    # If this is Vordt, prepend a small emoji indicating move vs attack
    if entry.name == "Vordt of the Boreal Valley":
        btype = None
        if isinstance(beh, dict):
            btype = beh.get("type")
        if btype == "move":
            st.markdown("**🏃 Move**")
        elif btype == "attack":
            st.markdown("**⚔️ Attack**")

    st.image(img_bytes, width=card_width)
