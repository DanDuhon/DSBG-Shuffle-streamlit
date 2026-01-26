from pathlib import Path
from typing import Any, Dict
import json
import os
import streamlit as st

from core import supabase_store
from core import auth
from core.settings_manager import _has_supabase_config, is_streamlit_cloud


DATA_DIR = Path("data")
SAVED_ENCOUNTERS_PATH = DATA_DIR / "saved_encounters.json"


def load_saved_encounters(*, reload: bool = False) -> Dict[str, Any]:
    # Streamlit Cloud: Supabase-backed documents (per-account)
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            return {}

        try:
            names = supabase_store.list_documents("saved_encounter", user_id=user_id, access_token=access_token)
        except Exception:
            names = []

        out: Dict[str, Any] = {}
        for n in names:
            try:
                obj = supabase_store.get_document("saved_encounter", n, user_id=user_id, access_token=access_token)
                if obj is not None:
                    out[n] = obj
            except Exception:
                continue
        return out

    # Streamlit Cloud should never read shared local files.
    if is_streamlit_cloud():
        return {}

    if not SAVED_ENCOUNTERS_PATH.exists():
        return {}
    with SAVED_ENCOUNTERS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def save_saved_encounters(encounters: Dict[str, Any]) -> None:
    # Persist to Supabase on Streamlit Cloud when configured and logged in;
    # otherwise write local JSON file.
    if is_streamlit_cloud() and _has_supabase_config():
        user_id = auth.get_user_id()
        access_token = auth.get_access_token()
        if not user_id or not access_token:
            return

        # Upsert each encounter
        for name, obj in (encounters or {}).items():
            try:
                supabase_store.upsert_document(
                    "saved_encounter", name, obj, user_id=user_id, access_token=access_token
                )
            except Exception:
                # continue on individual failures
                continue

        # Delete any remote encounters not present locally
        try:
            remote = supabase_store.list_documents("saved_encounter", user_id=user_id, access_token=access_token)
            for r in remote:
                if r not in encounters:
                    try:
                        supabase_store.delete_document(
                            "saved_encounter", r, user_id=user_id, access_token=access_token
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        return

    # Streamlit Cloud should never persist anonymously to local JSON.
    if is_streamlit_cloud():
        return

    _atomic_write(SAVED_ENCOUNTERS_PATH, encounters)
