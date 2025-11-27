#ui/campaign_tab/generation.py
import streamlit as st
from random import sample, choice
from json import loads
from typing import List, Dict, Any, Union, Literal, Optional

from ui.campaign_tab.models import ProgressNode, Chapter, EncounterChoice, NodeType
from ui.campaign_tab.assets import BOSSES_FILE, EVENTS_SHORTCUTS_FILE, V2_STRUCTURE
from ui.encounters_tab.generation import load_valid_sets, generate_encounter_image, load_encounter
from ui.encounters_tab.logic import shuffle_encounter, list_encounters, encounter_is_valid


Ruleset = Literal["V1", "V2"]


@st.cache_data(show_spinner=False)
def load_events_shortcuts() -> dict:
    if EVENTS_SHORTCUTS_FILE.exists():
        return loads(EVENTS_SHORTCUTS_FILE.read_text("utf-8"))
    return {}


@st.cache_data(show_spinner=False)
def load_bosses() -> Dict[str, Any]:
    if BOSSES_FILE.exists():
        return loads(BOSSES_FILE.read_text("utf-8"))
    return {}


@st.cache_data(show_spinner=False)
def cached_encounter_image(expansion: str, level: int, name: str, enemies: list[int], char_count: int, edited: bool):
    """Cached wrapper that automatically loads encounter data before image generation."""
    encounter_slug = f"{expansion}_{level}_{name}"
    data = load_encounter(encounter_slug, char_count)
    return generate_encounter_image(expansion, level, name, data, enemies, use_edited=edited)


@st.cache_data(show_spinner="Generating campaign...")
def cached_generate_campaign(ruleset: str, expansions: list[str], character_count: int, bosses: dict):
    from ui.campaign_tab.generation import generate_v1_campaign, generate_v2_campaign
    return (
        generate_v1_campaign(expansions, character_count, bosses)
        if ruleset == "V1"
        else generate_v2_campaign(expansions, character_count, bosses)
    )


def _generate_encounter_node(raw: Dict[str, Any], lvl: int, character_count: int, expansions: List[str]) -> ProgressNode:
    res = shuffle_encounter(
        {"name": raw["name"], "level": lvl},
        character_count,
        expansions,
        raw["expansion"],
        st.session_state.user_settings["edited_toggles"].get(f"edited_toggle_{raw['name']}_{raw['expansion']}", False)
    )
    shortcuts = load_events_shortcuts()
    key = f"{raw['expansion']}_{lvl}_{raw['name']}"
    is_shortcut = shortcuts.get(key, {}).get("shortcut", False)

    node = ProgressNode(
        name=raw["name"],
        type="encounter",
        expansion=raw["expansion"],
        level=lvl,
        revealed=False,
        shortcut=is_shortcut
    )
    node.card_img = res["card_img"]
    node.enemies = res["enemies"]

    return node


def generate_v2_campaign(active_expansions: List[str], character_count: int, bosses: Dict[str, Any], randomize_bosses: bool = True) -> List[Chapter]:
    def _choose_boss(boss_type: str):
        candidates = [b for b in bosses.values() if b["type"] == boss_type and any(exp in active_expansions for exp in b["expansions"])]
        if not candidates:
            return None
        chosen = choice(candidates) if randomize_bosses else candidates[0]
        return ProgressNode(name=chosen["name"], type=boss_type, expansion=chosen["expansions"][0], revealed=False)
    

    def pick_two_unique(level: int):
        pool = [e for e in by_level.get(level, []) if e["name"] not in used_encounters]

        # If not enough uniques, allow duplicates or use placeholders
        if len(pool) < 2:
            pool = by_level.get(level, [])
        if len(pool) < 2:
            placeholders = [
                ProgressNode(name=f"Unknown Level {level} Encounter A", type="encounter", level=level),
                ProgressNode(name=f"Unknown Level {level} Encounter B", type="encounter", level=level),
            ]
            return EncounterChoice(options=placeholders, selected=None)

        chosen = sample(pool, 2)
        for c in chosen:
            used_encounters.add(c["name"])
        nodes = [_generate_encounter_node(c, level, character_count, active_expansions) for c in chosen]
        return EncounterChoice(options=nodes, level=level, selected=None)
    
    
    chapters: List[Chapter] = []
    encounters_by_expansion = list_encounters()
    by_level: Dict[int, List[Dict[str, Any]]] = {}
    for _, enc_list in encounters_by_expansion.items():
        for e in enc_list:
            if e["version"] == "V2" or e["level"] == 4:
                by_level.setdefault(e["level"], []).append(e)

    mini = _choose_boss("mini boss")
    main = _choose_boss("main boss")
    mega = _choose_boss("mega boss")

    used_encounters = set()

    for boss in [mini, main, mega]:
        if boss:
            encounters: List[Union[ProgressNode, EncounterChoice]] = []
            for lvl in V2_STRUCTURE[bosses[boss.name]["type"]]:
                encounters.append(pick_two_unique(lvl))
            chapters.append(Chapter(boss=boss, encounters=encounters))

    return chapters


