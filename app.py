# app.py
import streamlit as st

from pathlib import Path
import base64

from ui.sidebar import render_sidebar
from ui.encounter_mode.render import render as encounter_mode_render
from ui.boss_mode.render import render as boss_mode_render
from ui.campaign_mode.render import render as campaign_mode_render
from ui.event_mode.render import render as event_mode_render
from ui.character_mode.render import render as character_mode_render
from ui.behavior_viewer.render import render as behavior_viewer_render
from core import client_id as client_id_module
from core.settings_manager import load_settings, save_settings

st.set_page_config(
    page_title="DSBG-Shuffle",
    layout="wide",
    initial_sidebar_state="auto",
)


def _font_face_css(font_family: str, font_path: Path, weight: int = 400) -> str:
    """Return an @font-face rule embedding a local TTF as a data URI.

    Streamlit doesn't provide a static files pipeline by default; embedding keeps
    the Dark Souls look consistent in offline/Docker runs.
    """
    try:
        data = base64.b64encode(font_path.read_bytes()).decode("ascii")
    except Exception:
        return ""

    return (
        "@font-face {"
        f"font-family: '{font_family}';"
        f"src: url('data:font/ttf;base64,{data}') format('truetype');"
        f"font-weight: {int(weight)};"
        "font-style: normal;"
        "font-display: swap;"
        "}"
    )


_ASSETS_DIR = Path("assets")
_FONT_CASLON_REG = _ASSETS_DIR / "Adobe Caslon Pro Regular.ttf"
_FONT_CASLON_SEMI = _ASSETS_DIR / "AdobeCaslonProSemibold.ttf"

_embedded_fonts_css = "\n".join(
    [
        _font_face_css("DSBG-Caslon", _FONT_CASLON_REG, 400),
        _font_face_css("DSBG-Caslon", _FONT_CASLON_SEMI, 600),
    ]
)

