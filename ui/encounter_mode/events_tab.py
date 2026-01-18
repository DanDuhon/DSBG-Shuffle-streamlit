# ui/encounter_mode/events_tab.py
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from core.settings_manager import save_settings
from ui.encounter_mode.play_panels import _is_v1_encounter
from ui.event_mode.logic import (
    DECK_STATE_KEY,
    RENDEZVOUS_EVENTS,
    draw_event_card,
    initialize_event_deck,
    list_all_event_cards,
    list_event_deck_options,
    load_event_configs,
    put_current_on_bottom,
    put_current_on_top,
    remove_card_from_deck,
    reset_event_deck,
    shuffle_current_into_deck,
)
from core.image_cache import get_image_bytes_cached


def _ensure_deck_state(settings: Dict[str, Any]) -> Dict[str, Any]:
    state = st.session_state.get(DECK_STATE_KEY)
    if isinstance(state, dict):
        return state

    saved = settings.get("event_deck")
    if isinstance(saved, dict):
        st.session_state[DECK_STATE_KEY] = saved
        return saved

    state = {"draw_pile": [], "discard_pile": [], "current_card": None, "preset": None}
    st.session_state[DECK_STATE_KEY] = state
    return state


def _get_card_w(settings: Dict[str, Any]) -> int:
    w = int(
        settings.get(
            "ui_card_width",
            st.session_state.get("ui_card_width", 360),
        )
    )
    return max(240, min(560, w))


def _sync_deck_to_settings(settings: Dict[str, Any]) -> None:
    deck_state = st.session_state.get(DECK_STATE_KEY)
    if isinstance(deck_state, dict):
        settings["event_deck"] = deck_state
        save_settings(settings)


def _attach_event_to_current_encounter(event_name: str, card_path: str) -> None:
    name = str(event_name or "").strip()
    if not name:
        return

    name_norm = name.lower()
    is_rendezvous = name_norm in RENDEZVOUS_EVENTS

    events = st.session_state.get("encounter_events")
    if not isinstance(events, list):
        events = []

    # Rendezvous: only one at a time
    if is_rendezvous:
        events = [
            e
            for e in events
            if not (isinstance(e, dict) and bool(e.get("is_rendezvous")))
        ]

    base = Path(str(card_path)).stem if card_path else name
    event_obj = {
        "id": base,
        "name": name,
        "path": str(card_path),
        "card_path": str(card_path),      # keep alias for backward-compat
        "image_path": str(card_path),     # keep alias for backward-compat
        "is_rendezvous": is_rendezvous,
    }
    events.append(event_obj)
    st.session_state["encounter_events"] = events
    st.rerun()


def _clear_attached_events() -> None:
    st.session_state.pop("encounter_events", None)
    st.rerun()


