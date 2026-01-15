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
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Painted Passage|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Roll Out|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Skittering Frenzy|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Survive for {players+2} turns.",
            ],
            "trials": [
            ],
        },
    },
    "The First Bastion|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Activate the lever three times. Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy4}."
            ],
        },
        "edited": {
            "objectives": [
                "Activate the lever three times. Reach the exit node.",
            ],
            "trials": [
                "Kill a {enemy4}."
            ],
        },
    },
    "Unseen Scurrying|Painted World of Ariamis": {
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
                "Reveal three blank trap tokens.",
            ],
            "trials": [
            ],
        },
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy4}."
            ],
        },
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies",
            ],
            "trials": [
                "Kill all enemies within {players+3} turns."
            ],
        },
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy6}."
            ],
        },
    },
    "Gnashing Beaks|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Open the chest. Reach the exit node.",
            ],
            "trials": [
                "Open the chest within {players+3} turns."
            ],
        },
    },
    "Inhospitable Ground|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Monstrous Maw|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "Skeletal Spokes|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Survive for {players+2} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Snowblind|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies on {players} tiles. Reach the exit node.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Kill all enemies on {players} tiles. Reach the exit node or kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Defeat all enemies within {players+5} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Deathly Freeze|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Draconic Decay|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Eye of the Storm|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy6}.",
            ],
            "trials": [
            ],
        },
    },
    "Frozen Revolutions|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Activate both levers. Reach the exit node.",
            ],
            "trials": [
                "No barrels are discarded."
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
    "Trecherous Tower|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reveal four blank trap tokens.",
            ],
            "trials": [
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
    "Aged Sentinel|The Sunless City": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
                "Use both gravestones."
            ],
        },
    },
    "Broken Passageway|The Sunless City": {
        "default": {
            "objectives": [
                "Survive for {players+2} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Dark Alleyway|The Sunless City": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "Illusionary Doorway|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Kingdom's Messengers|The Sunless City": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill all enemies."
            ],
        },
    },
    "Shattered Keep|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Tempting Maw|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies within {players+3} turns (the {enemy5} does not count as an enemy if the chest hasn't been opened).",
            ],
            "trials": [
                "Kill the {enemy5}."
            ],
        },
    },
    "The Bell Tower|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever {players+1} turns.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Activate the lever at least once. Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Undead Sanctum|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Deathly Tolls|The Sunless City": {
        "default": {
            "objectives": [
                "Survive for {players+3} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Flooded Fortress|The Sunless City": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill {players+2} enemies."
            ],
        },
        "edited": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy2} and {players} other enemies."
            ],
        },
    },
    "Gleaming Silver|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Complete the encounter within {players+3} turns."
            ],
        },
    },
    "Parish Church|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Flip all trap tokens."
            ],
        },
        "edited": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Open the chest."
            ],
        },
    },
    "Parish Gates|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever. Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "The Fountainhead|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "The Hellkite Bridge|The Sunless City": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "The Iron Golem|The Sunless City": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "The Shine of Gold|The Sunless City": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Archive Entrance|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Don't discard the lever token."
            ],
        },
    },
    "Castle Break In|The Sunless City": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Central Plaza|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever {players} times. Kill all enemies.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Kill all enemies {players} times.",
            ],
            "trials": [
            ],
        },
    },
    "Depths of the Cathedral|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies on a number of tiles equal to {players} (if there are four players, kill all enemies).",
            ],
            "trials": [
            ],
        },
    },
    "Grim Reunion|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever. Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy11}."
            ],
        },
        "edited": {
            "objectives": [
                "Activate the lever. Reach the exit node or kill all enemies.",
            ],
            "trials": [
                "Kill the {enemy11}."
            ],
        },
    },
    "Hanging Rafters|The Sunless City": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill {players+3} enemies."
            ],
        },
    },
    "The Grand Hall|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever.",
            ],
            "trials": [
                "Kill all enemies."
            ],
        },
    },
    "The Grand Hall|The Sunless City": {
        "default": {
            "objectives": [
                "Activate the lever.",
            ],
            "trials": [
                "Kill all enemies without flipping more than two trap tokens with values."
            ],
        },
    },
    "Trophy Room|The Sunless City": {
        "default": {
            "objectives": [
                "Kill {enemy_list:5,6}.",
            ],
            "trials": [
            ],
        },
    },
    "Twilight Falls|The Sunless City": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Abandoned Storeroom|Tomb of Giants": {
        "default": {
            "objectives": [
                "Break all barrels.",
            ],
            "trials": [
            ],
        },
    },
    "Bridge Too Far|Tomb of Giants": {
        "default": {
            "objectives": [
                "Activate the lever three times.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Activate the lever at least twice. Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Dark Resurrection|Tomb of Giants": {
        "default": {
            "objectives": [
                "Place the torch on the shrine node.",
            ],
            "trials": [
            ],
        },
    },
    "Deathly Magic|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Grave Matters|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Last Rites|Tomb of Giants": {
        "default": {
            "objectives": [
                "Survive for {players+2} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Puppet Master|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill the {enemy2}.",
            ],
            "trials": [
            ],
        },
    },
    "Rain of Filth|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "The Beast From the Depths|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "Altar of Bones|Tomb of Giants": {
        "default": {
            "objectives": [
                "Occupy the shrine for {players+2} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Far From the Sun|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "In Deep Water|Tomb of Giants": {
        "default": {
            "objectives": [
                "Survive for {players+3} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Lost Chapel|Tomb of Giants": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Maze of the Dead|Tomb of Giants": {
        "default": {
            "objectives": [
                "Activate all levers.",
            ],
            "trials": [
            ],
        },
    },
    "Pitch Black|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill {enemy_list:2,6}.",
            ],
            "trials": [
            ],
        },
    },
    "The Abandoned Chest|Tomb of Giants": {
        "default": {
            "objectives": [
                "Open the chest. Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "The Mass Grave|Tomb of Giants": {
        "default": {
            "objectives": [
                "Activate the lever. Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Urns of the Fallen|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "A Trusty Ally|Tomb of Giants": {
        "default": {
            "objectives": [
                "Survive for {players+4} turns.",
            ],
            "trials": [
            ],
        },
    },
    "Death's Precipice|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
        "edited": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Giant's Coffin|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Complete the encounter within 7 turns."
            ],
        },
    },
    "Honour Guard|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Lakeview Refuge|Tomb of Giants": {
        "default": {
            "objectives": [
                "Place the torch on the shrine node.",
            ],
            "trials": [
                "Kill the {enemy9}."
            ],
        },
    },
    "Last Shred of Light|Tomb of Giants": {
        "default": {
            "objectives": [
                "Activate the lever three times.",
            ],
            "trials": [
            ],
        },
    },
    "Skeleton Overlord|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "The Locked Grave|Tomb of Giants": {
        "default": {
            "objectives": [
                "Open all chests.",
            ],
            "trials": [
                "Kill the {enemy8}."
            ],
        },
    },
    "The Skeleton Ball|Tomb of Giants": {
        "default": {
            "objectives": [
                "Kill {enemy_list:1,6}.",
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
