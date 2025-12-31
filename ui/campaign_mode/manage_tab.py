# ui/campaign_mode/manage_tab.py
import streamlit as st
from typing import Any, Dict
from ui.campaign_mode.manage_tab_v1 import _render_v1_campaign
from ui.campaign_mode.manage_tab_v2 import _render_v2_campaign


def _render_campaign_tab(
    bosses_by_name: Dict[str, Any],
    invaders_by_name: Dict[str, Any],
) -> None:
    version = st.session_state.get("campaign_rules_version", "V1")

    if version == "V1":
        state = st.session_state.get("campaign_v1_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v1_campaign(state, bosses_by_name)
    else:
        state = st.session_state.get("campaign_v2_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v2_campaign(state, bosses_by_name)
