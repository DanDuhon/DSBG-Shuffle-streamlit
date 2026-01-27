#ui/encounter_mode/logic.py
import streamlit as st
import re
import os
import json
from functools import lru_cache
from pathlib import Path
from io import BytesIO
from random import choice

from ui.encounter_mode.generation import (
    generate_encounter_image,
    load_encounter,
    load_valid_sets,
)
from core.enemies import ENEMY_EXPANSIONS_BY_ID
from ui.encounter_mode.data.enemies import enemyNames
from ui.encounter_mode.data.rewards import ENCOUNTER_ORIGINAL_REWARDS
from ui.encounter_mode.data.behavior_modifiers import ( # Don't remove these, they get imported elsewhere
    ENCOUNTER_BEHAVIOR_MODIFIERS,
    ENCOUNTER_BEHAVIOR_MODIFIERS_EDITED,
)
from core.character.character_stats import average_souls_to_equip
from ui.character_mode.data_io import _find_data_file, _load_json_list
from core.settings_manager import get_config_bool, is_streamlit_cloud
from core.expansions import is_v2_expansion


INVADERS_PATH = Path("data/invaders.json")
HARD_MAX_INVADERS_BY_LEVEL = {
    1: 2,
    2: 3,
    3: 5,
    4: 4,
}
INVADER_LIMIT_SETTING_KEYS = (
    "max_invaders_per_level",            # preferred
    "max_invaders_by_level",             # tolerated alias
    "max_allowed_invaders_per_level",    # tolerated alias
)


# Cloud-only: reduce long-lived LRU caches to lower memory pressure.
_TIGHTEN_LRU = is_streamlit_cloud() and get_config_bool(
    "DSBG_DISABLE_ENCOUNTER_IMAGE_CACHES", default=False
)

_AVAILABILITY_CACHE_MAX = 1024 if _TIGHTEN_LRU else 4096
_VIABLE_ALT_CACHE_MAX = 2048 if _TIGHTEN_LRU else 16384


@st.cache_data(show_spinner=False)
def _list_encounters_cached():
    # Build and return the human-friendly expansion->encounter list using
    # the pre-index so callers benefit from a single cached filesystem scan.
    idx = _build_encounter_index_cached()

    # Reconstruct encounters grouped by expansion in the same sorted order
    # that the legacy `list_encounters()` produced.
    expansions = {}
    for key, ent in idx.items():
        exp = ent.get("expansion")
        lvl = ent.get("level")
        name = ent.get("name")
        expansions.setdefault(exp, []).append({"name": name, "expansion": exp, "level": lvl, "version": ent.get("version")})

    # --- Custom expansion sorting (keep parity with previous implementation) ---
    def expansion_sort_key(exp):
        exp_lower = exp.lower()
        if is_v2_expansion(exp):
            return (0, exp_lower)
        elif "dark souls the board game" in exp_lower:
            return (1, exp_lower)
        elif any(x in exp_lower for x in ["darkroot", "explorers", "iron keep"]):
            return (2, exp_lower)
        elif "executioner" in exp_lower:
            return (3, exp_lower)
        else:
            return (4, exp_lower)

    sorted_expansions = sorted(expansions.keys(), key=expansion_sort_key)

    sorted_data = {}
    for exp in sorted_expansions:
        sorted_encounters = sorted(
            expansions[exp],
            key=lambda e: (e["level"], e["name"].lower()),
        )
        sorted_data[exp] = sorted_encounters

    return sorted_data


@st.cache_data(show_spinner=False)
def _build_encounter_index_cached():
    """Scan `data/encounters` and build a pre-index mapping a base slug
    (`{expansion}_{level}_{name}`) to available character-count variants and
    metadata. Returns a dict keyed by base slug.

    Example entry:
      {
        'Painted World of Ariamis_1_Frozen Sentries': {
            'expansion': 'Painted World of Ariamis',
            'level': 1,
            'name': 'Frozen Sentries',
            'counts': [1,2,3],
            'filenames': {1: 'data/encounters/..._1.json', 2: '..._2.json', ...},
            'version': 'V1'
        }
      }
    """
    index = {}
    pattern = re.compile(r"(.+?)_(\d+)_(.+?)_(\d+)\.json")
    data_dir = Path("data/encounters")
    if not data_dir.exists():
        return index

    for f in os.listdir(data_dir):
        if not f.endswith(".json"):
            continue
        m = pattern.match(f)
        if not m:
            continue
        expansion, level_s, enc_name, count_s = m.groups()
        lvl = int(level_s)
        cnt = int(count_s)

        base_key = f"{expansion}_{lvl}_{enc_name}"
        ent = index.setdefault(base_key, {"expansion": expansion, "level": lvl, "name": enc_name, "counts": [], "filenames": {}, "version": None})

        # record available character-count variant and filename
        if cnt not in ent["counts"]:
            ent["counts"].append(cnt)
        ent["filenames"][cnt] = str(data_dir / f)

        # determine encounter image versioning heuristics
        if lvl == 4:
            ent["version"] = "V2"
        else:
            exp_lower = expansion.lower()
            if exp_lower in {"dark souls the board game", "darkroot", "explorers", "iron keep", "executioner's chariot"}:
                ent["version"] = "V1"
            else:
                ent["version"] = "V2"

    return index


