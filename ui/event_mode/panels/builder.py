from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from core import auth
from core.settings_manager import _has_supabase_config, is_streamlit_cloud
from core.image_cache import get_image_bytes_cached
from ui.event_mode.logic import (
    list_all_event_cards,
    load_custom_event_decks,
    save_custom_event_decks,
)


_BUILDER_KEY = "event_mode_builder"
_BUILDER_SYNC_KEY = "event_mode_builder_sync"


def _builder_get() -> Dict[str, Any]:
    b = st.session_state.get(_BUILDER_KEY)
    if isinstance(b, dict):
        b.setdefault("name", "")
        b.setdefault("cards", {})
        return b
    b = {"name": "", "cards": {}, "loaded_from": None}
    st.session_state[_BUILDER_KEY] = b
    return b


def render_deck_builder(*, settings: Dict[str, Any], configs: Dict[str, Any]) -> None:
    """Render the Event Mode Deck Builder panel."""

    custom_decks = load_custom_event_decks()
    names = sorted(custom_decks.keys())

    c1, c2 = st.columns([1.2, 1])

    with c1:
        st.markdown("### Edit / Create")
        pick = st.selectbox(
            "Load custom deck", options=["(new)"] + names, key="event_builder_pick"
        )

        if st.button("Load into editor 📥", width="stretch"):
            b = _builder_get()
            if pick == "(new)":
                b.update({"name": "", "cards": {}, "loaded_from": None})
            else:
                d = custom_decks.get(pick) or {}
                cards = d.get("cards") if isinstance(d, dict) else {}
                b.update({"name": pick, "cards": dict(cards or {}), "loaded_from": pick})
            st.session_state[_BUILDER_KEY] = b
            st.session_state[_BUILDER_SYNC_KEY] = True

        b = _builder_get()
        b_name = st.text_input(
            "Deck name", value=b.get("name", "") or "", key="event_builder_name"
        )
        b["name"] = b_name

    with c2:
        st.markdown("### Deck Summary")
        b = _builder_get()

        cloud_mode = bool(is_streamlit_cloud())
        supabase_ready = bool(_has_supabase_config())
        can_persist = (not cloud_mode) or (supabase_ready and auth.is_authenticated())
        if cloud_mode and not supabase_ready:
            st.caption("Saving is disabled until Supabase is configured.")
        elif cloud_mode and not auth.is_authenticated():
            st.caption("Log in to save.")

        # Build card counts from the live number-input session keys so UI changes
        # immediately enable the Save button without needing a full rerun.
        cards_map: Dict[str, int] = {}
        prefix = "event_builder_copies_all::"
        for key, val in st.session_state.items():
            if not isinstance(key, str) or not key.startswith(prefix):
                continue
            path = key.split("::", 1)[1]
            try:
                copies = int(val or 0)
            except Exception:
                copies = 0
            if copies <= 0:
                continue
            canon = Path(str(path)).as_posix()
            cards_map[canon] = cards_map.get(canon, 0) + copies

        total = sum(int(v or 0) for v in cards_map.values())
        st.markdown(f"**Unique cards:** {len(cards_map)}")
        st.markdown(f"**Total cards:** {total}")

        save_disabled = (not can_persist) or not (b.get("name") and cards_map)

        if st.button("Save custom deck 💾", width="stretch", disabled=save_disabled):
            if not can_persist:
                st.error("Not logged in; cannot persist on Streamlit Cloud.")
                return
            name = str(b["name"]).strip()
            if name:
                custom_decks[name] = {"cards": dict(cards_map)}
                save_custom_event_decks(custom_decks)

                b["loaded_from"] = name
                st.session_state[_BUILDER_KEY] = b
                st.session_state[_BUILDER_SYNC_KEY] = True

                try:
                    st.session_state["event_builder_pick"] = name
                except Exception:
                    pass
                try:
                    st.session_state["event_builder_name"] = name
                except Exception:
                    pass
                st.rerun()

        reset_disabled = not bool(cards_map)
        if st.button("Reset deck 🔄", width="stretch", disabled=reset_disabled):
            prefix = "event_builder_copies_all::"
            for key in list(st.session_state.keys()):
                if isinstance(key, str) and key.startswith(prefix):
                    try:
                        st.session_state[key] = 0
                    except Exception:
                        pass
            b.update({"cards": {}})
            st.session_state[_BUILDER_KEY] = b
            st.session_state[_BUILDER_SYNC_KEY] = True
            st.rerun()

        del_disabled = (not can_persist) or not (
            b.get("loaded_from") and b.get("loaded_from") in custom_decks
        )
        if st.button("Delete loaded deck 🗑️", width="stretch", disabled=del_disabled):
            loaded = b.get("loaded_from")
            if loaded in custom_decks:
                del custom_decks[loaded]
                save_custom_event_decks(custom_decks)

                b.update({"name": "", "cards": {}, "loaded_from": None})
                st.session_state[_BUILDER_KEY] = b
                st.session_state[_BUILDER_SYNC_KEY] = True

                try:
                    st.session_state["event_builder_pick"] = "(new)"
                except Exception:
                    pass
                try:
                    st.session_state["event_builder_name"] = ""
                except Exception:
                    pass

                prefix = "event_builder_copies_all::"
                for key in list(st.session_state.keys()):
                    if isinstance(key, str) and key.startswith(prefix):
                        try:
                            st.session_state[key] = 0
                        except Exception:
                            pass
                st.rerun()

    st.markdown("---")

    search_col, type_col, deck_col = st.columns([1, 1, 1])
    with search_col:
        search = st.text_input("Search card names", value="")
    with type_col:
        type_opts = ["Consumable", "Immediate", "Rendezvous"]
        type_filter = st.multiselect("Card types", options=type_opts, default=type_opts)
    with deck_col:
        show_only_selected = st.checkbox("Show only cards in deck", value=False)

    cards = list_all_event_cards(configs=configs)
    if search.strip():
        s = search.strip().lower()
        cards = [c for c in cards if s in str(c.get("id", "")).lower()]
    if type_filter:
        allowed = set(type_filter)
        cards = [c for c in cards if str(c.get("type") or "") in allowed]
    else:
        cards = []

    b = _builder_get()
    raw_map: Dict[str, Any] = b.get("cards") or {}
    cards_map2: Dict[str, int] = {}
    for k, v in raw_map.items():
        copies = int(v or 0)
        if copies <= 0:
            continue
        canon = Path(str(k)).as_posix()
        cards_map2[canon] = cards_map2.get(canon, 0) + copies

    sync = bool(st.session_state.pop(_BUILDER_SYNC_KEY, False))

    for c in cards:
        img_path = Path(str(c["image_path"])).as_posix()
        if show_only_selected and img_path not in cards_map2:
            continue

        card_id = str(c.get("id", ""))
        exp = str(c.get("expansion", ""))
        event_type = c.get("type")
        text = c.get("text")
        cur = int(cards_map2.get(img_path, 0) or 0)

        key = f"event_builder_copies_all::{img_path}"
        if sync:
            st.session_state[key] = cur
        elif key not in st.session_state:
            st.session_state[key] = cur

        r_img, r_id, r_exp, r_type, r_text, r_copies = st.columns(
            [0.4, 1.4, 1.2, 1.2, 3.1, 1.6]
        )
        with r_img:
            p = Path(img_path)
            img_bytes = get_image_bytes_cached(str(p))
            if img_bytes:
                st.image(img_bytes, width="stretch")
            st.markdown("<div style='height:0.05rem'></div>", unsafe_allow_html=True)
        with r_id:
            st.caption(card_id)
        with r_exp:
            st.caption(exp)
        with r_type:
            st.caption(event_type)
        with r_text:
            if isinstance(text, str) and text.strip():
                st.caption(text)
            else:
                st.caption("—")
        with r_copies:
            v = st.number_input(
                "copies",
                min_value=0,
                max_value=50,
                step=1,
                key=key,
                label_visibility="collapsed",
            )

        v = int(v or 0)
        if v > 0:
            cards_map2[img_path] = v
        else:
            cards_map2.pop(img_path, None)

    b["cards"] = dict(cards_map2)
    st.session_state[_BUILDER_KEY] = b
