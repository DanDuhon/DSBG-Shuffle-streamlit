from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ui.behavior_viewer.models import BehaviorPickerModel, DATA_CARD_SENTINEL
from ui.behavior_viewer.ordering import compute_behavior_order


def _build_compact_options(entry_name: str, cfg: Any, beh_order: List[str]) -> List[str]:
    """Build compact-mode options, including header rows for heatup cards."""
    options_compact: List[str] = [DATA_CARD_SENTINEL]

    if entry_name == "Ornstein & Smough":
        all_names = list(cfg.behaviors.keys())
        dual_non_heatup = [
            n
            for n in all_names
            if "&" in n and not cfg.behaviors.get(n, {}).get("heatup", False)
        ]
        nonheat = [
            n
            for n in all_names
            if n not in dual_non_heatup and not cfg.behaviors.get(n, {}).get("heatup")
        ]

        def _sort_key(n: str):
            t = cfg.behaviors.get(n, {}).get("type")
            rank = 0 if t == "move" else 1 if t == "attack" else 2
            return (rank, str(n).lower())

        nonheat.sort(key=_sort_key)
        orn_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Ornstein"]
        smough_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Smough"]
        orn_heatup.sort(key=_sort_key)
        smough_heatup.sort(key=_sort_key)
        remaining = nonheat[:]
        dual_non_heatup.sort(key=_sort_key)

        if dual_non_heatup:
            options_compact.extend(dual_non_heatup)
        if orn_heatup:
            options_compact.append("— Ornstein heatups —")
            options_compact.extend(orn_heatup)
        if smough_heatup:
            options_compact.append("— Smough heatups —")
            options_compact.extend(smough_heatup)
        if remaining:
            options_compact.append("— Other —")
            options_compact.extend(remaining)

        return options_compact

    non_heatup = [n for n in beh_order if not cfg.behaviors.get(n, {}).get("heatup")]
    heatups = [n for n in beh_order if cfg.behaviors.get(n, {}).get("heatup")]
    options_compact.extend(non_heatup)
    if heatups:
        options_compact.append("— Heatup cards —")
        options_compact.extend(heatups)

    return options_compact


def build_picker_model(*, category: str, entry: Any, cfg: Any) -> BehaviorPickerModel:
    beh_order = compute_behavior_order(entry.name, cfg)

    display_map: Dict[str, str] = {}
    display_labels: List[str] = []

    for name in (beh_order if category != "Regular Enemies" else []):
        b = cfg.behaviors.get(name, {})
        heat = b.get("heatup")
        btype = b.get("type")

        # Emoji for move vs attack; special-case Last Giant arm/Falling Slam and Vordt Frostbreath
        if entry.name == "Executioner's Chariot" and isinstance(name, str) and name.startswith("Death Race"):
            type_emoji = "🛞"
        elif entry.name == "Great Grey Wolf Sif" and isinstance(name, str) and name.startswith("Limping Strike"):
            type_emoji = "🩸"
        elif entry.name == "The Last Giant" and isinstance(name, str) and name.startswith("Falling Slam"):
            type_emoji = "⬇️"
        elif entry.name == "The Last Giant" and isinstance(name, str) and cfg.behaviors.get(name, {}).get("arm") == True:
            type_emoji = "💪"
        elif entry.name == "Vordt of the Boreal Valley" and name == "Frostbreath":
            type_emoji = "❄️"
        elif entry.name == "Vordt of the Boreal Valley" and btype == "move":
            type_emoji = "🦶"
        elif entry.name == "Vordt of the Boreal Valley" and btype == "attack":
            type_emoji = "🪓"
        else:
            type_emoji = ""

        # Compose label: heatup indicator (if any) goes first, then type emoji, then name
        if entry.name == "Ornstein & Smough":
            if isinstance(heat, str) and heat == "Ornstein":
                prefix = "🔥 Ornstein —"
            elif isinstance(heat, str) and heat == "Smough":
                prefix = "🔥 Smough —"
            else:
                prefix = ""
        elif entry.name == "The Four Kings":
            num_map = {
                "2": "2️⃣",
                "3": "3️⃣",
                "4": "4️⃣",
            }
            prefix = num_map[str(heat)] if heat else ""
        else:
            prefix = "🔥" if heat else ""

        parts: List[str] = []
        if prefix:
            parts.append(prefix)
        if type_emoji:
            parts.append(type_emoji)

        # For Gaping Dragon and Executioner's Chariot, collapse numbered labels to single names
        if entry.name == "Gaping Dragon" and isinstance(name, str) and name.startswith("Stomach Slam"):
            display_name = "Stomach Slam"
        elif entry.name == "Executioner's Chariot" and isinstance(name, str) and name.startswith("Death Race"):
            display_name = "Death Race"
        elif entry.name == "The Pursuer" and isinstance(name, str) and name.startswith("Stabbing Strike"):
            display_name = "Stabbing Strike"
        elif entry.name == "The Pursuer" and isinstance(name, str) and name.startswith("Wide Blade Swing"):
            display_name = "Wide Blade Swing"
        else:
            display_name = name

        parts.append(display_name)
        label = " ".join(parts)

        display_map[label] = name
        display_labels.append(label)

    options = [DATA_CARD_SENTINEL] + display_labels
    options_compact = _build_compact_options(entry.name, cfg, beh_order)

    return BehaviorPickerModel(
        beh_order=beh_order,
        display_map=display_map,
        display_labels=display_labels,
        options=options,
        options_compact=options_compact,
    )
