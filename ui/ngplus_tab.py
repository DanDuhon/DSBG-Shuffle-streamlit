from pathlib import Path

import streamlit as st

from core import behavior_decks as bd
from core import behavior_icons as bi
from core.behavior_render_cache import (
    render_data_card_cached,
    render_behavior_card_cached,
)

BEHAVIOR_CARDS_PATH = "assets/behavior cards/"


def _describe_ng_level(level: int) -> str:
    if level <= 0:
        return "NG+0 (normal game): no bonuses."
    # Dodge bonus mapping must match behavior_decks
    dodge_bonus_map = {
        1: 0,
        2: 1,
        3: 1,
        4: 2,
        5: 2,
    }
    dodge = dodge_bonus_map.get(level, 0)
    return (
        f"NG+{level}: +{level} damage, "
        f"health bonus level {level}, "
        f"{'+' + str(dodge) + ' dodge difficulty' if dodge else 'no dodge bonus'}."
    )


def render():
    st.subheader("New Game+")

    # --- NG+ level selector ---
    current_default = st.session_state.get("ng_plus_level", 0)
    level = st.slider(
        "NG+ level",
        min_value=0,
        max_value=5,
        value=current_default,
        step=1,
        key="ng_plus_level",  # this becomes the canonical value used elsewhere
    )
    st.caption(_describe_ng_level(level))

    with st.expander("Health bonus rules", expanded=False):
        st.markdown(
            """
- **Base HP 1–2:** +health bonus level to max HP  
- **Base HP 3–7:** Extra HP by level = 2, 3, 5, 6, 8  
- **Base HP 8–10:** +2 × health bonus level  
- **Base HP >10:** +10% of base HP (rounded up) per health bonus level  
            """
        )

    st.markdown("---")
    st.markdown("### Preview enemies / bosses at this NG+ level")

    files = bd.list_behavior_files()
    if not files:
        st.warning("No behavior files found in `data/behaviors`.")
        return

    labels = [f.name[:-5] for f in files]
    choice = st.selectbox(
        "Choose enemy / invader / boss to preview",
        options=labels,
        index=0 if labels else None,
        key="ngplus_preview_choice",
    )

    if not choice:
        return

    fpath = files[labels.index(choice)]
    cfg = bd.load_behavior(fpath)

    # Apply NG+ for the preview only (does not affect any running decks)
    if level:
        bd.apply_ng_plus(cfg, level)

    st.markdown(f"**Selected:** {cfg.name}")

    # --- Regular enemy preview ---
    if "behavior" in cfg.raw:
        st.markdown("_Regular enemy_")

        data_card_path = f"{BEHAVIOR_CARDS_PATH}{cfg.name} - data.jpg"
        img_bytes = render_data_card_cached(data_card_path, cfg.raw, is_boss=False)
        st.image(
            img_bytes,
            caption=f"{cfg.name} (NG+{level})" if level else cfg.name,
        )
        return

    # --- Boss / Invader preview ---
    st.markdown("_Boss / Invader_")

    st.markdown("**Data card(s)**")

    # Special case: Ornstein & Smough dual data cards
    if "Ornstein" in cfg.raw and "Smough" in cfg.raw:
        orn_bytes, sm_bytes = bi.render_dual_boss_data_cards(cfg.raw)
        cols = st.columns(2)
        with cols[0]:
            st.image(
                orn_bytes,
                caption=f"Ornstein (NG+{level})" if level else "Ornstein",
            )
        with cols[1]:
            st.image(
                sm_bytes,
                caption=f"Smough (NG+{level})" if level else "Smough",
            )
    else:
        # Fallback: main data card based on config
        # BehaviorConfig.display_cards already holds asset paths
        data_cards = cfg.data_cards or [f"{cfg.name} - data.jpg"]
        main_path = f"{BEHAVIOR_CARDS_PATH}{Path(data_cards[0]).name}"

        img_bytes = render_data_card_cached(main_path, cfg.raw, is_boss=True)
        st.image(
            img_bytes,
            caption=f"{cfg.name} (NG+{level})" if level else cfg.name,
        )

    # --- Behavior card preview ---
    st.markdown("**Behavior cards**")

    behavior_names = sorted(cfg.behaviors.keys())
    if not behavior_names:
        st.info("No behavior cards found for this enemy.")
        return

    selected_behaviors = st.multiselect(
        "Select behavior cards to preview",
        options=behavior_names,
        default=behavior_names[:1],
        key="ngplus_behavior_choice",
    )

    if not selected_behaviors:
        return

    cols = st.columns(len(selected_behaviors))
    for idx, bname in enumerate(selected_behaviors):
        clean_name = bd._strip_behavior_suffix(str(bname))
        base_path = f"{BEHAVIOR_CARDS_PATH}{cfg.name} - {clean_name}.jpg"
        img_bytes = render_behavior_card_cached(
            base_path,
            cfg.behaviors[bname],
            is_boss=True,
        )
        with cols[idx]:
            st.image(
                img_bytes,
                caption=f"{bname} (NG+{level})" if level else bname,
            )