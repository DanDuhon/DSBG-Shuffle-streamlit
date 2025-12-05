# ui/boss_mode_tab.py
import random
import streamlit as st

from ui.behavior_decks_tab.assets import (
    BEHAVIOR_CARDS_PATH,
    CARD_BACK,
    CATEGORY_EMOJI,
)
from ui.behavior_decks_tab.logic import (
    _ensure_state,
    _new_state_from_file,
    _load_cfg_for_state,
    _reset_deck,
    _draw_card,
    _manual_heatup,
    apply_heatup,
    _clear_heatup_prompt,
    _ornstein_smough_heatup_ui,
)
from ui.behavior_decks_tab.generation import (
    build_behavior_catalog,
    render_data_card_cached,
    render_dual_boss_data_cards,
    render_behavior_card_cached,
    render_dual_boss_behavior_card,
)
from ui.behavior_decks_tab.render import render_health_tracker


BOSS_MODE_CATEGORIES = ["Mini Bosses", "Main Bosses", "Mega Bosses"]
CARD_DISPLAY_WIDTH = 380


def _get_boss_mode_state_key(entry) -> str:
    return f"boss_mode::{entry.category}::{entry.name}"


def _ensure_boss_state(entry):
    key = _get_boss_mode_state_key(entry)
    state = st.session_state.get(key)
    if not state:
        state, cfg = _new_state_from_file(entry.path)
        st.session_state[key] = state
        # also keep "current" pointers for functions that expect behavior_deck
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    else:
        cfg = _load_cfg_for_state(state)
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    return state, cfg


def render():
    _ensure_state()

    # --- Build or reuse catalog
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]

    # Only categories we care about
    available_cats = [
        c for c in BOSS_MODE_CATEGORIES if catalog.get(c)
    ] or BOSS_MODE_CATEGORIES

    # --- Enemy selector row
    col_sel, col_info = st.columns([2, 1])

    with col_sel:
        default_cat = st.session_state.get("boss_mode_category", available_cats[0])
        if default_cat not in available_cats:
            default_cat = available_cats[0]

        with st.expander("Boss Selector", expanded=True):
            category = st.radio(
                "Type",
                available_cats,
                index=available_cats.index(default_cat),
                key="boss_mode_category",
                horizontal=True,
                format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
            )

            entries = catalog.get(category, [])
            if not entries:
                st.info("No bosses found in this category.")
                return

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

    if not entry:
        st.info("Select a boss to begin.")
        return

    # Ensure we have a state + cfg for this enemy
    state, cfg = _ensure_boss_state(entry)

    with col_info:
        if cfg.text:
            with st.expander(f"**{cfg.name}**"):
                st.caption(cfg.text)

        if st.button("🔄 Reset fight"):
            _reset_deck(state, cfg)
            st.rerun()
            
    # Draw / Heat-up buttons
    c_btns = st.columns([1, 1])
    with c_btns[0]:
        if st.button("Draw next card"):
            _draw_card(state)
    with c_btns[1]:
        if st.button("Manual Heat-Up"):
            _manual_heatup(state)
            
    cfg.entities = render_health_tracker(cfg, state)

    # --- Heat-Up confirmation prompt (Boss Mode) ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and (cfg.name == "Vordt of the Boreal Valley" or not state.get("heatup_done", False))
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        # Generic bosses (and Vordt), first-time heat-up
        st.warning(
            f"⚠️ The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} "
            f"has entered Heat-Up range!"
        )

        confirm_cols = st.columns(2)
        with confirm_cols[0]:
            if st.button("🔥 Confirm Heat-Up", key="boss_mode_confirm_heatup"):
                rng = random.Random()
                apply_heatup(state, cfg, rng, reason="auto")

                _clear_heatup_prompt()
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
            if st.button("Cancel", key="boss_mode_cancel_heatup"):
                _clear_heatup_prompt()
                st.session_state["heatup_done"] = False
                st.rerun()

    elif st.session_state.get("pending_heatup_prompt", False):
        # Boss-specific special cases
        boss = st.session_state.get("pending_heatup_target")

        # --- Old Dragonslayer: require 4+ damage confirmation ---
        if boss == "Old Dragonslayer":
            st.warning("Was 4+ damage done in a single attack?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Heat-Up", key="boss_mode_ods_confirm"):
                    state["old_dragonslayer_confirmed"] = True
                    _clear_heatup_prompt()
                    apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel", key="boss_mode_ods_cancel"):
                    _clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()

        # --- Ornstein & Smough: death/phase change confirmation ---
        elif boss == "Ornstein & Smough":
            st.warning("⚔️ One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Phase Change", key="boss_mode_ons_confirm"):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel", key="boss_mode_ons_cancel"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()

    # --- Main fight view
    col_left, col_right = st.columns([1, 1])

    # LEFT: Data Card
    with col_left:
        if cfg.name == "Executioner Chariot":
            # you can keep the existing pre/post-heatup swap logic if you like
            # or just always show the main data card
            img = render_data_card_cached(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg",
                cfg.raw,
                is_boss=True,
            )
            st.image(img, width=CARD_DISPLAY_WIDTH)

        elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
            o_img, s_img = render_dual_boss_data_cards(cfg.raw)
            o_col, s_col = st.columns(2)
            with o_col:
                st.image(o_img, width=CARD_DISPLAY_WIDTH)
            with s_col:
                st.image(s_img, width=CARD_DISPLAY_WIDTH)
        else:
            # first display card is always the data card
            data_path = cfg.display_cards[0] if cfg.display_cards else None
            if data_path:
                img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
                st.image(img, width=CARD_DISPLAY_WIDTH)

        st.markdown("---")

    # RIGHT: Deck + current card
    with col_right:
        # Current card image
        current = state.get("current_card")
        if not current:
            st.image(CARD_BACK, width=CARD_DISPLAY_WIDTH)
        else:
            if cfg.name == "Ornstein & Smough":
                img = render_dual_boss_behavior_card(cfg.raw, current, state)
            else:
                base_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - {current}.jpg"
                img = render_behavior_card_cached(
                    base_path,
                    cfg.behaviors[current],
                    is_boss=True,
                )
            st.image(img, width=CARD_DISPLAY_WIDTH)

        # Deck status summary
        st.markdown("---")
        st.caption(
            f"Draw pile: {len(state.get('draw_pile', []))} cards"
            f" • Discard: {len(state.get('discard_pile', []))} cards"
        )

    # --- Heat-Up confirmation (reuse existing logic)
    # If you like, you can literally factor the block from behavior_decks_tab.render
    # into a helper and call it here so the behavior is identical.
