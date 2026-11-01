"""Palettes for The Long Archive.

Every colour the renderer uses is one field of a Palette, which is what keeps
a frame coherent.  The three variants are the palette families suggested by
SLOW_WORLDS_DESIGN.md sec. 4.1, narrowed to the ones the mode actually wants:

  bone       Deep Blue & Bone  - the reviewed still
  amber      Ember & Rust      - a warmer, older vault
  verdigris  Phosphor & Ash    - a cold green archive

The glyph and mark colours are deliberately separate from the HUD colours so
the picture can be dim while the console stays legible.
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


@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: RGB
    bg_bottom: RGB
    haze: RGB
    star: RGB

    face_top: RGB
    face_bottom: RGB
    side: RGB

    ink: RGB
    ink_dim: RGB
    structure: RGB
    detail: RGB
    accent: RGB
    accent_dim: RGB
    glow: RGB
    warm: RGB
    lore: RGB

    hud: RGB
    hud_dim: RGB
    hud_faint: RGB

    bar_hot: RGB
    bar_edge: RGB


_BONE = Palette(
    name="bone",
    bg_top=(1, 4, 10), bg_bottom=(0, 1, 3),
    haze=(14, 30, 54), star=(140, 166, 198),
    face_top=(8, 15, 26), face_bottom=(2, 4, 8), side=(1, 3, 6),
    ink=(220, 230, 242), ink_dim=(102, 132, 160),
    structure=(56, 112, 162), detail=(26, 58, 92),
    accent=(127, 224, 232), accent_dim=(52, 104, 114),
    glow=(169, 216, 232), warm=(242, 200, 121), lore=(236, 232, 218),
    hud=(198, 218, 236), hud_dim=(96, 136, 168), hud_faint=(38, 74, 108),
    bar_hot=(242, 234, 212), bar_edge=(42, 86, 98),
)

_AMBER = Palette(
    name="amber",
    bg_top=(10, 5, 3), bg_bottom=(3, 2, 1),
    haze=(42, 22, 9), star=(180, 140, 90),
    face_top=(26, 15, 9), face_bottom=(7, 4, 2), side=(3, 2, 1),
    ink=(235, 211, 180), ink_dim=(150, 112, 78),
    structure=(142, 62, 46), detail=(78, 32, 22),
    accent=(255, 122, 60), accent_dim=(128, 60, 30),
    glow=(255, 208, 138), warm=(255, 196, 120), lore=(238, 222, 198),
    hud=(236, 214, 182), hud_dim=(160, 116, 82), hud_faint=(72, 44, 28),
    bar_hot=(255, 232, 192), bar_edge=(104, 48, 26),
)

_VERDIGRIS = Palette(
    name="verdigris",
    bg_top=(2, 7, 6), bg_bottom=(0, 2, 2),
    haze=(10, 38, 32), star=(120, 170, 150),
    face_top=(8, 26, 22), face_bottom=(2, 6, 5), side=(1, 3, 2),
    ink=(210, 236, 216), ink_dim=(110, 150, 128),
    structure=(74, 140, 112), detail=(34, 72, 58),
    accent=(105, 240, 180), accent_dim=(46, 110, 84),
    glow=(185, 255, 220), warm=(222, 196, 140), lore=(224, 238, 218),
    hud=(196, 232, 206), hud_dim=(100, 154, 126), hud_faint=(36, 72, 58),
    bar_hot=(228, 255, 238), bar_edge=(30, 90, 70),
)

_PALETTES = {p.name: p for p in (_BONE, _AMBER, _VERDIGRIS)}
PALETTE_NAMES = tuple(_PALETTES)


def get_palette(name: str) -> Palette:
    try:
        return _PALETTES[name]
    except KeyError:
        raise ValueError("palette must be " + ", ".join(PALETTE_NAMES)) from None