_DS_GLOBAL_STYLE = """
    <style>
    __EMBEDDED_FONTS__

    :root {
        --ds-bg: #050506;
        --ds-bg-elev: #0b0b0d;
        --ds-panel: rgba(10, 10, 12, 0.78);
        --ds-border: rgba(255, 255, 255, 0.10);
        --ds-border-strong: rgba(255, 255, 255, 0.16);
        --ds-text: #e0d6b5;
        --ds-text-dim: rgba(224, 214, 181, 0.72);
        --ds-accent: #c28f2c;           /* ember gold */
        --ds-accent-soft: rgba(194, 143, 44, 0.25);
        --ds-danger: #b64a3a;
        --ds-shadow: 0 12px 28px rgba(0,0,0,0.88);
        --ds-font-body: "DSBG-Caslon", "Georgia", serif;
        --ds-font-display: "DSBG-Caslon", "Georgia", serif;
    }

    /* App background: ember-lit stone + subtle grit */
    .stApp {
        color: var(--ds-text);
        background-color: var(--ds-bg);
        background-image:
            radial-gradient(1200px 600px at 20% -10%, rgba(194, 143, 44, 0.10), transparent 55%),
            radial-gradient(900px 500px at 80% 0%, rgba(255, 255, 255, 0.05), transparent 60%),
            radial-gradient(800px 600px at 50% 120%, rgba(0, 0, 0, 0.75), transparent 50%),
            repeating-linear-gradient(45deg, rgba(255,255,255,0.015) 0px, rgba(255,255,255,0.015) 1px, transparent 1px, transparent 5px),
            linear-gradient(#070709 0%, #030304 35%, #000000 100%);
        background-attachment: fixed;
    }

    html, body {
        font-family: var(--ds-font-body);
        color: var(--ds-text);
    }

    /* Headings: sharper and more "metal etched" */
    div[data-testid="stMarkdownContainer"] h1,
    div[data-testid="stMarkdownContainer"] h2,
    div[data-testid="stMarkdownContainer"] h3 {
        font-family: var(--ds-font-display);
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(245, 233, 200, 0.95);
        text-shadow: 0 1px 0 rgba(0,0,0,0.65);
    }

    /* Tabs: look like worn metal with a glowing selected state */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(10, 10, 12, 0.78) !important;
        border-radius: 0 !important;
        border-bottom: 2px solid rgba(255, 255, 255, 0.14) !important;
        padding: 0.5rem 1rem !important;
        color: var(--ds-text-dim) !important;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stTabs [aria-selected="true"] {
        border-bottom-color: var(--ds-accent) !important;
        color: rgba(245, 233, 200, 0.95) !important;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.55), 0 0 0 1px var(--ds-accent-soft);
    }

    /* Sidebar: subtle divider and more compact */
    section[data-testid="stSidebar"] {
        background-color: var(--ds-bg-elev) !important;
        border-right: 1px solid var(--ds-border) !important;
    }

    /* Buttons: ember edge, steel body */
    div.stButton > button,
    button[kind="primary"],
    button[kind="secondary"] {
        border-radius: 0 !important;
        border: 1px solid var(--ds-border-strong) !important;
        background: linear-gradient(180deg, rgba(25,25,28,0.92), rgba(12,12,14,0.92)) !important;
        color: var(--ds-text) !important;
        box-shadow: 0 8px 16px rgba(0,0,0,0.55);
        transition: box-shadow 120ms ease, transform 120ms ease, border-color 120ms ease;
    }
    div.stButton > button:hover,
    button[kind="primary"]:hover,
    button[kind="secondary"]:hover {
        border-color: rgba(194, 143, 44, 0.55) !important;
        box-shadow: 0 10px 22px rgba(0,0,0,0.65), 0 0 0 1px var(--ds-accent-soft);
        transform: translateY(-1px);
    }
    div.stButton > button:active,
    button[kind="primary"]:active,
    button[kind="secondary"]:active {
        transform: translateY(0px);
    }

    /* Inputs/selects: darker fields with ember focus */
    input, textarea {
        color: var(--ds-text) !important;
        background-color: rgba(10, 10, 12, 0.75) !important;
    }
    div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div,
    div[data-baseweb="select"] > div {
        background-color: rgba(10, 10, 12, 0.75) !important;
        border: 1px solid var(--ds-border) !important;
        border-radius: 0 !important;
        box-shadow: none !important;
    }
    div[data-baseweb="input"]:focus-within > div,
    div[data-baseweb="textarea"]:focus-within > div,
    div[data-baseweb="select"]:focus-within > div {
        border-color: rgba(194, 143, 44, 0.55) !important;
        box-shadow: 0 0 0 1px var(--ds-accent-soft) !important;
    }

    /* Expanders: panel look */
    details {
        background: var(--ds-panel);
        border: 1px solid var(--ds-border);
        border-radius: 0;
        box-shadow: var(--ds-shadow);
    }
    summary {
        color: rgba(245, 233, 200, 0.92);
        font-family: var(--ds-font-display);
        letter-spacing: 0.04em;
    }

    /* Links */
    a { color: rgba(194, 143, 44, 0.92) !important; }
    a:hover { color: rgba(245, 233, 200, 0.98) !important; }

    /* Scrollbars (WebKit) */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: rgba(255,255,255,0.04); }
    ::-webkit-scrollbar-thumb {
        background: rgba(194, 143, 44, 0.35);
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.10);
    }

    /* Card-style images: subtle 3D drop shadow */
    .card-image img {
        border-radius: 6px;
        background: radial-gradient(circle at top, rgba(255,255,255,0.12) 0, rgba(10,10,12,0.92) 65%);
        box-shadow:
            0 10px 22px rgba(0, 0, 0, 0.9),
            0 0 0 1px rgba(255, 255, 255, 0.06);
    }

    /* Shared icon rows/grids used by Campaign + Encounter icon renderers */
    .campaign-party-section h5,
    .icons-section h5 {
        margin: 0.75rem 0 0.25rem 0;
        font-family: var(--ds-font-display);
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: rgba(245, 233, 200, 0.92);
    }

    .campaign-party-row,
    .icons-row {
        display: flex;
        gap: 6px;
        flex-wrap: nowrap;
        overflow-x: auto;
        padding-bottom: 2px;
    }

    .icons-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 6px;
    }

    .campaign-party-fallback,
    .icon-fallback {
        height: 48px;
        background: rgba(255,255,255,0.08);
        border: 1px solid var(--ds-border);
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        text-align: center;
        padding: 2px;
        color: var(--ds-text);
    }

    /* Tighter spacing between party/expansion icons */
    .encounter-icons-wrapper {
        display: inline-block;
        font-size: 0;              /* kills gaps from text/&nbsp; between icons */
    }

    .encounter-icons-wrapper img {
        display: inline-block;
        vertical-align: middle;
        margin-right: 0.2rem;      /* adjust to taste */
        margin-bottom: 0.15rem;    /* small vertical breathing room */
    }

    .encounter-icons-wrapper img:last-child {
        margin-right: 0;
    }
    /* Global: reduce vertical spacing for markdown elements (paragraphs, lists, headings)
       This keeps rendered dice/icon lines and short bullets more compact across the app. */
    div[data-testid="stMarkdownContainer"] > p,
    div[data-testid="stMarkdownContainer"] ul,
    div[data-testid="stMarkdownContainer"] li {
        line-height: 1.20 !important;
        margin-top: 0.20rem !important;
        margin-bottom: 0.20rem !important;
    }
    div[data-testid="stMarkdownContainer"] h1,
    div[data-testid="stMarkdownContainer"] h2,
    div[data-testid="stMarkdownContainer"] h3,
    div[data-testid="stMarkdownContainer"] h4,
    div[data-testid="stMarkdownContainer"] h5 {
        margin-top: 0.48rem !important;
        margin-bottom: 0.48rem !important;
    }
    </style>
"""

