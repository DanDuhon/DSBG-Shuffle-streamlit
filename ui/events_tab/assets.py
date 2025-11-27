#ui/events_tab/assets.py
import streamlit as st
from pathlib import Path
import base64

# Static asset locations and presets
DECK_BACK_PATH = Path("assets/events/deck_back.png")

PRESETS = [
    "Mixed V2",
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City",
]

@st.cache_resource(show_spinner=False)
def img_to_base64(path: str) -> str:
    """Convert image to base64 for inline rendering."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")
