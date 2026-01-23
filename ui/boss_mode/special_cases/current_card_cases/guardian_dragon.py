import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached
from ui.boss_mode.guardian_dragon_fiery_breath import (
    GUARDIAN_CAGE_PREFIX,
    GUARDIAN_DRAGON_NAME,
    _guardian_fiery_next_pattern,
    _guardian_render_fiery_breath,
)
from ui.campaign_mode.core import _card_w


def try_render_guardian_dragon_current(*, cfg, state, current) -> bool:
    if not (
        cfg.name == GUARDIAN_DRAGON_NAME
        and isinstance(current, str)
        and current.startswith(GUARDIAN_CAGE_PREFIX)
    ):
        return False

    last_key = f"boss_mode_last_current::{cfg.name}"
    last_current = st.session_state.get(last_key)
    is_new_draw = last_current != current
    st.session_state[last_key] = current

    mode = (
        "generated" if st.session_state.get("guardian_fiery_generate", False) else "deck"
    )

    pattern_nodes = state.get("guardian_fiery_current_pattern")
    prev_mode = state.get("guardian_fiery_current_mode")
    if pattern_nodes is None or prev_mode != mode or is_new_draw:
        pattern_nodes = _guardian_fiery_next_pattern(state, mode)
        state["guardian_fiery_current_pattern"] = pattern_nodes
        state["guardian_fiery_current_mode"] = mode

    cage_path = _behavior_image_path(cfg, current)
    cage_beh = cfg.behaviors.get(current, {}) or {}
    cage_beh_no_dodge = dict(cage_beh)
    cage_beh_no_dodge.pop("dodge", None)
    cage_img = render_behavior_card_cached(
        cage_path,
        cage_beh_no_dodge,
        is_boss=True,
    )

    fiery_img = _guardian_render_fiery_breath(cfg, pattern_nodes)

    c1, c2 = st.columns(2)
    with c1:
        w = _card_w()
        st.image(cage_img, width=w)
    with c2:
        st.image(fiery_img, width=_card_w())

    return True
