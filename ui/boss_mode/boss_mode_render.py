# ui/boss_mode_tab.py
import random
import pyautogui
import streamlit as st
import io

from PIL import Image
from ui.behavior_decks_tab.assets import (
    BEHAVIOR_CARDS_PATH,
    CARD_BACK,
    CATEGORY_EMOJI,
    _behavior_image_path
)
from ui.behavior_decks_tab.logic import (
    _ensure_state,
    _new_state_from_file,
    _load_cfg_for_state,
    _reset_deck,
    _draw_card,
    _manual_heatup,
    apply_heatup,
    _clear_heatup_prompt,
    _ornstein_smough_heatup_ui,
)
from ui.behavior_decks_tab.generation import (
    build_behavior_catalog,
    render_data_card_cached,
    render_dual_boss_data_cards,
    render_behavior_card_cached,
    render_dual_boss_behavior_card,
)
from ui.behavior_decks_tab.render import render_health_tracker


BOSS_MODE_CATEGORIES = ["Mini Bosses", "Main Bosses", "Mega Bosses"]
CARD_DISPLAY_WIDTH = int(380 * (pyautogui.size().height / 1400))
NODE_COORDS = [
    (0, 0),
    (0, 2),
    (0, 4),
    (0, 6),
    (1, 1),
    (1, 3),
    (1, 5),
    (2, 0),
    (2, 2),
    (2, 4),
    (2, 6),
    (3, 1),
    (3, 3),
    (3, 5),
    (4, 0),
    (4, 2),
    (4, 4),
    (4, 6),
    (5, 1),
    (5, 3),
    (5, 5),
    (6, 0),
    (6, 2),
    (6, 4),
    (6, 6),
]
GUARDIAN_DRAGON_NAME = "Guardian Dragon"
GUARDIAN_FIERY_BREATH_NAME = "Fiery Breath"
GUARDIAN_CAGE_PREFIX = "Cage Grasp Inferno"
GUARDIAN_FIERY_DECK_SIZE = 4
GUARDIAN_STANDARD_PATTERNS = [
    {
        "dest": (0, 0),
        "aoe": [
            (2, 0),
            (1, 1),
            (0, 2),
            (1, 3),
            (2, 2),
            (3, 1),
            (3, 3),
        ],
    },
    {
        "dest": (6, 0),
        "aoe": [
            (4, 0),
            (3, 1),
            (5, 1),
            (4, 2),
            (6, 2),
            (3, 3),
            (5, 3),
        ],
    },
    {
        "dest": (6, 6),
        "aoe": [
            (4, 6),
            (3, 5),
            (5, 5),
            (4, 4),
            (6, 4),
            (3, 3),
            (5, 3),
        ],
    },
    {
        "dest": (0, 6),
        "aoe": [
            (2, 6),
            (1, 5),
            (3, 5),
            (0, 4),
            (2, 4),
            (1, 3),
            (3, 3),
        ],
    },
]


def _guardian_node_distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _guardian_fiery_generate_pattern(base_pattern, rng=None):
    """
    Return a pattern similar to base_pattern, but with some AoE nodes
    jittered to nearby nodes so each deck build feels a bit different.

    base_pattern: {"dest": (x, y), "aoe": [(x, y), ...]}
    """
    if rng is None:
        rng = random.Random()

    dest = base_pattern["dest"]
    base_aoe = list(base_pattern["aoe"])
    aoe = set(base_aoe)

    for node in base_aoe:
        # With some probability, try to move this node to a nearby one.
        if rng.random() < 0.4:
            candidates = [
                cand
                for cand in NODE_COORDS
                if cand != dest
                and cand != node
                and _guardian_node_distance(cand, dest) <= 4
                and _guardian_node_distance(cand, node) <= 3
            ]
            if candidates:
                new_node = rng.choice(candidates)
                aoe.discard(node)
                aoe.add(new_node)

    # Ensure we keep the same number of AoE nodes (7)
    target_len = len(base_aoe)
    # Add extras if we lost any due to collisions
    candidates = [
        cand
        for cand in NODE_COORDS
        if cand != dest and cand not in aoe and _guardian_node_distance(cand, dest) <= 4
    ]
    rng.shuffle(candidates)
    while len(aoe) < target_len and candidates:
        aoe.add(candidates.pop())

    # If we somehow ended up with too many, trim back down
    if len(aoe) > target_len:
        aoe = set(rng.sample(list(aoe), target_len))

    return {"dest": dest, "aoe": sorted(aoe)}


