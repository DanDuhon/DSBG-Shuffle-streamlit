# ui/campaign_mode/manage_tab_v2.py
import streamlit as st
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.image_cache import get_image_data_uri_cached
from ui.campaign_mode.core import (
    BONFIRE_ICON_PATH,
    PARTY_TOKEN_PATH,
    SOULS_TOKEN_PATH,
    _default_sparks_max,
    _describe_v2_node_label,
    _v2_compute_allowed_destinations,
    _reset_all_encounters_on_bonfire_return,
    _card_w,
)
from ui.campaign_mode.generation import _v2_pick_scout_ahead_alt_frozen
from ui.campaign_mode.tabs.manage_tab_shared import (
    _frozen_sig,
    _render_boss_outcome_controls,
    _is_stage_closed_for_node,
    _render_campaign_encounter_card,
)
from ui.campaign_mode.tabs.manage_tab_v1 import _render_v1_current_panel
from ui.campaign_mode.state import _get_settings, _get_player_count
from ui.campaign_mode.ui_helpers import _render_party_icons


_SCOUT_AHEAD_ID = "scout ahead"


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
    """Remove stale Scout Ahead state when the event is no longer applicable.

    This is a safety cleanup for encounter nodes that previously had Scout Ahead
    attached (and therefore may have had an extra encounter option appended).

    Cleanup rules:
    - Only runs when the node is still unpicked (`node["choice_index"] is None`).
    - If `node["scout_ahead"]["base_options_count"]` is present, truncate
      `node["options"]` back to that original length.
    - Always remove `node["scout_ahead"]` afterwards.

    This prevents users from selecting the extra "Scout Ahead" option after the
    rendezvous event has been consumed/removed.
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
    """Ensure Scout Ahead provides a persistent extra encounter choice for a V2 encounter node.

    Expected V2 encounter-node schema (relevant fields):
    - node["options"]: list[dict] frozen encounter candidates for this space
    - node["choice_index"]: int | None (selected option index)
    - node["rendezvous_event"]: dict | None (Scout Ahead is detected here)
    - node["scout_ahead"]: dict (managed by this helper while the node is unpicked)

    `node["scout_ahead"]` schema/invariants:
    - "base_options_count": int
        Number of options that existed before appending the Scout Ahead alternative.
    - "alt_frozen": dict
        The generated alternative frozen encounter.
    - "alt_choice_index": int
        Index of alt_frozen inside node["options"] (may be recomputed by signature).
    - "base_choice_index": int (optional; written when the user picks a non-alt choice)
        Used for later comparisons/UX around the Scout Ahead selection.

    Returns the choice index of the Scout Ahead alternative option, or None if
    the node has no options to extend.
    """
    options = node.get("options") or []
    if not isinstance(options, list) or not options:
        return None

    level = node.get("level")
    lvl_int = int(level)

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


def _render_party_events_panel(state: Dict[str, Any]) -> None:
    instants = state.get("instant_events_unresolved") or []
    consumables = state.get("party_consumable_events") or []
    orphans = state.get("orphaned_rendezvous_events") or []

    if not instants and not consumables and not orphans:
        return

    # Unified 4-column grid for both Immediate and Consumable events.
    cols = st.columns(4)

    # Build a typed list of events so we can render them into the 4-column
    # grid while still labeling each card with its type above the image.
    typed_events: list[tuple[dict, str]] = []
    if isinstance(instants, list):
        for ev in instants:
            if not isinstance(ev, dict) or not ev.get("path"):
                continue
            typed_events.append((ev, "Immediate"))
    if isinstance(consumables, list):
        for ev in consumables:
            if not isinstance(ev, dict) or not ev.get("path"):
                continue
            typed_events.append((ev, "Consumable"))

    for i, (ev, ev_type) in enumerate(typed_events):
        col = cols[i % 4]
        with col:
            st.markdown(f"**{ev_type}**")
            path_str = str(ev.get("path") or "")
            img_src = path_str
            src = get_image_data_uri_cached(path_str)
            if src:
                img_src = src

            st.image(img_src, width="stretch")
            nm = str(ev.get("name") or ev.get("id") or ev_type).strip()
            if nm:
                st.caption(nm)

    # Controls
    if instants:
        if st.button(
            "Clear immediate event notifications 🧹",
            key="campaign_clear_instant_events",
            width="stretch",
        ):
            state["instant_events_unresolved"] = []
            st.rerun()

    if orphans:
        st.markdown("**Rendezvous with no remaining encounter target**")
        for ev in orphans:
            if isinstance(ev, dict) and ev.get("name"):
                st.caption(str(ev["name"]))


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
        _render_v2_campaign_compact(
            settings=settings,
            state=state,
            campaign=campaign,
            nodes=nodes,
            current_node=current_node,
        )
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
        disable_travel = (
            current_node.get("kind") == "encounter"
            and current_node.get("choice_index") is None
        )

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
            _render_v2_path_row(
                n, campaign, state, allowed_destinations, disable_travel=disable_travel
            )

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
                chapter_labels[
                    "mini"
                ] = f"{mini_boss.get('boss_name', 'Mini Boss')} Chapter"

        if main_boss is not None:
            if main_boss.get("was_random") and not main_boss.get("revealed"):
                chapter_labels["main"] = "Unknown Main Boss Chapter"
            else:
                chapter_labels[
                    "main"
                ] = f"{main_boss.get('boss_name', 'Main Boss')} Chapter"

        if mega_boss is not None:
            if mega_boss.get("was_random") and not mega_boss.get("revealed"):
                chapter_labels["mega"] = "Unknown Mega Boss Chapter"
            else:
                chapter_labels[
                    "mega"
                ] = f"{mega_boss.get('boss_name', 'Mega Boss')} Chapter"

        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            with st.expander(chapter_labels[stage], expanded=True):
                for n in nodes_for_stage:
                    _render_v2_path_row(
                        n,
                        campaign,
                        state,
                        allowed_destinations,
                        disable_travel=disable_travel,
                    )

        for n in other_nodes:
            _render_v2_path_row(
                n, campaign, state, allowed_destinations, disable_travel=disable_travel
            )

    with col_detail:
        _render_v2_current_panel(campaign, current_node, state)
        _render_boss_outcome_controls(state, campaign, current_node)

    st.session_state["campaign_v2_state"] = state


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
            f"**Current location:** " f"{_describe_v2_node_label(campaign, current_node)}"
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
        if (
            current_is_bonfire
            and kind in ("encounter", "boss")
            and node.get("shortcut_unlocked")
        ):
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

        btn_label = "Travel ➡️"
        if isinstance(dest_node, dict):
            k = dest_node.get("kind")
            if k == "bonfire":
                btn_label = "Return to Bonfire (spend 1 Spark) 🔥"
            elif k == "boss":
                btn_label = "Confront ⚔️"
            if current_is_bonfire and dest_node.get("shortcut_unlocked"):
                btn_label = "Take Shortcut ↗️"

        # Disable the compact travel button if choices must be resolved on the
        # current encounter space.
        disable_travel_compact = (
            current_node.get("kind") == "encounter"
            and current_node.get("choice_index") is None
        )

        if st.button(
            btn_label,
            key="campaign_v2_compact_travel_btn",
            width="stretch",
            disabled=disable_travel_compact,
        ):
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
                chapter_labels[
                    "mini"
                ] = f"{mini_boss.get('boss_name', 'Mini Boss')} Chapter"

        if main_boss is not None:
            if main_boss.get("was_random") and not main_boss.get("revealed"):
                chapter_labels["main"] = "Unknown Main Boss Chapter"
            else:
                chapter_labels[
                    "main"
                ] = f"{main_boss.get('boss_name', 'Main Boss')} Chapter"

        if mega_boss is not None:
            if mega_boss.get("was_random") and not mega_boss.get("revealed"):
                chapter_labels["mega"] = "Unknown Mega Boss Chapter"
            else:
                chapter_labels[
                    "mega"
                ] = f"{mega_boss.get('boss_name', 'Mega Boss')} Chapter"

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
        stage_is_closed = bool(stage_closed and kind in ("encounter", "boss"))

        can_travel_here = True
        if allowed_destinations is not None and node_id not in allowed_destinations:
            can_travel_here = False
        if stage_is_closed:
            can_travel_here = False

        # Bonfire row
        if kind == "bonfire":
            # When travel is disabled due to an unresolved encounter choice,
            # or the destination is otherwise illegal, render the Return button as disabled.
            disabled = (not can_travel_here) or (
                disable_travel and node_id != campaign.get("current_node_id")
            )
            if st.button(
                "Return to Bonfire (spend 1 Spark) 🔥",
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
            btn_label = "Travel ➡️" if kind == "encounter" else "Confront ⚔️"
            if is_shortcut_destination:
                btn_label = "Take Shortcut ↗️"

            # When travel is disabled due to an unresolved encounter choice,
            # or the destination is otherwise illegal, render the travel/confront/
            # shortcut button disabled for other nodes.
            disabled = (not can_travel_here) or (
                disable_travel and node_id != campaign.get("current_node_id")
            )

            if show_souls_token:
                cur_cols = st.columns([1, 0.5])
                with cur_cols[0]:
                    if st.button(
                        btn_label,
                        key=f"campaign_v2_goto_{node_id}",
                        width="stretch",
                        disabled=disabled,
                    ):
                        campaign["current_node_id"] = node_id
                        node["revealed"] = True
                        state["campaign"] = campaign
                        st.session_state["campaign_v2_state"] = state
                        st.rerun()
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                if st.button(
                    btn_label,
                    key=f"campaign_v2_goto_{node_id}",
                    width="stretch",
                    disabled=disabled,
                ):
                    campaign["current_node_id"] = node_id
                    node["revealed"] = True
                    state["campaign"] = campaign
                    st.session_state["campaign_v2_state"] = state
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
            st.caption(
                "No encounter options attached to this space. Regenerate this campaign."
            )
            return

        rv = current_node.get("rendezvous_event")
        is_scout_ahead = _is_scout_ahead_event(rv)

        alt_idx: Optional[int] = None
        if is_scout_ahead:
            alt_idx = _v2_ensure_scout_ahead_alt_option(
                node=current_node, settings=settings, campaign=campaign
            )
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

                    st.markdown(
                        "<div style='height:0.05rem'></div>", unsafe_allow_html=True
                    )

                    if is_scout_ahead and alt_idx is not None and idx == int(alt_idx):
                        btn_label = "Choose Scout Ahead"
                    else:
                        btn_label = f"Choose option {idx + 1}"

                    if st.button(
                        btn_label,
                        key=f"campaign_v2_choose_{current_node.get('id')}_{idx}",
                        width="stretch",
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
                src = get_image_data_uri_cached(str(p))

                st.image(src or img_src, width=w)

            return

        # Choice already made
        chosen_idx = int(choice_idx)

        if not (0 <= chosen_idx < len(options)):
            st.caption(
                "Chosen encounter index is out of range; regenerate this campaign."
            )
            return

        # Scout Ahead: show the choice again (previously chosen vs new encounter)
        if is_scout_ahead:
            sa = current_node.get("scout_ahead")
            if isinstance(sa, dict):
                if alt_idx is None:
                    alt_idx = sa.get("alt_choice_index")
                alt_idx_int = int(alt_idx) if alt_idx is not None else None

                base_idx = sa.get("base_choice_index")
                if not isinstance(base_idx, int) or not (0 <= base_idx < len(options)):
                    base_idx = chosen_idx
                    if alt_idx_int is not None and base_idx == alt_idx_int:
                        base_idx = 0 if len(options) > 0 else chosen_idx
                        if (
                            alt_idx_int is not None
                            and base_idx == alt_idx_int
                            and len(options) > 1
                        ):
                            base_idx = 1
                    sa["base_choice_index"] = base_idx

                if (
                    alt_idx_int is not None
                    and 0 <= alt_idx_int < len(options)
                    and alt_idx_int != base_idx
                ):
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
                        "Apply choice ✅",
                        key=f"campaign_v2_scout_ahead_apply_{current_node.get('id')}",
                        width="stretch",
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
                        img_src = rv["path"]
                        src = get_image_data_uri_cached(img_src)
                        if src:
                            img_src = src

                        st.image(img_src, width=w)
                    return

        # Normal: show the chosen encounter card
        frozen = options[chosen_idx]
        _render_campaign_encounter_card(frozen)

        # Always show attached rendezvous card under the encounter card
        if isinstance(rv, dict) and rv.get("path"):
            w = _card_w()
            img_src = rv["path"]
            src = get_image_data_uri_cached(img_src)
            if src:
                img_src = src

            st.image(img_src, width=w)

        return

    # Boss: identical to V1 logic
    _render_v1_current_panel(campaign, current_node)