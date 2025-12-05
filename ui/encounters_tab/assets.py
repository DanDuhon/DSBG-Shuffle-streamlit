#ui/encounters_tab/assets.py
import streamlit as st
from PIL import Image
from pathlib import Path


ENCOUNTER_CARDS_DIR = Path("assets/encounter cards")
EDITED_ENCOUNTER_CARDS_DIR = Path("assets/edited encounter cards")
ENEMY_ICONS_DIR = Path("assets/enemy icons")
KEYWORDS_DIR = Path("assets/keywords")

v1Expansions = {
    "Dark Souls The Board Game",
    "Darkroot",
    "Explorers",
    "Iron Keep"
}

v1Level4s = {
    "Executioner Chariot",
    "Executioner's Chariot",  # allow both spellings
    "Asylum Demon",
    "Black Dragon Kalameet",
    "Gaping Dragon",
    "Guardian Dragon",
    "Manus, Father of the Abyss",
    "Old Iron King",
    "The Four Kings",
    "The Last Giant",
    "Vordt of the Boreal Valley"
}

positions = {
    "V2": {
        (0, 0): (609, 663),
        (0, 1): (667, 663),
        (0, 2): (725, 663),
        (1, 0): (609, 721),
        (1, 1): (667, 721),
        (1, 2): (725, 721),
        (5, 0): (609, 911),
        (5, 1): (667, 911),
        (5, 2): (725, 911),
        (6, 0): (609, 969),
        (6, 1): (667, 969),
        (6, 2): (725, 969),
        (8, 0): (609, 1159),
        (8, 1): (667, 1159),
        (8, 2): (725, 1159),
        (9, 0): (609, 1217),
        (9, 1): (667, 1217),
        (9, 2): (725, 1217)
    },
    "V2Level4": {},
    "V1": {
        (0, 0): (370, 370),
        (0, 1): (600, 370),
        (0, 2): (830, 370),
        (1, 0): (370, 620),
        (1, 1): (600, 620),
        (1, 2): (830, 620),
    },
    "V1Level4": {}
}

editedEncounterKeywords = {
    ("Eye of the Storm", "Painted World of Ariamis"): ["hidden","timer"],
    ("Frozen Revolutions", "Painted World of Ariamis"): ["trial"],
    ("Inhospitable Ground", "Painted World of Ariamis"): ["snowstorm", "bitterCold"],
    ('No Safe Haven', 'Painted World of Ariamis'): ["poisonMist", "snowstorm", "bitterCold"],
    ("Promised Respite", "Painted World of Ariamis"): ["snowstorm", "bitterCold"],
    ("The First Bastion", "Painted World of Ariamis"): ["trial","timer","timer","timer"],
    ("Velka's Chosen", "Painted World of Ariamis"): ["barrage"],
    ("Depths of the Cathedral", "The Sunless City"): ["mimic"],
    ("Flooded Fortress", "The Sunless City"): ["trial", "gang"],#, "difficultTerrain", "permanentTraps"],
    ("Illusionary Doorway", "The Sunless City"): ["illusion","timer"],
    ("Parish Church", "The Sunless City"): ["mimic", "illusion", "trial","timer","timer"],
    ("Kingdom's Messengers", "The Sunless City"): ["trial"],
    ("The Grand Hall", "The Sunless City"): ["trial","mimic"],
    ("Twilight Falls", "The Sunless City"): ["illusion"],
    ("Dark Resurrection", "Tomb of Giants"): ["darkness"],
    ("Death's Precipice", "Tomb of Giants"): ["barrage"],#,"blockedExits", "cramped"],
    ("Far From the Sun", "Tomb of Giants"): ["darkness"],
    ("Giant's Coffin", "Tomb of Giants"): ["onslaught","trial","timer"],
    ("In Deep Water", "Tomb of Giants"): ["timer"],
    ("Lakeview Refuge", "Tomb of Giants"): ["onslaught","darkness","trial"],
    ("Last Rites", "Tomb of Giants"): ["timer"],
    ("Last Shred of Light", "Tomb of Giants"): ["darkness"],
    ("Pitch Black", "Tomb of Giants"): ["darkness"],
    ("Skeleton Overlord", "Tomb of Giants"): ["timer"],
    ("The Beast From the Depths", "Tomb of Giants"): ["trial"],
    ("The Locked Grave", "Tomb of Giants"): ["trial"],
    ("The Mass Grave", "Tomb of Giants"): ["onslaught","timer","timer","timer"]
}

