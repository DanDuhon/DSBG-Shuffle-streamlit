from PIL import Image
from pathlib import Path

from core.enemyNames import enemyNames


ENEMY_ICONS_DIR = Path(__file__).parent.parent / "assets" / "enemy icons"

# Registry: maps "Expansion|Encounter Name" → processor function
PROCESSORS = {}


def paste_enemy_icon(img, enemy_id, x, y, size=30):
    """
    Paste an enemy icon onto the card image at (x, y).
    - enemy_id: ID of the enemy, lookup will matche a file in assets/enemies/<enemy_name>.png
    - size: target size in pixels (square)
    """
    try:
        icon_path = ENEMY_ICONS_DIR / f"{enemyNames[enemy_id]}.png"
        if not icon_path.exists():
            print(f"[WARN] Enemy icon not found: {icon_path}")
            return img
        
        icon = Image.open(icon_path).convert("RGBA")

        # Size the image down based on the longer side.
        width, height = icon.size
        s = size / (width if width > height else height)
        icon_size = (int(round(width * s)), int(round(height * s)))
        icon = icon.resize(icon_size, Image.Resampling.LANCZOS)

        # This is used to center the icon no matter its width or height.
        xOffset = int(round((size - icon_size[0]) / 2))
        yOffset = int(round((size - icon_size[1]) / 2))
        coords = (x + xOffset, y + yOffset)

        img.paste(icon, coords, icon)  # use alpha channel
    except Exception as e:
        print(f"[ERROR] Could not paste enemy icon {enemyNames[enemy_id]}: {e}")

    return img


def register(encounter_key):
    """Decorator to register a processor for an encounter."""
    def decorator(func):
        PROCESSORS[encounter_key] = func
        return func
    return decorator

def apply_processor(img, expansion, encounter_name, enemies):
    """Apply custom processing if a processor exists for this encounter."""
    key = f"{expansion}|{encounter_name}"
    if key in PROCESSORS:
        return PROCESSORS[key](img, enemies)
    return img


@register("Painted World of Ariamis|No Safe Haven")
def process_no_safe_haven(img, enemies):
    return paste_enemy_icon(img, enemies[-1], x=125, y=297)
