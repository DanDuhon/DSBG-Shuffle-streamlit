import streamlit as st
import re
import base64
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from copy import deepcopy

from ui.events_tab.events_logic import EVENT_BEHAVIOR_MODIFIERS
from ui.encounters_tab.encounters_logic import ENCOUNTER_BEHAVIOR_MODIFIERS
from ui.encounters_tab.encounters_assets import enemyNames
from core.encounter_rules import (
    make_encounter_key,
    get_rules_for_encounter,
    get_upcoming_rules_for_encounter,
)
from core.encounter_triggers import (
    EncounterTrigger,
    get_triggers_for_encounter,
)
from ui.behavior_decks_tab.behavior_decks_generation import (
    render_data_card_cached,
    build_behavior_catalog,
)
from ui.behavior_decks_tab.behavior_decks_logic import load_behavior
from ui.behavior_decks_tab.behavior_decks_models import BehaviorEntry
from ui.behavior_decks_tab.behavior_decks_assets import BEHAVIOR_CARDS_PATH

# ---------------------------------------------------------------------
# Text + template helpers
# ---------------------------------------------------------------------

TIMER_ICON_PATH = Path("assets") / "timer.png"
BEHAVIOR_CARD_DIR = Path("assets") / "behavior_cards"

# {enemy1}, {enemy2}, etc.
_ENEMY_PATTERN = re.compile(r"{enemy(\d+)}")
# {enemy1_plural} explicit plural
_ENEMY_PLURAL_PATTERN = re.compile(r"{enemy(\d+)_plural}")
# {enemy1}s -> pluralize the enemy name
_ENEMY_S_PATTERN = re.compile(r"{enemy(\d+)}s\b")
# {players+3}, {players+1}, etc.
_PLAYERS_PLUS_PATTERN = re.compile(r"{players\+(\d+)}")
# {enemy_list:1,2,3} -> grouped phrase from multiple enemy indices
_ENEMY_LIST_PATTERN = re.compile(r"{enemy_list:([^}]+)}")

_VOWELS = set("AEIOUaeiou")

# ---------------------------------------------------------------------
# Hard timer limits for encounters (no visible trigger)
# ---------------------------------------------------------------------

# Values here are *offsets from party size*:
#   actual_limit = player_count + offset
_HARD_TIMER_LIMITS = {
    # Corvian Host: "Kill all enemies before the Timer reaches {players+5}"
    "Corvian Host|Painted World of Ariamis": {
        "default": 5,   # limit = players + 5
    },
    # Add more encounters here later if needed
}

# Optional caps for phrases like "on {players+0} tiles" in objective text.
# Values are the maximum number of tiles that physically exist in the encounter.
OBJECTIVE_TILE_CAPS = {
    # Example: whatever encounter this objective belongs to
    # "Some Encounter Name|Painted World of Ariamis": 3,
    "Central Plaza|Painted World of Ariamis": 3,
}

# Mapping from encounter key -> variant ("default"/"edited") -> objective/trial templates.
# Each template can use {enemyN}, {players}, {players+N}, etc.
ENCOUNTER_OBJECTIVES = {
    "Cloak and Feathers|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
        },
    },
    "Frozen Sentries|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "No Safe Haven|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
    "Painted Passage|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Promised Respite|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Roll Out|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Skittering Frenzy|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Survive until the Timer reaches {players+2}.",
            ],
            "trials": [
            ],
        },
    },
    "The First Bastion|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Activate the lever 3 times. Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy4}."
            ],
        },
        "edited": {
            "objectives": [
                "Activate the lever 3 times. Reach the exit node.",
            ],
            "trials": [
                "Kill a {enemy4}."
            ],
        },
    },
    "Unseen Scurrying|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Abandoned and Forgotten|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reveal three blank trap tokens.",
            ],
            "trials": [
            ],
        },
    },
    "Cold Snap|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy4}."
            ],
        },
    },
    "Corrupted Hovel|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Kill all enemies before the Timer reaches {players+2}"
            ],
        },
    },
    "Distant Tower|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
                "Kill the {enemy5}."
            ],
        },
    },
    "Gnashing Beaks|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Open the chest. Reach the exit node.",
            ],
            "trials": [
                "Open the chest before the Timer reaches {players+3}."
            ],
        },
    },
    "Inhospitable Ground|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Montrous Maw|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy1}.",
            ],
            "trials": [
            ],
        },
    },
    "Skeletal Spokes|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Survive until the Timer reaches {players+2}.",
            ],
            "trials": [
            ],
        },
    },
    "Snowblind|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Central Plaza|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies on {players+0} tiles. Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies before the Timer reaches {players+5}.",
            ],
            "trials": [
            ],
        },
    },
    "Deathly Freeze|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
            ],
        },
    },
    "Draconic Decay|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reach the exit node.",
            ],
            "trials": [
            ],
        },
    },
    "Eye of the Storm|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy6}.",
            ],
            "trials": [
            ],
        },
    },
    "Frozen Revolutions|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Activate both levers. Reach the exit node.",
            ],
            "trials": [
                "No barrels are discarded."
            ],
        },
    },
    "The Last Bastion|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill all enemies.",
            ],
            "trials": [
                "Kill the {enemy1} first."
            ],
        },
    },
    "Trecherous Tower|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Reveal four blank trap tokens.",
            ],
            "trials": [
            ],
        },
    },
    "Velka's Chosen|Painted World of Ariamis": {
        "default": {
            "objectives": [
                "Kill the {enemy3}.",
            ],
            "trials": [
            ],
        },
    },
}


def _safe_enemy_name(enemy_names: List[str], idx_1_based: int) -> str:
    idx = idx_1_based - 1
    if 0 <= idx < len(enemy_names):
        return enemy_names[idx]
    return f"[enemy{idx_1_based}?]"


# Hard-coded irregular plurals – extend as needed
_IRREGULAR_ENEMY_PLURALS = {
}


