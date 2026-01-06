#ui/encounter_mode/play_panels.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from copy import deepcopy
import streamlit as st

from core.encounter import templates, objectives as obj_mod
from core.encounter_rewards import get_v1_reward_config_for_encounter
from core.encounter_rules import (
    make_encounter_key,
    get_rules_for_encounter,
    get_upcoming_rules_for_encounter,
    get_rules_for_event,
    get_upcoming_rules_for_event,
)
from core.encounter_triggers import (
    EncounterTrigger,
    get_triggers_for_encounter,
    get_triggers_for_event,
)

from core.encounter import timer as timer_mod

from core.behavior import render as behavior_decks_render
from core.behavior.assets import BEHAVIOR_CARDS_PATH
from core.behavior.generation import render_data_card_cached, build_behavior_catalog
from core.behavior.logic import load_behavior
from core.behavior.models import BehaviorEntry
from ui.encounter_mode import invader_panel
from ui.encounter_mode.assets import (
    enemyNames,
    encounterKeywords,
    editedEncounterKeywords,
    keywordText
)
from ui.encounter_mode.logic import ENCOUNTER_BEHAVIOR_MODIFIERS
from ui.encounter_mode.play_state import get_player_count, log_entry
from ui.event_mode.logic import EVENT_BEHAVIOR_MODIFIERS, V2_EXPANSIONS, EVENT_REWARDS
from core.image_cache import get_image_data_uri_cached, bytes_to_data_uri


# ---------------------------------------------------------------------
# Constants / small data tables
# ---------------------------------------------------------------------

TIMER_ICON_PATH = Path("assets") / "timer.png"
V2_EXPANSIONS_SET = set(V2_EXPANSIONS)

# Optional caps for phrases like "on 4 tiles" in objective text.
# Values are the maximum number of tiles that physically exist in the encounter.
OBJECTIVE_TILE_CAPS = {
    # Example: whatever encounter this objective belongs to
    # "Some Encounter Name|Painted World of Ariamis": 3,
    "Central Plaza|Painted World of Ariamis": 3,
}


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------

def _is_v2_encounter(encounter: dict) -> bool:
    """
    Decide whether an encounter should be treated as a V2 card.

    Priority:
    - explicit 'version' / 'encounter_version' field on the encounter
    - otherwise, expansion membership in V2_EXPANSIONS
    """
    version = (
        encounter.get("version")
        or encounter.get("encounter_version")
        or ""
    ).upper()

    if version.startswith("V1"):
        return False
    if version.startswith("V2"):
        return True

    expansion = encounter.get("expansion")
    return expansion in V2_EXPANSIONS_SET


def _is_v1_encounter(encounter: dict) -> bool:
    """
    Everything that isn't explicitly V2 is treated as V1-style:
    - basic objective
    - basic rewards
    - no rules / triggers / events
    """
    return not _is_v2_encounter(encounter)


def _keyword_label(keyword: str) -> str:
    txt = keywordText.get(keyword)
    if isinstance(txt, str) and txt.strip():
        return txt.split("—", 1)[0].strip()

    import re as _re
    s = _re.sub(r"(?<!^)(?=[A-Z])", " ", str(keyword)).replace("_", " ").strip()
    return s.title() if s else str(keyword)


def _get_encounter_keywords(encounter: dict, settings: dict) -> list[str]:
    if _is_v1_encounter(encounter):
        return []

    name = encounter.get("encounter_name") or encounter.get("name") or ""
    expansion = encounter.get("expansion") or ""
    if not name or not expansion:
        return []

    encounter_key = make_encounter_key(name=name, expansion=expansion)
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    src = editedEncounterKeywords if edited else encounterKeywords
    raw = src.get((name, expansion)) or []

    out: list[str] = []
    seen: set[str] = set()
    for k in raw:
        if not k:
            continue
        k = str(k)
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _render_keywords_summary(encounter: dict, settings: dict) -> None:
    keys = _get_encounter_keywords(encounter, settings)
    if not keys:
        return

    labels = ", ".join(_keyword_label(k) for k in keys)
    st.caption(f"Keywords: {labels}")


def _render_rule_block(rendered_text: str, *, prefix: str = "", key_hint: Optional[str] = None) -> None:
    if ":" not in rendered_text:
        if prefix:
            st.markdown(f"- {prefix}{rendered_text}", unsafe_allow_html=True)
        else:
            st.markdown(f"- {rendered_text}", unsafe_allow_html=True)


