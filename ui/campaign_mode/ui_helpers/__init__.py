# ui/campaign_mode/ui_helpers.py
import streamlit as st
from pathlib import Path
from typing import Any, Dict, Optional
from ui.campaign_mode.core import CHARACTERS_DIR
from core.image_cache import get_image_data_uri_cached


def _img_tag_from_path(
    path: Path,
    title: str = "",
    height_px: int = 48,
    extra_css: str = "",
) -> Optional[str]:
    if not path.is_file():
        return None
    src = get_image_data_uri_cached(str(path))
    if not src:
        return None
    style = f"height:{height_px}px; {extra_css}".strip()
    style_attr = f" style='{style}'" if style else ""
    title_attr = f" title='{title}'" if title else ""
    return f"<img src='{src}'{title_attr}{style_attr} />"


def _render_party_icons(settings: Dict[str, Any]) -> None:
    characters = settings.get("selected_characters") or []
    if not characters:
        return

    chars_dir = CHARACTERS_DIR

    html = """
    <style>
      .campaign-party-section h5 { margin: 0.75rem 0 0.25rem 0; }
      .campaign-party-row {
        display:flex;
        gap:6px;
        flex-wrap:nowrap;
        overflow-x:auto;
        padding-bottom:2px;
      }
      .campaign-party-row::-webkit-scrollbar { height: 6px; }
      .campaign-party-row::-webkit-scrollbar-thumb {
        background: #bbb;
        border-radius: 3px;
      }
      .campaign-party-fallback {
        height:48px;
        background:#ccc;
        border-radius:6px;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:10px;
        text-align:center;
        padding:2px;
      }
    </style>
    <div class="campaign-party-section">
    <h5>Party</h5>
    <div class="campaign-party-row">
    """

    for char in characters:
        fname = f"{char}.png"
        tag = _img_tag_from_path(
            chars_dir / fname,
            title=str(char),
            extra_css="border-radius:6px;",
        )
        if tag:
            html += tag
        else:
            initial = (str(char) or "?")[0:1]
            html += (
                f"<div class='campaign-party-fallback' title='{char}'>"
                f"{initial}</div>"
            )

    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)
