from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


DATA_CARD_SENTINEL = "(Data Card)"


@dataclass(frozen=True)
class BehaviorPickerModel:
    beh_order: List[str]
    display_map: Dict[str, str]
    display_labels: List[str]
    options: List[str]
    options_compact: List[str]
