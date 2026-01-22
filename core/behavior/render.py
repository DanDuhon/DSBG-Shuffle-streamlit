"""Compatibility shims for legacy imports.

Historically, Streamlit UI for "Behavior Decks" lived in this module.
To keep `core/` more focused on logic/data, those renderers now live under `ui/`.

Import paths are preserved so older code can still do:
  from core.behavior.render import render, render_health_tracker
"""

from __future__ import annotations

from typing import Any


def render() -> None:
    from ui.behavior_decks.render import render as _render

    return _render()


def render_health_tracker(cfg: Any, state: Any):
    from ui.shared.health_tracker import render_health_tracker as _render_health_tracker

    return _render_health_tracker(cfg, state)
