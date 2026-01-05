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

    def render(self, enemy_pattern, players_plus_pattern, *, enemy_names: List[str], player_count: Optional[int] = None) -> str:
        def _sub_enemy(match: re.Match) -> str:
            idx_1_based = int(match.group(1))
            idx = idx_1_based - 1
            if 0 <= idx < len(enemy_names):
                return enemy_names[idx]
            return f"[enemy{idx_1_based}?]"

        text = enemy_pattern.sub(_sub_enemy, self.template)

        if player_count is not None:
            def _sub_players_plus(m: re.Match) -> str:
                offset = int(m.group(1))
                return str(player_count + offset)

            text = players_plus_pattern.sub(_sub_players_plus, text)
            text = text.replace("{players}", str(player_count))

        return text


# Mapping:
# outer key   -> encounter identifier (e.g. 'Cloak and Feathers|Painted World of Ariamis')
# inner key   -> variant: 'default' (non-edited) or 'edited'
# list value  -> EncounterRule definitions for that variant
EncounterRulesMap = Dict[str, Dict[str, List[EncounterRule]]]

EventRulesMap = Dict[str, List[EncounterRule]]


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
            )
        ],
        "edited": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
            ),
            EncounterRule(
                template="Snowstorm (tile 1 only): At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold (tile 1 only): If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
            )
        ],
    },
    "Frozen Sentries|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            )
        ],
    },
    "Painted Passage|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            )
        ],
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            )
        ],
        "edited": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
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
            )
        ],
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
            )
        ],
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Poison Mist: If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
            )
        ],
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Barrage: At the end of each character's turn, that character must make a defense roll using only their dodge dice. If no dodge symbols are rolled, the character suffers 2 damage and Stagger.",
            )
        ],
    },
    "Inhospitable Ground|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            )
        ],
        "edited": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
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
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
            ),
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attack only has a single die already, ignore this rule.",
            ),
        ],
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Barrage: At the end of each character's turn, that character must make a defense roll using only their dodge dice. If no dodge symbols are rolled, the character suffers 2 damage and Stagger.",
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
            ),
            EncounterRule(
                template="Characters can only leave a tile if there are no {enemy1_plural} on it.",
                phase="player"
            ),
        ],
    },
    "Deathly Freeze|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
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
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attack only has a single die already, ignore this rule.",
            ),
            EncounterRule(
                template="Characters can only leave a tile if there are no enemies on it.",
                phase="player"
            ),
        ],
        "edited": [
            EncounterRule(
                template="Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attack only has a single die already, ignore this rule.",
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
                template="Once {enemy_list:1,2,3,4} have been killed, spawn a {enemy6} on enemy spawn node 2 on tile 3.",
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
                template="{enemy7_plural} ignore barrels during movement.",
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
                template="{enemy7_plural} ignore barrels during movement.",
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
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
            ),
        ],
    },
    "Trecherous Tower|Painted World of Ariamis": {
        "default": [
            EncounterRule(
                template="Snowstorm: At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
            ),
            EncounterRule(
                template="Bitter Cold: If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
            ),
        ],
    },
    "Aged Sentinel|The Sunless City": {
        "default": [
            EncounterRule(
                template="The enemy skips its starting turn.",
                phase="enemy",
                timer_eq=0
            ),
        ],
    },
    "Broken Passageway|The Sunless City": {
        "default": [
            EncounterRule(
                template="Respawn all enemies.",
                phase="enemy",
                timer_eq=2
            ),
            EncounterRule(
                template="Respawn all enemies.",
                phase="enemy",
                timer_eq=4
            ),
        ],
    },
    "Dark Alleyway|The Sunless City": {
        "default": [
            EncounterRule(
                template="Reduce the node model limit to two.",
            ),
        ],
    },
    "Illusionary Doorway|The Sunless City": {
        "default": [
            EncounterRule(
                template="Illusion: If a character moves onto a node with a token, flip the token. If the token has a damage value, resolve the effects normally. If the token is the doorway/blank, discard all face down trap tokens, and place the next sequential tile as shown on the encounter card. Then, place the character on a doorway node on the new tile. Once a doorway token has been revealed, it counts as the doorway node that connects to the next sequential tile.",
            ),
        ],
    },
    "Undead Sanctum|The Sunless City": {
        "default": [
            EncounterRule(
                template="Onslaught: Each tile begins the encounter as active (all enemies on active tiles act on their turn).",
                timer_eq=0
            ),
        ],
    },
    "Deathly Tolls|The Sunless City": {
        "default": [
            EncounterRule(
                template="Onslaught: Each tile begins the encounter as active (all enemies on active tiles act on their turn).",
                timer_eq=0
            ),
            EncounterRule(
                template="Mimic ({enemy8}): If a character opens a chest in this encounter, shuffle the chest deck and draw a card. If a blank card is drawn, resolve the chest rules as normal. If the teeth card is drawn, replace the chest with a {enemy8} model instead. The chest deck contains three blank cards and two teeth cards. You can simulate this with trap tokens also - shuffle three blank trap tokens and two trap tokens with a value.",
            )
        ],
    },
    "Flooded Fortress|The Sunless City": {
        "default": [
            EncounterRule(
                template="Characters must spend 1 stamina if they make their normal movement during their turn. Running is unaffected.",
                phase="player"
            ),
        ],
    },
    "Gleaming Silver|The Sunless City": {
        "default": [
            EncounterRule(
                template="Mimic: If a character opens a chest in this encounter, shuffle the chest deck and draw a card. If a blank card is drawn, resolve the chest rules as normal. If the teeth card is drawn, replace the chest with the listed model instead. The chest deck contains three blank cards and two teeth cards. You can simulate this with trap tokens also - shuffle three blank trap tokens and two trap tokens with a value.",
            )
        ],
    },
}

