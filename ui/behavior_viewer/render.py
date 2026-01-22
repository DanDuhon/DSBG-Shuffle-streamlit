import streamlit as st
from core.behavior.generation import (
    build_behavior_catalog,
)
from core.behavior.logic import load_behavior
from ui.behavior_viewer.labels import build_picker_model
from ui.behavior_viewer.panels.card_display import render_card_display
from ui.behavior_viewer.panels.card_picker import render_card_picker
from ui.behavior_viewer.panels.selector import render_selector


def render():
    # Build catalog once per session
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]
    category, entry = render_selector(catalog=catalog)
    if not category or not entry:
        return

    # Load the behavior config
    cfg = load_behavior(entry.path)

    model = build_picker_model(category=category, entry=entry, cfg=cfg)

    left_col, right_col = st.columns([1, 2])

    # Card display width (from settings)
    user_settings = st.session_state.get("user_settings") or {}
    card_w = int(user_settings.get("ui_card_width", st.session_state.get("ui_card_width", 360)))
    card_w = max(240, min(560, card_w))

    # Respect compact UI setting: dropdown in compact mode, radio otherwise.
    compact = bool(st.session_state.get("ui_compact", False))

    choice = render_card_picker(
        model=model,
        compact=compact,
        left_col=left_col,
        priscilla_entry_name=entry.name,
    )

    with right_col:
        render_card_display(
            entry=entry,
            cfg=cfg,
            model=model,
            compact=compact,
            choice=choice,
            card_width=card_w,
        )
