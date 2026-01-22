from core.behavior.generation import render_data_card_cached
import streamlit as st

from ui.campaign_mode.core import _card_w


def render_default_data_card(*, cfg, state) -> None:
    data_path = cfg.display_cards[0] if cfg.display_cards else None
    if data_path:
        img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
        st.image(img, width=_card_w())
