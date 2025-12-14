#ui/campaign_mode/core.py
import streamlit as st
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from ui.encounters_tab.logic import (
    _list_encounters_cached,
    _load_valid_sets_cached,
    filter_expansions,
    filter_encounters,
    shuffle_encounter,
)
from ui.event_mode.logic import V2_EXPANSIONS


DATA_DIR = Path("data")
BOSSES_PATH = DATA_DIR / "bosses.json"
INVADERS_PATH = DATA_DIR / "invaders.json"
CAMPAIGNS_PATH = DATA_DIR / "campaigns.json"
ASSETS_DIR = Path("assets")
PARTY_TOKEN_PATH = ASSETS_DIR / "party_token.png"
SOULS_TOKEN_PATH = ASSETS_DIR / "souls_token.png"
BONFIRE_ICON_PATH = ASSETS_DIR / "bonfire.gif"
CHARACTERS_DIR = ASSETS_DIR / "characters"
V2_EXPANSIONS_SET = set(V2_EXPANSIONS)


def _get_player_count_from_settings(settings: Dict[str, Any]) -> int:
    """
    Local copy of the player-count logic to avoid importing ui.campaign_mode.state
    and creating a circular import.
    """
    selected_chars = settings.get("selected_characters")
    if isinstance(selected_chars, list) and selected_chars:
        return max(1, len(selected_chars))

    raw = st.session_state.get("player_count", 1)
    return max(1, int(raw))


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
    if version == "V1":
        return True

    # Be permissive if version is missing/blank
    if version == "":
        return True

    return False
 

def _is_v2_campaign_eligible(encounter: Dict[str, Any]) -> bool:
    """
    V2 campaign rule:

    - Only encounters that are V2.
    - Prefer explicit 'V2' version tagging (e.g. 'V2', 'V2.1', ...).
    - If version is blank, treat encounters from V2 expansions as V2.
    - Never accept encounters tagged as V1.
    """
    version = str(encounter.get("version", "")).upper()
    expansion = encounter.get("expansion")
    level = int(encounter["level"])

    # Explicit version tags win.
    if version.startswith("V2") or level == 4:
        return True
    if version.startswith("V1"):
        return False

    # Version missing/blank: fall back to expansion membership.
    if expansion in V2_EXPANSIONS_SET:
        return True

    # Anything else is not V2.
    return False


