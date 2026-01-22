from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

import streamlit as st

from core.image_cache import get_image_bytes_cached
from core.settings_manager import save_settings
from ui.event_mode.logic import (
    DECK_STATE_KEY,
    _ensure_deck_state,
    draw_event_card,
    initialize_event_deck,
    list_event_deck_options,
    put_current_on_bottom,
    put_current_on_top,
    remove_card_from_deck,
    reset_event_deck,
    shuffle_current_into_deck,
)
from ui.event_mode.panels.discard import render_discard_container, render_discard_titles


@dataclass(frozen=True)
class EventSimulatorContext:
    deck_state: Dict[str, Any]
    preset: Optional[str]
    current_card: Optional[str]
    event_name: str
    has_current: bool
    is_big_pilgrims_key: bool
    is_lost_to_time: bool


def _event_name_from_path(card_path: Optional[str]) -> str:
    if not card_path:
        return ""
    stem = Path(str(card_path)).stem
    return stem.replace("_", " ").strip()


def _sync_deck_to_settings(settings: Dict[str, Any]) -> None:
    deck_state = st.session_state.get(DECK_STATE_KEY)
    if isinstance(deck_state, dict):
        settings["event_deck"] = deck_state
        save_settings(settings)


def _context_from_state(deck_state: Dict[str, Any], preset: Optional[str]) -> EventSimulatorContext:
    current_card = deck_state.get("current_card")
    has_current = bool(current_card)

    event_name = _event_name_from_path(current_card)
    name_norm = event_name.lower() if event_name else ""

    return EventSimulatorContext(
        deck_state=deck_state,
        preset=preset,
        current_card=str(current_card) if current_card else None,
        event_name=event_name,
        has_current=has_current,
        is_big_pilgrims_key=name_norm == "big pilgrim's key",
        is_lost_to_time=name_norm == "lost to time",
    )


