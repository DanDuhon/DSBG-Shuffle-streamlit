import streamlit as st

from core.behavior.assets import _behavior_image_path
from core.behavior.generation import render_behavior_card_cached, render_data_card_cached
from core.behavior.priscilla_overlay import overlay_priscilla_arcs
from ui.campaign_mode.core import _card_w


def try_render_vordt_data_card(*, cfg, state) -> bool:
    if cfg.name != "Vordt of the Boreal Valley":
        return False

    data_path = cfg.display_cards[0] if cfg.display_cards else None
    if not data_path:
        return True

    data_img = render_data_card_cached(data_path, cfg.raw, is_boss=True)

    if state.get("vordt_frostbreath_active", False):
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

            c1, c2 = st.columns(2)
            with c1:
                st.image(data_img, width=_card_w())
            with c2:
                if cfg.name == "Crossbreed Priscilla" and st.session_state.get(
                    "behavior_deck", {}
                ).get("priscilla_invisible", False):
                    frost_img = overlay_priscilla_arcs(
                        frost_img,
                        frost_key,
                        cfg.behaviors.get(frost_key, {}),
                    )
                st.image(frost_img, width=_card_w())
    else:
        st.image(data_img, width=_card_w())

    return True
