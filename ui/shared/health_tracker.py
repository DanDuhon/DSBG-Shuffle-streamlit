import streamlit as st

from core.behavior.logic import _apply_sif_limping_mode, _revert_sif_limping_mode


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
        if cfg.name == "Executioner's Chariot" and not st.session_state.get("chariot_heatup_done", False):
            disabled_flag = True

        # --- Ornstein & Smough: disable if dead
        elif cfg.name == "Ornstein & Smough":
            if "Ornstein" in label and st.session_state.get("ornstein_dead", False):
                disabled_flag = True
            elif "Smough" in label and st.session_state.get("smough_dead", False):
                disabled_flag = True

        # --- The Four Kings: add sliders as kings are summoned ---
        elif cfg.name == "The Four Kings":
            enabled_count = state.get("enabled_kings", 1)
            st.session_state["enabled_kings"] = enabled_count  # keep in sync

            # e.label is "King 1", "King 2", etc.
            king_num = int(e.label.split()[-1])

            # If this king hasn't been summoned yet, don't render a slider for it
            if king_num > enabled_count:
                continue

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
