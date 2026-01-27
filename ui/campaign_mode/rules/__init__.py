from typing import Any, Dict
from core.expansions import V2_EXPANSIONS


V2_EXPANSIONS_SET = set(V2_EXPANSIONS)


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
    level = int(encounter.get("level"))

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
