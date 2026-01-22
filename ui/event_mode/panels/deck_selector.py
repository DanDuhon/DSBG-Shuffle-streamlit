from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from core.settings_manager import save_settings
from ui.event_mode.logic import DECK_STATE_KEY, _ensure_deck_state, initialize_event_deck, list_event_deck_options


def render_active_event_deck_selector(
    *,
    settings: Dict[str, Any],
    configs: Dict[str, Any],
    label: str = "Active event deck",
    key: str = "active_event_deck",
    rerun_on_change: bool = False,
) -> Optional[str]:
    """Render a shared selector for the globally active event deck.

    This is intended as the top-level selector (outside the simulator), used across modes.

    Returns the currently selected preset (or None if no options exist).
    """

    deck_state = _ensure_deck_state(settings)
    options = list_event_deck_options(configs=configs)

    current = deck_state.get("preset") or (settings.get("event_deck") or {}).get("preset")
    if current not in options:
        current = options[0] if options else None

    if not options:
        return None

    chosen = st.selectbox(
        label,
        options=options,
        index=options.index(current) if current in options else 0,
        key=key,
    )

    if chosen != current:
        initialize_event_deck(chosen, configs=configs)
        settings["event_deck"] = st.session_state[DECK_STATE_KEY]
        save_settings(settings)
        if rerun_on_change:
            st.rerun()

    return chosen
