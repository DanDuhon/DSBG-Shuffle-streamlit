from __future__ import annotations
from datetime import datetime
import streamlit as st


def get_encounter_id(encounter: dict):
    """Best-effort way to identify the current encounter for resetting state.

    Falls back to a name qualified by expansion and level, because the bare name
    is not unique: "Broken Passageway" exists in both Dark Souls The Board Game
    and The Sunless City, and "Central Plaza" in both Painted World of Ariamis
    and The Sunless City. Sharing an id meant switching between such a pair did
    not reset the timer/phase/log, and made them share widget and invader-deck
    keys. Campaign Mode supplies an explicit slug and is unaffected.
    """
    for key in ("id", "slug", "encounter_slug"):
        value = encounter.get(key)
        if value:
            return value

    name = encounter.get("encounter_name") or encounter.get("name")
    if not name:
        return None

    expansion = encounter.get("expansion")
    level = encounter.get("encounter_level", encounter.get("level"))
    parts = [str(p) for p in (expansion, level, name) if p not in (None, "")]
    return "|".join(parts)


def get_player_count() -> int:
    """Return the current player count from session_state, clamped to at least 1."""
    pc = int(st.session_state.get("player_count", 1))
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
            # Monotonic counter that increments each time we ENTER Enemy Phase
            # via normal forward play or reset. Used for one-shot triggers.
            "enemy_phase_entry": 1,
            "log": [],
            # Internal flag: freshly initialized state for this encounter.
            "_fresh": True,
        }
        st.session_state["encounter_play"] = state
        # Clear any transient trigger messages when switching encounters.
        st.session_state["encounter_last_trigger_messages"] = []

    # Back-compat: older sessions may not have the entry counter.
    state.setdefault("enemy_phase_entry", 1)

    return state


def apply_pending_action(
    play_state: dict,
    timer_behavior: dict,
    *,
    trigger_scope_key: str | None = None,
):
    """
    If the last run scheduled a pending turn action (next, prev, reset),
    apply it *before* rendering anything, and return the action string.

    `trigger_scope_key` is the encounter's trigger scope; a reset clears it so
    checkboxes/counters return to their defaults along with the timer.

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
        # Clear this encounter's triggers first: a trigger left checked would
        # otherwise be folded straight back into the timer by the
        # recompute-from-triggers pass, undoing the reset.
        if trigger_scope_key:
            scopes = st.session_state.get("encounter_triggers")
            if isinstance(scopes, dict):
                scopes.pop(trigger_scope_key, None)

        init = timer_behavior.get("initial_timer")
        reset_play_state(
            play_state,
            initial_timer=init if isinstance(init, int) else 0,
        )

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
    # Clear transient trigger messages when the turn advances.
    st.session_state["encounter_last_trigger_messages"] = []

    if play_state["phase"] == "enemy":
        play_state["phase"] = "player"
        log_entry(play_state, "Advanced to Player Phase")
    else:  # player -> enemy
        if not disable_auto_timer:
            play_state["timer"] += 1
            play_state["phase"] = "enemy"
            play_state["enemy_phase_entry"] = int(play_state.get("enemy_phase_entry", 0) or 0) + 1
            log_entry(play_state, "Advanced to Enemy Phase; timer increased")
        else:
            play_state["phase"] = "enemy"
            play_state["enemy_phase_entry"] = int(play_state.get("enemy_phase_entry", 0) or 0) + 1
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
    # Clear transient trigger messages when moving turns backward.
    st.session_state["encounter_last_trigger_messages"] = []

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


def reset_play_state(play_state: dict, *, initial_timer: int = 0) -> None:
    """Clear log and return to this encounter's starting Enemy Phase state.

    `initial_timer` mirrors the value applied when the state was first created
    (e.g. Maze of the Dead edited starts at Timer 3). Resetting to a hard 0
    ignored that, so such encounters could not actually be reset.
    """
    start = initial_timer if isinstance(initial_timer, int) and initial_timer >= 0 else 0
    play_state["phase"] = "enemy"
    play_state["timer"] = start
    play_state["log"] = []
    play_state["enemy_phase_entry"] = int(play_state.get("enemy_phase_entry", 0) or 0) + 1
    # Clear transient trigger messages when resetting.
    st.session_state["encounter_last_trigger_messages"] = []
    log_entry(play_state, f"Play state reset (Timer {start}, Enemy Phase)")
