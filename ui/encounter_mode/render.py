from typing import Any, Dict
import streamlit as st

from ui.encounter_mode.tabs import setup_tab
from ui.encounter_mode.tabs import play_tab
from ui.encounter_mode.tabs import events_tab


def render(settings: Dict[str, Any], valid_party: bool, character_count: int) -> None:
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

    if cloud_low_memory:
        prev = st.session_state.get("_encounter_mode_tab_last")
        tab = st.radio(
            "Encounter Mode",
            ["Setup", "Events", "Play"],
            horizontal=True,
            key="encounter_mode_tab",
        )

        if prev != tab:
            # Drop heavyweight encounter render artifacts on tab switches.
            try:
                enc = st.session_state.get("current_encounter")
                if isinstance(enc, dict):
                    for k in ("card_img", "card_bytes", "buf"):
                        enc.pop(k, None)
            except Exception:
                pass
        st.session_state["_encounter_mode_tab_last"] = tab

        if tab == "Setup":
            setup_tab.render(settings=settings, valid_party=valid_party, character_count=character_count)
        elif tab == "Events":
            events_tab.render(settings)
        else:
            play_tab.render(settings=settings)
        return

    tab_setup, tab_events, tab_play = st.tabs(["Setup", "Events", "Play"])
    with tab_setup:
        setup_tab.render(settings=settings, valid_party=valid_party, character_count=character_count)
    with tab_events:
        events_tab.render(settings)
    with tab_play:
        play_tab.render(settings=settings)
