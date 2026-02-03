# ui/campaign_mode/manage_tab.py
import streamlit as st
from typing import Any, Dict

from ui.campaign_mode.tabs.manage_tab_v1 import _render_v1_campaign
from ui.campaign_mode.tabs.manage_tab_v2 import _render_v2_campaign
from ui.campaign_mode.state import _get_settings, _ensure_v1_state, _ensure_v2_state
from ui.campaign_mode.helpers import get_player_count_from_settings


def _render_campaign_tab(
    bosses_by_name: Dict[str, Any],
    invaders_by_name: Dict[str, Any],
) -> None:
    version = st.session_state.get("campaign_rules_version", "V1")

    settings = _get_settings()
    player_count = get_player_count_from_settings(settings)

    if version == "V1":
        state = _ensure_v1_state(player_count)
        if not isinstance(state.get("campaign"), dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v1_campaign(state, bosses_by_name)
    else:
        state = _ensure_v2_state(player_count)
        if not isinstance(state.get("campaign"), dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v2_campaign(state, bosses_by_name)
