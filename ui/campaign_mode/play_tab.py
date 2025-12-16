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
)
from ui.campaign_mode.state import _get_player_count, _get_settings, _ensure_v1_state, _ensure_v2_state
from ui.encounter_mode import play_tab as encounter_play_tab
from ui.event_mode.logic import (
    load_event_configs,
    initialize_event_deck,
    draw_event_card,
    DECK_STATE_KEY,
    compute_draw_rewards_for_card,
    RENDEZVOUS_EVENTS,
    list_event_deck_options,
)


def _auto_apply_pending_events_to_current_encounter(
    campaign: Dict[str, Any],
    state: Dict[str, Any],
    current_node: Dict[str, Any],
) -> None:
    """
    If this is a V2 campaign and there are pending event rewards, automatically
    draw that many events from the event deck and attach them to the current
    encounter.

    Rules:
    - Only applies to V2 campaigns.
    - Only applies on encounter spaces (never bonfire or boss).
    - Does nothing if there are 0 pending events.
    """
    # Use the global rules toggle instead of relying on the campaign payload.
    rules_version = str(st.session_state.get("campaign_rules_version", "V1")).upper()
    if rules_version != "V2":
        return

    pending = int(state.get("pending_events") or 0)
    if pending <= 0:
        return

    # Pending events only apply to encounter spaces, never bonfire or bosses.
    if current_node.get("kind") != "encounter":
        return

    encounter = st.session_state.get("current_encounter") or {}
    if not encounter:
        return

    # Prepare settings and event configs
    settings = _get_settings()
    configs = load_event_configs()

    # Ensure deck state exists (mirror Encounters tab logic)
    deck_state = st.session_state.get(DECK_STATE_KEY)
    if not deck_state:
        deck_state = settings.get("event_deck") or {
            "draw_pile": [],
            "discard_pile": [],
            "current_card": None,
            "preset": None,
        }
        st.session_state[DECK_STATE_KEY] = deck_state

    saved_deck_cfg = settings.get("event_deck") or {}
    preset = deck_state.get("preset") or saved_deck_cfg.get("preset")
    if not preset:
        opts = list_event_deck_options(configs=configs)
        preset = opts[0] if opts else None
    if not preset:
        return

    # (Re)initialize deck if needed
    if deck_state.get("preset") != preset or not deck_state.get("draw_pile"):
        initialize_event_deck(preset, configs=configs)
        deck_state = st.session_state[DECK_STATE_KEY]

    attached = 0
    player_count = _get_player_count(settings)

    # Draw and attach the pending events
    for _ in range(pending):
        card_path = draw_event_card()
        deck_state = st.session_state.get(DECK_STATE_KEY, deck_state)
        settings["event_deck"] = deck_state
        save_settings(settings)

        if not card_path:
            break

        # Attach the event card to this encounter, enforcing rendezvous rules.
        base = Path(str(card_path)).stem
        is_rendezvous = base in RENDEZVOUS_EVENTS

        events = st.session_state.get("encounter_events", [])
        if is_rendezvous:
            events = [ev for ev in events if not ev.get("is_rendezvous")]

        events.append(
            {
                "id": base,
                "name": base,
                "path": str(card_path),
                "is_rendezvous": is_rendezvous,
            }
        )
        st.session_state["encounter_events"] = events
        attached += 1

        # Apply any immediate mechanical draw rewards (e.g., Bonfire Ascetics).
        draw_totals = compute_draw_rewards_for_card(
            card_path, player_count=player_count
        )
        souls_delta = int(draw_totals.get("souls") or 0)
        if souls_delta:
            state["souls"] = int(state.get("souls") or 0) + souls_delta

        # Note: draw-time treasure rewards are computed but not yet wired
        # to the treasure-deck UI; that can be added later if desired.

    if attached:
        state["pending_events"] = max(0, pending - attached)
        st.session_state["campaign_v2_state"] = state


