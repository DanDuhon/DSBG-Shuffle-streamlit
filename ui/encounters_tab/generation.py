#ui/encounters_tab/generation.py
import streamlit as st
import os
import base64
from json import load
from pathlib import Path
from PIL import Image

from ui.encounters_tab.assets import (get_keyword_image, get_enemy_image, encounterKeywords, editedEncounterKeywords, keywordSize, keywordText, v1Expansions, v1Level4s, positions, ENCOUNTER_CARDS_DIR, EDITED_ENCOUNTER_CARDS_DIR)


ENCOUNTER_DATA_DIR = Path("data/encounters")
VALID_SETS_PATH = Path("data/encounters_valid_sets.json")


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


def build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited):
    """Return HTML block for card image + keyword hotspots"""
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    tooltip_css = """
    <style>
    .encounter-container { position: relative; display: block; margin: auto; width: 100%; max-width: 1200px; }
    @media (min-width: 1600px) { .encounter-container { max-width: 95%; } }
    @media (min-width: 992px) and (max-width: 1599px) { .encounter-container { max-width: 68%; } }
    @media (min-width: 768px) and (max-width: 991px) { .encounter-container { max_width: 95%; } }
    @media (max-width: 767px) { .encounter-container { max-width: 100%; } }
    .encounter-container img { width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); }
    .hotspot { position: absolute; cursor: help; }
    .hotspot::after { content: attr(data-tooltip); position: absolute; left: 0; top: 100%;
        white-space: normal; padding: 6px 8px; border-radius: 6px; background: #222; color: #fff;
        font-size: 14px; width: 240px; z-index: 9999; opacity: 0; transition: opacity 0.2s; pointer-events: none; }
    .hotspot:hover::after { opacity: 1; }
    </style>
    """

    keywords = editedEncounterKeywords.get((encounter_name, expansion), []) if use_edited else encounterKeywords.get((encounter_name, expansion), [])

    hotspots = []
    for i, keyword in enumerate(keywords):
        if keyword not in keywordSize:
            continue
        w, h = keywordSize[keyword]
        x, y = 282, 400 + (32 * i)
        left_pct = 100 * x / card_img.size[0]
        top_pct = 100 * y / card_img.size[1]
        width_pct = 100 * w / card_img.size[0]
        height_pct = 100 * h / card_img.size[1]
        text = keywordText.get(keyword, "No description available.")
        safe_text = text.replace('"', '&quot;').replace("'", "\'")
        hotspots.append(
            f'<span class="hotspot" style="top:{top_pct}%; left:{left_pct}%; '
            f'width:{width_pct}%; height:{height_pct}%;" data-tooltip="{safe_text}"></span>'
        )

    hotspots_html = "".join(hotspots)
    return f"""{tooltip_css}
    <div class="encounter-container">
      <img src="data:image/png;base64,{img_b64}" alt="{encounter_name}"/>
      {hotspots_html}
    </div>
    """


def _img_tag_from_path(path: Path, title: str, height_px: int = 30, extra_css: str = "") -> str:
    try:
        if not path.exists():
            return ""
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")

        style = (
            f"height:{height_px}px; "
            f"max-height:none; "
            f"width:auto; "
            f"max-width:none; "
            f"{extra_css}"
        )

        return (
            f"<img src='data:image/png;base64,{b64}' "
            f"title='{title}' alt='{title}' "
            f"style='{style}'/>"
        )
    except Exception:
        return ""


def render_encounter_icons(current_encounter, assets_dir="assets"):
    chars_dir = Path(assets_dir) / "characters"
    exps_dir  = Path(assets_dir) / "expansions"

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

        if fname == "Executioner Chariot.png":
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


def load_encounter(encounter_slug: str, character_count: int):
    """Load encounter JSON by name (e.g., 'Altar of Bones1.json')."""
    file_path = ENCOUNTER_DATA_DIR / f"{encounter_slug}_{character_count}.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = load(f)
    return data


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
