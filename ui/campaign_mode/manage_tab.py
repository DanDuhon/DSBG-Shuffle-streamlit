#ui/campaign_mode/manage_tab.py
import streamlit as st
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from ui.behavior_decks_tab.assets import BEHAVIOR_CARDS_PATH
from ui.behavior_decks_tab.generation import render_data_card_cached, render_dual_boss_data_cards
from ui.campaign_mode.core import BONFIRE_ICON_PATH, PARTY_TOKEN_PATH, _default_sparks_max, _describe_v1_node_label, _describe_v2_node_label, _v2_compute_allowed_destinations
from ui.campaign_mode.state import _get_settings, _get_player_count
from ui.campaign_mode.ui_helpers import _render_party_icons
from ui.encounters_tab.render import render_original_encounter


def _render_campaign_tab(
    bosses_by_name: Dict[str, Any],
    invaders_by_name: Dict[str, Any],
) -> None:
    version = st.session_state.get("campaign_rules_version", "V1")

    if version == "V1":
        state = st.session_state.get("campaign_v1_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v1_campaign(state, bosses_by_name)
    else:
        state = st.session_state.get("campaign_v2_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v2_campaign(state, bosses_by_name)


def _render_v1_campaign(state: Dict[str, Any], bosses_by_name: Dict[str, Any]) -> None:
    """
    V1 Campaign tab:

    - Party icons at top
    - Sparks (display only)
    - Soul cache numeric input under Sparks
    - Path with Return to Bonfire / Travel / Confront
    - Party token on the current row
    - Right-hand panel with bonfire / encounter card / boss card
    """
    settings = _get_settings()

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("Generate a V1 campaign in the Setup tab to begin.")
        return

    nodes = campaign.get("nodes") or []
    if not nodes:
        st.info("Campaign has no nodes; regenerate it from the Setup tab.")
        return

    # Resolve current node
    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id", "bonfire")
    current_node = node_by_id.get(current_id) or nodes[0]
    campaign["current_node_id"] = current_node.get("id", "bonfire")
    state["campaign"] = campaign

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            # Party icons above everything
            _render_party_icons(settings)

            # Sparks: display only
            player_count = _get_player_count(settings)
            sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))
            sparks_cur = int(state.get("sparks", sparks_max))
            st.metric("Sparks", f"{sparks_cur} / {sparks_max}")

            # Soul cache directly under Sparks
            souls_key = "campaign_v1_souls_campaign"
            if souls_key not in st.session_state:
                st.session_state[souls_key] = int(state.get("souls", 0) or 0)

            souls_value = st.number_input(
                "Soul cache",
                min_value=0,
                step=1,
                key=souls_key,
            )
            state["souls"] = int(souls_value)

        st.markdown("---")
        st.markdown(
            f"**Current location:** "
            f"{_describe_v1_node_label(campaign, current_node)}"
        )

        st.markdown("#### Path")

        # Group nodes: bonfire, then chapters by stage, then any leftovers
        bonfire_nodes: List[Dict[str, Any]] = []
        stage_nodes: Dict[str, List[Dict[str, Any]]] = {
            "mini": [],
            "main": [],
            "mega": [],
        }
        other_nodes: List[Dict[str, Any]] = []

        for node in nodes:
            kind = node.get("kind")
            stage = node.get("stage")
            if kind == "bonfire":
                bonfire_nodes.append(node)
            elif stage in stage_nodes:
                stage_nodes[stage].append(node)
            else:
                other_nodes.append(node)

        # Bonfire stays at the top, outside any chapter
        for n in bonfire_nodes:
            _render_v1_path_row(n, campaign, state)

        mini_boss = stage_nodes["mini"][-1]
        main_boss = stage_nodes["main"][-1]
        mega_boss = [] if not stage_nodes["mega"] else stage_nodes["mega"][-1]

        chapter_labels = {
            "mini": "Unknown Mini Boss Chapter" if mini_boss["was_random"] and not mini_boss["revealed"] else f"{mini_boss['boss_name']} Chapter",
            "main": "Unknown Main Boss Chapter" if main_boss["was_random"] and not main_boss["revealed"] else f"{main_boss['boss_name']} Chapter",
        }

        if mega_boss:
            chapter_labels["mega"] = "Unknown Mega Boss Chapter" if mega_boss["was_random"] and not mega_boss["revealed"] else f"{mega_boss['boss_name']} Chapter"

        # Wrap mini/main/mega tracks in expanders
        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            with st.expander(chapter_labels[stage], expanded=True):
                for n in nodes_for_stage:
                    _render_v1_path_row(n, campaign, state)

        # Any nodes that don't belong to the known stages
        for n in other_nodes:
            _render_v1_path_row(n, campaign, state)

    with col_detail:
        _render_v1_current_panel(campaign, current_node)

    # Persist updated state
    st.session_state["campaign_v1_state"] = state


