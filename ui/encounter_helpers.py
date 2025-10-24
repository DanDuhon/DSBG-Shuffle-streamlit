import base64
from io import BytesIO
import streamlit as st
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
        "enemies": enemies
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
        "enemies": enemies
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
