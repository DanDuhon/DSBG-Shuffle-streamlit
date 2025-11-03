import random, time
import streamlit as st
from pathlib import Path
from core.settings_manager import load_settings, save_settings
from core import behavior_decks as bd
from core import behavior_icons as bi


BEHAVIOR_CARDS_PATH = "assets/behavior cards/"
CARD_BACK = "assets/behavior cards/back.jpg"


def _behavior_image_path(cfg, behavior_name: str) -> str:
    """Map a behavior name to its corresponding image path."""
    clean_name = bd._strip_behavior_suffix(behavior_name)
    return f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg"

def _ensure_state():
    if "behavior_deck" not in st.session_state:
        st.session_state["behavior_deck"] = None

def _new_state_from_file(fpath: str):
    cfg = bd.load_behavior(Path(fpath))
    rng = random.Random()
    
    # Pass rng into deck builder — let it handle everything, including random heat-up
    deck = bd.build_draw_pile(cfg, rng)

    state = {
        "draw_pile": deck,
        "discard_pile": [],
        "current_card": None,
        "selected_file": str(fpath),
        "display_cards": cfg.display_cards,
        "entities": [e.__dict__.copy() for e in cfg.entities]
    }
    return state, cfg

def _load_cfg_for_state(state):
    if not state or not state.get("selected_file"):
        return None
    return bd.load_behavior(Path(state["selected_file"]))

def render_health_tracker(cfg):
    tracker = st.session_state.get("hp_tracker", {})
    debounce_window = 0.5  # seconds

    # Initialize session cache for last edit timestamps
    if "last_edit" not in st.session_state:
        st.session_state["last_edit"] = {}

    for e in cfg.entities:
        ent_id = e.id
        label = e.label
        hp = e.hp
        hpmax = e.hp_max
        heat_thresh = (e.heatup_thresholds or [None])[0]
        heat_active = bool(heat_thresh is not None and hp <= heat_thresh)
        reset_id = st.session_state.get("deck_reset_id", 0)

        if cfg.name == "Executioner Chariot" and not st.session_state.get("chariot_heatup_done", False):
            new_val = st.slider(
                label,
                min_value=0,
                max_value=hpmax,
                value=0,
                disabled=True,
                key=f"slider_{ent_id}_{reset_id}",
            )
        else:
            new_val = st.slider(
                label,
                min_value=0,
                max_value=hpmax,
                value=int(hp),
                key=f"slider_{ent_id}_{reset_id}",
            )

        # --- Record timestamp on change
        if new_val != hp:
            st.session_state["last_edit"][ent_id] = time.time()

        # --- Commit if stable (no movement for > debounce_window)
        last_time = st.session_state["last_edit"].get(ent_id, 0)
        if time.time() - last_time > debounce_window:
            e.hp = int(new_val)
            tracker[ent_id] = {"hp": int(new_val), "hp_max": hpmax}

    st.session_state["hp_tracker"] = tracker
    return cfg.entities

def _draw_card(state):
    if not state["draw_pile"]:
        bd.recycle_deck(state)
    if state["draw_pile"]:
        if state.get("current_card"):
            state["discard_pile"].append(state["current_card"])
        state["current_card"] = state["draw_pile"].pop(0)

def _reset_deck(state, cfg):
    rng = random.Random()
    state["draw_pile"] = bd.build_draw_pile(cfg, rng)
    state["discard_pile"] = []
    state["current_card"] = None

    # --- Reset entities in UI state (dicts)
    for e in state["entities"]:
        if isinstance(e, dict):
            # use hp_max if present, otherwise keep current hp
            e["hp"] = e.get("hp_max", e.get("hp", 0))
            e["crossed"] = []
        else:
            # fallback: handle Entity objects just in case
            e.hp = e.hp_max
            e.crossed = []

    # --- Reset entities in cfg (the ones the sliders render)
    for ent in cfg.entities:
        ent.hp = ent.hp_max
        ent.crossed = []

    # --- Clear session-based UI states / flags
    st.session_state.pop("hp_tracker", None)
    st.session_state.pop("last_edit", None)
    st.session_state["deck_reset_id"] = st.session_state.get("deck_reset_id", 0) + 1
    st.session_state["chariot_heatup_done"] = False



def _manual_heatup(state):
    cfg = _load_cfg_for_state(state)
    if not cfg:
        return
    rng = random.Random()
    bd.apply_heatup(state, cfg, rng, reason="manual")

    # --- Special case: Executioner Chariot
    if cfg.name == "Executioner Chariot":
        st.session_state["chariot_heatup_done"] = True

        # Rebuild from 4 regular + 1 heat-up card
        base_cards = [b for b in cfg.deck if not cfg.behaviors.get(b, {}).get("heatup", False) and "Death Race" not in b and "Mega Boss Setup" not in b]
        heat_cards = [b for b in cfg.behaviors if cfg.behaviors[b].get("heatup", False)]
        rng.shuffle(base_cards)
        rng.shuffle(heat_cards)
        state["draw_pile"] = base_cards[:4] + heat_cards[:1]
        rng.shuffle(state["draw_pile"])
        state["discard_pile"].clear()
        state["current_card"] = None