def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. Adjust to match how your Setup tab stores the toggle.
    """
    # 1) Encounter dict itself
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    # 2) Session state override (if you set one from Setup)
    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    # 3) Settings-level toggle keyed by encounter key
    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def _get_enemy_display_names(encounter: dict) -> list[str]:
    """
    Return human-readable names for the shuffled enemies in this encounter.

    Assumes Setup stored the shuffled list on encounter["enemies"].
    Replace the internals with your real enemy metadata lookup instead of str().
    """
    enemy_ids = encounter.get("enemies") or []

    names: list[str] = []
    for eid in enemy_ids:
        if isinstance(eid, dict):
            names.append(eid.get("name") or eid.get("id") or str(eid))
        else:
            # Index into the global enemyNames mapping from assets
            names.append(enemyNames[eid])

    return names


def _detect_gang_name(encounter: dict) -> Optional[str]:
    """Detect majority gang among shuffled enemies.

    Gang membership rules:
    - enemy printed name contains gang name (case-insensitive)
    - enemy base health is 1 (from behavior JSON or embedded dict)

    Returns one of: 'Hollow', 'Alonne', 'Skeleton', 'Silver Knight', or None.
    """
    gang_keys = ["Hollow", "Alonne", "Skeleton", "Silver Knight"]
    counts: Dict[str, int] = {k: 0 for k in gang_keys}

    # Honor explicit override (e.g., Original button in Setup)
    force = encounter.get("force_gang")
    if isinstance(force, str) and force in gang_keys:
        return force

    enemy_ids = encounter.get("enemies") or []
    for eid in enemy_ids:
        name = None
        health = None

        if isinstance(eid, dict):
            name = eid.get("name") or eid.get("id")
            if "health" in eid:
                try:
                    health = int(eid.get("health"))
                except Exception:
                    health = None
        else:
            if isinstance(eid, int):
                name = enemyNames.get(eid)
            else:
                name = str(eid)

            if name:
                try:
                    # load base behavior JSON to read default health
                    cfg = load_behavior(Path("data/behaviors") / f"{name}.json")
                    health = int(cfg.raw.get("health", 1))
                except Exception:
                    health = None

        if not name:
            continue

        lname = name.lower()
        for g in gang_keys:
            if g.lower() in lname and health == 1:
                counts[g] += 1
                break

    best = None
    best_count = 0
    for k, v in counts.items():
        if v > best_count:
            best = k
            best_count = v

    return best if best_count > 0 else None


def _render_gang_rule(encounter: dict, settings: dict) -> bool:
    """Render the Gang rule for this encounter if appropriate.

    Returns True if the rule was rendered, False otherwise.
    """
    encounter_keywords = _get_encounter_keywords(encounter, settings)
    if "gang" not in encounter_keywords:
        return False

    gang_name = _detect_gang_name(encounter)
    if gang_name:
        text = (
            f"{gang_name} Gang — If a character is attacked by a {gang_name} "
            f"enemy and another {gang_name} enemy is within one node of the character, "
            "increase the attacking model’s damage and dodge difficulty values "
            "by 1 when resolving the attack."
        )
    else:
        text = (
            "Gang — If a character is attacked by a gang enemy and another "
            "gang enemy is within one node of the character, increase the "
            "attacking model’s damage and dodge difficulty values by 1 when "
            "resolving the attack."
        )

    st.markdown(f"- {text}", unsafe_allow_html=True)
    return True


# ---------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------


def _render_objectives(encounter: dict, settings: dict) -> None:
    """
    Render the Objective / Trial sections for the encounter, using the
    ENCOUNTER_OBJECTIVES data and the text templating helpers.
    """
    # Build encounter key and figure out edited vs default variant
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    # --- V1: fixed objective text ------------------------------------
    if _is_v1_encounter(encounter):
        st.markdown("#### Objective")
        st.markdown("- Kill all enemies.")
        return
    # -----------------------------------------------------------------

    edited = _detect_edited_flag(encounter_key, encounter, settings)
    cfg = obj_mod.get_objective_config_for_key(encounter_key, edited=edited)
    if not cfg:
        return

    enemy_names = _get_enemy_display_names(encounter)
    player_count = get_player_count()

    # Figure out if there is a tile cap for this encounter
    tile_cap = OBJECTIVE_TILE_CAPS.get(encounter_key)

    primary = cfg.get("objectives") or []
    trials = cfg.get("trials") or []

    if len(primary) + len(trials) == 0:
        return

    st.markdown("#### Objective")

    # Main objectives
    for template in primary:
        text = templates.render_text_template(
            template,
            enemy_names,
            player_count=player_count,
        )
        if tile_cap is not None:
            text = templates.cap_tiles_in_text(text, tile_cap)
        st.markdown(f"- {text}", unsafe_allow_html=True)

    # Optional trial text
    if trials:
        st.markdown("#### Trial")
        for template in trials:
            text = templates.render_text_template(
                template,
                enemy_names,
                player_count=player_count,
            )
            if tile_cap is not None:
                text = templates.cap_tiles_in_text(text, tile_cap)
            st.markdown(f"- {text}", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Rewards
# ---------------------------------------------------------------------


def _render_rewards(encounter: dict, settings: dict, play_state: dict) -> None:
    """
    Render a Rewards section for the encounter, combining:
    - Encounter-level rewards from ENCOUNTER_REWARDS
    - Trial rewards gated by their checkbox triggers
    - Event-level rewards from EVENT_REWARDS for any attached events
    """
    st.markdown("#### Rewards")

    # Build encounter key and edited flag (mirrors _render_objectives)
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)
    player_count = get_player_count()
    enemy_names = _get_enemy_display_names(encounter)
    is_v1 = _is_v1_encounter(encounter)

    # Trigger state (used for trials, counters, and modifiers)
    triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )
    trigger_state = _ensure_trigger_state(encounter_key, triggers)

    # Aggregate totals across encounter + events
    totals = {
        "souls": 0,
        "treasure": 0,
        "event": 0,
        "refresh_heroic": 0,
        "refresh_luck": 0,
        "refresh_estus": 0,
        "search": 0,
        "shortcut": 0,
    }
    special_lines: list[str] = []
    souls_multipliers: list[int] = []

    # ---- Encounter-level rewards ----
    from core.encounter_rewards import get_reward_config_for_key  # local import to avoid cycles

    if is_v1:
        enc_cfg = get_v1_reward_config_for_encounter(encounter)
    else:
        enc_cfg = get_reward_config_for_key(encounter_key, edited=edited)

    if enc_cfg:
        _apply_rewards_from_config(
            enc_cfg,
            source_label="Encounter",
            totals=totals,
            special_lines=special_lines,
            souls_multipliers=souls_multipliers,
            trigger_state=trigger_state,
            player_count=player_count,
            enemy_names=enemy_names,
            timer=play_state["timer"],
        )

    # ---- Event-level rewards ----
    # V1 encounter cards cannot have attached events mechanically in Encounter Mode.
    if not is_v1:
        events = st.session_state.get("encounter_events", [])

        for ev in events:
            ev_name = ev.get("name") or ev.get("title") or ev.get("id")
            if not ev_name:
                continue
            ev_rewards = EVENT_REWARDS.get(ev_name)  # type: ignore[index]
            if not ev_rewards:
                continue

            # Wrap in a minimal config so we can reuse the same helper
            ev_cfg = {"rewards": ev_rewards}
            _apply_rewards_from_config(
                ev_cfg,  # type: ignore[arg-type]
                source_label=f"Event: {ev_name}",
                totals=totals,
                special_lines=special_lines,
                souls_multipliers=souls_multipliers,
                trigger_state=trigger_state,
                player_count=player_count,
                enemy_names=enemy_names,
                timer=play_state["timer"],
            )

    # ---- Apply souls multipliers after everything else ----
    if totals["souls"] and souls_multipliers:
        mult = 1
        for m in souls_multipliers:
            if m and m != 1:
                mult *= m
        if mult != 1:
            totals["souls"] *= mult

    # Make the final totals available to other tabs (e.g. Campaign Play)
    st.session_state["last_encounter_reward_totals"] = totals.copy()

    # Remember which encounter produced these totals so Campaign Mode can
    # ignore stale rewards from other encounters.
    last_enc = st.session_state.get("last_encounter") or {}
    slug = last_enc.get("slug") or encounter.get("slug")
    if slug:
        st.session_state["last_encounter_rewards_for_slug"] = slug

    # If nothing to show, bail out
    if not any(totals.values()) and not special_lines:
        st.caption("No reward data configured for this encounter.")
        return

    # ---- Summary layout ----
    if totals["souls"]:
        st.markdown(f"- {totals['souls']} souls")
    if totals["treasure"]:
        st.markdown(f"- Draw {totals['treasure']} treasures")
    if totals["event"]:
        st.markdown(f"- Draw {totals['event']+1} events")
    if totals["refresh_heroic"]:
        st.markdown(f"- Refresh Heroic Action")
    if totals["refresh_luck"]:
        st.markdown(f"- Refresh Luck")
    if totals["refresh_estus"]:
        st.markdown(f"- Refresh Estus Flask")
    if totals["search"]:
        st.markdown(f"- Search reward (check the encounter card)")
    if totals["shortcut"]:
        st.markdown(f"- Shortcut")


def _apply_rewards_from_config(
    cfg,
    *,
    source_label: str,
    totals: dict,
    special_lines: list[str],
    souls_multipliers: list[int],
    trigger_state: dict,
    player_count: int,
    enemy_names: list[str],
    timer: int,
) -> None:
    """
    Apply rewards from a single EncounterRewardsConfig-like dict into the
    running totals and details.

    Understands:
    - rewards + trial_rewards
    - numeric fields: flat, per_player, per_counter, per_player_per_counter
    - refresh_resource for refresh rewards
    - modifiers.souls_multiplier (if present)
    """
    rewards = list(cfg.get("rewards", []))

    # Gate trial rewards behind their checkbox triggers
    for r in cfg.get("trial_rewards", []):
        trial_id = r.get("trial_trigger_id")
        if trial_id and not trigger_state.get(trial_id):
            continue
        rewards.append(r)

    # Base rewards
    for r in rewards:
        rtype = r.get("type")
        if not rtype:
            continue

        # Determine counter_val. Priority:
        # 1) If reward defines `timer_thresholds`, compute respawns
        #    cumulatively from the provided `timer` value.
        # 2) Otherwise, fall back to explicit counter_trigger_id in trigger_state.
        counter_val = 0
        if r.get("timer_thresholds") is not None:
            thresholds = r["timer_thresholds"]
            counter_val = sum(1 for t in thresholds if timer >= int(t))
        else:
            counter_id = r.get("counter_trigger_id")
            if counter_id:
                counter_val = int(trigger_state.get(counter_id, 0) or 0)

        flat = int(r.get("flat", 0) or 0)
        per_player = int(r.get("per_player", 0) or 0)
        per_counter = int(r.get("per_counter", 0) or 0)
        per_ppc = int(r.get("per_player_per_counter", 0) or 0)

        amount = flat
        amount += per_player * player_count
        amount += per_counter * counter_val
        amount += per_ppc * player_count * counter_val

        # Numeric types update totals
        if rtype == "souls":
            totals["souls"] += amount
        elif rtype == "treasure":
            totals["treasure"] += amount
        elif rtype == "event":
            totals["event"] += amount
        elif rtype == "refresh":
            resource = r.get("refresh_resource") or ""
            if resource == "heroic":
                totals["refresh_heroic"] += amount
            elif resource == "luck":
                totals["refresh_luck"] += amount
            elif resource == "estus":
                totals["refresh_estus"] += amount
        elif rtype == "search":
            totals["search"] += 1
        elif rtype == "shortcut":
            totals["shortcut"] += 1

        # Human-readable detail line if text is provided or needed
        text_template = r.get("text")
        if text_template:
            text = templates.render_text_template(
                text_template,
                enemy_names,
                value=counter_val,
                player_count=player_count,
            )
            special_lines.append(f"{source_label}: {text}")
        elif rtype in ("search", "shortcut", "text"):
            # Fallback generic labels if no explicit text
            if rtype == "search":
                special_lines.append(
                    f"{source_label}: Resolve a search effect (see card)."
                )
            elif rtype == "shortcut":
                special_lines.append(
                    f"{source_label}: Unlock a shortcut (see encounter card)."
                )
            elif rtype == "text":
                # Bare text with no template – nothing to render
                pass

    # Optional modifiers (currently only souls_multiplier)
    for mod in cfg.get("modifiers", []):
        if mod.get("type") != "souls_multiplier":
            continue
        trig_id = mod.get("trigger_id")
        if trig_id and not trigger_state.get(trig_id):
            continue
        mult = int(mod.get("multiplier", 1) or 1)
        if mult <= 1:
            continue
        souls_multipliers.append(mult)

        mod_text = mod.get("text")
        if mod_text:
            text = templates.render_text_template(
                mod_text,
                enemy_names,
                player_count=player_count,
            )
            special_lines.append(f"{source_label}: {text}")


# ---------------------------------------------------------------------
# Rules + upcoming rules
# ---------------------------------------------------------------------


def _render_rules(encounter: dict, settings: dict, play_state: dict) -> None:
    # V1 encounter cards have no special rules/triggers section in Encounter Mode.
    if _is_v1_encounter(encounter):
        return
    
    st.markdown("#### Rules")

    # Build encounter key (name + expansion or however your data is structured)
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)

    enemy_names = _get_enemy_display_names(encounter)
    player_count = get_player_count()
    timer = play_state["timer"]
    phase = play_state["phase"]  # "enemy" or "player"

    # ------------------------------------------------------------------
    # Encounter-level rules that apply *right now*
    # ------------------------------------------------------------------
    current_encounter_rules = get_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        timer=timer,
        phase=phase,
    )
    # Precompute gang rule and render it early so it appears even when no other rules exist.
    gang_shown = _render_gang_rule(encounter, settings)

    # ------------------------------------------------------------------
    # Event-level rules that apply *right now*
    # ------------------------------------------------------------------
    events = st.session_state.get("encounter_events", []) or []
    event_rule_groups: list[tuple[str, list]] = []

    for ev in events:
        ev_id = ev.get("id")
        ev_name = ev.get("name")
        label = ev_name or ev_id or ""

        rules_for_event: list = []

        # Allow either id or name as key into EVENT_RULES
        for key in (ev_id, ev_name):
            if not key:
                continue

            rules_for_event = get_rules_for_event(
                event_key=key,
                timer=timer,
                phase=phase,
            )
            if rules_for_event:
                break

        if rules_for_event:
            event_rule_groups.append((label, rules_for_event))

    # (gang info already computed above)

    # ------------------------------------------------------------------
    # Render current rules
    # ------------------------------------------------------------------
    # Collect rules that look like "Keyword: description" (contain ':')
    keyword_rules: list[tuple[str, str]] = []  # (label_or_none, rendered_text)

    # Encounter-level keyword rules
    remaining_enc_rules = []
    for rule in current_encounter_rules:
        if ":" in (rule.template or ""):
            text = templates.render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            keyword_rules.append((None, text))
        else:
            remaining_enc_rules.append(rule)

    # Event-level keyword rules
    remaining_event_groups = []
    for label, rules_for_event in event_rule_groups:
        remaining = []
        for rule in rules_for_event:
            if ":" in (rule.template or ""):
                text = templates.render_text_template(
                    rule.template,
                    enemy_names,
                    player_count=player_count,
                )
                keyword_rules.append((label, text))
            else:
                remaining.append(rule)
        if remaining:
            remaining_event_groups.append((label, remaining))

    # If no rules at all, show caption
    if not remaining_enc_rules and not remaining_event_groups and not keyword_rules and not gang_shown:
        st.caption("No relevant rules right now.")
    else:
        # Encounter-level rules first
        # Inject computed gang rule first if present (skip if already shown)
        if not gang_shown:
            _render_gang_rule(encounter, settings)

        # Keywords subsection (top of Rules) — always visible expanders
        if keyword_rules:
            st.markdown("**Keywords**")
            for label, text in keyword_rules:
                head, _sep, tail = text.partition(":")
                title = head.strip()
                body = tail.strip()
                with st.expander(title, expanded=False):
                    if label:
                        st.markdown(f"- [{label}] {body}", unsafe_allow_html=True)
                    else:
                        st.markdown(f"- {body}", unsafe_allow_html=True)

        # Then render any non-keyword encounter rules
        for i, rule in enumerate(remaining_enc_rules):
            text = templates.render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            _render_rule_block(text, key_hint=f"enc_now_{i}")

        # Then per-event rules, grouped under headings
        for label, rules_for_event in remaining_event_groups:
            for i, rule in enumerate(rules_for_event):
                text = templates.render_text_template(
                    rule.template,
                    enemy_names,
                    player_count=player_count,
                )
                _render_rule_block(text, key_hint=f"ev_now_{label}_{i}")

    # ------------------------------------------------------------------
    # Upcoming rules: encounter + events
    # ------------------------------------------------------------------
    upcoming_combined: list[tuple[int, str | None, Any]] = []

    # Encounter-level upcoming rules
    enc_upcoming = get_upcoming_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        current_timer=timer,
        max_lookahead=3,  # show next 3 Timer step(s); tweak if you like
    )
    for trigger_timer, rule in enc_upcoming:
        upcoming_combined.append((trigger_timer, None, rule))

    # Event-level upcoming rules
    for ev in events:
        ev_id = ev.get("id")
        ev_name = ev.get("name")
        label = ev_name or ev_id or ""

        for key in (ev_id, ev_name):
            if not key:
                continue

            ev_upcoming = get_upcoming_rules_for_event(
                event_key=key,
                current_timer=timer,
                max_lookahead=3,
            )
            if not ev_upcoming:
                continue

            for trigger_timer, rule in ev_upcoming:
                upcoming_combined.append((trigger_timer, label, rule))

            # Avoid double-fetching for id+name if both map to same rules
            break

    if upcoming_combined:
        # Sort by when they will trigger
        upcoming_combined.sort(key=lambda t: t[0])

        st.markdown("**Upcoming rules**")

        for idx, (trigger_timer, source_label, rule) in enumerate(upcoming_combined):
            phase_label = {
                "enemy": "Enemy Phase",
                "player": "Player Phase",
            }.get(rule.phase, "")

            text = templates.render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )

            # Prefix with event label if this comes from an event
            ev_prefix = f"[{source_label}] " if source_label else ""

            timer_prefix = f"**Timer {trigger_timer}{' · ' + phase_label if phase_label else ''}** — {ev_prefix}"
            _render_rule_block(text, prefix=timer_prefix, key_hint=f"upcoming_{idx}")


def _render_current_rules(encounter: dict, settings: dict, play_state: dict, *, show_header: bool = True) -> None:
    """Render only the rules that apply *right now* (no upcoming section)."""
    if _is_v1_encounter(encounter):
        return

    if show_header:
        st.markdown("#### Rules")

    name = encounter.get("encounter_name") or encounter.get("name") or "Unknown Encounter"
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    enemy_names = _get_enemy_display_names(encounter)
    player_count = get_player_count()
    timer = play_state["timer"]
    phase = play_state["phase"]

    current_encounter_rules = get_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        timer=timer,
        phase=phase,
    )

    # Compute gang info early so Gang can be shown even when no other rules exist
    encounter_keywords = _get_encounter_keywords(encounter, settings)
    gang_name_preview = None
    if "gang" in encounter_keywords:
        gang_name_preview = _detect_gang_name(encounter)

    events = st.session_state.get("encounter_events", []) or []
    event_rule_groups: list[tuple[str, list]] = []

    for ev in events:
        ev_id = ev.get("id")
        ev_name = ev.get("name")
        label = ev_name or ev_id or ""

        rules_for_event: list = []
        for key in (ev_id, ev_name):
            if not key:
                continue
            rules_for_event = get_rules_for_event(event_key=key, timer=timer, phase=phase)
            if rules_for_event:
                break

        if rules_for_event:
            event_rule_groups.append((label, rules_for_event))

    if not current_encounter_rules and not event_rule_groups and not ("gang" in encounter_keywords):
        st.caption("No rules to show for this encounter in the current state.")
        return

    # Inject computed gang rule first if present
    _render_gang_rule(encounter, settings)

    for i, rule in enumerate(current_encounter_rules):
        text = templates.render_text_template(rule.template, enemy_names, player_count=player_count)
        _render_rule_block(text, key_hint=f"cur_only_{i}")

    for label, rules_for_event in event_rule_groups:
        for i, rule in enumerate(rules_for_event):
            text = templates.render_text_template(rule.template, enemy_names, player_count=player_count)
            _render_rule_block(text, key_hint=f"cur_ev_{label}_{i}")


# ---------------------------------------------------------------------
# Timer + phase header
# ---------------------------------------------------------------------


def _render_timer_and_phase(play_state: dict) -> None:
    # One row: [Timer icon count] | [Enemy Phase / Player Phase]
    c1, c2 = st.columns([1.4, 1])

    # Left side: Timer [icon] [counter]
    with c1:
        try:
            data_uri = get_image_data_uri_cached(str(TIMER_ICON_PATH))
            img_tag = (
                f"<img src='{data_uri}' "
                f"style='height:18px; width:auto; margin:0 0.25rem;'/>"
            )
        except Exception:
            img_tag = "<span style='margin:0 0.25rem;'>⏱️</span>"

        html = f"""
        <div style="display:flex; align-items:center; gap:0.35rem;">
            <span style="font-weight:600;">Timer</span>
            {img_tag}
            <span style="font-size:1.2rem; font-weight:600;">{play_state['timer']}</span>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

    # Right side: phase label
    with c2:
        phase_label = (
            "Enemy Phase" if play_state["phase"] == "enemy" else "Player Phase"
        )
        st.markdown(
            f"<div style='text-align:right; font-size:1.1rem; font-weight:600;'>{phase_label}</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------
# Turn controls (Next / Previous / Reset + special timer buttons)
# ---------------------------------------------------------------------


def _render_turn_controls(
    play_state: dict,
    stop_on_timer_objective: bool = False,
    timer_behavior: Optional[dict] = None,
    *,
    compact: bool = False,
) -> None:
    if timer_behavior is None:
        timer_behavior = {}

    st.markdown("#### Turn Controls")

    def _action_button(label: str, *, key: str, action: str, disabled: bool = False) -> None:
        if st.button(label, key=key, disabled=disabled, width="stretch"):
            st.session_state["encounter_play_pending_action"] = action
            st.rerun()

    if compact:
        _action_button("Previous Turn", key="encounter_play_prev_turn", action="prev")
        _action_button("Next Turn", key="encounter_play_next_turn", action="next", disabled=stop_on_timer_objective)
        _action_button("Reset", key="encounter_play_reset", action="reset")
    else:
        b1, b2, b3 = st.columns(3)
        with b1:
            _action_button("Previous Turn", key="encounter_play_prev_turn", action="prev")
        with b2:
            _action_button("Next Turn", key="encounter_play_next_turn", action="next", disabled=stop_on_timer_objective)
        with b3:
            _action_button("Reset", key="encounter_play_reset", action="reset")

    if stop_on_timer_objective:
        st.caption("Time has run out; Next Turn is disabled for this encounter.")

    has_manual_inc = bool(timer_behavior.get("manual_increment"))
    # Optionally hide the generic manual-increment button when the encounter
    # manages Timer advancement via triggers (e.g. lever pulls).
    show_manual_button = has_manual_inc and not bool(timer_behavior.get("hide_manual_increment_button", False))
    has_reset_btn = bool(timer_behavior.get("reset_button"))
    if not (has_manual_inc or has_reset_btn):
        return

    st.markdown("##### Special Timer Actions")

    # Define labels/help text/log text with safe defaults so they exist
    # even if the button is hidden. Actual rendering uses `show_manual_button`.
    label = timer_behavior.get("manual_increment_label", "Increase Timer") if has_manual_inc else None
    help_text = timer_behavior.get("manual_increment_help") if has_manual_inc else None
    log_text = timer_behavior.get("manual_increment_log", "Timer manually increased.") if has_manual_inc else None

    label2 = timer_behavior.get("reset_button_label", "Reset Timer (special rule)") if has_reset_btn else None
    help_text2 = timer_behavior.get("reset_button_help") if has_reset_btn else None
    log_text2 = timer_behavior.get("reset_button_log", "Timer reset due to special rule.") if has_reset_btn else None

    if compact:
        if show_manual_button:
            if st.button(label, key="encounter_play_manual_timer_increase", width="stretch"):
                play_state["timer"] += 1
                log_entry(play_state, log_text)
                st.rerun()
            if help_text:
                st.caption(help_text)

        if has_reset_btn:
            if st.button(label2, key="encounter_play_special_timer_reset", width="stretch"):
                old_timer = play_state["timer"]
                play_state["timer"] = 0
                log_entry(play_state, f"{log_text2} (was {old_timer}, now 0)")
                st.rerun()
            if help_text2:
                st.caption(help_text2)
        return

    cols = st.columns((1 if has_manual_inc else 0) + (1 if has_reset_btn else 0))
    col_idx = 0
    if show_manual_button:
        with cols[col_idx]:
            if st.button(label, key="encounter_play_manual_timer_increase", width="stretch"):
                play_state["timer"] += 1
                log_entry(play_state, log_text)
                st.rerun()
        col_idx += 1
        if help_text:
            st.caption(help_text)

    if has_reset_btn:
        with cols[col_idx]:
            if st.button(label2, key="encounter_play_special_timer_reset", width="stretch"):
                old_timer = play_state["timer"]
                play_state["timer"] = 0
                log_entry(play_state, f"{log_text2} (was {old_timer}, now 0)")
                st.rerun()
        if help_text2:
            st.caption(help_text2)


# ---------------------------------------------------------------------
# Encounter triggers
# ---------------------------------------------------------------------


def _ensure_trigger_state(
    scope_key: str,
    triggers: list[EncounterTrigger],
) -> dict:
    """
    Ensure we have a state dict for this trigger group (encounter or event)
    in session_state.
    """
    all_state = st.session_state.setdefault("encounter_triggers", {})
    scope_state = all_state.setdefault(scope_key, {})

    for trig in triggers:
        if trig.id not in scope_state:
            if trig.kind in ("counter", "numeric"):
                scope_state[trig.id] = int(trig.default_value or 0)
            elif trig.kind == "checkbox":
                scope_state[trig.id] = bool(trig.default_value or False)
            elif trig.kind == "timer_objective":
                scope_state[trig.id] = False

    return scope_state


def _render_encounter_triggers(
    encounter: dict,
    play_state: dict,
    settings: dict,
) -> None:
    # No triggers for V1 encounter cards.
    if _is_v1_encounter(encounter):
        return
    
    st.markdown("#### Encounter Triggers")

    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)
    timer_behavior = timer_mod.get_timer_behavior(encounter, edited=edited)

    # --- Gather all trigger sources: encounter + attached events ---
    encounter_triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )

    # Render any recent trigger messages (persisted across reruns).
    recent_msgs = st.session_state.get("encounter_last_trigger_messages", []) or []
    if recent_msgs:
        with st.container():
            for m in recent_msgs[-6:]:
                st.info(m)

    enemy_names = _get_enemy_display_names(encounter)

    sources: list[dict] = []

    # 1) Encounter-level triggers (same as before)
    if encounter_triggers:
        sources.append(
            {
                "kind": "encounter",
                "scope_key": encounter_key,
                "label": None,
                "triggers": encounter_triggers,
            }
        )

    # 2) Event-level triggers
    events = st.session_state.get("encounter_events", []) or []
    for ev in events:
        ev_id = ev.get("id")
        ev_name = ev.get("name") or ev_id or ""

        ev_triggers: list[EncounterTrigger] = []
        scope_key: str | None = None

        # Allow either id or name as key into EVENT_TRIGGERS
        for key in (ev_id, ev_name):
            if not key:
                continue
            trig_list = get_triggers_for_event(event_key=key)
            if trig_list:
                ev_triggers = trig_list
                scope_key = f"event:{key}"
                break

        if ev_triggers and scope_key:
            sources.append(
                {
                    "kind": "event",
                    "scope_key": scope_key,
                    "label": ev_name,
                    "triggers": ev_triggers,
                }
            )

    if not sources:
        st.caption("No special triggers defined for this encounter yet.")
        return

    # --- Render all sources ---
    for src in sources:
        scope_key = src["scope_key"]
        triggers = src["triggers"]

        # Ensure state bucket for this group (encounter or event)
        state = _ensure_trigger_state(scope_key, triggers)

        # Make widget keys stable & unique per group
        widget_scope = scope_key.replace("|", "_")

        for trig in triggers:
            # Phase-gating: only show if it applies in the current phase
            if trig.phase not in ("any", play_state["phase"]):
                continue

            # ----- CHECKBOX -----
            if trig.kind == "checkbox":
                prev = bool(state.get(trig.id, trig.default_value or False))

                suffix = ""
                if trig.template:
                    suffix = templates.render_text_template(
                        trig.template,
                        enemy_names,
                    )

                if trig.label and suffix:
                    label_text = f"{trig.label}: {suffix}"
                else:
                    label_text = trig.label or suffix or trig.id

                new_val = st.checkbox(
                    label_text,
                    value=prev,
                    key=f"trigger_cb_{widget_scope}_{trig.id}",
                )

                # One-shot effect when it flips False -> True
                if new_val and not prev and trig.effect_template:
                    effect_text = templates.render_text_template(
                        trig.effect_template,
                        enemy_names,
                    )
                    # Persist the effect in the turn log so it survives a rerun.
                    log_entry(play_state, effect_text)
                    # Also persist for immediate display across reruns.
                    st.session_state.setdefault("encounter_last_trigger_messages", []).append(effect_text)
                    st.info(effect_text)

                state[trig.id] = new_val
                # If this trigger is configured to advance the Timer, do so now.
                inc_on = timer_behavior.get("increment_on_trigger")
                if inc_on and new_val and not prev and inc_on == trig.id:
                    play_state["timer"] += 1
                    # Use configured log text if available
                    log_text = timer_behavior.get("manual_increment_log", "Timer increased.")
                    log_entry(play_state, log_text)
                    # Re-run so the UI reflects the timer change immediately
                    st.rerun()

            # ----- COUNTER -----
            elif trig.kind == "counter":
                value_int = int(state.get(trig.id, trig.default_value or 0))

                suffix = ""
                if trig.template:
                    suffix = templates.render_text_template(
                        trig.template,
                        enemy_names,
                        value=value_int,
                    )

                if trig.label and suffix:
                    label_text = f"{trig.label}: {suffix}"
                else:
                    label_text = trig.label or suffix or trig.id

                new_val = st.number_input(
                    label_text,
                    min_value=trig.min_value,
                    max_value=(
                        trig.max_value if trig.max_value is not None else 999
                    ),
                    value=value_int,
                    key=f"trigger_num_{widget_scope}_{trig.id}",
                )

                # Show per-step effects as the counter increases. Log them
                # so they persist across the immediate rerun performed when
                # the Timer advances.
                if trig.step_effects and new_val > value_int:
                    for step in range(value_int + 1, new_val + 1):
                        tmpl = trig.step_effects.get(step)
                        if tmpl:
                            effect_text = templates.render_text_template(
                                tmpl,
                                enemy_names,
                            )
                            log_entry(play_state, effect_text)
                            st.session_state.setdefault("encounter_last_trigger_messages", []).append(effect_text)
                            st.info(effect_text)

                state[trig.id] = new_val
                # If this counter trigger is configured to advance the Timer, do so now.
                inc_on = timer_behavior.get("increment_on_trigger")
                if inc_on and new_val > value_int and inc_on == trig.id:
                    play_state["timer"] += 1
                    log_text = timer_behavior.get("manual_increment_log", "Timer increased.")
                    log_entry(play_state, log_text)
                    st.rerun()

            # ----- NUMERIC (plain number) -----
            elif trig.kind == "numeric":
                value_int = int(state.get(trig.id, trig.default_value or 0))

                suffix = ""
                if trig.template:
                    suffix = templates.render_text_template(
                        trig.template,
                        enemy_names,
                        value=value_int,
                    )

                if trig.label and suffix:
                    label_text = f"{trig.label}: {suffix}"
                else:
                    label_text = trig.label or suffix or trig.id

                new_val = st.number_input(
                    label_text,
                    value=value_int,
                    key=f"trigger_numeric_{widget_scope}_{trig.id}",
                )
                state[trig.id] = new_val

            # ----- TIMER OBJECTIVE -----
            elif trig.kind == "timer_objective":
                label_text = trig.label or templates.render_text_template(
                    trig.template or "",
                    enemy_names,
                )

                st.markdown(f"- {label_text}")

                target_timer: Optional[int] = None
                if trig.timer_target is not None:
                    # For triggers in the UI we treat timer_target as an offset from player_count.
                    target_timer = get_player_count() + trig.timer_target

                if (
                    target_timer is not None
                    and play_state["timer"] >= target_timer
                ):
                    if trig.stop_on_complete:
                        st.caption(
                            f"✅ Objective reached at Timer {target_timer}."
                        )
                    else:
                        st.caption("✅ Objective condition met.")
                elif target_timer is not None:
                    st.caption(
                        f"⏳ Objective fails once Timer reaches {target_timer}."
                    )


