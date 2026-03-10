import streamlit as st
import time
from supabase import create_client, Client
from core.settings_manager import get_config_str, is_streamlit_cloud

_AUTH_SESSION_KEY = "_dsbg_auth_session_v2"

@st.cache_resource
def _get_supabase_client() -> Client | None:
    url = get_config_str("SUPABASE_URL")
    key = get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def is_auth_ui_enabled() -> bool:
    return bool(is_streamlit_cloud() and _get_supabase_client() is not None)

def get_user_id() -> str | None:
    session_data = st.session_state.get(_AUTH_SESSION_KEY)
    return session_data.user.id if session_data else None

def get_user_email() -> str | None:
    session_data = st.session_state.get(_AUTH_SESSION_KEY)
    return session_data.user.email if session_data else None

def get_access_token() -> str | None:
    session_data = st.session_state.get(_AUTH_SESSION_KEY)
    return session_data.session.access_token if session_data else None

def is_authenticated() -> bool:
    return bool(get_user_id() and get_access_token())

def login(email: str, password: str) -> dict:
    client = _get_supabase_client()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state[_AUTH_SESSION_KEY] = res
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def sign_up(email: str, password: str) -> dict:
    client = _get_supabase_client()
    try:
        res = client.auth.sign_up({"email": email, "password": password})
        st.session_state[_AUTH_SESSION_KEY] = res
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

def render_auth_ui():
    """Drop-in UI component to render the login/signup form."""
    if not is_auth_ui_enabled():
        return

    if is_authenticated():
        st.sidebar.caption(f"Logged in as: {get_user_email()}")
        if st.sidebar.button("Log Out"):
            logout()
            st.rerun()
        return

    with st.sidebar.form("auth_form"):
        st.write("Account Access")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        action = st.radio("Action", ["Log In", "Sign Up"], horizontal=True)
        submit = st.form_submit_button("Submit")

        if submit:
            if not email or not password:
                st.error("Email and password required.")
            elif action == "Log In":
                res = login(email, password)
                if res["ok"]: 
                    st.rerun()
                else: 
                    st.error(res["error"])
            else:
                res = sign_up(email, password)
                if res["ok"]:
                    st.success("Account created. You are now logged in.")
                    time.sleep(1) # Optional UI breather before rerun
                    st.rerun()
                else:
                    st.error(res["error"])