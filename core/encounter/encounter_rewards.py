# core/encounter_rewards.py

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict, Literal

from core.encounter.encounter_rules import make_encounter_key


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
    # Timer-based thresholds (optional): list of Timer values at which
    # a single respawn is considered to have occurred. Respawns are
    # counted cumulatively (e.g. Timer >= 6 => two respawns for
    # thresholds [3,6,9]).
    timer_thresholds: List[int]

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
                },
                {
                    "type": "shortcut",
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
    "Aged Sentinel|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "treasure",
                    "flat": 1
                }
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "aged_sentinel_trial",
                },
            ],
        },
    },
    "Broken Passageway|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "broken_passageway_kills"
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
        },
    },
    "Dark Alleyway|The Sunless City": {
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
                }
            ],
        },
    },
    "Illusionary Doorway|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
        },
    },
    "Kingdom's Messengers|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
                {
                    "type": "shortcut"
                }
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "flat": 3,
                    "trial_trigger_id": "kingdoms_messengers_trial",
                },
            ],
        },
    },
    "Shattered Keep|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 2,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "Tempting Maw|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                    "trial_trigger_id": "tempting_maw_trial",
                },
            ]
        },
    },
    "The Bell Tower|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "the_bell_tower_kills"
                },
                {
                    "type": "shortcut"
                }
            ],
        },
    },
    "Undead Sanctum|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "Deathly Tolls|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 2,
                },
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "deathly_tolls_kills"
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut"
                }
            ],
        },
    },
    "Flooded Fortress|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "flooded_fortress_trial",
                },
            ]
        },
    },
    "Gleaming Silver|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "abandoned_and_forgotten_flipped_trap"
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                }
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "trial_trigger_id": "flooded_fortress_trial",
                },
            ]
        },
    },
    "Parish Church|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 4,
                },
                {
                    "type": "search"
                }
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "flat": 4,
                },
            ]
        },
    },
    "Parish Gates|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "event",
                    "flat": 1
                }
            ],
        },
    },
    "The Fountainhead|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 5,
                },
                {
                    "type": "shortcut"
                }
            ],
        },
    },
    "The Hellkite Bridge|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "search"
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "The Iron Golem|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4,
                },
                {
                    "type": "search"
                },
                {
                    "type": "refresh",
                    "refresh_resource": "estus",
                    "per_player": 1,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                }
            ],
        },
    },
    "The Shine of Gold|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
                {
                    "type": "treasure",
                    "flat": 3
                }
            ],
        },
    },
    "Archive Entrance|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 3,
                },
                {
                    "type": "treasure",
                    "flat": 2
                }
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                    "trial_trigger_id": "archive_entrance_trial",
                },
            ]
        },
    },
    "Castle Break In|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 7,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "Central Plaza|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 8,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut"
                }
            ],
        },
    },
    "Depths of the Cathedral|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 5,
                    "counter_trigger_id": "depths_of_the_cathedral_tiles_cleared"
                },
                {
                    "type": "refresh",
                    "refresh_resource": "estus",
                    "per_player": 1,
                },
                {
                    "type": "treasure",
                    "flat": 1
                }
            ],
        },
    },
    "Grim Reunion|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 5,
                },
                {
                    "type": "shortcut"
                }
            ],
            "trial_rewards": [
                {
                    "type": "treasure",
                    "flat": 2,
                    "trial_trigger_id": "grim_reunion_trial",
                },
            ]
        },
    },
    "Hanging Rafters|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 6,
                },
                {
                    "type": "event",
                    "flat": 2
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "The Grand Hall|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 9,
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
                    "trial_trigger_id": "grim_reunion_trial",
                },
            ]
        },
    },
    "Trophy Room|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 10,
                },
                {
                    "type": "search"
                }
            ],
        },
    },
    "Twilight Falls|The Sunless City": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "shortcut"
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                },
            ],
        },
    },
    "Abandoned Storeroom|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
            ],
        },
    },
    "Bridge Too Far|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "bridge_too_far_kills"
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Dark Resurrection|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 1,
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "search"
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Deathly Magic|Tomb of Giants": {
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
    "Grave Matters|Tomb of Giants": {
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
    "Last Rites|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 4,
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
    "Puppet Master|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 1,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "heroic",
                    "per_player": 1,
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "Rain of Filth|Tomb of Giants": {
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
    "The Beast From the Depths|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 1,
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "the_beast_from_the_depths_trial",
                },
            ]
        },
    },
    "Altar of Bones|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4,
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
    "Far From the Sun|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 1,
                    "counter_trigger_id": "far_from_the_sun_kills"
                },
                {
                    "type": "treasure",
                    "flat": 1
                },
                {
                    "type": "event",
                    "flat": 2
                },
            ],
        },
    },
    "In Deep Water|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 8,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "Lost Chapel|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "event",
                    "flat": 2
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Maze of the Dead|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Pitch Black|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
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
    "The Abandoned Chest|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "The Mass Grave|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    # Souls: 1 per player + 2 per respawn
                    "per_player": 1,
                    "per_counter": 2,
                    # Use Timer thresholds instead of a manual counter.
                    "timer_thresholds": [3, 6, 9],
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Urns of the Fallen|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 2,
                },
                {
                    "type": "event",
                    "flat": 1
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "A Trusty Ally|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 4,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
            ],
        },
    },
    "Death's Precipice|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 8,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
                {
                    "type": "search"
                },
            ],
        },
    },
    "Giant's Coffin|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
                },
                {
                    "type": "event",
                    "flat": 1
                },
            ],
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "giants_coffin_trial",
                },
            ]
        },
    },
    "Honour Guard|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 5,
                },
                {
                    "type": "refresh",
                    "refresh_resource": "luck",
                    "per_player": 1,
                },
            ],
        },
    },
    "Lakeview Refuge|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 8,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
            ],
            "trial_rewards": [
                {
                    "type": "souls",
                    "flat": 6,
                    "trial_trigger_id": "lakeview_refuge_trial",
                },
            ]
        },
    },
    "Last Shred of Light|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "flat": 10,
                },
                {
                    "type": "treasure",
                    "flat": 2
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
    "Skeleton Overlord|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 3,
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
    "The Locked Grave|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_counter": 2,
                    "counter_trigger_id": "the_locked_grave_kills"
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
            "trial_rewards": [
                {
                    "type": "search",
                    "trial_trigger_id": "_trial",
                },
            ]
        },
    },
    "The Skeleton Ball|Tomb of Giants": {
        "default": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "flat": 8,
                },
                {
                    "type": "search"
                },
                {
                    "type": "shortcut"
                },
            ],
        },
    },
}

