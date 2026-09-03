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
from ui.campaign_mode.tabs.boss_fight_tab import _render_campaign_boss_fight_tab
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
            ["Setup", "Manage Campaign", "Play Encounter", "Boss Fight"],
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

        if tab == "Boss Fight":
            _render_campaign_boss_fight_tab(bosses, invaders)
            return

        _render_campaign_tab(bosses, invaders)
        return

    # `on_change="rerun"` + `.open` so only the visible tab's body executes.
    # Without it every tab runs on every rerun: with the party on an encounter
    # node the hidden Play tab rendered the whole Encounter Mode play UI
    # (encounter card, enemy panels, invader panels and their card renders),
    # and on a boss node Manage and Boss Fight each pushed the same multi-MB
    # boss data card. The cost is a server round-trip per tab switch.
    #
    # Safe here because no tab depends on another having run: Play never sets
    # the souls widget key directly, it calls `queue_widget_set`, and the queue
    # survives in session_state until `apply_pending_widget_sets()` drains it
    # when Manage next renders. (That also retires the old constraint that Play
    # had to render before Manage -- exactly one tab body runs now.)
    setup_tab, campaign_tab, play_tab, boss_fight_tab = st.tabs(
        ["Setup", "Manage Campaign", "Play Encounter", "Boss Fight"],
        on_change="rerun",
    )

    if setup_tab.open:
        with setup_tab:
            settings = settings_check
            version, player_count = _render_setup_header(settings)
            if version == "V1":
                state = _render_v1_setup(bosses, settings, player_count)
            else:
                state = _render_v2_setup(bosses, settings, player_count)
            _render_save_load_section(version, state, settings)

    if play_tab.open:
        with play_tab:
            _render_campaign_play_tab(bosses, invaders)

    if campaign_tab.open:
        with campaign_tab:
            _render_campaign_tab(bosses, invaders)

    if boss_fight_tab.open:
        with boss_fight_tab:
            _render_campaign_boss_fight_tab(bosses, invaders)