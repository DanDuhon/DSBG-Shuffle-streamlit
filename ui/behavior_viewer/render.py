import streamlit as st
from core.behavior.generation import (
    build_behavior_catalog,
    render_behavior_card_cached,
    render_data_card_cached,
    render_dual_boss_data_cards,
)
from core.behavior.logic import load_behavior
from core.behavior.assets import CATEGORY_ORDER, _behavior_image_path
from core.image_cache import get_image_bytes_cached
from core.behavior.priscilla_overlay import overlay_priscilla_arcs


def render():
    # Build catalog once per session
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]
    # Choose category and entity on the same row
    categories = [c for c in CATEGORY_ORDER if c in catalog] or list(catalog.keys())
    if not categories:
        st.info("No behavior categories found.")
        return

    col_cat, col_ent = st.columns([1, 2])
    with col_cat:
        default_cat = st.session_state.get("behavior_viewer_category", categories[0])
        category = st.selectbox(
            "Category",
            categories,
            index=categories.index(default_cat) if default_cat in categories else 0,
            key="behavior_viewer_category",
        )

    entries = catalog.get(category, [])
    # Filter out internal-only or stray entries (e.g., priscilla_arcs)
    entries = [e for e in entries if e.name != "priscilla_arcs"]
    if not entries:
        with col_ent:
            st.info("No behavior entries found for this category.")
        return

    with col_ent:
        last = st.session_state.get("behavior_viewer_choice_name")
        names = [e.name for e in entries]
        idx = names.index(last) if last in names else 0
        entry = st.selectbox(
            "Choose entity",
            entries,
            index=idx,
            key="behavior_viewer_choice",
            format_func=lambda e: e.name,
        )
        st.session_state["behavior_viewer_choice_name"] = entry.name

    if not entry:
        return

    # Load the behavior config
    cfg = load_behavior(entry.path)

    # Present cards as radio options on the left; show image on the right
    # Build behavior option ordering. Special-case Ornstein & Smough grouping.
    if entry.name == "Ornstein & Smough":
        all_names = list(cfg.behaviors.keys())
        # Dual combined non-heatup cards (e.g., "X & Y") should appear first
        dual_non_heatup = [n for n in all_names if "&" in n and not cfg.behaviors.get(n, {}).get("heatup", False)]
        # Other non-heatup cards
        nonheat = [n for n in all_names if n not in dual_non_heatup and not cfg.behaviors.get(n, {}).get("heatup")]
        # Sort so move behaviors come before attack behaviors, then by name
        def _sort_key(n):
            t = cfg.behaviors.get(n, {}).get("type")
            rank = 0 if t == "move" else 1 if t == "attack" else 2
            return (rank, str(n).lower())
        nonheat.sort(key=_sort_key)
        # Heatup groups go to the end
        orn_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Ornstein"]
        smough_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Smough"]
        orn_heatup.sort(key=_sort_key)
        smough_heatup.sort(key=_sort_key)
        # remaining for compact display convenience
        remaining = nonheat[:]
        dual_non_heatup.sort(key=_sort_key)
        beh_order = dual_non_heatup + nonheat + orn_heatup + smough_heatup
        # Special-case: for Vordt, ensure Frostbreath appears first (under Data Card)
        if entry.name == "Vordt of the Boreal Valley":
            if "Frostbreath" in beh_order:
                beh_order.remove("Frostbreath")
                beh_order.insert(0, "Frostbreath")
    else:
        # General case: non-heatup first, then heatup cards at end
        all_names = list(cfg.behaviors.keys())
        def _sort_key(n):
            t = cfg.behaviors.get(n, {}).get("type")
            rank = 0 if t == "move" else 1 if t == "attack" else 2
            return (rank, str(n).lower())
        nonheat = [n for n in all_names if not cfg.behaviors.get(n, {}).get("heatup")]
        heatups = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup")]
        # Sort non-heatup as before (move -> attack -> other, then name)
        nonheat.sort(key=_sort_key)
        # Sort heatups by their heatup value (numeric when possible), then by name
        def _heatup_key(n):
            h = cfg.behaviors.get(n, {}).get("heatup")
            h_str = str(h)
            h_key = int(h_str) if h_str.isdigit() else h_str.lower()
            return (h_key, str(n).lower())
        heatups.sort(key=_heatup_key)
        # Place non-heatup cards first, then heatup cards
        beh_order = nonheat + heatups
        # Special-case: for Vordt, ensure Frostbreath appears first (under Data Card)
        if entry.name == "Vordt of the Boreal Valley":
            if "Frostbreath" in beh_order:
                beh_order.remove("Frostbreath")
                beh_order.insert(0, "Frostbreath")

        # Build compact-mode options with group headers for heatup cards
    # Build display labels for non-compact radio so heatup cards are indicated
    # Special-case: remove Fiery Breath from Guardian Dragon options
    if entry.name == "Guardian Dragon":
        if "Fiery Breath" in beh_order:
            beh_order.remove("Fiery Breath")

    # Special-case: Gaping Dragon has duplicate 'Stomach Slam' cards; only show 'Stomach Slam 1'
    if entry.name == "Gaping Dragon":
        keep = "Stomach Slam 1"
        # Remove other stomach slam variants (e.g., 'Stomach Slam 2')
        beh_order = [n for n in beh_order if not (n.startswith("Stomach Slam") and n != keep)]
        # If the preferred card isn't present but a generic exists, keep the first stomach slam
        if keep not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Stomach Slam"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break

    # Special-case: The Pursuer - collapse Stabbing Strike and Wide Blade Swing variants to single entries
    if entry.name == "The Pursuer":
        # Keep the first variant for each duplicate group
        keep_ss = "Stabbing Strike 1"
        keep_wb = "Wide Blade Swing 1"
        beh_order = [n for n in beh_order if not (n.startswith("Stabbing Strike") and n != keep_ss)]
        beh_order = [n for n in beh_order if not (n.startswith("Wide Blade Swing") and n != keep_wb)]
        # If preferred names are missing, pull any matching variant to front
        if keep_ss not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Stabbing Strike"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break
        if keep_wb not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Wide Blade Swing"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break

    # Special-case: The Last Giant ordering and emojis
    if entry.name == "The Last Giant":
        # Identify falling slam(s), arm cards, non-arm non-heatup, and heatups
        falling = [n for n in beh_order if isinstance(n, str) and n.startswith("Falling Slam")]
        # Use explicit `arm` flag from JSON to find arm cards
        arm_cards = [n for n in beh_order if cfg.behaviors.get(n, {}).get("arm") == True]
        non_arm_nonheat = [n for n in beh_order if n not in falling and n not in arm_cards and not cfg.behaviors.get(n, {}).get("heatup")]
        heatups_last = [n for n in beh_order if cfg.behaviors.get(n, {}).get("heatup")]
        # Build desired order: Falling Slam first, then non-arm non-heatup, then arm cards, then heatups
        beh_order = falling + non_arm_nonheat + arm_cards + heatups_last

    # Always exclude 'Mega Boss Setup' from lists
    if "Mega Boss Setup" in beh_order:
        beh_order = [n for n in beh_order if n != "Mega Boss Setup"]

    # Special-case: Executioner's Chariot - single Death Race, placed first
    if entry.name == "Executioner's Chariot":
        keep = "Death Race 1"
        # Remove other Death Race variants
        beh_order = [n for n in beh_order if not (isinstance(n, str) and n.startswith("Death Race") and n != keep)]
        # Ensure preferred Death Race is first (if missing, pull any Death Race into front)
        if keep in beh_order:
            beh_order = [keep] + [n for n in beh_order if n != keep]
        else:
            for n in list(cfg.behaviors.keys()):
                if isinstance(n, str) and n.startswith("Death Race"):
                    if n in beh_order:
                        beh_order = [n] + [x for x in beh_order if x != n]
                    else:
                        beh_order.insert(0, n)
                    break

    # Special-case: Great Grey Wolf Sif - show Limping Strike first under the data card
    if entry.name == "Great Grey Wolf Sif":
        limp = None
        for n in beh_order:
            if isinstance(n, str) and n.startswith("Limping Strike"):
                limp = n
                break
        if limp:
            beh_order = [limp] + [n for n in beh_order if n != limp]

    display_map = {}
    display_labels = []
    for name in (beh_order if category != "Regular Enemies" else []):
        b = cfg.behaviors.get(name, {})
        heat = b.get("heatup")
        btype = b.get("type")
        # Emoji for move vs attack; special-case Last Giant arm/Falling Slam and Vordt Frostbreath
        if entry.name == "Executioner's Chariot" and isinstance(name, str) and name.startswith("Death Race"):
            type_emoji = "🛞"
        elif entry.name == "Great Grey Wolf Sif" and isinstance(name, str) and name.startswith("Limping Strike"):
            type_emoji = "🩸"
        elif entry.name == "The Last Giant" and isinstance(name, str) and name.startswith("Falling Slam"):
            type_emoji = "⬇️"
        elif entry.name == "The Last Giant" and isinstance(name, str) and cfg.behaviors.get(name, {}).get("arm") == True:
            type_emoji = "💪"
        elif entry.name == "Vordt of the Boreal Valley" and name == "Frostbreath":
            type_emoji = "❄️"
        elif  entry.name == "Vordt of the Boreal Valley" and btype == "move":
            type_emoji = "🦶"
        elif  entry.name == "Vordt of the Boreal Valley" and btype == "attack":
            type_emoji = "🪓"
        else:
            type_emoji = ""

        # Compose label: heatup indicator (if any) goes first, then type emoji, then name
        if entry.name == "Ornstein & Smough":
            if isinstance(heat, str) and heat == "Ornstein":
                prefix = "🔥 Ornstein —"
            elif isinstance(heat, str) and heat == "Smough":
                prefix = "🔥 Smough —"
            else:
                prefix = ""
        elif entry.name == "The Four Kings":
            num_map = {
                "2": "2️⃣",
                "3": "3️⃣",
                "4": "4️⃣",
            }
            prefix = num_map[str(heat)] if heat else ""
        else:
            prefix = "🔥" if heat else ""

        # Build label parts, avoiding extra spaces when empty
        parts = []
        if prefix:
            parts.append(prefix)
        if type_emoji:
            parts.append(type_emoji)
        # For Gaping Dragon and Executioner's Chariot, collapse numbered labels to single names
        if entry.name == "Gaping Dragon" and isinstance(name, str) and name.startswith("Stomach Slam"):
            display_name = "Stomach Slam"
        elif entry.name == "Executioner's Chariot" and isinstance(name, str) and name.startswith("Death Race"):
            display_name = "Death Race"
        elif entry.name == "The Pursuer" and isinstance(name, str) and name.startswith("Stabbing Strike"):
            display_name = "Stabbing Strike"
        elif entry.name == "The Pursuer" and isinstance(name, str) and name.startswith("Wide Blade Swing"):
            display_name = "Wide Blade Swing"
        else:
            display_name = name
        parts.append(display_name)
        label = " ".join(parts)

        # Map the displayed label back to the actual behavior key
        display_map[label] = name
        display_labels.append(label)

    options = ["(Data Card)"] + display_labels

    left_col, right_col = st.columns([1, 2])

    # Respect compact UI setting: dropdown in compact mode, radio otherwise.
    compact = bool(st.session_state.get("ui_compact", False))

    # Build compact-mode options with group headers for heatup cards
    options_compact = ["(Data Card)"]
    if entry.name == "Ornstein & Smough":
        if 'dual_non_heatup' in locals() and dual_non_heatup:
            options_compact.extend(dual_non_heatup)
        if 'orn_heatup' in locals() and orn_heatup:
            options_compact.append("— Ornstein heatups —")
            options_compact.extend(orn_heatup)
        if 'smough_heatup' in locals() and smough_heatup:
            options_compact.append("— Smough heatups —")
            options_compact.extend(smough_heatup)
        if 'remaining' in locals() and remaining:
            options_compact.append("— Other —")
            options_compact.extend(remaining)
    else:
        non_heatup = [n for n in beh_order if not cfg.behaviors.get(n, {}).get("heatup")]
        heatups = [n for n in beh_order if cfg.behaviors.get(n, {}).get("heatup")]
        options_compact.extend(non_heatup)
        if heatups:
            options_compact.append("— Heatup cards —")
            options_compact.extend(heatups)

    # Try to preserve previous selection across mode changes
    prev = st.session_state.get("behavior_viewer_card_choice") or st.session_state.get("behavior_viewer_card_choice_compact")
    if compact:
        default_index = options_compact.index(prev) if prev in options_compact else 0
    else:
        if prev in options:
            default_index = options.index(prev)
        else:
            # If previous was stored as the original behavior name, find its display label
            found_label = None
            for lbl, orig in display_map.items():
                if orig == prev:
                    found_label = lbl
                    break
            default_index = options.index(found_label) if found_label and found_label in options else 0

    with left_col:
        if compact:
            choice = st.selectbox("Card", options_compact, index=default_index, key="behavior_viewer_card_choice_compact")
        else:
            choice = st.radio("Card", options, index=default_index, key="behavior_viewer_card_choice")

        # Priscilla invisibility toggle
        priscilla_invis_key = "behavior_viewer_priscilla_invisible"
        if entry.name == "Crossbreed Priscilla":
            # `st.checkbox` will set `st.session_state[priscilla_invis_key]` itself;
            # avoid assigning into session_state after widget creation.
            st.checkbox("Show invisibility version", value=False, key=priscilla_invis_key)

    with right_col:
        if choice == "(Data Card)":
            if entry.name == "Ornstein & Smough":
                o_img, s_img = render_dual_boss_data_cards(cfg.raw)
                c1, c2 = st.columns(2)
                with c1:
                    st.image(o_img, width=360)
                with c2:
                    st.image(s_img, width=360)
            else:
                # Special-case: always show skeletal horse data card for Executioner's Chariot
                if entry.name == "Executioner's Chariot":
                    img_bytes = render_data_card_cached(
                        "assets/behavior cards/Executioner's Chariot - Skeletal Horse.jpg",
                        cfg.raw,
                        is_boss=(entry.tier != "enemy"),
                    )
                    st.image(img_bytes, width=360)
                elif cfg.display_cards:
                    img_bytes = render_data_card_cached(cfg.display_cards[0], cfg.raw, is_boss=(entry.tier != "enemy"))
                    st.image(img_bytes, width=360)
        else:
            # Map display label back to original behavior name for non-compact mode
            if compact:
                sel = choice
            else:
                sel = display_map.get(choice, choice)

            # Headers in compact mode (strings starting with '—') are just labels
            if compact and isinstance(sel, str) and sel.strip().startswith("—"):
                st.info("Select a behavior card — header rows are labels in compact mode.")
            else:
                beh = cfg.behaviors.get(sel, {})
                img_path = _behavior_image_path(cfg, sel)
                img_bytes = render_behavior_card_cached(img_path, beh, is_boss=(entry.tier != "enemy"))
                # Apply Priscilla overlay when requested
                if entry.name == "Crossbreed Priscilla" and st.session_state.get(priscilla_invis_key, True):
                    img_bytes = overlay_priscilla_arcs(img_bytes, sel, beh)
                # If this is Vordt, prepend a small emoji indicating move vs attack
                if entry.name == "Vordt of the Boreal Valley":
                    btype = None
                    if isinstance(beh, dict):
                        btype = beh.get("type")
                    if btype == "move":
                        st.markdown("**🏃 Move**")
                    elif btype == "attack":
                        st.markdown("**⚔️ Attack**")
                st.image(img_bytes, width=360)
