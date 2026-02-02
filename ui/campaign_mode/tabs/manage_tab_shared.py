# ui/campaign_mode/manage_tab_shared.py
import streamlit as st
from typing import Any, Dict, Optional

from core import auth
from ui.campaign_mode.persistence import get_campaigns, _save_campaigns

from core.settings_manager import _has_supabase_config, is_streamlit_cloud
from ui.campaign_mode.persistence.dirty import set_campaign_baseline
from ui.campaign_mode.core import (
    _reset_all_encounters_on_bonfire_return,
    _record_dropped_souls,
)
from ui.encounter_mode.tabs.setup_tab import render_original_encounter
from ui.encounter_mode.generation import load_encounter_data
from ui.campaign_mode.helpers import get_player_count_from_settings


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
    token_node_id = state.get("souls_token_node_id")
    token_amount = int(state.get("souls_token_amount") or 0)
    dropped_amount = int(state.get("dropped_souls") or 0)

    tid = None if token_node_id is None else str(token_node_id)
    nid = None if node_id is None else str(node_id)

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

    # 4) When the party returns to the bonfire, clear completion on all encounters.
    # This applies to both V1 and V2; shortcuts remain valid.
    _reset_all_encounters_on_bonfire_return(campaign)

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
            "Boss defeated ✅ (close chapter)",
            key=f"campaign_{version.lower()}_boss_defeated",
            width="stretch",
        ):
            _apply_boss_defeated(state, campaign, current_node, version)

    with col_fail:
        if st.button(
            "Boss failed ❌ (return to bonfire, lose 1 Spark)",
            key=f"campaign_{version.lower()}_boss_failed",
            width="stretch",
        ):
            _apply_boss_failure(state, campaign, current_node, version)


def _render_campaign_encounter_card(frozen: Dict[str, Any]) -> None:
    """
    Shared helper to render a frozen campaign encounter card (V1 or V2).
    """
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

    expansion = frozen.get("expansion")
    level = frozen.get("encounter_level")
    name = frozen.get("encounter_name")
    enemies = frozen.get("enemies") or []

    if not expansion or level is None or not name:
        st.caption("Encounter card data incomplete.")
        return

    encounter_data = frozen.get("encounter_data")
    use_edited = bool(frozen.get("edited", False))

    # If generation/persistence stripped full encounter JSON, load it on demand
    if not encounter_data:
        # Determine player count from user settings so we load the correct variant
        settings = st.session_state.get("user_settings") or {}
        player_count = int(get_player_count_from_settings(settings))
        encounter_data = load_encounter_data(expansion, name, character_count=player_count, level=level)

    res = render_original_encounter(
        encounter_data,
        expansion,
        name,
        level,
        use_edited,
        enemies=enemies,
        include_bytes=not cloud_low_memory,
    )
    if res and res.get("ok"):
        img = res["card_img"]

        st.image(img, width="stretch")
    else:
        st.warning("Failed to render encounter card.")


def _render_campaign_save_controls(
    *,
    version: str,
    state: Dict[str, Any],
    settings: Dict[str, Any],
) -> None:
    """Save the current campaign snapshot (no load controls).

    Intended for the Manage Campaign tab, under the "Current space" panel.

    Persists to the same backing store used by the Setup tab so users can
    later load it from there.
    """
    version = (version or "").upper() or "V1"

    st.markdown("---")
    st.markdown("##### Save campaign")

    cloud_mode = bool(is_streamlit_cloud())
    supabase_ready = bool(_has_supabase_config())
    can_persist = (not cloud_mode) or (supabase_ready and auth.is_authenticated())
    if cloud_mode and not supabase_ready:
        st.caption("Saving is disabled until Supabase is configured.")
    elif cloud_mode and not auth.is_authenticated():
        st.caption("Log in to save.")

    campaigns = get_campaigns()
    saved_names = sorted((campaigns or {}).keys())

    pick_key = f"campaign_manage_save_pick_{version.lower()}"
    name_key = f"campaign_manage_save_name_{version.lower()}"
    default_name = str(state.get("name") or "").strip()

    if name_key not in st.session_state:
        st.session_state[name_key] = default_name

    def _sync_selected_name_to_text() -> None:
        selected = st.session_state.get(pick_key)
        if isinstance(selected, str) and selected and selected != "<type a new name>":
            st.session_state[name_key] = selected

    if saved_names:
        options = ["<type a new name>"] + saved_names
        index = 0
        if default_name and default_name in saved_names:
            try:
                index = options.index(default_name)
            except Exception:
                index = 0

        st.selectbox(
            "Saved campaign names",
            options=options,
            index=index,
            key=pick_key,
            on_change=_sync_selected_name_to_text,
        )
    else:
        st.caption("No saved campaigns yet — type a name to create one.")

    name_input = st.text_input(
        "Name to save as",
        key=name_key,
        placeholder="e.g. Friday night run",
    )

    name_now = str(st.session_state.get(name_key) or "").strip()
    exists_already = bool(name_now) and name_now in (campaigns or {})
    overwrite_ok_key = f"campaign_manage_save_overwrite_ok_{version.lower()}"
    overwrite_ok = True
    if exists_already:
        overwrite_ok = bool(
            st.checkbox(
                "Overwrite existing saved campaign",
                key=overwrite_ok_key,
                value=False,
            )
        )

    if st.button(
        "Save campaign 💾",
        key=f"campaign_manage_save_btn_{version.lower()}",
        width="stretch",
        disabled=not can_persist,
    ):
        name = str(name_input or "").strip()
        if not name:
            st.error("Campaign name is required to save.")
            return

        if not can_persist:
            st.error("Not logged in; cannot persist on Streamlit Cloud.")
            return

        if name in (campaigns or {}) and not overwrite_ok:
            st.warning("That name already exists — confirm overwrite to replace it.")
            return

        # For V1/V2, a generated campaign graph is required to resume later.
        if version in ("V1", "V2") and not isinstance(state.get("campaign"), dict):
            st.error(
                "Generate the campaign before saving; this save currently has no encounters."
            )
            return

        state["name"] = name
        snapshot = {
            "rules_version": version,
            "state": state,
            "sidebar_settings": {
                "active_expansions": settings.get("active_expansions"),
                "selected_characters": settings.get("selected_characters"),
                "ngplus_level": int(st.session_state.get("ngplus_level", 0)),
            },
        }

        campaigns[name] = snapshot
        _save_campaigns(campaigns)
        set_campaign_baseline(version=version, state=state)
        st.success(f"Saved campaign '{name}'.")