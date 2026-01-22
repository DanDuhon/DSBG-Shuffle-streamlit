import random

import streamlit as st

from core.behavior.logic import apply_heatup, _ornstein_smough_heatup_ui
from ui.shared.behavior_session_state import clear_heatup_prompt


def render_heatup_prompt(*, cfg, state) -> None:
    """Render the Boss Mode heat-up confirmation prompt(s), if active.

    Preserves all existing session keys and button keys from ui.boss_mode.render.
    """

    # --- Heat-Up confirmation prompt (Boss Mode) ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and (
            cfg.name == "Vordt of the Boreal Valley" or not state.get("heatup_done", False)
        )
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        st.warning(
            f"The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} "
            f"has entered Heat-Up range!"
        )

        confirm_cols = st.columns(2)
        with confirm_cols[0]:
            if st.button(
                "Confirm Heat-Up 🔥", key="boss_mode_confirm_heatup", width="stretch"
            ):
                rng = random.Random()
                apply_heatup(state, cfg, rng, reason="auto")

                clear_heatup_prompt()
                st.session_state["pending_heatup_prompt"] = False
                st.session_state["pending_heatup_target"] = None
                st.session_state["pending_heatup_type"] = None

                if cfg.name not in {
                    "Old Dragonslayer",
                    "Ornstein & Smough",
                    "Vordt of the Boreal Valley",
                }:
                    st.session_state["heatup_done"] = True
                st.rerun()

        with confirm_cols[1]:
            if st.button("Cancel ❌", key="boss_mode_cancel_heatup", width="stretch"):
                clear_heatup_prompt()
                st.session_state["heatup_done"] = False
                st.rerun()

    elif st.session_state.get("pending_heatup_prompt", False):
        boss = st.session_state.get("pending_heatup_target")

        if boss == "Old Dragonslayer":
            st.warning("Was 4+ damage done in a single attack?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Confirm Heat-Up 🔥", key="boss_mode_ods_confirm", width="stretch"
                ):
                    state["old_dragonslayer_confirmed"] = True
                    clear_heatup_prompt()
                    apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel ❌", key="boss_mode_ods_cancel", width="stretch"):
                    clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()

        elif boss == "Ornstein & Smough":
            st.warning("One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "Confirm Phase Change 🔥",
                    key="boss_mode_ons_confirm",
                    width="stretch",
                ):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel ❌", key="boss_mode_ons_cancel", width="stretch"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()
