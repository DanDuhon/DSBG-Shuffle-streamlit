import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Dict, Any, Union
import random
import streamlit as st

from core.encounters import list_encounters, load_valid_sets, encounter_is_valid, generate_encounter_image, load_encounter
from ui.encounter_helpers import shuffle_encounter


# -----------------------------
# Storage
# -----------------------------
CAMPAIGNS_FILE = Path("data/saved_campaigns.json")
BOSSES_FILE = Path("data/bosses.json")
BOSSES_IMAGES = Path("assets/boss cards")
BONFIRE_IMAGE = Path("assets/bonfire.gif")
PARTY_TOKEN = Path("assets/party_token.png")
SOULS_TOKEN = Path("assets/souls_token.png")
EVENTS_SHORTCUTS_FILE = Path("data/encounters_events_shortcuts.json")
V2_STRUCTURE = {
    "mini boss":  [1, 1, 1, 2],   # 3x L1, 1x L2
    "main boss":  [2, 2, 3, 3],   # 2x L2, 2x L3
    "mega boss":  [4],            # 1x L4
}

# -----------------------------
# Data Model
# -----------------------------
Ruleset = Literal["V1", "V2"]
NodeType = Literal["encounter", "mini boss", "main boss", "mega boss", "bonfire"]


@st.cache_data
def load_events_shortcuts() -> dict:
    if EVENTS_SHORTCUTS_FILE.exists():
        return json.loads(EVENTS_SHORTCUTS_FILE.read_text("utf-8"))
    return {}

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
        camp = cls(
            name=data.get("name", "Loaded Campaign"),
            ruleset=data.get("ruleset", "V2"),
            characters=data.get("characters", []),
            sparks=data.get("sparks", 0),
            current_chapter=data.get("current_chapter"),
            current_index=data.get("current_index"),
            chapters=chapters,
        )

        # --- Regenerate encounter images immediately ---
        for ch in camp.chapters:
            for node in ch.encounters + [ch.boss]:
                if isinstance(node, ProgressNode) and node.type == "encounter":
                    if node.enemies:  # only if enemies were saved
                        try:
                            node.card_img = generate_encounter_image(
                                node.name,
                                node.level,
                                node.enemies,
                                active_expansions=camp.characters,  # or your expansions source
                            )
                        except Exception as e:
                            print(f"⚠️ Failed to regenerate encounter image for {node.name}: {e}")
        return camp



# Saving/Loading
def load_saved_campaigns():
    if CAMPAIGNS_FILE.exists():
        try:
            return json.loads(CAMPAIGNS_FILE.read_text("utf-8"))
        except Exception:
            return {"campaigns": []}
    return {"campaigns": []}


def save_campaigns(data):
    CAMPAIGNS_FILE.write_text(json.dumps(data, indent=2))


def save_current_campaign(camp: Campaign, name: str):
    data = load_saved_campaigns()
    campaigns = data.get("campaigns", [])

    # enforce max 5
    if len(campaigns) >= 5:
        st.warning("You already have 5 saved campaigns. Delete one to save another.")
        return False

    campaigns.append(camp.to_dict(name=name))
    data["campaigns"] = campaigns
    save_campaigns(data)
    st.success(f"Campaign '{name}' saved!")
    return True


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


# -----------------------------
# Persistence helpers
# -----------------------------
def _default_store() -> Dict[str, Any]:
    return {"campaigns": []}

def load_store() -> Dict[str, Any]:
    if CAMPAIGNS_FILE.exists():
        try:
            return json.loads(CAMPAIGNS_FILE.read_text("utf-8"))
        except Exception:
            return _default_store()
    return _default_store()

def save_store(store: Dict[str, Any]) -> None:
    CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


# -----------------------------
# Boss Data
# -----------------------------
def load_bosses() -> Dict[str, Any]:
    if BOSSES_FILE.exists():
        return json.loads(BOSSES_FILE.read_text("utf-8"))
    return {}

