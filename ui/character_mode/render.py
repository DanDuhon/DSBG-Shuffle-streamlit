# ui/character_mode/render.py
from __future__ import annotations
import pandas as pd
import streamlit as st
from typing import Any, Dict, List, Set
from ui.character_mode.build import _build_stats, _validate_build
from ui.character_mode.constants import CLASS_TIERS, HAND_CONDITION_OPTIONS, HAND_FEATURE_OPTIONS, TIERS
from ui.character_mode.data_io import _find_data_file, _load_json_list
from ui.character_mode.dice_math import _dice_icons, _dice_min_max_avg
from ui.character_mode.filters import _apply_armor_filters, _apply_hand_item_filters, _filter_items
from ui.character_mode.item_fields import _armor_dodge_int, _armor_upgrade_slots_int, _extra_upgrade_slots, _hand_dodge_int, _hand_hands_required_int, _hand_range_str, _hand_upgrade_slots_int, _hands_required, _id, _immunities_set, _item_expansions, _name, _slot_cost, _sorted_with_none_first, _src_str, _upgrade_slots
from ui.character_mode.selection import _merge_visible_selection, _normalize_hand_selection, _ordered_unique
from ui.character_mode.tables import _rows_for_armor_table, _rows_for_hand_table
from ui.character_mode.aggregates import build_attack_totals_rows, build_defense_totals, expected_damage_taken
from ui.character_mode.widgets import _render_selection_table


