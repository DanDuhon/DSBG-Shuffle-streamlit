from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import json
import base64
import random
import streamlit as st

from ui.encounters_tab.logic import (
    _list_encounters_cached,
    _load_valid_sets_cached,
    filter_expansions,
    filter_encounters,
    shuffle_encounter,
)
from ui.encounters_tab.generation import generate_encounter_image
from ui.encounters_tab.render import render_original_encounter
from ui.behavior_decks_tab.assets import BEHAVIOR_CARDS_PATH
from ui.behavior_decks_tab.generation import (
    render_data_card_cached,
    render_dual_boss_data_cards,
)


DATA_DIR = Path("data")
BOSSES_PATH = DATA_DIR / "bosses.json"
INVADERS_PATH = DATA_DIR / "invaders.json"
CAMPAIGNS_PATH = DATA_DIR / "campaigns.json"

ASSETS_DIR = Path("assets")
PARTY_TOKEN_PATH = ASSETS_DIR / "party_token.png"
BONFIRE_ICON_PATH = ASSETS_DIR / "bonfire.gif"
CHARACTERS_DIR = ASSETS_DIR / "characters"


def _load_json_object(path: Path) -> Dict[str, Any]:
    """Load a JSON object from path. Raise if malformed; return {} if missing."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def _load_campaigns() -> Dict[str, Any]:
    """Load all saved campaigns as a mapping name -> payload."""
    if not CAMPAIGNS_PATH.exists():
        return {}
    with CAMPAIGNS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    raise ValueError(f"Expected JSON object in {CAMPAIGNS_PATH}, got {type(data).__name__}")


def _save_campaigns(campaigns: Dict[str, Any]) -> None:
    CAMPAIGNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CAMPAIGNS_PATH.open("w", encoding="utf-8") as f:
        json.dump(campaigns, f, indent=2, sort_keys=True)


def _get_settings() -> Dict[str, Any]:
    settings = st.session_state.get("user_settings")
    if settings is None:
        settings = {}
        st.session_state["user_settings"] = settings
    return settings


def _get_player_count(settings: Dict[str, Any]) -> int:
    selected_chars = settings.get("selected_characters")
    if isinstance(selected_chars, list) and selected_chars:
        return max(1, len(selected_chars))
    raw = st.session_state.get("player_count", 1)
    try:
        return max(1, int(raw))
    except Exception:
        return 1


def _default_sparks_max(player_count: int) -> int:
    # Campaign rule: party starts with (6 - player_num) sparks, clamped to at least 1.
    return max(1, 6 - player_count)


def _img_tag_from_path(
    path: Path,
    title: str = "",
    height_px: int = 48,
    extra_css: str = "",
) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except Exception:
        return None
    b64 = base64.b64encode(data).decode("ascii")
    style = f"height:{height_px}px; {extra_css}".strip()
    style_attr = f" style='{style}'" if style else ""
    title_attr = f" title='{title}'" if title else ""
    return f"<img src='data:image/png;base64,{b64}'{title_attr}{style_attr} />"


def _render_party_icons(settings: Dict[str, Any]) -> None:
    characters = settings.get("selected_characters") or []
    if not characters:
        return

    chars_dir = CHARACTERS_DIR

    html = """
    <style>
      .campaign-party-section h5 { margin: 0.75rem 0 0.25rem 0; }
      .campaign-party-row {
        display:flex;
        gap:6px;
        flex-wrap:nowrap;
        overflow-x:auto;
        padding-bottom:2px;
      }
      .campaign-party-row::-webkit-scrollbar { height: 6px; }
      .campaign-party-row::-webkit-scrollbar-thumb {
        background: #bbb;
        border-radius: 3px;
      }
      .campaign-party-fallback {
        height:48px;
        background:#ccc;
        border-radius:6px;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:10px;
        text-align:center;
        padding:2px;
      }
    </style>
    <div class="campaign-party-section">
    <h5>Party</h5>
    <div class="campaign-party-row">
    """

    for char in characters:
        fname = f"{char}.png"
        tag = _img_tag_from_path(
            chars_dir / fname,
            title=str(char),
            extra_css="border-radius:6px;",
        )
        if tag:
            html += tag
        else:
            initial = (str(char) or "?")[0:1]
            html += (
                f"<div class='campaign-party-fallback' title='{char}'>"
                f"{initial}</div>"
            )

    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)


def _filter_bosses(
    bosses: Dict[str, Any],
    *,
    boss_type: str,
    active_expansions: List[str],
) -> List[Dict[str, Any]]:
    active = set(active_expansions or [])
    out: List[Dict[str, Any]] = []

    for _name, cfg in bosses.items():
        if cfg.get("type") != boss_type:
            continue
        exp_list = cfg.get("expansions") or []
        if exp_list:
            if not set(exp_list).issubset(active):
                continue
        out.append(cfg)

    out.sort(key=lambda c: str(c.get("name", "")))
    return out


def _resolve_v1_bosses_for_campaign(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Resolve mini/main/mega boss names for this campaign.

    - Respects 'Random' / 'None' selections in state["bosses"].
    - Limits choices to bosses whose expansions are all active.
    - Returns a dict like:
        {
            "mini": {"name": "Gargoyle", "was_random": True},
            "main": {"name": "Artorias", "was_random": False},
            "mega": {"name": "Black Dragon Kalameet", "was_random": True},
        }
      where 'name' can be None for mega if the slot is disabled.
    """
    active_expansions = settings.get("active_expansions") or []
    if not active_expansions:
        raise ValueError("No active expansions enabled; cannot generate a campaign.")

    bosses_state = state.get("bosses") or {}
    result: Dict[str, Dict[str, Any]] = {}

    for slot, boss_type in (("mini", "mini boss"), ("main", "main boss"), ("mega", "mega boss")):
        sel = bosses_state.get(slot)

        # Mega boss can be explicitly disabled
        if slot == "mega" and (sel is None or sel == "None"):
            result[slot] = {"name": None, "was_random": False}
            continue

        filtered = _filter_bosses(
            bosses_by_name,
            boss_type=boss_type,
            active_expansions=active_expansions,
        )
        if not filtered:
            raise ValueError(f"No {boss_type} options available for campaign generation.")

        if not sel or sel == "Random":
            cfg = random.choice(filtered)
            name = cfg.get("name")
            if not name:
                raise ValueError(f"{boss_type!r} entry missing name in bosses.json.")
            result[slot] = {"name": name, "was_random": True}
        else:
            name = sel
            valid_names = {b.get("name") for b in filtered}
            if name not in valid_names:
                raise ValueError(
                    f"Selected {boss_type} '{name}' is not valid for current expansions."
                )
            result[slot] = {"name": name, "was_random": False}

    return result


