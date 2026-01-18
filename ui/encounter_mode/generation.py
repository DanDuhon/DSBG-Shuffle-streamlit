#ui/encounter_mode/generation.py
import streamlit as st
from functools import lru_cache
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple
from json import load
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from ui.encounter_mode.assets import (
    get_enemy_image_by_id,
    encounterKeywords,
    editedEncounterKeywords,
    keywordText,
    v1Expansions,
    v1Level4s,
    positions,
    ENCOUNTER_CARDS_DIR,
    EDITED_ENCOUNTER_CARDS_DIR,
    ENCOUNTER_ORIGINAL_REWARDS
)
from core.behavior.logic import load_behavior
from core.image_cache import get_image_bytes_cached, bytes_to_data_uri


ENCOUNTER_DATA_DIR = Path("data/encounters")
VALID_SETS_PATH = Path("data/encounters_valid_sets.json")

@dataclass(frozen=True)
class SpecialRuleEnemyIcon:
    """
    One enemy icon stamped into the *special rules* area.

    enemy_index:
        0-based index into the `enemies` list passed into
        generate_encounter_image. So:

            enemy_index = 0 -> enemy1
            enemy_index = 1 -> enemy2
            enemy_index = 2 -> enemy3
            ...

    x, y:
        Pixel coordinates of the TOP-LEFT of a 40x40 "icon box"
        on the encounter card image (same semantics as `positions`).

    size:
        Max dimension (in pixels) to scale the icon to.
    """
    enemy_index: int
    x: int
    y: int
    size: int = 25


