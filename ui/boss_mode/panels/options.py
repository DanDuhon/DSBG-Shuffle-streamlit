import streamlit as st

from core.behavior.logic import _reset_deck

from ui.boss_mode.executioners_chariot_death_race import (
    EXECUTIONERS_CHARIOT_NAME,
)
from ui.boss_mode.guardian_dragon_fiery_breath import GUARDIAN_DRAGON_NAME
from ui.boss_mode.kalameet_fiery_ruin import BLACK_DRAGON_KALAMEET_NAME
from ui.boss_mode.old_iron_king_blasted_nodes import OLD_IRON_KING_NAME


def render_boss_info_and_options(*, cfg, state) -> None:
    """Render boss info text, boss-specific options, and Reset fight button."""

    if cfg.text:
        with st.expander(f"**{cfg.name}**"):
            st.caption(cfg.text)

    if cfg.name == GUARDIAN_DRAGON_NAME:
        st.checkbox(
            "Use randomized Fiery Breath patterns",
            key="guardian_fiery_generate",
            help=(
                "If checked, Fiery Breath uses a randomized 4-pattern deck. "
                "If unchecked, he uses the printed patterns."
            ),
            value=True,
        )

    if cfg.name == BLACK_DRAGON_KALAMEET_NAME:
        st.checkbox(
            "Use randomized Fiery Ruin patterns",
            key="kalameet_aoe_generate",
            help=(
                "If checked, Fiery Ruin uses a randomized 8-pattern deck. "
                "If unchecked, he uses the printed patterns."
            ),
            value=True,
        )

    if cfg.name == OLD_IRON_KING_NAME:
        st.checkbox(
            "Use randomized Blasted Nodes patterns",
            key="oik_blasted_generate",
            help=(
                "If checked, Blasted Nodes uses a randomized 6-pattern deck. "
                "If unchecked, it uses the printed patterns."
            ),
            value=True,
        )

    if cfg.name == EXECUTIONERS_CHARIOT_NAME:
        st.checkbox(
            "Use randomized Death Race patterns",
            key="ec_death_race_generate",
            help=(
                "If checked, Death Race uses randomized AoE patterns. "
                "If unchecked, it uses the printed Death Race patterns."
            ),
            value=True,
        )

    if st.button("Reset fight 🔄", width="stretch"):
        _reset_deck(state, cfg)

        if cfg.name == GUARDIAN_DRAGON_NAME:
            state.pop("guardian_fiery_sequence", None)
            state.pop("guardian_fiery_index", None)
            state.pop("guardian_fiery_patterns", None)
            state.pop("guardian_fiery_mode", None)

        if cfg.name == BLACK_DRAGON_KALAMEET_NAME:
            state.pop("kalameet_aoe_sequence", None)
            state.pop("kalameet_aoe_index", None)
            state.pop("kalameet_aoe_patterns", None)
            state.pop("kalameet_aoe_mode", None)
            state.pop("kalameet_aoe_current_pattern", None)

        if cfg.name == OLD_IRON_KING_NAME:
            state.pop("oik_blasted_sequence", None)
            state.pop("oik_blasted_index", None)
            state.pop("oik_blasted_patterns", None)
            state.pop("oik_blasted_mode", None)
            state.pop("oik_blasted_current_pattern", None)
            state.pop("oik_blasted_current_mode", None)

        if cfg.name == EXECUTIONERS_CHARIOT_NAME:
            state.pop("ec_death_race_patterns", None)
            state.pop("ec_death_race_sequence", None)
            state.pop("ec_death_race_index", None)
            state.pop("ec_death_race_mode", None)
            state.pop("ec_death_race_current_pattern", None)
            state.pop("ec_death_race_current_mode", None)

        st.rerun()
