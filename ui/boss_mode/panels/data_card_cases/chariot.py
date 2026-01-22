import streamlit as st

from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.behavior.generation import render_data_card_cached
from ui.boss_mode.executioners_chariot_death_race import EXECUTIONERS_CHARIOT_NAME
from ui.boss_mode.panels.encounter_setups import render_ec_mega_boss_setup_panel
from ui.campaign_mode.core import _card_w


def try_render_chariot_data_card(*, cfg, state) -> bool:
    if cfg.name != EXECUTIONERS_CHARIOT_NAME:
        return False

    data_col, setup_col = st.columns([1, 1])

    with data_col:
        if not st.session_state.get("chariot_heatup_done", False):
            img = render_data_card_cached(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner's Chariot.jpg",
                cfg.raw,
                is_boss=True,
                no_edits=True,
            )
        else:
            img = render_data_card_cached(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                cfg.raw,
                is_boss=True,
            )

        st.image(img, width=_card_w())

    if not st.session_state.get("chariot_heatup_done", False):
        with setup_col:
            render_ec_mega_boss_setup_panel()

    return True