# ---------------------------------------------------------------------
# Attached events, log, encounter card, enemy behaviors placeholder
# ---------------------------------------------------------------------


def _render_attached_events(encounter: dict) -> None:
    # V1 encounters cannot have attached events in Encounter Mode.
    # Also clear any stale events that might be left over from a V2 run.
    if _is_v1_encounter(encounter):
        st.session_state.pop("encounter_events", None)
        return
    
    events = st.session_state.get("encounter_events", [])

    with st.expander("Attached Events"):
        if not events:
            st.caption("No events attached to this encounter.")
            return

        rendezvous_count = sum(1 for ev in events if ev.get("is_rendezvous"))
        st.caption(
            f"{len(events)} event(s) attached"
            + (f" ({rendezvous_count} rendezvous)." if rendezvous_count else ".")
        )

        for ev in events:
            name = ev.get("name") or ev.get("id")
            st.markdown(f"- **{name}**")

            mods = EVENT_BEHAVIOR_MODIFIERS.get(name) or EVENT_BEHAVIOR_MODIFIERS.get(
                ev.get("id")
            )
            if mods:
                for m in mods:
                    desc = (
                        m.get("description")
                        or f"{m.get('stat')} {m.get('op')} {m.get('value')}"
                    )
                    st.caption(f"  • {desc}")
            else:
                st.caption("  • No special behavior modifiers recorded (yet).")


