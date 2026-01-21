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
    _v2_pick_scout_ahead_alt_frozen as v2_pick_scout_ahead_alt_frozen,
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
