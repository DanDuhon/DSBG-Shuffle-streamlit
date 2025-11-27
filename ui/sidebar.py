#ui/sidebar.py
import streamlit as st
from core.characters import CHARACTER_EXPANSIONS

all_expansions = [
    "Painted World of Ariamis",
    "The Sunless City",
    "Tomb of Giants",
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep",
    "Characters Expansion",
    "Phantoms",
    "Executioner Chariot",
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
]

def render_sidebar(settings: dict):
    st.sidebar.header("Settings")

    # Expansions
    with st.sidebar.expander("🧩 Expansions", expanded=False):
        active_expansions = st.multiselect(
            "Active Expansions:",
            all_expansions,
            default=settings.get("active_expansions", []),
            key="active_expansions",
        )
        settings["active_expansions"] = active_expansions

    # Characters
    available_characters = sorted(
        c for c, exps in CHARACTER_EXPANSIONS.items()
        if any(exp in active_expansions for exp in exps)
    )

    previous_selection = settings.get("selected_characters", [])
    still_valid = [c for c in previous_selection if c in available_characters]
    if len(still_valid) < len(previous_selection):
        removed = [c for c in previous_selection if c not in still_valid]
        st.sidebar.warning(f"Removed invalid characters: {', '.join(removed)}")
        settings["selected_characters"] = still_valid

    with st.sidebar.expander("🎭 Party", expanded=False):
        selected_characters = st.multiselect(
            "Selected Characters (max 4):",
            options=available_characters,
            default=settings.get("selected_characters", []),
            max_selections=4,
            key="selected_characters",
        )
        settings["selected_characters"] = selected_characters

    # --- New Game+ selection ---
    current_ng = int(st.session_state.get("ngplus_level", 0))

    with st.sidebar.expander(
        f"⬆️ New Game+ (Current: NG+{current_ng})",
        expanded=False,
    ):
        level = st.radio(
            "NG+ Level",
            options=list(range(0, 6)),  # 0–5
            index=current_ng,
            key="ngplus_level",
            format_func=lambda v: "NG+0 (Base)" if v == 0 else f"NG+{v}",
        )
