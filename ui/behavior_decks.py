# ui/decks.py
import os, random
import streamlit as st
from pathlib import Path
from core.settings_manager import load_settings, save_settings
from core import behavior_decks as bd
from core import behavior_icons as bi


BEHAVIOR_CARDS_PATH = "assets/behavior cards/"
CARD_BACK = "assets/behavior cards/back.jpg"


def _ensure_state():
    if "behavior_deck" not in st.session_state:
        st.session_state["behavior_deck"] = None

def _new_state_from_file(fpath: str, seed: int = 0):
    cfg = bd.load_behavior(Path(fpath))
    state = bd.state_from_cfg(cfg, seed=seed)
    state["selected_file"] = fpath
    return state, cfg

def _load_cfg_for_state(state):
    if not state or not state.get("selected_file"):
        return None
    return bd.load_behavior(Path(state["selected_file"]))

def _hp_row(entity, idx, state):
    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        st.markdown(f"**{entity['label']}**")
        bar = max(0, min(entity["hp"], entity["hp_max"]))
        st.progress(bar / max(1, entity["hp_max"]))
        st.caption(f"{entity['hp']} / {entity['hp_max']} HP")

    with cols[1]:
        delta = st.number_input(f"Δ HP ({entity['label']})", value=0, step=1, format="%d", key=f"hp_delta_{idx}")
    with cols[2]:
        apply = st.button("Apply", key=f"apply_{idx}")
    with cols[3]:
        reset = st.button("Full Heal", key=f"heal_{idx}")

    changed = False
    triggered = []
    if apply:
        prev = entity["hp"]
        new = max(0, min(entity["hp_max"], prev + int(delta)))
        entity["hp"] = new
        cfg_obj = _load_cfg_for_state(state)
        if cfg_obj:
            rng = random.Random(state.get("seed", 0))
            # find corresponding entity in cfg
            # we only need thresholds; entity dict already has them
            triggered = bd.check_and_trigger_heatup(prev, new, _to_entity_dataclass(entity), state, cfg_obj, rng)
        changed = True
        st.rerun()
    if reset:
        entity["hp"] = entity["hp_max"]
        changed = True
        st.rerun()
    return changed, triggered

def _to_entity_dataclass(edict):
    return bd.Entity(
        id=edict["id"], label=edict["label"], hp_max=edict["hp_max"], hp=edict["hp"],
        heatup_thresholds=edict.get("heatup_thresholds", []), crossed=edict.get("crossed", [])
    )

def _draw_card(state):
    if not state["draw_pile"]:
        bd.recycle_deck(state)
    if state["draw_pile"]:
        if state.get("current_card"):
            state["discard_pile"].append(state["current_card"])
        state["current_card"] = state["draw_pile"].pop(0)

def _reset_deck(state, cfg, seed=None):
    if seed is not None:
        state["seed"] = int(seed)
    rng = random.Random(state.get("seed", 0))
    state["draw_pile"] = bd.build_draw_pile(cfg, rng)
    state["discard_pile"] = []
    state["current_card"] = None
    # reset heat-up flags on entities
    for e in state["entities"]:
        e["hp"] = e["hp_max"]
        e["crossed"] = []

def _manual_heatup(state):
    cfg = _load_cfg_for_state(state)
    if not cfg: return
    rng = random.Random(state.get("seed", 0))
    bd.apply_heatup(state, cfg, rng, reason="manual")

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

    # --- selector row (left: file picker; right: seed + build/reset)
    colL, colR = st.columns([2, 1])
    with colL:
        files = bd.list_behavior_files()
        labels = [f.name[:-5] for f in files]
        choice = st.selectbox("Choose enemy / invader / boss", options=labels, index=0 if labels else None, key="behavior_choice")
    with colR:
        seed = st.number_input("Seed", value=0, step=1)

    if choice and files:
        fpath = str(files[labels.index(choice)])
        cfg = bd.load_behavior(Path(fpath))
        
    cols = st.columns(2)

    if "behavior" in cfg.raw:
        with cols[0]:
            # regular enemy mode
            data_card = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            img_bytes = bi.render_data_card(data_card, cfg.raw, is_boss=False)
            st.image(img_bytes)

        return
    
    # Bosses and invaders
    build = st.button("Build / Reset", use_container_width=True)
    if build or st.session_state["behavior_deck"] is None or st.session_state["behavior_deck"].get("selected_file") != fpath:
        state, cfg = _new_state_from_file(fpath, seed=int(seed))
        st.session_state["behavior_deck"] = state

    state = st.session_state["behavior_deck"]
    if not state:
        st.info("Select a behavior file to begin.")
        return

    cfg = _load_cfg_for_state(state)
    if not cfg:
        st.error("Unable to load config.")
        return

    # --- Reference card(s): show data card for bosses/invaders
    st.markdown("**Reference Cards**")

    # data card is always index 0 if we had it
    if "Ornstein" in cfg.raw and "Smough" in cfg.raw:
        # Dual boss special case
        edited_data = bi.render_dual_boss_data_cards(cfg.raw)
    else:
        data_path = state["display_cards"][0]
        edited_data = bi.render_data_card(data_path, cfg.raw, is_boss=True)
    with cols[0]:
        st.image(edited_data)

    # --- Health block (multi-entity friendly)
    for idx, e in enumerate(state["entities"]):
        _hp_row(e, idx, state)

    st.markdown("---")

    # --- Row: Deck | Current | Discard, with actions below
    c1, c2 = st.columns(2)
    with c1: st.markdown("**Draw Pile**")
    st.caption(f"{len(state['draw_pile'])} cards")
    with c2: st.markdown("**Current Card**")
    st.caption(f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played")

    # --- Current card (behavior) ---
    with c2:
        if state.get("current_card"):
            if cfg.name == "Ornstein & Smough":
                current_path = state["current_card"]
                current_name = Path(current_path).stem
                edited_behavior = bi.render_dual_boss_behavior_card(cfg.raw, current_name)
            else:
                # figure out which behavior JSON we should use
                # the filename is like "Artorias - Heavy Thrust.jpg"
                current_path = state["current_card"]
                current_name = Path(current_path).stem   # "Artorias - Heavy Thrust"
                # behavior key is everything after "Artorias - "
                beh_key = current_name.replace(f"{cfg.name} - ", "")
                beh_json = cfg.raw.get(beh_key, {})
                # render as boss behavior card
                edited_behavior = bi.render_behavior_card(current_path, beh_json, is_boss=True)
            st.image(edited_behavior)

    with c1:
        if state["draw_pile"]:
            st.image(CARD_BACK)
        else:
            # Pad the space so the buttons stay in the same place while the deck is empty
            st.markdown("<div style='min-height:484px;'>", unsafe_allow_html=True)
        draw = st.button("Draw", use_container_width=True)
        if draw:
            _draw_card(state)
            st.rerun()

        manual_heat = st.button("Manual Heat-Up", use_container_width=True)
        if manual_heat:
            _manual_heatup(state)
            st.rerun()

        reset_btn = st.button("Full Reset (same seed)", use_container_width=True)
        if reset_btn:
            _reset_deck(state, cfg)
            st.rerun()

    st.markdown("---")

    # --- Save slots (persist to settings file)
    _save_slot_ui(settings, state)
