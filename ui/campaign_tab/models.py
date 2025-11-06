from typing import List, Optional, Union, Literal
from dataclasses import dataclass, field


NodeType = Literal["encounter", "mini boss", "main boss", "mega boss", "bonfire"]


@dataclass
class ProgressNode:
    name: str
    type: NodeType
    expansion: Optional[str] = None
    level: Optional[int] = None
    completed: bool = False
    ever_completed: bool = False
    revealed: bool = False
    failed: bool = False
    failed_at: Optional[int] = None
    shortcut: bool = False
    enemies: Optional[List[str]] = field(default=None)
    card_img: Optional[object] = field(default=None, repr=False)


@dataclass
class EncounterChoice:
    options: List[ProgressNode]
    selected: Optional[int] = None
    level: Optional[int] = None
    revealed: bool = False
    completed: bool = False
    ever_completed: bool = False
    failed: bool = False

    def pick(self, index: int) -> ProgressNode:
        self.selected = index
        return self.options[index]
    
    @property
    def type(self):
        return "encounter_choice"
    
    @property
    def name(self) -> str:
        if self.selected is not None and self.options:
            return self.options[self.selected].name
        # while unrevealed, present as "Unknown"
        return "Unknown Encounter"
    
    @property
    def expansion(self):
        if self.selected is not None and self.options:
            return self.options[self.selected].expansion
        return None


@dataclass
class Chapter:
    boss: ProgressNode
    encounters: List[Union[ProgressNode, EncounterChoice]]
    collapsed: bool = True


    def to_dict(self) -> dict:
        return {
            "boss": _serialize_node(self.boss),
            "encounters": [_serialize_node(x) for x in self.encounters],
            "collapsed": self.collapsed,
        }


    @classmethod
    def from_dict(cls, data: dict):
        boss = _deserialize_node(data["boss"])
        encs = [_deserialize_node(x) for x in data.get("encounters", [])]
        return cls(boss=boss, encounters=encs, collapsed=data.get("collapsed", True))

@dataclass
class Campaign:
    name: str
    ruleset: str
    characters: list[str]
    sparks: int
    chapters: list["Chapter"]
    current_chapter: Optional[int] = None
    current_index: Optional[int] = None


    def to_dict(self, name: Optional[str] = None) -> dict:
        return {
            "name": name or self.name,
            "ruleset": self.ruleset,
            "characters": self.characters,
            "sparks": self.sparks,
            "current_chapter": self.current_chapter,
            "current_index": self.current_index,
            "chapters": [ch.to_dict() for ch in self.chapters],
        }


    @classmethod
    def from_dict(cls, data: dict):
        chapters = [Chapter.from_dict(ch) for ch in data.get("chapters", [])]
        return cls(
            name=data.get("name", "Loaded Campaign"),
            ruleset=data.get("ruleset", "V2"),
            characters=data.get("characters", []),
            sparks=data.get("sparks", 0),
            current_chapter=data.get("current_chapter"),
            current_index=data.get("current_index"),
            chapters=chapters,
        )


# -------- Node (de)serialization --------
def _serialize_node(node):
    """Return a JSON-serializable dict for either ProgressNode or EncounterChoice."""
    if isinstance(node, EncounterChoice):
        return {
            "kind": "choice",
            "selected": node.selected,
            "revealed": node.revealed,
            "completed": node.completed,
            "ever_completed": node.ever_completed,
            "failed": node.failed,
            # store options as regular nodes
            "options": [_serialize_node(opt) for opt in node.options],
            # level is handy for labels; only present if you added it
            "level": getattr(node, "level", None),
        }
    else:  # ProgressNode
        return {
            "kind": "node",
            "name": node.name,
            "type": node.type,
            "expansion": node.expansion,
            "level": node.level,
            "completed": node.completed,
            "ever_completed": node.ever_completed,
            "revealed": node.revealed,
            "failed": node.failed,
            "failed_at": node.failed_at,
            # we don't serialize card_img (image object); regenerate as needed
            "enemies": node.enemies,
            # include shortcut if you’ve added it to ProgressNode; safe get:
            "shortcut": getattr(node, "shortcut", False),
        }


def _deserialize_node(d):
    """Recreate either ProgressNode or EncounterChoice from a dict."""
    if d.get("kind") == "choice":
        opts = [_deserialize_node(x) for x in d.get("options", [])]
        choice = EncounterChoice(
            options=opts,
            selected=d.get("selected"),
            revealed=d.get("revealed", False),
            completed=d.get("completed", False),
            ever_completed=d.get("ever_completed", False),
            failed=d.get("failed", False),
        )
        # Optional: keep a deterministic level on the choice if present
        if "level" in d:
            setattr(choice, "level", d["level"])
        return choice
    else:
        return ProgressNode(
            name=d.get("name", "Unknown"),
            type=d.get("type", "encounter"),
            expansion=d.get("expansion"),
            level=d.get("level"),
            completed=d.get("completed", False),
            ever_completed=d.get("ever_completed", False),
            revealed=d.get("revealed", False),
            failed=d.get("failed", False),
            failed_at=d.get("failed_at"),
            enemies=d.get("enemies"),
            shortcut=d.get("shortcut", False)
        )
