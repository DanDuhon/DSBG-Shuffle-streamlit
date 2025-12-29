import io
import json
import re
import base64
from pathlib import Path
from PIL import Image

from core.behavior.assets import ICONS_DIR, coords_map
from core.image_cache import bytes_to_data_uri


PRISCILLA_ARC_MAP: dict[str, object] = {}


def _load_map() -> None:
    p = Path("data/behaviors/priscilla_arcs.json")
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                # Accept either a list of directions (old format)
                # or a mapping {direction: [x,y], ...}
                if isinstance(v, list):
                    PRISCILLA_ARC_MAP[k] = v
                elif isinstance(v, dict):
                    # validate coord lists
                    coords = {}
                    for dir_k, coord_v in v.items():
                        if isinstance(coord_v, (list, tuple)) and len(coord_v) >= 2:
                            x = int(coord_v[0])
                            y = int(coord_v[1])
                            coords[dir_k] = (x, y)
                    if coords:
                        PRISCILLA_ARC_MAP[k] = coords


_load_map()


def _decode_data_uri(uri: str) -> tuple[bytes, str]:
    m = re.match(r"data:(?P<mime>[-\w/+\.]+);base64,(?P<b>.+)", uri)
    if not m:
        raise ValueError("Not a data URI")
    b = base64.b64decode(m.group("b"))
    mime = m.group("mime")
    return b, mime


def overlay_priscilla_arcs(image_input, behavior_name: str, behavior_json: dict | None = None):
    """Overlay arc icons for Crossbreed Priscilla according to mapping.

    `image_input` may be raw bytes or a data URI string. The function returns
    the same type as provided (bytes -> bytes, data-uri str -> data-uri str).
    """
    # determine input type
    returned_as_data_uri = False
    mime = "image/png"

    if isinstance(image_input, str) and image_input.startswith("data:"):
        img_bytes, mime = _decode_data_uri(image_input)
        returned_as_data_uri = True
    elif isinstance(image_input, (bytes, bytearray)):
        img_bytes = bytes(image_input)
    else:
        return image_input

    mapping = PRISCILLA_ARC_MAP.get(behavior_name)
    if not mapping:
        return image_input

    base = Image.open(io.BytesIO(img_bytes)).convert("RGBA")

    # Two supported mapping shapes:
    #  - list of directions (e.g. ["left"])
    #  - dict of direction -> (x,y) coordinates (new format)
    if isinstance(mapping, list):
        directions = mapping
        for d in directions:
            if d not in {"up", "down", "left", "right"}:
                continue
            arc_name = f"arc_normal_{d}.png"
            icon_path = ICONS_DIR / arc_name
            if not icon_path.exists():
                continue
            icon = Image.open(icon_path).convert("RGBA")

            # choose placement coordinate from coords_map as a fallback
            coord = None
            if d in {"left", "right"}:
                coord = coords_map.get("attack_physical", {}).get(d)
            if not coord:
                fallback = {
                    "up": coords_map.get("attack_physical", {}).get("middle"),
                    "down": coords_map.get("node", {}).get("middle") if coords_map.get("node") else None,
                    "left": coords_map.get("attack_physical", {}).get("left"),
                    "right": coords_map.get("attack_physical", {}).get("right"),
                }
                coord = fallback.get(d)
            if not coord:
                continue

            x, y = coord
            ix, iy = icon.size
            paste_xy = (int(x - ix / 2), int(y - iy / 2))
            base.alpha_composite(icon, paste_xy)

    elif isinstance(mapping, dict):
        for d, coord in mapping.items():
            if d not in {"up", "down", "left", "right"}:
                continue
            if not coord or len(coord) < 2:
                continue
            x = int(coord[0])
            y = int(coord[1])

            arc_name = f"arc_normal_{d}.png"
            icon_path = ICONS_DIR / arc_name
            icon = Image.open(icon_path).convert("RGBA")

            ix, iy = icon.size
            paste_xy = (int(x - ix / 2), int(y - iy / 2))
            base.alpha_composite(icon, paste_xy)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    out_bytes = buf.getvalue()

    if returned_as_data_uri:
        return bytes_to_data_uri(out_bytes, mime=mime)
    return out_bytes
