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
    # Prefer value already in session state
    cid = None
    try:
        cid = st.session_state.get("client_id")
    except Exception:
        cid = None

    if cid:
        return cid

    # Try browser localStorage via st_javascript
    if st_javascript:
        try:
            js_get = f"localStorage.getItem({json.dumps(LOCALSTORAGE_KEY)})"
            val = st_javascript(js_get)
            if val:
                st.session_state["client_id"] = val
                return val
        except Exception:
            pass

    # Create new UUID and persist
    new_id = str(uuid.uuid4())
    try:
        st.session_state["client_id"] = new_id
    except Exception:
        pass

    if st_javascript:
        try:
            js_set = f"localStorage.setItem({json.dumps(LOCALSTORAGE_KEY)}, {json.dumps(new_id)})"
            st_javascript(js_set)
        except Exception:
            pass

    return new_id
