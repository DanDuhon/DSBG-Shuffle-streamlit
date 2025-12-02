# core/encounter_rewards.py

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict, Literal

from core.encounter_rules import make_encounter_key


RewardType = Literal[
    "souls",
    "treasure",
    "event",
    "refresh",
    "shortcut",
    "search",
    "text",
]


class RewardConfig(TypedDict, total=False):
    # What this reward does
    type: RewardType

    # Generic numeric pieces
    flat: int
    per_player: int
    per_counter: int
    per_player_per_counter: int

    # Link to encounter triggers
    counter_trigger_id: str      # for counters / kill-tracking, etc.
    trial_trigger_id: str        # for trial-completion checkboxes

    # Refresh-specific
    refresh_resource: Literal["heroic", "luck", "estus"]

    # Optional human-readable text template
    text: str


class ModifierConfig(TypedDict, total=False):
    # e.g. double total souls if a trigger is met
    type: Literal["souls_multiplier"]
    multiplier: int
    trigger_id: str
    text: str


class EncounterRewardsConfig(TypedDict, total=False):
    rewards: List[RewardConfig]
    trial_rewards: List[RewardConfig]
    modifiers: List[ModifierConfig]


# outer key: "<encounter_name>|<expansion>"
# inner key: "default" / "edited"
ENCOUNTER_REWARDS: Dict[str, Dict[str, EncounterRewardsConfig]] = {
    "The First Bastion|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "flat": 3,
                    "trial_trigger_id": "the_first_bastion_trial",
                },
            ],
        },
    },
    "No Safe Haven|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "Frozen Sentries|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 1,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "refresh",
                    "refresh_resource": "estus",
                    "per_player": 1,
                },
            ],
        },
    },
    "Skittering Frenzy|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 4,
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
            ],
        },
    },
    "Roll Out|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
            ],
        },
    },
    "Unseen Scurrying|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "Cloak and Feathers|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                },
                {
                    "type": "shortcut"
                }
            ],
        },
    },
    "Painted Passage|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "search",
                }
            ],
        },
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 2,
                    "counter_trigger_id": "promised_respite_kills"
                },
                {
                    "type": "search",
                }
            ],
        },
    },
    "Inhospitable Ground|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3
                },
                {
                    "type": "search",
                },
                {
                    "type": "shortcut",
                }
            ],
        },
    },
    "Gnashing Beaks|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut",
                }
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "flat": 4,
                    "trial_trigger_id": "gnashing_beaks_trial",
                },
            ],
        },
    },
    "The Last Bastion|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 6
                },
                {
                    "type": "refresh",
                    "refresh_resource": "estus",
                    "per_player": 1,
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
            "trial_rewards": [
                {
                    "type": "treasure",
                    "flat": 3,
                    "trial_trigger_id": "the_last_bastion_trial",
                },
            ],
        },
    },
    "Frozen Revolutions|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 8
                },
                {
                    "type": "treasure",
                    "flat": 3
                }
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "frozen_revolutions_trial",
                },
            ],
        },
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
            "trial_rewards": [
                {
                    "type": "treasure",
                    "flat": 2,
                    "trial_trigger_id": "corrupted_hovel_trial",
                },
            ],
        },
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                }
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "distant_tower_trial",
                },
            ],
        },
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4
                },
                {
                    "type": "event",
                    "flat": 1
                },
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "cold_snap_trial",
                },
            ],
        },
    },
    "Skeletal Spokes|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3
                },
                {
                    "type": "event",
                    "flat": 1
                },
            ],
        },
    },
    "Snowblind|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                },
                {
                    "type": "search",
                },
            ],
        },
    },
    "Abandoned and Forgotten|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "abandoned_and_forgotten_face_down_traps"
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "shortcut",
                },
            ],
        },
    },
    "Monstrous Maw|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 6
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "search",
                },
            ],
        },
    },
    "Velka's Chosen|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 8
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
                {
                    "type": "search",
                },
            ],
        },
    },
    "Deathly Freeze|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 10
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
                {
                    "type": "search",
                },
            ],
        },
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 6,
                    "counter_trigger_id": "central_plaza_tiles_cleared"
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut",
                },
            ],
        },
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 8
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "search",
                },
            ],
        },
    },
    "Trecherous Tower|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "per_player_per_counter": 1,
                    "counter_trigger_id": "trecherous_tower_face_down_traps"
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "shortcut",
                },
            ],
        },
    },
    "Eye of the Storm|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 6,
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                },
            ],
        },
    },
    "Draconic Decay|Painted World of Ariamis": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 10,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
                {
                    "type": "event",
                    "flat": 1
                },
            ],
        },
    },
}


def get_reward_config_for_key(
    encounter_key: str,
    *,
    edited: bool = False,
) -> Optional[EncounterRewardsConfig]:
    """
    Return the rewards config for a given encounter key, or None if not defined.
    """
    variants = ENCOUNTER_REWARDS.get(encounter_key)
    if not variants:
        return None

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default")


def get_reward_config_for_encounter(
    encounter: dict,
    *,
    edited: bool = False,
) -> Optional[EncounterRewardsConfig]:
    """
    Convenience wrapper that builds the encounter key from an encounter dict.
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    return get_reward_config_for_key(encounter_key, edited=edited)
