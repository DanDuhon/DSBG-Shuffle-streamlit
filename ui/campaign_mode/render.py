#ui/campaign_mode/render.py
import streamlit as st
from ui.campaign_mode.persistence import get_bosses, get_invaders
from ui.campaign_mode.state import _get_settings
from ui.campaign_mode.tabs.setup_tab import (
    _render_save_load_section,
    _render_setup_header,
    _render_v1_setup,
    _render_v2_setup,
)
from ui.campaign_mode.tabs.manage_tab import _render_campaign_tab
from ui.campaign_mode.tabs.play_tab import _render_campaign_play_tab


def render() -> None:
    bosses = get_bosses()
    invaders = get_invaders()

    # Require at least one selected character in campaign mode
    settings_check = _get_settings()
    if not settings_check.get("selected_characters"):
        st.error("No characters selected. Please pick at least one character in the sidebar before using Campaign Mode.")
        st.stop()

    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

    if cloud_low_memory:
        prev = st.session_state.get("_campaign_mode_tab_last")
        tab = st.radio(
            "Campaign Mode",
            ["Setup", "Manage Campaign", "Play Encounter"],
            horizontal=True,
            key="campaign_mode_tab",
        )
        if prev != tab:
            # Drop any stray encounter render artifacts (not campaign state).
            try:
                enc = st.session_state.get("current_encounter")
                if isinstance(enc, dict):
                    for k in ("card_img", "card_bytes", "buf"):
                        enc.pop(k, None)
            except Exception:
                pass
        st.session_state["_campaign_mode_tab_last"] = tab

        if tab == "Setup":
            settings = settings_check
            version, player_count = _render_setup_header(settings)
            if version == "V1":
                state = _render_v1_setup(bosses, settings, player_count)
            else:
                state = _render_v2_setup(bosses, settings, player_count)
            _render_save_load_section(version, state, settings)
            return

        if tab == "Play Encounter":
            _render_campaign_play_tab(bosses, invaders)
            return

        _render_campaign_tab(bosses, invaders)
        return

    setup_tab, campaign_tab, play_tab = st.tabs(
        ["Setup", "Manage Campaign", "Play Encounter"]
    )

    with setup_tab:
        settings = settings_check
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