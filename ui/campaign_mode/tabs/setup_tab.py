#ui/campaign_mode/setup_tab.py
import copy
import streamlit as st
from typing import Any, Dict
import logging

from core import auth
from ui.campaign_mode.core import _default_sparks_max
from ui.campaign_mode.generation import (
    _filter_bosses,
    _generate_v1_campaign,
    _generate_v2_campaign,
)
from ui.campaign_mode.persistence import(
    CampaignsUnavailable,
    get_campaigns,
    _save_campaigns,
)
from ui.campaign_mode.persistence.dirty import (
    any_campaign_has_unsaved_changes,
    campaign_has_unsaved_changes,
    clear_campaign_baseline,
    set_campaign_baseline,
)

from core.settings_manager import _has_supabase_config, is_streamlit_cloud
from ui.campaign_mode.state import (
    _get_player_count,
    _ensure_v1_state,
    _ensure_v2_state,
    clear_other_campaign_state,
    queue_widget_set,
)
from core.debug import dump_session_state


_PENDING_WIDGET_RESETS_KEY = "_campaign_pending_widget_resets"


def _queue_widget_reset(widget_key: str) -> None:
    """Request that a widget session key be cleared on the *next* rerun.

    Streamlit forbids modifying a widget-backed `st.session_state[key]` after the
    widget is instantiated in the same run. To safely "reset" checkboxes after a
    button click, we enqueue the key and clear it before widgets are created on
    the subsequent rerun.
    """

    if not widget_key:
        return

    pending = st.session_state.get(_PENDING_WIDGET_RESETS_KEY)
    if not isinstance(pending, list):
        pending = []
    if widget_key not in pending:
        pending.append(widget_key)
    st.session_state[_PENDING_WIDGET_RESETS_KEY] = pending


def _apply_pending_widget_resets() -> None:
    pending = st.session_state.get(_PENDING_WIDGET_RESETS_KEY)
    if not pending:
        return
    if not isinstance(pending, list):
        st.session_state.pop(_PENDING_WIDGET_RESETS_KEY, None)
        return

    for key in pending:
        # Clearing the key (rather than setting False) ensures the widget will
        # re-seed from its `value=` default on the next creation.
        st.session_state.pop(str(key), None)

    # Clear the queue.
    st.session_state[_PENDING_WIDGET_RESETS_KEY] = []


def _has_any_loaded_campaign() -> bool:
    """Return True if either V1 or V2 currently has a generated/loaded campaign."""
    v1 = st.session_state.get("campaign_v1_state")
    if isinstance(v1, dict) and isinstance(v1.get("campaign"), dict):
        return True
    v2 = st.session_state.get("campaign_v2_state")
    if isinstance(v2, dict) and isinstance(v2.get("campaign"), dict):
        return True
    return False


def _render_setup_header(settings: Dict[str, Any]) -> tuple[str, int]:
    """Render Campaign setup header controls.

    Session keys touched:
    - Reads/writes: "campaign_rules_version" (authoritative rule version)
    - Widget-only: "campaign_rules_version_widget" (separate key to avoid Streamlit
      widget-state conflicts when programmatically mutating the authoritative key)
    """
    player_count = _get_player_count(settings)
    options = ["V1", "V2"]
    current = st.session_state.get("campaign_rules_version", "V1")
    if current not in options:
        current = "V1"
    index = options.index(current)

    # Widget uses a different key so we can freely mutate campaign_rules_version.
    # Only provide `index` the first time the widget is created; passing
    # `index` on every render can interfere with the widget's internal state
    # and cause clicks to require multiple presses to take effect.
    radio_kwargs = {"options": options, "horizontal": True, "key": "campaign_rules_version_widget"}
    if "campaign_rules_version_widget" not in st.session_state:
        radio_kwargs["index"] = index
    prev_version = st.session_state.get("_campaign_rules_version_last")
    if prev_version not in options:
        prev_version = current

    version = st.radio("Rules version", **radio_kwargs)

    # Option B: switching versions clears the other version's state so
    # completion/status cannot leak across. Discarding UNSAVED progress that way
    # is irreversible, so defer it behind an explicit confirmation (Generate and
    # Load already gate the same kind of destruction).
    if version != prev_version:
        if campaign_has_unsaved_changes(version=prev_version):
            st.session_state["_campaign_pending_discard"] = prev_version
        else:
            clear_other_campaign_state(keep_version=version)
            st.session_state.pop("_campaign_pending_discard", None)

    # This is now safe; no widget with this key exists
    st.session_state["campaign_rules_version"] = version
    st.session_state["_campaign_rules_version_last"] = version

    pending = st.session_state.get("_campaign_pending_discard")
    if pending == version:
        # Switched back to it; nothing to discard.
        st.session_state.pop("_campaign_pending_discard", None)
    elif pending:
        if campaign_has_unsaved_changes(version=pending):
            st.warning(
                f"Your {pending} campaign has unsaved changes. It is being kept "
                f"for now — save it below, or switch back to {pending} to keep "
                "playing it. Discarding it cannot be undone."
            )
            if st.button(
                f"Discard unsaved {pending} campaign",
                key=f"campaign_discard_{pending}",
            ):
                clear_other_campaign_state(keep_version=version)
                st.session_state.pop("_campaign_pending_discard", None)
                st.rerun()
        else:
            # It got saved in the meantime; clearing is safe now.
            clear_other_campaign_state(keep_version=version)
            st.session_state.pop("_campaign_pending_discard", None)

    st.markdown("---")
    return version, player_count


