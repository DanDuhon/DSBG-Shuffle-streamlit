#ui/encounter_mode/logic.py
import streamlit as st
import re
import os
import json
from pathlib import Path
from io import BytesIO
from random import choice
from collections import defaultdict

from ui.encounter_mode.generation import generate_encounter_image, load_encounter, load_valid_sets, ENCOUNTER_DATA_DIR

INVADERS_PATH = Path("data/invaders.json")
HARD_MAX_INVADERS_BY_LEVEL = {
    1: 2,
    2: 3,
    3: 5,
    4: 4,
}
INVADER_LIMIT_SETTING_KEYS = (
    "max_invaders_per_level",            # preferred
    "max_invaders_by_level",             # tolerated alias
    "max_allowed_invaders_per_level",    # tolerated alias
)
ENCOUNTER_BEHAVIOR_MODIFIERS = {
    "Painted World of Ariamis_1_Frozen Sentries": [
        {
            "id": "pw_frozen_sentries_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Frozen Sentries",
            "target": "all_enemies",
            "stat": "push",
            "op": "flag",
            "value": True,
            "description": "Attacks gain push from special rules.",
        }
    ],
    "Painted World of Ariamis_1_Skittering Frenzy": [
        {
            "id": "pw_skittering_frenzy_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Skittering Frenzy",
            "target": "all_enemies",
            "stat": "armor",
            "op": "add",
            "value": 1,
            "description": "+1 block from special rules.",
        },
        {
            "id": "pw_skittering_frenzy_damage",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Skittering Frenzy",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 1,
            "description": "+1 damage from special rules.",
        },
        {
            "id": "pw_skittering_frenzy_respawn",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Skittering Frenzy",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "When an enemy is killed, respawn it on the closest enemy spawn node to the character with the aggro token at the end of the next enemy turn.",
        },
    ],
    "Painted World of Ariamis_1_Roll Out": [
        {
            "id": "pw_roll_out_barrels",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Roll Out",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Enemies ignore barrels during movement.",
        },
        {
            "id": "pw_roll_out_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Roll Out",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "If an enemy is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
        }
    ],
    "Painted World of Ariamis_1_Unseen Scurrying": [
        {
            "id": "pw_unseen_scurrying_hidden",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Unseen Scurrying",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attacks only has a single die already, ignore this rule.",
        }
    ],
    "Painted World of Ariamis_1_Cloak and Feathers": [
        {
            "id": "pw_cloak_and_feathers_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Cloak and Feathers",
            "target": "all_enemies",
            "stat": "armor",
            "op": "add",
            "value": -1,
            "description": "-1 block from special rules.",
        },
        {
            "id": "pw_cloak_and_feathers_resist",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Cloak and Feathers",
            "target": "all_enemies",
            "stat": "resist",
            "op": "add",
            "value": -1,
            "description": "-1 resist from special rules.",
        },
        {
            "id": "pw_cloak_and_feathers_dodge",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_1_Cloak and Feathers",
            "target": "all_enemies",
            "stat": "dodge_difficulty",
            "op": "add",
            "value": -1,
            "description": "-1 dodge difficulty from special rules.",
        }
    ],
    "Painted World of Ariamis_2_Inhospitable Ground": [
        {
            "id": "pw_inhospitable_ground_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Inhospitable Ground",
            "target": "all_enemies",
            "stat": "push",
            "op": "flag",
            "value": True,
            "description": "Attacks gain push from special rules.",
        }
    ],
    "Painted World of Ariamis_2_Skeletal Spokes": [
        {
            "id": "pw_skeletal_spokes_barrels",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Skeletal Spokes",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Enemies ignore barrels during movement.",
        },
        {
            "id": "pw_skeletal_spokes_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Skeletal Spokes",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "If an enemy is pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
        },
        {
            "id": "pw_skeletal_spokes_respawn",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Skeletal Spokes",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "If an enemy is killed, respawn it on the closest enemy spawn node, then draw a treasure card and add it to the inventory.",
        }
    ],
    "Painted World of Ariamis_2_Corrupted Hovel": [
        {
            "id": "pw_corrupted_hovel_poison",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Corrupted Hovel",
            "target_alt_indices": [1,3],
            "stat": "poison",
            "op": "flag",
            "value": True,
            "description": "Poison from special rules.",
        },
        {
            "id": "pw_corrupted_hovel_node",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Corrupted Hovel",
            "target_alt_indices": [1,3],
            "stat": "node",
            "op": "flag",
            "value": True,
            "description": "Node attack from special rules.",
        }
    ],
    "Painted World of Ariamis_2_Snowblind": [
        {
            "id": "pw_snowblind_hidden",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Snowblind",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attacks only has a single die already, ignore this rule.",
        }
    ],
    "Painted World of Ariamis_2_Monstrous Maw": [
        {
            "id": "pw_monstrous_maw_health",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Monstrous Maw",
            "target": "all_enemies",
            "stat": "health",
            "op": "set",
            "value": 10,
            "description": "Base HP 10 from special rules.",
        },
        {
            "id": "pw_monstrous_maw_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Monstrous Maw",
            "target": "all_enemies",
            "stat": "armor",
            "op": "add",
            "value": 1,
            "description": "+1 block from special rules.",
        },
        {
            "id": "pw_monstrous_maw_resist",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Monstrous Maw",
            "target": "all_enemies",
            "stat": "resist",
            "op": "add",
            "value": 1,
            "description": "+1 resist from special rules.",
        },
        {
            "id": "pw_monstrous_maw_dodge",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_2_Monstrous Maw",
            "target": "all_enemies",
            "stat": "dodge_difficulty",
            "op": "add",
            "value": 1,
            "description": "+1 dodge difficulty from special rules.",
        }
    ],
    "Painted World of Ariamis_3_Velka's Chosen": [
        {
            "id": "pw_velkas_chosen_health",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Velka's Chosen",
            "target_alt_indices": [2],
            "stat": "health",
            "op": "add",
            "base": 2,
            "per_player": 1,
            "description": "+[player_num]+2 HP from special rules.",
        },
        {
            "id": "pw_velkas_chosen_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Velka's Chosen",
            "target_alt_indices": [2],
            "stat": "armor",
            "op": "add",
            "value": 1,
            "description": "+1 block from special rules.",
        },
        {
            "id": "pw_velkas_chosen_resist",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Velka's Chosen",
            "target_alt_indices": [2],
            "stat": "resist",
            "op": "add",
            "value": 1,
            "description": "+1 resist from special rules.",
        },
        {
            "id": "pw_velkas_chosen_dodge",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Velka's Chosen",
            "target_alt_indices": [2],
            "stat": "dodge_difficulty",
            "op": "add",
            "value": 1,
            "description": "+1 dodge difficulty from special rules.",
        },
        {
            "id": "pw_velkas_chosen_poison",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Velka's Chosen",
            "target_alt_indices": [2],
            "stat": "poison",
            "op": "flag",
            "value": True,
            "description": "Poison from special rules.",
        }
    ],
    "Painted World of Ariamis_3_Deathly Freeze": [
        {
            "id": "pw_deathly_freeze_node",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Deathly Freeze",
            "target_alt_indices": [2,6],
            "stat": "node",
            "op": "flag",
            "value": True,
            "description": "Node attack from special rules.",
        },
        {
            "id": "pw_deathly_freeze_range",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Deathly Freeze",
            "target_alt_indices": [2,6],
            "stat": "range",
            "op": "add",
            "value": 1,
            "description": "+1 range from special rules.",
        },
    ],
    "Painted World of Ariamis_3_Corvian Host": [
        {
            "id": "pw_corvian_host_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Corvian Host",
            "target_alt_indices": [2,5],
            "stat": "armor",
            "op": "add",
            "value": 1,
            "description": "+1 block from special rules.",
        },
        {
            "id": "pw_corvian_host_resist",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Corvian Host",
            "target_alt_indices": [2,5],
            "stat": "resist",
            "op": "add",
            "value": 1,
            "description": "+1 resist from special rules.",
        },
        {
            "id": "pw_corvian_host_bleed",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Corvian Host",
            "target_alt_indices": [2,5],
            "stat": "bleed",
            "op": "flag",
            "value": True,
            "description": "Bleed from special rules.",
        },
    ],
    "Painted World of Ariamis_3_Eye of the Storm": [
        {
            "id": "pw_eye_of_the_storm_block",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Eye of the Storm",
            "target_alt_indices": [5],
            "stat": "armor",
            "op": "add",
            "value": 1,
            "description": "+1 block from special rules.",
        },
        {
            "id": "pw_eye_of_the_storm_resist",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Eye of the Storm",
            "target_alt_indices": [5],
            "stat": "resist",
            "op": "add",
            "value": 1,
            "description": "+1 resist from special rules.",
        },
        {
            "id": "pw_eye_of_the_storm_hidden",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Eye of the Storm",
            "target": "all_enemies",
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Hidden: After declaring an attack, players must discard a die of their choice before rolling. If the attacks only has a single die already, ignore this rule.",
        },
    ],
    "Painted World of Ariamis_3_Frozen Revolutions": [
        {
            "id": "pw_frozen_revolutions_repeat",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Frozen Revolutions",
            "target_alt_indices": [6,7],
            "stat": "repeat",
            "op": "add",
            "value": 1,
            "description": "+1 repeat from special rules.",
        },
        {
            "id": "pw_frozen_revolutions_barrels",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Frozen Revolutions",
            "target_alt_indices": [6,7],
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "Ignore barrels during movement.",
        },
        {
            "id": "pw_frozen_revolutions_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_Frozen Revolutions",
            "target_alt_indices": [6,7],
            "stat": "damage",
            "op": "add",
            "value": 0,
            "description": "If pushed onto a node containing a barrel, it suffers Stagger, then discard the barrel.",
        }
    ],
    "Painted World of Ariamis_3_The Last Bastion": [
        {
            "id": "pw_last_bastion_health",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_The Last Bastion",
            "target_alt_indices": [0],
            "stat": "health",
            "op": "add",
            "value": 5,
            "description": "+5 base HP from special rules.",
        },
        {
            "id": "pw_last_bastion_dodge",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_The Last Bastion",
            "target_alt_indices": [0],
            "stat": "dodge_difficulty",
            "op": "add",
            "value": 1,
            "description": "1+ dodge difficulty from special rules.",
        },
        {
            "id": "pw_last_bastion_damage",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_The Last Bastion",
            "target_alt_indices": [0],
            "stat": "damage",
            "op": "add",
            "value": 1,
            "description": "1+ damage from special rules.",
        },
        {
            "id": "pw_last_bastion_push",
            "source": "encounter",
            "source_id": "Painted World of Ariamis_3_The Last Bastion",
            "target_alt_indices": [0],
            "stat": "push",
            "op": "flag",
            "value": True,
            "description": "Push from special rules.",
        }
    ],
}


