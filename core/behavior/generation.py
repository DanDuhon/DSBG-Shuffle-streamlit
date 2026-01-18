# ui/behavior_decks_tab/generation.py
import streamlit as st
import json
import hashlib
import io
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Dict, Any, Optional
from collections import defaultdict

from core.behavior.assets import (
    ICONS_DIR,
    FONTS,
    coords_map,
    text_styles,
    FONT_PATH_NUMBER,
    FONT_PATH_DEJAVU,
    build_icon_filename,
    CATEGORY_ORDER,
    BOSS_CATEGORY_MAP,
)
from core.image_cache import load_pil_image_cached
from core.behavior.models import BehaviorEntry
from core.behavior.logic import load_behavior, list_behavior_files
from core.ngplus import get_current_ngplus_level


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
    _ = _hash_json(
        behavior_json
    )  # incorporated into Streamlit cache key by argument value
    _ = variant_id
    return render_behavior_card(
        base_path, behavior_json, is_boss=is_boss, base_card=base_card
    )


def infer_category(cfg) -> str:
    """
    Map a BehaviorConfig to one of our UI categories using:
      - is_invader flag
      - 'enemy' vs boss tier
      - explicit boss name mapping
    """
    # 1) Invaders override everything
    if getattr(cfg, "is_invader", False):
        return "Invaders"

    # 2) Regular enemies: configurations with 'behavior' at top level are
    #    treated as single-enemy configs and give tier 'enemy'.:contentReference[oaicite:1]{index=1}
    if cfg.tier == "enemy":
        return "Regular Enemies"

    # 3) Bosses: use explicit mapping
    return BOSS_CATEGORY_MAP.get(cfg.name, "Main Bosses")


@st.cache_data(show_spinner=False)
def build_behavior_catalog() -> dict[str, list[BehaviorEntry]]:
    """Scan behavior JSON files and group them by category for the UI.

    Cached with Streamlit so repeated UI reruns don't re-scan disk.
    """
    files = (
        list_behavior_files()
    )  # returns Paths to *.json:contentReference[oaicite:2]{index=2}
    groups: dict[str, list[BehaviorEntry]] = defaultdict(list)

    for fpath in files:
        cfg = load_behavior(
            fpath
        )  # BehaviorConfig:contentReference[oaicite:3]{index=3}
        category = infer_category(cfg)

        entry = BehaviorEntry(
            name=cfg.name,
            category=category,
            path=fpath,
            tier=cfg.tier,
            is_invader=cfg.is_invader,
            order_num=getattr(cfg, "raw", {}).get("order_num", 10),
        )
        groups[category].append(entry)

    for entries in groups.values():
        entries.sort(key=lambda e: e.name)

    for cat in CATEGORY_ORDER:
        groups.setdefault(cat, [])

    return groups


