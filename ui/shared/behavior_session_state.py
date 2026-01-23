import streamlit as st


def ensure_behavior_session_state() -> None:
    """Guarantee required Streamlit session_state keys exist for behavior decks.

    This centralizes Behavior Decks/Boss Mode state defaults in the UI layer.
    """

    defaults = {
        "behavior_deck": None,
        "behavior_state": None,
        "hp_tracker": {},
        "last_edit": {},
        "deck_reset_id": 0,
        "chariot_heatup_done": False,
        "heatup_done": False,
        "pending_heatup_prompt": False,
        "old_dragonslayer_heatups": 0,
        "old_dragonslayer_pending": False,
        "old_dragonslayer_confirmed": False,
        "vordt_attack_heatup_done": False,
        "vordt_move_heatup_done": False,
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def clear_heatup_prompt() -> None:
    """Fully clear any pending heat-up UI flags."""

    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.session_state["pending_heatup_type"] = None
