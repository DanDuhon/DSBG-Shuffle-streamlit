import streamlit as st
from pathlib import Path
from typing import Any, Dict

from ui.campaign_mode.core import CHARACTERS_DIR


def _render_party_icons(settings: Dict[str, Any]) -> None:
    """Render selected party character icons.

    Uses Streamlit-native layout (no data-URIs / unsafe HTML) and a fixed
    4-column grid since party size is 1-4.
    """

    characters = list(settings.get("selected_characters") or [])
    if not characters:
        return

    st.markdown("##### Party")

    cols = st.columns(6)
    chars_dir = Path(CHARACTERS_DIR)

    for idx in range(min(6, len(characters))):
        with cols[idx]:
            char = str(characters[idx])
            p = chars_dir / f"{char}.png"
            if p.is_file():
                st.image(str(p), width="stretch")
            else:
                # No captions under icons; keep a minimal fallback when missing.
                st.write(char)
