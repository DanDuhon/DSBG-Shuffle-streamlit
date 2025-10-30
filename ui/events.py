import streamlit as st
import os
import base64
import random
from core import events
from core.settings_manager import save_settings


DECK_BACK_PATH = "assets/events/deck_back.png"


def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()
    

def get_card_width(layout_width: int = 700, col_ratio: int = 2, total_ratio: int = 4, max_width: int = 300) -> int:
    """
    Estimate card width based on layout and screen size.
    
    Args:
        layout_width: Approx expander/container width (px).
        col_ratio: Column weight for the target column.
        total_ratio: Sum of weights for all columns.
        max_width: Hard cap so desktop doesn't get too huge.
    """
    col_w = int(layout_width * (col_ratio / total_ratio))
    return min(col_w - 20, max_width)


def render(settings):
    configs = events.load_event_configs()
    deck_state = settings["event_deck"]

    # ------------------------
    # Row 1: Deck, current card, discard pile
    # ------------------------
    card_width = get_card_width(layout_width=700, col_ratio=2, total_ratio=4, max_width=350)
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        presets = ["Mixed V2", "Painted World of Ariamis", "The Sunless City", "Tomb of Giants"]

        preset = st.selectbox("Choose an event deck preset", presets, key="event_preset")

        # Ensure deck state exists
        if "event_deck" not in settings:
            settings["event_deck"] = {
                "draw_pile": [],
                "discard_pile": [],
                "current_card": None,
                "preset": None
            }

        # If preset changed or deck empty, build new
        if deck_state.get("preset") != preset or (
            not deck_state["draw_pile"] and not deck_state["discard_pile"] and not deck_state["current_card"]
        ):
            if preset == "Mixed V2":
                deck = events.build_mixed_v2_deck(configs)
            else:
                deck = events.build_deck({preset: configs[preset]})
            random.shuffle(deck)
            deck_state["draw_pile"] = deck
            deck_state["discard_pile"] = []
            deck_state["current_card"] = None
            deck_state["preset"] = preset
            save_settings(settings)

    with col2:
        if deck_state["current_card"]:
            st.image(deck_state["current_card"], width=card_width)
        else:
            # Show the deck back instead of text
            st.image(DECK_BACK_PATH, width=card_width)

    with col3:
        with st.expander("Discard Pile", expanded=False):
            if deck_state["discard_pile"]:
                render_discard_pile(deck_state["discard_pile"], card_width=80)
            else:
                st.caption("Empty")

    # ------------------------
    # Row 2: Action buttons
    # ------------------------
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    # Draw card
    with col1:
        if st.button("Draw Card", use_container_width=True):
            if deck_state["draw_pile"]:
                if deck_state["current_card"]:
                    deck_state["discard_pile"].append(deck_state["current_card"])
                card = deck_state["draw_pile"].pop(0)
                deck_state["current_card"] = card
                save_settings(settings)
                st.rerun()

    # Put current card on top
    with col2:
        if st.button("Put on Top", use_container_width=True):
            if deck_state["current_card"]:
                deck_state["draw_pile"].insert(0, deck_state["current_card"])
                deck_state["current_card"] = None
                save_settings(settings)
                st.rerun()

    # Put current card on bottom
    with col3:
        if st.button("Put on Bottom", use_container_width=True):
            if deck_state["current_card"]:
                deck_state["draw_pile"].append(deck_state["current_card"])
                deck_state["current_card"] = None
                save_settings(settings)
                st.rerun()

    # Reset deck
    with col4:
        if st.button("Reset Deck", use_container_width=True):
            if preset == "Mixed V2":
                deck = events.build_mixed_v2_deck(configs)
            else:
                deck = events.build_deck({preset: configs[preset]})
            random.shuffle(deck)
            deck_state["draw_pile"] = deck
            deck_state["discard_pile"] = []
            deck_state["current_card"] = None
            deck_state["preset"] = preset
            save_settings(settings)
            st.rerun()

    # After building deck based on preset:
    if preset == "Mixed V2":
        all_cards = events.build_mixed_v2_deck(configs)
    else:
        all_cards = events.build_deck({preset: configs[preset]})
        
    st.markdown("---")  # separator line

    st.subheader("Browse All Cards in Preset")

    # Map names -> paths (remove extension for display)
    card_map = {
        os.path.splitext(os.path.basename(path))[0]: path
        for path in all_cards
    }

    card_names = sorted(card_map.keys())  # alphabetize for easier browsing

    col1, col2 = st.columns([1, 1])
    with col1:
        # Radio list of card names
        selected_name = st.radio("Select a card:", card_names, index=None)

    with col2:
        # Display selected card
        if selected_name:
            st.image(card_map[selected_name], width=card_width, caption=selected_name)
        else:
            st.image(DECK_BACK_PATH, width=card_width, caption="None selected")


def render_discard_pile(discard_pile, card_width: int = 100, offset: int = 20, max_iframe_height: int = 280):
    """
    Renders the discard pile as an overlapping stack of images with a scrollbar if too tall.
    """
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
        cards_html.append(
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="position:absolute; top:{top}px; left:0; '
            f'width:{card_width}px; height:auto; '
            f'border-radius:8px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);" '
            f'title="{os.path.splitext(os.path.basename(path))[0]}">'
        )

    stack_html = f"""
    <div style="position:relative; width:{card_width}px; height:{total_h}px;">
        {''.join(cards_html)}
    </div>
    """

    # Wrap in a scrollable container
    container_html = f"""
    <div style="max-height:{max_iframe_height}px; overflow-y:auto; padding-right:5px;">
        {stack_html}
    </div>
    """

    st.components.v1.html(container_html, height=max_iframe_height)
