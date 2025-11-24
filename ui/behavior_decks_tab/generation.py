import streamlit as st
import json
import hashlib
import io
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Any, Optional

from core.image_cache import _load_jpg_cached, _load_png_cached
from ui.behavior_decks_tab.assets import ICONS_DIR, FONTS, coords_map, text_styles, build_icon_filename


@st.cache_data(show_spinner=False)
def render_data_card_cached(
    base_path: str,
    raw_json: Dict[str, Any],
    is_boss: bool,
    no_edits: bool = False,
    variant_id: Optional[str] = None,
) -> bytes:
    """
    Cached wrapper for render_data_card(...). Returns PNG bytes.
    Cache key includes a stable hash of raw_json and variant.
    """
    _ = _hash_json(raw_json)  # incorporated into Streamlit cache key by argument value
    _ = variant_id
    return render_data_card(base_path, raw_json, is_boss, no_edits)


@st.cache_data(show_spinner=False)
def render_behavior_card_cached(
    base_path: str,
    behavior_json: Dict[str, Any],
    is_boss: bool,
    base_card: Optional[bytes] = None,
    variant_id: Optional[str] = None,
) -> bytes:
    """
    Cached wrapper for render_behavior_card(...). Returns PNG bytes.
    Cache key includes a stable hash of behavior_json and variant.
    """
    _ = _hash_json(behavior_json)  # incorporated into Streamlit cache key by argument value
    _ = variant_id
    return render_behavior_card(base_path, behavior_json, is_boss=is_boss, base_card=base_card)


@st.cache_data(show_spinner=False)
def render_behavior_deck_cached(deck_key: str, cards: List[Dict[str, Any]]) -> List[bytes]:
    """
    Pre-render and cache a complete deck as a list of PNG bytes, in draw order.

    Each item in 'cards' should be a dict with at least:
      - kind: "data" | "behavior"
      - base_path: str
      - json: dict              (raw_json for data; behavior_json for behavior)
      - is_boss: bool
      - no_edits: bool          (only for kind == "data"; optional otherwise)
      - base_card: Optional[bytes]  (only for kind == "behavior" when using a pre-rendered data card)
      - variant_id: Optional[str]

    The 'deck_key' should be a stable identifier for the deck composition, e.g.:
        f"{boss}_{difficulty}_{heatup}_{seed}"
    Changing the key forces Streamlit to rebuild the deck cache once.
    """
    rendered: List[bytes] = []
    for item in cards:
        kind = item.get("kind")
        base_path = item.get("base_path")
        json_blob = item.get("json", {})
        is_boss = bool(item.get("is_boss", False))
        variant_id = item.get("variant_id")

        if kind == "data":
            no_edits = bool(item.get("no_edits", False))
            img_bytes = render_data_card_cached(base_path, json_blob, is_boss, no_edits, variant_id=variant_id)
        else:
            base_card = item.get("base_card")
            img_bytes = render_behavior_card_cached(base_path, json_blob, is_boss, base_card=base_card, variant_id=variant_id)

        rendered.append(img_bytes)

    return rendered


def _hash_json(obj: Any) -> str:
    try:
        s = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except TypeError:
        # Fallback for non-JSON-serializable objects: use repr
        s = repr(obj)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _draw_text(img: Image.Image, key: str, value: str, is_boss: bool):
    draw = ImageDraw.Draw(img)
    # choose coord key prefix
    prefix = "boss" if is_boss else "enemy"
    coord_key = f"{prefix}_{key}"
    if coord_key not in coords_map:
        return
    x, y = coords_map[coord_key]
    style = text_styles.get(key, {"size": 40, "fill": "white"})
    font = FONTS.get(key, ImageFont.load_default())
    draw.text((x, y), value, font=font, fill=style["fill"])


def _overlay_effect_icons(base: Image.Image, effects: list[str], slot: str, *, is_boss: bool):
    """Overlay up to two status effect icons for a given attack slot."""
    if not effects:
        return

    placement = coords_map["effects"]
    count = len(effects)
    count = min(count, 2)  # safety

    size_scale = 0.45 if count == 1 else 0.3

    if count == 1:
        x, y = placement[1].get(slot, (0, 0))
        effect = effects[0]
        icon_path = ICONS_DIR / f"{effect}.png"
        if not icon_path.exists():
            return
        icon = Image.open(icon_path).convert("RGBA")
        if size_scale != 1.0:
            w, h = icon.size
            icon = icon.resize((int(w * size_scale), int(h * size_scale)))
        base.alpha_composite(icon, (x, y))

    elif count == 2:
        for i, effect in enumerate(effects):
            coords = placement[2].get(slot)
            if not coords or i >= len(coords):
                continue
            x, y = coords[i]
            icon_path = ICONS_DIR / f"{effect}.png"
            if not icon_path.exists():
                continue
            icon = Image.open(icon_path).convert("RGBA")
            w, h = icon.size
            icon = icon.resize((int(w * size_scale), int(h * size_scale)))
            base.alpha_composite(icon, (x, y))


