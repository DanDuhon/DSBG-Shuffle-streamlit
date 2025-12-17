#ui/sidebar.py
import streamlit as st
from core.settings_manager import save_settings
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
    "Executioner's Chariot",
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
INVADER_CAP_CLAMP = {1: 2, 2: 3, 3: 5, 4: 4}
CARD_WIDTH_MIN = 240
CARD_WIDTH_MAX = 560
CARD_WIDTH_DEFAULT = 380


def _sync_invader_caps():
    settings = st.session_state.get("user_settings") or {}
    caps = settings.get("max_invaders_per_level")
    if not isinstance(caps, dict):
        caps = {}
    out = {}
    for lvl, mx in INVADER_CAP_CLAMP.items():
        out[str(lvl)] = int(st.session_state.get(f"cap_invaders_lvl_{lvl}", mx))
    settings["max_invaders_per_level"] = out
    st.session_state["user_settings"] = settings
    save_settings(settings)


def render_sidebar(settings: dict):
    st.sidebar.header("Settings")

    caps = settings.get("max_invaders_per_level") or {}

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

    # Invaders
    with st.sidebar.expander("⚔️ Encounter Invader Cap", expanded=False):
        for lvl, mx in INVADER_CAP_CLAMP.items():
            cur = caps.get(str(lvl), mx)
            try:
                cur = int(cur)
            except Exception:
                cur = mx
            cur = max(0, min(cur, mx))
            st.slider(
                f"Level {lvl}",
                min_value=0,
                max_value=mx,
                value=cur,
                key=f"cap_invaders_lvl_{lvl}",
                on_change=_sync_invader_caps,
            )

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

    # One-time init for the widget key (must happen BEFORE st.slider is created)
    if "ui_card_width" not in st.session_state:
        try:
            st.session_state["ui_card_width"] = int(settings.get("ui_card_width", 360))
        except Exception:
            st.session_state["ui_card_width"] = 360

    with st.sidebar.expander("🖼️ Card Display", expanded=False):
        st.slider(
            "Card width (px)",
            min_value=240,
            max_value=560,
            step=10,
            key="ui_card_width",
            value=int(st.session_state["ui_card_width"]),
        )

    # Sync widget -> persisted settings (mutate IN PLACE, do not replace settings dict)
    settings["ui_card_width"] = int(st.session_state["ui_card_width"])

    # Session-only UI controls (do not persist across devices)
    if "ui_compact" not in st.session_state:
        st.session_state["ui_compact"] = False

    with st.sidebar.expander("📱 UI", expanded=False):
        st.checkbox("Compact layout (mobile)", key="ui_compact")
