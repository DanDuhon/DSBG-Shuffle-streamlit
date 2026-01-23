import streamlit as st

from ui.boss_mode.state import boss_draw_current, boss_manual_heatup_current


def render_combat_controls(*, where: str) -> None:
    """Render Boss Mode combat controls (draw + manual heat-up)."""

    st.button(
        "Draw next card 🃏",
        key=f"boss_mode_draw_{where}",
        width="stretch",
        on_click=boss_draw_current,
    )
    st.button(
        "Manual Heat-Up 🔥",
        key=f"boss_mode_heatup_{where}",
        width="stretch",
        on_click=boss_manual_heatup_current,
    )
