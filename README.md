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
You can run the app in two ways (but only one at a time unless you give them different ports):
### Lightweight (fast, dev-friendly)
- Small image, skips large data/ and assets/ during build.
- Requires you to mount them at runtime.
```
docker build -f Dockerfile.light -t dsbg-web:light .
docker run -p 8501:8501 -v $(pwd)/data:/app/data -v $(pwd)/assets:/app/assets dsbg-web:light
```

### Full Offline (self-contained)
- Larger image, but includes all JSON + images.
- Runs anywhere with no mounted volumes needed.
```
docker build -f Dockerfile.full -t dsbg-web:full .
docker run -p 8501:8501 dsbg-web:full
```

### Docker Compose
To simplify switching between builds, use docker-compose.yml.

**Run lightweight build**
`docker compose up dsbg-light`
- Runs on http://localhost:8501
- Fast rebuilds
- Requires local `./data` + `./assets` folders

**Run full offline build**
`docker compose up dsbg-full`
- Runs on http://localhost:8501
- Larger image, but 100% portable

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
├── Dockerfile.light
├── Dockerfile.full
├── docker-compose.yml
├── .dockerignore
└── README.md
```
