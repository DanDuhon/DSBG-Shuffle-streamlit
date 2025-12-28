import streamlit as st
from core.behavior.generation import (
    build_behavior_catalog,
    render_behavior_card_cached,
    render_data_card_cached,
    render_dual_boss_data_cards,
)
from core.behavior.logic import load_behavior
from core.behavior.assets import CATEGORY_ORDER, _behavior_image_path
from core.image_cache import bytes_to_data_uri
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
    try:
        cfg = load_behavior(entry.path)
    except Exception as e:
        st.error(f"Failed to load behavior data: {e}")
        return

    # Present cards as radio options on the left; show image on the right
    # Build behavior option ordering. Special-case Ornstein & Smough grouping.
    if entry.name == "Ornstein & Smough":
        all_names = list(cfg.behaviors.keys())
        # Dual combined non-heatup cards (e.g., "X & Y") should appear first
        dual_non_heatup = [n for n in all_names if "&" in n and not cfg.behaviors.get(n, {}).get("heatup", False)]
        # Other non-heatup cards
        nonheat = [n for n in all_names if n not in dual_non_heatup and not cfg.behaviors.get(n, {}).get("heatup")]
        nonheat.sort()
        # Heatup groups go to the end
        orn_heatup = sorted([n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Ornstein"])
        smough_heatup = sorted([n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Smough"])
        # remaining for compact display convenience
        remaining = nonheat[:]
        beh_order = dual_non_heatup + nonheat + orn_heatup + smough_heatup
    else:
        # General case: non-heatup first, then heatup cards at end
        all_names = list(cfg.behaviors.keys())
        nonheat = sorted([n for n in all_names if not cfg.behaviors.get(n, {}).get("heatup")])
        heatups = sorted([n for n in all_names if cfg.behaviors.get(n, {}).get("heatup")])
        beh_order = nonheat + heatups

        # Build compact-mode options with group headers for heatup cards
    # Build display labels for non-compact radio so heatup cards are indicated
    display_map = {}
    display_labels = []
    for name in (beh_order if category != "Regular Enemies" else []):
        heat = cfg.behaviors.get(name, {}).get("heatup")
        if entry.name == "Ornstein & Smough":
            if isinstance(heat, str) and heat == "Ornstein":
                label = f"🔥 Ornstein — {name}"
            elif isinstance(heat, str) and heat == "Smough":
                label = f"🔥 Smough — {name}"
            else:
                label = name
        else:
            label = f"🔥 {name}" if heat else name
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
    try:
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
    except Exception:
        default_index = 0

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
                try:
                    o_img, s_img = render_dual_boss_data_cards(cfg.raw)
                    c1, c2 = st.columns(2)
                    with c1:
                        src_o = bytes_to_data_uri(o_img)
                        st.markdown(f"<div class=\"card-image\"><img src=\"{src_o}\" style=\"width:100%\"></div>", unsafe_allow_html=True)
                    with c2:
                        src_s = bytes_to_data_uri(s_img)
                        st.markdown(f"<div class=\"card-image\"><img src=\"{src_s}\" style=\"width:100%\"></div>", unsafe_allow_html=True)
                except Exception:
                    st.warning("Unable to render Ornstein & Smough data cards.")
            else:
                if cfg.display_cards:
                    img_bytes = render_data_card_cached(cfg.display_cards[0], cfg.raw, is_boss=(entry.tier != "enemy"))
                    src = bytes_to_data_uri(img_bytes)
                    st.markdown(f"<div class=\"card-image\"><img src=\"{src}\" style=\"width:360px\"></div>", unsafe_allow_html=True)
                else:
                    st.warning("No data card image available for this entity.")
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
                try:
                    img_path = _behavior_image_path(cfg, sel)
                    img_bytes = render_behavior_card_cached(img_path, beh, is_boss=(entry.tier != "enemy"))
                    # Apply Priscilla overlay when requested
                    if entry.name == "Crossbreed Priscilla" and st.session_state.get(priscilla_invis_key, True):
                        try:
                            img_bytes = overlay_priscilla_arcs(img_bytes, sel, beh)
                        except Exception:
                            pass
                    src = bytes_to_data_uri(img_bytes)
                    st.markdown(f"<div class=\"card-image\"><img src=\"{src}\" style=\"width:360px\"></div>", unsafe_allow_html=True)
                except Exception:
                    st.warning("Unable to render behavior image; the image file may be missing.")