def _pluralize_enemy_name(name: str) -> str:
    """Best-effort pluralization with a small irregulars table."""
    if name in _IRREGULAR_ENEMY_PLURALS:
        return _IRREGULAR_ENEMY_PLURALS[name]

    parts = name.split()
    if not parts:
        return name

    last = parts[-1]
    lower = last.lower()

    # Swordsman -> Swordsmen
    if lower.endswith("man"):
        plural_last = last[:-3] + "men"
    # Hollow -> Hollows (default)
    # Knights -> Knights (we won't get here because of irregulars)
    elif lower.endswith(("s", "x", "z", "ch", "sh")):
        plural_last = last + "es"
    # Party -> Parties
    elif lower.endswith("y") and len(last) > 1 and last[-2].lower() not in "aeiou":
        plural_last = last[:-1] + "ies"
    else:
        plural_last = last + "s"

    return " ".join(parts[:-1] + [plural_last])


def _apply_enemy_placeholders(template: str, enemy_names: List[str]) -> str:
    """Replace {enemyN}, {enemyN_plural}, and {enemyN}s with proper names/plurals."""

    # 1) {enemyN}s -> plural of the enemy name
    def _sub_plural_s(match: re.Match) -> str:
        idx_1_based = int(match.group(1))
        base = _safe_enemy_name(enemy_names, idx_1_based)
        return _pluralize_enemy_name(base)

    text = _ENEMY_S_PATTERN.sub(_sub_plural_s, template)

    # 2) {enemyN_plural} -> plural form
    def _sub_plural(match: re.Match) -> str:
        idx_1_based = int(match.group(1))
        base = _safe_enemy_name(enemy_names, idx_1_based)
        return _pluralize_enemy_name(base)

    text = _ENEMY_PLURAL_PATTERN.sub(_sub_plural, text)

    # 3) {enemyN} -> single name
    def _sub_single(match: re.Match) -> str:
        idx_1_based = int(match.group(1))
        return _safe_enemy_name(enemy_names, idx_1_based)

    text = _ENEMY_PATTERN.sub(_sub_single, text)
    return text


def _apply_player_placeholders(text: str, player_count: int) -> str:
    """Handle {players} and {players+N} placeholders."""

    def _sub_players_plus(m: re.Match) -> str:
        offset = int(m.group(1))
        return str(player_count + offset)

    text = _PLAYERS_PLUS_PATTERN.sub(_sub_players_plus, text)
    return text.replace("{players}", str(player_count))


def _format_enemy_list_from_indices(indices_str: str, enemy_names: List[str]) -> str:
    """
    Given something like '1,2,3,4' and the enemy_names list, return a phrase like:
      - 'four Phalanx Hollows'
      - 'two Phalanx Hollows and two Hollow Soldiers'
      - 'both Phalanx Hollows' (if exactly two of one type)
    """
    # Parse "1,2,3,4" -> [1, 2, 3, 4]
    idxs: list[int] = []
    for part in indices_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idxs.append(int(part))
        except ValueError:
            continue

    # Map indices to names (1-based indices)
    names: list[str] = []
    for idx_1 in idxs:
        idx0 = idx_1 - 1
        if 0 <= idx0 < len(enemy_names):
            names.append(enemy_names[idx0])

    # Group by name, preserving first-seen order
    groups: list[dict] = []
    seen: dict[str, dict] = {}
    for name in names:
        if name in seen:
            seen[name]["count"] += 1
        else:
            g = {"name": name, "count": 1}
            seen[name] = g
            groups.append(g)

    if not groups:
        return ""

    def number_word(n: int) -> str:
        words = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
        }
        return words.get(n, str(n))

    parts: list[str] = []
    for g in groups:
        n = g["count"]
        name = g["name"]
        if n == 1:
            phrase = name
        elif n == 2 and len(groups) == 1:
            # Exactly two of a single enemy type -> 'both Xs'
            phrase = f"both {_pluralize_enemy_name(name)}"
        else:
            phrase = f"{number_word(n)} {_pluralize_enemy_name(name)}"
        parts.append(phrase)

    # Natural-language join
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


# For collapsing things like "Phalanx Hollow, Phalanx Hollow, ... killed."
_DUPLICATE_ENEMY_LIST_PATTERN = re.compile(
    r"^(?P<names>.+?) killed(\.)?$", re.IGNORECASE
)


def _collapse_duplicate_enemy_list(text: str) -> str:
    """
    Collapse 'Phalanx Hollow, Phalanx Hollow, Phalanx Hollow, and Phalanx Hollow killed.'
    into 'All Phalanx Hollows killed.' and similar patterns.
    """
    stripped = text.strip()
    m = _DUPLICATE_ENEMY_LIST_PATTERN.match(stripped)
    if not m:
        return text

    names_str = m.group("names")
    # Split on commas and "and"
    parts = re.split(r",\s*|\s+and\s+", names_str)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return text

    first = parts[0]
    if not all(p == first for p in parts):
        return text

    count = len(parts)
    plural = _pluralize_enemy_name(first)
    if count == 2:
        prefix = "two"
    elif count == 3:
        prefix = "three"
    elif count == 4:
        prefix = "four"
    if names_str[0].isupper():
        prefix = prefix.capitalize()

    out = f"{prefix} {plural} killed"
    if stripped.endswith("."):
        out += "."
    return out


_TILE_PHRASE_PATTERN = re.compile(r"\bon\s+(\d+)\s+tiles\b", re.IGNORECASE)


def _cap_tiles_in_text(text: str, max_tiles: int) -> str:
    """
    If text contains phrases like 'on 4 tiles' but the encounter only has
    max_tiles (e.g. 3), clamp the number to max_tiles.

    E.g. 'Kill all enemies on 4 tiles.' -> 'Kill all enemies on 3 tiles.'
    """

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if n <= max_tiles:
            return m.group(0)
        return m.group(0).replace(str(n), str(max_tiles), 1)

    return _TILE_PHRASE_PATTERN.sub(repl, text)


