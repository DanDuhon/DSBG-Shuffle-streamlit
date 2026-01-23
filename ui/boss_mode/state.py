import streamlit as st

from core.ngplus import get_current_ngplus_level
from core.behavior.logic import (
    _draw_card,
    _load_cfg_for_state,
    _manual_heatup,
    _new_state_from_file,
)


def get_boss_mode_state_key(entry) -> str:
    return f"boss_mode::{entry.category}::{entry.name}"


def ensure_boss_state(entry):
    """Ensure Boss Mode state+cfg exist for the selected boss.

    Preserves the session keys used throughout the app:
    - Per-boss state: boss_mode::<category>::<name>
    - Current pointers: behavior_deck, behavior_cfg
    - Tracks ngplus_level in the per-boss state
    """

    key = get_boss_mode_state_key(entry)
    current_ng = int(get_current_ngplus_level() or 0)

    state = st.session_state.get(key)
    if not state:
        state, cfg = _new_state_from_file(entry.path)
        state["ngplus_level"] = current_ng

        if cfg.name == "Crossbreed Priscilla":
            state["priscilla_invisible"] = True

        st.session_state[key] = state
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
        return state, cfg

    cached_ng = int(state.get("ngplus_level", -1))
    if cached_ng != current_ng:
        state, cfg = _new_state_from_file(entry.path)
        state["ngplus_level"] = current_ng
        st.session_state[key] = state
    else:
        cfg = _load_cfg_for_state(state)

    st.session_state["behavior_deck"] = state
    st.session_state["behavior_cfg"] = cfg

    return state, cfg


def boss_draw_current() -> None:
    entry = st.session_state.get("boss_mode_choice")
    if not entry:
        return

    state, _cfg = ensure_boss_state(entry)

    st.session_state["boss_mode_draw_token"] = (
        st.session_state.get("boss_mode_draw_token", 0) + 1
    )
    _draw_card(state)


def boss_manual_heatup_current() -> None:
    entry = st.session_state.get("boss_mode_choice")
    if not entry:
        return

    state, _cfg = ensure_boss_state(entry)
    _manual_heatup(state)
