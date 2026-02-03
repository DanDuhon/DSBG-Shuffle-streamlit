# app.py
import streamlit as st

from pathlib import Path
import base64
import os
import time

from ui.sidebar import render_sidebar
from ui.encounter_mode.render import render as encounter_mode_render
from ui.boss_mode.render import render as boss_mode_render
from ui.campaign_mode.render import render as campaign_mode_render
from ui.event_mode.render import render as event_mode_render
from ui.character_mode.render import render as character_mode_render
from ui.behavior_viewer.render import render as behavior_viewer_render
from core import auth
from core.settings_manager import get_config_bool, is_streamlit_cloud, load_settings, save_settings

_APP_START = time.perf_counter()

st.set_page_config(
    page_title="DSBG-Shuffle",
    layout="wide",
    initial_sidebar_state="auto",
)


def _cloud_low_memory_enabled() -> bool:
    """Cloud-only: enable low-memory UX + aggressive cleanup.

    Defaults to enabled on Streamlit Cloud.
    """

    try:
        if not is_streamlit_cloud():
            return False
        return bool(get_config_bool("DSBG_CLOUD_LOW_MEMORY", default=True))
    except Exception:
        return False


def _strip_image_fields_inplace(obj: object) -> None:
    """Best-effort removal of heavyweight image payloads from nested dicts."""

    if not isinstance(obj, dict):
        return

    for k in ("card_img", "card_bytes", "buf", "image", "img", "image_bytes"):
        try:
            obj.pop(k, None)
        except Exception:
            pass


def _cloud_low_memory_sanitize_session_state() -> None:
    """Drop heavyweight image payloads that can linger in session_state."""

    # Encounter Mode: current encounter dict can hold PIL objects and PNG bytes.
    try:
        _strip_image_fields_inplace(st.session_state.get("current_encounter"))
    except Exception:
        pass

    # Saved encounters (session cache only; persistence already strips images).
    try:
        saved = st.session_state.get("saved_encounters")
        if isinstance(saved, dict):
            for v in saved.values():
                _strip_image_fields_inplace(v)
    except Exception:
        pass

    # Any other known encounter/campaign frozen dicts.
    for key in (
        "encounter_play",
        "campaign_v1_last_frozen",
        "campaign_v2_last_frozen",
    ):
        try:
            _strip_image_fields_inplace(st.session_state.get(key))
        except Exception:
            pass


def _cloud_low_memory_cleanup_on_mode_switch(prev_mode: str | None, new_mode: str | None) -> None:
    """Cloud-only cleanup when switching top-level modes.

    Preserve core state (campaign progress, settings), but drop derived
    heavyweight render artifacts.
    """

    # Encounter card images and buffers are the primary known offenders.
    try:
        _strip_image_fields_inplace(st.session_state.get("current_encounter"))
    except Exception:
        pass

    # Clear per-mode transient render caches.
    for k in (
        "_memdbg_last",
        "_dsbg_auth_js_used_this_run",
        "_dsbg_js_keys_used_this_run",
    ):
        try:
            st.session_state.pop(k, None)
        except Exception:
            pass




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


@st.cache_resource(show_spinner=False)
def _get_embedded_fonts_css_cached() -> str:
    return _build_embedded_fonts_css()


def _build_embedded_fonts_css() -> str:
    return "\n".join(
        [
            _font_face_css("DSBG-Caslon", _FONT_CASLON_REG, 400),
            _font_face_css("DSBG-Caslon", _FONT_CASLON_SEMI, 600),
        ]
    )


