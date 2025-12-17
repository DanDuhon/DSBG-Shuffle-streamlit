import streamlit as st
import json
from typing import Any, Dict, List, Optional
from pathlib import Path


def _find_data_file(filename: str) -> Optional[Path]:
    candidates = [
        Path("data") / filename,
        Path("data") / "items" / filename,
        Path(filename),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


@st.cache_data(show_spinner=False)
def _load_json_list(path_str: str) -> List[Dict[str, Any]]:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list in {path}, got {type(data).__name__}")
    return data