#ui/campaign_mode/play_tab.py
import streamlit as st
from pathlib import Path
from typing import Any, Dict, Optional
from core.settings_manager import save_settings
from ui.campaign_mode.core import (
    _describe_v1_node_label,
    _describe_v2_node_label,
    _reset_all_encounters_on_bonfire_return,
    _record_dropped_souls,
    _campaign_find_next_encounter_node,
)
from ui.campaign_mode.state import (
    _get_player_count,
    _get_settings,
    _ensure_v1_state,
    _ensure_v2_state,
    queue_widget_set,
)
from ui.encounter_mode.tabs import play_tab as encounter_play_tab
from ui.event_mode.logic import (
    load_event_configs,
    ensure_event_deck_ready,
    draw_event_card,
    DECK_STATE_KEY,
    compute_draw_rewards_for_card,
    RENDEZVOUS_EVENTS,
    CONSUMABLE_EVENTS,
    IMMEDIATE_EVENTS,
)


def _event_kind_for_card(base_id: str, configs: Dict[str, Any]) -> str:
    bid = str(base_id or "")
    if bid in RENDEZVOUS_EVENTS:
        return "rendezvous"
    if bid in CONSUMABLE_EVENTS:
        return "consumable"
    if bid in IMMEDIATE_EVENTS:
        return "instant"

    cfg = configs.get(bid)
    if isinstance(cfg, dict):
        raw = str(
            cfg.get("kind")
            or cfg.get("type")
            or cfg.get("event_type")
            or cfg.get("category")
            or cfg.get("timing")
            or ""
        ).lower()
        if "rendez" in raw:
            return "rendezvous"
        if "consum" in raw:
            return "consumable"
        if "instant" in raw:
            return "instant"


def _ensure_event_deck_ready(settings: Dict[str, Any], configs: Dict[str, Any]) -> Optional[str]:
    # Backward-compatible wrapper around the shared helper.
    return ensure_event_deck_ready(settings, configs=configs)


def _consume_fight_attached_events(state: Dict[str, Any], current_node: Dict[str, Any]) -> None:
    # Clear party consumables after the fight resolves
    if isinstance(state.get("party_consumable_events"), list):
        state["party_consumable_events"] = []

    # Remove rendezvous from this node after it has been used in the fight
    if isinstance(current_node, dict):
        current_node.pop("rendezvous_event", None)


def _inject_fight_events_into_session(
    *,
    state: Dict[str, Any],
    current_node: Dict[str, Any],
) -> None:
    """Bridge Campaign-attached events into Encounter Mode's expected session keys.

    Writes:
    - `st.session_state["encounter_events"]`: list[dict]
      Each dict includes a "path" to an event card image and flags like:
        - "is_rendezvous" (attached to this encounter node)
        - "is_consumable" (party-held; applies to next fight)

    Encounter Mode's Play tab reads `encounter_events` to display/apply events as
    part of the fight UI.
    """
    events = []

    rv = current_node.get("rendezvous_event")
    if isinstance(rv, dict) and rv.get("path"):
        e = dict(rv)
        e["is_rendezvous"] = True
        events.append(e)

    consumables = state.get("party_consumable_events") or []
    if isinstance(consumables, list):
        for ev in consumables:
            if not isinstance(ev, dict) or not ev.get("path"):
                continue
            e = dict(ev)
            e["is_rendezvous"] = False
            e["is_consumable"] = True
            events.append(e)

    st.session_state["encounter_events"] = events


