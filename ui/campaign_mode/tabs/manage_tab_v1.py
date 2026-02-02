# ui/campaign_mode/manage_tab_v1.py
import streamlit as st
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.behavior.generation import (
    render_data_card_cached,
    render_data_card_uncached,
    render_dual_boss_data_cards,
)
from ui.campaign_mode.core import (
    BONFIRE_ICON_PATH,
    _default_sparks_max,
    _describe_v1_node_label,
    _reset_all_encounters_on_bonfire_return,
)
from ui.campaign_mode.tabs.manage_tab_shared import (
    _render_boss_outcome_controls,
    _render_campaign_encounter_card,
    _render_campaign_save_controls,
)
from ui.campaign_mode.state import _get_settings, _get_player_count
from ui.campaign_mode.ui_helpers import _render_party_icons


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
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

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

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            # In compact UI, wrap the bonfire image in a collapsed expander to save space.
            if bool(st.session_state.get("ui_compact")):
                with st.expander("Bonfire", expanded=False):
                    st.image(str(BONFIRE_ICON_PATH), width="stretch")
            else:
                st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            # Party icons above everything
            if cloud_low_memory:
                chars = list(settings.get("selected_characters") or [])
                if chars:
                    st.markdown("##### Party")
                    st.caption(", ".join(str(c) for c in chars[:4]))
            else:
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

        # Layout cache:
        # `_generate_v1_layout(...)` is moderately expensive and sensitive to transient
        # node metadata. Cache one layout per stage under:
        #   state["_last_layouts"][stage] = {"key": <layout_key>, "layout": <tiles>}
        # where `layout_key` is a stable fingerprint of the node identities + frozen
        # encounter labels for that stage. Cached tiles are stored JSON-friendly
        # (e.g., door sets become lists) and rehydrated on read.
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
                    return int(lv or 0)

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
                            tile["label"] = f"{tile.get('label')} (souls)"
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
                            tile["label"] = f"{tile.get('label')} (souls)"

                map_html = _render_ascii_map(ascii_tiles, current_id, visited=set(state.get("visited_nodes") or []), completed={n.get("id") for n in nodes if n.get("status")=="complete"})
                lines = map_html.split("\n")
                safe_lines = [ln.replace(" ", "&nbsp;") for ln in lines]
                html = (
                    '<div style="overflow:auto; white-space:nowrap; font-family:monospace; max-width:100%;">'
                    + '<div style="display:inline-block; padding:0.25rem;">'
                    + "<br>".join(safe_lines)
                    + "</div></div>"
                )

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
            "Rest at Bonfire (spend 1 Spark) 🔥",
            key="v1_return_button",
            width="stretch",
            disabled=disable_return_button,
        ):
            _reset_all_encounters_on_bonfire_return(campaign)
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

            # Reachability BFS:
            # - Targets are *incomplete* encounter/boss nodes adjacent via `tiles[*]["connected"]`.
            # - Traversal may pass through the bonfire and nodes with status == "complete".
            # - Traversal stops at the first incomplete encounter/boss (it is a target, but we
            #   do not continue beyond it), preventing "skipping" unresolved nodes.
            # - `reachable_paths[target]` stores the reconstructed node-id path for UI hints.

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
        _render_campaign_save_controls(version="V1", state=state, settings=settings)
        _render_boss_outcome_controls(state, campaign, current_node)

    # Persist updated state
    st.session_state["campaign_v1_state"] = state
        

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

    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

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
                    st.image(o_img, width="stretch")
                with s_col:
                    st.image(s_img, width="stretch")
            else:
                if boss_name == "Executioner's Chariot":
                    data_path = (
                        BEHAVIOR_CARDS_PATH + "Executioner's Chariot - Skeletal Horse.jpg"
                    )
                else:
                    data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"

                # Cloud low-memory: still show images, but avoid Streamlit cache
                # retention of large PNG bytes.
                if cloud_low_memory:
                    img = render_data_card_uncached(
                        data_path,
                        raw_data,
                        is_boss=True,
                    )
                else:
                    img = render_data_card_cached(
                        data_path,
                        raw_data,
                        is_boss=True,
                    )
                st.image(img, width="stretch")
        else:
            st.markdown(f"**{prefix}: Unknown**")
            st.caption("No boss selected for this space.")

        st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)

        if st.button(
            "Start Boss Fight ⚔️",
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
        return int(lvl or 0)

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
        cleaned = re.sub(r"<img[^>]*>", "◈", lbl)
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