_embedded_fonts_css = (
    _get_embedded_fonts_css_cached()
    if get_config_bool("DSBG_CACHE_EMBEDDED_FONTS", default=True)
    else _build_embedded_fonts_css()
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

# Auth session hydration should run at most once per rerun.
# `core.auth.ensure_session_loaded()` uses this flag to avoid creating
# duplicate streamlit-javascript components in the same run.
try:
    st.session_state["_dsbg_auth_js_used_this_run"] = False
    st.session_state["_dsbg_js_keys_used_this_run"] = []
except Exception:
    pass

# --- Initialize Settings ---
if "user_settings" not in st.session_state:
    st.session_state.user_settings = load_settings()

# Streamlit Cloud: if the user logs in/out, reload per-account settings.
# This keeps the experience intuitive (login immediately pulls your saved settings).
if auth.is_auth_ui_enabled():
    try:
        current_uid = auth.get_user_id()
    except Exception:
        current_uid = None
    previous_uid = st.session_state.get("_auth_user_id")
    if current_uid != previous_uid:
        st.session_state["_auth_user_id"] = current_uid
        st.session_state.user_settings = load_settings()
        # Reset sidebar draft state so widgets re-seed cleanly.
        for k in ["_settings_draft", "_settings_draft_base_fp", "_settings_ui_base_fp"]:
            try:
                st.session_state.pop(k, None)
            except Exception:
                pass
        st.rerun()

settings = st.session_state.user_settings

# Cloud-only low-memory mode (affects UI + caching behavior). This is intentionally
# session-state based so UI modules can gate behavior without adding new params.
st.session_state["cloud_low_memory"] = bool(_cloud_low_memory_enabled())
if st.session_state.get("cloud_low_memory"):
    _cloud_low_memory_sanitize_session_state()

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
    from ui.campaign_mode.persistence.dirty import set_campaign_baseline

    snap_name = pending.get("name")
    snapshot = pending.get("snapshot", {}) or {}

    snap_version = snapshot.get("rules_version", "V1")
    st.session_state["campaign_rules_version"] = snap_version

    # Keep the Setup tab radio widget and version-switch tracker in sync.
    # (The radio uses a separate key to avoid Streamlit widget-state conflicts.)
    st.session_state["campaign_rules_version_widget"] = snap_version
    st.session_state["_campaign_rules_version_last"] = snap_version

    # Restore campaign state dict for correct version
    state_key = "campaign_v1_state" if snap_version == "V1" else "campaign_v2_state"
    loaded_state = snapshot.get("state", {}) or {}
    st.session_state[state_key] = loaded_state

    # IMPORTANT: Clear widget-backed keys so numeric inputs re-seed from the
    # loaded snapshot rather than retaining stale values from a previous session.
    # This is especially important on Streamlit Cloud, where users frequently
    # load/save across logins and reruns.
    for k in (
        "campaign_v1_sparks_campaign",
        "campaign_v1_souls_campaign",
        "campaign_v2_sparks_campaign",
        "campaign_v2_souls_campaign",
    ):
        try:
            st.session_state.pop(k, None)
        except Exception:
            pass

    # Mark this loaded campaign as clean (no unsaved changes yet).
    set_campaign_baseline(version=snap_version, state=loaded_state)

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

prev_mode = st.session_state.get("_last_mode") or st.session_state.get("mode")
mode = st.sidebar.radio(
    "Mode",
    ["Encounter Mode", "Event Mode", "Boss Mode", "Campaign Mode", "Character Mode", "Behavior Card Viewer"],
    key="mode",
)

if st.session_state.get("cloud_low_memory") and prev_mode != mode:
    _cloud_low_memory_cleanup_on_mode_switch(prev_mode, mode)
st.session_state["_last_mode"] = mode

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


def _rss_mb() -> float | None:
    """Best-effort RSS in MB (Linux/proc only)."""
    try:
        status = Path("/proc/self/status")
        if not status.exists():
            return None
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    kb = float(parts[1])
                    return kb / 1024.0
    except Exception:
        return None
    return None


if is_streamlit_cloud() and get_config_bool("DSBG_DEBUG_PERF", default=False):
    elapsed_s = time.perf_counter() - _APP_START
    with st.sidebar.expander("Diagnostics", expanded=False):
        st.caption(f"Render time: {elapsed_s:.3f}s")
        rss = _rss_mb()
        if rss is not None:
            st.caption(f"RSS: {rss:.1f} MB")
        try:
            st.caption(f"Python PID: {os.getpid()}")
        except Exception:
            pass


def _memory_debug_enabled() -> bool:
    # Allow enabling locally via env/secrets, but default to off.
    try:
        return bool(get_config_bool("DSBG_DEBUG_MEMORY", default=False))
    except Exception:
        return False


if _memory_debug_enabled():
    from ui.shared.memory_debug import (
        format_bytes,
        get_process_rss_mb,
        memlog_checkpoint,
        memlog_clear,
        memlog_export_json,
        memlog_get_events,
        memtrace_arm,
        memtrace_disarm,
        summarize_mapping,
    )

    with st.sidebar.expander("Debug: Memory", expanded=False):
        rss_now = get_process_rss_mb()
        if rss_now is not None:
            st.caption(f"Process RSS: {rss_now:.1f} MB")

        st.markdown("##### Checkpoint log")
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            st.session_state["_memdbg_log_enabled"] = st.checkbox(
                "Enable checkpoint logging",
                value=bool(st.session_state.get("_memdbg_log_enabled", False)),
                key="memdbg_log_enabled",
            )
        with c2:
            st.session_state["_memdbg_log_gc"] = st.checkbox(
                "GC at checkpoint",
                value=bool(st.session_state.get("_memdbg_log_gc", False)),
                key="memdbg_log_gc",
            )
        with c3:
            st.session_state["_memdbg_log_trace"] = st.checkbox(
                "Trace alloc (slow)",
                value=bool(st.session_state.get("_memdbg_log_trace", False)),
                key="memdbg_log_trace",
            )

        if bool(st.session_state.get("_memdbg_log_trace", False)):
            t1, t2 = st.columns(2)
            with t1:
                if st.button("Arm trace window", width="stretch", key="memdbg_trace_arm"):
                    memtrace_arm(st.session_state)
                    st.info("Trace armed: next two checkpoints will produce a diff.")
            with t2:
                if st.button("Disarm trace", width="stretch", key="memdbg_trace_disarm"):
                    memtrace_disarm(st.session_state)
                    st.rerun()

        st.session_state["_memdbg_sample_every"] = st.number_input(
            "Sample every N checkpoints",
            min_value=1,
            max_value=100,
            value=int(st.session_state.get("_memdbg_sample_every", 1) or 1),
            step=1,
            help="Higher values reduce log volume in tight loops.",
            key="memdbg_sample_every",
        )

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Checkpoint now", width="stretch", key="memdbg_checkpoint_now"):
                memlog_checkpoint(st.session_state, "manual", force=True, extra={"where": "sidebar"})
                st.rerun()
        with b2:
            if st.button("Clear checkpoint log", width="stretch", key="memdbg_clear_log"):
                memlog_clear(st.session_state)
                st.rerun()
        with b3:
            st.download_button(
                "Export log JSON",
                data=memlog_export_json(st.session_state),
                file_name="dsbg_memlog.json",
                mime="application/json",
                use_container_width=True,
                key="memdbg_export_log",
            )

        events = memlog_get_events(st.session_state)
        if events:
            # Optional: summarize deltas by label to quickly spot the hot step.
            if st.button("Summarize checkpoint log", width="stretch", key="memdbg_summarize"):
                by_label = {}
                last_lru = None
                for e in events:
                    if not isinstance(e, dict):
                        continue
                    label = str(e.get("label") or "")
                    delta = e.get("delta_mb")
                    if isinstance(delta, (int, float)):
                        agg = by_label.setdefault(label, {"count": 0, "sum_delta": 0.0, "max_delta": None, "min_delta": None})
                        agg["count"] += 1
                        agg["sum_delta"] += float(delta)
                        mx = agg.get("max_delta")
                        mn = agg.get("min_delta")
                        agg["max_delta"] = float(delta) if mx is None else max(float(mx), float(delta))
                        agg["min_delta"] = float(delta) if mn is None else min(float(mn), float(delta))

                    extra = e.get("extra")
                    if isinstance(extra, dict) and isinstance(extra.get("encgen_lru"), dict):
                        last_lru = extra.get("encgen_lru")

                rows = []
                for label, agg in by_label.items():
                    c = int(agg.get("count") or 0)
                    s = float(agg.get("sum_delta") or 0.0)
                    rows.append(
                        {
                            "label": label,
                            "count": c,
                            "sum_delta_mb": round(s, 3),
                            "avg_delta_mb": round((s / c) if c else 0.0, 3),
                            "max_delta_mb": agg.get("max_delta"),
                            "min_delta_mb": agg.get("min_delta"),
                        }
                    )

                rows.sort(key=lambda r: abs(float(r.get("sum_delta_mb") or 0.0)), reverse=True)
                st.dataframe(rows, width="stretch", hide_index=True)

                if isinstance(last_lru, dict) and last_lru:
                    # Show the most recent cache sizes captured from encounter generation.
                    lru_rows = []
                    for k, ci in last_lru.items():
                        if not isinstance(ci, dict):
                            continue
                        lru_rows.append({"cache": str(k), "currsize": ci.get("currsize"), "maxsize": ci.get("maxsize"), "hits": ci.get("hits"), "misses": ci.get("misses")})
                    if lru_rows:
                        st.markdown("**Latest encounter-image cache sizes**")
                        st.dataframe(lru_rows, width="stretch", hide_index=True)

            # Show a compact table of the most recent events.
            show_n = min(200, len(events))
            rows = []
            for e in events[-show_n:]:
                if not isinstance(e, dict):
                    continue
                extra = e.get("extra")
                extra_str = ""
                if isinstance(extra, dict) and extra:
                    # Keep the table readable; full payload is in the JSON export.
                    try:
                        # Prefer small highlights.
                        keys = [k for k in ("op", "level", "encounter", "stage", "attempt", "ok") if k in extra]
                        if keys:
                            extra_str = ", ".join(f"{k}={extra.get(k)!r}" for k in keys)
                        else:
                            extra_str = str(list(extra.keys())[:6])
                    except Exception:
                        extra_str = "(extra)"

                trace = e.get("trace_top")
                trace_hint = ""
                if isinstance(trace, list) and trace:
                    trace_hint = str(trace[0])

                rows.append(
                    {
                        "seq": e.get("seq"),
                        "label": e.get("label"),
                        "rss_mb": e.get("rss_mb"),
                        "delta_mb": e.get("delta_mb"),
                        "gc_ms": e.get("gc_ms"),
                        "extra": extra_str,
                        "trace_top": trace_hint,
                    }
                )

            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.caption("No checkpoints yet. Enable logging, then run a shuffle or generate a campaign.")

        # Compute-on-demand so we don't add overhead to normal runs.
        if st.button("Compute session_state breakdown", width="stretch", key="memdbg_compute"):
            total, top = summarize_mapping(
                st.session_state,
                top_n=30,
                max_depth=6,
                max_children=2000,
            )
            st.session_state["_memdbg_last"] = {
                "total": int(total),
                "top": [e.__dict__ for e in top],
            }

        last = st.session_state.get("_memdbg_last")
        if isinstance(last, dict) and last.get("top"):
            total_b = int(last.get("total") or 0)
            st.caption(f"Approx session_state total: {format_bytes(total_b)}")
            rows = []
            for e in list(last.get("top") or []):
                if not isinstance(e, dict):
                    continue
                rows.append(
                    {
                        "key": str(e.get("key")),
                        "size": format_bytes(int(e.get("bytes") or 0)),
                        "type": str(e.get("type_name") or ""),
                    }
                )
            if rows:
                st.dataframe(rows, width="stretch", hide_index=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Clear Streamlit caches", width="stretch", key="memdbg_clear_caches"):
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                try:
                    st.cache_resource.clear()
                except Exception:
                    pass
                st.success("Cleared Streamlit caches.")
                st.rerun()
        with c2:
            if st.button("Clear mem debug output", width="stretch", key="memdbg_clear_output"):
                st.session_state.pop("_memdbg_last", None)
                st.rerun()
