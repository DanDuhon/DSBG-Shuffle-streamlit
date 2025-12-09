# app.py
import streamlit as st

import ui.encounters_tab as encounters_tab
import ui.events_tab as events_tab
from ui.encounter_mode import play_tab
from ui.boss_mode.boss_mode_render import render as boss_mode_render
from ui.campaign_mode.campaign_mode_render import render as campaign_mode_render
from ui import sidebar
from core.settings_manager import load_settings, save_settings

st.set_page_config(
    page_title="DSBG-Shuffle",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
    /* Make main background darker and slightly textured-feeling */
    .stApp {
        background: radial-gradient(circle at top, #222 0, #000 60%);
        color: #e0d6b5;
    }

    /* Use a more gothic/serif-like font if available */
    html, body, [class*="css"]  {
        font-family: "Cinzel", "Georgia", serif;
    }

    /* Tabs: look like worn metal with a glowing selected state */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #111 !important;
        border-radius: 0 !important;
        border-bottom: 2px solid #333 !important;
        padding: 0.5rem 1rem !important;
        color: #aaa !important;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stTabs [aria-selected="true"] {
        border-bottom-color: #c28f2c !important;
        color: #f5e9c8 !important;
    }

    /* Sidebar: subtle divider and more compact */
    section[data-testid="stSidebar"] {
        background-color: #050506 !important;
        border-right: 1px solid #333 !important;
    }

    /* Cards (images) subtle frame */
    img {
        border-radius: 4px;
        box-shadow: 0 0 12px rgba(0,0,0,0.7);
    }

    /* Tighter spacing between party/expansion icons */
    .encounter-icons-wrapper {
        display: inline-block;
        font-size: 0;              /* kills gaps from text/&nbsp; between icons */
    }

    .encounter-icons-wrapper img {
        display: inline-block;
        vertical-align: middle;
        margin-right: 0.2rem;      /* adjust to taste */
        margin-bottom: 0.15rem;    /* small vertical breathing room */
    }

    .encounter-icons-wrapper img:last-child {
        margin-right: 0;
    }
    </style>
""", unsafe_allow_html=True)

# --- Initialize Settings ---
if "user_settings" not in st.session_state:
    st.session_state.user_settings = load_settings()

settings = st.session_state.user_settings

# --- Apply pending campaign snapshot (from Campaign Mode) *before* sidebar widgets ---
pending = st.session_state.get("pending_campaign_snapshot")
if pending:
    snap_name = pending.get("name")
    snapshot = pending.get("snapshot", {}) or {}

    snap_version = snapshot.get("rules_version", "V1")
    st.session_state["campaign_rules_version"] = snap_version

    # Restore campaign state dict for correct version
    state_key = "campaign_v1_state" if snap_version == "V1" else "campaign_v2_state"
    st.session_state[state_key] = snapshot.get("state", {}) or {}

    # Restore sidebar-related settings (expansions, party, NG+)
    snap_sidebar = snapshot.get("sidebar_settings", {}) or {}
    changes = []

    snap_exp = snap_sidebar.get("active_expansions")
    if snap_exp is not None and snap_exp != settings.get("active_expansions"):
        settings["active_expansions"] = snap_exp
        # Safe now: widget with this key does not exist yet on this run
        st.session_state["active_expansions"] = snap_exp
        changes.append("expansions")

    snap_chars = snap_sidebar.get("selected_characters")
    if snap_chars is not None and snap_chars != settings.get("selected_characters"):
        settings["selected_characters"] = snap_chars
        st.session_state["selected_characters"] = snap_chars
        changes.append("party")

    snap_ng = snap_sidebar.get("ngplus_level")
    if snap_ng is not None:
        try:
            snap_ng_int = int(snap_ng)
        except Exception:
            snap_ng_int = 0
        current_ng = int(st.session_state.get("ngplus_level", 0))
        if snap_ng_int != current_ng:
            st.session_state["ngplus_level"] = snap_ng_int
            changes.append("NG+ level")

    # Persist updated settings
    st.session_state["user_settings"] = settings
    save_settings(settings)

    # One-shot notice for Campaign Mode UI
    st.session_state["campaign_load_notice"] = {
        "name": snap_name,
        "changes": changes,
    }

    # Clear the pending snapshot flag
    del st.session_state["pending_campaign_snapshot"]

# Sidebar: expansions + party + NG+
sidebar.render_sidebar(settings)
save_settings(settings)

selected_characters = settings.get("selected_characters", [])
character_count = len(selected_characters)
valid_party = 0 < character_count <= 4
st.session_state["player_count"] = character_count


mode = st.sidebar.radio(
    "Mode",
    ["Encounter Mode", "Boss Mode", "Campaign Mode"],
    key="mode",
)

if mode == "Encounter Mode":
    setup, events, play = st.tabs(["Setup", "Events", "Play"])

    with setup:
        encounters_tab.render(settings, valid_party, character_count)

    with events:
        events_tab.render(settings, attach_to_encounter=True)

    with play:
        play_tab.render(settings)
elif mode == "Boss Mode":
    boss_mode_render()
elif mode == "Campaign Mode":
    campaign_mode_render()
