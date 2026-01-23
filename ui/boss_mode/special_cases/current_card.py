from ui.boss_mode.special_cases.current_card_cases.executioners_chariot import (
    try_render_executioners_chariot_current,
)
from ui.boss_mode.special_cases.current_card_cases.gaping_dragon import (
    try_render_gaping_dragon_current,
)
from ui.boss_mode.special_cases.current_card_cases.guardian_dragon import (
    try_render_guardian_dragon_current,
)
from ui.boss_mode.special_cases.current_card_cases.kalameet import (
    try_render_kalameet_current,
)
from ui.boss_mode.special_cases.current_card_cases.old_iron_king import (
    try_render_old_iron_king_current,
)
from ui.boss_mode.special_cases.current_card_cases.ornstein_smough import (
    try_render_ornstein_smough_current,
)
from ui.boss_mode.special_cases.current_card_cases.vordt import try_render_vordt_current


def render_special_current_card(*, cfg, state, current) -> bool:
    """Render special-case current-card views in Boss Mode.

    Returns True if it rendered something and the caller should stop.
    """

    return (
        try_render_ornstein_smough_current(cfg=cfg, state=state, current=current)
        or try_render_vordt_current(cfg=cfg, state=state, current=current)
        or try_render_gaping_dragon_current(cfg=cfg, state=state, current=current)
        or try_render_guardian_dragon_current(cfg=cfg, state=state, current=current)
        or try_render_kalameet_current(cfg=cfg, state=state, current=current)
        or try_render_old_iron_king_current(cfg=cfg, state=state, current=current)
        or try_render_executioners_chariot_current(cfg=cfg, state=state, current=current)
    )
