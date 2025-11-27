#ui/encounters_tab/render.py
import streamlit as st
import os
from io import BytesIO

from ui.encounters_tab.logic import (
    _list_encounters_cached,
    _load_valid_sets_cached,
    filter_expansions,
    filter_encounters,
    shuffle_encounter,
    apply_edited_toggle,
)
from ui.encounters_tab.generation import (
    editedEncounterKeywords,
    build_encounter_hotspots,
    generate_encounter_image,
    render_encounter_icons,
    build_encounter_keywords,
)
from ui.events_tab.logic import (
    load_event_configs,
    initialize_event_deck,
    draw_event_card,
    DECK_STATE_KEY,
    RENDEZVOUS_EVENTS,
)
from ui.events_tab.assets import PRESETS
from core.settings_manager import save_settings


# --- Event attachment helpers -------------------------------------------------
def _attach_event_to_current_encounter(card_path: str) -> None:
    """Attach an event card image to the current encounter, enforcing the rendezvous rule."""
    if not card_path:
        return
    
    if "saved_encounters" not in st.session_state:
        st.session_state.saved_encounters = {}

    if "encounter_events" not in st.session_state:
        st.session_state.encounter_events = []

    base = os.path.splitext(os.path.basename(str(card_path)))[0]
    is_rendezvous = base in RENDEZVOUS_EVENTS

    events = st.session_state.encounter_events

    if is_rendezvous:
        events = [ev for ev in events if not ev.get("is_rendezvous")]

    event_obj = {
        "id": base,
        "name": base,
        "path": str(card_path),
        "is_rendezvous": is_rendezvous,
    }

    events.append(event_obj)
    st.session_state.encounter_events = events


def render_event_card(event_obj):
    """Render the attached event card (or a placeholder if none)."""
    if not event_obj:
        st.caption("No event attached yet.")
        return

    title = event_obj.get("name", "Event")
    st.markdown(f"#### {title}")

    # If you store an image for the event, show it here
    image = event_obj.get("image")
    if image is not None:
        st.image(image, width="stretch")

    # Fallback / extra rules text
    text = event_obj.get("text")
    if text:
        st.markdown(text)


# --- Encounter helpers --------------------------------------------------------
def render_card(buf, card_img, encounter_name, expansion, use_edited):
    """Render a card with hotspots and caption."""
    html = build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited)
    st.markdown(html, unsafe_allow_html=True)