def _draw_and_apply_campaign_events(
    *,
    count: int,
    campaign: Dict[str, Any],
    state: Dict[str, Any],
    from_node_id: str,
    settings: Dict[str, Any],
) -> Dict[str, int]:
    """
    Draw `count` events immediately and route by type:
      - rendezvous -> attach to next encounter node (skip bosses)
      - consumable -> attach to party
      - instant -> add to unresolved list

    Returns counters: {"drawn": x, "rendezvous": a, "consumable": b, "instant": c}
    """
    # Routing rules:
    # - rendezvous cards attach to the next *encounter* node (never bosses)
    # - consumables attach to party state for the next fight
    # - instants are recorded for later resolution
    out = {
        "drawn": 0, "rendezvous": 0, "consumable": 0, "instant": 0,
        "instant_events": [], "consumable_events": [], "rendezvous_events": [],
    }

    configs = load_event_configs()
    preset = _ensure_event_deck_ready(settings, configs=configs)
    if not preset:
        return out

    player_count = _get_player_count(settings)

    for _ in range(max(0, int(count))):
        card_path = draw_event_card()
        deck_state = st.session_state.get(DECK_STATE_KEY)
        if deck_state:
            settings["event_deck"] = deck_state
            save_settings(settings)

        if not card_path:
            break

        base = Path(str(card_path)).stem
        kind = _event_kind_for_card(base, configs=configs)

        ev = {
            "id": base,
            "name": base,
            "path": str(card_path),
            "kind": kind,
            "is_rendezvous": (kind == "rendezvous"),
        }

        # Apply any draw-time rewards (souls, etc.)
        draw_totals = compute_draw_rewards_for_card(card_path, player_count=player_count)
        souls_delta = int(draw_totals.get("souls") or 0)
        if souls_delta:
            state["souls"] = int(state.get("souls") or 0) + souls_delta

        if kind == "rendezvous":
            target = _campaign_find_next_encounter_node(campaign, from_node_id)
            if target is None:
                state.setdefault("orphaned_rendezvous_events", [])
                state["orphaned_rendezvous_events"].append(ev)
            else:
                # overwrite semantics
                target["rendezvous_event"] = ev
            out["rendezvous"] += 1
            out["rendezvous_events"].append(ev)

        elif kind == "consumable":
            state.setdefault("party_consumable_events", [])
            state["party_consumable_events"].append(ev)
            out["consumable"] += 1
            out["consumable_events"].append(ev)

        else:
            state.setdefault("instant_events_unresolved", [])
            state["instant_events_unresolved"].append(ev)
            out["instant"] += 1
            out["instant_events"].append(ev)

        out["drawn"] += 1

    return out


def _sync_current_encounter_from_campaign_for_play(*_args, **_kwargs) -> bool:
    """Ensure Encounter Mode is pointed at the encounter for the party's current campaign node.

    Reads:
    - `st.session_state["campaign_rules_version"]` to choose V1/V2 state
    - `st.session_state["campaign_v1_state"]` / `st.session_state["campaign_v2_state"]`

    Writes (Encounter Mode bridge):
    - `st.session_state.current_encounter`: encounter dict shaped like Encounter Mode expects
    - `st.session_state["last_encounter"]`: metadata used by timers/labels/reward accounting
    - Initializes `st.session_state.encounter_events` if missing (events are injected separately)

    Returns:
    - True if a valid encounter node was resolved and loaded
    - False if the party is at bonfire/boss/non-encounter, or if V2 has no choice selected yet
    """
    version = st.session_state.get("campaign_rules_version", "V1")
    state_key = "campaign_v1_state" if version == "V1" else "campaign_v2_state"

    state = st.session_state.get(state_key)
    if not isinstance(state, dict):
        # No campaign generated/loaded yet.
        return False

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        # State exists but campaign payload missing.
        return False

    nodes = campaign.get("nodes") or []
    if not nodes:
        return False

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id") or "bonfire"
    current_node = node_by_id.get(current_id) or nodes[0]

    if current_node.get("kind") != "encounter":
        # Party is at bonfire or boss (or something non-playable).
        return False

    # Resolve frozen encounter for this node
    if version == "V1":
        frozen = current_node.get("frozen") or {}
    else:
        options = current_node.get("options") or []
        choice_idx = current_node.get("choice_index")
        if not isinstance(choice_idx, int) or not (0 <= choice_idx < len(options)):
            # V2: no choice made yet for this space.
            return False
        frozen = options[choice_idx] or {}

    if not isinstance(frozen, dict) or not frozen:
        return False

    # Build encounter dict in the shape Encounter Mode expects
    encounter = dict(frozen)

    expansion = encounter.get("expansion")
    level = encounter.get("encounter_level")
    name = encounter.get("encounter_name")

    # Best-effort slug; Encounter Mode play_state falls back to name anyway
    if expansion and level is not None and name:
        level_int = int(level)
        slug = f"{expansion}_{level_int}_{name}"
    else:
        slug = (
            encounter.get("slug")
            or encounter.get("encounter_name")
            or "campaign_encounter"
        )

    encounter.setdefault("slug", slug)

    st.session_state.current_encounter = encounter

    # Ensure events list exists so play panels don't explode.
    if "encounter_events" not in st.session_state:
        st.session_state.encounter_events = []

    # Maintain last_encounter metadata so timers / labels behave as expected.
    settings = _get_settings()
    # Use centralized helper to determine player count
    from ui.campaign_mode.helpers import get_player_count_from_settings

    character_count = int(get_player_count_from_settings(settings))

    st.session_state["last_encounter"] = {
        "label": name or slug,
        "slug": slug,
        "expansion": expansion,
        "character_count": character_count,
        "edited": bool(encounter.get("edited", False)),
        "enemies": encounter.get("enemies") or [],
        "expansions_used": encounter.get("expansions_used") or [],
    }

    return True


