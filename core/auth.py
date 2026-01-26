import json
from dataclasses import dataclass
from typing import Any, Optional

from core.settings_manager import get_config_str, is_streamlit_cloud

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None

try:
    from streamlit_javascript import st_javascript
except Exception:  # pragma: no cover
    st_javascript = None


_AUTH_SESSION_KEY = "_dsbg_auth_session_v1"
_AUTH_JS_KEY = "dsbg_auth_js_v1"


def _coerce_js_dict(val: Any) -> dict | None:
    """Coerce a streamlit-javascript return into a dict.

    Depending on the streamlit-javascript version/browser, results can come back
    as a Python dict, a JSON string, or None.
    """

    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _run_js(code: str, *, key: str) -> Any:
    """Run JavaScript via streamlit-javascript, compatible across versions.

    Some versions of `streamlit-javascript` do not support the `default=` kwarg.
    This wrapper tries the newer signature first, then falls back.
    """

    if st_javascript is None:
        return None

    # Streamlit forbids creating multiple elements with the same key in a
    # single rerun. Track used keys and no-op on repeats.
    if st is not None:
        try:
            used = st.session_state.get("_dsbg_js_keys_used_this_run")
        except Exception:
            used = None
        if not isinstance(used, list):
            used = []
        if key in used:
            return None
        try:
            used.append(key)
            st.session_state["_dsbg_js_keys_used_this_run"] = used
        except Exception:
            pass

    # Compatibility: different streamlit-javascript versions have different
    # signatures; prefer the positional form that supports default=None and key.
    try:
        # Common signature: st_javascript(js_code, default, key, ...)
        return st_javascript(code, None, key)
    except TypeError:
        try:
            # Newer signature: st_javascript(js_code, key=...)
            return st_javascript(code, key=key)
        except TypeError:
            try:
                return st_javascript(js_code=code, key=key)
            except TypeError:
                # Last resort: call positionally.
                return st_javascript(code)


@dataclass(frozen=True)
class AuthSession:
    user_id: str
    email: str | None
    access_token: str


def _get_supabase_url() -> str | None:
    return get_config_str("SUPABASE_URL")


def _get_supabase_anon_key() -> str | None:
    # Prefer explicit anon key going forward.
    # Back-compat: allow SUPABASE_KEY if that's what the deployment provides.
    return get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")


def is_auth_ui_enabled() -> bool:
    """Return True when we should show account UI.

    Requirements:
    - Only show in Streamlit Cloud deployments.
    - Only show when Supabase config is present.
    """

    if not is_streamlit_cloud():
        return False
    return bool(_get_supabase_url() and _get_supabase_anon_key() and st is not None and st_javascript is not None)


