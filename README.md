# DSBG-Shuffle (Streamlit)

A Streamlit companion app for **Dark Souls: The Board Game** with local/offline and Streamlit Cloud options.

The app has a variety of modules that can enhance your DSBG experience either in preparation for play or at the table.

## 📖 New to DSBG-Shuffle? Start Here!

## Streamlit Cloud
You can access this app here: https://dsbg-shuffle.streamlit.app/
If you'd rather self-host it, see below.

Saving on the cloud site requires an account. See [Accounts & Sign-In](#accounts--sign-in-streamlit-cloud) below.

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
- **Python 3.14** (see `.python-version`)

`requirements.txt` is a fully pinned dependency set resolved for CPython 3.14, so
older interpreters will fail to find wheels for several pins. Direct dependencies
live in `requirements.in`; see the header of that file for how to change one.

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
- **Campaign Mode**: Setup / Manage Campaign / Play Encounter / Boss Fight tabs.
- **Character Mode**: Character build tool.
- **Behavior Card Viewer**: Quick viewer for behavior cards.

## Accounts & Sign-In (Streamlit Cloud)

The cloud site uses **Supabase email + password** accounts. Google sign-in and email
magic links have been removed; if you used either one before, see
[Migrating from Google / magic-link](#migrating-from-google--magic-link) below.

The account controls live at the top of the sidebar, with three actions:

### Sign Up

Enter an email and a password, then Submit. If the Supabase project requires email
confirmation you’ll be told to confirm via email before logging in; otherwise you’re
logged in immediately.

### Log In

Enter your email and password. Your session is stored in a browser cookie that lasts
**30 days**, so you normally stay logged in across visits and reruns. The access token
is refreshed automatically while you use the app.

**Log Out** signs out only the device you clicked it on — your other devices stay
logged in.

### Reset/Migrate

This one form handles both a forgotten password and migrating a legacy account:

1. Enter your email, leave the code box blank, and Submit. Supabase emails you an
   **8-digit recovery code**.
2. Enter that code plus a new password, then Submit. The password is bound to your
   existing account and you’re logged in.

#### Migrating from Google / magic-link

If you previously signed in with Google or an email magic link, use **Reset/Migrate**
with the *same email address* you used before. Setting a password attaches it to that
existing account, so all your saved settings, encounters, campaigns, and character
builds come with you. Do **not** use Sign Up — that creates a new, empty account.

### Notes for self-hosters

The account UI only appears when the deployment is configured as cloud **and**
Supabase credentials are present. In Streamlit secrets (or environment variables):

- `DSBG_DEPLOYMENT = "cloud"`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Without those, local and Docker runs skip auth entirely and persist to JSON on disk.

## Data & Persistence

The app ships with JSON and image assets in the repo:

- `data/`: game data, user settings, saved encounters, campaign data, etc.
- `assets/`: images used throughout the UI

Settings:
- Local runs persist to `data/user_settings.json`.
- Docker runs persist `data/` in a volume (so updates/rebuilds keep your data).

Streamlit Cloud:
- Saving requires an account (email + password — see [Accounts & Sign-In](#accounts--sign-in-streamlit-cloud)).
- Saved data is tied to the account, not the device, so logging in elsewhere brings it with you.
- When logged out, settings changes still affect the current session, but nothing is saved.

## AI Disclaimer

This app was built with the help of AI. For years I've wanted to have a version of DSBG-Shuffle that could be used on a mobile device because it just makes using it at the gaming table easier. Finally I turned to AI to help me set that up. It would have taken far longer without it. AI was also helpful in choosing the platform. I went with Streamlit because it's pretty much just Python and that means I will be able to support it and continue development without having to depend on AI.
