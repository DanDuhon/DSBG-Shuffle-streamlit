import json
import random

import streamlit as st

from ui.encounter_mode.generation import generate_encounter_image
from ui.campaign_mode.core import _card_w
from ui.campaign_mode.helpers import get_player_count_from_settings
from ui.encounter_mode.assets import ENCOUNTER_CARDS_DIR


def _party_size_1_to_4() -> int:
    settings = st.session_state.get("user_settings", {})
    character_count = get_player_count_from_settings(settings)
    n = int(character_count)
    return max(1, min(n, 4))


def _candidates_from_alternatives(alts, *, settings: dict) -> list:
    if not alts:
        return []

    if isinstance(alts, list):
        return list(alts)

    if not isinstance(alts, dict):
        return []

    active = set(settings.get("active_expansions", []))
    candidates: list = []

    for exp_combo, combos in alts.items():
        exp_set = {e.strip() for e in str(exp_combo).split(",")} if exp_combo else set()
        if not exp_set or exp_set.issubset(active):
            if isinstance(combos, list):
                candidates.extend(combos)

    return candidates


def _load_json_cached(*, json_path: str, cache_key: str):
    if cache_key not in st.session_state:
        with open(json_path, "r", encoding="utf-8") as f:
            st.session_state[cache_key] = json.load(f)
    return st.session_state[cache_key]


def render_nito_setup_panel() -> None:
    """Render Gravelord Nito Setup encounter card with Shuffle/Original."""

    n = _party_size_1_to_4()
    json_path = f"data/encounters/Tomb of Giants_3_Gravelord Nito Setup_{n}.json"
    encounter_data = _load_json_cached(
        json_path=json_path,
        cache_key=f"nito_setup_data::{n}",
    )

    enemies_key = "nito_setup_enemies"
    mode_key = "nito_setup_mode"

    if enemies_key not in st.session_state:
        st.session_state[enemies_key] = encounter_data.get("original")
        st.session_state[mode_key] = "original"

    col_shuffle, col_original = st.columns(2)

    with col_shuffle:
        if st.button("Shuffle Setup 🔀", key="nito_shuffle", width="stretch"):
            settings = st.session_state.get("user_settings", {})
            alts = encounter_data.get("alternatives")
            candidates = _candidates_from_alternatives(alts, settings=settings)

            if candidates:
                st.session_state[enemies_key] = random.choice(candidates)
                st.session_state[mode_key] = "shuffled"
            else:
                st.session_state[enemies_key] = encounter_data.get("original")
                st.session_state[mode_key] = "original"

    with col_original:
        if st.button("Original Setup 🔁", key="nito_original", width="stretch"):
            st.session_state[enemies_key] = encounter_data.get("original")
            st.session_state[mode_key] = "original"

    enemies = st.session_state[enemies_key]

    card_filename = "Tomb of Giants_Gravelord Nito Setup.jpg"
    card_path = ENCOUNTER_CARDS_DIR / card_filename
    if not card_path.exists():
        raise FileNotFoundError(f"Required encounter card missing: {card_path}")

    card_img = generate_encounter_image(
        "Tomb of Giants",
        3,
        "Gravelord Nito Setup",
        encounter_data,
        enemies,
        use_edited=False,
    )

    st.image(card_img, width=_card_w())


def render_ec_mega_boss_setup_panel() -> None:
    """Render Executioner's Chariot Mega Boss Setup encounter card with Shuffle/Original."""

    n = _party_size_1_to_4()
    json_path = f"data/encounters/Executioner's Chariot_4_Mega Boss Setup_{n}.json"
    encounter_data = _load_json_cached(
        json_path=json_path,
        cache_key=f"ec_mega_setup_data::{n}",
    )

    enemies_key = "ec_mega_setup_enemies"
    mode_key = "ec_mega_setup_mode"

    if enemies_key not in st.session_state:
        st.session_state[enemies_key] = encounter_data.get("original")
        st.session_state[mode_key] = "original"

    col_shuffle, col_original = st.columns(2)

    with col_shuffle:
        if st.button("Shuffle Setup 🔀", key="ec_mega_shuffle", width="stretch"):
            settings = st.session_state.get("user_settings", {})
            alts = encounter_data.get("alternatives")
            candidates = _candidates_from_alternatives(alts, settings=settings)

            if candidates:
                st.session_state[enemies_key] = random.choice(candidates)
                st.session_state[mode_key] = "shuffled"

    with col_original:
        if st.button("Original Setup 🔁", key="ec_mega_original", width="stretch"):
            st.session_state[enemies_key] = encounter_data.get("original")
            st.session_state[mode_key] = "original"

    enemies = st.session_state[enemies_key]

    card_img = generate_encounter_image(
        "Executioner's Chariot",
        4,
        "Mega Boss Setup",
        encounter_data,
        enemies,
        use_edited=False,
    )

    st.image(card_img, width=_card_w())
