import streamlit as st
import json
from core.settings_manager import save_settings
from core import events as events_core

def render():
    settings = st.session_state.user_settings

    if "campaigns" not in settings:
        settings["campaigns"] = {}

    st.header("📜 Campaign Manager")

    # -------------------
    # Campaign selection
    # -------------------
    campaign_names = list(settings["campaigns"].keys())
    selected_campaign = st.selectbox(
        "Select a campaign:",
        ["(none)"] + campaign_names,
        index=0
    )

    # Track "current campaign" for other tabs
    if selected_campaign != "(none)":
        settings["current_campaign"] = selected_campaign
    else:
        settings["current_campaign"] = None

    # -------------------
    # Create new campaign
    # -------------------
    with st.expander("➕ Create New Campaign"):
        new_name = st.text_input("Campaign Name")
        if st.button("Create Campaign"):
            if not new_name:
                st.warning("Please provide a campaign name.")
            elif new_name in settings["campaigns"]:
                st.warning("That name already exists.")
            else:
                settings["campaigns"][new_name] = {
                    "active_expansions": settings.get("active_expansions", []),
                    "selected_characters": settings.get("selected_characters", []),
                    "spark_count": 5,
                    "progress_index": 0,
                    "sequence": []
                }
                save_settings(settings)
                st.success(f"Campaign '{new_name}' created!")
                st.rerun()

    # -------------------
    # Campaign detail view
    # -------------------
    if selected_campaign != "(none)":
        camp = settings["campaigns"][selected_campaign]

        st.subheader(f"🎯 {selected_campaign}")

        # Expansions & party
        st.markdown("**Expansions:** " + ", ".join(camp.get("active_expansions", [])))
        st.markdown("**Party:** " + ", ".join(camp.get("selected_characters", [])))

        # Sparks counter
        st.write("🔥 Sparks remaining:")
        col1, col2, col3 = st.columns([1,1,3])
        with col1:
            if st.button("➖", key="spark_minus"):
                camp["spark_count"] = max(0, camp["spark_count"] - 1)
                save_settings(settings)
                st.rerun()
        with col2:
            if st.button("➕", key="spark_plus"):
                camp["spark_count"] += 1
                save_settings(settings)
                st.rerun()
        with col3:
            st.write(f"{camp['spark_count']} sparks")

        # Progress tracker
        st.write(f"📍 Progress index: {camp['progress_index']}")
        if st.button("Advance Progress"):
            camp["progress_index"] += 1
            save_settings(settings)
            st.rerun()

        # -------------------
        # Edit Mode
        # -------------------
        edit_mode = st.checkbox("✏️ Edit Campaign", value=False)

        if edit_mode:
            st.info("Sequence of encounters and bosses. Use ⬆️/⬇️/🗑️ controls to manage order.")

            if not camp.get("sequence"):
                st.caption("Empty campaign — add encounters or bosses from their tabs.")
            else:
                for i, item in enumerate(camp["sequence"]):
                    if item["type"] == "encounter":
                        st.markdown(f"**Encounter:** {item['name']} (Lv {item['level']}, {item['expansion']})")

                        # Attached events
                        if item.get("events"):
                            for j, ev in enumerate(item["events"]):
                                ev_cols = st.columns([5,1])
                                ev_cols[0].write(f"↳ {ev['name']} ({ev['type']})")
                                if ev_cols[1].button("🗑️", key=f"del_ev_{i}_{j}"):
                                    item["events"].pop(j)
                                    save_settings(settings); st.rerun()
                        else:
                            st.caption("↳ No events attached")

                        # Add event inline (dropdown of all events)
                        if st.button("➕ Add Event", key=f"add_ev_{i}"):
                            st.session_state[f"adding_event_{i}"] = True
                        if st.session_state.get(f"adding_event_{i}", False):
                            configs = events_core.load_event_configs(camp.get("active_expansions", []))
                            all_cards = {}
                            for exp, conf in configs.items():
                                for ev in conf.get("events", []):
                                    all_cards[ev["name"]] = {"expansion": exp, "type": ev.get("type", "normal")}
                            selected_ev = st.selectbox("Select Event", ["(none)"] + list(all_cards.keys()), key=f"ev_sel_{i}")
                            if selected_ev != "(none)" and st.button("Confirm Add", key=f"confirm_ev_{i}"):
                                add_event_to_encounter(item, all_cards[selected_ev]["type"], selected_ev)
                                save_settings(settings); st.rerun()

                    elif item["type"] == "boss":
                        st.markdown(f"**Boss:** {item['name']}")

                    # Reorder/remove controls
                    cols = st.columns([1,1,1])
                    if cols[0].button("⬆️", key=f"up_{i}") and i > 0:
                        camp["sequence"][i-1], camp["sequence"][i] = camp["sequence"][i], camp["sequence"][i-1]
                        save_settings(settings); st.rerun()
                    if cols[1].button("⬇️", key=f"down_{i}") and i < len(camp["sequence"])-1:
                        camp["sequence"][i+1], camp["sequence"][i] = camp["sequence"][i], camp["sequence"][i+1]
                        save_settings(settings); st.rerun()
                    if cols[2].button("🗑️", key=f"del_{i}"):
                        camp["sequence"].pop(i)
                        save_settings(settings); st.rerun()

        # -------------------
        # Export / Import / Delete
        # -------------------
        st.divider()
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.download_button(
                "⬇️ Export Campaign",
                data=json.dumps(camp, indent=2),
                file_name=f"{selected_campaign}.json",
                mime="application/json"
            ):
                st.success("Campaign exported!")

        with col2:
            uploaded = st.file_uploader("⬆️ Import Campaign", type="json", key="import_campaign")
            if uploaded:
                try:
                    imported = json.load(uploaded)
                    if "sequence" in imported:
                        settings["campaigns"][selected_campaign + " (imported)"] = imported
                        save_settings(settings)
                        st.success("Campaign imported!")
                        st.rerun()
                    else:
                        st.error("Invalid campaign file.")
                except Exception as e:
                    st.error(f"Failed to import: {e}")

        with col3:
            if st.button("🗑️ Delete Campaign"):
                del settings["campaigns"][selected_campaign]
                save_settings(settings)
                st.success("Campaign deleted.")
                st.rerun()


def add_event_to_encounter(encounter, ev_type, ev_name):
    """Attach an event to an encounter enforcing rules."""
    if "events" not in encounter:
        encounter["events"] = []

    # Enforce 3 max
    if ev_type != "rendezvous" and len(encounter["events"]) >= 3:
        st.warning("This encounter already has 3 events. Cannot add more.")
        return

    if ev_type == "rendezvous":
        # If rendezvous already exists, discard old
        old_rendezvous = next((e for e in encounter["events"] if e["type"] == "rendezvous"), None)
        if old_rendezvous:
            encounter["events"] = [e for e in encounter["events"] if e["type"] != "rendezvous"]
            st.warning(f"{old_rendezvous['name']} was discarded (only one rendezvous allowed).")
        if len(encounter["events"]) >= 3:
            st.warning("Encounter is full. Cannot add another rendezvous.")
            return

    encounter["events"].append({"name": ev_name, "type": ev_type})
    st.success(f"Added {ev_name} ({ev_type}) to {encounter['name']}")