@st.cache_data(show_spinner=False)
def render_data_card(base_path: str, raw_json: dict, is_boss: bool, no_edits: bool=False) -> bytes:
    """
    Paint stats (health, armor, resist, maybe heatup) on the base data card.
    """
    base = Image.open(base_path).convert("RGBA")
    if no_edits:
        buf = io.BytesIO()
        base.save(buf, format="PNG")
        return buf.getvalue()

    # --- core stats ---
    if "armor" in raw_json:
        _draw_text(base, "armor", str(raw_json["armor"]), is_boss)
    if "health" in raw_json:
        _draw_text(base, "health", str(raw_json["health"]), is_boss)
    if "resist" in raw_json:
        _draw_text(base, "resist", str(raw_json["resist"]), is_boss)

    # --- boss-only: show heatup threshold if present ---
    if is_boss and isinstance(raw_json.get("heatup"), int):
        _draw_text(base, "heatup", str(raw_json["heatup"]), is_boss)

    # --- regular enemy: show dodge (comes from behavior.dodge) ---
    if not is_boss:
        beh = raw_json.get("behavior") or {}
        if "dodge" in beh:
            _draw_text(base, "dodge", str(beh["dodge"]), is_boss)
            return render_behavior_card(base_path, raw_json["behavior"], is_boss=False, base_card=base)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    return buf.getvalue()


def render_dual_boss_data_cards(raw_json: dict) -> tuple[bytes, bytes]:
    """
    Render the Ornstein & Smough dual-boss data cards separately, with stats applied.
    Returns two PNG byte arrays (one for Ornstein, one for Smough).
    """

    def _draw_stats(img: Image.Image, subdata: dict) -> Image.Image:
        """Draw armor, health, resist, etc., onto a single data card."""
        draw = ImageDraw.Draw(img)
        coords = {
            "armor": (350, 635),
            "health": (676, 95),
            "resist": (415, 635),
        }
        colors = {
            "armor": "white",
            "health": "white",
            "resist": "black",
        }
        for key, value in subdata.items():
            if key not in coords:
                continue
            x, y = coords[key]
            font = FONTS.get(key, ImageFont.load_default())
            draw.text((x, y), str(value), font=font, fill=colors.get(key, "white"))
        return img

    # Load Ornstein and Smough base data cards
    ornstein_img = Image.open("assets/behavior cards/Ornstein - data.jpg").convert("RGBA")
    smough_img   = Image.open("assets/behavior cards/Smough - data.jpg").convert("RGBA")

    # Draw their respective stats if available
    if "Ornstein" in raw_json:
        ornstein_img = _draw_stats(ornstein_img, raw_json["Ornstein"])
    if "Smough" in raw_json:
        smough_img = _draw_stats(smough_img, raw_json["Smough"])

    # Convert both to bytes for Streamlit
    buf_o, buf_s = io.BytesIO(), io.BytesIO()
    ornstein_img.save(buf_o, format="PNG")
    smough_img.save(buf_s, format="PNG")

    return buf_o.getvalue(), buf_s.getvalue()


@st.cache_data(show_spinner=False)
def render_behavior_card(base_path: str, behavior_json: dict, *, is_boss: bool, base_card: Image=None) -> bytes:
    """
    Take a behavior card image (e.g. 'Artorias - Heavy Thrust.jpg')
    and paint icons (left/middle/right) + repeat in the right place.
    """
    if base_card:
        base = base_card
    else:
        base = Image.open(base_path).convert("RGBA")

    # where to place repeat if behavior_json has a repeat
    repeat_icon_slot = "boss_repeat" if is_boss else "enemy_repeat"

    if is_boss:
        if "repeat" in behavior_json:
            icon_path = f"{ICONS_DIR}\\repeat_{behavior_json['repeat']}.png"
            icon = Image.open(icon_path).convert("RGBA")
            x, y = coords_map[repeat_icon_slot]
            base.alpha_composite(icon, (x, y))
        if "dodge" in behavior_json:
            _draw_text(base, "dodge", str(behavior_json["dodge"]), is_boss)

    for slot in ("left", "middle", "right"):
        if slot not in behavior_json:
            continue

        spec = behavior_json[slot]
        if not spec:
            continue

        icon_name = build_icon_filename(spec)
        if not icon_name:
            continue

        icon_path = ICONS_DIR / icon_name
        if not icon_path.exists():
            continue

        icon = Image.open(icon_path).convert("RGBA")

        if not is_boss and icon_name.startswith("repeat_"):
            x, y = coords_map["enemy_repeat"][slot]
            base.alpha_composite(icon, (x, y))
            continue

        slot_coords = coords_map.get(f"attack_{spec['type']}", {})
        if slot not in slot_coords:
            continue

        effects = spec.get("effect")
        if effects:
            _overlay_effect_icons(base, effects, slot, is_boss=is_boss)

        x, y = slot_coords[slot]
        base.alpha_composite(icon, (x, y))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    return buf.getvalue()


