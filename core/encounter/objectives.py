from __future__ import annotations
from typing import Optional


# ---------------------------------------------------------------------------
# Encounter Objectives data
# ---------------------------------------------------------------------------

ENCOUNTER_OBJECTIVES = {
    "Cloak and Feathers|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
        },
    },
    "Frozen Sentries|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "No Safe Haven|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Abandoned and Forgotten|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Activate the lever 3 times. All players must reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Buried in Bone|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3} and the {enemy4}.",
            ],
            "trials": [
            ],
        },
    },
    "Dead of Night|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}. The {enemy1} must be the last enemy on the board.",
            ],
            "trials": [
            ],
        },
    },
    "Defiled Altar|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy4}.",
            ],
            "trials": [
            ],
        },
    },
    "Through the Fog|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Beyond the Bridge|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}. The {enemy1} must be the last enemy on the board.",
            ],
            "trials": [
            ],
        },
    },
    "Avenge the Fallen|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy2}.",
            ],
            "trials": [
            ],
        },
    },
    "The Dregs of War|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "A Cold Reception|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Keep the {enemy2_plural} at least 3 nodes away from the {enemy1}. Kill all enemies.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Keep the {enemy2_plural} at least 3 nodes away from the {enemy1}. Kill all enemies.",
            ],
            "trials": [
                (
                    "Each time the {enemy1} moves closer to the {enemy2_plural}, "
                    "decrease the timer value by 1."
                ),
            ],
        },
    },
    "The Deep Dark|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Survive {players+1} rounds. Kill all enemies.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Survive {players+1} rounds. Kill all enemies.",
            ],
            "trials": [
                "The {enemy2} is immune to all damage unless the {enemy1} is at least 3 nodes away.",
            ],
        },
    },
    "Moonlit Vigil|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Forsaken Encampment|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Frozen Guardian|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Remnants of War|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Rotten Spire|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Spires of the Damned|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}. The {enemy3} must be the last enemy on the board.",
            ],
            "trials": [
            ],
        },
    },
    "The Frozen King|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "The Gauntlet|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "If a player starts their activation on a barrel, increase the timer by 1.",
            ],
        },
    },
    "The Hanging Cage|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "The Huddled Masses|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy2}.",
            ],
            "trials": [
            ],
        },
    },
    "The Last Bastion|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Kill the {enemy1} first."
            ],
        },
    },
    "Velka's Chosen|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
}


def get_objective_config_for_key(
    encounter_key: str,
    *,
    edited: bool = False,
) -> Optional[dict]:
    """
    Return the objective config dict for a given encounter key, or None if not defined.

    The config dict has shape:
        {
            "objectives": [template_str, ...],
            "trials": [template_str, ...],
        }

    If edited=True and an "edited" variant exists for this encounter, that
    variant is returned; otherwise the "default" variant is returned.
    """
    variants = ENCOUNTER_OBJECTIVES.get(encounter_key)
    if not variants:
        return None

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default")
