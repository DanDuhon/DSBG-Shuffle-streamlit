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
from ui.behavior_decks_tab.generation import build_behavior_catalog
from ui.behavior_decks_tab.logic import load_behavior


def _get_catalog():
    """Reuse the same behavior catalog as the Behavior Decks tab."""
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()
    return st.session_state["behavior_catalog"]


def _card_text_block(card: Dict[str, Any], label: str | None = None) -> None:
    if label:
        st.markdown(f"**{label}**")

    dodge = card.get("dodge")
    mid = card.get("middle", {})
    dmg = mid.get("damage")
    dmg_type = mid.get("type")
    effects = mid.get("effect")

    lines: List[str] = []

    if dodge is not None:
        lines.append(f"- Dodge difficulty: **{dodge}**")

    if dmg is not None:
        if dmg_type:
            lines.append(f"- Attack: **{dmg}** ({dmg_type})")
        else:
            lines.append(f"- Attack: **{dmg}**")

    if effects:
        if isinstance(effects, list):
            effects_text = ", ".join(str(e) for e in effects)
        else:
            effects_text = str(effects)
        lines.append(f"- Effects: {effects_text}")

    if not lines:
        st.write("_No attack info on this card._")
    else:
        st.markdown("\n".join(lines))


def render():
    current_level = get_current_ngplus_level()

    st.subheader("New Game+ Overview")
    st.markdown(f"Current level from sidebar: **NG+{current_level}**")

    # --- Level descriptions 0–5 ---
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

    # --- HP & heat-up scaling summary ---
    st.markdown("#### HP & Heat-up Scaling Rules")

    st.markdown(
        """
- Base HP **1–3**: +1 HP per NG+ level  
- Base HP **4–7**: +2 / +3 / +5 / +6 / +8 HP at NG+1–5  
- Base HP **8–10**: +2 HP per NG+ level  
- Base HP **>10**: +10% HP per NG+ level (rounded up)  
- **Heat-up triggers**: increased by the same amount as the HP bonus  
- **Sif – Limping Strike**: stays at **3** HP no matter the NG+ level  
"""
    )

    st.markdown("#### Special: Paladin Leeroy")

    st.markdown(
        """
Paladin Leeroy gains a once-per-life buffer in NG+:

> *"The first time Leeroy's health would be  
> reduced to 0, set his health to **X** instead."*

Where **X = 2 + HP bonus from NG+** for his data card.  
(For example, if NG+ increases his max HP by 4, X will be 6.)
"""
    )

    st.markdown("---")
    st.subheader("Per-Card Inspector")

    catalog = _get_catalog()
    categories = [c for c, entries in catalog.items() if entries]
    if not categories:
        st.info("No behavior decks available.")
        return

    # Category selection (reuse previous choice if possible)
    default_cat = st.session_state.get("ngplus_inspect_category", categories[0])
    if default_cat not in categories:
        default_cat = categories[0]

    category = st.selectbox(
        "Category",
        categories,
        index=categories.index(default_cat),
        key="ngplus_inspect_category",
    )

    entries = catalog.get(category, [])
    if not entries:
        st.info("No enemies in this category.")
        return

    names = [e.name for e in entries]

    default_enemy = st.session_state.get("ngplus_inspect_enemy")
    if default_enemy not in names:
        default_enemy = names[0]

    enemy_name = st.selectbox(
        "Enemy / Invader / Boss",
        names,
        index=names.index(default_enemy),
        key="ngplus_inspect_enemy",
    )

    selected_entry = next(e for e in entries if e.name == enemy_name)

    # Load raw config, then apply NG+ for the current level
    cfg = load_behavior(Path(str(selected_entry.path)))
    raw_ng = apply_ngplus_to_raw(cfg.raw, current_level, enemy_name=enemy_name)

    st.markdown(f"### {enemy_name} @ NG+{current_level}")

    # Health summary (show base + bonus)
    base_hp = cfg.raw.get("health")
    if isinstance(base_hp, (int, float)):
        hp_bonus = health_bonus_for_level(int(base_hp), current_level)
        new_hp = raw_ng.get("health", base_hp)
        st.markdown(
            f"- Max HP: **{new_hp}** (base {int(base_hp)} + bonus {hp_bonus})"
        )
    elif "health" in raw_ng:
        st.markdown(f"- Max HP: **{raw_ng['health']}**")

    # Single-card enemy (e.g. Alonne Bow Knight)
    if "behavior" in raw_ng and isinstance(raw_ng["behavior"], dict):
        _card_text_block(raw_ng["behavior"], "Behavior card")
        return

    # Multi-card boss/invader (e.g. Armorer Dennis)
    behavior_keys = [
        key
        for key, value in raw_ng.items()
        if isinstance(value, dict) and "middle" in value
    ]

    if not behavior_keys:
        st.info("No behavior cards found for this enemy.")
        return

    for name in sorted(behavior_keys):
        _card_text_block(raw_ng[name], name)