# Number of chests printed on each V1 encounter card.
# Key format matches make_encounter_key: "<encounter_name>|<expansion>".
V1_CHEST_COUNTS: Dict[str, int] = {
    "Broken Passageway|Dark Souls The Board Game": 1,
    "Dark Hollow|Dark Souls The Board Game": 1,
    "Forsaken Depths|Dark Souls The Board Game": 1,
    "Ghostly Keep|Dark Souls The Board Game": 1,
    "Hollow Cave|Dark Souls The Board Game": 1,
    "Unlighted Chamber|Dark Souls The Board Game": 1,
    "Burned Gardens|Dark Souls The Board Game": 1,
    "High Wall of Lothric|Dark Souls The Board Game": 1,
    "Lost Labyrinth|Dark Souls The Board Game": 1,
    "Empty Crypt|Dark Souls The Board Game": 1,
    "Lost Shrine|Dark Souls The Board Game": 1,
    "Pit of the Dead|Dark Souls The Board Game": 1,
    "Profane Shrine|Dark Souls The Board Game": 1,
    "Wretched Gardens|Dark Souls The Board Game": 1,
    "Fearful Woods|Darkroot": 1,
    "Wild Glades|Darkroot": 1,
    "Stone Hollow|Darkroot": 1,
    "Withered Thicket|Darkroot": 1,
    "Dark Woods|Darkroot": 1,
    "Hydra Lake|Darkroot": 1,
    "Halls of the Forsworn|Explorers": 1,
    "Unholy Tunnels|Explorers": 1,
    "Lost Grotto|Explorers": 1,
    "Gallery of the Hidden Warrior|Explorers": 1,
    "Charred Keep|Iron Keep": 1,
    "Furnace Room|Iron Keep": 1,
    "Searing Hallway|Iron Keep": 1,
    "Smouldering Labyrinth|Iron Keep": 1,
    "Castle Aflame|Iron Keep": 1,
    "Sweltering Sanctum|Iron Keep": 1,
    "Quiet Graveyard|Executioner's Chariot": 1,
    "Misty Burial Site|Executioner's Chariot": 1,
    "Desolace Cemetery|Executioner's Chariot": 1,
    "Gate of Peril|Executioner's Chariot": 1,
    "Huntsman's Copse|Executioner's Chariot": 1,
    "Undead Purgatory|Executioner's Chariot": 1,
    "Asylum's North Hall|Asylum Demon": 1,
    "Shattered Cell|Asylum Demon": 1,
    "Gough's Perch|Black Dragon Kalameet": 1,
    "Great Stone Bridge|Black Dragon Kalameet": 1,
    "Perilous Crossing|Black Dragon Kalameet": 1,
    "Darkened Chamber|Gaping Dragon": 1,
    "Outskirts of Blighttown|Gaping Dragon": 2,
    "Sewers of Lordran|Gaping Dragon": 1,
    "The Depths|Gaping Dragon": 1,
    "Dragon Shrine|Guardian Dragon": 1,
    "Manor Foregarden|Guardian Dragon": 1,
    "Research Library|Guardian Dragon": 1,
    "Scholar's Hall|Guardian Dragon": 1,
    "Shadow of the Abyss|Manus, Father of the Abyss": 1,
    "The Desecrated Grave|Manus, Father of the Abyss": 1,
    "Fortress Gates|Old Iron King": 1,
    "Ironhearth Hall|Old Iron King": 1,
    "Lava Path|Old Iron King": 1,
    "Cursed Cavern|The Four Kings": 1,
    "Edge of the Abyss|The Four Kings": 1,
    "Hall of Wraiths|The Four Kings": 1,
    "New Londo Ruins|The Four Kings": 1,
    "Forest of Fallen Giants|The Last Giant": 1,
    "The Petrified Fallen|The Last Giant": 1,
    "Guarded Path|Vordt of the Boreal Valley": 1,
    "The Dog's Domain|Vordt of the Boreal Valley": 1
}


def get_v1_reward_config_for_encounter(
    encounter: dict,
) -> EncounterRewardsConfig:
    """
    Generic reward formula for V1 encounter cards.

    - 2 souls per character
    - +2 treasure draws per chest printed on the encounter card

    Chest counts are looked up in V1_CHEST_COUNTS using the usual
    "<encounter_name>|<expansion>" key. Unknown encounters default
    to 0 chests.
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    chest_count = V1_CHEST_COUNTS.get(encounter_key, 0)

    rewards: List[RewardConfig] = [
        {
            "type": "souls",
            "per_player": 2,
        },
    ]

    if chest_count:
        rewards.append(
            {
                "type": "treasure",
                "flat": 2 * chest_count,
            }
        )

    return {"rewards": rewards}


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
