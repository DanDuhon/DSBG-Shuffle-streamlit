import json
import os
import re
import random
from collections import defaultdict
from pathlib import Path
from PIL import Image
from .enemyNames import enemyNames
from .encounterKeywords import encounterKeywords, keywordSize
from .editedEncounterKeywords import editedEncounterKeywords


ENCOUNTER_DATA_DIR = Path(__file__).parent.parent / "data" / "encounters"
ENEMY_ICONS_DIR = Path(__file__).parent.parent / "assets" / "enemy icons"
ENCOUNTER_CARDS_DIR = Path(__file__).parent.parent / "assets" / "encounter cards"
EDITED_ENCOUNTER_CARDS_DIR = Path(__file__).parent.parent / "assets" / "edited encounter cards"
KEYWORDS_DIR = Path(__file__).parent.parent / "assets" / "keywords"
VALID_SETS_PATH = Path("data") / "encounters_valid_sets.json"


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


def load_encounter(encounter_slug: str, character_count: int):
    """Load encounter JSON by name (e.g., 'Altar of Bones1.json')."""
    file_path = ENCOUNTER_DATA_DIR / f"{encounter_slug}_{character_count}.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


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
    combo = random.choice(list(valid_alts.keys()))
    enemies = random.choice(valid_alts[combo])
    return combo, enemies


def get_enemy_image(enemy_id: int):
    """Return image path for a given enemy ID."""
    image_path = ENEMY_ICONS_DIR / f"{enemyNames[enemy_id]}.png"
    return str(image_path)


def get_keyword_image(keyword: str):
    """Return image path for a given keyword."""
    image_path = KEYWORDS_DIR / f"{keyword}.png"
    return str(image_path)


def generate_encounter_image(expansion_name: str, level: int, encounter_name: str, data: dict, enemies: list[int], use_edited=False):
    """Render the encounter card with enemy icons based on enemySlots layout."""
    card_path = ENCOUNTER_CARDS_DIR / f"{expansion_name}_{level}_{encounter_name}.jpg"

    if use_edited:
        edited_path = EDITED_ENCOUNTER_CARDS_DIR / f"{expansion_name}_{level}_{encounter_name}.jpg"
        if os.path.exists(edited_path):
            card_path = edited_path
        keywordLookup = editedEncounterKeywords
    else:
        keywordLookup = encounterKeywords
            
    card_img = Image.open(card_path).convert("RGBA")

    for i, keyword in enumerate(keywordLookup.get((encounter_name, expansion_name), [])):
        if keyword not in keywordSize:
            continue
        keywordImagePath = get_keyword_image(keyword)
        keywordImage = Image.open(keywordImagePath).convert("RGBA").resize(keywordSize[keyword], Image.Resampling.LANCZOS)
        card_img.alpha_composite(keywordImage, dest=(282, int(400 + (32 * i))))

    enemy_slots = data.get("enemySlots", data.get("encounter_data", {}).get("enemySlots", []))
    enemy_index = 0  # which enemy from the chosen set we’re using next

    for slot_idx, enemy_count in enumerate(enemy_slots):
        if enemy_count <= 0 or slot_idx in {4, 7, 10}: # these slots are spawns, so don't place them
            continue

        for i in range(enemy_count):
            if enemy_index >= len(enemies):
                break

            enemy_id = enemies[enemy_index]
            enemy_index += 1

            icon_path = get_enemy_image(enemy_id)
            icon_img = Image.open(icon_path)
            width, height = icon_img.size
            # Size the image down to 40 pixels based on the longer side.
            s = 40 / (width if width > height else height)
            icon_size = (int(round(width * s)), int(round(height * s)))
            icon_img = icon_img.convert("RGBA").resize(icon_size, Image.Resampling.LANCZOS)
            # Normalize a common name mismatch so classification works
            normalized = expansion_name.replace("Executioner's Chariot", "Executioner Chariot")

            if normalized in v1Expansions:
                lookup = "V1"
            elif normalized in v1Level4s and level < 4:
                lookup = "V1"
            elif normalized in v1Level4s:
                lookup = "V1Level4"
            elif level == 4:
                lookup = "V2Level4"
            else:
                lookup = "V2"

            # This is used to center the icon no matter its width or height.
            xOffset = int(round((40 - icon_size[0]) / 2))
            yOffset = int(round((40 - icon_size[1]) / 2))
            pos_table = positions.get(lookup) or positions.get("V2", {})
            key = (slot_idx, i)
            if key not in pos_table:
                # Fallback to V2 if current table missing this key
                pos_table = positions.get("V2", {})
                if key not in pos_table:
                    # No safe coordinate to use; skip this icon
                    continue
            coords = (pos_table[key][0] + xOffset, pos_table[key][1] + yOffset)
            card_img.alpha_composite(icon_img, dest=coords)

    return card_img


def load_valid_sets():
    """Load the precomputed valid sets JSON file once."""
    if VALID_SETS_PATH.exists():
        with open(VALID_SETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


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


v1Expansions = {
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep"
}

v1Level4s = {
    "Executioner Chariot",
    "Executioner's Chariot",  # allow both spellings
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
}

positions = {
    "V2": {
        (0, 0): (609, 663),
        (0, 1): (667, 663),
        (0, 2): (725, 663),
        (1, 0): (609, 721),
        (1, 1): (667, 721),
        (1, 2): (725, 721),
        (5, 0): (609, 911),
        (5, 1): (667, 911),
        (5, 2): (725, 911),
        (6, 0): (609, 969),
        (6, 1): (667, 969),
        (6, 2): (725, 969),
        (8, 0): (609, 1159),
        (8, 1): (667, 1159),
        (8, 2): (725, 1159),
        (9, 0): (609, 1217),
        (9, 1): (667, 1217),
        (9, 2): (725, 1217)
    },
    "V2Level4": {},
    "V1": {},
    "V1Level4": {}
}