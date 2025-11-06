import streamlit as st
from pathlib import Path
from PIL import Image

CAMPAIGNS_FILE = Path("data/saved_campaigns.json")
BOSSES_FILE = Path("data/bosses.json")
BOSSES_IMAGES = Path("assets/boss cards")
BONFIRE_IMAGE = Path("assets/bonfire.gif")
PARTY_TOKEN = Path("assets/party_token.png")
SOULS_TOKEN = Path("assets/souls_token.png")
EVENTS_SHORTCUTS_FILE = Path("data/encounters_events_shortcuts.json")
V2_STRUCTURE = {
    "mini boss":  [1, 1, 1, 2],
    "main boss":  [2, 2, 3, 3],
    "mega boss":  [4],
}


@st.cache_data(show_spinner=False)
def get_asset_image(obj):
    """Return a displayable image object for Streamlit (preserving GIF animation)."""
    # Already a PIL image → return it as-is
    if isinstance(obj, Image.Image):
        return obj

    # Path or string → decide how to load
    if isinstance(obj, (str, Path)):
        path = str(obj)
        if path.lower().endswith(".gif"):
            # Return raw bytes so Streamlit keeps animation
            with open(path, "rb") as f:
                return f.read()
        else:
            # Static image → open normally
            return Image.open(path)

    raise TypeError(f"Unsupported image type: {type(obj)}")
