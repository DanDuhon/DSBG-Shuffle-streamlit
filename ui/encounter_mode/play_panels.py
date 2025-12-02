from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from copy import deepcopy
import base64
import streamlit as st

from ui.events_tab.logic import EVENT_BEHAVIOR_MODIFIERS
from ui.encounters_tab.assets import enemyNames
from core.encounter_rules import (
    make_encounter_key,
    get_rules_for_encounter,
    get_upcoming_rules_for_encounter,
)
from core.encounter_triggers import (
    EncounterTrigger,
    get_triggers_for_encounter,
    get_triggers_for_event,
)

from core.encounter import templates
from core.encounter import objectives as obj_mod
from ui.encounter_mode.play_state import get_player_count, log_entry

from ui.behavior_decks_tab.assets import BEHAVIOR_CARDS_PATH
from ui.behavior_decks_tab.generation import render_data_card_cached, build_behavior_catalog
from ui.behavior_decks_tab.logic import load_behavior
from ui.behavior_decks_tab.models import BehaviorEntry
from ui.encounters_tab.logic import ENCOUNTER_BEHAVIOR_MODIFIERS


# ---------------------------------------------------------------------
# Constants / small data tables
# ---------------------------------------------------------------------

TIMER_ICON_PATH = Path("assets") / "timer.png"

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
# Rules + upcoming rules
# ---------------------------------------------------------------------


def _render_rules(encounter: dict, settings: dict, play_state: dict) -> None:
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

    # Rules that apply *right now*
    current_rules = get_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        timer=play_state["timer"],
        phase=play_state["phase"],  # "enemy" or "player"
    )

    enemy_names = _get_enemy_display_names(encounter)
    player_count = get_player_count()

    if not current_rules:
        st.caption("No rules to show for this encounter in the current state.")
    else:
        for rule in current_rules:
            text = templates.render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            st.markdown(f"- {text}", unsafe_allow_html=True)

    # --- Upcoming rules: inline section (no expander) ---
    upcoming = get_upcoming_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        current_timer=play_state["timer"],
        max_lookahead=3,  # show next 3 Timer step(s); tweak if you like
    )

    if upcoming:
        st.markdown("**Upcoming rules**")

        for trigger_timer, rule in upcoming:
            phase_label = {
                "enemy": "Enemy Phase",
                "player": "Player Phase",
                "any": "Any Phase",
            }.get(rule.phase, "Any Phase")

            text = templates.render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            st.markdown(
                f"- **Timer {trigger_timer} · {phase_label}** — {text}",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------
# Timer + phase header
# ---------------------------------------------------------------------


def _render_timer_and_phase(play_state: dict) -> None:
    # One row: [Timer icon count] | [Enemy Phase / Player Phase]
    c1, c2 = st.columns([1.4, 1])

    # Left side: Timer [icon] [counter]
    with c1:
        try:
            with open(TIMER_ICON_PATH, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            img_tag = (
                f"<img src='data:image/png;base64,{data}' "
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
) -> None:
    if timer_behavior is None:
        timer_behavior = {}

    st.markdown("#### Turn Controls")

    b1, b2, b3 = st.columns(3)

    # Previous Turn
    with b1:
        if st.button("Previous Turn", key="encounter_play_prev_turn"):
            st.session_state["encounter_play_pending_action"] = "prev"
            st.rerun()

    # Next Turn
    with b2:
        if st.button(
            "Next Turn",
            key="encounter_play_next_turn",
            disabled=stop_on_timer_objective,
        ):
            st.session_state["encounter_play_pending_action"] = "next"
            st.rerun()

    # Reset
    with b3:
        if st.button("Reset", key="encounter_play_reset"):
            st.session_state["encounter_play_pending_action"] = "reset"
            st.rerun()

    if stop_on_timer_objective:
        st.caption("Time has run out; Next Turn is disabled for this encounter.")

    # --- Special timer actions (per-encounter) ---
    has_manual_inc = bool(timer_behavior.get("manual_increment"))
    has_reset_btn = bool(timer_behavior.get("reset_button"))

    if has_manual_inc or has_reset_btn:
        st.markdown("##### Special Timer Actions")
        cols = st.columns(
            (1 if has_manual_inc else 0) + (1 if has_reset_btn else 0)
        )

        col_idx = 0

        # Manual 'Increase Timer' button (e.g. Eye of the Storm edited)
        if has_manual_inc:
            label = timer_behavior.get(
                "manual_increment_label",
                "Increase Timer",
            )
            help_text = timer_behavior.get("manual_increment_help")
            log_text = timer_behavior.get(
                "manual_increment_log",
                "Timer manually increased.",
            )

            with cols[col_idx]:
                if st.button(
                    label,
                    key="encounter_play_manual_timer_increase",
                ):
                    play_state["timer"] += 1
                    log_entry(play_state, log_text)
                    st.rerun()
            col_idx += 1
            if help_text:
                st.caption(help_text)

        # 'Reset Timer' button (e.g. Corvian Host: tile made active)
        if has_reset_btn:
            label = timer_behavior.get(
                "reset_button_label",
                "Reset Timer (special rule)",
            )
            help_text = timer_behavior.get("reset_button_help")
            log_text = timer_behavior.get(
                "reset_button_log",
                "Timer reset due to special rule.",
            )

            with cols[col_idx]:
                if st.button(
                    label,
                    key="encounter_play_special_timer_reset",
                ):
                    old_timer = play_state["timer"]
                    play_state["timer"] = 0
                    log_entry(
                        play_state,
                        f"{log_text} (was {old_timer}, now 0)",
                    )
                    st.rerun()
            if help_text:
                st.caption(help_text)


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
    st.markdown("#### Encounter Triggers")

    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)

    # --- Gather all trigger sources: encounter + attached events ---
    encounter_triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )

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

    # 2) Event-level triggers (NEW)
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
        kind = src["kind"]
        scope_key = src["scope_key"]
        label = src["label"]
        triggers = src["triggers"]

        # Sub-heading for event-based triggers so they’re easy to distinguish
        if kind == "event" and label:
            st.markdown(f"**Event: {label}**")

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
                    st.info(effect_text)

                state[trig.id] = new_val

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

                # Show per-step effects as the counter increases
                if trig.step_effects and new_val > value_int:
                    for step in range(value_int + 1, new_val + 1):
                        tmpl = trig.step_effects.get(step)
                        if tmpl:
                            effect_text = templates.render_text_template(
                                tmpl,
                                enemy_names,
                            )
                            st.info(effect_text)

                state[trig.id] = new_val

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