st.markdown(
    _DS_GLOBAL_STYLE.replace("__EMBEDDED_FONTS__", _embedded_fonts_css),
    unsafe_allow_html=True,
)

# Ensure client_id from browser localStorage is available before loading settings
try:
    cid = client_id_module.get_or_create_client_id()
    try:
        st.session_state["client_id"] = cid
    except Exception:
        pass
except Exception:
    # If client-side helper fails, continue — server-side generation will happen later
    pass

# --- Initialize Settings ---
if "user_settings" not in st.session_state:
    st.session_state.user_settings = load_settings()

settings = st.session_state.user_settings

# NG+ is read by game logic via st.session_state (see core.ngplus.get_current_ngplus_level).
# Initialize it from persisted settings if not already set.
if "ngplus_level" not in st.session_state:
    try:
        st.session_state["ngplus_level"] = int(settings.get("ngplus_level", 0) or 0)
    except Exception:
        st.session_state["ngplus_level"] = 0

# If settings were just saved (manual Save button), clean up state that may now
# be invalid under the new settings (e.g., current encounter containing enemies
# from a now-disabled expansion).
if st.session_state.pop("_settings_just_saved", False):
    try:
        old_exp = set(st.session_state.pop("_settings_old_active_expansions", []) or [])
        new_exp = set(st.session_state.pop("_settings_new_active_expansions", []) or [])
    except Exception:
        old_exp, new_exp = set(), set()

    if old_exp != new_exp:
        for key in [
            "current_encounter",
            "last_encounter",
            "encounter_play",
            "encounter_events",
            "encounter_dropdown",
        ]:
            try:
                st.session_state.pop(key, None)
            except Exception:
                pass

# Ensure a single per-client `client_id` exists in session and persisted settings.
# This avoids multiple different UUIDs being generated across reruns.
try:
    client_id = st.session_state.get("client_id") or settings.get("client_id")
except Exception:
    client_id = settings.get("client_id") if isinstance(settings, dict) else None

if not client_id:
    import uuid

    client_id = str(uuid.uuid4())
    settings["client_id"] = client_id
    try:
        st.session_state["client_id"] = client_id
    except Exception:
        pass
    # Persist settings with the new client_id (this will upsert to Supabase when configured)
    st.session_state["_settings_allow_save"] = True
    save_settings(settings)
    st.session_state["_settings_allow_save"] = False

