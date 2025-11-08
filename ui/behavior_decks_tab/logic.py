import streamlit as st
from core.behavior_decks import (
    build_draw_pile,
    recycle_deck,
    apply_heatup,
    list_behavior_files,
)
from ui.behavior_decks_tab.models import BehaviorDeckState


SESSION_KEY = "behavior_state"


def ensure_state():
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = BehaviorDeckState(boss="")
    return st.session_state[SESSION_KEY]


def init_deck(boss: str):
    state = BehaviorDeckState(boss=boss)
    state.draw_pile = build_draw_pile(boss)
    st.session_state[SESSION_KEY] = state


def draw_card():
    state = ensure_state()
    if state.current_card:
        state.discard_pile.append(state.current_card)
    if not state.draw_pile and state.discard_pile:
        state.draw_pile = recycle_deck(state.discard_pile.copy())
        state.discard_pile.clear()
    if state.draw_pile:
        state.current_card = state.draw_pile.pop(0)


def heatup():
    state = ensure_state()
    apply_heatup(state)
    state.heatup_triggered = True
