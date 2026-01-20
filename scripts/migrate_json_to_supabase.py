"""Simple migration script to push existing JSON files from `data/` to Supabase.

Usage:
  SUPABASE_URL=https://... SUPABASE_KEY=yourkey python scripts/migrate_json_to_supabase.py

This script does not require Streamlit and uses the same PostgREST upsert pattern
as `core.supabase_store`.
"""
import os
import sys
import json
import glob
import requests
from pathlib import Path


def _base_url():
    url = os.environ.get("SUPABASE_URL")
    return url.rstrip("/")


def _key():
    key = os.environ.get("SUPABASE_KEY")
    return key


def _table_url():
    return f"{_base_url()}/rest/v1/app_documents"


def _headers():
    k = _key()
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def upsert(payloads):
    url = _table_url()
    params = {"on_conflict": "doc_type,key_name,user_id"}
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    resp = requests.post(url, headers=headers, params=params, json=payloads)
    resp.raise_for_status()
    return resp.json()


def push_user_settings(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    payload = [{"doc_type": "user_settings", "key_name": "default", "data": data}]
    return upsert(payload)


def push_saved_encounters(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    payloads = []
    for name, obj in data.items():
        payloads.append({"doc_type": "saved_encounter", "key_name": name, "data": obj})
    if payloads:
        return upsert(payloads)
    return []


def push_campaigns(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    payloads = []
    for key, obj in data.items():
        payloads.append({"doc_type": "campaign", "key_name": key, "data": obj})
    if payloads:
        return upsert(payloads)
    return []


def push_character_builds(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    payloads = []
    for name, obj in data.items():
        payloads.append({"doc_type": "character_build", "key_name": name, "data": obj})
    if payloads:
        return upsert(payloads)
    return []


def push_event_decks(path: Path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    payloads = []
    decks = data.get("decks") if isinstance(data, dict) else {}
    for name, deck in decks.items():
        payloads.append({"doc_type": "event_deck", "key_name": name, "data": deck})
    if payloads:
        return upsert(payloads)
    return []


def main():
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    if not data_dir.exists():
        print("data/ directory not found; run from repo root")
        sys.exit(1)

    print("Pushing user_settings.json...")
    print(push_user_settings(data_dir / "user_settings.json"))

    print("Pushing saved_encounters.json...")
    print(push_saved_encounters(data_dir / "saved_encounters.json"))

    print("Pushing campaigns.json...")
    print(push_campaigns(data_dir / "campaigns.json"))

    print("Pushing character_builds.json...")
    print(push_character_builds(data_dir / "character_builds.json"))

    print("Pushing custom_event_decks.json...")
    print(push_event_decks(data_dir / "custom_event_decks.json"))

    print("Migration complete.")


if __name__ == "__main__":
    main()
