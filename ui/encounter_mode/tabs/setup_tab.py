#ui/encounter_mode/setup_tab.py
import streamlit as st
from pathlib import Path
from io import BytesIO

from core import auth
from core.settings_manager import _has_supabase_config, is_streamlit_cloud, save_settings
from ui.encounter_mode.persistence import load_saved_encounters, save_saved_encounters
from core.behavior.generation import build_behavior_catalog
from core.behavior.models import BehaviorEntry
from ui.encounter_mode.generation import (
    editedEncounterKeywords,
    generate_encounter_image,
    render_encounter_icons,
    build_encounter_keywords,
    load_encounter_data,
)
from ui.encounter_mode.panels.invader_panel import (
    _get_invader_behavior_entries_for_encounter,
)
from ui.encounter_mode.logic import (
    _list_encounters_cached,
    _load_valid_sets_cached,
    filter_expansions,
    filter_encounters,
    shuffle_encounter,
    analyze_encounter_availability,
    apply_edited_toggle,
)
from ui.event_mode.logic import (
    load_event_configs,
    ensure_event_deck_ready,
    draw_event_card,
    DECK_STATE_KEY,
    _attach_event_to_current_encounter,
)
from ui.event_mode.panels.deck_selector import render_active_event_deck_selector
from core.image_cache import get_image_bytes_cached


# --- Event attachment helpers -------------------------------------------------
# Event attachment helper is provided by `ui.event_mode.logic`.


def _event_img_path(ev: dict) -> str | None:
    return (
        ev.get("path")
        or ev.get("card_path")
        or ev.get("image_path")
        or ev.get("img_path")
    )


