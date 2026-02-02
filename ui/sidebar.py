#ui/sidebar.py
import streamlit as st
from core import auth
from core.settings_manager import get_config_str, is_streamlit_cloud, save_settings, settings_fingerprint
from datetime import datetime, timezone
from copy import deepcopy
from core.character.characters import CHARACTER_EXPANSIONS
from core.ngplus import MAX_NGPLUS_LEVEL, _HP_4_TO_7_BONUS, dodge_bonus_for_level
from core.enemies import ENEMY_EXPANSIONS_BY_ID
from ui.encounter_mode.assets import enemyNames
from ui.encounter_mode.generation import editedEncounterKeywords


all_expansions = [
    "Painted World of Ariamis",
    "The Sunless City",
    "Tomb of Giants",
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep",
    "Characters Expansion",
    "Phantoms",
    "Executioner's Chariot",
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
]
INVADER_CAP_CLAMP = {1: 2, 2: 3, 3: 5, 4: 4}
CARD_WIDTH_MIN = 240
CARD_WIDTH_MAX = 560
CARD_WIDTH_DEFAULT = 380

if "sidebar_ngplus_expanded" not in st.session_state:
    st.session_state["sidebar_ngplus_expanded"] = False


def _ngplus_level_changed():
    st.session_state["sidebar_ngplus_expanded"] = True


def _sync_invader_caps():
    settings = st.session_state.get("_settings_draft")
    if not isinstance(settings, dict):
        settings = st.session_state.get("user_settings") or {}
    caps = settings.get("max_invaders_per_level")
    if not isinstance(caps, dict):
        caps = {}
    out = {}
    for lvl, mx in INVADER_CAP_CLAMP.items():
        out[str(lvl)] = int(st.session_state.get(f"cap_invaders_lvl_{lvl}", mx))
    settings["max_invaders_per_level"] = out
    st.session_state["_settings_draft"] = settings