def _js_get_session(supabase_url: str, supabase_anon_key: str) -> str:
    return (
        "(async () => {"
        f"const SUPABASE_URL = {json.dumps(supabase_url)};"
        f"const SUPABASE_ANON_KEY = {json.dumps(supabase_anon_key)};"
        "const getTopHref = () => { try { return window.parent.location.href; } catch (e) { return window.location.href; } };"
        "const replaceTopHref = (href) => { try { window.parent.history.replaceState({}, '', href); } catch (e) { try { window.history.replaceState({}, '', href); } catch (e2) {} } };"
        "const ensureLib = () => new Promise((resolve, reject) => {"
        "  try {"
        "    if (window.supabase && window.supabase.createClient) return resolve(true);"
        "    const id = 'dsbg_supabase_js_umd_v2';"
        "    const existing = document.getElementById(id);"
        "    if (existing) {"
        "      const tick = () => {"
        "        if (window.supabase && window.supabase.createClient) return resolve(true);"
        "        setTimeout(tick, 50);"
        "      };"
        "      tick();"
        "      return;"
        "    }"
        "    const s = document.createElement('script');"
        "    s.id = id;"
        "    s.async = true;"
        "    s.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js';"
        "    s.onload = () => resolve(true);"
        "    s.onerror = (e) => reject(e);"
        "    document.head.appendChild(s);"
        "  } catch (e) { reject(e); }"
        "});"
        "await ensureLib();"
        "window.__dsbg_supabase_client = window.__dsbg_supabase_client || window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {"
        "  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' },"
        "});"
        "const client = window.__dsbg_supabase_client;"
        "try {"
        "  const href = getTopHref();"
        "  const u = new URL(href);"
        "  const maybeClearTopUrl = () => {"
        "    try {"
        "      u.searchParams.delete('code');"
        "      u.searchParams.delete('state');"
        "      u.searchParams.delete('error');"
        "      u.searchParams.delete('error_code');"
        "      u.searchParams.delete('error_description');"
        "      u.hash = '';"
        "      replaceTopHref(u.toString());"
        "    } catch (e) {}"
        "  };"

        "  /* PKCE flow: ?code=... */"
        "  const code = u.searchParams.get('code');"
        "  if (code) {"
        "    const ex = await client.auth.exchangeCodeForSession(code);"
        "    if (ex && ex.error) {"
        "      return JSON.stringify({ ok: false, error: 'exchangeCodeForSession: ' + String(ex.error.message || ex.error) });"
        "    }"
        "    maybeClearTopUrl();"
        "  }"

        "  /* Implicit flow fallback: #access_token=...&refresh_token=... */"
        "  if (!code && u.hash) {"
        "    const parts = String(u.hash || '').split('#').filter(Boolean);"
        "    const last = parts.length ? parts[parts.length - 1] : '';"
        "    const qp = new URLSearchParams(last);"
        "    const at = qp.get('access_token');"
        "    const rt = qp.get('refresh_token');"
        "    if (at && rt) {"
        "      const ss = await client.auth.setSession({ access_token: at, refresh_token: rt });"
        "      if (ss && ss.error) {"
        "        return JSON.stringify({ ok: false, error: 'setSession: ' + String(ss.error.message || ss.error) });"
        "      }"
        "      maybeClearTopUrl();"
        "    }"
        "  }"
        "} catch (e) { return JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }); }"
        "const res = await client.auth.getSession();"
        "if (res && res.error) {"
        "  return JSON.stringify({ ok: false, error: String(res.error.message || res.error), session: null });"
        "}"
        "const s = res && res.data ? res.data.session : null;"
        "if (!s) return JSON.stringify({ ok: true, session: null });"
        "return JSON.stringify({ ok: true, session: {"
        "  access_token: s.access_token,"
        "  refresh_token: s.refresh_token,"
        "  expires_at: s.expires_at,"
        "  user: { id: s.user && s.user.id ? s.user.id : null, email: s.user && s.user.email ? s.user.email : null }"
        "}}});"
        "})()"
    )


def _js_login_google(supabase_url: str, supabase_anon_key: str) -> str:
    return (
        "(async () => {"
        f"const SUPABASE_URL = {json.dumps(supabase_url)};"
        f"const SUPABASE_ANON_KEY = {json.dumps(supabase_anon_key)};"
        "const ensureLib = () => new Promise((resolve, reject) => {"
        "  try {"
        "    if (window.supabase && window.supabase.createClient) return resolve(true);"
        "    const id = 'dsbg_supabase_js_umd_v2';"
        "    const existing = document.getElementById(id);"
        "    if (existing) {"
        "      const tick = () => {"
        "        if (window.supabase && window.supabase.createClient) return resolve(true);"
        "        setTimeout(tick, 50);"
        "      };"
        "      tick();"
        "      return;"
        "    }"
        "    const s = document.createElement('script');"
        "    s.id = id;"
        "    s.async = true;"
        "    s.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js';"
        "    s.onload = () => resolve(true);"
        "    s.onerror = (e) => reject(e);"
        "    document.head.appendChild(s);"
        "  } catch (e) { reject(e); }"
        "});"
        "await ensureLib();"
        "window.__dsbg_supabase_client = window.__dsbg_supabase_client || window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {"
        "  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' },"
        "});"
        "const client = window.__dsbg_supabase_client;"
        "if (!client) return { ok: false, error: 'supabase client not initialized' };"
        "let topHref = null;"
        "try { topHref = window.parent.location.href; } catch (e) { topHref = window.location.href; }"
        "const redirectTo = String(topHref).split('?')[0];"
        "const res = await client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo } });"
        "if (res && res.error) return { ok: false, error: String(res.error.message || res.error) };"
        "const url = res && res.data ? res.data.url : null;"
        "if (url) {"
        "  const win = window.open(url, '_blank', 'noopener,noreferrer');"
        "  if (!win) return { ok: false, error: 'Popup blocked. Allow popups for this site and try again.' };"
        "  return { ok: true, opened: true };"
        "}"
        "return { ok: false, error: 'No OAuth URL returned by Supabase' };"
        "})()"
    )


