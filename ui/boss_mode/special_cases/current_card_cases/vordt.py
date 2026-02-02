import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from ui.campaign_mode.core import _card_w


def try_render_vordt_current(*, cfg, state, current) -> bool:
    if cfg.name != "Vordt of the Boreal Valley" or not isinstance(current, tuple):
        return False

    move_card, atk_card = current

    c1, c2 = st.columns(2)
    with c1:
        move_path = _behavior_image_path(cfg, move_card)
        w = _card_w()

        cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
        render_behavior = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
        move_img = render_behavior(
            move_path,
            cfg.behaviors.get(move_card, {}),
            is_boss=True,
        )
        st.image(move_img, width=w)

    with c2:
        atk_path = _behavior_image_path(cfg, atk_card)
        w = _card_w()
        atk_img = render_behavior(
            atk_path,
            cfg.behaviors.get(atk_card, {}),
            is_boss=True,
        )
        st.image(atk_img, width=w)

    return True