def _collect_valid_encounters(active_expansions: List[str], character_count: int, ruleset: Ruleset) -> Dict[int, List[Dict[str, Any]]]:
    """Return dict of level -> list of valid encounters for the given ruleset."""
    encounters_by_expansion = list_encounters()
    valid_sets = load_valid_sets()
    by_level: Dict[int, List[Dict[str, Any]]] = {}

    for expansion, enc_list in encounters_by_expansion.items():
        for e in enc_list:
            level = e.get("level")
            version = e.get("version")

            # Skip if ruleset doesn't match, unless it's a level 4 encounter
            if level != 4 and version != ruleset:
                continue

            key = f"{expansion}_{level}_{e['name']}"
            if encounter_is_valid(key, character_count, tuple(active_expansions), valid_sets):
                by_level.setdefault(level, []).append({
                    "name": e["name"],
                    "expansion": expansion,
                    "level": level,
                    "version": version,
                })

    return by_level


def generate_v1_campaign(active_expansions: List[str], character_count: int, bosses: Dict[str, Any], randomize_bosses: bool = True) -> List[Chapter]:
    chapters: List[Chapter] = []
    by_level = _collect_valid_encounters(active_expansions, character_count, "V1")

    mini = _choose_boss(bosses, "mini boss", active_expansions, randomize_bosses)
    main = _choose_boss(bosses, "main boss", active_expansions, randomize_bosses)
    mega = _choose_boss(bosses, "mega boss", active_expansions, randomize_bosses)

    used_encounters = set()


    def pick_unique_encounter(lvl: int):
        pool = [e for e in by_level.get(lvl, []) if e["name"] not in used_encounters]
        if not pool:
            return ProgressNode(name=f"Unknown Level {lvl} Encounter", type="encounter", level=lvl, revealed=False)
        chosen = choice(pool)
        used_encounters.add(chosen["name"])

        # Immediately generate image + enemies
        res = shuffle_encounter(
            {"name": chosen["name"], "level": lvl},
            character_count,
            active_expansions,
            chosen["expansion"],
            st.session_state.user_settings["edited_toggles"].get(f"edited_toggle_{chosen['name']}_{chosen['expansion']}", False)
        )
        node = ProgressNode(
            name=chosen["name"],
            type="encounter",
            expansion=chosen["expansion"],
            level=lvl,
            revealed=False,
        )
        node.card_img = res["card_img"]
        node.enemies = res["enemies"]
        return node
    

    for boss in [mini, main, mega]:
        if boss:
            encounters: List[ProgressNode] = []
            for lvl in bosses[boss.name]["encounters"]:
                node = pick_unique_encounter(lvl)
                encounters.append(node)
            chapters.append(Chapter(boss=boss, encounters=encounters))

    return chapters


def _choose_boss(bosses: Dict[str, Any], boss_type: NodeType, active_expansions: List[str], randomize: bool = True) -> Optional[ProgressNode]:
    candidates = [b for b in bosses.values() if b["type"] == boss_type and any(exp in active_expansions for exp in b["expansions"])]
    if not candidates:
        return None
    chosen = choice(candidates) if randomize else candidates[0]
    return ProgressNode(name=chosen["name"], type=boss_type, expansion=chosen["expansions"][0], revealed=False)
