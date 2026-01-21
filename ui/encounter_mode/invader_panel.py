# ui/encounter_mode/invader_panel.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import random
import streamlit as st

from core.behavior.assets import BEHAVIOR_CARDS_PATH, _behavior_image_path
from core.behavior.generation import (
    build_behavior_catalog,
    render_data_card_cached,
    render_behavior_card_cached,
)
from core.behavior.logic import (
    _ensure_state,
    _new_state_from_file,
    _load_cfg_for_state,
    _draw_card,
    _manual_heatup,
    check_and_trigger_heatup,
)
from core.behavior.models import BehaviorEntry, BehaviorConfig
from ui.encounter_mode import play_state
from core.ngplus import get_current_ngplus_level


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_invaders_tab(encounter: dict) -> None:
    """
    Top-level entry for the 'Invaders' tab in the Play screen.

    - Detect which invaders appear in this encounter.
    - If none, show a small caption and exit.
    - If exactly one, render that invader directly.
    - If multiple, show a radio to select which invader to control.
    """
    _ensure_state()  # make sure hp_tracker / heatup flags exist

    entries = _get_invader_behavior_entries_for_encounter(encounter)
    if not entries:
        st.caption("No invaders with behavior decks found for this encounter.")
        return

    if len(entries) == 1:
        entry = entries[0]
    else:
        entry = _invader_selector(entries, encounter)

    if entry is None:
        return

    _render_single_invader(entry, encounter)


def reset_invaders_for_encounter(encounter: dict) -> None:
    """
    Hook to be called from the main encounter reset logic.

    For any invaders in this encounter, this will:

      - Rebuild their behavior deck state from disk (fresh state).
      - Reset their entity HP back to max.
      - Clear their HP tracker entries so the slider re-initializes.
      - Bump 'deck_reset_id' so the slider key changes and picks up
        the fresh default value.
    """
    entries = _get_invader_behavior_entries_for_encounter(encounter)
    if not entries:
        return

    # Start with whatever tracker we already have (or an empty dict)
    tracker = st.session_state.get("hp_tracker") or {}

    current_ng = int(get_current_ngplus_level() or 0)

    for entry in entries:
        state_key = _invader_state_key(entry, encounter)

        # Build a brand-new state + cfg for this invader
        state, cfg = _new_state_from_file(str(entry.path))

        state["ngplus_level"] = current_ng
        
        st.session_state[state_key] = state

        # Reset HP on the BehaviorConfig entities and clear tracker
        for ent in getattr(cfg, "entities", []):
            ent_id = getattr(ent, "id", None)
            if not ent_id:
                continue

            # Full heal on reset
            if hasattr(ent, "hp_max"):
                ent.hp = ent.hp_max
            # Clear any old HP tracker entry for this entity
            tracker.pop(ent_id, None)

        # Also mirror the HP reset into state["entities"], like the main
        # _reset_deck logic does, so any other logic that inspects the
        # state mirror sees full HP.
        for ent_state in state.get("entities", []):
            if isinstance(ent_state, dict):
                hp_max = ent_state.get("hp_max")
                if hp_max is not None:
                    ent_state["hp"] = hp_max
                    ent_state["crossed"] = []
            else:
                if hasattr(ent_state, "hp_max"):
                    ent_state.hp = ent_state.hp_max
                    ent_state.crossed = []

    # Persist the updated HP tracker back into session_state
    st.session_state["hp_tracker"] = tracker

    # Bump reset id so the slider's key changes and re-initializes
    st.session_state["deck_reset_id"] = st.session_state.get("deck_reset_id", 0) + 1


# ---------------------------------------------------------------------------
# Discovery helpers: which invaders are in this encounter?
# ---------------------------------------------------------------------------

