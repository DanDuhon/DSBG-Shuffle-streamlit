"""Public API for Campaign Mode UI.

This module re-exports pure logic, persistence and constants for use by UI
modules so they don't import internal `_`-prefixed symbols from `core.py`.
"""
from ui.campaign_mode.persistence import (
    get_bosses,
    get_invaders,
    get_campaigns,
    _save_campaigns as save_campaigns,
    clear_json_cache,
    load_json_file,
)

from ui.campaign_mode.generation import (
    _filter_bosses as filter_bosses,
    _generate_v1_campaign as generate_v1_campaign,
    _generate_v2_campaign as generate_v2_campaign,
    _pick_random_campaign_encounter as pick_random_campaign_encounter,
    _v2_pick_scout_ahead_alt_frozen as v2_pick_scout_ahead_alt_frozen,
    _campaign_encounter_signature as campaign_encounter_signature,
)

from ui.campaign_mode.rules import (
    _is_v1_campaign_eligible as is_v1_campaign_eligible,
    _is_v2_campaign_eligible as is_v2_campaign_eligible,
    V2_EXPANSIONS_SET,
)

from ui.campaign_mode.core import (
    ASSETS_DIR,
    PARTY_TOKEN_PATH,
    SOULS_TOKEN_PATH,
    BONFIRE_ICON_PATH,
    CHARACTERS_DIR,
    ENCOUNTER_GRAVESTONES,
    _default_sparks_max as default_sparks_max,
    _describe_v1_node_label as describe_v1_node_label,
    _describe_v2_node_label as describe_v2_node_label,
    _v2_compute_allowed_destinations as v2_compute_allowed_destinations,
    _reset_all_encounters_on_bonfire_return as reset_all_encounters_on_bonfire_return,
    _record_dropped_souls as record_dropped_souls,
    _card_w as card_w,
    _campaign_find_next_encounter_node as campaign_find_next_encounter_node,
)

__all__ = [
    # persistence
    "get_bosses",
    "get_invaders",
    "get_campaigns",
    "save_campaigns",
    "clear_json_cache",
    "load_json_file",
    # generation
    "filter_bosses",
    "generate_v1_campaign",
    "generate_v2_campaign",
    "pick_random_campaign_encounter",
    "v2_pick_scout_ahead_alt_frozen",
    "campaign_encounter_signature",
    # rules
    "is_v1_campaign_eligible",
    "is_v2_campaign_eligible",
    "V2_EXPANSIONS_SET",
    # constants / helpers
    "ASSETS_DIR",
    "PARTY_TOKEN_PATH",
    "SOULS_TOKEN_PATH",
    "BONFIRE_ICON_PATH",
    "CHARACTERS_DIR",
    "ENCOUNTER_GRAVESTONES",
    "default_sparks_max",
    "describe_v1_node_label",
    "describe_v2_node_label",
    "v2_compute_allowed_destinations",
    "reset_all_encounters_on_bonfire_return",
    "record_dropped_souls",
    "card_w",
    "campaign_find_next_encounter_node",
]