def _pick_random_campaign_encounter(
    *,
    encounters_by_expansion: Dict[str, List[Dict[str, Any]]],
    valid_sets: Dict[str, Any],
    character_count: int,
    active_expansions: List[str],
    level: int,
    eligibility_fn=_is_v1_campaign_eligible,
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

    Differences from the original implementation:
    - We *do not* fail on the first shuffle_encounter error.
    - We treat a failed shuffle as an invalid candidate and try another,
      until all candidates are exhausted.
    """
    # First, get the expansions that are valid under the current settings,
    # same as Encounter Mode does.
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
            lvl = int(e["level"])
            if lvl != level_int:
                continue

            # Only keep encounters allowed by the provided eligibility function.
            if not eligibility_fn(e):
                continue
            level_candidates.append(e)

        if level_candidates:
            candidate_expansions.append((exp_choice, level_candidates))

    if not candidate_expansions:
        raise ValueError(
            f"No valid level {level_int} encounters in any expansion "
            "for current party/expansion settings."
        )

    # Try candidates until one successfully builds, or all have been exhausted.
    last_error_msg: Optional[str] = None

    while candidate_expansions:
        # Randomly pick an expansion bucket
        exp_idx = random.randrange(len(candidate_expansions))
        exp_choice, level_candidates = candidate_expansions[exp_idx]

        # Randomly pick a base encounter within that bucket
        base_idx = random.randrange(len(level_candidates))
        base_enc = level_candidates[base_idx]

        res = shuffle_encounter(
            base_enc,
            character_count,
            active_expansions,
            exp_choice,
            use_edited=False,
        )

        if res.get("ok"):
            # Success: freeze and return the encounter snapshot
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

        # Failed to build this specific encounter; drop it and keep trying.
        last_error_msg = res.get("message")

        # Remove this candidate from its expansion bucket
        del level_candidates[base_idx]
        if not level_candidates:
            # This expansion has no more usable encounters at this level; drop it.
            del candidate_expansions[exp_idx]

    # If we get here, *every* candidate at this level failed to build.
    # Surface a single, more informative error.
    msg = (
        f"Failed to build any campaign encounter at level {level_int} "
        "for the current party/expansion settings."
    )
    if last_error_msg:
        msg += f" Last shuffle error: {last_error_msg}"
    raise RuntimeError(msg)


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
    player_count = _get_player_count_from_settings(settings)
    active_expansions = settings.get("active_expansions") or []

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        raise ValueError("No encounters available to generate a campaign.")

    valid_sets = _load_valid_sets_cached()
    resolved_bosses = _resolve_v1_bosses_for_campaign(bosses_by_name, settings, state)

    campaign: Dict[str, Any] = {
        "version": "V1",
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


def _generate_v2_campaign(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a V2 campaign track.

    Differences from V1 right now:
    - Each encounter *space* holds a choice between up to two frozen encounters
      at the appropriate level (where possible).
    - Eligibility prefers encounters tagged as V2 (or in V2 expansions), with
      level 4 still shared across both versions.
    """
    player_count = _get_player_count_from_settings(settings)
    active_expansions = settings.get("active_expansions") or []

    if not active_expansions:
        raise ValueError("No active expansions enabled; cannot generate a campaign.")

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        raise ValueError("No encounters available to generate a campaign.")

    valid_sets = _load_valid_sets_cached()
    resolved_bosses = _resolve_v1_bosses_for_campaign(bosses_by_name, settings, state)

    campaign: Dict[str, Any] = {
        "version": "V2",
        "player_count": player_count,
        "bosses": resolved_bosses,
        "nodes": [],
        "current_node_id": "bonfire",
    }
    nodes: List[Dict[str, Any]] = campaign["nodes"]
    nodes.append({"id": "bonfire", "kind": "bonfire"})

    def _build_options_for_level(lvl_int: int) -> List[Dict[str, Any]]:
        """
        Return up to two distinct frozen encounters at this level, using the
        V2 eligibility rules.
        """
        options: List[Dict[str, Any]] = []

        first = _pick_random_campaign_encounter(
            encounters_by_expansion=encounters_by_expansion,
            valid_sets=valid_sets,
            character_count=player_count,
            active_expansions=active_expansions,
            level=lvl_int,
            eligibility_fn=_is_v2_campaign_eligible,
        )
        options.append(first)

        # Try to find a second *different* encounter; fall back to a single
        # option if no variety is available.
        try:
            sig = (
                first.get("expansion"),
                int(first.get("encounter_level", lvl_int)),
                first.get("encounter_name"),
            )
        except Exception:
            sig = None

        second: Optional[Dict[str, Any]] = None
        for _ in range(6):
            candidate = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
                eligibility_fn=_is_v2_campaign_eligible,
            )

            if sig is None:
                second = candidate
                break

            try:
                c_sig = (
                    candidate.get("expansion"),
                    int(candidate.get("encounter_level", lvl_int)),
                    candidate.get("encounter_name"),
                )
            except Exception:
                c_sig = None

            if c_sig != sig:
                second = candidate
                break

        if second is not None:
            options.append(second)

        return options

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

            options = _build_options_for_level(lvl_int)

            nodes.append(
                {
                    "id": f"encounter:{stage_key}:{idx}",
                    "kind": "encounter",
                    "stage": stage_key,  # "mini" | "main" | "mega"
                    "index": idx,
                    "level": lvl_int,
                    "options": options,
                    "choice_index": None,
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
 

def _describe_v2_node_label(campaign: Dict[str, Any], node: Dict[str, Any]) -> str:
    """
    Human-readable label for a V2 campaign node.

    - Encounters: show "Encounter Choice (Level X)" until a choice is made,
      then show the chosen encounter name.
    - Bosses / bonfire: same semantics as V1.
    """
    kind = node.get("kind")
    if kind == "bonfire":
        return "Bonfire"

    if kind == "encounter":
        level = node.get("level")
        options = node.get("options") or []
        choice_idx = node.get("choice_index")

        if (
            isinstance(choice_idx, int)
            and 0 <= choice_idx < len(options)
        ):
            frozen = options[choice_idx] or {}
            name = frozen.get("encounter_name") or "Unknown Encounter"
            return f"Level {level} Encounter: {name}"

        return f"Encounter Choice (Level {level})"

    if kind == "boss":
        stage = node.get("stage")
        bosses_info = (campaign.get("bosses") or {}).get(stage, {})  # type: ignore[index]
        boss_name = bosses_info.get("name")
        was_random = bool(bosses_info.get("was_random"))
        revealed = bool(node.get("revealed")) or (boss_name and not was_random)

        prefix_map = {"mini": "Mini Boss", "main": "Main Boss", "mega": "Mega Boss"}
        prefix = prefix_map.get(stage, "Boss")

        if not boss_name:
            return f"{prefix}: None"
        if was_random and not revealed:
            return f"Unknown {prefix}"
        return f"{prefix}: {boss_name}"

    return "Unknown node"


def _v2_compute_allowed_destinations(campaign: Dict[str, Any]) -> Optional[set[str]]:
    """
    For V2 campaigns, if the party is currently on an encounter node,
    return the set of node ids that are legal destinations under the
    movement rule:

      - you may always return to the bonfire
      - you may move to the next encounter/boss in the same stage,
        but only if the current encounter has been marked as complete

    Otherwise, return None to indicate no extra restrictions.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    # Only restrict movement when standing on an encounter space
    if not current_node or current_node.get("kind") != "encounter":
        return None

    # Always allow returning to the bonfire
    allowed: set[str] = {"bonfire"}

    # If the encounter hasn't been marked complete yet, stop here
    if current_node.get("status") != "complete":
        return allowed

    # Otherwise, we can also go to the next encounter/boss in the same stage
    stage = current_node.get("stage")
    try:
        current_index = int(current_node.get("index"))
    except Exception:
        return allowed

    next_node_id: Optional[str] = None
    next_index: Optional[int] = None

    for node in nodes:
        if node.get("stage") != stage:
            continue

        # Boss nodes have no "index"; treat them as coming after all encounters
        if node.get("kind") == "boss":
            idx = current_index + 1_000_000
        else:
            try:
                idx = int(node.get("index"))
            except Exception:
                continue

        if idx <= current_index:
            continue

        if next_index is None or idx < next_index:
            next_index = idx
            next_node_id = node.get("id")

    if next_node_id:
        allowed.add(next_node_id)

    return allowed
