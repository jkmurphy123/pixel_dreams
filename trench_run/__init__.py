"""Wireframe trench-run mode internals.

Phases 1–4: projection, themed world sectors, static asset kit, X-wing
motion, vector renderer, action, HUD, and adaptive quality.
No pygame display is owned here; the controller/mode owns it.
"""

__all__ = [
    "projection",
    "palette",
    "meshes",
    "assets",
    "world",
    "ship",
    "render",
]
