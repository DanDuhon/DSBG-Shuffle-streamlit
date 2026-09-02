from __future__ import annotations

from typing import Any

import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import (
    render_behavior_card_cached,
    render_behavior_card_uncached,
    render_data_card_cached,
    render_data_card_uncached,
    render_dual_boss_behavior_card,
    render_dual_boss_data_cards,
)
from core.behavior.priscilla_overlay import overlay_priscilla_arcs

from ui.behavior_viewer.models import BehaviorPickerModel, DATA_CARD_SENTINEL
from ui.boss_mode.guardian_dragon_fiery_breath import (
    GUARDIAN_CAGE_PREFIX,
    GUARDIAN_DRAGON_NAME,
)


def render_card_display(
    *,
    entry: Any,
    cfg: Any,
    model: BehaviorPickerModel,
    compact: bool,
    choice: str,
    card_width: int,
) -> None:
    """Render the right-column card display."""

    cloud_low_memory = bool(st.session_state.get("cloud_low_memory", False))

    display_map = model.display_map

    if choice == DATA_CARD_SENTINEL:
        if entry.name == "Ornstein & Smough":
            # `render_dual_boss_data_cards` is uncached, so it is safe on the
            # low-memory path too -- and unlike a raw thumbnail it actually
            # paints the stats onto the card.
            o_img, s_img = render_dual_boss_data_cards(cfg.raw)
            c1, c2 = st.columns(2)
            with c1:
                st.image(o_img, width=card_width)
            with c2:
                st.image(s_img, width=card_width)
            return

        # Special-case: always show skeletal horse data card for Executioner's Chariot
        if entry.name == "Executioner's Chariot":
            base_path = "assets/behavior cards/Executioner's Chariot - Skeletal Horse.jpg"
            render_data = (
                render_data_card_uncached if cloud_low_memory else render_data_card_cached
            )
            st.image(
                render_data(base_path, cfg.raw, is_boss=(entry.tier != "enemy")),
                width=card_width,
            )
            return

        if cfg.display_cards:
            # Low memory picks the uncached renderer, NOT a raw thumbnail. The
            # thumbnail is the untouched base image, so on Streamlit Cloud --
            # where low-memory mode is on by default -- every data card here
            # showed up without its health/armor/resist/heatup values or its
            # dodge icon. Boss Mode already did it this way, which is why the
            # same card looked right there.
            render_data = (
                render_data_card_uncached if cloud_low_memory else render_data_card_cached
            )
            st.image(
                render_data(
                    cfg.display_cards[0],
                    cfg.raw,
                    is_boss=(entry.tier != "enemy"),
                ),
                width=card_width,
            )
        return

    # Map display label back to original behavior name for non-compact mode
    if compact:
        sel = choice
    else:
        sel = display_map.get(choice, choice)

    # Headers in compact mode (strings starting with '—') are just labels
    if compact and isinstance(sel, str) and sel.strip().startswith("—"):
        st.info("Select a behavior card — header rows are labels in compact mode.")
        return

    beh = cfg.behaviors.get(sel, {})

    # Guardian Dragon's "Cage Grasp Inferno" cards carry a `dodge` value in the
    # JSON, but on the printed card that difficulty belongs to the paired Fiery
    # Breath AoE card, not this one. Boss Mode strips it for exactly this reason
    # (`try_render_guardian_dragon_current`) and draws it on the AoE card; the
    # viewer shows one card at a time, so it just drops it.
    if (
        entry.name == GUARDIAN_DRAGON_NAME
        and isinstance(sel, str)
        and sel.startswith(GUARDIAN_CAGE_PREFIX)
        and isinstance(beh, dict)
    ):
        beh = {k: v for k, v in beh.items() if k != "dodge"}

    if cloud_low_memory:
        # Cloud low-memory: avoid generating/caching rendered PNGs per card.
        # Show the base JPG as a thumbnail instead.
        try:
            img_path = None
            if entry.name == "Ornstein & Smough" and isinstance(sel, str) and "&" in sel:
                # No simple base image path for dual cards; fall back to renderer.
                img_bytes = render_dual_boss_behavior_card(cfg.raw, sel, boss_name=entry.name)
                st.image(img_bytes, width=card_width)
                return
            img_path = _behavior_image_path(cfg, sel)
            # In low-memory environments we avoid caching large PNGs, but still
            # render the behavior onto the base image so icons appear. Use the
            # uncached renderer variant to prevent storing large blobs in
            # Streamlit cache while preserving icon compositing.
            img_bytes = render_behavior_card_uncached(
                img_path,
                beh,
                is_boss=(entry.tier != "enemy"),
            )
            if img_bytes:
                st.image(img_bytes, width=card_width)
            else:
                st.caption("Card image unavailable.")
        except Exception:
            st.caption("Card image unavailable.")
        return

    # Normal/full mode: render and cache edited cards.
    # Dual Ornstein & Smough cards need the special dual-boss renderer
    if entry.name == "Ornstein & Smough" and isinstance(sel, str) and "&" in sel:
        img_bytes = render_dual_boss_behavior_card(cfg.raw, sel, boss_name=entry.name)
    else:
        img_path = _behavior_image_path(cfg, sel)
        img_bytes = render_behavior_card_cached(
            img_path,
            beh,
            is_boss=(entry.tier != "enemy"),
        )
        # Apply Priscilla overlay when requested
        priscilla_invis_key = "behavior_viewer_priscilla_invisible"
        # Default False, matching the checkbox in `card_picker` -- the key is
        # absent whenever that checkbox has not been rendered (another enemy
        # selected), and defaulting True drew the invisibility overlay on a card
        # the user never asked for it on.
        if entry.name == "Crossbreed Priscilla" and st.session_state.get(
            priscilla_invis_key, False
        ):
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

    st.image(img_bytes, width=card_width)
