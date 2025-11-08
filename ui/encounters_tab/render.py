import streamlit as st
from io import BytesIO

from ui.encounters_tab.logic import _list_encounters_cached, _load_valid_sets_cached, filter_expansions, filter_encounters, shuffle_encounter, apply_edited_toggle
from ui.encounters_tab.generation import editedEncounterKeywords, build_encounter_hotspots, generate_encounter_image, render_encounter_icons, build_encounter_keywords


def render_card(buf, card_img, encounter_name, expansion, use_edited):
    """Render a card with hotspots and caption"""
    html = build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited)
    st.markdown(html, unsafe_allow_html=True)


def render_original_encounter(encounter_data, selected_expansion, encounter_name,
                              encounter_level, use_edited, enemies=None):
    """Re-render the original encounter image (not shuffled)"""
    if enemies is None:
        enemies = encounter_data["original"]

    card_img = generate_encounter_image(
        selected_expansion, encounter_level, encounter_name, encounter_data, enemies, use_edited
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
        "expansions_used": [selected_expansion]
    }


def render(settings, valid_party, character_count):
    active_expansions = settings["active_expansions"]

    # --- Encounter Selection ---
    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        st.error("No encounters found.")
        st.stop()

    valid_sets = _load_valid_sets_cached()

    # Filter expansions with valid encounters
    filtered_expansions = filter_expansions(encounters_by_expansion, character_count, tuple(active_expansions), valid_sets)

    if not filtered_expansions:
        st.error("No valid expansions for the current settings.")
        st.stop()

    # Two-column layout
    col_controls, col_card = st.columns([1, 2])

    with col_controls:
        selected_expansion = st.selectbox(
            "Select Set/Expansion:",
            filtered_expansions,
            index=0,
            disabled=not valid_party
        )

        all_encounters = encounters_by_expansion[selected_expansion]

        filtered_encounters = filter_encounters(all_encounters, selected_expansion, character_count, tuple(active_expansions), valid_sets)

        if not filtered_encounters:
            st.warning("No valid encounters for the selected expansions and party size.")
            st.stop()

        display_names = [f"{e['name']} (level {e['level']})" for e in filtered_encounters]

        default_label = st.session_state.get("last_encounter", {}).get("label")
        selected_label = st.selectbox(
            "Select Encounter:",
            display_names,
            index=display_names.index(default_label) if default_label in display_names else 0,
            key="encounter_dropdown",
            disabled=not valid_party,
        )

        # Determine current encounter
        if selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            encounter_name = selected_encounter["name"]
            key = f"{encounter_name}|{selected_expansion}"  # always string
            has_edited = (encounter_name, selected_expansion) in editedEncounterKeywords
        else:
            encounter_name, key, has_edited = None, None, False

        # Ensure edited_toggles dict exists in settings
        if "edited_toggles" not in settings:
            settings["edited_toggles"] = {}

        # Get previous state (default False)
        prev_state = settings["edited_toggles"].get(key, False) if key else False

        # Reset if encounter doesn’t support edited
        if not has_edited and key:
            settings["edited_toggles"][key] = False
            prev_state = False

        use_edited = st.checkbox(
            "Use Edited Encounter",
            value=prev_state,
            key=f"edited_toggle_{encounter_name}_{selected_expansion}",
            disabled=not has_edited
        )

        # Save state back to settings (persists via save_settings in app.py)
        if key:
            settings["edited_toggles"][key] = use_edited

        toggle_changed = (
            "last_toggle" in st.session_state
            and st.session_state["last_toggle"] != use_edited
        )
        st.session_state["last_toggle"] = use_edited

        shuffle_clicked = st.button("Shuffle", use_container_width=True)
        original_clicked = st.button("Original", use_container_width=True)

        # Shuffle
        if shuffle_clicked and selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            res = shuffle_encounter(
                selected_encounter, character_count, active_expansions, selected_expansion, use_edited
            )
            if res["ok"]:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"]
                }
            else:
                st.warning(res["message"])

        # Original
        if original_clicked and selected_label and "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            encounter_slug = f"{current['expansion']}_{current['encounter_level']}_{current['encounter_name']}"
            res = render_original_encounter(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": encounter_slug,
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"]
                }

        # Toggle edited/original refresh
        toggle_changed = (prev_state != use_edited)

        if toggle_changed and "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            encounter_slug = f"{current['expansion']}_{current['encounter_level']}_{current['encounter_name']}"
            res = apply_edited_toggle(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited,
                enemies=current["enemies"],
                combo=current["expansions_used"]
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": encounter_slug,
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"]
                }

        # Auto shuffle when changing encounters (but avoid redundant work on reruns)
        if selected_label and not shuffle_clicked and not original_clicked and not toggle_changed:
            # Only auto-shuffle if we don't already have a current encounter for this selection
            last = st.session_state.get("last_encounter", {})
            if last.get("label") != selected_label or last.get("edited") != use_edited:
                selected_encounter = filtered_encounters[display_names.index(selected_label)]
                res = shuffle_encounter(
                    selected_encounter, character_count, active_expansions, selected_expansion, use_edited
                )
                if res["ok"]:
                    st.session_state.current_encounter = res
                    st.session_state["last_encounter"] = {
                        "label": selected_label,
                        "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                        "expansion": selected_expansion,
                        "character_count": character_count,
                        "edited": use_edited,
                        "enemies": res["enemies"],
                        "expansions_used": res["expansions_used"]
                    }
                else:
                    st.warning(res["message"])

        # Character and expansion icons
        if "current_encounter" in st.session_state:
            icons_html = render_encounter_icons(st.session_state.current_encounter)
            st.markdown(icons_html, unsafe_allow_html=True)

    with col_card:
        if "current_encounter" in st.session_state:
            encounter = st.session_state.current_encounter
            render_card(encounter["buf"], encounter["card_img"],
                        encounter["encounter_name"], encounter["expansion"], use_edited)
        elif "last_encounter" in st.session_state:
            st.info(f"Last encounter was {st.session_state['last_encounter']['label']}")
        else:
            st.info("Select an encounter to get started.")

    st.markdown("<br>", unsafe_allow_html=True)

    # Keywords
    if "current_encounter" in st.session_state:
        current = st.session_state.current_encounter
        keyword_items = build_encounter_keywords(
            current["encounter_name"], current["expansion"], use_edited
        )
    else:
        keyword_items = []

    if keyword_items:
        with st.expander("Special Rules Reference", expanded=False):
            for _, text in keyword_items:
                st.markdown(text)