def _fix_indefinite_articles(text: str) -> str:
    """
    Fix simple 'a'/'an' issues like 'a Alonne Knight' -> 'an Alonne Knight'.
    This is intentionally lightweight, not full English grammar.
    """
    pattern = re.compile(r"\b(a|an)\s+([A-Za-z])")

    def repl(match: re.Match) -> str:
        article, first_char = match.group(1), match.group(2)
        if first_char in _VOWELS:
            return f"an {first_char}"
        else:
            return f"a {first_char}"

    return pattern.sub(repl, text)


def _render_text_template(
    template: str,
    enemy_names: List[str],
    *,
    value: Optional[int] = None,
    player_count: Optional[int] = None,
) -> str:
    text = template

    # 1) {enemy_list:1,2,3} – group and format those enemies as a phrase
    def _sub_enemy_list(m: re.Match) -> str:
        indices_str = m.group(1)
        return _format_enemy_list_from_indices(indices_str, enemy_names)

    text = _ENEMY_LIST_PATTERN.sub(_sub_enemy_list, text)

    # 2) Regular enemy placeholders ({enemyN}, {enemyN}s, {enemyN_plural})
    text = _apply_enemy_placeholders(text, enemy_names)

    # 3) Players and players+N
    if player_count is None:
        player_count = _get_player_count()
    if player_count is not None:
        text = _apply_player_placeholders(text, player_count)

    # 4) {value} for counters / numerics
    if value is not None:
        text = text.replace("{value}", str(value))

    # 5) Grammar cleanups
    text = _collapse_duplicate_enemy_list(text)
    text = _fix_indefinite_articles(text)

    return text


# ---------------------------------------------------------------------
# Helpers: state + ids
# ---------------------------------------------------------------------


def _get_encounter_id(encounter: dict):
    """Best-effort way to identify the current encounter for resetting state."""
    for key in ("id", "slug", "encounter_slug", "encounter_name"):
        if key in encounter:
            return encounter[key]
    return None


def _get_player_count() -> int:
    try:
        pc = int(st.session_state.get("player_count", 1))
    except Exception:
        pc = 1
    return max(pc, 1)


# ---------------------------------------------------------------------
# Special timer behaviour for specific encounters
# ---------------------------------------------------------------------

# Per-encounter / per-variant timer tweaks:
# - manual_increment: don't auto-increase Timer on player→enemy; show a button instead
# - reset_button: show a button that resets Timer to 0 (without changing phase)
_SPECIAL_TIMER_BEHAVIORS = {
    "Eye of the Storm|Painted World of Ariamis": {
        "edited": {
            "manual_increment": True,
            "manual_increment_label": "Increase Timer (no enemies on active tiles)",
            "manual_increment_help": (
                "Only click this at the end of a character's turn if there are no "
                "enemies on any active tile."
            ),
            "manual_increment_log": "Timer increased (no enemies on active tiles).",
        }
    },
    "Corvian Host|Painted World of Ariamis": {
        "default": {
            "reset_button": True,
            "reset_button_label": "Tile made active (reset Timer)",
            "reset_button_help": (
                "When a tile is made active, reset the Timer to 0 (objective: "
                "kill all enemies before time runs out)."
            ),
            "reset_button_log": "Timer reset to 0 because a tile was made active.",
        }
    },
}


def _get_timer_behavior_for_encounter(encounter: dict, settings: dict) -> dict:
    """
    Return a small config dict describing any special timer behavior
    for the current encounter (if any).
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)

    variants = _SPECIAL_TIMER_BEHAVIORS.get(encounter_key)
    if not variants:
        return {}

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default", {})


def _compute_stop_on_timer_objective(encounter: dict, settings: dict, play_state: dict) -> bool:
    """
    Decide if Next Turn should be disabled because a timer-based
    objective has expired.

    Sources:
    - Visible timer_objective triggers (if any).
    - Hidden encounter-level limits from _HARD_TIMER_LIMITS.
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)
    player_count = _get_player_count()

    # 1) Visible timer_objective triggers (if you ever use them)
    triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )
    if triggers:
        for trig in triggers:
            if (
                trig.kind == "timer_objective"
                and trig.stop_on_complete
                and trig.timer_target is not None
            ):
                # For triggers we treat timer_target as an absolute value.
                if play_state["timer"] >= trig.timer_target:
                    return True

    # 2) Hidden encounter-level hard timer caps
    caps = _HARD_TIMER_LIMITS.get(encounter_key)
    if caps:
        # Pick default vs edited variant if present
        offset = caps.get("edited" if edited else "default")
        if offset is not None:
            limit = player_count + offset
            if play_state["timer"] >= limit:
                return True

    return False


def _ensure_play_state(encounter_id):
    """
    Keep a small piece of state for the Play tab.
    Reset automatically when the active encounter changes.
    """
    state = st.session_state.get("encounter_play")

    if (not state) or (state.get("encounter_id") != encounter_id):
        state = {
            "encounter_id": encounter_id,
            "phase": "enemy",   # "enemy" | "player"
            "timer": 0,         # starts at 0, increments after player phase
            "log": [],
        }
        st.session_state["encounter_play"] = state

    return state


def _apply_pending_action(play_state: dict, timer_behavior: dict) -> None:
    """
    If the last run scheduled a pending turn action (next, prev, reset),
    apply it *before* rendering anything.
    """
    action = st.session_state.pop("encounter_play_pending_action", None)

    disable_auto_timer = bool(timer_behavior.get("manual_increment", False))

    if action == "next":
        _advance_turn(play_state, disable_auto_timer=disable_auto_timer)
    elif action == "prev":
        _previous_turn(play_state)
    elif action == "reset":
        _reset_play_state(play_state)


def _log(play_state: dict, text: str):
    play_state.setdefault("log", []).append(
        {
            "timer": play_state.get("timer", 0),
            "phase": play_state.get("phase", "enemy"),
            "text": text,
            "time": datetime.now().strftime("%H:%M"),
        }
    )


