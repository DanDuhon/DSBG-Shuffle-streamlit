"""Event card short text (JSON-backed).

Kept as a module-level dict for backward-compatible imports.
"""

from ui.event_mode.event_card_meta import get_event_card_text_map


EVENT_CARD_TEXT: dict[str, str] = get_event_card_text_map()
