import base64
import re
import streamlit as st
from io import BytesIO
from pathlib import Path
from core.encounters import (
    load_encounter,
    pick_random_alternative,
    generate_encounter_image,
)
from core.encounterKeywords import encounterKeywords, keywordSize, keywordText
from core.editedEncounterKeywords import editedEncounterKeywords


def render_card(buf, card_img, encounter_name, expansion, use_edited):
    """Render a card with hotspots and caption"""
    html = build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited)
    st.markdown(html, unsafe_allow_html=True)


def render_original_encounter(encounter_data, selected_expansion, encounter_name,
                              encounter_level, use_edited, enemies=None):
    """Re-render the original encounter image (not shuffled)"""
    if enemies is None:
        enemies = encounter_data["original"]

    card_img = generate_encounter_image(
        selected_expansion,
        encounter_level,
        encounter_name,
        encounter_data,
        enemies,
        use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")

    return {
        "ok": True,
        "buf": buf,
        "card_img": card_img,
        "encounter_data": encounter_data,
        "encounter_name": encounter_name,
        "encounter_level": encounter_level,
        "expansion": selected_expansion,
        "enemies": enemies,
        "expansions_used": [selected_expansion,]
    }


def apply_edited_toggle(encounter_data, expansion, encounter_name, encounter_level, use_edited, enemies, combo):
    """
    Re-render the encounter card when toggling between edited and original encounters.
    Does not reshuffle enemies — just swaps the encounter card image and keywords.
    """
    # Generate card image (respecting use_edited)
    card_img = generate_encounter_image(
        expansion,
        encounter_level,
        encounter_name,
        encounter_data,
        enemies=enemies,
        use_edited=use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    return {
        "ok": True,
        "encounter_data": encounter_data,
        "expansion": expansion,
        "encounter_name": encounter_name,
        "encounter_level": encounter_level,
        "enemies": enemies,
        "card_img": card_img,
        "buf": buf,
        "expansions_used": combo
    }


def shuffle_encounter(selected_encounter, character_count, active_expansions,
                      selected_expansion, use_edited):
    """Shuffle and generate a randomized encounter"""
    name = selected_encounter["name"]
    level = selected_encounter["level"]
    encounter_slug = f"{selected_expansion}_{level}_{name}"

    encounter_data = load_encounter(encounter_slug, character_count)

    # Pick random enemies
    combo, enemies = pick_random_alternative(encounter_data, set(active_expansions))
    if not combo or not enemies:
        return {"ok": False, "message": "No valid alternatives."}

    card_img = generate_encounter_image(
        selected_expansion,
        level,
        name,
        encounter_data,
        enemies,
        use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")

    return {
        "ok": True,
        "buf": buf,
        "card_img": card_img,
        "encounter_data": encounter_data,
        "encounter_name": name,
        "encounter_level": level,
        "expansion": selected_expansion,
        "enemies": enemies,
        "expansions_used": combo.split(",") if type(combo) == str else combo
    }


def build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited):
    """Return HTML block for card image + keyword hotspots"""
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    tooltip_css = """
    <style>
    .encounter-container { position: relative; display: block; margin: auto; width: 100%; max-width: 1200px; }
    @media (min-width: 1600px) { .encounter-container { max-width: 95%; } }
    @media (min-width: 992px) and (max-width: 1599px) { .encounter-container { max-width: 68%; } }
    @media (min-width: 768px) and (max-width: 991px) { .encounter-container { max-width: 95%; } }
    @media (max-width: 767px) { .encounter-container { max-width: 100%; } }
    .encounter-container img { width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); }
    .hotspot { position: absolute; cursor: help; }
    .hotspot::after { content: attr(data-tooltip); position: absolute; left: 0; top: 100%;
        white-space: normal; padding: 6px 8px; border-radius: 6px; background: #222; color: #fff;
        font-size: 14px; width: 240px; z-index: 9999; opacity: 0; transition: opacity 0.2s; pointer-events: none; }
    .hotspot:hover::after { opacity: 1; }
    </style>
    """

    # Get keywords
    if use_edited:
        keywords = editedEncounterKeywords.get((encounter_name, expansion), [])
    else:
        keywords = encounterKeywords.get((encounter_name, expansion), [])

    hotspots = []
    for i, keyword in enumerate(keywords):
        if keyword not in keywordSize:
            continue
        w, h = keywordSize[keyword]
        x, y = 282, 400 + (32 * i)
        left_pct = 100 * x / card_img.size[0]
        top_pct = 100 * y / card_img.size[1]
        width_pct = 100 * w / card_img.size[0]
        height_pct = 100 * h / card_img.size[1]
        text = keywordText.get(keyword, "No description available.")
        hotspots.append(
            f'<span class="hotspot" style="top:{top_pct}%; left:{left_pct}%; '
            f'width:{width_pct}%; height:{height_pct}%;" data-tooltip="{text}"></span>'
        )

    hotspots_html = "".join(hotspots)
    return f"""{tooltip_css}
    <div class="encounter-container">
      <img src="data:image/png;base64,{img_b64}" alt="{encounter_name}"/>
      {hotspots_html}
    </div>
    """


def build_encounter_keywords(encounter_name, expansion, use_edited=False):
    """Return list of (keyword, description)"""
    if use_edited:
        keywords = editedEncounterKeywords.get((encounter_name, expansion), [])
    else:
        keywords = encounterKeywords.get((encounter_name, expansion), [])
    return [(kw, keywordText.get(kw, "No description available.")) for kw in keywords]


def _img_tag_from_path(path: Path, title: str, height_px: int = 30, extra_css: str = "") -> str:
    """
    Safely embed an image file as a base64 data URI for Streamlit's HTML.
    Returns an <img> tag or an empty string if the file doesn't exist.
    """
    try:
        if not path.exists():
            return ""
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        # Don't set explicit width; let it scale from height to preserve aspect
        return (
            f"<img src='data:image/png;base64,{b64}' "
            f"title='{title}' alt='{title}' "
            f"style='height:{height_px}px; {extra_css}'/>"
        )
    except Exception:
        # If anything fails, just return empty so we can fallback to a placeholder
        return ""


def render_encounter_icons(current_encounter, assets_dir="assets"):
    """
    Render party and the expansions actually used in the current encounter
    (icons embedded as base64 so they display in Streamlit).
    Includes special rules for Dark Souls The Board Game vs Sunless City.
    """
    chars_dir = Path(assets_dir) / "characters"
    exps_dir  = Path(assets_dir) / "expansions"

    html = """
    <style>
      .icons-section h4 { margin: 0.75rem 0 0.25rem 0; }
      .icons-row { display:flex; gap:6px; flex-wrap:nowrap; overflow-x:auto; padding-bottom:2px; }
      .icons-row::-webkit-scrollbar { height: 6px; }
      .icons-row::-webkit-scrollbar-thumb { background: #bbb; border-radius: 3px; }
      .icons-grid { display:grid; grid-template-columns: repeat(6, 1fr); gap:6px; }
      .icon-fallback {
        height:48px; background:#ccc; border-radius:6px;
        display:flex; align-items:center; justify-content:center;
        font-size:10px; text-align:center; padding:2px;
      }
    </style>
    <div class="icons-section">
    """

    # --- PARTY (single row) ---
    characters = st.session_state.user_settings.get("selected_characters", [])
    if characters:
        html += "<h5>Party</h5><div class='icons-row'>"
        for char in characters:
            fname = f"{char}.png"
            tag = _img_tag_from_path(chars_dir / fname, title=char, extra_css="border-radius:6px;")
            if tag:
                html += tag
            else:
                # 1-letter fallback
                initial = (char or "?")[0:1]
                html += f"<div class='icon-fallback' title='{char}'>{initial}</div>"
        html += "</div>"

    # --- EXPANSIONS IN USE (grid of 6) ---
    enemies = current_encounter["enemies"]
    expansions_used = list(current_encounter.get("expansions_used", []))  # make a copy
    icons = []
    html += "<h5>Expansions Needed</h5><div class='icons-grid'>"

    enemy_ids = set([e["name"] if isinstance(e, dict) else e for e in enemies])

    # --- Special combined rules ---
    if any(exp in current_encounter["expansions_used"] for exp in ["Dark Souls The Board Game", "The Sunless City"]):
        if 16 not in enemy_ids and 34 not in enemy_ids:
            icons.append({"file": "Dark Souls The Board Game The Sunless City.png",
                            "label": "Dark Souls The Board Game / The Sunless City"})
            # strip out the originals, but from our copy only
            expansions_used = [exp for exp in expansions_used if exp not in ["Dark Souls The Board Game", "The Sunless City"]]
        else:
            if 16 in enemy_ids: # Large Hollow Soldier
                icons.append({"file": "Dark Souls The Board Game.png", "label": "Dark Souls The Board Game"})
            if 34 in enemy_ids: # Mimic
                icons.append({"file": "The Sunless City.png", "label": "The Sunless City"})

        # --- All other expansions normal ---
        for exp in [exp for exp in current_encounter["expansions_used"] if exp not in {"Dark Souls The Board Game", "The Sunless City"}]:
            icons.append({"file": f"{exp}.png", "label": exp})
    else:
        for exp in current_encounter["expansions_used"]:
            icons.append({"file": f"{exp}.png", "label": exp})

    # --- Render unique icons ---
    seen = set()
    for icon in icons:
        fname, label = icon["file"], icon["label"]
        if fname in seen:
            continue
        seen.add(fname)

        tag = _img_tag_from_path(exps_dir / fname, title=label,
                                    extra_css="object-fit:contain; border-radius:6px;")
        if tag:
            html += tag
        else:
            html += f"<div class='icon-fallback' title='{label}'>{label}</div>"

    html += "</div>"

    return html
