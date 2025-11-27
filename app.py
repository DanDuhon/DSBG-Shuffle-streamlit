import streamlit as st
import ui.campaign_tab as campaign_tab
import ui.encounters_tab as encounters_tab
import ui.events_tab as events_tab
import ui.behavior_decks_tab as behavior_decks_tab
import ui.encounter_play_tab as encounter_play_tab
from ui.ngplus_tab.render import render as ngplus_render
from ui import sidebar
from core.settings_manager import load_settings, save_settings

st.set_page_config(page_title="DSBG-Shuffle", layout="wide", initial_sidebar_state="expanded")

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

# --- Mode selection (in sidebar) ---
st.sidebar.markdown("# Mode")
mode = st.sidebar.radio(
    "Select Mode",
    ["Encounters", "Campaign", "Deck Tools", "New Game+"],
    index=0,
)

st.sidebar.markdown("---")

# Sidebar (expansions + party)
sidebar.render_sidebar(settings)
save_settings(settings)

# Validation
selected_characters = settings.get("selected_characters", [])
character_count = len(selected_characters)
valid_party = 0 < character_count <= 4
st.session_state["player_count"] = character_count

# --- Main content area ---
if mode == "Encounters":
    setup_tab, events_tab_ui, play_tab = st.tabs(["Setup", "Events", "Play"])

    with setup_tab:
        encounters_tab.render(settings, valid_party, character_count)

    with events_tab_ui:
        # Event deck UI that can attach cards to the current encounter
        events_tab.render(settings, attach_to_encounter=True)

    with play_tab:
        # New Encounter Play assistant
        encounter_play_tab.render(settings)

elif mode == "Campaign":
    # Campaign generator/tracker
    campaign_tab.render()

elif mode == "Deck Tools":
    # Inner tabs for Event + Behavior deck simulations
    tools_events_tab, tools_behavior_tab = st.tabs(["Event Decks", "Behavior Decks"])

    with tools_events_tab:
        events_tab.render(settings, attach_to_encounter=False)

    with tools_behavior_tab:
        behavior_decks_tab.render()

elif mode == "New Game+":
    # NG+ options and card viewer
    ngplus_render()
