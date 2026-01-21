#ui/sidebar.py
import streamlit as st
from core.settings_manager import save_settings, _has_supabase_config
from core import supabase_store
import time
import uuid
from core.characters import CHARACTER_EXPANSIONS
from core.ngplus import MAX_NGPLUS_LEVEL, _HP_4_TO_7_BONUS, dodge_bonus_for_level
from core.enemies import ENEMY_EXPANSIONS_BY_ID
from ui.encounter_mode.assets import enemyNames
from ui.encounter_mode.generation import editedEncounterKeywords

all_expansions = [
    "Painted World of Ariamis",
    "The Sunless City",
    "Tomb of Giants",
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep",
    "Characters Expansion",
    "Phantoms",
    "Executioner's Chariot",
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
]
INVADER_CAP_CLAMP = {1: 2, 2: 3, 3: 5, 4: 4}
CARD_WIDTH_MIN = 240
CARD_WIDTH_MAX = 560
CARD_WIDTH_DEFAULT = 380

if "sidebar_ngplus_expanded" not in st.session_state:
    st.session_state.sidebar_ngplus_expanded = False


def _ngplus_level_changed():
    st.session_state.sidebar_ngplus_expanded = True


def _sync_invader_caps():
    settings = st.session_state.get("user_settings") or {}
    caps = settings.get("max_invaders_per_level")
    if not isinstance(caps, dict):
        caps = {}
    out = {}
    for lvl, mx in INVADER_CAP_CLAMP.items():
        out[str(lvl)] = int(st.session_state.get(f"cap_invaders_lvl_{lvl}", mx))
    settings["max_invaders_per_level"] = out
    st.session_state["user_settings"] = settings
    save_settings(settings)


