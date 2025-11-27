#ui/campaign_tab/persistence.py
import streamlit as st
from json import loads, dumps
from typing import Dict, Any

from ui.campaign_tab.assets import CAMPAIGNS_FILE
from ui.campaign_tab.models import Campaign


def load_saved_campaigns():
    if CAMPAIGNS_FILE.exists():
        try:
            return loads(CAMPAIGNS_FILE.read_text("utf-8"))
        except Exception:
            return {"campaigns": []}
    return {"campaigns": []}


def save_campaigns(data):
    CAMPAIGNS_FILE.write_text(dumps(data, indent=2))


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


def _default_store() -> Dict[str, Any]:
    return {"campaigns": []}


def load_store() -> Dict[str, Any]:
    if CAMPAIGNS_FILE.exists():
        try:
            return loads(CAMPAIGNS_FILE.read_text("utf-8"))
        except Exception:
            return _default_store()
    return _default_store()


def save_store(store: Dict[str, Any]) -> None:
    CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_FILE.write_text(dumps(store, indent=2), encoding="utf-8")