# -----------------------------
# Campaign generation
# -----------------------------
def _generate_encounter_node(raw: Dict[str, Any], lvl: int, character_count: int, expansions: List[str]) -> ProgressNode:
    res = shuffle_encounter(
        {"name": raw["name"], "level": lvl},
        character_count,
        expansions,
        raw["expansion"],
        st.session_state.user_settings["edited_toggles"].get(f"edited_toggle_{raw['name']}_{raw['expansion']}", False)
    )
    shortcuts = load_events_shortcuts()
    key = f"{raw['expansion']}_{lvl}_{raw['name']}"
    is_shortcut = shortcuts.get(key, {}).get("shortcut", False)

    node = ProgressNode(
        name=raw["name"],
        type="encounter",
        expansion=raw["expansion"],
        level=lvl,
        revealed=False,
        shortcut=is_shortcut
    )
    node.card_img = res["card_img"]
    node.enemies = res["enemies"]

    return node


def generate_v2_campaign(active_expansions: List[str], character_count: int, bosses: Dict[str, Any], randomize_bosses: bool = True) -> List[Chapter]:
    def _choose_boss(boss_type: str):
        candidates = [b for b in bosses.values() if b["type"] == boss_type and any(exp in active_expansions for exp in b["expansions"])]
        if not candidates:
            return None
        chosen = random.choice(candidates) if randomize_bosses else candidates[0]
        return ProgressNode(name=chosen["name"], type=boss_type, expansion=chosen["expansions"][0], revealed=False)
    

    def pick_two_unique(level: int):
        pool = [e for e in by_level.get(level, []) if e["name"] not in used_encounters]

        # If not enough uniques, allow duplicates or use placeholders
        if len(pool) < 2:
            pool = by_level.get(level, [])
        if len(pool) < 2:
            placeholders = [
                ProgressNode(name=f"Unknown Level {level} Encounter A", type="encounter", level=level),
                ProgressNode(name=f"Unknown Level {level} Encounter B", type="encounter", level=level),
            ]
            return EncounterChoice(options=placeholders, selected=None)

        chosen = random.sample(pool, 2)
        for c in chosen:
            used_encounters.add(c["name"])
        nodes = [_generate_encounter_node(c, level, character_count, active_expansions) for c in chosen]
        return EncounterChoice(options=nodes, level=level, selected=None)
    
    
    chapters: List[Chapter] = []
    encounters_by_expansion = list_encounters()
    by_level: Dict[int, List[Dict[str, Any]]] = {}
    for _, enc_list in encounters_by_expansion.items():
        for e in enc_list:
            if e["version"] == "V2" or e["level"] == 4:
                by_level.setdefault(e["level"], []).append(e)

    mini = _choose_boss("mini boss")
    main = _choose_boss("main boss")
    mega = _choose_boss("mega boss")

    used_encounters = set()

    for boss in [mini, main, mega]:
        if boss:
            encounters: List[Union[ProgressNode, EncounterChoice]] = []
            for lvl in V2_STRUCTURE[bosses[boss.name]["type"]]:
                encounters.append(pick_two_unique(lvl))
            chapters.append(Chapter(boss=boss, encounters=encounters))

    return chapters


# -----------------------------
# Souls token handling
# -----------------------------
def fail_node(node: Union[ProgressNode, EncounterChoice]):
    if isinstance(node, EncounterChoice):
        if node.selected is not None:
            node.options[node.selected].failed = True
        node.failed = True
    else:
        node.failed = True


def clear_souls_tokens(camp: Campaign, node: ProgressNode, failed: bool = False):
    if failed:
        for chapter in camp.chapters:
            for n in chapter.encounters + [chapter.boss]:
                if isinstance(n, EncounterChoice):
                    for opt in n.options:
                        if opt is not node:
                            opt.failed = False
                else:
                    if n is not node:
                        n.failed = False
    else:
        if isinstance(node, EncounterChoice) and node.selected is not None:
            node.options[node.selected].failed = False
        else:
            node.failed = False


def ensure_encounter_image(node: ProgressNode, camp: "Campaign") -> None:
    """
    Make sure a ProgressNode has its encounter image and enemies.
    Only applies to encounter nodes.
    """
    if node.type != "encounter":
        return

    if node.card_img is not None:
        return  # already generated
    
    if node.type == "encounter" and node.card_img is None and node.enemies:
        encounter_slug = f"{node.expansion}_{node.level}_{node.name}"
        encounter_data = load_encounter(encounter_slug, len(camp.characters))

        res = generate_encounter_image(
            node.expansion,
            node.level,
            node.name,
            encounter_data,
            node.enemies,
            st.session_state.user_settings["edited_toggles"].get(
                f"edited_toggle_{node.name}_{node.expansion}", False
            )
        )
        node.card_img = res
    else:
        res = shuffle_encounter(
            {"name": node.name, "level": node.level},
            len(camp.characters),
            st.session_state.user_settings.get("active_expansions", []),
            node.expansion,
            st.session_state.user_settings["edited_toggles"].get(
                f"edited_toggle_{node.name}_{node.expansion}", False
            ),
        )

        node.card_img = res["card_img"]
        node.enemies = res.get("enemies", [])


