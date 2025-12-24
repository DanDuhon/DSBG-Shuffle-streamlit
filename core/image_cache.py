
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
import base64

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


# -------------------------------------------------------------
# Bytes helper (cached by file mtime)
# -------------------------------------------------------------
def _stat_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except Exception:
        return 0


@st.cache_data(show_spinner=False)
def _get_image_bytes_cached(path_str: str, mtime_ns: int) -> bytes:
    """Internal cached reader keyed by (path, mtime).

    Returns raw file bytes. If the file is an image, returns its bytes as-is.
    """
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Missing image: {p}")
    return p.read_bytes()


def get_image_bytes_cached(path: str) -> bytes:
    """Public helper: return file bytes for `path`, invalidating cache on file change."""
    p = Path(path)
    return _get_image_bytes_cached(str(p), _stat_mtime_ns(p))


@st.cache_data(show_spinner=False)
def bytes_to_data_uri(data: bytes, mime: str = "image/png") -> str:
    """Convert raw bytes to a data URI (cached by content hash).

    `data` can be any image bytes; `mime` should be set to the correct
    content-type (e.g., 'image/png' or 'image/jpeg').
    """
    if not data:
        return ""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def get_image_data_uri_cached(path: str) -> str:
    """Return a `data:<mime>;base64,...` URI for `path`, cached and invalidated on file change."""
    p = Path(path)
    try:
        data = get_image_bytes_cached(str(p))
    except Exception:
        return ""
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return bytes_to_data_uri(data, mime=mime)