def _render_v1_setup(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    player_count: int,
) -> Dict[str, Any]:
    state = _ensure_v1_state(player_count)

    # Apply any pending checkbox resets *before* creating widgets.
    _apply_pending_widget_resets()
    active_expansions = settings.get("active_expansions") or []

    mini_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mini boss",
        active_expansions=active_expansions,
    )
    main_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="main boss",
        active_expansions=active_expansions,
    )
    mega_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mega boss",
        active_expansions=active_expansions,
    )

    if bool(st.session_state.get("ui_compact")):
        cols = [st.container(), st.container(), st.container()]
    else:
        cols = st.columns(3)


    # Mini boss
    with cols[0]:
        st.markdown("**Mini Boss**")
        if not mini_bosses:
            st.caption("No mini bosses available with current expansions.")
            state["bosses"]["mini"] = "Random"
        else:
            mini_names = [b["name"] for b in mini_bosses]
            mini_options = ["Random"] + mini_names
            current = state["bosses"].get("mini", "Random")
            if current not in mini_options:
                current = "Random"
            mini_choice = st.selectbox(
                "Mini boss",
                options=mini_options,
                index=mini_options.index(current),
                key="campaign_v1_mini_boss",
            )
            state["bosses"]["mini"] = mini_choice

    # Main boss
    with cols[1]:
        st.markdown("**Main Boss**")
        if not main_bosses:
            st.caption("No main bosses available with current expansions.")
            state["bosses"]["main"] = "Random"
        else:
            main_names = [b["name"] for b in main_bosses]
            main_options = ["Random"] + main_names
            current = state["bosses"].get("main", "Random")
            if current not in main_options:
                current = "Random"
            main_choice = st.selectbox(
                "Main boss",
                options=main_options,
                index=main_options.index(current),
                key="campaign_v1_main_boss",
            )
            state["bosses"]["main"] = main_choice

    # Mega boss
    with cols[2]:
        st.markdown("**Mega Boss**")
        if not mega_bosses:
            st.caption("No mega bosses available with current expansions.")
            state["bosses"]["mega"] = "None"
        else:
            mega_names = [b["name"] for b in mega_bosses]
            mega_options = ["None", "Random"] + mega_names
            current = state["bosses"].get("mega", "None")
            if current not in mega_options:
                current = "None"
            mega_choice = st.selectbox(
                "Mega boss (optional)",
                options=mega_options,
                index=mega_options.index(current),
                key="campaign_v1_mega_boss",
            )
            state["bosses"]["mega"] = mega_choice

    # --- Generate full campaign encounters (frozen) ---
    # Option: only use original enemy lists when building encounters
    if "only_original_enemies" not in state:
        state["only_original_enemies"] = False
    only_original = st.checkbox(
        "Only use original enemies (do not select alternative enemy sets)",
        value=bool(state.get("only_original_enemies", False)),
        key="campaign_v1_only_original_enemies",
    )
    state["only_original_enemies"] = bool(only_original)
    # Mirror into settings so campaign generation code can read it
    settings["only_original_enemies_for_campaigns"] = bool(only_original)

    needs_confirm = bool(_has_any_loaded_campaign() and any_campaign_has_unsaved_changes())
    confirm_key = "campaign_v1_generate_confirm_overwrite"
    confirm_ok = True
    if needs_confirm:
        st.warning("Generating a new campaign will replace your current unsaved campaign.")
        confirm_ok = bool(
            st.checkbox(
                "I understand — overwrite current campaign",
                key=confirm_key,
                value=False,
            )
        )

    if st.button(
        "Generate campaign ⚙️",
        key="campaign_v1_generate",
        width="stretch",
        disabled=bool(needs_confirm and not confirm_ok),
    ):
        # Option B: generating a V1 campaign discards any loaded V2 campaign.
        clear_other_campaign_state(keep_version="V1")
        with st.spinner("Generating campaign..."):
            campaign = _generate_v1_campaign(bosses_by_name, settings, state)
        state["campaign"] = campaign
        player_count = _get_player_count(settings)
        sparks_max = int(_default_sparks_max(player_count))
        if sparks_max < 1:
            sparks_max = 1
        state["sparks_max"] = sparks_max
        state["sparks"] = sparks_max
        sparks_key = "campaign_v1_sparks_campaign"
        queue_widget_set(sparks_key, sparks_max)
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0
        st.session_state["campaign_v1_state"] = state
        # Generated campaigns are unsaved by default.
        clear_campaign_baseline(version="V1")
        # Reset confirmation on the next run so we don't mutate widget state after creation.
        _queue_widget_reset(confirm_key)
        st.session_state["campaign_generate_notice"] = "Campaign generated."
        st.rerun()

    notice = st.session_state.pop("campaign_generate_notice", None)
    if notice:
        st.success(str(notice))

    st.markdown("### Campaign overview")

    def describe_slot(label: str, slot_key: str) -> str:
        sel = state["bosses"].get(slot_key, "Random" if slot_key != "mega" else "None")
        if sel == "Random":
            return f"{label}: Random (boss revealed when reached)"
        if slot_key == "mega" and sel == "None":
            return f"{label}: None selected"
        return f"{label}: {sel}"

    st.markdown(f"- **{describe_slot('Mini boss', 'mini')}**")
    st.markdown(f"- **{describe_slot('Main boss', 'main')}**")
    st.markdown(f"- **{describe_slot('Mega boss', 'mega')}**")

    return state


