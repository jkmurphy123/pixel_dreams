"""Neon palettes for the cyberspace mode.

A palette is deliberately small: a background pair, a fog/haze tint, the street
and trunk colours, the HUD inks, and two lists of accent colours for structures.
Everything the renderer draws is a blend or a scale of one of those, which keeps
a single palette coherent instead of a bag of unrelated hues.
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


def scale(c: RGB, factor: float) -> RGB:
    """Scale brightness; never returns a negative channel."""
    if factor <= 0.0:
        return (0, 0, 0)
    return (clamp8(c[0] * factor), clamp8(c[1] * factor), clamp8(c[2] * factor))


@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: RGB
    bg_bottom: RGB
    haze: RGB
    fog: RGB
    street: RGB
    street_major: RGB
    grid: RGB
    trunk: RGB
    node: RGB
    traffic: RGB
    hud: RGB
    hud_dim: RGB
    hud_faint: RGB
    warn: RGB
    good: RGB
    buildings: tuple[RGB, ...]
    constructs: tuple[RGB, ...]


#: The default set: electric cyan streets, magenta/violet megastructures, a
#: little acid green for data and hot orange-red for ICE.  Backgrounds are
#: near-black with a violet bias, because true black kills the bloom.
_NEUROMANCER = Palette(
    name="neuromancer",
    bg_top=(12, 5, 30),
    bg_bottom=(2, 1, 9),
    haze=(38, 12, 70),
    fog=(8, 4, 22),
    street=(36, 176, 236),
    street_major=(90, 236, 255),
    grid=(16, 72, 112),
    trunk=(126, 86, 255),
    node=(255, 78, 214),
    traffic=(212, 255, 255),
    hud=(168, 255, 255),
    hud_dim=(64, 148, 170),
    hud_faint=(30, 64, 82),
    warn=(255, 74, 104),
    good=(116, 255, 158),
    buildings=((0, 214, 255), (255, 62, 200), (142, 92, 255),
               (70, 255, 180), (255, 150, 62), (188, 158, 255)),
    constructs=((255, 58, 190), (0, 226, 255), (130, 255, 116),
                (150, 100, 255), (255, 160, 74)),
)

_PHOSPHOR = Palette(
    name="phosphor",
    bg_top=(1, 12, 5),
    bg_bottom=(0, 4, 2),
    haze=(8, 40, 16),
    fog=(2, 16, 6),
    street=(54, 226, 118),
    street_major=(160, 255, 186),
    grid=(18, 82, 38),
    trunk=(80, 200, 120),
    node=(196, 255, 144),
    traffic=(224, 255, 208),
    hud=(176, 255, 190),
    hud_dim=(62, 148, 84),
    hud_faint=(26, 66, 38),
    warn=(255, 186, 86),
    good=(130, 255, 152),
    buildings=((46, 236, 112), (110, 255, 160), (24, 176, 92),
               (190, 255, 142), (40, 200, 170), (220, 255, 220)),
    constructs=((140, 255, 168), (68, 226, 132), (206, 255, 128)),
)

_MAGENTA = Palette(
    name="magenta",
    bg_top=(14, 2, 18),
    bg_bottom=(3, 0, 6),
    haze=(50, 6, 42),
    fog=(20, 3, 22),
    street=(238, 64, 180),
    street_major=(255, 152, 224),
    grid=(96, 22, 78),
    trunk=(150, 70, 255),
    node=(255, 210, 96),
    traffic=(255, 226, 250),
    hud=(255, 186, 238),
    hud_dim=(158, 66, 132),
    hud_faint=(72, 22, 62),
    warn=(255, 96, 88),
    good=(130, 255, 190),
    buildings=((255, 64, 190), (188, 72, 255), (255, 126, 92),
               (255, 206, 86), (110, 214, 255), (255, 236, 250)),
    constructs=((255, 170, 70), (255, 84, 204), (120, 200, 255)),
)

_ICE = Palette(
    name="ice",
    bg_top=(2, 6, 18),
    bg_bottom=(0, 2, 8),
    haze=(8, 26, 60),
    fog=(2, 10, 28),
    street=(80, 180, 255),
    street_major=(214, 244, 255),
    grid=(26, 64, 116),
    trunk=(90, 232, 255),
    node=(255, 88, 92),
    traffic=(236, 250, 255),
    hud=(208, 242, 255),
    hud_dim=(86, 132, 178),
    hud_faint=(30, 54, 82),
    warn=(255, 82, 98),
    good=(126, 255, 188),
    buildings=((110, 196, 255), (210, 232, 255), (78, 132, 240),
               (102, 236, 230), (255, 255, 255), (255, 126, 120)),
    constructs=((255, 110, 110), (170, 230, 255), (110, 255, 220)),
)

_AMBER = Palette(
    name="amber",
    bg_top=(16, 8, 2),
    bg_bottom=(4, 2, 0),
    haze=(56, 24, 4),
    fog=(24, 10, 2),
    street=(238, 158, 54),
    street_major=(255, 214, 142),
    grid=(94, 54, 14),
    trunk=(214, 108, 34),
    node=(255, 236, 178),
    traffic=(255, 246, 210),
    hud=(255, 206, 132),
    hud_dim=(158, 104, 44),
    hud_faint=(70, 40, 12),
    warn=(255, 92, 62),
    good=(196, 255, 148),
    buildings=((255, 176, 70), (226, 130, 42), (255, 220, 150),
               (190, 116, 38), (255, 104, 72), (255, 244, 222)),
    constructs=((255, 200, 100), (255, 132, 60), (255, 240, 180)),
)

PALETTES: dict[str, Palette] = {
    p.name: p for p in (_NEUROMANCER, _PHOSPHOR, _MAGENTA, _ICE, _AMBER)
}

PALETTE_NAMES = tuple(PALETTES)


def get_palette(name: str) -> Palette:
    """An unknown palette name falls back to the default rather than raising.

    Config parsing already refuses an unknown name, so this is only a safety net
    for programmatic callers and tests.
    """
    return PALETTES.get(str(name).strip().lower(), _NEUROMANCER)
