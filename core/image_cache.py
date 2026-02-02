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
from PIL import Image, ImageOps
import io
import base64
from functools import lru_cache

from core.settings_manager import get_config_bool, is_streamlit_cloud


try:
    import streamlit as st  # type: ignore

    def cache_data(*args, **kwargs):
        return st.cache_data(*args, **kwargs)

    def cache_resource(*args, **kwargs):
        return st.cache_resource(*args, **kwargs)

except Exception:  # pragma: no cover
    st = None

    def cache_data(*_args, **_kwargs):
        def _decorator(fn):
            return lru_cache(maxsize=None)(fn)

        return _decorator

    def cache_resource(*_args, **_kwargs):
        def _decorator(fn):
            return lru_cache(maxsize=None)(fn)

        return _decorator

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
# Bytes helper (cached by file mtime)
# -------------------------------------------------------------

# Cache sizing
# Streamlit Cloud memory can be as low as ~690MB. Keep caches conservative on
# Cloud, while allowing a larger cache footprint for local runs.
try:
    _IS_CLOUD = bool(is_streamlit_cloud())
except Exception:
    _IS_CLOUD = False

if _IS_CLOUD:
    IMAGE_BYTES_CACHE_MAX_ENTRIES = 128
    IMAGE_BYTES_CACHE_TTL_SECONDS = 60 * 60
    PIL_IMAGE_CACHE_MAX_ENTRIES = 24
    PIL_IMAGE_CACHE_TTL_SECONDS = 60 * 60
    DATA_URI_CACHE_MAX_ENTRIES = 32
    DATA_URI_CACHE_TTL_SECONDS = 15 * 60

    THUMBNAIL_CACHE_MAX_ENTRIES = 256
    THUMBNAIL_CACHE_TTL_SECONDS = 60 * 60
    DEFAULT_THUMBNAIL_WIDTH_PX = 140
else:
    IMAGE_BYTES_CACHE_MAX_ENTRIES = 512
    IMAGE_BYTES_CACHE_TTL_SECONDS = 6 * 60 * 60
    PIL_IMAGE_CACHE_MAX_ENTRIES = 96
    PIL_IMAGE_CACHE_TTL_SECONDS = 6 * 60 * 60
    DATA_URI_CACHE_MAX_ENTRIES = 128
    DATA_URI_CACHE_TTL_SECONDS = 60 * 60

    THUMBNAIL_CACHE_MAX_ENTRIES = 1024
    THUMBNAIL_CACHE_TTL_SECONDS = 6 * 60 * 60
    DEFAULT_THUMBNAIL_WIDTH_PX = 200


def get_default_thumbnail_width_px() -> int:
    """Default thumbnail width (pixels).

    This is intentionally smaller on Streamlit Cloud to reduce per-session image
    decode/retention pressure when rendering large lists/grids.
    """

    return int(DEFAULT_THUMBNAIL_WIDTH_PX)


def _resample_filter():
    # Pillow compatibility shim (Resampling enum introduced in newer versions)
    try:
        return Image.Resampling.LANCZOS  # type: ignore[attr-defined]
    except Exception:
        return Image.LANCZOS


def _flatten_to_rgb(img: Image.Image, background_rgb: tuple[int, int, int]) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode not in ("RGBA", "LA"):
        img = img.convert("RGBA")
    bg = Image.new("RGB", img.size, color=background_rgb)
    bg.paste(img, mask=img.split()[-1])
    return bg


def _resize_to_width(img: Image.Image, max_width: int) -> Image.Image:
    if max_width <= 0:
        return img
    if img.width <= max_width:
        return img
    new_h = max(1, int(round(img.height * (max_width / float(img.width)))))
    return img.resize((int(max_width), new_h), resample=_resample_filter())


@cache_data(
    show_spinner=False,
    max_entries=THUMBNAIL_CACHE_MAX_ENTRIES,
    ttl=THUMBNAIL_CACHE_TTL_SECONDS,
)
def _get_image_thumbnail_bytes_cached(
    path_str: str,
    mtime_ns: int,
    max_width: int,
    fmt: str,
    quality: int,
    background_rgb: tuple[int, int, int],
) -> bytes:
    """Return resized/encoded thumbnail bytes for an image file.

    Keyed by (path, mtime, options) so updates to the file invalidate the cache.
    """

    p = Path(path_str)
    if not p.exists():
        return b""

    # Ensure deterministic, safe options
    fmt_upper = str(fmt or "PNG").upper()
    if fmt_upper not in ("PNG", "JPEG"):
        fmt_upper = "PNG"
    try:
        q = int(quality)
    except Exception:
        q = 75
    q = max(10, min(95, q))

    try:
        with Image.open(p) as opened:
            img = ImageOps.exif_transpose(opened)
            img.load()
    except Exception:
        return b""

    img = _resize_to_width(img, int(max_width))

    buf = io.BytesIO()
    if fmt_upper == "JPEG":
        img_rgb = _flatten_to_rgb(img, background_rgb=background_rgb)
        img_rgb.save(buf, format="JPEG", quality=q, optimize=True)
    else:
        # PNG keeps alpha if present.
        img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def get_image_thumbnail_bytes_cached(
    path: str,
    *,
    max_width: int | None = None,
    fmt: str = "PNG",
    quality: int = 75,
    background_rgb: tuple[int, int, int] = (18, 18, 18),
) -> bytes:
    """Public helper: return thumbnail bytes for `path` (cached).

    Returns empty bytes if the path is missing or unreadable.
    """

    p = Path(_normalize_path_str(path))
    if not p.exists():
        return b""
    w = int(max_width) if isinstance(max_width, int) else int(DEFAULT_THUMBNAIL_WIDTH_PX)
    return _get_image_thumbnail_bytes_cached(
        str(p),
        _stat_mtime_ns(p),
        w,
        fmt,
        quality,
        background_rgb,
    )
