import random
from typing import Any, Dict, List, Optional
import streamlit as st

try:
    from ui.shared.memory_debug import memlog_checkpoint
except Exception:  # pragma: no cover
    memlog_checkpoint = None  # type: ignore
from ui.encounter_mode.logic import (
    _list_encounters_cached,
    _load_valid_sets_cached,
    filter_expansions,
    filter_encounters,
    shuffle_encounter,
)
from ui.campaign_mode.helpers import get_player_count_from_settings
from ui.campaign_mode.rules import _is_v2_campaign_eligible


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
    active_expansions = settings.get("active_expansions") or []
    if not active_expansions:
        raise ValueError("No active expansions enabled; cannot generate a campaign.")

    bosses_state = state.get("bosses") or {}
    result: Dict[str, Dict[str, Any]] = {}

    for slot, boss_type in (
        ("mini", "mini boss"),
        ("main", "main boss"),
        ("mega", "mega boss"),
    ):
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
            raise ValueError(
                f"No {boss_type} options available for campaign generation."
            )

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
    level = int(encounter["level"])
    if level == 4:
        return True
    version = str(encounter.get("version", "")).upper()
    if version == "V1":
        return True
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
    settings: Optional[Dict[str, Any]] = None,
    eligibility_fn=_is_v1_campaign_eligible,
) -> Dict[str, Any]:
    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:pick_encounter_enter",
                extra={
                    "level": int(level),
                    "char_count": int(character_count),
                    "active_expansions": int(len(active_expansions or [])),
                },
            )
        except Exception:
            pass

    filtered_expansions = filter_expansions(
        encounters_by_expansion,
        character_count,
        tuple(active_expansions),
        valid_sets,
    )
    if not filtered_expansions:
        raise ValueError("No valid encounter sets available for campaign generation.")

    level_int = int(level)

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
            continue

        level_candidates: List[Dict[str, Any]] = []
        for e in filtered_encounters:
            lvl = int(e["level"])
            if lvl != level_int:
                continue
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

    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:candidates_built",
                extra={
                    "level": int(level_int),
                    "candidate_expansions": int(len(candidate_expansions)),
                    "flat_candidates": int(sum(len(v) for _, v in candidate_expansions)),
                },
            )
        except Exception:
            pass

    last_error_msg: Optional[str] = None

    # Flatten candidate list into (exp_choice, base_enc) pairs for easier batching
    flat_candidates: List[tuple[str, List[Dict[str, Any]]]] = []
    for exp_choice, lvl_list in candidate_expansions:
        for enc in lvl_list:
            flat_candidates.append((exp_choice, enc))

    # Try candidates in randomized batches.
    #
    # NOTE: This module intentionally executes shuffle attempts synchronously
    # (no worker threads) to avoid Streamlit runtime warnings such as:
    #   "missing ScriptRunContext! This warning can be ignored when running in
    #    bare mode."
    #
    # Background: creating worker threads (e.g. via ThreadPoolExecutor) is
    # appealing for parallelizing many expensive `shuffle_encounter()` calls,
    # but Streamlit raises warnings when code running in those threads
    # indirectly touches the Streamlit runtime (decorators like
    # `@st.cache_data`/`@st.cache_resource`, or `st.session_state`). Those
    # warnings indicate the worker thread has no ScriptRunContext and can lead
    # to subtle bugs.
    #
    # Safe re-enable checklist (if you want to restore parallelism):
    # 1) Ensure every function called from worker threads is free of any
    #    direct `streamlit` runtime usage. Replace accesses to
    #    `st.session_state` by passing an explicit `settings` snapshot.
    # 2) Replace `@st.cache_data` / `@st.cache_resource` on worker-invoked
    #    paths with thread-safe caches, e.g. `functools.lru_cache`, or call
    #    the cached functions from the main thread and pass results into
    #    workers.
    # 3) Audit image and IO helpers (`core.image_cache`, `ui.encounter_mode.*`)
    #    to avoid Streamlit caching decorators being invoked inside workers.
    # 4) Add tests that reproduce the parallel path and confirm no
    #    ScriptRunContext warnings appear before enabling higher worker counts.
    #
    # For now, keep execution synchronous to ensure stable behavior.
    max_workers = 1
    random.shuffle(flat_candidates)

    # Iterate until we exhaust candidates. Execute shuffle attempts synchronously
    # to avoid creating ThreadPoolExecutor threads which can trigger
    # Streamlit "missing ScriptRunContext" warnings when they touch runtime APIs.
    settings_snapshot = dict(settings) if isinstance(settings, dict) else {}

    def _attempt_shuffle_sync(exp_choice: str, base_enc: Dict[str, Any]):
        key = f"{base_enc.get('name')}|{exp_choice}"
        use_edited = False
        if isinstance(settings, dict):
            edited_toggles = settings.get("edited_toggles") or {}
            use_edited = bool(edited_toggles.get(key, False))

        res = shuffle_encounter(
            base_enc,
            character_count,
            active_expansions,
            exp_choice,
            use_edited,
            bool(
                settings_snapshot.get("only_original_enemies_for_campaigns", False)
            ),
            settings=settings_snapshot,
            campaign_mode=True,
            render_image=False,
        )

        if memlog_checkpoint is not None:
            try:
                memlog_checkpoint(
                    st.session_state,
                    "camp:shuffle_attempt",
                    extra={
                        "level": int(level_int),
                        "exp": str(exp_choice),
                        "encounter": str(base_enc.get("name")),
                        "ok": bool(res.get("ok")),
                        "msg": str(res.get("message") or "")[:200],
                    },
                )
            except Exception:
                pass
        return res

    while flat_candidates:
        batch = flat_candidates[:max_workers]
        remaining = flat_candidates[max_workers:]

        for exp_choice, base_enc in batch:
            res = _attempt_shuffle_sync(exp_choice, base_enc)

            if res.get("ok"):
                frozen = {
                    "expansion": res.get("expansion", exp_choice),
                    "encounter_level": res.get("encounter_level", level_int),
                    "encounter_name": res.get("encounter_name") or base_enc.get("name"),
                    "enemies": res.get("enemies") or [],
                    "expansions_used": res.get("expansions_used") or [],
                    "edited": bool(res.get("edited", False)),
                }

                if memlog_checkpoint is not None:
                    try:
                        memlog_checkpoint(
                            st.session_state,
                            "camp:shuffle_success",
                            extra={
                                "level": int(level_int),
                                "exp": str(frozen.get("expansion")),
                                "encounter": str(frozen.get("encounter_name")),
                                "enemy_count": int(len(frozen.get("enemies") or [])),
                            },
                        )
                    except Exception:
                        pass
                return frozen

            last_error_msg = res.get("message") or last_error_msg

        # No success in this batch: drop tried candidates and continue
        flat_candidates = remaining

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
    return (
        frozen.get("expansion"),
        int(frozen.get("encounter_level", default_level)),
        frozen.get("encounter_name"),
    )


