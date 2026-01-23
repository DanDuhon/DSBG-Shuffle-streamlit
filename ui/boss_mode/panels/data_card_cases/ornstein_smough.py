import streamlit as st

from core.behavior.generation import render_dual_boss_data_cards
from ui.campaign_mode.core import _card_w


def try_render_ornstein_smough_data_card(*, cfg, state) -> bool:
    if not ("Ornstein" in cfg.raw and "Smough" in cfg.raw):
        return False

    o_img, s_img = render_dual_boss_data_cards(cfg.raw)

    ornstein_dead = st.session_state.get("ornstein_dead", False)
    smough_dead = st.session_state.get("smough_dead", False)

    if ornstein_dead and not smough_dead:
        st.image(s_img, width=_card_w())
    elif smough_dead and not ornstein_dead:
        st.image(o_img, width=_card_w())
    else:
        o_col, s_col = st.columns(2)
        with o_col:
            st.image(o_img, width=_card_w())
        with s_col:
            st.image(s_img, width=_card_w())

    return True
