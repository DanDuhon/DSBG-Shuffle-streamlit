# ui/campaign_mode/helpers.py
import streamlit as st
from typing import Any, Dict


def get_player_count_from_settings(settings: Dict[str, Any]) -> int:
    """
    Unified helper to determine the player count from settings or session state.
    Mirrors previous logic in `core._get_player_count_from_settings` and
    `state._get_player_count` so both can delegate here and avoid drift.
    """
    selected_chars = settings.get("selected_characters") if isinstance(settings, dict) else None
    if isinstance(selected_chars, list) and selected_chars:
        try:
            return max(1, len(selected_chars))
        except Exception:
            pass

    raw = st.session_state.get("player_count", 1)
    try:
        return max(1, int(raw))
    except Exception:
        return 1
