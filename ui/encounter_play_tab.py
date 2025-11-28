import streamlit as st
import base64
from datetime import datetime
from pathlib import Path

from ui.events_tab.logic import EVENT_BEHAVIOR_MODIFIERS
from ui.encounters_tab.assets import enemyNames
from core.encounter_rules import (
    make_encounter_key,
    get_rules_for_encounter,
    get_upcoming_rules_for_encounter,
)
from core.encounter_triggers import (
    ENCOUNTER_TRIGGERS,
    EncounterTrigger,
    render_trigger_template,
)


TIMER_ICON_PATH = Path("assets") / "timer.png"


# ---------------------------------------------------------------------
# Helpers: state + ids
# ---------------------------------------------------------------------
def _get_encounter_id(encounter: dict):
    """Best-effort way to identify the current encounter for resetting state."""
    for key in ("id", "slug", "encounter_slug", "encounter_name"):
        if key in encounter:
            return encounter[key]
    return None


def _get_player_count() -> int:
    try:
        pc = int(st.session_state.get("player_count", 1))
    except Exception:
        pc = 1
    return max(pc, 1)


def _ensure_play_state(encounter_id):
    """
    Keep a small piece of state for the Play tab.
    Reset automatically when the active encounter changes.
    """
    state = st.session_state.get("encounter_play")

    if (not state) or (state.get("encounter_id") != encounter_id):
        state = {
            "encounter_id": encounter_id,
            "phase": "enemy",   # "enemy" | "player"
            "timer": 0,         # starts at 0, increments after player phase
            "log": [],
        }
        st.session_state["encounter_play"] = state

    return state


def _log(play_state: dict, text: str):
    play_state.setdefault("log", []).append(
        {
            "timer": play_state.get("timer", 0),
            "phase": play_state.get("phase", "enemy"),
            "text": text,
            "time": datetime.now().strftime("%H:%M"),
        }
    )


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
            names.append(enemyNames[eid])

    return names


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

    if not current_rules:
        st.caption("No rules to show for this encounter in the current state.")
    else:
        for rule in current_rules:
            text = rule.render(enemy_names=enemy_names)
            st.markdown(f"- {text}")

    # --- Upcoming rules: inline section (no expander) ---
    upcoming = get_upcoming_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        current_timer=play_state["timer"],
        max_lookahead=3,  # show next 3 Timer step(s); tweak if you like
    )

    st.markdown("**Upcoming rules**")

    if not upcoming:
        st.caption("No upcoming rules.")

    for trigger_timer, rule in upcoming:
        phase_label = {
            "enemy": "Enemy Phase",
            "player": "Player Phase",
            "any": "Any Phase",
        }.get(rule.phase, "Any Phase")
        text = rule.render(enemy_names=enemy_names)
        st.markdown(
            f"- **Timer {trigger_timer} · {phase_label}** — {text}"
        )


def _get_encounter_trigger_defs(encounter_key: str) -> list[EncounterTrigger]:
    return ENCOUNTER_TRIGGERS.get(encounter_key, [])


def _ensure_trigger_state(encounter_key: str, triggers: list[EncounterTrigger]) -> dict:
    """
    Ensure we have a state dict for this encounter's triggers in session_state.
    """
    all_state = st.session_state.setdefault("encounter_triggers", {})
    enc_state = all_state.setdefault(encounter_key, {})

    for trig in triggers:
        if trig.id not in enc_state:
            if trig.kind in ("counter", "numeric"):
                enc_state[trig.id] = int(trig.default_value or 0)
            elif trig.kind == "checkbox":
                enc_state[trig.id] = bool(trig.default_value or False)
            elif trig.kind == "timer_objective":
                enc_state[trig.id] = False  # could track "acknowledged" if you want

    return enc_state


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------
def render(settings: dict) -> None:
    """
    Encounter Play tab.

    Assumes:
    - Setup tab has populated st.session_state.current_encounter
    - Events tab has optionally populated st.session_state.encounter_events
    """
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    encounter = st.session_state.current_encounter
    encounter_id = _get_encounter_id(encounter)
    play_state = _ensure_play_state(encounter_id)

    # -----------------------------------------------------------------
    # Main layout: 3 columns
    # Left: timer/phase + controls + triggers + rules + events + log
    # Middle: encounter card
    # Right: enemy behavior cards (placeholder for now)
    # -----------------------------------------------------------------
    col_left, col_mid, col_right = st.columns([1, 1, 1], gap="large")

    with col_left:
        timer_phase_container = st.container()
        controls_container = st.container()
        rest_container = st.container()

        # First: figure out if any timer_objective wants to stop play
        # (purely based on current timer + triggers definition)
        stop_on_timer_objective = _render_encounter_triggers(encounter, play_state, settings)

        # Then controls (can use stop_on_timer_objective)
        with controls_container:
            _render_turn_controls(play_state, stop_on_timer_objective=stop_on_timer_objective)

        # Finally, timer+phase (after button clicks update state)
        with timer_phase_container:
            _render_timer_and_phase(play_state)

        # Rules, events, log
        with rest_container:
            _render_rules(encounter, settings, play_state)
            _render_attached_events()
            _render_log(play_state)

    with col_mid:
        _render_encounter_card(encounter)

    with col_right:
        _render_enemy_behaviors_placeholder(encounter)