# Keyed by (encounter_name, expansion_name)
SPECIAL_RULE_ENEMY_ICON_SLOTS: Dict[Tuple[str, str], List[SpecialRuleEnemyIcon]] = {
    ("The First Bastion", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=725, y=434),
        SpecialRuleEnemyIcon(enemy_index=2, x=380, y=480),
        SpecialRuleEnemyIcon(enemy_index=3, x=430, y=400),
        SpecialRuleEnemyIcon(enemy_index=3, x=500, y=505),
    ],
    ("The Iron Golem", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295),
        SpecialRuleEnemyIcon(enemy_index=0, x=375, y=394),
        SpecialRuleEnemyIcon(enemy_index=0, x=346, y=442),
    ],
    ("The Last Bastion", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=431, y=458),
        SpecialRuleEnemyIcon(enemy_index=0, x=636, y=506),
        SpecialRuleEnemyIcon(enemy_index=0, x=679, y=533),
    ],
    ("The Locked Grave", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=7, x=434, y=396),
        SpecialRuleEnemyIcon(enemy_index=7, x=616, y=444),
    ],
    ("The Shine of Gold", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=125, y=295),
        SpecialRuleEnemyIcon(enemy_index=2, x=414, y=442),
        SpecialRuleEnemyIcon(enemy_index=2, x=563, y=514),
        SpecialRuleEnemyIcon(enemy_index=2, x=501, y=543),
        SpecialRuleEnemyIcon(enemy_index=0, x=539, y=392),
        SpecialRuleEnemyIcon(enemy_index=1, x=500, y=392),
    ],
    ("The Skeleton Ball", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295),
        SpecialRuleEnemyIcon(enemy_index=5, x=455, y=295),
    ],
    ("Trecherous Tower", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=573, y=445, size=45),
        SpecialRuleEnemyIcon(enemy_index=3, x=573, y=505, size=45),
        SpecialRuleEnemyIcon(enemy_index=4, x=573, y=569, size=45),
    ],
    ("Trophy Room", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=119, y=295),
        SpecialRuleEnemyIcon(enemy_index=4, x=420, y=397),
        SpecialRuleEnemyIcon(enemy_index=4, x=294, y=493),
        SpecialRuleEnemyIcon(enemy_index=6, x=161, y=295),
        SpecialRuleEnemyIcon(enemy_index=6, x=462, y=397),
        SpecialRuleEnemyIcon(enemy_index=6, x=336, y=493),
    ],
    ("Velka's Chosen", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=125, y=295),
        SpecialRuleEnemyIcon(enemy_index=2, x=598, y=395),
        SpecialRuleEnemyIcon(enemy_index=2, x=410, y=445),
    ],
    ("Cloak and Feathers", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
    ],
    ("Aged Sentinel", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=280, y=465, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=410, y=515, size=28),
    ],
    ("Cold Snap", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=3, x=430, y=465, size=28),
    ],
    ("Corvian Host", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=323, y=480, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=523, y=480, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=533, y=505, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=382, y=560, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=295, y=585, size=28),
    ],
    ("Central Plaza", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=285, y=530, size=28),
    ],
    ("Corrupted Hovel", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=290, y=500, size=28),
    ],
    ("Gleaming Silver", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=280, y=550, size=28),
        SpecialRuleEnemyIcon(enemy_index=1, x=320, y=550, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=360, y=550, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=400, y=550, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=360, y=425, size=28),
    ],
    ("Dark Alleyway", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
    ],
    ("Abandoned and Forgotten", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=573, y=445, size=45),
        SpecialRuleEnemyIcon(enemy_index=1, x=573, y=505, size=45),
        SpecialRuleEnemyIcon(enemy_index=2, x=573, y=569, size=45),
    ],
    ("Deathly Freeze", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=6, x=284, y=480, size=28),
    ],
    ("Deathly Magic", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=123, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=549, y=394, size=28),
    ],
    ("Deathly Tolls", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=7, x=362, y=458, size=28),
    ],
    ("Depths of the Cathedral", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=8, x=362, y=398, size=28),
    ],
    ("Distant Tower", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=5, x=434, y=429, size=28),
    ],
    ("Eye of the Storm", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=373, y=485, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=567, y=511, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=125, y=295, size=28),
    ],
    ("Frozen Revolutions", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=6, x=283, y=458, size=28),
        SpecialRuleEnemyIcon(enemy_index=6, x=283, y=492, size=28),
        SpecialRuleEnemyIcon(enemy_index=6, x=710, y=492, size=28),
    ],
    ("Giant's Coffin", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=483, y=468, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=571, y=468, size=28),
    ],
    ("Gnashing Beaks", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=634, y=469, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=681, y=469, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=476, y=494, size=28),
    ],
    ("Grim Reunion", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=10, x=438, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=10, x=540, y=517, size=28),
    ],
    ("In Deep Water", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=479, y=398, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=651, y=398, size=28),
    ],
    ("Lakeview Refuge", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=8, x=430, y=461, size=28),
        SpecialRuleEnemyIcon(enemy_index=8, x=582, y=523, size=28),
        SpecialRuleEnemyIcon(enemy_index=9, x=285, y=577, size=28),
        SpecialRuleEnemyIcon(enemy_index=10, x=326, y=577, size=28),
        SpecialRuleEnemyIcon(enemy_index=11, x=367, y=577, size=28),
        SpecialRuleEnemyIcon(enemy_index=12, x=408, y=577, size=28),
    ],
    ("Monstrous Maw", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=420, y=394, size=28),
    ],
    ("No Safe Haven", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=125, y=295, size=28),
    ],
    ("Parish Church", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=10, x=359, y=398, size=28),
    ],
    ("Parish Gates", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=3, x=612, y=444, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=375, y=517, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=285, y=568, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=326, y=469, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=414, y=517, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=326, y=568, size=28),
    ],
    ("Pitch Black", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=126, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=453, y=295, size=28),
    ],
    ("Puppet Master", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=125, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=287, y=396, size=28),
    ],
    ("Shattered Keep", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=288, y=429, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=329, y=429, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=370, y=429, size=28),
    ],
    ("Skeletal Spokes", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=287, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=328, y=423, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=328, y=483, size=28),
    ],
    ("Skeleton Overlord", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=461, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=1, x=416, y=521, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=622, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=2, x=491, y=521, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=630, y=469, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=669, y=521, size=28),
    ],
    ("Tempting Maw", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=445, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=441, y=396, size=28),
        SpecialRuleEnemyIcon(enemy_index=4, x=698, y=505, size=28),
    ],
    ("The Abandoned Chest", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=649, y=392, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=285, y=419, size=28),
    ],
    ("The Beast From the Depths", "Tomb of Giants"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=124, y=293, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=440, y=400, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=314, y=448, size=28),
    ],
    ("The Bell Tower", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=647, y=392, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=688, y=392, size=28),
    ],
    ("The Grand Hall", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=7, x=360, y=430, size=28),
    ],
}

