# ui/campaign_mode/manage_tab.py
import streamlit as st
import json
import hashlib
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.behavior.generation import (
    render_data_card_cached,
    render_dual_boss_data_cards,
)
from core.image_cache import get_image_data_uri_cached, bytes_to_data_uri
from ui.campaign_mode.api import (
    BONFIRE_ICON_PATH,
    PARTY_TOKEN_PATH,
    SOULS_TOKEN_PATH,
    default_sparks_max,
    describe_v1_node_label,
    describe_v2_node_label,
    v2_compute_allowed_destinations,
    reset_all_encounters_on_bonfire_return,
    record_dropped_souls,
    card_w,
    v2_pick_scout_ahead_alt_frozen,
)
from ui.campaign_mode.state import _get_settings, _get_player_count
from ui.campaign_mode.ui_helpers import _render_party_icons
from ui.encounter_mode.setup_tab import render_original_encounter


_SCOUT_AHEAD_ID = "scout ahead"


def _frozen_sig(
    frozen: Dict[str, Any], default_level: int
) -> Optional[tuple[str, int, str]]:
    """(expansion, level, encounter_name) signature for a frozen encounter."""
    if not isinstance(frozen, dict):
        return None
    exp = str(frozen.get("expansion") or "")
    lvl = int(frozen.get("encounter_level", default_level))
    name = str(frozen.get("encounter_name") or "")
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
    settings = _get_settings()

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("Generate a V2 campaign in the Setup tab to begin.")
        return
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

    cand = v2_pick_scout_ahead_alt_frozen(
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

            st.markdown(
                f"""
                <div class="card-image">
                    <img src="{img_src}" style="width:100%">
                </div>
                """,
                unsafe_allow_html=True,
            )
            nm = str(ev.get("name") or ev.get("id") or ev_type).strip()
            if nm:
                st.caption(nm)

    # Controls
    if instants:
        if st.button(
            "Clear immediate event notifications",
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
        _render_v1_campaign_compact(
            settings=settings,
            state=state,
            campaign=campaign,
            nodes=nodes,
            current_node=current_node,
        )
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
            sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))

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
            f"{describe_v1_node_label(campaign, current_node)}"
        )

        st.markdown("#### Path")

        # Render all chapters (mini, main, mega) as separate expanders.
        # Keep a per-chapter expanded state in `state['_chapter_expanded']`.
        if "_chapter_expanded" not in state or not isinstance(state.get("_chapter_expanded"), dict):
            state["_chapter_expanded"] = {"mini": True, "main": False, "mega": False}

        # Determine per-stage node lists
        stage_nodes: Dict[str, List[Dict[str, Any]]] = {"mini": [], "main": [], "mega": []}
        for node in nodes:
            stg = node.get("stage")
            if stg in stage_nodes:
                stage_nodes[stg].append(node)

        # Compute which stages are currently completed (boss defeated)
        stage_completed: Dict[str, bool] = {}
        order = ("mini", "main", "mega")
        for s in order:
            boss_list = [n for n in stage_nodes.get(s, []) if n.get("kind") == "boss"]
            boss = boss_list[-1] if boss_list else None
            stage_completed[s] = bool(boss and boss.get("status") == "complete")

        # Detect newly completed stages and advance expanders/current node
        prev_completed = state.get("_stage_completed") or {}
        advanced = False
        for idx, s in enumerate(order):
            was = bool(prev_completed.get(s))
            now = bool(stage_completed.get(s))
            if not was and now:
                # Stage s just completed: close it and open the next stage
                state["_chapter_expanded"][s] = False
                if idx + 1 < len(order):
                    nxt = order[idx + 1]
                    state["_chapter_expanded"][nxt] = True
                # Move party to bonfire in the new chapter (use canonical bonfire id)
                campaign["current_node_id"] = "bonfire"
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                advanced = True
        if advanced:
            # Persist and rerun to update UI state (expander changes + location)
            state["_stage_completed"] = stage_completed
            st.session_state["campaign_v1_state"] = state
            st.rerun()

        # Update last-seen completion map
        state["_stage_completed"] = stage_completed

        # Cache per-stage layouts under state['_last_layouts'] to avoid
        # regenerating when ephemeral metadata changes.
        if "_last_layouts" not in state or not isinstance(state.get("_last_layouts"), dict):
            state["_last_layouts"] = {}

        for s in order:
            # Build nodes to include the bonfire and this stage's nodes
            nodes_for_layout = [n for n in nodes if n.get("kind") == "bonfire"]
            nodes_for_layout.extend(stage_nodes.get(s, []))

            # fingerprint
            fp_parts: List[str] = []
            for n in nodes_for_layout:
                kind = n.get("kind")
                nid = n.get("id") or ""
                if kind == "bonfire":
                    fp_parts.append(f"{nid}:bonfire")
                elif kind == "encounter":
                    fr = n.get("frozen") or {}
                    exp = str(fr.get("expansion") or n.get("expansion") or "")
                    lvl = str(fr.get("encounter_level") or n.get("encounter_level") or n.get("level") or "")
                    name = str(fr.get("encounter_name") or n.get("encounter_name") or "")
                    fp_parts.append(f"{nid}:enc:{exp}:{lvl}:{name}")
                elif kind == "boss":
                    boss_name = str(n.get("boss_name") or n.get("label") or "")
                    fp_parts.append(f"{nid}:boss:{boss_name}")
                else:
                    fp_parts.append(f"{nid}:other")

            fp_raw = "|".join(fp_parts)
            fp = hashlib.md5(fp_raw.encode("utf-8")).hexdigest()
            layout_key = f"v1:{s}:{fp}:{','.join(sorted([n.get('id') or '' for n in nodes_for_layout]))}"

            cached = state.get("_last_layouts", {}).get(s)
            if cached and isinstance(cached, dict) and cached.get("key") == layout_key and isinstance(cached.get("layout"), dict):
                tiles = {}
                for tid, t in cached.get("layout", {}).items():
                    if not isinstance(t, dict):
                        continue
                    tt = dict(t)
                    if isinstance(tt.get("doors"), list):
                        tt["doors"] = set(tt.get("doors") or [])
                    tiles[tid] = tt
            else:
                tiles = _generate_v1_layout(nodes_for_layout)
                saveable: Dict[str, Any] = {}
                for tid, t in tiles.items():
                    if not isinstance(t, dict):
                        continue
                    tt = dict(t)
                    if isinstance(tt.get("doors"), set):
                        tt["doors"] = list(tt.get("doors"))
                    tt["neighbor_dirs"] = [list(x) for x in tt.get("neighbor_dirs", [])]
                    tt["connected"] = list(tt.get("connected", []))
                    saveable[tid] = tt
                state["_last_layouts"][s] = {"key": layout_key, "layout": saveable}

            # Render ASCII map for this chapter inside an expander
            # Determine boss node for this stage (if any)
            boss_list = [n for n in stage_nodes.get(s, []) if n.get("kind") == "boss"]
            boss_node = boss_list[-1] if boss_list else None

            # If mega boss was not selected at generation, skip the mega expander
            if s == "mega" and (not boss_node or not boss_node.get("boss_name")):
                continue

            expanded = bool(state.get("_chapter_expanded", {}).get(s, s == "mini"))
            boss_emoji_map = {"mini": "⚔️", "main": "🐺", "mega": "🐉"}
            em = boss_emoji_map.get(s, "")
            # Default title includes 'Boss' (e.g., 'Mini Boss Chapter').
            # If the boss was explicitly chosen (not random) or has been
            # revealed, show the boss's name immediately. If the boss was
            # chosen randomly, keep the generic title until it's revealed.
            if boss_node and (boss_node.get("revealed") or not bool(boss_node.get("was_random"))):
                boss_name = boss_node.get("boss_name") or boss_node.get("label") or "Boss"
                title = f"{em} {boss_name} Chapter"
            else:
                stage_name_map = {"mini": "Mini", "main": "Main", "mega": "Mega"}
                title = f"{em} {stage_name_map.get(s, s.capitalize())} Boss Chapter"

            with st.expander(title, expanded=expanded):
                tiles_for_render = {k: v for k, v in tiles.items() if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("x"), int) and isinstance(v.get("y"), int)}

                def _extract_level_local(node: Dict[str, Any]) -> int:
                    lv = None
                    if isinstance(node.get("frozen"), dict):
                        lv = node.get("frozen", {}).get("encounter_level")
                    lv = lv or node.get("encounter_level") or node.get("level")
                    return int(lv)

                ascii_tiles: Dict[str, Dict[str, Any]] = {}
                for tid, tile in tiles_for_render.items():
                    ascii_tiles[tid] = dict(tile)

                emoji_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣"}
                for tid, tile in list(ascii_tiles.items()):
                    node = node_by_id.get(tid)
                    if not isinstance(node, dict):
                        continue
                    kind = node.get("kind")
                    if kind == "bonfire":
                        tile["label"] = "🔥 Bonfire"
                        continue
                    if kind == "encounter":
                        lvl = _extract_level_local(node)
                        e = emoji_map.get(lvl, f"{min(lvl,9)}️⃣")
                        if not bool(node.get("revealed")):
                            tile["label"] = f"{e} Unknown"
                        else:
                            name = None
                            if isinstance(node.get("frozen"), dict):
                                name = node.get("frozen", {}).get("encounter_name")
                            name = name or node.get("encounter_name") or node.get("label") or "Encounter"
                            tile["label"] = f"{e} {name}"
                        souls_token_node_id = state.get("souls_token_node_id")
                        if souls_token_node_id is not None and tid == souls_token_node_id:
                            token = f"__SOULS_IMG_{tid}__"
                            tile["label"] = f"{tile.get('label')} {token}"
                            if "_soul_img_tokens" not in locals():
                                _soul_img_tokens = {}
                            _soul_img_tokens[tid] = token
                        continue
                    if kind == "boss":
                        stage = node.get("stage")
                        boss_emoji_map = {"mini": "⚔️", "main": "🐺", "mega": "🐉"}
                        boss_label_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
                        em = boss_emoji_map.get(stage, "")
                        if node.get("revealed"):
                            name = node.get("boss_name") or node.get("label") or tile.get("label") or "Boss"
                            tile["label"] = f"{em} {name}"
                        else:
                            tile["label"] = f"{em} {boss_label_map.get(stage, tile.get('label') or 'Boss')}"
                        souls_token_node_id = state.get("souls_token_node_id")
                        if souls_token_node_id is not None and tid == souls_token_node_id:
                            token = f"__SOULS_IMG_{tid}__"
                            tile["label"] = f"{tile.get('label')} {token}"
                            if "_soul_img_tokens" not in locals():
                                _soul_img_tokens = {}
                            _soul_img_tokens[tid] = token

                map_html = _render_ascii_map(ascii_tiles, current_id, visited=set(state.get("visited_nodes") or []), completed={n.get("id") for n in nodes if n.get("status")=="complete"})
                lines = map_html.split("\n")
                safe_lines = [ln.replace(" ", "&nbsp;") for ln in lines]
                html = (
                    '<div style="overflow:auto; white-space:nowrap; font-family:monospace; max-width:100%;">'
                    + '<div style="display:inline-block; padding:0.25rem;">'
                    + "<br>".join(safe_lines)
                    + "</div></div>"
                )

                tokens = globals().get("_soul_img_tokens") or locals().get("_soul_img_tokens") or {}
                if tokens:
                    src = get_image_data_uri_cached(str(SOULS_TOKEN_PATH))
                    if not src:
                        p = Path(SOULS_TOKEN_PATH)
                        if p.exists():
                            data = p.read_bytes()
                            src = bytes_to_data_uri(data, content_type="image/png")
                    img_html = f'<img src="{src}" style="width:16px;height:16px;vertical-align:middle"/>'
                    for tid, token in tokens.items():
                        html = html.replace(token, img_html)
                    html = html.replace("◈", img_html)

                st.markdown(html, unsafe_allow_html=True)

        # Determine current stage (first incomplete) so downstream travel
        # controls continue to reference the appropriate layout.
        current_stage = next((s for s in order if not stage_completed.get(s)), order[0])

        # Load `tiles` for the current stage into the variable expected by
        # the travel-control logic below.
        tiles = {}
        cached = state.get("_last_layouts", {}).get(current_stage)
        if cached and isinstance(cached, dict) and isinstance(cached.get("layout"), dict):
            for tid, t in cached.get("layout", {}).items():
                if not isinstance(t, dict):
                    continue
                tt = dict(t)
                if isinstance(tt.get("doors"), list):
                    tt["doors"] = set(tt.get("doors") or [])
                tiles[tid] = tt
        else:
            # Fallback: regenerate current stage layout
            nodes_for_layout = [n for n in nodes if n.get("kind") == "bonfire"]
            nodes_for_layout.extend(stage_nodes.get(current_stage, []))
            tiles = _generate_v1_layout(nodes_for_layout)

        # --- Travel controls for ASCII map ---
        st.markdown("#### Travel Controls")

        cur_node_id = campaign.get("current_node_id")
        # When standing on an incomplete encounter, disable return/travel controls
        disable_travel_due_to_unresolved_encounter = (
            current_node.get("kind") == "encounter" and current_node.get("status") != "complete"
        )

        # Return to bonfire (spend 1 Spark)
        # Disable when travel is blocked due to an unresolved encounter or
        # when the party is already at the bonfire.
        disable_return_button = (
            disable_travel_due_to_unresolved_encounter
            or current_node.get("kind") == "bonfire"
        )
        if st.button(
            "Return to Bonfire (spend 1 Spark)",
            key="v1_return_button",
            width="stretch",
            disabled=disable_return_button,
        ):
            reset_all_encounters_on_bonfire_return(campaign)
            sparks_cur = int(state.get("sparks") or 0)
            state["sparks"] = sparks_cur - 1 if sparks_cur > 0 else 0
            campaign["current_node_id"] = "bonfire"
            state["campaign"] = campaign
            st.session_state.pop("campaign_v1_sparks_campaign", None)
            st.session_state["campaign_v1_state"] = state
            st.rerun()

        # Travel buttons: any incomplete encounter/boss reachable from current
        # space without passing through other incomplete encounters. Traversal
        # is allowed through the bonfire and any nodes with status == 'complete'.
        reachable_targets: Set[str] = set()
        # Map target -> path (list of node ids from current -> ... -> target)
        reachable_paths: Dict[str, List[str]] = {}
        if isinstance(tiles.get(cur_node_id), dict):
            from collections import deque

            q = deque([cur_node_id])
            visited = {cur_node_id}
            prev: Dict[str, Optional[str]] = {cur_node_id: None}
            while q:
                cur = q.popleft()
                cur_tile = tiles.get(cur, {})
                for nb in cur_tile.get("connected", []):
                    if nb in visited:
                        continue
                    nb_node = node_by_id.get(nb)
                    if not isinstance(nb_node, dict):
                        continue
                    # record predecessor for path reconstruction
                    visited.add(nb)
                    prev[nb] = cur

                    # If neighbor is an uncompleted encounter/boss, it's a valid target
                    if nb_node.get("kind") in ("encounter", "boss") and nb_node.get("status") != "complete":
                        # reconstruct path from current to nb
                        path = []
                        cur_h = nb
                        while cur_h is not None:
                            path.append(cur_h)
                            cur_h = prev.get(cur_h)
                        path.reverse()
                        # path now is [current, ..., nb] or possibly starting at neighbor if prev missing
                        # ensure it starts with cur_node_id
                        if path and path[0] != cur_node_id:
                            path = [cur_node_id] + path
                        reachable_targets.add(nb)
                        reachable_paths[nb] = path
                        # Do not traverse further through an uncompleted encounter/boss
                        continue
                    # Only traverse through bonfire or completed nodes
                    if nb_node.get("kind") == "bonfire" or nb_node.get("status") == "complete":
                        q.append(nb)

        # Render buttons in the original node order so ordering is stable.
        for node in nodes:
            nid = node.get("id")
            if not nid or nid not in reachable_targets:
                continue
            t = tiles.get(nid) or {}
            if t.get("kind") not in ("encounter", "boss"):
                continue
            btn_label = "Travel"
            # Choose a readable label for the button. When an encounter has
            # been revealed, show its real name (like the ASCII map). When
            # unrevealed, show a generic "Unknown". Boss labels follow stage
            # naming.
            kind = node.get("kind")
            if kind == "bonfire":
                label = "Bonfire"
            elif kind == "encounter":
                # include level emoji like the ASCII map
                lvl = _extract_level_local(node)
                e = emoji_map.get(lvl, f"{min(lvl,9)}️⃣")
                if not node.get("revealed"):
                    label = f"{e} Unknown"
                else:
                    name = None
                    if isinstance(node.get("frozen"), dict):
                        name = node.get("frozen", {}).get("encounter_name")
                    name = name or node.get("encounter_name") or node.get("label")
                    label = f"{e} {name or 'Encounter'}"
            elif kind == "boss":
                stage = node.get("stage")
                boss_emoji_map = {"mini": "⚔️", "main": "🐺", "mega": "🐉"}
                boss_label_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
                em = boss_emoji_map.get(stage, "")
                if node.get("revealed"):
                    name = node.get("boss_name") or node.get("label") or t.get("label") or nid
                    label = f"{em} {name}"
                else:
                    label = f"{em} {boss_label_map.get(stage, node.get('label') or t.get('label') or nid)}"
            # Directional hint: compute full path arrows (always shown)
            path = reachable_paths.get(nid)
            if path:
                # path is like [cur, n1, n2, ..., nid]
                arrows: List[str] = []
                for i in range(len(path) - 1):
                    a = path[i]
                    b = path[i + 1]
                    ta = tiles.get(a) or {}
                    tb = tiles.get(b) or {}
                    ax, ay = ta.get("x"), ta.get("y")
                    bx, by = tb.get("x"), tb.get("y")
                    if not all(isinstance(v, int) for v in (ax, ay, bx, by)):
                        continue
                    dx = bx - ax
                    dy = by - ay
                    if abs(dx) >= abs(dy):
                        arrow = "→" if dx > 0 else "←"
                    else:
                        arrow = "↓" if dy > 0 else "↑"
                    arrows.append(arrow)
                if arrows:
                    arrow_text = " " + " ".join(arrows)

            # Build button text and respect unresolved-encounter disabling
            btn_text = f"{btn_label}{arrow_text} to {label}"
            if st.button(btn_text, key=f"v1_travel_{nid}", width="stretch", disabled=disable_travel_due_to_unresolved_encounter):
                campaign["current_node_id"] = nid
                node["revealed"] = True
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                st.rerun()

        # Note: fail/completed controls are handled in the Play tab; no-op here.

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
            sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))

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
            f"{describe_v2_node_label(campaign, current_node)}"
        )

        # When standing on an encounter space, restrict legal destinations.
        allowed_destinations = v2_compute_allowed_destinations(campaign)

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
    sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))

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
            f"**Current location:** " f"{describe_v1_node_label(campaign, current_node)}"
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
    sparks_max = int(state.get("sparks_max", default_sparks_max(player_count)))

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
            f"**Current location:** " f"{describe_v2_node_label(campaign, current_node)}"
    )

    allowed_destinations = v2_compute_allowed_destinations(campaign)

    def _label_for_node(node: Dict[str, Any]) -> str:
        base = describe_v2_node_label(campaign, node)
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
                    reset_all_encounters_on_bonfire_return(campaign)

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


