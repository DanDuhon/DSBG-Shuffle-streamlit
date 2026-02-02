import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from ui.boss_mode.kalameet_fiery_ruin import (
    BLACK_DRAGON_KALAMEET_NAME,
    KALAMEET_HELLFIRE_PREFIX,
    _kalameet_next_pattern,
    _kalameet_render_fiery_ruin,
)
from ui.campaign_mode.core import _card_w


def try_render_kalameet_current(*, cfg, state, current) -> bool:
    if not (
        cfg.name == BLACK_DRAGON_KALAMEET_NAME
        and isinstance(current, str)
        and current.startswith(KALAMEET_HELLFIRE_PREFIX)
    ):
        return False

    last_key = f"boss_mode_last_current::{cfg.name}"
    last_current = st.session_state.get(last_key)
    is_new_draw = last_current != current
    st.session_state[last_key] = current

    mode = "generated" if st.session_state.get("kalameet_aoe_generate", False) else "deck"

    pattern_nodes = state.get("kalameet_aoe_current_pattern")
    prev_mode = state.get("kalameet_aoe_current_mode")
    if pattern_nodes is None or prev_mode != mode or is_new_draw:
        pattern_nodes = _kalameet_next_pattern(state, mode)
        state["kalameet_aoe_current_pattern"] = pattern_nodes
        state["kalameet_aoe_current_mode"] = mode

    hellfire_path = _behavior_image_path(cfg, current)
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    render_behavior = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
    hellfire_img = render_behavior(
        hellfire_path,
        cfg.behaviors.get(current, {}),
        is_boss=True,
    )

    fiery_img = _kalameet_render_fiery_ruin(cfg, pattern_nodes)

    c1, c2 = st.columns(2)
    with c1:
        w = _card_w()
        st.image(hellfire_img, width=w)
    with c2:
        st.image(fiery_img, width=_card_w())

    return True
