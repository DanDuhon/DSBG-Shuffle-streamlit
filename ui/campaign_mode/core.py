#ui/campaign_mode/core.py
import streamlit as st
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from ui.encounter_mode.logic import (
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


def _campaign_encounter_signature(
    frozen: Dict[str, Any],
    default_level: int,
) -> Optional[tuple[str, int, str]]:
    """
    Compact identity for a frozen campaign encounter so we can avoid
    repeating the same card across the campaign where possible.

    Identity is based on (expansion, level, encounter_name).
    """
    try:
        return (
            frozen.get("expansion"),
            int(frozen.get("encounter_level", default_level)),
            frozen.get("encounter_name"),
        )
    except Exception:
        return None


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

    Additional rule:
    - Avoid repeating the same encounter card unless there are no other
      eligible options at that level left.
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

    # Track which encounters have already appeared in this campaign so we
    # only repeat them when there are no unused options left.
    used_signatures: set[tuple[str, int, str]] = set()

    def _pick_v1_prefer_unused(lvl_int: int) -> Dict[str, Any]:
        """
        Pick a frozen encounter at lvl_int, preferring encounters whose
        (expansion, level, name) signature has not been used yet.

        If every eligible encounter at this level has already been used,
        we fall back to whatever _pick_random_campaign_encounter returns.
        """
        frozen: Optional[Dict[str, Any]] = None
        last_candidate: Optional[Dict[str, Any]] = None
        last_sig: Optional[tuple[str, int, str]] = None

        for _ in range(12):
            candidate = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
            )
            last_candidate = candidate
            sig = _campaign_encounter_signature(candidate, lvl_int)
            last_sig = sig

            # Prefer encounters that have not appeared yet
            if sig is None or sig not in used_signatures:
                frozen = candidate
                break

        if frozen is None:
            # Every candidate we tried has already appeared; accept a repeat.
            if last_candidate is None:
                frozen = _pick_random_campaign_encounter(
                    encounters_by_expansion=encounters_by_expansion,
                    valid_sets=valid_sets,
                    character_count=player_count,
                    active_expansions=active_expansions,
                    level=lvl_int,
                )
                sig = _campaign_encounter_signature(frozen, lvl_int)
            else:
                frozen = last_candidate
                sig = last_sig
        else:
            sig = _campaign_encounter_signature(frozen, lvl_int)

        if sig is not None:
            used_signatures.add(sig)

        return frozen

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

            frozen = _pick_v1_prefer_unused(lvl_int)

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

    # Track which encounters have already appeared anywhere in this V2 campaign,
    # so we avoid repeating the same card unless we run out of options.
    used_signatures: set[tuple[str, int, str]] = set()

    def _build_options_for_level(lvl_int: int) -> List[Dict[str, Any]]:
        """
        Return up to two distinct frozen encounters at this level, using the
        V2 eligibility rules.

        Additional rule:
        - Avoid repeating the same encounter card across the campaign unless
          there are no other eligible options left at this level.
        """
        options: List[Dict[str, Any]] = []

        # --- First option: prefer encounters that haven't been used yet ---
        first: Optional[Dict[str, Any]] = None
        first_sig: Optional[tuple[str, int, str]] = None
        last_candidate: Optional[Dict[str, Any]] = None
        last_sig: Optional[tuple[str, int, str]] = None

        for _ in range(12):
            candidate = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
                eligibility_fn=_is_v2_campaign_eligible,
            )
            last_candidate = candidate
            sig = _campaign_encounter_signature(candidate, lvl_int)
            last_sig = sig

            # Prefer encounters that haven't appeared in the campaign yet
            if sig is None or sig not in used_signatures:
                first = candidate
                first_sig = sig
                break

        if first is None:
            # Every candidate we tried has already appeared; accept a repeat.
            if last_candidate is None:
                first = _pick_random_campaign_encounter(
                    encounters_by_expansion=encounters_by_expansion,
                    valid_sets=valid_sets,
                    character_count=player_count,
                    active_expansions=active_expansions,
                    level=lvl_int,
                    eligibility_fn=_is_v2_campaign_eligible,
                )
                first_sig = _campaign_encounter_signature(first, lvl_int)
            else:
                first = last_candidate
                first_sig = last_sig

        if first_sig is not None:
            used_signatures.add(first_sig)

        options.append(first)

        # --- Second option: a different, preferably-unused encounter ---
        second: Optional[Dict[str, Any]] = None
        second_sig: Optional[tuple[str, int, str]] = None

        for _ in range(12):
            candidate = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
                eligibility_fn=_is_v2_campaign_eligible,
            )

            # Don't show the exact same frozen encounter twice in one space
            if first is not None and candidate == first:
                continue

            sig = _campaign_encounter_signature(candidate, lvl_int)

            # Avoid the same card as the first option if we can
            if first_sig is not None and sig == first_sig:
                continue

            # Prefer encounters that have not appeared anywhere else yet
            if sig is not None and sig in used_signatures:
                continue

            second = candidate
            second_sig = sig
            break

        if second is not None:
            if second_sig is not None:
                used_signatures.add(second_sig)
            options.append(second)

        return options

    def _add_stage(stage_key: str, boss_name: Optional[str]) -> None:
        if not boss_name:
            return

        cfg = bosses_by_name.get(boss_name)
        if not cfg:
            raise ValueError(f"Unknown boss '{boss_name}' in bosses.json.")

        # For V2, encounter levels are fixed by stage:
        #   mini: 1, 1, 1, 2
        #   main: 2, 2, 3, 3
        #   mega: 4
        if stage_key == "mini":
            levels = [1, 1, 1, 2]
        elif stage_key == "main":
            levels = [2, 2, 3, 3]
        else:
            levels = [4]

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