encounterKeywords = {
    ("A Trusty Ally", "Tomb of Giants"): ["onslaught"],
    ("Abandoned and Forgotten", "Painted World of Ariamis"): ["eerie"],
    ("Aged Sentinel", "The Sunless City"): ["trial"],
    ("Altar of Bones", "Tomb of Giants"): ["timer"],
    ("Archive Entrance", "The Sunless City"): ["trial"],
    ("Broken Passageway", "The Sunless City"): ["timer","timer"],
    ("Castle Break In", "The Sunless City"): ["timer", "","timer"],
    ("Central Plaza", "Painted World of Ariamis"): ["barrage"],
    ("Cold Snap", "Painted World of Ariamis"): ["snowstorm","bitterCold","trial"],
    ("Corrupted Hovel", "Painted World of Ariamis"): ["poisonMist","trial"],
    ("Corvian Host", "Painted World of Ariamis"): ["poisonMist"],
    ("Dark Resurrection", "Tomb of Giants"): ["darkness"],
    ("Deathly Freeze", "Painted World of Ariamis"): ["snowstorm","bitterCold"],
    ("Deathly Tolls", "The Sunless City"): ["timer","mimic","onslaught"],
    ("Depths of the Cathedral", "The Sunless City"): ["mimic"],
    ("Distant Tower", "Painted World of Ariamis"): ["barrage","trial"],
    ("Eye of the Storm", "Painted World of Ariamis"): ["hidden"],
    ("Far From the Sun", "Tomb of Giants"): ["darkness"],
    ("Flooded Fortress", "The Sunless City"): ["trial"],
    ("Frozen Revolutions", "Painted World of Ariamis"): ["trial"],
    ("Frozen Sentries", "Painted World of Ariamis"): ["snowstorm"],
    ("Giant's Coffin", "Tomb of Giants"): ["onslaught","trial","timer"],
    ("Gleaming Silver", "The Sunless City"): ["trial","mimic"],
    ("Gnashing Beaks", "Painted World of Ariamis"): ["trial"],
    ("Grim Reunion", "The Sunless City"): ["trial"],
    ("Hanging Rafters", "The Sunless City"): ["trial","onslaught"],
    ("Illusionary Doorway", "The Sunless City"): ["illusion"],
    ("In Deep Water", "Tomb of Giants"): ["timer"],
    ("Inhospitable Ground", "Painted World of Ariamis"): ["snowstorm"],
    ("Kingdom's Messengers", "The Sunless City"): ["trial"],
    ("Lakeview Refuge", "Tomb of Giants"): ["onslaught","darkness","trial"],
    ("Last Rites", "Tomb of Giants"): ["timer"],
    ("Last Shred of Light", "Tomb of Giants"): ["darkness"],
    ("No Safe Haven", "Painted World of Ariamis"): ["poisonMist"],
    ("Painted Passage", "Painted World of Ariamis"): ["snowstorm"],
    ("Parish Church", "The Sunless City"): ["mimic","illusion","trial"],
    ("Pitch Black", "Tomb of Giants"): ["darkness"],
    ("Promised Respite", "Painted World of Ariamis"): ["snowstorm"],
    ("Skeleton Overlord", "Tomb of Giants"): ["timer"],
    ("Snowblind", "Painted World of Ariamis"): ["snowstorm","bitterCold","hidden"],
    ("Tempting Maw", "The Sunless City"): ["trial"],
    ("The Beast From the Depths", "Tomb of Giants"): ["trial"],
    ("The First Bastion", "Painted World of Ariamis"): ["trial"],
    ("The Grand Hall", "The Sunless City"): ["trial","mimic"],
    ("The Last Bastion", "Painted World of Ariamis"): ["snowstorm","bitterCold","trial"],
    ("The Locked Grave", "Tomb of Giants"): ["trial"],
    ("The Mass Grave", "Tomb of Giants"): ["onslaught","timer","timer","timer"],
    ("The Shine of Gold", "The Sunless City"): ["timer"],
    ("Trecherous Tower", "Painted World of Ariamis"): ["snowstorm","bitterCold","eerie"],
    ("Twilight Falls", "The Sunless City"): ["illusion"],
    ("Undead Sanctum", "The Sunless City"): ["onslaught"],
    ("Unseen Scurrying", "Painted World of Ariamis"): ["hidden"]
}

keywordSize = {
    "barrage": (89, 30),
    "bitterCold": (124, 30),
    "darkness": (103, 30),
    "eerie": (61, 30),
    "gangAlonne": (156, 30),
    "gangHollow": (160, 30),
    "gangScarecrow": (187, 30),
    "gangSilverKnight": (222, 30),
    "gangSkeleton": (168, 30),
    "hidden": (84, 30),
    "illusion": (84, 30),
    "mimic": (77, 30),
    "onslaught": (117, 30),
    "poisonMist": (132, 30),
    "snowstorm": (124, 30),
    "trial": (61, 30),
    "timer": (60, 30)
}