def _get_invader_behavior_entries_for_encounter(encounter: dict) -> List[BehaviorEntry]:
    """
    Return BehaviorEntry objects for invaders that are actually present
    in this encounter.

    Matching strategy:

    1) If the encounter JSON explicitly marks invaders (e.g. an
       `invaders` field), use that list first.
       - Supports a list of strings/ids or dicts with 'name' /
         'display_name' / 'id'.

    2) If no explicit invader list is found or it's empty, fall back to
       the encounter's enemy display names via `_get_enemy_display_names`.

    3) Build the behavior catalog with `build_behavior_catalog()` and
       keep only entries where `is_invader` is True.

    4) Match by case-insensitive name against the invader names derived
       in steps (1) / (2), preserving the encounter order and skipping
       duplicates.
    """

    def _norm(s: str) -> str:
        return s.strip().lower()

    # --- 1) Prefer explicit invader list if present ---
    invader_names: List[str] = []
    raw_invaders = encounter.get("invaders")

    if raw_invaders:
        # Accept either a single dict/string or a list
        if not isinstance(raw_invaders, (list, tuple)):
            raw_invaders = [raw_invaders]

        for item in raw_invaders:
            name = None
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("display_name")
                    or item.get("id")
                )
            else:
                name = str(item)

            if name:
                invader_names.append(str(name))

    # --- 2) Build a lookup of invader BehaviorEntries by normalized name ---
    catalog = build_behavior_catalog()
    by_name: Dict[str, BehaviorEntry] = {}

    for entries in catalog.values():
        for entry in entries:
            if getattr(entry, "is_invader", False) and entry.name:
                key = _norm(entry.name)
                # First one wins; avoid overwriting if multiple share a name
                by_name.setdefault(key, entry)

    # --- 3) Preserve encounter order, avoid duplicates ---
    seen: set[str] = set()
    result: List[BehaviorEntry] = []

    for name in invader_names:
        key = _norm(name)
        if key in seen:
            continue
        entry = by_name.get(key)
        if entry is not None:
            seen.add(key)
            result.append(entry)

    return result


from ui.encounter_mode.helpers import _get_enemy_display_names



# ---------------------------------------------------------------------------
# Per-invader state helpers
# ---------------------------------------------------------------------------

def _invader_state_key(entry: BehaviorEntry, encounter: dict) -> str:
    """
    Build a stable key for this invader's deck state within this encounter.

    Uses the encounter id (if available) plus the invader name so that
    switching encounters doesn't leak state between them.
    """
    enc_id = play_state.get_encounter_id(encounter) or "unknown_encounter"
    return f"invader_deck::{enc_id}::{entry.name}"


def _ensure_invader_state(entry: BehaviorEntry, encounter: dict) -> dict:
    """
    Initialize or load the behavior deck state for a single invader.

    This wraps _new_state_from_file so we can reuse the same state
    structure that the Behavior Decks tab already expects.
    """
    state_key = _invader_state_key(entry, encounter)

    current_ng = int(get_current_ngplus_level() or 0)
    existing = st.session_state.get(state_key)
    if existing:
        cached_ng = int(existing.get("ngplus_level", -1))
        if cached_ng == current_ng:
            return existing

    # NG+ changed (or no state): rebuild from disk so NG+ is re-applied
    state, cfg = _new_state_from_file(str(entry.path))
    state["ngplus_level"] = current_ng
    st.session_state[state_key] = state

    # Reset HP slider initialization to pick up new hp_max
    tracker = st.session_state.get("hp_tracker") or {}
    for ent in getattr(cfg, "entities", []) or []:
        ent_id = getattr(ent, "id", None)
        if ent_id:
            tracker.pop(ent_id, None)
    st.session_state["hp_tracker"] = tracker
    st.session_state["deck_reset_id"] = st.session_state.get("deck_reset_id", 0) + 1

    return state


# ---------------------------------------------------------------------------
# UI: selection and rendering
# ---------------------------------------------------------------------------

def _invader_selector(entries: List[BehaviorEntry], encounter: dict) -> Optional[BehaviorEntry]:
    """
    Option D:
      - If there are multiple invaders, show a simple radio control.
      - Preserve the last choice for this encounter if possible.
    """
    enc_id = play_state.get_encounter_id(encounter) or "unknown_encounter"
    session_key = f"invader_choice::{enc_id}"

    names = [e.name for e in entries]
    default_name = st.session_state.get(session_key, names[0])

    choice = st.radio(
        "Select invader:",
        options=names,
        index=names.index(default_name) if default_name in names else 0,
        key=session_key,
    )

    for entry in entries:
        if entry.name == choice:
            return entry

    return None


