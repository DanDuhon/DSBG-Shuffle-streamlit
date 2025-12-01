from __future__ import annotations

import re
from typing import List, Optional


# ---------------------------------------------------------------------
# Regex patterns for text templates
# ---------------------------------------------------------------------
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


def _safe_enemy_name(enemy_names: List[str], idx_1_based: int) -> str:
    idx = idx_1_based - 1
    if 0 <= idx < len(enemy_names):
        return enemy_names[idx]
    return f"[enemy{idx_1_based}?]"


def _pluralize_enemy_name(name: str) -> str:
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
    else:
        # Only handle up to 4 duplicates for now
        return text

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


def cap_tiles_in_text(text: str, max_tiles: int) -> str:
    """Public wrapper around _cap_tiles_in_text."""
    return _cap_tiles_in_text(text, max_tiles)


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


def render_text_template(
    template: str,
    enemy_names: List[str],
    *,
    value: Optional[int] = None,
    player_count: Optional[int] = None,
) -> str:
    """Public entry point mirroring the original _render_text_template helper.

    Note: this is Streamlit-free – callers must pass player_count explicitly
    if they want {players} / {players+N} expansion.
    """
    text = template

    # 1) {enemy_list:1,2,3} – group and format those enemies as a phrase
    def _sub_enemy_list(m: re.Match) -> str:
        indices_str = m.group(1)
        return _format_enemy_list_from_indices(indices_str, enemy_names)

    text = _ENEMY_LIST_PATTERN.sub(_sub_enemy_list, text)

    # 2) Regular enemy placeholders ({enemyN}, {enemyN}s, {enemyN_plural})
    text = _apply_enemy_placeholders(text, enemy_names)

    # 3) Players and players+N
    if player_count is not None:
        text = _apply_player_placeholders(text, player_count)

    # 4) {value} for counters / numerics
    if value is not None:
        text = text.replace("{value}", str(value))

    # 5) Grammar cleanups
    text = _collapse_duplicate_enemy_list(text)
    text = _fix_indefinite_articles(text)

    return text


# Backwards-compatibility alias if old code imports this name.
def _render_text_template(
    template: str,
    enemy_names: List[str],
    *,
    value: Optional[int] = None,
    player_count: Optional[int] = None,
) -> str:
    return render_text_template(
        template,
        enemy_names,
        value=value,
        player_count=player_count,
    )
