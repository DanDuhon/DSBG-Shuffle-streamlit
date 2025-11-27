#ui/encounters_tab/models.py
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Encounter:
    """Represents a single encounter card and its generated data."""
    name: str
    expansion: str
    level: int
    enemies: List[int] = field(default_factory=list)
    card_img: Optional[object] = None
    edited: bool = False
