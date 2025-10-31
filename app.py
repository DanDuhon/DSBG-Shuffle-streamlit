import streamlit as st
from ui import sidebar, encounters, events, campaign, variants, behavior_decks
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
tab_encounters, tab_events, tab_campaign, tab_decks, tab_variants = st.tabs(
    ["Encounters", "Events", "Campaign", "Behavior Decks", "Behavior Variants"]
)

with tab_encounters:
    encounters.render(settings, valid_party, character_count)

with tab_events:
    events.render(settings)

with tab_campaign:
    campaign.render(settings)

with tab_decks:
    behavior_decks.render()

with tab_variants:
    variants.render()
