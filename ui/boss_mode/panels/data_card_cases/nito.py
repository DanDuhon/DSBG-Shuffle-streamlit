import streamlit as st

from core.behavior.generation import render_data_card_cached
from ui.boss_mode.panels.encounter_setups import render_nito_setup_panel
from ui.campaign_mode.core import _card_w


def try_render_nito_data_card(*, cfg, state) -> bool:
    if cfg.name != "Gravelord Nito":
        return False

    data_col, setup_col = st.columns([1, 1])

    with data_col:
        data_path = cfg.display_cards[0] if cfg.display_cards else None
        if data_path:
            img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
            st.image(img, width=_card_w())

    with setup_col:
        render_nito_setup_panel()

    return True