@st.cache_data(show_spinner=False)
def _load_valid_sets_cached():
    return load_valid_sets()


def _coerce_enemy_id(x):
    # Enemies are usually ints; be defensive in case a dict/name slips in.
    if isinstance(x, dict):
        x = x.get("enemy_id") or x.get("id") or x.get("name")
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        s = x.strip()
        if s.isdigit():
            return int(s)
        return s
    return x


@st.cache_data(show_spinner=False)
def _load_invader_enemy_ids():
    """
    Load invader identifiers so we can count how many invaders are in a chosen enemy list.
    Supports a few plausible shapes for invaders.json.
    """
    if not INVADERS_PATH.exists():
        return set()

    with INVADERS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    ids = set()

    if isinstance(data, dict):
        for k, v in data.items():
            # Always include the key as a fallback identifier
            ids.add(_coerce_enemy_id(k))
            if isinstance(v, dict):
                cand = v.get("enemy_id") or v.get("id") or v.get("name")
                if cand is not None:
                    ids.add(_coerce_enemy_id(cand))
    elif isinstance(data, list):
        for v in data:
            ids.add(_coerce_enemy_id(v))

    return ids


def _get_invader_limit_for_level(level: int) -> int:
    lvl = int(level)
    hard = int(HARD_MAX_INVADERS_BY_LEVEL.get(lvl, 0))

    settings = st.session_state.get("user_settings") or {}
    limits = None
    for k in INVADER_LIMIT_SETTING_KEYS:
        if k in settings:
            limits = settings.get(k)
            break

    user_val = None
    if isinstance(limits, dict):
        user_val = limits.get(str(lvl), limits.get(lvl))
    elif isinstance(limits, (list, tuple)) and len(limits) >= lvl:
        user_val = limits[lvl - 1]
    elif isinstance(limits, int):
        user_val = limits

    if user_val is None:
        user_val = hard

    user_int = int(user_val)

    return max(0, min(hard, user_int))


def _get_invader_limit_for_level_with_settings(level: int, settings: dict | None) -> int:
    """Like `_get_invader_limit_for_level`, but does not touch Streamlit runtime.

    This is important for callers that want stable cache keys.
    """
    lvl = int(level)
    hard = int(HARD_MAX_INVADERS_BY_LEVEL.get(lvl, 0))
    settings = settings or {}

    limits = None
    for k in INVADER_LIMIT_SETTING_KEYS:
        if k in settings:
            limits = settings.get(k)
            break

    user_val = None
    if isinstance(limits, dict):
        user_val = limits.get(str(lvl), limits.get(lvl))
    elif isinstance(limits, (list, tuple)) and len(limits) >= lvl:
        user_val = limits[lvl - 1]
    elif isinstance(limits, int):
        user_val = limits

    if user_val is None:
        user_val = hard

    try:
        user_int = int(user_val)
    except Exception:
        user_int = hard

    return max(0, min(hard, user_int))


def _disabled_enemy_ids_signature(settings: dict | None) -> tuple[str, ...]:
    """Return a stable signature of disabled enemies based on merged toggles.

    Code checks are of the form: `if str(eid) in effective_enemy_included and not bool(value)`.
    Therefore only the set of disabled IDs matters for availability computations.
    """
    settings = settings or {}
    legacy_enemy_included = settings.get("enemy_included", {}) or {}
    campaign_enemy_included = settings.get("campaign_enemy_included", {}) or {}
    effective_enemy_included = {}
    if isinstance(legacy_enemy_included, dict):
        effective_enemy_included.update(legacy_enemy_included)
    if isinstance(campaign_enemy_included, dict):
        effective_enemy_included.update(campaign_enemy_included)

    disabled = [str(k) for k, v in effective_enemy_included.items() if not bool(v)]
    return tuple(sorted(disabled))