def _render_single_invader(entry: BehaviorEntry, encounter: dict) -> None:
    """
    Render the full UI for a single invader:

    Layout:

        ┌───────────────────────┬────────────────────────┐
        │ Data card             │ Current behavior card  │
        ├───────────────────────┼────────────────────────┤
        │ HP slider             │ Deck controls          │
        └───────────────────────┴────────────────────────┘
    """
    # Ensure we have a deck state for this invader
    state = _ensure_invader_state(entry, encounter)

    # Get the BehaviorConfig associated with this state
    cfg = _load_cfg_for_state(state)
    if not cfg:
        st.error("Unable to load behavior data for this invader.")
        return

    # Prefer a display_name in the raw JSON if present, fall back to cfg.name
    display_name = (
        cfg.raw.get("display_name")
        or cfg.raw.get("name")
        or cfg.name
    )

    st.markdown(f"### Invader: {display_name}")

    # Two columns for the dashboard layout
    col_left, col_right = st.columns(2, gap="medium")

    # --- Set up placeholders + bottom-row content first ---

    # LEFT: header + data-card placeholder + HP block
    with col_left:
        st.markdown("**Data Card**")
        data_ph = st.empty()  # will hold the data card image
        _render_invader_health_block(cfg, state)  # HP under the card

    # RIGHT: header + behavior-card placeholder + deck controls
    with col_right:
        st.markdown("**Current Card**")
        behavior_ph = st.empty()  # will hold the current behavior card image
        _render_invader_deck_controls(cfg, state)  # buttons under the card

    # At this point, if the Draw button was clicked on this rerun,
    # _render_invader_deck_controls has already called _draw_card(state)
    # and mutated the state. Now we compute the images from the *updated* state.
    data_bytes, behavior_bytes = _get_invader_card_images(cfg, state)

    # --- Fill in the image placeholders (top row) ---

    if data_bytes is not None:
        data_ph.image(data_bytes, width="stretch")
    else:
        data_ph.caption("No data card image found.")

    if behavior_bytes is not None:
        behavior_ph.image(behavior_bytes, width="stretch")
    else:
        behavior_ph.caption("No card drawn yet.")



