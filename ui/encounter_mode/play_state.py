from __future__ import annotations
from datetime import datetime
import streamlit as st


def get_encounter_id(encounter: dict):
    """Best-effort way to identify the current encounter for resetting state."""
    for key in ("id", "slug", "encounter_slug", "encounter_name"):
        if key in encounter:
            return encounter[key]
    return None


def get_player_count() -> int:
    """Return the current player count from session_state, clamped to at least 1."""
    try:
        pc = int(st.session_state.get("player_count", 1))
    except Exception:
        pc = 1
    return max(pc, 1)


def ensure_play_state(encounter_id):
    """
    Keep a small piece of state for the Play tab.
    Reset automatically when the active encounter changes.
    """
    state = st.session_state.get("encounter_play")

    if (not state) or (state.get("encounter_id") != encounter_id):
        state = {
            "encounter_id": encounter_id,
            "phase": "enemy",   # "enemy" | "player"
            "timer": 0,         # starts at 0, increments after player phase
            "log": [],
        }
        st.session_state["encounter_play"] = state

    return state


def apply_pending_action(play_state: dict, timer_behavior: dict):
    """
    If the last run scheduled a pending turn action (next, prev, reset),
    apply it *before* rendering anything, and return the action string.

    Returns:
        "next", "prev", "reset", or None if no pending action was set.
    """
    action = st.session_state.pop("encounter_play_pending_action", None)

    disable_auto_timer = bool(timer_behavior.get("manual_increment", False))

    if action == "next":
        advance_turn(play_state, disable_auto_timer=disable_auto_timer)
    elif action == "prev":
        previous_turn(play_state)
    elif action == "reset":
        reset_play_state(play_state)

    return action


def log_entry(play_state: dict, text: str):
    """Append an entry to the play log, capturing timer, phase, and a timestamp."""
    play_state.setdefault("log", []).append(
        {
            "timer": play_state.get("timer", 0),
            "phase": play_state.get("phase", "enemy"),
            "text": text,
            "time": datetime.now().strftime("%H:%M"),
        }
    )


def advance_turn(play_state: dict, disable_auto_timer: bool = False) -> None:
    """
    Smart 'Next Turn' behavior:

    - Start: Timer 0, Enemy Phase.
    - Enemy → Player (no timer change).
    - Player → Enemy and **timer +1**, unless disable_auto_timer is True.
    """
    if play_state["phase"] == "enemy":
        play_state["phase"] = "player"
        log_entry(play_state, "Advanced to Player Phase")
    else:  # player -> enemy
        if not disable_auto_timer:
            play_state["timer"] += 1
            play_state["phase"] = "enemy"
            log_entry(play_state, "Advanced to Enemy Phase; timer increased")
        else:
            play_state["phase"] = "enemy"
            log_entry(
                play_state,
                "Advanced to Enemy Phase (Timer unchanged due to encounter rule)",
            )


def previous_turn(play_state: dict) -> None:
    """
    Reverse of advance_turn, as best we can:

    - Player → Enemy (no timer change).
    - Enemy → Player and **timer -1**, but never below 0.
    """
    if play_state["phase"] == "player":
        play_state["phase"] = "enemy"
        log_entry(play_state, "Reverted to Enemy Phase")
    else:  # enemy
        if play_state["timer"] > 0:
            play_state["timer"] -= 1
            play_state["phase"] = "player"
            log_entry(
                play_state,
                f"Reverted to Player Phase; timer reduced to {play_state['timer']}",
            )
        else:
            log_entry(play_state, "Already at starting state; cannot go back further")


def reset_play_state(play_state: dict) -> None:
    """Clear timer and log, and return to the initial Enemy Phase state."""
    play_state["phase"] = "enemy"
    play_state["timer"] = 0
    play_state["log"] = []
    log_entry(play_state, "Play state reset (Timer 0, Enemy Phase)")
