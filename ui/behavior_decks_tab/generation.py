import streamlit as st
from PIL import Image
from ui.behavior_decks_tab.assets import get_behavior_card_path, dim_greyscale


def _render_behavior_card(name: str) -> Image.Image:
    path = get_behavior_card_path(name)
    img = Image.open(path).convert("RGBA")
    return img


@st.cache_data(show_spinner=False)
def render_behavior_card_cached(name: str):
    return _render_behavior_card(name)


@st.cache_data(show_spinner=False)
def render_dimmed_behavior_card_cached(name: str):
    img = _render_behavior_card(name)
    return dim_greyscale(img)