def render_deck_simulator(
    *,
    settings: Dict[str, Any],
    configs: Dict[str, Any],
    card_width: int | str = "stretch",
    key_prefix: str = "event_sim",
    show_preset_selector: bool = False,
    preset_select_key: Optional[str] = None,
    extra_left_controls: Optional[Callable[[EventSimulatorContext], None]] = None,
    extra_metrics: Optional[Iterable[tuple[str, int]]] = None,
    discard_mode: str = "container",  # "container" | "titles"
) -> EventSimulatorContext:
    """Render the shared Event Deck Simulator UI.

    This is used by both Event Mode and Encounter Mode's Encounter Events tab.
    """

    deck_state = _ensure_deck_state(settings)
    preset = deck_state.get("preset") or (settings.get("event_deck") or {}).get("preset")

    opts = list_event_deck_options(configs=configs)
    if not preset and opts:
        preset = opts[0]
        initialize_event_deck(preset, configs=configs)
        _sync_deck_to_settings(settings)
        deck_state = st.session_state[DECK_STATE_KEY]

    # Only auto-init if the deck is truly empty (avoid rebuilding mid-run).
    if preset and not (
        deck_state.get("draw_pile")
        or deck_state.get("discard_pile")
        or deck_state.get("current_card")
    ):
        initialize_event_deck(preset, configs=configs)
        _sync_deck_to_settings(settings)
        deck_state = st.session_state[DECK_STATE_KEY]

    if show_preset_selector and opts:
        sel_key = preset_select_key or f"{key_prefix}_preset"
        sel = st.selectbox(
            "Event deck",
            options=opts,
            index=opts.index(preset) if preset in opts else 0,
            key=sel_key,
        )
        if sel != preset:
            initialize_event_deck(sel, configs=configs)
            _sync_deck_to_settings(settings)
            st.rerun()
        preset = sel

    def _refresh() -> EventSimulatorContext:
        ds = st.session_state.get(DECK_STATE_KEY, deck_state)
        return _context_from_state(ds, preset)

    ctx = _refresh()

    if not st.session_state.get("ui_compact", False):
        left, mid, right = st.columns([1, 0.7, 0.85], gap="small")

        with left:
            r1a, r1b = st.columns(2)
            with r1a:
                if st.button("Draw 🃏", width="stretch", key=f"{key_prefix}_draw"):
                    draw_event_card()
                    _sync_deck_to_settings(settings)
            with r1b:
                if st.button(
                    "Reset and Shuffle 🔄",
                    width="stretch",
                    key=f"{key_prefix}_reset",
                ):
                    reset_event_deck(configs=configs, preset=preset)
                    _sync_deck_to_settings(settings)

            ctx = _refresh()

            r2a, r2b = st.columns(2)
            with r2a:
                if st.button(
                    "Current → Top ⬆️",
                    width="stretch",
                    disabled=not ctx.has_current,
                    key=f"{key_prefix}_top",
                ):
                    put_current_on_top()
                    _sync_deck_to_settings(settings)
            with r2b:
                if st.button(
                    "Current → Bottom ⬇️",
                    width="stretch",
                    disabled=not ctx.has_current,
                    key=f"{key_prefix}_bottom",
                ):
                    put_current_on_bottom()
                    _sync_deck_to_settings(settings)

            ctx = _refresh()

            # Extension point (Encounter Mode attaches events here)
            if extra_left_controls:
                extra_left_controls(ctx)

            # Card-specific actions
            if ctx.has_current and (ctx.is_big_pilgrims_key or ctx.is_lost_to_time):
                s1, s2 = st.columns(2)
                with s1:
                    if st.button(
                        "Shuffle into deck 🔀",
                        width="stretch",
                        key=f"{key_prefix}_shuffle_into_deck",
                    ):
                        shuffle_current_into_deck()
                        _sync_deck_to_settings(settings)
                        st.rerun()
                with s2:
                    if ctx.is_lost_to_time:
                        if st.button(
                            "Remove from deck ❌",
                            width="stretch",
                            key=f"{key_prefix}_remove_from_deck",
                        ):
                            remove_card_from_deck()
                            _sync_deck_to_settings(settings)
                            st.rerun()

            draw_n = len(ctx.deck_state.get("draw_pile") or [])
            discard_n = len(ctx.deck_state.get("discard_pile") or [])
            total_n = draw_n + discard_n + (1 if ctx.deck_state.get("current_card") else 0)

            metrics: list[tuple[str, int]] = [("Draw", draw_n), ("Discard", discard_n), ("Total", total_n)]
            if extra_metrics:
                metrics.extend(list(extra_metrics))

            cols = st.columns(len(metrics))
            for col, (label, value) in zip(cols, metrics):
                with col:
                    st.metric(label, value)

        with mid:
            if ctx.current_card:
                img_bytes = get_image_bytes_cached(str(Path(ctx.current_card)))
                if img_bytes:
                    st.image(img_bytes, width=card_width)
                st.caption(ctx.event_name or "—")
            else:
                st.markdown("### Current card")
                st.caption("—")

        with right:
            st.markdown("### Discard")
            if discard_mode == "titles":
                render_discard_titles(ctx.deck_state)
            else:
                render_discard_container(ctx.deck_state)

        return ctx

    # Compact layout
    def _cb_draw() -> None:
        draw_event_card()
        _sync_deck_to_settings(settings)

    def _cb_reset() -> None:
        ds = st.session_state.get(DECK_STATE_KEY) or {}
        preset_now = ds.get("preset") or preset
        reset_event_deck(configs=configs, preset=preset_now)
        _sync_deck_to_settings(settings)

    def _cb_top() -> None:
        put_current_on_top()
        _sync_deck_to_settings(settings)

    def _cb_bottom() -> None:
        put_current_on_bottom()
        _sync_deck_to_settings(settings)

    def _cb_shuffle_into_deck() -> None:
        shuffle_current_into_deck()
        _sync_deck_to_settings(settings)

    def _cb_remove_from_deck() -> None:
        remove_card_from_deck()
        _sync_deck_to_settings(settings)

    st.button("Draw 🃏", width="stretch", key=f"{key_prefix}_draw", on_click=_cb_draw)

    ctx = _refresh()

    if ctx.has_current and (ctx.is_big_pilgrims_key or ctx.is_lost_to_time):
        st.button(
            "Shuffle into deck 🔀",
            width="stretch",
            key=f"{key_prefix}_shuffle_into_deck",
            on_click=_cb_shuffle_into_deck,
        )
        if ctx.is_lost_to_time:
            st.button(
                "Remove from deck ❌",
                width="stretch",
                key=f"{key_prefix}_remove_from_deck",
                on_click=_cb_remove_from_deck,
            )

    # Extension point
    if extra_left_controls:
        extra_left_controls(ctx)

    if ctx.current_card:
        img_bytes = get_image_bytes_cached(str(Path(ctx.current_card)))
        if img_bytes:
            st.image(img_bytes, width=card_width)
        st.caption(ctx.event_name or "—")
    else:
        st.markdown("### Current card")
        st.caption("—")

    st.button(
        "Current → Top ⬆️",
        width="stretch",
        disabled=not ctx.has_current,
        key=f"{key_prefix}_top",
        on_click=_cb_top,
    )
    st.button(
        "Current → Bottom ⬇️",
        width="stretch",
        disabled=not ctx.has_current,
        key=f"{key_prefix}_bottom",
        on_click=_cb_bottom,
    )

    st.button(
        "Reset and Shuffle 🔄",
        width="stretch",
        key=f"{key_prefix}_reset",
        on_click=_cb_reset,
    )

    st.markdown("### Discard")
    if discard_mode == "titles":
        render_discard_titles(ctx.deck_state)
    else:
        render_discard_container(ctx.deck_state)

    return ctx
