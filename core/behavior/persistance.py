#ui/behavior_decks_tab/persistence.py
import streamlit as st
from typing import Dict, Any

from core.settings_manager import save_settings


def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "selected_file": state.get("selected_file"),
        "draw_pile": state.get("draw_pile", []),
        "discard_pile": state.get("discard_pile", []),
        "current_card": state.get("current_card"),
        "display_cards": state.get("display_cards", []),
        "entities": state.get("entities", [])
    }


def _save_slot_ui(settings, state):
    with st.expander("💾 Save / Load Deck State", expanded=False):
        # keep max 5 slots
        saves = settings.setdefault("behavior_deck_saves", [])
        # render existing
        for i in range(5):
            cols = st.columns([3, 1, 1])
            title = (saves[i]["title"] if i < len(saves) else f"Slot {i+1}")
            with cols[0]:
                new_title = st.text_input(f"Name (Slot {i+1})", value=title, key=f"slot_title_{i}")
            with cols[1]:
                if st.button("Save", key=f"slot_save_{i}", width="stretch"):
                    payload = serialize_state(state) if state else {}
                    entry = {"title": new_title, "state": payload}
                    if i < len(saves):
                        saves[i] = entry
                    else:
                        saves.append(entry)
                    saves[:] = saves[:5]
                    save_settings(settings)
                    st.success(f"Saved to Slot {i+1}")
            with cols[2]:
                if st.button("Load", key=f"slot_load_{i}", width="stretch"):
                    if i < len(saves) and saves[i].get("state"):
                        st.session_state["behavior_deck"] = saves[i]["state"]
                        st.success(f"Loaded Slot {i+1}")
                        st.rerun()
        # cleanup extra slots if any
        if len(saves) > 5:
            saves[:] = saves[:5]
            save_settings(settings)