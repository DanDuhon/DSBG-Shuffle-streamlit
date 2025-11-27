# core/encounter_rules.py
import re
from dataclasses import dataclass
from typing import Literal, Optional, Dict, List


Phase = Literal["enemy", "player", "any"]


@dataclass(frozen=True)
class EncounterRule:
    """
    A single text rule for an encounter.

    template:
        Text that may contain placeholders like `{enemy1}`, `{enemy2}`, etc.
        The number is 1-based and refers to the corresponding enemy in the
        encounter's shuffled enemy list.

    phase:
        "enemy", "player", or "any" (always shown regardless of phase).

    timer_min / timer_max:
        Inclusive bounds for the Timer counter, if set.

    timer_eq:
        Show only when Timer is exactly this value.
    """

    template: str
    phase: Phase = "any"
    timer_min: Optional[int] = None
    timer_max: Optional[int] = None
    timer_eq: Optional[int] = None

    def matches(self, *, timer: int, phase: str) -> bool:
        """Return True if this rule should be shown for the given state."""
        if self.phase != "any" and self.phase != phase:
            return False

        if self.timer_eq is not None and timer != self.timer_eq:
            return False

        if self.timer_min is not None and timer < self.timer_min:
            return False

        if self.timer_max is not None and timer > self.timer_max:
            return False

        return True

    def render(self, *, enemy_names: List[str]) -> str:
        """
        Render template with dynamic pieces substituted.

        Supported placeholders:
          - {enemy1}, {enemy2}, ...  (1-based indices into enemy_names)
        """

        def _sub_enemy(match: re.Match) -> str:
            idx_1_based = int(match.group(1))
            idx = idx_1_based - 1
            if 0 <= idx < len(enemy_names):
                return enemy_names[idx]
            # Fallback: leave something obvious if lookup fails
            return f"[enemy{idx_1_based}?]"

        text = _ENEMY_PATTERN.sub(_sub_enemy, self.template)
        return text


_ENEMY_PATTERN = re.compile(r"{enemy(\d+)}")


# Mapping:
# outer key   -> encounter identifier (e.g. 'Cloak and Feathers|Painted World of Ariamis')
# inner key   -> variant: 'default' (non-edited) or 'edited'
# list value  -> EncounterRule definitions for that variant
EncounterRulesMap = Dict[str, Dict[str, List[EncounterRule]]]


ENCOUNTER_RULES: EncounterRulesMap = {
    "Cloak and Feathers|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Character attacks cost +1 stamina.",
                phase="player"
            )
        ],
    },
    "No Safe Haven|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
                phase="player"
            )
        ],
        "edited": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
                phase="player"
            ),
            EncounterRule(
                template="Snowstorm (tile 1 only): At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold (tile 1 only): If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            )
        ],
    },
    "Frozen Sentries|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            )
        ],
    },
    "Painted Passage|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            )
        ],
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            )
        ],
        "edited": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            )
        ],
    },
    "Roll Out|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Enemies ignore barrels during movement.",
                phase="enemy"
            ),
            EncounterRule(
                template="If an enemy is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
                phase="player"
            )
        ],
    },
    "Skittering Frenzy|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="If an enemy is killed, respawn it on the closest enemy spawn node to the character with the aggro token at the end of the next enemy turn.",
                phase="player"
            )
        ],
    },
    "The First Bastion|Painted World of Ariamis": {
        "edited": [
            EncounterRule(
                template="Spawn a {enemy2} on enemy spawn node 1.",
                phase="enemy",
                timer_eq=1
            ),
            EncounterRule(
                template="Spawn a {enemy3} on enemy spawn node 1.",
                phase="enemy",
                timer_eq=2
            ),
            EncounterRule(
                template="Spawn a {enemy4} on enemy spawn node 1.",
                phase="enemy",
                timer_eq=4
            )
        ],
    },
    "Unseen Scurrying|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attack only has a single die already, ignore this rule.",
                phase="player"
            )
        ],
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            )
        ],
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
                phase="player"
            )
        ],
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Barrage: At the end of each character's turn, that character must make a defense roll using only their dodge dice.\n\nIf no dodge symbols are rolled, the character suffers 2 damage and Stagger.",
                phase="player"
            )
        ],
    },
    "Inhospitable Ground|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            )
        ],
        "edited": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            )
        ],
    },
    "Skeletal Spokes|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Enemies ignore barrels during movement.",
                phase="enemy"
            ),
            EncounterRule(
                template="If {enemy3} is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
                phase="player"
            ),
            EncounterRule(
                template="If {enemy3} is killed, respawn it on the closest enemy node, then draw a treasure card and add it to the inventory.",
                phase="player"
            )
        ],
    },
    "Snowblind|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            ),
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attack only has a single die already, ignore this rule.",
                phase="player"
            ),
        ],
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Barrage: At the end of each character's turn, that character must make a defense roll using only their dodge dice.\n\nIf no dodge symbols are rolled, the character suffers 2 damage and Stagger.",
                phase="player"
            ),
            EncounterRule(
                template="Characters can only leave a tile if there are no enemies on it.",
                phase="player"
            )
        ],
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
                phase="player"
            ),
            EncounterRule(
                template="When a tile is made active, reset the Timer.",
                phase="player"
            ),
            EncounterRule(
                template="Characters can only leave a tile if there are no {enemy1}s on it.",
                phase="player"
            ),
            EncounterRule(
                template="When all {enemy3}s have been killed on tiles 1 and 2, spawn a {enemy3} on both enemy spawn nodes on tile 3.",
                phase="player"
            ),
        ],
    },
    "Deathly Freeze|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            ),
        ],
    },
    "Draconic Decay|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="At the end of each enemy turn, place 3 poison mist tokens on the lowest numbered tile.",
                phase="enemy"
            ),
            EncounterRule(
                template="When placing tokens, if every node on a tile has a poison mist token on it, remove the tile from play, then place any remaining tokens on the next lowest tile. Any models on the tile when it is removed are killed.",
                phase="enemy"
            ),
        ],
    },
    "Eye of the Storm|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling.\n\nIf the attack only has a single die already, ignore this rule.",
                phase="player"
            ),
            EncounterRule(
                template="Characters can only leave a tile if there are no enemies on it.",
                phase="player"
            ),
        ],
        "edited": [
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling.\n\nIf the attack only has a single die already, ignore this rule.",
                phase="player"
            ),
            EncounterRule(
                template="Respawn all enemies.",
                timer_eq=3,
                phase="enemy"
            ),
            EncounterRule(
                template="The Timer only increases at the end of a character's turn if there are no enemies on active tiles.",
                phase="player"
            ),
            EncounterRule(
                template="Once all {enemy1}s have been killed, spawn the {enemy6} on enemy spawn node 2 on tile 3.",
                phase="player"
            ),
        ],
    },
    "Frozen Revolutions|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Reduce the node model limit to two.",
            ),
            EncounterRule(
                template="{enemy7}s ignore barrels during movement.",
                phase="enemy"
            ),
            EncounterRule(
                template="If a {enemy7} is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
                phase="player"
            ),
        ],
        "edited": [
            EncounterRule(
                template="Reduce the node model limit to two.",
            ),
            EncounterRule(
                template="{enemy7}s ignore barrels during movement.",
                phase="enemy"
            ),
            EncounterRule(
                template="If a {enemy7} is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
                phase="player"
            ),
            EncounterRule(
                template="If a {enemy7} is killed, it respawns on enemy spawn node 1 on tile 3.",
                phase="player"
            ),
        ],
    },
    "The Last Bastion|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            ),
        ],
    },
    "Trecherous Tower|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
                phase="player"
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
                phase="player"
            ),
        ],
    },
    # Example only; fill with real data as needed.
    #
    # "Cloak and Feathers|Core Set": {
    #     "default": [
    #         # Always visible, any phase / timer
    #         EncounterRule(
    #             template="TODO: Always-on rule text for Cloak and Feathers.",
    #         ),
    #         # Enemy phase, timer >= 2
    #         EncounterRule(
    #             template="TODO: Enemy-phase rule once the Timer is 2 or more.",
    #             phase="enemy",
    #             timer_min=2,
    #         ),
    #     ],
    #     "edited": [
    #         # Edited-only rule at Timer == 3 (enemy phase only)
    #         EncounterRule(
    #             template="TODO: Edited variant rule at Timer 3.",
    #             phase="enemy",
    #             timer_eq=3,
    #         ),
    #     ],
    # },
}