def _detect_edited_flag(encounter_key: str, encounter: dict, settings: dict) -> bool:
    """
    Best-effort way to figure out whether this encounter is using the
    'edited' version. Adjust to match how your Setup tab stores the toggle.
    """
    # 1) Encounter dict itself
    if isinstance(encounter.get("edited"), bool):
        return encounter["edited"]

    # 2) Session state override (if you set one from Setup)
    if isinstance(st.session_state.get("current_encounter_edited"), bool):
        return st.session_state["current_encounter_edited"]

    # 3) Settings-level toggle keyed by encounter key
    edited_toggles = settings.get("edited_toggles", {})
    return bool(edited_toggles.get(encounter_key, False))


def _get_behavior_entry_by_name() -> dict[str, BehaviorEntry]:
    """
    Build (or reuse) a mapping from behavior name -> BehaviorEntry.

    Uses the same catalog that the Behavior Decks tab uses, so we get
    consistent order_num values and file paths.
    """
    # Cache the catalog in session_state so we don't rebuild it every rerun
    if "behavior_catalog" not in st.session_state:
        st.session_state["behavior_catalog"] = build_behavior_catalog()

    catalog: dict[str, list[BehaviorEntry]] = st.session_state["behavior_catalog"]

    if "behavior_entry_by_name" not in st.session_state:
        by_name: dict[str, BehaviorEntry] = {}
        for entries in catalog.values():
            for entry in entries:
                # BehaviorEntry.name is what Behavior Decks uses as the UI label
                # If duplicates exist across categories, first one wins.
                if entry.name not in by_name:
                    by_name[entry.name] = entry
        st.session_state["behavior_entry_by_name"] = by_name

    return st.session_state["behavior_entry_by_name"]


def _get_sorted_enemy_names(encounter: dict) -> list[str]:
    """
    Return distinct enemy names for this encounter, sorted by
    descending order_num (higher order_num first).

    - Uses _get_enemy_display_names() to respect the shuffled encounter enemies.
    - Looks up BehaviorEntry.order_num via the shared behavior catalog.
    """
    raw_names = _get_enemy_display_names(encounter)
    if not raw_names:
        return []

    entry_by_name = _get_behavior_entry_by_name()

    # Preserve first-appearance per encounter for tie-breaking
    seen: set[str] = set()
    info: list[tuple[str, int, int]] = []  # (name, order_num, first_index)

    for idx, name in enumerate(raw_names):
        if name in seen:
            continue
        seen.add(name)

        entry = entry_by_name.get(name)
        # Default order_num matches build_behavior_catalog's fallback (10)
        order_num = entry.order_num if entry is not None else 10
        info.append((name, order_num, idx))

    # Sort: primary = order_num desc, secondary = encounter order asc
    info.sort(key=lambda t: (-t[1], t[2]))
    return [name for (name, _, _) in info]


def _get_behavior_catalog() -> dict[str, list[BehaviorEntry]]:
    """
    Reuse the Behavior Decks catalog so we don't rescan the filesystem
    on every rerun.
    """
    cache_key = "behavior_catalog"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = build_behavior_catalog()
    return st.session_state[cache_key]


def _get_enemy_display_names(encounter: dict) -> list[str]:
    """
    Return human-readable names for the shuffled enemies in this encounter.

    Assumes Setup stored the shuffled list on encounter["enemies"].
    Replace the internals with your real enemy metadata lookup instead of str().
    """
    enemy_ids = encounter.get("enemies") or []

    names: list[str] = []
    for eid in enemy_ids:
        if isinstance(eid, dict):
            names.append(eid.get("name") or eid.get("id") or str(eid))
        else:
            names.append(enemyNames[eid])

    return names


def _get_enemy_behavior_entries_for_encounter(encounter: dict) -> list[BehaviorEntry]:
    """
    Take the shuffled encounter enemies and return a list of unique
    BehaviorEntry objects in descending order_num (no duplicates).

    This lets us show one behavior stack per distinct enemy type.
    """
    enemy_names = _get_enemy_display_names(encounter)
    if not enemy_names:
        return []

    # Preserve first-appearance order but drop duplicates
    seen: set[str] = set()
    ordered_unique_names: list[str] = []
    for name in enemy_names:
        if name not in seen:
            seen.add(name)
            ordered_unique_names.append(name)

    catalog = _get_behavior_catalog()

    # Flatten the catalog into name → BehaviorEntry
    by_name: dict[str, BehaviorEntry] = {}
    for entries in catalog.values():
        for entry in entries:
            # BehaviorEntry.name is what the Behavior Decks UI uses
            if entry.name not in by_name:
                by_name[entry.name] = entry

    result: list[BehaviorEntry] = []
    for name in ordered_unique_names:
        entry = by_name.get(name)
        if entry:
            result.append(entry)

    return result


def _get_objective_config(encounter: dict, settings: dict) -> Optional[dict]:
    """
    Return the objective config dict for this encounter, or None if not defined.

    The dict has shape:
      {
        "objectives": [template_str, ...],
        "trials": [template_str, ...],
      }
    """
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)
    variants = ENCOUNTER_OBJECTIVES.get(encounter_key)
    if not variants:
        return None

    if edited and "edited" in variants:
        return variants["edited"]

    return variants.get("default")