# Event-level rules.
# These use the same EncounterRule dataclass, but are keyed directly
# by a string that should match either the event's id or its printed name.
EVENT_RULES: EventRulesMap = {
    "Alluring Skull": [
        EncounterRule(
            template="Alluring Skull event: The character with Alluring Skull gets +1 dodge.",
            phase="player",
        ),
    ],
    "Green Blossom": [
        EncounterRule(
            template="Green Blossom event: The character with Green Blossom can move any number of nodes without spending stamina.",
            phase="player",
        ),
    ],
    "Lifegem": [
        EncounterRule(
            template="Lifegem event: The character with Lifegem heals 1 damage at the start of their turn.",
            phase="player",
        ),
    ],
    "Pine Resin": [
        EncounterRule(
            template="Pine Resin event: The character with Pine Resin adds +1 to their damage total.",
            phase="player",
        ),
    ],
    "Repair Powder": [
        EncounterRule(
            template="Repair Powder event: The character with Repair Powder reduces damage taken from enemy attacks by 1.",
            phase="player",
        ),
    ],
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


def get_rules_for_event(
    *,
    event_key: str,
    timer: int,
    phase: str,
) -> List[EncounterRule]:
    """
    Return the rules that apply *right now* for a given event.

    `event_key` should match the key used in EVENT_RULES (usually the event's
    id, but you can also use the printed name).
    """
    rules = EVENT_RULES.get(event_key, [])
    return [r for r in rules if r.matches(timer=timer, phase=phase)]


def get_upcoming_rules_for_event(
    *,
    event_key: str,
    current_timer: int,
    max_lookahead: int = 3,
) -> List[tuple[int, EncounterRule]]:
    """
    Return (timer_value, rule) pairs for EVENT_RULES entries that will become
    active within the next `max_lookahead` timer steps.

    Mirrors get_upcoming_rules_for_encounter but on a per-event basis.
    """
    rules = EVENT_RULES.get(event_key, [])
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

    upcoming.sort(key=lambda pair: pair[0])
    return upcoming
