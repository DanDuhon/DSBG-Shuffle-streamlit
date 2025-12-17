# ui/encounter_mode/play_tab.py
from __future__ import annotations

import re
import streamlit as st

from core.encounter_rules import make_encounter_key
from core.encounter import timer as timer_mod
from ui.encounter_mode import play_state, play_panels, invader_panel
from ui.encounter_mode.assets import encounterKeywords, editedEncounterKeywords, keywordText


def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. This mirrors the helper in play_panels so the
    timer logic can share the same decision.
    """
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def _keyword_label(keyword: str) -> str:
    # Prefer the human-facing label from keywordText (everything before the em-dash).
    txt = keywordText.get(keyword)
    if isinstance(txt, str) and txt.strip():
        return txt.split("—", 1)[0].strip()

    # Fallback: camelCase -> "Title Case"
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", str(keyword)).replace("_", " ").strip()
    return spaced.title() if spaced else str(keyword)


def _get_encounter_keywords(name: str, expansion: str, edited: bool) -> list[str]:
    src = editedEncounterKeywords if edited else encounterKeywords
    raw = (src.get((name, expansion)) or []) if isinstance(src, dict) else []

    out: list[str] = []
    seen: set[str] = set()
    for k in raw:
        if not k:
            continue
        k = str(k)
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _render_keywords_summary(encounter: dict, edited: bool) -> None:
    # V1 cards typically have no keyword section; keep the UI quiet.
    expansion = encounter.get("expansion")
    if not expansion:
        return

    name = encounter.get("encounter_name") or encounter.get("name") or ""
    if not name:
        return

    keys = _get_encounter_keywords(name, expansion, edited)
    if not keys:
        return

    labels = ", ".join(_keyword_label(k) for k in keys)
    st.markdown("#### Rules")
    st.caption(f"Keywords: {labels}")


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

    name = encounter.get("encounter_name") or encounter.get("name") or "Unknown Encounter"
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    timer_behavior = timer_mod.get_timer_behavior(encounter, edited=edited)
    action = play_state.apply_pending_action(play, timer_behavior)

    if action == "reset":
        invader_panel.reset_invaders_for_encounter(encounter)

    player_count = play_state.get_player_count()
    stop_on_timer_objective = timer_mod.should_stop_on_timer_objective(
        encounter=encounter,
        edited=edited,
        player_count=player_count,
        timer_value=play["timer"],
    )

    ui_compact = bool(st.session_state.get("ui_compact", False))

    if ui_compact:
        play_panels._render_timer_and_phase(play)
        play_panels._render_turn_controls(
            play,
            stop_on_timer_objective=stop_on_timer_objective,
            timer_behavior=timer_behavior,
            compact=True,
        )
        play_panels._render_encounter_triggers(encounter, play, settings)
        play_panels._render_current_rules(encounter, settings, play)
        play_panels._render_keywords_summary(encounter, settings)

        tab_enemies, tab_invaders, tab_rules, tab_other = st.tabs(
            ["Enemies", "Invaders", "Rules", "Other"]
        )

        with tab_enemies:
            play_panels._render_enemy_behaviors(encounter, columns=1)

        with tab_invaders:
            invader_panel.render_invaders_tab(encounter)

        with tab_rules:
            play_panels._render_rules(encounter, settings, play)

        with tab_other:
            play_panels._render_objectives(encounter, settings)
            play_panels._render_rewards(encounter, settings)
            play_panels._render_attached_events(encounter)
            play_panels._render_log(play)

        return

    # -----------------------------------------------------------------
    # DESKTOP UI (existing 3-column layout)
    # -----------------------------------------------------------------
    col_left, col_mid, col_right = st.columns([1, 1, 1], gap="large")

    with col_left:
        timer_phase_container = st.container()
        controls_container = st.container()

        with timer_phase_container:
            play_panels._render_timer_and_phase(play)

        with controls_container:
            play_panels._render_turn_controls(
                play,
                stop_on_timer_objective=stop_on_timer_objective,
                timer_behavior=timer_behavior,
            )
            play_panels._render_encounter_triggers(encounter, play, settings)
            play_panels._render_attached_events(encounter)
            play_panels._render_log(play)

    with col_mid:
        objectives_container = st.container()
        rest_container = st.container()
        rewards_container = st.container()

        with objectives_container:
            play_panels._render_objectives(encounter, settings)

        with rest_container:
            play_panels._render_rules(encounter, settings, play)

        with rewards_container:
            play_panels._render_rewards(encounter, settings)

    with col_right.container():
        tab_enemies, tab_invaders = st.tabs(["Encounter Enemies", "Invaders"])

        with tab_enemies:
            play_panels._render_enemy_behaviors(encounter, columns=2)

        with tab_invaders:
            invader_panel.render_invaders_tab(encounter)