def render(settings: Dict[str, Any]) -> None:
    st.markdown("## Character Mode")

    active = set(x for x in (settings.get("active_expansions") or []))

    # Selection state
    ss = st.session_state
    ss.setdefault("cm_selected_armor_id", "")
    ss.setdefault("cm_selected_armor_upgrade_ids", [])
    ss.setdefault("cm_selected_hand_ids", [])
    ss.setdefault("cm_selected_weapon_upgrade_ids_by_hand", {})

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
        class_exps = sorted(x for x in cfg["expansions"])
        enabled_for_class = sorted(set(class_exps) & active)
        st.caption(
            "Class expansions: "
            + (", ".join(class_exps) if class_exps else "(none)")
            + " | Enabled for class: "
            + (", ".join(enabled_for_class) if enabled_for_class else "(none)")
        )

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

        tier_indices = {
            "str": st.radio("Strength tier", options=tier_opts, index=0, format_func=_fmt("str"), horizontal=True, key="cm_tier_str_i"),
            "dex": st.radio("Dexterity tier", options=tier_opts, index=0, format_func=_fmt("dex"), horizontal=True, key="cm_tier_dex_i"),
            "itl": st.radio("Intelligence tier", options=tier_opts, index=0, format_func=_fmt("itl"), horizontal=True, key="cm_tier_itl_i"),
            "fth": st.radio("Faith tier", options=tier_opts, index=0, format_func=_fmt("fth"), horizontal=True, key="cm_tier_fth_i"),
        }

        ss["cm_persist_tiers"] = dict(tier_indices)

        stats = _build_stats(class_name, tier_indices)

    with right:
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

    # Build options from items that are in enabled expansions
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
    armor_order: List[str] = []

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

        st.caption(f"{len(filtered_hand)} item(s)")
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

        attack_rows = build_attack_totals_rows(
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
            att_cfg = {
                "Select": st.column_config.CheckboxColumn("Select", width="small"),
                "Item": st.column_config.TextColumn("Item", width="medium"),
                "Dice": st.column_config.TextColumn("Dice", width=150),
                "TotDice": st.column_config.TextColumn("Tot Dice", width=170),
                "TotMin": st.column_config.NumberColumn("Tot Min", width=70),
                "TotMax": st.column_config.NumberColumn("Tot Max", width=70),
                "TotAvg": st.column_config.NumberColumn("Tot Avg", width=80, format="%.2f"),
                "TotCond": st.column_config.TextColumn("Tot Cond", width=140),
                "TotStam": st.column_config.NumberColumn("Tot Stam", width=80),
                "Range": st.column_config.TextColumn("Range", width=70),
                "Magic": st.column_config.CheckboxColumn("Magic", disabled=True, width=70),
                "Node": st.column_config.CheckboxColumn("Node", disabled=True, width=70),
                "Shaft": st.column_config.CheckboxColumn("Shaft", disabled=True, width=70),
                "Ign Blk": st.column_config.CheckboxColumn("Ign Blk", disabled=True, width=75),
                "Cond": st.column_config.TextColumn("Cond", width=90),
                "Text": st.column_config.TextColumn("Text", width="large"),
            }
            att_order = [
                "Select", "Item", "Atk#",
                "TotDice", "TotStam", "TotMin", "TotMax", "TotAvg", "TotCond",
                "Dice", "Stam", "Cond", "Text",
                "Magic", "Node", "Ign Blk", "Push", "Range", "Shaft", "Repeat",
            ]
            edited = st.data_editor(
                df,
                key="cm_table_attacks",
                hide_index=True,
                width="stretch",
                disabled=[c for c in df.columns if c != "Select"],
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

        st.caption(f"{len(filtered_armor)} item(s)")
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

        new_armor_id = chosen[0] if chosen else prev_armor_id
        if new_armor_id != prev_armor_id:
            ss["cm_selected_armor_id"] = new_armor_id
            ss["cm_selected_armor_upgrade_ids"] = []

    with tab_wu:
        st.caption(f"{len(filtered_wu)} item(s)")
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
        st.caption(f"{len(filtered_au)} item(s)")
        if not ss.get("cm_selected_armor_id"):
            st.info("Select an armor to attach armor upgrades.")
        else:
            armor_obj = armor_by_id.get(ss.get("cm_selected_armor_id") or "") or {}
            armor_capacity = _upgrade_slots(armor_obj)
            st.caption(f"Armor upgrade slots: {armor_capacity}")

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

    # --- Selected Items + validation (right column) ---
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

    with summary_slot.container():
        st.markdown("### Selected Items")

        if validation_errors:
            st.warning("Build is invalid:")
            for e in validation_errors:
                st.markdown(f"- {e}")

        # Armor
        armor_id = ss.get("cm_selected_armor_id") or ""
        armor_obj = armor_by_id.get(armor_id) if armor_id else None
        armor_capacity = _upgrade_slots(armor_obj or {})

        if armor_obj:
            arow = st.columns([8, 2])
            arow[0].markdown(f"**Armor:** {_name(armor_obj)}")
            if arow[1].button("Remove", key="cm_remove_armor"):
                ss["cm_selected_armor_id"] = ""
                ss["cm_selected_armor_upgrade_ids"] = []
                st.rerun()

            if ss["cm_selected_armor_upgrade_ids"]:
                used = sum(_slot_cost(au_by_id.get(x) or {}) for x in ss["cm_selected_armor_upgrade_ids"])
                st.caption(f"Armor upgrade slots: {armor_capacity} (used {used})")
                for uid in list(ss["cm_selected_armor_upgrade_ids"]):
                    u = au_by_id.get(uid) or {}
                    urow = st.columns([8, 2])
                    urow[0].markdown(f"- {_name(u)} (cost {_slot_cost(u)})")
                    if urow[1].button("Remove", key=f"cm_remove_armor_up_{uid}"):
                        ss["cm_selected_armor_upgrade_ids"] = [x for x in ss["cm_selected_armor_upgrade_ids"] if x != uid]
                        st.rerun()
        else:
            st.markdown("**Armor:** (none)")

        # Hand items
        if ss["cm_selected_hand_ids"]:
            st.markdown("**Hand Items:**")
            for hid in list(ss["cm_selected_hand_ids"]):
                h = hand_by_id.get(hid) or {}
                ups = list((ss["cm_selected_weapon_upgrade_ids_by_hand"].get(hid) or []))
                extra = sum(_extra_upgrade_slots(wu_by_id.get(uid) or {}) for uid in ups)
                cap = _upgrade_slots(h) + int(extra)
                hrow = st.columns([8, 2])
                hrow[0].markdown(
                    f"- {_name(h)} (hands {_hands_required(h)}, slot cost {_slot_cost(h)}, upgrade slots {cap})"
                )
                if hrow[1].button("Remove", key=f"cm_remove_hand_{hid}"):
                    ss["cm_selected_hand_ids"] = [x for x in ss["cm_selected_hand_ids"] if x != hid]
                    wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
                    wu_map.pop(hid, None)
                    ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map
                    st.rerun()
 
                for uid in ups:
                    u = wu_by_id.get(uid) or {}
                    urow = st.columns([8, 2])
                    urow[0].markdown(f"  - {_name(u)} (cost {_slot_cost(u)})")
                    if urow[1].button("Remove", key=f"cm_remove_wu_{hid}_{uid}"):
                        wu_map = dict(ss.get("cm_selected_weapon_upgrade_ids_by_hand") or {})
                        wu_map[hid] = [x for x in (wu_map.get(hid) or []) if x != uid]
                        ss["cm_selected_weapon_upgrade_ids_by_hand"] = wu_map
                        st.rerun()
        else:
            st.markdown("**Hand Items:** (none)")

        st.markdown("---")
        st.markdown("#### Totals")

        # Gather selected objects
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

        def_tot = build_defense_totals(
            armor_obj=armor_obj,
            armor_upgrade_objs=armor_upgrade_objs,
            hand_objs=selected_hand_objs,
            weapon_upgrade_objs=selected_weapon_upgrade_objs,
        )

        dodge_effective = max(int(def_tot.dodge_armor), 0) + max(int(def_tot.dodge_hand_max), 0)

        bstats = _dice_min_max_avg(def_tot.block)
        rstats = _dice_min_max_avg(def_tot.resist)

        st.markdown(f"**Dodge dice (effective):** {dodge_effective} (armor {def_tot.dodge_armor} + best hand {def_tot.dodge_hand_max})")
        st.markdown(f"**Block (total):** {_dice_icons(def_tot.block)} | min {bstats['min']:.0f}, max {bstats['max']:.0f}, avg {bstats['avg']:.2f}")
        st.markdown(f"**Resist (total):** {_dice_icons(def_tot.resist)} | min {rstats['min']:.0f}, max {rstats['max']:.0f}, avg {rstats['avg']:.2f}")

        # Total attack lines for selected items (includes armor + upgrades)
        weapon_upgrades_by_hand = {
            hid: [wu_by_id[uid] for uid in (wu_map.get(hid) or []) if uid in wu_by_id]
            for hid in selected_hand_ids
        }
        atk_rows = build_attack_totals_rows(
            hand_items=selected_hand_objs,
            selected_hand_ids=set(selected_hand_ids),
            armor_obj=armor_obj,
            armor_upgrade_objs=armor_upgrade_objs,
            weapon_upgrades_by_hand=weapon_upgrades_by_hand,
        )
        if atk_rows:
            df_atk = pd.DataFrame(atk_rows)
            cols = [c for c in ["Item", "Atk#", "TotStam", "TotDice", "TotMin", "TotMax", "TotAvg", "TotCond", "Range", "Magic", "Node", "Shaft", "Push", "Repeat", "Text"] if c in df_atk.columns]
            st.dataframe(df_atk[cols], hide_index=True, width="stretch")
        else:
            st.caption("No attack lines on selected items.")

        st.markdown("#### Damage Intake Simulator")
        incoming = st.slider("Incoming damage", min_value=2, max_value=15, value=6, step=1, key="cm_sim_incoming")
        diff = st.slider("Dodge difficulty", min_value=1, max_value=5, value=2, step=1, key="cm_sim_dodge_diff")

        sim_block = expected_damage_taken(incoming_damage=incoming, dodge_dice=dodge_effective, dodge_difficulty=diff, defense_dice=def_tot.block)
        sim_resist = expected_damage_taken(incoming_damage=incoming, dodge_dice=dodge_effective, dodge_difficulty=diff, defense_dice=def_tot.resist)

        st.markdown(f"**Dodge success:** {sim_block['p_dodge']*100:.1f}%")
        st.markdown(f"**Expected damage taken (physical/block):** {sim_block['exp_taken']:.2f} (if dodge fails: {sim_block['exp_after_def']:.2f})")
        st.markdown(f"**Expected damage taken (magic/resist):** {sim_resist['exp_taken']:.2f} (if dodge fails: {sim_resist['exp_after_def']:.2f})")

        st.markdown("#### Effects")
        effects = []

        def _add_eff(x):
            s = str(x or '').strip()
            if s:
                effects.append(s)

        if armor_obj:
            _add_eff(armor_obj.get('text'))
            for imm in (armor_obj.get('immunities') or []):
                _add_eff(f"Immunity: {imm}")

        for u in armor_upgrade_objs:
            _add_eff(u.get('text'))
            for imm in (u.get('immunities') or []):
                _add_eff(f"Immunity: {imm}")

        for h in selected_hand_objs:
            _add_eff(h.get('text'))
            for imm in (h.get('immunities') or []):
                _add_eff(f"Immunity: {imm}")

        for u in selected_weapon_upgrade_objs:
            _add_eff(u.get('text'))
            for imm in (u.get('immunities') or []):
                _add_eff(f"Immunity: {imm}")

        # Derived effects from attack lines
        for r in atk_rows or []:
            _add_eff(r.get('TotCond'))
            _add_eff(r.get('Text'))

        effects = list(dict.fromkeys([e for e in effects if e]))
        if effects:
            for e in effects:
                st.markdown(f"- {e}")
        else:
            st.caption("No effects found on selected items.")