def _v2_get_current_stage(campaign: Dict[str, Any]) -> Optional[str]:
    """
    Determine the 'current chapter' (stage) for a V2 campaign.

    Priority:
      1. If the current node has a stage, use that.
      2. Otherwise, pick the first stage in (mini, main, mega) whose boss
         is not complete.
      3. If all bosses are complete, fall back to the last stage that exists.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    stage_order = ("mini", "main", "mega")

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    if current_node is not None:
        stage = current_node.get("stage")
        if stage in stage_order:
            return stage

    # First stage whose boss is not complete
    for stage in stage_order:
        boss = next(
            (
                n
                for n in nodes
                if n.get("stage") == stage and n.get("kind") == "boss"
            ),
            None,
        )
        if boss is None:
            continue
        if boss.get("status") != "complete":
            return stage

    # All bosses complete; fall back to the last stage that exists
    for stage in reversed(stage_order):
        if any(n.get("stage") == stage for n in nodes):
            return stage

    return None


def _v2_get_current_stage(campaign: Dict[str, Any]) -> Optional[str]:
    """
    Determine the 'current chapter' (stage) for a V2 campaign.

    Priority:
      1. If the current node has a stage, use that.
      2. Otherwise, pick the first stage in (mini, main, mega) whose boss
         is not complete.
      3. If all bosses are complete, fall back to the last stage that exists.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    stage_order = ("mini", "main", "mega")

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    # If we're currently on an encounter or boss, use its stage directly
    if current_node is not None:
        stage = current_node.get("stage")
        if stage in stage_order:
            return stage

    # Otherwise, choose the first stage whose boss is not complete
    for stage in stage_order:
        boss = next(
            (
                n
                for n in nodes
                if n.get("stage") == stage and n.get("kind") == "boss"
            ),
            None,
        )
        if boss is None:
            continue
        if boss.get("status") != "complete":
            return stage

    # All bosses complete; fall back to the last stage that exists
    for stage in reversed(stage_order):
        if any(n.get("stage") == stage for n in nodes):
            return stage

    return None


