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

    # `on_change="rerun"` + `.open` so only the visible tab body runs. All three
    # used to execute on every rerun -- Play renders the encounter card, every
    # enemy panel and the invader panels, while the user is still on Setup.
    # Costs a server round-trip per tab switch.
    tab_setup, tab_events, tab_play = st.tabs(
        ["Setup", "Events", "Play"], on_change="rerun"
    )
    if tab_setup.open:
        with tab_setup:
            setup_tab.render(settings=settings, valid_party=valid_party, character_count=character_count)
    if tab_events.open:
        with tab_events:
            events_tab.render(settings)
    if tab_play.open:
        with tab_play:
            play_tab.render(settings=settings)