def render_dual_boss_behavior_card(raw_json: dict, card_name: str, boss_name: str = "Ornstein & Smough") -> bytes:
    """
    Draw Ornstein & Smough's combined behavior card.
    Each half (Ornstein / Smough) can have independent attacks and effects.
    """
    img_path = f"assets/behavior cards/{boss_name} - {card_name}.jpg"
    base = Image.open(img_path).convert("RGBA")

    div_idx = card_name.index("&")
    ornstein_beh = card_name[:div_idx-1]
    smough_beh = card_name[div_idx+2:]

    for boss_key, zone in [(ornstein_beh, "dual_ornstein"), (smough_beh, "dual_smough")]:
        data = raw_json[card_name].get(boss_key)
        _draw_dual_attack(base, data, zone)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    return buf.getvalue()


def _draw_dual_attack(base: Image.Image, data: dict, zone: str):
    """
    Overlay attack, repeat, and effect icons for one boss (Ornstein or Smough)
    on the dual card. Supports 'left' and 'right' slots.
    """
    zone_map = coords_map[zone]

    for slot in ["left", "right"]:
        slot_data = data.get(slot)
        if not slot_data:
            continue

        attack_type = slot_data.get("type")
        damage = slot_data.get("damage")
        repeat = slot_data.get("repeat", False)
        effects = slot_data.get("effect", [])

        # --- Attack icon ---
        if attack_type and damage:
            atk_icon_path = ICONS_DIR / f"attack_{attack_type}_{damage}.png"
            if atk_icon_path.exists():
                coords = zone_map.get(f"attack_{attack_type}", {}).get(slot)
                if coords:
                    icon = Image.open(atk_icon_path).convert("RGBA")
                    base.alpha_composite(icon, coords)

        # --- Repeat icon ---
        if repeat:
            rpt_coords = zone_map.get("repeat", {}).get(slot)
            rpt_icon = ICONS_DIR / "repeat.png"
            if rpt_coords and rpt_icon.exists():
                icon = Image.open(rpt_icon).convert("RGBA")
                base.alpha_composite(icon, rpt_coords)

        # --- Effects ---
        if effects:
            size_scale = 0.45 if count == 1 else 0.3
            count = len(effects)
            if count == 1:
                eff_coords = zone_map.get("effect_one", {}).get(slot)
                eff_icon_path = ICONS_DIR / f"{effects[0]}.png"
                if eff_coords and eff_icon_path.exists():
                    icon = Image.open(eff_icon_path).convert("RGBA")
                    if size_scale != 1.0:
                        w, h = icon.size
                        icon = icon.resize((int(w * size_scale), int(h * size_scale)))
                    base.alpha_composite(icon, eff_coords)
            else:
                eff_coords_list = zone_map.get("effect_two", {}).get(slot, [])
                for i, eff in enumerate(effects[:2]):
                    if i >= len(eff_coords_list):
                        break
                    x, y = eff_coords_list[i]
                    eff_icon_path = ICONS_DIR / f"{eff}.png"
                    if eff_icon_path.exists():
                        icon = Image.open(eff_icon_path).convert("RGBA")
                        if size_scale != 1.0:
                            w, h = icon.size
                            icon = icon.resize((int(w * size_scale), int(h * size_scale)))
                        base.alpha_composite(icon, (x, y))


@st.cache_resource(show_spinner=False)
def load_behavior_base(path: str) -> Image.Image:
    """Load and cache a base behavior/data card image as RGBA."""
    if _load_jpg_cached:
        return _load_jpg_cached(path).convert("RGBA")
    return Image.open(path).convert("RGBA")


@st.cache_resource(show_spinner=False)
def load_behavior_icon(filename: str) -> Image.Image:
    """Load and cache a behavior icon (PNG) from assets/behavior icons."""
    from pathlib import Path as _P
    full = _P("assets/behavior icons") / filename
    if _load_png_cached:
        return _load_png_cached(full)
    return Image.open(full).convert("RGBA")


@st.cache_resource(show_spinner=False)
def load_font(size: int = 32) -> ImageFont.FreeTypeFont:
    """Load and cache OptimusPrinceps font at a given size."""
    return ImageFont.truetype("assets/OptimusPrinceps.ttf", size)