# --- One-shot cross-tab handoff: Campaign Mode -> app bootstrap ---
# Campaign Setup tab cannot safely overwrite sidebar widget keys after widgets
# are instantiated on the current run. Instead it sets:
#
#   st.session_state["pending_campaign_snapshot"] = {"name": <str>, "snapshot": <dict>}
#
# On the next run, `app.py` applies the snapshot *before* creating any sidebar
# widgets so it can seed widget-backed session keys (expansions/party/NG+).
# This also restores the correct campaign state dict under:
#   - "campaign_v1_state" when snapshot["rules_version"] == "V1"
#   - "campaign_v2_state" otherwise
# The key is deleted after applying so it behaves as a one-shot.
#
# Session keys touched (high-level):
# - Reads: pending_campaign_snapshot
# - Writes: campaign_rules_version, campaign_v1_state/campaign_v2_state,
#   active_expansions, selected_characters, ngplus_level, user_settings,
#   campaign_load_notice
# - Deletes: pending_campaign_snapshot
#
# NOTE: `_settings_allow_save` is currently advisory; save_settings(...) does not
# consult it (it exists as a potential future gate for UI-driven saves).
# --- Apply pending campaign snapshot (from Campaign Mode) *before* sidebar widgets ---
pending = st.session_state.get("pending_campaign_snapshot")
if pending:
    snap_name = pending.get("name")
    snapshot = pending.get("snapshot", {}) or {}

    snap_version = snapshot.get("rules_version", "V1")
    st.session_state["campaign_rules_version"] = snap_version

    # Restore campaign state dict for correct version
    state_key = "campaign_v1_state" if snap_version == "V1" else "campaign_v2_state"
    st.session_state[state_key] = snapshot.get("state", {}) or {}

    # Restore sidebar-related settings (expansions, party, NG+)
    snap_sidebar = snapshot.get("sidebar_settings", {}) or {}
    changes = []

    snap_exp = snap_sidebar.get("active_expansions")
    if snap_exp is not None and snap_exp != settings.get("active_expansions"):
        settings["active_expansions"] = snap_exp
        # Safe now: widget with this key does not exist yet on this run
        st.session_state["active_expansions"] = snap_exp
        changes.append("expansions")

    snap_chars = snap_sidebar.get("selected_characters")
    if snap_chars is not None and snap_chars != settings.get("selected_characters"):
        settings["selected_characters"] = snap_chars
        st.session_state["selected_characters"] = snap_chars
        changes.append("party")

    snap_ng = snap_sidebar.get("ngplus_level")
    if snap_ng is not None:
        snap_ng_int = int(snap_ng)
        current_ng = int(st.session_state.get("ngplus_level", 0))
        if snap_ng_int != current_ng:
            st.session_state["ngplus_level"] = snap_ng_int
            changes.append("NG+ level")

    # Persist updated settings
    st.session_state["user_settings"] = settings
    st.session_state["_settings_allow_save"] = True
    save_settings(settings)
    st.session_state["_settings_allow_save"] = False

    # One-shot notice for Campaign Mode UI
    st.session_state["campaign_load_notice"] = {
        "name": snap_name,
        "changes": changes,
    }

    # Clear the pending snapshot flag
    del st.session_state["pending_campaign_snapshot"]

# Sidebar: expansions + party + NG+

selected_characters = settings.get("selected_characters", [])
character_count = len(selected_characters)
valid_party = 0 < character_count <= 4
st.session_state["player_count"] = character_count

# --- One-shot cross-tab handoff: Campaign Mode -> Boss Mode ---
# Campaign Mode can request an immediate Boss Mode view (e.g., after a boss node
# is selected). Contract:
#   st.session_state["pending_boss_mode_from_campaign"] = {"boss_name": <str>}
# `app.py` switches `mode` and provides Boss Mode a preselection via
# `st.session_state["boss_mode_pending_name"]`. The pending key is always
# deleted after processing.
pending_boss = st.session_state.get("pending_boss_mode_from_campaign")
if pending_boss:
    boss_name = pending_boss.get("boss_name")
    if boss_name:
        st.session_state["mode"] = "Boss Mode"
        st.session_state["boss_mode_pending_name"] = boss_name
    del st.session_state["pending_boss_mode_from_campaign"]
mode = st.sidebar.radio(
    "Mode",
    ["Encounter Mode", "Event Mode", "Boss Mode", "Campaign Mode", "Character Mode", "Behavior Card Viewer"],
    key="mode",
)

render_sidebar(settings)

# Recompute selected characters and party size after sidebar widgets may have
# mutated `settings` via `st.session_state` so renderers get current values.
selected_characters = settings.get("selected_characters", [])
character_count = len(selected_characters)
valid_party = 0 < character_count <= 4
st.session_state["player_count"] = character_count

if mode == "Encounter Mode":
    encounter_mode_render(settings, valid_party, character_count)
elif mode == "Event Mode":
    event_mode_render(settings)
elif mode == "Boss Mode":
    boss_mode_render()
elif mode == "Campaign Mode":
    campaign_mode_render()
elif mode == "Character Mode":
    character_mode_render(settings)
elif mode == "Behavior Card Viewer":
    behavior_viewer_render()
