import random, io
import streamlit as st
from copy import deepcopy
from pathlib import Path
from PIL import Image, ImageOps
from core.settings_manager import load_settings, save_settings
from core import behavior_decks as bd
from core import behavior_icons as bi
from core.behavior.generation import (
    render_data_card_cached,
    render_data_card_uncached,
    render_behavior_card_cached,
    render_behavior_card_uncached,
)


BEHAVIOR_CARDS_PATH = "assets/behavior cards/"
CARD_BACK = "assets/behavior cards/back.jpg"


def _render_data_card(*args, **kwargs):
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    func = render_data_card_uncached if cloud_low_memory else render_data_card_cached
    return func(*args, **kwargs)


def _render_behavior_card(*args, **kwargs):
    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))
    func = render_behavior_card_uncached if cloud_low_memory else render_behavior_card_cached
    return func(*args, **kwargs)


def _behavior_image_path(cfg, behavior_name: str) -> str:
    """Map a behavior name (or pair of names) to its corresponding image path(s)."""
    if isinstance(behavior_name, tuple):
        # Return list of paths for both movement & attack cards
        paths = []
        for name in behavior_name:
            clean_name = bd._strip_behavior_suffix(str(name))
            paths.append(f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg")
        return paths
    else:
        clean_name = bd._strip_behavior_suffix(str(behavior_name))
        return f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg"
    
def _dim_greyscale(img_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    gray = ImageOps.grayscale(img).convert("RGBA")
    # darken a bit for clarity
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 110))
    out = Image.alpha_composite(gray, overlay)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

