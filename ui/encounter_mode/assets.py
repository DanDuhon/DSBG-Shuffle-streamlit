#ui/encounters_tab/assets.py
import streamlit as st
from PIL import Image
from pathlib import Path

from ui.encounter_mode.data.enemies import enemyNames
from ui.encounter_mode.data.keywords import (
    EDITED_ENCOUNTER_KEYWORDS_STATIC,
    encounterKeywords,
    keywordText,
)
from ui.encounter_mode.data.layout import positions, v1Expansions, v1Level4s
from ui.encounter_mode.data.rewards import ENCOUNTER_ORIGINAL_REWARDS


ENCOUNTER_CARDS_DIR = Path("assets/encounter cards")
EDITED_ENCOUNTER_CARDS_DIR = Path("assets/edited encounter cards")
ENEMY_ICONS_DIR = Path("assets/enemy icons")
KEYWORDS_DIR = Path("assets/keywords")

def _discover_edited_encounters(dir_path: Path) -> dict:
    """
    Inspect the edited encounter cards directory and return a mapping
    {(encounter_name, expansion): []} for each edited card found.

    Filenames are expected in the form:
        <Expansion>_<level>_<Encounter Name>.<ext>
    We parse only the expansion and encounter name; the level is ignored
    for the purpose of detecting edited availability.
    """
    out: dict = {}
    if not dir_path.exists():
        return {}
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        name = p.stem
        parts = name.split("_", 2)
        if len(parts) < 3:
            continue
        expansion, _level, encounter_name = parts
        expansion = expansion.strip()
        encounter_name = encounter_name.strip()
        if encounter_name and expansion:
            out[(encounter_name, expansion)] = []
    return out


# Build editedEncounterKeywords dynamically from the edited encounter cards
# folder so availability detection is driven by assets present on disk.
# Use the static keywords when available, otherwise default to empty list.
_discovered = _discover_edited_encounters(EDITED_ENCOUNTER_CARDS_DIR)
editedEncounterKeywords = {
    k: EDITED_ENCOUNTER_KEYWORDS_STATIC.get(k, []) for k in _discovered.keys()
}


def get_enemy_image_by_id(enemy_id: int):
    """Return image path for a given enemy ID."""
    image_path = ENEMY_ICONS_DIR / f"{enemyNames[enemy_id]}.png"
    return str(image_path)