def _v2_pick_scout_ahead_alt_frozen(
    *,
    settings: Dict[str, Any],
    level: int,
    exclude_signatures: Optional[set[tuple[str, int, str]]] = None,
    max_tries: int = 30,
    campaign: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    lvl_int = int(level)

    exclude = exclude_signatures or set()

    player_count = get_player_count_from_settings(settings)

    active_expansions = settings.get("active_expansions") or []
    if not active_expansions:
        return None

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        return None

    valid_sets = _load_valid_sets_cached()

    if isinstance(campaign, dict):
        pool = campaign.get("v2_extra_pool")
        if isinstance(pool, list) and pool:
            for i, cand in enumerate(list(pool)):
                cand_lvl = int(
                    cand.get("encounter_level") or cand.get("level") or 0
                )
                if cand_lvl != lvl_int:
                    continue
                sig = _campaign_encounter_signature(cand, lvl_int)
                if sig is not None and sig in exclude:
                    continue
                pool.remove(cand)
                return cand

    tries = max(1, int(max_tries or 30))
    for _ in range(tries):
        cand = _pick_random_campaign_encounter(
            encounters_by_expansion=encounters_by_expansion,
            valid_sets=valid_sets,
            character_count=player_count,
            active_expansions=active_expansions,
            level=lvl_int,
            settings=settings,
            eligibility_fn=_is_v2_campaign_eligible,
        )

        sig = _campaign_encounter_signature(cand, lvl_int)
        if sig is not None and sig in exclude:
            continue
        return cand

    return None


def _generate_v1_campaign(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:v1_generate_enter",
                extra={
                    "active_expansions": int(len((settings.get("active_expansions") or []))),
                },
            )
        except Exception:
            pass

    player_count = get_player_count_from_settings(settings)
    active_expansions = settings.get("active_expansions") or []

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        raise ValueError("No encounters available to generate a campaign.")

    valid_sets = _load_valid_sets_cached()
    resolved_bosses = _resolve_v1_bosses_for_campaign(bosses_by_name, settings, state)

    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:v1_data_loaded",
                extra={
                    "player_count": int(player_count),
                    "expansions": int(len(active_expansions or [])),
                    "encounter_exps": int(len(encounters_by_expansion or {})),
                },
            )
        except Exception:
            pass

    campaign: Dict[str, Any] = {
        "version": "V1",
        "player_count": player_count,
        "bosses": resolved_bosses,
        "nodes": [],
        "current_node_id": "bonfire",
    }
    nodes: List[Dict[str, Any]] = campaign["nodes"]
    nodes.append({"id": "bonfire", "kind": "bonfire"})

    used_signatures: set[tuple[str, int, str]] = set()

    def _pick_v1_prefer_unused(lvl_int: int) -> Dict[str, Any]:
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
                settings=settings,
            )
            last_candidate = candidate
            sig = _campaign_encounter_signature(candidate, lvl_int)
            last_sig = sig

            if sig is None or sig not in used_signatures:
                frozen = candidate
                break

        if frozen is None:
            if last_candidate is None:
                frozen = _pick_random_campaign_encounter(
                    encounters_by_expansion=encounters_by_expansion,
                    valid_sets=valid_sets,
                    character_count=player_count,
                    active_expansions=active_expansions,
                    level=lvl_int,
                    settings=settings,
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
            lvl_int = int(lvl)

            frozen = _pick_v1_prefer_unused(lvl_int)

            nodes.append(
                {
                    "id": f"encounter:{stage_key}:{idx}",
                    "kind": "encounter",
                    "stage": stage_key,
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

    _add_stage("mini", resolved_bosses["mini"]["name"])
    _add_stage("main", resolved_bosses["main"]["name"])

    mega_name = resolved_bosses.get("mega", {}).get("name")
    if mega_name:
        _add_stage("mega", mega_name)

    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:v1_generate_done",
                extra={
                    "nodes": int(len(campaign.get("nodes") or [])),
                },
            )
        except Exception:
            pass

    return campaign


def _generate_v2_campaign(
    bosses_by_name: Dict[str, Any],
    settings: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:v2_generate_enter",
                extra={
                    "active_expansions": int(len((settings.get("active_expansions") or []))),
                },
            )
        except Exception:
            pass

    player_count = get_player_count_from_settings(settings)
    active_expansions = settings.get("active_expansions") or []

    if not active_expansions:
        raise ValueError("No active expansions enabled; cannot generate a campaign.")

    encounters_by_expansion = _list_encounters_cached()
    if not encounters_by_expansion:
        raise ValueError("No encounters available to generate a campaign.")

    valid_sets = _load_valid_sets_cached()
    resolved_bosses = _resolve_v1_bosses_for_campaign(bosses_by_name, settings, state)

    if memlog_checkpoint is not None:
        try:
            memlog_checkpoint(
                st.session_state,
                "camp:v2_data_loaded",
                extra={
                    "player_count": int(player_count),
                    "expansions": int(len(active_expansions or [])),
                    "encounter_exps": int(len(encounters_by_expansion or {})),
                },
            )
        except Exception:
            pass

    campaign: Dict[str, Any] = {
        "version": "V2",
        "player_count": player_count,
        "bosses": resolved_bosses,
        "nodes": [],
        "current_node_id": "bonfire",
    }
    nodes: List[Dict[str, Any]] = campaign["nodes"]
    nodes.append({"id": "bonfire", "kind": "bonfire"})

    used_signatures: set[tuple[str, int, str]] = set()

    def _build_options_for_level(lvl_int: int) -> List[Dict[str, Any]]:
        options: List[Dict[str, Any]] = []

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
                settings=settings,
                eligibility_fn=_is_v2_campaign_eligible,
            )
            last_candidate = candidate
            sig = _campaign_encounter_signature(candidate, lvl_int)
            last_sig = sig

            if sig is None or sig not in used_signatures:
                first = candidate
                first_sig = sig
                break

        if first is None:
            if last_candidate is None:
                first = _pick_random_campaign_encounter(
                    encounters_by_expansion=encounters_by_expansion,
                    valid_sets=valid_sets,
                    character_count=player_count,
                    active_expansions=active_expansions,
                    level=lvl_int,
                    settings=settings,
                    eligibility_fn=_is_v2_campaign_eligible,
                )
                first_sig = _campaign_encounter_signature(first, lvl_int)
            else:
                first = last_candidate
                first_sig = last_sig

        if first_sig is not None:
            used_signatures.add(first_sig)

        options.append(first)

        second: Optional[Dict[str, Any]] = None
        second_sig: Optional[tuple[str, int, str]] = None

        for _ in range(12):
            candidate = _pick_random_campaign_encounter(
                encounters_by_expansion=encounters_by_expansion,
                valid_sets=valid_sets,
                character_count=player_count,
                active_expansions=active_expansions,
                level=lvl_int,
                settings=settings,
                eligibility_fn=_is_v2_campaign_eligible,
            )

            if first is not None and candidate == first:
                continue

            sig = _campaign_encounter_signature(candidate, lvl_int)

            if first_sig is not None and sig == first_sig:
                continue

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

        if stage_key == "mini":
            levels = [1, 1, 1, 2]
        elif stage_key == "main":
            levels = [2, 2, 3, 3]
        else:
            levels = [4]

        if not isinstance(levels, list) or not levels:
            return

        for idx, lvl in enumerate(levels):
            lvl_int = int(lvl)

            options = _build_options_for_level(lvl_int)

            nodes.append(
                {
                    "id": f"encounter:{stage_key}:{idx}",
                    "kind": "encounter",
                    "stage": stage_key,
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

    _add_stage("mini", resolved_bosses["mini"]["name"])
    _add_stage("main", resolved_bosses["main"]["name"])

    mega_name = resolved_bosses.get("mega", {}).get("name")
    if mega_name:
        _add_stage("mega", mega_name)

    encounter_nodes = [n for n in nodes if n.get("kind") == "encounter"]
    total_spaces = len(encounter_nodes)
    pool_size = max(0, total_spaces + 2)

    pool: List[Dict[str, Any]] = []
    pool_sigs: set[tuple[str, int, str]] = set()

    used = set(used_signatures) if isinstance(used_signatures, set) else set()

    max_attempts = max(200, pool_size * 20)
    attempts = 0

    avail_levels = []
    for n in encounter_nodes:
        lvl = int(n.get("level") or 0)
        if lvl > 0:
            avail_levels.append(lvl)
    if not avail_levels:
        avail_levels = [1]

    while len(pool) < pool_size and attempts < max_attempts:
        attempts += 1
        target_level = int(random.choice(avail_levels))

        cand = _pick_random_campaign_encounter(
            encounters_by_expansion=encounters_by_expansion,
            valid_sets=valid_sets,
            character_count=player_count,
            active_expansions=active_expansions,
            level=target_level,
            settings=settings,
            eligibility_fn=_is_v2_campaign_eligible,
        )

        cand_level = int(cand.get("encounter_level") or cand.get("level") or 0)

        sig = _campaign_encounter_signature(cand, cand_level)
        if sig is None:
            continue
        if sig in used:
            continue
        if sig in pool_sigs:
            continue

        pool.append(cand)
        pool_sigs.add(sig)

    campaign["v2_extra_pool"] = pool
    campaign["v2_debug_log"] = [
        f"Starting pool generation: target_size={pool_size}, total_spaces={total_spaces}"
    ]
    campaign["v2_debug_log"].append(
        f"Available levels: {sorted(set(avail_levels))}"
    )
    campaign["v2_debug_log"].append(
        f"Finished pool generation: attempts={attempts}, final_pool_size={len(pool)}"
    )

    return campaign