def render_sidebar(settings: dict):
    st.sidebar.header("Settings")

    # Use the live session copy of user_settings when available so
    # changes made elsewhere (e.g. toggling an encounter) appear
    # immediately in the sidebar without waiting for a full rerun.
    settings = st.session_state.get("user_settings", settings) or {}

    caps = settings.get("max_invaders_per_level") or {}

    # Expansions
    with st.sidebar.expander("🧩 Expansions", expanded=False):
        active_expansions = st.multiselect(
            "Active Expansions:",
            all_expansions,
            default=settings.get("active_expansions", []),
            key="active_expansions",
        )
        settings["active_expansions"] = active_expansions

    # Characters
    available_characters = sorted(
        c for c, exps in CHARACTER_EXPANSIONS.items()
        if any(exp in active_expansions for exp in exps)
    )

    previous_selection = settings.get("selected_characters", [])
    still_valid = [c for c in previous_selection if c in available_characters]
    if len(still_valid) < len(previous_selection):
        removed = [c for c in previous_selection if c not in still_valid]
        st.sidebar.warning(f"Removed invalid characters: {', '.join(removed)}")
        settings["selected_characters"] = still_valid

    with st.sidebar.expander("🎭 Party", expanded=False):
        selected_characters = st.multiselect(
            "Selected Characters (max 4):",
            options=available_characters,
            default=settings.get("selected_characters", []),
            max_selections=4,
            key="selected_characters",
        )
        settings["selected_characters"] = selected_characters

    # --- New Game+ selection ---
    if "sidebar_ngplus_expanded" not in st.session_state:
        st.session_state["sidebar_ngplus_expanded"] = False

    def _ngplus_level_changed():
        st.session_state["sidebar_ngplus_expanded"] = True

    current_ng = int(st.session_state.get("ngplus_level", 0))

    with st.sidebar.expander(
        f"⬆️ New Game+ (Current: NG+{current_ng})",
        expanded=bool(st.session_state.get("sidebar_ngplus_expanded", False)),
    ):
        level = st.number_input(
            "NG+ Level",
            min_value=0,
            max_value=MAX_NGPLUS_LEVEL,
            value=max(0, min(int(current_ng), MAX_NGPLUS_LEVEL)),
            step=1,
            key="ngplus_level",
            on_change=_ngplus_level_changed,
        )
        lvl = int(level)

        # Compute nodes added at this NG+ level (per-level mapping)
        extra_map = [0, 1, 1, 2, 2, 3]
        nodes_added = extra_map[lvl] if 0 <= lvl < len(extra_map) else 0

        # Optional: increase AoE node counts for Mega Bosses per NG+ level
        prev_increase = bool(settings.get("ngplus_increase_nodes", False))
        checkbox_label = "Increase AoE node count with NG+ (Mega bosses only)"

        increase_nodes = st.checkbox(
            checkbox_label,
            value=prev_increase,
            key="ngplus_increase_nodes",
        )
        settings["ngplus_increase_nodes"] = bool(increase_nodes)
        st.session_state["user_settings"] = settings
        save_settings(settings)

        if lvl > 0:
            dodge_b = dodge_bonus_for_level(lvl)
            if dodge_b == 1:
                dodge_text = "+1 to dodge difficulty."
            elif dodge_b == 2:
                dodge_text = "+2 to dodge difficulty."

            # NG+ summary text
            st.markdown(
                "\n".join(
                    [
                        f"- Base HP 1-3: +{lvl}",
                        f"- Base HP 4-7: +{_HP_4_TO_7_BONUS[lvl]}",
                        f"- Base HP 8-10: +{lvl*2}",
                        f"- Base HP 11+: +{lvl*10}% (rounded up)",
                        f"- +{lvl} damage to all attacks.",
                        f"- +{nodes_added} node{'s' if nodes_added != 1 else ''}", " to Mega Boss AoE patterns.",
                    ]
                    + ([f"- {dodge_text}"] if dodge_b > 0 else [])
                )
            )

    # Enemy selection (global): group by expansion and let user enable/disable enemies
    # Applies to both Encounter Mode and Campaign Mode generation.
    with st.sidebar.expander("🛡️ Enemy Selection", expanded=False):
        active_expansions = settings.get("active_expansions") or []
        if not active_expansions:
            st.caption("Enable expansions to pick available enemies.")
        else:
            # Build reverse map: expansion -> list of eid
            exp_map: dict = {}
            # Special combined expander for enemies that appear in both base game and Sunless City
            DSBG = "Dark Souls The Board Game"
            SUN = "The Sunless City"
            COMBO = f"{DSBG} & {SUN}"
            combo_list: list[int] = []

            for eid, exps in ENEMY_EXPANSIONS_BY_ID.items():
                # consider only expansions that are currently active
                exps_active = [exp for exp in exps if exp in active_expansions]
                if not exps_active:
                    continue
                # If enemy appears in both DSBG and Sunless City, place it in the combined list
                if DSBG in exps_active and SUN in exps_active:
                    combo_list.append(int(eid))
                    continue
                # Otherwise, add to each individual expansion that is active
                for exp in exps_active:
                    exp_map.setdefault(exp, []).append(int(eid))

            # If combo_list has entries and at least one of the two expansions is active,
            # add the combined expander to the map under a dedicated key.
            if combo_list and (DSBG in active_expansions or SUN in active_expansions):
                exp_map[COMBO] = combo_list

            # Ensure settings key exists
            settings.setdefault("enemy_included", {})
            included = settings.get("enemy_included") or {}

            # Render expanders per expansion
            seen = set()
            # Ensure the combined expander (if present) appears near the top
            ordered_exps = sorted([e for e in exp_map.keys() if e != COMBO])
            if COMBO in exp_map:
                ordered_exps = [COMBO] + ordered_exps

            for exp in ordered_exps:
                with st.expander(f"{exp}", expanded=False):
                    eids = sorted(exp_map.get(exp, []), key=lambda x: enemyNames.get(x, str(x)))
                    for idx, eid in enumerate(eids):
                        name = enemyNames.get(eid, str(eid))
                        # Only render an interactive checkbox the first time we see this enemy.
                        # If the same enemy appears under multiple expansions, show a non-interactive
                        # label in subsequent expansion groups to avoid duplicate widget keys.
                        if eid in seen:
                            st.write(f"{name}  ", unsafe_allow_html=False)
                            continue

                        seen.add(eid)
                        key = f"enemy_incl_{eid}"
                        # Persist keys as strings for JSON safety
                        default_val = bool(included.get(str(eid), True))
                        val = st.checkbox(name, value=default_val, key=key)
                        included[str(eid)] = bool(val)

            # Mirror changes back into settings/session
            settings["enemy_included"] = included
            st.session_state["user_settings"] = settings

    # Invaders
    with st.sidebar.expander("⚔️ Encounter Invader Cap", expanded=False):
        for lvl, mx in INVADER_CAP_CLAMP.items():
            cur = caps.get(str(lvl), mx)
            cur = int(cur)
            cur = max(0, min(cur, mx))
            st.slider(
                f"Level {lvl}",
                min_value=0,
                max_value=mx,
                value=cur,
                key=f"cap_invaders_lvl_{lvl}",
                on_change=_sync_invader_caps,
            )

    # One-time init for the widget key (must happen BEFORE st.slider is created)
    if "ui_card_width" not in st.session_state:
        st.session_state["ui_card_width"] = int(settings.get("ui_card_width", 360))

        # Encounter item reward shuffle setting
        # Options control how encounters that specify a particular item reward are handled.
        # Persist the choice in user_settings as `encounter_item_reward_mode`.
        modes = [
            "Similar Soul Cost",
            "Same Item Tier",
            "Original",
        ]
        prev_mode = settings.get("encounter_item_reward_mode", "Original")
        with st.sidebar.expander("💎 Item Swap", expanded=False):
            mode = st.selectbox(
                "When an encounter rewards a specific item, treat it as:",
                options=modes,
                index=modes.index(prev_mode) if prev_mode in modes else modes.index("Original"),
                key="encounter_item_reward_mode",
            )
            settings["encounter_item_reward_mode"] = mode
            st.session_state["user_settings"] = settings
            save_settings(settings)

    # Rules display preference: show phase-only rules/triggers only in their phase
    prev_rules_pref = bool(settings.get("rules_show_only_in_phase", True))
    with st.sidebar.expander("⚙️ Rule/Trigger Display", expanded=False):
        rules_pref = st.checkbox(
            "Only show rules/triggers when relevant (player or enemy phase). This only affects the Play tab.",
            value=prev_rules_pref,
            key="rules_show_only_in_phase",
        )
        settings["rules_show_only_in_phase"] = bool(rules_pref)
        st.session_state["user_settings"] = settings

    # Edited encounters: global toggle + per-encounter status
    with st.sidebar.expander("✏️ Edited Encounters", expanded=False):
        settings.setdefault("edited_toggles", {})

        def _edited_global_changed():
            # Called when the global edited-encounters checkbox changes.
            curr = bool(st.session_state.get("edited_encounters_global", False))
            settings.setdefault("edited_toggles", {})
            # Apply the global setting to all known edited encounter toggles
            for enc_name, enc_exp in sorted(editedEncounterKeywords):
                k = f"{enc_name}|{enc_exp}"
                settings["edited_toggles"][k] = curr
                # Also update the per-encounter checkbox widget state so
                # the checkbox in the Encounter setup reflects this change
                widget_key = f"edited_toggle_{enc_name}_{enc_exp}"
                st.session_state[widget_key] = curr
            settings["edited_encounters_global"] = curr
            st.session_state["user_settings"] = settings
            save_settings(settings)

        prev_global = bool(settings.get("edited_encounters_global", False))
        # Checkbox is persisted in session state so it remains across reruns
        st.checkbox(
            "Enable edited encounters (global)",
            value=prev_global,
            key="edited_encounters_global",
            on_change=_edited_global_changed,
        )

        st.markdown("**Edited encounters available:**")
        if not editedEncounterKeywords:
            st.caption("No edited encounters available.")
        else:
            # Show list with status emoji
            edited_list = sorted(editedEncounterKeywords, key=lambda t: (t[1], t[0]))
            # Read toggles from the live session settings so changes elsewhere
            # are visible immediately.
            toggles = st.session_state.get("user_settings", {}).get("edited_toggles", {})
            for enc_name, enc_exp in edited_list:
                k = f"{enc_name}|{enc_exp}"
                # Prefer the live per-encounter checkbox widget state if present
                widget_key = f"edited_toggle_{enc_name}_{enc_exp}"
                if widget_key in st.session_state:
                    enabled = bool(st.session_state.get(widget_key, False))
                else:
                    enabled = bool(toggles.get(k, False))
                emoji = "✅" if enabled else "❌"
                st.write(f"{emoji} {enc_name} ({enc_exp})")

    with st.sidebar.expander("🖼️ Card Display", expanded=False):
        st.slider(
            "Card width (px)",
            min_value=240,
            max_value=560,
            step=10,
            key="ui_card_width",
            value=int(st.session_state["ui_card_width"]),
        )
        st.caption("This scales the size of boss cards and event cards in Encounter Mode's Event tab.")

    # Sync widget -> persisted settings (mutate IN PLACE, do not replace settings dict)
    settings["ui_card_width"] = int(st.session_state["ui_card_width"])

    # Session + persisted UI controls
    # Initialize from settings if present so the choice persists across runs
    if "ui_compact" not in st.session_state:
        st.session_state["ui_compact"] = bool(settings.get("ui_compact", False))

    with st.sidebar.expander("📱 UI", expanded=False):
        st.checkbox("Compact layout (mobile)", key="ui_compact")

    # Persist the compact toggle into the settings dict (and session_state)
    settings["ui_compact"] = bool(st.session_state.get("ui_compact", False))
    st.session_state["user_settings"] = settings