# Per-encounter placement for rendered Gang text on the original card image.
# Key: (encounter_name, expansion_name) -> (x, y, size)
GANG_TEXT_POSITIONS: Dict[Tuple[str, str], Tuple[int, int, int]] = {
    ("Undead Sanctum", "The Sunless City"): (280, 430, 28),
    ("The Fountainhead", "The Sunless City"): (280, 400, 28),
    ("Deathly Tolls", "The Sunless City"): (280, 495, 28),
    ("Flooded Fortress", "The Sunless City"): (280, 430, 28),
    ("Depths of the Cathedral", "The Sunless City"): (280, 430, 28),
    ("Twilight Falls", "The Sunless City"): (280, 430, 28),
}

EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS: Dict[Tuple[str, str], List[SpecialRuleEnemyIcon]] = {
    # Only add entries here when the edited card needs different coordinates.
    # Example:
    # ("Velka's Chosen", "Painted World of Ariamis"): [
    #     SpecialRuleEnemyIcon(enemy_index=0, x=330, y=448),
    # ],
    ("Trophy Room", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=119, y=295),
        SpecialRuleEnemyIcon(enemy_index=4, x=420, y=447),
        SpecialRuleEnemyIcon(enemy_index=4, x=294, y=543),
        SpecialRuleEnemyIcon(enemy_index=6, x=161, y=295),
        SpecialRuleEnemyIcon(enemy_index=6, x=462, y=447),
        SpecialRuleEnemyIcon(enemy_index=6, x=336, y=543),
    ],
    ("The First Bastion", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=1, x=480, y=430),
        SpecialRuleEnemyIcon(enemy_index=2, x=480, y=463),
        SpecialRuleEnemyIcon(enemy_index=3, x=420, y=400),
        SpecialRuleEnemyIcon(enemy_index=3, x=480, y=495),
    ],
    ("Monstrous Maw", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=125, y=295, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=416, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=0, x=285, y=494, size=28),
    ],
    ("Eye of the Storm", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=0, x=378, y=510, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=650, y=540, size=28),
        SpecialRuleEnemyIcon(enemy_index=5, x=125, y=295, size=28),
    ],
    ("Frozen Revolutions", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=6, x=283, y=452, size=28),
        SpecialRuleEnemyIcon(enemy_index=6, x=283, y=480, size=28),
        SpecialRuleEnemyIcon(enemy_index=6, x=700, y=478, size=28),
        SpecialRuleEnemyIcon(enemy_index=6, x=375, y=555, size=28),
    ],
    ("Velka's Chosen", "Painted World of Ariamis"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=130, y=295),
        SpecialRuleEnemyIcon(enemy_index=2, x=598, y=445),
        SpecialRuleEnemyIcon(enemy_index=2, x=420, y=495),
    ],
    ("The Bell Tower", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=647, y=450, size=28),
        SpecialRuleEnemyIcon(enemy_index=3, x=688, y=450, size=28),
    ],
    ("Flooded Fortress", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=433, y=400, size=28),
    ],
    ("The Hellkite Bridge", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=2, x=620, y=500, size=28),
    ],
    ("Central Plaza", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=4, x=285, y=490, size=28),
    ],
    ("Grim Reunion", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=10, x=438, y=394, size=28),
        SpecialRuleEnemyIcon(enemy_index=10, x=540, y=477, size=28),
        SpecialRuleEnemyIcon(enemy_index=10, x=573, y=587, size=28),
    ],
    ("The Grand Hall", "The Sunless City"): [
        SpecialRuleEnemyIcon(enemy_index=7, x=360, y=453, size=28),
    ],
}


