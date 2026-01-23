# Dark Souls Board Game Web Companion

This is a Streamlit web app for managing Dark Souls: The Board Game encounters, events, behaviors, and campaign tracking.
Originally a Tkinter desktop app called DSBG-Shuffle, it is being refactored into a modular web companion.

# 🚀 Features (current & planned)

## ✅ Encounters Tab –
- Browse encounters by expansion
- Mix enemies together in existing encounters
- Toggle original/edited keywords with tooltips
- Party filtering (up to 4 characters)

## 🃏 Events Tab (coming soon) –
- View event cards
- Simulate event card decks

## 📜 Campaign Tab (coming soon) –
- Build or track campaigns
- Save & load campaign state

## ⚔️ Behavior Variants Tab (coming soon) –
- Scale enemy difficulty with prebuilt variants

## 🧩 Behavior Decks Tab (coming soon) –
- Simulate enemy behavior decks
- Track health, heat-up, invaders, bosses

# 🛠️ Installation
## Local (no Docker)
```
# clone repo
git clone https://github.com/yourusername/dsbg-web.git
cd dsbg-web

# install dependencies
pip install -r requirements.txt

# run app
streamlit run app.py
```

## 🐳 Docker Options
This repo supports a single, self-contained Docker image intended for offline / local LAN use.

### Docker Compose (recommended)
Build and start the app:
```
docker compose up --build
```

Then open:
- http://localhost:8501 (same machine)
- http://<your-lan-ip>:8501 (other devices on your LAN)

**Windows LAN note:** if other devices can't connect, allow inbound TCP port `8501` in Windows Defender Firewall (or temporarily disable the firewall to confirm it's the issue).

### Persistence (important)
The container uses a named Docker volume for `data/` so your changes persist across updates.

If you want to reset to a fresh install (this deletes saved settings/campaigns):
```
docker compose down
docker volume rm dsbg-shuffle-streamlit_dsbg_data
```

### Updating
Pull latest code and rebuild:
```
docker compose up --build
```

# 📂 Project Structure
```
dsbg-app/
│
├── app.py                # orchestrates tabs
│
├── ui/                   # tab UIs
│   ├── sidebar.py
│   ├── encounters.py
│   ├── encounter_helpers.py
│   ├── events.py
│   ├── campaign.py
│   ├── variants.py
│   └── decks.py
│
├── core/                 # data + logic
│   ├── encounters.py
│   ├── enemyNames.py
│   ├── characters.py
│   ├── encounterKeywords.py
│   ├── editedEncounterKeywords.py
│   └── settings_manager.py
│
├── data/                 # JSON encounter + event data
├── assets/               # images (enemy icons, encounter cards, keywords)
├── requirements.txt
├── Dockerfile
├── docker-compose.yaml
├── .dockerignore
└── README.md
```
