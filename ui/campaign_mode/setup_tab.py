#ui/campaign_mode/setup_tab.py
import streamlit as st
from typing import Any, Dict
from ui.campaign_mode.api import (
    filter_bosses,
    generate_v1_campaign,
    generate_v2_campaign,
    get_campaigns,
    save_campaigns,
    default_sparks_max,
)
from ui.campaign_mode.state import _get_player_count, _ensure_v1_state, _ensure_v2_state


def _render_setup_header(settings: Dict[str, Any]) -> tuple[str, int]:
    player_count = _get_player_count(settings)
    options = ["V1", "V2"]
    current = st.session_state.get("campaign_rules_version", "V1")
    if current not in options:
        current = "V1"
    index = options.index(current)

    # Widget uses a different key so we can freely mutate campaign_rules_version.
    # Only provide `index` the first time the widget is created; passing
    # `index` on every render can interfere with the widget's internal state
    # and cause clicks to require multiple presses to take effect.
    radio_kwargs = {"options": options, "horizontal": True, "key": "campaign_rules_version_widget"}
    if "campaign_rules_version_widget" not in st.session_state:
        radio_kwargs["index"] = index
    version = st.radio("Rules version", **radio_kwargs)

    # This is now safe; no widget with this key exists
    st.session_state["campaign_rules_version"] = version

    st.markdown("---")
    return version, player_count


def _render_v1_setup(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    player_count: int,
) -> Dict[str, Any]:
    state = _ensure_v1_state(player_count)
    active_expansions = settings.get("active_expansions") or []

    mini_bosses = filter_bosses(
        bosses_by_name,
        boss_type="mini boss",
        active_expansions=active_expansions,
    )
    main_bosses = filter_bosses(
        bosses_by_name,
        boss_type="main boss",
        active_expansions=active_expansions,
    )
    mega_bosses = filter_bosses(
        bosses_by_name,
        boss_type="mega boss",
        active_expansions=active_expansions,
    )

    if bool(st.session_state.get("ui_compact")):
        cols = [st.container(), st.container(), st.container()]
    else:
        cols = st.columns(3)


    # Mini boss
    with cols[0]:
        st.markdown("**Mini Boss**")
        if not mini_bosses:
            st.caption("No mini bosses available with current expansions.")
            state["bosses"]["mini"] = "Random"
        else:
            mini_names = [b["name"] for b in mini_bosses]
            mini_options = ["Random"] + mini_names
            current = state["bosses"].get("mini", "Random")
            if current not in mini_options:
                current = "Random"
            mini_choice = st.selectbox(
                "Mini boss",
                options=mini_options,
                index=mini_options.index(current),
                key="campaign_v1_mini_boss",
            )
            state["bosses"]["mini"] = mini_choice

    # Main boss
    with cols[1]:
        st.markdown("**Main Boss**")
        if not main_bosses:
            st.caption("No main bosses available with current expansions.")
            state["bosses"]["main"] = "Random"
        else:
            main_names = [b["name"] for b in main_bosses]
            main_options = ["Random"] + main_names
            current = state["bosses"].get("main", "Random")
            if current not in main_options:
                current = "Random"
            main_choice = st.selectbox(
                "Main boss",
                options=main_options,
                index=main_options.index(current),
                key="campaign_v1_main_boss",
            )
            state["bosses"]["main"] = main_choice

    # Mega boss
    with cols[2]:
        st.markdown("**Mega Boss**")
        if not mega_bosses:
            st.caption("No mega bosses available with current expansions.")
            state["bosses"]["mega"] = "None"
        else:
            mega_names = [b["name"] for b in mega_bosses]
            mega_options = ["None", "Random"] + mega_names
            current = state["bosses"].get("mega", "None")
            if current not in mega_options:
                current = "None"
            mega_choice = st.selectbox(
                "Mega boss (optional)",
                options=mega_options,
                index=mega_options.index(current),
                key="campaign_v1_mega_boss",
            )
            state["bosses"]["mega"] = mega_choice

    # --- Generate full campaign encounters (frozen) ---
    # Option: only use original enemy lists when building encounters
    if "only_original_enemies" not in state:
        state["only_original_enemies"] = False
    only_original = st.checkbox(
        "Only use original enemies (do not select alternative enemy sets)",
        value=bool(state.get("only_original_enemies", False)),
        key="campaign_v1_only_original_enemies",
    )
    state["only_original_enemies"] = bool(only_original)
    # Mirror into settings so campaign generation code can read it
    settings["only_original_enemies_for_campaigns"] = bool(only_original)

    if st.button("Generate campaign ⚙️", key="campaign_v1_generate", width="stretch"):
        with st.spinner("Generating campaign..."):
            campaign = generate_v1_campaign(bosses_by_name, settings, state)
        state["campaign"] = campaign
        player_count = _get_player_count(settings)
        sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))
        state["sparks_max"] = sparks_max
        state["sparks"] = sparks_max
        sparks_key = "campaign_v1_sparks_campaign"
        st.session_state[sparks_key] = sparks_max
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0
        st.session_state["campaign_v1_state"] = state
        st.success("Campaign generated.")

    st.markdown("### Campaign overview")

    def describe_slot(label: str, slot_key: str) -> str:
        sel = state["bosses"].get(slot_key, "Random" if slot_key != "mega" else "None")
        if sel == "Random":
            return f"{label}: Random (boss revealed when reached)"
        if slot_key == "mega" and sel == "None":
            return f"{label}: None selected"
        return f"{label}: {sel}"

    st.markdown(f"- **{describe_slot('Mini boss', 'mini')}**")
    st.markdown(f"- **{describe_slot('Main boss', 'main')}**")
    st.markdown(f"- **{describe_slot('Mega boss', 'mega')}**")

    return state


