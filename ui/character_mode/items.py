from typing import TypedDict, Literal


ItemType = Literal["armor", "armor_upgrade", "hand_item", "weapon_upgrade"]

class StatReq(TypedDict):
    str: int
    dex: int
    itl: int
    fth: int

class DiceProfile(TypedDict, total=False):
    black: int
    blue: int
    orange: int
    green: int

class ItemSource(TypedDict, total=False):
    expansion: str          # "Darkroot", "Iron Keep", etc.
    entity: str             # "Herald", "Gravelord Nito", etc.
    type: str               # "Starter Class Item", "Class Item", "Transposed Class Item"

class BaseItem(TypedDict, total=False):
    id: int                 # unique id in your data
    name: str
    item_type: ItemType
    source: ItemSource
    requirements: StatReq
    text: str               # full card rules text
    tags: list[str]         # e.g. ["melee", "greatsword", "spell", "shield"]

class Armor(BaseItem, total=False):
    item_type: Literal["armor"]

    block_dice: DiceProfile   # used when blocking
    resist_dice: DiceProfile  # used as armor/resist
    dodge_dice: DiceProfile   # used when dodging

    upgrade_slots: int        # 0–2

class ArmorUpgradeEffects(TypedDict, total=False):
    add_block_dice: DiceProfile
    add_resist_dice: DiceProfile
    add_dodge_dice: DiceProfile
    # future: flags, conditions, etc.

class ArmorUpgrade(BaseItem, total=False):
    item_type: Literal["armor_upgrade"]

    # how many upgrade slot points this uses (usually 1)
    slot_cost: int

    # structured numeric effects (optional)
    effects: ArmorUpgradeEffects

class Attack(TypedDict, total=False):
    id: str                 # internal id, or index label like "atk0"
    label: str              # optional: "Light", "Heavy", "Skill", or just "0 STA"
    stamina: int            # stamina cost
    dice: DiceProfile       # dice rolled
    flat_mod: int           # -1, 0, +1, etc.

    condition: str          # e.g. "bleed", "poison", "stagger" (token or free text)
    node_attack: bool       # True if this is a node attack
    repeat: bool            # True if this attack repeats
    text: str               # attack-specific text blob from card

class HandItem(BaseItem, total=False):
    item_type: Literal["hand_item"]

    # e.g. "weapon", "shield", "spell", "miracle"
    hand_category: str

    block_dice: DiceProfile
    resist_dice: DiceProfile
    dodge_dice: DiceProfile

    upgrade_slots: int      # how many weapon upgrades can attach

    range: int              # 0 = self/melee, 1,2,... as per card
    hands_required: int     # 1 or 2

    attacks: list[Attack]

class AttackModification(TypedDict, total=False):
    # which attacks this applies to:
    target: str             # "all", "light", "heavy", "skill", or attack id
    add_dice: DiceProfile
    add_flat_mod: int
    change_to_magic: bool   # simple flag, you can refine later
    add_condition: str      # e.g. "bleed"
    text: str               # extra rule text for this attack only

class WeaponUpgradeEffects(TypedDict, total=False):
    attack_mods: list[AttackModification]
    add_block_dice: DiceProfile
    add_resist_dice: DiceProfile
    add_dodge_dice: DiceProfile
    # future: range changes, hands_required changes, etc.

class WeaponUpgrade(BaseItem, total=False):
    item_type: Literal["weapon_upgrade"]

    slot_cost: int                 # upgrade slot cost on the weapon
    applies_to: list[str]          # e.g. ["weapon"], or ["weapon", "shield", "spell"]
    effects: WeaponUpgradeEffects