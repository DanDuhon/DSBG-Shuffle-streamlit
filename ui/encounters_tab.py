import streamlit as st
from core.encounters import list_encounters, load_valid_sets, encounter_is_valid
from core.editedEncounterKeywords import editedEncounterKeywords
from .encounter_helpers import (
    render_card, render_original_encounter, shuffle_encounter,
    build_encounter_keywords, render_encounter_icons, apply_edited_toggle
)

# Cached wrappers to avoid repeated I/O
@st.cache_data(show_spinner=False)
def _list_encounters_cached():
    return list_encounters()

@st.cache_data(show_spinner=False)
def _load_valid_sets_cached():
    return load_valid_sets()

def render(settings, valid_party, character_count):
    active_expansions = settings["active_expansions"]

    # --- Encounter Selection ---
    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        st.error("No encounters found.")
        st.stop()

    valid_sets = _load_valid_sets_cached()

    # Filter expansions with valid encounters
    filtered_expansions = []
    for expansion_name, encounter_list in encounters_by_expansion.items():
        has_valid = any(
            encounter_is_valid(
                f"{expansion_name}_{e['level']}_{e['name']}",
                character_count,
                tuple(active_expansions),
                valid_sets
            )
            for e in encounter_list
        )
        if has_valid:
            filtered_expansions.append(expansion_name)

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

        filtered_encounters = [
            e for e in all_encounters
            if encounter_is_valid(
                f"{selected_expansion}_{e['level']}_{e['name']}",
                character_count,
                tuple(active_expansions),
                valid_sets
            )
        ]

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