def _render_v2_setup(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    player_count: int,
) -> Dict[str, Any]:
    """
    V2 Setup:
    - Same boss-selection controls as V1 for now.
    - Campaign generation creates encounter spaces with two choices each.
    """
    state = _ensure_v2_state(player_count)
    active_expansions = settings.get("active_expansions") or []

    mini_bosses = filter_bosses(
        bosses_by_name,
        boss_type="mini boss",
        active_expansions=active_expansions,
    )
    main_bosses = filter_bosses(
        bosses_by_name,
        boss_type="main boss",
        active_expansions=active_expansions,
    )
    mega_bosses = filter_bosses(
        bosses_by_name,
        boss_type="mega boss",
        active_expansions=active_expansions,
    )

    if bool(st.session_state.get("ui_compact")):
        cols = [st.container(), st.container(), st.container()]
    else:
        cols = st.columns(3)

    # Mini boss
    with cols[0]:
        st.markdown("**Mini Boss**")
        if not mini_bosses:
            st.caption("No mini bosses available with current expansions.")
            state["bosses"]["mini"] = "Random"
        else:
            mini_names = [b["name"] for b in mini_bosses]
            mini_options = ["Random"] + mini_names
            current = state["bosses"].get("mini", "Random")
            if current not in mini_options:
                current = "Random"
            mini_choice = st.selectbox(
                "Mini boss",
                options=mini_options,
                index=mini_options.index(current),
                key="campaign_v2_mini_boss",
            )
            state["bosses"]["mini"] = mini_choice

    # Main boss
    with cols[1]:
        st.markdown("**Main Boss**")
        if not main_bosses:
            st.caption("No main bosses available with current expansions.")
            state["bosses"]["main"] = "Random"
        else:
            main_names = [b["name"] for b in main_bosses]
            main_options = ["Random"] + main_names
            current = state["bosses"].get("main", "Random")
            if current not in main_options:
                current = "Random"
            main_choice = st.selectbox(
                "Main boss",
                options=main_options,
                index=main_options.index(current),
                key="campaign_v2_main_boss",
            )
            state["bosses"]["main"] = main_choice

    # Mega boss
    with cols[2]:
        st.markdown("**Mega Boss**")
        if not mega_bosses:
            st.caption("No mega bosses available with current expansions.")
            state["bosses"]["mega"] = "None"
        else:
            mega_names = [b["name"] for b in mega_bosses]
            mega_options = ["None", "Random"] + mega_names
            current = state["bosses"].get("mega", "None")
            if current not in mega_options:
                current = "None"
            mega_choice = st.selectbox(
                "Mega boss (optional)",
                options=mega_options,
                index=mega_options.index(current),
                key="campaign_v2_mega_boss",
            )
            state["bosses"]["mega"] = mega_choice

    # Option: only use original enemy lists when building encounters (V2)
    if "only_original_enemies" not in state:
        state["only_original_enemies"] = False
    only_original = st.checkbox(
        "Only use original enemies (do not select alternative enemy sets)",
        value=bool(state.get("only_original_enemies", False)),
        key="campaign_v2_only_original_enemies",
    )
    state["only_original_enemies"] = bool(only_original)
    # Mirror into settings so campaign generation reads it immediately
    settings["only_original_enemies_for_campaigns"] = bool(only_original)

    if st.button("Generate campaign ⚙️", key="campaign_v2_generate", width="stretch"):
        with st.spinner("Generating V2 campaign..."):
            # Mirror v2-only original-enemy option into settings as well
            if "only_original_enemies" not in state:
                state["only_original_enemies"] = False
            settings["only_original_enemies_for_campaigns"] = bool(state.get("only_original_enemies", False))
            campaign = generate_v2_campaign(bosses_by_name, settings, state)
        state["campaign"] = campaign
        player_count = _get_player_count(settings)
        sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))
        state["sparks_max"] = sparks_max
        state["sparks"] = sparks_max
        sparks_key = "campaign_v2_sparks_campaign"
        st.session_state[sparks_key] = sparks_max
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0
        st.session_state["campaign_v2_state"] = state
        st.success("Campaign generated.")

    st.markdown("### Campaign overview")

    def describe_slot(label: str, slot_key: str) -> str:
        sel = state["bosses"].get(slot_key, "Random" if slot_key != "mega" else "None")
        if sel == "Random":
            return f"{label}: Random (boss revealed when reached)"
        if slot_key == "mega" and sel == "None":
            return f"{label}: None selected"
        return f"{label}: {sel}"

    st.markdown(f"- **{describe_slot('Mini boss', 'mini')}**")
    st.markdown(f"- **{describe_slot('Main boss', 'main')}**")
    st.markdown(f"- **{describe_slot('Mega boss', 'mega')}**")

    st.session_state["campaign_v2_state"] = state
    return state


