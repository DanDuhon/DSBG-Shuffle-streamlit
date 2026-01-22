import streamlit as st

from ui.shared.health_tracker import render_health_tracker

from ui.boss_mode.panels.data_card_cases.chariot import try_render_chariot_data_card
from ui.boss_mode.panels.data_card_cases.default import render_default_data_card
from ui.boss_mode.panels.data_card_cases.nito import try_render_nito_data_card
from ui.boss_mode.panels.data_card_cases.ornstein_smough import (
    try_render_ornstein_smough_data_card,
)
from ui.boss_mode.panels.data_card_cases.vordt import try_render_vordt_data_card


def render_data_card_column(*, cfg, state) -> None:
    """Render Boss Mode LEFT column (data card + boss-specific panels).

    This function preserves existing session keys, widget keys, and layout behavior.
    """

    handled = (
        try_render_chariot_data_card(cfg=cfg, state=state)
        or try_render_nito_data_card(cfg=cfg, state=state)
        or try_render_ornstein_smough_data_card(cfg=cfg, state=state)
        or try_render_vordt_data_card(cfg=cfg, state=state)
    )
    if not handled:
        render_default_data_card(cfg=cfg, state=state)

    if st.session_state.get("ui_compact", False):
        cfg.entities = render_health_tracker(cfg, state)