def make_encounter_key(*, name: str, expansion: str) -> str:
    """Helper to build a stable key for ENCOUNTER_RULES."""
    return f"{name}|{expansion}"


def get_rules_for_encounter(
    *,
    encounter_key: str,
    edited: bool,
    timer: int,
    phase: str,
) -> List[EncounterRule]:
    """
    Return the rules that apply *right now* for a given encounter.

    - If an 'edited' ruleset exists and `edited` is True, it is used.
    - Otherwise, the 'default' ruleset (non-edited) is used.
    - Within that variant, rules are filtered by timer and phase.
    """
    variants = ENCOUNTER_RULES.get(encounter_key)
    if not variants:
        return []

    # Choose the correct variant based on toggle + availability
    if edited and "edited" in variants:
        rules = variants["edited"]
    else:
        rules = variants.get("default", [])

    return [r for r in rules if r.matches(timer=timer, phase=phase)]


def get_upcoming_rules_for_encounter(
    *,
    encounter_key: str,
    edited: bool,
    current_timer: int,
    max_lookahead: int = 3,
) -> List[tuple[int, EncounterRule]]:
    """
    Return (trigger_timer, rule) pairs for rules that will become active
    in the next few timer steps.

    - Only looks at the chosen variant (default vs edited).
    - Only considers rules with timer_eq or timer_min > current_timer.
    - Does not filter by phase here; phase is still indicated by rule.phase.
    """
    variants = ENCOUNTER_RULES.get(encounter_key)
    if not variants:
        return []

    # Pick variant the same way as get_rules_for_encounter
    if edited and "edited" in variants:
        rules = variants["edited"]
    else:
        rules = variants.get("default", [])

    upcoming: list[tuple[int, EncounterRule]] = []

    for r in rules:
        trigger_timer: Optional[int] = None

        if r.timer_eq is not None:
            if current_timer < r.timer_eq <= current_timer + max_lookahead:
                trigger_timer = r.timer_eq

        elif r.timer_min is not None:
            # Rule becomes active at timer_min, if it's in the future window
            if current_timer < r.timer_min <= current_timer + max_lookahead:
                trigger_timer = r.timer_min

        # We ignore timer_max-only or always-on rules for "upcoming"
        if trigger_timer is not None:
            upcoming.append((trigger_timer, r))

    # Sort by when they will trigger
    upcoming.sort(key=lambda pair: pair[0])
    return upcoming
