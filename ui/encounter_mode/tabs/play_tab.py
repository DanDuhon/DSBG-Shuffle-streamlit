"""Encounter Play router.

The public API stays as ui.encounter_mode.tabs.play_tab.render(...), but the
implementation lives in separate V1/V2 modules.
"""

from __future__ import annotations

import streamlit as st

from core.expansions import is_v2_expansion
from ui.encounter_mode.tabs import play_tab_v1, play_tab_v2


def render(settings: dict, campaign: bool = False) -> None:
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    enc = st.session_state.get("current_encounter")
    if not isinstance(enc, dict):
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    expansion = enc.get("expansion")
    if is_v2_expansion(expansion):
        play_tab_v2.render(settings=settings, campaign=campaign)
    else:
        play_tab_v1.render(settings=settings, campaign=campaign)
