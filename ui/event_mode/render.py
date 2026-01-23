"""Event Mode entrypoint.

This file stays as a thin orchestrator so other modes can reuse the same panels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from core.image_cache import get_image_bytes_cached
from ui.event_mode.event_card_meta import get_event_cards_meta, validate_event_card_meta
from ui.event_mode.logic import list_all_event_cards, load_event_configs
from ui.event_mode.panels.builder import render_deck_builder
from ui.event_mode.panels.deck_selector import render_active_event_deck_selector


def render(settings: Dict[str, Any]) -> None:
    configs = load_event_configs()

    # Lightweight data validation: helps catch missing metadata when new cards are added.
    meta_cards = get_event_cards_meta()
    known_ids = [c.get("id") for c in list_all_event_cards(configs=configs) if c.get("id")]
    meta_warnings = validate_event_card_meta(cards=meta_cards, known_card_ids=known_ids)
    if meta_warnings:
        with st.expander(f"Event metadata warnings ({len(meta_warnings)})", expanded=False):
            st.warning("\n".join([f"- {w}" for w in meta_warnings]))

    render_active_event_deck_selector(
        settings=settings,
        configs=configs,
        label="Active event deck",
        key="active_event_deck",
        rerun_on_change=False,
    )

    tab_builder, tab_viewer = st.tabs(["Deck Builder", "Card Viewer"])

    with tab_builder:
        render_deck_builder(settings=settings, configs=configs)

    with tab_viewer:
        cards = list_all_event_cards(configs=configs)
        if not cards:
            st.info("No event cards found.")
            return

        # Card display width (from settings)
        user_settings = st.session_state.get("user_settings") or {}
        card_w = int(user_settings.get("ui_card_width", st.session_state.get("ui_card_width", 360)))
        card_w = max(240, min(560, card_w))

        # Build stable, human-friendly labels.
        labels: list[str] = []
        label_to_card: dict[str, dict] = {}
        label_counts: dict[str, int] = {}

        for c in cards:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue

            # Prefer a simple title-ish display, but keep it predictable.
            display = cid.replace("_", " ").strip()
            if display and display.lower() == display:
                display = display.title()

            # Ensure uniqueness if two cards end up with the same label.
            n = label_counts.get(display, 0) + 1
            label_counts[display] = n
            label = display if n == 1 else f"{display} ({n})"

            labels.append(label)
            label_to_card[label] = c

        if not labels:
            st.info("No event cards found.")
            return

        compact = bool(st.session_state.get("ui_compact", False))
        picker_key = "event_card_viewer_choice"

        left, right = st.columns([1, 2], gap="medium")
        with left:
            if compact:
                choice = st.selectbox(
                    "Event card",
                    options=labels,
                    key=picker_key,
                )
            else:
                choice = st.radio(
                    "Event card",
                    options=labels,
                    key=picker_key,
                )

        with right:
            card = label_to_card.get(choice) or {}
            img_path = card.get("image_path")
            if not isinstance(img_path, str) or not img_path:
                st.error("Event card image path is missing.")
                return

            img_bytes = get_image_bytes_cached(str(Path(img_path)))
            if not img_bytes:
                st.error(f"Unable to load image: {img_path}")
                return

            st.image(img_bytes, width=card_w)

            expansion = card.get("expansion")
            if isinstance(expansion, str) and expansion.strip():
                st.caption(f"Found in: {expansion}")
            else:
                st.caption("Found in: (unknown)")
