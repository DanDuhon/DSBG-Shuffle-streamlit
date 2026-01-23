from typing import Any, Dict


def _attack_has_dice(atk: Dict[str, Any]) -> bool:
    d = atk.get("dice") or {}
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        if int(v) != 0:
            return True
    return False