def _v2_get_current_stage(campaign: Dict[str, Any]) -> Optional[str]:
    """
    Determine the 'current chapter' (stage) for a V2 campaign.

    Priority:
      1. If the current node has a stage, use that.
      2. Otherwise, pick the first stage in (mini, main, mega) whose boss
         is not complete.
      3. If all bosses are complete, fall back to the last stage that exists.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    stage_order = ("mini", "main", "mega")

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    # If we're currently on an encounter or boss, use its stage directly
    if current_node is not None:
        stage = current_node.get("stage")
        if stage in stage_order:
            return stage

    # Otherwise, choose the first stage whose boss is not complete
    for stage in stage_order:
        boss = next(
            (
                n
                for n in nodes
                if n.get("stage") == stage and n.get("kind") == "boss"
            ),
            None,
        )
        if boss is None:
            continue
        if boss.get("status") != "complete":
            return stage

    # All bosses complete; fall back to the last stage that exists
    for stage in reversed(stage_order):
        if any(n.get("stage") == stage for n in nodes):
            return stage

    return None


def _record_dropped_souls(
    state: Dict[str, Any],
    failed_node_id: Optional[str],
    current_souls: int,
) -> None:
    """
    Record or clear a dropped-souls token in the campaign state.

    Only one node can have dropped souls at a time:
      - If failed_node_id is truthy and current_souls > 0, store the token there.
      - Otherwise clear any existing token.
    """
    if failed_node_id and current_souls > 0:
        state["souls_token_node_id"] = failed_node_id
        state["souls_token_amount"] = current_souls
    else:
        state["souls_token_node_id"] = None
        state["souls_token_amount"] = 0


def _reset_all_encounters_on_bonfire_return(campaign: Dict[str, Any]) -> None:
    """
    Clear completion state from all encounter nodes when the party returns
    to the Bonfire.

    This does NOT touch shortcuts; flags such as 'shortcut_unlocked' stay
    in place so shortcuts remain valid on future runs.
    """
    nodes = campaign.get("nodes") or []
    for node in nodes:
        if node.get("kind") == "encounter" and node.get("status") == "complete":
            node["status"] = "incomplete"


def _v2_compute_allowed_destinations(campaign: Dict[str, Any]) -> Optional[set[str]]:
    """
    For V2 campaigns, compute the set of legal destinations under the movement rules.

    When standing on an encounter node:
      - you may always return to the bonfire
      - you may move to the next encounter/boss in the same stage,
        but only if the current encounter has been marked as complete

    When standing on the bonfire:
      - you may move only to the first encounter in the current chapter
      - or to any encounter in that chapter that has a shortcut unlocked

    For any other current node, return None to indicate no extra restrictions.
    """
    nodes = campaign.get("nodes") or []
    if not nodes:
        return None

    node_by_id = {n.get("id"): n for n in nodes}
    current_id = campaign.get("current_node_id")
    current_node = node_by_id.get(current_id)

    if not current_node:
        return None

    kind = current_node.get("kind")

    # Case 1: standing on an encounter space
    if kind == "encounter":
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

    # Case 2: standing on the bonfire
    if kind == "bonfire":
        stage = _v2_get_current_stage(campaign)
        if stage is None:
            return None

        # Collect encounters in this stage with their index
        encounters: list[tuple[int, Dict[str, Any]]] = []
        for node in nodes:
            if node.get("kind") != "encounter" or node.get("stage") != stage:
                continue
            try:
                idx = int(node.get("index"))
            except Exception:
                continue
            encounters.append((idx, node))

        if not encounters:
            return None

        # First encounter in the chapter
        encounters.sort(key=lambda t: t[0])
        first_encounter_node = encounters[0][1]
        allowed: set[str] = set()
        first_id = first_encounter_node.get("id")
        if first_id:
            allowed.add(first_id)

        # Any encounter in the current chapter that has an unlocked shortcut
        for idx, node in encounters[1:]:
            if not node.get("shortcut_unlocked"):
                continue
            node_id = node.get("id")
            if node_id:
                allowed.add(node_id)

        return allowed or None

    # Any other current node (e.g., boss): do not add extra restrictions
    return None