def _render_save_load_section(
    version: str,
    current_state: Dict[str, Any],
    settings: Dict[str, Any],
) -> None:
    st.markdown("---")
    st.subheader("Save / Load campaign")

    campaigns = get_campaigns()

    if bool(st.session_state.get("ui_compact")):
        col_save = st.container()
        col_load = st.container()
    else:
        col_save, col_load = st.columns([1, 1])


    # ----- SAVE -----
    with col_save:
        default_name = str(current_state.get("name", "")).strip()
        name_input = st.text_input(
            "Campaign name",
            value=default_name,
            key=f"campaign_name_{version}",
        )

        if st.button("Save campaign 💾", key=f"campaign_save_{version}", width="stretch"):
            name = name_input.strip()
            if not name:
                st.error("Campaign name is required to save.")
            else:
                # For campaign rules versions that rely on an explicit node track
                # (V1 and V2), require a generated campaign so Campaign can resume.
                if version in ("V1", "V2") and not isinstance(
                    current_state.get("campaign"), dict
                ):
                    st.error(
                        "Generate the campaign before saving; "
                        "this save currently has no encounters."
                    )
                else:
                    current_state["name"] = name
                    snapshot = {
                        "rules_version": version,
                        "state": current_state,
                        "sidebar_settings": {
                            "active_expansions": settings.get("active_expansions"),
                            "selected_characters": settings.get("selected_characters"),
                            "ngplus_level": int(
                                st.session_state.get("ngplus_level", 0)
                            ),
                        },
                    }
                    campaigns[name] = snapshot
                    save_campaigns(campaigns)
                    st.success(f"Saved campaign '{name}'.")

    # ----- LOAD / DELETE -----
    with col_load:
        if campaigns:
            names = sorted(campaigns.keys())
            selected_name = st.selectbox(
                "Existing campaigns",
                options=["<none>"] + names,
                index=0,
                key=f"campaign_load_select_{version}",
            )

            if bool(st.session_state.get("ui_compact")):
                load_col = st.container()
                delete_col = st.container()
            else:
                load_col, delete_col = st.columns([1, 1])


            with load_col:
                if st.button(
                    "Load selected campaign",
                    key=f"campaign_load_btn_{version}",
                    width="stretch"
                ):
                    if selected_name != "<none>":
                        snapshot = campaigns[selected_name]
                        st.session_state["pending_campaign_snapshot"] = {
                            "name": selected_name,
                            "snapshot": snapshot,
                        }
                        st.rerun()

            with delete_col:
                if st.button(
                    "Delete selected",
                    key=f"campaign_delete_btn_{version}",
                    width="stretch"
                ):
                    if selected_name == "<none>":
                        st.error("Select a campaign to delete.")
                    else:
                        campaigns.pop(selected_name, None)
                        save_campaigns(campaigns)
                        st.success(f"Deleted campaign '{selected_name}'.")
                        st.rerun()
        else:
            st.caption("No saved campaigns yet.")

        # One-shot notice: appears directly under the load controls
        notice = st.session_state.pop("campaign_load_notice", None)
        if notice:
            name = notice.get("name") or "Unnamed"
            changes = notice.get("changes") or []
            if changes:
                st.success(
                    f"Loaded campaign '{name}' and updated: "
                    + ", ".join(changes)
                    + "."
                )
            else:
                st.success(f"Loaded campaign '{name}' (no sidebar changes).")
