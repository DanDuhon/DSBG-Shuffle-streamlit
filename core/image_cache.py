
"""
core.image_cache
-----------------
Centralized image loading and caching utilities for Dark Souls: The Board Game Streamlit app.

Provides disk-persistent caching for:
- Encounter cards (original & edited)
- Enemy icons
- Character icons
- Expansion icons
"""

from pathlib import Path
from PIL import Image
import streamlit as st

# -------------------------------------------------------------
# Paths and cache directories
# -------------------------------------------------------------
ASSETS = Path("assets")
CACHE_ROOT = Path("data/.cache")
CACHE_DIRS = {
    "base_cards": CACHE_ROOT / "base_cards",
    "edited_cards": CACHE_ROOT / "edited_cards",
    "icons": CACHE_ROOT / "icons",
    "characters": CACHE_ROOT / "characters",
    "expansions": CACHE_ROOT / "expansions",
}
for d in CACHE_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------
# Generic cached loaders
# -------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _load_jpg_cached(src_path: Path, cache_dir: Path) -> Image.Image:
    """Load a JPG image from assets or disk cache."""
    dst = cache_dir / src_path.name
    if dst.exists():
        try:
            return Image.open(dst).convert("RGB")
        except Exception:
            dst.unlink(missing_ok=True)
    if src_path.exists():
        img = Image.open(src_path).convert("RGB")
        img.save(dst, format="JPEG")
        return img
    raise FileNotFoundError(f"Missing JPG image: {src_path}")


@st.cache_resource(show_spinner=False)
def _load_png_cached(src_path: Path, cache_dir: Path) -> Image.Image:
    """Load a PNG image from assets or disk cache."""
    dst = cache_dir / src_path.name
    if dst.exists():
        try:
            return Image.open(dst).convert("RGBA")
        except Exception:
            dst.unlink(missing_ok=True)
    if src_path.exists():
        img = Image.open(src_path).convert("RGBA")
        img.save(dst, format="PNG")
        return img
    raise FileNotFoundError(f"Missing PNG image: {src_path}")


# -------------------------------------------------------------
# Public cached loaders
# -------------------------------------------------------------
def load_base_card(encounter_name: str, use_edited: bool) -> Image.Image:
    """Load base encounter card (JPG)."""
    folder = "edited encounter cards" if use_edited else "encounter cards"
    src_path = ASSETS / folder / f"{encounter_name}.jpg"
    cache_dir = CACHE_DIRS["edited_cards" if use_edited else "base_cards"]
    return _load_jpg_cached(src_path, cache_dir)


def load_enemy_icon(enemy_name: str) -> Image.Image:
    """Load enemy icon (PNG)."""
    src_path = ASSETS / "enemy icons" / f"{enemy_name}.png"
    return _load_png_cached(src_path, CACHE_DIRS["icons"])


def load_character_icon(name: str) -> Image.Image:
    """Load character icon (PNG)."""
    src_path = ASSETS / "characters" / f"{name}.png"
    return _load_png_cached(src_path, CACHE_DIRS["characters"])


def load_expansion_icon(name: str) -> Image.Image:
    """Load expansion icon (PNG)."""
    src_path = ASSETS / "expansions" / f"{name}.png"
    return _load_png_cached(src_path, CACHE_DIRS["expansions"])