def _js_login_magic_link(email: str, supabase_url: str, supabase_anon_key: str) -> str:
    return (
        "(async () => {"
        f"const email = {json.dumps(email)};"
        f"const SUPABASE_URL = {json.dumps(supabase_url)};"
        f"const SUPABASE_ANON_KEY = {json.dumps(supabase_anon_key)};"
        "const ensureLib = () => new Promise((resolve, reject) => {"
        "  try {"
        "    if (window.supabase && window.supabase.createClient) return resolve(true);"
        "    const id = 'dsbg_supabase_js_umd_v2';"
        "    const existing = document.getElementById(id);"
        "    if (existing) {"
        "      const tick = () => {"
        "        if (window.supabase && window.supabase.createClient) return resolve(true);"
        "        setTimeout(tick, 50);"
        "      };"
        "      tick();"
        "      return;"
        "    }"
        "    const s = document.createElement('script');"
        "    s.id = id;"
        "    s.async = true;"
        "    s.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js';"
        "    s.onload = () => resolve(true);"
        "    s.onerror = (e) => reject(e);"
        "    document.head.appendChild(s);"
        "  } catch (e) { reject(e); }"
        "});"
        "await ensureLib();"
        "window.__dsbg_supabase_client = window.__dsbg_supabase_client || window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {"
        "  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' },"
        "});"
        "const client = window.__dsbg_supabase_client;"
        "if (!client) return { ok: false, error: 'supabase client not initialized' };"
        "let topHref = null;"
        "try { topHref = window.parent.location.href; } catch (e) { topHref = window.location.href; }"
        "const emailRedirectTo = String(topHref).split('?')[0];"
        "const res = await client.auth.signInWithOtp({ email, options: { emailRedirectTo } });"
        "if (res && res.error) return { ok: false, error: String(res.error.message || res.error) };"
        "return { ok: true };"
        "})()"
    )


def _js_logout() -> str:
    return (
        "(async () => {"
        "const client = window.__dsbg_supabase_client;"
        "if (!client) return { ok: true };"
        "await client.auth.signOut();"
        "return { ok: true };"
        "})()"
    )


def _coerce_session(payload: Any) -> Optional[AuthSession]:
    if not isinstance(payload, dict):
        return None
    if not payload.get("ok"):
        return None
    session = payload.get("session")
    if session is None:
        return None
    if not isinstance(session, dict):
        return None
    user = session.get("user")
    if not isinstance(user, dict):
        return None
    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        return None
    email = user.get("email")
    if email is not None and not isinstance(email, str):
        email = None
    access_token = session.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None
    return AuthSession(user_id=user_id, email=email, access_token=access_token)