def _guardian_fiery_init_deck(state, mode):
    """
    (Re)build the Fiery Breath pattern deck according to current rules.

    mode == "generated" -> generate patterns based on the four base ones
    mode == "deck"      -> use the four base patterns as-is
    """
    rng = random.Random()
    patterns = []
    for base in GUARDIAN_STANDARD_PATTERNS:
        if mode == "generated":
            patterns.append(_guardian_fiery_generate_pattern(base, rng))
        else:
            # Copy so we don't mutate the constants
            patterns.append(
                {"dest": base["dest"], "aoe": list(base["aoe"])}
            )

    rng.shuffle(patterns)
    state["guardian_fiery_deck"] = patterns
    state["guardian_fiery_discard"] = []
    state["guardian_fiery_deck_mode"] = mode


def _guardian_fiery_draw_pattern(state, mode):
    """
    Get the next Fiery Breath pattern, honouring the chosen mode:

    mode == "generated"  -> fresh-ish patterns per 4-card cycle
    mode == "deck"       -> the four static standard patterns
    """
    rng = random.Random()
    deck_mode = state.get("guardian_fiery_deck_mode")
    deck = state.get("guardian_fiery_deck") or []
    discard = state.get("guardian_fiery_discard") or []

    # Mode changed or deck empty -> rebuild
    if not deck or deck_mode != mode:
        _guardian_fiery_init_deck(state, mode)
        deck = state.get("guardian_fiery_deck") or []
        discard = state.get("guardian_fiery_discard") or []

    if not deck:
        # Safety fallback: generate from the first base pattern
        base = GUARDIAN_STANDARD_PATTERNS[0]
        return _guardian_fiery_generate_pattern(base, rng)

    pattern = deck.pop(0)
    discard.append(pattern)
    state["guardian_fiery_deck"] = deck
    state["guardian_fiery_discard"] = discard
    state["guardian_fiery_deck_mode"] = mode

    return pattern


def _guardian_node_to_xy(coord, icon_w, icon_h):
    col, row = coord

    # Centre of the node, from your measured values / derived step
    x = round(-41 + 107.5 * col)
    y = round(55 + 110.5 * row)

    # Convert centre to top-left for the icon
    # x = int(cx - icon_w / 2)
    # y = int(cy - icon_h / 2)
    return x, y


def _guardian_render_fiery_breath(cfg, pattern):
    """
    Render the Fiery Breath card with destination + AoE node icons overlaid.

    pattern is {"dest": (x, y), "aoe": [(x, y), ...]} using GUARDIAN_NODE_COORDS.
    """
    base = render_behavior_card_cached(
        _behavior_image_path(cfg, GUARDIAN_FIERY_BREATH_NAME),
        cfg.behaviors.get(GUARDIAN_FIERY_BREATH_NAME, {}),
        is_boss=True,
    )

    # Convert cached output to a PIL Image we can edit.
    if isinstance(base, Image.Image):
        base_img = base.convert("RGBA")
    elif isinstance(base, (bytes, bytearray)):
        base_img = Image.open(io.BytesIO(base)).convert("RGBA")
    elif isinstance(base, str):
        base_img = Image.open(base).convert("RGBA")
    else:
        # Last-ditch fallback: try to treat it as a file-like object
        base_img = Image.open(base).convert("RGBA")

    # Figure out where the assets directory is (parent of behavior cards)
    try:
        assets_dir = BEHAVIOR_CARDS_PATH.parent
    except Exception:
        from pathlib import Path
        assets_dir = Path(BEHAVIOR_CARDS_PATH).parent

    # Load icons
    aoe_icon_path = assets_dir / "behavior icons" / "aoe_node.png"
    dest_icon_path = assets_dir / "behavior icons" / "destination_node.png"

    aoe_icon = Image.open(aoe_icon_path).convert("RGBA")
    dest_icon = Image.open(dest_icon_path).convert("RGBA")

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    aoe_icon = aoe_icon.resize((250, 250), resample)
    dest_icon = dest_icon.resize((122, 122), resample)

    # Overlay destination node first
    dest = pattern.get("dest")
    if dest:
        x, y = _guardian_node_to_xy(dest, dest_icon.width, dest_icon.height)
        print((dest, x, y))
        base_img.alpha_composite(dest_icon, dest=(x, y))

    # Overlay AoE nodes
    for coord in pattern.get("aoe", []):
        x, y = _guardian_node_to_xy(coord, aoe_icon.width, aoe_icon.height)
        print((coord, x, y))
        base_img.alpha_composite(aoe_icon, dest=(x, y))

    return base_img


