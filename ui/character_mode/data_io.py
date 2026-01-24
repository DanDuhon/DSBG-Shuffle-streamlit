import streamlit as st
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from core import supabase_store
from core.settings_manager import _has_supabase_config, get_runtime_client_id


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
    # Supabase-backed persistence: one row per build
    if _has_supabase_config():
        client_id = get_runtime_client_id()

        out: Dict[str, Any] = {}
        try:
            names = supabase_store.list_documents("character_build", user_id=client_id)
        except Exception:
            names = []

        for n in names:
            try:
                obj = supabase_store.get_document("character_build", n, user_id=client_id)
                if obj is not None:
                    out[n] = obj
            except Exception:
                continue
        return out

    path = BUILDS_FILE
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def save_builds(builds: Dict[str, Any]) -> None:
    # Supabase-backed: upsert each build as separate document
    if _has_supabase_config():
        client_id = get_runtime_client_id()

        for name, obj in (builds or {}).items():
            try:
                supabase_store.upsert_document("character_build", name, obj, user_id=client_id)
            except Exception:
                pass

        # Delete remote builds not present locally
        try:
            remote = supabase_store.list_documents("character_build", user_id=client_id)
            for r in remote:
                if r not in builds:
                    try:
                        supabase_store.delete_document("character_build", r, user_id=client_id)
                    except Exception:
                        pass
        except Exception:
            pass
        return

    BUILDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with BUILDS_FILE.open("w", encoding="utf-8") as f:
        json.dump(builds or {}, f, indent=2)