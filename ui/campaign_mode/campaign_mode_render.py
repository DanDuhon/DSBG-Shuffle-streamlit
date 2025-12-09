from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import json
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
from ui.behavior_decks_tab.assets import BEHAVIOR_CARDS_PATH


DATA_DIR = Path("data")
BOSSES_PATH = DATA_DIR / "bosses.json"
INVADERS_PATH = DATA_DIR / "invaders.json"
CAMPAIGNS_PATH = DATA_DIR / "campaigns.json"

ASSETS_DIR = Path("assets")
PARTY_TOKEN_PATH = ASSETS_DIR / "party_token.png"
BONFIRE_ICON_PATH = ASSETS_DIR / "bonfire.gif"


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

        level_candidates = [
            e for e in filtered_encounters
            if int(e.get("level", -1)) == level_int
        ]
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
    Render the encounter card image for a frozen campaign encounter, if possible.
    Falls back to a warning if we can't resolve the original encounter.
    """
    expansion = frozen.get("expansion")
    level = frozen.get("encounter_level")
    name = frozen.get("encounter_name")
    enemies = frozen.get("enemies") or []

    if not (expansion and level and name):
        st.caption("Encounter card data incomplete.")
        return

    # Look up the original encounter definition from the cached list.
    encounters_by_expansion = _list_encounters_cached()
    base_list = encounters_by_expansion.get(expansion)
    if not base_list:
        st.warning(f"No encounter data found for expansion '{expansion}'.")
        return

    base_enc = None
    level_int = int(level)
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

    try:
        card_img = generate_encounter_image(
            expansion,
            level_int,
            name,
            base_enc,
            enemies,
            use_edited=False,
        )
    except Exception as exc:
        st.warning(f"Failed to render encounter card: {exc}")
        return

    st.image(card_img, width="stretch")


def _render_v1_current_panel(campaign: Dict[str, Any], current_node: Dict[str, Any]) -> None:
    """
    Right-hand panel: show bonfire / encounter card / boss data card
    with appropriate action button.
    """
    kind = current_node.get("kind")

    st.markdown("#### Current space")

    # Bonfire
    if kind == "bonfire":
        st.caption("Resting at the bonfire.")
        if BONFIRE_ICON_PATH.is_file():
            st.image(str(BONFIRE_ICON_PATH), width="stretch")
        else:
            st.caption("bonfire.gif not found in assets.")
        return

    # Encounter space
    if kind == "encounter":
        frozen = current_node.get("frozen") or {}
        name = frozen.get("encounter_name") or "Unknown Encounter"
        level = frozen.get("encounter_level")
        expansion = frozen.get("expansion") or "Unknown Expansion"

        st.markdown(f"**Level {level} Encounter**")
        st.caption(f"{name} ({expansion})")

        _render_v1_encounter_card(frozen)

        if st.button("Start Encounter", key=f"campaign_v1_start_enc_{current_node.get('id')}"):
            st.info("Encounter play not wired yet; use Encounter Mode for now.")
        return

    # Boss space
    if kind == "boss":
        stage = current_node.get("stage")
        boss_name = current_node.get("boss_name")

        prefix_map = {
            "mini": "Mini Boss",
            "main": "Main Boss",
            "mega": "Mega Boss",
        }
        prefix = prefix_map.get(stage, "Boss")

        if boss_name:
            st.markdown(f"**{prefix}: {boss_name}**")
        else:
            st.markdown(f"**{prefix}: Unknown**")

        # Boss data card (same pattern as play_panels / invader_panel)
        if boss_name:
            data_path = Path(BEHAVIOR_CARDS_PATH + f"{boss_name} - data.jpg")
            if data_path.is_file():
                st.image(str(data_path), width="stretch")
            else:
                st.warning(f"Data card not found for '{boss_name}'.")
        else:
            st.caption("No boss selected for this space.")

        if st.button("Start Boss Fight", key=f"campaign_v1_start_boss_{stage}"):
            st.info("Boss play not wired yet; use Boss Mode for now.")
        return

    st.caption("No details available for this space.")


def _render_v1_play(state: Dict[str, Any], bosses_by_name: Dict[str, Any]) -> None:
    """
    V1 Play tab:

    - Sparks tracker + Soul cache + party summary at the top.
    - Shows current location (Bonfire / encounter / boss).
    - Shows the full campaign path:
        Bonfire
        Unknown Level X Encounter
        Unknown Mini/Main/Mega Boss (if boss was Random)
    - Each encounter/boss has a button to move the party there.
      The current location row shows the party token image instead of a button.
    - Right-hand panel shows bonfire / encounter card / boss data card.
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
    state["campaign"] = campaign  # keep state/campaign in sync

    # Layout: left = overview/path, right = current card/panel
    col_overview, col_detail = st.columns([2, 1])

    with col_overview:
        st.markdown("### Campaign overview")

        # --- Sparks + Soul cache row ---
        col_sparks, col_souls = st.columns(2)

        # Sparks tracker (editable numeric, but no +/-)
        with col_sparks:
            sparks_max = int(state.get("sparks_max", _default_sparks_max(_get_player_count(settings))))
            sparks_cur = int(state.get("sparks", sparks_max))
            st.metric("Sparks", f"{sparks_cur} / {sparks_max}")

            new_sparks = st.number_input(
                "Current sparks",
                min_value=0,
                max_value=sparks_max,
                value=sparks_cur,
                step=1,
                key="campaign_v1_sparks_play",
            )
            state["sparks"] = int(new_sparks)

        # Soul cache with +/- and manual entry
        with col_souls:
            souls_key = "campaign_v1_souls_play"

            col_minus, col_input, col_plus = st.columns([1, 3, 1])
            with col_minus:
                minus_clicked = st.button("−", key="campaign_v1_souls_minus")
            with col_plus:
                plus_clicked = st.button("+", key="campaign_v1_souls_plus")

            if minus_clicked or plus_clicked:
                current_val = st.session_state.get(souls_key, int(state.get("souls", 0)))
                delta = 1 if plus_clicked else -1
                new_val = max(0, int(current_val) + delta)
                st.session_state[souls_key] = new_val
                state["souls"] = new_val

            with col_input:
                souls_value = st.number_input(
                    "Soul cache",
                    min_value=0,
                    value=int(state.get("souls", 0)),
                    step=1,
                    key=souls_key,
                )
                state["souls"] = int(souls_value)

        # --- Party row (simple summary, analogous to Encounter Mode) ---
        party = settings.get("selected_characters") or []
        if party:
            party_str = ", ".join(str(c) for c in party)
            st.markdown(f"**Party:** {party_str}")
        else:
            st.caption("Party not configured; select characters in the sidebar.")

        st.markdown("---")

        # Current location label
        st.markdown(
            f"**Current location:** {_describe_v1_node_label(campaign, current_node)}"
        )

        st.markdown("#### Path")

        # Path list with Travel/Confront/Return and party token on current node
        for node in nodes:
            label = _describe_v1_node_label(campaign, node)
            row_cols = st.columns([3, 1])

            with row_cols[0]:
                st.markdown(f"- {label}")

            with row_cols[1]:
                node_id = node.get("id")
                kind = node.get("kind")
                is_current = node_id == campaign.get("current_node_id")

                # If this is the current location, show the party token instead of a button
                if is_current:
                    if PARTY_TOKEN_PATH.is_file():
                        st.image(str(PARTY_TOKEN_PATH), width=48)
                    else:
                        st.caption("Party")
                    continue

                # Bonfire row gets a "Return to Bonfire" action
                if kind == "bonfire":
                    if st.button(
                        "Return to Bonfire",
                        key="campaign_v1_goto_bonfire",
                    ):
                        campaign["current_node_id"] = node_id
                        state["campaign"] = campaign
                        st.session_state["campaign_v1_state"] = state
                        st.rerun()
                    continue

                # Encounter/boss rows: Travel / Confront
                if kind in ("encounter", "boss"):
                    btn_label = "Travel" if kind == "encounter" else "Confront"
                    if st.button(btn_label, key=f"campaign_v1_goto_{node_id}"):
                        # Move party and reveal node
                        campaign["current_node_id"] = node_id
                        node["revealed"] = True

                        state["campaign"] = campaign
                        st.session_state["campaign_v1_state"] = state
                        st.rerun()

    # Right-hand: bonfire / encounter card / boss data card
    with col_detail:
        _render_v1_current_panel(campaign, current_node)

    # Persist updated state (sparks / souls / campaign position)
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

    # --- New: generate full campaign encounters (frozen) ---
    if st.button("Generate campaign", key="campaign_v1_generate"):
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
                current_state["name"] = name
                snapshot = {
                    "rules_version": version,
                    "state": current_state,
                    "sidebar_settings": {
                        "active_expansions": settings.get("active_expansions"),
                        "selected_characters": settings.get("selected_characters"),
                        "ngplus_level": int(st.session_state.get("ngplus_level", 0)),
                    },
                }
                campaigns[name] = snapshot
                _save_campaigns(campaigns)
                st.success(f"Saved campaign '{name}'.")

    with col_load:
        if campaigns:
            names = sorted(campaigns.keys())
            selected_name = st.selectbox(
                "Existing campaigns",
                options=["<none>"] + names,
                index=0,
                key=f"campaign_load_select_{version}",
            )
            if st.button("Load selected campaign", key=f"campaign_load_btn_{version}"):
                if selected_name != "<none>":
                    snapshot = campaigns[selected_name]

                    st.session_state["pending_campaign_snapshot"] = {
                        "name": selected_name,
                        "snapshot": snapshot,
                    }
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
                    f"Loaded campaign '{name}' and updated: " + ", ".join(changes) + "."
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