def render_current_location(node: Union[ProgressNode, EncounterChoice], camp: Campaign) -> Optional[ProgressNode]:
    if isinstance(node, ProgressNode):
        return node
    elif isinstance(node, EncounterChoice):
        if node.selected is None:
            return None
        else:
            return node.options[node.selected]
    return None


def _collect_valid_encounters(active_expansions: List[str], character_count: int, ruleset: Ruleset) -> Dict[int, List[Dict[str, Any]]]:
    """Return dict of level -> list of valid encounters for the given ruleset."""
    encounters_by_expansion = list_encounters()
    valid_sets = load_valid_sets()
    by_level: Dict[int, List[Dict[str, Any]]] = {}

    for expansion, enc_list in encounters_by_expansion.items():
        for e in enc_list:
            level = e.get("level")
            version = e.get("version")

            # Skip if ruleset doesn't match, unless it's a level 4 encounter
            if level != 4 and version != ruleset:
                continue

            key = f"{expansion}_{level}_{e['name']}"
            if encounter_is_valid(key, character_count, tuple(active_expansions), valid_sets):
                by_level.setdefault(level, []).append({
                    "name": e["name"],
                    "expansion": expansion,
                    "level": level,
                    "version": version,
                })

    return by_level

def _choose_boss(bosses: Dict[str, Any], boss_type: NodeType, active_expansions: List[str], randomize: bool = True) -> Optional[ProgressNode]:
    candidates = [b for b in bosses.values() if b["type"] == boss_type and any(exp in active_expansions for exp in b["expansions"])]
    if not candidates:
        return None
    chosen = random.choice(candidates) if randomize else candidates[0]
    return ProgressNode(name=chosen["name"], type=boss_type, expansion=chosen["expansions"][0], revealed=False)

def generate_v1_campaign(active_expansions: List[str], character_count: int, bosses: Dict[str, Any], randomize_bosses: bool = True) -> List[Chapter]:
    chapters: List[Chapter] = []
    by_level = _collect_valid_encounters(active_expansions, character_count, "V1")

    mini = _choose_boss(bosses, "mini boss", active_expansions, randomize_bosses)
    main = _choose_boss(bosses, "main boss", active_expansions, randomize_bosses)
    mega = _choose_boss(bosses, "mega boss", active_expansions, randomize_bosses)

    used_encounters = set()


    def pick_unique_encounter(lvl: int):
        pool = [e for e in by_level.get(lvl, []) if e["name"] not in used_encounters]
        if not pool:
            return ProgressNode(name=f"Unknown Level {lvl} Encounter", type="encounter", level=lvl, revealed=False)
        chosen = random.choice(pool)
        used_encounters.add(chosen["name"])

        # Immediately generate image + enemies
        res = shuffle_encounter(
            {"name": chosen["name"], "level": lvl},
            character_count,
            active_expansions,
            chosen["expansion"],
            st.session_state.user_settings["edited_toggles"].get(f"edited_toggle_{chosen['name']}_{chosen['expansion']}", False)
        )
        node = ProgressNode(
            name=chosen["name"],
            type="encounter",
            expansion=chosen["expansion"],
            level=lvl,
            revealed=False,
        )
        node.card_img = res["card_img"]
        node.enemies = res["enemies"]
        return node
    

    for boss in [mini, main, mega]:
        if boss:
            encounters: List[ProgressNode] = []
            for lvl in bosses[boss.name]["encounters"]:
                node = pick_unique_encounter(lvl)
                encounters.append(node)
            chapters.append(Chapter(boss=boss, encounters=encounters))

    return chapters

