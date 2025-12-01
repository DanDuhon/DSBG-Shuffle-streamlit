# core/encounter_triggers.py
from __future__ import annotations

import re
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


def render_trigger_template(
    template: str,
    enemy_pattern,
    players_plus_pattern,
    enemy_names: List[str],
    value: Optional[int] = None,
    player_count: Optional[int] = None,
) -> str:
    """Render a trigger template with {enemyN}, {players}, {players+N}, and optional {value}."""

    def _sub_enemy(match: re.Match) -> str:
        idx_1_based = int(match.group(1))
        idx = idx_1_based - 1
        if 0 <= idx < len(enemy_names):
            return enemy_names[idx]
        return f"[enemy{idx_1_based}?]"

    text = enemy_pattern.sub(_sub_enemy, template)

    if player_count is not None:
        def _sub_players_plus(m: re.Match) -> str:
            offset = int(m.group(1))
            return str(player_count + offset)

        # {players+3}, {players+1}, etc.
        text = players_plus_pattern.sub(_sub_players_plus, text)

        # plain {players}
        text = text.replace("{players}", str(player_count))

    if value is not None:
        text = text.replace("{value}", str(value))

    return text


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


ENCOUNTER_TRIGGERS: EncounterTriggersMap = {
    "The First Bastion|Painted World of Ariamis": {
        "default": [
            EncounterTrigger(
                id="the_first_bastion_lever",
                label="Lever activations",
                kind="counter",
                template="{value}/3",
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
}