def _ensure_card_bytes_inplace(encounter: dict) -> bytes | None:
    """Ensure encounter["card_bytes"] is present for display.

    This avoids re-encoding the same PIL image to PNG on every Streamlit rerun.
    """
    try:
        existing = encounter.get("card_bytes")
        if isinstance(existing, (bytes, bytearray)) and existing:
            return bytes(existing)
    except Exception:
        pass

    img = encounter.get("card_img")
    if img is None:
        return None

    try:
        buf = BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        encounter["card_bytes"] = data
        return data
    except Exception:
        return None


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
    card_bytes = buf.getvalue()

    return {
        "ok": True,
        "card_img": card_img,
        "card_bytes": card_bytes,
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

    # Require at least one selected character
    if not settings.get("selected_characters") or len(settings.get("selected_characters", [])) == 0:
        st.error("No characters selected. Please pick at least one character in the sidebar.")
        st.stop()

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

    # Migration: if saved encounters exist in user settings, move them to file
    try:
        persisted_in_settings = settings.pop("saved_encounters", None)
        if isinstance(persisted_in_settings, dict):
            # write to new file and update settings on disk
            save_saved_encounters(persisted_in_settings)
            save_settings(settings)
    except Exception:
        pass

    # Load persisted saved encounters from dedicated file if session empty
    if not st.session_state.get("saved_encounters"):
        try:
            file_encs = load_saved_encounters()
            if isinstance(file_encs, dict):
                st.session_state.saved_encounters = dict(file_encs)
        except Exception:
            pass
    if "encounter_events" not in st.session_state:
        st.session_state.encounter_events = []

    if not st.session_state.get("ui_compact", False):
        # --- Two-column layout: controls | cards ---
        col_controls, col_enc, col_event = st.columns([0.5, 0.575, 1])

        # -------------------------------------------------------------------------
        # LEFT COLUMN – SETUP / SAVE
        # -------------------------------------------------------------------------
        with col_controls.container():
            st.markdown("#### Encounter Setup")

            # Expansion selection
            selected_expansion = st.selectbox(
                "Set / Expansion",
                filtered_expansions,
                index=0,
                disabled=not valid_party,
            )

            # Defensive fallback: `st.selectbox` can return None in some
            # situations (widget state mismatch). Prefer the first available
            # expansion rather than raising a KeyError later.
            if not selected_expansion:
                if filtered_expansions:
                    selected_expansion = filtered_expansions[0]
                else:
                    st.error(
                        "No valid expansions available.\n"
                        f"Active expansions: {active_expansions}\n"
                        f"Selected characters: {settings.get('selected_characters', [])}\n"
                        f"Encounter sets loaded: {len(encounters_by_expansion)}"
                    )
                    st.stop()

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

            # --- Level filter radio buttons (only show levels that exist) ---
            level_values = sorted({e["level"] for e in filtered_encounters})

            level_filter = "All"
            if len(level_values) > 1:
                level_options = ["All"] + [str(lv) for lv in level_values]
                prev_level = st.session_state.get("encounter_level_filter", "All")
                if prev_level not in level_options:
                    prev_level = "All"

                level_filter = st.radio(
                    "Encounter level",
                    level_options,
                    index=level_options.index(prev_level),
                    horizontal=True,
                    key="encounter_level_filter",
                )
            elif len(level_values) == 1:
                # Only a single level available – implicitly filter to it
                level_filter = str(level_values[0])

            if level_filter != "All":
                level_int = int(level_filter)
                filtered_encounters = [
                    e for e in filtered_encounters if e["level"] == level_int
                ]

            if not filtered_encounters:
                st.warning("No encounters at this level for the current filters.")
                st.stop()

            display_names = [
                f"{e['name']} (level {e['level']})" for e in filtered_encounters
            ]

            default_label = st.session_state.get("last_encounter", {}).get("label")
            default_index = 0
            if default_label:
                if default_label in display_names:
                    default_index = display_names.index(default_label)
                else:
                    base = default_label.split(" (level")[0]
                    default_index = next(
                        (i for i, d in enumerate(display_names) if d.startswith(base)),
                        0,
                    )

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

            # If this encounter has no edited variant, do not persist a toggle
            # entry at all (and clean up any stale persisted entry).
            if not has_edited and key:
                if key in settings["edited_toggles"]:
                    del settings["edited_toggles"][key]
                    st.session_state["user_settings"] = settings
                    save_settings(settings)
                prev_state = False

            widget_key = f"edited_toggle_{encounter_name}_{selected_expansion}"

            def _on_edited_changed():
                new_val = bool(st.session_state.get(widget_key, False))
                settings.setdefault("edited_toggles", {})
                if has_edited and key:
                    settings["edited_toggles"][key] = new_val
                st.session_state["user_settings"] = settings
                save_settings(settings)

            use_edited = st.checkbox(
                "Use lenlendan's edits",
                value=prev_state,
                key=widget_key,
                disabled=not has_edited,
                on_change=_on_edited_changed,
            )

            if key and has_edited:
                settings["edited_toggles"][key] = use_edited
                # Persist the change immediately so other UI (sidebar) sees it
                st.session_state["user_settings"] = settings
                save_settings(settings)

            toggle_changed = prev_state != use_edited
            st.session_state["last_toggle"] = use_edited

            # Determine availability for shuffle/original buttons
            availability = analyze_encounter_availability(
                selected_encounter,
                character_count,
                tuple(active_expansions),
                settings=settings,
            ) if selected_label else {"num_viable_alternatives": 0, "original_viable": False}
            shuffle_disabled = availability.get("num_viable_alternatives", 0) <= 1
            original_disabled = not availability.get("original_viable", False)

            # --- Shuffle / Original buttons ---
            col_shuffle, col_original = st.columns(2)
            with col_shuffle:
                shuffle_clicked = st.button("Shuffle 🔀", width="stretch", disabled=shuffle_disabled)
                if shuffle_disabled:
                    st.warning("No other enemy alternatives available for this encounter.")
            with col_original:
                original_clicked = st.button("Original 🔁", width="stretch", disabled=original_disabled)
                if original_disabled:
                    st.warning("Original enemy list is not available (disabled or unmapped enemies).")

            # Shuffle
            if shuffle_clicked and selected_label:
                selected_encounter = filtered_encounters[display_names.index(selected_label)]

                # Try shuffling until we get a different enemy set than the
                # currently-displayed/last one. Cap attempts to avoid infinite loops.
                prev_enemies = (
                    st.session_state.get("current_encounter", {}).get("enemies")
                    or st.session_state.get("last_encounter", {}).get("enemies")
                )
                max_attempts = 20
                attempt = 0
                final_res = None
                while attempt < max_attempts:
                    res = shuffle_encounter(
                        selected_encounter,
                        character_count,
                        active_expansions,
                        selected_expansion,
                        use_edited,
                    )
                    if not res.get("ok"):
                        final_res = res
                        break
                    # If there is no previous enemies to compare to, accept first result
                    if not prev_enemies:
                        final_res = res
                        break
                    # Accept when enemies differ from previous
                    if res.get("enemies") != prev_enemies:
                        final_res = res
                        break
                    attempt += 1

                if final_res and final_res.get("ok"):
                    st.session_state.current_encounter = final_res
                    # Reset Play tab state so the Play UI starts fresh for this new encounter
                    st.session_state["encounter_play"] = None
                    st.session_state["last_encounter"] = {
                        "label": selected_label,
                        "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                        "expansion": selected_expansion,
                        "character_count": character_count,
                        "edited": use_edited,
                        "enemies": final_res["enemies"],
                        "expansions_used": final_res["expansions_used"],
                    }
                    _apply_added_invaders_to_current_encounter()
                    if attempt and attempt >= max_attempts:
                        st.warning("Shuffle produced the same enemy list repeatedly; showing last result.")
                else:
                    st.warning((final_res or {}).get("message", "Unable to shuffle encounter."))

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
                    # Mark this encounter as an Original render so Play uses the Hollow gang
                    res["force_gang"] = "Hollow"
                    st.session_state.current_encounter = res
                    # Reset Play tab state so the Play UI starts fresh for this original render
                    st.session_state["encounter_play"] = None
                    st.session_state["last_encounter"] = {
                        "label": selected_label,
                        "slug": f"{res['expansion']}_{res['encounter_level']}_{res['encounter_name']}",
                        "expansion": res["expansion"],
                        "character_count": character_count,
                        "edited": use_edited,
                        "enemies": res["enemies"],
                        "expansions_used": res["expansions_used"],
                    }
                    _apply_added_invaders_to_current_encounter()

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
                    _apply_added_invaders_to_current_encounter()

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
                    or last.get("expansion") != selected_expansion
                )

                if encounter_changed:
                    selected_encounter = filtered_encounters[display_names.index(selected_label)]
                    # Always auto-shuffle to ensure the encounter card is shown
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
                        _apply_added_invaders_to_current_encounter()
                        # Only clear events when we actually switched encounters
                        st.session_state.encounter_events = []
                    else:
                        st.warning(res.get("message", "Unable to build encounter."))

            # --- Optional invader configuration for this encounter ---
            if "current_encounter" in st.session_state:
                _render_invader_setup_controls(st.session_state.current_encounter)

            # Character / expansion icons
            if "current_encounter" in st.session_state:
                icons_html = render_encounter_icons(st.session_state.current_encounter)
                st.markdown(
                    f'<div class="encounter-icons-wrapper">{icons_html}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # ---------------------------------------------------------
            # Save / Load curated encounters
            # ---------------------------------------------------------
            st.subheader("Saved Encounters")

            cloud_mode = bool(is_streamlit_cloud())
            supabase_ready = bool(_has_supabase_config())
            can_persist = (not cloud_mode) or (supabase_ready and auth.is_authenticated())
            if cloud_mode and not supabase_ready:
                st.caption("Saving is disabled until Supabase is configured.")
            elif cloud_mode and not auth.is_authenticated():
                st.caption("Log in to save.")

            save_name_default = (
                st.session_state.get("last_encounter", {}).get("slug") or "custom_encounter"
            )
            save_name = st.text_input("Save as:", value=save_name_default)

            if st.button("Save Current 💾", width="stretch", disabled=not can_persist):
                if "current_encounter" not in st.session_state:
                    st.warning("No active encounter to save.")
                else:
                    if not can_persist:
                        st.error("Not logged in; cannot persist on Streamlit Cloud.")
                        st.stop()
                    # Build payload but strip non-JSON-serializable objects (images/bytes)
                    raw = dict(st.session_state.current_encounter)
                    for k in ("card_img", "buf", "card_bytes"):
                        if k in raw:
                            raw.pop(k, None)

                    # Ensure we do not persist full encounter JSON in saved payloads
                    raw.pop("encounter_data", None)
                    payload = {
                        **raw,
                        "events": st.session_state.get("encounter_events", []),
                        "meta_label": st.session_state.get("last_encounter", {}).get("label"),
                        "character_count": character_count,
                        "edited": use_edited,
                    }
                    st.session_state.saved_encounters[save_name] = payload
                    # Persist saved encounters into dedicated file
                    try:
                        save_saved_encounters(st.session_state.saved_encounters)
                    except Exception:
                        # fallback: store in user settings
                        settings["saved_encounters"] = st.session_state.saved_encounters
                        st.session_state["user_settings"] = settings
                        save_settings(settings)
                    st.success(f"Saved encounter as '{save_name}'.")

            if st.session_state.saved_encounters:
                load_name = st.selectbox(
                    "Load saved encounter:",
                    list(st.session_state.saved_encounters.keys()),
                )
                load_col, delete_col = st.columns([1, 1])
                with load_col:
                    if st.button("Load 📥", width="stretch"):
                        payload = dict(st.session_state.saved_encounters[load_name])

                        # Re-generate the encounter image (images are not persisted).
                        # Load encounter JSON on-demand if it wasn't saved in payload.
                        try:
                            exp = payload.get("expansion") or payload.get("expansions_used", [None])[0]
                            lvl = int(payload.get("encounter_level") or payload.get("level") or 0)
                            nm = payload.get("encounter_name") or payload.get("name")
                            pc = int(payload.get("character_count") or character_count)
                            enc_data = payload.get("encounter_data") or payload.get("data") or {}
                            if not enc_data and exp and nm:
                                enc_data = load_encounter_data(exp, nm, character_count=pc, level=lvl)

                            card_img = generate_encounter_image(
                                exp,
                                lvl,
                                nm,
                                enc_data or {},
                                payload.get("enemies") or [],
                                use_edited=payload.get("edited", False),
                            )
                        except Exception:
                            card_img = None

                        if card_img is not None:
                            payload["card_img"] = card_img
                            try:
                                buf = BytesIO()
                                card_img.save(buf, format="PNG")
                                payload["card_bytes"] = buf.getvalue()
                            except Exception:
                                payload.pop("card_bytes", None)

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

                        # Reconstruct 'added invaders' from payload['invaders']
                        _restore_added_invaders_from_payload(payload)
                        _apply_added_invaders_to_current_encounter()

                with delete_col:
                    if st.button("Delete 🗑️", width="stretch", disabled=needs_login):
                        if load_name in st.session_state.saved_encounters:
                            st.session_state.saved_encounters.pop(load_name, None)
                            # Persist deletion to dedicated file, fallback to settings
                            try:
                                save_saved_encounters(st.session_state.saved_encounters)
                            except Exception:
                                settings["saved_encounters"] = st.session_state.saved_encounters
                                st.session_state["user_settings"] = settings
                                save_settings(settings)
                            st.success(f"Deleted saved encounter '{load_name}'.")
                            st.rerun()

        # -------------------------------------------------------------------------
        # RIGHT COLUMN – CARDS
        # -------------------------------------------------------------------------
        with col_enc:
            if "current_encounter" in st.session_state:
                encounter = st.session_state.current_encounter
                img_bytes = _ensure_card_bytes_inplace(encounter)
                if img_bytes:
                    st.image(img_bytes, width="stretch")
                else:
                    st.caption("Encounter image unavailable.")

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

            elif "last_encounter" in st.session_state:
                st.info(f"Last encounter was {st.session_state['last_encounter']['label']}")
            else:
                st.info("Select an encounter to get started.")

        with col_event.container():
            st.markdown("#### Events")

            configs = load_event_configs()
            render_active_event_deck_selector(
                settings=settings,
                configs=configs,
                label="Active event deck",
                key="enc_setup_active_event_deck",
                rerun_on_change=False,
            )

            events = st.session_state.get("encounter_events", [])

            # Event controls (attach / clear) in this column
            col_ev1, col_ev2, col_ev3 = st.columns(3)
            with col_ev1:
                if st.button(
                    "Attach Random Event 🎲",
                    width="stretch",
                    key="enc_attach_random_event",
                ):
                    ensure_event_deck_ready(settings, configs=configs)

                    # Draw and attach
                    draw_event_card()
                    settings["event_deck"] = st.session_state.get(DECK_STATE_KEY)
                    save_settings(settings)
                    deck_state = st.session_state.get(DECK_STATE_KEY)
                    card_path = deck_state.get("current_card")
                    if card_path:
                        _attach_event_to_current_encounter(card_path)
                    events = st.session_state.get("encounter_events", [])

            with col_ev2:
                if st.button(
                    "Clear Events 🧹",
                    width="stretch",
                    key="enc_clear_events",
                ):
                    st.session_state.encounter_events = []
                    events = []

            # Summary line
            if not events:
                st.caption("No events attached yet.")

            # Event card images
            if events:
                ncols = 3
                for row_start in range(0, len(events), ncols):
                    row_events = events[row_start:row_start + ncols]
                    cols = st.columns(ncols)

                    for i, ev in enumerate(row_events):
                        with cols[i]:
                            img = _event_img_path(ev)
                            if img:
                                ev["path"] = str(img)
                                p = Path(ev["path"])
                                img_bytes = get_image_bytes_cached(str(p))

                                if img_bytes:
                                    st.image(img_bytes, width="stretch")
                            else:
                                st.caption("Event image missing.")
    else:
        st.markdown("#### Encounter Setup")

        # Expansion selection
        selected_expansion = st.selectbox(
            "Set / Expansion",
            filtered_expansions,
            index=0,
            disabled=not valid_party,
        )

        if not selected_expansion:
            if filtered_expansions:
                selected_expansion = filtered_expansions[0]
            else:
                st.error(
                    "No valid expansions available.\n"
                    f"Active expansions: {active_expansions}\n"
                    f"Selected characters: {settings.get('selected_characters', [])}\n"
                    f"Encounter sets loaded: {len(encounters_by_expansion)}"
                )
                st.stop()

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

        # --- Level filter radio buttons (only show levels that exist) ---
        level_values = sorted({e["level"] for e in filtered_encounters})

        level_filter = "All"
        if len(level_values) > 1:
            level_options = ["All"] + [str(lv) for lv in level_values]
            prev_level = st.session_state.get("encounter_level_filter", "All")
            if prev_level not in level_options:
                prev_level = "All"

            level_filter = st.radio(
                "Encounter level",
                level_options,
                index=level_options.index(prev_level),
                horizontal=True,
                key="encounter_level_filter",
            )
        elif len(level_values) == 1:
            # Only a single level available – implicitly filter to it
            level_filter = str(level_values[0])

        if level_filter != "All":
            level_int = int(level_filter)
            filtered_encounters = [
                e for e in filtered_encounters if e["level"] == level_int
            ]

        if not filtered_encounters:
            st.warning("No encounters at this level for the current filters.")
            st.stop()

        display_names = [
            f"{e['name']} (level {e['level']})" for e in filtered_encounters
        ]

        default_label = st.session_state.get("last_encounter", {}).get("label")
        default_index = 0
        if default_label:
            if default_label in display_names:
                default_index = display_names.index(default_label)
            else:
                base = default_label.split(" (level")[0]
                default_index = next(
                    (i for i, d in enumerate(display_names) if d.startswith(base)),
                    0,
                )

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

        # If this encounter has no edited variant, do not persist a toggle
        # entry at all (and clean up any stale persisted entry).
        if not has_edited and key:
            if key in settings["edited_toggles"]:
                del settings["edited_toggles"][key]
                st.session_state["user_settings"] = settings
                save_settings(settings)
            prev_state = False

        widget_key = f"edited_toggle_{encounter_name}_{selected_expansion}"

        def _on_edited_changed_compact():
            new_val = bool(st.session_state.get(widget_key, False))
            settings.setdefault("edited_toggles", {})
            if has_edited and key:
                settings["edited_toggles"][key] = new_val
            st.session_state["user_settings"] = settings
            save_settings(settings)

        use_edited = st.checkbox(
            "Use Edited Encounter",
            value=prev_state,
            key=widget_key,
            disabled=not has_edited,
            on_change=_on_edited_changed_compact,
        )

        if key and has_edited:
            settings["edited_toggles"][key] = use_edited
            # Persist the change immediately so other UI (sidebar) sees it
            st.session_state["user_settings"] = settings
            save_settings(settings)

        toggle_changed = prev_state != use_edited
        st.session_state["last_toggle"] = use_edited

        # --- Shuffle / Original buttons ---
        col_shuffle, col_original = st.columns(2)
        with col_shuffle:
            shuffle_clicked = st.button("Shuffle 🔀", width="stretch")
        with col_original:
            original_clicked = st.button("Original 🔁", width="stretch")

        # Shuffle
        if shuffle_clicked and selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]

            # Try shuffling until we get a different enemy set than the
            # currently-displayed/last one. Cap attempts to avoid infinite loops.
            prev_enemies = (
                st.session_state.get("current_encounter", {}).get("enemies")
                or st.session_state.get("last_encounter", {}).get("enemies")
            )
            max_attempts = 20
            attempt = 0
            final_res = None
            while attempt < max_attempts:
                res = shuffle_encounter(
                    selected_encounter,
                    character_count,
                    active_expansions,
                    selected_expansion,
                    use_edited,
                    render_image=False,
                )
                if not res.get("ok"):
                    final_res = res
                    break
                # If there is no previous enemies to compare to, accept first result
                if not prev_enemies:
                    final_res = res
                    break
                # Accept when enemies differ from previous
                if res.get("enemies") != prev_enemies:
                    final_res = res
                    break
                attempt += 1

            if final_res and final_res.get("ok"):
                # Render the card once (PIL work), after we have a final enemy list.
                if "card_img" not in final_res:
                    card_img = generate_encounter_image(
                        final_res["expansion"],
                        final_res["encounter_level"],
                        final_res["encounter_name"],
                        final_res.get("encounter_data") or {},
                        final_res.get("enemies") or [],
                        use_edited,
                    )
                    final_res["card_img"] = card_img
                    try:
                        buf = BytesIO()
                        card_img.save(buf, format="PNG")
                        final_res["card_bytes"] = buf.getvalue()
                    except Exception:
                        final_res.pop("card_bytes", None)
                else:
                    _ensure_card_bytes_inplace(final_res)

                st.session_state.current_encounter = final_res
                # Reset Play tab state so the Play UI starts fresh for this new encounter
                st.session_state["encounter_play"] = None
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": final_res["enemies"],
                    "expansions_used": final_res["expansions_used"],
                }
                _apply_added_invaders_to_current_encounter()
                if attempt and attempt >= max_attempts:
                    st.warning("Shuffle produced the same enemy list repeatedly; showing last result.")
            else:
                st.warning((final_res or {}).get("message", "Unable to shuffle encounter."))

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
                # Mark this encounter as an Original render so Play uses the Hollow gang
                res["force_gang"] = "Hollow"
                st.session_state.current_encounter = res
                _ensure_card_bytes_inplace(st.session_state.current_encounter)
                # Reset Play tab state so the Play UI starts fresh for this original render
                st.session_state["encounter_play"] = None
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{res['expansion']}_{res['encounter_level']}_{res['encounter_name']}",
                    "expansion": res["expansion"],
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"],
                    "expansions_used": res["expansions_used"],
                }
                _apply_added_invaders_to_current_encounter()

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
                _apply_added_invaders_to_current_encounter()

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
                or last.get("expansion") != selected_expansion
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
                    _ensure_card_bytes_inplace(st.session_state.current_encounter)
                    st.session_state["last_encounter"] = {
                        "label": selected_label,
                        "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                        "expansion": selected_expansion,
                        "character_count": character_count,
                        "edited": use_edited,
                        "enemies": res["enemies"],
                        "expansions_used": res["expansions_used"],
                    }
                    _apply_added_invaders_to_current_encounter()
                    # Only clear events when we actually switched encounters
                    st.session_state.encounter_events = []
                else:
                    st.warning(res.get("message", "Unable to build encounter."))
                    
        if "current_encounter" in st.session_state:
            encounter = st.session_state.current_encounter
            img_bytes = _ensure_card_bytes_inplace(encounter)
            if img_bytes:
                st.image(img_bytes, width="stretch")
            else:
                st.caption("Encounter image unavailable.")

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

        elif "last_encounter" in st.session_state:
            st.info(f"Last encounter was {st.session_state['last_encounter']['label']}")
        else:
            st.info("Select an encounter to get started.")

        # --- Optional invader configuration for this encounter ---
        if "current_encounter" in st.session_state:
            _render_invader_setup_controls(st.session_state.current_encounter)

        st.markdown("#### Events")

        configs = load_event_configs()
        render_active_event_deck_selector(
            settings=settings,
            configs=configs,
            label="Active event deck",
            key="enc_setup_active_event_deck",
            rerun_on_change=False,
        )

        events = st.session_state.get("encounter_events", [])
        
        if st.button(
            "Attach Random Event 🎲",
            width="stretch",
            key="enc_attach_random_event",
        ):
            ensure_event_deck_ready(settings, configs=configs)

            # Draw and attach
            draw_event_card()
            settings["event_deck"] = st.session_state.get(DECK_STATE_KEY)
            save_settings(settings)
            deck_state = st.session_state.get(DECK_STATE_KEY)
            card_path = deck_state.get("current_card")
            if card_path:
                _attach_event_to_current_encounter(card_path)
            events = st.session_state.get("encounter_events", [])
            
        if st.button(
            "Clear Events 🧹",
            width="stretch",
            key="enc_clear_events",
        ):
            st.session_state.encounter_events = []
            events = []

        # Summary line
        if not events:
            st.caption("No events attached yet.")

        # Event card images
        for ev in events:
            img = _event_img_path(ev)
            if img:
                # migrate in-place so future code can rely on "path"
                ev["path"] = str(img)
                # Show image directly
                # If `img` is a path or bytes, `st.image` will handle it.
                st.image(str(img), width="stretch")
            else:
                st.caption("Event image missing.")


