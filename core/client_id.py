import uuid
import json

try:
    from streamlit_javascript import st_javascript
except Exception:
    st_javascript = None

import streamlit as st

LOCALSTORAGE_KEY = "dsbg_client_id"


def get_or_create_client_id() -> str:
    """Return the client id stored in browser localStorage, or create one.

    Uses `streamlit-javascript` if available. Falls back to a server-side
    generated UUID stored in `st.session_state` if the JS bridge is not
    available.
    """
    # 1) Prefer value already in session state
    try:
        cid = st.session_state.get("client_id")
    except Exception:
        cid = None
    if cid:
        return cid

    # 2) Check query params (useful fallback when JS bridge isn't available)
    try:
        params = st.experimental_get_query_params()
        qcid = params.get("client_id", [None])[0]
        if qcid:
            st.session_state["client_id"] = qcid
            return qcid
    except Exception:
        pass

    # 3) Try browser localStorage via st_javascript
    if st_javascript:
        try:
            js_get = f"localStorage.getItem({json.dumps(LOCALSTORAGE_KEY)})"
            val = st_javascript(js_get)
            if val:
                st.session_state["client_id"] = val
                return val
        except Exception:
            pass

    # 4) Create new UUID and persist to available client-side stores
    new_id = str(uuid.uuid4())
    try:
        st.session_state["client_id"] = new_id
    except Exception:
        pass

    # Try to write to localStorage
    if st_javascript:
        try:
            js_set = f"localStorage.setItem({json.dumps(LOCALSTORAGE_KEY)}, {json.dumps(new_id)})"
            st_javascript(js_set)
        except Exception:
            pass

    # Also set query param so the id survives refreshes even if localStorage fails
    try:
        st.experimental_set_query_params(client_id=new_id)
    except Exception:
        pass

    return new_id
