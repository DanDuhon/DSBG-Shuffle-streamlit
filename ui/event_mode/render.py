# ui/event_mode/render.py
import os
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from core.settings_manager import save_settings
from ui.event_mode.logic import (
    DECK_STATE_KEY,
    draw_event_card,
    initialize_event_deck,
    list_all_event_cards,
    list_event_deck_options,
    load_custom_event_decks,
    load_event_configs,
    save_custom_event_decks,
    put_current_on_bottom,
    put_current_on_top,
    remove_card_from_deck,
    reset_event_deck,
    shuffle_current_into_deck,
    _ensure_deck_state,
)

# cached image helper (use at module level to avoid repeated dynamic imports)
from core.image_cache import get_image_data_uri_cached, get_image_bytes_cached


_BUILDER_KEY = "event_mode_builder"
_BUILDER_SYNC_KEY = "event_mode_builder_sync"


# Use shared `_ensure_deck_state` from `ui.event_mode.logic`.


def _builder_get() -> Dict[str, Any]:
    b = st.session_state.get(_BUILDER_KEY)
    if isinstance(b, dict):
        b.setdefault("name", "")
        b.setdefault("cards", {})
        return b
    b = {"name": "", "cards": {}, "loaded_from": None}
    st.session_state[_BUILDER_KEY] = b
    return b


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
        title = os.path.splitext(os.path.basename(path))[0]
        src = __import__(
            "core.image_cache", fromlist=["get_image_data_uri_cached"]
        ).get_image_data_uri_cached(path)
        if not src:
            raise Exception("empty data uri")
        cards_html.append(
            f'<img src="{src}" '
            f'style="position:absolute; top:{top}px; left:0; '
            f'width:{card_width}px; border-radius:8px; box-shadow:2px 2px 6px rgba(0,0,0,0.5);" '
            f'title="{title}">'
        )

    stack_html = f"<div style='position:relative; width:{card_width}px; height:{total_h}px;'>{''.join(cards_html)}</div>"
    container_html = f"<div style='max-height:{max_iframe_height}px; overflow-y:auto; padding-right:5px;'>{stack_html}</div>"
    st.components.v1.html(container_html, height=max_iframe_height)


def _render_discard_container(deck_state: Dict[str, Any]) -> None:
    discard = list(deck_state.get("discard_pile") or [])
    if not discard:
        with st.container(border=True):
            st.caption("Empty.")
        return

    with st.container(border=True):
        i_col, t_col = st.columns([1, 1])
        with i_col:
            render_discard_pile(discard)
        with t_col:
            st.caption(
                "  \n".join(
                    [
                        os.path.splitext(os.path.basename(path))[0]
                        for path in reversed(discard)
                    ]
                )
            )