def _is_v1_campaign_eligible(encounter: Dict[str, Any]) -> bool:
    """
    V1 campaign rule:
    - Only V1 encounters (by the 'version' field coming from _list_encounters_cached)
    - Level 4 encounters are treated as both V1 and V2, so they are always allowed.
    """
    level = int(encounter["level"])
    
    # Level 4 is allowed for both V1 and V2 campaigns
    if level == 4:
        return True

    version = str(encounter.get("version", "")).upper()
    if version.startswith("V1"):
        return True

    # Be permissive if version is missing/blank
    if version == "":
        return True

    return False


def _pick_random_campaign_encounter(
    *,
    encounters_by_expansion: Dict[str, List[Dict[str, Any]]],
    valid_sets: Dict[str, Any],
    character_count: int,
    active_expansions: List[str],
    level: int,
) -> Dict[str, Any]:
    """
    Pick and freeze a single encounter at the given level, using the same
    filtering pipeline Encounter Mode uses, then shuffle enemies once.

    Returns a JSON-serializable dict:
        {
            "expansion": ...,
            "encounter_level": ...,
            "encounter_name": ...,
            "enemies": [...],
            "expansions_used": [...],
        }
    """
    filtered_expansions = filter_expansions(
        encounters_by_expansion,
        character_count,
        tuple(active_expansions),
        valid_sets,
    )
    if not filtered_expansions:
        raise ValueError("No valid encounter sets available for campaign generation.")

    level_int = int(level)

    # Build (expansion, [level-matching encounters]) pairs up front
    candidate_expansions: list[tuple[str, list[Dict[str, Any]]]] = []

    for exp_choice in filtered_expansions:
        all_encounters = encounters_by_expansion[exp_choice]

        filtered_encounters = filter_encounters(
            all_encounters,
            exp_choice,
            character_count,
            tuple(active_expansions),
            valid_sets,
        )
        if not filtered_encounters:
            # This expansion has no valid encounters at all under current settings.
            continue

        level_candidates: List[Dict[str, Any]] = []
        for e in filtered_encounters:
            try:
                lvl = int(e.get("level", -1))
            except Exception:
                continue
            if lvl != level_int:
                continue
            # V1 campaign: only V1 encounters, except level 4 which is allowed for both
            if not _is_v1_campaign_eligible(e):
                continue
            level_candidates.append(e)

        if level_candidates:
            candidate_expansions.append((exp_choice, level_candidates))

    if not candidate_expansions:
        raise ValueError(
            f"No valid level {level_int} encounters in any expansion "
            "for current party/expansion settings."
        )

    # Now pick a random expansion that actually has level-matching encounters
    exp_choice, level_candidates = random.choice(candidate_expansions)
    base_enc = random.choice(level_candidates)

    res = shuffle_encounter(
        base_enc,
        character_count,
        active_expansions,
        exp_choice,
        use_edited=False,
    )
    if not res.get("ok"):
        raise RuntimeError(
            f"Failed to build campaign encounter '{base_enc.get('name')}' "
            f"({exp_choice}, level {level_int})."
        )

    frozen = {
        "expansion": res.get("expansion", exp_choice),
        "encounter_level": res.get("encounter_level", level_int),
        "encounter_name": res.get("encounter_name") or base_enc.get("name"),
        "enemies": res.get("enemies") or [],
        "expansions_used": res.get("expansions_used") or [],
        # critical: keep the processed encounter_data so cards render correctly
        "encounter_data": res.get("encounter_data"),
        "edited": bool(res.get("edited", False)),
    }
    return frozen