# -------------------------------------------------------------------------
# Invader helpers for Setup tab
# -------------------------------------------------------------------------

ADDED_INVADERS_KEY = "encounter_added_invaders_by_key"

_KIRK_KNIGHT = "kirk, knight of thorns"
_KIRK_LONGFINGER = "longfinger kirk"


def _norm_invader_name(name: str) -> str:
    return str(name).strip().lower()


def _invader_map_key(encounter: dict) -> str:
    """
    Build a stable key for 'added invaders' based on the encounter identity
    (expansion + level + name). This intentionally ignores 'edited' so that
    added invaders persist across original/edited toggles.
    """
    exp = encounter.get("expansion") or "?"
    lvl = encounter.get("encounter_level") or encounter.get("level") or "?"
    name = encounter.get("encounter_name") or encounter.get("name") or "?"
    return f"{exp}|{lvl}|{name}"


def _get_all_invader_entries() -> list[BehaviorEntry]:
    """
    Return all BehaviorEntry objects that are invaders (is_invader=True),
    reusing the behavior catalog from the Behavior Decks tab if present.
    """
    catalog = st.session_state.get("behavior_catalog")
    if catalog is None:
        catalog = build_behavior_catalog()
        st.session_state["behavior_catalog"] = catalog

    entries: list[BehaviorEntry] = []
    for per_cat in catalog.values():
        for entry in per_cat:
            if getattr(entry, "is_invader", False) and entry.name:
                entries.append(entry)
    return entries


