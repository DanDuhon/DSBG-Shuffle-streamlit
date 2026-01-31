# DSBG-Shuffle (Streamlit)

A Streamlit companion app for **Dark Souls: The Board Game** with local/offline and Streamlit Cloud options.

The app has a variety of modules that can enhance your DSBG experience either in preparation for play or at the table.

## 📖 New to DSBG-Shuffle? Start Here!

## Streamlit Cloud
You can access this app here: https://dsbg-shuffle.streamlit.app/
If you'd rather self-host it, see below.

## Self-Hosting
**For detailed, beginner-friendly setup instructions, see [SETUP.md](SETUP.md)**

The SETUP.md guide includes:
- Step-by-step instructions for complete beginners
- How to install Python and Docker (with explanations of what they are)
- Detailed local and Docker setup guides
- How to access the app from other devices (tablets, phones, etc.)
- Comprehensive troubleshooting section
- Quick reference commands

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
- Saving requires an account (Google OAuth or email magic-link).
- When logged out, settings changes still affect the current session, but nothing is saved.

## AI Disclaimer

This app was built with the help of AI. For years I've wanted to have a version of DSBG-Shuffle that could be used on a mobile device because it just makes using it at the gaming table easier. Finally I turned to AI to help me set that up. It would have taken far longer without it. AI was also helpful in choosing the platform. I went with Streamlit because it's pretty much just Python and that means I will be able to support it and continue development without having to depend on AI.
