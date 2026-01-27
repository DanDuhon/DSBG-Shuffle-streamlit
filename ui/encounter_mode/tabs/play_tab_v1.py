# ui/encounter_mode/tabs/play_tab_v1.py
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from ui.encounter_mode.panels import play_panels
from ui.encounter_mode.state import play_state


# V1 Play tab only: tweak this if you don't like the layout.
V1_BEHAVIOR_COLUMNS = 4


# Streamlit 1.50 supports fragments. Use them to keep the heavy Enemy Behavior
# cards render from re-running on every Play interaction.
if hasattr(st, "fragment"):

    @st.fragment
    def _enemy_cards_fragment(encounter_id: str, *, columns: int = 2) -> None:
        enc = st.session_state.get("current_encounter")
        if not isinstance(enc, dict):
            return
        if play_state.get_encounter_id(enc) != encounter_id:
            return
        play_panels._render_enemy_behaviors(enc, columns=columns)

else:

    def _enemy_cards_fragment(encounter_id: str, *, columns: int = 2) -> None:
        enc = st.session_state.get("current_encounter")
        if not isinstance(enc, dict):
            return
        play_panels._render_enemy_behaviors(enc, columns=columns)


def render(settings: dict, campaign: bool = False) -> None:  # noqa: ARG001
    """Simplified V1 Encounter Play UI.

    Intentionally omits: timer, phase, turn controls, triggers, attached events,
    turn log, and rules.

    `campaign` is accepted for API compatibility with V2 Play.
    """
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    encounter: Dict[str, Any] = st.session_state.current_encounter
    encounter_id = play_state.get_encounter_id(encounter)

    ui_compact = bool(st.session_state.get("ui_compact", False))

    # Always compute/store totals so Campaign Play can apply rewards.
    totals = play_panels.compute_reward_totals(encounter, settings, {"timer": 0})
    play_panels.store_reward_totals_for_campaign(encounter, totals)
    souls = int(totals.get("souls") or 0)
    treasure = int(totals.get("treasure") or 0)

    if ui_compact:
        play_panels._render_objectives(encounter, settings)
        st.markdown("#### Rewards")
        st.markdown(f"- Souls: **{souls}**")
        if treasure:
            st.markdown(f"- Draw {treasure} treasures")
        _enemy_cards_fragment(encounter_id, columns=1)
        return

    col_left, col_right = st.columns([1, 3], gap="large")
    with col_left:
        play_panels._render_objectives(encounter, settings)
        st.markdown("#### Rewards")
        st.markdown(f"- Souls: **{souls}**")
        if treasure:
            st.markdown(f"- Draw {treasure} treasures")

    with col_right:
        _enemy_cards_fragment(encounter_id, columns=V1_BEHAVIOR_COLUMNS)
