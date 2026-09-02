import json
import time
import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth._sync.storage import SyncMemoryStorage
from core.settings_manager import get_config_str, is_streamlit_cloud
from streamlit_cookies_controller import CookieController

_AUTH_SESSION_KEY = "_dsbg_auth_state_v2"
_CLIENT_SESSION_KEY = "_dsbg_supabase_client"
_COOKIE_KEY = "dsbg_session_tokens"
_COOKIE_MAX_AGE = 2592000  # 30 days
_REFRESH_MARGIN_S = 300  # refresh the JWT 5 minutes before it expires

# Initialize the cookie manager
cookies = CookieController()


def _is_auth_rejection(exc: Exception) -> bool:
    """True when Supabase actively rejected the credentials.

    Only a rejection should cost the user their persistent cookie; network
    errors and other transient failures must leave it in place so the next
    run can retry instead of silently logging the user out.
    """
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status in (400, 401, 403, 422)
    return type(exc).__name__ in {"AuthApiError", "AuthInvalidCredentialsError"}


def _store_session(res) -> None:
    """Hydrate session_state and the browser cookie from a Supabase auth result."""
    st.session_state[_AUTH_SESSION_KEY] = {
        "user_id": res.user.id,
        "email": res.user.email,
        "access_token": res.session.access_token,
        "refresh_token": res.session.refresh_token,
        "expires_at": getattr(res.session, "expires_at", None),
    }
    cookies.set(
        _COOKIE_KEY,
        json.dumps({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
        }),
        max_age=_COOKIE_MAX_AGE,
    )


def _session_is_fresh(state: dict) -> bool:
    """True when the cached access token is still comfortably valid."""
    expires_at = state.get("expires_at")
    if isinstance(expires_at, (int, float)):
        return time.time() < (float(expires_at) - _REFRESH_MARGIN_S)
    # Unknown expiry (older gotrue versions may hand back a datetime, or
    # nothing at all): re-validate rather than risk using a stale JWT.
    ts = getattr(expires_at, "timestamp", None)
    if callable(ts):
        try:
            return time.time() < (float(ts()) - _REFRESH_MARGIN_S)
        except Exception:
            return False
    return False

@st.cache_resource
def _get_supabase_config() -> tuple[str, str] | None:
    """Project URL + anon key. Safe to share process-wide: immutable config."""
    url = get_config_str("SUPABASE_URL")
    key = get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")
    if not url or not key:
        return None
    return url, key


def _get_supabase_client() -> Client | None:
    """One Supabase client per Streamlit session.

    This must NOT be `@st.cache_resource`. A cached client is shared by every
    concurrent user, and supabase_auth's session storage is a plain in-process
    dict on the client. Every `set_session` (reached from `restore_session` on
    each rerun) and `sign_in_with_password` writes the caller's tokens into it,
    so whichever user touched the client last owns that storage. `sign_out`
    then reads its access token back out and revokes *that* user's refresh
    tokens -- globally, on all their devices -- no matter who clicked Log Out.

    A client per session gives each user their own storage, so a logout can
    only ever affect the user who asked for it.

    `auto_refresh_token=False`: the default spawns a background refresh Timer
    thread per client, which would now mean one thread per logged-in session.
    Its refreshed tokens would also go nowhere -- they land in the client's
    storage, while this module reads tokens from `st.session_state` and the
    cookie. Refresh is already handled synchronously by `restore_session`,
    which calls `set_session` and writes the result back through
    `_store_session`.
    """
    client = st.session_state.get(_CLIENT_SESSION_KEY)
    if client is not None:
        return client

    config = _get_supabase_config()
    if config is None:
        return None

    url, key = config
    client = create_client(
        url,
        key,
        options=SyncClientOptions(
            storage=SyncMemoryStorage(),
            auto_refresh_token=False,
        ),
    )
    st.session_state[_CLIENT_SESSION_KEY] = client
    return client

def is_auth_ui_enabled() -> bool:
    # Checks config, not the client: this runs on every rerun and building a
    # client for a user who never logs in would be pure overhead.
    return bool(is_streamlit_cloud() and _get_supabase_config() is not None)

def restore_session():
    """Rebuild the session from browser cookies, refreshing the JWT when stale.

    Runs on every access to the session so an expired access token is renewed
    mid-session rather than only at first hydration.
    """
    state = st.session_state.get(_AUTH_SESSION_KEY)
    if state and _session_is_fresh(state):
        return  # Hydrated and still valid

    if state and state.get("refresh_token"):
        tokens = {
            "access_token": state.get("access_token"),
            "refresh_token": state.get("refresh_token"),
        }
    else:
        cookie_str = cookies.get(_COOKIE_KEY)
        if not cookie_str:
            return
        try:
            tokens = json.loads(cookie_str)
        except ValueError:
            # Corrupt cookie; nothing recoverable in it.
            cookies.remove(_COOKIE_KEY)
            return

    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        return

    client = _get_supabase_client()
    if client is None:
        return

    try:
        # set_session automatically refreshes the JWT if it has expired
        res = client.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        _store_session(res)
    except Exception as exc:
        if _is_auth_rejection(exc):
            # The refresh token is dead or revoked; purge so the user can log in again.
            st.session_state.pop(_AUTH_SESSION_KEY, None)
            cookies.remove(_COOKIE_KEY)
        # Otherwise keep the cookie and any existing session: likely transient.