@lru_cache(maxsize=_AVAILABILITY_CACHE_MAX)
def _analyze_encounter_availability_cached(
    encounter_slug: str,
    level: int,
    character_count: int,
    active_expansions_norm: tuple[str, ...],
    disabled_enemy_ids: tuple[str, ...],
    inv_limit: int,
) -> tuple[int, bool]:
    """Cached core for availability.

    Returns (num_viable_alternatives, original_viable).
    """
    data = load_encounter(encounter_slug, int(character_count))
    orig = (data or {}).get("original") or []

    invader_ids = _load_invader_enemy_ids()
    disabled_set = set(disabled_enemy_ids)

    # original viability
    original_viable = True
    if not orig:
        original_viable = False
    else:
        inv_count = 0
        for e in orig:
            eid = _coerce_enemy_id(e)
            if eid not in ENEMY_EXPANSIONS_BY_ID:
                original_viable = False
                break
            if str(eid) in disabled_set:
                original_viable = False
                break
            if invader_ids and eid in invader_ids:
                inv_count += 1
                if inv_count > int(inv_limit):
                    original_viable = False
                    break

    # viable alternatives (deduplicate identical enemy sets)
    total = 0
    valid_alts = get_alternatives(data or {}, set(active_expansions_norm))
    if valid_alts:
        seen = set()
        for _combo, alt_sets in valid_alts.items():
            for enemies in alt_sets or []:
                if enemies is None:
                    continue
                enemy_list = list(enemies)

                normalized = tuple(sorted(_coerce_enemy_id(e) for e in enemy_list))
                if normalized in seen:
                    continue

                skip = False
                inv_count = 0
                for e in enemy_list:
                    eid = _coerce_enemy_id(e)
                    if eid not in ENEMY_EXPANSIONS_BY_ID:
                        skip = True
                        break
                    if str(eid) in disabled_set:
                        skip = True
                        break
                    if invader_ids and eid in invader_ids:
                        inv_count += 1
                        if inv_count > int(inv_limit):
                            skip = True
                            break
                if not skip:
                    seen.add(normalized)
                    total += 1

    return total, original_viable