def _sync_current_encounter_from_campaign_for_play(*_args, **_kwargs) -> bool:
    """
    Ensure st.session_state.current_encounter reflects the encounter
    at the party's current campaign node (if any).

    Returns True if we loaded a campaign encounter into current_encounter,
    False if there is no valid encounter at the current node.
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
        try:
            level_int = int(level)
        except Exception:
            level_int = level
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
    selected_chars = settings.get("selected_characters") or []
    try:
        character_count = int(
            len(selected_chars) or st.session_state.get("player_count", 1)
        )
    except Exception:
        character_count = 1

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

    # Decide which campaign is active: prefer V2 if present.
    v2_state = st.session_state.get("campaign_v2_state")
    v1_state = st.session_state.get("campaign_v1_state")

    active_state: Optional[Dict[str, Any]] = None
    active_version: str = "V1"

    if isinstance(v2_state, dict) and isinstance(v2_state.get("campaign"), dict):
        active_state = v2_state
        active_version = "V2"
    elif isinstance(v1_state, dict) and isinstance(v1_state.get("campaign"), dict):
        active_state = v1_state
        active_version = "V1"

    if not active_state:
        st.info("No campaign is currently loaded. Use the Campaign tab to generate or load one.")
        return

    # Normalize state (sparks/souls) for the active version
    player_count = _get_player_count(settings)
    if active_version == "V2":
        state = _ensure_v2_state(player_count)
        state_key = "campaign_v2_state"
    else:
        state = _ensure_v1_state(player_count)
        state_key = "campaign_v1_state"

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
        st.info(f"Current space is {label}. There is no regular encounter to play here.")
        return

    # Ensure Encounter Mode's current_encounter matches this campaign node.
    has_valid_encounter = _sync_current_encounter_from_campaign_for_play()

    # In V2, an encounter space with no choice selected yet is not playable.
    if not has_valid_encounter:
        if active_version == "V2":
            label = _describe_v2_node_label(campaign, current_node)
            st.info(
                f"Current space is {label}. "
                "Choose an encounter for this space on the Campaign tab before playing it."
            )
        else:
            # Defensive fallback for V1; should basically never trigger.
            st.info("No encounter is configured for this campaign space.")
        return

    # Auto-attach any pending events to THIS encounter (V2 only, encounter spaces only).
    _auto_apply_pending_events_to_current_encounter(campaign, state, current_node)

    encounter = st.session_state.get("current_encounter")
    if not encounter:
        st.info("No encounter is available on this space.")
        return

    # Finally, render the normal Encounter Mode Play tab for the current encounter.
    # using the shared user settings just like Encounter Mode does.
    encounter_play_tab.render(settings)

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

    try:
        reward_souls = int(reward_totals.get("souls") or 0)
    except Exception:
        reward_souls = 0

    # Shortcut rewards can come from the encounter or attached events
    try:
        reward_shortcuts = int(reward_totals.get("shortcut") or 0)
    except Exception:
        reward_shortcuts = 0

    current_souls = int(state.get("souls", 0))

    # Dropped souls associated with this encounter (from a previous failure)
    dropped_souls = 0
    souls_token_node_id = state.get("souls_token_node_id")
    if (
        souls_token_node_id
        and current_node is not None
        and current_node.get("id") == souls_token_node_id
    ):
        try:
            dropped_souls = int(state.get("souls_token_amount") or 0)
        except Exception:
            dropped_souls = 0

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
            st.caption("No soul, shortcut, or event rewards are configured for this encounter.")
        else:
            if reward_souls > 0:
                st.markdown(f"- Souls reward for this encounter: **+{reward_souls}**")
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
                "Mark encounter as completed (apply rewards to campaign)",
                key="campaign_play_mark_completed",
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
                    st.session_state[souls_key] = new_souls

                # Events are *queued* to be auto-applied on the next encounter space
                if reward_events > 0 and active_version == "V2":
                    pending_events = int(state.get("pending_events") or 0)
                    state["pending_events"] = pending_events + reward_events

                # For V2, mark this encounter node as completed so movement to the
                # next encounter/boss becomes legal, and record shortcut unlocks
                if active_version == "V2" and current_node is not None:
                    if current_node.get("kind") == "encounter":
                        current_node["status"] = "complete"
                        if reward_shortcuts > 0:
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

                # Events attached to this encounter do not persist to the next one.
                st.session_state["encounter_events"] = []

                # Clear the last-encounter totals so we don't double-apply next time.
                st.session_state["last_encounter_reward_totals"] = {}
                st.session_state.pop("last_encounter_rewards_for_slug", None)

                st.success("Encounter completed; campaign state updated.")
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
            "Mark encounter as failed (return to bonfire, lose 1 Spark)",
            key="campaign_play_mark_failed",
        ):
            # Identify which node just failed (for the souls token in the management tab)
            failed_node_id = None
            if current_node is not None:
                failed_node_id = current_node.get("id") or campaign.get("current_node_id")
            else:
                failed_node_id = campaign.get("current_node_id")

            # Souls in the cache at the moment of failure
            current_souls = int(state.get("souls") or 0)

            # Record dropped souls for this encounter; overwrite any previous data.
            _record_dropped_souls(state, failed_node_id, current_souls)

            # Reset soul cache to 0 on failure (dropped souls stay on the map instead)
            state["souls"] = 0
            st.session_state[souls_key] = 0

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
            st.session_state[sparks_key] = int(state.get("sparks") or 0)

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
