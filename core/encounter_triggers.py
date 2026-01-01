# core/encounter_triggers.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Dict, List

Phase = Literal["enemy", "player", "any"]
TriggerKind = Literal["checkbox", "counter", "numeric", "timer_objective"]


@dataclass(frozen=True)
class EncounterTrigger:
    id: str

    # Short UI text on the widget ("Lever activations", "Chest opened", etc.)
    label: str

    kind: TriggerKind  # "checkbox" | "counter" | "numeric" | "timer_objective"

    # Optional status text shown next to label (can contain {value}, {enemy1}, etc.)
    template: Optional[str] = None

    # Optional one-shot effect text for checkboxes, when they flip False -> True
    effect_template: Optional[str] = None

    # Optional per-step effect for counters:
    # {1: "Spawn a {enemy2}...", 2: "Spawn a {enemy3}...", ...}
    step_effects: Optional[Dict[int, str]] = None

    phase: Phase = "any"
    min_value: int = 0
    max_value: Optional[int] = None
    default_value: Optional[int | bool] = None
    timer_target: Optional[int] = None
    stop_on_complete: bool = False


# outer key   -> encounter identifier, e.g. "The First Bastion|Painted World of Ariamis"
# inner key   -> variant: "default" (non-edited) or "edited"
# list value  -> EncounterTrigger definitions for that variant
EncounterTriggersMap = Dict[str, Dict[str, List[EncounterTrigger]]]
EventTriggersMap = Dict[str, List[EncounterTrigger]]


def get_triggers_for_encounter(
    *,
    encounter_key: str,
    edited: bool,
) -> List[EncounterTrigger]:
    """
    Return the triggers for a given encounter.

    - If an "edited" triggers list exists and `edited` is True, it is used.
    - Otherwise, the "default" triggers list is used.
    """
    variants = ENCOUNTER_TRIGGERS.get(encounter_key)
    if not variants:
        return []

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default", [])


def get_triggers_for_event(*, event_key: str) -> List[EncounterTrigger]:
    """
    Return the triggers defined for a specific event card.

    `event_key` should match the key used in EVENT_TRIGGERS (usually the
    event's id, but you can also use the printed name if you prefer).
    """
    return EVENT_TRIGGERS.get(event_key, [])


ENCOUNTER_TRIGGERS: EncounterTriggersMap = {
    "The First Bastion|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="the_first_bastion_lever",
                label="Lever activations",
                kind="counter",
                template="",
                min_value=0,
                max_value=3,
                default_value=0,
                phase="player",
                step_effects={
                    1: "Spawn a {enemy2} on enemy spawn node 1 on tile 1.",
                    2: "Spawn a {enemy3} on enemy spawn node 2 on tile 1.",
                    3: "Spawn a {enemy4} on enemy spawn node 1 on tile 1.",
                },
            ),
            EncounterTrigger(
                id="the_first_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="the_first_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="promised_respite_kills",
                label="Enemies killed",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="promised_respite_kills",
                label="Enemies killed",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
    },
    "Abandoned and Forgotten|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="abandoned_and_forgotten_face_down_traps",
                label="Face down trap tokens",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="abandoned_and_forgotten_face_down_traps",
                label="Face down trap tokens",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
    },
    "Trecherous Tower|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="trecherous_tower_face_down_traps",
                label="Face down trap tokens",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="trecherous_tower_face_down_traps",
                label="Face down trap tokens",
                kind="counter",
                template="",
                min_value=0,
                max_value=None,
                phase="player",
            ),
        ],
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="central_plaza_tiles_cleared",
                label="Tiles cleared of enemies",
                kind="counter",
                template="",
                min_value=0,
                max_value=3,
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="central_plaza_tiles_cleared",
                label="Tiles cleared of enemies",
                kind="counter",
                template="",
                min_value=0,
                max_value=3,
                phase="player",
            ),
        ],
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="corrupted_hovel_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Gnashing Beaks|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="gnashing_beaks_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
            EncounterTrigger(
                id="gnashing_beaks_chest",
                label="Chest opened",
                effect_template="Spawn a {enemy_list:4,5} on enemy spawn 1 on tile 1, and a {enemy6} on enemy spawn 2 on tile 1.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="distant_tower_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="cold_snap_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="corvian_host_spawn",
                label="",
                template="Kill {enemy_list:3,3}.",
                effect_template="Spawn a {enemy7} on both enemy spawn nodes on tile 3.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Eye of the Storm|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="eye_of_the_storm_spawn",
                label="",
                template="Kill {enemy_list:1,2,3,4}.",
                effect_template="Spawn a {enemy6} on both enemy spawn nodes on tile 3.",
                kind="checkbox",
                phase="player",
            ),
        ],
        "edited": [
            EncounterTrigger(
                id="eye_of_the_storm_spawn",
                label="",
                template="Kill {enemy_list:1,2,3,4}.",
                effect_template="Spawn a {enemy6} on both enemy spawn nodes on tile 3.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Frozen Revolutions|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="frozen_revolutions_trial",
                label="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "The Last Bastion|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "Broken Passageway|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="broken_passageway_kills",
                label="Enemies killed",
                kind="counter",
                phase="player",
            ),
        ],
    },
    "Kingdom's Messengers|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="kingdoms_messengers_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
    "|The Sunless City": {
        "default": [
            EncounterTrigger(
                id="the_last_bastion_trial",
                label="",
                template="Trial complete.",
                kind="checkbox",
                phase="player",
            ),
        ],
    },
}

EVENT_TRIGGERS: EventTriggersMap = {
    "Blacksmith's Trial": [
        EncounterTrigger(
            id="blacksmiths_trial",
            label="",
            template="Blacksmith's Trial event: Reroll an attack or defense roll.",
            kind="checkbox",
            phase="player",
        ),
    ],
    "Fleeting Glory": [
        EncounterTrigger(
            id="fleeting_glory",
            label="",
            template="Fleeting Glory event: If a character would die, instead clear the endurance bar.",
            kind="checkbox",
            phase="player",
        ),
    ],
    "Princess Guard": [
        EncounterTrigger(
            id="fleeting_glory",
            label="",
            template="Princess Guard event: If a character is attacked and would die, ignore the attack.",
            kind="checkbox",
            phase="player",
        ),
    ],
}
