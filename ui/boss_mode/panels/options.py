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
            # persist_state: this checkbox stops rendering whenever the user
            # switches to another boss, which drops the key -- so an unchecked
            # preference silently flipped back to True on every boss switch.
            key="guardian_fiery_generate",
            persist_state="session",
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
            persist_state="session",
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
            persist_state="session",
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
            persist_state="session",
            help=(
                "If checked, Death Race uses randomized AoE patterns. "
                "If unchecked, it uses the printed Death Race patterns."
            ),
            value=True,
        )

    if st.button("Reset fight 🔄", width="stretch"):
        _reset_deck(state, cfg)

        # Each AoE boss stores the same six per-fight keys under its own prefix.
        # These were spelled out per boss and had drifted — Guardian kept its
        # `current_pattern`/`current_mode` and Kalameet kept its `current_mode`,
        # so the first card drawn after a reset could render the previous
        # fight's pattern.
        aoe_prefixes = {
            GUARDIAN_DRAGON_NAME: "guardian_fiery",
            BLACK_DRAGON_KALAMEET_NAME: "kalameet_aoe",
            OLD_IRON_KING_NAME: "oik_blasted",
            EXECUTIONERS_CHARIOT_NAME: "ec_death_race",
        }
        prefix = aoe_prefixes.get(cfg.name)
        if prefix:
            for suffix in (
                "sequence",
                "index",
                "patterns",
                "mode",
                "current_pattern",
                "current_mode",
            ):
                state.pop(f"{prefix}_{suffix}", None)

        # The stale-draw guards key off this; leaving it set meant the first
        # draw after a reset was not treated as a new draw.
        st.session_state.pop(f"boss_mode_last_draw::{cfg.name}", None)
        st.session_state.pop(f"boss_mode_last_current::{cfg.name}", None)

        st.rerun()