def _render_v2_setup(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    player_count: int,
) -> Dict[str, Any]:
    """
    V2 Setup:
    - Same boss-selection controls as V1 for now.
    - Campaign generation creates encounter spaces with two choices each.
    """
    state = _ensure_v2_state(player_count)

    # Apply any pending checkbox resets *before* creating widgets.
    _apply_pending_widget_resets()
    active_expansions = settings.get("active_expansions") or []

    mini_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mini boss",
        active_expansions=active_expansions,
    )
    main_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="main boss",
        active_expansions=active_expansions,
    )
    mega_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mega boss",
        active_expansions=active_expansions,
    )

    if bool(st.session_state.get("ui_compact")):
        cols = [st.container(), st.container(), st.container()]
    else:
        cols = st.columns(3)

    # Mini boss
    with cols[0]:
        st.markdown("**Mini Boss**")
        if not mini_bosses:
            st.caption("No mini bosses available with current expansions.")
            state["bosses"]["mini"] = "Random"
        else:
            mini_names = [b["name"] for b in mini_bosses]
            mini_options = ["Random"] + mini_names
            current = state["bosses"].get("mini", "Random")
            if current not in mini_options:
                current = "Random"
            mini_choice = st.selectbox(
                "Mini boss",
                options=mini_options,
                index=mini_options.index(current),
                key="campaign_v2_mini_boss",
            )
            state["bosses"]["mini"] = mini_choice

    # Main boss
    with cols[1]:
        st.markdown("**Main Boss**")
        if not main_bosses:
            st.caption("No main bosses available with current expansions.")
            state["bosses"]["main"] = "Random"
        else:
            main_names = [b["name"] for b in main_bosses]
            main_options = ["Random"] + main_names
            current = state["bosses"].get("main", "Random")
            if current not in main_options:
                current = "Random"
            main_choice = st.selectbox(
                "Main boss",
                options=main_options,
                index=main_options.index(current),
                key="campaign_v2_main_boss",
            )
            state["bosses"]["main"] = main_choice

    # Mega boss
    with cols[2]:
        st.markdown("**Mega Boss**")
        if not mega_bosses:
            st.caption("No mega bosses available with current expansions.")
            state["bosses"]["mega"] = "None"
        else:
            mega_names = [b["name"] for b in mega_bosses]
            mega_options = ["None", "Random"] + mega_names
            current = state["bosses"].get("mega", "None")
            if current not in mega_options:
                current = "None"
            mega_choice = st.selectbox(
                "Mega boss (optional)",
                options=mega_options,
                index=mega_options.index(current),
                key="campaign_v2_mega_boss",
            )
            state["bosses"]["mega"] = mega_choice

    # Option: only use original enemy lists when building encounters (V2)
    if "only_original_enemies" not in state:
        state["only_original_enemies"] = False
    only_original = st.checkbox(
        "Only use original enemies (do not select alternative enemy sets)",
        value=bool(state.get("only_original_enemies", False)),
        key="campaign_v2_only_original_enemies",
    )
    state["only_original_enemies"] = bool(only_original)
    # Mirror into settings so campaign generation reads it immediately
    settings["only_original_enemies_for_campaigns"] = bool(only_original)

    needs_confirm = bool(_has_any_loaded_campaign() and any_campaign_has_unsaved_changes())
    confirm_key = "campaign_v2_generate_confirm_overwrite"
    confirm_ok = True
    if needs_confirm:
        st.warning("Generating a new campaign will replace your current unsaved campaign.")
        confirm_ok = bool(
            st.checkbox(
                "I understand — overwrite current campaign",
                key=confirm_key,
                value=False,
            )
        )

    if st.button(
        "Generate campaign ⚙️",
        key="campaign_v2_generate",
        width="stretch",
        disabled=bool(needs_confirm and not confirm_ok),
    ):
        # Option B: generating a V2 campaign discards any loaded V1 campaign.
        clear_other_campaign_state(keep_version="V2")
        with st.spinner("Generating V2 campaign..."):
            # Mirror v2-only original-enemy option into settings as well
            if "only_original_enemies" not in state:
                state["only_original_enemies"] = False
            settings["only_original_enemies_for_campaigns"] = bool(state.get("only_original_enemies", False))
            campaign = _generate_v2_campaign(bosses_by_name, settings, state)
        state["campaign"] = campaign
        player_count = _get_player_count(settings)
        sparks_max = int(_default_sparks_max(player_count))
        if sparks_max < 1:
            sparks_max = 1
        state["sparks_max"] = sparks_max
        state["sparks"] = sparks_max
        sparks_key = "campaign_v2_sparks_campaign"
        queue_widget_set(sparks_key, sparks_max)
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0
        st.session_state["campaign_v2_state"] = state
        # Generated campaigns are unsaved by default.
        clear_campaign_baseline(version="V2")
        # Reset confirmation on the next run so we don't mutate widget state after creation.
        _queue_widget_reset(confirm_key)
        st.session_state["campaign_generate_notice"] = "Campaign generated."
        st.rerun()

    notice = st.session_state.pop("campaign_generate_notice", None)
    if notice:
        st.success(str(notice))

    st.markdown("### Campaign overview")

    def describe_slot(label: str, slot_key: str) -> str:
        sel = state["bosses"].get(slot_key, "Random" if slot_key != "mega" else "None")
        if sel == "Random":
            return f"{label}: Random (boss revealed when reached)"
        if slot_key == "mega" and sel == "None":
            return f"{label}: None selected"
        return f"{label}: {sel}"

    st.markdown(f"- **{describe_slot('Mini boss', 'mini')}**")
    st.markdown(f"- **{describe_slot('Main boss', 'main')}**")
    st.markdown(f"- **{describe_slot('Mega boss', 'mega')}**")

    st.session_state["campaign_v2_state"] = state
    return state