def _apply_added_invaders_to_current_encounter() -> None:
    """
    Combine 'locked' invaders (those that come from the encounter itself)
    with user-added invaders and store them on encounter['invaders'] so
    the Invaders tab can pick them up.

    Locked invaders are derived from the encounter enemies via the same
    detection logic used in invader_panel, but ignoring any existing
    encounter['invaders'] value.
    """
    if "current_encounter" not in st.session_state:
        return

    encounter = st.session_state.current_encounter
    key = _invader_map_key(encounter)
    added_map = st.session_state.get(ADDED_INVADERS_KEY, {})
    added = added_map.get(key, []) or []

    # If nothing has been added, we don't need an explicit 'invaders' list;
    # the Invaders tab will fall back to enemy display names. :contentReference[oaicite:2]{index=2}
    if not added:
        # But if there *is* already an explicit invaders list from elsewhere,
        # leave it alone.
        return

    # Derive locked invaders from enemies only (ignore any existing 'invaders').
    enc_for_auto = dict(encounter)
    enc_for_auto.pop("invaders", None)

    auto_entries = _get_invader_behavior_entries_for_encounter(enc_for_auto)
    locked_names = [e.name for e in auto_entries]

    seen: set[str] = set()
    combined: list[str] = []

    def _add_name(n: str) -> None:
        k = _norm_invader_name(n)
        if k in seen:
            return
        seen.add(k)
        combined.append(n)

    for n in locked_names:
        _add_name(n)
    for n in added:
        _add_name(n)

    encounter["invaders"] = combined
    st.session_state.current_encounter = encounter