# ---------------------------------------------------------------------
# Left column: timer/phase, buttons, triggers, rules, events, log
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


def _advance_turn(play_state: dict) -> None:
    """
    Smart 'Next Turn' behavior:

    - Start: Timer 0, Enemy Phase.
    - Enemy → Player (no timer change).
    - Player → Enemy and **timer +1**.
    """
    if play_state["phase"] == "enemy":
        play_state["phase"] = "player"
        _log(play_state, "Advanced to Player Phase")
    else:  # player -> enemy, increment timer
        play_state["timer"] += 1
        play_state["phase"] = "enemy"
        _log(play_state, "Advanced to Enemy Phase; timer increased")


def _previous_turn(play_state: dict) -> None:
    """
    Reverse of _advance_turn, as best we can:

    - Player → Enemy (no timer change).
    - Enemy → Player and **timer -1**, but never below 0.
    """
    if play_state["phase"] == "player":
        play_state["phase"] = "enemy"
        _log(play_state, "Reverted to Enemy Phase")
    else:  # enemy
        if play_state["timer"] > 0:
            play_state["timer"] -= 1
            play_state["phase"] = "player"
            _log(
                play_state,
                f"Reverted to Player Phase; timer reduced to {play_state['timer']}",
            )
        else:
            _log(play_state, "Already at starting state; cannot go back further")


def _reset_play_state(play_state: dict) -> None:
    play_state["phase"] = "enemy"
    play_state["timer"] = 0
    play_state["log"] = []
    _log(play_state, "Play state reset (Timer 0, Enemy Phase)")


def _render_turn_controls(play_state: dict, stop_on_timer_objective: bool = False) -> None:
    st.markdown("#### Turn Controls")

    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("Previous Turn", key="encounter_play_prev_turn"):
            _previous_turn(play_state)

    with b2:
        if st.button(
            "Next Turn",
            key="encounter_play_next_turn",
            disabled=stop_on_timer_objective,
        ):
            _advance_turn(play_state)

    with b3:
        if st.button("Reset", key="encounter_play_reset"):
            _reset_play_state(play_state)

    if stop_on_timer_objective:
        st.caption("Time has run out; Next Turn is disabled for this encounter.")
    else:
        st.caption(
            "Flow: **Enemy → Player → Enemy (+1 Timer)**. "
            "Use Previous Turn if you click Next Turn by mistake."
        )


def _get_encounter_triggers(encounter: dict):
    """
    Placeholder: later this can pull structured triggers from encounter data.

    For now, always returns an empty list so the section stays hidden.
    """
    return encounter.get("triggers", []) or []


