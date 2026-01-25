# DSBG-Shuffle (Streamlit)

A Streamlit companion app for **Dark Souls: The Board Game** with local/offline and Streamlit Cloud options.

The app has a variety of modules that can enhance your DSBG experience either in preparation for play or at the table.


## Quickstart (Local)

Prereqs:
- Python 3.11+ recommended

From the repo root:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501

Important: the app uses relative paths and expects to run from the **repository root**.

## Quickstart (Docker)

The container binds Streamlit on port **8501** and persists `data/` via a named Docker volume.

```bash
docker compose up --build
```

Open:
- http://localhost:8501 (same machine)
- http://<your-lan-ip>:8501 (other devices on your LAN)

Resetting persisted data (this deletes saved settings/campaigns/encounters stored under `data/`):

```bash
docker compose down
docker volume rm dsbg-shuffle-streamlit_dsbg_data
```

Windows LAN note: if other devices can’t connect, allow inbound TCP **8501** in Windows Defender Firewall.

## What’s In The App

In the sidebar you’ll choose a **Mode**:

- **Encounter Mode**: Setup / Events / Play tabs for encounters.
- **Event Mode**: Event deck builder plus an event card viewer.
- **Boss Mode**: Boss selector + behavior deck controls, heat-up, and trackers.
- **Campaign Mode**: Campaign setup and play encounters from the campaign.
- **Character Mode**: Character build tool.
- **Behavior Card Viewer**: Quick viewer for behavior cards.

## Data & Persistence

The app ships with JSON and image assets in the repo:

- `data/`: game data, user settings, saved encounters, campaign data, etc.
- `assets/`: images used throughout the UI

Settings:
- Local runs persist to `data/user_settings.json`.
- Docker runs persist `data/` in a volume (so updates/rebuilds keep your data).

Streamlit Cloud:
- Saving requires an account (Google OAuth, with email magic-link fallback).
- When logged out, settings changes still affect the current session, but nothing is saved.

## Streamlit Cloud Secrets

This app supports Streamlit Cloud configuration via Secrets.

Recommended Secrets:

- `DSBG_DEPLOYMENT = "cloud"` (enables Cloud-only behavior)
- `DSBG_CACHE_EMBEDDED_FONTS = true` (keeps embedded fonts but avoids rebuilding base64 CSS on reruns)
- `DSBG_DISABLE_ENCOUNTER_IMAGE_CACHES = true` (prevents caching encounter-card asset images on Cloud)
  - Note: when enabled, the app also tightens a few large in-process `lru_cache` sizes (enemy icon resizing + encounter availability checks) to reduce Cloud RAM pressure.
- `DSBG_DEBUG_PERF = true` (optional; shows a small Diagnostics panel in the sidebar)

If you use Supabase persistence, also set:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (preferred)

Then, in the Supabase dashboard:
- Enable Auth providers: Google (primary) and Email (magic link fallback).
- Create the `app_documents` table (see `core/supabase_store.py` docstring for the expected columns).
- Enable Row Level Security (RLS) so users can only access their own rows.