def render_sidebar(settings: dict):
    """Render the Settings sidebar.

    Persistence contract:
    - Local/Docker: settings changes take effect immediately and are saved to JSON automatically.
    - Streamlit Cloud: settings can be changed while logged out, but saving requires login.

    Session keys touched (high-level):
    - Applied/draft: "user_settings", "_settings_draft", "_settings_draft_base_fp", "_settings_ui_base_fp"
    - Save metadata: "_settings_last_saved_fp", "_settings_last_saved_at"
    - Representative widget keys: "ngplus_level", "ui_card_width", "ui_compact" (plus many dynamic keys)
    """

    cloud_mode = bool(is_streamlit_cloud())

    # If Cloud mode is enabled but Supabase secrets are missing, users will not
    # see login UI and nothing should persist.
    if cloud_mode:
        supa_url = get_config_str("SUPABASE_URL")
        supa_key = get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")
        if not (supa_url and supa_key):
            st.sidebar.warning(
                "Cloud mode is enabled, but Supabase secrets are missing (SUPABASE_URL and SUPABASE_ANON_KEY). "
                "Login is disabled and saves will not persist across refresh."
            )

    # Misconfiguration helper: if Supabase is configured but Cloud mode is off,
    # auth UI and save gating will be disabled and the app will fall back to
    # local JSON persistence (even if this is running on Streamlit Cloud).
    if not cloud_mode:
        supa_url = get_config_str("SUPABASE_URL")
        supa_key = get_config_str("SUPABASE_ANON_KEY") or get_config_str("SUPABASE_KEY")
        if supa_url and supa_key:
            st.sidebar.warning(
                "Supabase is configured, but DSBG_DEPLOYMENT is not set to 'cloud'. "
                "Login + per-account saving are disabled, and the app will use local JSON persistence. "
                "Set DSBG_DEPLOYMENT='cloud' in Streamlit secrets to require login to save."
            )

    # Cloud-only Account UI (Google OAuth primary + magic link fallback).
    if auth.is_auth_ui_enabled():
        st.sidebar.header("Account")
        auth.ensure_session_loaded()

        debug_perf_raw = str(get_config_str("DSBG_DEBUG_PERF") or "").strip().lower()
        debug_perf = debug_perf_raw in {"1", "true", "yes", "y", "on"}
        if debug_perf:
            with st.sidebar.expander("Debug: JS bridge", expanded=False):
                st.caption(
                    "If auth buttons say ‘no response from browser’, the Streamlit JS component may not be returning. "
                    "This test should return 2."
                )

                def _redact_url(val):
                    if not isinstance(val, str):
                        return val
                    out = val
                    for key in [
                        "access_token",
                        "refresh_token",
                        "provider_token",
                        "id_token",
                        "token",
                    ]:
                        if key in out:
                            # Very lightweight redaction: replace values like key=...& with key=REDACTED&
                            out = out.replace(f"{key}=", f"{key}=REDACTED")
                    return out

                def _redact_payload(obj):
                    if not isinstance(obj, dict):
                        return obj
                    # Shallow redaction + common nested session fields
                    red = dict(obj)
                    sess = red.get("session")
                    if isinstance(sess, dict):
                        sess = dict(sess)
                        for k in ("access_token", "refresh_token", "provider_token", "id_token"):
                            if k in sess:
                                sess[k] = "REDACTED"
                        red["session"] = sess
                    for k in ("access_token", "refresh_token", "provider_token", "id_token"):
                        if k in red:
                            red[k] = "REDACTED"
                    return red

                # Show runtime/package versions to confirm what Streamlit Cloud actually installed.
                try:
                    import sys
                    from importlib.metadata import version as _pkg_version  # type: ignore

                    st.write(
                        {
                            "python": sys.version.split(" ")[0],
                            "streamlit": getattr(st, "__version__", "(unknown)"),
                            "streamlit-javascript": _pkg_version("streamlit-javascript"),
                        }
                    )
                except Exception as e:
                    st.write({"versions_error": str(e)})

                try:
                    from streamlit_javascript import st_javascript  # type: ignore

                    # Compatibility: streamlit-javascript 0.1.5 only supports
                    # (code) or (code, waiting_text). Newer builds may support
                    # (code, default, key, ...). We only rely on the portable
                    # signatures here.
                    try:
                        test_val = st_javascript("1+1", "Waiting for response")
                    except TypeError:
                        test_val = st_javascript("1+1")

                    # A second probe that does not require async/await.
                    try:
                        href_val = st_javascript(
                            "(function(){ return window.location.href; })()",
                            "Waiting for response",
                        )
                    except TypeError:
                        href_val = st_javascript("(function(){ return window.location.href; })()")

                    # Try to read the top-level (parent) URL too; some browsers
                    # may block this in iframes, so treat failures as expected.
                    try:
                        parent_href = st_javascript(
                            "(function(){ try { return window.parent.location.href; } catch(e) { return null; } })()",
                            "Waiting for response",
                        )
                    except TypeError:
                        parent_href = st_javascript(
                            "(function(){ try { return window.parent.location.href; } catch(e) { return null; } })()"
                        )

                    st.write({
                        "js_return": test_val,
                        "href": _redact_url(href_val),
                        "parent_href": _redact_url(parent_href),
                    })
                except Exception as e:
                    st.write({"js_return": None, "error": str(e)})

                last_auth_debug = st.session_state.get("_auth_last_debug")
                if last_auth_debug is not None:
                    st.caption("Last auth response")
                    st.write(last_auth_debug)

                last_sess_raw = st.session_state.get("_auth_last_session_raw")
                if last_sess_raw is not None:
                    st.caption("Last session raw")
                    st.write(_redact_url(last_sess_raw) if isinstance(last_sess_raw, str) else last_sess_raw)

                last_sess_payload = st.session_state.get("_auth_last_session_payload")
                if last_sess_payload is not None:
                    st.caption("Last session payload")
                    st.write(_redact_payload(last_sess_payload))

                last_logout_raw = st.session_state.get("_auth_last_logout_raw")
                if last_logout_raw is not None:
                    st.caption("Last logout raw")
                    st.write(_redact_url(last_logout_raw) if isinstance(last_logout_raw, str) else last_logout_raw)

                last_logout_payload = st.session_state.get("_auth_last_logout_payload")
                if last_logout_payload is not None:
                    st.caption("Last logout payload")
                    st.write(_redact_payload(last_logout_payload) if isinstance(last_logout_payload, dict) else last_logout_payload)

                last_magic_raw = st.session_state.get("_auth_last_magic_raw")
                if last_magic_raw is not None:
                    st.caption("Last magic-link raw")
                    st.write(_redact_url(last_magic_raw) if isinstance(last_magic_raw, str) else last_magic_raw)

                last_magic_payload = st.session_state.get("_auth_last_magic_payload")
                if last_magic_payload is not None:
                    st.caption("Last magic-link payload")
                    st.write(_redact_payload(last_magic_payload) if isinstance(last_magic_payload, dict) else last_magic_payload)

        auth_err = st.session_state.get("_auth_last_error")
        if isinstance(auth_err, str) and auth_err.strip():
            st.sidebar.error(auth_err)

        if auth.is_authenticated():
            ident = auth.get_user_email() or auth.get_user_id() or "(unknown user)"
            st.sidebar.caption(f"Signed in: {ident}")
            if st.sidebar.button("Log out", width="stretch", key="auth_logout_btn"):
                auth.logout()
                st.rerun()
        else:
            if st.sidebar.button("Sign in with Google", width="stretch", key="auth_google_btn"):
                st.session_state["_auth_last_error"] = ""
                res = auth.login_google()
                if debug_perf:
                    st.session_state["_auth_last_debug"] = {"action": "google", "response": res}
                if not isinstance(res, dict):
                    st.session_state["_auth_last_error"] = (
                        "Could not start Google sign-in (no response from browser). "
                        "Try again and allow popups for this site."
                    )
                elif res.get("ok") is False:
                    err = str(res.get("error") or "Could not start Google sign-in.")
                    if "Unsupported provider" in err or "provider is not enabled" in err:
                        err = (
                            "Google sign-in is disabled in Supabase for this project. "
                            "Enable it in Supabase Dashboard → Authentication → Providers → Google.\n\n"
                            f"Details: {err}"
                        )
                    st.session_state["_auth_last_error"] = err
                elif res.get("ok") is True:
                    if res.get("authed") is True:
                        st.sidebar.success("Signed in. You can close the Google tab.")
                    else:
                        st.sidebar.caption("Google sign-in opened in a new tab. Finish sign-in there, then return here.")

            email = st.sidebar.text_input(
                "Email (magic link)",
                key="auth_magic_email",
                placeholder="you@example.com",
            )
            if st.sidebar.button(
                "Send magic link",
                width="stretch",
                key="auth_magic_btn",
            ):
                st.session_state["_auth_last_error"] = ""
                res = auth.send_magic_link(email)
                if debug_perf:
                    st.session_state["_auth_last_debug"] = {"action": "magic_link", "email": email, "response": res}

                if isinstance(res, dict) and res.get("ok") is True:
                    st.sidebar.success("Magic link sent. Check your email.")
                elif isinstance(res, dict) and res.get("maybe_sent") is True:
                    st.sidebar.success("Magic link sent (likely). Check your email.")
                    st.sidebar.caption("The browser component didn’t respond, but the email may still have been sent.")
                else:
                    if isinstance(res, dict) and res.get("error"):
                        st.session_state["_auth_last_error"] = str(res.get("error"))
                    else:
                        st.session_state["_auth_last_error"] = "Could not send magic link."

    st.sidebar.header("Settings")
    # Streamlit Cloud renders a Save UI (gated by login). Local/Docker auto-saves.
    save_ui = st.sidebar.container() if cloud_mode else None

    applied_settings = st.session_state.get("user_settings", settings) or {}
    applied_fp = settings_fingerprint(applied_settings)

    if cloud_mode:
        # Cloud: keep draft/commit model to allow "changes apply but don't persist".
        draft_settings = st.session_state.get("_settings_draft")
        draft_base_fp = st.session_state.get("_settings_draft_base_fp")
        if not isinstance(draft_settings, dict) or draft_base_fp != applied_fp:
            draft_settings = deepcopy(applied_settings)
            st.session_state["_settings_draft"] = draft_settings
            st.session_state["_settings_draft_base_fp"] = applied_fp
        settings = draft_settings
    else:
        # Local/Docker: edit the live settings dict in-place so the rest of the app
        # sees updates immediately in the same rerun.
        st.session_state["_settings_draft"] = applied_settings
        st.session_state["_settings_draft_base_fp"] = applied_fp
        settings = applied_settings

    def _key_safe(text: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text))

    # When the applied settings baseline changes (e.g., after clicking Save),
    # reset checkbox widget state to match the new draft.
    base_fp = st.session_state.get("_settings_draft_base_fp")
    old_ui_base_fp = st.session_state.get("_settings_ui_base_fp")
    ui_base_changed = old_ui_base_fp != base_fp
    if ui_base_changed:
        st.session_state["_settings_ui_base_fp"] = base_fp

    caps = settings.get("max_invaders_per_level") or {}

    # Expansions
    with st.sidebar.expander("🧩 Expansions", expanded=False):
        active_set = set(settings.get("active_expansions", []) or [])
        for exp in all_expansions:
            k = f"exp_active_{_key_safe(exp)}"
            if ui_base_changed or k not in st.session_state:
                st.session_state[k] = exp in active_set
            st.checkbox(exp, key=k)
        active_expansions = [exp for exp in all_expansions if st.session_state.get(f"exp_active_{_key_safe(exp)}")]
        settings["active_expansions"] = active_expansions

    # Characters
    available_characters = sorted(
        c for c, exps in CHARACTER_EXPANSIONS.items()
        if any(exp in active_expansions for exp in exps)
    )

    previous_selection = settings.get("selected_characters", [])
    still_valid = [c for c in previous_selection if c in available_characters]
    if len(still_valid) < len(previous_selection):
        removed = [c for c in previous_selection if c not in still_valid]
        st.sidebar.warning(f"Removed invalid characters: {', '.join(removed)}")
        for c in removed:
            st.session_state[f"party_char_{_key_safe(c)}"] = False
        settings["selected_characters"] = still_valid

    with st.sidebar.expander("🎭 Party", expanded=False):
        def _party_limit_changed(changed_key: str):
            selected_now = [
                c
                for c in available_characters
                if st.session_state.get(f"party_char_{_key_safe(c)}")
            ]
            if len(selected_now) > 4:
                st.session_state[changed_key] = False
                st.session_state["_party_max_warning"] = True

        selected_set = set(settings.get("selected_characters", []) or [])
        for c in available_characters:
            k = f"party_char_{_key_safe(c)}"
            if ui_base_changed or k not in st.session_state:
                st.session_state[k] = c in selected_set
            st.checkbox(c, key=k, on_change=_party_limit_changed, args=(k,))

        selected_characters = [c for c in available_characters if st.session_state.get(f"party_char_{_key_safe(c)}")]
        settings["selected_characters"] = selected_characters

        if st.session_state.pop("_party_max_warning", False):
            st.warning("Party is limited to 4 characters.")

    # --- New Game+ selection ---
    # (uses module-level `_ngplus_level_changed` to toggle expander open)

    # Keep NG+ as a "live" setting (drives gameplay immediately via session_state),
    # but also persist it when the user clicks Save by copying it into draft settings.
    if ui_base_changed or "ngplus_level" not in st.session_state:
        try:
            st.session_state["ngplus_level"] = int(settings.get("ngplus_level", 0) or 0)
        except Exception:
            st.session_state["ngplus_level"] = 0

    current_ng = int(st.session_state.get("ngplus_level", 0))

    with st.sidebar.expander(
        f"⬆️ New Game+ (Current: NG+{current_ng})",
        expanded=bool(st.session_state.get("sidebar_ngplus_expanded", False)),
    ):
        level = st.number_input(
            "NG+ Level",
            min_value=0,
            max_value=MAX_NGPLUS_LEVEL,
            value=max(0, min(int(current_ng), MAX_NGPLUS_LEVEL)),
            step=1,
            key="ngplus_level",
            on_change=_ngplus_level_changed,
        )
        lvl = int(level)

        # Persist into draft settings so the Save button can store it.
        settings["ngplus_level"] = int(lvl)
        st.session_state["_settings_draft"] = settings

        # Compute nodes added at this NG+ level (per-level mapping)
        extra_map = [0, 1, 1, 2, 2, 3]
        nodes_added = extra_map[lvl] if 0 <= lvl < len(extra_map) else 0

        # Optional: increase AoE node counts for Mega Bosses per NG+ level
        prev_increase = bool(settings.get("ngplus_increase_nodes", False))
        checkbox_label = "Increase AoE node count with NG+ (Mega bosses only)"

        increase_nodes = st.checkbox(
            checkbox_label,
            value=prev_increase,
            key="ngplus_increase_nodes",
        )
        settings["ngplus_increase_nodes"] = bool(increase_nodes)
        st.session_state["_settings_draft"] = settings

        if lvl > 0:
            dodge_b = dodge_bonus_for_level(lvl)
            if dodge_b == 1:
                dodge_text = "+1 to dodge difficulty."
            elif dodge_b == 2:
                dodge_text = "+2 to dodge difficulty."

            # NG+ summary text
            st.markdown(
                "\n".join(
                    [
                        f"- Base HP 1-3: +{lvl}",
                        f"- Base HP 4-7: +{_HP_4_TO_7_BONUS[lvl]}",
                        f"- Base HP 8-10: +{lvl*2}",
                        f"- Base HP 11+: +{lvl*10}% (rounded up)",
                        f"- +{lvl} damage to all attacks.",
                        f"- +{nodes_added} node{'s' if nodes_added != 1 else ''}", " to Mega Boss AoE patterns.",
                    ]
                    + ([f"- {dodge_text}"] if dodge_b > 0 else [])
                )
            )

    # Enemy selection (global): group by expansion and let user enable/disable enemies
    # Applies to both Encounter Mode and Campaign Mode generation.
    with st.sidebar.expander("🛡️ Enemy Selection", expanded=False):
        active_expansions = settings.get("active_expansions") or []
        if not active_expansions:
            st.caption("Enable expansions to pick available enemies.")
        else:
            # Build reverse map: expansion -> list of eid
            exp_map: dict = {}
            # Special combined expander for enemies that appear in both base game and Sunless City
            DSBG = "Dark Souls The Board Game"
            SUN = "The Sunless City"
            COMBO = f"{DSBG} & {SUN}"
            combo_list: list[int] = []

            for eid, exps in ENEMY_EXPANSIONS_BY_ID.items():
                # consider only expansions that are currently active
                exps_active = [exp for exp in exps if exp in active_expansions]
                if not exps_active:
                    continue
                # If enemy appears in both DSBG and Sunless City, place it in the combined list
                if DSBG in exps_active and SUN in exps_active:
                    combo_list.append(int(eid))
                    continue
                # Otherwise, add to each individual expansion that is active
                for exp in exps_active:
                    exp_map.setdefault(exp, []).append(int(eid))

            # If combo_list has entries and at least one of the two expansions is active,
            # add the combined expander to the map under a dedicated key.
            if combo_list and (DSBG in active_expansions or SUN in active_expansions):
                exp_map[COMBO] = combo_list

            # Ensure settings key exists
            settings.setdefault("enemy_included", {})
            included = settings.get("enemy_included") or {}

            # Render expanders per expansion
            seen = set()
            # Ensure the combined expander (if present) appears near the top
            ordered_exps = sorted([e for e in exp_map.keys() if e != COMBO])
            if COMBO in exp_map:
                ordered_exps = [COMBO] + ordered_exps

            for exp in ordered_exps:
                with st.expander(f"{exp}", expanded=False):
                    eids = sorted(exp_map.get(exp, []), key=lambda x: enemyNames.get(x, str(x)))
                    for idx, eid in enumerate(eids):
                        name = enemyNames.get(eid, str(eid))
                        # Only render an interactive checkbox the first time we see this enemy.
                        # If the same enemy appears under multiple expansions, show a non-interactive
                        # label in subsequent expansion groups to avoid duplicate widget keys.
                        if eid in seen:
                            st.write(f"{name}  ", unsafe_allow_html=False)
                            continue

                        seen.add(eid)
                        key = f"enemy_incl_{eid}"
                        # Persist keys as strings for JSON safety
                        default_val = bool(included.get(str(eid), True))
                        val = st.checkbox(name, value=default_val, key=key)
                        included[str(eid)] = bool(val)

            # Mirror changes back into settings/session
            settings["enemy_included"] = included
            st.session_state["_settings_draft"] = settings

    # Invaders
    with st.sidebar.expander("⚔️ Encounter Invader Cap", expanded=False):
        for lvl, mx in INVADER_CAP_CLAMP.items():
            cur = caps.get(str(lvl), mx)
            cur = int(cur)
            cur = max(0, min(cur, mx))
            st.slider(
                f"Level {lvl}",
                min_value=0,
                max_value=mx,
                value=cur,
                key=f"cap_invaders_lvl_{lvl}",
                on_change=_sync_invader_caps,
            )

    # One-time init for widget-backed session keys that must exist before widget
    # creation. This pattern prevents Streamlit from constantly resetting widget
    # values on rerun when `settings` baseline changes.
    if "ui_card_width" not in st.session_state:
        st.session_state["ui_card_width"] = int(settings.get("ui_card_width", 360))

        # Encounter item reward shuffle setting
        # Options control how encounters that specify a particular item reward are handled.
        # Persist the choice in user_settings as `encounter_item_reward_mode`.
        modes = [
            "Similar Soul Cost",
            "Same Item Tier",
            "Original",
        ]
        prev_mode = settings.get("encounter_item_reward_mode", "Original")
        with st.sidebar.expander("💎 Item Swap", expanded=False):
            mode = st.selectbox(
                "When an encounter rewards a specific item, treat it as:",
                options=modes,
                index=modes.index(prev_mode) if prev_mode in modes else modes.index("Original"),
                key="encounter_item_reward_mode",
            )
            settings["encounter_item_reward_mode"] = mode
            st.session_state["_settings_draft"] = settings

    # Rules display preference: show phase-only rules/triggers only in their phase
    prev_rules_pref = bool(settings.get("rules_show_only_in_phase", True))
    with st.sidebar.expander("⚙️ Rule/Trigger Display", expanded=False):
        rules_pref = st.checkbox(
            "Only show rules/triggers when relevant (player or enemy phase). This only affects the Play tab.",
            value=prev_rules_pref,
            key="rules_show_only_in_phase",
        )
        settings["rules_show_only_in_phase"] = bool(rules_pref)
        st.session_state["_settings_draft"] = settings

    # Edited encounters: global toggle + per-encounter status
    with st.sidebar.expander("✏️ Edited Encounters", expanded=False):
        settings.setdefault("edited_toggles", {})

        def _edited_global_changed():
            # Called when the global edited-encounters checkbox changes.
            curr = bool(st.session_state.get("edited_encounters_global", False))
            settings.setdefault("edited_toggles", {})
            # Apply the global setting to all known edited encounter toggles
            for enc_name, enc_exp in sorted(editedEncounterKeywords):
                k = f"{enc_name}|{enc_exp}"
                settings["edited_toggles"][k] = curr
                # Also update the per-encounter checkbox widget state so
                # the checkbox in the Encounter setup reflects this change
                widget_key = f"edited_toggle_{enc_name}_{enc_exp}"
                st.session_state[widget_key] = curr
            settings["edited_encounters_global"] = curr
            st.session_state["_settings_draft"] = settings

        prev_global = bool(settings.get("edited_encounters_global", False))
        # Checkbox is persisted in session state so it remains across reruns
        st.checkbox(
            "Enable edited encounters (global)",
            value=prev_global,
            key="edited_encounters_global",
            on_change=_edited_global_changed,
        )

        st.markdown("**Edited encounters available:**")
        if not editedEncounterKeywords:
            st.caption("No edited encounters available.")
        else:
            # Show list with status emoji
            edited_list = sorted(editedEncounterKeywords, key=lambda t: (t[1], t[0]))
            toggles = settings.get("edited_toggles", {})
            for enc_name, enc_exp in edited_list:
                k = f"{enc_name}|{enc_exp}"
                # Prefer the live per-encounter checkbox widget state if present
                widget_key = f"edited_toggle_{enc_name}_{enc_exp}"
                if widget_key in st.session_state:
                    enabled = bool(st.session_state.get(widget_key, False))
                else:
                    enabled = bool(toggles.get(k, False))
                emoji = "✅" if enabled else "❌"
                st.write(f"{emoji} {enc_name} ({enc_exp})")

    with st.sidebar.expander("🖼️ Card Display", expanded=False):
        st.slider(
            "Card width (px)",
            min_value=240,
            max_value=560,
            step=10,
            key="ui_card_width",
            value=int(st.session_state["ui_card_width"]),
        )
        st.caption("This scales the size of boss cards and event cards in Encounter Mode's Event tab.")

    # Sync widget -> persisted settings (mutate IN PLACE, do not replace settings dict)
    settings["ui_card_width"] = int(st.session_state["ui_card_width"])

    # Session + persisted UI controls
    # Initialize from settings if present so the choice persists across runs
    if "ui_compact" not in st.session_state:
        st.session_state["ui_compact"] = bool(settings.get("ui_compact", False))

    with st.sidebar.expander("📱 UI", expanded=False):
        st.checkbox("Compact layout (mobile)", key="ui_compact")

    # Persist the compact toggle into the settings dict (and session_state)
    settings["ui_compact"] = bool(st.session_state.get("ui_compact", False))
    st.session_state["_settings_draft"] = settings

    # Save UI is rendered in the reserved top container, but it depends on the final
    # post-widget draft state computed below (so the dirty flag is accurate).
    # --- Save UI (rendered at the top placeholder) ---
    current_fp = settings_fingerprint(settings)
    dirty = bool(current_fp != applied_fp)

    if cloud_mode and save_ui is not None:
        with save_ui:
            missing_auth_ui = cloud_mode and not auth.is_auth_ui_enabled()
            needs_login = auth.is_auth_ui_enabled() and not auth.is_authenticated()
            if missing_auth_ui:
                st.caption("Saving is disabled until Supabase auth is configured.")
            elif needs_login:
                st.caption("Log in to save.")

            if st.button(
                "Save settings",
                disabled=(not dirty) or needs_login or missing_auth_ui,
                width="stretch",
                key="save_settings_btn",
            ):
                old_active_expansions = list(applied_settings.get("active_expansions", []) or [])
                new_active_expansions = list(settings.get("active_expansions", []) or [])

                committed = deepcopy(settings)
                st.session_state["user_settings"] = committed
                st.session_state["_settings_draft"] = deepcopy(committed)
                st.session_state["_settings_draft_base_fp"] = settings_fingerprint(committed)

                ok = bool(save_settings(committed))
                if not ok:
                    st.sidebar.error("Settings were applied but could not be persisted.")

                st.session_state["_settings_just_saved"] = True
                st.session_state["_settings_old_active_expansions"] = old_active_expansions
                st.session_state["_settings_new_active_expansions"] = new_active_expansions
                st.rerun()

            last_saved_at = st.session_state.get("_settings_last_saved_at")
            if last_saved_at:
                try:
                    dt = datetime.fromisoformat(str(last_saved_at))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    local_dt = dt.astimezone()
                    save_text = local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                except Exception:
                    save_text = str(last_saved_at)
                st.caption(f"Last saved: {save_text}")
            else:
                st.caption("Last saved: —")
    elif (not cloud_mode) and dirty:
        # Local/Docker: auto-persist immediately when settings changed.
        # `save_settings` already avoids redundant writes via fingerprinting.
        save_settings(settings)
        st.session_state["_settings_draft_base_fp"] = settings_fingerprint(settings)