@st.cache_data(show_spinner=False)
def cached_encounter_image(expansion: str, level: int, name: str, data: dict, enemies: list[int], edited: bool):
    """Cache the generated encounter image."""
    return generate_encounter_image(expansion, level, name, data, enemies, use_edited=edited)


def load_valid_sets():
    """Load the precomputed valid sets JSON file once."""
    if VALID_SETS_PATH.exists():
        with open(VALID_SETS_PATH, "r", encoding="utf-8") as f:
            return load(f)
    return {}


def _img_tag_from_path(path: Path, title: str, height_px: int = 30, extra_css: str = "") -> str:
    if not path.exists():
        return ""
    data = get_image_bytes_cached(str(path))
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    data_uri = bytes_to_data_uri(data, mime=mime)

    style = (
        f"height:{height_px}px; "
        f"max-height:none; "
        f"width:auto; "
        f"max-width:none; "
        f"{extra_css}"
    )

    return (
        f"<img src='{data_uri}' "
        f"title='{title}' alt='{title}' "
        f"style='{style}'/>")


def render_encounter_icons(current_encounter, assets_dir="assets"):
    chars_dir = Path(assets_dir) / "characters"
    exps_dir = Path(assets_dir) / "expansions"

    html = """
    <style>
      .icons-section h4 { margin: 0.75rem 0 0.25rem 0; }
      .icons-row { display:flex; gap:6px; flex-wrap:nowrap; overflow-x:auto; padding-bottom:2px; }
      .icons-row::-webkit-scrollbar { height: 6px; }
      .icons-row::-webkit-scrollbar-thumb { background: #bbb; border-radius: 3px; }
      .icons-grid { display:grid; grid-template-columns: repeat(6, 1fr); gap:6px; }
      .icon-fallback {
        height:48px; background:#ccc; border-radius:6px;
        display:flex; align-items:center; justify-content:center;
        font-size:10px; text-align:center; padding:2px;
      }
    </style>
    <div class="icons-section">
    """

    # PARTY
    characters = st.session_state.user_settings.get("selected_characters", [])
    if characters:
        html += "<h5>Party</h5><div class='icons-row'>"
        for char in characters:
            fname = f"{char}.png"
            tag = _img_tag_from_path(chars_dir / fname, title=char, extra_css="border-radius:6px;")
            if tag:
                html += tag
            else:
                initial = (char or "?")[0:1]
                html += f"<div class='icon-fallback' title='{char}'>{initial}</div>"
        html += "</div>"

    # EXPANSIONS USED
    enemies = current_encounter["enemies"]
    expansions_used = list(current_encounter.get("expansions_used", []))
    icons = []
    html += "<h5>Expansions Needed</h5><div class='icons-grid'>"

    enemy_ids = set([e["name"] if isinstance(e, dict) else e for e in enemies])

    if any(exp in expansions_used for exp in ["Dark Souls The Board Game", "The Sunless City"]):
        if 16 not in enemy_ids and 34 not in enemy_ids:
            icons.append({"file": "Dark Souls The Board Game The Sunless City.png",
                          "label": "Dark Souls The Board Game / The Sunless City"})
            expansions_used = [exp for exp in expansions_used if exp not in ["Dark Souls The Board Game", "The Sunless City"]]
        else:
            if 16 in enemy_ids:
                icons.append({"file": "Dark Souls The Board Game.png", "label": "Dark Souls The Board Game"})
            if 34 in enemy_ids:
                icons.append({"file": "The Sunless City.png", "label": "The Sunless City"})
        for exp in [exp for exp in expansions_used if exp not in {"Dark Souls The Board Game", "The Sunless City"}]:
            icons.append({"file": f"{exp}.png", "label": exp})
    else:
        for exp in expansions_used:
            icons.append({"file": f"{exp}.png", "label": exp})

    seen = set()
    for icon in icons:
        fname, label = icon["file"], icon["label"]
        if fname in seen:
            continue
        seen.add(fname)

        if fname == "Executioner's Chariot.png":
            height_px = 36
        else:
            height_px = 30

        tag = _img_tag_from_path(
            exps_dir / fname,
            title=label,
            height_px=height_px,
            extra_css="object-fit:contain; border-radius:6px;",
        )
        if tag:
            html += tag
        else:
            html += f"<div class='icon-fallback' title='{label}'>{label}</div>"

    html += "</div>"
    return html