def _render_campaign_play_tab(
    bosses_by_name: Dict[str, Any],
    invaders: Dict[str, Any],
) -> None:
    """
    Campaign Play tab.

    - Uses Encounter Mode's Play tab to actually run the encounter.
    - Reads the last encounter's reward totals to:
        - Add souls to the campaign soul cache.
        - Queue up event rewards so they are attached to the *next encounter*
          space (never bosses).
    """
    settings = _get_settings()

    # Always use the authoritative rules version for selecting the active campaign.
    active_version = st.session_state.get("campaign_rules_version", "V1")
    if active_version not in ("V1", "V2"):
        active_version = "V1"

    state_key = "campaign_v1_state" if active_version == "V1" else "campaign_v2_state"
    active_state = st.session_state.get(state_key)
    if not isinstance(active_state, dict) or not isinstance(active_state.get("campaign"), dict):
        st.info("No campaign is currently loaded. Use the Campaign tab to generate or load one.")
        return

    # Normalize state (sparks/souls) for the active version
    player_count = _get_player_count(settings)
    state = _ensure_v1_state(player_count) if active_version == "V1" else _ensure_v2_state(player_count)

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("No campaign data found. Generate a campaign from the Setup tab.")
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
    st.session_state[state_key] = state

    kind = current_node.get("kind")

    # Only the encounter spaces have something to play here.
    if kind != "encounter":
        label = (
                _describe_v2_node_label(campaign, current_node)
                if active_version == "V2"
                else _describe_v1_node_label(campaign, current_node)
            )
        st.info(f"There is no regular encounter to play here.")
        return

    # Ensure Encounter Mode's current_encounter matches this campaign node.
    has_valid_encounter = _sync_current_encounter_from_campaign_for_play()
    _inject_fight_events_into_session(state=state, current_node=current_node)

    # In V2, an encounter space with no choice selected yet is not playable.
    if not has_valid_encounter:
        if active_version == "V2":
            label = _describe_v2_node_label(campaign, current_node)
            st.info(
                f"Choose an encounter for this space on the Campaign tab before playing it."
            )
        return

    encounter = st.session_state.get("current_encounter")
    if not encounter:
        st.info("No encounter is available on this space.")
        return

    # Finally, render the normal Encounter Mode Play tab for the current encounter.
    # using the shared user settings just like Encounter Mode does.
    encounter_play_tab.render(settings, True)

    st.markdown("---")

    # ---- Campaign outcome from the LAST encounter you played in Encounter Mode ----
    st.markdown("#### Campaign Outcome")

    reward_totals = st.session_state.get("last_encounter_reward_totals") or {}

    # Only use rewards if they were produced by the encounter currently
    # loaded into Campaign Play; otherwise ignore them.
    current_encounter = st.session_state.get("current_encounter") or {}
    current_slug = current_encounter.get("slug")
    rewards_slug = st.session_state.get("last_encounter_rewards_for_slug")

    if not reward_totals or not current_slug or rewards_slug != current_slug:
        reward_totals = {}

    reward_souls = int(reward_totals.get("souls") or 0)

    reward_treasure = int(reward_totals.get("treasure") or 0)

    # Shortcut rewards can come from the encounter or attached events
    reward_shortcuts = int(reward_totals.get("shortcut") or 0)

    current_souls = int(state.get("souls", 0))

    # Dropped souls associated with this encounter (from a previous failure)
    dropped_souls = 0
    souls_token_node_id = state.get("souls_token_node_id")
    if (
        souls_token_node_id
        and current_node is not None
        and current_node.get("id") == souls_token_node_id
    ):
        dropped_souls = int(state.get("souls_token_amount") or 0)

    # Event rewards only make sense for V2 campaigns
    reward_events = 0
    if active_version == "V2":
        reward_events = int(reward_totals.get("event", 0)) + 1

    # Treat already-completed encounters as resolved: no further outcome buttons.
    encounter_is_complete = (
        current_node is not None
        and current_node.get("kind") == "encounter"
        and current_node.get("status") == "complete"
    )

    has_any_rewards = (
        (reward_souls > 0)
        or (reward_treasure > 0)
        or (dropped_souls > 0)
        or (reward_events > 0)
        or (reward_shortcuts > 0)
    )

    if encounter_is_complete:
        st.info(
            "This encounter has already been resolved in the campaign; "
            "rewards have already been applied."
        )
    else:
        if not has_any_rewards:
            st.caption("No soul, treasure, shortcut, or event rewards are configured for this encounter.")
        else:
            if reward_souls > 0:
                st.markdown(f"- Souls reward for this encounter: **+{reward_souls}**")
            if reward_treasure > 0:
                st.markdown(f"- Treasure reward for this encounter: **draw {reward_treasure}**")
            if dropped_souls > 0:
                st.markdown(f"- Dropped souls on this space: **+{dropped_souls}**")
            if reward_events > 0:
                st.markdown(
                    f"- Event reward for this encounter: **{reward_events}** event card(s) "
                    "will be queued for the next encounter space (not bosses)."
                )
            if reward_shortcuts > 0 and active_version == "V2" and current_node is not None:
                st.markdown(
                    "- **Shortcut unlocked:** this encounter space now provides a shortcut "
                    "from the bonfire."
                )

        # Show any still-pending events (after the auto-attach above)
        if active_version == "V2":
            pending_events = int(state.get("pending_events") or 0)
            if pending_events > 0:
                st.markdown(
                    f"- Pending events: **{pending_events}** event card(s) waiting for the next encounter space."
                )

        # Button to commit the last encounter's rewards into the campaign state
        if has_any_rewards and not encounter_is_complete:
            if st.button(
                "Mark encounter as completed (apply rewards to campaign) ✅",
                key="campaign_play_mark_completed",
                width="stretch"
            ):
                # Souls (normal reward + any dropped souls) go straight into the soul cache
                total_souls_gain = max(reward_souls, 0) + max(dropped_souls, 0)
                if total_souls_gain > 0:
                    new_souls = current_souls + total_souls_gain
                    state["souls"] = new_souls

                    # Keep the Campaign Management soul-cache widget in sync so the
                    # value updates on the next render.
                    souls_key = (
                        "campaign_v1_souls_campaign"
                        if active_version == "V1"
                        else "campaign_v2_souls_campaign"
                    )
                    queue_widget_set(souls_key, new_souls)

                # Consume events used in THIS fight (rendezvous on this node + party consumables)
                _consume_fight_attached_events(state, current_node)

                if reward_events > 0 and active_version == "V2":
                    counts = _draw_and_apply_campaign_events(
                        count=reward_events,
                        campaign=campaign,
                        state=state,
                        from_node_id=str(current_node.get("id") or campaign.get("current_node_id") or ""),
                        settings=settings,
                    )

                    # Keep campaign soul widget synced if draw rewards added souls
                    new_souls = int(state.get("souls") or 0)
                    souls_key = "campaign_v2_souls_campaign"
                    queue_widget_set(souls_key, new_souls)

                # Mark this encounter node as completed so movement to the
                # next encounter/boss becomes legal. For V2, also record shortcut unlocks.
                if current_node is not None and current_node.get("kind") == "encounter":
                    current_node["status"] = "complete"
                    if active_version == "V2" and reward_shortcuts > 0:
                        # Persistent shortcut unlocked for this encounter node
                        current_node["shortcut_unlocked"] = True
                state["campaign"] = campaign

                # If this encounter had dropped souls, consume them now
                if (
                    dropped_souls > 0
                    and souls_token_node_id
                    and current_node is not None
                    and current_node.get("id") == souls_token_node_id
                ):
                    state["souls_token_node_id"] = None
                    state["souls_token_amount"] = 0

                st.session_state[state_key] = state

                # Keep the Campaign Management sparks widget in sync so Manage
                # doesn't overwrite state with a stale widget value.
                sparks_key = (
                    "campaign_v1_sparks_campaign"
                    if active_version == "V1"
                    else "campaign_v2_sparks_campaign"
                )
                queue_widget_set(sparks_key, int(state.get("sparks") or 0))

                # Events attached to this encounter do not persist to the next one.
                st.session_state["encounter_events"] = []

                # Clear the last-encounter totals so we don't double-apply next time.
                st.session_state["last_encounter_reward_totals"] = {}
                st.session_state.pop("last_encounter_rewards_for_slug", None)

                st.success("Encounter completed; campaign updated.")
        elif not encounter_is_complete:
            st.caption(
                'Play the encounter above, then click '
                '"Mark encounter as completed" to apply these rewards to the campaign.'
            )

    if not encounter_is_complete:
        # Button to mark the encounter as failed: lose 1 Spark, drop souls on this space, and return to the bonfire
        sparks_cur = int(state.get("sparks") or 0)

        souls_key = (
            "campaign_v1_souls_campaign"
            if active_version == "V1"
            else "campaign_v2_souls_campaign"
        )
        sparks_key = (
            "campaign_v1_sparks_campaign"
            if active_version == "V1"
            else "campaign_v2_sparks_campaign"
        )

        if st.button(
            "Mark encounter as failed (return to bonfire, lose 1 Spark) ❌",
            key="campaign_play_mark_failed",
            width="stretch"
        ):
            # Identify which node just failed (for the souls token in the management tab)
            failed_node_id = None
            if current_node is not None:
                failed_node_id = current_node.get("id") or campaign.get("current_node_id")
            else:
                failed_node_id = campaign.get("current_node_id")

            if active_version == "V2":
                _consume_fight_attached_events(state, current_node)

            # Souls in the cache at the moment of failure
            current_souls = int(state.get("souls") or 0)

            # Record dropped souls for this encounter; overwrite any previous data.
            _record_dropped_souls(state, failed_node_id, current_souls)

            # Reset soul cache to 0 on failure (dropped souls stay on the map instead)
            state["souls"] = 0
            queue_widget_set(souls_key, 0)

            # Decrement Sparks, but never below 0
            if sparks_cur > 0:
                state["sparks"] = sparks_cur - 1
            else:
                state["sparks"] = 0

            # After updating state["sparks"], keep the Campaign tab widget in sync.
            sparks_key = (
                "campaign_v1_sparks_campaign"
                if active_version == "V1"
                else "campaign_v2_sparks_campaign"
            )
            queue_widget_set(sparks_key, int(state.get("sparks") or 0))

            # When the party returns to the bonfire, all encounters that
            # were marked complete become incomplete again. Shortcuts remain.
            _reset_all_encounters_on_bonfire_return(campaign)

            # Move the party back to the bonfire
            campaign["current_node_id"] = "bonfire"
            state["campaign"] = campaign

            # Persist updated campaign state
            st.session_state[state_key] = state

            # Events attached to this encounter do not persist to the next one.
            st.session_state["encounter_events"] = []

            # Clear the last-encounter totals so we don't double-apply next time.
            st.session_state["last_encounter_reward_totals"] = {}
            st.session_state.pop("last_encounter_rewards_for_slug", None)

            if sparks_cur > 0:
                st.warning(
                    "Encounter failed; party returned to the bonfire and lost 1 Spark."
                )
            else:
                st.warning(
                    "Encounter failed; party returned to the bonfire but has no Sparks left."
                )
