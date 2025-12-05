from __future__ import annotations

import streamlit as st
import pyautogui
from core.encounter_rules import make_encounter_key
from core.encounter import timer as timer_mod
from ui.encounter_mode import play_state
from ui.encounter_mode import play_panels
from ui.encounter_mode import invader_panel


def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. This mirrors the helper in play_panels so the
    timer logic can share the same decision.
    """
    # 1) Encounter dict itself
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    # 2) Session state override (if you set one from Setup)
    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    # 3) Settings-level toggle keyed by encounter key
    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def render(settings: dict) -> None:
    """
    Encounter Play tab.

    Assumes:
    - Setup tab has populated st.session_state.current_encounter
    - Events tab has optionally populated st.session_state.encounter_events
    """
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    encounter = st.session_state.current_encounter
    encounter_id = play_state.get_encounter_id(encounter)
    play = play_state.ensure_play_state(encounter_id)

    # Build encounter key + edited flag once so timer & panels agree
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    # Per-encounter special timer behaviour (manual increment, reset button, etc.)
    timer_behavior = timer_mod.get_timer_behavior(encounter, edited=edited)

    # Apply any pending action (from button click in the previous run)
    action = play_state.apply_pending_action(play, timer_behavior)

    # If the user hit the Reset button, also reset any invader decks/HP
    # tied to this encounter.
    if action == "reset":
        invader_panel.reset_invaders_for_encounter(encounter)

    # Decide if any timer objective wants to stop progression
    player_count = play_state.get_player_count()
    stop_on_timer_objective = timer_mod.should_stop_on_timer_objective(
        encounter=encounter,
        edited=edited,
        player_count=player_count,
        timer_value=play["timer"],
    )

    # -----------------------------------------------------------------
    # Main layout: 3 columns
    # Left: timer/phase + controls + triggers + events + log
    # Middle: objectives + rules
    # Right: enemy behavior cards (placeholder for now)
    # -----------------------------------------------------------------
    col_left, col_mid, col_right = st.columns([1, 1, 1], gap="large")

    # LEFT COLUMN
    with col_left:
        timer_phase_container = st.container()
        controls_container = st.container()

        # Timer + phase (top row)
        with timer_phase_container:
            play_panels._render_timer_and_phase(play)

        # Turn controls (Next Turn can be disabled by timer objective)
        with controls_container:
            play_panels._render_turn_controls(
                play,
                stop_on_timer_objective=stop_on_timer_objective,
                timer_behavior=timer_behavior,
            )
            play_panels._render_encounter_triggers(encounter, play, settings)
            play_panels._render_attached_events(encounter)
            play_panels._render_log(play)

    # MIDDLE COLUMN
    with col_mid:
        objectives_container = st.container()
        rest_container = st.container()
        rewards_container = st.container()

        # Objectives (including Trials)
        with objectives_container:
            play_panels._render_objectives(encounter, settings)

        # Rules (which incorporate timer/phase-aware upcoming rules)
        with rest_container:
            play_panels._render_rules(encounter, settings, play)

        # Rewards summary
        with rewards_container:
            play_panels._render_rewards(encounter, settings)

    # RIGHT COLUMN
    with col_right.container(height=int(pyautogui.size().height * 0.65)):
        tab_enemies, tab_invaders = st.tabs(["Encounter Enemies", "Invaders"])

        # Standard encounter enemies
        with tab_enemies:
            play_panels._render_enemy_behaviors(encounter)

        # Invader behavior decks + HP tracker (only shows content if
        # this encounter actually has invaders with behavior decks).
        with tab_invaders:
            invader_panel.render_invaders_tab(encounter)
