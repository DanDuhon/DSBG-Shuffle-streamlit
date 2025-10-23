import base64
import streamlit as st
from io import BytesIO
from core.encounters import (
    list_encounters,
    load_encounter,
    pick_random_alternative,
    generate_encounter_image,
    load_valid_sets,
    encounter_is_valid
    )
from core.characters import CHARACTER_EXPANSIONS
from core.settings_manager import load_settings, save_settings
from core.encounterKeywords import encounterKeywords, keywordSize, keywordText
from core.editedEncounterKeywords import editedEncounterKeywords


def render_card(buf, card_img, encounter_name, expansion, use_edited):
    # Card + hotspots + caption
    html = build_encounter_hotspots(buf, card_img, encounter_name, expansion, use_edited)
    st.markdown(html, unsafe_allow_html=True)


def render_original_encounter(encounter_data, selected_expansion, encounter_name, encounter_level, use_edited, enemies=None):
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


def shuffle_encounter(selected_encounter, character_count, active_expansions, selected_expansion, use_edited):
    """
    selected_encounter: dict like {"name": ..., "level": ...}
    character_count: int (1-4)
    active_expansions: list[str]
    selected_expansion: str
    """
    name = selected_encounter["name"]
    level = selected_encounter["level"]
    encounter_slug = f"{selected_expansion}_{level}_{name}"

    encounter_data = load_encounter(encounter_slug, character_count)

    # Pick random enemies
    combo, enemies = pick_random_alternative(encounter_data, set(active_expansions))
    if not combo or not enemies:
        return {"ok": False, "message": "No valid alternatives."}

    # Build card
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
    """
    Returns a single HTML block containing:
      - the card image,
      - optional keyword hotspots.
    """
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    tooltip_css = """
    <style>
    .encounter-container {
        position: relative;
        display: block;
        margin: auto;
        width: 100%;
        max-width: 1200px;   /* Hard cap for very large monitors */
    }
    
    /* For large desktops */
    @media (min-width: 1600px) {
        .encounter-container { max-width: 95%; }
    }

    /* For medium screens (laptops / smaller desktops) */
    @media (min-width: 992px) and (max-width: 1599px) {
        .encounter-container { max-width: 68%; }
    }

    /* For tablets */
    @media (min-width: 768px) and (max-width: 991px) {
        .encounter-container { max-width: 95%; }
    }

    /* For mobile */
    @media (max-width: 767px) {
        .encounter-container { max-width: 100%; }
    }

    .encounter-container img {
        width: 100%;      /* Fill the container */
        height: auto;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .hotspot {
        position: absolute;
        cursor: help;
    }
    .hotspot::after {
        content: attr(data-tooltip);
        position: absolute;
        left: 0;
        top: 100%;
        white-space: normal;
        padding: 6px 8px;
        border-radius: 6px;
        background: #222;
        color: #fff;
        font-size: 14px;
        width: 240px;
        z-index: 9999;
        opacity: 0;
        transition: opacity 0.2s;
        pointer-events: none;
    }
    .hotspot:hover::after {
        opacity: 1;
    }
    </style>
    """

    # Build hotspot spans
    hotspots = []
    if use_edited:
        keywords = editedEncounterKeywords.get((encounter_name, expansion), [])
    else:
        keywords = encounterKeywords.get((encounter_name, expansion), [])

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
            f'<span class="hotspot" style="top:{top_pct}%; left:{left_pct}%; width:{width_pct}%; height:{height_pct}%;" data-tooltip="{text}"></span>'
        )

    hotspots_html = "".join(hotspots)

    html = f"""
    {tooltip_css}
    <div class="encounter-container">
      <img src="data:image/png;base64,{img_b64}" alt="{encounter_name}"/>
      {hotspots_html}
    </div>
    """

    return html


def build_encounter_keywords(encounter_name, expansion, use_edited=False):
    if use_edited:
        keywords = editedEncounterKeywords.get((encounter_name, expansion), [])
    else:
        keywords = encounterKeywords.get((encounter_name, expansion), [])
    return [(kw, keywordText.get(kw, "No description available.")) for kw in keywords]