keywordText = {
    "barrage": "Barrage — At the end of each character's turn, that character must make a defense roll using only their dodge dice. If no dodge symbols are rolled, the character suffers 2 damage and Stagger.",
    "bitterCold": "Bitter Cold — If a character has a Frostbite token at the end of their turn, they suffer 1 damage.",
    "blockedExists": "Blocked Exits — Characters can only leave a tile if there are no enemies on it.",
    "cramped": "Cramped — Reduce the node model limit to two.",
    "darkness": "Darkness — During this encounter, characters can only attack enemies on the same or an adjacent node.",
    "difficultTerrain": "Difficult Terrain — Characters must spend 1 stamina to walk on their turn or move during another character's turn.",
    "eerie": "Eerie — During setup, take five blank trap tokens and five trap tokens with values on them, and place a random token face down on each of the highlighted nodes. If a character moves onto a node with a token, flip the token. If the token is blank, place it to one side. If the token has a damage value, instead of resolving it normally, spawn an enemy corresponding to the value shown, then discard the token.",
    "hidden": "Hidden — After declaring an attack, players must discard a die of their choice before rolling. If the attacks only has a single die already, ignore this rule.",
    "illusion": "Illusion — During setup, only place tile one. Then, shuffle one doorway (or blank) trap token and four trap tokens with damage values, and place a token face down on each of the highlighted nodes. If a character moves onto a node with a token, flip the token. If the token has a damage value, resolve the effects normally. If the token is the doorway, discard all face down trap tokens, and place the next sequential tile as shown on the encounter card. Then, place the character on a doorway node on the new tile. After placing the character, if the new tile has highlighted nodes, repeat the steps above. Once a doorway token has been revealed, it counts as the doorway node that connects to the next sequential tile.",
    "mimic": "Mimic — If a character opens a chest in this encounter, shuffle the chest deck and draw a card. If a blank card is drawn, resolve the chest rules as normal. If the teeth card is drawn, replace the chest with the listed model instead. The chest deck contains three blank cards and two teeth cards. You can simulate this with trap tokens also - shuffle three blank trap tokens and two trap tokens with a value.",
    "onslaught": "Onslaught — Each tile begins the encounter as active (all enemies on active tiles act on their turn).",
    "permanentTraps": "Permanent Traps — Trap tokens with values are never discarded and are resolved each time a character is placed on its node.",
    "poisonMist": "Poison Mist — During setup, place trap tokens on the tile indicated in brackets using the normal trap placement rules. Then, reveal the tokens, replacing each token with a value with a poison cloud token. If a character ends their turn on the same node as a poison cloud token, they suffer Poison.",
    "snowstorm": "Snowstorm — At the start of each character's turn, that character suffers Frostbite unless they have the torch token on their dashboard or are on the same node as the torch token or a character with the torch token on their dashboard.",
    "timer": "Timer — If the timer marker reaches the value shown in brackets, resolve the effect listed.",
    "trial": "Trial — Trials offer an extra objective providing additional rewards if completed. This is shown in parentheses, either in writing, or as a number of turns in which the characters must complete the encounter's main objective. Completing trial objectives is not mandatory to complete an encounter."
}

enemyNames = {
    1: "Alonne Bow Knight",
    2: "Alonne Knight Captain",
    3: "Alonne Sword Knight",
    4: "Black Hollow Mage",
    5: "Bonewheel Skeleton",
    6: "Crossbow Hollow",
    7: "Crow Demon",
    8: "Demonic Foliage",
    9: "Engorged Zombie",
    10: "Falchion Skeleton",
    11: "Firebomb Hollow",
    12: "Giant Skeleton Archer",
    13: "Giant Skeleton Soldier",
    14: "Hollow Soldier",
    15: "Ironclad Soldier",
    16: "Large Hollow Soldier",
    17: "Mushroom Child",
    18: "Mushroom Parent",
    19: "Necromancer",
    20: "Phalanx",
    21: "Phalanx Hollow",
    22: "Plow Scarecrow",
    23: "Sentinel",
    24: "Shears Scarecrow",
    25: "Silver Knight Greatbowman",
    26: "Silver Knight Spearman",
    27: "Silver Knight Swordsman",
    28: "Skeleton Archer",
    29: "Skeleton Beast",
    30: "Skeleton Soldier",
    31: "Snow Rat",
    32: "Stone Guardian",
    33: "Stone Knight",
    34: "Mimic",
    35: "Armorer Dennis",
    36: "Fencer Sharron",
    37: "Invader Brylex",
    38: "Kirk, Knight of Thorns",
    39: "Longfinger Kirk",
    40: "Maldron the Assassin",
    41: "Maneater Mildred",
    42: "Marvelous Chester",
    43: "Melinda the Butcher",
    44: "Oliver the Collector",
    45: "Paladin Leeroy",
    46: "Xanthous King Jeremiah",
    47: "Hungry Mimic",
    48: "Voracious Mimic"
}


@st.cache_data(show_spinner=False)
def get_enemy_image_by_name(enemy_name: str):
    """Load and cache enemy icon images."""
    return Image.open(ENEMY_ICONS_DIR / f"{enemy_name}.png")


@st.cache_data(show_spinner=False)
def get_keyword_image(keyword_name: str):
    """Load and cache keyword icon images."""
    # Adjust path as needed
    path = Path("assets/keywords") / f"{keyword_name}.png"
    return Image.open(path)


def get_enemy_image_by_id(enemy_id: int):
    """Return image path for a given enemy ID."""
    image_path = ENEMY_ICONS_DIR / f"{enemyNames[enemy_id]}.png"
    return str(image_path)


def get_keyword_image(keyword: str):
    """Return image path for a given keyword."""
    image_path = KEYWORDS_DIR / f"{keyword}.png"
    return str(image_path)
