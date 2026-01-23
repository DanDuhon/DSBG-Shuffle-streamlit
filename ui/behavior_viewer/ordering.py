from __future__ import annotations

from typing import Any, Dict, List


def compute_behavior_order(entry_name: str, cfg: Any) -> List[str]:
    """Compute the ordered list of behavior names for the given entry.

    This function intentionally preserves the existing special-case ordering
    rules from the original Behavior Viewer implementation.
    """

    # Present cards as radio options on the left; show image on the right
    # Build behavior option ordering. Special-case Ornstein & Smough grouping.
    if entry_name == "Ornstein & Smough":
        all_names = list(cfg.behaviors.keys())
        # Dual combined non-heatup cards (e.g., "X & Y") should appear first
        dual_non_heatup = [
            n
            for n in all_names
            if "&" in n and not cfg.behaviors.get(n, {}).get("heatup", False)
        ]
        # Other non-heatup cards
        nonheat = [
            n
            for n in all_names
            if n not in dual_non_heatup and not cfg.behaviors.get(n, {}).get("heatup")
        ]

        # Sort so move behaviors come before attack behaviors, then by name
        def _sort_key(n: str):
            t = cfg.behaviors.get(n, {}).get("type")
            rank = 0 if t == "move" else 1 if t == "attack" else 2
            return (rank, str(n).lower())

        nonheat.sort(key=_sort_key)
        # Heatup groups go to the end
        orn_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Ornstein"]
        smough_heatup = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup") == "Smough"]
        orn_heatup.sort(key=_sort_key)
        smough_heatup.sort(key=_sort_key)
        # remaining for compact display convenience
        remaining = nonheat[:]
        dual_non_heatup.sort(key=_sort_key)
        beh_order = dual_non_heatup + nonheat + orn_heatup + smough_heatup

        # Special-case: for Vordt, ensure Frostbreath appears first (under Data Card)
        # (Unreachable here, but preserved from the original implementation.)
        if entry_name == "Vordt of the Boreal Valley":
            if "Frostbreath" in beh_order:
                beh_order.remove("Frostbreath")
                beh_order.insert(0, "Frostbreath")
    else:
        # General case: non-heatup first, then heatup cards at end
        all_names = list(cfg.behaviors.keys())

        def _sort_key(n: str):
            t = cfg.behaviors.get(n, {}).get("type")
            rank = 0 if t == "move" else 1 if t == "attack" else 2
            return (rank, str(n).lower())

        nonheat = [n for n in all_names if not cfg.behaviors.get(n, {}).get("heatup")]
        heatups = [n for n in all_names if cfg.behaviors.get(n, {}).get("heatup")]
        # Sort non-heatup as before (move -> attack -> other, then name)
        nonheat.sort(key=_sort_key)

        # Sort heatups by their heatup value (numeric when possible), then by name
        def _heatup_key(n: str):
            h = cfg.behaviors.get(n, {}).get("heatup")
            h_str = str(h)
            h_key: Any = int(h_str) if h_str.isdigit() else h_str.lower()
            return (h_key, str(n).lower())

        heatups.sort(key=_heatup_key)
        # Place non-heatup cards first, then heatup cards
        beh_order = nonheat + heatups

        # Special-case: for Vordt, ensure Frostbreath appears first (under Data Card)
        if entry_name == "Vordt of the Boreal Valley":
            if "Frostbreath" in beh_order:
                beh_order.remove("Frostbreath")
                beh_order.insert(0, "Frostbreath")

    # Build display labels for non-compact radio so heatup cards are indicated
    # Special-case: remove Fiery Breath from Guardian Dragon options
    if entry_name == "Guardian Dragon":
        if "Fiery Breath" in beh_order:
            beh_order.remove("Fiery Breath")

    # Special-case: Gaping Dragon has duplicate 'Stomach Slam' cards; only show 'Stomach Slam 1'
    if entry_name == "Gaping Dragon":
        keep = "Stomach Slam 1"
        # Remove other stomach slam variants (e.g., 'Stomach Slam 2')
        beh_order = [n for n in beh_order if not (n.startswith("Stomach Slam") and n != keep)]
        # If the preferred card isn't present but a generic exists, keep the first stomach slam
        if keep not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Stomach Slam"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break

    # Special-case: The Pursuer - collapse Stabbing Strike and Wide Blade Swing variants to single entries
    if entry_name == "The Pursuer":
        # Keep the first variant for each duplicate group
        keep_ss = "Stabbing Strike 1"
        keep_wb = "Wide Blade Swing 1"
        beh_order = [n for n in beh_order if not (n.startswith("Stabbing Strike") and n != keep_ss)]
        beh_order = [n for n in beh_order if not (n.startswith("Wide Blade Swing") and n != keep_wb)]
        # If preferred names are missing, pull any matching variant to front
        if keep_ss not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Stabbing Strike"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break
        if keep_wb not in beh_order:
            for n in list(cfg.behaviors.keys()):
                if n.startswith("Wide Blade Swing"):
                    if n not in beh_order:
                        beh_order.insert(0, n)
                    break

    # Special-case: The Last Giant ordering and emojis
    if entry_name == "The Last Giant":
        # Identify falling slam(s), arm cards, non-arm non-heatup, and heatups
        falling = [n for n in beh_order if isinstance(n, str) and n.startswith("Falling Slam")]
        # Use explicit `arm` flag from JSON to find arm cards
        arm_cards = [n for n in beh_order if cfg.behaviors.get(n, {}).get("arm") == True]
        non_arm_nonheat = [
            n
            for n in beh_order
            if n not in falling
            and n not in arm_cards
            and not cfg.behaviors.get(n, {}).get("heatup")
        ]
        heatups_last = [n for n in beh_order if cfg.behaviors.get(n, {}).get("heatup")]
        # Build desired order: Falling Slam first, then non-arm non-heatup, then arm cards, then heatups
        beh_order = falling + non_arm_nonheat + arm_cards + heatups_last

    # Always exclude 'Mega Boss Setup' from lists
    if "Mega Boss Setup" in beh_order:
        beh_order = [n for n in beh_order if n != "Mega Boss Setup"]

    # Special-case: Executioner's Chariot - single Death Race, placed first
    if entry_name == "Executioner's Chariot":
        keep = "Death Race 1"
        # Remove other Death Race variants
        beh_order = [
            n
            for n in beh_order
            if not (isinstance(n, str) and n.startswith("Death Race") and n != keep)
        ]
        # Ensure preferred Death Race is first (if missing, pull any Death Race into front)
        if keep in beh_order:
            beh_order = [keep] + [n for n in beh_order if n != keep]
        else:
            for n in list(cfg.behaviors.keys()):
                if isinstance(n, str) and n.startswith("Death Race"):
                    if n in beh_order:
                        beh_order = [n] + [x for x in beh_order if x != n]
                    else:
                        beh_order.insert(0, n)
                    break

    # Special-case: Great Grey Wolf Sif - show Limping Strike first under the data card
    if entry_name == "Great Grey Wolf Sif":
        limp = None
        for n in beh_order:
            if isinstance(n, str) and n.startswith("Limping Strike"):
                limp = n
                break
        if limp:
            beh_order = [limp] + [n for n in beh_order if n != limp]

    return beh_order