def render_original_encounter(
    encounter_data,
    selected_expansion,
    encounter_name,
    encounter_level,
    use_edited,
    enemies=None,
):
    """Re-render the original encounter image (not shuffled)."""
    if enemies is None:
        enemies = encounter_data["original"]

    card_img = generate_encounter_image(
        selected_expansion,
        encounter_level,
        encounter_name,
        encounter_data,
        enemies,
        use_edited,
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    return {
        "ok": True,
        "buf": buf,
        "card_img": card_img,
        "encounter_data": encounter_data,
        "encounter_name": encounter_name,
        "encounter_level": encounter_level,
        "expansion": selected_expansion,
        "enemies": enemies,
        "expansions_used": [selected_expansion],
    }


# --- Main render --------------------------------------------------------------


def render(settings: dict, valid_party: bool, character_count: int) -> None:
    """
    Main Encounter tab UI.

    - Left column: encounter setup, event attachment, save/load curated encounters.
    - Right column: encounter card + attached event card.
    """
    active_expansions = settings.get("active_expansions", [])

    # --- Encounter Selection Data ---
    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        st.error("No encounters found.")
        st.stop()

    valid_sets = _load_valid_sets_cached()

    # Filter expansions with valid encounters
    filtered_expansions = filter_expansions(
        encounters_by_expansion,
        character_count,
        tuple(active_expansions),
        valid_sets,
    )

    if not filtered_expansions:
        st.error("No valid expansions for the current settings.")
        st.stop()

    # Ensure some state containers exist
    if "saved_encounters" not in st.session_state:
        st.session_state.saved_encounters = {}  # name -> encounter dict

    if "encounter_events" not in st.session_state:
        st.session_state.encounter_events = []

    # --- Two-column layout: controls | cards ---
    col_controls, col_cards = st.columns([1, 2])

    # -------------------------------------------------------------------------
    # LEFT COLUMN – SETUP / EVENT / SAVE
    # -------------------------------------------------------------------------
    with col_controls:
        st.subheader("Encounter Setup")

        # Expansion selection
        selected_expansion = st.selectbox(
            "Set / Expansion",
            filtered_expansions,
            index=0,
            disabled=not valid_party,
        )

        all_encounters = encounters_by_expansion[selected_expansion]

        filtered_encounters = filter_encounters(
            all_encounters,
            selected_expansion,
            character_count,
            tuple(active_expansions),
            valid_sets,
        )

        if not filtered_encounters:
            st.warning("No valid encounters for the selected expansions and party size.")
            st.stop()

        display_names = [
            f"{e['name']} (level {e['level']})" for e in filtered_encounters
        ]

        default_label = st.session_state.get("last_encounter", {}).get("label")
        try:
            default_index = display_names.index(default_label) if default_label else 0
        except ValueError:
            default_index = 0

        selected_label = st.selectbox(
            "Encounter",
            display_names,
            index=default_index,
            key="encounter_dropdown",
            disabled=not valid_party,
        )

        # Current encounter metadata
        if selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            encounter_name = selected_encounter["name"]
            key = f"{encounter_name}|{selected_expansion}"
            has_edited = (encounter_name, selected_expansion) in editedEncounterKeywords
        else:
            encounter_name = None
            key = None
            has_edited = False

        # Ensure edited_toggles exists
        if "edited_toggles" not in settings:
            settings["edited_toggles"] = {}

        prev_state = settings["edited_toggles"].get(key, False) if key else False

        # If this encounter has no edited variant, force toggle off
        if not has_edited and key:
            settings["edited_toggles"][key] = False
            prev_state = False

        use_edited = st.checkbox(
            "Use Edited Encounter",
            value=prev_state,
            key=f"edited_toggle_{encounter_name}_{selected_expansion}",
            disabled=not has_edited,
        )

        if key:
            settings["edited_toggles"][key] = use_edited

        toggle_changed = prev_state != use_edited
        st.session_state["last_toggle"] = use_edited

        # --- Shuffle / Original buttons ---
        shuffle_clicked = st.button("Shuffle", width="stretch")
        original_clicked = st.button("Original", width="stretch")

        # Shuffle
        if shuffle_clicked and selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            res = shuffle_encounter(
                selected_encounter,
                character_count,
                active_expansions,
                selected_expansion,
                use_edited,
            )
            if res.get("ok"):
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"],
                }
            else:
                st.warning(res.get("message", "Unable to shuffle encounter."))

        # Original
        if original_clicked and selected_label and "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            res = render_original_encounter(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited,
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{res['expansion']}_{res['encounter_level']}_{res['encounter_name']}",
                    "expansion": res["expansion"],
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"],
                }

        # Apply edited/original toggle when we already have a current encounter
        if toggle_changed and "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            res = apply_edited_toggle(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited,
                enemies=current["enemies"],
                combo=current["expansions_used"],
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{res['expansion']}_{res['encounter_level']}_{res['encounter_name']}",
                    "expansion": res["expansion"],
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"],
                }

        # Auto-shuffle when encounter selection changes (and no explicit button pressed)
        if (
            selected_label
            and not shuffle_clicked
            and not original_clicked
            and not toggle_changed
        ):
            last = st.session_state.get("last_encounter", {})
            encounter_changed = (
                last.get("label") != selected_label
                or last.get("edited") != use_edited
            )

            if encounter_changed:
                selected_encounter = filtered_encounters[display_names.index(selected_label)]
                res = shuffle_encounter(
                    selected_encounter,
                    character_count,
                    active_expansions,
                    selected_expansion,
                    use_edited,
                )
                if res.get("ok"):
                    st.session_state.current_encounter = res
                    st.session_state["last_encounter"] = {
                        "label": selected_label,
                        "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                        "expansion": selected_expansion,
                        "character_count": character_count,
                        "edited": use_edited,
                        "enemies": res["enemies"],
                        "expansions_used": res["expansions_used"],
                    }
                    # Only clear events when we actually switched encounters
                    st.session_state.encounter_events = []
                else:
                    st.warning(res.get("message", "Unable to build encounter."))

        # Character / expansion icons
        if "current_encounter" in st.session_state:
            icons_html = render_encounter_icons(st.session_state.current_encounter)
            st.markdown(
                f'<div class="encounter-icons-wrapper">{icons_html}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ---------------------------------------------------------
        # Event attachment
        # ---------------------------------------------------------
        st.subheader("Event Management")

        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            if st.button("Attach Random Event", width="stretch"):
                # Ensure event deck exists and has a preset
                if DECK_STATE_KEY not in st.session_state:
                    st.session_state[DECK_STATE_KEY] = {
                        "draw_pile": [],
                        "discard_pile": [],
                        "current_card": None,
                        "preset": None,
                    }

                deck_state = st.session_state[DECK_STATE_KEY]
                configs = load_event_configs()

                preset = (
                    deck_state.get("preset")
                    or settings.get("event_deck", {}).get("preset")
                    or PRESETS[0]
                )

                # Initialize if empty or preset changed
                if deck_state.get("preset") != preset or not deck_state["draw_pile"]:
                    initialize_event_deck(preset, configs=configs)

                # Draw and attach
                draw_event_card()
                save_settings(settings)  # persist deck state if you like
                deck_state = st.session_state[DECK_STATE_KEY]
                card_path = deck_state.get("current_card")
                if card_path:
                    _attach_event_to_current_encounter(card_path)

        with col_ev2:
            if st.button("Clear Events", width="stretch"):
                st.session_state.encounter_events = []

        # Small summary line
        events = st.session_state.encounter_events
        if events:
            rendezvous_count = sum(1 for ev in events if ev.get("is_rendezvous"))
            st.caption(
                f"{len(events)} event(s) attached "
                f"({rendezvous_count} rendezvous)."
            )
        else:
            st.caption("No events attached yet.")

        st.markdown("---")

        # ---------------------------------------------------------
        # Save / Load curated encounters
        # ---------------------------------------------------------
        st.subheader("Saved Encounters")

        save_name_default = (
            st.session_state.get("last_encounter", {}).get("slug") or "custom_encounter"
        )
        save_name = st.text_input("Save as:", value=save_name_default)

        if st.button("Save Current", width="stretch"):
            if "current_encounter" not in st.session_state:
                st.warning("No active encounter to save.")
            else:
                payload = {
                    **st.session_state.current_encounter,
                    "events": st.session_state.get("encounter_events", []),
                    "meta_label": st.session_state.get("last_encounter", {}).get("label"),
                    "character_count": character_count,
                    "edited": use_edited,
                }
                st.session_state.saved_encounters[save_name] = payload
                st.success(f"Saved encounter as '{save_name}'.")

        if st.session_state.saved_encounters:
            load_name = st.selectbox(
                "Load saved encounter:",
                list(st.session_state.saved_encounters.keys()),
            )
            if st.button("Load", width="stretch"):
                payload = st.session_state.saved_encounters[load_name]
                st.session_state.current_encounter = payload
                st.session_state.encounter_events = payload.get("events", [])
                st.session_state["last_encounter"] = {
                    "label": payload.get("meta_label", load_name),
                    "slug": payload.get("slug"),
                    "expansion": payload.get("expansion"),
                    "character_count": payload.get("character_count"),
                    "edited": payload.get("edited", False),
                    "enemies": payload.get("enemies"),
                    "expansions_used": payload.get("expansions_used"),
                }

    # -------------------------------------------------------------------------
    # RIGHT COLUMN – CARDS
    # -------------------------------------------------------------------------
    with col_cards:
        if "current_encounter" in st.session_state:
            # Two-card layout: Encounter | Event
            c1, c2 = st.columns(2)

            with c1:
                st.markdown("#### Encounter")
                encounter = st.session_state.current_encounter
                render_card(
                    encounter["buf"],
                    encounter["card_img"],
                    encounter["encounter_name"],
                    encounter["expansion"],
                    use_edited,
                )

                # Divider between card and rules
                st.markdown(
                    "<hr style='margin: 0.5rem 0 0.75rem 0; border-color: #333;' />",
                    unsafe_allow_html=True,
                )

                # -------------------------------------------------------------------------
                # Keywords below the encounter card
                # -------------------------------------------------------------------------
                if "current_encounter" in st.session_state:
                    current = st.session_state.current_encounter
                    keyword_items = build_encounter_keywords(
                        current["encounter_name"],
                        current["expansion"],
                        use_edited,
                    )
                else:
                    keyword_items = []

                if keyword_items:
                    with st.expander("Special Rules Reference", expanded=False):
                        for _, text in keyword_items:
                            st.markdown(text)

            with c2:
                st.markdown("#### Events")

                events = st.session_state.get("encounter_events", [])
                if not events:
                    st.caption("No events attached.")
                else:
                    ncols = 2
                    for row_start in range(0, len(events), ncols):
                        row_events = events[row_start:row_start + ncols]
                        cols = st.columns(ncols)  # always 2 columns

                        for i, ev in enumerate(row_events):
                            with cols[i]:
                                st.image(ev["path"], width="stretch")

        elif "last_encounter" in st.session_state:
            st.info(f"Last encounter was {st.session_state['last_encounter']['label']}")
        else:
            st.info("Select an encounter to get started.")
