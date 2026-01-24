import uuid
import json

try:
    from streamlit_javascript import st_javascript
except Exception:
    st_javascript = None

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None

LOCALSTORAGE_KEY = "dsbg_client_id"


def _get_query_param(key: str) -> str | None:
    """Best-effort query param getter across Streamlit versions."""
    if st is None:
        return None

    # Streamlit >= 1.30: st.query_params is a dict-like proxy
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None:
            val = qp.get(key)
            if isinstance(val, list):
                return val[0] if val else None
            if isinstance(val, str):
                return val
    except Exception:
        pass

    # Older Streamlit: experimental_get_query_params
    try:
        params = st.experimental_get_query_params()
        val = params.get(key, [None])[0]
        return val
    except Exception:
        return None


def _set_query_param(key: str, value: str) -> None:
    """Best-effort query param setter across Streamlit versions.

    Important: preserve existing query params when possible.
    """
    if st is None:
        return

    # Streamlit >= 1.30: in-place update
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None:
            try:
                qp[key] = value
            except Exception:
                qp.update({key: value})
            return
    except Exception:
        pass

    # Older Streamlit: experimental_set_query_params replaces full set
    try:
        existing = st.experimental_get_query_params()
        existing[key] = [value]
        flattened = {k: (v[0] if isinstance(v, list) and v else v) for k, v in existing.items()}
        st.experimental_set_query_params(**flattened)
    except Exception:
        return


def get_or_create_client_id() -> str:
    """Return the client id stored in browser localStorage, or create one.

    Uses `streamlit-javascript` if available. Falls back to a server-side
    generated UUID stored in `st.session_state` if the JS bridge is not
    available.
    """
    if st is None:
        raise RuntimeError("core.client_id.get_or_create_client_id requires Streamlit")
    # 1) Prefer value already in session state
    try:
        cid = st.session_state.get("client_id")
    except Exception:
        cid = None
    if cid:
        return cid

    # 2) Check query params (useful fallback when JS bridge isn't available)
    qcid = _get_query_param("client_id")
    if qcid:
        try:
            st.session_state["client_id"] = qcid
        except Exception:
            pass
        return qcid

    # 3) Try browser localStorage via st_javascript
    if st_javascript:
        try:
            js_get = f"localStorage.getItem({json.dumps(LOCALSTORAGE_KEY)})"
            val = st_javascript(js_get)
            if isinstance(val, str) and val.lower() == "null":
                val = None
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
    _set_query_param("client_id", new_id)

    return new_id
