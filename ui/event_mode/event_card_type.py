"""Event card type/category (JSON-backed).

Kept as a module-level dict for backward-compatible imports.
"""

from ui.event_mode.event_card_meta import get_event_card_type_map


EVENT_CARD_TYPE: dict[str, str] = get_event_card_type_map()