def _render_v2_campaign(state: Dict[str, Any], bosses_by_name: Dict[str, Any]) -> None:
    """
    V2 Campaign tab:

    - Same high-level layout as V1 (party, sparks, souls, path, current space).
    - Encounter spaces present a choice between two frozen encounters once you
      travel there for the first time.
    """
    settings = _get_settings()

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("Generate a V2 campaign in the Setup tab to begin.")
        return

    nodes = campaign.get("nodes") or []
    if not nodes:
        st.info("Campaign has no nodes; regenerate it from the Setup tab.")
        return

    # Resolve current node
    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id", "bonfire")
    current_node = node_by_id.get(current_id) or nodes[0]
    campaign["current_node_id"] = current_node.get("id", "bonfire")
    state["campaign"] = campaign

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            _render_party_icons(settings)

            player_count = _get_player_count(settings)
            sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))
            sparks_cur = int(state.get("sparks", sparks_max))
            st.metric("Sparks", f"{sparks_cur} / {sparks_max}")

            souls_key = "campaign_v2_souls_campaign"
            if souls_key not in st.session_state:
                st.session_state[souls_key] = int(state.get("souls", 0) or 0)

            souls_value = st.number_input(
                "Soul cache",
                min_value=0,
                step=1,
                key=souls_key,
            )
            state["souls"] = int(souls_value)

        st.markdown("---")
        st.markdown(
            f"**Current location:** "
            f"{_describe_v2_node_label(campaign, current_node)}"
        )

        # When standing on an encounter space, restrict legal destinations.
        allowed_destinations = _v2_compute_allowed_destinations(campaign)

        st.markdown("#### Path")

        bonfire_nodes: List[Dict[str, Any]] = []
        stage_nodes: Dict[str, List[Dict[str, Any]]] = {
            "mini": [],
            "main": [],
            "mega": [],
        }
        other_nodes: List[Dict[str, Any]] = []

        for node in nodes:
            kind = node.get("kind")
            stage = node.get("stage")
            if kind == "bonfire":
                bonfire_nodes.append(node)
            elif stage in stage_nodes:
                stage_nodes[stage].append(node)
            else:
                other_nodes.append(node)

        for n in bonfire_nodes:
            _render_v2_path_row(n, campaign, state, allowed_destinations)

        # Same chapter labelling logic as V1
        if stage_nodes["mini"]:
            mini_boss = stage_nodes["mini"][-1]
        else:
            mini_boss = None
        if stage_nodes["main"]:
            main_boss = stage_nodes["main"][-1]
        else:
            main_boss = None
        mega_boss = stage_nodes["mega"][-1] if stage_nodes["mega"] else None

        chapter_labels: Dict[str, str] = {}
        if mini_boss is not None:
            if mini_boss.get("was_random") and not mini_boss.get("revealed"):
                chapter_labels["mini"] = "Unknown Mini Boss Chapter"
            else:
                chapter_labels["mini"] = f"{mini_boss.get('boss_name', 'Mini Boss')} Chapter"

        if main_boss is not None:
            if main_boss.get("was_random") and not main_boss.get("revealed"):
                chapter_labels["main"] = "Unknown Main Boss Chapter"
            else:
                chapter_labels["main"] = f"{main_boss.get('boss_name', 'Main Boss')} Chapter"

        if mega_boss is not None:
            if mega_boss.get("was_random") and not mega_boss.get("revealed"):
                chapter_labels["mega"] = "Unknown Mega Boss Chapter"
            else:
                chapter_labels["mega"] = f"{mega_boss.get('boss_name', 'Mega Boss')} Chapter"

        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            with st.expander(chapter_labels[stage], expanded=True):
                for n in nodes_for_stage:
                    _render_v2_path_row(n, campaign, state, allowed_destinations)

        for n in other_nodes:
            _render_v2_path_row(n, campaign, state, allowed_destinations)

    with col_detail:
        _render_v2_current_panel(campaign, current_node, state)

    st.session_state["campaign_v2_state"] = state


