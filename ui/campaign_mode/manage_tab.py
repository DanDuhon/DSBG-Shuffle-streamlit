#ui/campaign_mode/manage_tab.py
import streamlit as st
import json
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.behavior.generation import render_data_card_cached, render_dual_boss_data_cards
from ui.campaign_mode.core import (
    BONFIRE_ICON_PATH,
    PARTY_TOKEN_PATH,
    SOULS_TOKEN_PATH,
    _default_sparks_max,
    _describe_v1_node_label,
    _describe_v2_node_label,
    _v2_compute_allowed_destinations,
    _reset_all_encounters_on_bonfire_return,
    _record_dropped_souls,
    _card_w,
    _v2_pick_scout_ahead_alt_frozen,
)
from ui.campaign_mode.state import _get_settings, _get_player_count
from ui.campaign_mode.ui_helpers import _render_party_icons
from ui.encounter_mode.setup_tab import render_original_encounter



_SCOUT_AHEAD_ID = "scout ahead"


def _frozen_sig(frozen: Dict[str, Any], default_level: int) -> Optional[tuple[str, int, str]]:
    """(expansion, level, encounter_name) signature for a frozen encounter."""
    if not isinstance(frozen, dict):
        return None
    try:
        exp = str(frozen.get("expansion") or "")
        lvl = int(frozen.get("encounter_level", default_level))
        name = str(frozen.get("encounter_name") or "")
    except Exception:
        return None
    if not exp or not name:
        return None
    return (exp, lvl, name)


def _is_scout_ahead_event(rv: Any) -> bool:
    if not isinstance(rv, dict):
        return False
    raw = str(rv.get("id") or rv.get("name") or "").strip().lower()
    return raw == _SCOUT_AHEAD_ID


def _consume_scout_ahead(current_node: Dict[str, Any]) -> None:
    rv = current_node.get("rendezvous_event")
    if not isinstance(rv, dict):
        return
    rid = str(rv.get("id") or rv.get("name") or "").strip().lower()
    if rid != "scout ahead":
        return

    # One-time effect: once a final encounter is chosen, Scout Ahead is spent.
    current_node.pop("rendezvous_event", None)
    current_node.pop("scout_ahead", None)


def _v2_cleanup_scout_ahead_if_unpicked(node: Dict[str, Any]) -> None:
    """
    If Scout Ahead was attached and we already appended an extra option, but the
    node still has no choice selected (choice_index is None), and the Scout Ahead
    rendezvous is no longer present, remove the extra option so the user can't
    pick it without the event.
    """
    if not isinstance(node, dict):
        return
    if node.get("choice_index") is not None:
        return

    sa = node.get("scout_ahead")
    if not isinstance(sa, dict):
        return

    base_count = sa.get("base_options_count")
    opts = node.get("options")
    if isinstance(base_count, int) and isinstance(opts, list) and base_count >= 0:
        node["options"] = opts[:base_count]

    node.pop("scout_ahead", None)