def _render_objectives(encounter: dict, settings: dict) -> None:
    cfg = _get_objective_config(encounter, settings)
    if not cfg:
        return

    enemy_names = _get_enemy_display_names(encounter)
    player_count = _get_player_count()

    # Figure out if there is a tile cap for this encounter
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)
    tile_cap = OBJECTIVE_TILE_CAPS.get(encounter_key)

    primary = cfg.get("objectives") or []
    trials = cfg.get("trials") or []

    if len(primary) + len(trials) == 0:
        return

    st.markdown("#### Objective")

    # Main objectives
    for template in primary:
        text = _render_text_template(
            template,
            enemy_names,
            player_count=player_count,
        )
        if tile_cap is not None:
            text = _cap_tiles_in_text(text, tile_cap)
        st.markdown(f"- {text}", unsafe_allow_html=True)

    if trials:
        st.markdown("#### Trial")
        for template in trials:
            text = _render_text_template(
                template,
                enemy_names,
                player_count=player_count,
            )
            if tile_cap is not None:
                text = _cap_tiles_in_text(text, tile_cap)
            st.markdown(f"- {text}", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Rules + upcoming rules
# ---------------------------------------------------------------------


def _render_rules(encounter: dict, settings: dict, play_state: dict) -> None:
    st.markdown("#### Rules")

    # Build encounter key (name + expansion or however your data is structured)
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)

    # Rules that apply *right now*
    current_rules = get_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        timer=play_state["timer"],
        phase=play_state["phase"],  # "enemy" or "player"
    )

    enemy_names = _get_enemy_display_names(encounter)
    player_count = _get_player_count()

    if not current_rules:
        st.caption("No rules to show for this encounter in the current state.")
    else:
        for rule in current_rules:
            text = _render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            st.markdown(f"- {text}", unsafe_allow_html=True)

    # --- Upcoming rules: inline section (no expander) ---
    upcoming = get_upcoming_rules_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
        current_timer=play_state["timer"],
        max_lookahead=3,  # show next 3 Timer step(s); tweak if you like
    )

    if upcoming:
        st.markdown("**Upcoming rules**")

        for trigger_timer, rule in upcoming:
            phase_label = {
                "enemy": "Enemy Phase",
                "player": "Player Phase",
                "any": "Any Phase",
            }.get(rule.phase, "Any Phase")

            text = _render_text_template(
                rule.template,
                enemy_names,
                player_count=player_count,
            )
            st.markdown(
                f"- **Timer {trigger_timer} · {phase_label}** — {text}",
                unsafe_allow_html=True,
            )


def _ensure_trigger_state(encounter_key: str, triggers: list[EncounterTrigger]) -> dict:
    """
    Ensure we have a state dict for this encounter's triggers in session_state.
    """
    all_state = st.session_state.setdefault("encounter_triggers", {})
    enc_state = all_state.setdefault(encounter_key, {})

    for trig in triggers:
        if trig.id not in enc_state:
            if trig.kind in ("counter", "numeric"):
                enc_state[trig.id] = int(trig.default_value or 0)
            elif trig.kind == "checkbox":
                enc_state[trig.id] = bool(trig.default_value or False)
            elif trig.kind == "timer_objective":
                enc_state[trig.id] = False  # could track "acknowledged" if you want

    return enc_state


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------


def render(settings: dict) -> None:
    """
    Encounter Play tab.

    Assumes:
    - Setup tab has populated st.session_state.current_encounter
    - Events tab has optionally populated st.session_state.encounter_events
    """
    if "current_encounter" not in st.session_state:
        st.info("Use the **Setup** tab to select and shuffle an encounter first.")
        return

    encounter = st.session_state.current_encounter
    encounter_id = _get_encounter_id(encounter)
    play_state = _ensure_play_state(encounter_id)

    # Per-encounter special timer behaviour (manual increment, reset button, etc.)
    timer_behavior = _get_timer_behavior_for_encounter(encounter, settings)

    # Apply any pending action (from button click in the previous run)
    _apply_pending_action(play_state, timer_behavior)

    # Decide if any timer objective wants to stop progression
    stop_on_timer_objective = _compute_stop_on_timer_objective(
        encounter, settings, play_state
    )

    # -----------------------------------------------------------------
    # Main layout: 2 columns
    # Left: objectives + timer/phase + controls + rules + triggers + events + log
    # Right: enemy behavior cards (placeholder for now)
    # -----------------------------------------------------------------
    col_left, col_mid, col_right = st.columns([1, 1, 1], gap="large")

    with col_left:
        timer_phase_container = st.container()
        controls_container = st.container()

        # Timer + phase (top row)
        with timer_phase_container:
            _render_timer_and_phase(play_state)

        # Turn controls (Next Turn can be disabled by timer objective)
        with controls_container:
            _render_turn_controls(
                play_state,
                stop_on_timer_objective=stop_on_timer_objective,
                timer_behavior=timer_behavior,
            )
            _render_encounter_triggers(encounter, play_state, settings)
            _render_attached_events()
            _render_log(play_state)

    with col_mid:
        objectives_container = st.container()

        # Objectives (including Trials)
        with objectives_container:
            _render_objectives(encounter, settings)

        rest_container = st.container()

        # Rest of the info stack:
        # Rules
        # Encounter Triggers
        # Attached Events
        # Turn Log
        with rest_container:
            _render_rules(encounter, settings, play_state)


    with col_right:
        _render_enemy_behaviors(encounter)


# ---------------------------------------------------------------------
# Left column: timer/phase, buttons, triggers, rules, events, log
# ---------------------------------------------------------------------