def _get_invader_card_images(
    cfg: BehaviorConfig,
    state: dict,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    """
    Return (data_card_bytes, current_behavior_card_bytes) for this invader.

    - Uses the same boss-style layout as the Behavior Decks tab.
    - No dual-boss or other special cases; invaders are treated as
      single-entity bosses.
    """
    # --- Data card ---
    data_bytes: Optional[bytes] = None
    behavior_bytes: Optional[bytes] = None

    data_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
    data_bytes = render_data_card_cached(
        data_path,
        cfg.raw,
        is_boss=True,  # invaders use boss-style data cards
    )

    # --- Current behavior card ---
    current = state.get("current_card")
    if not current:
        return data_bytes, None

    # Behavior Decks sometimes stores current_card as a tuple for weird
    # bosses; for invaders we still guard defensively.
    if isinstance(current, tuple):
        beh_key = current[0] if current and isinstance(current[0], str) else None
    else:
        beh_key = current

    if not isinstance(beh_key, str):
        return data_bytes, None

    beh_json = cfg.behaviors.get(beh_key, {})
    current_path = _behavior_image_path(cfg, beh_key)

    behavior_bytes = render_behavior_card_cached(
        current_path,
        beh_json,
        is_boss=True,  # boss-style layout
    )

    return data_bytes, behavior_bytes


def _render_invader_health_block(cfg: BehaviorConfig, state: dict) -> None:
    """
    Render a compact HP tracker for this invader and trigger heat-up
    automatically when HP crosses thresholds.

    Uses the same pattern as render_health_tracker, but for a single
    entity and with check_and_trigger_heatup.
    """
    tracker = st.session_state.setdefault("hp_tracker", {})
    reset_id = st.session_state.get("deck_reset_id", 0)

    entities = getattr(cfg, "entities", []) or []

    if entities:
        ent = entities[0]
        ent_id = getattr(ent, "id", cfg.name)
        hp_default = int(getattr(ent, "hp", 0) or 0)
        hp_max = int(getattr(ent, "hp_max", hp_default) or hp_default or 0)
    else:
        ent = None
        ent_id = cfg.name
        hp_default = int(cfg.raw.get("hp", 0)) if isinstance(cfg.raw, dict) else 0
        hp_max = hp_default

    hp_max = max(0, hp_max)

    initial_val = int(tracker.get(ent_id, {}).get("hp", hp_default))
    if hp_max > 0:
        initial_val = max(0, min(initial_val, hp_max))

    slider_key = f"invader_hp_{ent_id}_{reset_id}"

    # Keys for pending heat-up confirmation for this specific invader
    pending_flag_key = f"invader_heatup_pending_{ent_id}"
    pending_prev_key = f"invader_heatup_prev_{ent_id}"
    pending_new_key = f"invader_heatup_new_{ent_id}"

    # --- on_change callback, bound to this slider/key/entity ---
    def _on_hp_change(
        *,
        _slider_key=slider_key,
        _ent_id=ent_id,
        _hpmax=hp_max,
        _hp_default=hp_default,
        _ent=ent,
        _cfg=cfg,
        _state=state,
        _pending_flag_key=pending_flag_key,
        _pending_prev_key=pending_prev_key,
        _pending_new_key=pending_new_key,
    ):
        # New value from the slider
        val = st.session_state.get(_slider_key, _hp_default)
        val = max(0, min(int(val), int(_hpmax)))

        # Previous value from tracker (before this change)
        prev = int(tracker.get(_ent_id, {}).get("hp", _hp_default))

        # Store new value in the tracker
        tracker[_ent_id] = {"hp": val, "hp_max": _hpmax}
        st.session_state["hp_tracker"] = tracker

        # Keep the entity's own HP in sync
        if _ent is not None:
            _ent.hp = val

            # Detect if we *crossed* any heat-up threshold on the way down
            thresholds = getattr(_ent, "heatup_thresholds", []) or []
            crossed = False
            for t in thresholds:
                t_int = int(t)
                if prev > t_int >= val:
                    crossed = True
                    break

            if crossed:
                # Don't actually heat-up yet – ask for confirmation
                st.session_state[_pending_flag_key] = True
                st.session_state[_pending_prev_key] = prev
                st.session_state[_pending_new_key] = val
            else:
                # If we moved back up above thresholds, clear any stale prompt
                if thresholds and val > min(int(t) for t in thresholds if t is not None):
                    st.session_state[_pending_flag_key] = False
                    st.session_state.pop(_pending_prev_key, None)
                    st.session_state.pop(_pending_new_key, None)

    # Slider itself; on_change handles all the logic
    st.slider(
        "HP",
        min_value=0,
        max_value=hp_max if hp_max > 0 else max(0, initial_val),
        value=initial_val,
        step=1,
        key=slider_key,
        on_change=_on_hp_change,
    )

    # Display current value from tracker (after any change)
    current_hp = int(st.session_state["hp_tracker"].get(ent_id, {}).get("hp", initial_val))
    st.caption(f"{current_hp} / {hp_max}")

    # If a threshold was crossed by this invader's slider, ask for confirmation
    if st.session_state.get(pending_flag_key):
        st.warning("This invader has entered Heat-Up range. Confirm heat-up?")

        col_confirm, col_cancel = st.columns(2)

        with col_confirm:
            if st.button("Confirm Heat-Up 🔥", key=f"{slider_key}_confirm_heatup", width="stretch"):
                prev = int(st.session_state.get(pending_prev_key, current_hp))
                new = int(st.session_state.get(pending_new_key, current_hp))

                if ent is not None:
                    rng = random.Random()
                    # Now actually perform the heat-up using the same helper
                    check_and_trigger_heatup(prev, new, ent, state, cfg, rng)

                    # Keep tracker aligned with whatever HP we ended on
                    tracker[ent_id] = {"hp": new, "hp_max": hp_max}
                    st.session_state["hp_tracker"] = tracker

                # Clear pending state
                st.session_state[pending_flag_key] = False
                st.session_state.pop(pending_prev_key, None)
                st.session_state.pop(pending_new_key, None)

                st.rerun()

        with col_cancel:
            if st.button("Cancel ❌", key=f"{slider_key}_cancel_heatup", width="stretch"):
                # Just drop the pending heat-up; no changes to heat-up state
                st.session_state[pending_flag_key] = False
                st.session_state.pop(pending_prev_key, None)
                st.session_state.pop(pending_new_key, None)

                # If you *also* want to roll HP back to pre-threshold,
                # you could optionally do that here. For now we just keep the slider.
                st.rerun()


def _render_invader_deck_controls(cfg: BehaviorConfig, state: dict) -> None:
    """
    Minimal deck controls for invaders:

    - Draw next card.
    - Optional manual heat-up button.
    - No reset button (that happens via reset_invaders_for_encounter()).
    - No save/load slots.
    """
    col_draw, col_heatup = st.columns(2)

    with col_draw:
        if st.button("Draw next card 🃏", key=f"invader_draw_{cfg.name}", width="stretch"):
            _draw_card(state)

    with col_heatup:
        # Optional: only show if cfg has heat-up behavior
        if st.button("Manual heat-up 🔥", key=f"invader_heatup_{cfg.name}", width="stretch"):
            _manual_heatup(state)
            
    draw_count = len(state.get("draw_pile", []))
    discard_count = len(state.get("discard_pile", []))
    st.caption(f"Deck: {draw_count} | Played: {discard_count}")
