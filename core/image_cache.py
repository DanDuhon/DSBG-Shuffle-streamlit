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
import io
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
        return Image.open(dst).convert("RGB")
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
        return Image.open(dst).convert("RGBA")
    if src_path.exists():
        img = Image.open(src_path).convert("RGBA")
        img.save(dst, format="PNG")
        return img
    raise FileNotFoundError(f"Missing PNG image: {src_path}")


# -------------------------------------------------------------
# Bytes helper (cached by file mtime)
# -------------------------------------------------------------
def _stat_mtime_ns(path: Path) -> int:
    return int(path.stat().st_mtime_ns)


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
    data = get_image_bytes_cached(str(p))
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return bytes_to_data_uri(data, mime=mime)


# -------------------------------------------------------------
# PIL Image helpers (cached by file mtime)
# -------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _load_pil_image_cached_raw(
    path_str: str, mtime_ns: int, convert: str | None = None
) -> Image.Image:
    """Internal helper: load image bytes and return a PIL Image.

    Keyed by (path, mtime) so updates to the file invalidate the cache.
    """
    data = _get_image_bytes_cached(path_str, mtime_ns)
    img = Image.open(io.BytesIO(data))
    if convert:
        img = img.convert(convert)
    return img


def load_pil_image_cached(path: str, convert: str | None = "RGBA") -> Image.Image:
    """Public helper: return a PIL Image for `path` (cached).

    The returned Image should be copied by callers before mutating it.
    """
    p = Path(path)
    return _load_pil_image_cached_raw(str(p), _stat_mtime_ns(p), convert)
