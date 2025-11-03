from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import io

ASSETS_DIR = Path("assets")
ICONS_DIR = ASSETS_DIR / "behavior icons"
FONT_PATH = ASSETS_DIR / "OptimusPrinceps.ttf"

# -----------------------------------------------------------
# COORDS
#   - enemy_* : regular enemy placements
#   - boss_*  : invaders/bosses
#   - repeat  : separate because bosses place it differently
# -----------------------------------------------------------
coords_map = {
    "attack_physical": {
        "left": (44, 737),
        "middle": (291, 737),
        "right": (440, 737),
    },
    "attack_magic": {
        "left": (40, 735),
        "middle": (287, 735),
        "right": (440, 735),
    },
    "attack_push": {
        "left": (40, 735),
        "middle": (287, 735),
        "right": (440, 735),
    },
    "effects": {
        1: {"left": (70, 750), "middle": (430, 880), "right": (520, 750)},
        2: {
            "left": [(50, 740), (90, 770)],
            "middle": [(455, 875), (420, 920)],
            "right": [(500, 740), (550, 770)]
        }
    },

    # -------- STATS: enemy data card --------
    "enemy_armor": (350, 615),
    "enemy_health": (689, 96),
    "enemy_resist": (415, 615),
    "enemy_dodge": (710, 605),

    # -------- STATS: boss/invader data card --------
    # put them wherever your boss data card has the boxes
    "boss_armor": (350, 635),
    "boss_health": (676, 95),
    "boss_resist": (415, 635),
    "boss_heatup": (655, 640),

    # -------- REPEAT ICONS --------
    # regular enemy repeat
    "enemy_repeat": {
        "middle": (344, 786),
        "right": (440, 320),
    },
    # boss / invader repeat
    "boss_repeat": (344, 588),
    "boss_dodge": (710, 605),
    
    # Ornstein & Smough
    "dual_ornstein": {
        "attack_physical": {
            "left": (150, 180),
            "right": (440, 180),
        },
        "attack_magic": {
            "left": (150, 180),
            "right": (440, 180),
        },
        "attack_push": {
            "left": (150, 180),
            "right": (440, 180),
        },
        "repeat": {
            "left": (100, 240),
            "right": (500, 240),
        },
        "effect_one": {
            "left": (170, 260),
            "right": (480, 260),
        },
        "effect_two": {
            "left": [(150, 250), (190, 290)],
            "right": [(460, 250), (500, 290)],
        },
    },
    "dual_smough": {
        "attack_physical": {
            "left": (150, 820),
            "right": (440, 820),
        },
        "attack_magic": {
            "left": (150, 820),
            "right": (440, 820),
        },
        "attack_push": {
            "left": (150, 180),
            "right": (440, 180),
        },
        "repeat": {
            "left": (100, 880),
            "right": (500, 880),
        },
        "effect_one": {
            "left": (170, 900),
            "right": (480, 900),
        },
        "effect_two": {
            "left": [(150, 890), (190, 930)],
            "right": [(460, 890), (500, 930)],
        },
    }
}

# -----------------------------------------------------------
# TEXT STYLES (you can keep the same for boss)
# -----------------------------------------------------------
text_styles = {
    "armor":  {"size": 85, "fill": "white"},
    "health": {"size": 60, "fill": "white"},
    "resist": {"size": 85, "fill": "black"},
    "dodge":  {"size": 70, "fill": "black"},
    "heatup": {"size": 60, "fill": "black"},
}

def _load_fonts():
    try:
        return {
            name: ImageFont.truetype(str(FONT_PATH), style["size"])
            for name, style in text_styles.items()
        }
    except Exception:
        return {name: ImageFont.load_default() for name in text_styles}

FONTS = _load_fonts()


# -----------------------------------------------------------
# Icon name builder
# -----------------------------------------------------------
def build_icon_filename(spec: dict) -> str | None:
    t = spec.get("type")
    dmg = spec.get("damage")
    repeat = spec.get("repeat")

    if repeat:
        return f"repeat_{repeat}.png"

    if not t:
        return None

    if t in ("physical", "magic", "push"):
        return f"attack_{t}_{dmg}.png"
    else:
        # status effects (bleed, stagger, etc.)
        return f"{t}.png"


# -----------------------------------------------------------
# COMMON: draw a single text value
# -----------------------------------------------------------
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


# -----------------------------------------------------------
# COMMON: overlay status effects
# -----------------------------------------------------------
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


# -----------------------------------------------------------
# DATA CARD RENDERING
# -----------------------------------------------------------
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
    ornstein_img = Image.open(ASSETS_DIR / "behavior cards" / "Ornstein - data.jpg").convert("RGBA")
    smough_img   = Image.open(ASSETS_DIR / "behavior cards" / "Smough - data.jpg").convert("RGBA")

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


# -----------------------------------------------------------
# BEHAVIOR CARD RENDERING
#  - boss/invader AND regular enemy use the same behavior JSON shape
#  - only coords differ (enemy vs boss)
# -----------------------------------------------------------
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
    img_path = ASSETS_DIR / "behavior cards" / f"{boss_name} - {card_name}.jpg"
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