def _ensure_state():
    """Guarantee required Streamlit session_state keys exist."""
    defaults = {
        "behavior_deck": None,
        "behavior_state": None,
        "hp_tracker": {},
        "last_edit": {},
        "deck_reset_id": 0,
        "chariot_heatup_done": False,
        "heatup_done": False,
        "pending_heatup_prompt": False,
        "old_dragonslayer_heatups": 0,
        "old_dragonslayer_pending": False,
        "old_dragonslayer_confirmed": False
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

def _clear_heatup_prompt():
    """Fully clear any pending heat-up UI flags."""
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.session_state["pending_heatup_type"] = None


def _four_kings_summon(cfg, state, rng):
    """Perform a Royal Summons (max 3)."""
    summons = state.get("four_kings_summons", 0)
    if summons >= 3:
        return

    summons += 1
    state["four_kings_summons"] = summons

    # --- ENABLE next king (persisted in state, mirrored to session)
    enabled_before = state.get("enabled_kings", 1)
    enabled_after = min(enabled_before + 1, 4)
    state["enabled_kings"] = enabled_after
    st.session_state["enabled_kings"] = enabled_after

    # --- combine current + discard back into deck
    draw = state["draw_pile"]
    discard = state["discard_pile"]
    if state.get("current_card"):
        discard.append(state["current_card"])
        state["current_card"] = None
    draw.extend(discard)
    discard.clear()

    # --- remove one random card from the deck
    removed = None
    if draw:
        removed = rng.choice(draw)
        draw.remove(removed)

    # --- pick tier based on the *summons count* (1→2, 2→3, 3→4)
    tier = 1 + summons
    tier_key = str(tier)

    # ensure we match even if JSON encodes numbers as strings
    heatups = [b for b, v in cfg.behaviors.items()
               if str(v.get("heatup", "")) == tier_key]
    rng.shuffle(heatups)
    added = heatups[:2]
    draw.extend(added)

    rng.shuffle(draw)
    
    # --- Persist enabled_kings into state for stable reloads
    state["enabled_kings"] = st.session_state.get("enabled_kings", 1)


def _new_state_from_file(fpath: str):
    cfg = bd.load_behavior(Path(fpath))
    rng = random.Random()

    if cfg.name == "The Four Kings":
        # Replace generic entity with correctly labeled first King
        first = bd._make_king_entity(cfg, 1)
        cfg.entities = [first]
    
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

    state["original_behaviors"] = deepcopy(cfg.behaviors)

    if "vordt_move_draw" in cfg.raw:
        state["vordt_move_draw"] = cfg.raw["vordt_move_draw"][:]
        state["vordt_move_discard"] = []
        state["vordt_attack_draw"] = cfg.raw["vordt_attack_draw"][:]
        state["vordt_attack_discard"] = []

    return state, cfg

def _load_cfg_for_state(state):
    if not state or not state.get("selected_file"):
        return None

    # Use cached BehaviorConfig if already stored
    if "cfg" in state and state["cfg"]:
        return state["cfg"]

    # Otherwise, load fresh from disk
    cfg = bd.load_behavior(Path(state["selected_file"]))

    # Apply NG+ modifiers if a level is selected
    ng_level = st.session_state.get("ng_plus_level", 0)
    if ng_level:
        bd.apply_ng_plus(cfg, ng_level)

    state["cfg"] = cfg
    return cfg

def render_health_tracker(cfg, state):
    tracker = st.session_state.setdefault("hp_tracker", {})
    reset_id = st.session_state.get("deck_reset_id", 0)

    for e in cfg.entities:
        ent_id = e.id                 # must be unique: "ornstein", "smough", "king_1"
        label = e.label               # "Ornstein", "Smough", "King 1"
        hp = e.hp
        hpmax = e.hp_max
        heat_thresh = (e.heatup_thresholds or [None])[0]
        slider_key = f"hp_{ent_id}_{reset_id}"   # e.g., hp_ornstein_0 / hp_king_1_0

        initial_val = int(tracker.get(ent_id, {}).get("hp", hp))

        # IMPORTANT: bind everything used inside as default args to avoid late binding
        def on_hp_change(
            *,
            _slider_key=slider_key,
            _ent_id=ent_id,
            _hpmax=hpmax,
            _heat_thresh=heat_thresh,
            _hp_default=hp,
            _boss_name=cfg.name
        ):
            val = st.session_state.get(_slider_key, _hp_default)
            val = max(0, min(int(val), int(_hpmax)))
            prev = tracker.get(_ent_id, {}).get("hp", _hp_default)
            tracker[_ent_id] = {"hp": val, "hp_max": _hpmax}

            for ent in cfg.entities:
                if ent.id == _ent_id:
                    ent.hp = val
                    break

            # --- standard heat-up threshold
            if _heat_thresh is not None and not st.session_state.get("heatup_done", False):
                if val <= _heat_thresh:
                    st.session_state["pending_heatup_prompt"] = True
                    if cfg.name == "Old Dragonslayer":
                        st.session_state["pending_heatup_target"] = "Old Dragonslayer"
                        st.session_state["pending_heatup_type"] = "old_dragonslayer"
                    elif cfg.name == "Artorias":
                        st.session_state["pending_heatup_target"] = "Artorias"
                        st.session_state["pending_heatup_type"] = "artorias"

            # --- Old Dragonslayer: 4+ in one change
            if _boss_name == "Old Dragonslayer" and (prev - val) >= 4:
                st.session_state["pending_heatup_prompt"] = True
                st.session_state["pending_heatup_target"] = "Old Dragonslayer"
                st.session_state["pending_heatup_type"] = "old_dragonslayer"

            # --- Crossbreed Priscilla: any damage cancels invisibility
            elif _boss_name == "Crossbreed Priscilla" and val < prev:
                st.session_state.setdefault("behavior_deck", {})["priscilla_invisible"] = False

        # --- Ornstein & Smough special handling
        if cfg.name == "Ornstein & Smough":
            ornstein = next((ent for ent in cfg.entities if "Ornstein" in ent.label), None)
            smough = next((ent for ent in cfg.entities if "Smough" in ent.label), None)
            if ornstein and smough:
                orn_hp = int(ornstein.hp)
                smo_hp = int(smough.hp)
                if orn_hp <= 0 and not st.session_state.get("ornstein_dead_pending", False) \
                        and not st.session_state.get("ornstein_dead", False):
                    st.session_state["ornstein_dead_pending"] = True
                    st.session_state["pending_heatup_target"] = "Ornstein & Smough"
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["smough_dead_pending"] = False
                    st.write("[DEBUG] Ornstein death detected; pending heatup prompt set.")
                elif smo_hp <= 0 and not st.session_state.get("smough_dead_pending", False) \
                        and not st.session_state.get("smough_dead", False):
                    st.session_state["smough_dead_pending"] = True
                    st.session_state["pending_heatup_target"] = "Ornstein & Smough"
                    st.session_state["pending_heatup_prompt"] = True
                    st.session_state["ornstein_dead_pending"] = False
                    st.write("[DEBUG] Smough death detected; pending heatup prompt set.")

        elif cfg.name == "The Last Giant":
            st.session_state["pending_heatup_target"] = "The Last Giant"
            st.session_state["pending_heatup_type"] = "last_giant"

        disabled_flag = False

        # CHARIOT: locked pre-heatup
        if cfg.name == "Executioner Chariot" and not st.session_state.get("chariot_heatup_done", False):
            disabled_flag = True

        # --- Ornstein & Smough: disable if dead
        elif cfg.name == "Ornstein & Smough":
            if "Ornstein" in label and st.session_state.get("ornstein_dead", False):
                disabled_flag = True
            elif "Smough" in label and st.session_state.get("smough_dead", False):
                disabled_flag = True

        # --- The Four Kings: enable sliders incrementally
        elif cfg.name == "The Four Kings":
            enabled_count = state.get("enabled_kings", 1)
            st.session_state["enabled_kings"] = enabled_count  # keep in sync for UI continuity
            try:
                king_num = int(label.split()[-1])
            except Exception:
                king_num = 1
            if king_num > enabled_count:
                disabled_flag = True

        st.slider(
            label,
            0,
            hpmax,
            value=initial_val,
            key=slider_key,
            on_change=on_hp_change,
            disabled=disabled_flag,
        )

    return cfg.entities

def _ornstein_smough_heatup_ui(state, cfg):
    rng = random.Random()

    # Decide who died and who survives, with heal amount
    if st.session_state.get("smough_dead_pending"):
        dead = "Smough"
        survivor_label = "Ornstein"
        heal_amt = 10
        st.session_state["smough_dead_pending"] = False
        st.session_state["smough_dead"] = True
    elif st.session_state.get("ornstein_dead_pending"):
        dead = "Ornstein"
        survivor_label = "Smough"
        heal_amt = 15
        st.session_state["ornstein_dead_pending"] = False
        st.session_state["ornstein_dead"] = True
    else:
        dead = None
        survivor_label = None
        heal_amt = 0

    state = st.session_state["behavior_deck"]

    # --- Heal survivor FIRST, from tracker (source of truth), then sync everywhere
    if survivor_label:
        # find survivor IDs in state/cfg
        surv_state = next((e for e in state["entities"] if survivor_label in e["label"]), None)
        surv_cfg   = next((e for e in cfg.entities        if survivor_label in e.label), None)

        if surv_state and surv_cfg:
            surv_id = surv_state["id"]
            tracker = st.session_state.setdefault("hp_tracker", {})
            # current HP from tracker if present, else from state entity
            cur_hp = int(tracker.get(surv_id, {}).get("hp", surv_state["hp"]))
            new_hp = min(cur_hp + heal_amt, int(surv_state["hp_max"]))

            # write back to tracker (so slider shows it), state, and cfg mirror
            tracker[surv_id] = {"hp": new_hp, "hp_max": surv_state["hp_max"]}
            surv_state["hp"] = new_hp
            surv_cfg.hp = new_hp

    # --- Now switch to the correct phase deck (shuffle once)
    if dead:
        bd._ornstein_smough_heatup(state, cfg, dead, rng)

    # close the prompt
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["pending_heatup_target"] = None
    st.rerun()

def _draw_card(state):
    cfg = _load_cfg_for_state(state)

    # --- Dancer of the Boreal Valley: if the *current* card is a heat-up,
    #     recycle EVERYTHING (current + discard + draw) and shuffle BEFORE any generic recycle.
    if cfg and cfg.name == "Dancer of the Boreal Valley":
        current = state.get("current_card")
        if current:
            beh = cfg.behaviors.get(current, {})
            if beh.get("heatup", False):
                all_cards = [current] + state.get("discard_pile", []) + state.get("draw_pile", [])
                rng = random.Random()
                rng.shuffle(all_cards)
                state["draw_pile"] = all_cards
                state["discard_pile"].clear()
                state["current_card"] = None
                state["dancer_reshuffled"] = True

    # --- Special case: Vordt of the Boreal Valley
    if "vordt_move_draw" in state and "vordt_attack_draw" in state:
        def draw_from(deck_key, discard_key):
            if not state[deck_key]:
                state[deck_key] = state[discard_key][:]
                random.shuffle(state[deck_key])
                state[discard_key].clear()
            card = state[deck_key].pop(0)
            state[discard_key].append(card)
            return card

        move_card = draw_from("vordt_move_draw", "vordt_move_discard")
        atk_card = draw_from("vordt_attack_draw", "vordt_attack_discard")
        state["current_card"] = (move_card, atk_card)
        return

    # Ensure deck availability
    if not state["draw_pile"]:
        if cfg and cfg.name == "The Four Kings":
            summons = state.get("four_kings_summons", 0)
            if summons < 3:
                if not st.session_state.get("four_kings_summon_in_progress", False):
                    st.session_state["four_kings_summon_in_progress"] = True
                    _four_kings_summon(cfg, state, random.Random())
                    st.session_state["four_kings_summon_in_progress"] = False
            else:
                # After third summons, recycle normally
                bd.recycle_deck(state)
        else:
            bd.recycle_deck(state)

    # If still empty, bail cleanly (prevents "played count" from increasing)
    if not state["draw_pile"]:
        return

    # Draw safely: only move current to discard when we have a next card
    next_card = state["draw_pile"].pop(0)
    if state.get("current_card"):
        state["discard_pile"].append(state["current_card"])
    state["current_card"] = next_card

def _reset_deck(state, cfg):
    """Reset the current deck and health states for the selected boss."""
    rng = random.Random()

    if "cfg" in state:
        del state["cfg"]  # Force reload of pristine behavior data next run
    
    # Restore original behaviors if saved
    if "original_behaviors" in state:
        cfg.behaviors = deepcopy(state["original_behaviors"])
    
    state["draw_pile"] = bd.build_draw_pile(cfg, rng)
    state["discard_pile"] = []
    state["current_card"] = None
    state["heatup_done"] = False

    # --- Special case: Vordt of the Boreal Valley
    if cfg.name == "Vordt of the Boreal Valley":
        # Let the core deck rule rebuild both decks
        behaviors = cfg.behaviors
        move_cards = [
            b for b in behaviors
            if behaviors[b].get("type") == "move" and not behaviors[b].get("heatup", False)
        ]
        atk_cards = [
            b for b in behaviors
            if behaviors[b].get("type") == "attack" and not behaviors[b].get("heatup", False)
        ]

        rng.shuffle(move_cards)
        rng.shuffle(atk_cards)

        # Reinitialize state decks for UI
        state["vordt_move_draw"] = move_cards[:4]
        state["vordt_move_discard"] = []
        state["vordt_attack_draw"] = atk_cards[:3]
        state["vordt_attack_discard"] = []

        # Sync cfg.raw so that later save/load is consistent
        cfg.raw["vordt_move_draw"] = state["vordt_move_draw"][:]
        cfg.raw["vordt_move_discard"] = []
        cfg.raw["vordt_attack_draw"] = state["vordt_attack_draw"][:]
        cfg.raw["vordt_attack_discard"] = []
    elif cfg.name == "Old Dragonslayer":
        state["old_dragonslayer_heatups"] = 0
        state["old_dragonslayer_pending"] = False
        state["old_dragonslayer_confirmed"] = False
    elif cfg.name == "Crossbreed Priscilla":
        state["priscilla_invisible"] = True
    elif cfg.name == "Great Grey Wolf Sif":
        state["sif_limping"] = False
        st.session_state.pop("sif_limping_triggered", None)
    elif cfg.name == "The Four Kings":
        state["four_kings_summons"] = 0
        st.session_state["enabled_kings"] = 1
        # restore all kings to full hp
        for ent in cfg.entities:
            ent.hp = ent.hp_max
            ent.crossed = []
    elif cfg.name == "Ornstein & Smough":
        for k in [
            "ornstein_dead", "smough_dead",
            "ornstein_dead_pending", "smough_dead_pending",
            "disabled_ornstein", "disabled_smough",
            "ornstein_smough_phase", "os_phase_shuffled_once",
            "pending_heatup_prompt", "pending_heatup_target",
        ]:
            st.session_state.pop(k, None)
        state["ornstein_smough_phase"] = None
    else:
        # Clean up any leftover special keys
        for key in [
            "vordt_move_draw",
            "vordt_move_discard",
            "vordt_attack_draw",
            "vordt_attack_discard",
        ]:
            state.pop(key, None)
            cfg.raw.pop(key, None)
        state["old_dragonslayer_heatups"] = 0
        state["old_dragonslayer_pending"] = False
        state["old_dragonslayer_confirmed"] = False
        state.pop("priscilla_invisible", None)

    # --- Reset entities (UI + cfg)
    for e in state["entities"]:
        if isinstance(e, dict):
            e["hp"] = e.get("hp_max", e.get("hp", 0))
            e["crossed"] = []
        else:
            e.hp = e.hp_max
            e.crossed = []

    for ent in cfg.entities:
        ent.hp = ent.hp_max
        ent.crossed = []
        st.session_state.pop(f"hp_{ent.id}", None)

    # --- Clear UI caches / flags
    st.session_state.pop("hp_tracker", None)
    st.session_state.pop("last_edit", None)
    st.session_state["deck_reset_id"] = st.session_state.get("deck_reset_id", 0) + 1
    st.session_state["chariot_heatup_done"] = False
    st.session_state["pending_heatup_prompt"] = False
    st.session_state["heatup_done"] = False
    st.session_state["behavior_cfg"] = cfg


def _manual_heatup(state):
    cfg = _load_cfg_for_state(state)
    if not cfg:
        return
    rng = random.Random()

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
    elif cfg.name == "Ornstein & Smough":
        _ornstein_smough_heatup_ui(state, cfg)
    else:
        bd.apply_heatup(state, cfg, rng, reason="manual")
        st.session_state["pending_heatup_prompt"] = False
        st.session_state["pending_heatup_target"] = None
        st.session_state["pending_heatup_type"] = None
        st.session_state["heatup_done"] = True


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

    if "last_selected_boss" not in st.session_state or st.session_state["last_selected_boss"] != choice:
        # Reset per-boss heat-up and prompt flags
        for key in [
            "heatup_done",
            "pending_heatup_prompt",
            "pending_heatup_target",
            "pending_heatup_type",
        ]:
            st.session_state[key] = False if key == "heatup_done" else None

        # Also clear boss-specific pending flags if any
        for key in [
            "smough_dead_pending", "ornstein_dead_pending",
            "old_dragonslayer_pending",
        ]:
            if key in st.session_state:
                st.session_state[key] = False

        st.session_state["last_selected_boss"] = choice

    if not (choice and files):
        st.info("Select a behavior file to begin.")
        return

    fpath = str(files[labels.index(choice)])
    cfg = bd.load_behavior(Path(fpath))

    # Apply NG+ modifiers for previews
    ng_level = st.session_state.get("ng_plus_level", 0)
    if ng_level:
        bd.apply_ng_plus(cfg, ng_level)

    # --- Regular enemy mode
    if "behavior" in cfg.raw:
        cols = st.columns(2)
        with cols[0]:
            data_card = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            img_bytes = _render_data_card(data_card, cfg.raw, is_boss=False)
            st.image(img_bytes)
        return

    # --- Boss / Invader mode
    if cfg.name == "The Four Kings":
        # Only King 1 starts enabled; others show disabled
        st.session_state["enabled_kings"] = 1

    if "chariot_heatup_done" not in st.session_state:
        st.session_state["chariot_heatup_done"] = False

    if (
        st.session_state["behavior_deck"] is None
        or st.session_state["behavior_deck"].get("selected_file") != fpath
    ):
        state, cfg = _new_state_from_file(fpath)
        st.session_state["behavior_deck"] = state

        # --- Crossbreed Priscilla: ensure invisibility starts active on first load
        if cfg.name == "Crossbreed Priscilla":
            st.session_state["behavior_deck"]["priscilla_invisible"] = True

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

    print(cfg.raw)

    # Special rules for Chariot data card display based on phase.
    if cfg.name == "Executioner Chariot":
        if not st.session_state.get("chariot_heatup_done", False):
            edited_img = _render_data_card(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner Chariot.jpg",
                cfg.raw,
                is_boss=True,
                no_edits=True,
            )
        else:
            edited_img = _render_data_card(
                BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                cfg.raw,
                is_boss=True,
            )
        with cols[0]:
            st.image(edited_img)
    elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
        ornstein_img, smough_img = bi.render_dual_boss_data_cards(cfg.raw)
        dual_cols = st.columns(2)
        with dual_cols[0]:
            if st.session_state.get("ornstein_dead"):
                st.image(_dim_greyscale(ornstein_img), width="stretch")
            else:
                st.image(ornstein_img, width="stretch")
        with dual_cols[1]:
            if st.session_state.get("smough_dead"):
                st.image(_dim_greyscale(smough_img), width="stretch")
            else:
                st.image(smough_img, width="stretch")
    else:
        for i, data_path in enumerate(state["display_cards"]):
            if i == 0:
                edited_img = _render_data_card(data_path, cfg.raw, is_boss=True)
            else:
                card_name = Path(data_path).stem.split(" - ")[-1]
                edited_img = _render_behavior_card(
                    data_path, cfg.raw[card_name], is_boss=True
                )
            with cols[i if i < len(cols) else -1]:
                st.image(edited_img)
                
    if cfg.name == "Crossbreed Priscilla":
        invis = st.session_state["behavior_deck"].get("priscilla_invisible", False)
        st.caption(f"🫥 Invisibility: {'ON' if invis else 'OFF'}")

    # --- Health block
    st.markdown("---")
    st.subheader("Health Tracker")
    cfg.entities = render_health_tracker(cfg, state)

    # --- Auto Heat-Up Prompt ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and not st.session_state.get("heatup_done", False)
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        st.warning(
            f"⚠️ The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} has entered Heat-Up range!"
        )

        confirm_cols = st.columns([1, 1])
        with confirm_cols[0]:
            if st.button("🔥 Confirm Heat-Up", key="confirm_heatup"):
                rng = random.Random()
                bd.apply_heatup(state, cfg, rng, reason="auto")
                _clear_heatup_prompt()
                st.session_state["pending_heatup_prompt"] = False
                st.session_state["pending_heatup_target"] = None
                st.session_state["pending_heatup_type"] = None
                st.session_state["heatup_done"] = True
                st.rerun()
        with confirm_cols[1]:
            if st.button("Cancel", key="cancel_heatup"):
                _clear_heatup_prompt()
                st.session_state["heatup_done"] = False
                st.rerun()

    elif st.session_state.get("pending_heatup_prompt", False):
        boss = st.session_state.get("pending_heatup_target")
        if boss == "Old Dragonslayer":
            st.warning("Was 4+ damage was done in a single attack?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Heat-Up"):
                    state["old_dragonslayer_confirmed"] = True
                    _clear_heatup_prompt()
                    bd.apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel"):
                    _clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()
        
        
        # --- Ornstein & Smough death confirmation ---
        elif boss == "Ornstein & Smough":
            st.warning("⚔️ One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Phase Change"):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()

    st.markdown("---")

    # --- Draw pile and current card columns
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Draw Pile**")
        if cfg.name == "Vordt of the Boreal Valley":
            st.caption(f"{len(state['vordt_move_draw'])} movement cards remaining")
            if state["vordt_move_draw"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)
                
            st.caption(f"{len(state['vordt_attack_draw'])} attack cards remaining")
            if state["vordt_attack_draw"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)
        else:
            st.caption(f"{len(state['draw_pile'])} cards remaining")
            if state["draw_pile"]:
                st.image(CARD_BACK)
            else:
                st.markdown("<div style='min-height:484px;'></div>", unsafe_allow_html=True)

    with c2:
        st.markdown("**Current Card**")

        # --- Vordt of the Boreal Valley special layout
        if cfg.name == "Vordt of the Boreal Valley" and isinstance(state["current_card"], tuple):
            move_card, atk_card = state["current_card"]
            move_path = _behavior_image_path(cfg, move_card)
            atk_path = _behavior_image_path(cfg, atk_card)

            # --- Movement Deck Row ---
            if move_card:
                st.caption(f"{len(state['vordt_move_discard'])} movement cards played")
                st.image(
                    _render_behavior_card(
                        move_path,
                        cfg.behaviors.get(move_card, {}),
                        is_boss=True,
                    )
                )

            # --- Attack Deck Row ---
            if atk_card:
                st.caption(f"{len(state['vordt_attack_discard'])} attack cards played")
                st.image(
                    _render_behavior_card(
                        atk_path,
                        cfg.behaviors.get(atk_card, {}),
                        is_boss=True,
                    )
                )

        # --- Ornstein & Smough dual boss case
        elif cfg.name == "Ornstein & Smough":
            st.caption(
                f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played"
            )
            current_name = state["current_card"]

            if current_name:
                # --- During phase-2 (after one death), cards no longer contain '&'
                if "&" in (current_name or ""):
                    edited_behavior = bi.render_dual_boss_behavior_card(
                        cfg.raw, current_name, boss_name=cfg.name
                    )
                else:
                    edited_behavior = _render_behavior_card(
                        _behavior_image_path(cfg, current_name),
                        cfg.behaviors.get(current_name, {}),
                        is_boss=True,
                    )

                st.image(edited_behavior)

        # --- Normal single-card bosses
        elif state.get("current_card"):
            st.caption(
                f"{len(state['discard_pile']) + (1 if state['current_card'] else 0)} cards played"
            )
            beh_key = state["current_card"]
            beh_json = cfg.behaviors.get(beh_key, {})
            print(beh_json)
            current_path = _behavior_image_path(cfg, beh_key)
            edited_behavior = _render_behavior_card(current_path, beh_json, is_boss=True)
            st.image(edited_behavior)

    # --- Action buttons
    btn_cols = st.columns(2)
    with btn_cols[0]:
        draw_label = "Draw Movement + Attack" if cfg.name == "Vordt of the Boreal Valley" else "Draw"
        if st.button(draw_label, width="stretch", key="behavior_draw"):
            _clear_heatup_prompt()
            _draw_card(state)
            st.rerun()
    with btn_cols[1]:
        if st.button("Manual Heat-Up", width="stretch"):
            _clear_heatup_prompt()
            _manual_heatup(state)
            st.rerun()

    st.markdown("---")

    # --- Save slots (persist to settings file)
    _save_slot_ui(settings, state)
