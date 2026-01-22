# ui/boss_mode_tab.py
import streamlit as st

from core.behavior.logic import _ensure_state
from core.behavior.render import render_health_tracker

from ui.boss_mode.state import ensure_boss_state
from ui.boss_mode.panels.combat_controls import render_combat_controls
from ui.boss_mode.panels.current_card import render_current_card_column
from ui.boss_mode.panels.heatup_prompt import render_heatup_prompt
from ui.boss_mode.panels.options import render_boss_info_and_options
from ui.boss_mode.panels.data_card import render_data_card_column
from ui.boss_mode.panels.selector import (
    apply_pending_boss_preselect,
    get_available_categories,
    get_or_build_catalog,
    render_boss_selector,
)


BOSS_MODE_CATEGORIES = ["Mini Bosses", "Main Bosses", "Mega Bosses"]


def render():
    _ensure_state()

    catalog = get_or_build_catalog()
    apply_pending_boss_preselect(catalog)
    available_cats = get_available_categories(
        catalog=catalog,
        boss_mode_categories=BOSS_MODE_CATEGORIES,
    )

    # --- Enemy selector row
    col_sel, col_info = st.columns([2, 1])

    with col_sel:
        entry = render_boss_selector(
            catalog=catalog,
            available_categories=available_cats,
        )

    if not entry:
        st.info("Select a boss to begin.")
        return

    # Ensure we have a state + cfg for this enemy
    state, cfg = ensure_boss_state(entry)

    with col_info:
        render_boss_info_and_options(cfg=cfg, state=state)

    # Draw / Heat-up buttons
    if not st.session_state.get("ui_compact", False):
        c_hp_btns = st.columns([1, 1])
        with c_hp_btns[0]:
            cfg.entities = render_health_tracker(cfg, state)
        with c_hp_btns[1]:
            render_combat_controls(where="top")

    render_heatup_prompt(cfg=cfg, state=state)

    # --- Main fight view
    col_left, col_right = st.columns([1, 1])

    # LEFT: Data Card
    with col_left:
        render_data_card_column(cfg=cfg, state=state)

    # RIGHT: Deck + current card
    with col_right:
        render_current_card_column(cfg=cfg, state=state)

    # Mobile UX: duplicate controls below the cards in "Compact layout".
    if st.session_state.get("ui_compact", False):
        render_combat_controls(where="bottom")