def _render_v1_path_row(
    node: Dict[str, Any],
    campaign: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    label = describe_v1_node_label(campaign, node)
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
                width="stretch",
            ):
                # Returning to the bonfire clears completion for all encounters
                # in this campaign. Shortcuts remain.
                reset_all_encounters_on_bonfire_return(campaign)

                # Spend a Spark, but not below zero
                sparks_cur = int(state.get("sparks") or 0)
                state["sparks"] = sparks_cur - 1 if sparks_cur > 0 else 0

                campaign["current_node_id"] = "bonfire"
                state["campaign"] = campaign

                # Force widget to re-seed on rerun
                st.session_state.pop("campaign_v1_sparks_campaign", None)

                st.session_state["campaign_v1_state"] = state
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
                    if st.button(
                        btn_label, key=f"campaign_v1_goto_{node_id}", width="stretch"
                    ):
                        campaign["current_node_id"] = node_id
                        node["revealed"] = True
                        state["campaign"] = campaign
                        st.session_state["campaign_v1_state"] = state
                        st.rerun()
                with cur_cols[1]:
                    st.image(str(SOULS_TOKEN_PATH), width=32)
            else:
                if st.button(
                    btn_label, key=f"campaign_v1_goto_{node_id}", width="stretch"
                ):
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
    label = describe_v2_node_label(campaign, node)
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
                reset_all_encounters_on_bonfire_return(campaign)

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
        return

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

            # Load raw behavior JSON directly (cache-aware)
            json_path = Path("data") / "behaviors" / f"{boss_name}.json"
            from ui.campaign_mode.persistence import load_json_file
            raw_data = load_json_file(json_path)
            if raw_data is None:
                raise RuntimeError(f"Failed to load behavior JSON for '{boss_name}'")

            # Special case: Ornstein & Smough dual-boss card
            if "Ornstein" in boss_name and "Smough" in boss_name:
                o_img, s_img = render_dual_boss_data_cards(raw_data)
                o_col, s_col = st.columns(2)
                with o_col:
                    src_o = bytes_to_data_uri(o_img, mime="image/png")
                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src_o}" style="width:100%">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with s_col:
                    src_s = bytes_to_data_uri(s_img, mime="image/png")
                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{src_s}" style="width:100%">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                if boss_name == "Executioner's Chariot":
                    data_path = (
                        BEHAVIOR_CARDS_PATH
                        + "Executioner's Chariot - Skeletal Horse.jpg"
                    )
                else:
                    data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                img = render_data_card_cached(
                    data_path,
                    raw_data,
                    is_boss=True,
                )
                src = bytes_to_data_uri(img, mime="image/png")
                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(f"**{prefix}: Unknown**")
            st.caption("No boss selected for this space.")

        st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)

        if st.button(
            "Start Boss Fight",
            key=f"campaign_v1_start_boss_{current_node.get('id')}",
            width="stretch",
        ):
            if not boss_name:
                st.warning("No boss configured for this node.")
            else:
                st.session_state["pending_boss_mode_from_campaign"] = {
                    "boss_name": boss_name
                }
                st.rerun()
        return