# -----------------------------
# Navigation helpers
# -----------------------------
def move_to_bonfire(camp: Campaign, spend_spark: bool = True):
    if spend_spark:
        camp.sparks = max(0, camp.sparks - 1)

    if camp.current_chapter is not None:
        chapter = camp.chapters[camp.current_chapter]
        # If the boss of this chapter is not yet completed,
        # reset all encounters in this chapter to incomplete
        if not chapter.boss.completed:
            for node in chapter.encounters:
                node.completed = False

    camp.current_chapter = None
    camp.current_index = None

# -----------------------------
# Campaign logic
# -----------------------------
def handle_boss_defeat(camp: Campaign):
    if camp.current_chapter is None:
        return
    chapter = camp.chapters[camp.current_chapter]
    # Mark boss as complete
    chapter.boss.completed = True
    chapter.boss.ever_completed = True
    chapter.boss.failed = False
    for n in chapter.encounters:
        n.completed = True
    # Collapse this chapter
    chapter.collapsed = True
    # Expand next chapter if exists
    if camp.current_chapter + 1 < len(camp.chapters):
        camp.chapters[camp.current_chapter + 1].collapsed = False
    # Reset sparks
    camp.sparks = max(0, 6 - len(camp.characters))
    # Return to bonfire
    move_to_bonfire(camp, spend_spark=False)

# -----------------------------
# Advance from Bonfire helper
# -----------------------------
def advance_from_bonfire(camp: Campaign):
    # find the index of the last completed boss
    last_completed_boss_chapter = -1
    for ci, chapter in enumerate(camp.chapters):
        if chapter.boss.completed:
            last_completed_boss_chapter = ci

    # start searching from the next chapter after the last completed boss
    start_chapter = last_completed_boss_chapter + 1

    for ci in range(start_chapter, len(camp.chapters)):
        chapter = camp.chapters[ci]
        if not chapter.boss.completed:
            # find first incomplete encounter
            for idx, node in enumerate(chapter.encounters):
                if not node.completed:
                    node.revealed = True
                    camp.current_chapter = ci
                    camp.current_index = idx
                    chapter.collapsed = False
                    return
            # if all encounters done, move to boss
            camp.current_chapter = ci
            camp.current_index = len(chapter.encounters)
            chapter.boss.revealed = True
            chapter.collapsed = False
            return
        

def get_boss_image(name: str):
    """Return image path for a given boss name."""
    image_path = BOSSES_IMAGES / f"{name}.jpg"
    return str(image_path)


