#ui/campaign_mode/render.py
import streamlit as st
from ui.campaign_mode.core import get_bosses, get_invaders
from ui.campaign_mode.state import _get_settings
from ui.campaign_mode.setup_tab import _render_setup_header, _render_v1_setup, _render_v2_setup, _render_save_load_section
from ui.campaign_mode.manage_tab import _render_campaign_tab
from ui.campaign_mode.play_tab import _render_campaign_play_tab


def render() -> None:
    bosses = get_bosses()
    invaders = get_invaders()

    setup_tab, campaign_tab, play_tab = st.tabs(
        ["Setup", "Manage Campaign", "Play Encounter"]
    )

    with setup_tab:
        settings = _get_settings()
        version, player_count = _render_setup_header(settings)
        if version == "V1":
            state = _render_v1_setup(bosses, settings, player_count)
        else:
            state = _render_v2_setup(bosses, settings, player_count)
        _render_save_load_section(version, state, settings)

    # IMPORTANT: Play tab before Manage Campaign tab so we can safely
    # update st.session_state[souls_key] before the Soul cache widget
    # is created in this run.
    with play_tab:
        _render_campaign_play_tab(bosses, invaders)

    with campaign_tab:
        _render_campaign_tab(bosses, invaders)