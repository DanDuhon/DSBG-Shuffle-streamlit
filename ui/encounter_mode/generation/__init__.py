#ui/encounter_mode/generation.py
import streamlit as st
from functools import lru_cache
import os
from typing import Dict, Tuple
from json import load
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from core.behavior.logic import load_behavior
from core.image_cache import get_image_bytes_cached, bytes_to_data_uri
from core.settings_manager import get_config_bool, is_streamlit_cloud
from ui.encounter_mode.assets import (
    get_enemy_image_by_id,
    editedEncounterKeywords,
    ENCOUNTER_CARDS_DIR,
    EDITED_ENCOUNTER_CARDS_DIR,
)
from ui.encounter_mode.data.layout import positions, v1Expansions, v1Level4s
from ui.encounter_mode.data.keywords import encounterKeywords, keywordText
from ui.encounter_mode.data.rewards import ENCOUNTER_ORIGINAL_REWARDS
from ui.encounter_mode.data.special_rule_icons import (
    SPECIAL_RULE_ENEMY_ICON_SLOTS,
    GANG_TEXT_POSITIONS,
    EDITED_SPECIAL_RULE_ENEMY_ICON_SLOTS,
)


ENCOUNTER_DATA_DIR = Path("data/encounters")
VALID_SETS_PATH = Path("data/encounters_valid_sets.json")

_REWARD_FONT_PATH = Path("assets/AdobeCaslonProSemibold.ttf")


_TIGHTEN_LRU = is_streamlit_cloud() and get_config_bool(
    "DSBG_DISABLE_ENCOUNTER_IMAGE_CACHES", default=False
)

_ENEMY_ICON_RGBA_CACHE_MAX = 256 if _TIGHTEN_LRU else 1024
_ICON_RESIZED_CACHE_MAX = 512 if _TIGHTEN_LRU else 4096


@lru_cache(maxsize=8)
def _get_reward_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(_REWARD_FONT_PATH), int(size))
    except Exception:
        # Fall back gracefully if font is missing in some environments.
        return ImageFont.load_default()


@lru_cache(maxsize=256)
def _load_rgba_image(path: str) -> Image.Image:
    """Load an RGBA image from disk.

    NOTE: Returned image must be treated as read-only.
    Callers should `copy()` before mutating/compositing.
    """
    return Image.open(path).convert("RGBA")


def _should_bypass_encounter_card_base_image_cache() -> bool:
    try:
        return is_streamlit_cloud() and get_config_bool("DSBG_DISABLE_ENCOUNTER_IMAGE_CACHES", default=False)
    except Exception:
        return False


@lru_cache(maxsize=_ENEMY_ICON_RGBA_CACHE_MAX)
def _load_enemy_icon_rgba(path: str) -> Image.Image:
    """Load an enemy icon as RGBA (read-only cached base)."""
    return Image.open(path).convert("RGBA")


@lru_cache(maxsize=_ICON_RESIZED_CACHE_MAX)
def _get_icon_resized(path: str, box_size: int) -> Tuple[Image.Image, Tuple[int, int]]:
    """Return icon resized to fit within `box_size` square.

    Returns (resized_icon_img, (w, h)). Cached; treat as read-only.
    """
    src = _load_enemy_icon_rgba(path)
    width, height = src.size
    max_side = width if width > height else height
    if max_side <= 0:
        # Defensive; return a 1x1 transparent image.
        img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return img, (1, 1)

    s = int(box_size) / max_side
    icon_size = (int(round(width * s)), int(round(height * s)))
    resized = src.resize(icon_size, Image.Resampling.LANCZOS)
    return resized, icon_size


@lru_cache(maxsize=256)
def _get_enemy_health_from_behavior(name: str) -> int:
    try:
        cfg = load_behavior(Path("data/behaviors") / f"{name}.json")
        return int(cfg.raw.get("health", 1))
    except Exception:
        return 1


