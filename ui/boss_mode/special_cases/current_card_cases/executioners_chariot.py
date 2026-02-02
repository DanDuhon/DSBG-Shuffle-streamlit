import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from ui.boss_mode.executioners_chariot_death_race import (
    DEATH_RACE_BEHAVIOR_NAME,
    EXECUTIONERS_CHARIOT_NAME,
    _ec_death_race_next_pattern,
    _ec_render_death_race_aoe,
)
from ui.campaign_mode.core import _card_w


def try_render_executioners_chariot_current(*, cfg, state, current) -> bool:
    if not (
        cfg.name == EXECUTIONERS_CHARIOT_NAME
        and isinstance(current, str)
        and current.startswith(DEATH_RACE_BEHAVIOR_NAME)
    ):
        return False

    draw_token = st.session_state.get("boss_mode_draw_token", 0)
    last_key = f"boss_mode_last_draw::{cfg.name}"
    last_draw = st.session_state.get(last_key)
    is_new_draw = last_draw != draw_token
    st.session_state[last_key] = draw_token

    mode = (
        "generated" if st.session_state.get("ec_death_race_generate", False) else "deck"
    )

    pattern_nodes = state.get("ec_death_race_current_pattern")
    prev_mode = state.get("ec_death_race_current_mode")
    if pattern_nodes is None or prev_mode != mode or is_new_draw:
        pattern_nodes = _ec_death_race_next_pattern(state, mode)
        state["ec_death_race_current_pattern"] = pattern_nodes
        state["ec_death_race_current_mode"] = mode

    death_race_path = _behavior_image_path(cfg, current)
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    render_behavior = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
    death_race_img = render_behavior(
        death_race_path,
        cfg.behaviors.get(current, {}),
        is_boss=True,
    )

    aoe_img = _ec_render_death_race_aoe(cfg, pattern_nodes)

    c1, c2 = st.columns(2)
    with c1:
        w = _card_w()
        st.image(death_race_img, width=w)
    with c2:
        st.image(aoe_img, width=_card_w())

    return True