def _render_save_load_section(
    version: str,
    current_state: Dict[str, Any],
    settings: Dict[str, Any],
) -> None:
    # Apply any pending resets before creating Save/Load widgets.
    _apply_pending_widget_resets()

    st.markdown("---")
    st.subheader("Save / Load campaign")

    # One-shot notice carried across the post-save rerun (see the save handler).
    save_notice = st.session_state.pop("campaign_save_notice", None)
    if save_notice:
        st.success(str(save_notice))

    cloud_mode = bool(is_streamlit_cloud())
    supabase_ready = bool(_has_supabase_config())
    can_persist = (not cloud_mode) or (supabase_ready and auth.is_authenticated())
    if cloud_mode and not supabase_ready:
        st.caption("Saving is disabled until Supabase is configured.")
    elif cloud_mode and not auth.is_authenticated():
        st.caption("Log in to save.")

    try:
        campaigns = get_campaigns()
        campaigns_available = True
    except CampaignsUnavailable:
        campaigns = {}
        campaigns_available = False
        st.error(
            "Could not reach the campaign store, so your saved campaigns can't "
            "be listed right now. They have not been deleted — check your "
            "connection and reload."
        )

    if bool(st.session_state.get("ui_compact")):
        col_save = st.container()
        col_load = st.container()
    else:
        col_save, col_load = st.columns([1, 1])


    # ----- SAVE -----
    with col_save:
        default_name = str(current_state.get("name", "")).strip()
        name_input = st.text_input(
            "Campaign name",
            value=default_name,
            key=f"campaign_name_{version}",
            # This tab stops rendering when the user switches tabs; without
            # session persistence a half-typed name would be lost.
            persist_state="session",
        )

        # Overwrite confirmation when saving to an existing name
        save_overwrite_ok = True
        if name_input.strip() in campaigns:
            save_overwrite_ok = bool(
                st.checkbox(
                    "Overwrite existing saved campaign",
                    key=f"campaign_save_overwrite_ok_{version}",
                    value=False,
                )
            )

        if st.button(
            "Save campaign 💾",
            key=f"campaign_save_{version}",
            width="stretch",
            disabled=not can_persist,
        ):
            name = name_input.strip()
            # Flat chain, not early `return`s: returning here exits
            # `_render_save_load_section` from inside `with col_save:`, which
            # takes the entire Load/Delete column -- plus the load notice and
            # the debug expander -- off the page for that run. Reachable by
            # saving over an existing name without ticking overwrite.
            if not name:
                st.error("Campaign name is required to save.")
            elif not can_persist:
                st.error("Not logged in; cannot persist on Streamlit Cloud.")
            elif name in campaigns and not save_overwrite_ok:
                st.warning("That name already exists — confirm overwrite to replace it.")
            # For campaign rules versions that rely on an explicit node track
            # (V1 and V2), require a generated campaign so Campaign can resume.
            elif version in ("V1", "V2") and not isinstance(
                current_state.get("campaign"), dict
            ):
                st.error(
                    "Generate the campaign before saving; "
                    "this save currently has no encounters."
                )
            else:
                current_state["name"] = name
                # Snapshot round-trip:
                # - `state` captures the campaign version-specific runtime state dict.
                # - `sidebar_settings` captures only the settings that must be applied
                #   *before* sidebar widgets are created on the next run
                #   (expansions/party/NG+).
                # The load path hands this snapshot back to `app.py` via a one-shot
                # session key.
                snapshot = {
                    "rules_version": version,
                    # Deep-copy: `current_state` is the live session_state
                    # dict. Storing it by reference makes the saved snapshot
                    # keep mutating as the user keeps playing, so the next
                    # save of ANY campaign rewrites this one's file entry.
                    "state": copy.deepcopy(current_state),
                    "sidebar_settings": {
                        "active_expansions": settings.get("active_expansions"),
                        "selected_characters": settings.get("selected_characters"),
                        "ngplus_level": int(
                            st.session_state.get("ngplus_level", 0)
                        ),
                    },
                }
                campaigns[name] = snapshot
                if not _save_campaigns(campaigns):
                    # Leave the campaign dirty so the user keeps their
                    # overwrite warnings and knows it is still unsaved.
                    campaigns.pop(name, None)
                    st.error(
                        f"Could not save campaign '{name}'. Your progress is "
                        "still unsaved — check your connection and try again."
                    )
                else:
                    set_campaign_baseline(version=version, state=current_state)
                    # Rerun so the Load/Delete controls appear immediately.
                    # They are rendered from `campaigns`, which is read at
                    # the top of this function; without a rerun the newly
                    # saved campaign can be missed for that run. Delete and
                    # Generate already rerun for the same reason.
                    st.session_state["campaign_save_notice"] = (
                        f"Saved campaign '{name}'."
                    )
                    st.rerun()

    # ----- LOAD / DELETE -----
    with col_load:
        if campaigns:
            names = sorted(campaigns.keys())
            selected_name = st.selectbox(
                "Existing campaigns",
                options=["<none>"] + names,
                index=0,
                key=f"campaign_load_select_{version}",
                # Keep the picked campaign across a tab switch.
                persist_state="session",
            )

            if bool(st.session_state.get("ui_compact")):
                load_col = st.container()
                delete_col = st.container()
            else:
                load_col, delete_col = st.columns([1, 1])


            with load_col:
                # Only require overwrite confirmation when the campaign version that
                # will be overwritten has unsaved changes.
                target_version = version
                if selected_name != "<none>":
                    snap = campaigns.get(selected_name) or {}
                    if isinstance(snap, dict):
                        target_version = str(snap.get("rules_version") or version)
                needs_confirm = bool(
                    _has_any_loaded_campaign()
                    and campaign_has_unsaved_changes(version=target_version)
                )
                confirm_ok = True
                if needs_confirm:
                    confirm_ok = bool(
                        st.checkbox(
                            "Overwrite current campaign when loading",
                            key=f"campaign_load_confirm_overwrite_{version}",
                            value=False,
                        )
                    )
                if st.button(
                    "Load selected campaign 📥",
                    key=f"campaign_load_btn_{version}",
                    width="stretch",
                    disabled=bool(needs_confirm and not confirm_ok),
                ):
                    if selected_name != "<none>":
                        snapshot = campaigns[selected_name]
                        # Reset confirmation checkbox next run (avoid mutating widget state).
                        _queue_widget_reset(f"campaign_load_confirm_overwrite_{version}")
                        # One-shot load handoff:
                        # We cannot safely overwrite sidebar widget keys mid-run, so we
                        # stash the chosen snapshot under `pending_campaign_snapshot` and
                        # trigger `st.rerun()`. `app.py` consumes this flag early on the next
                        # run, restores campaign state, seeds sidebar session keys, persists
                        # settings, and then deletes the flag.
                        st.session_state["pending_campaign_snapshot"] = {
                            "name": selected_name,
                            "snapshot": snapshot,
                        }
                        st.rerun()

            with delete_col:
                if st.button(
                    "Delete selected 🗑️",
                    key=f"campaign_delete_btn_{version}",
                    width="stretch",
                    disabled=not can_persist,
                ):
                    if selected_name == "<none>":
                        st.error("Select a campaign to delete.")
                    else:
                        removed = campaigns.pop(selected_name, None)
                        if _save_campaigns(campaigns):
                            st.success(f"Deleted campaign '{selected_name}'.")
                            st.rerun()
                        else:
                            # Put it back so the list still matches what is stored.
                            if removed is not None:
                                campaigns[selected_name] = removed
                            st.error(
                                f"Could not delete campaign '{selected_name}'. "
                                "Check your connection and try again."
                            )
        elif campaigns_available:
            # Only claim there are none when we actually got a reliable answer.
            st.caption("No saved campaigns yet.")

        # One-shot notice: appears directly under the load controls
        notice = st.session_state.pop("campaign_load_notice", None)
        if notice:
            name = notice.get("name") or "Unnamed"
            changes = notice.get("changes") or []
            if changes:
                st.success(
                    f"Loaded campaign '{name}' and updated: "
                    + ", ".join(changes)
                    + "."
                )
            else:
                st.success(f"Loaded campaign '{name}' (no sidebar changes).")

        # --- Debug expander: session-state dumper ---
        try:
            with st.expander("Debug (developer)"):
                if st.button("Dump session_state to file", key=f"campaign_debug_dump_{version}"):
                    try:
                        # Pass the Streamlit session_state object directly; the
                        # dumper is resilient to it and will extract keys.
                        path = dump_session_state(st.session_state)
                        logging.getLogger("dsbg").info(f"Wrote session_state dump: {path}")
                        st.success(f"Wrote session_state dump: {path}")
                    except Exception as e:
                        logging.getLogger("dsbg").exception("Failed to write session_state dump")
                        st.error(f"Failed to write session_state dump: {e}")
                if st.button("Show session_state in UI", key=f"campaign_debug_show_{version}"):
                    try:
                        # Build a safe dict for UI display by converting non-serializable
                        # values to strings.
                        def _safe(v):
                            try:
                                import json as _json

                                _json.dumps(v)
                                return v
                            except Exception:
                                try:
                                    return str(v)
                                except Exception:
                                    return "<unserializable>"

                        ss = {}
                        for k, val in dict(st.session_state).items():
                            ss[str(k)] = _safe(val)

                        st.json(ss)
                    except Exception:
                        logging.getLogger("dsbg").exception("Failed to render session_state in UI")
                        st.error("Failed to render session_state in UI")
        except Exception:
            logging.getLogger("dsbg").exception("Debug expander failed")