def _render_encounter_triggers(encounter: dict, play_state: dict, settings: dict) -> bool:
    """
    Render encounter-specific triggers and trackers.

    Returns:
        stop_on_timer_objective: bool
            True if there is a timer_objective with stop_on_complete=True
            that has been reached. You *can* use this to disable Next Turn.
    """
    # Build encounter key (same as for rules)
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    triggers = _get_encounter_trigger_defs(encounter_key)
    if not triggers:
        return False  # nothing to render, nothing to block

    st.markdown("#### Encounter Triggers")

    enemy_names = _get_enemy_display_names(encounter)
    state = _ensure_trigger_state(encounter_key, triggers)

    stop_on_timer_objective = False

    for trig in triggers:
        current_val = state.get(trig.id, trig.default_value or 0)

        if trig.kind == "checkbox":
            old_val = bool(current_val)
            player_count = _get_player_count()

            # Build label:
            # - If template is present, render it (with {players}, {players+N}, etc.)
            # - If label is also present, use "Label: rendered_template"
            if trig.template:
                rendered = render_trigger_template(
                    trig.template,
                    enemy_names=enemy_names,
                    player_count=player_count,
                )
                if trig.label:
                    label_text = f"{trig.label}: {rendered}"
                else:
                    label_text = rendered
            else:
                # No template → just use label
                label_text = trig.label or ""

            new_val = st.checkbox(
                label_text,
                value=old_val,
                key=f"trigger_{encounter_key}_{trig.id}",
            )
            state[trig.id] = new_val

            # One-shot effect when flipping False -> True
            if trig.effect_template and (not old_val and new_val):
                effect = render_trigger_template(
                    trig.effect_template,
                    enemy_names=enemy_names,
                    player_count=player_count,
                )
                st.info(effect)

        # ----- COUNTER (e.g. The First Bastion lever) -----
        elif trig.kind == "counter":
            old_val = int(current_val)
            new_val = old_val

            # Layout: label (left) and - / + buttons (right)
            c_label, c_minus, c_plus = st.columns([3, 1, 1])

            # First process buttons (so state is updated before we render label)
            with c_minus:
                if st.button("➖", key=f"trigger_dec_{encounter_key}_{trig.id}"):
                    new_val = max(trig.min_value, old_val - 1)

            with c_plus:
                if st.button("➕", key=f"trigger_inc_{encounter_key}_{trig.id}"):
                    upper = trig.max_value if trig.max_value is not None else old_val + 1
                    base = max(new_val, old_val)
                    new_val = min(upper, base + 1)

            # If the value changed this run, update state and fire any step effect
            if new_val != old_val:
                state[trig.id] = new_val

                # Only fire step_effects on increments
                if trig.step_effects and new_val > old_val:
                    tmpl = trig.step_effects.get(new_val)
                    if tmpl:
                        effect = render_trigger_template(
                            tmpl,
                            enemy_names=enemy_names,
                        )
                        st.info(effect)

            effective_val = state[trig.id]

            # Now build the label using the UPDATED value
            suffix = ""
            if trig.template:
                suffix = render_trigger_template(
                    trig.template,
                    enemy_names=enemy_names,
                    value=effective_val,
                )
            if trig.label and suffix:
                label_text = f"{trig.label}: {suffix}"
            else:
                label_text = trig.label or suffix

            with c_label:
                st.markdown(label_text)

        # ----- NUMERIC (e.g. barrels per tile) -----
        elif trig.kind == "numeric":
            value_int = int(current_val)

            suffix = ""
            if trig.template:
                suffix = render_trigger_template(
                    trig.template,
                    enemy_names=enemy_names,
                    value=value_int,
                )
            if trig.label and suffix:
                label_text = f"{trig.label}: {suffix}"
            else:
                label_text = trig.label or suffix

            new_val = st.number_input(
                label_text,
                min_value=trig.min_value,
                max_value=trig.max_value if trig.max_value is not None else 999,
                value=value_int,
                key=f"trigger_num_{encounter_key}_{trig.id}",
            )
            state[trig.id] = new_val

        # ----- TIMER OBJECTIVE -----
        elif trig.kind == "timer_objective":
            label_text = trig.label or render_trigger_template(
                trig.template or "", enemy_names=enemy_names
            )

            st.markdown(f"- {label_text}")
            if trig.timer_target is not None and play_state["timer"] >= trig.timer_target:
                if trig.stop_on_complete:
                    stop_on_timer_objective = True
                st.caption(f"✅ Objective reached at Timer {trig.timer_target}.")
            elif trig.timer_target is not None:
                st.caption(f"⏳ Objective triggers at Timer {trig.timer_target}.")

    return stop_on_timer_objective


def _get_rules_for_encounter(encounter: dict, settings: dict):
    """
    Placeholder hook for your actual rules system.
    """
    rules = encounter.get("rules") or []
    return [str(r) for r in rules]


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
                    desc = m.get("description") or f"{m.get('stat')} {m.get('op')} {m.get('value')}"
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


# ---------------------------------------------------------------------
# Middle column: encounter card
# ---------------------------------------------------------------------
def _render_encounter_card(encounter: dict) -> None:
    st.markdown("#### Encounter Card")
    img = encounter.get("card_img")
    if img is not None:
        st.image(img, width="stretch")
    else:
        st.caption("Encounter card not available (no image in state).")


# ---------------------------------------------------------------------
# Right column: enemy behavior cards (placeholder)
# ---------------------------------------------------------------------
def _render_enemy_behaviors_placeholder(encounter: dict) -> None:
    st.markdown("#### Enemy Behavior Cards")

    st.caption(
        "Placeholder: behavior cards for each distinct enemy in this "
        "encounter will appear here in descending **order_num** order."
    )

    enemies = encounter.get("enemies") or encounter.get("figures") or []
    if enemies:
        st.caption("Detected enemies (for future behavior cards):")
        for e in enemies:
            if isinstance(e, dict):
                label = e.get("name") or e.get("id") or str(e)
            else:
                label = str(e)
            st.markdown(f"- {label}")