def _normalize_path_str(path: str) -> str:
    # Many saved payloads may contain Windows-style backslashes; normalize so
    # the same data works on Streamlit Cloud (Linux).
    return str(path).replace("\\", "/")


def _stat_mtime_ns(path: Path) -> int:
    return int(path.stat().st_mtime_ns)


@cache_data(
    show_spinner=False,
    max_entries=IMAGE_BYTES_CACHE_MAX_ENTRIES,
    ttl=IMAGE_BYTES_CACHE_TTL_SECONDS,
)
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
    p = Path(_normalize_path_str(path))

    # Many UI call sites treat missing images as optional. Returning empty bytes
    # keeps the app resilient when an asset path is missing or invalid.
    if not p.exists():
        return b""

    if _should_bypass_image_cache_for_path(p):
        return p.read_bytes()
    return _get_image_bytes_cached(str(p), _stat_mtime_ns(p))


@cache_data(
    show_spinner=False,
    max_entries=DATA_URI_CACHE_MAX_ENTRIES,
    ttl=DATA_URI_CACHE_TTL_SECONDS,
)
def bytes_to_data_uri(data: object, mime: str = "image/png") -> str:
    """Convert raw bytes or a PIL Image to a data URI (cached by content hash).

    Accepts:
      - raw `bytes` or `bytearray`
      - a `PIL.Image.Image` instance
      - a file-like object with a `getvalue()` method (e.g., `io.BytesIO`)

    `mime` should be the desired content type (e.g., 'image/png' or 'image/jpeg').
    """
    if not data:
        return ""

    # If caller passed a PIL Image, serialize it to bytes using the mime/format
    if isinstance(data, Image.Image):
        buf = io.BytesIO()
        fmt = "PNG" if mime == "image/png" else "JPEG"
        img = data
        if fmt == "JPEG" and img.mode in ("RGBA", "LA"):
            img = img.convert("RGB")
        img.save(buf, format=fmt)
        bytes_data = buf.getvalue()
    # Bytes-like objects
    elif isinstance(data, (bytes, bytearray)):
        bytes_data = bytes(data)
    # file-like buffer
    elif hasattr(data, "getvalue"):
        bytes_data = data.getvalue()
    else:
        raise TypeError("bytes_to_data_uri expects bytes, PIL.Image, or a buffer with getvalue()")

    b64 = base64.b64encode(bytes_data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def get_image_data_uri_cached(path: str) -> str:
    """Return a `data:<mime>;base64,...` URI for `path`, cached and invalidated on file change."""
    p = Path(_normalize_path_str(path))
    data = get_image_bytes_cached(str(p))
    if not data:
        return ""
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    if _should_bypass_image_cache_for_path(p):
        return _bytes_to_data_uri_uncached(data, mime=mime)
    return bytes_to_data_uri(data, mime=mime)


# -------------------------------------------------------------
# PIL Image helpers (cached by file mtime)
# -------------------------------------------------------------
@cache_resource(
    show_spinner=False,
    max_entries=PIL_IMAGE_CACHE_MAX_ENTRIES,
    ttl=PIL_IMAGE_CACHE_TTL_SECONDS,
)
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
    if _should_bypass_image_cache_for_path(p):
        if not p.exists():
            raise FileNotFoundError(f"Missing image: {p}")
        data = p.read_bytes()
        img = Image.open(io.BytesIO(data))
        if convert:
            img = img.convert(convert)
        return img
    return _load_pil_image_cached_raw(str(p), _stat_mtime_ns(p), convert)


def _bytes_to_data_uri_uncached(data: bytes, mime: str = "image/png") -> str:
    if not data:
        return ""
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_encounter_card_asset_path(p: Path) -> bool:
    s = str(p).replace("\\", "/").lower()
    return (
        "/assets/encounter cards/" in s
        or s.endswith("/assets/encounter cards")
        or "/assets/edited encounter cards/" in s
        or s.endswith("/assets/edited encounter cards")
    )


def _should_bypass_image_cache_for_path(p: Path) -> bool:
    try:
        if not is_streamlit_cloud():
            return False
        if not get_config_bool("DSBG_DISABLE_ENCOUNTER_IMAGE_CACHES", default=False):
            return False
        return _is_encounter_card_asset_path(p)
    except Exception:
        return False
