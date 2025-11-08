import os
import streamlit as st
from ui.events_tab.logic import (
    load_event_configs,
    initialize_event_deck,
    draw_event_card,
    get_card_width,
    put_current_on_bottom,
    put_current_on_top,
    build_deck_for_preset,
    DECK_STATE_KEY
)
from ui.events_tab.assets import DECK_BACK_PATH, PRESETS, img_to_base64
from core.settings_manager import save_settings


def render(settings):
    """Main UI renderer for the Events tab."""
    configs = load_event_configs()

    if "event_deck" not in st.session_state:
        st.session_state["event_deck"] = {
            "draw_pile": [],
            "discard_pile": [],
            "current_card": None,
            "preset": None,
        }

    deck_state = st.session_state["event_deck"]

    col_controls, col_board = st.columns([1, 2], gap="large")

    # --- Controls ---
    with col_controls:
        preset = st.selectbox(
            "Choose an event deck preset",
            PRESETS,
            index=PRESETS.index(deck_state.get("preset"))
            if deck_state.get("preset") in PRESETS else 0,
            key="event_preset_select"
        )

        # Initialize deck if new preset or empty deck
        if deck_state.get("preset") != preset or not deck_state["draw_pile"]:
            initialize_event_deck(preset, configs=configs)
            settings["event_deck"] = deck_state
            save_settings(settings)
            st.rerun()

        with st.form("event_deck_buttons_form"):
            draw = st.form_submit_button("Draw", width="stretch")
            if draw:
                draw_event_card()
                save_settings(settings)
                st.rerun()

            c3, c4 = st.columns(2)
            with c3:
                top = st.form_submit_button("Put on Top", width="stretch")
                if top:
                    put_current_on_top()
                    save_settings(settings)
                    st.rerun()
            with c4:
                bottom = st.form_submit_button("Put on Bottom", width="stretch")
                if bottom:
                    put_current_on_bottom()
                    save_settings(settings)
                    st.rerun()
                    
            reset = st.form_submit_button("Reset Deck", width="stretch")
            if reset:
                initialize_event_deck(preset, configs=configs)
                save_settings(settings)
                st.rerun()

        st.metric("Draw Pile", len(deck_state["draw_pile"]))
        st.metric("Discard Pile", len(deck_state["discard_pile"]))

    # --- Board / Cards ---
    with col_board:
        card_width = get_card_width(layout_width=900, col_ratio=2, total_ratio=3, max_width=420)
        col_current, col_discard = st.columns([2, 1])

        with col_current:
            st.subheader("Current Card")
            card = deck_state["current_card"] or str(DECK_BACK_PATH)
            st.image(card, width=card_width)

        with col_discard:
            st.subheader("Discard Pile")
            render_discard_pile(deck_state["discard_pile"], card_width=110)

    # --- Card Browser ---
    render_card_browser(preset, configs)


def render_discard_pile(discard_pile, card_width=100, offset=22, max_iframe_height=300):
    """Display discard pile stack in HTML for layered visualization."""
    if not discard_pile:
        st.caption("Empty")
        return

    aspect_w, aspect_h = 498, 745
    card_h = int(card_width * (aspect_h / aspect_w))
    total_h = card_h + offset * (len(discard_pile) - 1)

    cards_html = []
    for i, path in enumerate(discard_pile):
        top = i * offset
        b64 = img_to_base64(path)
        title = os.path.splitext(os.path.basename(path))[0]
        cards_html.append(
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="position:absolute; top:{top}px; left:0; '
            f'width:{card_width}px; border-radius:8px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);" '
            f'title="{title}">'
        )

    stack_html = f"<div style='position:relative; width:{card_width}px; height:{total_h}px;'>{''.join(cards_html)}</div>"
    container_html = f"<div style='max-height:{max_iframe_height}px; overflow-y:auto; padding-right:5px;'>{stack_html}</div>"
    st.components.v1.html(container_html, height=max_iframe_height)


def render_card_browser(preset, configs):
    st.markdown("---")
    st.subheader("Browse All Cards in Preset")

    all_cards = build_deck_for_preset(st.session_state[DECK_STATE_KEY]["preset"] or preset, configs)
    # Unique names only for browsing
    card_map = {}
    for path in all_cards:
        name = os.path.splitext(os.path.basename(path))[0]
        card_map[name] = path  # last one wins, fine for browsing

    names = sorted(card_map.keys())
    col_a, col_b = st.columns([1, 2])
    with col_a:
        selected_name = st.radio("Select a card:", names, index=None)
    with col_b:
        if selected_name:
            st.image(card_map[selected_name], width=get_card_width(layout_width=900, col_ratio=2, total_ratio=3, max_width=420), caption=selected_name)
        else:
            st.image(DECK_BACK_PATH, width=get_card_width(layout_width=900, col_ratio=2, total_ratio=3, max_width=420), caption="None selected")