def _generate_v1_layout(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    import random

    tiles: Dict[str, Dict[str, Any]] = {}
    bonfire = None
    boss_node = None
    encounters = []
    for n in nodes:
        k = n.get("kind")
        if k == "bonfire":
            bonfire = n
        elif k == "boss":
            boss_node = n
        elif k == "encounter":
            encounters.append(n)

    if not bonfire:
        if nodes:
            bonfire = nodes[0]
        else:
            return {}

    def extract_level(node: Dict[str, Any]) -> int:
        lvl = None
        if isinstance(node.get("frozen"), dict):
            lvl = node.get("frozen", {}).get("encounter_level")
        lvl = lvl or node.get("encounter_level") or node.get("level")
        try:
            return int(lvl)
        except Exception:
            return 1

    def label_for_encounter(node: Dict[str, Any]) -> str:
        lvl = extract_level(node)
        revealed = bool(node.get("revealed"))
        emoji_map = {
            1: "1️⃣",
            2: "2️⃣",
            3: "3️⃣",
            4: "4️⃣",
        }
        e = emoji_map.get(lvl, f"{min(lvl,9)}️⃣")
        if not revealed:
            return f"{e}Unknown"
        # Try to get a name from frozen data or node metadata
        name = None
        if isinstance(node.get("frozen"), dict):
            name = node.get("frozen", {}).get("encounter_name")
        name = name or node.get("encounter_name") or node.get("label")
        if not name:
            name = "Encounter"
        return f"{e}{name}"

    tiles[bonfire.get("id")] = {
        "id": bonfire.get("id"),
        # keep label text plain; renderer will add surrounding brackets
        "label": "🔥Bonfire",
        "kind": "bonfire",
        "x": 0,
        "y": 0,
        "level": 0,
        "neighbors": [],
    }

    occupied = {(0, 0)}

    pool = ["2"] * 3 + ["3"] * 2
    sampled = random.sample(pool, k=min(len(encounters), 4))
    pool_max_threes = pool.count("3")
    type_map: Dict[str, str] = {}
    for i, n in enumerate(encounters):
        typ = sampled[i] if i < len(sampled) else "2"
        type_map[n.get("id")] = typ

    dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    random.shuffle(dirs)
    use_two_bonfire = random.random() < 0.5 and len(encounters) >= 2

    # Place first encounter adjacent to bonfire
    placed_order: List[str] = []
    if len(encounters) >= 1:
        first = encounters[0]
        # pick any free direction
        placed_first = False
        random.shuffle(dirs)
        for dx, dy in dirs:
            cand = (dx, dy)
            if cand not in occupied:
                x, y = cand
                tiles[first.get("id")] = {
                    "id": first.get("id"),
                    "label": label_for_encounter(first),
                    "kind": "encounter",
                    "x": x,
                    "y": y,
                    "level": extract_level(first),
                    "neighbors": [],
                }
                occupied.add(cand)
                placed_order.append(first.get("id"))
                placed_first = True
                first_dir = (dx, dy)
                break
        if not placed_first:
            tiles[first.get("id")] = {
                "id": first.get("id"),
                "label": label_for_encounter(first),
                "kind": "encounter",
                "x": 1,
                "y": 0,
                "level": extract_level(first),
                "neighbors": [],
            }
            occupied.add((1, 0))
            placed_order.append(first.get("id"))
            first_dir = (1, 0)

    # Place second encounter adjacent to bonfire if allowed; avoid opposite of first
    connector_placed = False
    if len(encounters) >= 2 and use_two_bonfire:
        second = encounters[1]
        # choose a direction that's not the opposite of first_dir
        opp_map = {(1, 0): (-1, 0), (-1, 0): (1, 0), (0, 1): (0, -1), (0, -1): (0, 1)}
        forbidden = opp_map.get(first_dir)
        cand_dirs = [d for d in dirs if d != forbidden]
        random.shuffle(cand_dirs)
        placed_second = False
        for dx, dy in cand_dirs:
            cand = (dx, dy)
            if cand not in occupied:
                x, y = cand
                tiles[second.get("id")] = {
                    "id": second.get("id"),
                    "label": label_for_encounter(second),
                    "kind": "encounter",
                    "x": x,
                    "y": y,
                    "level": extract_level(second),
                    "neighbors": [],
                }
                occupied.add(cand)
                placed_order.append(second.get("id"))
                placed_second = True
                second_dir = (dx, dy)
                break
        if placed_second:
            # Step 3: place a tile that connects the two bonfire-adjacent tiles
            if len(encounters) >= 3:
                third = encounters[2]
                conn_x = first_dir[0] + second_dir[0]
                conn_y = first_dir[1] + second_dir[1]
                conn_pos = (conn_x, conn_y)
                if conn_pos not in occupied:
                    tiles[third.get("id")] = {
                        "id": third.get("id"),
                        "label": label_for_encounter(third),
                        "kind": "encounter",
                        "x": conn_x,
                        "y": conn_y,
                        "level": extract_level(third),
                        "neighbors": [],
                    }
                    occupied.add(conn_pos)
                    placed_order.append(third.get("id"))
                    connector_placed = True

    # Continue placing remaining encounters in order
    start_idx = 1
    if use_two_bonfire and len(encounters) >= 2:
        start_idx = 2
    # if connector was placed, skip the third since we've already placed it
    if connector_placed:
        start_idx = max(start_idx, 3)
    for i in range(start_idx, len(encounters)):
        n = encounters[i]
        # if this was already placed by connector logic, skip
        if n.get("id") in placed_order:
            continue
        # place adjacent to any already placed tile; prefer cells with larger manhattan
        # but avoid candidates that would force more opposite-edge (3-door) tiles
        # than the sampled pool provides.
        def count_required_threes_if(extra_pos: Optional[tuple] = None, extra_id: Optional[str] = None) -> int:
            temp_pos = {tid: (t["x"], t["y"]) for tid, t in tiles.items()}
            if extra_pos and extra_id:
                temp_pos[extra_id] = extra_pos
            pos_set = set(temp_pos.values())
            req = 0
            for enc in encounters:
                eid = enc.get("id")
                if eid not in temp_pos:
                    continue
                x0, y0 = temp_pos[eid]
                neigh_dirs = set()
                if (x0 + 1, y0) in pos_set:
                    neigh_dirs.add("E")
                if (x0 - 1, y0) in pos_set:
                    neigh_dirs.add("W")
                if (x0, y0 + 1) in pos_set:
                    neigh_dirs.add("S")
                if (x0, y0 - 1) in pos_set:
                    neigh_dirs.add("N")
                if ("N" in neigh_dirs and "S" in neigh_dirs and not ("E" in neigh_dirs or "W" in neigh_dirs)) or (
                    "E" in neigh_dirs and "W" in neigh_dirs and not ("N" in neigh_dirs or "S" in neigh_dirs)
                ):
                    req += 1
            return req

        available_threes = sampled.count("3")
        best = None
        best_dist = -1
        for px, py in list(occupied):
            for dx, dy in dirs:
                cand = (px + dx, py + dy)
                if cand in occupied:
                    continue
                # simulate placing here and ensure required threes <= available
                req = count_required_threes_if(extra_pos=cand, extra_id=n.get("id"))
                if req > available_threes:
                    continue
                dist = abs(cand[0]) + abs(cand[1])
                if dist > best_dist:
                    best = cand
                    best_dist = dist
        if best is None:
            # fallback: allow placement even if it may exceed available threes
            for px, py in list(occupied):
                for dx, dy in dirs:
                    cand = (px + dx, py + dy)
                    if cand in occupied:
                        continue
                    dist = abs(cand[0]) + abs(cand[1])
                    if dist > best_dist:
                        best = cand
                        best_dist = dist
        if best is None:
            best = (len(occupied) + 1, 0)
        x, y = best
        tiles[n.get("id")] = {
            "id": n.get("id"),
            "label": label_for_encounter(n),
            "kind": "encounter",
            "x": x,
            "y": y,
            "level": extract_level(n),
            "neighbors": [],
        }
        occupied.add((x, y))

    if boss_node and encounters:
        farthest = None
        far_dist = -1
        for n in encounters:
            nid = n.get("id")
            pos = (tiles[nid]["x"], tiles[nid]["y"])
            dist = abs(pos[0]) + abs(pos[1])
            if dist > far_dist:
                far_dist = dist
                farthest = n
        if farthest:
            fid = farthest.get("id")
            fx, fy = tiles[fid]["x"], tiles[fid]["y"]
            for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
                bx, by = fx + dx, fy + dy
                if (bx, by) in occupied:
                    continue
                tiles[boss_node.get("id")] = {
                    "id": boss_node.get("id"),
                    "label": boss_node.get("label") or boss_node.get("boss_name") or "Boss",
                    "kind": "boss",
                    "x": bx,
                    "y": by,
                    "level": extract_level(boss_node) or (tiles[fid].get("level") + 1),
                    "neighbors": [],
                }
                occupied.add((bx, by))
                break

    ids = list(tiles.keys())
    for a in ids:
        ax, ay = tiles[a]["x"], tiles[a]["y"]
        for b in ids:
            if a == b:
                continue
            bx, by = tiles[b]["x"], tiles[b]["y"]
            if abs(ax - bx) + abs(ay - by) == 1:
                tiles[a].setdefault("neighbors", []).append(b)

    def dir_from(a, b):
        ax, ay = a
        bx, by = b
        if bx == ax + 1 and by == ay:
            return "E"
        if bx == ax - 1 and by == ay:
            return "W"
        if bx == ax and by == ay + 1:
            return "S"
        if bx == ax and by == ay - 1:
            return "N"
        return None

    for tid, t in tiles.items():
        tpos = (t["x"], t["y"])
        n_dirs = []
        for nid in t.get("neighbors", []):
            other = tiles.get(nid)
            if not other:
                continue
            d = dir_from(tpos, (other["x"], other["y"]))
            if d:
                n_dirs.append((nid, d))
        t["neighbor_dirs"] = n_dirs

    # Ensure we have enough 3-door samples to satisfy any tiles that must be 3-door
    required_threes = 0
    bonfire_neighbors = set()
    if bonfire and bonfire.get("id") in tiles:
        bonfire_neighbors = set(n for n, _ in tiles[bonfire.get("id")].get("neighbor_dirs", []))
    for tid, t in tiles.items():
        if t.get("kind") != "encounter":
            continue
        nid_dirs = [d for (_, d) in t.get("neighbor_dirs", [])]
        neighbor_ids = [n for (n, _) in t.get("neighbor_dirs", [])]
        # Opposite-only neighbors require a 3-door tile
        if ("N" in nid_dirs and "S" in nid_dirs and not ("E" in nid_dirs or "W" in nid_dirs)) or (
            "E" in nid_dirs and "W" in nid_dirs and not ("N" in nid_dirs or "S" in nid_dirs)
        ):
            required_threes += 1
            continue
        # Any tile with 3+ neighbor directions must be a 3-door tile
        if len(nid_dirs) >= 3:
            required_threes += 1
            continue
        # If the tile connects two tiles that are both bonfire-adjacent, it must be 3-door
        if len(set(neighbor_ids) & bonfire_neighbors) >= 2:
            required_threes += 1

    attempts = 0
    max_attempts = 10
    # Cap required_threes to pool maximum (can't have more 3-tiles than pool provides)
    required_threes = min(required_threes, pool_max_threes)
    # Resample the initial tile-type pool until it contains enough '3' entries
    while sampled.count("3") < required_threes and attempts < max_attempts:
        sampled = random.sample(pool, k=min(len(encounters), 4))
        attempts += 1

    # Rebuild type_map from (possibly) updated sampled list
    type_map = {}
    for i, n in enumerate(encounters):
        typ = sampled[i] if i < len(sampled) else "2"
        type_map[n.get("id")] = typ

    allowed_count: Dict[str, int] = {}
    for tid, t in tiles.items():
        if t.get("kind") == "bonfire":
            allowed_count[tid] = 2 if use_two_bonfire else 1
        elif t.get("kind") == "boss":
            allowed_count[tid] = 1
        elif t.get("kind") == "encounter":
            # if structurally this tile requires three doors, enforce it
            nid_dirs = [d for (_, d) in t.get("neighbor_dirs", [])]
            neighbor_ids = [n for (n, _) in t.get("neighbor_dirs", [])]
            requires_three_flag = (
                ("N" in nid_dirs and "S" in nid_dirs and not ("E" in nid_dirs or "W" in nid_dirs))
                or ("E" in nid_dirs and "W" in nid_dirs and not ("N" in nid_dirs or "S" in nid_dirs))
                or len(nid_dirs) >= 3
                or len(set(neighbor_ids) & bonfire_neighbors) >= 2
            )
            if requires_three_flag:
                allowed_count[tid] = 3
            else:
                allowed_count[tid] = int(type_map.get(tid, "2"))
        else:
            allowed_count[tid] = 2

    for tid in tiles:
        tiles[tid]["doors"] = set()

    for nid, d in tiles[bonfire.get("id")].get("neighbor_dirs", []):
        if d and len(tiles[bonfire.get("id")]["doors"]) < allowed_count[bonfire.get("id")]:
            tiles[bonfire.get("id")]["doors"].add(d)

    if boss_node and boss_node.get("id") in tiles:
        bid = boss_node.get("id")
        nb = [n for n, _ in tiles[bid].get("neighbor_dirs", [])]
        # Prefer choosing the adjacent encounter that is farthest from the bonfire
        chosen = None
        best_dist = -1
        for n in nb:
            if tiles[n]["kind"] != "encounter":
                continue
            pos = (tiles[n]["x"], tiles[n]["y"])
            dist = abs(pos[0]) + abs(pos[1])
            if dist > best_dist:
                best_dist = dist
                chosen = n
        if chosen:
            d = dir_from((tiles[bid]["x"], tiles[bid]["y"]), (tiles[chosen]["x"], tiles[chosen]["y"]))
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if d and opp:
                tiles[bid]["doors"].add(d)
                if len(tiles[chosen]["doors"]) < allowed_count.get(chosen, 2):
                    tiles[chosen]["doors"].add(opp)

    adjacent_pairs = [("N","E"),("E","S"),("S","W"),("W","N")]
    for tid, t in tiles.items():
        if t.get("kind") != "encounter":
            continue
        nid_dirs = [d for (_, d) in t.get("neighbor_dirs", [])]
        typ = int(type_map.get(tid, "2"))
        # If this tile has 3+ neighbors or connects two bonfire-adjacent tiles,
        # it must be treated as a 3-door tile regardless of sampled type.
        neighbor_ids = [n for (n, _) in t.get("neighbor_dirs", [])]
        if len(nid_dirs) >= 3 or len(set(neighbor_ids) & bonfire_neighbors) >= 2:
            typ = max(typ, 3)
        if ("N" in nid_dirs and "S" in nid_dirs and not ("E" in nid_dirs or "W" in nid_dirs)) or ("E" in nid_dirs and "W" in nid_dirs and not ("N" in nid_dirs or "S" in nid_dirs)):
            typ = 3
        chosen_dirs: List[str] = []
        if typ >= 3:
            chosen_dirs = nid_dirs[:3]
        else:
            found = False
            for a,b in adjacent_pairs:
                if a in nid_dirs and b in nid_dirs:
                    chosen_dirs = [a,b]
                    found = True
                    break
            if not found:
                chosen_dirs = nid_dirs[:2]
        for d in chosen_dirs[:allowed_count.get(tid, len(chosen_dirs))]:
            tiles[tid]["doors"].add(d)
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            for nid, nd in t.get("neighbor_dirs", []):
                if nd == d:
                    # only add reciprocal door if the neighbor has available door slots
                    if len(tiles.get(nid, {}).get("doors", set())) < allowed_count.get(nid, 2):
                        tiles[nid].setdefault("doors", set()).add(opp)

    for tid, t in tiles.items():
        connected = []
        for nid, d in t.get("neighbor_dirs", []):
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if opp and d in t.get("doors", set()) and opp in tiles.get(nid, {}).get("doors", set()):
                connected.append(nid)
        t["connected"] = connected

    # Ensure each boss has at most one mutual doorway: if multiple were created,
    # keep the first mutual neighbor and remove other mutual doors on both sides.
    for tid, t in tiles.items():
        if t.get("kind") != "boss":
            continue
        mutual = []
        for nid, d in t.get("neighbor_dirs", []):
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if opp and d in t.get("doors", set()) and opp in tiles.get(nid, {}).get("doors", set()):
                mutual.append((nid, d))
        if len(mutual) <= 1:
            continue
        # keep the first mutual connection, remove the rest
        keep_nid, keep_dir = mutual[0]
        for rem_nid, rem_dir in mutual[1:]:
            # remove boss door
            if rem_dir in t.get("doors", set()):
                t["doors"].discard(rem_dir)
            # remove opposite door on neighbor
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(rem_dir)
            if opp and opp in tiles.get(rem_nid, {}).get("doors", set()):
                tiles[rem_nid]["doors"].discard(opp)

    # Recompute connected after any trimming
    for tid, t in tiles.items():
        connected = []
        for nid, d in t.get("neighbor_dirs", []):
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if opp and d in t.get("doors", set()) and opp in tiles.get(nid, {}).get("doors", set()):
                connected.append(nid)
        t["connected"] = connected

    # Repair loop: ensure each encounter has at least two mutual connections
    opp_map = {"N": "S", "S": "N", "E": "W", "W": "E"}
    changed = True
    passes = 0
    while changed and passes < 5:
        changed = False
        passes += 1
        for tid, t in tiles.items():
            if t.get("kind") != "encounter":
                continue
            cur_conn = set(t.get("connected", []))
            if len(cur_conn) >= 2:
                continue
            # try to add connections to neighbor encounters first
            for nid, d in t.get("neighbor_dirs", []):
                if nid in cur_conn:
                    continue
                if len(t.get("doors", set())) >= allowed_count.get(tid, 2):
                    break
                if len(tiles[nid].get("doors", set())) >= allowed_count.get(nid, 2):
                    continue
                opp = opp_map.get(d)
                if not opp:
                    continue
                # add reciprocal doors
                t["doors"].add(d)
                tiles[nid].setdefault("doors", set()).add(opp)
                # update connected lists
                t.setdefault("connected", []).append(nid)
                tiles[nid].setdefault("connected", []).append(tid)
                changed = True
                cur_conn.add(nid)
                if len(cur_conn) >= 2:
                    break
            # if still short, try connecting to bonfire or boss if adjacent and slots allow
            if len(cur_conn) < 2:
                for nid, d in t.get("neighbor_dirs", []):
                    if nid in cur_conn:
                        continue
                    if tiles[nid].get("kind") not in ("bonfire", "boss"):
                        continue
                    if len(t.get("doors", set())) >= allowed_count.get(tid, 2):
                        break
                    if len(tiles[nid].get("doors", set())) >= allowed_count.get(nid, 2):
                        continue
                    opp = opp_map.get(d)
                    if not opp:
                        continue
                    t["doors"].add(d)
                    tiles[nid].setdefault("doors", set()).add(opp)
                    t.setdefault("connected", []).append(nid)
                    tiles[nid].setdefault("connected", []).append(tid)
                    changed = True
                    cur_conn.add(nid)
                    if len(cur_conn) >= 2:
                        break

    # Final recompute of connected to reflect repairs
    for tid, t in tiles.items():
        connected = []
        for nid, d in t.get("neighbor_dirs", []):
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if opp and d in t.get("doors", set()) and opp in tiles.get(nid, {}).get("doors", set()):
                connected.append(nid)
        t["connected"] = connected

    # Final fix-up pass: repair one-sided doors by adding missing reciprocals when allowed
    opp_map = {"N":"S","S":"N","E":"W","W":"E"}
    changed = True
    fix_pass = 0
    while changed and fix_pass < 3:
        changed = False
        fix_pass += 1
        for tid, t in tiles.items():
            for nid, d in t.get("neighbor_dirs", []):
                opp = opp_map.get(d)
                if not opp:
                    continue
                me_has = d in t.get("doors", set())
                other_has = opp in tiles.get(nid, {}).get("doors", set())
                if me_has == other_has:
                    continue
                # if other has the door but I don't, try to add mine
                if other_has and not me_has:
                    if len(t.get("doors", set())) < allowed_count.get(tid, 2) and len(tiles[nid].get("doors", set())) <= allowed_count.get(nid, 2):
                        t.setdefault("doors", set()).add(d)
                        tiles[nid].setdefault("doors", set()).add(opp)
                        changed = True
                # if I have the door but other doesn't, try to add other
                elif me_has and not other_has:
                    if len(tiles[nid].get("doors", set())) < allowed_count.get(nid, 2) and len(t.get("doors", set())) <= allowed_count.get(tid, 2):
                        tiles[nid].setdefault("doors", set()).add(opp)
                        t.setdefault("doors", set()).add(d)
                        changed = True

    # Recompute connected one last time
    for tid, t in tiles.items():
        connected = []
        for nid, d in t.get("neighbor_dirs", []):
            opp = {"N":"S","S":"N","E":"W","W":"E"}.get(d)
            if opp and d in t.get("doors", set()) and opp in tiles.get(nid, {}).get("doors", set()):
                connected.append(nid)
        t["connected"] = connected

    # Attach a compact generator trace to help debug placement and assignments
    tiles["__gen_trace__"] = {
        "sampled": list(sampled),
        "type_map": dict(type_map),
        "required_threes": int(required_threes),
        "placed_order": list(placed_order),
        "allowed_count": {k: int(v) for k, v in allowed_count.items()},
        "occupied_positions": {k: (v["x"], v["y"]) for k, v in tiles.items() if isinstance(v, dict) and "x" in v},
    }

    return tiles


def _render_ascii_map(tiles: Dict[str, Dict[str, Any]], cur_id: str, visited: Optional[set] = None, completed: Optional[set] = None) -> str:
    if visited is None:
        visited = set()
    if completed is None:
        completed = set()

    coords = {tid: (t["x"], t["y"]) for tid, t in tiles.items()}
    xs = [c[0] for c in coords.values()] if coords else [0]
    ys = [c[1] for c in coords.values()] if coords else [0]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    # cell width adapts to the longest label to avoid clipping and double-bracketing
    import re

    def _measure_label(lbl: str) -> int:
        # Replace known long image/token patterns with a single visible
        # character so measurements don't inflate cell widths.
        if not isinstance(lbl, str):
            lbl = str(lbl or "")
        # common placeholder token pattern and any img tags or data URIs
        cleaned = re.sub(r"__SOULS_IMG_[^\s]*__", "◈", lbl)
        cleaned = re.sub(r"<img[^>]*>", "◈", cleaned)
        cleaned = re.sub(r"data:[^\s\"]+", "◈", cleaned)
        return len(cleaned)

    max_label_len = 0
    for t in tiles.values():
        lab = str(t.get("label") or "")
        l = _measure_label(lab)
        if l > max_label_len:
            max_label_len = l
    # Add padding for brackets and spacing
    cell_w = max(9, max_label_len + 4)
    cell_h = 3
    W = (maxx - minx + 1) * cell_w + 1
    H = (maxy - miny + 1) * cell_h + 1
    canvas = [[" "]*W for _ in range(H)]

    def center_pos(x, y):
        cx = (x - minx) * cell_w + cell_w//2
        cy = (y - miny) * cell_h + cell_h//2
        return cx, cy

    cell_positions: Dict[str, tuple[int, int, int]] = {}
    for tid, t in tiles.items():
        cx, cy = center_pos(t["x"], t["y"])
        label = str(t.get("label") or tid)
        # Use a cleaned short label for ASCII placement so long tokens or
        # data-URIs don't inflate the drawn width. Keep `label` unchanged
        # for later HTML replacement.
        def _clean_label(lbl: str) -> str:
            s = str(lbl or "")
            s = re.sub(r"__SOULS_IMG_[^\s]*__", "◈", s)
            s = re.sub(r"<img[^>]*>", "◈", s)
            s = re.sub(r"data:[^\s\"]+", "◈", s)
            return s
        short = _clean_label(label)
        cell_text = f"[{short}]"
        if tid == cur_id:
            cell_text = f"*{short}*"
        lx = cx - len(cell_text) // 2
        for i, ch in enumerate(cell_text):
            if 0 <= lx + i < W and 0 <= cy < H:
                canvas[cy][lx + i] = ch
        cell_positions[tid] = (cy, lx, len(cell_text))

    for a, ta in tiles.items():
        ax, ay = center_pos(ta["x"], ta["y"])
        for b in ta.get("connected", []):
            tb = tiles.get(b)
            if not tb:
                continue
            bx, by = center_pos(tb["x"], tb["y"])
            if ax == bx and ay == by:
                continue
            x0, x1 = sorted((ax, bx))
            for x in range(x0+1, x1):
                if canvas[ay][x] == " ":
                    canvas[ay][x] = "-"
                elif canvas[ay][x] == "|":
                    canvas[ay][x] = "+"
            y0, y1 = sorted((ay, by))
            for y in range(y0+1, y1):
                if canvas[y][bx] == " ":
                    canvas[y][bx] = "|"
                elif canvas[y][bx] == "-":
                    canvas[y][bx] = "+"

    full_lines = ["".join(row) for row in canvas]

    # Trim any uniform left-margin padding so the ASCII map is flush-left
    # while preserving internal spacing. Compute the minimum leading-space
    # count across non-empty lines and remove that many spaces from each
    # line. Keep insertion positions relative to the trimmed canvas.
    nonempty = [ln for ln in full_lines if ln.strip()]
    if nonempty:
        min_lead = min((len(ln) - len(ln.lstrip(" "))) for ln in nonempty)
    else:
        min_lead = 0

    insertions: Dict[int, List[tuple[int, str]]] = {}
    for tid, (cy, lx, length) in cell_positions.items():
        t = tiles.get(tid) or {}
        if t.get("kind") == "encounter" and tid not in completed:
            insertions.setdefault(cy, []).append((lx - min_lead, "<b>"))
            insertions.setdefault(cy, []).append((lx + length - min_lead, "</b>"))

    out_lines: List[str] = []
    for y, line in enumerate(full_lines):
        # remove uniform left padding
        if min_lead and len(line) >= min_lead:
            line = line[min_lead:]

        ins = insertions.get(y) or []
        if not ins:
            out_lines.append(line.rstrip())
            continue
        ins_sorted = sorted(ins, key=lambda x: x[0], reverse=True)
        s = line
        for pos, txt in ins_sorted:
            adj = max(0, pos)
            if adj > len(s):
                adj = len(s)
            s = s[:adj] + txt + s[adj:]
        out_lines.append(s.rstrip())

    return "\n".join(out_lines)

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

            # Load raw behavior JSON directly (cache-aware)
            json_path = Path("data") / "behaviors" / f"{boss_name}.json"
            raw_data = None
            try:
                from ui.campaign_mode.persistence import load_json_file

                raw_data = load_json_file(json_path)
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
                                src_o = bytes_to_data_uri(o_img, mime="image/png")
                                if not src_o:
                                    raise Exception("empty data uri")
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
                                src_s = bytes_to_data_uri(s_img, mime="image/png")
                                if not src_s:
                                    raise Exception("empty data uri")
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
                                        st.warning(
                                            f"Failed to render Ornstein & Smough data cards: {exc}"
                                        )
                else:
                    if boss_name == "Executioner's Chariot":
                        data_path = (
                            BEHAVIOR_CARDS_PATH
                            + "Executioner's Chariot - Skeletal Horse.jpg"
                        )
                    else:
                        data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                    try:
                        img = render_data_card_cached(
                            data_path,
                            raw_data,
                            is_boss=True,
                        )
                        try:
                            src = bytes_to_data_uri(img, mime="image/png")
                            if not src:
                                raise Exception("empty data uri")
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
            width="stretch",
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
                w = card_w()
                p = Path(rv["path"])
                try:
                    src = get_image_data_uri_cached(str(p))
                    if not src:
                        raise Exception("empty data uri")
                except Exception:
                    src = str(p)

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{src}" style="width:100%">
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
                try:
                    alt_idx_int = int(alt_idx) if alt_idx is not None else None
                except Exception:
                    alt_idx_int = None

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
                        "Apply choice",
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
                        w = card_w()
                        img_src = rv["path"]
                        src = get_image_data_uri_cached(img_src)
                        if src:
                            img_src = src

                        st.markdown(
                            f"""
                            <div class="card-image" style="width:{w}px">
                                <img src="{img_src}" style="width:100%">
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
            w = card_w()
            img_src = rv["path"]
            src = get_image_data_uri_cached(img_src)
            if src:
                img_src = src

            st.markdown(
                f"""
                <div class="card-image" style="width:{w}px">
                    <img src="{img_src}" style="width:100%">
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

    # 1) Pick up any dropped souls token that is sitting on this boss.
    # Support both the canonical `souls_token_*` fields and the older
    # `dropped_souls` fallback to ensure previously-recorded failures
    # are reclaimed when the space is completed.
    token_node_id = state.get("souls_token_node_id")
    token_amount = int(state.get("souls_token_amount") or 0)
    dropped_amount = int(state.get("dropped_souls") or 0)

    try:
        tid = None if token_node_id is None else str(token_node_id)
        nid = None if node_id is None else str(node_id)
    except Exception:
        tid = token_node_id
        nid = node_id

    if tid is not None and nid is not None and tid == nid and (token_amount > 0 or dropped_amount > 0):
        # Use the larger of the two amounts to avoid double-counting when
        # both fields exist (they represent the same dropped amount).
        pickup = max(token_amount, dropped_amount)
        current_souls += pickup
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0
        state.pop("dropped_souls", None)

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
    reset_all_encounters_on_bonfire_return(campaign)

    # 5) Party returns to the bonfire, without spending a Spark here
    campaign["current_node_id"] = "bonfire"
    state["campaign"] = campaign

    # Clear any stale "dropped_souls" trackers if you use them elsewhere
    state.pop("dropped_souls", None)

    # Force the Sparks widget to re-seed from updated state on rerun
    if version == "V2":
        st.session_state.pop("campaign_v2_sparks_campaign", None)
    else:
        st.session_state.pop("campaign_v1_sparks_campaign", None)

    st.session_state[state_key] = state

    st.success(
        "Boss defeated; rewards applied and the party has returned to the bonfire."
    )
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
    # Use public API re-export from ui.campaign_mode.api
    record_dropped_souls(state, failed_node_id, current_souls)

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
    reset_all_encounters_on_bonfire_return(campaign)

    # Party returns to the bonfire
    campaign["current_node_id"] = "bonfire"
    state["campaign"] = campaign
    # Force the Sparks and Soul cache widgets to re-seed on rerun
    if version == "V2":
        st.session_state.pop("campaign_v2_sparks_campaign", None)
        st.session_state.pop("campaign_v2_souls_campaign", None)
    else:
        st.session_state.pop("campaign_v1_sparks_campaign", None)
        st.session_state.pop("campaign_v1_souls_campaign", None)

    st.session_state[state_key] = state

    # Clear encounter-specific session data
    st.session_state["encounter_events"] = []
    st.session_state["last_encounter_reward_totals"] = {}
    st.session_state.pop("last_encounter_rewards_for_slug", None)

    if sparks_cur > 0:
        st.warning("Boss failed; party returned to the bonfire and lost 1 Spark.")
    else:
        st.warning("Boss failed; party returned to the bonfire but has no Sparks left.")
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
            width="stretch",
        ):
            _apply_boss_defeated(state, campaign, current_node, version)

    with col_fail:
        if st.button(
            "Boss failed (return to bonfire, lose 1 Spark)",
            key=f"campaign_{version.lower()}_boss_failed",
            width="stretch",
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
        src = bytes_to_data_uri(buf.getvalue(), mime="image/png")

        st.markdown(
            f"""
            <div class="card-image">
                <img src="{src}" style="width:100%">
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("Failed to render encounter card.")