def _get_boss_mode_state_key(entry) -> str:
    return f"boss_mode::{entry.category}::{entry.name}"


def _ensure_boss_state(entry):
    key = _get_boss_mode_state_key(entry)
    state = st.session_state.get(key)
    if not state:
        state, cfg = _new_state_from_file(entry.path)
        st.session_state[key] = state
        # also keep "current" pointers for functions that expect behavior_deck
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    else:
        cfg = _load_cfg_for_state(state)
        st.session_state["behavior_deck"] = state
        st.session_state["behavior_cfg"] = cfg
    return state, cfg


def render():
    _ensure_state()

    # --- Build or reuse catalog
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]

    # Only categories we care about
    available_cats = [
        c for c in BOSS_MODE_CATEGORIES if catalog.get(c)
    ] or BOSS_MODE_CATEGORIES

    # --- Enemy selector row
    col_sel, col_info = st.columns([2, 1])

    with col_sel:
        default_cat = st.session_state.get("boss_mode_category", available_cats[0])
        if default_cat not in available_cats:
            default_cat = available_cats[0]

        with st.expander("Boss Selector", expanded=True):
            category = st.radio(
                "Type",
                available_cats,
                index=available_cats.index(default_cat),
                key="boss_mode_category",
                horizontal=True,
                format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
            )

            entries = catalog.get(category, [])
            if not entries:
                st.info("No bosses found in this category.")
                return

            names = [e.name for e in entries]
            last_choice = st.session_state.get("boss_mode_choice_name")
            idx = names.index(last_choice) if last_choice in names else 0

            entry = st.selectbox(
                "Who are you fighting?",
                entries,
                index=idx,
                key="boss_mode_choice",
                format_func=lambda e: e.name,
            )
            st.session_state["boss_mode_choice_name"] = entry.name

    if not entry:
        st.info("Select a boss to begin.")
        return

    # Ensure we have a state + cfg for this enemy
    state, cfg = _ensure_boss_state(entry)

    with col_info:
        if cfg.text:
            with st.expander(f"**{cfg.name}**"):
                st.caption(cfg.text)

        # Guardian Dragon: option to control Fiery Breath node patterns
        if cfg.name == GUARDIAN_DRAGON_NAME:
            st.checkbox(
                "Generate new Fiery Breath pattern each time",
                key="guardian_fiery_generate",
                help=(
                    "If checked, Fiery Breath's node pattern is generated anew "
                    "for every use. If unchecked, it uses a 4-card pattern deck "
                    "that cycles without replacement."
                ),
            )

        if st.button("🔄 Reset fight"):
            _reset_deck(state, cfg)
            if cfg.name == GUARDIAN_DRAGON_NAME:
                # Clear Fiery Breath state when resetting the fight
                state.pop("guardian_fiery_deck", None)
                state.pop("guardian_fiery_discard", None)
                state.pop("guardian_fiery_current_pattern", None)
                state.pop("guardian_fiery_current_mode", None)
            st.rerun()
            
    # Draw / Heat-up buttons
    c_hp_btns = st.columns([1, 1])
    with c_hp_btns[0]:
        cfg.entities = render_health_tracker(cfg, state)
    with c_hp_btns[1]:
        if st.button("Draw next card"):
            _draw_card(state)
        if st.button("Manual Heat-Up"):
            _manual_heatup(state)

    # --- Heat-Up confirmation prompt (Boss Mode) ---
    if (
        st.session_state.get("pending_heatup_prompt", False)
        and (cfg.name == "Vordt of the Boreal Valley" or not state.get("heatup_done", False))
        and cfg.name not in {"Old Dragonslayer", "Ornstein & Smough"}
    ):
        # Generic bosses (and Vordt), first-time heat-up
        st.warning(
            f"⚠️ The {'invader' if cfg.raw.get('is_invader', False) else 'boss'} "
            f"has entered Heat-Up range!"
        )

        confirm_cols = st.columns(2)
        with confirm_cols[0]:
            if st.button("🔥 Confirm Heat-Up", key="boss_mode_confirm_heatup"):
                rng = random.Random()
                apply_heatup(state, cfg, rng, reason="auto")

                _clear_heatup_prompt()
                st.session_state["pending_heatup_prompt"] = False
                st.session_state["pending_heatup_target"] = None
                st.session_state["pending_heatup_type"] = None

                if cfg.name not in {
                    "Old Dragonslayer",
                    "Ornstein & Smough",
                    "Vordt of the Boreal Valley",
                }:
                    st.session_state["heatup_done"] = True
                st.rerun()

        with confirm_cols[1]:
            if st.button("Cancel", key="boss_mode_cancel_heatup"):
                _clear_heatup_prompt()
                st.session_state["heatup_done"] = False
                st.rerun()

    elif st.session_state.get("pending_heatup_prompt", False):
        # Boss-specific special cases
        boss = st.session_state.get("pending_heatup_target")

        # --- Old Dragonslayer: require 4+ damage confirmation ---
        if boss == "Old Dragonslayer":
            st.warning("Was 4+ damage done in a single attack?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Heat-Up", key="boss_mode_ods_confirm"):
                    state["old_dragonslayer_confirmed"] = True
                    _clear_heatup_prompt()
                    apply_heatup(state, cfg, random.Random(), reason="manual")
                    st.rerun()
            with c2:
                if st.button("Cancel", key="boss_mode_ods_cancel"):
                    _clear_heatup_prompt()
                    state["old_dragonslayer_pending"] = False
                    state["old_dragonslayer_confirmed"] = False
                    st.rerun()

        # --- Ornstein & Smough: death/phase change confirmation ---
        elif boss == "Ornstein & Smough":
            st.warning("⚔️ One of the duo has fallen! Apply the new phase?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔥 Confirm Phase Change", key="boss_mode_ons_confirm"):
                    _ornstein_smough_heatup_ui(state, cfg)
            with c2:
                if st.button("Cancel", key="boss_mode_ons_cancel"):
                    st.session_state["pending_heatup_prompt"] = False
                    st.session_state["smough_dead_pending"] = False
                    st.session_state["ornstein_dead_pending"] = False
                    st.rerun()

    # --- Main fight view
    col_left, col_right = st.columns([1, 1])

    # LEFT: Data Card
    with col_left:
        if cfg.name == "Executioner's Chariot":
            # Phase 1: show the Chariot card
            # Phase 2 (after heat-up): show the Skeletal Horse card
            if not st.session_state.get("chariot_heatup_done", False):
                img = render_data_card_cached(
                    BEHAVIOR_CARDS_PATH + f"{cfg.name} - Executioner's Chariot.jpg",
                    cfg.raw,
                    is_boss=True,
                    no_edits=True,  # matches Behavior Decks tab behavior
                )
            else:
                img = render_data_card_cached(
                    BEHAVIOR_CARDS_PATH + f"{cfg.name} - Skeletal Horse.jpg",
                    cfg.raw,
                    is_boss=True,
                )

            st.image(img, width=CARD_DISPLAY_WIDTH)

        elif "Ornstein" in cfg.raw and "Smough" in cfg.raw:
            o_img, s_img = render_dual_boss_data_cards(cfg.raw)

            ornstein_dead = st.session_state.get("ornstein_dead", False)
            smough_dead = st.session_state.get("smough_dead", False)

            # If one is dead (phase 2), show only the survivor's data card
            if ornstein_dead and not smough_dead:
                # Smough survives
                st.image(s_img, width=CARD_DISPLAY_WIDTH)
            elif smough_dead and not ornstein_dead:
                # Ornstein survives
                st.image(o_img, width=CARD_DISPLAY_WIDTH)
            else:
                # Phase 1 (both alive) or weird edge case: show both
                o_col, s_col = st.columns(2)
                with o_col:
                    st.image(o_img, width=CARD_DISPLAY_WIDTH)
                with s_col:
                    st.image(s_img, width=CARD_DISPLAY_WIDTH)
        # Special case for Vordt's Frostbreath
        elif cfg.name == "Vordt of the Boreal Valley":
            data_path = cfg.display_cards[0] if cfg.display_cards else None
            if data_path:
                data_img = render_data_card_cached(data_path, cfg.raw, is_boss=True)

                if state.get("vordt_frostbreath_active", False):
                    # Find the Frostbreath behavior key (handles "Frostbreath", "Frost Breath", etc.)
                    frost_key = None
                    for key in cfg.behaviors.keys():
                        name_lower = key.lower()
                        if "frost" in name_lower and "breath" in name_lower:
                            frost_key = key
                            break

                    if frost_key:
                        frost_path = _behavior_image_path(cfg, frost_key)
                        frost_img = render_behavior_card_cached(
                            frost_path,
                            cfg.behaviors[frost_key],
                            is_boss=True,
                        )
                        # Show data card + Frostbreath side-by-side
                        c1, c2 = st.columns(2)
                        with c1:
                            st.image(data_img, width=CARD_DISPLAY_WIDTH)
                        with c2:
                            st.image(frost_img, width=CARD_DISPLAY_WIDTH)
                    else:
                        # Safety fallback: just show data card
                        st.image(data_img, width=CARD_DISPLAY_WIDTH)
                else:
                    # Normal Vordt display, no Frostbreath this draw
                    st.image(data_img, width=CARD_DISPLAY_WIDTH)
        else:
            # first display card is always the data card
            data_path = cfg.display_cards[0] if cfg.display_cards else None
            if data_path:
                img = render_data_card_cached(data_path, cfg.raw, is_boss=True)
                st.image(img, width=CARD_DISPLAY_WIDTH)

    # RIGHT: Deck + current card
    with col_right:
        current = state.get("current_card")

        if not current:
            # No card drawn yet => show card back
            st.image(CARD_BACK, width=CARD_DISPLAY_WIDTH)
        else:
        # --- Ornstein & Smough dual-boss case ---
            if cfg.name == "Ornstein & Smough":
                current_name = current

                if current_name:
                    # Phase 1: combined card, e.g. "Swiping Combo & Bonzai Drop"
                    if "&" in (current_name or ""):
                        img = render_dual_boss_behavior_card(
                            cfg.raw,
                            current_name,
                            boss_name=cfg.name,
                        )
                    # Phase 2: single behavior card, e.g. "Charged Swiping Combo"
                    else:
                        img = render_behavior_card_cached(
                            _behavior_image_path(cfg, current_name),
                            cfg.behaviors.get(current_name, {}),
                            is_boss=True,
                        )

                    st.image(img, width=CARD_DISPLAY_WIDTH)

            # --- Vordt of the Boreal Valley: movement + attack decks ---
            elif cfg.name == "Vordt of the Boreal Valley" and isinstance(current, tuple):
                move_card, atk_card = current

                # Show the cards side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    move_path = _behavior_image_path(cfg, move_card)
                    st.image(
                        render_behavior_card_cached(
                            move_path,
                            cfg.behaviors.get(move_card, {}),
                            is_boss=True,
                        ),
                        width=CARD_DISPLAY_WIDTH,
                    )
                with c2:
                    atk_path = _behavior_image_path(cfg, atk_card)
                    st.image(
                        render_behavior_card_cached(
                            atk_path,
                            cfg.behaviors.get(atk_card, {}),
                            is_boss=True,
                        ),
                        width=CARD_DISPLAY_WIDTH,
                    )

            # --- Gaping Dragon: Stomach Slam shows Crawling Charge alongside ---
            elif cfg.name == "Gaping Dragon" and current.startswith("Stomach Slam"):
                # Stomach Slam image
                stomach_path = _behavior_image_path(cfg, current)
                stomach_img = render_behavior_card_cached(
                    stomach_path,
                    cfg.behaviors[current],
                    is_boss=True,
                )

                # Find Crawling Charge in the behaviors (handles things like "Crawling Charge 2")
                crawl_key = None
                for key in cfg.behaviors.keys():
                    if key.startswith("Crawling Charge"):
                        crawl_key = key
                        break

                if crawl_key:
                    crawl_path = _behavior_image_path(cfg, crawl_key)
                    crawl_img = render_behavior_card_cached(
                        crawl_path,
                        cfg.behaviors[crawl_key],
                        is_boss=True,
                    )

                    # Show them side-by-side
                    c1, c2 = st.columns(2)
                    with c1:
                        st.image(stomach_img, width=CARD_DISPLAY_WIDTH)
                    with c2:
                        st.image(crawl_img, width=CARD_DISPLAY_WIDTH)
                else:
                    # Fallback: if Crawling Charge isn't found for some reason,
                    # at least show Stomach Slam
                    st.image(stomach_img, width=CARD_DISPLAY_WIDTH)

            # --- Guardian Dragon: Cage Grasp Inferno shows Fiery Breath alongside ---
            elif cfg.name == GUARDIAN_DRAGON_NAME and isinstance(current, str) and current.startswith(GUARDIAN_CAGE_PREFIX):
                # Track when a new card is drawn so we only change the pattern
                # when the deck actually advances.
                last_key = f"boss_mode_last_current::{cfg.name}"
                last_current = st.session_state.get(last_key)
                is_new_draw = last_current != current
                st.session_state[last_key] = current

                # Decide which Fiery Breath pattern mode we're in
                mode = "generated" if st.session_state.get("guardian_fiery_generate", False) else "deck"

                # Reuse the existing pattern for this card where possible,
                # otherwise draw a new one according to the selected mode.
                pattern_nodes = state.get("guardian_fiery_current_pattern")
                prev_mode = state.get("guardian_fiery_current_mode")
                if pattern_nodes is None or prev_mode != mode or is_new_draw:
                    pattern_nodes = _guardian_fiery_draw_pattern(state, mode)
                    state["guardian_fiery_current_pattern"] = pattern_nodes
                    state["guardian_fiery_current_mode"] = mode

                # Base Cage Grasp Inferno image
                cage_path = _behavior_image_path(cfg, current)
                cage_img = render_behavior_card_cached(
                    cage_path,
                    cfg.behaviors.get(current, {}),
                    is_boss=True,
                )

                # Fiery Breath with AoE overlay
                fiery_img = _guardian_render_fiery_breath(cfg, pattern_nodes)

                # Show them side-by-side
                c1, c2 = st.columns(2)
                with c1:
                    st.image(cage_img, width=CARD_DISPLAY_WIDTH)
                with c2:
                    st.image(fiery_img, width=CARD_DISPLAY_WIDTH)

            # --- Normal single-card case ---
            else:
                base_path = _behavior_image_path(cfg, current)
                img = render_behavior_card_cached(
                    base_path,
                    cfg.behaviors[current],
                    is_boss=True,
                )
                st.image(img, width=CARD_DISPLAY_WIDTH)

        if cfg.name == "Vordt of the Boreal Valley":
            st.caption(
                f"{len(state.get('vordt_move_discard', [])) + (1 if current else 0)} movement cards played"
                f" • {len(state.get('vordt_attack_discard', [])) + (1 if current else 0)} attack cards played"
            )
        else:
            st.caption(
                f"Draw pile: {len(state.get('draw_pile', []))} cards"
                f" • Discard: {len(state.get('discard_pile', [])) + (1 if current else 0)} cards"
            )
