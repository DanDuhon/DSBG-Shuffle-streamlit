import streamlit as st

from ui.behavior_decks_tab.logic import ensure_state, init_deck, draw_card, heatup
from ui.behavior_decks_tab.generation import (
    render_behavior_card_cached,
    render_dimmed_behavior_card_cached
)

def render():
    state = ensure_state()

    st.subheader("Behavior Decks")

    bosses = ["Asylum Demon", "Ornstein & Smough", "Four Kings"]  # extend from JSON later
    boss = st.selectbox("Choose Boss", bosses)

    if state.boss != boss:
        init_deck(boss)
        st.rerun()

    cols = st.columns(2)

    with cols[0]:
        if st.button("Draw", use_container_width=True):
            draw_card()
            st.rerun()

        if st.button("Heat Up", use_container_width=True):
            heatup()
            st.rerun()

        if st.button("Reset", use_container_width=True):
            init_deck(boss)
            st.rerun()

        st.metric("Draw Pile", len(state.draw_pile))
        st.metric("Discard", len(state.discard_pile))

    with cols[1]:
        st.write("Current Card:")
        if state.current_card:
            img = render_behavior_card_cached(state.current_card)
            st.image(img, width=300)
        else:
            st.write("*None drawn yet*")
