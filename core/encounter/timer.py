from __future__ import annotations
from typing import Dict
from core.encounter_rules import make_encounter_key
from core.encounter_triggers import get_triggers_for_encounter


# ---------------------------------------------------------------------
# Special timer behaviour for specific encounters
# ---------------------------------------------------------------------

# Per-encounter / per-variant timer tweaks:
# - manual_increment: don't auto-increase Timer on player→enemy; show a button instead
# - reset_button: show a button that resets Timer to 0 (without changing phase)
_SPECIAL_TIMER_BEHAVIORS = {
    "Eye of the Storm|Painted World of Ariamis": {
        "edited": {
            "manual_increment": True,
            "manual_increment_label": "Increase Timer (no enemies on active tiles)",
            "manual_increment_help": (
                "Only click this at the end of a character's turn if there are no "
                "enemies on any active tile."
            ),
            "manual_increment_log": "Timer increased (no enemies on active tiles).",
        }
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": {
            "reset_button": True,
            "reset_button_label": "Tile made active (reset Timer)",
            "reset_button_help": (
                "When a tile is made active, reset the Timer to 0 (objective: "
                "kill all enemies before time runs out)."
            ),
            "reset_button_log": "Timer reset to 0 because a tile was made active.",
        }
    },
    "The Bell Tower|The Sunless City": {
        "default": {
            # Don't auto-increase the Timer on Player→Enemy transitions.
            "manual_increment": True,
            # Hide the generic manual-increment button — Timer increases only
            # when the lever trigger is activated.
            "hide_manual_increment_button": True,
            "manual_increment_label": "Increase Timer (lever pulled)",
            "manual_increment_help": (
                "The Timer increases only when the lever is pulled. "
                "Do not increment the Timer manually."
            ),
            "manual_increment_log": "Timer increased due to lever activation.",
            # When this trigger id steps, increment the Timer automatically.
            "increment_on_trigger": "bell_tower_lever",
        }
    },
}


# Hidden encounter-level timer caps (in rounds).
#
# Values are stored as offsets from the player_count. For example, a value of 5
# means "players + 5", so in a 3-player game the timer cap is 8.
_HARD_TIMER_LIMITS: Dict[str, Dict[str, int]] = {
    # Corvian Host: "Kill all enemies before the Timer reaches {players+5}"
    "Corvian Host|Painted World of Ariamis": {
        "default": 5,   # limit = players + 5
    },
    # Add more encounters here later if needed
}


def get_timer_behavior(encounter: dict, *, edited: bool = False) -> dict:
    """
    Return a small config dict describing any special timer behavior
    for the given encounter (if any).

    The returned dict is taken from _SPECIAL_TIMER_BEHAVIORS and may contain:
      - manual_increment: bool
      - manual_increment_label: str
      - manual_increment_help: str
      - manual_increment_log: str
      - reset_button: bool
      - reset_button_label: str
      - reset_button_help: str
      - reset_button_log: str
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    variants = _SPECIAL_TIMER_BEHAVIORS.get(encounter_key)
    if not variants:
        return {}

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default", {})


def should_stop_on_timer_objective(
    encounter: dict,
    *,
    edited: bool,
    player_count: int,
    timer_value: int,
) -> bool:
    """
    Decide if a timer-based objective has expired.

    Sources:
    - Visible timer_objective triggers (if any) defined in ENCOUNTER_TRIGGERS.
    - Hidden encounter-level limits from _HARD_TIMER_LIMITS.

    This is a pure function: callers must supply the current timer value,
    the player count, and whether the encounter is using its edited variant.
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    # 1) Visible timer_objective triggers (if you ever use them)
    triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )
    if triggers:
        for trig in triggers:
            if (
                trig.kind == "timer_objective"
                and trig.stop_on_complete
                and trig.timer_target is not None
            ):
                # For triggers we treat timer_target as an absolute value.
                if timer_value >= trig.timer_target:
                    return True

    # 2) Hidden encounter-level hard timer caps
    caps = _HARD_TIMER_LIMITS.get(encounter_key)
    if caps:
        # Pick default vs edited variant if present
        offset = caps.get("edited" if edited else "default")
        if offset is not None:
            limit = player_count + offset
            if timer_value >= limit:
                return True

    return False
