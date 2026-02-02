import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_behavior_card_uncached
from ui.campaign_mode.core import _card_w


def try_render_gaping_dragon_current(*, cfg, state, current) -> bool:
    if cfg.name != "Gaping Dragon" or not isinstance(current, str) or not current.startswith(
        "Stomach Slam"
    ):
        return False

    stomach_path = _behavior_image_path(cfg, current)
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    render_behavior = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
    stomach_img = render_behavior(
        stomach_path,
        cfg.behaviors[current],
        is_boss=True,
    )

    crawl_key = None
    for key in cfg.behaviors.keys():
        if key.startswith("Crawling Charge"):
            crawl_key = key
            break

    if crawl_key:
        crawl_path = _behavior_image_path(cfg, crawl_key)
        crawl_img = render_behavior(
            crawl_path,
            cfg.behaviors[crawl_key],
            is_boss=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            w = _card_w()
            st.image(stomach_img, width=w)

        with c2:
            w = _card_w()
            st.image(crawl_img, width=w)

    return True