def _save_slot_ui(settings, state):
    with st.expander("💾 Save / Load Deck State", expanded=False):
        # keep max 5 slots
        saves = settings.setdefault("behavior_deck_saves", [])
        # render existing
        for i in range(5):
            cols = st.columns([3, 1, 1])
            title = (saves[i]["title"] if i < len(saves) else f"Slot {i+1}")
            with cols[0]:
                new_title = st.text_input(f"Name (Slot {i+1})", value=title, key=f"slot_title_{i}")
            with cols[1]:
                if st.button("Save", key=f"slot_save_{i}"):
                    payload = bd.serialize_state(state) if state else {}
                    entry = {"title": new_title, "state": payload}
                    if i < len(saves):
                        saves[i] = entry
                    else:
                        saves.append(entry)
                    saves[:] = saves[:5]
                    save_settings(settings)
                    st.success(f"Saved to Slot {i+1}")
            with cols[2]:
                if st.button("Load", key=f"slot_load_{i}"):
                    if i < len(saves) and saves[i].get("state"):
                        st.session_state["behavior_deck"] = saves[i]["state"]
                        st.success(f"Loaded Slot {i+1}")
                        st.rerun()
        # cleanup extra slots if any
        if len(saves) > 5:
            saves[:] = saves[:5]
            save_settings(settings)

def render():
    _ensure_state()
    settings = st.session_state.get("user_settings") or load_settings()

    st.subheader("Behavior Decks")

    files = bd.list_behavior_files()
    labels = [f.name[:-5] for f in files]
    choice = st.selectbox(
        "Choose enemy / invader / boss",
        options=labels,
        index=0 if labels else None,
        key="behavior_choice",
    )

    if not (choice and files):
        st.info("Select a behavior file to begin.")
        return

    fpath = str(files[labels.index(choice)])
    cfg = bd.load_behavior(Path(fpath))

    # --- Regular enemy mode
    if "behavior" in cfg.raw:
        cols = st.columns(2)
        with cols[0]:
            data_card = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            img_bytes = bi.render_data_card(data_card, cfg.raw, is_boss=False)
            st.image(img_bytes)
        return

    # --- Boss / Invader mode
    if "chariot_heatup_done" not in st.session_state:
        st.session_state["chariot_heatup_done"] = False

    if (
        st.session_state["behavior_deck"] is None
        or st.session_state["behavior_deck"].get("selected_file") != fpath
    ):
        state, cfg = _new_state_from_file(fpath)
        st.session_state["behavior_deck"] = state

    if st.button("🔄 Reset Deck and Health", key="reset_deck"):
        _reset_deck(st.session_state["behavior_deck"], cfg)

    state = st.session_state["behavior_deck"]
    if not state:
        st.info("Select a behavior file to begin.")
        return

    cfg = _load_cfg_for_state(state)
    if not cfg:
        st.error("Unable to load config.")
        return

    # --- Reference Cards section
    st.subheader("Reference Cards")

    cols = st.columns(max(2, len(state["display_cards"])))

    if cfg.name == "Executioner Chariot":
        if not st.session_state.get("chariot_heatup_done", False):
            edited_img = bi.render_data_card(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner Chariot.jpg",
                cfg.raw,
                is_boss=True,
                no_edits=True,
            )
        else:
            edited_img = bi.render_data_card(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                cfg.raw,
                is_boss=True,
            )
        with cols[0]:
            st.image(edited_img)
    elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
        # Dual boss special case: render each data card separately, side-by-side
        ornstein_img, smough_img = bi.render_dual_boss_data_cards(cfg.raw)
        dual_cols = st.columns(2)
        for img, col in zip([ornstein_img, smough_img], dual_cols):
            with col:
                st.image(img, width="stretch", output_format="PNG")
    else:
        for i, data_path in enumerate(state["display_cards"]):
            if i == 0:
                edited_img = bi.render_data_card(data_path, cfg.raw, is_boss=True)
            else:
                card_name = Path(data_path).stem.split(" - ")[-1]
                edited_img = bi.render_behavior_card(
                    data_path, cfg.raw[card_name], is_boss=True
                )
            with cols[i if i < len(cols) else -1]:
                st.image(edited_img)

    # --- Health block
    st.markdown("---")
    st.subheader("Health Tracker")
    cfg.entities = render_health_tracker(cfg)

    st.markdown("---")

    # --- Draw pile and current card columns
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Draw Pile**")
        st.caption(f"{len(state['draw_pile'])} cards remaining")
        if state["draw_pile"]:
            st.image(CARD_BACK)
        else:
            st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)

    with c2:
        st.markdown("**Current Card**")
        st.caption(
            f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played"
        )
        if state.get("current_card"):
            if cfg.name == "Ornstein & Smough":
                current_name = state["current_card"]
                edited_behavior = bi.render_dual_boss_behavior_card(
                    cfg.raw, current_name, boss_name=cfg.name
                )
            else:
                beh_key = state["current_card"]
                beh_json = cfg.behaviors.get(beh_key, {})
                current_path = _behavior_image_path(cfg, beh_key)
                edited_behavior = bi.render_behavior_card(
                    current_path, beh_json, is_boss=True
                )
            st.image(edited_behavior)

    # --- Action buttons
    st.markdown("---")
    btn_cols = st.columns(2)
    with btn_cols[0]:
        if st.button("Draw", width="stretch"):
            _draw_card(state)
            st.rerun()
    with btn_cols[1]:
        if st.button("Manual Heat-Up", width="stretch"):
            _manual_heatup(state)
            st.rerun()

    st.markdown("---")

    # --- Save slots (persist to settings file)
    _save_slot_ui(settings, state)