def _render_attached_events() -> None:
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


def _mod_applies_to_enemy(mod: Dict[str, Any], enemy_name: str) -> bool:
    """
    For now, everything is 'all_enemies', but this gives you a hook to
    target specific enemies later (enemy_name, enemy_id, etc.).
    """
    target = mod.get("target", "all_enemies")
    if target == "all_enemies":
        return True
    if target == "enemy_name" and mod.get("enemy_name") == enemy_name:
        return True
    # Extend with more targeting rules as needed
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
            if not _mod_applies_to_enemy(mod, enemy_name):
                continue

            mod_id = mod.get("id")
            dedup_key = (mod_id, "encounter")
            if mod_id and dedup_key in seen_ids:
                continue
            if mod_id:
                seen_ids.add(dedup_key)

            mods.append((mod, "encounter", enc_label))

    # --- Event-level mods ---
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
                if not _mod_applies_to_enemy(mod, enemy_name):
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
    EFFECT_FLAG_STATS = {"bleed", "poison", "frostbite", "toxic"}

    for mod in mods:
        stat = mod.get("stat")
        op = mod.get("op")
        val = mod.get("value")

        if not stat or not op:
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
    desc = mod.get("description")
    if desc:
        return desc

    stat = mod.get("stat", "stat")
    op = mod.get("op", "")
    value = mod.get("value")

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


def _render_enemy_behaviors(encounter: dict) -> None:
    """
    Right-hand column: show enemy data + behavior cards for all distinct
    enemies in this encounter, using the Behavior Decks pipeline.

    - One stack per distinct enemy type (based on the shuffled list).
    - Uses NG+ scaling via load_behavior.
    - Applies encounter/event behavior modifiers to the raw JSON before rendering.
    """
    st.markdown("#### Enemy Behavior Cards")

    entries = _get_enemy_behavior_entries_for_encounter(encounter)
    if not entries:
        st.caption("No enemy behavior data found for this encounter.")
        return

    # Sort by order_num descending (higher priority first)
    entries = sorted(
        entries,
        key=lambda e: getattr(e, "order_num", 10),
        reverse=True,
    )

    # Two sub-columns so we don't get a super tall single column
    col_a, col_b = st.columns(2, gap="medium")

    for i, entry in enumerate(entries):
        target_col = col_a if i % 2 == 0 else col_b
        with target_col:
            # Load behavior config (NG+ already applied inside load_behavior)
            cfg = load_behavior(entry.path)
            enemy_name = cfg.name

            # Gather all behavior modifiers that apply to this enemy
            mod_tuples = _gather_behavior_mods_for_enemy(encounter, enemy_name)
            mod_dicts = [m for (m, _, _) in mod_tuples]

            # Apply mods to raw json before rendering data card
            raw_for_render = _apply_behavior_mods_to_raw(cfg.raw, mod_dicts)

            # Always show the data card for this enemy/boss if available
            data_card_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            data_bytes = render_data_card_cached(
                data_card_path,
                raw_for_render,
                is_boss=(cfg.tier == "boss"),
            )
            if data_bytes is not None:
                st.image(data_bytes, width="stretch")

            # If there are active modifiers, show a small list under the card
            if mod_tuples:
                st.caption("_Behavior modifiers in effect:_")
                for mod, source_kind, source_label in mod_tuples:
                    desc = _describe_behavior_mod(mod)
                    if not desc:
                        continue

                    if source_kind == "event":
                        prefix = f"Event: {source_label}" if source_label else "Event"
                    else:
                        prefix = "Encounter"

                    st.caption(f"  • {prefix} — {desc}")
