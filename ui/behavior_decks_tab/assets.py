from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageEnhance


BEHAVIOR_CARDS_PATH = Path("assets/behavior_cards")
CARD_BACK = BEHAVIOR_CARDS_PATH / "back.jpg"


@lru_cache(maxsize=None)
def get_behavior_card_path(name: str) -> Path:
    return BEHAVIOR_CARDS_PATH / f"{name}.jpg"


def dim_greyscale(img: Image.Image) -> Image.Image:
    img = img.convert("LA")
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(0.6)