def _render_log(play_state: dict) -> None:
    with st.expander("Turn Log"):
        log = play_state.get("log") or []
        if not log:
            st.caption(
                "Timer / phase changes, resets, etc. will appear here as a quick history."
            )
            return

        for entry in reversed(log[-25:]):
            phase_label = "Enemy Phase" if entry["phase"] == "enemy" else "Player Phase"
            st.markdown(
                f"- Timer {entry['timer']} · {phase_label} · {entry['time']} — {entry['text']}"
            )
            

def _get_enemy_behavior_entries_for_encounter(encounter: dict) -> List[BehaviorEntry]:
    """
    Return a list of BehaviorEntry objects, one per *distinct* enemy type
    in the encounter, based on the shuffled enemy list.

    Matching is done by display name: enemy display name == BehaviorConfig.name.
    """
    enemy_names = _get_enemy_display_names(encounter)
    if not enemy_names:
        return []

    # Build a name→BehaviorEntry lookup from the behavior catalog
    catalog = build_behavior_catalog()  # {category: [BehaviorEntry, ...]}
    by_name: Dict[str, BehaviorEntry] = {}
    for entries in catalog.values():
        for entry in entries:
            # First one wins; avoid overwriting if duplicates exist
            by_name.setdefault(entry.name, entry)

    entries: List[BehaviorEntry] = []
    seen: set[str] = set()
    for name in enemy_names:
        if name in seen:
            continue
        seen.add(name)
        entry = by_name.get(name)
        if entry is not None:
            entries.append(entry)

    return entries