@lru_cache(maxsize=256)
def _get_resized_gang_image(path: str, target_height_px: int) -> Image.Image:
    """Load and resize a gang keyword image to a target height (cached)."""
    src = _load_rgba_image(path)
    gw, gh = src.size
    if gh <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    scale = int(target_height_px) / gh
    new_size = (int(round(gw * scale)), int(round(gh * scale)))
    return src.resize(new_size, Image.Resampling.LANCZOS)



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

    Current behavior: loads the exact file:
    `data/encounters/{encounter_slug}_{character_count}.json`.

    If the file is missing, this function raises `FileNotFoundError`.
    (Callers that want variant fallback should implement it at a higher level
    using the encounter index / available character-count variants.)
    """
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

    # Base encounter card image can be large; on Streamlit Cloud we optionally bypass
    # caching to reduce long-lived memory usage.
    if _should_bypass_encounter_card_base_image_cache():
        card_img = Image.open(card_path).convert("RGBA")
    else:
        card_img = _load_rgba_image(str(card_path))
    card_img = card_img.copy()

    # ---------------------------------------------------------
    # 1) Main enemy grid icons
    # ---------------------------------------------------------
    enemy_slots = data.get("enemySlots", data.get("encounter_data", {}).get("enemySlots", []))
    enemy_index = 0  # which enemy from the chosen set we’re using next

    # Layout selection is constant for the entire card.
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
    pos_table = positions.get(lookup) or positions.get("V2", {})

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
            icon_img, icon_size = _get_icon_resized(str(icon_path), int(size))

            # This is used to center the icon no matter its width or height.
            xOffset = int(round((size - icon_size[0]) / 2))
            yOffset = int(round((size - icon_size[1]) / 2))

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
        icon_img, icon_size = _get_icon_resized(str(icon_path), int(cfg.size))

        # Center inside the cfg.size x cfg.size box whose top-left is (cfg.x, cfg.y)
        xOffset = int(round((cfg.size - icon_size[0]) / 2))
        yOffset = int(round((cfg.size - icon_size[1]) / 2))

        dest = (cfg.x + xOffset, cfg.y + yOffset)
        card_img.alpha_composite(icon_img, dest=dest)
    # ---------------------------------------------------------
    # 4) Render item reward text
    # ---------------------------------------------------------
    entries = ENCOUNTER_ORIGINAL_REWARDS.get((encounter_name, expansion_name), [])
    # When shuffling with replacement preferences (e.g. Similar Soul Cost), allow
    # the shuffler to provide replacement names via `encounter_data["_shuffled_reward_replacements"]`.
    repl_map = (data or {}).get("_shuffled_reward_replacements") or {}

    if entries:
        # Prepare a drawing context for text rendering only when needed.
        draw = ImageDraw.Draw(card_img)

        pref = st.session_state.get("user_settings", {}).get("encounter_item_reward_mode", "Original")

        # Fixed font + size per spec (cached)
        font = _get_reward_font(25)

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
    pos_entry = GANG_TEXT_POSITIONS.get((encounter_name, expansion_name))
    # Only do gang detection work if we're actually going to render a gang image.
    if pos_entry and "gang" in kws:
        # Detect gang name from shuffled/original enemies list
        gang_keys = ["Hollow", "Alonne", "Skeleton", "Silver Knight"]
        counts: Dict[str, int] = {k: 0 for k in gang_keys}

        from ui.encounter_mode.assets import enemyNames as _enemyNames

        for eid in enemies:
            name = None
            health = None
            if isinstance(eid, dict):
                name = eid.get("name") or eid.get("id")
                if "health" in eid:
                    health = int(eid.get("health"))
            else:
                if isinstance(eid, int):
                    # map id -> name using assets mapping
                    name = _enemyNames.get(eid)
                else:
                    name = str(eid)

                if name:
                    health = _get_enemy_health_from_behavior(name)

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
            gimg = _get_resized_gang_image(str(gang_img_path), int(gsize))
            # Composite centered on the requested point
            card_img.alpha_composite(gimg, dest=(gx, gy))

    return card_img


@st.cache_data(show_spinner=False)
def load_encounter_data(expansion: str, name: str | None = None, character_count: int | None = None, level: int | None = None) -> dict:
    """
    Wrapper around load_encounter that can later handle list or dataclass conversion.
    """
    if name:
        # Prefer filenames that include expansion, level, and name
        if level is not None:
            slug = f"{expansion}_{int(level)}_{name}"
        else:
            slug = f"{expansion}_{name}"
        return load_encounter(slug, character_count)
    else:
        # Future support for all encounters in expansion
        return {}
