import streamlit as st

from core.behavior.assets import CATEGORY_EMOJI
from core.behavior.generation import build_behavior_catalog


def get_or_build_catalog() -> dict:
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    return st.session_state["behavior_catalog"]


def apply_pending_boss_preselect(catalog: dict) -> None:
    """If Campaign Mode requested a specific boss, preselect it once."""
    pending_name = st.session_state.pop("boss_mode_pending_name", None)
    if not pending_name:
        return

    target_cat = None
    for cat, entries in catalog.items():
        for entry in entries:
            if getattr(entry, "name", None) == pending_name:
                target_cat = cat
                break
        if target_cat:
            break

    if target_cat:
        st.session_state["boss_mode_category"] = target_cat
        st.session_state["boss_mode_choice_name"] = pending_name


def get_available_categories(*, catalog: dict, boss_mode_categories: list[str]) -> list[str]:
    return [c for c in boss_mode_categories if catalog.get(c)] or list(boss_mode_categories)


def render_boss_selector(*, catalog: dict, available_categories: list[str]):
    """Render the boss selector expander and return the selected entry (or None)."""

    default_cat = st.session_state.get("boss_mode_category", available_categories[0])
    if default_cat not in available_categories:
        default_cat = available_categories[0]

    with st.expander("Boss Selector", expanded=True):
        category = st.radio(
            "Type",
            available_categories,
            index=available_categories.index(default_cat),
            key="boss_mode_category",
            horizontal=True,
            format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
        )

        entries = catalog.get(category, [])
        if not entries:
            return None

        names = [e.name for e in entries]
        last_choice = st.session_state.get("boss_mode_choice_name")
        idx = names.index(last_choice) if last_choice in names else 0

        entry = st.selectbox(
            "Who are you fighting?",
            entries,
            index=idx,
            key="boss_mode_choice",
            format_func=lambda e: e.name,
        )
        st.session_state["boss_mode_choice_name"] = entry.name

    return entry
