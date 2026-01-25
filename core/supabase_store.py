"""Lightweight Supabase/PostgREST helpers for storing JSON documents.

This module uses the Supabase REST API (PostgREST) via `requests` so it
can be invoked from inside Streamlit (using `st.secrets`) or from scripts
that export `SUPABASE_URL` and a Supabase API key.

Expect the following table (see scripts/supabase_schema.sql):
- app_documents(doc_type TEXT, key_name TEXT, user_id TEXT, data JSONB)

Secrets expected in Streamlit Cloud (via `st.secrets`):
    SUPABASE_URL
    SUPABASE_ANON_KEY (preferred)
    SUPABASE_KEY (fallback)

Example usage inside Streamlit:
  from core import supabase_store as store
    store.upsert_document('user_settings','default', settings_dict, user_id=user_id, access_token=jwt)
  obj = store.get_document('user_settings','default')
"""
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import requests
from datetime import datetime


def _parse_dt(val: Any) -> Optional[datetime]:
    if not isinstance(val, str) or not val:
        return None
    try:
        # Handle common PostgREST/Supabase ISO formats
        s = val.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _pick_latest_row(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Choose the most recent row from a list.

    This is defensive: if the Supabase table lacks the unique constraint that
    `on_conflict` expects, duplicates can exist. We prefer the newest row by:
    - updated_at (if present)
    - created_at (if present)
    - id (if present)
    - otherwise the last row returned
    """
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    best = None
    best_key = None
    for r in rows:
        updated = _parse_dt(r.get("updated_at"))
        created = _parse_dt(r.get("created_at"))
        rid = r.get("id")
        rid_int = rid if isinstance(rid, int) else None
        key = (
            updated or created,
            created,
            rid_int,
        )
        if best is None or (best_key is not None and key > best_key) or best_key is None:
            best = r
            best_key = key
    return best or rows[-1]


def _maybe_streamlit():
    try:
        import streamlit as st  # type: ignore

        return st
    except Exception:
        return None


def _base_url_from_env() -> str:
    # Prefer environment variables for non-Streamlit runs (scripts, Docker).
    url = os.environ.get("SUPABASE_URL")
    if not url:
        st = _maybe_streamlit()
        if st is not None and hasattr(st, "secrets"):
            url = st.secrets.get("SUPABASE_URL")
    if not url:
        raise EnvironmentError("SUPABASE_URL not set in env or st.secrets")
    return url.rstrip("/")


def _key_from_env() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")
    if not key:
        st = _maybe_streamlit()
        if st is not None and hasattr(st, "secrets"):
            key = st.secrets.get("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_KEY")
    if not key:
        raise EnvironmentError("SUPABASE_ANON_KEY/SUPABASE_KEY not set in env or st.secrets")
    return key


def _headers(access_token: Optional[str] = None) -> Dict[str, str]:
    key = _key_from_env()
    return {
        "apikey": key,
        "Authorization": f"Bearer {access_token or key}",
        "Content-Type": "application/json",
        # Prefer header is used for return behaviour; override in callers as needed.
        "Prefer": "return=representation",
    }


_DOC_CACHE_KEY = "_supabase_doc_cache_v1"
_LIST_CACHE_KEY = "_supabase_list_cache_v1"


def _cache_enabled() -> bool:
    """Enable/disable Supabase in-session cache.

    Defaults to enabled under Streamlit. Can be disabled via env var:
      DSBG_SUPABASE_CACHE=0
    """
    if os.environ.get("DSBG_SUPABASE_CACHE") in ("0", "false", "FALSE", "no", "NO"):
        return False
    st = _maybe_streamlit()
    return st is not None


def _doc_cache_get(key: Tuple[str, str, str]) -> Tuple[bool, Any]:
    st = _maybe_streamlit()
    if st is None:
        return (False, None)
    try:
        cache = st.session_state.get(_DOC_CACHE_KEY)
        if isinstance(cache, dict):
            if key in cache:
                return (True, cache.get(key))
    except Exception:
        return (False, None)
    return (False, None)


def _doc_cache_set(key: Tuple[str, str, str], value: Any) -> None:
    st = _maybe_streamlit()
    if st is None:
        return
    try:
        cache = st.session_state.get(_DOC_CACHE_KEY)
        if not isinstance(cache, dict):
            cache = {}
        cache[key] = value
        st.session_state[_DOC_CACHE_KEY] = cache
    except Exception:
        return


def _list_cache_get(key: Tuple[str, str]) -> Optional[List[str]]:
    st = _maybe_streamlit()
    if st is None:
        return None
    try:
        cache = st.session_state.get(_LIST_CACHE_KEY)
        if isinstance(cache, dict):
            val = cache.get(key)
            if isinstance(val, list):
                return list(val)
    except Exception:
        return None
    return None


def _list_cache_set(key: Tuple[str, str], value: List[str]) -> None:
    st = _maybe_streamlit()
    if st is None:
        return
    try:
        cache = st.session_state.get(_LIST_CACHE_KEY)
        if not isinstance(cache, dict):
            cache = {}
        cache[key] = list(value)
        st.session_state[_LIST_CACHE_KEY] = cache
    except Exception:
        return


def invalidate_document_cache(doc_type: str, key_name: str, user_id: str) -> None:
    """Remove a single document from the in-session cache (best-effort)."""
    st = _maybe_streamlit()
    if st is None:
        return
    try:
        dcache = st.session_state.get(_DOC_CACHE_KEY)
        if isinstance(dcache, dict):
            dcache.pop((str(user_id), str(doc_type), str(key_name)), None)
            st.session_state[_DOC_CACHE_KEY] = dcache
    except Exception:
        pass


def invalidate_list_cache(doc_type: str, user_id: str) -> None:
    """Remove a doc_type list cache entry for this user (best-effort)."""
    st = _maybe_streamlit()
    if st is None:
        return
    try:
        lcache = st.session_state.get(_LIST_CACHE_KEY)
        if isinstance(lcache, dict):
            lcache.pop((str(user_id), str(doc_type)), None)
            st.session_state[_LIST_CACHE_KEY] = lcache
    except Exception:
        pass


def _table_url() -> str:
    base = _base_url_from_env()
    # PostgREST REST endpoint
    return f"{base}/rest/v1/app_documents"


def upsert_document(
    doc_type: str,
    key_name: str,
    data: Any,
    user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Insert or update a JSON document.

    Uses PostgREST upsert via `on_conflict` and `Prefer: resolution=merge-duplicates`.
    Returns the server representation (list) on success.
    """
    url = _table_url()
    payload: Dict[str, Any] = {"doc_type": doc_type, "key_name": key_name, "data": data}
    if user_id is not None:
        payload["user_id"] = user_id

    params = {"on_conflict": "doc_type,key_name,user_id"}
    headers = _headers(access_token=access_token)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    try:
        resp = requests.post(url, headers=headers, params=params, json=[payload], timeout=10)
        resp.raise_for_status()
        # Update in-session caches (best-effort)
        if _cache_enabled() and user_id is not None:
            uid = str(user_id)
            _doc_cache_set((uid, doc_type, key_name), data)
            # Keep list cache warm too
            existing = _list_cache_get((uid, doc_type))
            if isinstance(existing, list):
                if key_name not in existing:
                    existing.append(key_name)
                _list_cache_set((uid, doc_type), existing)
        return resp.json()
    except Exception:
        raise


def _get_document_remote(
    doc_type: str, key_name: str, user_id: str, access_token: Optional[str] = None
) -> Optional[Any]:
    """Remote fetch implementation (no cache)."""
    """Fetch a single document's `data` field or None if not found."""
    if not user_id:
        return None
    url = _table_url()
    headers = _headers(access_token=access_token)
    # PostgREST filtering via query params (e.g., doc_type=eq.x)
    # Select all fields so we can pick the newest row if duplicates exist.
    params: Dict[str, str] = {"select": "*", "doc_type": f"eq.{doc_type}", "key_name": f"eq.{key_name}", "user_id": f"eq.{user_id}"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        arr = resp.json()
        if not isinstance(arr, list) or not arr:
            return None
        row = _pick_latest_row(arr)
        if not row or "data" not in row:
            return None
        return row.get("data")
    except Exception:
        return None


def get_document(
    doc_type: str,
    key_name: str,
    user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Optional[Any]:
    """Fetch a single document's `data` field or None if not found.

    Under Streamlit, results are cached in session_state to avoid repeated
    Supabase reads across reruns. Writes update/invalidate the cache.
    """

    # Schema expects user_id NOT NULL; treat missing user_id as "not found".
    if user_id is None:
        return None

    uid = str(user_id)
    if _cache_enabled():
        found, cached = _doc_cache_get((uid, doc_type, key_name))
        if found:
            return cached

    val = _get_document_remote(doc_type, key_name, uid, access_token=access_token)
    if _cache_enabled():
        _doc_cache_set((uid, doc_type, key_name), val)
    return val


def _list_documents_remote(doc_type: str, user_id: str, access_token: Optional[str] = None) -> List[str]:
    """Remote list implementation (no cache)."""
    """Return a list of `key_name` values for a given doc_type."""
    if not user_id:
        return []
    url = _table_url()
    headers = _headers(access_token=access_token)
    params: Dict[str, str] = {"select": "key_name", "doc_type": f"eq.{doc_type}"}
    params["user_id"] = f"eq.{user_id}"

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        return []
    # De-dupe defensively in case duplicates exist in the table.
    out: List[str] = []
    seen: set[str] = set()
    for r in rows:
        try:
            k = r.get("key_name")
        except Exception:
            k = None
        if isinstance(k, str) and k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def list_documents(doc_type: str, user_id: Optional[str] = None, access_token: Optional[str] = None) -> List[str]:
    """Return a list of `key_name` values for a given doc_type.

    Under Streamlit, results are cached in session_state to avoid repeated
    Supabase reads across reruns. Writes update/invalidate the cache.
    """

    if user_id is None:
        return []

    uid = str(user_id)
    if _cache_enabled():
        cached = _list_cache_get((uid, doc_type))
        if isinstance(cached, list):
            return cached

    names = _list_documents_remote(doc_type, uid, access_token=access_token)
    if _cache_enabled():
        _list_cache_set((uid, doc_type), names)
    return names


def delete_document(
    doc_type: str,
    key_name: str,
    user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> bool:
    """Delete a document; returns True if deleted."""
    # Schema expects user_id NOT NULL
    if user_id is None:
        return False

    url = _table_url()
    headers = _headers(access_token=access_token)
    params: Dict[str, str] = {"doc_type": f"eq.{doc_type}", "key_name": f"eq.{key_name}"}
    params["user_id"] = f"eq.{user_id}"

    resp = requests.delete(url, headers=headers, params=params, timeout=10)
    # 204 No Content or 200 with representation
    ok = resp.status_code in (200, 204)
    if ok and _cache_enabled() and user_id is not None:
        uid = str(user_id)
        invalidate_document_cache(doc_type, key_name, uid)
        invalidate_list_cache(doc_type, uid)
    return ok