# --- Initialize Settings ---
if "user_settings" not in st.session_state:
    st.session_state.user_settings = load_settings()

settings = st.session_state.user_settings

st.set_page_config(page_title="DSBG-Shuffle", layout="centered")

# Sidebar
st.sidebar.header("Settings")

# Expansions
all_expansions = [
    "Painted World of Ariamis",
    "The Sunless City",
    "Tomb of Giants",
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep",
    "Characters Expansion",
    "Phantoms",
    "Executioner Chariot",
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
]


with st.sidebar.expander("🧩 Expansions", expanded=False):
    active_expansions = st.multiselect(
        "Active Expansions:",
        all_expansions,
        default=settings.get("active_expansions", []),
        key="active_expansions",
    )
    settings["active_expansions"] = active_expansions

settings["active_expansions"] = active_expansions

# --- Dynamically build character list based on selected expansions ---
available_characters = sorted(
    c for c, exps in CHARACTER_EXPANSIONS.items()
    if any(exp in active_expansions for exp in exps)
)

# Remove invalid selections if expansion changed
previous_selection = settings.get("selected_characters", [])
still_valid_characters = [c for c in previous_selection if c in available_characters]
if len(still_valid_characters) < len(previous_selection):
    removed = [c for c in previous_selection if c not in still_valid_characters]
    st.sidebar.warning(f"Removed invalid characters: {', '.join(removed)}")
    settings["selected_characters"] = still_valid_characters

# === PARTY ===
with st.sidebar.expander("🎭 Party", expanded=False):
    selected_characters = st.multiselect(
        "Selected Characters (max 4):",
        options=available_characters,
        default=settings.get("selected_characters", []),
        max_selections=4,
        key="selected_characters",
    )
    settings["selected_characters"] = selected_characters

# Save updated settings
save_settings(settings)

# --- Validation & Encounter Controls ---
if len(selected_characters) == 0:
    st.warning("⚠️ Select at least one character to continue.")
elif len(selected_characters) > 4:
    st.error("❌ You can only select up to 4 characters.")

valid_party = 0 < len(selected_characters) <= 4
character_count = len(selected_characters)

shuffle_disabled = not valid_party
show_original = False
res = None

# Tabs for major sections
tab_encounters, tab_events, tab_campaign, tab_variants, tab_decks = st.tabs(["Encounters", "Events", "Campaign", "Behavior Variants", "Behavior Decks"])

