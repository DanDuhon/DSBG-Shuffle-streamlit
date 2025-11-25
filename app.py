import streamlit as st
import ui.campaign_tab as campaign_tab
import ui.encounters_tab as encounters_tab
import ui.events_tab as events_tab
import ui.behavior_decks_tab as behavior_decks_tab
import ui.ngplus_tab as ngplus_tab
from ui import sidebar
from core.settings_manager import load_settings, save_settings

st.set_page_config(page_title="DSBG-Shuffle", layout="centered")

# --- Initialize Settings ---
if "user_settings" not in st.session_state:
    st.session_state.user_settings = load_settings()

settings = st.session_state.user_settings

# Sidebar (expansions + party)
sidebar.render_sidebar(settings)
save_settings(settings)

# Validation
selected_characters = settings.get("selected_characters", [])
character_count = len(selected_characters)
valid_party = 0 < character_count <= 4

# Tabs
tab_encounters, tab_events, tab_campaign, tab_decks, tab_ngplus = st.tabs(
    ["Encounters", "Events", "Campaign", "Behavior Decks", "New Game+"]
)

with tab_encounters:
    encounters_tab.render(settings, valid_party, character_count)

with tab_events:
    events_tab.render(settings)

with tab_campaign:
    campaign_tab.render()

with tab_decks:
    behavior_decks_tab.render()

with tab_ngplus:
    ngplus_tab.render()
