import streamlit as st

from core.behavior.assets import CATEGORY_EMOJI
from core.behavior.generation import build_behavior_catalog


def get_or_build_catalog() -> dict:
    # build_behavior_catalog() is cached process-wide and invalidated by
    # behavior-file mtimes, so no session_state copy is needed.
    return build_behavior_catalog()


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

    # Session state drives both widgets below: apply_pending_boss_preselect and
    # Campaign Mode's boss fight tab steer them by writing the keys. Seed the key
    # here rather than also passing `index=`, which Streamlit ignores once the
    # key exists (so the two sources disagree and it warns). Only reseed when the
    # stored value is no longer valid, or a fresh user selection gets clobbered.
    if st.session_state.get("boss_mode_category") not in available_categories:
        st.session_state["boss_mode_category"] = available_categories[0]

    with st.expander("Boss Selector", expanded=True):
        category = st.radio(
            "Type",
            available_categories,
            key="boss_mode_category",
            horizontal=True,
            format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
        )

        entries = catalog.get(category, [])
        if not entries:
            return None

        names = [e.name for e in entries]
        # BehaviorEntry is a dataclass, so this compares by value and stays
        # correct even though the catalog is a fresh cache copy each run.
        if st.session_state.get("boss_mode_choice") not in entries:
            last_choice = st.session_state.get("boss_mode_choice_name")
            st.session_state["boss_mode_choice"] = (
                entries[names.index(last_choice)] if last_choice in names else entries[0]
            )

        entry = st.selectbox(
            "Who are you fighting?",
            entries,
            key="boss_mode_choice",
            format_func=lambda e: e.name,
        )
        st.session_state["boss_mode_choice_name"] = entry.name

    return entry
