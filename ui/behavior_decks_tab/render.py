#ui/behavior_decks_tab/render.py
import streamlit as st
import random
from pathlib import Path

from core.settings_manager import load_settings
from ui.behavior_decks_tab.logic import (_ensure_state, load_behavior
    , _new_state_from_file, _reset_deck, _load_cfg_for_state
    , _draw_card, _manual_heatup, apply_heatup, _clear_heatup_prompt
    , _ornstein_smough_heatup_ui, _apply_sif_limping_mode
    , _revert_sif_limping_mode)
from ui.behavior_decks_tab.assets import (BEHAVIOR_CARDS_PATH, CARD_BACK
    , _dim_greyscale, _behavior_image_path, CATEGORY_ORDER, CATEGORY_EMOJI)
from ui.behavior_decks_tab.persistance import _save_slot_ui
from ui.behavior_decks_tab.generation import (render_dual_boss_data_cards
    , render_dual_boss_behavior_card, render_data_card_cached
    , render_behavior_card_cached, build_behavior_catalog)
from ui.behavior_decks_tab.models import BehaviorEntry
from ui.ngplus_tab.logic import apply_ngplus_to_raw, get_current_ngplus_level


def render():
    _ensure_state()
    settings = st.session_state.get("user_settings") or load_settings()

    st.subheader("Behavior Decks")

    # Build or reuse catalog
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]

    # Available categories (non-empty ones only is nice UX)
    available_cats = [
        c for c in CATEGORY_ORDER
        if catalog.get(c)  # optional: only show if it has entries
    ] or CATEGORY_ORDER

    # Default to last used category, else "Regular Enemies"
    default_cat = st.session_state.get("behavior_category", "Regular Enemies")
    if default_cat not in available_cats:
        default_cat = available_cats[0]

    with st.expander("Enemy Selector", expanded=True):
        # --- NG+ badge / indicator ---
        ng_level = get_current_ngplus_level()

        if ng_level <= 0:
            label = "NG+0 (Base game)"
        else:
            label = f"NG+{ng_level} active"

        st.markdown(
            f"""
            <div style="text-align: left; margin-bottom: 0.25rem;">
            <span style="
                display:inline-block;
                padding: 0.1rem 0.6rem;
                border-radius: 999px;
                font-size: 0.8rem;
                background-color: #444444;
                color: #ffffff;
                opacity: 0.9;
            ">
                🌀 {label}
            </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 1) Category chooser (radio; horizontal works nicely)
        category = st.radio(
            "Type of enemy / boss",
            available_cats,
            index=available_cats.index(default_cat),
            key="behavior_category",
            horizontal=True,
            format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
        )

        entries: list[BehaviorEntry] = catalog.get(category, [])
        if not entries:
            st.info("No encounters found in this category.")
            return

        names = [e.name for e in entries]

        # Preserve previous selection if possible
        last_choice = st.session_state.get("behavior_choice")
        if last_choice in names:
            default_index = names.index(last_choice)
        else:
            default_index = 0

        # 3) Actual enemy/boss dropdown, but now short
        choice = st.selectbox(
            "Choose enemy / invader / boss",
            options=names,
            index=default_index,
            key="behavior_choice",
        )

        selected_entry = next(e for e in entries if e.name == choice)
        fpath = str(selected_entry.path)
        cfg = load_behavior(Path(fpath))

    # Apply NG+ scaling to the raw config
    ng_level = get_current_ngplus_level()
    cfg.raw = apply_ngplus_to_raw(cfg.raw, ng_level, enemy_name=selected_entry.name)

    # --- Regular single-card enemy: no deck state at all
    if "behavior" in cfg.raw:
        cols = st.columns(2)
        with cols[0]:
            data_card = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            img_bytes = render_data_card_cached(data_card, cfg.raw, is_boss=False)
            st.image(img_bytes)
        return

    # --- Boss / Invader mode ---
    if cfg.name == "The Four Kings":
        st.session_state["enabled_kings"] = 1

    if "chariot_heatup_done" not in st.session_state:
        st.session_state["chariot_heatup_done"] = False

    # Create / reuse deck state, but reuse the cfg we just loaded
    if (
        st.session_state["behavior_deck"] is None
        or st.session_state["behavior_deck"].get("selected_file") != fpath
    ):
        state, cfg = _new_state_from_file(fpath, cfg)   # <-- pass cfg in
        st.session_state["behavior_deck"] = state

        if cfg.name == "Crossbreed Priscilla":
            st.session_state["behavior_deck"]["priscilla_invisible"] = True
    else:
        state = st.session_state["behavior_deck"]
        cfg = _load_cfg_for_state(state)

    if st.button("🔄 Reset Deck and Health", key="reset_deck"):
        _reset_deck(st.session_state["behavior_deck"], cfg)

    state = st.session_state["behavior_deck"]
    if not state:
        st.info("Select a behavior file to begin.")
        return

    cfg = _load_cfg_for_state(state)
    if not cfg:
        st.error("Unable to load config.")
        return

    # --- Reference Cards section
    st.subheader("Reference Cards")

    cols = st.columns(max(2, len(state["display_cards"])))

    # Special rules for Chariot data card display based on phase.
    if cfg.name == "Executioner Chariot":
        if not st.session_state.get("chariot_heatup_done", False):
            edited_img = render_data_card_cached(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner Chariot.jpg",
                cfg.raw,
                is_boss=True,
                no_edits=True,
            )
        else:
            edited_img = render_data_card_cached(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                cfg.raw,
                is_boss=True,
            )
        with cols[0]:
            st.image(edited_img)
    elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
        ornstein_img, smough_img = render_dual_boss_data_cards(cfg.raw)
        dual_cols = st.columns(2)
        with dual_cols[0]:
            if st.session_state.get("ornstein_dead"):
                st.image(_dim_greyscale(ornstein_img), width="stretch")
            else:
                st.image(ornstein_img, width="stretch")
        with dual_cols[1]:
            if st.session_state.get("smough_dead"):
                st.image(_dim_greyscale(smough_img), width="stretch")
            else:
                st.image(smough_img, width="stretch")
    else:
        for i, data_path in enumerate(state["display_cards"]):
            if i == 0:
                edited_img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
            else:
                card_name = Path(data_path).stem.split(" - ")[-1]
                edited_img = render_behavior_card_cached(
                    data_path, cfg.raw[card_name], is_boss=True
                )
            with cols[i if i < len(cols) else -1]:
                st.image(edited_img)
                
    if cfg.name == "Crossbreed Priscilla":
        invis = st.session_state["behavior_deck"].get("priscilla_invisible", False)
        st.caption(f"🫥 Invisibility: {'ON' if invis else 'OFF'}")

    # --- Health block
    st.markdown("---")
    st.subheader("Health Tracker")
    cfg.entities = render_health_tracker(cfg, state)

    # --- Auto Heat-Up Prompt ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and (cfg.name == "Vordt of the Boreal Valley" or not st.session_state.get("heatup_done", False))
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        st.warning(f"⚠️ The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} has entered Heat-Up range!")

        confirm_cols = st.columns([1, 1])
        with confirm_cols[0]:
            if st.button("🔥 Confirm Heat-Up", key="confirm_heatup"):
                rng = random.Random()
                apply_heatup(state, cfg, rng, reason="auto")
                _clear_heatup_prompt()
                st.session_state["pending_heatup_prompt"] = False
                st.session_state["pending_heatup_target"] = None
                st.session_state["pending_heatup_type"] = None
                if cfg.name not in {"Old Dragonslayer", "Ornstein & Smough", "Vordt of the Boreal Valley"}:
                    st.session_state["heatup_done"] = True
                st.rerun()
        with confirm_cols[1]:
            if st.button("Cancel", key="cancel_heatup"):
                _clear_heatup_prompt()
                st.session_state["heatup_done"] = False
                st.rerun()
    elif st.session_state.get("pending_heatup_prompt", False):
        boss = st.session_state.get("pending_heatup_target")
        if boss == "Old Dragonslayer":
            st.warning("Was 4+ damage was done in a single attack?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Heat-Up"):
                    state["old_dragonslayer_confirmed"] = True
                    _clear_heatup_prompt()
                    apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel"):
                    _clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()
        
        
        # --- Ornstein & Smough death confirmation ---
        elif boss == "Ornstein & Smough":
            st.warning("⚔️ One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Phase Change"):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()

    st.markdown("---")

    # --- Draw pile and current card columns
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Draw Pile**")
        if cfg.name == "Vordt of the Boreal Valley":
            st.caption(f"{len(state['vordt_move_draw'])} movement cards remaining")
            if state["vordt_move_draw"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)
                
            st.caption(f"{len(state['vordt_attack_draw'])} attack cards remaining")
            if state["vordt_attack_draw"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)
        else:
            st.caption(f"{len(state['draw_pile'])} cards remaining")
            if state["draw_pile"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)

    with c2:
        st.markdown("**Current Card**")

        # --- Vordt of the Boreal Valley special layout
        if cfg.name == "Vordt of the Boreal Valley" and isinstance(state["current_card"], tuple):
            move_card, atk_card = state["current_card"]
            move_path = _behavior_image_path(cfg, move_card)
            atk_path = _behavior_image_path(cfg, atk_card)

            # --- Movement Deck Row ---
            if move_card:
                st.caption(f"{len(state['vordt_move_discard'])} movement cards played")
                st.image(
                    render_behavior_card_cached(
                        move_path,
                        cfg.behaviors.get(move_card, {}),
                        is_boss=True,
                    )
                )

            # --- Attack Deck Row ---
            if atk_card:
                st.caption(f"{len(state['vordt_attack_discard'])} attack cards played")
                st.image(
                    render_behavior_card_cached(
                        atk_path,
                        cfg.behaviors.get(atk_card, {}),
                        is_boss=True,
                    )
                )

        # --- Ornstein & Smough dual boss case
        elif cfg.name == "Ornstein & Smough":
            st.caption(
                f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played"
            )
            current_name = state["current_card"]

            if current_name:
                # --- During phase-2 (after one death), cards no longer contain '&'
                if "&" in (current_name or ""):
                    edited_behavior = render_dual_boss_behavior_card(
                        cfg.raw, current_name, boss_name=cfg.name
                    )
                else:
                    edited_behavior = render_behavior_card_cached(
                        _behavior_image_path(cfg, current_name),
                        cfg.behaviors.get(current_name, {}),
                        is_boss=True,
                    )

                st.image(edited_behavior)

        # --- Normal single-card bosses
        elif state.get("current_card"):
            st.caption(
                f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played"
            )
            beh_key = state["current_card"]
            beh_json = cfg.behaviors.get(beh_key, {})
            current_path = _behavior_image_path(cfg, beh_key)
            edited_behavior = render_behavior_card_cached(
                current_path, beh_json, is_boss=True
            )
            st.image(edited_behavior)

    # --- Action buttons
    btn_cols = st.columns(2)
    with btn_cols[0]:
        draw_label = "Draw Movement + Attack" if cfg.name == "Vordt of the Boreal Valley" else "Draw"
        if st.button(draw_label, width="stretch", key="behavior_draw"):
            _clear_heatup_prompt()
            _draw_card(state)
            st.rerun()
    with btn_cols[1]:
        if st.button("Manual Heat-Up", width="stretch"):
            _clear_heatup_prompt()
            _manual_heatup(state)
            st.rerun()

    st.markdown("---")

    # --- Save slots (persist to settings file)
    _save_slot_ui(settings, state)


def render_health_tracker(cfg, state):
    tracker = st.session_state.setdefault("hp_tracker", {})
    reset_id = st.session_state.get("deck_reset_id", 0)

    for e in cfg.entities:
        ent_id = e.id                 # must be unique: "ornstein", "smough", "king_1"
        label = f"{e.label} HP"               # "Ornstein", "Smough", "King 1"
        hp = e.hp
        hpmax = e.hp_max
        heat_thresh = (e.heatup_thresholds or [None])[0]
        slider_key = f"hp_{ent_id}_{reset_id}"   # e.g., hp_ornstein_0 / hp_king_1_0

        initial_val = int(tracker.get(ent_id, {}).get("hp", hp))

        # IMPORTANT: bind everything used inside as default args to avoid late binding
        def on_hp_change(
            *,
            _slider_key=slider_key,
            _ent_id=ent_id,
            _hpmax=hpmax,
            _heat_thresh=heat_thresh,
            _hp_default=hp,
            _boss_name=cfg.name
        ):
            val = st.session_state.get(_slider_key, _hp_default)
            val = max(0, min(int(val), int(_hpmax)))
            prev = tracker.get(_ent_id, {}).get("hp", _hp_default)
            tracker[_ent_id] = {"hp": val, "hp_max": _hpmax}

            for ent in cfg.entities:
                if ent.id == _ent_id:
                    ent.hp = val
                    break

            # --- Great Grey Wolf Sif: enter/exit limping mode around 3 HP
            if _boss_name == "Great Grey Wolf Sif":
                # Enter limping mode
                if val <= 3 and not state.get("sif_limping_active", False):
                    _apply_sif_limping_mode(state, cfg)
                # Leave limping mode if healed above 3
                elif val > 3 and state.get("sif_limping_active", False):
                    _revert_sif_limping_mode(state, cfg)

            # --- standard heat-up threshold
            if (
                _boss_name != "Vordt of the Boreal Valley"
                and _heat_thresh is not None
                and not state.get("heatup_done", False)
            ):
                if val <= _heat_thresh:
                    st.session_state["pending_heatup_prompt"] = True
                    if cfg.name == "Old Dragonslayer":
                        st.session_state["pending_heatup_target"] = "Old Dragonslayer"
                        st.session_state["pending_heatup_type"] = "old_dragonslayer"
                    elif cfg.name == "Artorias":
                        st.session_state["pending_heatup_target"] = "Artorias"
                        st.session_state["pending_heatup_type"] = "artorias"

            if _boss_name == "Vordt of the Boreal Valley":
                h1 = cfg.raw.get("heatup1")
                h2 = cfg.raw.get("heatup2")

                attack_done = st.session_state.get("vordt_attack_heatup_done", False)
                move_done   = st.session_state.get("vordt_move_heatup_done", False)

                crossed_attack = (
                    isinstance(h1, int)
                    and not attack_done
                    and prev > h1 >= val
                )
                crossed_move = (
                    isinstance(h2, int)
                    and not move_done
                    and prev > h2 >= val
                )

                if crossed_attack and crossed_move:
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["pending_heatup_target"] = "Vordt of the Boreal Valley"
                    st.session_state["pending_heatup_type"] = "vordt_both"
                elif crossed_attack:
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["pending_heatup_target"] = "Vordt of the Boreal Valley"
                    st.session_state["pending_heatup_type"] = "vordt_attack"
                elif crossed_move:
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["pending_heatup_target"] = "Vordt of the Boreal Valley"
                    st.session_state["pending_heatup_type"] = "vordt_move"

            # --- Old Dragonslayer: 4+ in one change
            if _boss_name == "Old Dragonslayer" and (prev - val) >= 4:
                st.session_state["pending_heatup_prompt"] = True
                st.session_state["pending_heatup_target"] = "Old Dragonslayer"
                st.session_state["pending_heatup_type"] = "old_dragonslayer"

            # --- Crossbreed Priscilla: any damage cancels invisibility
            elif _boss_name == "Crossbreed Priscilla" and val < prev:
                st.session_state.setdefault("behavior_deck", {})["priscilla_invisible"] = False

        # --- Ornstein & Smough special handling
        if cfg.name == "Ornstein & Smough":
            ornstein = next((ent for ent in cfg.entities if "Ornstein" in ent.label), None)
            smough = next((ent for ent in cfg.entities if "Smough" in ent.label), None)
            if ornstein and smough:
                orn_hp = int(ornstein.hp)
                smo_hp = int(smough.hp)
                if orn_hp <= 0 and not st.session_state.get("ornstein_dead_pending", False) \
                        and not st.session_state.get("ornstein_dead", False):
                    st.session_state["ornstein_dead_pending"] = True
                    st.session_state["pending_heatup_target"] = "Ornstein & Smough"
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["smough_dead_pending"] = False
                elif smo_hp <= 0 and not st.session_state.get("smough_dead_pending", False) \
                        and not st.session_state.get("smough_dead", False):
                    st.session_state["smough_dead_pending"] = True
                    st.session_state["pending_heatup_target"] = "Ornstein & Smough"
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["ornstein_dead_pending"] = False

        elif cfg.name == "The Last Giant":
            st.session_state["pending_heatup_target"] = "The Last Giant"
            st.session_state["pending_heatup_type"] = "last_giant"

        disabled_flag = False

        # CHARIOT: locked pre-heatup
        if cfg.name == "Executioner Chariot" and not st.session_state.get("chariot_heatup_done", False):
            disabled_flag = True

        # --- Ornstein & Smough: disable if dead
        elif cfg.name == "Ornstein & Smough":
            if "Ornstein" in label and st.session_state.get("ornstein_dead", False):
                disabled_flag = True
            elif "Smough" in label and st.session_state.get("smough_dead", False):
                disabled_flag = True

        # --- The Four Kings: enable sliders incrementally
        elif cfg.name == "The Four Kings":
            enabled_count = state.get("enabled_kings", 1)
            st.session_state["enabled_kings"] = enabled_count  # keep in sync for UI continuity
            try:
                king_num = int(label.split()[-1])
            except Exception:
                king_num = 1
            if king_num > enabled_count:
                disabled_flag = True

        st.slider(
            label,
            0,
            hpmax,
            value=initial_val,
            key=slider_key,
            on_change=on_hp_change,
            disabled=disabled_flag,
        )

    return cfg.entities