def _render_timer_and_phase(play_state: dict) -> None:
    # One row: [Timer icon count] | [Enemy Phase / Player Phase]
    c1, c2 = st.columns([1.4, 1])

    # Left side: Timer [icon] [counter]
    with c1:
        try:
            with open(TIMER_ICON_PATH, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            img_tag = (
                f"<img src='data:image/png;base64,{data}' "
                f"style='height:18px; width:auto; margin:0 0.25rem;'/>"
            )
        except Exception:
            img_tag = "<span style='margin:0 0.25rem;'>⏱️</span>"

        html = f"""
        <div style="display:flex; align-items:center; gap:0.35rem;">
            <span style="font-weight:600;">Timer</span>
            {img_tag}
            <span style="font-size:1.2rem; font-weight:600;">{play_state['timer']}</span>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

    # Right side: phase label
    with c2:
        phase_label = (
            "Enemy Phase" if play_state["phase"] == "enemy" else "Player Phase"
        )
        st.markdown(
            f"<div style='text-align:right; font-size:1.1rem; font-weight:600;'>{phase_label}</div>",
            unsafe_allow_html=True,
        )


def _advance_turn(play_state: dict, disable_auto_timer: bool = False) -> None:
    """
    Smart 'Next Turn' behavior:

    - Start: Timer 0, Enemy Phase.
    - Enemy → Player (no timer change).
    - Player → Enemy and **timer +1**, unless disable_auto_timer is True.
    """
    if play_state["phase"] == "enemy":
        play_state["phase"] = "player"
        _log(play_state, "Advanced to Player Phase")
    else:  # player -> enemy
        if not disable_auto_timer:
            play_state["timer"] += 1
            play_state["phase"] = "enemy"
            _log(play_state, "Advanced to Enemy Phase; timer increased")
        else:
            play_state["phase"] = "enemy"
            _log(
                play_state,
                "Advanced to Enemy Phase (Timer unchanged due to encounter rule)",
            )


def _previous_turn(play_state: dict) -> None:
    """
    Reverse of _advance_turn, as best we can:

    - Player → Enemy (no timer change).
    - Enemy → Player and **timer -1**, but never below 0.
    """
    if play_state["phase"] == "player":
        play_state["phase"] = "enemy"
        _log(play_state, "Reverted to Enemy Phase")
    else:  # enemy
        if play_state["timer"] > 0:
            play_state["timer"] -= 1
            play_state["phase"] = "player"
            _log(
                play_state,
                f"Reverted to Player Phase; timer reduced to {play_state['timer']}",
            )
        else:
            _log(play_state, "Already at starting state; cannot go back further")


def _reset_play_state(play_state: dict) -> None:
    play_state["phase"] = "enemy"
    play_state["timer"] = 0
    play_state["log"] = []
    _log(play_state, "Play state reset (Timer 0, Enemy Phase)")


def _render_turn_controls(
    play_state: dict,
    stop_on_timer_objective: bool = False,
    timer_behavior: Optional[dict] = None,
) -> None:
    if timer_behavior is None:
        timer_behavior = {}

    st.markdown("#### Turn Controls")

    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("Previous Turn", key="encounter_play_prev_turn"):
            st.session_state["encounter_play_pending_action"] = "prev"
            st.rerun()

    with b2:
        if st.button(
            "Next Turn",
            key="encounter_play_next_turn",
            disabled=stop_on_timer_objective,
        ):
            st.session_state["encounter_play_pending_action"] = "next"
            st.rerun()

    with b3:
        if st.button("Reset", key="encounter_play_reset"):
            st.session_state["encounter_play_pending_action"] = "reset"
            st.rerun()

    if stop_on_timer_objective:
        st.caption("Time has run out; Next Turn is disabled for this encounter.")

    # --- Special timer actions (per-encounter) ---
    has_manual_inc = bool(timer_behavior.get("manual_increment"))
    has_reset_btn = bool(timer_behavior.get("reset_button"))

    if has_manual_inc or has_reset_btn:
        st.markdown("##### Special Timer Actions")
        cols = st.columns((1 if has_manual_inc else 0) + (1 if has_reset_btn else 0))

        col_idx = 0

        # Manual 'Increase Timer' button (Eye of the Storm edited)
        if has_manual_inc:
            label = timer_behavior.get(
                "manual_increment_label",
                "Increase Timer",
            )
            help_text = timer_behavior.get("manual_increment_help")
            log_text = timer_behavior.get(
                "manual_increment_log",
                "Timer manually increased.",
            )

            with cols[col_idx]:
                if st.button(
                    label,
                    key="encounter_play_manual_timer_increase",
                ):
                    play_state["timer"] += 1
                    _log(play_state, log_text)
                    st.rerun()
            col_idx += 1
            if help_text:
                st.caption(help_text)

        # 'Reset Timer' button (Corvian Host: tile made active)
        if has_reset_btn:
            label = timer_behavior.get(
                "reset_button_label",
                "Reset Timer (special rule)",
            )
            help_text = timer_behavior.get("reset_button_help")
            log_text = timer_behavior.get(
                "reset_button_log",
                "Timer reset due to special rule.",
            )

            with cols[col_idx]:
                if st.button(
                    label,
                    key="encounter_play_special_timer_reset",
                ):
                    old_timer = play_state["timer"]
                    play_state["timer"] = 0
                    _log(
                        play_state,
                        f"{log_text} (was {old_timer}, now 0)",
                    )
                    st.rerun()
            if help_text:
                st.caption(help_text)


def _render_encounter_triggers(encounter: dict, play_state: dict, settings: dict) -> None:
    st.markdown("#### Encounter Triggers")

    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    edited = _detect_edited_flag(encounter_key, encounter, settings)

    triggers = get_triggers_for_encounter(
        encounter_key=encounter_key,
        edited=edited,
    )
    if not triggers:
        st.caption("No special triggers defined for this encounter yet.")
        return

    enemy_names = _get_enemy_display_names(encounter)
    state = _ensure_trigger_state(encounter_key, triggers)

    for trig in triggers:
        # Phase-gating: only show if it applies in the current phase
        if trig.phase not in ("any", play_state["phase"]):
            continue

        # ----- CHECKBOX -----
        if trig.kind == "checkbox":
            prev = bool(state.get(trig.id, trig.default_value or False))

            suffix = ""
            if trig.template:
                suffix = _render_text_template(
                    trig.template,
                    enemy_names,
                )

            if trig.label and suffix:
                label_text = f"{trig.label}: {suffix}"
            else:
                label_text = trig.label or suffix or trig.id

            new_val = st.checkbox(
                label_text,
                value=prev,
                key=f"trigger_cb_{encounter_key}_{trig.id}",
            )

            # One-shot effect when it flips False -> True
            if new_val and not prev and trig.effect_template:
                effect_text = _render_text_template(
                    trig.effect_template,
                    enemy_names,
                )
                st.info(effect_text)

            state[trig.id] = new_val

        # ----- COUNTER -----
        elif trig.kind == "counter":
            value_int = int(state.get(trig.id, trig.default_value or 0))

            suffix = ""
            if trig.template:
                suffix = _render_text_template(
                    trig.template,
                    enemy_names,
                    value=value_int,
                )

            if trig.label and suffix:
                label_text = f"{trig.label}: {suffix}"
            else:
                label_text = trig.label or suffix or trig.id

            new_val = st.number_input(
                label_text,
                min_value=trig.min_value,
                max_value=trig.max_value if trig.max_value is not None else 999,
                value=value_int,
                key=f"trigger_num_{encounter_key}_{trig.id}",
            )

            # Show per-step effects as the counter increases
            if trig.step_effects and new_val > value_int:
                for step in range(value_int + 1, new_val + 1):
                    tmpl = trig.step_effects.get(step)
                    if tmpl:
                        effect_text = _render_text_template(
                            tmpl,
                            enemy_names,
                        )
                        st.info(effect_text)

            state[trig.id] = new_val

        # ----- NUMERIC (plain number) -----
        elif trig.kind == "numeric":
            value_int = int(state.get(trig.id, trig.default_value or 0))

            suffix = ""
            if trig.template:
                suffix = _render_text_template(
                    trig.template,
                    enemy_names,
                    value=value_int,
                )

            if trig.label and suffix:
                label_text = f"{trig.label}: {suffix}"
            else:
                label_text = trig.label or suffix or trig.id

            new_val = st.number_input(
                label_text,
                value=value_int,
                key=f"trigger_numeric_{encounter_key}_{trig.id}",
            )
            state[trig.id] = new_val

        # ----- TIMER OBJECTIVE -----
        elif trig.kind == "timer_objective":
            label_text = trig.label or _render_text_template(
                trig.template or "",
                enemy_names,
            )

            st.markdown(f"- {label_text}")

            target_timer = None
            if trig.timer_target is not None:
                # Same semantics as _compute_stop_on_timer_objective:
                # timer_target is an offset from player_count.
                target_timer = _get_player_count() + trig.timer_target

            if (
                target_timer is not None
                and play_state["timer"] >= target_timer
            ):
                if trig.stop_on_complete:
                    st.caption(f"✅ Objective reached at Timer {target_timer}.")
                else:
                    st.caption("✅ Objective condition met.")
            elif target_timer is not None:
                st.caption(f"⏳ Objective fails once Timer reaches {target_timer}.")


def _render_attached_events() -> None:
    events = st.session_state.get("encounter_events", [])

    with st.expander("Attached Events"):
        if not events:
            st.caption("No events attached to this encounter.")
            return

        rendezvous_count = sum(1 for ev in events if ev.get("is_rendezvous"))
        st.caption(
            f"{len(events)} event(s) attached"
            + (f" ({rendezvous_count} rendezvous)." if rendezvous_count else ".")
        )

        for ev in events:
            name = ev.get("name") or ev.get("id")
            st.markdown(f"- **{name}**")

            mods = EVENT_BEHAVIOR_MODIFIERS.get(name) or EVENT_BEHAVIOR_MODIFIERS.get(
                ev.get("id")
            )
            if mods:
                for m in mods:
                    desc = (
                        m.get("description")
                        or f"{m.get('stat')} {m.get('op')} {m.get('value')}"
                    )
                    st.caption(f"  • {desc}")
            else:
                st.caption("  • No special behavior modifiers recorded (yet).")


def _render_log(play_state: dict) -> None:
    with st.expander("Turn Log"):
        log = play_state.get("log") or []
        if not log:
            st.caption(
                "Timer / phase changes, resets, etc. will appear here as a quick history."
            )
            return

        for entry in reversed(log[-25:]):
            phase_label = "Enemy Phase" if entry["phase"] == "enemy" else "Player Phase"
            st.markdown(
                f"- Timer {entry['timer']} · {phase_label} · {entry['time']} — {entry['text']}"
            )


# ---------------------------------------------------------------------
# Middle column: encounter card
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# Enemy behavior card helpers
# ---------------------------------------------------------------------
def _find_behavior_cards_for_enemy(enemy_name: str) -> list[Path]:
    json_dir = Path("data") / "behaviors"
    json_path = json_dir / f"{enemy_name}.json"
    if not json_path.exists():
        return []

    cfg = load_behavior(json_path)

    return [Path(p) for p in getattr(cfg, "display_cards", []) or []]


def _get_distinct_enemy_names(encounter: dict) -> list[str]:
    """
    Return distinct enemy display names in encounter order.
    Uses the same enemy name resolution as _get_enemy_display_names().
    """
    all_names = _get_enemy_display_names(encounter)
    seen = set()
    out: list[str] = []

    for name in all_names:
        if name not in seen:
            seen.add(name)
            out.append(name)

    return out


def _render_encounter_card(encounter: dict) -> None:
    st.markdown("#### Encounter Card")
    img = encounter.get("card_img")
    if img is not None:
        st.image(img, width="stretch")
    else:
        st.caption("Encounter card not available (no image in state).")


def _modifier_applies_to_enemy(mod: dict, enemy_name: str) -> bool:
    """
    Return True if this behavior modifier should apply to the given enemy.

    We support:
      - no 'enemy' field → applies to all enemies
      - 'enemy': "Name"   → exact match
      - 'enemy': ["A","B"] → applies if enemy_name in that list
    """
    target = mod.get("enemy")
    if not target:
        return True
    if isinstance(target, str):
        return target == enemy_name
    if isinstance(target, (list, tuple, set)):
        return enemy_name in target
    return False


def _describe_behavior_mod(mod: dict) -> str:
    """
    Build a human-readable description for a behavior modifier.
    Falls back to 'stat op value' if no explicit description is provided.
    """
    if "description" in mod and mod["description"]:
        return str(mod["description"])

    stat = mod.get("stat", "?")
    op = mod.get("op", "?")
    value = mod.get("value", "?")
    return f"{stat} {op} {value}"


def _apply_single_behavior_modifier(raw: dict, mod: dict) -> None:
    """
    Apply a single modifier in-place to raw JSON.

    Expected fields in mod:
      - stat: dotted path into raw JSON, e.g. "health", "armor", "behaviors.Slam.damage"
      - op:   "+", "-", "*", "/", "set" (or "=")
      - value: numeric
    """
    path = mod.get("stat")
    if not path:
        return

    try:
        value = float(mod.get("value"))
    except (TypeError, ValueError):
        return

    keys = str(path).split(".")
    d = raw
    for k in keys[:-1]:
        if not isinstance(d, dict) or k not in d:
            return
        d = d[k]

    last = keys[-1]
    old = d.get(last)
    if not isinstance(old, (int, float)):
        return

    op = mod.get("op", "+")
    if op == "+":
        new = old + value
    elif op == "-":
        new = old - value
    elif op == "*":
        new = old * value
    elif op == "/":
        if value == 0:
            return
        new = old / value
    elif op in ("set", "="):
        new = value
    else:
        return

    # Preserve integer-ness if the original was an int
    if isinstance(old, int):
        d[last] = int(round(new))
    else:
        d[last] = new


def _gather_behavior_mods_for_enemy(encounter: dict, enemy_name: str) -> list[tuple[dict, str, str]]:
    """
    Collect all behavior modifiers affecting this enemy for the current encounter:

      - From attached events (EVENT_BEHAVIOR_MODIFIERS)
      - From the encounter itself (ENCOUNTER_BEHAVIOR_MODIFIERS)

    Return a list of tuples: (mod_dict, source_kind, source_label)
      - source_kind: "event" or "encounter"
      - source_label: event name or "" for encounter-level
    """
    mods: list[tuple[dict, str, str]] = []

    # --- Encounter-level mods (may have default/edited variants) ---
    name = (
        encounter.get("encounter_name")
        or encounter.get("name")
        or "Unknown Encounter"
    )
    expansion = encounter.get("expansion", "Unknown Expansion")
    encounter_key = make_encounter_key(name=name, expansion=expansion)

    settings = st.session_state.get("user_settings", {})
    edited = _detect_edited_flag(encounter_key, encounter, settings)

    enc_mods_cfg = ENCOUNTER_BEHAVIOR_MODIFIERS.get(encounter_key)
    enc_mod_list: list[dict] = []

    if isinstance(enc_mods_cfg, dict):
        if edited and "edited" in enc_mods_cfg:
            enc_mod_list = enc_mods_cfg.get("edited") or []
        else:
            enc_mod_list = enc_mods_cfg.get("default") or enc_mods_cfg.get("base") or []
    elif isinstance(enc_mods_cfg, list):
        enc_mod_list = enc_mods_cfg

    for m in enc_mod_list or []:
        if _modifier_applies_to_enemy(m, enemy_name):
            mods.append((m, "encounter", ""))

    # --- Event-level mods ---
    events = st.session_state.get("encounter_events", [])
    for ev in events:
        ev_name = ev.get("name") or ev.get("id")
        ev_mods = EVENT_BEHAVIOR_MODIFIERS.get(ev_name) or EVENT_BEHAVIOR_MODIFIERS.get(
            ev.get("id")
        )
        if not ev_mods:
            continue

        for m in ev_mods:
            if _modifier_applies_to_enemy(m, enemy_name):
                mods.append((m, "event", ev_name or ""))

    return mods


def _apply_behavior_mods_to_raw(raw: dict, mods: list[dict]) -> dict:
    """
    Return a deep-copied raw JSON with all mods applied.
    """
    if not mods:
        return raw
    patched = deepcopy(raw)
    for m in mods:
        _apply_single_behavior_modifier(patched, m)
    return patched


# ---------------------------------------------------------------------
# Right column: enemy behavior cards (placeholder)
# ---------------------------------------------------------------------


def _render_enemy_behaviors(encounter: dict) -> None:
    """
    Right-hand column: show enemy data + behavior cards for all distinct
    enemies in this encounter, using the Behavior Decks pipeline.

    - One stack per distinct enemy type (based on the shuffled list).
    - Uses NG+ scaling via load_behavior.
    - Applies encounter/event behavior modifiers to the raw JSON before rendering.
    """
    st.markdown("#### Enemy Behavior Cards")

    entries = _get_enemy_behavior_entries_for_encounter(encounter)
    if not entries:
        st.caption("No enemy behavior data found for this encounter.")
        return

    # Sort by order_num descending (higher priority first)
    entries = sorted(
        entries,
        key=lambda e: getattr(e, "order_num", 10),
        reverse=True,
    )

    # Two sub-columns so we don't get a super tall single column
    col_a, col_b = st.columns(2, gap="medium")

    for i, entry in enumerate(entries):
        target_col = col_a if i % 2 == 0 else col_b
        with target_col:
            # Load behavior config (NG+ already applied inside load_behavior)
            cfg = load_behavior(entry.path)
            enemy_name = cfg.name

            # Gather all behavior modifiers that apply to this enemy
            mod_tuples = _gather_behavior_mods_for_enemy(encounter, enemy_name)
            mod_dicts = [m for (m, _, _) in mod_tuples]

            # Apply mods to raw json before rendering data card
            raw_for_render = _apply_behavior_mods_to_raw(cfg.raw, mod_dicts)

            # Always show the data card for this enemy/boss if available
            data_card_path = BEHAVIOR_CARDS_PATH + f"{cfg.name} - data.jpg"
            data_bytes = render_data_card_cached(
                data_card_path,
                raw_for_render,
                is_boss=(cfg.tier == "boss"),
            )
            if data_bytes is not None:
                st.image(data_bytes, width="stretch")

            # If there are active modifiers, show a small list under the card
            if mod_tuples:
                st.caption("_Behavior modifiers in effect:_")
                for mod, source_kind, source_label in mod_tuples:
                    desc = _describe_behavior_mod(mod)
                    if not desc:
                        continue

                    if source_kind == "event":
                        prefix = f"Event: {source_label}" if source_label else "Event"
                    else:
                        prefix = "Encounter"

                    st.caption(f"  • {prefix} — {desc}")