def _hash_json(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _draw_text(img: Image.Image, key: str, value: str, is_boss: bool):
    draw = ImageDraw.Draw(img)
    # choose coord key prefix
    prefix = "boss" if is_boss else "enemy"
    coord_key = f"{prefix}_{key}"
    # If health is non-numeric (e.g. "∞") or >=10, use the larger/boss
    # health coordinates so the text fits. Be defensive: try converting
    # to int, but fall back to a large value for non-numeric strings.
    is_non_numeric = False
    if coord_key == "enemy_health":
        val_int = int(value)
        if val_int >= 10:
            coord_key = "boss_health"
    if coord_key not in coords_map:
        return
    x, y = coords_map[coord_key]
    style = text_styles.get(key, {"size": 40, "fill": "white", "font": FONT_PATH_NUMBER})
    # If this is a health value and non-numeric (e.g. "∞") render it larger
    # and center it on the target coords so it sits visibly inside the heart icon.
    if key == "health" and is_non_numeric:
        # If user provided a specific icon for infinite health, overlay it
        # centered on the heart. If the icon is missing the exists check
        # prevents an attempt to load it; any unexpected exceptions will
        # propagate so they are visible during development.
        icon_path = ICONS_DIR / "infinite_health.png"
        if icon_path.exists():
            icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
            # Limit icon size so it fits inside the heart
            max_dim = 96
            iw, ih = icon.size
            scale = min(1.0, max_dim / max(iw, ih))
            if scale < 1.0:
                icon = icon.resize((int(iw * scale), int(ih * scale)), resample=Image.LANCZOS)
            w, h = icon.size
            tx = int(x - w // 2) + 23
            ty = int(y - h // 2) + 27
            img.alpha_composite(icon, (tx, ty))
            return

    font = FONTS.get(key, ImageFont.load_default())
    draw.text((x, y), value, font=font, fill=style["fill"])


def _overlay_effect_icons(
    base: Image.Image, effects: list[str], slot: str, *, is_boss: bool
):
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
        icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
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
            icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
            w, h = icon.size
            icon = icon.resize((int(w * size_scale), int(h * size_scale)))
            base.alpha_composite(icon, (x, y))


def _overlay_push_node_icon(
    base: Image.Image,
    slot: str,
    *,
    is_boss: bool,
    kind: str,  # "push" or "node"
) -> None:
    """
    Draw a push/node marker for a given attack slot.

    Looks for coords in:
      - coords_map["boss_push"] / coords_map["boss_node"] for bosses
      - coords_map["enemy_push"] / coords_map["enemy_node"] for enemies
    falling back to coords_map["push"] / coords_map["node"] if those exist.
    """
    assert kind in ("push", "node")

    prefix = "boss" if is_boss else "enemy"
    coord_map = coords_map.get(f"{prefix}_{kind}") or coords_map.get(kind)
    if not coord_map:
        return

    xy = coord_map.get(slot)
    if not xy:
        return
    x, y = xy

    icon_filename = f"{kind}.png"  # e.g., push.png / node.png
    icon_path = ICONS_DIR / icon_filename
    if not icon_path.exists():
        return

    icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
    base.alpha_composite(icon, (x, y))


@st.cache_data(show_spinner=False)
def render_data_card(
    base_path: str, raw_json: dict, is_boss: bool, no_edits: bool = False
) -> bytes:
    """
    Paint stats (health, armor, resist, maybe heatup) on the base data card.
    """
    base = load_pil_image_cached(base_path, convert="RGBA").copy()
    if no_edits:
        buf = io.BytesIO()
        base.save(buf, format="PNG")
        return buf.getvalue()

    # Special-cases: Adjust text to include NG+ level
    # and render it at specific coords with Adobe Caslon Pro Regular.ttf size 33
    try:
        bp_stem = Path(base_path).stem
    except Exception:
        bp_stem = str(base_path)
    if "Paladin Leeroy" in bp_stem:
        level = get_current_ngplus_level()
        text = f"The first time Leeroy's health would be\nreduced to 0, set his health to {2 + level} instead."
        draw = ImageDraw.Draw(base)
        font_path = Path("assets/Adobe Caslon Pro Regular.ttf")
        font = ImageFont.truetype(str(font_path), 33)
        draw.text((97, 855), text, font=font, fill="black")
    elif "Maneater Mildred" in bp_stem:
        level = get_current_ngplus_level()
        heal = 1 if level <= 2 else 2 if level <= 4 else 3
        text = f"If Mildred's attack damages one or more\ncharacters, she gains {heal} health."
        draw = ImageDraw.Draw(base)
        font_path = Path("assets/Adobe Caslon Pro Regular.ttf")
        font = ImageFont.truetype(str(font_path), 33)
        draw.text((97, 855), text, font=font, fill="black")

    # --- core stats ---
    if "armor" in raw_json:
        _draw_text(base, "armor", str(raw_json["armor"]), is_boss)
    if "health" in raw_json:
        _draw_text(base, "health", str(raw_json["health"]), is_boss)
    if "resist" in raw_json:
        _draw_text(base, "resist", str(raw_json["resist"]), is_boss)
    if "text" in raw_json:
        _draw_text(base, "text", str(raw_json["text"]), is_boss)
    if "range" in raw_json:
        # If this behavior explicitly defines a range (e.g., range 0),
        # write it onto the card using the coords_map entry for range.
        # Expects coords_map["boss_range"] / coords_map["enemy_range"] to exist.
        _draw_text(base, "range", str(raw_json["range"]), is_boss)

    # --- boss-only: show heatup threshold if present ---
    if is_boss and isinstance(raw_json.get("heatup"), int):
        _draw_text(base, "heatup", str(raw_json["heatup"]), is_boss)
    if is_boss and isinstance(raw_json.get("heatup1"), int):
        _draw_text(base, "heatup1", str(raw_json["heatup1"]), is_boss)
        _draw_text(base, "heatup2", str(raw_json["heatup2"]), is_boss)

    # --- regular enemy: show dodge (comes from behavior.dodge) ---
    if not is_boss:
        beh = raw_json.get("behavior") or {}
        if "dodge" in beh:
            _draw_text(base, "dodge", str(beh["dodge"]), is_boss)
            return render_behavior_card(
                base_path, raw_json["behavior"], is_boss=False, base_card=base
            )

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
    ornstein_img = load_pil_image_cached(
        "assets/behavior cards/Ornstein - data.jpg", convert="RGBA"
    ).copy()
    smough_img = load_pil_image_cached(
        "assets/behavior cards/Smough - data.jpg", convert="RGBA"
    ).copy()

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
def render_behavior_card(
    base_path: str, behavior_json: dict, *, is_boss: bool, base_card: Image = None
) -> bytes:
    """
    Take a behavior card image (e.g. 'Artorias - Heavy Thrust.jpg')
    and paint icons (left/middle/right) + repeat in the right place.
    """
    if base_card:
        base = base_card
    else:
        base = load_pil_image_cached(base_path, convert="RGBA").copy()

    # where to place repeat if behavior_json has a repeat
    repeat_icon_slot = "boss_repeat" if is_boss else "enemy_repeat"

    if is_boss:
        if "repeat" in behavior_json:
            icon_path = f"{ICONS_DIR}\\repeat_{behavior_json['repeat']}.png"
            icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
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

        icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()

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

        # --- Push / Node overlays ---
        # Allow push/node markers for moves as well as physical/magic attacks.
        # Movement specs may include `push` as either a boolean or an int damage value.
        if spec.get("push") and spec.get("type") in {"physical", "magic", "move"}:
            _overlay_push_node_icon(base, slot, is_boss=is_boss, kind="push")

        if spec.get("node") and spec.get("type") in {"physical", "magic", "move"}:
            _overlay_push_node_icon(base, slot, is_boss=is_boss, kind="node")

        # If this is a movement that also deals push damage (e.g. "push": 4),
        # try to overlay the attack_push_{damage}.png icon as well so the damage
        # value is visible. Place it using the attack_push coords.
        if spec.get("type") == "move" and isinstance(spec.get("push"), int):
            push_dmg = spec["push"]
            push_icon_path = ICONS_DIR / f"attack_push_{push_dmg}.png"
            push_coords_map = coords_map.get("attack_push", {})
            if push_icon_path.exists() and slot in push_coords_map:
                px, py = push_coords_map[slot]
                push_icon = load_pil_image_cached(str(push_icon_path), convert="RGBA").copy()
                base.alpha_composite(push_icon, (px, py))

        x, y = slot_coords[slot]
        base.alpha_composite(icon, (x, y))

    # --- Special-case overlay for The Fountainhead enemy behavior cards ---
    if not is_boss and behavior_json.get("_fountainhead_icon"):
        icon_path = ICONS_DIR / "move_away_closest_1.png"
        if icon_path.exists():
            fh_icon = load_pil_image_cached(str(icon_path), convert="RGBA").copy()
            x, y = 565, 755
            base.alpha_composite(fh_icon, (x, y))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    return buf.getvalue()


def render_dual_boss_behavior_card(
    raw_json: dict, card_name: str, boss_name: str = "Ornstein & Smough"
) -> bytes:
    """
    Draw Ornstein & Smough's combined behavior card.
    Each half (Ornstein / Smough) can have independent attacks and effects.
    """
    img_path = f"assets/behavior cards/{boss_name} - {card_name}.jpg"
    base = load_pil_image_cached(img_path, convert="RGBA").copy()

    div_idx = card_name.index("&")
    ornstein_beh = card_name[: div_idx - 1]
    smough_beh = card_name[div_idx + 2 :]

    for boss_key, zone in [
        (ornstein_beh, "dual_ornstein"),
        (smough_beh, "dual_smough"),
    ]:
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
                    icon = load_pil_image_cached(
                        str(atk_icon_path), convert="RGBA"
                    ).copy()
                    base.alpha_composite(icon, coords)

        # --- Repeat icon ---
        if repeat:
            rpt_coords = zone_map.get("repeat", {}).get(slot)
            rpt_icon = ICONS_DIR / "repeat.png"
            if rpt_coords and rpt_icon.exists():
                icon = load_pil_image_cached(str(rpt_icon), convert="RGBA").copy()
                base.alpha_composite(icon, rpt_coords)

        # --- Effects ---
        if effects:
            size_scale = 0.45 if count == 1 else 0.3
            count = len(effects)
            if count == 1:
                eff_coords = zone_map.get("effect_one", {}).get(slot)
                eff_icon_path = ICONS_DIR / f"{effects[0]}.png"
                if eff_coords and eff_icon_path.exists():
                    icon = load_pil_image_cached(
                        str(eff_icon_path), convert="RGBA"
                    ).copy()
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
                        icon = load_pil_image_cached(
                            str(eff_icon_path), convert="RGBA"
                        ).copy()
                        if size_scale != 1.0:
                            w, h = icon.size
                            icon = icon.resize(
                                (int(w * size_scale), int(h * size_scale))
                            )
                        base.alpha_composite(icon, (x, y))
