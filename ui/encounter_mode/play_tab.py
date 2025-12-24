# ui/encounter_mode/play_tab.py
from __future__ import annotations

import re
import streamlit as st
import random
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from core.encounter_rules import make_encounter_key
from core.encounter import timer as timer_mod
from ui.encounter_mode import play_state, play_panels, invader_panel
from ui.encounter_mode.setup_tab import render_original_encounter
from ui.encounter_mode.assets import encounterKeywords, editedEncounterKeywords, keywordText
from core.image_cache import get_image_bytes_cached, get_image_data_uri_cached, bytes_to_data_uri
from ui.event_mode.logic import DECK_STATE_KEY as _EVENT_DECK_STATE_KEY
from ui.campaign_mode.core import ENCOUNTER_GRAVESTONES, _v2_pick_scout_ahead_alt_frozen



def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. This mirrors the helper in play_panels so the
    timer logic can share the same decision.
    """
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def _keyword_label(keyword: str) -> str:
    # Prefer the human-facing label from keywordText (everything before the em-dash).
    txt = keywordText.get(keyword)
    if isinstance(txt, str) and txt.strip():
        return txt.split("—", 1)[0].strip()

    # Fallback: camelCase -> "Title Case"
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", str(keyword)).replace("_", " ").strip()
    return spaced.title() if spaced else str(keyword)


def _get_encounter_keywords(name: str, expansion: str, edited: bool) -> list[str]:
    src = editedEncounterKeywords if edited else encounterKeywords
    raw = (src.get((name, expansion)) or []) if isinstance(src, dict) else []

    out: list[str] = []
    seen: set[str] = set()
    for k in raw:
        if not k:
            continue
        k = str(k)
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _render_keywords_summary(encounter: dict, edited: bool) -> None:
    # V1 cards typically have no keyword section; keep the UI quiet.
    expansion = encounter.get("expansion")
    if not expansion:
        return

    name = encounter.get("encounter_name") or encounter.get("name") or ""
    if not name:
        return

    keys = _get_encounter_keywords(name, expansion, edited)
    if not keys:
        return

    labels = ", ".join(_keyword_label(k) for k in keys)
    st.markdown("#### Rules")
    st.caption(f"Keywords: {labels}")


def _render_gravestones_for_encounter(encounter: Dict[str, Any], settings: dict) -> None:
    name = str((encounter or {}).get("encounter_name") or (encounter or {}).get("name") or "").strip()
    n = int(ENCOUNTER_GRAVESTONES.get(name, 0) or 0)
    if n <= 0:
        return

    def _event_card_label(card: Any) -> str:
        if isinstance(card, dict):
            nm = str(card.get("name") or card.get("id") or "").strip()
            if nm:
                return nm
            p = card.get("path")
            if isinstance(p, str) and p:
                return Path(p).stem
        if isinstance(card, str) and card:
            return Path(card).stem
        return "Event"

    def _get_event_deck_ref() -> Optional[Dict[str, Any]]:
        deck = settings.get("event_deck")
        if isinstance(deck, dict):
            return deck

        # Common fallbacks if event mode stores it directly in session_state
        for k in ("event_deck", "event_deck_state"):
            d = st.session_state.get(k)
            if isinstance(d, dict):
                settings["event_deck"] = d
                return d

        if _EVENT_DECK_STATE_KEY:
            d = st.session_state.get(_EVENT_DECK_STATE_KEY)
            if isinstance(d, dict):
                settings["event_deck"] = d
                return d

        return None
    
    def _sig(fr: Any, default_level: int) -> Optional[tuple[str, int, str]]:
        if not isinstance(fr, dict):
            return None
        try:
            exp = str(fr.get("expansion") or "")
            lvl = int(fr.get("encounter_level", default_level))
            nm = str(fr.get("encounter_name") or "")
        except Exception:
            return None
        if not exp or not nm:
            return None
        return (exp, lvl, nm)

    def _render_frozen_encounter_card(frozen: Any) -> str:
        """
        Render and return a label for a frozen campaign encounter.
        """
        if not isinstance(frozen, dict):
            st.caption("Encounter card unavailable.")
            return "Encounter"

        exp = frozen.get("expansion")
        lvl = frozen.get("encounter_level")
        nm = frozen.get("encounter_name")
        enemies = frozen.get("enemies") or []
        encounter_data = frozen.get("encounter_data")
        use_edited = bool(frozen.get("edited", False))

        label = str(nm or "Encounter")

        if not (exp and lvl is not None and nm and encounter_data):
            st.caption(label)
            return label

        res = render_original_encounter(
            encounter_data,
            exp,
            nm,
            lvl,
            use_edited,
            enemies=enemies,
        )
        if res and res.get("ok"):
            img_obj = res.get("card_img")
            img_bytes = None
            try:
                # bytes-like
                if isinstance(img_obj, (bytes, bytearray)):
                    img_bytes = bytes(img_obj)
                # BytesIO or file-like
                elif hasattr(img_obj, "read") and callable(img_obj.read):
                    try:
                        pos = None
                        try:
                            pos = img_obj.tell()
                        except Exception:
                            pos = None
                        img_obj.seek(0)
                    except Exception:
                        pass
                    try:
                        img_bytes = img_obj.read()
                    except Exception:
                        img_bytes = None
                    try:
                        if pos is not None:
                            img_obj.seek(pos)
                    except Exception:
                        pass
                # PIL Image (duck-typed by having a save method)
                elif hasattr(img_obj, "save") and callable(img_obj.save):
                    try:
                        buf = BytesIO()
                        img_obj.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                    except Exception:
                        img_bytes = None
                # Path string
                elif isinstance(img_obj, str):
                    try:
                        img_bytes = get_image_bytes_cached(img_obj)
                    except Exception:
                        img_bytes = None
            except Exception:
                img_bytes = None

                if img_bytes:
                    data_uri = bytes_to_data_uri(img_bytes, mime="image/png")
                    st.markdown(
                        f"""
                        <div class="card-image">
                            <img src="{data_uri}" style="width:100%">
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption(label)
        else:
            st.caption(label)

        return label

    def _ensure_draw_pile(deck: Dict[str, Any]) -> list:
        draw = deck.get("draw_pile")
        disc = deck.get("discard_pile")
        if not isinstance(draw, list):
            draw = []
            deck["draw_pile"] = draw
        if not isinstance(disc, list):
            disc = []
            deck["discard_pile"] = disc

        # If draw is empty but discard has cards, reshuffle discard into draw.
        if not draw and disc:
            draw[:] = disc
            disc.clear()
            random.shuffle(draw)

        return draw

    # Per-encounter persistent UI state (disables rows after use)
    ctx = str(
        encounter.get("encounter_slug")
        or encounter.get("slug")
        or f"{name}|{encounter.get('encounter_level') or encounter.get('level') or ''}"
    )
    store = st.session_state.setdefault("gravestones_state", {})
    ctx_state = store.setdefault(ctx, {})  # row_idx -> row dict

    with st.expander("Gravestones", expanded=False):
        # Header row (keeps layout readable on narrow widths)
        h0, h1, h2, h3 = st.columns([0.5, 1.5, 1.8, 1.6])
        with h0:
            st.write("")
        with h1:
            st.markdown("**Events**")
        with h2:
            st.markdown("**Encounters**")
        with h3:
            st.markdown("**Treasure**")

        for i in range(1, n + 1):
            row_key = str(i)
            row = ctx_state.setdefault(
                row_key,
                {
                    "phase": "idle",            # idle | events_choose | encounters_choose | done
                    "pending_card": None,       # events: removed top card while deciding
                    "pending_enc": None,        # encounters: {"target_node_id": str, "peek_frozen": dict}
                    "result": None,
                }
            )

            phase = str(row.get("phase") or "idle")

            c0, c1, c2, c3 = st.columns([0.5, 1.5, 1.8, 1.6])

            with c0:
                if n > 1:
                    st.write(f"{i}")

            if phase == "idle":
                # Row action buttons
                with c1:
                    if st.button("Use", key=f"gravestone_events_{ctx}_{i}", help="Use On Events", width="stretch"):
                        deck = _get_event_deck_ref()
                        if not isinstance(deck, dict):
                            row["phase"] = "done"
                            row["result"] = "No event deck is initialized in this session."
                            st.rerun()

                        draw = _ensure_draw_pile(deck)
                        if not draw:
                            row["phase"] = "done"
                            row["result"] = "Event deck is empty."
                            st.rerun()

                        # Take the top card out while the user decides.
                        top = draw.pop(0)
                        row["pending_card"] = top
                        row["phase"] = "events_choose"

                        # Keep settings/session in sync (best-effort)
                        settings["event_deck"] = deck
                        if _EVENT_DECK_STATE_KEY and isinstance(st.session_state.get(_EVENT_DECK_STATE_KEY), dict):
                            st.session_state[_EVENT_DECK_STATE_KEY] = deck

                        st.rerun()

                with c2:
                    if st.button("Use", key=f"gravestone_encounters_{ctx}_{i}", disabled=False, help="Use On Encounters", width="stretch"):
                        # Requires an active V2 campaign; encounters are peeked from the next unchosen encounter space.
                        v2_state = st.session_state.get("campaign_v2_state")
                        if not isinstance(v2_state, dict) or not isinstance(v2_state.get("campaign"), dict):
                            row["phase"] = "done"
                            row["result"] = "No V2 campaign is loaded."
                            st.rerun()

                        campaign = v2_state["campaign"]
                        nodes = campaign.get("nodes") or []
                        if not isinstance(nodes, list) or not nodes:
                            row["phase"] = "done"
                            row["result"] = "Campaign has no nodes."
                            st.rerun()

                        from_id = str(campaign.get("current_node_id") or "")

                        # Find next encounter node after from_id where choice_index is None (unchosen).
                        start_idx = -1
                        for ix, n in enumerate(nodes):
                            if n.get("id") == from_id:
                                start_idx = ix
                                break

                        target = None
                        for n in nodes[start_idx + 1 :]:
                            if n.get("kind") != "encounter":
                                continue
                            if n.get("choice_index") is None:
                                target = n
                                break

                        if not isinstance(target, dict):
                            row["phase"] = "done"
                            row["result"] = "No upcoming unchosen encounter space found."
                            st.rerun()

                        options = target.get("options")
                        if not isinstance(options, list) or not options:
                            row["phase"] = "done"
                            row["result"] = "Target encounter space has no options."
                            st.rerun()

                        peek = options[0]
                        row["pending_enc"] = {"target_node_id": str(target.get("id") or ""), "peek_frozen": peek}
                        row["phase"] = "encounters_choose"
                        st.rerun()

                with c3:
                    if st.button("Use", key=f"gravestone_treasure_{ctx}_{i}", help="Use On Treasure", width="stretch"):
                        row["phase"] = "done"
                        row["result"] = "Look at the top card of the treasure deck, then put it on the top or bottom of the deck."
                        st.rerun()

            elif phase == "events_choose":
                pending = row.get("pending_card")
                deck = _get_event_deck_ref()

                # Column 2: show the card
                with c1:
                    if isinstance(pending, dict) and pending.get("path"):
                        img_ref = pending.get("path")
                        img_bytes = None
                        try:
                            if isinstance(img_ref, (bytes, bytearray)):
                                img_bytes = bytes(img_ref)
                            elif isinstance(img_ref, str):
                                img_bytes = get_image_bytes_cached(img_ref)
                            elif hasattr(img_ref, "read") and callable(img_ref.read):
                                img_bytes = img_ref.read()
                        except Exception:
                            img_bytes = None

                        if img_bytes:
                            data_uri = bytes_to_data_uri(img_bytes, mime="image/jpeg")
                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{data_uri}" style="width:100%">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                    elif isinstance(pending, str) and pending:
                        try:
                            img_bytes = get_image_bytes_cached(pending)
                        except Exception:
                            img_bytes = None
                        if img_bytes:
                            data_uri = bytes_to_data_uri(img_bytes, mime="image/jpeg")
                            st.markdown(
                                f"""
                                <div class="card-image">
                                    <img src="{data_uri}" style="width:100%">
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                    else:
                        st.write("Event card unavailable.")
                    st.caption(_event_card_label(pending))

                # Column 3: Put On Top
                with c2:
                    if st.button("Put On Top", key=f"gravestone_evt_top_{ctx}_{i}", width="stretch"):
                        if isinstance(deck, dict):
                            draw = _ensure_draw_pile(deck)
                            draw.insert(0, pending)
                            settings["event_deck"] = deck
                            if _EVENT_DECK_STATE_KEY and isinstance(st.session_state.get(_EVENT_DECK_STATE_KEY), dict):
                                st.session_state[_EVENT_DECK_STATE_KEY] = deck

                        row["phase"] = "done"
                        row["result"] = f"{_event_card_label(pending)} put on top."
                        row["pending_card"] = None
                        st.rerun()

                # Column 4: Put On Bottom
                with c3:
                    if st.button("Put On Bottom", key=f"gravestone_evt_bottom_{ctx}_{i}", width="stretch"):
                        if isinstance(deck, dict):
                            draw = _ensure_draw_pile(deck)
                            draw.append(pending)
                            settings["event_deck"] = deck
                            if _EVENT_DECK_STATE_KEY and isinstance(st.session_state.get(_EVENT_DECK_STATE_KEY), dict):
                                st.session_state[_EVENT_DECK_STATE_KEY] = deck

                        row["phase"] = "done"
                        row["result"] = f"{_event_card_label(pending)} put on bottom."
                        row["pending_card"] = None
                        st.rerun()
            elif phase == "encounters_choose":
                pending = row.get("pending_enc") or {}
                target_node_id = str(pending.get("target_node_id") or "")
                peek_frozen = pending.get("peek_frozen")

                # Column 2: show the encounter card we are peeking at
                with c1:
                    label = _render_frozen_encounter_card(peek_frozen)

                # Column 3: Put On Top (no-op)
                with c2:
                    if st.button("Put On Top", key=f"gravestone_enc_top_{ctx}_{i}", width="stretch"):
                        row["phase"] = "done"
                        row["result"] = f"{label} put on top."
                        row["pending_enc"] = None
                        st.rerun()

                # Column 4: Put On Bottom (replace the top option on the target node)
                with c3:
                    if st.button("Put On Bottom", key=f"gravestone_enc_bottom_{ctx}_{i}", width="stretch"):
                        v2_state = st.session_state.get("campaign_v2_state")
                        if not isinstance(v2_state, dict) or not isinstance(v2_state.get("campaign"), dict):
                            row["phase"] = "done"
                            row["result"] = "No V2 campaign is loaded."
                            row["pending_enc"] = None
                            st.rerun()

                        campaign = v2_state["campaign"]
                        nodes = campaign.get("nodes") or []
                        target = None
                        for n in nodes:
                            if n.get("id") == target_node_id:
                                target = n
                                break

                        if not isinstance(target, dict):
                            row["phase"] = "done"
                            row["result"] = "Target encounter space no longer exists."
                            row["pending_enc"] = None
                            st.rerun()

                        # If the target was chosen while this UI was open, do nothing.
                        if target.get("choice_index") is not None:
                            row["phase"] = "done"
                            row["result"] = "Target encounter space was already chosen; no change made."
                            row["pending_enc"] = None
                            st.rerun()

                        options = target.get("options")
                        if not isinstance(options, list) or not options:
                            row["phase"] = "done"
                            row["result"] = "Target encounter space has no options."
                            row["pending_enc"] = None
                            st.rerun()

                        try:
                            lvl_int = int(target.get("level") or 1)
                        except Exception:
                            lvl_int = 1

                        # Exclude signatures of all current options so we don't re-roll the same card.
                        exclude: set[tuple[str, int, str]] = set()
                        for fr in options:
                            s = _sig(fr, lvl_int)
                            if s is not None:
                                exclude.add(s)

                        cand = _v2_pick_scout_ahead_alt_frozen(
                            settings=settings,
                            level=lvl_int,
                            exclude_signatures=exclude,
                            campaign=campaign,
                        )

                        if isinstance(cand, dict):
                            options[0] = cand
                            target["options"] = options
                            v2_state["campaign"] = campaign
                            st.session_state["campaign_v2_state"] = v2_state
                            row["phase"] = "done"
                            row["result"] = f"{label} put on bottom. New encounter generated."
                        else:
                            row["phase"] = "done"
                            row["result"] = "No alternative encounter found; encounter left on top."

                        row["pending_enc"] = None
                        st.rerun()

            else:
                # done
                with c1:
                    st.write("")
                with c2:
                    st.write("")
                with c3:
                    st.write("")
                msg = row.get("result")
                if isinstance(msg, str) and msg:
                    st.caption(msg)


def render(settings: dict, campaign: bool=False) -> None:
    """
    Encounter Play tab.

    Assumes:
    - Setup tab has populated st.session_state.current_encounter
    - Events tab has optionally populated st.session_state.encounter_events
    """
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    encounter = st.session_state.current_encounter
    encounter_id = play_state.get_encounter_id(encounter)
    play = play_state.ensure_play_state(encounter_id)

    name = encounter.get("encounter_name") or encounter.get("name") or "Unknown Encounter"
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    timer_behavior = timer_mod.get_timer_behavior(encounter, edited=edited)
    action = play_state.apply_pending_action(play, timer_behavior)

    if action == "reset":
        invader_panel.reset_invaders_for_encounter(encounter)

    player_count = play_state.get_player_count()
    stop_on_timer_objective = timer_mod.should_stop_on_timer_objective(
        encounter=encounter,
        edited=edited,
        player_count=player_count,
        timer_value=play["timer"],
    )

    ui_compact = bool(st.session_state.get("ui_compact", False))

    if ui_compact:
        play_panels._render_timer_and_phase(play)
        play_panels._render_turn_controls(
            play,
            stop_on_timer_objective=stop_on_timer_objective,
            timer_behavior=timer_behavior,
            compact=True,
        )
        play_panels._render_encounter_triggers(encounter, play, settings)
        if campaign:
            _render_gravestones_for_encounter(encounter, settings)
        play_panels._render_current_rules(encounter, settings, play)
        play_panels._render_keywords_summary(encounter, settings)

        tab_enemies, tab_invaders, tab_rules, tab_other = st.tabs(
            ["Enemies", "Invaders", "Rules", "Other"]
        )

        with tab_enemies:
            play_panels._render_enemy_behaviors(encounter, columns=1)

        with tab_invaders:
            invader_panel.render_invaders_tab(encounter)

        with tab_rules:
            play_panels._render_rules(encounter, settings, play)

        with tab_other:
            play_panels._render_objectives(encounter, settings)
            play_panels._render_rewards(encounter, settings)
            play_panels._render_attached_events(encounter)
            play_panels._render_log(play)

        return

    # -----------------------------------------------------------------
    # DESKTOP UI (existing 3-column layout)
    # -----------------------------------------------------------------
    col_left, col_mid, col_right = st.columns([1, 1, 1], gap="large")

    with col_left:
        timer_phase_container = st.container()
        controls_container = st.container()

        with timer_phase_container:
            play_panels._render_timer_and_phase(play)

        with controls_container:
            play_panels._render_turn_controls(
                play,
                stop_on_timer_objective=stop_on_timer_objective,
                timer_behavior=timer_behavior,
            )
            play_panels._render_encounter_triggers(encounter, play, settings)
            if campaign:
                _render_gravestones_for_encounter(encounter, settings)
            play_panels._render_attached_events(encounter)
            play_panels._render_log(play)

    with col_mid:
        objectives_container = st.container()
        rest_container = st.container()
        rewards_container = st.container()

        with objectives_container:
            play_panels._render_objectives(encounter, settings)

        with rest_container:
            play_panels._render_rules(encounter, settings, play)

        with rewards_container:
            play_panels._render_rewards(encounter, settings)

    with col_right.container():
        tab_enemies, tab_invaders = st.tabs(["Encounter Enemies", "Invaders"])

        with tab_enemies:
            play_panels._render_enemy_behaviors(encounter, columns=2)

        with tab_invaders:
            invader_panel.render_invaders_tab(encounter)
