# ui/character_mode/render.py
from __future__ import annotations
import pandas as pd
import streamlit as st
import json
from typing import Any, Dict, List, Set
import itertools
from core.character_stats import CLASS_TIERS, TIERS
from ui.character_mode.build import _build_stats, _validate_build, _eligibility_issues
from ui.character_mode.constants import (
    HAND_CONDITION_OPTIONS,
    HAND_FEATURE_OPTIONS
)
from ui.character_mode.data_io import _find_data_file, _load_json_list, load_builds, save_builds
from ui.character_mode.dice_math import _dice_icons, _dice_min_max_avg, _dodge_icons
from ui.character_mode.filters import (
    _apply_armor_filters,
    _apply_hand_item_filters,
    _filter_items
)
from ui.character_mode.item_fields import (
    _armor_dodge_int,
    _armor_upgrade_slots_int,
    _extra_upgrade_slots,
    _hand_dodge_int,
    _hand_hands_required_int,
    _hand_range_str,
    _hand_upgrade_slots_int,
    _hands_required,
    _id,
    _immunities_set,
    _item_expansions,
    _name,
    _sorted_with_none_first,
    _src_str,
    _upgrade_slots,
    _is_twohand_compatible_shield
)
from ui.character_mode.selection import (
    _merge_visible_selection,
    _normalize_hand_selection,
    _ordered_unique
)
from ui.character_mode.tables import _rows_for_armor_table, _rows_for_hand_table
from ui.character_mode.aggregates import (
    expected_damage_taken,
    build_attack_totals_rows_cached,
    build_defense_totals_cached,
)
from ui.character_mode.widgets import _render_selection_table
from core.settings_manager import save_settings


