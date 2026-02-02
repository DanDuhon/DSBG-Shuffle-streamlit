import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import (
    render_behavior_card_cached,
    render_behavior_card_uncached,
    render_dual_boss_behavior_card,
)
from ui.campaign_mode.core import _card_w


def try_render_ornstein_smough_current(*, cfg, state, current) -> bool:
    if cfg.name != "Ornstein & Smough":
        return False

    current_name = current
    if current_name:
        if "&" in (current_name or ""):
            img = render_dual_boss_behavior_card(
                cfg.raw,
                current_name,
                boss_name=cfg.name,
            )
        else:
            cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
            render_behavior = (
                render_behavior_card_uncached
                if cloud_low_memory
                else render_behavior_card_cached
            )
            img = render_behavior(
                _behavior_image_path(cfg, current_name),
                cfg.behaviors.get(current_name, {}),
                is_boss=True,
            )

        st.image(img, width=_card_w())

    return True
