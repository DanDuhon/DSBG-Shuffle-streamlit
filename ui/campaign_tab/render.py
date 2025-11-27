#ui/campaign_tab/render.py
import streamlit as st
from typing import Optional

from ui.campaign_tab.models import ProgressNode, Campaign, EncounterChoice
from ui.campaign_tab.generation import load_bosses, cached_generate_campaign
from ui.campaign_tab.logic import move_to_bonfire, handle_boss_defeat, render_current_location, advance_from_bonfire, clear_souls_tokens, fail_node, ensure_encounter_image
from ui.campaign_tab.persistence import load_saved_campaigns, save_campaigns
from ui.campaign_tab.assets import BONFIRE_IMAGE, PARTY_TOKEN, SOULS_TOKEN, BOSSES_IMAGES, get_asset_image


def render():
    if "campaign_expander_collapsed" not in st.session_state:
        st.session_state["campaign_expander_collapsed"] = False

    bosses = load_bosses()

    with st.expander("📁 Campaigns — New / Save / Load", expanded=not st.session_state.get("campaign_expander_collapsed", False)):
        with st.form("new_campaign_form"):
            cols = st.columns([1, 2, 2])
            with cols[0]:
                name = st.text_input("Campaign Name", value="My Campaign")
            with cols[1]:
                ruleset = st.selectbox("Ruleset", ["V2", "V1"])
            with cols[2]:
                chars = st.session_state.user_settings.get("selected_characters", [])
                submitted = st.form_submit_button("Create New Campaign", width="stretch")
                if submitted:
                    if not chars:
                        st.warning("Select at least 1 character in the sidebar first.")
                    else:
                        initial_sparks = max(0, 6 - len(chars))
                        chapters = cached_generate_campaign(
                            ruleset,
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
        saved = load_saved_campaigns().get("campaigns", {})

        # Save button only if an active campaign exists
        if "active_campaign" in st.session_state and st.session_state["active_campaign"]:
            camp = st.session_state["active_campaign"]
            with st.form("save_campaign_form"):
                save_name = st.text_input("Save campaign as:", value=camp.name or "")
                submitted = st.form_submit_button("💾 Save Campaign")
                if submitted:
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
            with st.form("load_campaign_form"):
                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("📂 Load Selected")
                    if submitted:
                        idx = names.index(choice)
                        loaded = Campaign.from_dict(saved[idx])
                        st.session_state["active_campaign"] = loaded
                        st.session_state["campaign_expander_collapsed"] = True
                        st.rerun()
                with col2:
                    submitted = st.form_submit_button("🗑️ Delete Selected")
                    if submitted:
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
            if st.button("🔥 Leave Bonfire", width="stretch"):
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
                
                if st.button("⏩ Take Shortcut", width="stretch"):
                    ci, idx = options[choice]
                    camp.current_chapter = ci
                    camp.current_index = idx
                    st.session_state["active_campaign"] = camp
                    st.markdown("<div style='min-height:60px;'></div>", unsafe_allow_html=True)
                    st.rerun()
            else:
                st.markdown("<div style='min-height:170px;'></div>", unsafe_allow_html=True)
        else:
            chapter = camp.chapters[camp.current_chapter]
            nodes = chapter.encounters + [chapter.boss]
            node = nodes[camp.current_index]

            current_node = render_current_location(node, camp)

            if current_node:
                chapter = camp.chapters[camp.current_chapter]
                if current_node.type == "encounter":
                    if st.button("✅ Complete and Advance Party", width="stretch"):
                        current_node.completed = True
                        current_node.ever_completed = True
                        clear_souls_tokens(camp, current_node)
                        nxt = camp.current_index + 1
                        if nxt < len(chapter.encounters) + 1:
                            (chapter.encounters + [chapter.boss])[nxt].revealed = True
                            camp.current_index = nxt
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                
                    if st.button("↩️ Complete and Return to Bonfire", width="stretch"):
                        current_node.completed = True
                        current_node.ever_completed = True
                        clear_souls_tokens(camp, current_node)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()

                    if st.button("💀 Failed Encounter", width="stretch"):
                        current_node.completed = False
                        fail_node(current_node)
                        clear_souls_tokens(camp, current_node, failed=True)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                elif current_node.type in ("mini boss", "main boss", "mega boss"):
                    if st.button("🏆 Defeat Boss (Return to Bonfire)", width="stretch"):
                        clear_souls_tokens(camp, current_node)
                        handle_boss_defeat(camp)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    if st.button("💀 Failed Boss", width="stretch"):
                        current_node.completed = False
                        fail_node(current_node)
                        clear_souls_tokens(camp, current_node, failed=True)
                        move_to_bonfire(camp, spend_spark=True)
                        st.session_state["active_campaign"] = camp
                        st.rerun()
                    st.markdown("<div style='min-height:77px;'></div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='min-height:220px;'></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='min-height:210px;'></div>", unsafe_allow_html=True)

        # Bonfire and chapters
        cols = st.columns([4, 1])
        with cols[0]:
            st.write(f"🔥 Bonfire - {camp.sparks} Spark{'' if camp.sparks == 1 else 's'}")
        with cols[1]:
            if camp.current_chapter is None:
                st.image(get_asset_image(str(PARTY_TOKEN)), width=32)

        for ci, chapter in enumerate(camp.chapters):
            boss_label = chapter.boss.name if chapter.boss.revealed else f"Unknown {chapter.boss.type.title()}"
            with st.expander(f"{boss_label} Chapter", expanded=not chapter.collapsed):
                for i, node in enumerate(chapter.encounters + [chapter.boss]):
                    cols = st.columns([5, 1, 1])
                    with cols[0]:
                        show_img = False
                        if isinstance(node, EncounterChoice):
                            if node.selected is None:
                                label = f"Unknown Level {node.level} Encounter"
                            else:
                                choice = node.options[node.selected]
                                if choice.revealed:
                                    label = choice.name
                                    show_img = True
                                else:
                                    label = f"Unknown Level {choice.level} Encounter"
                        else:
                            if not node.revealed:
                                if node.type == "encounter":
                                    label = f"Unknown Level {node.level} Encounter"
                                else:
                                    label = f"Unknown {node.type.replace('_', ' ').title()}"
                            else:
                                label = node.name
                        if show_img:
                                # Wrap text and thumbnail side-by-side
                                inner_cols = st.columns([3, 1])
                                with inner_cols[0]:
                                    st.markdown(node.name)
                                with inner_cols[1]:
                                    st.image(get_asset_image(node.options[node.selected].card_img))
                        else:
                            st.write(label)
                    with cols[1]:
                        if camp.current_chapter == ci and camp.current_index == i:
                            st.image(get_asset_image(str(PARTY_TOKEN)), width=32)
                    with cols[2]:
                        if isinstance(node, EncounterChoice):
                            if node.selected is not None and node.options[node.selected].failed:
                                st.image(get_asset_image(str(SOULS_TOKEN)), width=32)
                        else:
                            if node.failed:
                                st.image(get_asset_image(str(SOULS_TOKEN)), width=32)

    with right_col:
        if camp.current_chapter is None:
            st.image(get_asset_image(str(BONFIRE_IMAGE)))
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
                            st.image(get_asset_image(option.card_img), width=230)
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
                    st.image(get_asset_image(str(boss_path)), width=400)
                else:
                    st.warning(f"No boss card for {current_node.name}")
            elif current_node.type == "encounter":
                ensure_encounter_image(current_node, camp)
                if current_node.card_img:
                    st.image(get_asset_image(current_node.card_img), width=400)
                else:
                    st.warning(f"No encounter card for {current_node.name}")

    st.session_state["active_campaign"] = camp