def _restore_added_invaders_from_payload(payload: dict) -> None:
    """
    When loading a saved encounter, reconstruct the 'added invaders' list
    for this encounter key by comparing payload['invaders'] to the invaders
    that can be derived from its enemies.
    """
    inv = payload.get("invaders")
    if not inv:
        return

    # Build the "locked" set from enemies only.
    enc_for_auto = dict(payload)
    enc_for_auto.pop("invaders", None)
    auto_entries = _get_invader_behavior_entries_for_encounter(enc_for_auto)
    auto_norms = {_norm_invader_name(e.name) for e in auto_entries}

    added: list[str] = []

    if isinstance(inv, (list, tuple)):
        for item in inv:
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("display_name")
                    or item.get("id")
                )
            else:
                name = str(item)

            if not name:
                continue

            if _norm_invader_name(name) not in auto_norms:
                added.append(name)

    if not added:
        return

    key = _invader_map_key(payload)
    added_map = st.session_state.setdefault(ADDED_INVADERS_KEY, {})
    added_map[key] = added
    st.session_state[ADDED_INVADERS_KEY] = added_map


def _render_invader_setup_controls(encounter: dict) -> None:
    """
    Expander in the Setup tab to add/remove invaders for the current encounter.

    - Locked invaders (from enemies) are listed but cannot be removed.
    - Added invaders can be removed.
    - Only one of each invader per encounter.
    - 'Kirk, Knight of Thorns' and 'Longfinger Kirk' are mutually exclusive.
    """
    key = _invader_map_key(encounter)

    with st.expander("Invaders for this encounter", expanded=False):
        st.caption(
            "Add extra invaders to this encounter. "
            "Invaders that are part of the encounter setup itself "
            "cannot be removed here."
        )

        # ----- Locked invaders (from enemies / encounter data) -----

        enc_for_auto = dict(encounter)
        enc_for_auto.pop("invaders", None)
        locked_entries = _get_invader_behavior_entries_for_encounter(enc_for_auto)
        locked_names = [e.name for e in locked_entries]

        if locked_names:
            st.markdown("**From encounter enemies (cannot remove):**")
            for name in locked_names:
                st.markdown(f"- {name}")

        # ----- Added invaders (per encounter key) -----

        added_map = st.session_state.setdefault(ADDED_INVADERS_KEY, {})
        added_names: list[str] = list(added_map.get(key, []))

        if added_names:
            st.markdown("**Added invaders:**")
            for idx, name in enumerate(added_names):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"- {name}")
                with c2:
                    if st.button(
                        "❌",
                        key=f"remove_invader_{key}_{idx}",
                        width="stretch"
                    ): 
                        added_names = [n for n in added_names if n != name]
                        added_map[key] = added_names
                        st.session_state[ADDED_INVADERS_KEY] = added_map
                        _apply_added_invaders_to_current_encounter()
                        st.rerun()

        # ----- Add new invader -----

        present_norms = {
            _norm_invader_name(n) for n in (locked_names + added_names)
        }

        all_invaders = _get_all_invader_entries()
        candidate_names: list[str] = []

        for entry in sorted(all_invaders, key=lambda e: e.name):
            nm = entry.name
            kn = _norm_invader_name(nm)
            if kn in present_norms:
                continue

            # Enforce Kirk / Kirk mutual exclusivity
            if kn == _KIRK_KNIGHT and _KIRK_LONGFINGER in present_norms:
                continue
            if kn == _KIRK_LONGFINGER and _KIRK_KNIGHT in present_norms:
                continue

            candidate_names.append(nm)

        if not candidate_names:
            st.caption("No additional invaders available to add.")
            return

        choice = st.selectbox(
            "Add invader:",
            options=["(none)"] + candidate_names,
            key=f"invader_add_select_{key}",
        )

        if choice != "(none)" and st.button(
            "Add invader ➕", key=f"invader_add_btn_{key}",
            width="stretch"
        ):
            if choice not in added_names:
                added_names.append(choice)
                added_map[key] = added_names
                st.session_state[ADDED_INVADERS_KEY] = added_map
                _apply_added_invaders_to_current_encounter()
                st.rerun()

        st.caption(
            "Note: 'Kirk, Knight of Thorns' and 'Longfinger Kirk' "
            "cannot both be present in the same encounter."
        )