def render(settings: Dict[str, Any]) -> None:
    st.markdown("### Encounter Events")

    current_enc = st.session_state.get("current_encounter")
    has_encounter = isinstance(current_enc, dict) and bool(current_enc.get("encounter_name"))
    is_v1 = bool(_is_v1_encounter(current_enc)) if has_encounter else False
    can_attach = has_encounter and not is_v1

    if has_encounter:
        exp = current_enc.get("expansion", "")
        lvl = current_enc.get("encounter_level", "")
        name = current_enc.get("encounter_name", "")
        st.caption(f"Current encounter: {exp} · Level {lvl} · {name}")
    else:
        st.caption("Current encounter: —")

    if has_encounter and is_v1:
        st.caption("V1 encounter selected: Encounter Mode ignores attached events for V1 encounters.")

    card_w = _get_card_w(settings)

    configs = load_event_configs()
    opts = list_event_deck_options(configs=configs)

    tab_sim, tab_pick = st.tabs(["Deck Simulator", "Attach Specific Event"])

    # ---------------- Deck Simulator ----------------
    with tab_sim:
        deck_state = _ensure_deck_state(settings)
        preset = deck_state.get("preset") or (settings.get("event_deck") or {}).get("preset")

        if not preset and opts:
            preset = opts[0]
            initialize_event_deck(preset, configs=configs)
            _sync_deck_to_settings(settings)
            deck_state = st.session_state[DECK_STATE_KEY]

        if preset and not (
            deck_state.get("draw_pile") or deck_state.get("discard_pile") or deck_state.get("current_card")
        ):
            initialize_event_deck(preset, configs=configs)
            _sync_deck_to_settings(settings)
            deck_state = st.session_state[DECK_STATE_KEY]

        if opts:
            sel = st.selectbox(
                "Event deck",
                options=opts,
                index=opts.index(preset) if preset in opts else 0,
                key="enc_events_preset",
            )
            if sel != preset:
                initialize_event_deck(sel, configs=configs)
                _sync_deck_to_settings(settings)
                st.rerun()
            preset = sel
        else:
            st.caption("No event decks found.")

        if not st.session_state.get("ui_compact", False):
            left, mid, right = st.columns([1, 0.7, 0.85], gap="small")

            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_stem = Path(str(current_card)).stem if current_card else ""
            event_name = card_stem.replace("_", " ").strip() if card_stem else ""
            name_norm = event_name.lower() if event_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            with left:
                r1a, r1b = st.columns(2)
                with r1a:
                    if st.button("Draw 🃏", width="stretch", key="enc_events_sim_draw"):
                        draw_event_card()
                        _sync_deck_to_settings(settings)
                with r1b:
                    if st.button("Reset and Shuffle 🔄", width="stretch", key="enc_events_sim_reset"):
                        reset_event_deck(configs=configs, preset=preset)
                        _sync_deck_to_settings(settings)

                # refresh locals
                deck_state = st.session_state.get(DECK_STATE_KEY, deck_state)
                current_card = deck_state.get("current_card")
                has_current = bool(current_card)
                card_stem = Path(str(current_card)).stem if current_card else ""
                event_name = card_stem.replace("_", " ").strip() if card_stem else ""
                name_norm = event_name.lower() if event_name else ""
                is_big_pilgrims_key = name_norm == "big pilgrim's key"
                is_lost_to_time = name_norm == "lost to time"

                r2a, r2b = st.columns(2)
                with r2a:
                    if st.button(
                        "Current → Top ⬆️",
                        width="stretch",
                        disabled=not has_current,
                        key="enc_events_sim_top",
                    ):
                        put_current_on_top()
                        _sync_deck_to_settings(settings)
                with r2b:
                    if st.button(
                        "Current → Bottom ⬇️",
                        width="stretch",
                        disabled=not has_current,
                        key="enc_events_sim_bottom",
                    ):
                        put_current_on_bottom()
                        _sync_deck_to_settings(settings)

                # refresh locals
                deck_state = st.session_state.get(DECK_STATE_KEY, deck_state)
                current_card = deck_state.get("current_card")
                has_current = bool(current_card)
                card_stem = Path(str(current_card)).stem if current_card else ""
                event_name = card_stem.replace("_", " ").strip() if card_stem else ""
                name_norm = event_name.lower() if event_name else ""
                is_big_pilgrims_key = name_norm == "big pilgrim's key"
                is_lost_to_time = name_norm == "lost to time"

                a1, a2 = st.columns(2)
                with a1:
                    if st.button(
                        "Attach current 📎",
                        width="stretch",
                        disabled=(not can_attach) or (not has_current),
                        key="enc_events_attach_current",
                    ):
                        _attach_event_to_current_encounter(event_name, str(current_card))
                with a2:
                    if st.button(
                        "Clear attached 🧹",
                        width="stretch",
                        disabled=not bool(st.session_state.get("encounter_events")),
                        key="enc_events_clear_attached",
                    ):
                        _clear_attached_events()

                if has_current and (is_big_pilgrims_key or is_lost_to_time):
                    s1, s2 = st.columns(2)
                    with s1:
                        if st.button(
                            "Shuffle into deck 🔀",
                            width="stretch",
                            key="enc_events_sim_shuffle_into_deck",
                        ):
                            shuffle_current_into_deck()
                            _sync_deck_to_settings(settings)
                            st.rerun()
                    with s2:
                        if is_lost_to_time:
                            if st.button(
                                "Remove from deck ❌",
                                width="stretch",
                                key="enc_events_sim_remove_from_deck",
                            ):
                                remove_card_from_deck()
                                _sync_deck_to_settings(settings)
                                st.rerun()

                draw_n = len(deck_state.get("draw_pile") or [])
                discard_n = len(deck_state.get("discard_pile") or [])
                total_n = draw_n + discard_n + (1 if deck_state.get("current_card") else 0)
                attached_n = len(st.session_state.get("encounter_events") or [])

                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("Draw", draw_n)
                with m2:
                    st.metric("Discard", discard_n)
                with m3:
                    st.metric("Total", total_n)
                with m4:
                    st.metric("Attached", attached_n)

            with mid:
                if current_card:
                    p = Path(str(current_card))
                    img_bytes = get_image_bytes_cached(str(p))

                    if img_bytes:
                        st.image(img_bytes, width=card_w)
                    st.caption(event_name or "—")
                else:
                    st.markdown("### Current card")
                    st.caption("—")

            with right:
                st.markdown("### Discard")
                discard = list(deck_state.get("discard_pile") or [])
                if not discard:
                    st.caption("Empty")
                else:
                    # simple, fast: just list newest-first
                    for p in reversed(discard[-50:]):
                        st.caption(Path(str(p)).stem.replace("_", " "))
        else:
            left, mid, right = st.columns([1, 0.7, 0.85], gap="small")

            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_stem = Path(str(current_card)).stem if current_card else ""
            event_name = card_stem.replace("_", " ").strip() if card_stem else ""
            name_norm = event_name.lower() if event_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            if st.button("Draw 🃏", width="stretch", key="enc_events_sim_draw"):
                draw_event_card()
                _sync_deck_to_settings(settings)

            # refresh locals
            deck_state = st.session_state.get(DECK_STATE_KEY, deck_state)
            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_stem = Path(str(current_card)).stem if current_card else ""
            event_name = card_stem.replace("_", " ").strip() if card_stem else ""
            name_norm = event_name.lower() if event_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            if has_current and (is_big_pilgrims_key or is_lost_to_time):
                if st.button(
                    "Shuffle into deck 🔀",
                    width="stretch",
                    key="enc_events_sim_shuffle_into_deck",
                ):
                    shuffle_current_into_deck()
                    _sync_deck_to_settings(settings)
                    st.rerun()
                    
                    if is_lost_to_time:
                        if st.button(
                            "Remove from deck ❌",
                            width="stretch",
                            key="enc_events_sim_remove_from_deck",
                        ):
                            remove_card_from_deck()
                            _sync_deck_to_settings(settings)
                            st.rerun()

            draw_n = len(deck_state.get("draw_pile") or [])
            discard_n = len(deck_state.get("discard_pile") or [])
            total_n = draw_n + discard_n + (1 if deck_state.get("current_card") else 0)
            attached_n = len(st.session_state.get("encounter_events") or [])

            if current_card:
                p = Path(str(current_card))
                img_bytes = get_image_bytes_cached(str(p))

                if img_bytes:
                    st.image(img_bytes, width=card_w)
                st.caption(event_name or "—")
            else:
                st.markdown("### Current card")
                st.caption("—")

            if st.button(
                "Attach current 📎",
                width="stretch",
                disabled=(not can_attach) or (not has_current),
                key="enc_events_attach_current",
            ):
                _attach_event_to_current_encounter(event_name, str(current_card))
                
            if st.button(
                "Clear attached 🧹",
                width="stretch",
                disabled=not bool(st.session_state.get("encounter_events")),
                key="enc_events_clear_attached",
            ):
                _clear_attached_events()
                
            if st.button("Reset and Shuffle 🔄", width="stretch", key="enc_events_sim_reset"):
                reset_event_deck(configs=configs, preset=preset)
                _sync_deck_to_settings(settings)

            if st.button(
                "Current → Top ⬆️",
                width="stretch",
                disabled=not has_current,
                key="enc_events_sim_top",
            ):
                put_current_on_top()
                _sync_deck_to_settings(settings)
                
            if st.button(
                "Current → Bottom ⬇️",
                width="stretch",
                disabled=not has_current,
                key="enc_events_sim_bottom",
            ):
                put_current_on_bottom()
                _sync_deck_to_settings(settings)

            # refresh locals
            deck_state = st.session_state.get(DECK_STATE_KEY, deck_state)
            current_card = deck_state.get("current_card")
            has_current = bool(current_card)
            card_stem = Path(str(current_card)).stem if current_card else ""
            event_name = card_stem.replace("_", " ").strip() if card_stem else ""
            name_norm = event_name.lower() if event_name else ""
            is_big_pilgrims_key = name_norm == "big pilgrim's key"
            is_lost_to_time = name_norm == "lost to time"

            st.markdown("### Discard")
            discard = list(deck_state.get("discard_pile") or [])
            if not discard:
                st.caption("Empty")
            else:
                # simple, fast: just list newest-first
                for p in reversed(discard[-50:]):
                    st.caption(Path(str(p)).stem.replace("_", " "))

    # ---------------- Attach Specific Event ----------------
    with tab_pick:
        cards: List[Dict[str, Any]] = list_all_event_cards(configs=configs)

        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            search = st.text_input("Search", value="", key="enc_events_pick_search")
        with c2:
            type_opts = ["Consumable", "Immediate", "Rendezvous"]
            type_filter = st.multiselect(
                "Type",
                options=type_opts,
                default=type_opts,
                key="enc_events_pick_types",
            )
        with c3:
            exp_opts = sorted(
                {
                    str(c.get("expansion") or "")
                    for c in cards
                    if str(c.get("expansion") or "").strip()
                }
            )
            exp_sel = st.multiselect(
                "Expansion",
                options=exp_opts,
                default=exp_opts,
                key="enc_events_pick_exps",
            )

        if search.strip():
            s = search.strip().lower()
            cards = [c for c in cards if s in str(c.get("id", "")).lower()]

        if type_filter:
            allowed = set(type_filter)
            cards = [c for c in cards if str(c.get("type") or "") in allowed]
        else:
            cards = []

        if exp_sel:
            allowed_exp = set(exp_sel)
            cards = [c for c in cards if str(c.get("expansion") or "") in allowed_exp]

        cards = sorted(cards, key=lambda x: str(x.get("name") or ""))

        left, right = st.columns([1, 0.5], gap="large")

        if not cards:
            with left:
                st.caption("No events match the current filters.")
            with right:
                st.markdown("### Card")
                st.caption("—")
        else:
            labels = [
                f"{c.get('id','')} · {c.get('type','')}".strip()
                for c in cards
            ]

            with left:
                choice = st.radio(
                    "Events",
                    options=labels,
                    index=0,
                    key="enc_events_pick_radio",
                )
                chosen = cards[labels.index(choice)]

                if st.button(
                    "Attach selected 📎",
                    width="stretch",
                    disabled=not can_attach,
                    key="enc_events_attach_selected",
                ):
                    _attach_event_to_current_encounter(str(chosen["id"]), str(chosen["image_path"]))

            with right:
                st.markdown("### Card")
                p = Path(str(chosen["image_path"]))
                img_bytes = get_image_bytes_cached(str(p))

                if img_bytes:
                    st.image(img_bytes, width=card_w)
                txt = str(chosen.get("text") or "").strip()
                if txt:
                    st.caption(txt)