def apply_edited_toggle(encounter_data, expansion, encounter_name, encounter_level,
                        use_edited, enemies, combo):
    """Swap between edited/original encounter visuals (no reshuffle)."""
    card_img = generate_encounter_image(
        expansion, encounter_level, encounter_name, encounter_data, enemies, use_edited
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


def filter_encounters(all_encounters, selected_expansion: str, character_count: int, active_expansions: tuple, valid_sets: dict):
    out = []
    settings = st.session_state.get("user_settings") or {}
    enemy_included = settings.get("enemy_included", {}) or {}

    for e in all_encounters:
        key = f"{selected_expansion}_{e['level']}_{e['name']}"
        if not encounter_is_valid(key, character_count, tuple(active_expansions), valid_sets):
            continue
        # Also ensure the encounter has at least one viable enemy set under
        # current enemy toggles and invader limits.
        if _encounter_has_viable_alternative(e['expansion'], e['level'], e['name'], character_count, set(active_expansions), enemy_included, settings=settings):
            out.append(e)
    return out


def filter_expansions(encounters_by_expansion, character_count: int, active_expansions: tuple, valid_sets: dict):
    filtered_expansions = []
    settings = st.session_state.get("user_settings") or {}
    enemy_included = settings.get("enemy_included", {}) or {}
    for expansion_name, encounter_list in encounters_by_expansion.items():
        has_valid = False
        for e in encounter_list:
            key = f"{expansion_name}_{e['level']}_{e['name']}"
            if not encounter_is_valid(key, character_count, active_expansions, valid_sets):
                continue
            if _encounter_has_viable_alternative(expansion_name, e['level'], e['name'], character_count, set(active_expansions), enemy_included, settings=settings):
                has_valid = True
                break
        if has_valid:
            filtered_expansions.append(expansion_name)
    return filtered_expansions


@lru_cache(maxsize=_VIABLE_ALT_CACHE_MAX)
def _encounter_has_viable_alternative_cached(
    encounter_slug: str,
    level: int,
    character_count: int,
    active_expansions_norm: tuple[str, ...],
    disabled_enemy_ids: tuple[str, ...],
    inv_limit: int,
    original_only: bool,
) -> bool:
    """Cached core for determining whether an encounter can be generated.

    Returns True if either:
    - `original_only` and the original enemy list is viable, or
    - at least one alternative enemy set is viable.
    """
    data = load_encounter(encounter_slug, int(character_count)) or {}
    invader_ids = _load_invader_enemy_ids()
    disabled_set = set(disabled_enemy_ids)

    def _list_is_viable(enemy_list) -> bool:
        if not enemy_list:
            return False
        inv_count = 0
        for e in enemy_list:
            eid = _coerce_enemy_id(e)
            if eid not in ENEMY_EXPANSIONS_BY_ID:
                return False
            if str(eid) in disabled_set:
                return False
            if invader_ids and eid in invader_ids:
                inv_count += 1
                if inv_count > int(inv_limit):
                    return False
        return True

    if bool(original_only):
        return _list_is_viable(data.get("original") or [])

    valid_alts = get_alternatives(data, set(active_expansions_norm))
    if not valid_alts:
        return False

    for _combo, alt_sets in valid_alts.items():
        for enemies in alt_sets or []:
            if enemies is None:
                continue
            if _list_is_viable(list(enemies)):
                return True
    return False


def _norm_name(x):
    """Normalize expansion/entry names for consistent comparisons."""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        for k in ("name", "title", "expansion"):
            if k in x:
                return str(x[k]).strip()
        try:
            return json.dumps(x, sort_keys=True)
        except Exception:
            return str(x)
    if isinstance(x, (list, tuple)) and x:
        return _norm_name(x[0])
    return str(x).strip()


def _encounter_has_viable_alternative(
    expansion: str,
    level: int,
    name: str,
    character_count: int,
    active_expansions: set,
    enemy_included: dict,
    settings: dict | None = None,
) -> bool:
    """Return True if the encounter has at least one enemy set that is allowed
    by `ENEMY_EXPANSIONS_BY_ID`, not disabled by `enemy_included`, and respects invader limits."""
    encounter_slug = f"{expansion}_{int(level)}_{name}"
    if settings is None:
        settings = st.session_state.get("user_settings") or {}

    # Merge caller-provided `enemy_included` with sidebar/campaign toggles
    campaign_enemy_included = settings.get("campaign_enemy_included", {}) or {}
    effective_enemy_included = {}
    if isinstance(enemy_included, dict):
        effective_enemy_included.update(enemy_included)
    if isinstance(campaign_enemy_included, dict):
        effective_enemy_included.update(campaign_enemy_included)
    disabled_enemy_ids = tuple(sorted(str(k) for k, v in effective_enemy_included.items() if not bool(v)))

    active_expansions_norm = tuple(sorted(_norm_name(a) for a in (active_expansions or set())))
    inv_limit = _get_invader_limit_for_level_with_settings(int(level), settings)
    original_only = bool(settings.get("only_original_enemies_for_campaigns", False))

    return _encounter_has_viable_alternative_cached(
        encounter_slug,
        int(level),
        int(character_count),
        active_expansions_norm,
        disabled_enemy_ids,
        int(inv_limit),
        bool(original_only),
    )


def encounter_is_valid(encounter_key: str, char_count: int, active_expansions: tuple, valid_sets: dict) -> bool:
    """
    Returns True if at least one expansion set for this encounter/char_count
    is a subset of the active expansions.
    """
    expansions_for_enc = valid_sets.get(encounter_key, {}).get(str(char_count), [])
    active_set = set(_norm_name(a) for a in active_expansions or ())
    for expansion_set in expansions_for_enc:
        norm_set = set(_norm_name(e) for e in (expansion_set or []))
        if norm_set.issubset(active_set):
            return True
    return False


def shuffle_encounter(
    selected_encounter,
    character_count,
    active_expansions,
    selected_expansion,
    use_edited,
    use_original_enemies: bool = False,
    settings: dict | None = None,
    campaign_mode: bool = False,
    render_image: bool = True,
):
    """Shuffle and generate a randomized encounter (respects invader limit setting).

    If `use_original_enemies` is True, the encounter will be generated with the
    original enemy list from the encounter JSON (no alternative selection).
    The original enemy list is still subject to the configured invader limit
    for the encounter level; if it violates the limit an error is returned.
    """
    name = selected_encounter["name"]
    level = int(selected_encounter["level"])
    encounter_slug = f"{selected_expansion}_{level}_{name}"

    # `load_encounter` is cached; never mutate the returned dict in-place.
    encounter_data = dict(load_encounter(encounter_slug, character_count) or {})
    # If caller requested the original enemy list, use it (respect invader limits).
    if use_original_enemies:
        enemies = encounter_data.get("original")
        # Validate invader limit
        limit = _get_invader_limit_for_level(level)
        invader_ids = _load_invader_enemy_ids()
        inv_count = 0
        if enemies and invader_ids is not None and limit >= 0:
            for e in enemies:
                if _coerce_enemy_id(e) in invader_ids:
                    inv_count += 1
                    if inv_count > limit:
                        return {
                            "ok": False,
                            "message": f"Original enemy list violates invader limit (level {level} max invaders = {limit}).",
                        }
        # Respect user's enemy inclusion toggles and authoritative mapping
        # Prefer caller-provided `settings` snapshot when available so callers
        # (including background threads) can avoid touching Streamlit runtime.
        if settings is None:
            settings = st.session_state.get("user_settings") or {}
        legacy_enemy_included = settings.get("enemy_included", {}) or {}
        campaign_enemy_included = settings.get("campaign_enemy_included", {}) or {}
        # merge legacy then campaign so campaign overrides
        effective_enemy_included = {}
        if isinstance(legacy_enemy_included, dict):
            effective_enemy_included.update(legacy_enemy_included)
        if isinstance(campaign_enemy_included, dict):
            effective_enemy_included.update(campaign_enemy_included)

        # merged toggle keys available in `effective_enemy_included`
        if enemies:
            for e in enemies:
                eid = _coerce_enemy_id(e)
                # checking original enemy
                # Exclude unmapped enemies
                if eid not in ENEMY_EXPANSIONS_BY_ID:
                    # unmapped enemy -> reject
                    return {"ok": False, "message": "Encounter references an unmapped enemy; cannot use original list."}
                # Check user toggle (use merged mapping)
                if str(eid) in effective_enemy_included and not bool(effective_enemy_included.get(str(eid))):
                    # disabled via toggles -> reject
                    return {"ok": False, "message": f"Original enemy list contains disabled enemy '{enemyNames.get(eid, eid)}'."}
        combo = selected_expansion
    else:
        # Pick random enemies (filtered by invader limit per encounter level)
        combo, enemies = pick_random_alternative(encounter_data, set(active_expansions), level)
        if not combo or not enemies:
            limit = _get_invader_limit_for_level(level)
            return {
                "ok": False,
                "message": f"No valid alternatives under current invader limit (level {level} max invaders = {limit}).",
            }

    # Handle Similar Soul Cost item replacements when user requested
    settings = settings or st.session_state.get("user_settings") or {}
    pref = settings.get("encounter_item_reward_mode", "Original")
    if pref in ("Similar Soul Cost", "Same Item Tier"):
        entries = ENCOUNTER_ORIGINAL_REWARDS.get((name, selected_expansion), []) or []
        if entries:
            # Use cached JSON loader to avoid re-reading files on every shuffle
            hand_path = _find_data_file("hand_items.json")
            hand_items = _load_json_list(str(hand_path)) if hand_path is not None else []
            armor_path = _find_data_file("armor.json")
            armor_items = _load_json_list(str(armor_path)) if armor_path is not None else []
            wu_path = _find_data_file("weapon_upgrades.json")
            weapon_upgrades = _load_json_list(str(wu_path)) if wu_path is not None else []
            au_path = _find_data_file("armor_upgrades.json")
            armor_upgrades = _load_json_list(str(au_path)) if au_path is not None else []

            selected_chars = (settings.get("selected_characters") or [])
            # Determine tier indices to use for each party member.
            # Support two shapes for persisted tiers:
            # 1) legacy: a single dict of stat->index (applies to all classes)
            # 2) per-class: mapping class_name -> {stat->index}
            default_tiers = {"str": 0, "dex": 0, "itl": 0, "fth": 0}
            persist = None
            if isinstance(settings, dict):
                persist = settings.get("cm_persist_tiers")
            if persist is None:
                persist = st.session_state.get("cm_persist_tiers")

            if not isinstance(persist, dict):
                persist = default_tiers

            party = []
            for cn in selected_chars:
                tiers_for_member = None
                # per-class mapping: { class_name: {stat: idx, ...}, ... }
                candidate = persist.get(cn) if isinstance(persist, dict) else None
                if isinstance(candidate, dict) and any(k in candidate for k in ("str", "dex", "itl", "fth")):
                    tiers_for_member = {k: int(candidate.get(k, 0)) for k in ("str", "dex", "itl", "fth")}

                # legacy single stat->idx mapping
                if tiers_for_member is None and all(k in persist for k in ("str", "dex", "itl", "fth")):
                    tiers_for_member = {k: int(persist.get(k, 0)) for k in ("str", "dex", "itl", "fth")}

                if tiers_for_member is None:
                    tiers_for_member = dict(default_tiers)

                party.append({"class_name": cn, "tier_indices": tiers_for_member})

            # Build a stable party signature so we can cache item cost computations.
            def _party_signature(chars, party_list):
                sig_parts = []
                for p in party_list:
                    c = p.get("class_name") or ""
                    t = p.get("tier_indices") or {}
                    sig_parts.append((c, int(t.get("str", 0)), int(t.get("dex", 0)), int(t.get("itl", 0)), int(t.get("fth", 0))))
                return tuple(sig_parts)

            party_sig = _party_signature(selected_chars, party)

            # Ensure a cache dict exists in session state
            ss = st.session_state
            ss.setdefault("item_cost_cache", {})
            cache_key = str(party_sig)
            cost_map = ss["item_cost_cache"].get(cache_key)
            if cost_map is None:
                # Compute cost for all items once for this party and store in cache
                cost_map = {}
                all_items = list(hand_items) + list(armor_items) + list(weapon_upgrades) + list(armor_upgrades)
                for it in all_items:
                    item_name = str(it.get("name") or "").strip()
                    stats = average_souls_to_equip(party, it.get("requirements", {})) if party else {"average": 0, "sum": 0}
                    cost = stats.get("average") if stats.get("average") is not None else stats.get("sum", 0)
                    cost_map[item_name] = cost
                ss["item_cost_cache"][cache_key] = cost_map

            # helper to normalize item metadata from either top-level or nested `source` keys
            def _meta(item):
                src = item.get("source") if isinstance(item, dict) else None
                return {
                    "type": (item.get("type") if item.get("type") is not None else (src.get("type") if isinstance(src, dict) else None)),
                    "legendary": (item.get("legendary") if item.get("legendary") is not None else (src.get("legendary") if isinstance(src, dict) else None)),
                    "entity": (item.get("entity") if item.get("entity") is not None else (src.get("entity") if isinstance(src, dict) else None)),
                    "expansions": (item.get("expansions") if item.get("expansions") is not None else (src.get("expansion") if isinstance(src, dict) else None))
                }

            replacements = {}
            for e in entries:
                orig_name = (e.get("text") or "").strip()
                if not orig_name:
                    continue

                orig_obj = None
                pool_items = []
                # locate original in pools
                for it in hand_items:
                    if str(it.get("name") or "").strip().lower() == orig_name.lower():
                        orig_obj = it
                        pool_items = hand_items
                        break
                if not orig_obj:
                    for it in armor_items:
                        if str(it.get("name") or "").strip().lower() == orig_name.lower():
                            orig_obj = it
                            pool_items = armor_items
                            break
                if not orig_obj:
                    # treat weapon and armor upgrades as a combined upgrade pool
                    for it in weapon_upgrades:
                        if str(it.get("name") or "").strip().lower() == orig_name.lower():
                            orig_obj = it
                            pool_items = list(weapon_upgrades) + list(armor_upgrades)
                            break
                if not orig_obj:
                    for it in armor_upgrades:
                        if str(it.get("name") or "").strip().lower() == orig_name.lower():
                            orig_obj = it
                            pool_items = list(weapon_upgrades) + list(armor_upgrades)
                            break

                if not orig_obj:
                    continue

                # If original item is locked to a class not in the current party, skip replacement
                m = _meta(orig_obj)
                orig_entity = m.get("entity")
                if orig_entity:
                    if isinstance(orig_entity, str) and orig_entity not in selected_chars:
                        continue
                    if isinstance(orig_entity, (list, tuple)) and not any(e in selected_chars for e in orig_entity):
                        continue

                # Exclude originals that are not allowed for this encounter level
                # Legendary items: When called from Campaign Mode, only allow after
                # the mini-boss has been defeated; otherwise (Encounter Mode) disallow on level 1.
                if m.get("legendary"):
                    if campaign_mode:
                        allowed_legendary = False
                        def _mini_defeated_in_state(s):
                            if not isinstance(s, dict):
                                return False
                            camp = s.get("campaign") or {}
                            nodes = camp.get("nodes") or []
                            for n in nodes:
                                if n.get("kind") == "boss" and n.get("stage") == "mini" and n.get("status") == "complete":
                                    return True
                            return False

                        v2 = st.session_state.get("campaign_v2_state")
                        v1 = st.session_state.get("campaign_v1_state")
                        if _mini_defeated_in_state(v2) or _mini_defeated_in_state(v1):
                            allowed_legendary = True

                        if not allowed_legendary:
                            continue
                    else:
                        if level == 1:
                            continue

                # Transposed items: If called from Campaign Mode, only allow after
                # mini-boss defeat; in Encounter Mode, disallow only on level 1.
                if (m.get("type") == "transposed"):
                    if campaign_mode:
                        allowed_transposed = False
                        def _mini_defeated_in_state(s):
                            if not isinstance(s, dict):
                                return False
                            camp = s.get("campaign") or {}
                            nodes = camp.get("nodes") or []
                            for n in nodes:
                                if n.get("kind") == "boss" and n.get("stage") == "mini" and n.get("status") == "complete":
                                    return True
                            return False

                        v2 = st.session_state.get("campaign_v2_state")
                        v1 = st.session_state.get("campaign_v1_state")
                        if _mini_defeated_in_state(v2) or _mini_defeated_in_state(v1):
                            allowed_transposed = True

                        if not allowed_transposed:
                            continue
                    else:
                        if level == 1:
                            continue

                # Items of type 'boss' or 'starter' are never valid rewards
                if m.get("type") in ("boss", "starter"):
                    continue

                # Invader items are only valid if they come from The Sunless City AND that expansion is enabled
                if m.get("type") == "invader":
                    orig_exps = set(m.get("expansions") or [])
                    if "The Sunless City" in orig_exps:
                        if "The Sunless City" not in set(active_expansions or []):
                            continue
                    else:
                        continue

                # Lookup precomputed cost from cache
                orig_cost = cost_map.get(str(orig_obj.get("name") or "").strip(), 0)

                # compute candidate costs
                cand_list = []
                cand_costs = []
                # Precompute active expansions set for filtering
                active_exps_set = set(active_expansions or [])

                for it in pool_items:
                    # Exclude items tied to a class not present in the current party
                    im = _meta(it)
                    it_entity = im.get("entity")
                    if it_entity:
                        if isinstance(it_entity, str) and it_entity not in selected_chars:
                            # skip candidate not relevant to party
                            continue
                        if isinstance(it_entity, (list, tuple)) and not any(e in selected_chars for e in it_entity):
                            continue

                    # Exclude items that are disallowed by type
                    it_type = im.get("type")
                    if it_type in ("boss", "starter"):
                        continue

                    # Legendary items: When called from Campaign Mode, only allow
                    # after the mini-boss has been defeated; otherwise disallow on level 1.
                    if im.get("legendary"):
                        if campaign_mode:
                            allowed_legendary = False
                            def _mini_defeated_in_state(s):
                                if not isinstance(s, dict):
                                    return False
                                camp = s.get("campaign") or {}
                                nodes = camp.get("nodes") or []
                                for n in nodes:
                                    if n.get("kind") == "boss" and n.get("stage") == "mini" and n.get("status") == "complete":
                                        return True
                                return False

                            v2 = st.session_state.get("campaign_v2_state")
                            v1 = st.session_state.get("campaign_v1_state")
                            if _mini_defeated_in_state(v2) or _mini_defeated_in_state(v1):
                                allowed_legendary = True

                            if not allowed_legendary:
                                continue
                        else:
                            if level == 1:
                                continue

                    # Transposed items: If called from Campaign Mode, only allow after
                    # mini-boss defeat; in Encounter Mode, disallow only on level 1.
                    if (im.get("type") == "transposed"):
                        if campaign_mode:
                            allowed_transposed = False
                            def _mini_defeated_in_state(s):
                                if not isinstance(s, dict):
                                    return False
                                camp = s.get("campaign") or {}
                                nodes = camp.get("nodes") or []
                                for n in nodes:
                                    if n.get("kind") == "boss" and n.get("stage") == "mini" and n.get("status") == "complete":
                                        return True
                                return False

                            v2 = st.session_state.get("campaign_v2_state")
                            v1 = st.session_state.get("campaign_v1_state")
                            if _mini_defeated_in_state(v2) or _mini_defeated_in_state(v1):
                                allowed_transposed = True

                            if not allowed_transposed:
                                continue
                        else:
                            if level == 1:
                                continue

                    # Invader items: only allowed if they are from The Sunless City and that expansion is enabled
                    if it_type == "invader":
                        it_exps = set(it.get("expansions") or [])
                        if "The Sunless City" in it_exps:
                            if "The Sunless City" not in active_exps_set:
                                continue
                        else:
                            continue

                    # Exclude items whose expansions are all disabled
                    it_exps = set(im.get("expansions") or [])
                    if it_exps and it_exps.isdisjoint(active_exps_set):
                        continue

                    cost = cost_map.get(str(it.get("name") or "").strip(), 0)
                    cand_list.append(it)
                    cand_costs.append(cost)

                chosen = None
                if pref == "Similar Soul Cost":
                    pct = 0.10
                    candidates = []
                    while True:
                        candidates = [it for it, c in zip(cand_list, cand_costs) if abs(c - orig_cost) <= max(1, orig_cost * pct)]
                        if len(candidates) > 1 or pct >= 1.0:
                            break
                        pct += 0.05

                    if not candidates:
                        candidates = cand_list

                    # exclude exact original from candidates so replacements are meaningful
                    candidates = [it for it in candidates if str(it.get("name") or "").strip().lower() != orig_name.lower()]
                    chosen = choice(candidates) if candidates else None

                else:  # Same Item Tier
                    # Build candidate list (exclude original from final selection)
                    candidates = list(cand_list)
                    costs = list(cand_costs)
                    total = len(candidates)
                    if total:
                        import math

                        # Pair and sort by cost ascending
                        paired = sorted(zip(candidates, costs), key=lambda x: (x[1] or 0))
                        n = total
                        first_bound = math.ceil(n / 3)
                        second_bound = math.ceil(2 * n / 3)

                        # find original's slot; prefer matching item name, fall back to cost position
                        orig_index = None
                        for idx, (it, c) in enumerate(paired):
                            if str(it.get("name") or "").strip().lower() == orig_name.lower():
                                orig_index = idx
                                break
                        if orig_index is None:
                            # approximate by cost
                            for idx, (it, c) in enumerate(paired):
                                if (c or 0) >= orig_cost:
                                    orig_index = idx
                                    break
                        if orig_index is None:
                            orig_index = n - 1

                        # determine tier for original
                        if orig_index < first_bound:
                            tier_slice = paired[0:first_bound]
                        elif orig_index < second_bound:
                            tier_slice = paired[first_bound:second_bound]
                        else:
                            tier_slice = paired[second_bound:]

                        # choose from same tier, excluding the original
                        tier_candidates = [it for it, c in tier_slice if str(it.get("name") or "").strip().lower() != orig_name.lower()]
                        if tier_candidates:
                            chosen = choice(tier_candidates)

                if chosen:
                    replacements[orig_name] = chosen.get("name")

            if replacements:
                encounter_data = dict(encounter_data) if encounter_data is not None else {}
                encounter_data.setdefault("_shuffled_reward_replacements", {}).update(replacements)

    # Allow callers (notably Setup tab retry loops) to choose enemies without
    # paying the cost of PIL rendering every attempt.
    if not render_image:
        return {
            "ok": True,
            "encounter_data": encounter_data,
            "encounter_name": name,
            "encounter_level": level,
            "expansion": selected_expansion,
            "enemies": enemies,
            "expansions_used": combo.split(",") if isinstance(combo, str) else combo,
        }

    card_img = generate_encounter_image(
        selected_expansion, level, name, encounter_data, enemies, use_edited
    )

    buf = BytesIO()
    card_img.save(buf, format="PNG")
    buf.seek(0)

    return {
        "ok": True,
        "buf": buf,
        "card_img": card_img,
        "encounter_data": encounter_data,
        "encounter_name": name,
        "encounter_level": level,
        "expansion": selected_expansion,
        "enemies": enemies,
        "expansions_used": combo.split(",") if isinstance(combo, str) else combo,
    }


def get_alternatives(data, active_expansions):
    """Return all valid alternative enemy sets based on expansions."""
    valid_alts = {}
    # Normalize active expansions to handle naming/casing/whitespace mismatches
    active_norm = set(_norm_name(a) for a in (active_expansions or ()))
    for combo, alt_sets in data.get("alternatives", {}).items():
        parts = [p for p in combo.split(",") if p is not None]
        combo_set = set(_norm_name(p) for p in parts)
        if combo_set.issubset(active_norm):
            valid_alts[combo] = alt_sets
    return valid_alts


def analyze_encounter_availability(selected_encounter: dict, character_count: int, active_expansions, settings=None) -> dict:
    """Return availability info for the given encounter.

    Returns a dict with:
      - 'num_viable_alternatives': int
      - 'original_viable': bool
    """
    expansion = selected_encounter["expansion"]
    level = int(selected_encounter["level"])
    name = selected_encounter["name"]
    encounter_slug = f"{expansion}_{level}_{name}"

    # Prefer caller-provided `settings` snapshot when available so callers
    # can avoid touching Streamlit runtime.
    if settings is None:
        settings = st.session_state.get("user_settings") or {}

    active_expansions_norm = tuple(sorted(_norm_name(a) for a in (active_expansions or ())))
    disabled_enemy_ids = _disabled_enemy_ids_signature(settings)
    inv_limit = _get_invader_limit_for_level_with_settings(level, settings)

    total, original_viable = _analyze_encounter_availability_cached(
        encounter_slug,
        level,
        int(character_count),
        active_expansions_norm,
        disabled_enemy_ids,
        int(inv_limit),
    )

    return {"num_viable_alternatives": int(total), "original_viable": bool(original_viable)}


def pick_random_alternative(data, active_expansions, encounter_level: int):
    """Randomly pick one valid alternative enemy set (respects invader limit)."""
    valid_alts = get_alternatives(data, active_expansions)
    if not valid_alts:
        return None, None

    invader_limit = _get_invader_limit_for_level(int(encounter_level))
    invader_ids = _load_invader_enemy_ids()
    # debug logging removed

    # Read settings + build merged enemy toggles once.
    settings = st.session_state.get("user_settings") or {}
    legacy_enemy_included = settings.get("enemy_included", {}) or {}
    campaign_enemy_included = settings.get("campaign_enemy_included", {}) or {}
    effective_enemy_included = {}
    if isinstance(legacy_enemy_included, dict):
        effective_enemy_included.update(legacy_enemy_included)
    if isinstance(campaign_enemy_included, dict):
        effective_enemy_included.update(campaign_enemy_included)

    filtered = {}
    for combo, alt_sets in valid_alts.items():
        kept = []
        for enemies in alt_sets or []:
            if enemies is None:
                continue
            # enemies should be a list[int], but tolerate other iterables
            enemy_list = list(enemies)

            # merged toggle keys available in `effective_enemy_included`

            inv_count = 0
            skip = False
            if invader_ids and invader_limit >= 0:
                for e in enemy_list:
                    eid = _coerce_enemy_id(e)
                    # If enemy not present in authoritative mapping, skip
                    if eid not in ENEMY_EXPANSIONS_BY_ID:
                        # unmapped enemy -> skip candidate
                        skip = True
                        break
                    if eid in invader_ids:
                        inv_count += 1
                        if inv_count > invader_limit:
                            skip = True
                            break
                    if str(eid) in effective_enemy_included and not bool(effective_enemy_included.get(str(eid))):
                        skip = True
                        break
            else:
                # Still enforce mapping and user toggles even if invader limit not checked
                for e in enemy_list:
                    eid = _coerce_enemy_id(e)
                    if eid not in ENEMY_EXPANSIONS_BY_ID:
                        skip = True
                        break
                    if str(eid) in effective_enemy_included and not bool(effective_enemy_included.get(str(eid))):
                        skip = True
                        break

            if not skip and inv_count <= invader_limit:
                kept.append(enemy_list)

        if kept:
            filtered[combo] = kept

    if not filtered:
        return None, None

    combo = choice(list(filtered.keys()))
    enemies = choice(filtered[combo])
    return combo, enemies