def _render_v1_path_row(
    node: Dict[str, Any],
    campaign: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    label = _describe_v1_node_label(campaign, node)
    row_cols = st.columns([3, 1])

    with row_cols[0]:
        st.markdown(f"- {label}")

    with row_cols[1]:
        node_id = node.get("id")
        kind = node.get("kind")
        is_current = node_id == campaign.get("current_node_id")

        # Current location: show party token instead of any button
        if is_current:
            st.image(str(PARTY_TOKEN_PATH), width=48)
            return

        # Bonfire row: Return to Bonfire
        if kind == "bonfire":
            if st.button(
                "Return to Bonfire",
                key=f"campaign_v1_goto_{node_id}",
            ):
                campaign["current_node_id"] = node_id
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                st.rerun()
            return

        # Encounter / boss: Travel / Confront
        if kind in ("encounter", "boss"):
            btn_label = "Travel" if kind == "encounter" else "Confront"
            if st.button(btn_label, key=f"campaign_v1_goto_{node_id}"):
                campaign["current_node_id"] = node_id
                node["revealed"] = True
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                st.rerun()
            return


def _render_v2_path_row(
    node: Dict[str, Any],
    campaign: Dict[str, Any],
    state: Dict[str, Any],
    allowed_destinations: Optional[set[str]] = None,
) -> None:
    label = _describe_v2_node_label(campaign, node)
    row_cols = st.columns([3, 1])

    with row_cols[0]:
        st.markdown(f"- {label}")

    with row_cols[1]:
        node_id = node.get("id")
        kind = node.get("kind")
        is_current = node_id == campaign.get("current_node_id")
        status = node.get("status")

        # Current location: party token instead of a button
        if is_current:
            st.image(str(PARTY_TOKEN_PATH), width=48)
            return

        # Completed encounters/bosses are not travel destinations
        if kind in ("encounter", "boss") and status == "complete":
            # Keep the row label visible but expose no button
            return

        # When the party is currently on an encounter space, restrict where
        # they can travel next. If allowed_destinations is not None, only
        # nodes whose id is in that set are legal moves.
        can_travel_here = True
        if allowed_destinations is not None and node_id not in allowed_destinations:
            can_travel_here = False

        # Bonfire row: Return to Bonfire
        if kind == "bonfire":
            if not can_travel_here:
                return
            if st.button(
                "Return to Bonfire",
                key=f"campaign_v2_goto_{node_id}",
            ):
                campaign["current_node_id"] = node_id
                state["campaign"] = campaign
                st.session_state["campaign_v2_state"] = state
                st.rerun()
            return

        # Encounter / boss: Travel / Confront
        if kind in ("encounter", "boss") and can_travel_here:
            btn_label = "Travel" if kind == "encounter" else "Confront"
            if st.button(btn_label, key=f"campaign_v2_goto_{node_id}"):
                campaign["current_node_id"] = node_id
                node["revealed"] = True
                state["campaign"] = campaign
                st.session_state["campaign_v2_state"] = state
                st.rerun()
            return
        

def _render_v1_current_panel(
    campaign: Dict[str, Any],
    current_node: Dict[str, Any],
) -> None:
    """
    Right-hand panel for V1:
    - Bonfire: bonfire image
    - Encounter: card
    - Boss: fully rendered data card + 'Start Boss Fight' (jumps to Boss Mode)
    """
    kind = current_node.get("kind")
    st.markdown("#### Current space")

    # Bonfire
    if kind == "bonfire":
        st.caption("Resting at the bonfire.")
        return

    # Encounter (single fixed encounter in V1)
    if kind == "encounter":
        frozen = current_node.get("frozen") or {}
        _render_campaign_encounter_card(frozen)

    # Boss
    if kind == "boss":
        stage = current_node.get("stage")
        # Prefer the campaign's boss metadata, fall back to node field
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name") or current_node.get("boss_name")

        prefix_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
        prefix = prefix_map.get(stage, "Boss")

        if boss_name:
            st.markdown(f"**{prefix}: {boss_name}**")

            # Load raw behavior JSON directly
            json_path = Path("data") / "behaviors" / f"{boss_name}.json"
            raw_data = None
            if json_path.is_file():
                try:
                    with json_path.open("r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                except Exception as exc:
                    st.warning(f"Failed to load behavior JSON for '{boss_name}': {exc}")

            if raw_data is None:
                # Fallback: show static base data card
                data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                st.image(data_path, width="stretch")
            else:
                # Special case: Ornstein & Smough dual-boss card
                if "Ornstein" in boss_name and "Smough" in boss_name:
                    try:
                        o_img, s_img = render_dual_boss_data_cards(raw_data)
                        o_col, s_col = st.columns(2)
                        with o_col:
                            st.image(o_img, width="stretch")
                        with s_col:
                            st.image(s_img, width="stretch")
                    except Exception as exc:
                        st.warning(f"Failed to render Ornstein & Smough data cards: {exc}")
                else:
                    if boss_name == "Executioner's Chariot":
                        data_path = BEHAVIOR_CARDS_PATH + "Executioner's Chariot - Skeletal Horse.jpg"
                    else:
                        data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                    try:
                        img = render_data_card_cached(
                            data_path,
                            raw_data,
                            is_boss=True,
                        )
                        st.image(img, width="stretch")
                    except Exception as exc:
                        st.warning(f"Failed to render boss data card: {exc}")
        else:
            st.markdown(f"**{prefix}: Unknown**")
            st.caption("No boss selected for this space.")

        if st.button(
            "Start Boss Fight",
            key=f"campaign_v1_start_boss_{current_node.get('id')}",
        ):
            if not boss_name:
                st.warning("No boss configured for this node.")
            else:
                st.session_state["pending_boss_mode_from_campaign"] = {
                    "boss_name": boss_name
                }
                st.rerun()
        return

    st.caption("No details available for this space.")


def _render_v2_current_panel(
    campaign: Dict[str, Any],
    current_node: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    """
    Right-hand panel for V2:
    - Bonfire: same as V1.
    - Encounter: choice between up to two frozen encounters (once per space).
    - Boss: same as V1 (including Boss Mode handoff).
    """
    kind = current_node.get("kind")
    st.markdown("#### Current space")

    # Bonfire
    if kind == "bonfire":
        st.caption("Resting at the bonfire.")
        return

    # Encounter with choice
    if kind == "encounter":
        options = current_node.get("options") or []
        choice_idx = current_node.get("choice_index")

        if not options:
            st.caption("No encounter options attached to this space. Regenerate this campaign.")
            return

        # No choice yet: present options side-by-side
        if choice_idx is None:
            st.markdown("**Choose an encounter for this space**")

            cols = st.columns(len(options))
            for idx, frozen in enumerate(options):
                with cols[idx]:
                    _render_campaign_encounter_card(frozen)
                    if st.button(
                        f"Choose option {idx + 1}",
                        key=f"campaign_v2_choose_{current_node.get('id')}_{idx}",
                    ):
                        current_node["choice_index"] = idx
                        current_node["frozen"] = frozen
                        current_node["revealed"] = True
                        state["campaign"] = campaign
                        st.session_state["campaign_v2_state"] = state
                        st.rerun()
            return

        # Choice already made: behave like V1
        idx = int(choice_idx)
        if not (0 <= idx < len(options)):
            st.caption("Chosen encounter index is out of range; regenerate this campaign.")
            return

        frozen = options[idx]
        _render_campaign_encounter_card(frozen)
        
        return

    # Boss: identical to V1 logic
    _render_v1_current_panel(campaign, current_node)


def _render_campaign_encounter_card(frozen: Dict[str, Any]) -> None:
    """
    Shared helper to render a frozen campaign encounter card (V1 or V2).
    """
    expansion = frozen.get("expansion")
    level = frozen.get("encounter_level")
    name = frozen.get("encounter_name")
    enemies = frozen.get("enemies") or []

    if not expansion or level is None or not name:
        st.caption("Encounter card data incomplete.")
        return

    encounter_data = frozen.get("encounter_data")
    use_edited = bool(frozen.get("edited", False))

    if not encounter_data:
        st.warning("Missing encounter data; regenerate this campaign.")
        return

    res = render_original_encounter(
        encounter_data,
        expansion,
        name,
        level,
        use_edited,
        enemies=enemies,
    )
    if res and res.get("ok"):
        st.image(res["card_img"], width="stretch")
    else:
        st.warning("Failed to render encounter card.")