@st.cache_data(show_spinner=False)
def _list_encounters_cached():
    return list_encounters()


@st.cache_data(show_spinner=False)
def _load_valid_sets_cached():
    return load_valid_sets()


def _coerce_enemy_id(x):
    # Enemies are usually ints; be defensive in case a dict/name slips in.
    if isinstance(x, dict):
        x = x.get("enemy_id") or x.get("id") or x.get("name")
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        s = x.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return s
        return s
    return x


@st.cache_data(show_spinner=False)
def _load_invader_enemy_ids():
    """
    Load invader identifiers so we can count how many invaders are in a chosen enemy list.
    Supports a few plausible shapes for invaders.json.
    """
    if not INVADERS_PATH.exists():
        return set()

    try:
        with INVADERS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()

    ids = set()

    if isinstance(data, dict):
        for k, v in data.items():
            # Always include the key as a fallback identifier
            ids.add(_coerce_enemy_id(k))
            if isinstance(v, dict):
                cand = v.get("enemy_id") or v.get("id") or v.get("name")
                if cand is not None:
                    ids.add(_coerce_enemy_id(cand))
    elif isinstance(data, list):
        for v in data:
            ids.add(_coerce_enemy_id(v))

    return ids


def _get_invader_limit_for_level(level: int) -> int:
    lvl = int(level)
    hard = int(HARD_MAX_INVADERS_BY_LEVEL.get(lvl, 0))

    settings = st.session_state.get("user_settings") or {}
    limits = None
    for k in INVADER_LIMIT_SETTING_KEYS:
        if k in settings:
            limits = settings.get(k)
            break

    user_val = None
    if isinstance(limits, dict):
        user_val = limits.get(str(lvl), limits.get(lvl))
    elif isinstance(limits, (list, tuple)) and len(limits) >= lvl:
        user_val = limits[lvl - 1]
    elif isinstance(limits, int):
        user_val = limits

    if user_val is None:
        user_val = hard

    try:
        user_int = int(user_val)
    except Exception:
        user_int = hard

    return max(0, min(hard, user_int))