def build_encounter_keywords(encounter_name, expansion, use_edited=False):
    """Return list of (keyword, description)"""
    keywords = editedEncounterKeywords.get((encounter_name, expansion), []) if use_edited else encounterKeywords.get((encounter_name, expansion), [])
    return [(kw, keywordText.get(kw, "No description available.")) for kw in keywords]


@lru_cache(maxsize=1024)
def load_encounter(encounter_slug: str, character_count: int):
    """Load encounter JSON by slug and character count.

    Prefer the exact `{encounter_slug}_{character_count}.json` filename; if
    that file is missing, scan the `data/encounters` directory for a matching
    base slug and character-count variant and return it if found.
    """
    # Fast path: exact filename
    file_path = ENCOUNTER_DATA_DIR / f"{encounter_slug}_{character_count}.json"
    with open(file_path, "r", encoding="utf-8") as f:
        return load(f)


def generate_encounter_image(
    expansion_name: str,
    level: int,
    encounter_name: str,
    data: dict,
    enemies: list[int],
    use_edited=False,
):
    """Render the encounter card with enemy icons based on enemySlots layout."""
    # Some encounter filenames omit the level (e.g. "Gravelord Nito Setup").
    # Build the filename using a precomputed suffix to avoid complex nested f-string expressions.
    suffix = "" if encounter_name == "Gravelord Nito Setup" else f"_{level}"
    card_path = ENCOUNTER_CARDS_DIR / f"{expansion_name}{suffix}_{encounter_name}.jpg"

    if use_edited:
        edited_path = EDITED_ENCOUNTER_CARDS_DIR / f"{expansion_name}_{level}_{encounter_name}.jpg"
        if os.path.exists(edited_path):
            card_path = edited_path

    card_img = Image.open(card_path).convert("RGBA")

    # ---------------------------------------------------------
    # 1) Main enemy grid icons
    # ---------------------------------------------------------
    enemy_slots = data.get("enemySlots", data.get("encounter_data", {}).get("enemySlots", []))
    enemy_index = 0  # which enemy from the chosen set we’re using next

    for slot_idx, enemy_count in enumerate(enemy_slots):
        if enemy_count <= 0 or slot_idx in {4, 7, 10}:  # these slots are spawns, so don't place them
            enemy_index += enemy_count
            continue

        for i in range(enemy_count):
            if enemy_index >= len(enemies):
                break

            enemy_id = enemies[enemy_index]
            enemy_index += 1

            icon_path = get_enemy_image_by_id(enemy_id)
            icon_img = Image.open(icon_path)
            width, height = icon_img.size

            # Size the image down to 40 pixels based on the longer side.
            max_side = width if width > height else height
            if max_side <= 0:
                continue

            # Normalize a common name mismatch so classification works
            normalized = expansion_name.replace("Executioner's Chariot", "Executioner's Chariot")

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

            size = 45 if "V2" in lookup else 145 if lookup == "V1" else 100
            s = size / max_side
            icon_size = (int(round(width * s)), int(round(height * s)))
            icon_img = icon_img.convert("RGBA").resize(icon_size, Image.Resampling.LANCZOS)

            # This is used to center the icon no matter its width or height.
            xOffset = int(round((size - icon_size[0]) / 2))
            yOffset = int(round((size - icon_size[1]) / 2))

            pos_table = positions.get(lookup) or positions.get("V2", {})
            key = (slot_idx, i)

            coords = (pos_table[key][0] + xOffset, pos_table[key][1] + yOffset)
            card_img.alpha_composite(icon_img, dest=coords)

    # ---------------------------------------------------------
    # 3) Special rules enemy icons
    # ---------------------------------------------------------
    cfg_key = (encounter_name, expansion_name)

    if use_edited:
        # Prefer edited layout if it exists, otherwise fall back to base layout
        special_icons = EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS.get(
            cfg_key,
            SPECIAL_RULE_ENEMY_ICON_SLOTS.get(cfg_key, []),
        )
    else:
        special_icons = SPECIAL_RULE_ENEMY_ICON_SLOTS.get(cfg_key, [])

    for cfg in special_icons:
        idx = cfg.enemy_index
        # 0-based index into the shuffled enemies list
        if not (0 <= idx < len(enemies)):
            continue

        enemy_id = enemies[idx]
        icon_path = get_enemy_image_by_id(enemy_id)
        icon_img = Image.open(icon_path)
        width, height = icon_img.size

        max_side = width if width > height else height
        if max_side <= 0:
            continue

        # Scale to cfg.size
        s = cfg.size / max_side
        icon_size = (int(round(width * s)), int(round(height * s)))
        icon_img = icon_img.convert("RGBA").resize(icon_size, Image.Resampling.LANCZOS)

        # Center inside the cfg.size x cfg.size box whose top-left is (cfg.x, cfg.y)
        xOffset = int(round((cfg.size - icon_size[0]) / 2))
        yOffset = int(round((cfg.size - icon_size[1]) / 2))

        dest = (cfg.x + xOffset, cfg.y + yOffset)
        card_img.alpha_composite(icon_img, dest=dest)
    # ---------------------------------------------------------
    # 4) Render item reward text
    # ---------------------------------------------------------
    # Prepare a drawing context for text rendering
    draw = ImageDraw.Draw(card_img)

    pref = st.session_state.get("user_settings", {}).get("encounter_item_reward_mode", "Original")

    # Fixed font + size per spec
    font = ImageFont.truetype("assets/AdobeCaslonProSemibold.ttf", 25)

    entries = ENCOUNTER_ORIGINAL_REWARDS.get((encounter_name, expansion_name), [])
    # When shuffling with replacement preferences (e.g. Similar Soul Cost), allow
    # the shuffler to provide replacement names via `encounter_data["_shuffled_reward_replacements"]`.
    repl_map = (data or {}).get("_shuffled_reward_replacements") or {}

    def _wrap_text_to_lines(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list:
        words = str(text).split()
        if not words:
            return [""]
        lines = []
        cur = words[0]
        for w in words[1:]:
            candidate = cur + " " + w
            bbox = draw.textbbox((0, 0), candidate, font=font)
            w_px = bbox[2] - bbox[0]
            if w_px <= max_w:
                cur = candidate
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    # Draw either the original listed text, or a replacement if provided and the
    # user's preference requests non-original rendering.
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"ENCOUNTER_ORIGINAL_REWARDS entries must be dicts: {entry}")
        orig_txt = entry.get("text")
        pos = entry.get("pos")
        if orig_txt is None or pos is None:
            raise ValueError(f"Malformed original reward entry: {entry}")

        # Choose displayed text: original for 'Original' mode, otherwise allow replacement
        if pref == "Original":
            txt = orig_txt
        else:
            txt = repl_map.get(orig_txt, orig_txt)

        # Wrap long text to avoid overflowing the card. Optional per-entry `max_width` in pixels.
        max_width = int(entry.get("max_width", 200))
        lines = _wrap_text_to_lines(txt, font, max_width)
        # vertical spacing: use font height
        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        x0 = int(pos[0])
        y0 = int(pos[1])
        for i, line in enumerate(lines):
            draw.text((x0, y0 + i * line_h), line, font=font, fill=(0, 0, 0))

    # ---------------------------------------------------------
    # 5) Render Gang text for Setup/original card if present
    # ---------------------------------------------------------
    # Determine whether this encounter card lists the gang keyword
    src = editedEncounterKeywords if use_edited else encounterKeywords
    kws = src.get((encounter_name, expansion_name)) or []
    if "gang" in kws:
        # Detect gang name from shuffled/original enemies list
        gang_keys = ["Hollow", "Alonne", "Skeleton", "Silver Knight"]
        counts: Dict[str, int] = {k: 0 for k in gang_keys}

        for eid in enemies:
            name = None
            health = None
            if isinstance(eid, dict):
                name = eid.get("name") or eid.get("id")
                if "health" in eid:
                    health = int(eid.get("health"))
            else:
                if isinstance(eid, int):
                    # map id -> name using assets mapping (imported elsewhere)
                    from ui.encounter_mode.assets import enemyNames as _enemyNames
                    name = _enemyNames.get(eid)
                else:
                    name = str(eid)

                if name:
                    cfg = load_behavior(Path("data/behaviors") / f"{name}.json")
                    health = int(cfg.raw.get("health", 1))

            if not name:
                continue

            lname = name.lower()
            for g in gang_keys:
                if g.lower() in lname and health == 1:
                    counts[g] += 1
                    break

        best = None
        best_count = 0
        for k, v in counts.items():
            if v > best_count:
                best = k
                best_count = v

        gang_name = best if best_count > 0 else None

        # Use pre-rendered gang images in assets/keywords instead of drawing text.
        pos_entry = GANG_TEXT_POSITIONS.get((encounter_name, expansion_name))
        if pos_entry:
            gx, gy, gsize = pos_entry

            # Candidate filenames to support different naming conventions
            candidates = []
            if gang_name:
                lname = gang_name.lower().replace(" ", "_")
                candidates.append(f"gang_{lname}.png")            # e.g. gang_hollow.png
                candidates.append(f"gang{gang_name.replace(' ', '')}.png")  # e.g. gangHollow.png
                candidates.append(f"gang_{gang_name.replace(' ', '')}.png")   # e.g. gang_Hollow.png

            gang_img_path = None
            for fname in candidates:
                p = Path("assets") / "keywords" / fname
                if p.exists():
                    gang_img_path = p
                    break

            if gang_img_path:
                gimg = Image.open(gang_img_path).convert("RGBA")
                gw, gh = gimg.size
                if gh <= 0:
                    raise ValueError("Invalid gang image height")
                scale = gsize / gh
                new_size = (int(round(gw * scale)), int(round(gh * scale)))
                gimg = gimg.resize(new_size, Image.Resampling.LANCZOS)
                # Composite centered on the requested point
                card_img.alpha_composite(gimg, dest=(gx, gy))

    return card_img


@st.cache_data(show_spinner=False)
def cached_encounter_image(expansion: str, level: int, name: str, data: dict, enemies: list[int], edited: bool):
    """Cached wrapper for generate_encounter_image to avoid re-rendering identical encounters."""
    return generate_encounter_image(expansion, level, name, data, enemies, use_edited=edited)


@st.cache_data(show_spinner=False)
def load_encounter_data(expansion: str, name: str | None = None, character_count: int = 3) -> dict:
    """
    Wrapper around load_encounter that can later handle list or dataclass conversion.
    """
    if name:
        slug = f"{expansion}_{name}"
        return load_encounter(slug, character_count)
    else:
        # Future support for all encounters in expansion
        return {}