def _generate_v1_campaign(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a full V1 campaign track:

    - Bonfire
    - Pre-mini encounters -> Mini boss
    - Pre-main encounters -> Main boss
    - Optional pre-mega encounters -> Mega boss

    All encounters are fully frozen (enemy lists chosen once).
    The structure is JSON-serializable so it can be saved to disk.
    """
    player_count = _get_player_count(settings)
    active_expansions = settings.get("active_expansions") or []

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        raise ValueError("No encounters available to generate a campaign.")

    valid_sets = _load_valid_sets_cached()
    resolved_bosses = _resolve_v1_bosses_for_campaign(bosses_by_name, settings, state)

    campaign: Dict[str, Any] = {
        "player_count": player_count,
        "bosses": resolved_bosses,
        "nodes": [],
        "current_node_id": "bonfire",
    }
    nodes: List[Dict[str, Any]] = campaign["nodes"]
    nodes.append({"id": "bonfire", "kind": "bonfire"})

    def _add_stage(stage_key: str, boss_name: Optional[str]) -> None:
        if not boss_name:
            return

        cfg = bosses_by_name.get(boss_name)
        if not cfg:
            raise ValueError(f"Unknown boss '{boss_name}' in bosses.json.")

        levels = cfg.get("encounters") or []
        if not isinstance(levels, list) or not levels:
            return

        for idx, lvl in enumerate(levels):
            try:
                lvl_int = int(lvl)
            except Exception as exc:
                raise ValueError(
                    f"Invalid encounter level '{lvl}' for boss '{boss_name}'."
                ) from exc

            frozen = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
            )

            nodes.append(
                {
                    "id": f"encounter:{stage_key}:{idx}",
                    "kind": "encounter",
                    "stage": stage_key,  # "mini" | "main" | "mega"
                    "index": idx,
                    "level": lvl_int,
                    "frozen": frozen,
                    "status": "locked",
                    "revealed": False,
                }
            )

        boss_info = resolved_bosses[stage_key]
        nodes.append(
            {
                "id": f"boss:{stage_key}",
                "kind": "boss",
                "stage": stage_key,
                "boss_name": boss_name,
                "was_random": bool(boss_info.get("was_random")),
                "status": "locked",
                "revealed": False,
            }
        )

    # Order: mini track, main track, optional mega track
    _add_stage("mini", resolved_bosses["mini"]["name"])
    _add_stage("main", resolved_bosses["main"]["name"])

    mega_name = resolved_bosses.get("mega", {}).get("name")
    if mega_name:
        _add_stage("mega", mega_name)

    return campaign


def _describe_v1_node_label(campaign: Dict[str, Any], node: Dict[str, Any]) -> str:
    """
    Human-readable label for a campaign node.

    - Encounters: "Unknown Level X Encounter" until revealed, then show name.
    - Random bosses: "Unknown Mini/Main/Mega Boss" until revealed.
    - Fixed bosses: show their name immediately.
    """
    kind = node.get("kind")
    if kind == "bonfire":
        return "Bonfire"

    if kind == "encounter":
        level = node.get("level")
        frozen = node.get("frozen") or {}
        name = frozen.get("encounter_name")
        revealed = bool(node.get("revealed"))
        if revealed and name:
            return f"Level {level} Encounter: {name}"
        return f"Unknown Level {level} Encounter"

    if kind == "boss":
        stage = node.get("stage")
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name")
        was_random = bool(bosses_info.get("was_random"))
        revealed = bool(node.get("revealed")) or (boss_name and not was_random)

        prefix_map = {
            "mini": "Mini Boss",
            "main": "Main Boss",
            "mega": "Mega Boss",
        }
        prefix = prefix_map.get(stage, "Boss")

        if not boss_name:
            return f"{prefix}: None"

        if was_random and not revealed:
            if stage == "mini":
                return "Unknown Mini Boss"
            if stage == "main":
                return "Unknown Main Boss"
            if stage == "mega":
                return "Unknown Mega Boss"

        return f"{prefix}: {boss_name}"

    return "Unknown node"


def _render_v1_encounter_card(frozen: Dict[str, Any]) -> None:
    """
    Render the encounter card for a frozen campaign encounter, using
    the shuffled enemies stored in the frozen payload.
    """
    expansion = frozen.get("expansion")
    level = frozen.get("encounter_level")
    name = frozen.get("encounter_name")
    enemies = frozen.get("enemies") or []

    if not expansion or level is None or not name:
        st.caption("Encounter card data incomplete.")
        return

    encounters_by_expansion = _list_encounters_cached()
    base_list = encounters_by_expansion.get(expansion)
    if not base_list:
        st.warning(f"No encounter data found for expansion '{expansion}'.")
        return

    level_int = int(level)
    base_enc = None
    for e in base_list:
        try:
            if e.get("name") == name and int(e.get("level", -1)) == level_int:
                base_enc = e
                break
        except Exception:
            continue

    if base_enc is None:
        st.warning(
            f"Could not locate original encounter '{name}' (level {level_int}) "
            f"in expansion '{expansion}'."
        )
        return

    # Critical part: pass the frozen shuffled enemies into the generator.
    card_img = generate_encounter_image(
        expansion,
        level_int,
        name,
        base_enc,
        enemies,
        False,  # use_edited
    )
    
    st.image(card_img, width="stretch")


def _render_v1_current_panel(
    campaign: Dict[str, Any],
    current_node: Dict[str, Any],
) -> None:
    """
    Right-hand panel for V1:
    - Bonfire: bonfire image
    - Encounter: card + 'Start Encounter'
    - Boss: fully rendered data card + 'Start Boss Fight' (jumps to Boss Mode)
    """
    kind = current_node.get("kind")
    st.markdown("#### Current space")

    # Bonfire
    if kind == "bonfire":
        st.caption("Resting at the bonfire.")
        return

    # Encounter
    if kind == "encounter":
        frozen = current_node.get("frozen") or {}
        level = frozen.get("encounter_level")
        name = frozen.get("encounter_name") or "Unknown Encounter"
        expansion = frozen.get("expansion") or "Unknown Expansion"
        encounter_data = frozen.get("encounter_data")
        enemies = frozen.get("enemies") or []
        use_edited = bool(frozen.get("edited", False))

        st.markdown(f"**Level {level} Encounter**")
        st.caption(f"{name} ({expansion})")

        if not encounter_data:
            st.warning("Missing encounter data; regenerate this campaign.")
        else:
            res = render_original_encounter(
                encounter_data,
                expansion,
                name,
                level,
                use_edited,
                enemies=enemies,
            )
            if res and res.get("ok"):
                st.image(res["card_img"], width="stretch")
            else:
                st.warning("Failed to render encounter card.")

        if st.button(
            "Start Encounter",
            key=f"campaign_v1_start_enc_{current_node.get('id')}",
        ):
            st.info("Encounter play not wired yet; use Encounter Mode for now.")
        return

    # Boss
    if kind == "boss":
        stage = current_node.get("stage")
        # Prefer the campaign's boss metadata, fall back to node field
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name") or current_node.get("boss_name")

        prefix_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
        prefix = prefix_map.get(stage, "Boss")

        if boss_name:
            st.markdown(f"**{prefix}: {boss_name}**")

            # Load raw behavior JSON directly
            json_path = Path("data") / "behaviors" / f"{boss_name}.json"
            raw_data = None
            if json_path.is_file():
                try:
                    with json_path.open("r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                except Exception as exc:
                    st.warning(f"Failed to load behavior JSON for '{boss_name}': {exc}")

            if raw_data is None:
                # Fallback: show static base data card
                data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                st.image(data_path, width="stretch")
            else:
                # Special case: Ornstein & Smough dual-boss card
                if "Ornstein" in boss_name and "Smough" in boss_name:
                    try:
                        o_img, s_img = render_dual_boss_data_cards(raw_data)
                        o_col, s_col = st.columns(2)
                        with o_col:
                            st.image(o_img, width="stretch")
                        with s_col:
                            st.image(s_img, width="stretch")
                    except Exception as exc:
                        st.warning(f"Failed to render Ornstein & Smough data cards: {exc}")
                else:
                    if boss_name == "Executioner's Chariot":
                        data_path = BEHAVIOR_CARDS_PATH + "Executioner's Chariot - Skeletal Horse.jpg"
                    else:
                        data_path = BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg"
                    try:
                        img = render_data_card_cached(
                            data_path,
                            raw_data,
                            is_boss=True,
                        )
                        st.image(img, width="stretch")
                    except Exception as exc:
                        st.warning(f"Failed to render boss data card: {exc}")
        else:
            st.markdown(f"**{prefix}: Unknown**")
            st.caption("No boss selected for this space.")

        if st.button(
            "Start Boss Fight",
            key=f"campaign_v1_start_boss_{current_node.get('id')}",
        ):
            if not boss_name:
                st.warning("No boss configured for this node.")
            else:
                st.session_state["pending_boss_mode_from_campaign"] = {
                    "boss_name": boss_name
                }
                st.rerun()
        return

    st.caption("No details available for this space.")


def _render_v1_path_row(
    node: Dict[str, Any],
    campaign: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    label = _describe_v1_node_label(campaign, node)
    row_cols = st.columns([3, 1])

    with row_cols[0]:
        st.markdown(f"- {label}")

    with row_cols[1]:
        node_id = node.get("id")
        kind = node.get("kind")
        is_current = node_id == campaign.get("current_node_id")

        # Current location: show party token instead of any button
        if is_current:
            st.image(str(PARTY_TOKEN_PATH), width=48)
            return

        # Bonfire row: Return to Bonfire
        if kind == "bonfire":
            if st.button(
                "Return to Bonfire",
                key=f"campaign_v1_goto_{node_id}",
            ):
                campaign["current_node_id"] = node_id
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                st.rerun()
            return

        # Encounter / boss: Travel / Confront
        if kind in ("encounter", "boss"):
            btn_label = "Travel" if kind == "encounter" else "Confront"
            if st.button(btn_label, key=f"campaign_v1_goto_{node_id}"):
                campaign["current_node_id"] = node_id
                node["revealed"] = True
                state["campaign"] = campaign
                st.session_state["campaign_v1_state"] = state
                st.rerun()
            return


def _render_v1_play(state: Dict[str, Any], bosses_by_name: Dict[str, Any]) -> None:
    """
    V1 Play tab:

    - Party icons at top
    - Sparks (display only)
    - Soul cache numeric input under Sparks
    - Path with Return to Bonfire / Travel / Confront
    - Party token on the current row
    - Right-hand panel with bonfire / encounter card / boss card
    """
    settings = _get_settings()

    campaign = state.get("campaign")
    if not isinstance(campaign, dict):
        st.info("Generate a V1 campaign in the Setup tab to begin.")
        return

    nodes = campaign.get("nodes") or []
    if not nodes:
        st.info("Campaign has no nodes; regenerate it from the Setup tab.")
        return

    # Resolve current node
    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id", "bonfire")
    current_node = node_by_id.get(current_id) or nodes[0]
    campaign["current_node_id"] = current_node.get("id", "bonfire")
    state["campaign"] = campaign

    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        col_bonfire, col_info = st.columns([1, 2])

        with col_bonfire:
            st.image(str(BONFIRE_ICON_PATH), width="stretch")

        with col_info:
            # Party icons above everything
            _render_party_icons(settings)

            # Sparks: display only
            player_count = _get_player_count(settings)
            sparks_max = int(state.get("sparks_max", _default_sparks_max(player_count)))
            sparks_cur = int(state.get("sparks", sparks_max))
            st.metric("Sparks", f"{sparks_cur} / {sparks_max}")

            # Soul cache directly under Sparks; no extra +/- buttons
            souls_value = st.number_input(
                "Soul cache",
                min_value=0,
                value=int(state.get("souls", 0)),
                step=1,
                key="campaign_v1_souls_play",
            )
            state["souls"] = int(souls_value)

        st.markdown("---")
        st.markdown(
            f"**Current location:** "
            f"{_describe_v1_node_label(campaign, current_node)}"
        )

        st.markdown("#### Path")

        # Group nodes: bonfire, then chapters by stage, then any leftovers
        bonfire_nodes: List[Dict[str, Any]] = []
        stage_nodes: Dict[str, List[Dict[str, Any]]] = {
            "mini": [],
            "main": [],
            "mega": [],
        }
        other_nodes: List[Dict[str, Any]] = []

        for node in nodes:
            kind = node.get("kind")
            stage = node.get("stage")
            if kind == "bonfire":
                bonfire_nodes.append(node)
            elif stage in stage_nodes:
                stage_nodes[stage].append(node)
            else:
                other_nodes.append(node)

        # Bonfire stays at the top, outside any chapter
        for n in bonfire_nodes:
            _render_v1_path_row(n, campaign, state)

        mini_boss = stage_nodes["mini"][-1]
        main_boss = stage_nodes["main"][-1]
        mega_boss = [] if not stage_nodes["mega"] else stage_nodes["mega"][-1]

        chapter_labels = {
            "mini": "Unknown Mini Boss Chapter" if mini_boss["was_random"] and not mini_boss["revealed"] else f"{mini_boss['boss_name']} Chapter",
            "main": "Unknown Main Boss Chapter" if main_boss["was_random"] and not main_boss["revealed"] else f"{main_boss['boss_name']} Chapter",
        }

        if mega_boss:
            chapter_labels["mega"] = "Unknown Mega Boss Chapter" if mega_boss["was_random"] and not mega_boss["revealed"] else f"{mega_boss['boss_name']} Chapter"

        # Wrap mini/main/mega tracks in expanders
        for stage in ("mini", "main", "mega"):
            nodes_for_stage = stage_nodes.get(stage) or []
            if not nodes_for_stage:
                continue
            with st.expander(chapter_labels[stage], expanded=True):
                for n in nodes_for_stage:
                    _render_v1_path_row(n, campaign, state)

        # Any nodes that don't belong to the known stages
        for n in other_nodes:
            _render_v1_path_row(n, campaign, state)

    with col_detail:
        _render_v1_current_panel(campaign, current_node)

    # Persist updated state
    st.session_state["campaign_v1_state"] = state


def _ensure_v1_state(player_count: int) -> Dict[str, Any]:
    key = "campaign_v1_state"
    state = st.session_state.get(key)
    if not isinstance(state, dict):
        state = {}

    state.setdefault(
        "bosses",
        {
            "mini": "Random",  # "Random" or concrete boss name
            "main": "Random",
            "mega": "None",    # "None", "Random", or concrete boss name
        },
    )

    state.setdefault("souls", 0)

    sparks_max = _default_sparks_max(player_count)
    prev_max = state.get("sparks_max")
    prev_current = state.get("sparks")

    state["sparks_max"] = sparks_max
    if prev_current is None or prev_max is None:
        state["sparks"] = sparks_max
    else:
        state["sparks"] = min(int(prev_current), sparks_max)

    st.session_state[key] = state
    return state


def _render_setup_header(settings: Dict[str, Any]) -> tuple[str, int]:
    player_count = _get_player_count(settings)
    options = ["V1", "V2"]
    current = st.session_state.get("campaign_rules_version", "V1")
    if current not in options:
        current = "V1"
    index = options.index(current)

    # Widget uses a different key so we can freely mutate campaign_rules_version
    version = st.radio(
        "Rules version",
        options=options,
        index=index,
        horizontal=True,
        key="campaign_rules_version_widget",
    )

    # This is now safe; no widget with this key exists
    st.session_state["campaign_rules_version"] = version

    st.markdown("---")
    return version, player_count


def _render_v1_setup(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    player_count: int,
) -> Dict[str, Any]:
    state = _ensure_v1_state(player_count)
    active_expansions = settings.get("active_expansions") or []

    mini_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mini boss",
        active_expansions=active_expansions,
    )
    main_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="main boss",
        active_expansions=active_expansions,
    )
    mega_bosses = _filter_bosses(
        bosses_by_name,
        boss_type="mega boss",
        active_expansions=active_expansions,
    )

    cols = st.columns(3)

    # Mini boss
    with cols[0]:
        st.markdown("**Mini Boss**")
        if not mini_bosses:
            st.caption("No mini bosses available with current expansions.")
            state["bosses"]["mini"] = "Random"
        else:
            mini_names = [b["name"] for b in mini_bosses]
            mini_options = ["Random"] + mini_names
            current = state["bosses"].get("mini", "Random")
            if current not in mini_options:
                current = "Random"
            mini_choice = st.selectbox(
                "Mini boss",
                options=mini_options,
                index=mini_options.index(current),
                key="campaign_v1_mini_boss",
            )
            state["bosses"]["mini"] = mini_choice

    # Main boss
    with cols[1]:
        st.markdown("**Main Boss**")
        if not main_bosses:
            st.caption("No main bosses available with current expansions.")
            state["bosses"]["main"] = "Random"
        else:
            main_names = [b["name"] for b in main_bosses]
            main_options = ["Random"] + main_names
            current = state["bosses"].get("main", "Random")
            if current not in main_options:
                current = "Random"
            main_choice = st.selectbox(
                "Main boss",
                options=main_options,
                index=main_options.index(current),
                key="campaign_v1_main_boss",
            )
            state["bosses"]["main"] = main_choice

    # Mega boss
    with cols[2]:
        st.markdown("**Mega Boss**")
        if not mega_bosses:
            st.caption("No mega bosses available with current expansions.")
            state["bosses"]["mega"] = "None"
        else:
            mega_names = [b["name"] for b in mega_bosses]
            mega_options = ["None", "Random"] + mega_names
            current = state["bosses"].get("mega", "None")
            if current not in mega_options:
                current = "None"
            mega_choice = st.selectbox(
                "Mega boss (optional)",
                options=mega_options,
                index=mega_options.index(current),
                key="campaign_v1_mega_boss",
            )
            state["bosses"]["mega"] = mega_choice

    # --- Generate full campaign encounters (frozen) ---
    if st.button("Generate campaign", key="campaign_v1_generate"):
        with st.spinner("Generating campaign..."):
            campaign = _generate_v1_campaign(bosses_by_name, settings, state)
        state["campaign"] = campaign
        st.session_state["campaign_v1_state"] = state
        st.success("Campaign generated.")

    st.markdown("### Campaign overview")

    def describe_slot(label: str, slot_key: str) -> str:
        sel = state["bosses"].get(slot_key, "Random" if slot_key != "mega" else "None")
        if sel == "Random":
            return f"{label}: Random (boss revealed when reached)"
        if slot_key == "mega" and sel == "None":
            return f"{label}: None selected"
        return f"{label}: {sel}"

    st.markdown(f"- **{describe_slot('Mini boss', 'mini')}**")
    st.markdown(f"- **{describe_slot('Main boss', 'main')}**")
    st.markdown(f"- **{describe_slot('Mega boss', 'mega')}**")

    return state


def _render_v2_setup_placeholder() -> Dict[str, Any]:
    state = st.session_state.get("campaign_v2_state")
    if not isinstance(state, dict):
        state = {}
    # Placeholder structure; flesh out when V2 rules are implemented.
    st.info("V2 campaign setup not implemented yet.")
    st.session_state["campaign_v2_state"] = state
    return state


def _render_save_load_section(
    version: str,
    current_state: Dict[str, Any],
    settings: Dict[str, Any],
) -> None:
    st.markdown("---")
    st.subheader("Save / Load campaign")

    campaigns = _load_campaigns()

    col_save, col_load = st.columns([1, 1])

    # ----- SAVE -----
    with col_save:
        default_name = str(current_state.get("name", "")).strip()
        name_input = st.text_input(
            "Campaign name",
            value=default_name,
            key=f"campaign_name_{version}",
        )

        if st.button("Save campaign", key=f"campaign_save_{version}"):
            name = name_input.strip()
            if not name:
                st.error("Campaign name is required to save.")
            else:
                # For V1, require a generated campaign so Play can resume correctly.
                if version == "V1" and not isinstance(
                    current_state.get("campaign"), dict
                ):
                    st.error(
                        "Generate the V1 campaign before saving; "
                        "this save currently has no encounters."
                    )
                else:
                    current_state["name"] = name
                    snapshot = {
                        "rules_version": version,
                        "state": current_state,
                        "sidebar_settings": {
                            "active_expansions": settings.get("active_expansions"),
                            "selected_characters": settings.get("selected_characters"),
                            "ngplus_level": int(
                                st.session_state.get("ngplus_level", 0)
                            ),
                        },
                    }
                    campaigns[name] = snapshot
                    _save_campaigns(campaigns)
                    st.success(f"Saved campaign '{name}'.")

    # ----- LOAD / DELETE -----
    with col_load:
        if campaigns:
            names = sorted(campaigns.keys())
            selected_name = st.selectbox(
                "Existing campaigns",
                options=["<none>"] + names,
                index=0,
                key=f"campaign_load_select_{version}",
            )

            load_col, delete_col = st.columns([1, 1])

            with load_col:
                if st.button(
                    "Load selected campaign",
                    key=f"campaign_load_btn_{version}",
                ):
                    if selected_name != "<none>":
                        snapshot = campaigns[selected_name]
                        st.session_state["pending_campaign_snapshot"] = {
                            "name": selected_name,
                            "snapshot": snapshot,
                        }
                        st.rerun()

            with delete_col:
                if st.button(
                    "Delete selected",
                    key=f"campaign_delete_btn_{version}",
                ):
                    if selected_name == "<none>":
                        st.error("Select a campaign to delete.")
                    else:
                        campaigns.pop(selected_name, None)
                        _save_campaigns(campaigns)
                        st.success(f"Deleted campaign '{selected_name}'.")
                        st.rerun()
        else:
            st.caption("No saved campaigns yet.")

        # One-shot notice: appears directly under the load controls
        notice = st.session_state.pop("campaign_load_notice", None)
        if notice:
            name = notice.get("name") or "Unnamed"
            changes = notice.get("changes") or []
            if changes:
                st.success(
                    f"Loaded campaign '{name}' and updated: "
                    + ", ".join(changes)
                    + "."
                )
            else:
                st.success(f"Loaded campaign '{name}' (no sidebar changes).")


def _render_play_tab(
    bosses_by_name: Dict[str, Any],
    invaders_by_name: Dict[str, Any],
) -> None:
    version = st.session_state.get("campaign_rules_version", "V1")

    if version == "V1":
        state = st.session_state.get("campaign_v1_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        _render_v1_play(state, bosses_by_name)
    else:
        state = st.session_state.get("campaign_v2_state")
        if not isinstance(state, dict):
            st.info("Configure your campaign in the Setup tab first.")
            return
        st.info("V2 campaign play not implemented yet.")


def render() -> None:
    bosses = _load_json_object(BOSSES_PATH)
    invaders = _load_json_object(INVADERS_PATH)

    setup_tab, play_tab = st.tabs(["Setup", "Play"])

    with setup_tab:
        settings = _get_settings()
        version, player_count = _render_setup_header(settings)
        if version == "V1":
            state = _render_v1_setup(bosses, settings, player_count)
        else:
            state = _render_v2_setup_placeholder()
        _render_save_load_section(version, state, settings)

    with play_tab:
        _render_play_tab(bosses, invaders)