def apply_edited_toggle(encounter_data, expansion, encounter_name, encounter_level,
                        use_edited, enemies, combo):
    """Swap between edited/original encounter visuals (no reshuffle)."""
    card_img = generate_encounter_image(
        expansion, encounter_level, encounter_name, encounter_data, enemies, use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    return {
        "ok": True,
        "encounter_data": encounter_data,
        "expansion": expansion,
        "encounter_name": encounter_name,
        "encounter_level": encounter_level,
        "enemies": enemies,
        "card_img": card_img,
        "buf": buf,
        "expansions_used": combo
    }


def filter_encounters(all_encounters, selected_expansion: str, character_count: int, active_expansions: tuple, valid_sets: dict):
    return [
            e for e in all_encounters
            if encounter_is_valid(
                f"{selected_expansion}_{e['level']}_{e['name']}",
                character_count,
                tuple(active_expansions),
                valid_sets
            )
        ]


def filter_expansions(encounters_by_expansion, character_count: int, active_expansions: tuple, valid_sets: dict):
    filtered_expansions = []
    for expansion_name, encounter_list in encounters_by_expansion.items():
        has_valid = any(
            encounter_is_valid(
                f"{expansion_name}_{e['level']}_{e['name']}",
                character_count,
                active_expansions,
                valid_sets
            )
            for e in encounter_list
        )
        if has_valid:
            filtered_expansions.append(expansion_name)
    return filtered_expansions


def encounter_is_valid(encounter_key: str, char_count: int, active_expansions: tuple, valid_sets: dict) -> bool:
    """
    Returns True if at least one expansion set for this encounter/char_count
    is a subset of the active expansions.
    """
    expansions_for_enc = valid_sets.get(encounter_key, {}).get(str(char_count), [])
    active_set = set(active_expansions)
    for expansion_set in expansions_for_enc:
        if set(expansion_set).issubset(active_set):
            return True
    return False


def shuffle_encounter(selected_encounter, character_count, active_expansions,
                      selected_expansion, use_edited):
    """Shuffle and generate a randomized encounter (respects invader limit setting)."""
    name = selected_encounter["name"]
    level = int(selected_encounter["level"])
    encounter_slug = f"{selected_expansion}_{level}_{name}"

    encounter_data = load_encounter(encounter_slug, character_count)

    # Pick random enemies (filtered by invader limit per encounter level)
    combo, enemies = pick_random_alternative(encounter_data, set(active_expansions), level)
    if not combo or not enemies:
        limit = _get_invader_limit_for_level(level)
        return {
            "ok": False,
            "message": f"No valid alternatives under current invader limit (level {level} max invaders = {limit}).",
        }

    card_img = generate_encounter_image(
        selected_expansion, level, name, encounter_data, enemies, use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    return {
        "ok": True,
        "buf": buf,
        "card_img": card_img,
        "encounter_data": encounter_data,
        "encounter_name": name,
        "encounter_level": level,
        "expansion": selected_expansion,
        "enemies": enemies,
        "expansions_used": combo.split(",") if isinstance(combo, str) else combo
    }


def get_alternatives(data, active_expansions):
    """Return all valid alternative enemy sets based on expansions."""
    valid_alts = {}
    for combo, alt_sets in data["alternatives"].items():
        combo_set = set(combo.split(","))
        if combo_set.issubset(active_expansions):
            valid_alts[combo] = alt_sets
    return valid_alts


def pick_random_alternative(data, active_expansions, encounter_level: int):
    """Randomly pick one valid alternative enemy set (respects invader limit)."""
    valid_alts = get_alternatives(data, active_expansions)
    if not valid_alts:
        return None, None

    invader_limit = _get_invader_limit_for_level(int(encounter_level))
    invader_ids = _load_invader_enemy_ids()

    filtered = {}
    for combo, alt_sets in valid_alts.items():
        kept = []
        for enemies in alt_sets or []:
            if enemies is None:
                continue
            # enemies should be a list[int], but tolerate other iterables
            try:
                enemy_list = list(enemies)
            except Exception:
                continue

            inv_count = 0
            if invader_ids and invader_limit >= 0:
                for e in enemy_list:
                    if _coerce_enemy_id(e) in invader_ids:
                        inv_count += 1
                        if inv_count > invader_limit:
                            break

            if inv_count <= invader_limit:
                kept.append(enemy_list)

        if kept:
            filtered[combo] = kept

    if not filtered:
        return None, None

    combo = choice(list(filtered.keys()))
    enemies = choice(filtered[combo])
    return combo, enemies


def list_encounters():
    """
    Parse encounter JSON filenames and return a dict grouped by expansion:
    {
      'Tomb of Giants': ['Altar of Bones', 'Crypt of the Dead'],
      'Iron Keep': ['The Bell Gargoyles']
    }
    """
    encounters = defaultdict(dict)
    pattern = re.compile(r"(.+?)_(\d+)_(.+?)_\d+\.json")

    for f in os.listdir(ENCOUNTER_DATA_DIR):
        if not f.endswith(".json"):
            continue
        match = pattern.match(f)
        if not match:
            continue

        expansion, level, encounter_name = match.groups()
        key = (encounter_name.lower(), int(level))

        # store once per unique (name, expansion, level)
        encounters[expansion][key] = {
            "name": encounter_name,
            "expansion": expansion,
            "level": int(level),
            "version": "V1" if int(level) < 4 and expansion.lower() in {"dark souls the board game", "darkroot", "explorers", "iron keep", "executioner's chariot"} else "V2"
        }


    # --- Custom expansion sorting ---
    def expansion_sort_key(exp):
        """Sort expansions according to your priority rules."""
        exp_lower = exp.lower()

        # new core sets first
        if any(x in exp_lower for x in ["tomb of giants", "painted world of ariamis", "the sunless city"]):
            return (0, exp_lower)
        # base game next
        elif "dark souls the board game" in exp_lower:
            return (1, exp_lower)
        # original expansions
        elif any(x in exp_lower for x in ["darkroot", "explorers", "iron keep"]):
            return (2, exp_lower)
        # executioner’s chariot
        elif "executioner" in exp_lower:
            return (3, exp_lower)
        # mega bosses or others
        else:
            return (4, exp_lower)

    sorted_expansions = sorted(encounters.keys(), key=expansion_sort_key)

    # --- Sort encounters by level then name ---
    sorted_data = {}
    for exp in sorted_expansions:
        sorted_encounters = sorted(
            encounters[exp].values(),
            key=lambda e: (e["level"], e["name"].lower())
        )
        sorted_data[exp] = sorted_encounters

    return sorted_data
