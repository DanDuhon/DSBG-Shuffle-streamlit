"""Event Mode entrypoint.

This file stays as a thin orchestrator so other modes can reuse the same panels.
"""

from typing import Any, Dict

import streamlit as st

from ui.event_mode.logic import load_event_configs
from ui.event_mode.logic import list_all_event_cards
from ui.event_mode.event_card_meta import get_event_cards_meta, validate_event_card_meta
from ui.event_mode.panels.builder import render_deck_builder
from ui.event_mode.panels.deck_selector import render_active_event_deck_selector
from ui.event_mode.panels.simulator import render_deck_simulator


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

    tab_builder, tab_sim = st.tabs(["Deck Builder", "Deck Simulator"])

    with tab_builder:
        render_deck_builder(settings=settings, configs=configs)

    with tab_sim:
        render_deck_simulator(
            settings=settings,
            configs=configs,
            key_prefix="event_sim",
            show_preset_selector=False,
            discard_mode="container",
        )
