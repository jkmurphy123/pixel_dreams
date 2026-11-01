"""Palettes for the Space Station V mode.

The station is a white-painted structure lit against a black sky, so the
default palette is deliberately close to the film: cold white hull lines, a
pale blue structure, amber habitat windows and a blue-and-cyan Earth.  The
other palettes are the same drawing in a different light; every renderer
colour is one of these fields, which is what keeps a frame coherent.
"""
from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


def clamp8(value) -> int:
    return 0 if value < 0 else 255 if value > 255 else int(value)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Linear blend from a to b; t is clamped."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def scale(color: RGB, factor: float) -> RGB:
    """Scale brightness; never returns a negative channel."""
    if factor <= 0.0:
        return (0, 0, 0)
    return (clamp8(color[0] * factor), clamp8(color[1] * factor),
            clamp8(color[2] * factor))


@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: RGB
    bg_bottom: RGB
    haze: RGB
    star: RGB

    # Earth: the disc fill is dark so stars do not read through the planet.
    earth_center: RGB
    earth_edge: RGB
    earth_ocean: RGB
    earth_ocean_dim: RGB
    earth_land: RGB
    earth_land_dim: RGB
    earth_atmo: RGB

    # Station roles.
    hull_hi: RGB
    hull: RGB
    structure: RGB
    detail: RGB
    window: RGB
    beacon: RGB
    dock: RGB

    # Console.
    hud: RGB
    hud_dim: RGB
    hud_faint: RGB
    warn: RGB
    good: RGB


_ORBITAL_WHITE = Palette(
    name="orbital_white",
    bg_top=(2, 5, 13),
    bg_bottom=(0, 1, 4),
    haze=(9, 23, 46),
    star=(162, 190, 226),
    earth_center=(13, 34, 62),
    earth_edge=(3, 9, 22),
    earth_ocean=(16, 58, 102),
    earth_ocean_dim=(6, 21, 42),
    earth_land=(128, 232, 255),
    earth_land_dim=(24, 88, 130),
    earth_atmo=(46, 132, 230),
    hull_hi=(250, 253, 255),
    hull=(196, 224, 244),
    structure=(112, 172, 218),
    detail=(52, 96, 140),
    window=(255, 214, 150),
    beacon=(255, 94, 80),
    dock=(255, 186, 96),
    hud=(198, 232, 255),
    hud_dim=(96, 152, 192),
    hud_faint=(38, 74, 108),
    warn=(255, 126, 104),
    good=(126, 246, 196),
)

_VECTOR_BLUE = Palette(
    name="vector_blue",
    bg_top=(2, 4, 12),
    bg_bottom=(0, 1, 5),
    haze=(6, 20, 44),
    star=(128, 166, 214),
    earth_center=(8, 26, 60),
    earth_edge=(1, 5, 16),
    earth_ocean=(18, 70, 150),
    earth_ocean_dim=(6, 24, 58),
    earth_land=(88, 208, 255),
    earth_land_dim=(18, 70, 120),
    earth_atmo=(40, 110, 255),
    hull_hi=(238, 250, 255),
    hull=(140, 210, 255),
    structure=(66, 134, 220),
    detail=(34, 72, 132),
    window=(255, 206, 120),
    beacon=(255, 100, 70),
    dock=(255, 160, 70),
    hud=(150, 226, 255),
    hud_dim=(66, 132, 180),
    hud_faint=(26, 62, 96),
    warn=(255, 110, 110),
    good=(100, 255, 200),
)

_PHOSPHOR = Palette(
    name="phosphor_green",
    bg_top=(1, 10, 4),
    bg_bottom=(0, 3, 1),
    haze=(7, 34, 14),
    star=(110, 170, 122),
    earth_center=(5, 26, 12),
    earth_edge=(1, 5, 2),
    earth_ocean=(14, 66, 32),
    earth_ocean_dim=(5, 24, 11),
    earth_land=(150, 255, 174),
    earth_land_dim=(30, 96, 48),
    earth_atmo=(42, 190, 92),
    hull_hi=(238, 255, 240),
    hull=(152, 236, 166),
    structure=(74, 172, 96),
    detail=(34, 88, 48),
    window=(224, 255, 178),
    beacon=(255, 176, 82),
    dock=(190, 255, 130),
    hud=(172, 255, 190),
    hud_dim=(70, 148, 88),
    hud_faint=(26, 66, 38),
    warn=(255, 186, 86),
    good=(130, 255, 152),
)

_AMBER = Palette(
    name="amber",
    bg_top=(10, 6, 2),
    bg_bottom=(3, 2, 1),
    haze=(36, 20, 7),
    star=(170, 126, 76),
    earth_center=(40, 24, 8),
    earth_edge=(9, 5, 2),
    earth_ocean=(92, 56, 20),
    earth_ocean_dim=(34, 20, 8),
    earth_land=(255, 220, 158),
    earth_land_dim=(104, 66, 26),
    earth_atmo=(196, 116, 42),
    hull_hi=(255, 244, 220),
    hull=(232, 186, 122),
    structure=(158, 108, 52),
    detail=(78, 50, 22),
    window=(255, 238, 188),
    beacon=(255, 92, 48),
    dock=(255, 190, 96),
    hud=(255, 198, 116),
    hud_dim=(154, 102, 48),
    hud_faint=(70, 44, 18),
    warn=(255, 96, 56),
    good=(196, 255, 150),
)

_MONO = Palette(
    name="mono",
    bg_top=(4, 4, 6),
    bg_bottom=(1, 1, 2),
    haze=(18, 19, 24),
    star=(140, 145, 158),
    earth_center=(26, 27, 33),
    earth_edge=(5, 5, 8),
    earth_ocean=(58, 60, 70),
    earth_ocean_dim=(22, 23, 29),
    earth_land=(232, 238, 248),
    earth_land_dim=(72, 76, 88),
    earth_atmo=(130, 140, 160),
    hull_hi=(255, 255, 255),
    hull=(214, 218, 226),
    structure=(136, 142, 154),
    detail=(64, 68, 78),
    window=(250, 250, 245),
    beacon=(255, 84, 70),
    dock=(220, 224, 232),
    hud=(226, 230, 238),
    hud_dim=(142, 148, 160),
    hud_faint=(58, 62, 72),
    warn=(255, 112, 96),
    good=(180, 255, 210),
)

PALETTES = {
    p.name: p for p in (_ORBITAL_WHITE, _VECTOR_BLUE, _PHOSPHOR, _AMBER, _MONO)
}
PALETTE_NAMES = tuple(PALETTES)


def get_palette(name: str) -> Palette:
    return PALETTES.get(str(name or "").lower(), _ORBITAL_WHITE)
