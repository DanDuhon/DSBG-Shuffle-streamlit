#ui/ngplus_tab/render.py
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from ui.ngplus_tab.logic import (
    MAX_NGPLUS_LEVEL,
    get_current_ngplus_level,
    dodge_bonus_for_level,
    apply_ngplus_to_raw,
    health_bonus_for_level,
)
from ui.behavior_decks_tab.generation import (
    build_behavior_catalog,
    render_data_card_cached,
    render_behavior_card_cached,
)
from ui.behavior_decks_tab.assets import BEHAVIOR_CARDS_PATH, CATEGORY_ORDER, CATEGORY_EMOJI
from ui.behavior_decks_tab.logic import _read_behavior_json
from ui.behavior_decks_tab.models import BehaviorEntry


# ---------- Helpers ----------
def _behavior_card_keys(raw: Dict[str, Any]) -> List[str]:
    """
    For boss/invader JSONs:
    behavior cards are top-level dicts that have a 'middle' section.
    """
    keys: List[str] = []
    for key, value in raw.items():
        if isinstance(value, dict) and "middle" in value:
            keys.append(key)
    return keys


def _data_card_path(enemy_name: str) -> str:
    """
    Best-effort data card path.
    Tries a couple of common filenames and picks the first that exists.
    """
    candidates: List[str] = []

    # Special-ish cases can be added here if needed
    if enemy_name == "Executioner's Chariot":
        candidates = [
            f"{enemy_name} - data.jpg",
            f"{enemy_name} - Skeletal Horse.jpg",
            f"{enemy_name} - Executioner's Chariot.jpg",
        ]
    else:
        candidates = [f"{enemy_name} - data.jpg"]

    for filename in candidates:
        path = Path(BEHAVIOR_CARDS_PATH + filename)
        if path.exists():
            return str(path)

    # Fallback: just use the first candidate
    return BEHAVIOR_CARDS_PATH + candidates[0]


def _behavior_card_path(enemy_name: str, card_name: str) -> str:
    """Default behavior card filename pattern."""
    return BEHAVIOR_CARDS_PATH + f"{enemy_name} - {card_name}.jpg"


# ---------- Main NG+ tab ----------
def render():
    current_level = get_current_ngplus_level()

    # --- Overview in an expander ---
    with st.expander("New Game+ rules overview", expanded=False):
        st.markdown(f"**Current NG+ level (from sidebar):** NG+{current_level}")

        st.markdown("### Level Effects")

        for lvl in range(0, MAX_NGPLUS_LEVEL + 1):
            is_current = lvl == current_level
            bullet = "✅" if is_current else "•"

            if lvl == 0:
                desc = (
                    "Base game values. No bonus damage, HP, dodge, or heat-up changes."
                )
            else:
                dodge_b = dodge_bonus_for_level(lvl)
                if dodge_b == 0:
                    dodge_text = "No change to dodge difficulty."
                elif dodge_b == 1:
                    dodge_text = "+1 to dodge difficulty."
                else:
                    dodge_text = "+2 to dodge difficulty."

                desc = (
                    f"+{lvl} damage on all attacks. "
                    "Max HP increases based on base HP (see rules below). "
                    "Heat-up triggers increase by the same amount as the HP bonus. "
                    f"{dodge_text}"
                )

            st.markdown(f"{bullet} **NG+{lvl}** – {desc}")

        st.markdown("#### HP & Heat-up Scaling Rules")

        st.markdown(
            """
- Base HP **1–3**: +1 HP per NG+ level  
- Base HP **4–7**: +2 / +3 / +5 / +6 / +8 HP at NG+1–5  
- Base HP **8–10**: +2 HP per NG+ level  
- Base HP **>10**: +10% HP per NG+ level (rounded up)  
- **Heat-up triggers**: increased by the same amount as the HP bonus  
- **Paladin Leeroy**: Healing Talisman's effect is increased by the HP bonus
- **Maldron the Assassin**: Maldron heals to full when heating up
- **Great Grey Wolf Sif**: Changes to only using Limping Strike **3** HP no matter the NG+ level  
"""
        )

    # --- Per-card inspector ---
    st.subheader("Card Inspector")

    # Build or reuse catalog (same pattern as Behavior Decks tab)
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    catalog = st.session_state["behavior_catalog"]

    # Available categories
    available_cats = [
        c for c in CATEGORY_ORDER
        if catalog.get(c)
    ] or CATEGORY_ORDER

    # 1 Category chooser (radio; horizontal)
    category = st.radio(
        "Type of enemy / boss",
        available_cats,
        index=0,
        key="ngplus_category",
        horizontal=True,
        format_func=lambda c: f"{CATEGORY_EMOJI.get(c, '')} {c}",
    )

    entries: List[BehaviorEntry] = catalog.get(category, [])
    if not entries:
        st.info("No encounters found in this category.")
        return

    names = [e.name for e in entries]

    # Preserve previous selection if possible
    last_choice = st.session_state.get("ngplus_choice")
    if last_choice in names:
        default_index = names.index(last_choice)
    else:
        default_index = 0

    # 3 Actual enemy/boss dropdown
    choice = st.selectbox(
        "Choose enemy / invader / boss",
        options=names,
        index=default_index,
        key="ngplus_choice",
    )

    selected_entry = next(e for e in entries if e.name == choice)
    fpath = Path(str(selected_entry.path))
    enemy_name = selected_entry.name

    # --- Load base JSON (no NG+), then apply NG+ ourselves ---
    base_raw = _read_behavior_json(str(fpath))  # original JSON
    raw_ng = apply_ngplus_to_raw(base_raw, current_level, enemy_name=enemy_name)

    st.markdown(f"### {enemy_name} @ NG+{current_level}")

    # --- Determine enemy type & behavior-card list ---
    is_single_card_enemy = (
        "behavior" in base_raw and isinstance(base_raw["behavior"], dict)
    )

    if is_single_card_enemy:
        behavior_keys: List[str] = []
    else:
        behavior_keys = _behavior_card_keys(raw_ng)

    # Behavior dropdown is only shown for bosses/invaders with multiple cards
    chosen_behavior_name: str | None = None
    if behavior_keys:
        sorted_keys = sorted(behavior_keys)
        default_card = st.session_state.get("ngplus_inspect_card")
        if default_card not in sorted_keys:
            default_card = sorted_keys[0]

        chosen_behavior_name = st.selectbox(
            "Behavior card",
            sorted_keys,
            index=sorted_keys.index(default_card),
            key="ngplus_inspect_card",
        )

    # ---------- Side-by-side card layout ----------

    cols = st.columns(2)

    # Left: data card
    with cols[0]:
        try:
            data_path = _data_card_path(enemy_name)
            img = render_data_card_cached(
                data_path,
                raw_ng,
                is_boss=not is_single_card_enemy,
            )
            st.image(img, width="stretch")
        except Exception:
            st.info("Could not render the data card image for this encounter.")

    # Right: selected behavior card (if any)
    with cols[1]:
        if chosen_behavior_name is not None:
            try:
                card_cfg = raw_ng[chosen_behavior_name]
                card_path = _behavior_card_path(enemy_name, chosen_behavior_name)
                card_img = render_behavior_card_cached(
                    card_path,
                    card_cfg,
                    is_boss=not is_single_card_enemy,
                )
                st.image(card_img, width="stretch")
            except Exception:
                st.info("Could not render this behavior card image.")
