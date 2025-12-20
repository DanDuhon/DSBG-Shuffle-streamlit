#ui/sidebar.py
import streamlit as st
from core.settings_manager import save_settings
from core.characters import CHARACTER_EXPANSIONS
from ui.ngplus_tab.logic import MAX_NGPLUS_LEVEL, _HP_4_TO_7_BONUS, dodge_bonus_for_level

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

if "sidebar_ngplus_expanded" not in st.session_state:
    st.session_state.sidebar_ngplus_expanded = False


def _ngplus_level_changed():
    st.session_state.sidebar_ngplus_expanded = True


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
    if "sidebar_ngplus_expanded" not in st.session_state:
        st.session_state["sidebar_ngplus_expanded"] = False

    def _ngplus_level_changed():
        st.session_state["sidebar_ngplus_expanded"] = True

    current_ng = int(st.session_state.get("ngplus_level", 0))

    with st.sidebar.expander(
        f"⬆️ New Game+ (Current: NG+{current_ng})",
        expanded=bool(st.session_state.get("sidebar_ngplus_expanded", False)),
    ):
        level = st.number_input(
            "NG+ Level",
            min_value=0,
            max_value=MAX_NGPLUS_LEVEL,
            value=max(0, min(int(current_ng), MAX_NGPLUS_LEVEL)),
            step=1,
            key="ngplus_level",
            on_change=_ngplus_level_changed,
        )

        lvl = int(level)
        if lvl > 0:
            dodge_b = dodge_bonus_for_level(lvl)
            if dodge_b == 1:
                dodge_text = "+1 to dodge difficulty."
            elif dodge_b == 2:
                dodge_text = "+2 to dodge difficulty."

            st.markdown(
                "\n".join(
                    [
                        f"- Base HP 1-3: +{lvl}",
                        f"- Base HP 4-7: +{_HP_4_TO_7_BONUS[lvl]}",
                        f"- Base HP 8-10: +{lvl*2}",
                        f"- Base HP 11+: +{lvl*10}% (rounded up)",
                        f"- +{lvl} damage to all attacks.",
                    ]
                    + ([f"- {dodge_text}"] if dodge_b > 0 else [])
                )
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
        st.caption("This scales the size of boss cards and event cards in Encounter Mode's Event tab.")

    # Sync widget -> persisted settings (mutate IN PLACE, do not replace settings dict)
    settings["ui_card_width"] = int(st.session_state["ui_card_width"])

    # Session-only UI controls (do not persist across devices)
    if "ui_compact" not in st.session_state:
        st.session_state["ui_compact"] = False

    with st.sidebar.expander("📱 UI", expanded=False):
        st.checkbox("Compact layout (mobile)", key="ui_compact")
