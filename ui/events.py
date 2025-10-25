import os
import random
import streamlit as st
import streamlit.components.v1 as components
from core import events
from core.settings_manager import save_settings

def render(settings):
    st.header("🃏 Event Deck")

    # Preset selection (persists in settings)
    preset = st.selectbox(
        "Select Event Deck Preset",
        ["Mixed V2", "Painted World of Ariamis", "The Sunless City", "Tomb of Giants"],
        key="event_deck_preset"
    )
    settings["event_preset"] = preset

    # Initialize deck if not present
    if "event_deck" not in settings or settings.get("event_preset") != preset:
        configs = events.load_event_configs()
        if preset == "Mixed V2":
            deck = events.build_mixed_v2_deck(configs)
        else:
            deck = events.build_deck({preset: configs[preset]})

        settings["event_deck"] = {
            "draw_pile": deck,
            "discard_pile": [],
            "current_card": None
        }
        settings["event_preset"] = preset

    deck_state = settings["event_deck"]

    # Controls
    cols = st.columns(5)
    with cols[0]:
        if st.button("▶️ Draw Next"):
            if deck_state["draw_pile"]:
                card = deck_state["draw_pile"].pop(0)
                deck_state["current_card"] = card
                deck_state["discard_pile"].append(card)
    with cols[1]:
        if st.button("🔄 Reset Deck"):
            configs = events.load_event_configs()
            if preset == "Mixed V2":
                deck = events.build_mixed_v2_deck(configs)
            else:
                deck = events.build_deck({preset: configs[preset]})

            # Shuffle the deck
            random.shuffle(deck)

            # Build fresh state
            new_state = {
                "draw_pile": deck,
                "discard_pile": [],
                "current_card": None
            }

            # Overwrite both memory + persistent state
            deck_state.update(new_state)
            settings["event_deck"] = new_state
            save_settings(settings)
    with cols[2]:
        if st.button("⬆️ Put on Top") and deck_state["current_card"]:
            deck_state["draw_pile"].insert(0, deck_state["current_card"])
            deck_state["discard_pile"].remove(deck_state["current_card"])
    with cols[3]:
        if st.button("⬇️ Put on Bottom") and deck_state["current_card"]:
            deck_state["draw_pile"].append(deck_state["current_card"])
            deck_state["discard_pile"].remove(deck_state["current_card"])
    with cols[4]:
        with st.expander("🗑️ Discard Pile"):
            pile = deck_state["discard_pile"]
            if pile:
                n = len(pile)
                offset = 20
                aspect_w, aspect_h = 498, 745
                max_iframe_height = 180  # cap pile height in px

                html = f"""
                <div id="discard-pile" style="position:relative;width:100%;--offset:{offset}px;overflow-y:auto;max-height:{max_iframe_height}px;">
                <div style="
                    width:100%;
                    aspect-ratio:{aspect_w}/{aspect_h};
                    margin-bottom:calc(var(--offset) * {max(n-1,0)});
                "></div>
                """

                for i, card in enumerate(pile):
                    b64 = events.img_to_base64(card)
                    name = os.path.splitext(os.path.basename(card))[0].replace("_", " ")
                    html += f"""
                    <img src="data:image/jpeg;base64,{b64}"
                        title="{name}"
                        style="
                        position:absolute;
                        top:calc(var(--offset) * {i});
                        left:0;
                        width:100%;
                        height:auto;
                        z-index:{100+i};
                        box-shadow:2px 2px 6px rgba(0,0,0,0.6);
                        border-radius:8px;
                        ">
                    """
                html += """
                </div>
                <script>
                function resizePile() {
                    const pile = document.getElementById("discard-pile");
                    const card = pile.querySelector("img");
                    if (card) {
                        const cardHeight = card.offsetHeight;
                        const offset = parseInt(getComputedStyle(pile).getPropertyValue("--offset"));
                        const count = pile.querySelectorAll("img").length;
                        const totalHeight = cardHeight + offset * (count - 1);
                        pile.style.height = totalHeight + "px";
                        // Cap at max height and let scrolling handle overflow
                        const cappedHeight = Math.min(totalHeight, {max_iframe_height});
                        window.parent.postMessage({isStreamlitMessage: true, type: "resize", height: cappedHeight + 20}, "*");
                    }
                }
                window.addEventListener("load", resizePile);
                window.addEventListener("resize", resizePile);
                </script>
                """

                # Starter height, JS will fix it
                components.html(html, height=200, scrolling=False)
            else:
                st.info("Discard pile is empty.")


    # Display current card
    if deck_state["current_card"]:
        st.image(deck_state["current_card"], width="stretch")
    else:
        st.info("No card drawn yet.")
