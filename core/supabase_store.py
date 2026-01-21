"""Lightweight Supabase/PostgREST helpers for storing JSON documents.

This module uses the Supabase REST API (PostgREST) via `requests` so it
can be invoked from inside Streamlit (using `st.secrets`) or from scripts
that export `SUPABASE_URL` and `SUPABASE_KEY` environment variables.

Expect the following table (see scripts/supabase_schema.sql):
- app_documents(doc_type TEXT, key_name TEXT, user_id TEXT, data JSONB)

Secrets expected in Streamlit Cloud (via `st.secrets`):
  SUPABASE_URL
  SUPABASE_KEY

Example usage inside Streamlit:
  from core import supabase_store as store
  store.upsert_document('user_settings','default', settings_dict)
  obj = store.get_document('user_settings','default')
"""
from typing import Any, Dict, List, Optional
import os
import json
import requests
import streamlit as st


def _base_url_from_env() -> str:
    # Prefer environment variables for non-Streamlit runs (scripts, Docker).
    url = os.environ.get("SUPABASE_URL") or (st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") else None)
    if not url:
        raise EnvironmentError("SUPABASE_URL not set in env or st.secrets")
    return url.rstrip("/")


def _key_from_env() -> str:
    key = os.environ.get("SUPABASE_KEY") or (st.secrets.get("SUPABASE_KEY") if hasattr(st, "secrets") else None)
    if not key:
        raise EnvironmentError("SUPABASE_KEY not set in env or st.secrets")
    return key


def _headers() -> Dict[str, str]:
    key = _key_from_env()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # Prefer header is used for return behaviour; override in callers as needed.
        "Prefer": "return=representation",
    }


def _table_url() -> str:
    base = _base_url_from_env()
    # PostgREST REST endpoint
    return f"{base}/rest/v1/app_documents"


def upsert_document(
    doc_type: str, key_name: str, data: Any, user_id: Optional[str] = None
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
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    try:
        resp = requests.post(url, headers=headers, params=params, json=[payload], timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        # Surface helpful message for debugging in Streamlit context
        try:
            st.error(f"Supabase upsert error: {exc}")
        except Exception:
            pass
        raise


def get_document(doc_type: str, key_name: str, user_id: Optional[str] = None) -> Optional[Any]:
    """Fetch a single document's `data` field or None if not found."""
    url = _table_url()
    headers = _headers()
    # PostgREST filtering via query params (e.g., doc_type=eq.x)
    params: Dict[str, str] = {"select": "data", "doc_type": f"eq.{doc_type}", "key_name": f"eq.{key_name}"}
    if user_id is None:
        params["user_id"] = "is.null"
    else:
        params["user_id"] = f"eq.{user_id}"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        arr = resp.json()
        if not arr:
            return None
        return arr[0]["data"]
    except Exception as exc:
        try:
            st.error(f"Supabase get_document error: {exc}")
        except Exception:
            pass
        return None


def list_documents(doc_type: str, user_id: Optional[str] = None) -> List[str]:
    """Return a list of `key_name` values for a given doc_type."""
    url = _table_url()
    headers = _headers()
    params: Dict[str, str] = {"select": "key_name", "doc_type": f"eq.{doc_type}"}
    if user_id is None:
        params["user_id"] = "is.null"
    else:
        params["user_id"] = f"eq.{user_id}"

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return [r["key_name"] for r in resp.json()]


def delete_document(doc_type: str, key_name: str, user_id: Optional[str] = None) -> bool:
    """Delete a document; returns True if deleted."""
    url = _table_url()
    headers = _headers()
    params: Dict[str, str] = {"doc_type": f"eq.{doc_type}", "key_name": f"eq.{key_name}"}
    if user_id is None:
        params["user_id"] = "is.null"
    else:
        params["user_id"] = f"eq.{user_id}"

    resp = requests.delete(url, headers=headers, params=params, timeout=10)
    # 204 No Content or 200 with representation
    return resp.status_code in (200, 204)


def ping() -> bool:
    """Quickly check Supabase connectivity by listing zero rows from table."""
    try:
        url = _table_url()
        headers = _headers()
        resp = requests.get(url, headers=headers, params={"select": "doc_type", "limit": "1"}, timeout=8)
        return resp.status_code == 200
    except Exception:
        return False