def render(settings: Dict[str, Any]) -> None:
    active = set(x for x in (settings.get("active_expansions") or []))

    # Selection state
    ss = st.session_state
    ss.setdefault("cm_selected_armor_id", "")
    ss.setdefault("cm_selected_armor_upgrade_ids", [])
    ss.setdefault("cm_selected_hand_ids", [])
    ss.setdefault("cm_selected_weapon_upgrade_ids_by_hand", {})

    # If a build was requested to be applied from the previous run, apply it
    # before any widgets are instantiated so we can safely set widget-backed
    # session_state keys.
    pending = ss.pop("cm_pending_build", None)
    if pending:
        ss["cm_persist_class"] = pending.get("class_name", ss.get("cm_persist_class"))
        tiers = pending.get("tier_indices", {}) or {}
        ss.setdefault("cm_persist_tiers", {"str": 0, "dex": 0, "itl": 0, "fth": 0})
        for stat, wkey in [("str", "cm_tier_str_i"), ("dex", "cm_tier_dex_i"), ("itl", "cm_tier_itl_i"), ("fth", "cm_tier_fth_i")]:
            val = int(tiers.get(stat, int(ss.get(wkey, 0))))
            # Safe to set widget keys here because widgets haven't been created yet
            ss[wkey] = val
            ss["cm_persist_tiers"][stat] = val
        # Also set the class widget key prior to instantiation
        ss["character_mode_class"] = ss["cm_persist_class"]
        ss["cm_selected_armor_id"] = pending.get("selected_armor_id", "")
        ss["cm_selected_armor_upgrade_ids"] = list(pending.get("selected_armor_upgrade_ids") or [])
        ss["cm_selected_hand_ids"] = list(pending.get("selected_hand_ids") or [])
        ss["cm_selected_weapon_upgrade_ids_by_hand"] = dict(pending.get("selected_weapon_upgrade_ids_by_hand") or {})

    left, right = st.columns([1, 1])

    with left:
        eligible_classes = sorted(
            [c for c, cfg in CLASS_TIERS.items() if set(cfg.get("expansions") or set()) & active]
        )
        if not eligible_classes:
            st.error("No classes are available for the enabled expansions.")
            return

        # Persist class across mode switches (widget state can be pruned when not rendered)
        ss.setdefault("cm_persist_class", eligible_classes[0])
        if ss["cm_persist_class"] not in eligible_classes:
            ss["cm_persist_class"] = eligible_classes[0]

        # Re-seed widget key if it was pruned or became invalid
        if ("character_mode_class" not in ss) or (ss.get("character_mode_class") not in eligible_classes):
            ss["character_mode_class"] = ss["cm_persist_class"]

        class_name = st.selectbox(
            "Class",
            options=eligible_classes,
            key="character_mode_class",
        )

        # Copy widget value into persistent storage
        ss["cm_persist_class"] = class_name

        cfg = CLASS_TIERS[class_name]

        tier_opts = [0, 1, 2, 3]

        def _fmt(stat_key: str):
            arr = cfg[stat_key]
            return lambda i: f"{TIERS[i]} ({arr[i]})"
        
        # Persist tier indices across mode switches
        ss.setdefault("cm_persist_tiers", {"str": 0, "dex": 0, "itl": 0, "fth": 0})

        # Re-seed widget keys if they were pruned
        for stat, wkey in [
            ("str", "cm_tier_str_i"),
            ("dex", "cm_tier_dex_i"),
            ("itl", "cm_tier_itl_i"),
            ("fth", "cm_tier_fth_i"),
        ]:
            if wkey not in ss:
                ss[wkey] = int(ss["cm_persist_tiers"].get(stat, 0))

        # Place tier radios in equal-width columns so labels align vertically
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            _str_i = st.radio(
                "Strength tier",
                options=tier_opts,
                index=int(ss.get("cm_tier_str_i", 0)),
                format_func=_fmt("str"),
                horizontal=True,
                key="cm_tier_str_i",
            )
        with c2:
            _dex_i = st.radio(
                "Dexterity tier",
                options=tier_opts,
                index=int(ss.get("cm_tier_dex_i", 0)),
                format_func=_fmt("dex"),
                horizontal=True,
                key="cm_tier_dex_i",
            )
        with c3:
            _itl_i = st.radio(
                "Intelligence tier",
                options=tier_opts,
                index=int(ss.get("cm_tier_itl_i", 0)),
                format_func=_fmt("itl"),
                horizontal=True,
                key="cm_tier_itl_i",
            )
        with c4:
            _fth_i = st.radio(
                "Faith tier",
                options=tier_opts,
                index=int(ss.get("cm_tier_fth_i", 0)),
                format_func=_fmt("fth"),
                horizontal=True,
                key="cm_tier_fth_i",
            )

        tier_indices = {"str": _str_i, "dex": _dex_i, "itl": _itl_i, "fth": _fth_i}

        ss["cm_persist_tiers"] = dict(tier_indices)

        stats = _build_stats(class_name, tier_indices)

        # Placeholder in the left column for the Totals panel (placed under stats)
        left_summary_slot = st.empty()
        # reserve vertical space (rendered inside container instead)

    with right:
        build_slot = st.empty()
        summary_slot = st.empty()

    st.markdown("---")
    query = st.text_input("Filter items by name", value="", key="character_mode_item_query")

    # Load item data (best-effort path resolution)
    paths = {
        "hand_items.json": _find_data_file("hand_items.json"),
        "armor.json": _find_data_file("armor.json"),
        "weapon_upgrades.json": _find_data_file("weapon_upgrades.json"),
        "armor_upgrades.json": _find_data_file("armor_upgrades.json"),
    }

    missing = [k for k, v in paths.items() if v is None]
    if missing:
        st.error("Missing item data files: " + ", ".join(missing))
        return

    hand_items = _load_json_list(str(paths["hand_items.json"]))
    armor_items = _load_json_list(str(paths["armor.json"]))
    weapon_upgrades = _load_json_list(str(paths["weapon_upgrades.json"]))
    armor_upgrades = _load_json_list(str(paths["armor_upgrades.json"]))

    all_items = hand_items + armor_items + weapon_upgrades + armor_upgrades

    # Build helpers (store builds in session state)
    ss.setdefault("cm_builds", {})
    # Load persisted builds from dedicated file (migrate from user settings if needed)
    persisted = load_builds() or {}
    # If no dedicated file exists but user settings contain builds, migrate them
    if not persisted and isinstance(settings.get("character_builds"), dict):
        persisted = dict(settings.get("character_builds"))
        save_builds(persisted)
        # remove migrated builds from user settings
        settings.pop("character_builds", None)
        st.session_state["user_settings"] = settings
        save_settings(settings)

    if isinstance(persisted, dict) and not ss.get("cm_builds"):
        ss["cm_builds"] = dict(persisted)

    def _current_build():
        return {
            "class_name": class_name,
            "tier_indices": tier_indices,
            "selected_armor_id": ss.get("cm_selected_armor_id") or "",
            "selected_armor_upgrade_ids": list(ss.get("cm_selected_armor_upgrade_ids") or []),
            "selected_hand_ids": list(ss.get("cm_selected_hand_ids") or []),
            "selected_weapon_upgrade_ids_by_hand": dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {}),
        }

    def _apply_build(data: dict):
        if not data:
            return
        # Only write persistent values here; actual widget-backed keys are
        # updated by setting `cm_pending_build` and rerunning so they can be
        # applied before widgets are instantiated.
        ss["cm_persist_class"] = data.get("class_name", ss.get("cm_persist_class"))
        tiers = data.get("tier_indices", {}) or {}
        ss.setdefault("cm_persist_tiers", {"str": 0, "dex": 0, "itl": 0, "fth": 0})
        for stat in ("str", "dex", "itl", "fth"):
            val = int(tiers.get(stat, int(ss["cm_persist_tiers"].get(stat, 0))))
            ss["cm_persist_tiers"][stat] = val
        ss["cm_selected_armor_id"] = data.get("selected_armor_id", "")
        ss["cm_selected_armor_upgrade_ids"] = list(data.get("selected_armor_upgrade_ids") or [])
        ss["cm_selected_hand_ids"] = list(data.get("selected_hand_ids") or [])
        ss["cm_selected_weapon_upgrade_ids_by_hand"] = dict(data.get("selected_weapon_upgrade_ids_by_hand") or {})

    # Build UI (save / load / delete / export)
    with build_slot.container():
        c1, c2 = st.columns([3, 1])
        with c1:
            _ = st.text_input("Build name", key="cm_build_name")
        with c2:
            if st.button("Save build", key="cm_build_save"):
                name = (ss.get("cm_build_name") or "").strip() or f"build_{len(ss.get('cm_builds', {}))+1}"
                ss["cm_builds"][name] = _current_build()
                # Persist saved builds to dedicated file
                save_builds(ss["cm_builds"])

        snaps = list(ss.get("cm_builds", {}).keys())
        sel = st.selectbox("Saved builds", options=[""] + snaps, key="cm_build_select")
        c3, c4 = st.columns([1, 1])
        with c3:
            if st.button("Load", key="cm_build_load"):
                name = ss.get("cm_build_select")
                if name:
                    # Mark build to be applied on the next run so we can set
                    # widget-backed keys before widgets are created.
                    ss["cm_pending_build"] = ss["cm_builds"][name]
                    st.rerun()
        with c4:
            if st.button("Delete", key="cm_build_delete"):
                name = ss.get("cm_build_select")
                if name and name in ss.get("cm_builds", {}):
                    ss["cm_builds"].pop(name, None)
                    # Persist deletion to dedicated file
                    save_builds(ss["cm_builds"])
                    st.rerun()

    enabled_items = []
    present_exps: Set[str] = set()
    src_types: Set[str] = set()
    src_entities: Set[str] = set()

    for it in all_items:
        exps = set(_item_expansions(it))
        if exps and exps.isdisjoint(active):
            continue
        enabled_items.append(it)
        present_exps |= exps
        src_types.add(_src_str(it, "type"))
        src_entities.add(_src_str(it, "entity"))

    expansion_options = sorted(present_exps & active)
    type_options = _sorted_with_none_first(src_types)
    entity_options = _sorted_with_none_first(src_entities)

    # --- Global filter defaults (must exist before any filtered_* computations) ---
    gf_expansion = st.session_state.get("cm_gf_expansion")
    gf_source_type = st.session_state.get("cm_gf_source_type")
    gf_source_entity = st.session_state.get("cm_gf_source_entity")
    gf_legendary = st.session_state.get("cm_gf_legendary") or "Any"

    gf_expansion = [x for x in (gf_expansion or expansion_options) if x in expansion_options]
    gf_source_type = [x for x in (gf_source_type or type_options) if x in type_options]
    gf_source_entity = [x for x in (gf_source_entity or entity_options) if x in entity_options]

    expansion_filter = set(gf_expansion)
    source_type_filter = set(gf_source_type)
    source_entity_filter = set(gf_source_entity)
    legendary_mode = gf_legendary if gf_legendary in {"Any", "Legendary only", "Non-legendary only"} else "Any"

    with st.expander("Global filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            prev = st.session_state.get("cm_gf_expansion") or expansion_options
            default = [x for x in prev if x in expansion_options] or expansion_options
            gf_expansion = st.multiselect(
                "Expansion",
                options=expansion_options,
                default=default,
                key="cm_gf_expansion",
            )
        with c2:
            gf_legendary = st.selectbox(
                "Legendary",
                options=["Any", "Legendary only", "Non-legendary only"],
                index=0,
                key="cm_gf_legendary",
            )

        c3, c4 = st.columns(2)
        with c3:
            prev = st.session_state.get("cm_gf_source_type") or type_options
            default = [x for x in prev if x in type_options] or type_options
            gf_source_type = st.multiselect(
                "Source Type",
                options=type_options,
                default=default,
                key="cm_gf_source_type",
            )
        with c4:
            prev = st.session_state.get("cm_gf_source_entity") or entity_options
            default = [x for x in prev if x in entity_options] or entity_options
            gf_source_entity = st.multiselect(
                "Source Entity",
                options=entity_options,
                default=default,
                key="cm_gf_source_entity",
            )

    expansion_filter = set(gf_expansion)
    source_type_filter = set(gf_source_type)
    source_entity_filter = set(gf_source_entity)
    legendary_mode = gf_legendary

    hand_by_id = {_id(x): x for x in hand_items}
    armor_by_id = {_id(x): x for x in armor_items}
    wu_by_id = {_id(x): x for x in weapon_upgrades}
    au_by_id = {_id(x): x for x in armor_upgrades}

    # left summary content is rendered after selections are reconciled below to ensure it reflects current selections

    # These two tables currently only use global filters
    filtered_wu = _filter_items(
        weapon_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )
    filtered_au = _filter_items(
        armor_upgrades,
        active_expansions=active,
        class_name=class_name,
        stats=stats,
        query=query,
        expansion_filter=expansion_filter,
        source_type_filter=source_type_filter,
        source_entity_filter=source_entity_filter,
        legendary_mode=legendary_mode,
    )

    wu_order = [_id(x) for x in filtered_wu]
    au_order = [_id(x) for x in filtered_au]

    # Filled inside tabs, but needed later (attacks tab + final reconcile)
    filtered_hand: List[Dict[str, Any]] = []
    filtered_armor: List[Dict[str, Any]] = []
    hand_order: List[str] = []

    tab_hand, tab_attacks, tab_armor, tab_wu, tab_au = st.tabs(
        ["Hand Items", "Attacks", "Armor", "Weapon Upgrades", "Armor Upgrades"]
    )

    with tab_hand:
        # --- Hand item filters live here now ---
        hand_pool_for_options = _filter_items(
            hand_items,
            active_expansions=active,
            class_name=class_name,
            stats=stats,
            query="",  # don't collapse options due to name search
            expansion_filter=expansion_filter,
            source_type_filter=source_type_filter,
            source_entity_filter=source_entity_filter,
            legendary_mode=legendary_mode,
        )

        cat_opts = sorted({str(x.get("hand_category") or "") for x in hand_pool_for_options})
        dodge_opts = sorted({_hand_dodge_int(x) for x in hand_pool_for_options})
        hands_opts = sorted({_hand_hands_required_int(x) for x in hand_pool_for_options})
        range_opts = sorted(
            {_hand_range_str(x) for x in hand_pool_for_options},
            key=lambda s: (s == "∞", int(s) if s != "∞" else 999),
        )
        slot_opts = sorted({_hand_upgrade_slots_int(x) for x in hand_pool_for_options})
        hand_immunity_opts = sorted({x for it in hand_pool_for_options for x in _immunities_set(it)})

        with st.expander("Hand item filters", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                prev = ss.get("cm_hf_categories") or cat_opts
                default = [x for x in prev if x in cat_opts] or cat_opts
                hf_categories = st.multiselect(
                    "Category",
                    options=cat_opts,
                    default=cat_opts,
                    key="cm_hf_categories",
                )

                prev = ss.get("cm_hf_dodge") or dodge_opts
                default = [x for x in prev if x in dodge_opts] or dodge_opts
                hf_dodge = st.multiselect(
                    "Dodge dice",
                    options=dodge_opts,
                    default=dodge_opts,
                    key="cm_hf_dodge",
                )

                prev = ss.get("cm_hf_hands") or hands_opts
                default = [x for x in prev if x in hands_opts] or hands_opts
                hf_hands = st.multiselect(
                    "Hands required",
                    options=hands_opts,
                    default=hands_opts,
                    key="cm_hf_hands",
                )

                hf_only_twohand_shields = st.checkbox(
                    "Only shields usable with a 2-hander",
                    value=bool(ss.get("cm_hf_only_twohand_shields") or False),
                    key="cm_hf_only_twohand_shields",
                )

            with c2:
                prev = ss.get("cm_hf_ranges") or range_opts
                default = [x for x in prev if x in range_opts] or range_opts
                hf_ranges = st.multiselect(
                    "Range",
                    options=range_opts,
                    default=range_opts,
                    key="cm_hf_ranges",
                )

                prev = ss.get("cm_hf_upgrade_slots") or slot_opts
                default = [x for x in prev if x in slot_opts] or slot_opts
                hf_upgrade_slots = st.multiselect(
                    "Upgrade slots",
                    options=slot_opts,
                    default=slot_opts,
                    key="cm_hf_upgrade_slots",
                )

                _attack_mode_opts = ["Any", "Attacks with dice", "No attacks with dice"]
                cur = ss.get("cm_hf_attack_lines_mode") or "Any"
                if cur not in _attack_mode_opts:
                    cur = "Any"
                hf_attack_lines_mode = st.radio(
                    "Attacks with dice",
                    options=_attack_mode_opts,
                    index=_attack_mode_opts.index(cur),
                    horizontal=True,
                    key="cm_hf_attack_lines_mode",
                )

            c3, c4, c5 = st.columns(3)
            with c3:
                hf_required_features = st.multiselect(
                    "Required properties (must match all)",
                    options=HAND_FEATURE_OPTIONS,
                    default=ss.get("cm_hf_required_features") or [],
                    key="cm_hf_required_features",
                )
            with c4:
                hf_any_conditions = st.multiselect(
                    "Conditions (match any)",
                    options=HAND_CONDITION_OPTIONS,
                    default=ss.get("cm_hf_any_conditions") or [],
                    key="cm_hf_any_conditions",
                )
            with c5:
                prev = ss.get("cm_hf_any_immunities") or []
                default = [x for x in prev if x in hand_immunity_opts]  # empty = show everything
                hf_any_immunities = st.multiselect(
                    "Immunities (match any)",
                    options=hand_immunity_opts,
                    default=default,
                    key="cm_hf_any_immunities",
                )

        hand_filter_categories = set(hf_categories) if hf_categories else None
        hand_filter_hands = set(int(x) for x in hf_hands) if hf_hands else None
        hand_filter_ranges = set(str(x) for x in hf_ranges) if hf_ranges else None
        hand_filter_slots = set(int(x) for x in hf_upgrade_slots) if hf_upgrade_slots else None
        hand_filter_dodge = set(int(x) for x in hf_dodge) if hf_dodge else None
        hand_required_features = set(hf_required_features or [])
        hand_any_conditions = set(hf_any_conditions or [])
        hand_any_immunities = set(hf_any_immunities or [])

        filtered_hand_base = _filter_items(
            hand_items,
            active_expansions=active,
            class_name=class_name,
            stats=stats,
            query=query,
            expansion_filter=expansion_filter,
            source_type_filter=source_type_filter,
            source_entity_filter=source_entity_filter,
            legendary_mode=legendary_mode,
        )
        filtered_hand = _apply_hand_item_filters(
            filtered_hand_base,
            categories=hand_filter_categories,
            hands_required=hand_filter_hands,
            only_twohand_compatible_shields=bool(hf_only_twohand_shields),
            dodge=hand_filter_dodge,
            ranges=hand_filter_ranges,
            upgrade_slots=hand_filter_slots,
            attack_lines_mode=hf_attack_lines_mode,
            required_features=hand_required_features,
            any_conditions=hand_any_conditions,
            any_immunities=hand_any_immunities,
        )
        hand_order = [_id(x) for x in filtered_hand]

        prev = list(ss.get("cm_selected_hand_ids", []))

        hand_cfg = {
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Category": st.column_config.TextColumn("Category", width=110),
            "Hands": st.column_config.NumberColumn("Hands", width=60),
            "Range": st.column_config.TextColumn("Range", width=70),
            "Upg Slots": st.column_config.NumberColumn("Slots", width=60),
            "Block": st.column_config.TextColumn("Block", width=95),
            "Resist": st.column_config.TextColumn("Resist", width=95),
            "Dodge": st.column_config.TextColumn("Dodge", width=75),
            "Text": st.column_config.TextColumn("Text", width="large"),
        }

        hand_col_order = [
            "Select", "Name",
            "Category", "Hands", "Range", "Upg Slots", "Block", "Resist", "Dodge", "Text",
            "STR", "DEX", "INT", "FAI",
            "Legendary", "Expansions", "SourceType", "SourceEntity",
        ]

        chosen = _render_selection_table(
            items=filtered_hand,
            selected_ids=prev,
            single_select=False,
            key="cm_table_hand",
            rows_fn=_rows_for_hand_table,
            column_config_override=hand_cfg,
            column_order=hand_col_order,
        )
        merged = _merge_visible_selection(
            prev_ids=prev,
            chosen_visible_ids=chosen,
            visible_order=hand_order,
        )
        ss["cm_selected_hand_ids"] = _normalize_hand_selection(
            merged,
            items_by_id=hand_by_id,
            stable_order=hand_order,
        )

    with tab_attacks:
        prev_ids = list(ss.get("cm_selected_hand_ids") or [])
        prev_set = set(prev_ids)
        # Build totals using current selection (armor + upgrades + weapon upgrades)
        armor_obj = armor_by_id.get(ss.get("cm_selected_armor_id") or "") if ss.get("cm_selected_armor_id") else None
        armor_upgrade_objs = [au_by_id[uid] for uid in (ss.get("cm_selected_armor_upgrade_ids") or []) if uid in au_by_id]

        wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
        weapon_upgrades_by_hand = {
            hid: [wu_by_id[uid] for uid in (wu_map.get(hid) or []) if uid in wu_by_id]
            for hid in set([_id(x) for x in filtered_hand])
        }

        attack_rows = build_attack_totals_rows_cached(
            hand_items=filtered_hand,
            selected_hand_ids=prev_set,
            armor_obj=armor_obj,
            armor_upgrade_objs=armor_upgrade_objs,
            weapon_upgrades_by_hand=weapon_upgrades_by_hand,
        )
        if not attack_rows:
            st.caption("0 attack lines (current Hand Items filters hide all attack lines).")
        else:
            df = pd.DataFrame(attack_rows)

            # Require RowId for stable identity
            if "RowId" not in df.columns:
                st.error("Attacks table requires RowId.")
                return

            df = df.set_index("RowId", drop=True)

            # Prepare display columns (keep underlying df but present named columns)
            disp = df.copy()
            # Totals that include gear modifications are provided in Tot* columns; fallback to base columns
            disp["Stamina"] = disp.get("TotStam") if "TotStam" in disp.columns else disp.get("Stam")
            disp["Dice"] = disp.get("TotDice") if "TotDice" in disp.columns else disp.get("Dice")
            disp["Min"] = disp.get("TotMin") if "TotMin" in disp.columns else disp.get("TotMin")
            disp["Max"] = disp.get("TotMax") if "TotMax" in disp.columns else disp.get("TotMax")
            disp["Avg"] = disp.get("TotAvg") if "TotAvg" in disp.columns else disp.get("TotAvg")
            # Avg per stamina
            def _avg_per_stam(row):
                s = row.get("Stamina") or 0
                a = row.get("Avg") or 0
                return float(a) / float(s) if float(s) != 0 else 0.0

            disp["Avg/Stam"] = disp.apply(_avg_per_stam, axis=1)
            disp["Range"] = disp.get("Range")
            disp["Shaft"] = disp.get("Shaft")
            disp["Magic"] = disp.get("Magic")
            # Coerce Repeat to numeric so missing/invalid values render blank
            disp["Repeat"] = pd.to_numeric(disp.get("Repeat"), errors="coerce")
            disp["Node"] = disp.get("Node")
            # 'Ignore Block' column (may be 'Ign Blk')
            if "Ign Blk" in disp.columns:
                disp["Ignore Block"] = disp["Ign Blk"]
            elif "IgnBlk" in disp.columns:
                disp["Ignore Block"] = disp["IgnBlk"]
            else:
                disp["Ignore Block"] = False
            # Condition/Cond
            if "Cond" in disp.columns:
                disp["Condition"] = disp["Cond"]
            elif "TotCond" in disp.columns:
                disp["Condition"] = disp["TotCond"]
            else:
                disp["Condition"] = ""
            disp["Text"] = disp.get("Text")

            att_cfg = {
                "Select": st.column_config.CheckboxColumn("Select", width="small"),
                "Item": st.column_config.TextColumn("Item", width="medium"),
                "Stamina": st.column_config.NumberColumn("Stamina", width=80),
                "Dice": st.column_config.TextColumn("Dice", width=150),
                "Min": st.column_config.NumberColumn("Min", width=70),
                "Max": st.column_config.NumberColumn("Max", width=70),
                "Avg": st.column_config.NumberColumn("Avg", width=80, format="%.2f"),
                "Avg/Stam": st.column_config.NumberColumn("Avg/Stam", width=80, format="%.3f"),
                "Range": st.column_config.TextColumn("Range", width=70),
                "Shaft": st.column_config.CheckboxColumn("Shaft", disabled=True, width=70),
                "Magic": st.column_config.CheckboxColumn("Magic", disabled=True, width=70),
                "Repeat": st.column_config.NumberColumn("Repeat", disabled=True, width=70),
                "Node": st.column_config.CheckboxColumn("Node", disabled=True, width=70),
                "Ignore Block": st.column_config.CheckboxColumn("Ignore Block", disabled=True, width=80),
                "Condition": st.column_config.TextColumn("Condition", width=140),
                "Text": st.column_config.TextColumn("Text", width="large"),
            }

            att_order = [
                "Select", "Item", "Stamina", "Dice", "Min", "Max", "Avg", "Avg/Stam",
                "Range", "Shaft", "Magic", "Repeat", "Node", "Ignore Block", "Condition", "Text",
            ]

            # Show data editor using the display frame; ensure Select column exists in disp
            if "Select" not in disp.columns:
                disp["Select"] = [False] * len(disp)

            # Keep index (RowId) and pass display frame to editor
            edited = st.data_editor(
                disp[att_order],
                key="cm_table_attacks",
                hide_index=True,
                width="stretch",
                disabled=[c for c in att_order if c != "Select"],
                column_config=att_cfg,
                column_order=att_order,
                num_rows="fixed",
            )

            # Derive item_id from RowId: "<item_id>::atk::<n>"
            item_id_series = edited.index.to_series().apply(lambda s: str(s).split("::atk::", 1)[0])

            attack_item_ids = sorted(set(item_id_series.tolist()))
            attack_item_set = set(attack_item_ids)

            # Maintain stable ordering based on current hand table order
            attack_visible_order = [iid for iid in hand_order if iid in attack_item_set]

            prev_ids = list(ss.get("cm_selected_hand_ids") or [])
            prev_set = set(prev_ids)

            selected_after = set(prev_set)
            for iid in attack_item_ids:
                mask = item_id_series == iid
                vals = list(edited.loc[mask, "Select"])
                was = iid in prev_set
                if was:
                    # any unchecked row indicates user intent to deselect the item
                    if any(v is False for v in vals):
                        selected_after.discard(iid)
                else:
                    # any checked row indicates user intent to select the item
                    if any(v is True for v in vals):
                        selected_after.add(iid)

            chosen_visible = [iid for iid in attack_visible_order if iid in selected_after]

            ss["cm_selected_hand_ids"] = _merge_visible_selection(
                prev_ids=prev_ids,
                chosen_visible_ids=chosen_visible,
                visible_order=attack_visible_order,
            )
            ss["cm_selected_hand_ids"] = _normalize_hand_selection(
                ss["cm_selected_hand_ids"],
                items_by_id=hand_by_id,
                stable_order=hand_order,
            )

    with tab_armor:
        # --- Armor filters live here now ---
        armor_pool_for_options = _filter_items(
            armor_items,
            active_expansions=active,
            class_name=class_name,
            stats=stats,
            query="",
            expansion_filter=expansion_filter,
            source_type_filter=source_type_filter,
            source_entity_filter=source_entity_filter,
            legendary_mode=legendary_mode,
        )

        armor_dodge_opts = sorted({_armor_dodge_int(x) for x in armor_pool_for_options})
        armor_slot_opts = sorted({_armor_upgrade_slots_int(x) for x in armor_pool_for_options})
        armor_immunity_opts = sorted({x for it in armor_pool_for_options for x in _immunities_set(it)})

        with st.expander("Armor filters", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                prev = ss.get("cm_af_dodge") or armor_dodge_opts
                default = [x for x in prev if x in armor_dodge_opts] or armor_dodge_opts
                af_dodge = st.multiselect("Dodge dice", options=armor_dodge_opts, default=armor_dodge_opts, key="cm_af_dodge")

                prev = ss.get("cm_af_slots") or armor_slot_opts
                default = [x for x in prev if x in armor_slot_opts] or armor_slot_opts
                af_slots = st.multiselect("Upgrade slots", options=armor_slot_opts, default=armor_slot_opts, key="cm_af_slots")

            with c2:
                prev = ss.get("cm_af_immunities") or []
                default = [x for x in prev if x in armor_immunity_opts]  # empty = show everything
                af_immunities = st.multiselect(
                    "Immunities (match any)",
                    options=armor_immunity_opts,
                    default=default,
                    key="cm_af_immunities",
                )

                _sr_opts = ["Any", "Has special rules", "No special rules"]
                cur = ss.get("cm_af_special") or "Any"
                if cur not in _sr_opts:
                    cur = "Any"
                af_special = st.radio(
                    "Special rules",
                    options=_sr_opts,
                    index=_sr_opts.index(cur),
                    horizontal=True,
                    key="cm_af_special",
                )

        armor_filter_dodge = set(int(x) for x in af_dodge) if af_dodge else None
        armor_filter_slots = set(int(x) for x in af_slots) if af_slots else None
        armor_any_immunities = set(af_immunities or [])
        armor_special_mode = af_special

        filtered_armor_base = _filter_items(
            armor_items,
            active_expansions=active,
            class_name=class_name,
            stats=stats,
            query=query,
            expansion_filter=expansion_filter,
            source_type_filter=source_type_filter,
            source_entity_filter=source_entity_filter,
            legendary_mode=legendary_mode,
        )
        filtered_armor = _apply_armor_filters(
            filtered_armor_base,
            dodge_dice=armor_filter_dodge,
            upgrade_slots=armor_filter_slots,
            any_immunities=armor_any_immunities,
            special_rules_mode=armor_special_mode,
        )
        armor_order = [_id(x) for x in filtered_armor]

        prev_armor_id = ss.get("cm_selected_armor_id") or ""

        armor_cfg = {
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Block": st.column_config.TextColumn("Block", width=95),
            "Resist": st.column_config.TextColumn("Resist", width=95),
            "Dodge": st.column_config.TextColumn("Dodge", width=70),
            "Upg Slots": st.column_config.NumberColumn("Slots", width=60),
            "Text": st.column_config.TextColumn("Text", width="large"),
        }

        armor_col_order = [
            "Select", "Name",
            "Block", "Resist", "Dodge",
            "Upg Slots", "Text",
            "STR", "DEX", "INT", "FAI",
            "Legendary", "Expansions", "SourceType", "SourceEntity",
        ]

        chosen = _render_selection_table(
            items=filtered_armor,
            selected_ids=[prev_armor_id],
            single_select=True,
            key="cm_table_armor",
            rows_fn=_rows_for_armor_table,
            column_config_override=armor_cfg,
            column_order=armor_col_order,
        )

        # If the user clears the selection (chosen == []), treat as no armor selected
        new_armor_id = chosen[0] if chosen else ""
        if new_armor_id != prev_armor_id:
            ss["cm_selected_armor_id"] = new_armor_id
            ss["cm_selected_armor_upgrade_ids"] = []

    with tab_wu:
        if not ss["cm_selected_hand_ids"]:
            st.info("Select hand items to attach weapon upgrades.")
        else:
            wu_map: Dict[str, List[str]] = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
            selected_hand_set = set(ss["cm_selected_hand_ids"])

            # prune removed hands + prune invalid upgrade ids (state hygiene)
            for hid in list(wu_map.keys()):
                if hid not in selected_hand_set:
                    wu_map.pop(hid, None)
            for hid in ss["cm_selected_hand_ids"]:
                wu_map[hid] = [x for x in (wu_map.get(hid) or []) if x in wu_by_id]

            ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

            for hid in ss["cm_selected_hand_ids"]:
                h = hand_by_id.get(hid) or {}
                prev = list(wu_map.get(hid) or [])
                extra = sum(_extra_upgrade_slots(wu_by_id.get(uid) or {}) for uid in prev)
                cap = _upgrade_slots(h) + int(extra)
                if cap <= 0:
                    continue
                with st.expander(f"{_name(h)} (upgrade slots: {cap})", expanded=False):
                    chosen = _render_selection_table(
                        items=filtered_wu,
                        selected_ids=prev,
                        single_select=False,
                        key=f"cm_weapon_up_{hid}",
                    )
                    wu_map[hid] = _merge_visible_selection(
                        prev_ids=prev,
                        chosen_visible_ids=chosen,
                        visible_order=wu_order,
                    )
            ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

    with tab_au:
        if not ss.get("cm_selected_armor_id"):
            st.info("Select an armor to attach armor upgrades.")
            ss["cm_selected_armor_upgrade_ids"] = []
        else:
            armor_obj = armor_by_id.get(ss.get("cm_selected_armor_id") or "") or {}
            armor_capacity = _upgrade_slots(armor_obj)
            st.caption(f"Armor upgrade slots: {armor_capacity}")

            if armor_capacity <= 0:
                st.info("Selected armor has no upgrade slots.")
                ss["cm_selected_armor_upgrade_ids"] = []
            else:
                prev = list(ss.get("cm_selected_armor_upgrade_ids") or [])
                chosen = _render_selection_table(
                    items=filtered_au,
                    selected_ids=prev,
                    single_select=False,
                    key="cm_armor_upgrades_table",
                )
                ss["cm_selected_armor_upgrade_ids"] = _merge_visible_selection(
                    prev_ids=prev,
                    chosen_visible_ids=chosen,
                    visible_order=au_order,
                )


    # --- Final reconcile (no legality enforcement) ---
    ss["cm_selected_hand_ids"] = _normalize_hand_selection(
        list(ss.get("cm_selected_hand_ids") or []),
        items_by_id=hand_by_id,
        stable_order=hand_order,
    )

    ss["cm_selected_armor_upgrade_ids"] = _ordered_unique(
        list(ss.get("cm_selected_armor_upgrade_ids") or []),
        stable_order=au_order,
    )

    wu_map: Dict[str, List[str]] = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
    selected_hand_set = set(ss["cm_selected_hand_ids"])

    # prune upgrades for removed hands (state hygiene, not legality)
    for hid in list(wu_map.keys()):
        if hid not in selected_hand_set:
            wu_map.pop(hid, None)

    for hid in ss["cm_selected_hand_ids"]:
        wu_map[hid] = _ordered_unique(list(wu_map.get(hid) or []), stable_order=wu_order)

    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

    # Enforce equip legality: remove items that no longer meet requirements
    # (e.g., stats lowered or expansions disabled). This keeps the build
    # consistent when the user changes class/tier/expansions.
    removed = {"armor": [], "armor_upgrades": [], "hands": [], "weapon_upgrades": []}
    # Armor
    armor_id = ss.get("cm_selected_armor_id") or ""
    if armor_id:
        aobj = armor_by_id.get(armor_id)
        if aobj:
            a_issues = _eligibility_issues(aobj, stats=stats, active=active)
            if a_issues:
                removed["armor"].append(aobj.get("name") or armor_id)
                ss["cm_selected_armor_id"] = ""
                ss["cm_selected_armor_upgrade_ids"] = []

    # Armor upgrades
    au_ids = list(ss.get("cm_selected_armor_upgrade_ids") or [])
    kept_au = []
    for uid in au_ids:
        u = au_by_id.get(uid)
        if not u:
            continue
        u_issues = _eligibility_issues(u, stats=stats, active=active)
        if u_issues:
            removed["armor_upgrades"].append(u.get("name") or uid)
        else:
            kept_au.append(uid)
    ss["cm_selected_armor_upgrade_ids"] = _ordered_unique(kept_au, stable_order=au_order)

    # Hands and their weapon upgrades
    hand_ids = list(ss.get("cm_selected_hand_ids") or [])
    new_hand_ids: List[str] = []
    for hid in hand_ids:
        h = hand_by_id.get(hid)
        if not h:
            continue
        h_issues = _eligibility_issues(h, stats=stats, active=active)
        if h_issues:
            removed["hands"].append(h.get("name") or hid)
            # drop associated weapon upgrades
            if hid in wu_map:
                for uid in wu_map.get(hid) or []:
                    u = wu_by_id.get(uid)
                    if u:
                        removed["weapon_upgrades"].append(u.get("name") or uid)
                wu_map.pop(hid, None)
        else:
            # prune weapon upgrades for this hand that are no longer valid
            kept_wus: List[str] = []
            for uid in (wu_map.get(hid) or []):
                u = wu_by_id.get(uid)
                if not u:
                    continue
                u_issues = _eligibility_issues(u, stats=stats, active=active)
                if u_issues:
                    removed["weapon_upgrades"].append(u.get("name") or uid)
                else:
                    kept_wus.append(uid)
            wu_map[hid] = _ordered_unique(kept_wus, stable_order=wu_order)
            new_hand_ids.append(hid)

    ss["cm_selected_hand_ids"] = _normalize_hand_selection(new_hand_ids, items_by_id=hand_by_id, stable_order=hand_order)
    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map

    # Inform the user about removals
    msgs = []
    for k, v in removed.items():
        if v:
            msgs.append(f"{k.replace('_', ' ').title()}: " + ", ".join(v))
    if msgs:
        st.info("Removed items due to changed eligibility:\n- " + "\n- ".join(msgs))

    # Recompute and render Totals now that selections are reconciled
    # Gather selected objects (may be empty)
    armor_id = ss.get("cm_selected_armor_id") or ""
    armor_obj = armor_by_id.get(armor_id) if armor_id else None
    armor_upgrade_objs = [au_by_id[uid] for uid in (ss.get("cm_selected_armor_upgrade_ids") or []) if uid in au_by_id]

    selected_hand_ids = list(ss.get("cm_selected_hand_ids") or [])
    selected_hand_objs = [hand_by_id[hid] for hid in selected_hand_ids if hid in hand_by_id]

    wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
    selected_weapon_upgrade_objs = []
    for hid in selected_hand_ids:
        for uid in (wu_map.get(hid) or []):
            if uid in wu_by_id:
                selected_weapon_upgrade_objs.append(wu_by_id[uid])

    # --- Side-by-side compare UI ---
    snap_names = ["<Current>"] + list(ss.get("cm_builds", {}).keys())
    st.markdown("#### Compare Builds")
    cl, cr = st.columns(2)
    with cl:
        left_choice = st.selectbox("Left build", options=snap_names, key="cm_compare_left")
    with cr:
        right_choice = st.selectbox("Right build", options=snap_names, key="cm_compare_right")

    if left_choice == right_choice:
        st.warning("Select two different builds to compare.")
    
    def _build_preview_from_build(data: dict):
        if not data:
            return None
        bclass = data.get("class_name")
        btiers = data.get("tier_indices") or {}
        bstats = _build_stats(bclass, btiers)
        # lookup items
        b_armor = (armor_by_id.get(data.get("selected_armor_id")) if data.get("selected_armor_id") else None)
        b_armor_upgrades = [au_by_id[uid] for uid in (data.get("selected_armor_upgrade_ids") or []) if uid in au_by_id]
        b_hand_ids = list(data.get("selected_hand_ids") or [])
        b_hand_objs = [hand_by_id[hid] for hid in b_hand_ids if hid in hand_by_id]
        b_wu_by_hand = {hid: [wu_by_id[uid] for uid in (data.get("selected_weapon_upgrade_ids_by_hand") or {}).get(hid, []) if uid in wu_by_id] for hid in b_hand_ids}
        b_wu_list = [wu for lst in b_wu_by_hand.values() for wu in lst]

        b_def = build_defense_totals_cached(
            armor_obj=b_armor, armor_upgrade_objs=b_armor_upgrades, hand_objs=b_hand_objs, weapon_upgrade_objs=b_wu_list
        )
        b_atk_rows = build_attack_totals_rows_cached(
            hand_items=b_hand_objs,
            selected_hand_ids=set(b_hand_ids),
            armor_obj=b_armor,
            armor_upgrade_objs=b_armor_upgrades,
            weapon_upgrades_by_hand=b_wu_by_hand,
        )
        return {
            "class": bclass,
            "tiers": btiers,
            "stats": bstats,
            "def": b_def,
            "atk_rows": b_atk_rows,
            "armor": b_armor,
            "hands": b_hand_objs,
            "wu_by_hand": b_wu_by_hand,
            "armor_upgrades": b_armor_upgrades,
        }

    left_snap = _current_build() if left_choice == "<Current>" else ss.get("cm_builds", {}).get(left_choice)
    right_snap = _current_build() if right_choice == "<Current>" else ss.get("cm_builds", {}).get(right_choice)

    # Single defense simulator controls for comparison
    st.markdown("#### Comparison Simulator")
    comp_c1, comp_c2 = st.columns(2)
    with comp_c1:
        incoming_cmp = st.slider("Incoming damage", min_value=2, max_value=15, value=6, step=1, key="cm_compare_incoming")
    with comp_c2:
        dodge_diff_cmp = st.slider("Dodge difficulty", min_value=1, max_value=5, value=2, step=1, key="cm_compare_dodge_diff")

    left_preview = _build_preview_from_build(left_snap)
    right_preview = _build_preview_from_build(right_snap)

    def _stats_str(sts: Dict[str, int]) -> str:
        return f"Strength: {sts.get('str')}, Dexterity: {sts.get('dex')}, Intelligence: {sts.get('itl')}, Faith: {sts.get('fth')}"

    def _render_preview_column(preview: dict, title: str):
        if not preview:
            st.markdown(f"**{title}**")
            st.caption("No build selected")
            return
        st.markdown(f"**{title}**")
        st.markdown(f"{_stats_str(preview.get('stats') or {})}")
        if preview.get('armor'):
            st.markdown(f"Armor: {preview['armor'].get('name')}")

        # Show aggregate defenses per valid equip combination:
        # - all pairs of 1-hand items
        # - each 2-hand item on its own
        hands = preview.get('hands') or []
        wu_by_hand = preview.get('wu_by_hand') or {}
        one_hands = [h for h in hands if _hands_required(h) == 1]
        two_hands = [h for h in hands if _hands_required(h) == 2]

        def _render_def_for(h_objs: List[dict], title_suffix: str):
            # collect weapon upgrades for these hands
            wus = [wu for hid in ([_id(h) for h in h_objs]) for wu in (wu_by_hand.get(hid) or [])]
            dtot = build_defense_totals_cached(armor_obj=preview.get('armor'), armor_upgrade_objs=preview.get('armor_upgrades') or [], hand_objs=h_objs, weapon_upgrade_objs=wus)
            # For combos, dodge is armor dodge plus the sum of the hands' dodge dice
            sum_hand_dodge = sum(_hand_dodge_int(h) for h in h_objs)
            eff_dodge = int(dtot.dodge_armor) + int(sum_hand_dodge)
            b_stats = _dice_min_max_avg(dtot.block)
            r_stats = _dice_min_max_avg(dtot.resist)
            st.markdown(f"**{title_suffix}**")
            st.markdown(f"- Dodge:\t{_dodge_icons(eff_dodge)} (armor {dtot.dodge_armor} + hands {sum_hand_dodge})")
            st.markdown(f"- Block:\t{_dice_icons(dtot.block)} (avg {b_stats['avg']:.2f})")
            st.markdown(f"- Resist:\t{_dice_icons(dtot.resist)} (avg {r_stats['avg']:.2f})")
            sim_block = expected_damage_taken(incoming_damage=incoming_cmp, dodge_dice=eff_dodge, dodge_difficulty=dodge_diff_cmp, defense_dice=dtot.block)
            sim_resist = expected_damage_taken(incoming_damage=incoming_cmp, dodge_dice=eff_dodge, dodge_difficulty=dodge_diff_cmp, defense_dice=dtot.resist)
            st.markdown(f"- Expected damage (physical/block): {sim_block['exp_taken']:.2f}, (magic/resist): {sim_resist['exp_taken']:.2f}")

        # Pairs of one-hand items
        if len(one_hands) >= 2:
            st.markdown("**Two 1-hand combos:**")
            for a, b in itertools.combinations(one_hands, 2):
                _render_def_for([a, b], f"{a.get('name')} + {b.get('name')}")

        # Single 2-hand items
        if two_hands:
            st.markdown("**2-hand items:**")
            for h in two_hands:
                _render_def_for([h], f"{h.get('name')}")

        # Attacks summary
        atk_rows = preview.get('atk_rows') or []
        if atk_rows:
            vals = [float(r.get('TotAvg') or 0) for r in atk_rows]
            avg_atk = sum(vals) / len(vals) if vals else 0.0
            st.markdown(f"**Attacks:** {len(atk_rows)} lines, avg damage per attack: {avg_atk:.2f}")

    cL, cR = st.columns(2)
    with cL:
        _render_preview_column(left_preview, "Left build")
    with cR:
        _render_preview_column(right_preview, "Right build")

    def_tot = build_defense_totals_cached(
        armor_obj=armor_obj,
        armor_upgrade_objs=armor_upgrade_objs,
        hand_objs=selected_hand_objs,
        weapon_upgrade_objs=selected_weapon_upgrade_objs,
    )

    dodge_effective = max(int(def_tot.dodge_armor), 0) + max(int(def_tot.dodge_hand_max), 0)

    # Total attack lines for selected items (includes armor + upgrades)
    weapon_upgrades_by_hand = {
        hid: [wu_by_id[uid] for uid in (wu_map.get(hid) or []) if uid in wu_by_id]
        for hid in selected_hand_ids
    }
    atk_rows = build_attack_totals_rows_cached(
        hand_items=selected_hand_objs,
        selected_hand_ids=set(selected_hand_ids),
        armor_obj=armor_obj,
        armor_upgrade_objs=armor_upgrade_objs,
        weapon_upgrades_by_hand=weapon_upgrades_by_hand,
    )

    with left_summary_slot.container():
        # Validate the current build and show warnings if any
        validation_errors = _validate_build(
            stats=stats,
            active=active,
            armor_id=ss.get("cm_selected_armor_id") or "",
            armor_upgrade_ids=list(ss.get("cm_selected_armor_upgrade_ids") or []),
            hand_ids=list(ss.get("cm_selected_hand_ids") or []),
            weapon_upgrade_ids_by_hand=dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {}),
            hand_by_id=hand_by_id,
            armor_by_id=armor_by_id,
            wu_by_id=wu_by_id,
            au_by_id=au_by_id,
        )
        if validation_errors:
            st.warning("Build validation issues:\n- " + "\n- ".join(validation_errors))

        # List selected items under Totals
        lines = []
        armor_id = ss.get("cm_selected_armor_id") or ""
        if armor_id and armor_id in armor_by_id:
            a = armor_by_id[armor_id]
            lines.append(a.get("name"))
            for uid in (ss.get("cm_selected_armor_upgrade_ids") or []):
                u = au_by_id.get(uid)
                if u:
                    lines.append(f"  - {u.get('name')}")

        # Hands and weapon upgrades (annotate weapon upgrades with parent hand name)
        for hid in list(ss.get("cm_selected_hand_ids") or []):
            h = hand_by_id.get(hid)
            if not h:
                continue
            lines.append(f"{h.get('name')}")
            for uid in (ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {}).get(hid, []):
                wu = wu_by_id.get(uid)
                if wu:
                    lines.append(f"  - {wu.get('name')} ({h.get('name')})")

        if lines:
            st.markdown("#### Selected Items")
            for l in lines:
                st.markdown(f"- {l}")

        df_atk = pd.DataFrame(atk_rows)
        disp_atk = df_atk.copy()
        disp_atk["Stamina"] = disp_atk.get("TotStam") if "TotStam" in disp_atk.columns else disp_atk.get("Stam")
        disp_atk["Dice"] = disp_atk.get("TotDice") if "TotDice" in disp_atk.columns else disp_atk.get("Dice")
        disp_atk["Min"] = disp_atk.get("TotMin") if "TotMin" in disp_atk.columns else disp_atk.get("TotMin")
        disp_atk["Max"] = disp_atk.get("TotMax") if "TotMax" in disp_atk.columns else disp_atk.get("TotMax")
        disp_atk["Avg"] = disp_atk.get("TotAvg") if "TotAvg" in disp_atk.columns else disp_atk.get("TotAvg")

        def _avg_per_stam_row(r):
            s = r.get("Stamina") or 0
            a = r.get("Avg") or 0
            return float(a) / float(s) if float(s) != 0 else 0.0

        disp_atk["Avg/Stam"] = disp_atk.apply(_avg_per_stam_row, axis=1)
        disp_atk["Push"] = disp_atk.get("Push")
        if "Ign Blk" in disp_atk.columns:
            disp_atk["Ignore Block"] = disp_atk["Ign Blk"]
        elif "IgnBlk" in disp_atk.columns:
            disp_atk["Ignore Block"] = disp_atk["IgnBlk"]
        else:
            disp_atk["Ignore Block"] = False

        if "Cond" in disp_atk.columns:
            disp_atk["Conditions"] = disp_atk["Cond"]
        elif "TotCond" in disp_atk.columns:
            disp_atk["Conditions"] = disp_atk["TotCond"]
        else:
            disp_atk["Conditions"] = ""

        # Coerce Repeat to numeric so missing/invalid values show blank
        disp_atk["Repeat"] = pd.to_numeric(disp_atk.get("Repeat"), errors="coerce")

        # Also show combo-based defenses under Totals
        st.markdown("#### Combos")
        one_hands = [h for h in selected_hand_objs if _hands_required(h) == 1]
        two_hands = [h for h in selected_hand_objs if _hands_required(h) == 2]
        twohand_compatible_shields = [h for h in selected_hand_objs if _is_twohand_compatible_shield(h)]

        def _render_def_combo(h_objs: List[dict], title: str):
            # collect weapon upgrades attached to these hand items
            wus = []
            for h in h_objs:
                hid = _id(h)
                wus.extend(weapon_upgrades_by_hand.get(hid) or [])
            dt = build_defense_totals_cached(armor_obj=armor_obj, armor_upgrade_objs=armor_upgrade_objs, hand_objs=h_objs, weapon_upgrade_objs=wus)
            # For combos we sum hand dodge values (not the max)
            sum_hand_dodge = sum(_hand_dodge_int(h) for h in h_objs)
            eff_dodge = int(dt.dodge_armor) + int(sum_hand_dodge)
            b_stats = _dice_min_max_avg(dt.block)
            r_stats = _dice_min_max_avg(dt.resist)
            st.markdown(f"**{title}**")
            st.markdown(
                f"""
                <ul style="list-style:none; padding-left:0; margin:0;">
                <li><span style="display:inline-block; width:3.5rem; font-weight:600">Dodge:</span> {_dodge_icons(eff_dodge)} <span style="color:#bfb79f">(armor {dt.dodge_armor} + hands {sum_hand_dodge})</span></li>
                <li><span style="display:inline-block; width:3.5rem; font-weight:600">Block:</span> {_dice_icons(dt.block)} <span style="color:#bfb79f">(avg {b_stats['avg']:.2f})</span></li>
                <li><span style="display:inline-block; width:3.5rem; font-weight:600">Resist:</span> {_dice_icons(dt.resist)} <span style="color:#bfb79f">(avg {r_stats['avg']:.2f})</span></li>
                </ul>
                """,
                unsafe_allow_html=True,
            )
            sim_incoming = ss.get("cm_sim_incoming", 6)
            sim_diff = ss.get("cm_sim_dodge_diff", 2)
            sim_block = expected_damage_taken(incoming_damage=sim_incoming, dodge_dice=eff_dodge, dodge_difficulty=sim_diff, defense_dice=dt.block)
            sim_resist = expected_damage_taken(incoming_damage=sim_incoming, dodge_dice=eff_dodge, dodge_difficulty=sim_diff, defense_dice=dt.resist)
            st.markdown(f"- Expected damage (physical/block): {sim_block['exp_taken']:.2f}, (magic/resist): {sim_resist['exp_taken']:.2f}")
            # Attack info for this combo (dice icons and avg per attack)
            # Compute combo-specific attack rows so per-attack mods from the
            # items participating in the combo (e.g., catalysts) are applied
            # to partner attacks only when the provider is included.
            combo_wu_by_hand = { _id(h): weapon_upgrades_by_hand.get(_id(h)) or [] for h in h_objs }
            combo_rows = build_attack_totals_rows_cached(
                hand_items=h_objs,
                selected_hand_ids=set([_id(h) for h in h_objs]),
                armor_obj=armor_obj,
                armor_upgrade_objs=armor_upgrade_objs,
                weapon_upgrades_by_hand=combo_wu_by_hand,
                apply_other_hand_attack_mods=True,
            )
            if combo_rows:
                df_combo = pd.DataFrame(combo_rows)
                # coerce Repeat to numeric so missing shows blank
                if 'Repeat' in df_combo.columns:
                    df_combo['Repeat'] = pd.to_numeric(df_combo.get('Repeat'), errors='coerce')
                pref = ["Item", "Atk#", "TotStam", "TotDice", "TotMin", "TotMax", "TotAvg", "TotCond", "Range", "Magic", "Node", "Shaft", "Push", "Repeat", "Text"]
                disp_cols = [c for c in pref if c in df_combo.columns]
                st.dataframe(df_combo[disp_cols], hide_index=True, width="stretch", height=140)

        if len(one_hands) >= 2:
            for a, b in itertools.combinations(one_hands, 2):
                _render_def_combo([a, b], f"{a.get('name')} + {b.get('name')}")
                st.markdown("---")

        if two_hands or twohand_compatible_shields:
            for h in two_hands:
                # single 2-hand item
                if not twohand_compatible_shields:
                    _render_def_combo([h], f"{h.get('name')}")
                    st.markdown("---")
                # pair 2-hand item with any shields marked usable with 2-hander
                for sh in twohand_compatible_shields:
                    _render_def_combo([h, sh], f"{h.get('name')} + {sh.get('name')}")
                    st.markdown("---")

    # --- Selected Items + validation (handled above in Totals) ---

    # Damage simulator + effects live in the right column summary slot
    with summary_slot.container():
        st.markdown("#### Defense Simulator")
        incoming = st.slider("Incoming damage", min_value=2, max_value=15, value=6, step=1, key="cm_sim_incoming")
        diff = st.slider("Dodge difficulty", min_value=1, max_value=5, value=2, step=1, key="cm_sim_dodge_diff")

        sim_incoming = ss.get("cm_sim_incoming", 6)
        sim_diff = ss.get("cm_sim_dodge_diff", 2)
        sim_block = expected_damage_taken(incoming_damage=sim_incoming, dodge_dice=dodge_effective, dodge_difficulty=sim_diff, defense_dice=def_tot.block)
        sim_resist = expected_damage_taken(incoming_damage=sim_incoming, dodge_dice=dodge_effective, dodge_difficulty=sim_diff, defense_dice=def_tot.resist)

        st.markdown(f"**Dodge success:** {sim_block['p_dodge']*100:.1f}%")
        st.markdown(f"**Expected damage taken (physical/block):** {sim_block['exp_taken']:.2f} (if dodge fails: {sim_block['exp_after_def']:.2f})")
        st.markdown(f"**Expected damage taken (magic/resist):** {sim_resist['exp_taken']:.2f} (if dodge fails: {sim_resist['exp_after_def']:.2f})")

        st.markdown("#### Effects")
        effects = []

        def _add_eff(x, source=None):
            s = str(x or '').strip()
            if not s:
                return
            if source:
                effects.append(f"{s} — {source}")
            else:
                effects.append(s)

        # Count how many hands have any weapon upgrades attached
        hands_with_wu = [hid for hid in selected_hand_ids if (wu_map.get(hid) or [])]
        multi_weapon_wu = len(hands_with_wu) > 1

        if armor_obj:
            _add_eff(armor_obj.get('text'), source=armor_obj.get('name'))
            for imm in (armor_obj.get('immunities') or []):
                _add_eff(f"Immunity: {imm}", source=armor_obj.get('name'))

        for u in armor_upgrade_objs:
            _add_eff(u.get('text'), source=u.get('name'))
            for imm in (u.get('immunities') or []):
                _add_eff(f"Immunity: {imm}", source=u.get('name'))

        for h in selected_hand_objs:
            _add_eff(h.get('text'), source=h.get('name'))
            for imm in (h.get('immunities') or []):
                _add_eff(f"Immunity: {imm}", source=h.get('name'))

        # Weapon upgrades: iterate by hand so we can include the parent hand name when needed
        for hid in selected_hand_ids:
            hand = hand_by_id.get(hid)
            hand_name = hand.get('name') if hand else None
            for uid in (wu_map.get(hid) or []):
                u = wu_by_id.get(uid)
                if not u:
                    continue
                # If multiple weapons have upgrades, include which weapon this upgrade is attached to
                if multi_weapon_wu and hand_name:
                    src = f"{u.get('name')} on {hand_name}"
                else:
                    src = u.get('name')
                _add_eff(u.get('text'), source=src)
                for imm in (u.get('immunities') or []):
                    _add_eff(f"Immunity: {imm}", source=src)

        effects = list(dict.fromkeys([e for e in effects if e]))
        if effects:
            for e in effects:
                st.markdown(f"- {e}")
        else:
            st.caption("No effects found on selected items.")