def ensure_session_loaded() -> Optional[AuthSession]:
    """Best-effort: load current Supabase session from the browser.

    In Streamlit Cloud, this uses `streamlit-javascript` to call into supabase-js
    (UMD via CDN) and returns the current user session if present.

    In non-cloud contexts, this is a no-op and returns None.
    """

    if not is_auth_ui_enabled():
        return None

    assert st is not None
    assert st_javascript is not None

    # Avoid creating duplicate JS components in a single rerun.
    # `app.py` resets this flag to False once per rerun.
    try:
        if bool(st.session_state.get("_dsbg_auth_js_used_this_run", False)):
            cached_any = st.session_state.get(_AUTH_SESSION_KEY)
            return cached_any if isinstance(cached_any, AuthSession) else None
    except Exception:
        pass

    # If we already have a session in Streamlit state, return it.
    try:
        cached = st.session_state.get(_AUTH_SESSION_KEY)
    except Exception:
        cached = None
    if isinstance(cached, AuthSession):
        return cached

    url = _get_supabase_url()
    anon = _get_supabase_anon_key()
    if not url or not anon:
        return None

    try:
        st.session_state["_dsbg_auth_js_used_this_run"] = True
    except Exception:
        pass

    val = _run_js(_js_get_session(url, anon), key=_AUTH_JS_KEY)
    if val is None:
        # streamlit-javascript often returns None on the first rerun after
        # insertion. We want to trigger *one* immediate rerun so auth can
        # hydrate without requiring the user to click something.
        #
        # IMPORTANT: never do this on reruns triggered by auth buttons, or we'd
        # swallow the click.
        try:
            pressed = False
            for k in ("auth_google_btn", "auth_magic_btn", "auth_logout_btn"):
                try:
                    if bool(st.session_state.get(k)):
                        pressed = True
                        break
                except Exception:
                    continue

            if not pressed and not bool(st.session_state.get("_dsbg_auth_waited_for_js", False)):
                st.session_state["_dsbg_auth_waited_for_js"] = True
                st.stop()
        except Exception:
            # Never let auth hydration break the app.
            pass
        return None

    # Reset one-shot wait flag once we have any response.
    try:
        st.session_state["_dsbg_auth_waited_for_js"] = False
    except Exception:
        pass

    # Persist the raw value for debugging; some versions may return a non-JSON
    # string (or another type) even when JS returns an object.
    try:
        st.session_state["_auth_last_session_raw"] = val
    except Exception:
        pass

    payload = _coerce_js_dict(val)
    try:
        st.session_state["_auth_last_session_payload"] = payload
    except Exception:
        pass

    if isinstance(payload, dict) and payload.get("ok") is False:
        try:
            err = payload.get("error")
            if isinstance(err, str) and err.strip():
                st.session_state["_auth_last_error"] = err
        except Exception:
            pass

    session = _coerce_session(payload)

    try:
        st.session_state[_AUTH_SESSION_KEY] = session
    except Exception:
        pass
    return session


def clear_cached_session() -> None:
    if st is None:
        return
    try:
        st.session_state.pop(_AUTH_SESSION_KEY, None)
        st.session_state.pop("_auth_js_attempts", None)
        st.session_state.pop("_dsbg_auth_js_used_this_run", None)
        st.session_state.pop("_dsbg_auth_waited_for_js", None)
        st.session_state.pop("_auth_last_session_raw", None)
        st.session_state.pop("_auth_last_session_payload", None)
    except Exception:
        return


def get_user_id() -> str | None:
    sess = ensure_session_loaded()
    return sess.user_id if sess else None


def get_user_email() -> str | None:
    sess = ensure_session_loaded()
    return sess.email if sess else None


def get_access_token() -> str | None:
    sess = ensure_session_loaded()
    return sess.access_token if sess else None


def is_authenticated() -> bool:
    return bool(get_user_id() and get_access_token())


def login_google() -> dict | None:
    if not is_auth_ui_enabled():
        return None
    assert st_javascript is not None
    # Trigger OAuth redirect. The sidebar already calls `ensure_session_loaded()`
    # before rendering buttons, which initializes the Supabase client.
    url = _get_supabase_url()
    anon = _get_supabase_anon_key()
    if not url or not anon:
        return {"ok": False, "error": "Supabase is not configured (missing SUPABASE_URL or SUPABASE_ANON_KEY)."}
    res = _run_js(_js_login_google(url, anon), key="dsbg_auth_google")
    coerced = _coerce_js_dict(res)
    return coerced if coerced is not None else {"ok": False, "error": "No response from browser. Try again (and allow popups)."}


def send_magic_link(email: str) -> dict | None:
    if not is_auth_ui_enabled():
        return {"ok": False, "error": "Auth UI is disabled."}
    email = (email or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "Enter a valid email address."}
    assert st_javascript is not None
    url = _get_supabase_url()
    anon = _get_supabase_anon_key()
    if not url or not anon:
        return {"ok": False, "error": "Supabase is not configured (missing SUPABASE_URL or SUPABASE_ANON_KEY)."}
    res = _run_js(_js_login_magic_link(email, url, anon), key="dsbg_auth_magic")
    coerced = _coerce_js_dict(res)
    return coerced if coerced is not None else {"ok": False, "error": "No response from browser. Try again."}


def logout() -> None:
    if not is_auth_ui_enabled():
        return
    assert st is not None
    assert st_javascript is not None
    _run_js(_js_logout(), key="dsbg_auth_logout")
    clear_cached_session()
    try:
        st.rerun()
    except Exception:
        pass