def _mod_applies_to_enemy(
    mod: Dict[str, Any],
    enemy_name: str,
    encounter: dict,
) -> bool:
    """
    Return True if this modifier applies to this enemy in this encounter.

    Supports:
    - target == "all_enemies"
    - target == "enemy_name"
    - target_alt_indices: list of 0-based enemy positions in the
      encounter's shuffled enemy list.
    """
    # Optional per-index targeting (0-based indices into the encounter enemies)
    alt_indices = mod.get("target_alt_indices")
    if alt_indices is not None:
        enemy_names = _get_enemy_display_names(encounter)
        target_names: set[str] = set()

        for idx in alt_indices:
            idx0 = int(idx)
            if 0 <= idx0 < len(enemy_names):
                target_names.add(enemy_names[idx0])

        # If nothing resolved or this enemy isn't in the targeted set,
        # this mod does not apply to this enemy.
        if not target_names or enemy_name not in target_names:
            return False

    # Then apply the simpler "target" field rules.
    target = mod.get("target", "all_enemies")
    if target == "all_enemies":
        return True
    if target == "enemy_name" and mod.get("enemy_name") == enemy_name:
        return True

    # If alt_indices was present and we didn't early-return False above,
    # but "target" is something unknown, just treat it as non-matching.
    return False


