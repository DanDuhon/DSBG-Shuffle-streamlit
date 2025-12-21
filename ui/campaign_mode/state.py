#ui/campaign_mode/state.py
import streamlit as st
from typing import Any, Dict
from ui.campaign_mode.core import _default_sparks_max


def _get_settings() -> Dict[str, Any]:
    settings = st.session_state.get("user_settings")
    if settings is None:
        settings = {}
        st.session_state["user_settings"] = settings
    return settings


def _get_player_count(settings: Dict[str, Any]) -> int:
    selected_chars = settings.get("selected_characters")
    if isinstance(selected_chars, list) and selected_chars:
        return max(1, len(selected_chars))
    raw = st.session_state.get("player_count", 1)
    return max(1, int(raw))


def _ensure_campaign_event_state(state: Dict[str, Any]) -> None:
    # Consumables held by party, apply to next fight (encounter or boss)
    if not isinstance(state.get("party_consumable_events"), list):
        state["party_consumable_events"] = []

    # Instant events drawn that need table resolution
    if not isinstance(state.get("instant_events_unresolved"), list):
        state["instant_events_unresolved"] = []

    # If a rendezvous draw has nowhere to go (end of campaign), keep it visible
    if not isinstance(state.get("orphaned_rendezvous_events"), list):
        state["orphaned_rendezvous_events"] = []
    

def _ensure_v1_state(player_count: int) -> Dict[str, Any]:
    key = "campaign_v1_state"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}

    state.setdefault(
        "bosses",
        {
            "mini": "Random",  # "Random" or concrete boss name
            "main": "Random",
            "mega": "None",    # "None", "Random", or concrete boss name
        },
    )

    state.setdefault("souls", 0)

    sparks_max = _default_sparks_max(player_count)
    prev_max = state.get("sparks_max")
    prev_current = state.get("sparks")

    state["sparks_max"] = sparks_max
    if prev_current is None or prev_max is None:
        state["sparks"] = sparks_max
    else:
        state["sparks"] = min(int(prev_current), sparks_max)

    st.session_state[key] = state
    _ensure_campaign_event_state(state)
    return state


def _ensure_v2_state(player_count: int) -> Dict[str, Any]:
    """
    V2 state is structurally similar to V1 for now (sparks + souls + bosses),
    but backed by its own session key.
    """
    key = "campaign_v2_state"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}

    state.setdefault(
        "bosses",
        {
            "mini": "Random",
            "main": "Random",
            "mega": "None",
        },
    )

    state.setdefault("souls", 0)

    sparks_max = _default_sparks_max(player_count)
    prev_max = state.get("sparks_max")
    prev_current = state.get("sparks")

    state["sparks_max"] = sparks_max
    if prev_current is None or prev_max is None:
        state["sparks"] = sparks_max
    else:
        state["sparks"] = int(prev_current)

    st.session_state[key] = state
    _ensure_campaign_event_state(state)
    return state