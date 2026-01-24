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


def _is_valid_uuid(val: str | None) -> bool:
    if not isinstance(val, str) or not val:
        return False
    try:
        uuid.UUID(val)
        return True
    except Exception:
        return False


def _js_localstorage_get_or_create() -> str:
    # IMPORTANT: create only if missing (avoids clobbering on refresh).
    # Return a value (string) synchronously when possible.
    return (
        "(() => {"
        f"const k = {json.dumps(LOCALSTORAGE_KEY)};"
        "let v = null;"
        "try { v = window.localStorage.getItem(k); } catch (e) { v = null; }"
        "if (!v || v === 'null' || v === 'undefined') {"
        "  try { v = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : null; } catch (e) { v = null; }"
        "  if (!v) {"
        "    // RFC4122-ish fallback"
        "    v = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {"
        "      const r = Math.random() * 16 | 0;"
        "      const t = c === 'x' ? r : (r & 0x3 | 0x8);"
        "      return t.toString(16);"
        "    });"
        "  }"
        "  try { window.localStorage.setItem(k, v); } catch (e) {}"
        "}"
        "return v;"
        "})()"
    )


def _js_localstorage_set(val: str) -> str:
    # Set only when different, to minimize churn.
    return (
        "(() => {"
        f"const k = {json.dumps(LOCALSTORAGE_KEY)};"
        f"const v = {json.dumps(val)};"
        "try {"
        "  const cur = window.localStorage.getItem(k);"
        "  if (cur !== v) window.localStorage.setItem(k, v);"
        "} catch (e) {}"
        "return v;"
        "})()"
    )


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
    if _is_valid_uuid(cid):
        return cid

    # 2) Check query params (useful fallback when JS bridge isn't available)
    qcid = _get_query_param("client_id")
    if _is_valid_uuid(qcid):
        try:
            st.session_state["client_id"] = qcid
        except Exception:
            pass
        # Sync localStorage to query param when JS bridge is available.
        if st_javascript:
            try:
                st_javascript(_js_localstorage_set(qcid))
            except Exception:
                pass
        return qcid

    # 3) Try browser localStorage via st_javascript (get-or-create, no clobber)
    if st_javascript:
        try:
            val = st_javascript(_js_localstorage_get_or_create())
            if isinstance(val, str) and val.lower() in ("null", "undefined"):
                val = None
            if _is_valid_uuid(val):
                try:
                    st.session_state["client_id"] = val
                except Exception:
                    pass
                # Keep URL stable across refreshes.
                _set_query_param("client_id", val)
                return val
        except Exception:
            pass

    # 4) Create new UUID and persist via query params.
    # We intentionally do NOT write localStorage here when the JS bridge is flaky,
    # because on Streamlit Cloud a component can return None during init and
    # clobber an existing localStorage id on each refresh.
    new_id = str(uuid.uuid4())
    try:
        st.session_state["client_id"] = new_id
    except Exception:
        pass

    # Also set query param so the id survives refreshes even if localStorage fails
    _set_query_param("client_id", new_id)

    # Best-effort: if JS is available, also sync localStorage after we have a stable id.
    if st_javascript:
        try:
            st_javascript(_js_localstorage_set(new_id))
        except Exception:
            pass

    return new_id