# -----------------------------
# Public entry point
# -----------------------------
def render(settings):
    if "campaign_expander_collapsed" not in st.session_state:
        st.session_state["campaign_expander_collapsed"] = False

    bosses = load_bosses()

    with st.expander("📁 Campaigns — New / Save / Load", expanded=not st.session_state.get("campaign_expander_collapsed", False)):
        cols = st.columns([1, 2, 2])
        with cols[0]:
            name = st.text_input("Campaign Name", value="My Campaign")
        with cols[1]:
            ruleset = st.selectbox("Ruleset", ["V2", "V1"])
        with cols[2]:
            chars = st.session_state.user_settings.get("selected_characters", [])
            if st.button("Create New Campaign", use_container_width=True):
                if not chars:
                    st.warning("Select at least 1 character in the sidebar first.")
                else:
                    initial_sparks = max(0, 6 - len(chars))
                    with st.spinner("Generating campaign..."):
                        if ruleset == "V1":
                            chapters = generate_v1_campaign(
                                st.session_state.user_settings.get("active_expansions", []),
                                len(chars),
                                bosses,
                            )
                        else:
                            chapters = generate_v2_campaign(
                                st.session_state.user_settings.get("active_expansions", []),
                                len(chars),
                                bosses,
                            )
                    for ci, ch in enumerate(chapters):
                        ch.collapsed = ci != 0
                    camp = Campaign(
                        name=name,
                        ruleset=ruleset,
                        characters=list(chars),
                        sparks=initial_sparks,
                        chapters=chapters,
                        current_chapter=None,
                        current_index=None,
                    )
                    st.session_state["active_campaign"] = camp
                    st.success(f"{ruleset} Campaign created.")
                    st.session_state["campaign_expander_collapsed"] = True
                    st.rerun()

        # --------------------
        # Save / Load / Delete
        # --------------------
        saved = load_saved_campaigns()["campaigns"]

        # Save button only if an active campaign exists
        if "active_campaign" in st.session_state and st.session_state["active_campaign"]:
            camp = st.session_state["active_campaign"]
            save_name = st.text_input("Save campaign as:", value=camp.name or "")
            if st.button("💾 Save Campaign"):
                data = load_saved_campaigns()
                campaigns = data.get("campaigns", [])
                if len(campaigns) >= 5:
                    st.warning("You already have 5 saved campaigns. Delete one to save another.")
                else:
                    campaigns.append(camp.to_dict(name=save_name))
                    data["campaigns"] = campaigns
                    save_campaigns(data)
                    st.success(f"Campaign '{save_name}' saved!")

        # Load / delete section if saved campaigns exist
        if saved:
            names = [c["name"] for c in saved]
            choice = st.selectbox("Load a campaign:", names, key="load_campaign_choice")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📂 Load Selected"):
                    idx = names.index(choice)
                    loaded = Campaign.from_dict(saved[idx])
                    st.session_state["active_campaign"] = loaded
                    st.session_state["campaign_expander_collapsed"] = True
                    st.rerun()
            with col2:
                if st.button("🗑️ Delete Selected"):
                    idx = names.index(choice)
                    del saved[idx]
                    save_campaigns({"campaigns": saved})
                    st.rerun()

    camp: Optional[Campaign] = st.session_state.get("active_campaign")
    if not camp:
        return

    st.subheader(f"Campaign: {camp.name} • {camp.ruleset}")

    left_col, right_col = st.columns([2, 4])

    # Determine current node
    current_node = None
    if camp.current_chapter is not None and camp.current_index is not None:
        chapter = camp.chapters[camp.current_chapter]
        node = (chapter.encounters + [chapter.boss])[camp.current_index]
        current_node = render_current_location(node, camp)

    with left_col:
        # Party actions always on top
        st.markdown("### ⚔️ Party Actions")

        if camp.current_chapter is None:
            if st.button("🔥 Leave Bonfire", use_container_width=True):
                advance_from_bonfire(camp)
                st.session_state["active_campaign"] = camp
                st.rerun()

            # Gather shortcut options for the first incomplete chapter
            shortcut_nodes = []
            target_chapter = None
            for ci, chapter in enumerate(camp.chapters):
                if not chapter.boss.ever_completed:
                    target_chapter = ci
                    break

            if target_chapter is not None:
                chapter = camp.chapters[target_chapter]
                for idx, n in enumerate(chapter.encounters):
                    if (
                        isinstance(n, ProgressNode) and n.shortcut and n.ever_completed
                    ) or (
                        isinstance(n, EncounterChoice)
                        and n.selected is not None
                        and n.options[n.selected].shortcut
                        and n.options[n.selected].ever_completed
                    ):
                        shortcut_nodes.append((target_chapter, idx, n))

            if shortcut_nodes:
                options = {f"{n.name}": (ci, idx) for ci, idx, n in shortcut_nodes}
                choice = st.selectbox("Shortcuts:", list(options.keys()), key="shortcut_choice")
                if st.button("⏩ Take Shortcut", use_container_width=True):
                    ci, idx = options[choice]
                    camp.current_chapter = ci
                    camp.current_index = idx
                    st.session_state["active_campaign"] = camp
                    st.markdown("<div style='min-height:60px;'>", unsafe_allow_html=True)
                    st.rerun()
            else:
                st.markdown("<div style='min-height:170px;'>", unsafe_allow_html=True)
        else:
            chapter = camp.chapters[camp.current_chapter]
            nodes = chapter.encounters + [chapter.boss]
            node = nodes[camp.current_index]

            current_node = render_current_location(node, camp)

            if current_node:
                chapter = camp.chapters[camp.current_chapter]
                if current_node.type == "encounter":
                    if st.button("✅ Complete and Advance Party", use_container_width=True):
                        current_node.completed = True
                        current_node.ever_completed = True
                        clear_souls_tokens(camp, current_node)
                        nxt = camp.current_index + 1
                        if nxt < len(chapter.encounters) + 1:
                            (chapter.encounters + [chapter.boss])[nxt].revealed = True
                            camp.current_index = nxt
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    if st.button("↩️ Complete and Return to Bonfire", use_container_width=True):
                        current_node.completed = True
                        current_node.ever_completed = True
                        clear_souls_tokens(camp, current_node)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    if st.button("💀 Failed Encounter", use_container_width=True):
                        current_node.completed = False
                        fail_node(current_node)
                        clear_souls_tokens(camp, current_node, failed=True)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                elif current_node.type in ("mini boss", "main boss", "mega boss"):
                    if st.button("🏆 Defeat Boss (Return to Bonfire)", use_container_width=True):
                        clear_souls_tokens(camp, current_node)
                        handle_boss_defeat(camp)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    if st.button("💀 Failed Boss", use_container_width=True):
                        current_node.completed = False
                        fail_node(current_node)
                        clear_souls_tokens(camp, current_node, failed=True)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    st.markdown("<div style='min-height:77px;'>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='min-height:220px;'>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='min-height:210px;'></div>", unsafe_allow_html=True)

            # Close the min-height wrapper
            st.markdown("</div>", unsafe_allow_html=True)

        # Bonfire and chapters
        cols = st.columns([4, 1])
        with cols[0]:
            st.write(f"🔥 Bonfire - {camp.sparks} Spark{'' if camp.sparks == 1 else 's'}")
        with cols[1]:
            if camp.current_chapter is None:
                st.image(str(PARTY_TOKEN), width=32)

        for ci, chapter in enumerate(camp.chapters):
            boss_label = chapter.boss.name if chapter.boss.revealed else f"Unknown {chapter.boss.type.title()}"
            with st.expander(f"{boss_label} Chapter", expanded=not chapter.collapsed):
                for i, node in enumerate(chapter.encounters + [chapter.boss]):
                    cols = st.columns([4, 1, 1])
                    with cols[0]:
                        if isinstance(node, EncounterChoice):
                            if node.selected is None:
                                label = f"Unknown Level {node.level} Encounter"
                            else:
                                choice = node.options[node.selected]
                                label = choice.name if choice.revealed else f"Unknown Level {choice.level} Encounter"
                        else:
                            if not node.revealed:
                                if node.type == "encounter":
                                    label = f"Unknown Level {node.level} Encounter"
                                else:
                                    label = f"Unknown {node.type.title()}"
                            else:
                                label = node.name
                        st.write(label)
                    with cols[1]:
                        if camp.current_chapter == ci and camp.current_index == i:
                            st.image(str(PARTY_TOKEN), width=32)
                    with cols[2]:
                        if isinstance(node, EncounterChoice):
                            if node.selected is not None and node.options[node.selected].failed:
                                st.image(str(SOULS_TOKEN), width=32)
                        else:
                            if node.failed:
                                st.image(str(SOULS_TOKEN), width=32)

    with right_col:
        if camp.current_chapter is None:
            st.image(str(BONFIRE_IMAGE))
        elif current_node is None and camp.current_chapter is not None:
            # EncounterChoice selection
            chapter = camp.chapters[camp.current_chapter]
            node = (chapter.encounters + [chapter.boss])[camp.current_index]
            if isinstance(node, EncounterChoice) and node.selected is None:
                st.info("Choose one of the two encounters:")
                cols = st.columns(2)
                for i, option in enumerate(node.options):
                    with cols[i]:
                        ensure_encounter_image(option, camp)
                        if option.card_img:
                            st.image(option.card_img, width=230)
                        if st.button(
                            f"Choose {option.name}",
                            key=f"choose_{camp.current_chapter}_{camp.current_index}_{i}",
                        ):
                            node.selected = i
                            node.revealed = True
                            node.options[i].revealed = True
                            st.session_state["active_campaign"] = camp
                            st.rerun()
        elif current_node:
            if current_node.type in ("mini boss", "main boss", "mega boss"):
                boss_path = BOSSES_IMAGES / f"{current_node.name}.jpg"
                if boss_path.exists():
                    st.image(str(boss_path), width=400)
                else:
                    st.warning(f"No boss card for {current_node.name}")
            elif current_node.type == "encounter":
                ensure_encounter_image(current_node, camp)
                if current_node.card_img:
                    st.image(current_node.card_img, width=400)
                else:
                    st.warning(f"No encounter card for {current_node.name}")

    st.session_state["active_campaign"] = camp
