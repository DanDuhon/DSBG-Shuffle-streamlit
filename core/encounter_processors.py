from PIL import Image
from core.image_cache import load_base_card, load_enemy_icon


def get_enemy_positions(encounter_data):
    """
    Extract enemy positions from encounter data.
    This is a stub that mirrors your current internal placement logic.
    Later, move your real position computation here so it can be reused and cached.
    """
    positions = []
    enemies = encounter_data.get("enemies", [])
    for enemy in enemies:
        if isinstance(enemy, dict) and "position" in enemy:
            positions.append(tuple(enemy["position"]))
        else:
            positions.append((0, 0))
    return positions


def compose_enemies(base_img: Image.Image, enemies: list, encounter_data: dict) -> Image.Image:
    """
    Composite enemy icons onto a base encounter card in memory.
    This function does NOT perform any file I/O beyond cached asset reads.
    """
    img = base_img.convert("RGBA").copy()
    positions = get_enemy_positions(encounter_data)

    for idx, enemy in enumerate(enemies):
        pos = positions[idx] if idx < len(positions) else (0, 0)
        try:
            enemy_name = enemy["name"] if isinstance(enemy, dict) else enemy
            icon_img = load_enemy_icon(enemy_name)
            img.alpha_composite(icon_img, pos)
        except FileNotFoundError:
            print(f"⚠️ Missing icon for enemy: {enemy}")
        except Exception as e:
            print(f"⚠️ Error placing enemy {enemy}: {e}")
    return img


def generate_encounter_image(expansion, level, name, encounter_data, enemies, use_edited):
    """
    Create a composited encounter image (returns PIL.Image).
    Uses cached loaders and performs all composition in memory.
    """
    base_card = load_base_card(name, use_edited)
    composed = compose_enemies(base_card, enemies, encounter_data)
    return composed
