import streamlit as st
import re
import os
from io import BytesIO
from random import choice
from collections import defaultdict

from ui.encounters_tab.generation import generate_encounter_image, load_encounter, load_valid_sets, ENCOUNTER_DATA_DIR
from ui.encounters_tab.models import Encounter


@st.cache_data(show_spinner=False)
def _list_encounters_cached():
    return list_encounters()


@st.cache_data(show_spinner=False)
def _load_valid_sets_cached():
    return load_valid_sets()


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
    """Shuffle and generate a randomized encounter"""
    name = selected_encounter["name"]
    level = selected_encounter["level"]
    encounter_slug = f"{selected_expansion}_{level}_{name}"

    encounter_data = load_encounter(encounter_slug, character_count)

    # Pick random enemies
    combo, enemies = pick_random_alternative(encounter_data, set(active_expansions))
    if not combo or not enemies:
        return {"ok": False, "message": "No valid alternatives."}

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


def pick_random_alternative(data, active_expansions):
    """Randomly pick one valid alternative enemy set."""
    valid_alts = get_alternatives(data, active_expansions)
    if not valid_alts:
        return None, None
    combo = choice(list(valid_alts.keys()))
    enemies = choice(valid_alts[combo])
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
            "version": "V1" if int(level) < 4 and expansion.lower() in {"dark souls the board game", "darkroot", "explorers", "iron keep", "executioner chariot"} else "V2"
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
