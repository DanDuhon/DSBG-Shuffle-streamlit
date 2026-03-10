import json
import time
import streamlit as st
from supabase import create_client, Client
from core.settings_manager import get_config_str, is_streamlit_cloud
from streamlit_cookies_controller import CookieController

_AUTH_SESSION_KEY = "_dsbg_auth_state_v2"
_COOKIE_KEY = "dsbg_session_tokens"

# Initialize the cookie manager
cookies = CookieController()

@st.cache_resource
def _get_supabase_client() -> Client | None:
    url = get_config_str("SUPABASE_URL")
    key = get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def is_auth_ui_enabled() -> bool:
    return bool(is_streamlit_cloud() and _get_supabase_client() is not None)

def restore_session():
    """Intercepts app load to rebuild the session from browser cookies if needed."""
    if _AUTH_SESSION_KEY in st.session_state:
        return # Already hydrated in server memory
    
    cookie_str = cookies.get(_COOKIE_KEY)
    if not cookie_str:
        return
        
    client = _get_supabase_client()
    try:
        tokens = json.loads(cookie_str)
        # set_session automatically refreshes the JWT if it has expired
        res = client.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        
        # Hydrate server memory
        st.session_state[_AUTH_SESSION_KEY] = {
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token
        }
        
        # Update the cookie with fresh tokens to prevent expiration lockouts
        new_cookie_data = json.dumps({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token
        })
        cookies.set(_COOKIE_KEY, new_cookie_data, max_age=2592000) # 30 days
        
    except Exception:
        # If the refresh token is dead or revoked, purge the dead cookie
        cookies.remove(_COOKIE_KEY)

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

def login(email: str, password: str) -> dict:
    client = _get_supabase_client()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        
        # Save to memory
        st.session_state[_AUTH_SESSION_KEY] = {
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token
        }
        
        # Save to browser cookie
        cookie_data = json.dumps({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token
        })
        cookies.set(_COOKIE_KEY, cookie_data, max_age=2592000)
        
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def sign_up(email: str, password: str) -> dict:
    client = _get_supabase_client()
    try:
        res = client.auth.sign_up({"email": email, "password": password})
        st.session_state[_AUTH_SESSION_KEY] = {
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token
        }
        cookie_data = json.dumps({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token
        })
        cookies.set(_COOKIE_KEY, cookie_data, max_age=2592000)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def logout() -> None:
    client = _get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop(_AUTH_SESSION_KEY, None)
    cookies.remove(_COOKIE_KEY)

def send_recovery_code(email: str) -> dict:
    client = _get_supabase_client()
    try:
        # Triggers the Reset Password email template
        client.auth.reset_password_for_email(email)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def verify_and_set_password(email: str, code: str, new_password: str) -> dict:
    client = _get_supabase_client()
    try:
        # 1. Verify the 8-digit recovery code
        res = client.auth.verify_otp({"email": email, "token": code, "type": "recovery"})
        
        # 2. Bind the new password to the existing OAuth/Magic Link account
        client.auth.update_user({"password": new_password})
        
        # 3. Hydrate session memory and cookies
        st.session_state[_AUTH_SESSION_KEY] = {
            "user_id": res.user.id,
            "email": res.user.email,
            "access_token": res.session.access_token
        }
        cookie_data = json.dumps({
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token
        })
        cookies.set(_COOKIE_KEY, cookie_data, max_age=2592000)
        
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

    with st.sidebar.form("auth_form"):
        st.write("Account Access")
        email = st.text_input("Email")
        
        action = st.radio("Action", ["Log In", "Sign Up", "Reset/Migrate"], horizontal=True)
        
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