# Dark Souls Board Game Web Companion

This is a Streamlit web app for managing Dark Souls: The Board Game encounters, events, behaviors, and campaign tracking.
This is a refactor of the original desktop app: https://github.com/DanDuhon/DSBG-Shuffle

# 🚀 Features (current & planned)

## Encounter Mode –
- Browse encounters.
- Shuffle enemies while maintaining a relative level of difficulty.
- Some encounters have toggle-able edits. Most of these discourage resting/healing between tiles within an encounter.
- Attach random or specific events to an encounter.
- Play encounters, displaying enemy behavior cards edited per encounter/event rules. Support for Timer/trigger based rules.

## Event Mode –
- View event cards.
- Simulate event card decks.
- Create custom event decks.

## Campaign Mode –
- Generate V1 or V2 campaigns.
- Play through a campaign using the encounters drawn.
- V1 campaigns generate the tile layout.
- Track souls and sparks with some automation.
- Save & load campaign.

## Boss Mode –
- Simulate boss behavior decks, track health, handle heat-up and special rules.

## Character Mode –
- Create character builds, see expected damage output and defensive stats.
- Save/load character builds.

# Installation
## Local (no Docker)
```
# clone repo
git clone https://github.com/yourusername/DSBG-Shuffle_streamlit.git
cd DSBG-Shuffle-streamlit

# install dependencies
pip install -r requirements.txt

# run app
streamlit run app.py
```

## Docker
