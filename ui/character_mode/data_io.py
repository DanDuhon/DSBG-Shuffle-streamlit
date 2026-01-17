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


# Character builds persistence (separate file from user_settings)
BUILDS_FILE = Path("data/character_builds.json")


@st.cache_data(show_spinner=False)
def load_builds() -> Dict[str, Any]:
    path = BUILDS_FILE
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def save_builds(builds: Dict[str, Any]) -> None:
    BUILDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with BUILDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(builds or {}, f, indent=2)