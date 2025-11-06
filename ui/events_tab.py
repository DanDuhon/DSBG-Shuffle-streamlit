import os
import streamlit as st
from core import events
from core.settings_manager import save_settings

DECK_BACK_PATH = "assets/events/deck_back.png"

PRESETS = ["Mixed V2", "Painted World of Ariamis", "Tomb of Giants", "The Sunless City"]


def get_card_width(layout_width: int = 700, col_ratio: int = 2, total_ratio: int = 4, max_width: int = 350) -> int:
    """
    Estimate card width based on layout and screen size.
    """
    col_w = int(layout_width * (col_ratio / total_ratio))
    return min(col_w - 20, max_width)


def render(settings):
    # Load cached configs once
    configs = events.load_event_configs()

    # Ensure deck state exists
    if "event_deck" not in st.session_state:
        st.session_state["event_deck"] = {
            "draw_pile": [],
            "discard_pile": [],
            "current_card": None,
            "preset": None
        }

    deck_state = st.session_state["event_deck"]

    # ------------------------
    # Controls / preset selection
    # ------------------------
    col_controls, col_board = st.columns([1, 2], gap="large")

    with col_controls:
        preset = st.selectbox("Choose an event deck preset", PRESETS, index=PRESETS.index(deck_state.get("preset")) if deck_state.get("preset") in PRESETS else 0, key="event_preset")

        # Initialize deck when preset changes or deck hasn't been initialized yet
        if deck_state.get("preset") != preset or (not deck_state["draw_pile"] and not deck_state["discard_pile"] and not deck_state["current_card"]):
            events.initialize_event_deck(preset, configs=configs)
            # Persist preset to settings for cross-run persistence if you choose to save settings externally
            settings["event_deck"] = deck_state
            save_settings(settings)

        st.markdown("### Deck Controls")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Draw", use_container_width=True):
                events.draw_event_card()
                save_settings(settings)
                st.rerun()
        with c2:
            if st.button("Reset Deck", use_container_width=True):
                events.initialize_event_deck(preset, configs=configs)
                save_settings(settings)
                st.rerun()

        c3, c4 = st.columns(2)
        with c3:
            if st.button("Put on Top", use_container_width=True):
                events.put_current_on_top()
                save_settings(settings)
                st.rerun()
        with c4:
            if st.button("Put on Bottom", use_container_width=True):
                events.put_current_on_bottom()
                save_settings(settings)
                st.rerun()

        # Deck stats
        st.markdown("### Deck Status")
        draw_ct = len(deck_state["draw_pile"])
        discard_ct = len(deck_state["discard_pile"])
        st.metric("Draw Pile", draw_ct)
        st.metric("Discard Pile", discard_ct)

    # ------------------------
    # Current card + discard pile
    # ------------------------
    with col_board:
        card_width = get_card_width(layout_width=900, col_ratio=2, total_ratio=3, max_width=420)
        col_current, col_discard = st.columns([2, 1])

        with col_current:
            st.subheader("Current Card")
            if deck_state["current_card"]:
                st.image(deck_state["current_card"], width=card_width)
            else:
                st.image(DECK_BACK_PATH, width=card_width)

        with col_discard:
            st.subheader("Discard Pile")
            render_discard_pile(deck_state["discard_pile"], card_width=110)

    # ------------------------
    # Browse all cards in preset
    # ------------------------
    st.markdown("---")
    st.subheader("Browse All Cards in Preset")

    all_cards = events.build_deck_for_preset(deck_state["preset"] or preset, configs)
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


def render_discard_pile(discard_pile, card_width: int = 100, offset: int = 22, max_iframe_height: int = 300):
    """
    Renders the discard pile as an overlapping stack of images with a scrollbar if too tall.
    Uses cached base64 from core.events.img_to_base64.
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
        b64 = events.img_to_base64(path)
        title = os.path.splitext(os.path.basename(path))[0]
        cards_html.append(
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="position:absolute; top:{top}px; left:0; '
            f'width:{card_width}px; height:auto; '
            f'border-radius:8px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);" '
            f'title="{title}">'
        )

    stack_html = f"""
    <div style="position:relative; width:{card_width}px; height:{total_h}px;">
        {''.join(cards_html)}
    </div>
    """

    container_html = f"""
    <div style="max-height:{max_iframe_height}px; overflow-y:auto; padding-right:5px;">
        {stack_html}
    </div>
    """

    st.components.v1.html(container_html, height=max_iframe_height)
