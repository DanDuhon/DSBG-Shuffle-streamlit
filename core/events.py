import json
import random
import base64
from collections import defaultdict
from pathlib import Path


DATA_DIR = Path("data/events")
ASSETS_DIR = Path("assets/events")

V2_EXPANSIONS = [
    "Painted World of Ariamis",
    "Tomb of Giants",
    "The Sunless City"
]


def img_to_base64(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii")


def load_event_configs(active_expansions=None):
    """Load event configs grouped by expansion."""
    configs = {}
    for json_file in DATA_DIR.glob("*.json"):
        expansion = json_file.stem
        if active_expansions and expansion not in active_expansions:
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                configs[expansion] = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load {json_file}: {e}")
    return configs


def build_deck(configs):
    """Build a shuffled deck from configs. Returns a list of image paths."""
    deck = []
    for expansion, conf in configs.items():
        for ev in conf.get("events", []):
            image = ASSETS_DIR / ev["image"]
            copies = ev.get("copies", 1)
            deck.extend([str(image)] * copies)
    random.shuffle(deck)
    return deck


def build_mixed_v2_deck(configs):
    """
    Build a combined V2 deck (Painted World, Tomb of Giants, Sunless City).
    - Each event image included at most max(copies) across expansions.
    """
    counts = defaultdict(int)

    for exp in V2_EXPANSIONS:
        if exp not in configs:
            continue
        for ev in configs[exp].get("events", []):
            image = ASSETS_DIR / ev["image"]
            copies = ev.get("copies", 1)
            counts[str(image)] = max(counts[str(image)], copies)

    deck = []
    for image, copies in counts.items():
        deck.extend([image] * copies)

    random.shuffle(deck)
    return deck
