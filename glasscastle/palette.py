"""Palettes for The Glass Castle.

Every colour the scene uses is a semantic field of a Palette, so a variant can
change the mood without touching geometry or timing.  The reviewed still is the
`ice` variant of the shared Aurora & Ice family from SLOW_WORLDS_DESIGN.md 4.1;
`aurora` is a hotter green/violet sky and `rose` is the fairy-tale rose/gold
reading.

The HUD colours are deliberately separate from the scene colours: the picture
may be dark while the title stays legible.
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


def scale(c: RGB, f: float) -> RGB:
    if f <= 0.0:
        return (0, 0, 0)
    return (clamp8(c[0] * f), clamp8(c[1] * f), clamp8(c[2] * f))


def smoothstep(t: float) -> float:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class Palette:
    name: str

    bg_top: RGB
    bg_mid: RGB
    bg_horizon: RGB
    haze: RGB
    star: RGB
    star_bright: RGB

    ink: RGB
    ink_dim: RGB
    hud: RGB
    hud_dim: RGB
    hud_faint: RGB

    structure: RGB
    accent: RGB
    accent_dim: RGB
    glow: RGB

    aurora_violet: RGB
    aurora_teal: RGB
    aurora_mint: RGB

    face_base: RGB
    face_hi: RGB
    face_lit: RGB
    face_dark: RGB
    edge: RGB
    edge_dim: RGB

    snow: RGB
    snow_dim: RGB
    plateau_top: RGB
    plateau_bottom: RGB
    warm: RGB
    warm_hi: RGB
    warm_dim: RGB

    cliff_top: RGB
    cliff_bottom: RGB
    cliff_face: RGB
    cliff_edge: RGB
    ridge: RGB
    ridge_snow: RGB


_ICE = Palette(
    name="ice",
    bg_top=(3, 5, 13), bg_mid=(6, 10, 24), bg_horizon=(14, 23, 43),
    haze=(24, 54, 74), star=(168, 206, 220), star_bright=(226, 248, 248),
    ink=(230, 243, 242), ink_dim=(150, 184, 196),
    hud=(214, 234, 238), hud_dim=(122, 158, 174), hud_faint=(62, 96, 116),
    structure=(142, 124, 255), accent=(88, 224, 184),
    accent_dim=(40, 112, 104), glow=(191, 247, 228),
    aurora_violet=(94, 78, 196), aurora_teal=(56, 182, 172),
    aurora_mint=(88, 236, 178),
    face_base=(21, 32, 57), face_hi=(64, 88, 138),
    face_lit=(130, 178, 210), face_dark=(11, 17, 32),
    edge=(188, 230, 242), edge_dim=(88, 120, 160),
    snow=(200, 234, 240), snow_dim=(120, 162, 186),
    plateau_top=(33, 51, 74), plateau_bottom=(15, 23, 38),
    warm=(255, 196, 128), warm_hi=(255, 240, 202), warm_dim=(176, 112, 62),
    cliff_top=(19, 28, 45), cliff_bottom=(3, 5, 11),
    cliff_face=(9, 13, 23), cliff_edge=(68, 100, 128),
    ridge=(22, 34, 58), ridge_snow=(92, 126, 152),
)

_AURORA = Palette(
    name="aurora",
    bg_top=(2, 5, 12), bg_mid=(7, 14, 26), bg_horizon=(28, 24, 44),
    haze=(30, 66, 70), star=(176, 220, 220), star_bright=(236, 255, 244),
    ink=(232, 250, 236), ink_dim=(150, 198, 180),
    hud=(216, 242, 230), hud_dim=(126, 176, 156), hud_faint=(60, 104, 88),
    structure=(160, 112, 255), accent=(116, 255, 160),
    accent_dim=(44, 128, 80), glow=(214, 255, 202),
    aurora_violet=(116, 78, 220), aurora_teal=(52, 210, 150),
    aurora_mint=(150, 255, 162),
    face_base=(20, 38, 48), face_hi=(64, 112, 116),
    face_lit=(132, 206, 186), face_dark=(9, 20, 26),
    edge=(206, 250, 224), edge_dim=(84, 140, 120),
    snow=(206, 244, 230), snow_dim=(116, 176, 154),
    plateau_top=(30, 58, 62), plateau_bottom=(10, 22, 28),
    warm=(255, 188, 112), warm_hi=(255, 236, 190), warm_dim=(168, 104, 52),
    cliff_top=(16, 32, 40), cliff_bottom=(2, 6, 9),
    cliff_face=(7, 16, 19), cliff_edge=(64, 116, 98),
    ridge=(18, 40, 46), ridge_snow=(92, 154, 132),
)

_ROSE = Palette(
    name="rose",
    bg_top=(8, 3, 12), bg_mid=(18, 7, 22), bg_horizon=(44, 20, 38),
    haze=(74, 34, 58), star=(236, 206, 220), star_bright=(255, 240, 244),
    ink=(255, 238, 236), ink_dim=(212, 164, 176),
    hud=(250, 224, 230), hud_dim=(196, 142, 158), hud_faint=(108, 70, 88),
    structure=(196, 116, 196), accent=(255, 154, 176),
    accent_dim=(132, 58, 84), glow=(255, 216, 208),
    aurora_violet=(162, 86, 202), aurora_teal=(236, 120, 158),
    aurora_mint=(255, 196, 188),
    face_base=(40, 24, 48), face_hi=(98, 60, 104),
    face_lit=(200, 148, 178), face_dark=(18, 10, 22),
    edge=(255, 232, 238), edge_dim=(150, 98, 124),
    snow=(255, 236, 236), snow_dim=(198, 152, 168),
    plateau_top=(54, 30, 52), plateau_bottom=(18, 8, 18),
    warm=(255, 206, 138), warm_hi=(255, 244, 214), warm_dim=(180, 112, 66),
    cliff_top=(34, 18, 34), cliff_bottom=(5, 2, 7),
    cliff_face=(18, 8, 18), cliff_edge=(116, 68, 88),
    ridge=(42, 22, 44), ridge_snow=(154, 108, 130),
)

_PALETTES = {p.name: p for p in (_ICE, _AURORA, _ROSE)}
PALETTE_NAMES = tuple(_PALETTES)


def get_palette(name: str) -> Palette:
    try:
        return _PALETTES[name]
    except KeyError:
        raise ValueError("palette must be " + ", ".join(PALETTE_NAMES)) from None