def get_user_id() -> str | None:
    restore_session()
    return st.session_state.get(_AUTH_SESSION_KEY, {}).get("user_id")

def get_user_email() -> str | None:
    restore_session()
    return st.session_state.get(_AUTH_SESSION_KEY, {}).get("email")

def get_access_token() -> str | None:
    restore_session()
    return st.session_state.get(_AUTH_SESSION_KEY, {}).get("access_token")

def is_authenticated() -> bool:
    return bool(get_user_id() and get_access_token())

_NO_CLIENT_ERROR = "Account features are not configured on this deployment."

def login(email: str, password: str) -> dict:
    client = _get_supabase_client()
    if client is None:
        return {"ok": False, "error": _NO_CLIENT_ERROR}
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        _store_session(res)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def sign_up(email: str, password: str) -> dict:
    client = _get_supabase_client()
    if client is None:
        return {"ok": False, "error": _NO_CLIENT_ERROR}
    try:
        res = client.auth.sign_up({"email": email, "password": password})
        if getattr(res, "session", None) is None:
            # Project requires email confirmation: no session is issued yet.
            return {
                "ok": False,
                "error": "Account created. Check your email to confirm it, then log in.",
            }
        _store_session(res)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def logout() -> None:
    client = _get_supabase_client()
    if client:
        try:
            # scope="local" revokes only this session's refresh token.
            # supabase_auth defaults to "global", which kills every session
            # the user has on every device.
            client.auth.sign_out({"scope": "local"})
        except Exception:
            pass
    # Drop the client too, so the next login starts from empty token storage.
    st.session_state.pop(_CLIENT_SESSION_KEY, None)
    st.session_state.pop(_AUTH_SESSION_KEY, None)
    cookies.remove(_COOKIE_KEY)

def send_recovery_code(email: str) -> dict:
    client = _get_supabase_client()
    if client is None:
        return {"ok": False, "error": _NO_CLIENT_ERROR}
    try:
        # Triggers the Reset Password email template
        client.auth.reset_password_for_email(email)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def verify_and_set_password(email: str, code: str, new_password: str) -> dict:
    client = _get_supabase_client()
    if client is None:
        return {"ok": False, "error": _NO_CLIENT_ERROR}
    try:
        # 1. Verify the 8-digit recovery code
        res = client.auth.verify_otp({"email": email, "token": code, "type": "recovery"})

        # 2. Bind the new password to the existing OAuth/Magic Link account
        client.auth.update_user({"password": new_password})

        # 3. Hydrate session memory and cookies
        _store_session(res)

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def render_auth_ui():
    """Drop-in UI component to render the login/signup/migrate form."""
    if not is_auth_ui_enabled():
        return

    if is_authenticated():
        st.sidebar.caption(f"Logged in as: {get_user_email()}")
        if st.sidebar.button("Log Out"):
            logout()
            time.sleep(0.5) 
            st.rerun()
        return

    # The action selector lives OUTSIDE the form on purpose. Inside a form,
    # widget changes do not rerun the script until submit, so the body below
    # stayed on whichever branch was current when the form was built: picking
    # "Reset/Migrate" left the Log In fields on screen, and the first Submit ran
    # the wrong branch.
    st.sidebar.write("Account Access")
    action = st.sidebar.radio(
        "Action",
        ["Log In", "Sign Up", "Reset/Migrate"],
        horizontal=True,
        key="auth_action",
    )

    with st.sidebar.form("auth_form"):
        email = st.text_input("Email")

        if action in ["Log In", "Sign Up"]:
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Submit")

            if submit:
                if not email or not password:
                    st.error("Email and password required.")
                elif action == "Log In":
                    res = login(email, password)
                    if res["ok"]: 
                        time.sleep(0.5) 
                        st.rerun()
                    else: 
                        st.error(res["error"])
                else:
                    res = sign_up(email, password)
                    if res["ok"]:
                        st.success("Account created. You are now logged in.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(res["error"])
        else:
            # OTP Migration and Recovery Flow
            st.caption("Previously used Google/Magic Link? Use this to set a password and recover your data.")
            code = st.text_input("8-Digit Code (Leave blank to request)")
            new_password = st.text_input("New Password", type="password")
            submit = st.form_submit_button("Submit")

            if submit:
                if not email:
                    st.error("Email required.")
                elif not code:
                    res = send_recovery_code(email)
                    if res["ok"]:
                        st.success("Code sent! Check your email, enter it below, and set your new password.")
                    else:
                        st.error(res["error"])
                else:
                    if not new_password:
                        st.error("Please enter a new password.")
                    else:
                        res = verify_and_set_password(email, code, new_password)
                        if res["ok"]:
                            st.success("Password set! You are now logged in.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(res["error"])