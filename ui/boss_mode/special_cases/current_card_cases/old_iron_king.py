import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from ui.boss_mode.old_iron_king_blasted_nodes import (
    OLD_IRON_KING_NAME,
    OIK_FIRE_BEAM_PREFIX,
    _oik_blasted_next_pattern,
    _oik_render_blasted_nodes,
)
from ui.campaign_mode.core import _card_w


def try_render_old_iron_king_current(*, cfg, state, current) -> bool:
    if not (
        cfg.name == OLD_IRON_KING_NAME
        and isinstance(current, str)
        and current.startswith(OIK_FIRE_BEAM_PREFIX)
    ):
        return False

    last_key = f"boss_mode_last_current::{cfg.name}"
    last_current = st.session_state.get(last_key)
    is_new_draw = last_current != current
    st.session_state[last_key] = current

    mode = "generated" if st.session_state.get("oik_blasted_generate", False) else "deck"

    pattern_nodes = state.get("oik_blasted_current_pattern")
    prev_mode = state.get("oik_blasted_current_mode")
    if pattern_nodes is None or prev_mode != mode or is_new_draw:
        pattern_nodes = _oik_blasted_next_pattern(state, mode)
        state["oik_blasted_current_pattern"] = pattern_nodes
        state["oik_blasted_current_mode"] = mode

    beam_path = _behavior_image_path(cfg, current)
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    render_behavior = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
    beam_img = render_behavior(
        beam_path,
        cfg.behaviors.get(current, {}),
        is_boss=True,
    )

    blasted_img = _oik_render_blasted_nodes(cfg, pattern_nodes)

    c1, c2 = st.columns(2)
    with c1:
        w = _card_w()
        st.image(beam_img, width=w)
    with c2:
        st.image(blasted_img, width=_card_w())

    return True
