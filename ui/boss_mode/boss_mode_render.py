# ui/boss_mode_tab.py
import random
import json
import streamlit as st
from core.image_cache import get_image_data_uri_cached, bytes_to_data_uri
from pathlib import Path

from ui.encounter_mode.generation import generate_encounter_image
from ui.campaign_mode.helpers import get_player_count_from_settings
from core.ngplus import get_current_ngplus_level
from core.behavior.assets import (
    BEHAVIOR_CARDS_PATH,
    CARD_BACK,
    CATEGORY_EMOJI,
    _behavior_image_path,
)
from core.behavior.logic import (
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
from core.behavior.generation import (
    build_behavior_catalog,
    render_data_card_cached,
    render_dual_boss_data_cards,
    render_behavior_card_cached,
    render_dual_boss_behavior_card,
)
from core.behavior.priscilla_overlay import overlay_priscilla_arcs
from core.behavior.render import render_health_tracker
from ui.boss_mode.guardian_dragon_fiery_breath import (
    GUARDIAN_DRAGON_NAME,
    GUARDIAN_CAGE_PREFIX,
    _guardian_fiery_next_pattern,
    _guardian_render_fiery_breath,
)
from ui.boss_mode.kalameet_fiery_ruin import (
    BLACK_DRAGON_KALAMEET_NAME,
    KALAMEET_HELLFIRE_PREFIX,
    _kalameet_next_pattern,
    _kalameet_render_fiery_ruin,
)
from ui.boss_mode.old_iron_king_blasted_nodes import (
    OLD_IRON_KING_NAME,
    OIK_FIRE_BEAM_PREFIX,
    _oik_blasted_next_pattern,
    _oik_render_blasted_nodes,
)
from ui.boss_mode.executioners_chariot_death_race import (
    EXECUTIONERS_CHARIOT_NAME,
    DEATH_RACE_BEHAVIOR_NAME,
    _ec_death_race_next_pattern,
    _ec_render_death_race_aoe,
)


BOSS_MODE_CATEGORIES = ["Mini Bosses", "Main Bosses", "Mega Bosses"]


def _card_w() -> int:
    s = st.session_state.get("user_settings") or {}
    w = int(s.get("ui_card_width", 360))
    return max(240, min(560, w))


def _get_boss_mode_state_key(entry) -> str:
    return f"boss_mode::{entry.category}::{entry.name}"


def _ensure_boss_state(entry):
    key = _get_boss_mode_state_key(entry)
    current_ng = int(get_current_ngplus_level() or 0)
    state = st.session_state.get(key)
    if not state:
        state, cfg = _new_state_from_file(entry.path)
        state["ngplus_level"] = current_ng
        # Ensure Priscilla starts invisible in boss mode state as well
        if cfg.name == "Crossbreed Priscilla":
            state["priscilla_invisible"] = True
        st.session_state[key] = state
        # also keep "current" pointers for functions that expect behavior_deck
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    else:
        cached_ng = int(state.get("ngplus_level", -1))
        if cached_ng != current_ng:
            # NG+ changed since this boss was loaded: rebuild from disk so cfg.raw/cfg.behaviors re-apply NG+
            state, cfg = _new_state_from_file(entry.path)
            state["ngplus_level"] = current_ng
            st.session_state[key] = state
        else:
            cfg = _load_cfg_for_state(state)
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    return state, cfg


def _boss_draw_current() -> None:
    entry = st.session_state.get("boss_mode_choice")
    if not entry:
        return
    state, _cfg = _ensure_boss_state(entry)

    st.session_state["boss_mode_draw_token"] = (
        st.session_state.get("boss_mode_draw_token", 0) + 1
    )
    _draw_card(state)


def _boss_manual_heatup_current() -> None:
    entry = st.session_state.get("boss_mode_choice")
    if not entry:
        return
    state, _cfg = _ensure_boss_state(entry)
    _manual_heatup(state)


def _render_combat_controls(*, where: str) -> None:
    st.button(
        "Draw next card",
        key=f"boss_mode_draw_{where}",
        width="stretch",
        on_click=_boss_draw_current,
    )
    st.button(
        "Manual Heat-Up",
        key=f"boss_mode_heatup_{where}",
        width="stretch",
        on_click=_boss_manual_heatup_current,
    )


def render():
    def _load_ec_mega_boss_setup_data():
        """
        Load the Executioner's Chariot Mega Boss Setup encounter JSON for the
        current party size (1–4 characters).
        """
        # Try to use the same info app.py uses:
        #   - settings["selected_characters"]
        #   - st.session_state["player_count"]
        settings = st.session_state.get("user_settings", {})
        character_count = get_player_count_from_settings(settings)

        n = int(character_count)

        # Mega boss setup only defines 1–4 character variants.
        n = max(1, min(n, 4))

        # NOTE: this matches what you described:
        #   /data/encounters/Executioner's Chariot_4_Mega Boss Setup_1.json
        # Drop the leading slash for a project-relative path.
        json_path = f"data/encounters/Executioner's Chariot_4_Mega Boss Setup_{n}.json"

        # Cache per party size so changing the party will reload the right file.
        cache_key = f"ec_mega_setup_data::{n}"
        if cache_key not in st.session_state:
            with open(json_path, "r", encoding="utf-8") as f:
                st.session_state[cache_key] = json.load(f)

        return st.session_state[cache_key]

    def _render_ec_mega_boss_setup_panel():
        """
        Show the Executioner's Chariot Mega Boss Setup encounter card
        with Shuffle / Original buttons, matching Encounter Mode behavior.
        """
        encounter_data = _load_ec_mega_boss_setup_data()

        # Session keys to remember which enemy combination we're showing
        enemies_key = "ec_mega_setup_enemies"
        mode_key = "ec_mega_setup_mode"

        # Default to the printed/original setup
        if enemies_key not in st.session_state:
            st.session_state[enemies_key] = encounter_data["original"]
            st.session_state[mode_key] = "original"

        # Controls: Shuffle / Original
        col_shuffle, col_original = st.columns(2)
        with col_shuffle:
            if st.button("Shuffle Setup", key="ec_mega_shuffle", width="stretch"):
                # Pick a random alternative combo.
                alts = encounter_data.get("alternatives") or {}
                candidates = []

                if isinstance(alts, dict):
                    # Keys are comma-separated expansion names; values are lists of enemy ID lists.
                    settings = st.session_state.get("user_settings", {})
                    active = set(settings.get("active_expansions", []))

                    for exp_combo, combos in alts.items():
                        exp_set = (
                            {e.strip() for e in exp_combo.split(",")}
                            if exp_combo
                            else set()
                        )
                        # Only use combos that are compatible with the currently active expansions.
                        if not exp_set or exp_set.issubset(active):
                            candidates.extend(combos)
                elif isinstance(alts, list):
                    # Fallback in case this file ever uses a simple list of combos
                    candidates = alts

                if candidates:
                    st.session_state[enemies_key] = random.choice(candidates)
                    st.session_state[mode_key] = "shuffled"
        with col_original:
            if st.button("Original Setup", key="ec_mega_original", width="stretch"):
                st.session_state[enemies_key] = encounter_data["original"]
                st.session_state[mode_key] = "original"

        enemies = st.session_state[enemies_key]

        # Generate the encounter card image just like Encounter Mode does
        card_img = generate_encounter_image(
            "Executioner's Chariot",
            4,
            "Mega Boss Setup",
            encounter_data,
            enemies,
            use_edited=False,
        )

        w = _card_w()

        src = bytes_to_data_uri(card_img, mime="image/png")

        st.markdown(
            f"""
            <div class="card-image">
                <img src="{src}" style="width:{w}px">
            </div>
            """,
            unsafe_allow_html=True,
        )

    _ensure_state()

    # --- Build or reuse catalog
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]

    # If Campaign Mode requested a specific boss, preselect it once.
    pending_name = st.session_state.pop("boss_mode_pending_name", None)
    if pending_name:
        target_cat = None
        for cat, entries in catalog.items():
            for e in entries:
                if getattr(e, "name", None) == pending_name:
                    target_cat = cat
                    break
            if target_cat:
                break
        if target_cat:
            st.session_state["boss_mode_category"] = target_cat
            st.session_state["boss_mode_choice_name"] = pending_name

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

        # Guardian Dragon: option to control Fiery Breath node patterns
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

        # Kalameet: option to control Fiery Ruin node patterns
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

        # Old Iron King: option to control Blasted Nodes patterns
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

        # Executioner's Chariot: option to control Death Race AoE patterns
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

        if st.button("🔄 Reset fight", width="stretch"):
            _reset_deck(state, cfg)
            if cfg.name == GUARDIAN_DRAGON_NAME:
                # Clear Fiery Breath state when resetting the fight
                state.pop("guardian_fiery_sequence", None)
                state.pop("guardian_fiery_index", None)
                state.pop("guardian_fiery_patterns", None)
                state.pop("guardian_fiery_mode", None)
            if cfg.name == BLACK_DRAGON_KALAMEET_NAME:
                # Clear Fiery Ruin state when resetting the fight
                state.pop("kalameet_aoe_sequence", None)
                state.pop("kalameet_aoe_index", None)
                state.pop("kalameet_aoe_patterns", None)
                state.pop("kalameet_aoe_mode", None)
                state.pop("kalameet_aoe_current_pattern", None)
            if cfg.name == OLD_IRON_KING_NAME:
                # Clear Blasted Nodes state when resetting the fight
                state.pop("oik_blasted_sequence", None)
                state.pop("oik_blasted_index", None)
                state.pop("oik_blasted_patterns", None)
                state.pop("oik_blasted_mode", None)
                state.pop("oik_blasted_current_pattern", None)
                state.pop("oik_blasted_current_mode", None)
            if cfg.name == EXECUTIONERS_CHARIOT_NAME:
                # Clear Death Race AoE state when resetting the fight
                state.pop("ec_death_race_patterns", None)
                state.pop("ec_death_race_sequence", None)
                state.pop("ec_death_race_index", None)
                state.pop("ec_death_race_mode", None)
                state.pop("ec_death_race_current_pattern", None)
                state.pop("ec_death_race_current_mode", None)
            st.rerun()

    # Draw / Heat-up buttons
    if not st.session_state.get("ui_compact", False):
        c_hp_btns = st.columns([1, 1])
        with c_hp_btns[0]:
            cfg.entities = render_health_tracker(cfg, state)
        with c_hp_btns[1]:
            _render_combat_controls(where="top")

    # --- Heat-Up confirmation prompt (Boss Mode) ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and (
            cfg.name == "Vordt of the Boreal Valley"
            or not state.get("heatup_done", False)
        )
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        # Generic bosses (and Vordt), first-time heat-up
        st.warning(
            f"⚠️ The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} "
            f"has entered Heat-Up range!"
        )

        confirm_cols = st.columns(2)
        with confirm_cols[0]:
            if st.button(
                "🔥 Confirm Heat-Up", key="boss_mode_confirm_heatup", width="stretch"
            ):
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
            if st.button("Cancel", key="boss_mode_cancel_heatup", width="stretch"):
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
                if st.button(
                    "🔥 Confirm Heat-Up", key="boss_mode_ods_confirm", width="stretch"
                ):
                    state["old_dragonslayer_confirmed"] = True
                    _clear_heatup_prompt()
                    apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel", key="boss_mode_ods_cancel", width="stretch"):
                    _clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()

        # --- Ornstein & Smough: death/phase change confirmation ---
        elif boss == "Ornstein & Smough":
            st.warning("⚔️ One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "🔥 Confirm Phase Change",
                    key="boss_mode_ons_confirm",
                    width="stretch",
                ):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel", key="boss_mode_ons_cancel", width="stretch"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()

    # --- Main fight view
    col_left, col_right = st.columns([1, 1])

    # LEFT: Data Card
    with col_left:
        if cfg.name == EXECUTIONERS_CHARIOT_NAME:
            # Two columns: data card | Mega Boss Setup (pre-heatup only)
            data_col, setup_col = st.columns([1, 1])

            with data_col:
                # Phase 1: show the Chariot card
                # Phase 2 (after heat-up): show the Skeletal Horse card
                if not st.session_state.get("chariot_heatup_done", False):
                    img = render_data_card_cached(
                        BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner's Chariot.jpg",
                        cfg.raw,
                        is_boss=True,
                        no_edits=True,  # matches Behavior Decks tab behavior
                    )
                else:
                    img = render_data_card_cached(
                        BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                        cfg.raw,
                        is_boss=True,
                    )

                w = _card_w()

                src = bytes_to_data_uri(img, mime="image/png")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:{w}px">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Before heat-up, show the Mega Boss Setup encounter + buttons
            if not st.session_state.get("chariot_heatup_done", False):
                with setup_col:
                    _render_ec_mega_boss_setup_panel()

        elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
            o_img, s_img = render_dual_boss_data_cards(cfg.raw)

            ornstein_dead = st.session_state.get("ornstein_dead", False)
            smough_dead = st.session_state.get("smough_dead", False)

            # If one is dead (phase 2), show only the survivor's data card
            if ornstein_dead and not smough_dead:
                # Smough survives
                w = _card_w()

                src = bytes_to_data_uri(s_img, mime="image/png")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:{w}px">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif smough_dead and not ornstein_dead:
                # Ornstein survives
                w = _card_w()

                src = bytes_to_data_uri(o_img, mime="image/png")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:{w}px">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                # Phase 1 (both alive): show both
                o_col, s_col = st.columns(2)
                with o_col:
                    w = _card_w()

                    src = bytes_to_data_uri(o_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with s_col:
                    w = _card_w()

                    src = bytes_to_data_uri(s_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        # Special case for Vordt's Frostbreath
        elif cfg.name == "Vordt of the Boreal Valley":
            data_path = cfg.display_cards[0] if cfg.display_cards else None
            if data_path:
                data_img = render_data_card_cached(data_path, cfg.raw, is_boss=True)

                if state.get("vordt_frostbreath_active", False):
                    # Find the Frostbreath behavior key (handles "Frostbreath", "Frost Breath", etc.)
                    frost_key = None
                    for key in cfg.behaviors.keys():
                        name_lower = key.lower()
                        if "frost" in name_lower and "breath" in name_lower:
                            frost_key = key
                            break

                    if frost_key:
                        frost_path = _behavior_image_path(cfg, frost_key)
                        frost_img = render_behavior_card_cached(
                            frost_path,
                            cfg.behaviors[frost_key],
                            is_boss=True,
                        )
                        # Show data card + Frostbreath side-by-side
                        c1, c2 = st.columns(2)
                        with c1:
                            w = _card_w()

                            src = bytes_to_data_uri(data_img, mime="image/png")

                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{src}" style="width:{w}px">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with c2:
                            w = _card_w()

                            # If Priscilla is invisible, overlay arcs onto the behavior card
                            if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                                frost_img = overlay_priscilla_arcs(frost_img, frost_key, cfg.behaviors.get(frost_key, {}))
                            src = bytes_to_data_uri(frost_img, mime="image/png")

                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{src}" style="width:{w}px">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                else:
                    # Normal Vordt display, no Frostbreath this draw
                    w = _card_w()

                    src = bytes_to_data_uri(data_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            # first display card is always the data card
            data_path = cfg.display_cards[0] if cfg.display_cards else None
            if data_path:
                img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
                w = _card_w()

                src = bytes_to_data_uri(img, mime="image/png")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:{w}px">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if st.session_state.get("ui_compact", False):
            cfg.entities = render_health_tracker(cfg, state)

    # RIGHT: Deck + current card
    with col_right:
        current = state.get("current_card")

        if not current:
            # No card drawn yet => show card back
            w = _card_w()

            p = Path(CARD_BACK)
            src = get_image_data_uri_cached(str(p))
            if not src:
                raise Exception("empty data uri")

            st.markdown(
                f"""
                <div class="card-image">
                    <img src="{src}" style="width:{w}px">
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            # --- Ornstein & Smough dual-boss case ---
            if cfg.name == "Ornstein & Smough":
                current_name = current

                if current_name:
                    # Phase 1: combined card, e.g. "Swiping Combo & Bonzai Drop"
                    if "&" in (current_name or ""):
                        img = render_dual_boss_behavior_card(
                            cfg.raw,
                            current_name,
                            boss_name=cfg.name,
                        )
                    # Phase 2: single behavior card, e.g. "Charged Swiping Combo"
                    else:
                        img = render_behavior_card_cached(
                            _behavior_image_path(cfg, current_name),
                            cfg.behaviors.get(current_name, {}),
                            is_boss=True,
                        )

                    w = _card_w()

                    src = bytes_to_data_uri(img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Vordt of the Boreal Valley: movement + attack decks ---
            elif cfg.name == "Vordt of the Boreal Valley" and isinstance(
                current, tuple
            ):
                move_card, atk_card = current

                # Show the cards side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    move_path = _behavior_image_path(cfg, move_card)
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        move_img = render_behavior_card_cached(
                            move_path, cfg.behaviors.get(move_card, {}), is_boss=True
                        )
                        move_img = overlay_priscilla_arcs(move_img, move_card, cfg.behaviors.get(move_card, {}))
                        src = bytes_to_data_uri(move_img, mime="image/png")
                    
                    else:
                        src = get_image_data_uri_cached(move_path)

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    atk_path = _behavior_image_path(cfg, atk_card)
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        atk_img = render_behavior_card_cached(
                            atk_path, cfg.behaviors.get(atk_card, {}), is_boss=True
                        )
                        atk_img = overlay_priscilla_arcs(atk_img, atk_card, cfg.behaviors.get(atk_card, {}))
                        src = bytes_to_data_uri(atk_img, mime="image/png")
                    else:
                        src = get_image_data_uri_cached(atk_path)

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Gaping Dragon: Stomach Slam shows Crawling Charge alongside ---
            elif cfg.name == "Gaping Dragon" and current.startswith("Stomach Slam"):
                # Stomach Slam image
                stomach_path = _behavior_image_path(cfg, current)
                stomach_img = render_behavior_card_cached(
                    stomach_path,
                    cfg.behaviors[current],
                    is_boss=True,
                )

                # Find Crawling Charge in the behaviors (handles things like "Crawling Charge 2")
                crawl_key = None
                for key in cfg.behaviors.keys():
                    if key.startswith("Crawling Charge"):
                        crawl_key = key
                        break

                if crawl_key:
                    crawl_path = _behavior_image_path(cfg, crawl_key)
                    crawl_img = render_behavior_card_cached(
                        crawl_path,
                        cfg.behaviors[crawl_key],
                        is_boss=True,
                    )

                    # Show them side-by-side
                    c1, c2 = st.columns(2)
                    with c1:
                        w = _card_w()

                        if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                            stomach_img = overlay_priscilla_arcs(stomach_img, current, cfg.behaviors.get(current, {}))
                        src = bytes_to_data_uri(stomach_img, mime="image/png")

                        st.markdown(
                            f"""
                            <div class="card-image">
                                <img src="{src}" style="width:{w}px">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with c2:
                        w = _card_w()

                        if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                            crawl_img = overlay_priscilla_arcs(crawl_img, crawl_key, cfg.behaviors.get(crawl_key, {}))
                        src = bytes_to_data_uri(crawl_img, mime="image/png")

                        st.markdown(
                            f"""
                            <div class="card-image">
                                <img src="{src}" style="width:{w}px">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # --- Guardian Dragon: Cage Grasp Inferno shows Fiery Breath alongside ---
            elif (
                cfg.name == GUARDIAN_DRAGON_NAME
                and isinstance(current, str)
                and current.startswith(GUARDIAN_CAGE_PREFIX)
            ):
                # Track when a new card is drawn so we only change the pattern
                # when the deck actually advances.
                last_key = f"boss_mode_last_current::{cfg.name}"
                last_current = st.session_state.get(last_key)
                is_new_draw = last_current != current
                st.session_state[last_key] = current

                # Decide which Fiery Breath pattern mode we're in
                mode = (
                    "generated"
                    if st.session_state.get("guardian_fiery_generate", False)
                    else "deck"
                )

                # Reuse the existing pattern for this card where possible,
                # otherwise draw a new one according to the selected mode.
                pattern_nodes = state.get("guardian_fiery_current_pattern")
                prev_mode = state.get("guardian_fiery_current_mode")
                if pattern_nodes is None or prev_mode != mode or is_new_draw:
                    pattern_nodes = _guardian_fiery_next_pattern(state, mode)
                    state["guardian_fiery_current_pattern"] = pattern_nodes
                    state["guardian_fiery_current_mode"] = mode

                # Base Cage Grasp Inferno image
                cage_path = _behavior_image_path(cfg, current)
                cage_img = render_behavior_card_cached(
                    cage_path,
                    cfg.behaviors.get(current, {}),
                    is_boss=True,
                )

                # Fiery Breath with AoE overlay
                fiery_img = _guardian_render_fiery_breath(cfg, pattern_nodes)

                # Show them side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        cage_img = overlay_priscilla_arcs(cage_img, current, cfg.behaviors.get(current, {}))
                    src = bytes_to_data_uri(cage_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    w = _card_w()

                    src = bytes_to_data_uri(fiery_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Black Dragon Kalameet: Hellfire cards show Fiery Ruin alongside ---
            elif (
                cfg.name == BLACK_DRAGON_KALAMEET_NAME
                and isinstance(current, str)
                and current.startswith(KALAMEET_HELLFIRE_PREFIX)
            ):
                # Track when a new card is drawn so we only change the pattern
                # when the deck actually advances.
                last_key = f"boss_mode_last_current::{cfg.name}"
                last_current = st.session_state.get(last_key)
                is_new_draw = last_current != current
                st.session_state[last_key] = current

                # Decide which Fiery Ruin pattern mode we're in
                mode = (
                    "generated"
                    if st.session_state.get("kalameet_aoe_generate", False)
                    else "deck"
                )

                # Reuse the existing pattern for this card where possible,
                # otherwise draw a new one according to the selected mode.
                pattern_nodes = state.get("kalameet_aoe_current_pattern")
                prev_mode = state.get("kalameet_aoe_current_mode")
                if pattern_nodes is None or prev_mode != mode or is_new_draw:
                    pattern_nodes = _kalameet_next_pattern(state, mode)
                    state["kalameet_aoe_current_pattern"] = pattern_nodes
                    state["kalameet_aoe_current_mode"] = mode

                # Base Hellfire card image
                hellfire_path = _behavior_image_path(cfg, current)
                hellfire_img = render_behavior_card_cached(
                    hellfire_path,
                    cfg.behaviors.get(current, {}),
                    is_boss=True,
                )

                # Fiery Ruin with AoE overlay
                fiery_img = _kalameet_render_fiery_ruin(cfg, pattern_nodes)

                # Show them side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        hellfire_img = overlay_priscilla_arcs(hellfire_img, current, cfg.behaviors.get(current, {}))
                    src = bytes_to_data_uri(hellfire_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    w = _card_w()

                    src = bytes_to_data_uri(fiery_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Old Iron King: Fire Beam cards show Blasted Nodes alongside ---
            elif (
                cfg.name == OLD_IRON_KING_NAME
                and isinstance(current, str)
                and current.startswith(OIK_FIRE_BEAM_PREFIX)
            ):
                # track when a new card is drawn so we only change the pattern
                last_key = f"boss_mode_last_current::{cfg.name}"
                last_current = st.session_state.get(last_key)
                is_new_draw = last_current != current
                st.session_state[last_key] = current

                # Decide which Blasted Nodes pattern mode we're in
                mode = (
                    "generated"
                    if st.session_state.get("oik_blasted_generate", False)
                    else "deck"
                )

                # Reuse the existing pattern for this card where possible,
                # otherwise draw a new one according to the selected mode.
                pattern_nodes = state.get("oik_blasted_current_pattern")
                prev_mode = state.get("oik_blasted_current_mode")
                if pattern_nodes is None or prev_mode != mode or is_new_draw:
                    pattern_nodes = _oik_blasted_next_pattern(state, mode)
                    state["oik_blasted_current_pattern"] = pattern_nodes
                    state["oik_blasted_current_mode"] = mode

                # Base Fire Beam card image
                beam_path = _behavior_image_path(cfg, current)
                beam_img = render_behavior_card_cached(
                    beam_path,
                    cfg.behaviors.get(current, {}),
                    is_boss=True,
                )

                # Blasted Nodes with AoE overlay
                blasted_img = _oik_render_blasted_nodes(cfg, pattern_nodes)

                # Show them side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        beam_img = overlay_priscilla_arcs(beam_img, current, cfg.behaviors.get(current, {}))
                    src = bytes_to_data_uri(beam_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    w = _card_w()

                    src = bytes_to_data_uri(blasted_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Executioner's Chariot: Death Race shows AoE track alongside ---
            elif (
                cfg.name == EXECUTIONERS_CHARIOT_NAME
                and isinstance(current, str)
                # Works for "Death Race" or "Death Race 1–4"
                and current.startswith(DEATH_RACE_BEHAVIOR_NAME)
            ):
                # Track when the *draw button* was pressed so we only change
                # the pattern when a new card is actually drawn.
                draw_token = st.session_state.get("boss_mode_draw_token", 0)
                last_key = f"boss_mode_last_draw::{cfg.name}"
                last_draw = st.session_state.get(last_key)
                is_new_draw = last_draw != draw_token
                st.session_state[last_key] = draw_token

                # Decide which Death Race pattern mode we're in
                mode = (
                    "generated"
                    if st.session_state.get("ec_death_race_generate", False)
                    else "deck"
                )

                # Reuse the existing pattern where possible,
                # otherwise draw a new one according to the selected mode.
                pattern_nodes = state.get("ec_death_race_current_pattern")
                prev_mode = state.get("ec_death_race_current_mode")
                if pattern_nodes is None or prev_mode != mode or is_new_draw:
                    pattern_nodes = _ec_death_race_next_pattern(state, mode=mode)
                    state["ec_death_race_current_pattern"] = pattern_nodes
                    state["ec_death_race_current_mode"] = mode

                # Base Death Race behavior card (trigger)
                death_race_path = _behavior_image_path(cfg, current)
                death_race_img = render_behavior_card_cached(
                    death_race_path,
                    cfg.behaviors.get(current, {}),
                    is_boss=True,
                )

                # Death Race AoE card with node overlay
                aoe_img = _ec_render_death_race_aoe(cfg, pattern_nodes)

                # Show them side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    w = _card_w()

                    if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                        death_race_img = overlay_priscilla_arcs(death_race_img, current, cfg.behaviors.get(current, {}))
                    src = bytes_to_data_uri(death_race_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c2:
                    w = _card_w()

                    src = bytes_to_data_uri(aoe_img, mime="image/png")

                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src}" style="width:{w}px">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # --- Normal single-card case ---
            else:
                base_path = _behavior_image_path(cfg, current)
                img = render_behavior_card_cached(
                    base_path,
                    cfg.behaviors[current],
                    is_boss=True,
                )
                w = _card_w()

                if cfg.name == "Crossbreed Priscilla" and st.session_state.get("behavior_deck", {}).get("priscilla_invisible", False):
                    img = overlay_priscilla_arcs(img, current, cfg.behaviors.get(current, {}))
                src = bytes_to_data_uri(img, mime="image/png")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:{w}px">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if cfg.name == "Vordt of the Boreal Valley":
            st.caption(
                f"{len(state.get('vordt_move_discard', [])) + (1 if current else 0)} movement cards played"
                f" • {len(state.get('vordt_attack_discard', [])) + (1 if current else 0)} attack cards played"
            )
        else:
            st.caption(
                f"Draw pile: {len(state.get('draw_pile', []))} cards"
                f" • Discard: {len(state.get('discard_pile', [])) + (1 if current else 0)} cards"
            )

    # Mobile UX: duplicate controls below the cards in "Compact layout".
    if st.session_state.get("ui_compact", False):
        _render_combat_controls(where="bottom")