def _v2_ensure_scout_ahead_alt_option(
    *,
    node: Dict[str, Any],
    settings: Dict[str, Any],
    campaign: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Ensure a Scout Ahead node has a persistent additional option appended to
    node['options'] and return its choice index.

    Persists under node['scout_ahead'].
    """
    options = node.get("options")
    if not isinstance(options, list) or not options:
        return None

    level = node.get("level")
    try:
        lvl_int = int(level)
    except Exception:
        lvl_int = 1

    sa = node.get("scout_ahead")
    if not isinstance(sa, dict):
        sa = {}
        node["scout_ahead"] = sa

    # Record how many options existed before we appended the Scout Ahead alternative.
    if "base_options_count" not in sa:
        sa["base_options_count"] = len(options)

    # If we already generated an alt, ensure it exists in options and return its index.
    alt_frozen = sa.get("alt_frozen")
    alt_idx = sa.get("alt_choice_index")

    if isinstance(alt_frozen, dict):
        # Try to locate by signature if the stored index is stale.
        if isinstance(alt_idx, int) and 0 <= alt_idx < len(options):
            return alt_idx

        alt_sig = _frozen_sig(alt_frozen, lvl_int)
        if alt_sig is not None:
            for i, fr in enumerate(options):
                if _frozen_sig(fr, lvl_int) == alt_sig:
                    sa["alt_choice_index"] = i
                    return i

        # Not found: append it now.
        options.append(alt_frozen)
        sa["alt_choice_index"] = len(options) - 1
        return sa["alt_choice_index"]

    # Need to generate a new alt
    exclude: set[tuple[str, int, str]] = set()
    for fr in options:
        sig = _frozen_sig(fr, lvl_int)
        if sig is not None:
            exclude.add(sig)

    cand = _v2_pick_scout_ahead_alt_frozen(
        settings=settings,
        level=lvl_int,
        exclude_signatures=exclude,
        campaign=campaign,
    )
    if not isinstance(cand, dict):
        return None

    sa["alt_frozen"] = cand
    options.append(cand)
    sa["alt_choice_index"] = len(options) - 1

    # If we don't have a "previously chosen" base yet, default to the first original option.
    base_idx = sa.get("base_choice_index")
    if not isinstance(base_idx, int):
        sa["base_choice_index"] = 0

    return sa["alt_choice_index"]


def _is_stage_closed_for_node(campaign: Dict[str, Any], node: Dict[str, Any]) -> bool:
    """
    Return True if the chapter (stage) that this node belongs to is closed because
    its boss has been marked as complete.
    """
    stage = node.get("stage")
    if not stage:
        return False

    for n in campaign.get("nodes") or []:
        if n.get("kind") == "boss" and n.get("stage") == stage:
            return n.get("status") == "complete"
    return False


def _render_party_events_panel(state: Dict[str, Any]) -> None:
    instants = state.get("instant_events_unresolved") or []
    consumables = state.get("party_consumable_events") or []
    orphans = state.get("orphaned_rendezvous_events") or []

    if not instants and not consumables and not orphans:
        return

    # 4-column grid:
    # - Immediate events in left two columns
    # - Consumable events in right two columns
    c0, c1, c2, c3 = st.columns(4)

    if instants:
        with c0:
            st.markdown("**Immediate**")
    if consumables:
        with c2:
            st.markdown("**Consumable**")

    if isinstance(instants, list) and instants:
        cols = [c0, c1]
        for i, ev in enumerate(instants):
            if not isinstance(ev, dict) or not ev.get("path"):
                continue
            with cols[i % 2]:
                path_str = str(ev.get("path") or "")
                # Prefer embedding the file as a base64 data URI so the
                # image renders reliably across platforms/browsers.
                img_src = path_str
                try:
                    from pathlib import Path as _P
                    p = _P(path_str)
                    if p.is_file():
                        data = p.read_bytes()
                        import base64 as _b64
                        ext = p.suffix.lower()
                        mime = "image/png" if ext in (".png",) else "image/jpeg"
                        b64 = _b64.b64encode(data).decode()
                        img_src = f"data:{mime};base64,{b64}"
                except Exception:
                    img_src = path_str

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{img_src}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                nm = str(ev.get("name") or ev.get("id") or "").strip()
                if nm:
                    st.caption(nm)

    if isinstance(consumables, list) and consumables:
        cols = [c2, c3]
        for i, ev in enumerate(consumables):
            if not isinstance(ev, dict) or not ev.get("path"):
                continue
            with cols[i % 2]:
                path_str = str(ev.get("path") or "")
                img_src = path_str
                try:
                    from pathlib import Path as _P
                    p = _P(path_str)
                    if p.is_file():
                        data = p.read_bytes()
                        import base64 as _b64
                        ext = p.suffix.lower()
                        mime = "image/png" if ext in (".png",) else "image/jpeg"
                        b64 = _b64.b64encode(data).decode()
                        img_src = f"data:{mime};base64,{b64}"
                except Exception:
                    img_src = path_str

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{img_src}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                nm = str(ev.get("name") or ev.get("id") or "Consumable").strip()
                st.caption(nm)

    # Controls
    if instants:
        if st.button("Clear immediate event notifications", key="campaign_clear_instant_events", width="stretch"):
            state["instant_events_unresolved"] = []
            st.rerun()

    if orphans:
        st.markdown("**Rendezvous with no remaining encounter target**")
        for ev in orphans:
            if isinstance(ev, dict) and ev.get("name"):
                st.caption(str(ev["name"]))

                
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
    souls_token_node_id = state.get("souls_token_node_id")

    if bool(st.session_state.get("ui_compact")):
        _render_v1_campaign_compact(settings=settings, state=state, campaign=campaign, nodes=nodes, current_node=current_node)
        st.session_state["campaign_v1_state"] = state
        return

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            # Party icons above everything
            _render_party_icons(settings)

            # Sparks: editable numeric input
            player_count = _get_player_count(settings)
            sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))

            sparks_key = "campaign_v1_sparks_campaign"
            # Seed the widget from state only once, when the key does not exist yet.
            if sparks_key not in st.session_state:
                st.session_state[sparks_key] = int(state.get("sparks", sparks_max))

            sparks_value = st.number_input(
                "Sparks",
                min_value=0,
                max_value=sparks_max,
                step=1,
                key=sparks_key,
            )
            state["sparks"] = int(sparks_value)

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

        # Ensure expander state keys exist. By default: mini expanded, main/mega closed.
        for _stage in ("mini", "main", "mega"):
            exp_key = f"campaign_v1_chapter_expander_{_stage}"
            if exp_key not in st.session_state:
                st.session_state[exp_key] = True if _stage == "mini" else False

        # Wrap mini/main/mega tracks in expanders using session-state for expansion.
        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            exp_key = f"campaign_v1_chapter_expander_{stage}"
            with st.expander(chapter_labels[stage], expanded=bool(st.session_state.get(exp_key))):
                for n in nodes_for_stage:
                    _render_v1_path_row(n, campaign, state)

        # Any nodes that don't belong to the known stages
        for n in other_nodes:
            _render_v1_path_row(n, campaign, state)

    with col_detail:
        _render_v1_current_panel(campaign, current_node)
        _render_boss_outcome_controls(state, campaign, current_node)

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
    souls_token_node_id = state.get("souls_token_node_id")

    if bool(st.session_state.get("ui_compact")):
        _render_v2_campaign_compact(settings=settings, state=state, campaign=campaign, nodes=nodes, current_node=current_node)
        st.session_state["campaign_v2_state"] = state
        return

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            _render_party_icons(settings)

            player_count = _get_player_count(settings)
            sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))

            sparks_key = "campaign_v2_sparks_campaign"
            if sparks_key not in st.session_state:
                st.session_state[sparks_key] = int(state.get("sparks", sparks_max))

            sparks_value = st.number_input(
                "Sparks",
                min_value=0,
                step=1,
                key=sparks_key,
            )
            state["sparks"] = int(sparks_value)

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

        _render_party_events_panel(state)
        st.markdown("---")
        st.markdown(
            f"**Current location:** "
            f"{_describe_v2_node_label(campaign, current_node)}"
        )

        # When standing on an encounter space, restrict legal destinations.
        allowed_destinations = _v2_compute_allowed_destinations(campaign)

        # If the party is currently on an encounter space that has not yet had a
        # choice made (choice_index is None), disable all other travel/return
        # controls until a choice is applied.
        disable_travel = False
        try:
            if current_node.get("kind") == "encounter" and current_node.get("choice_index") is None:
                disable_travel = True
        except Exception:
            disable_travel = False

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
            _render_v2_path_row(n, campaign, state, allowed_destinations, disable_travel=disable_travel)

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
                    _render_v2_path_row(n, campaign, state, allowed_destinations, disable_travel=disable_travel)

        for n in other_nodes:
            _render_v2_path_row(n, campaign, state, allowed_destinations, disable_travel=disable_travel)

    with col_detail:
        _render_v2_current_panel(campaign, current_node, state)
        _render_boss_outcome_controls(state, campaign, current_node)

    st.session_state["campaign_v2_state"] = state


def _render_v1_campaign_compact(
    *,
    settings: Dict[str, Any],
    state: Dict[str, Any],
    campaign: Dict[str, Any],
    nodes: List[Dict[str, Any]],
    current_node: Dict[str, Any],
) -> None:
    # Optional bonfire art (kept out of the main flow to save vertical space)
    with st.expander("Bonfire", expanded=False):
        st.image(str(BONFIRE_ICON_PATH), width="stretch")

    _render_party_icons(settings)

    player_count = _get_player_count(settings)
    sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))

    sparks_key = "campaign_v1_sparks_campaign"
    if sparks_key not in st.session_state:
        st.session_state[sparks_key] = int(state.get("sparks", sparks_max))

    sparks_value = st.number_input(
        "Sparks",
        min_value=0,
        step=1,
        key=sparks_key,
    )
    state["sparks"] = int(sparks_value)

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

    st.markdown(
        f"**Current location:** "
        f"{_describe_v1_node_label(campaign, current_node)}"
    )

    # Path is still available, but collapsed to avoid dominating the scroll.
    with st.expander("Full path", expanded=False):
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
            _render_v1_path_row(n, campaign, state)

        chapter_labels = {
            "mini": "Mini Boss Chapter",
            "main": "Main Boss Chapter",
            "mega": "Mega Boss Chapter",
        }

        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            with st.expander(chapter_labels[stage], expanded=False):
                for n in nodes_for_stage:
                    _render_v1_path_row(n, campaign, state)

        for n in other_nodes:
            _render_v1_path_row(n, campaign, state)

    st.markdown("---")
    _render_v1_current_panel(campaign, current_node)
    _render_boss_outcome_controls(state, campaign, current_node)


def _render_v2_campaign_compact(
    *,
    settings: Dict[str, Any],
    state: Dict[str, Any],
    campaign: Dict[str, Any],
    nodes: List[Dict[str, Any]],
    current_node: Dict[str, Any],
) -> None:
    player_count = _get_player_count(settings)
    sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))

    sparks_key = "campaign_v2_sparks_campaign"
    if sparks_key not in st.session_state:
        st.session_state[sparks_key] = int(state.get("sparks", sparks_max))

    sparks_value = st.number_input(
        "Sparks",
        min_value=0,
        step=1,
        key=sparks_key,
    )
    state["sparks"] = int(sparks_value)

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

    # Party-attached events (immediate + consumable)
    _render_party_events_panel(state)

    st.markdown(
        f"**Current location:** "
        f"{_describe_v2_node_label(campaign, current_node)}"
    )

    allowed_destinations = _v2_compute_allowed_destinations(campaign)

    def _label_for_node(node: Dict[str, Any]) -> str:
        base = _describe_v2_node_label(campaign, node)
        rv = node.get("rendezvous_event")
        if node.get("kind") == "encounter" and isinstance(rv, dict):
            rv_name = str(rv.get("name") or rv.get("id") or "").strip()
            if rv_name:
                base = f"{base} [{rv_name}]"
        return base

    # ----- Travel controller -----
    current_id = campaign.get("current_node_id")
    current_is_bonfire = current_node.get("kind") == "bonfire"

    candidates: List[str] = []
    labels: Dict[str, str] = {}

    for node in nodes:
        node_id = node.get("id")
        if not node_id or node_id == current_id:
            continue

        kind = node.get("kind")
        stage_closed = _is_stage_closed_for_node(campaign, node)
        if stage_closed and kind in ("encounter", "boss"):
            continue

        if allowed_destinations is not None and node_id not in allowed_destinations:
            continue

        lab = "Bonfire" if kind == "bonfire" else _label_for_node(node)
        if current_is_bonfire and kind in ("encounter", "boss") and node.get("shortcut_unlocked"):
            lab = f"{lab} (Shortcut)"

        candidates.append(node_id)
        labels[node_id] = lab

    if candidates:
        sel = st.selectbox(
            "Destination",
            options=candidates,
            format_func=lambda x: labels.get(x, str(x)),
            key="campaign_v2_compact_destination",
        )
        dest_node = None
        for n in nodes:
            if n.get("id") == sel:
                dest_node = n
                break

        btn_label = "Travel"
        if isinstance(dest_node, dict):
            k = dest_node.get("kind")
            if k == "bonfire":
                btn_label = "Return to Bonfire (spend 1 Spark)"
            elif k == "boss":
                btn_label = "Confront"
            if current_is_bonfire and dest_node.get("shortcut_unlocked"):
                btn_label = "Take Shortcut"

        # Disable the compact travel button if choices must be resolved on the
        # current encounter space.
        disable_travel_compact = False
        try:
            disable_travel_compact = current_node.get("kind") == "encounter" and current_node.get("choice_index") is None
        except Exception:
            disable_travel_compact = False

        if st.button(btn_label, key="campaign_v2_compact_travel_btn", width="stretch", disabled=disable_travel_compact):
            if isinstance(dest_node, dict):
                k = dest_node.get("kind")
                node_id = dest_node.get("id")

                if k == "bonfire":
                    _reset_all_encounters_on_bonfire_return(campaign)

                    sparks_cur = int(state.get("sparks") or 0)
                    state["sparks"] = sparks_cur - 1 if sparks_cur > 0 else 0

                    # Force widget to re-seed on rerun
                    st.session_state.pop("campaign_v2_sparks_campaign", None)

                    st.session_state["campaign_v2_state"] = state
                    st.rerun()

                if k in ("encounter", "boss") and node_id:
                    campaign["current_node_id"] = node_id
                    dest_node["revealed"] = True
                    state["campaign"] = campaign
                    st.session_state["campaign_v2_state"] = state
                    st.rerun()
    else:
        st.caption("No legal destinations available.")

    # ----- Full path (collapsed) -----
    with st.expander("Full path", expanded=False):
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

        chapter_labels: Dict[str, str] = {
            "mini": "Mini Boss Chapter",
            "main": "Main Boss Chapter",
            "mega": "Mega Boss Chapter",
        }

        mini_boss = stage_nodes.get("mini", [])[-1] if stage_nodes.get("mini") else None
        main_boss = stage_nodes.get("main", [])[-1] if stage_nodes.get("main") else None
        mega_boss = stage_nodes.get("mega", [])[-1] if stage_nodes.get("mega") else None

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
            with st.expander(chapter_labels[stage], expanded=False):
                for n in nodes_for_stage:
                    _render_v2_path_row(n, campaign, state, allowed_destinations)

        for n in other_nodes:
            _render_v2_path_row(n, campaign, state, allowed_destinations)

    st.markdown("---")
    _render_v2_current_panel(campaign, current_node, state)
    _render_boss_outcome_controls(state, campaign, current_node)


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
        stage_closed = _is_stage_closed_for_node(campaign, node)

        # Determine the campaign's current chapter (stage).
        # If the party is on a non-bonfire node, use that node's stage. If the
        # party is at the bonfire, pick the first non-complete boss stage in
        # order (mini, main, mega) to treat as the current chapter for the UI.
        def _campaign_current_stage(camp: Dict[str, Any]) -> Optional[str]:
            cur_id = camp.get("current_node_id")
            nodes = camp.get("nodes") or []
            if cur_id and cur_id != "bonfire":
                for nn in nodes:
                    if nn.get("id") == cur_id:
                        return nn.get("stage")

            # If at bonfire (or can't find current node), choose the first boss
            # stage that is not complete in the usual order.
            for stg in ("mini", "main", "mega"):
                for nn in nodes:
                    if nn.get("kind") == "boss" and nn.get("stage") == stg:
                        if nn.get("status") != "complete":
                            return stg
            return None

        current_stage = _campaign_current_stage(campaign)

        souls_token_node_id = state.get("souls_token_node_id")
        show_souls_token = (
            souls_token_node_id is not None
            and node_id == souls_token_node_id
            and kind in ("encounter", "boss")
        )

        # Current location: party token (and optional souls token)
        if is_current:
            if show_souls_token:
                cur_cols = st.columns([1, 0.5])
                with cur_cols[0]:
                    st.image(str(PARTY_TOKEN_PATH), width=48)
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                st.image(str(PARTY_TOKEN_PATH), width=48)
            return

        # Bonfire row
        if kind == "bonfire":
            if st.button(
                "Return to Bonfire (spend 1 Spark)",
                key=f"campaign_v1_goto_{node_id}",
                width="stretch"
            ):
                # Returning to the bonfire clears completion for all encounters
                # in this campaign. Shortcuts remain.
                _reset_all_encounters_on_bonfire_return(campaign)

                # Spend a Spark, but not below zero
                sparks_cur = int(state.get("sparks") or 0)
                state["sparks"] = sparks_cur - 1 if sparks_cur > 0 else 0

                campaign["current_node_id"] = "bonfire"
                state["campaign"] = campaign

                # Force widget to re-seed on rerun
                st.session_state.pop("campaign_v2_sparks_campaign", None)

                st.session_state["campaign_v2_state"] = state
                st.rerun()
            return

        # Encounters / bosses
        if kind in ("encounter", "boss"):
            # Chapter closed: no more travel into this stage
            if stage_closed:
                return

            # Only show Travel/Confront controls for nodes that belong to the
            # campaign's current chapter. If we couldn't determine a current
            # stage, fall back to the previous behavior (show controls).
            node_stage = node.get("stage")
            if current_stage is not None and node_stage != current_stage:
                return

            btn_label = "Travel" if kind == "encounter" else "Confront"

            if show_souls_token:
                cur_cols = st.columns([1, 0.5])
                with cur_cols[0]:
                    if st.button(btn_label, key=f"campaign_v1_goto_{node_id}", width="stretch"):
                        campaign["current_node_id"] = node_id
                        node["revealed"] = True
                        state["campaign"] = campaign
                        st.session_state["campaign_v1_state"] = state
                        st.rerun()
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                if st.button(btn_label, key=f"campaign_v1_goto_{node_id}", width="stretch"):
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
    allowed_destinations: Optional[Set[str]] = None,
    disable_travel: bool = False,
) -> None:
    label = _describe_v2_node_label(campaign, node)
    rv = node.get("rendezvous_event")
    if node.get("kind") == "encounter" and isinstance(rv, dict):
        rv_name = str(rv.get("name") or rv.get("id") or "").strip()
        if rv_name:
            label = f"{label} [{rv_name}]"
    row_cols = st.columns([3, 1])

    with row_cols[0]:
        st.markdown(f"- {label}")

    with row_cols[1]:
        node_id = node.get("id")
        kind = node.get("kind")
        is_current = node_id == campaign.get("current_node_id")
        current_is_bonfire = campaign.get("current_node_id") == "bonfire"
        stage_closed = _is_stage_closed_for_node(campaign, node)

        souls_token_node_id = state.get("souls_token_node_id")
        show_souls_token = (
            souls_token_node_id is not None
            and node_id == souls_token_node_id
            and kind in ("encounter", "boss")
        )

        # Current location: party token (and optional souls token)
        if is_current:
            if show_souls_token:
                cur_cols = st.columns([1, 0.5])
                with cur_cols[0]:
                    st.image(str(PARTY_TOKEN_PATH), width=48)
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                st.image(str(PARTY_TOKEN_PATH), width=48)
            return

        # If chapter is closed, encounters/bosses in this stage are no longer legal destinations
        if stage_closed and kind in ("encounter", "boss"):
            return

        can_travel_here = True
        if allowed_destinations is not None and node_id not in allowed_destinations:
            can_travel_here = False

        # Bonfire row
        if kind == "bonfire":
            if not can_travel_here:
                return
            # When travel is disabled due to an unresolved encounter choice,
            # render the Return button as disabled for other nodes.
            disabled = disable_travel and node_id != campaign.get("current_node_id")
            if st.button(
                "Return to Bonfire (spend 1 Spark)",
                key=f"campaign_v2_goto_{node_id}",
                width="stretch",
                disabled=disabled,
            ):
                # Returning to the bonfire clears completion for all encounters
                # in this campaign. Shortcuts remain valid.
                _reset_all_encounters_on_bonfire_return(campaign)

                # Spend a Spark, but not below zero
                sparks_cur = int(state.get("sparks") or 0)
                state["sparks"] = sparks_cur - 1 if sparks_cur > 0 else 0

                campaign["current_node_id"] = "bonfire"
                state["campaign"] = campaign

                # Force widget to re-seed on rerun
                st.session_state.pop("campaign_v2_sparks_campaign", None)

                st.session_state["campaign_v2_state"] = state
                st.rerun()
            return

        # Shortcut marker (from bonfire)
        is_shortcut_destination = bool(
            current_is_bonfire and node.get("shortcut_unlocked")
        )

        if kind in ("encounter", "boss"):
            if not can_travel_here:
                if show_souls_token:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
                return

            btn_label = "Travel" if kind == "encounter" else "Confront"
            if is_shortcut_destination:
                btn_label = "Take Shortcut"

            # When travel is disabled due to an unresolved encounter choice,
            # render the travel/confront/shortcut button disabled for other nodes.
            disabled = disable_travel and node_id != campaign.get("current_node_id")

            if show_souls_token:
                cur_cols = st.columns([1, 0.5])
                with cur_cols[0]:
                    if st.button(btn_label, key=f"campaign_v2_goto_{node_id}", width="stretch", disabled=disabled):
                        campaign["current_node_id"] = node_id
                        node["revealed"] = True
                        state["campaign"] = campaign
                        st.session_state["campaign_v2_state"] = state
                        st.rerun()
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                if st.button(btn_label, key=f"campaign_v2_goto_{node_id}", width="stretch", disabled=disabled):
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
                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{data_path}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                # Special case: Ornstein & Smough dual-boss card
                if "Ornstein" in boss_name and "Smough" in boss_name:
                    try:
                        o_img, s_img = render_dual_boss_data_cards(raw_data)
                        o_col, s_col = st.columns(2)
                        with o_col:
                            try:
                                b64_o = base64.b64encode(o_img).decode()
                                src_o = f"data:image/png;base64,{b64_o}"
                            except Exception:
                                src_o = o_img
                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{src_o}" style="width:100%">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with s_col:
                            try:
                                b64_s = base64.b64encode(s_img).decode()
                                src_s = f"data:image/png;base64,{b64_s}"
                            except Exception:
                                src_s = s_img
                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{src_s}" style="width:100%">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
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
                        try:
                            b64 = base64.b64encode(img).decode()
                            src = f"data:image/png;base64,{b64}"
                        except Exception:
                            src = img
                        st.markdown(
                            f"""
                            <div class="card-image">
                                <img src="{src}" style="width:100%">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    except Exception as exc:
                        st.warning(f"Failed to render boss data card: {exc}")
        else:
            st.markdown(f"**{prefix}: Unknown**")
            st.caption("No boss selected for this space.")

        st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)

        if st.button(
            "Start Boss Fight",
            key=f"campaign_v1_start_boss_{current_node.get('id')}",
            width="stretch"
        ):
            if not boss_name:
                st.warning("No boss configured for this node.")
            else:
                st.session_state["pending_boss_mode_from_campaign"] = {
                    "boss_name": boss_name
                }
                st.rerun()
        return


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
        settings = _get_settings()

        options = current_node.get("options") or []
        choice_idx = current_node.get("choice_index")

        if not options:
            st.caption("No encounter options attached to this space. Regenerate this campaign.")
            return

        rv = current_node.get("rendezvous_event")
        is_scout_ahead = _is_scout_ahead_event(rv)

        alt_idx: Optional[int] = None
        if is_scout_ahead:
            alt_idx = _v2_ensure_scout_ahead_alt_option(node=current_node, settings=settings, campaign=campaign)
            # Refresh local view after mutation
            options = current_node.get("options") or []
            choice_idx = current_node.get("choice_index")
        else:
            _v2_cleanup_scout_ahead_if_unpicked(current_node)

        # No choice yet: present options side-by-side (Scout Ahead adds one extra option)
        if choice_idx is None:
            st.markdown("**Choose an encounter for this space**")

            cols = st.columns(len(options))
            for idx, frozen in enumerate(options):
                with cols[idx]:
                    _render_campaign_encounter_card(frozen)

                    st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)

                    if is_scout_ahead and alt_idx is not None and idx == int(alt_idx):
                        btn_label = "Choose Scout Ahead"
                    else:
                        btn_label = f"Choose option {idx + 1}"

                    if st.button(
                        btn_label,
                        key=f"campaign_v2_choose_{current_node.get('id')}_{idx}",
                        width="stretch"
                    ):
                        # Persist base choice index for Scout Ahead comparisons
                        if is_scout_ahead:
                            sa = current_node.get("scout_ahead")
                            if isinstance(sa, dict):
                                if alt_idx is not None and idx != int(alt_idx):
                                    sa["base_choice_index"] = idx
                                elif not isinstance(sa.get("base_choice_index"), int):
                                    sa["base_choice_index"] = 0

                        current_node["choice_index"] = idx
                        current_node["frozen"] = frozen
                        current_node["revealed"] = True

                        _consume_scout_ahead(current_node)

                        state["campaign"] = campaign
                        st.session_state["campaign_v2_state"] = state
                        st.rerun()

            # Always show attached rendezvous card under the encounter card(s)
            if isinstance(rv, dict) and rv.get("path"):
                w = _card_w()
                p = Path(rv["path"])
                b64 = base64.b64encode(p.read_bytes()).decode()

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="data:image/png;base64,{b64}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
            return

        # Choice already made
        try:
            chosen_idx = int(choice_idx)
        except Exception:
            chosen_idx = -1

        if not (0 <= chosen_idx < len(options)):
            st.caption("Chosen encounter index is out of range; regenerate this campaign.")
            return

        # Scout Ahead: show the choice again (previously chosen vs new encounter)
        if is_scout_ahead:
            sa = current_node.get("scout_ahead")
            if isinstance(sa, dict):
                if alt_idx is None:
                    alt_idx = sa.get("alt_choice_index")
                try:
                    alt_idx_int = int(alt_idx) if alt_idx is not None else None
                except Exception:
                    alt_idx_int = None

                base_idx = sa.get("base_choice_index")
                if not isinstance(base_idx, int) or not (0 <= base_idx < len(options)):
                    base_idx = chosen_idx
                    if alt_idx_int is not None and base_idx == alt_idx_int:
                        base_idx = 0 if len(options) > 0 else chosen_idx
                        if alt_idx_int is not None and base_idx == alt_idx_int and len(options) > 1:
                            base_idx = 1
                    sa["base_choice_index"] = base_idx

                if alt_idx_int is not None and 0 <= alt_idx_int < len(options) and alt_idx_int != base_idx:
                    st.markdown("**Scout Ahead**")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.caption("Previously chosen")
                        _render_campaign_encounter_card(options[base_idx])
                    with col_b:
                        st.caption("Scout Ahead")
                        _render_campaign_encounter_card(options[alt_idx_int])

                    radio_key = f"campaign_v2_scout_ahead_pick_{current_node.get('id')}"
                    default_index = 1 if chosen_idx == alt_idx_int else 0
                    pick = st.radio(
                        "Use which encounter?",
                        options=["Previously chosen", "Scout Ahead"],
                        index=default_index,
                        horizontal=True,
                        key=radio_key,
                    )

                    if st.button(
                        "Apply choice",
                        key=f"campaign_v2_scout_ahead_apply_{current_node.get('id')}",
                        width="stretch"
                    ):
                        new_idx = alt_idx_int if pick == "Scout Ahead" else base_idx
                        current_node["choice_index"] = int(new_idx)
                        current_node["frozen"] = options[int(new_idx)]
                        current_node["revealed"] = True
                        
                        _consume_scout_ahead(current_node)

                        state["campaign"] = campaign
                        st.session_state["campaign_v2_state"] = state
                        st.rerun()

                    # Scout Ahead card under the encounter card(s)
                    if isinstance(rv, dict) and rv.get("path"):
                        w = _card_w()

                        st.markdown(
                            f"""
                            <div class="card-image" style="width:{w}px">
                                <img src="{rv['path']}" style="width:100%">
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    return

        # Normal: show the chosen encounter card
        frozen = options[chosen_idx]
        _render_campaign_encounter_card(frozen)

        # Always show attached rendezvous card under the encounter card
        if isinstance(rv, dict) and rv.get("path"):
            w = _card_w()

            st.markdown(
                f"""
                <div class="card-image" style="width:{w}px">
                    <img src="{rv['path']}" style="width:100%">
                </div>
                """,
                unsafe_allow_html=True,
            )

        return

    # Boss: identical to V1 logic
    _render_v1_current_panel(campaign, current_node)


def _apply_boss_defeated(
    state: Dict[str, Any],
    campaign: Dict[str, Any],
    boss_node: Dict[str, Any],
    version: str,
) -> None:
    """
    Boss victory rewards and state updates.

    V2:
      - If this is the mini-boss: gain [player_count] + 6 souls.
      - Any boss: gain +1 Spark (can exceed the original max).
      - Pick up any dropped-souls token on this boss.
      - Mark boss complete, return to bonfire, do NOT spend a Spark.

    V1:
      - Gain souls equal to (player_count * sparks_left).
      - Pick up any dropped-souls token on this boss.
      - Mark boss complete, return to bonfire.
      - Set Sparks back to the max value.
    """
    import streamlit as st  # ensure st is in scope if not already

    version = (version or "").upper()
    state_key = "campaign_v2_state" if version == "V2" else "campaign_v1_state"

    node_id = boss_node.get("id")
    stage = boss_node.get("stage")

    # Base values
    player_count = int(campaign.get("player_count") or 0)
    sparks_cur = int(state.get("sparks") or 0)
    sparks_max = int(state.get("sparks_max") or sparks_cur)
    current_souls = int(state.get("souls") or 0)

    # 1) Pick up any dropped souls token that is sitting on this boss
    token_node_id = state.get("souls_token_node_id")
    token_amount = int(state.get("souls_token_amount") or 0)
    if token_node_id == node_id and token_amount > 0:
        current_souls += token_amount
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0

    # 2) Apply version-specific boss soul rewards
    if version == "V2":
        # Mini-boss: fixed bonus of player_count + 6 souls
        if stage == "mini":
            current_souls += player_count + 6

        # Any boss: +1 spark, even if it exceeds starting/max value
        state["sparks"] = sparks_cur + 1

    else:  # V1
        # 1 soul per character per Spark left at the time of the kill
        # before we reset Sparks back to max
        if player_count > 0 and sparks_cur > 0:
            current_souls += player_count * sparks_cur

        # Reset Sparks to max for the next track
        state["sparks"] = sparks_max

    # Commit final souls and sparks into state
    state["souls"] = current_souls

    # 3) Mark boss as defeated, close the chapter
    boss_node["status"] = "complete"
    boss_node["revealed"] = True

    # Update chapter expander visibility: close the defeated chapter and
    # open the next chapter expander (if any). Use version-prefixed keys so
    # V1/V2 UI state remains separate.
    try:
        order = ["mini", "main", "mega"]
        if stage in order:
            idx = order.index(stage)
            cur_key = f"campaign_{version.lower()}_chapter_expander_{stage}"
            st.session_state[cur_key] = False

            # Find the next stage that exists in the campaign and is not complete
            next_stage = None
            for j in range(idx + 1, len(order)):
                candidate = order[j]
                for n in campaign.get("nodes") or []:
                    if n.get("kind") == "boss" and n.get("stage") == candidate:
                        if n.get("status") != "complete":
                            next_stage = candidate
                        break
                if next_stage:
                    break

            if next_stage:
                next_key = f"campaign_{version.lower()}_chapter_expander_{next_stage}"
                st.session_state[next_key] = True
    except Exception:
        pass

    # 4) When the party returns to the bonfire, clear completion on all encounters.
    # This applies to both V1 and V2; shortcuts remain valid.
    _reset_all_encounters_on_bonfire_return(campaign)

    # 5) Party returns to the bonfire, without spending a Spark here
    campaign["current_node_id"] = "bonfire"
    state["campaign"] = campaign

    # Clear any stale "dropped_souls" trackers if you use them elsewhere
    state.pop("dropped_souls", None)

    st.session_state[state_key] = state

    st.success("Boss defeated; rewards applied and the party has returned to the bonfire.")
    st.rerun()


def _apply_boss_failure(
    state: Dict[str, Any],
    campaign: Dict[str, Any],
    boss_node: Dict[str, Any],
    version: str,
) -> None:
    """
    Boss loss behaves exactly like a failed encounter:
    - Souls cache goes to 0, with a souls token dropped on the boss (if >0)
    - Lose 1 Spark (if any are left)
    - All encounters in this boss' stage are reset to incomplete
    - Party returns to the bonfire
    - Encounter reward/event state is cleared
    """
    import streamlit as st

    version = version.upper()
    state_key = "campaign_v2_state" if version == "V2" else "campaign_v1_state"

    failed_node_id = boss_node.get("id")

    # Drop souls on the boss, if any
    current_souls = int(state.get("souls") or 0)
    _record_dropped_souls(state, failed_node_id, current_souls)

    # Soul cache goes to 0
    state["souls"] = 0
    state["dropped_souls"] = current_souls if current_souls > 0 else 0

    # Spend a Spark, but not below zero
    sparks_cur = int(state.get("sparks") or 0)
    if sparks_cur > 0:
        state["sparks"] = sparks_cur - 1
    else:
        state["sparks"] = 0

    # When the party returns to the bonfire, all completed encounters
    # are reset to incomplete across the whole campaign. Shortcuts stay valid.
    _reset_all_encounters_on_bonfire_return(campaign)

    # Party returns to the bonfire
    campaign["current_node_id"] = "bonfire"
    state["campaign"] = campaign
    st.session_state[state_key] = state

    # Clear encounter-specific session data
    st.session_state["encounter_events"] = []
    st.session_state["last_encounter_reward_totals"] = {}
    st.session_state.pop("last_encounter_rewards_for_slug", None)

    if sparks_cur > 0:
        st.warning(
            "Boss failed; party returned to the bonfire and lost 1 Spark."
        )
    else:
        st.warning(
            "Boss failed; party returned to the bonfire but has no Sparks left."
        )
    st.rerun()


def _render_boss_outcome_controls(
    state: Dict[str, Any],
    campaign: Dict[str, Any],
    current_node: Dict[str, Any],
) -> None:
    """
    Show boss outcome buttons when the current node is a boss:
    - Boss defeated (close chapter)
    - Boss failed (return to bonfire, lose 1 Spark)
    """
    if not current_node or current_node.get("kind") != "boss":
        return

    version = str(campaign.get("version") or "V1").upper()

    st.markdown("#### Boss outcome")
    col_win, col_fail = st.columns(2)

    with col_win:
        if st.button(
            "Boss defeated (close chapter)",
            key=f"campaign_{version.lower()}_boss_defeated",
            width="stretch"
        ):
            _apply_boss_defeated(state, campaign, current_node, version)

    with col_fail:
        if st.button(
            "Boss failed (return to bonfire, lose 1 Spark)",
            key=f"campaign_{version.lower()}_boss_failed",
            width="stretch"
        ):
            _apply_boss_failure(state, campaign, current_node, version)


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
        img = res["card_img"]

        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        st.markdown(
            f"""
            <div class="card-image">
                <img src="data:image/png;base64,{b64}" style="width:100%">
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("Failed to render encounter card.")
