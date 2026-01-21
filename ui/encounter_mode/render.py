from typing import Any, Dict
import streamlit as st

from ui.encounter_mode.tabs import setup_tab
from ui.encounter_mode.tabs import play_tab
from ui.encounter_mode.tabs import events_tab


def render(settings: Dict[str, Any], valid_party: bool, character_count: int) -> None:
    tab_setup, tab_events, tab_play = st.tabs(["Setup", "Events", "Play"])
    with tab_setup:
        setup_tab.render(settings=settings, valid_party=valid_party, character_count=character_count)
    with tab_events:
        events_tab.render(settings)
    with tab_play:
        play_tab.render(settings=settings)
