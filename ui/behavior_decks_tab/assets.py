import io
import re
from PIL import Image, ImageFont, ImageOps
from pathlib import Path


BEHAVIOR_CARDS_PATH = "assets/behavior cards/"
ICONS_DIR = Path("assets/behavior icons")
CARD_BACK = Path("assets/behavior cards/back.jpg")
FONT_PATH_NUMBER = Path("assets/OptimusPrinceps.ttf")
FONT_PATH_TEXT = Path("assets/AdobeCaslonProSemibold.ttf")
CATEGORY_ORDER = [
    "Regular Enemies",
    "Invaders",
    "Mini Bosses",
    "Main Bosses",
    "Mega Bosses",
]
CATEGORY_EMOJI = {
    "Regular Enemies": "🗡️",
    "Invaders":        "👤",
    "Mini Bosses":     "⚔️",
    "Main Bosses":     "🐺",
    "Mega Bosses":     "🐉",
}
BOSS_CATEGORY_MAP = {
    # Mini bosses
    "Asylum Dmon": "Mini Bosses",
    "Black Knight": "Mini Bosses",
    "Boreal Outrider Knight": "Mini Bosses",
    "Gargoyle": "Mini Bosses",
    "Heavy Knight": "Mini Bosses",
    "Old Dragonslayer": "Mini Bosses",
    "Titanite Demon": "Mini Bosses",
    "Winged Knight": "Mini Bosses",

    # Main bosses
    "Artorias": "Main Bosses",
    "Crossbreed Priscilla": "Main Bosses",
    "Dancer of the Boreal Valley": "Main Bosses",
    "Gravelord Nito": "Main Bosses",
    "Great Grey Wolf Sif": "Main Bosses",
    "Ornstein & Smough": "Main Bosses",
    "Sir Alonne": "Main Bosses",
    "Smelter Demon": "Main Bosses",
    "The Puruser": "Main Bosses",

    # Mega bosses
    "Black Dragon Kalameet": "Mega Bosses",
    "Executioner Chariot": "Mega Bosses",
    "Gaping Dragon": "Mega Bosses",
    "Guardian Dragon": "Mega Bosses",
    "Manus, Father of the Abyss": "Mega Bosses",
    "Old Iron King": "Mega Bosses",
    "Stray Demon": "Mega Bosses",
    "The Four Kings": "Mega Bosses",
    "The Last Giant": "Mega Bosses",
    "Vordt of the Boreal Valley": "Mega Bosses",
}

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
    "text": (100, 100),

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
    "armor":  {"size": 85, "fill": "white", "font": FONT_PATH_NUMBER},
    "health": {"size": 60, "fill": "white", "font": FONT_PATH_NUMBER},
    "resist": {"size": 85, "fill": "black", "font": FONT_PATH_NUMBER},
    "dodge":  {"size": 70, "fill": "black", "font": FONT_PATH_NUMBER},
    "heatup": {"size": 60, "fill": "black", "font": FONT_PATH_NUMBER},
    "text":   {"size": 33, "fill": "black", "font": FONT_PATH_TEXT}
}


def _load_fonts():
    try:
        return {
            name: ImageFont.truetype(str(style["font"]), style["size"])
            for name, style in text_styles.items()
        }
    except Exception:
        return {name: ImageFont.load_default() for name in text_styles}
    

FONTS = _load_fonts()


def _behavior_image_path(cfg, behavior_name: str) -> str:
    """Map a behavior name (or pair of names) to its corresponding image path(s)."""
    if isinstance(behavior_name, tuple):
        # Return list of paths for both movement & attack cards
        paths = []
        for name in behavior_name:
            clean_name = _strip_behavior_suffix(str(name))
            paths.append(f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg")
        return paths
    else:
        clean_name = _strip_behavior_suffix(str(behavior_name))
        return f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg"


def _strip_behavior_suffix(name: str) -> str:
    """
    Strip numeric or trailing copy markers from behavior names.
    Example:
        "Stomach Slam 1" -> "Stomach Slam"
        "Stomach Slam 2" -> "Stomach Slam"
        "Death Race 4"   -> "Death Race"
    """
    return re.sub(r"\s+\d+$", "", name.strip())


def card_image_path(boss_name: str, behavior_name: str) -> str:
    """Map a behavior name to its card image path."""
    return _path(f"{boss_name} - {behavior_name}.jpg")


def _path(img_rel: str) -> str:
    return str(Path("assets") / "behavior cards" / img_rel)
    

def _dim_greyscale(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    gray = ImageOps.grayscale(img).convert("RGBA")
    # darken a bit for clarity
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 110))
    out = Image.alpha_composite(gray, overlay)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


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
