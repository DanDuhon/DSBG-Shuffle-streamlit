from pathlib import Path

import streamlit as st

from core.image_cache import get_image_bytes_cached
from core.behavior.assets import CARD_BACK, _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from core.behavior.priscilla_overlay import overlay_priscilla_arcs
from ui.boss_mode.special_cases.current_card import render_special_current_card
from ui.campaign_mode.core import _card_w


def render_current_card_column(*, cfg, state) -> None:
    """Render Boss Mode RIGHT column (card back/current card + deck stats caption)."""

    current = state.get("current_card")

    if not current:
        w = _card_w()
        img_bytes = get_image_bytes_cached(str(Path(CARD_BACK)))
        st.image(img_bytes, width=w)
    else:
        if not render_special_current_card(cfg=cfg, state=state, current=current):
            base_path = _behavior_image_path(cfg, current)
            cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
            render_behavior = (
                render_behavior_card_uncached
                if cloud_low_memory
                else render_behavior_card_cached
            )
            img = render_behavior(
                base_path,
                cfg.behaviors[current],
                is_boss=True,
            )

            if cfg.name == "Crossbreed Priscilla" and st.session_state.get(
                "behavior_deck", {}
            ).get("priscilla_invisible", False):
                img = overlay_priscilla_arcs(img, current, cfg.behaviors.get(current, {}))

            st.image(img, width=_card_w())

    if cfg.name == "Vordt of the Boreal Valley":
        st.caption(
            f"{len(state.get('vordt_move_discard', [])) + (1 if current else 0)} movement cards played"
            f" • {len(state.get('vordt_attack_discard', [])) + (1 if current else 0)} attack cards played"
        )
    else:
        st.caption(
            f"Draw pile: {len(state.get('draw_pile', []))} cards"
            f" • Discard: {len(state.get('discard_pile', [])) + (1 if current else 0)} cards"
        )
