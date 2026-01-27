from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from core.image_cache import get_image_bytes_cached
from ui.encounter_mode.versioning import is_v1_encounter
from ui.event_mode.logic import (
    _attach_event_to_current_encounter,
    list_all_event_cards,
    load_event_configs,
)
from ui.event_mode.panels.simulator import EventSimulatorContext, render_deck_simulator


def _get_card_w(settings: Dict[str, Any]) -> int:
    w = int(
        settings.get(
            "ui_card_width",
            st.session_state.get("ui_card_width", 360),
        )
    )
    return max(240, min(560, w))


def _clear_attached_events() -> None:
    st.session_state.pop("encounter_events", None)
    st.rerun()


def render(settings: Dict[str, Any]) -> None:
    st.markdown("### Encounter Events")

    current_enc = st.session_state.get("current_encounter")
    has_encounter = isinstance(current_enc, dict) and bool(current_enc.get("encounter_name"))
    is_v1 = bool(is_v1_encounter(current_enc)) if has_encounter else False
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

        attached_n = len(st.session_state.get("encounter_events") or [])
        if attached_n:
            st.caption(f"Attached events currently in session: {attached_n}")
            if st.button(
                "Clear attached 🧹",
                width="stretch",
                key="enc_events_clear_attached_v1",
            ):
                _clear_attached_events()

        st.info("Events are available for V2 encounters only.")
        return

    card_w = _get_card_w(settings)

    configs = load_event_configs()

    tab_sim, tab_pick = st.tabs(["Deck Simulator", "Attach Specific Event"])

    # ---------------- Deck Simulator ----------------
    with tab_sim:
        attached_n = len(st.session_state.get("encounter_events") or [])

        def _extra_controls(ctx: EventSimulatorContext) -> None:
            a1, a2 = st.columns(2)
            with a1:
                if st.button(
                    "Attach current 📎",
                    width="stretch",
                    disabled=(not can_attach) or (not ctx.has_current),
                    key="enc_events_attach_current",
                ):
                    _attach_event_to_current_encounter(ctx.event_name, str(ctx.current_card))
            with a2:
                if st.button(
                    "Clear attached 🧹",
                    width="stretch",
                    disabled=not bool(st.session_state.get("encounter_events")),
                    key="enc_events_clear_attached",
                ):
                    _clear_attached_events()

        render_deck_simulator(
            settings=settings,
            configs=configs,
            card_width=card_w,
            key_prefix="enc_events_sim",
            show_preset_selector=True,
            preset_select_key="enc_events_preset",
            extra_left_controls=_extra_controls,
            extra_metrics=[("Attached", attached_n)],
            discard_mode="titles",
        )

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