def _gather_behavior_mods_for_enemy(
    encounter: dict,
    enemy_name: str,
) -> List[Tuple[Dict[str, Any], str, str]]:
    """
    Return a list of (mod_dict, source_kind, source_label) tuples for this enemy,
    combining encounter-level and attached-event modifiers.

    - source_kind: "encounter" | "event"
    - source_label: encounter name or event name (for UI display)
    """
    mods: List[Tuple[Dict[str, Any], str, str]] = []
    seen_ids: set[tuple[str, str]] = set()

    # --- Encounter-level mods ---
    encounter_slug = f"{encounter['expansion']}_{encounter['encounter_level']}_{encounter['encounter_name']}"
    enc_label = encounter.get("encounter_name") or encounter.get("name") or ""

    if encounter_slug:
        for mod in ENCOUNTER_BEHAVIOR_MODIFIERS.get(encounter_slug, []):
            if not _mod_applies_to_enemy(mod, enemy_name, encounter):
                continue

            mod_id = mod.get("id")
            dedup_key = (mod_id, "encounter")
            if mod_id and dedup_key in seen_ids:
                continue
            if mod_id:
                seen_ids.add(dedup_key)

            mods.append((mod, "encounter", enc_label))

    # --- Event-level mods ---
    # V1 encounters ignore events (no attached event behavior mods).
    if _is_v1_encounter(encounter):
        return mods
    
    events = st.session_state.get("encounter_events", []) or []
    for ev in events:
        ev_id = ev.get("id")
        ev_name = ev.get("name")
        label = ev_name or ev_id or ""

        # Try both ID and name keys; EVENT_BEHAVIOR_MODIFIERS may use either
        for key in (ev_id, ev_name):
            if not key:
                continue
            for mod in EVENT_BEHAVIOR_MODIFIERS.get(key, []):
                if not _mod_applies_to_enemy(mod, enemy_name, encounter):
                    continue

                mod_id = mod.get("id")
                dedup_key = (mod_id, "event")
                if mod_id and dedup_key in seen_ids:
                    continue
                if mod_id:
                    seen_ids.add(dedup_key)

                mods.append((mod, "event", label))

    return mods


