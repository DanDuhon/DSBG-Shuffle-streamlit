from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BehaviorDeckState:
    boss: str
    phase: int = 1
    draw_pile: List[str] = field(default_factory=list)
    discard_pile: List[str] = field(default_factory=list)
    current_card: Optional[str] = None
    hp: Optional[int] = None
    heatup_triggered: bool = False
    summons: int = 0  # used for Four Kings