def render(settings: Dict[str, Any]) -> None:
    configs = load_event_configs()
    deck_state = _ensure_deck_state(settings)

    options = list_event_deck_options(configs=configs)
    current = deck_state.get("preset") or (settings.get("event_deck") or {}).get(
        "preset"
    )
    if current not in options:
        current = options[0] if options else None

    # Active deck selector (this is the global toggle used by all modes)
    if options:
        chosen = st.selectbox(
            "Active event deck",
            options=options,
            index=options.index(current) if current in options else 0,
        )
        if chosen != current:
            initialize_event_deck(chosen, configs=configs)
            deck_state = st.session_state[DECK_STATE_KEY]
            settings["event_deck"] = deck_state
            save_settings(settings)

    tab_builder, tab_sim = st.tabs(["Deck Builder", "Deck Simulator"])

    # ---------------- Deck Builder ----------------
    with tab_builder:
        custom_decks = load_custom_event_decks()
        names = sorted(custom_decks.keys())

        c1, c2 = st.columns([1.2, 1])

        with c1:
            st.markdown("### Edit / Create")
            pick = st.selectbox(
                "Load custom deck", options=["(new)"] + names, key="event_builder_pick"
            )

            if st.button("Load into editor 📥", width="stretch"):
                b = _builder_get()
                if pick == "(new)":
                    b.update({"name": "", "cards": {}, "loaded_from": None})
                else:
                    d = custom_decks.get(pick) or {}
                    cards = d.get("cards") if isinstance(d, dict) else {}
                    b.update(
                        {"name": pick, "cards": dict(cards or {}), "loaded_from": pick}
                    )
                st.session_state[_BUILDER_KEY] = b
                st.session_state[_BUILDER_SYNC_KEY] = True

            b = _builder_get()
            # Persist the name input to a stable session key so we can clear it
            # when deleting a deck without needing another render pass.
            b_name = st.text_input(
                "Deck name", value=b.get("name", "") or "", key="event_builder_name"
            )
            b["name"] = b_name

        with c2:
            st.markdown("### Deck Summary")
            b = _builder_get()
            # Build card counts from the live number-input session keys so
            # UI changes immediately enable the Save button without a full
            # rerun that updates the builder map first.
            cards_map: Dict[str, int] = {}
            prefix = "event_builder_copies_all::"
            for key, val in st.session_state.items():
                if not isinstance(key, str) or not key.startswith(prefix):
                    continue
                path = key.split("::", 1)[1]
                try:
                    copies = int(val or 0)
                except Exception:
                    copies = 0
                if copies <= 0:
                    continue
                canon = Path(str(path)).as_posix()
                cards_map[canon] = cards_map.get(canon, 0) + copies
            total = sum(int(v or 0) for v in cards_map.values())
            st.markdown(f"**Unique cards:** {len(cards_map)}")
            st.markdown(f"**Total cards:** {total}")

            save_disabled = not (b.get("name") and cards_map)

            if st.button("Save custom deck 💾", width="stretch", disabled=save_disabled):
                name = str(b["name"]).strip()
                if name:
                    custom_decks[name] = {"cards": dict(cards_map)}
                    save_custom_event_decks(custom_decks)
                    # Update builder state to reflect saved deck and force
                    # the UI to refresh so the new deck is listed in the
                    # "Load custom deck" dropdown immediately.
                    b["loaded_from"] = name
                    st.session_state[_BUILDER_KEY] = b
                    st.session_state[_BUILDER_SYNC_KEY] = True
                    try:
                        st.session_state["event_builder_pick"] = name
                    except Exception:
                        pass
                    try:
                        st.session_state["event_builder_name"] = name
                    except Exception:
                        pass
                    st.rerun()

            # Reset per-card counts to zero without deleting the saved deck
            reset_disabled = not bool(cards_map)
            if st.button("Reset deck 🔄", width="stretch", disabled=reset_disabled):
                prefix = "event_builder_copies_all::"
                for key in list(st.session_state.keys()):
                    if isinstance(key, str) and key.startswith(prefix):
                        try:
                            st.session_state[key] = 0
                        except Exception:
                            pass
                # Clear builder map and sync to UI
                b.update({"cards": {}})
                st.session_state[_BUILDER_KEY] = b
                st.session_state[_BUILDER_SYNC_KEY] = True
                st.rerun()

            del_disabled = not (
                b.get("loaded_from") and b.get("loaded_from") in custom_decks
            )
            if st.button("Delete loaded deck 🗑️", width="stretch", disabled=del_disabled):
                loaded = b.get("loaded_from")
                if loaded in custom_decks:
                    del custom_decks[loaded]
                    save_custom_event_decks(custom_decks)
                    # Clear builder state and UI widgets
                    b.update({"name": "", "cards": {}, "loaded_from": None})
                    st.session_state[_BUILDER_KEY] = b
                    st.session_state[_BUILDER_SYNC_KEY] = True
                    # Reset the load selector to the default '(new)'
                    try:
                        st.session_state["event_builder_pick"] = "(new)"
                    except Exception:
                        pass
                    # Clear the deck name input
                    try:
                        st.session_state["event_builder_name"] = ""
                    except Exception:
                        pass
                    # Zero all per-card copies inputs so the UI reflects an empty deck
                    prefix = "event_builder_copies_all::"
                    for key in list(st.session_state.keys()):
                        if isinstance(key, str) and key.startswith(prefix):
                            try:
                                st.session_state[key] = 0
                            except Exception:
                                pass
                    st.rerun()

        st.markdown("---")

        search_col, type_col, deck_col = st.columns([1, 1, 1])
        with search_col:
            search = st.text_input("Search card names", value="")
        with type_col:
            type_opts = ["Consumable", "Immediate", "Rendezvous"]
            type_filter = st.multiselect(
                "Card types", options=type_opts, default=type_opts
            )
        with deck_col:
            show_only_selected = st.checkbox("Show only cards in deck", value=False)

        cards = list_all_event_cards(configs=configs)
        if search.strip():
            s = search.strip().lower()
            cards = [c for c in cards if s in str(c.get("id", "")).lower()]
        if type_filter:
            allowed = set(type_filter)
            cards = [c for c in cards if str(c.get("type") or "") in allowed]
        else:
            cards = []

        # Full card list (filtered) with per-card copies inputs
        b = _builder_get()
        raw_map: Dict[str, Any] = b.get("cards") or {}
        cards_map: Dict[str, int] = {}
        for k, v in raw_map.items():
            copies = int(v or 0)
            if copies <= 0:
                continue
            canon = Path(str(k)).as_posix()
            cards_map[canon] = cards_map.get(canon, 0) + copies
        sync = bool(st.session_state.pop(_BUILDER_SYNC_KEY, False))

        for c in cards:
            img_path = Path(str(c["image_path"])).as_posix()
            if show_only_selected and img_path not in cards_map:
                continue

            card_id = str(c.get("id", ""))
            exp = str(c.get("expansion", ""))
            event_type = c.get("type")
            text = c.get("text")
            cur = int(cards_map.get(img_path, 0) or 0)

            key = f"event_builder_copies_all::{img_path}"
            if sync:
                st.session_state[key] = cur
            elif key not in st.session_state:
                st.session_state[key] = cur

            r_img, r_id, r_exp, r_type, r_text, r_copies = st.columns(
                [0.4, 1.4, 1.2, 1.2, 3.1, 1.6]
            )
            with r_img:
                p = Path(img_path)
                img_bytes = get_image_bytes_cached(str(p))
                if img_bytes:
                    st.image(img_bytes, width="stretch")

                st.markdown(
                    "<div style='height:0.05rem'></div>", unsafe_allow_html=True
                )
            with r_id:
                st.caption(card_id)
            with r_exp:
                st.caption(exp)
            with r_type:
                st.caption(event_type)
            with r_text:
                if isinstance(text, str) and text.strip():
                    st.caption(text)
                else:
                    st.caption("—")
            with r_copies:
                v = st.number_input(
                    "copies",
                    min_value=0,
                    max_value=50,
                    step=1,
                    key=key,
                    label_visibility="collapsed",
                )
            v = int(v or 0)
            if v > 0:
                cards_map[img_path] = v
            else:
                cards_map.pop(img_path, None)

        b["cards"] = dict(cards_map)
        st.session_state[_BUILDER_KEY] = b

    # ---------------- Deck Simulator ----------------
    with tab_sim:
        deck_state = _ensure_deck_state(settings)
        preset = deck_state.get("preset") or (settings.get("event_deck") or {}).get(
            "preset"
        )
        opts = list_event_deck_options(configs=configs)
        if not preset and opts:
            preset = opts[0]
            initialize_event_deck(preset, configs=configs)
            deck_state = st.session_state[DECK_STATE_KEY]
            settings["event_deck"] = deck_state
            save_settings(settings)

        # Only auto-init if the deck is truly empty (avoid rebuilding mid-run).
        if preset and not (
            deck_state.get("draw_pile")
            or deck_state.get("discard_pile")
            or deck_state.get("current_card")
        ):
            initialize_event_deck(preset, configs=configs)
            deck_state = st.session_state[DECK_STATE_KEY]
            settings["event_deck"] = deck_state
            save_settings(settings)

        if not st.session_state.get("ui_compact", False):
            # Desktop Layout:
            #   Left: buttons + metrics
            #   Mid: current card
            #   Right: discard container
            left, mid, right = st.columns([1, 0.7, 0.85], gap="small")

            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_name = Path(str(current_card)).stem if current_card else ""
            name_norm = card_name.replace("_", " ").strip().lower() if card_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            with left:
                b_row1_a, b_row1_b = st.columns(2)
                with b_row1_a:
                    if st.button("Draw 🃏", width="stretch", key="event_sim_draw"):
                        draw_event_card()
                        deck_state = st.session_state[DECK_STATE_KEY]
                        settings["event_deck"] = deck_state
                        save_settings(settings)
                with b_row1_b:
                    if st.button(
                        "Reset and Shuffle 🔄", width="stretch", key="event_sim_reset"
                    ):
                        reset_event_deck(configs=configs, preset=preset)
                        deck_state = st.session_state[DECK_STATE_KEY]
                        settings["event_deck"] = deck_state
                        save_settings(settings)

                b_row2_a, b_row2_b = st.columns(2)
                with b_row2_a:
                    if st.button(
                        "Current → Top ⬆️",
                        width="stretch",
                        disabled=not has_current,
                        key="event_sim_top",
                    ):
                        put_current_on_top()
                        deck_state = st.session_state[DECK_STATE_KEY]
                        settings["event_deck"] = deck_state
                        save_settings(settings)
                with b_row2_b:
                    if st.button(
                        "Current → Bottom ⬇️",
                        width="stretch",
                        disabled=not has_current,
                        key="event_sim_bottom",
                    ):
                        put_current_on_bottom()
                        deck_state = st.session_state[DECK_STATE_KEY]
                        settings["event_deck"] = deck_state
                        save_settings(settings)

                # Refresh locals after any action.
                current_card = deck_state.get("current_card")
                has_current = bool(current_card)
                card_name = Path(str(current_card)).stem if current_card else ""
                name_norm = (
                    card_name.replace("_", " ").strip().lower() if card_name else ""
                )
                is_big_pilgrims_key = name_norm == "big pilgrim's key"
                is_lost_to_time = name_norm == "lost to time"

                # Card-specific buttons belong in the left controls column.
                if has_current and (is_big_pilgrims_key or is_lost_to_time):
                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                                "Shuffle into deck 🔀",
                                width="stretch",
                                key="event_sim_shuffle_into_deck",
                            ):
                            shuffle_current_into_deck()
                            deck_state = st.session_state[DECK_STATE_KEY]
                            settings["event_deck"] = deck_state
                            save_settings(settings)
                            st.rerun()
                    with a2:
                        if is_lost_to_time:
                            if st.button(
                                "Remove from deck 🗑️",
                                width="stretch",
                                key="event_sim_remove_from_deck",
                            ):
                                remove_card_from_deck()
                                deck_state = st.session_state[DECK_STATE_KEY]
                                settings["event_deck"] = deck_state
                                save_settings(settings)
                                st.rerun()

                draw_n = len(deck_state.get("draw_pile") or [])
                discard_n = len(deck_state.get("discard_pile") or [])
                total_n = (
                    draw_n + discard_n + (1 if deck_state.get("current_card") else 0)
                )

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Draw", draw_n)
                with m2:
                    st.metric("Discard", discard_n)
                with m3:
                    st.metric("Total", total_n)

            with mid:
                if current_card:
                    card_name = Path(str(current_card)).stem
                    p = Path(str(current_card))
                    img_bytes = get_image_bytes_cached(str(p))
                    if img_bytes:
                        st.image(img_bytes, width="stretch")
                else:
                    st.markdown("### Current card")
                    st.caption("—")

            with right:
                st.markdown("### Discard")
                _render_discard_container(deck_state)
        else:

            def _sync_deck_to_settings() -> None:
                ds = st.session_state.get(DECK_STATE_KEY)
                if not isinstance(ds, dict):
                    return
                settings["event_deck"] = ds
                save_settings(settings)

            def _cb_draw() -> None:
                draw_event_card()
                _sync_deck_to_settings()

            def _cb_reset() -> None:
                ds = st.session_state.get(DECK_STATE_KEY) or {}
                preset_now = ds.get("preset") or preset
                reset_event_deck(configs=configs, preset=preset_now)
                _sync_deck_to_settings()

            def _cb_top() -> None:
                put_current_on_top()
                _sync_deck_to_settings()

            def _cb_bottom() -> None:
                put_current_on_bottom()
                _sync_deck_to_settings()

            def _cb_shuffle_into_deck() -> None:
                shuffle_current_into_deck()
                _sync_deck_to_settings()

            def _cb_remove_from_deck() -> None:
                remove_card_from_deck()
                _sync_deck_to_settings()

            # Read fresh state for this render pass
            deck_state = _ensure_deck_state(settings)
            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_name = Path(str(current_card)).stem if current_card else ""
            name_norm = card_name.replace("_", " ").strip().lower() if card_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            st.button("Draw 🃏", width="stretch", key="event_sim_draw", on_click=_cb_draw)

            if has_current and (is_big_pilgrims_key or is_lost_to_time):
                st.button(
                    "Shuffle into deck 🔀",
                    width="stretch",
                    key="event_sim_shuffle_into_deck",
                    on_click=_cb_shuffle_into_deck,
                )
                if is_lost_to_time:
                    st.button(
                        "Remove from deck 🗑️",
                        width="stretch",
                        key="event_sim_remove_from_deck",
                        on_click=_cb_remove_from_deck,
                    )

                if current_card:
                    p = Path(str(current_card))
                    img_bytes = get_image_bytes_cached(str(p))
                    if img_bytes:
                        st.image(img_bytes, width="stretch")
            else:
                st.markdown("### Current card")
                st.caption("—")

            st.button(
                "Current → Top ⬆️",
                width="stretch",
                disabled=not has_current,
                key="event_sim_top",
                on_click=_cb_top,
            )
            st.button(
                "Current → Bottom ⬇️",
                width="stretch",
                disabled=not has_current,
                key="event_sim_bottom",
                on_click=_cb_bottom,
            )

            st.button(
                "Reset and Shuffle 🔄",
                width="stretch",
                key="event_sim_reset",
                on_click=_cb_reset,
            )

            st.markdown("### Discard")
            _render_discard_container(deck_state)
