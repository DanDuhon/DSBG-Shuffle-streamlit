from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ui.event_mode.event_card_text import EVENT_CARD_TEXT
from ui.event_mode.event_card_type import EVENT_CARD_TYPE


def _collapse_ws(s: str) -> str:
    return " ".join(str(s).replace("\n", " ").replace("\r", " ").split())


def event_card_id_from_path(path: Any) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(str(path)).stem or None
    except Exception:
        return None


def event_type_for(ev: Any) -> str:
    if isinstance(ev, dict):
        t = ev.get("type")
        if isinstance(t, str) and t.strip():
            return t.strip()
        # Some payloads use 'event_type'
        t = ev.get("event_type")
        if isinstance(t, str) and t.strip():
            return t.strip()

        cid = event_card_id_from_path(ev.get("path") or ev.get("image_path") or ev.get("card_path"))
        if cid:
            t2 = EVENT_CARD_TYPE.get(cid)
            if isinstance(t2, str) and t2.strip():
                return t2.strip()

    return "Event"


def event_name_for(ev: Any) -> str:
    if isinstance(ev, dict):
        for k in ("name", "title", "id"):
            v = ev.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        cid = event_card_id_from_path(ev.get("path") or ev.get("image_path") or ev.get("card_path"))
        if cid:
            return cid

    if isinstance(ev, str) and ev.strip():
        return ev.strip()

    return "(unnamed)"


def event_brief_effect_for(ev: Any, *, max_len: int = 140) -> str:
    text: str = ""
    if isinstance(ev, dict):
        v = ev.get("brief")
        if isinstance(v, str) and v.strip():
            text = v
        else:
            v = ev.get("text")
            if isinstance(v, str) and v.strip():
                text = v

        if not text:
            cid = event_card_id_from_path(ev.get("path") or ev.get("image_path") or ev.get("card_path"))
            if cid:
                v2 = EVENT_CARD_TEXT.get(cid)
                if isinstance(v2, str) and v2.strip():
                    text = v2

    text = _collapse_ws(text)

    if not text:
        return ""

    if max_len and len(text) > int(max_len):
        return text[: max(0, int(max_len) - 1)].rstrip() + "…"

    return text


def format_event_brief_line(ev: Any, *, include_type: bool = True, max_len: int = 140) -> str:
    name = event_name_for(ev)
    typ = event_type_for(ev)
    brief = event_brief_effect_for(ev, max_len=max_len)

    if include_type and brief:
        return f"{name} — {typ}: {brief}"
    if include_type:
        return f"{name} — {typ}"
    if brief:
        return f"{name}: {brief}"
    return name
