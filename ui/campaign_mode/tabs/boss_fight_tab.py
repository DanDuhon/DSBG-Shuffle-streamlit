import streamlit as st
from typing import Any, Dict, Optional

from ui.shared.behavior_session_state import ensure_behavior_session_state

from ui.boss_mode.state import ensure_boss_state
from ui.boss_mode.panels.combat_controls import render_combat_controls
from ui.boss_mode.panels.current_card import render_current_card_column
from ui.boss_mode.panels.heatup_prompt import render_heatup_prompt
from ui.boss_mode.panels.options import render_boss_info_and_options
from ui.boss_mode.panels.data_card import render_data_card_column
from ui.boss_mode.panels.selector import get_or_build_catalog

from ui.campaign_mode.state import (
    _ensure_v1_state,
    _ensure_v2_state,
    _get_settings,
    _get_player_count,
)
from ui.campaign_mode.tabs.manage_tab_shared import _render_boss_outcome_controls


def _find_boss_entry_by_name(*, catalog: Dict[str, Any], boss_name: str) -> Optional[Any]:
    target = str(boss_name or "").strip()
    if not target:
        return None

    for _cat, entries in (catalog or {}).items():
        for entry in entries or []:
            if getattr(entry, "name", None) == target:
                return entry
    return None


def _resolve_current_campaign_boss_name(*, campaign: Dict[str, Any], current_node: Dict[str, Any]) -> Optional[str]:
    if not isinstance(current_node, dict) or current_node.get("kind") != "boss":
        return None

    stage = current_node.get("stage")
    bosses_info = (campaign.get("bosses") or {}).get(stage, {}) if isinstance(campaign, dict) else {}
    if isinstance(bosses_info, dict):
        boss_name = bosses_info.get("name")
        if boss_name:
            return str(boss_name)

    boss_name = current_node.get("boss_name")
    return str(boss_name) if boss_name else None


def _render_campaign_boss_fight_tab(*_args, **_kwargs) -> None:
    """Campaign Mode tab: trimmed Boss Mode fight view for the current boss space.

    - Always visible.
    - If the party is not on a boss node, shows a caption.
    - If on a boss node, renders Boss Mode UI (no selector) for that boss.
    - Includes boss victory/failure buttons (moved from Manage Campaign).

    Note: Combat controls in Boss Mode rely on `st.session_state["boss_mode_choice"]`.
    This tab sets that key behind the scenes for the current campaign boss.
    """

    st.markdown("### Boss Fight")

    settings = _get_settings()
    player_count = _get_player_count(settings)

    active_version = st.session_state.get("campaign_rules_version", "V1")
    if active_version not in ("V1", "V2"):
        active_version = "V1"

    state_key = "campaign_v1_state" if active_version == "V1" else "campaign_v2_state"
    active_state = st.session_state.get(state_key)
    if not isinstance(active_state, dict) or not isinstance(active_state.get("campaign"), dict):
        st.info("No campaign is currently loaded. Generate or load one in the Setup tab.")
        return

    # Normalize state (sparks/souls) for the active version.
    state = _ensure_v1_state(player_count) if active_version == "V1" else _ensure_v2_state(player_count)
    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("No campaign data found. Generate a campaign in the Setup tab.")
        return

    nodes = campaign.get("nodes") or []
    if not nodes:
        st.info("Campaign has no nodes; regenerate it from the Setup tab.")
        return

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id", "bonfire")
    current_node = node_by_id.get(current_id) or nodes[0]

    # Keep campaign pointer normalized.
    campaign["current_node_id"] = current_node.get("id", "bonfire")
    state["campaign"] = campaign
    st.session_state[state_key] = state

    boss_name = _resolve_current_campaign_boss_name(campaign=campaign, current_node=current_node)
    if not boss_name:
        st.caption(
            "No boss on the current space. When you move onto a boss node, this tab becomes your Boss Mode view."
        )
        return

    stage = current_node.get("stage")
    prefix_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
    prefix = prefix_map.get(stage, "Boss")
    st.markdown(f"**{prefix}: {boss_name}**")

    ensure_behavior_session_state()
    catalog = get_or_build_catalog()
    entry = _find_boss_entry_by_name(catalog=catalog, boss_name=boss_name)
    if not entry:
        st.warning(f"Boss '{boss_name}' was not found in the Boss Mode catalog.")
        st.caption(
            "If this boss is custom, ensure its behavior JSON exists under data/behaviors and is included in the catalog."
        )
        return

    # Combat controls rely on boss_mode_choice callbacks; set it behind the scenes.
    st.session_state["boss_mode_choice"] = entry
    st.session_state["boss_mode_choice_name"] = getattr(entry, "name", boss_name)
    if getattr(entry, "category", None):
        st.session_state["boss_mode_category"] = entry.category

    boss_state, cfg = ensure_boss_state(entry)

    # --- Info / options row
    col_title, col_info = st.columns([2, 1])
    with col_title:
        st.caption("Use Draw / Heat-Up to run the boss deck.")
    with col_info:
        render_boss_info_and_options(cfg=cfg, state=boss_state)

    # Draw / Heat-up buttons
    if not st.session_state.get("ui_compact", False):
        from ui.shared.health_tracker import render_health_tracker

        c_hp_btns = st.columns([1, 1])
        with c_hp_btns[0]:
            cfg.entities = render_health_tracker(cfg, boss_state)
        with c_hp_btns[1]:
            render_combat_controls(where="top")

    render_heatup_prompt(cfg=cfg, state=boss_state)

    # --- Main fight view
    col_left, col_right = st.columns([1, 1])
    with col_left:
        render_data_card_column(cfg=cfg, state=boss_state)
    with col_right:
        render_current_card_column(cfg=cfg, state=boss_state)

    if st.session_state.get("ui_compact", False):
        render_combat_controls(where="bottom")

    st.markdown("---")
    _render_boss_outcome_controls(state, campaign, current_node)
