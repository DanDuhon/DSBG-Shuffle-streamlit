#ui/campaign_tab/logic.py
import streamlit as st
from typing import Optional, Union

from ui.campaign_tab.models import ProgressNode, Campaign, EncounterChoice
from ui.campaign_tab.assets import BOSSES_IMAGES
from ui.campaign_tab.generation import cached_encounter_image
from ui.encounters_tab.logic import shuffle_encounter


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
    # V1: Reset sparks
    if camp.ruleset == "V1":
        camp.sparks = max(0, 6 - len(camp.characters))
    else:
        camp.sparks += 1
    # Return to bonfire
    move_to_bonfire(camp, spend_spark=False)


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
    
    if node.enemies:
        res = cached_encounter_image(
            node.expansion,
            node.level,
            node.name,
            node.enemies,
            len(camp.characters),
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


def get_boss_image(name: str):
    """Return image path for a given boss name."""
    image_path = BOSSES_IMAGES / f"{name}.jpg"
    return str(image_path)