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
    EDITED_ENCOUNTER_CARDS_DIR
)
from core.image_cache import get_image_bytes_cached, bytes_to_data_uri
from core.encounter_overrides import apply_override_to_encounter


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
    ]
    # EXAMPLE ONLY – you’ll plug in real coordinates:
    #
    # ("Velka's Chosen", "Painted World of Ariamis"): [
    #     # Put enemy1 icon in the special rules area
    #     SpecialRuleEnemyIcon(enemy_index=0, x=320, y=460),
    #     # Put enemy2 icon a bit to the right
    #     SpecialRuleEnemyIcon(enemy_index=1, x=360, y=460),
    # ],
}

EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS: Dict[Tuple[str, str], List[SpecialRuleEnemyIcon]] = {
    # Only add entries here when the edited card needs different coordinates.
    # Example:
    # ("Velka's Chosen", "Painted World of Ariamis"): [
    #     SpecialRuleEnemyIcon(enemy_index=0, x=330, y=448),
    # ],
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
    try:
        if not path.exists():
            return ""
        try:
            data = get_image_bytes_cached(str(path))
        except Exception:
            return ""
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
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return load(f)

    # Fallback: scan directory for matching base slug and character count
    base_prefix = f"{encounter_slug}_"
    if not ENCOUNTER_DATA_DIR.exists():
        raise FileNotFoundError(f"Encounter data directory not found: {ENCOUNTER_DATA_DIR}")

    for fname in os.listdir(ENCOUNTER_DATA_DIR):
        if not fname.endswith(".json"):
            continue
        if not fname.startswith(base_prefix):
            continue
        # filename format: <slug>_<character_count>.json
        parts = fname.rsplit("_", 1)
        if len(parts) != 2:
            continue
        cnt_part = parts[1]
        if not cnt_part.endswith(".json"):
            continue
        try:
            cnt = int(cnt_part[:-5])
        except Exception:
            continue
        if cnt != int(character_count):
            continue
        # Found matching file
        fp = ENCOUNTER_DATA_DIR / fname
        with open(fp, "r", encoding="utf-8") as f:
            return load(f)

    raise FileNotFoundError(f"No encounter file found for '{encounter_slug}' with character_count={character_count}")


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
            if key not in pos_table:
                # Fallback to V2 if current table missing this key
                pos_table = positions.get("V2", {})
                if key not in pos_table:
                    # No safe coordinate to use; skip this icon
                    continue

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
    # 4) Encounter-specific override placements & text
    # ---------------------------------------------------------
    # Example keys in data/encounter_overrides.json use the pattern
    # "{expansion}_{level}_{encounter_name}" or a filename-like key.
    enc_key = f"{expansion_name}_{level}_{encounter_name}"
    # Pass the existing enemy image resolver so integer IDs resolve to asset paths
    data = apply_override_to_encounter(enc_key, data, enemies, enemy_icon_resolver=get_enemy_image_by_id)

    placements = data.get("_meta", {}).get("_override_placements", [])
    texts = data.get("_meta", {}).get("_override_texts", [])

    draw = ImageDraw.Draw(card_img)
    # Use default bitmap font; let failures raise so caller can see them
    font = ImageFont.load_default()

    for p in placements:
        asset = p.get("resolved_asset") or p.get("asset")
        pos = p.get("pos")
        size = int(p.get("size", 25)) if p.get("size") is not None else 25
        if not asset or not pos:
            continue

        asset_path = Path(asset)
        # normalize simple relative references
        if not asset_path.exists():
            if asset.startswith("assets/"):
                asset_path = Path(asset)
            else:
                asset_path = Path("assets") / asset
        if not asset_path.exists():
            raise FileNotFoundError(f"Override asset not found: {asset} (resolved to {asset_path})")

        icon = Image.open(asset_path).convert("RGBA")
        w, h = icon.size
        max_side = w if w > h else h
        if max_side <= 0:
            raise ValueError(f"Invalid override asset (zero size): {asset_path}")
        s = size / max_side
        icon = icon.resize((int(round(w * s)), int(round(h * s))), Image.Resampling.LANCZOS)

        xOffset = int(round((size - icon.size[0]) / 2))
        yOffset = int(round((size - icon.size[1]) / 2))
        dest = (int(pos[0]) + xOffset, int(pos[1]) + yOffset)
        card_img.alpha_composite(icon, dest=dest)

    for t in texts:
        txt = t.get("text")
        pos = t.get("pos")
        if not txt or not pos:
            raise ValueError(f"Malformed override text directive: {t}")
        fill = t.get("fill", (0, 0, 0))
        draw.text((int(pos[0]), int(pos[1])), txt, fill=tuple(fill) if isinstance(fill, (list, tuple)) else fill, font=font)

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