def _apply_behavior_mods_to_raw(
    raw_json: Dict[str, Any],
    mods: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Apply a list of behavior modifiers to a behavior JSON blob.

    Semantics:

    - For status flags like "bleed" (op == "flag"):
      * Add the status to each attack's `effect` list (left/right/etc),
        without duplicating it.
      * Also set a top-level flag (raw["bleed"] = True) for future use.

    - For stat == "damage" and op == "add":
      * Add the value to each attack's `damage` field.

    - For stat == "dodge_difficulty" and op == "add":
      * Apply the delta to `behavior["dodge"]` (the dodge difficulty).

    - For everything else:
      * Fallback to the old behavior:
        - "flag": raw[stat] = value (or True if value is None)
        - "add":  raw[stat] += value (creating it if missing)
    """
    patched = deepcopy(raw_json)
    behavior = patched.get("behavior")

    def _iter_attack_nodes():
        """
        Yield the per-column attack dicts under behavior
        (left/right/etc), skipping scalar entries like "dodge".
        """
        if not isinstance(behavior, dict):
            return
        for key, node in behavior.items():
            if key == "dodge":
                # numeric dodge difficulty, handled separately
                continue
            if isinstance(node, dict):
                yield node

    # Flags that should show up as status icons on attacks
    EFFECT_FLAG_STATS = {"bleed", "poison", "frostbite", "stagger", "calamity", "corrosion"}

    for mod in mods:
        stat = mod.get("stat")
        op = mod.get("op")
        val = mod.get("value")

        if not stat or not op:
            continue

        # Support dynamic value sources (e.g., use the current play Timer)
        value_from = mod.get("value_from")
        if value_from == "timer":
            # Read current timer from play state if available
            play = st.session_state.get("encounter_play") or {}
            timer_val = int(play.get("timer", 0) or 0)
            # If mod.value is numeric, treat it as a multiplier; otherwise default 1
            try:
                multiplier = float(mod.get("value", 1) or 1)
            except Exception:
                multiplier = 1
            val = int(timer_val * multiplier)

        # Scaling based on number of characters
        if val is None:
            base = mod.get("base")
            per_player = mod.get("per_player")

            # If the modifier supplies a non-numeric base (e.g. "∞"),
            # preserve that value directly rather than converting to 0.
            if base is not None and not isinstance(base, (int, float)):
                val = base
            else:
                amount = 0
                if isinstance(base, (int, float)):
                    amount += base
                if isinstance(per_player, (int, float)):
                    amount += per_player * get_player_count()

                val = amount

        # --- Push / node flags: per-attack booleans, not status effects ---
        # Encounter/event modifiers may say "push" or "node" with op "flag"/"set".
        # Treat those as booleans on each real attack node (left/middle/right).
        if stat in {"push", "node"} and op in {"flag", "set"}:
            for node in _iter_attack_nodes():
                # Only apply push to physical/magic attacks; never to type=="push".
                if stat == "push":
                    if node.get("type") not in ("physical", "magic"):
                        continue

                # Only touch nodes that are actual attacks.
                if (
                    "damage" not in node
                    and "effect" not in node
                    and "type" not in node
                ):
                    continue

                node[stat] = True if val is None else bool(val)

            # Also keep a top-level flag for convenience / future use.
            patched[stat] = True if val is None else bool(val)
            continue

        # --- Status flags (Bleed, etc.) -> add to effect[] on attacks ---
        if op == "flag" and stat in EFFECT_FLAG_STATS:
            for node in _iter_attack_nodes():
                # Only touch real attacks (those that already have effect or damage)
                if "effect" not in node and "damage" not in node:
                    continue
                effects = node.setdefault("effect", [])
                if isinstance(effects, list) and stat not in effects:
                    effects.append(stat)

            # Keep a top-level flag as well, in case something cares later
            patched[stat] = True if val is None else val
            continue

        # --- Global damage modifiers: hit every attack's damage field ---
        if op == "add" and stat == "damage" and isinstance(val, (int, float)):
            for node in _iter_attack_nodes():
                dmg = node.get("damage")
                if isinstance(dmg, (int, float)):
                    node["damage"] = dmg + val
            continue

        # --- Dodge difficulty: map onto behavior["dodge"] ---
        if op == "add" and stat == "dodge_difficulty" and isinstance(val, (int, float)):
            if isinstance(behavior, dict):
                old = behavior.get("dodge", 0)
                try:
                    behavior["dodge"] = old + val
                except TypeError:
                    try:
                        behavior["dodge"] = float(old) + float(val)
                    except Exception:
                        behavior["dodge"] = val
            else:
                # Fallback: if for some reason "behavior" isn't structured as expected
                old = patched.get("dodge_difficulty", 0)
                try:
                    patched["dodge_difficulty"] = old + val
                except TypeError:
                    try:
                        patched["dodge_difficulty"] = float(old) + float(val)
                    except Exception:
                        patched["dodge_difficulty"] = val
            continue

        # --- Movement modifiers: adjust 'distance' on per-attack move nodes ---
        if stat == "move" and op in {"add", "set"} and isinstance(val, (int, float)):
            for node in _iter_attack_nodes():
                try:
                    if node.get("type") != "move":
                        continue
                    old = int(node.get("distance", 0) or 0)
                except Exception:
                    old = 0

                if op == "add":
                    new = old + int(val)
                else:
                    new = int(val)

                # Clamp to available icon distances (1..4)
                new = max(1, min(4, new))
                node["distance"] = new

            # Keep a top-level marker for convenience
            try:
                patched["move"] = int(val)
            except Exception:
                patched["move"] = val
            continue

        # --- Set per-attack 'type' specially (e.g., convert attacks to magic) ---
        if op == "set" and stat == "type":
            for node in _iter_attack_nodes():
                # Only touch nodes that are actual attacks.
                if (
                    "damage" not in node
                    and "effect" not in node
                    and "type" not in node
                ):
                    continue
                try:
                    node["type"] = val
                except Exception:
                    node["type"] = str(val)
            continue

        if op == "set":
            patched[stat] = val
            continue

        # --- Fallback: old simple behavior ---
        if op == "flag":
            patched[stat] = True if val is None else val

        elif op == "add":
            old = patched.get(stat, 0)
            try:
                patched[stat] = old + val
            except TypeError:
                # Fallback if existing value is weird/non-numeric
                try:
                    patched[stat] = float(old) + float(val)
                except Exception:
                    patched[stat] = val

    return patched


def _describe_behavior_mod(mod: Dict[str, Any]) -> str:
    """
    Turn a behavior-modifier dict into a short human-readable sentence.
    """
    # If the mod explicitly provides a description, allow dynamic
    # substitution for some value sources (e.g., Timer) so the UI shows
    # the actual numeric bonus applied right now.
    desc = mod.get("description")
    value_from = mod.get("value_from")
    if value_from == "timer":
        play = st.session_state.get("encounter_play") or {}
        timer_val = int(play.get("timer", 0) or 0)
        try:
            multiplier = float(mod.get("value", 1) or 1)
        except Exception:
            multiplier = 1
        applied = int(timer_val * multiplier)

        # If the mod supplies an explicit description string, try to
        # substitute a value placeholder or sensible keywords so the
        # text reads naturally (e.g. "+3 damage from special rules").
        if isinstance(desc, str) and desc:
            # Preferred templating: use {value} if present
            if "{value}" in desc or "{applied}" in desc or "{timer}" in desc:
                try:
                    return desc.format(value=applied, applied=applied, timer=timer_val)
                except Exception:
                    # Fall back to naive replacements below
                    pass

            # Backwards-compatible replacements for common phrasings
            if "Timer value" in desc:
                return desc.replace("Timer value", str(applied))
            if "Timer" in desc:
                return desc.replace("Timer", str(timer_val))

        # If there's no explicit description, for common ops return a
        # short numeric summary like "+N stat" for add operations.
        if mod.get("op") == "add":
            stat = mod.get("stat", "stat")
            sign = "+" if applied >= 0 else ""
            return f"{sign}{applied} {stat}"

    stat = mod.get("stat", "stat")
    op = mod.get("op", "")
    value = mod.get("value")

    # If modifier uses per-player scaling (base + per_player * player_count),
    # compute the applied value for descriptions and substitute into any
    # provided description placeholders before falling back to the raw text.
    if (mod.get("per_player") is not None) or (mod.get("base") is not None and mod.get("per_player") is not None):
        try:
            base = int(mod.get("base", 0) or 0)
        except Exception:
            base = 0
        try:
            per_player = int(mod.get("per_player", 0) or 0)
        except Exception:
            per_player = 0
        applied = base + per_player * get_player_count()
        # If an explicit description exists, try to format it with the applied value
        if isinstance(desc, str) and desc:
            if "{value}" in desc or "{applied}" in desc or "{player_num}" in desc:
                try:
                    return desc.format(value=applied, applied=applied, player_num=applied)
                except Exception:
                    pass
            # Backwards-compatible literal replacements
            if "[player_num]" in desc:
                return desc.replace("[player_num]", str(applied))

        if mod.get("op") == "add":
            sign = "+" if applied >= 0 else ""
            return f"{sign}{applied} {mod.get('stat', 'stat')}"

    # If a description exists but didn't match any dynamic placeholders,
    # return it as-is.
    if desc:
        return desc

    if op == "flag":
        if value is True or value is None:
            return f"{stat} enabled"
        if value is False:
            return f"{stat} disabled"
        return f"{stat} = {value}"

    if op == "add":
        if isinstance(value, (int, float)):
            sign = "+" if value >= 0 else ""
            return f"{sign}{value} {stat}"
        return f"{stat} + {value}"

    return f"{stat} {op} {value}"


def _render_enemy_behaviors(encounter: dict, *, columns: int = 2) -> None:
    """
    Right-hand column: show enemy data + behavior cards for all distinct
    enemies in this encounter, using the Behavior Decks pipeline.

    - One stack per distinct enemy type (based on the shuffled list).
    - Uses NG+ scaling via load_behavior.
    - Applies encounter/event behavior modifiers to the raw JSON before rendering.
    """
    st.markdown("#### Enemy Behavior Cards")

    enemy_entries = _get_enemy_behavior_entries_for_encounter(encounter)

    # Include invaders present in this encounter (avoid dupes by name)
    try:
        invader_entries = invader_panel._get_invader_behavior_entries_for_encounter(encounter)
    except Exception:
        invader_entries = []

    if invader_entries:
        existing_names = {getattr(e, "name", None) for e in enemy_entries}
        merged: List[BehaviorEntry] = list(enemy_entries)
        for inv in invader_entries:
            if getattr(inv, "name", None) not in existing_names:
                merged.append(inv)
        entries = merged
    else:
        entries = enemy_entries

    if not entries:
        st.caption("No enemy behavior data found for this encounter.")
        return

    # Descending "threat": prefer .threat if present; otherwise .order_num
    def _threat_key(e: BehaviorEntry) -> int:
        v = getattr(e, "threat", None)
        if isinstance(v, (int, float)):
            return int(v)
        return int(getattr(e, "order_num", 10))

    entries = sorted(entries, key=_threat_key, reverse=True)

    # Dynamic column count (critical: compact calls with columns=1)
    ncols = max(1, int(columns or 1))
    if ncols == 1:
        cols = [st.container()]
    else:
        cols = list(st.columns(ncols, gap="medium"))

    # For the combined summary below all cards
    all_enemy_names: list[str] = []
    aggregated_mods: dict[tuple[str, str, str], dict[str, Any]] = {}

    for i, entry in enumerate(entries):
        target_col = cols[i % ncols]
        with target_col:
            cfg = load_behavior(entry.path)
            enemy_name = cfg.name
            all_enemy_names.append(enemy_name)

            mod_tuples = _gather_behavior_mods_for_enemy(encounter, enemy_name)
            mod_dicts = [m for (m, _, _) in mod_tuples]
            raw_for_render = _apply_behavior_mods_to_raw(cfg.raw, mod_dicts)

            # Special-case: for The Fountainhead, mark behavior JSON so
            # behavior-card renderer can add the extra icon to enemy cards.
            fountainhead_flagged = False
            if (encounter.get("encounter_name") == "The Fountainhead" or encounter.get("name") == "The Fountainhead"):
                beh = raw_for_render.get("behavior")
                if isinstance(beh, dict):
                    beh["_fountainhead_icon"] = True
                    fountainhead_flagged = True

            # Special-case: Hanging Rafters — add 'stagger' to all enemy
            # move-type cards and to any attack slots that have push.
            hanging_rafters_changed = False
            if (encounter.get("encounter_name") == "Hanging Rafters" or encounter.get("name") == "Hanging Rafters"):
                # Find behavior card dicts: either under 'behavior' or top-level
                candidates = []
                root_beh = raw_for_render.get("behavior")
                if isinstance(root_beh, dict):
                    candidates.append(root_beh)
                else:
                    # Top-level behavior entries (common format)
                    for k, v in list(raw_for_render.items()):
                        if not isinstance(v, dict):
                            continue
                        # Heuristic: behavior entries have 'left'/'middle'/'right' or 'dodge'
                        if any(x in v for x in ("left", "middle", "right", "dodge")):
                            candidates.append(v)

                for beh in candidates:
                    try:
                        top_type = str(beh.get("type", "")).lower()
                    except Exception:
                        top_type = ""

                    for slot in ("left", "middle", "right"):
                        spec = beh.get(slot)
                        if not isinstance(spec, dict):
                            continue

                        # If the card is a move-type, add stagger to any attack node
                        if top_type == "move":
                            effects = spec.setdefault("effect", [])
                            if isinstance(effects, list) and "stagger" not in effects:
                                effects.append("stagger")
                                hanging_rafters_changed = True

                        # Also add stagger to any attack that has push (flag or type)
                        has_push = bool(spec.get("push")) or (spec.get("type") == "push")
                        if has_push:
                            effects = spec.setdefault("effect", [])
                            if isinstance(effects, list) and "stagger" not in effects:
                                effects.append("stagger")
                                hanging_rafters_changed = True
                

            # Special-case: use alternate data card for certain enemies in The Shine of Gold
            if cfg.name in ("Mimic", "Phalanx") and (encounter.get("encounter_name") == "The Shine of Gold" or encounter.get("name") == "The Shine of Gold"):
                data_card_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data_The Shine of Gold.jpg"
            else:
                data_card_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            data_bytes = render_data_card_cached(
                data_card_path,
                raw_for_render,
                is_boss=(cfg.tier == "boss"),
            )
            if data_bytes is not None:
                data_uri = bytes_to_data_uri(data_bytes, mime="image/jpeg")

                st.markdown(
                    f"""
                    <div class="card-image">
                        <img src="{data_uri}" style="width:100%">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)

        # If we made any special-case changes (Fountainhead / Hanging Rafters),
        # add synthetic modifier tuples so they appear in the global summary.
        enc_label = encounter.get("encounter_name") or encounter.get("name") or ""
        if fountainhead_flagged:
            mod_tuples.append((
                {
                    "id": "fountainhead_icon",
                    "stat": "icon",
                    "op": "flag",
                    "value": True,
                    "description": "Adds an extra move away from closest icon to enemy behavior cards (The Fountainhead).",
                },
                "encounter",
                enc_label,
            ))
        if hanging_rafters_changed:
            mod_tuples.append((
                {
                    "id": "hanging_rafters_stagger",
                    "stat": "stagger",
                    "op": "flag",
                    "value": True,
                    "description": "Adds Stagger to all move-attacks and attacks with push (Hanging Rafters).",
                },
                "encounter",
                enc_label,
            ))

        # Aggregate mods for global summary (needs enemy_name + mod_tuples)
        for mod, source_kind, source_label in mod_tuples:
            desc = _describe_behavior_mod(mod)
            if not desc:
                continue

            mod_id = mod.get("id") or desc
            label = source_label or ""
            key = (mod_id, source_kind, label)

            info = aggregated_mods.get(key)
            if info is None:
                info = {
                    "mod": mod,
                    "source_kind": source_kind,
                    "source_label": label,
                    "desc": desc,
                    "enemy_names": set(),
                }
                aggregated_mods[key] = info

            info["enemy_names"].add(enemy_name)

    if aggregated_mods:
        st.markdown("#### Behavior modifiers in effect")

        unique_enemy_names = set(all_enemy_names)

        def _sort_key(info: dict[str, Any]) -> tuple:
            kind = info["source_kind"]
            kind_order = 0 if kind == "encounter" else 1
            return (kind_order, info.get("source_label", "") or "", info.get("desc", ""))

        for info in sorted(aggregated_mods.values(), key=_sort_key):
            enemies = sorted(info["enemy_names"])
            if len(enemies) == len(unique_enemy_names):
                applies_to = "all enemies"
            elif len(enemies) == 1:
                applies_to = enemies[0]
            else:
                applies_to = ", ".join(enemies)

            source_kind = info["source_kind"]
            label = info.get("source_label") or ""
            desc = info["desc"]

            prefix = (f"Event: {label}" if label else "Event") if source_kind == "event" else "Encounter"

            st.markdown(
                f"- **{prefix}** — {desc}  \n"
                f"  _Applies to: {applies_to}_"
            )