# ----------------------------
# Encounter Tab
# ----------------------------
with tab_encounters:
    # --- Encounter Selection ---
    encounters_by_expansion = list_encounters()
    if not encounters_by_expansion:
        st.error("No encounters found.")
        st.stop()

    valid_sets = load_valid_sets()

    # Filter expansions that have at least one valid encounter
    filtered_expansions = []
    for expansion_name, encounter_list in encounters_by_expansion.items():
        has_valid = any(
            encounter_is_valid(
                f"{expansion_name}_{e['level']}_{e['name']}",
                character_count,
                tuple(active_expansions),
                valid_sets
            )
            for e in encounter_list
        )
        if has_valid:
            filtered_expansions.append(expansion_name)

    if not filtered_expansions:
        st.error("No valid expansions for the current settings.")
        st.stop()

    # Two columns: card vs controls
    col_controls, col_card = st.columns([1, 2])  # adjust ratio as needed

    with col_controls:
        selected_expansion = st.selectbox(
            "Select Set/Expansion:",
            filtered_expansions,
            index=0,
            disabled=not valid_party
        )

        # Build full encounter keys: "Expansion_Level_Name"
        all_encounters = encounters_by_expansion[selected_expansion]

        filtered_encounters = [
            e for e in all_encounters
            if encounter_is_valid(
                f"{selected_expansion}_{e['level']}_{e['name']}",  # match JSON key pattern
                character_count,
                tuple(active_expansions),
                valid_sets
            )
        ]

        if not filtered_encounters:
            st.warning("No valid encounters for the selected expansions and party size.")
            st.stop()

        display_names = [f"{e['name']} (level {e['level']})" for e in filtered_encounters]
        
        # Encounter selection
        # Default to last encounter if available
        default_label = None
        if "last_encounter" in st.session_state:
            default_label = st.session_state["last_encounter"]["label"]

        selected_label = st.selectbox(
            "Select Encounter:",
            display_names,
            index=display_names.index(default_label) if default_label in display_names else 0,
            key="encounter_dropdown",
            disabled=not valid_party,
        )

        use_edited = st.checkbox("Use Edited Encounter", value=False, key="edited_toggle")

        # Detect if toggle just changed
        toggle_changed = (
            "last_toggle" in st.session_state
            and st.session_state["last_toggle"] != use_edited
        )
        st.session_state["last_toggle"] = use_edited

        # Buttons
        shuffle_clicked = st.button("Shuffle Encounter", use_container_width=True)
        original_clicked = st.button("Show Original Encounter", use_container_width=True)

        if shuffle_clicked and selected_label:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            use_edited = st.session_state.get("edited_toggle", False)
            res = shuffle_encounter(
                selected_encounter,
                character_count,
                active_expansions,
                selected_expansion,
                use_edited
            )
            if res["ok"]:
                st.session_state.current_encounter = res
                # 🔹 Save state
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": f"{selected_expansion}_{selected_encounter['level']}_{selected_encounter['name']}",
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"]
                }
            else:
                st.warning(res["message"])

        if original_clicked and selected_label:
            current = st.session_state.current_encounter
            encounter_slug = f"{current['expansion']}_{current['encounter_level']}_{current['encounter_name']}"

            res = render_original_encounter(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": encounter_slug,
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"]
                }

        if toggle_changed and "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            encounter_slug = f"{current['expansion']}_{current['encounter_level']}_{current['encounter_name']}"

            res = render_original_encounter(
                current["encounter_data"],
                current["expansion"],
                current["encounter_name"],
                current["encounter_level"],
                use_edited,
                enemies=current["enemies"]
            )
            if res:
                st.session_state.current_encounter = res
                st.session_state["last_encounter"] = {
                    "label": selected_label,
                    "slug": encounter_slug,
                    "expansion": selected_expansion,
                    "character_count": character_count,
                    "edited": use_edited,
                    "enemies": res["enemies"]
                }

        # Auto shuffle when changing encounters
        if selected_label and not shuffle_clicked and not original_clicked and not toggle_changed:
            selected_encounter = filtered_encounters[display_names.index(selected_label)]
            use_edited = st.session_state.get("edited_toggle", False)
            res = shuffle_encounter(
                selected_encounter,
                character_count,
                active_expansions,
                selected_expansion,
                use_edited
            )
            if res["ok"]:
                st.session_state.current_encounter = res
            else:
                st.warning(res["message"])

        # Keyword expander
        use_edited = st.session_state.get("edited_toggle", False)
        if "current_encounter" in st.session_state:
            current = st.session_state.current_encounter
            keyword_items = build_encounter_keywords(
                current["encounter_name"],
                current["expansion"],
                use_edited
            )
        else:
            keyword_items = []

        if keyword_items:
            with st.expander("📖 Special Rules Reference", expanded=False):
                for kw in keyword_items:
                    st.markdown(f"{kw[1]}")

    with col_card:
        if "current_encounter" in st.session_state:
            encounter = st.session_state.current_encounter
            use_edited = st.session_state.get("edited_toggle", False)
            render_card(
                encounter["buf"],
                encounter["card_img"],
                encounter["encounter_name"],
                encounter["expansion"],
                use_edited
            )
        elif "last_encounter" in st.session_state:
            st.info(f"Last encounter was {st.session_state['last_encounter']['label']}")
        else:
            st.info("Select an encounter to get started.")

# ----------------------------
# Events Tab
# ----------------------------
with tab_events:
    st.info("Coming soon...")

# ----------------------------
# Campaign Tab
# ----------------------------
with tab_campaign:
    st.info("Coming soon...")

# ----------------------------
# Behavior Variants Tab
# ----------------------------
with tab_variants:
    st.info("Coming soon...")

# ----------------------------
# Behavior Decks Tab
# ----------------------------
with tab_decks:
    st.info("Coming soon...")
