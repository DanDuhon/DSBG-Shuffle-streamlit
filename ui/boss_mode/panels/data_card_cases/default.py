from core.behavior.generation import render_data_card_cached, render_data_card_uncached
import streamlit as st

from ui.campaign_mode.core import _card_w


def render_default_data_card(*, cfg, state) -> None:
    data_path = cfg.display_cards[0] if cfg.display_cards else None
    if data_path:
        cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
        img = (
            render_data_card_uncached(data_path, cfg.raw, is_boss=True)
            if cloud_low_memory
            else render_data_card_cached(data_path, cfg.raw, is_boss=True)
        )
        st.image(img, width=_card_w())
