# core/encounter_rewards.py

from __future__ import annotations
from typing import Dict, List, Optional
from core.encounter_rules import make_encounter_key  # same helper as elsewhere :contentReference[oaicite:7]{index=7}

# EncounterRewardsConfig is a plain dict so it stays JSON-shaped:
# {
#   "rewards": [RewardObject, ...],
#   "trial_rewards": [RewardObject, ...],  # trial rewards will usually have trial_trigger_id set
# }

EncounterRewardsConfig = Dict[str, List[dict]]

# outer key: "<encounter_name>|<expansion>"
# inner key: "default" / "edited"
ENCOUNTER_REWARDS: Dict[str, Dict[str, EncounterRewardsConfig]] = {
    # --- EXAMPLE ONLY; numbers are placeholders ---
    "The First Bastion|Painted World of Ariamis": {
        "default": {
            # Always granted when you clear the encounter
            "rewards": [
                {
                    "type": "souls",
                    # 2 souls per character
                    "per_player": 2,
                    "text": "{players}×2 souls (base reward)",
                },
                {
                    "type": "treasure",
                    "flat": 1,
                    "text": "Draw 1 treasure card.",
                },
            ],

            # Extra rewards if the Trial checkbox is ticked
            "trial_rewards": [
                {
                    "type": "souls",
                    "per_player": 1,
                    "trial_trigger_id": "the_first_bastion_trial",
                    "text": "Trial reward: +{players} souls.",
                },
                {
                    "type": "treasure",
                    "flat": 1,
                    "trial_trigger_id": "the_first_bastion_trial",
                    "text": "Trial reward: draw 1 additional treasure card.",
                },
            ],
        },

        # Optional edited variant if the reward table changes for edited mode
        "edited": {
            "rewards": [
                {
                    "type": "souls",
                    "per_player": 3,
                    "text": "{players}×3 souls (edited encounter).",
                },
            ],
            "trial_rewards": [
                # etc.
            ],
        },
    },
}


def get_reward_config_for_key(
    encounter_key: str,
    *,
    edited: bool = False,
) -> Optional[EncounterRewardsConfig]:
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
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    return get_reward_config_for_key(encounter_key, edited=edited)
