# core/encounter_triggers.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Dict, List
import re

Phase = Literal["enemy", "player", "any"]
TriggerKind = Literal["checkbox", "counter", "numeric", "timer_objective"]


@dataclass(frozen=True)
class EncounterTrigger:
    id: str

    # Short text for the widget ("Chest opened", "Lever", "Trial", etc.)
    label: str

    # What kind of control this is
    kind: TriggerKind  # "checkbox" | "counter" | "numeric" | "timer_objective"

    # Optional status text (can contain {value}, {enemy1}, etc.) shown next to/under label
    template: Optional[str] = None

    # Optional one-shot effect text shown when the trigger fires
    # (e.g. "Spawn a {enemy4} and a {enemy5} on ...")
    effect_template: Optional[str] = None

    phase: Phase = "any"
    min_value: int = 0
    max_value: Optional[int] = None
    default_value: Optional[int | bool] = None
    timer_target: Optional[int] = None
    stop_on_complete: bool = False


EncounterTriggersMap = Dict[str, List[EncounterTrigger]]


# Simple helper to reuse the {enemyN} placeholder pattern from rules.
_ENEMY_PATTERN = re.compile(r"{enemy(\d+)}")


def render_trigger_template(
    template: str,
    enemy_names: List[str],
    value: Optional[int] = None,
) -> str:
    """Render a trigger template with {enemyN} and optional {value}."""

    def _sub_enemy(match: re.Match) -> str:
        idx_1_based = int(match.group(1))
        idx = idx_1_based - 1
        if 0 <= idx < len(enemy_names):
            return enemy_names[idx]
        return f"[enemy{idx_1_based}?]"

    text = _ENEMY_PATTERN.sub(_sub_enemy, template)
    if value is not None:
        text = text.replace("{value}", str(value))
    return text


ENCOUNTER_TRIGGERS: EncounterTriggersMap = {
    "Gnashing Beaks|Painted World of Ariamis": [
        EncounterTrigger(
            id="gnashing_beaks_chest",
            template="Chest opened: Spawn a {enemy4} and a {enemy5} on enemy spawn 1 on tile 1, and a {enemy6} on enemy spawn 2 on tile 1.",
            kind="checkbox",
            phase="player",
        ),
    ],
    # ---------- EXAMPLES ONLY: you’ll fill out the real data ----------
    "The First Bastion|Painted World of Ariamis": [
        # Lever: activate 3 times, spawn {enemy1} each time
        EncounterTrigger(
            id="lever_activations",
            template="Lever activations: {value}/3 (each time, spawn a {enemy1} on spawn node 1).",
            kind="counter",
            min_value=0,
            max_value=3,
            default_value=0,
            phase="player",
        ),
        # Optional bonus objective / trial
        EncounterTrigger(
            id="trial",
            template="Trial: Clear tile 2 of enemies before Timer reaches 4.",
            kind="checkbox",
            phase="player",
        ),
        # Timer-based main objective
        EncounterTrigger(
            id="survive_until_timer_6",
            template="Objective: Survive until Timer reaches 6.",
            kind="timer_objective",
            timer_target=6,
            stop_on_complete=True,  # can use this to disable Next Turn
        ),
    ],

    "Corvian Host|Painted World of Ariamis": [
        EncounterTrigger(
            id="tile_made_active",
            template="Tile was made active (reset the Timer to 0 when this happens).",
            kind="checkbox",
            phase="player",
        ),
    ],

    "Frozen Revolutions|Painted World of Ariamis": [
        # Barrels per tile → affect enemy block/resist
        EncounterTrigger(
            id="barrels_tile1",
            template="Barrels on tile 1: {value}",
            kind="numeric",
            min_value=0,
            max_value=2,
            default_value=0,
            phase="any",
        ),
        EncounterTrigger(
            id="barrels_tile2",
            template="Barrels on tile 2: {value}",
            kind="numeric",
            min_value=0,
            max_value=2,
            default_value=0,
            phase="any",
        ),
        # Trial checkbox (for later rewards)
        EncounterTrigger(
            id="trial",
            template="Trial: Destroy all barrels before Timer reaches 4.",
            kind="checkbox",
            phase="player",
        ),
    ],
    # etc...
}
