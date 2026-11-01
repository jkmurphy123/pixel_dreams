"""Colour roles and depth ramps for the vector renderer.

Lines carry a semantic role; depth turns the base role toward the background.
Panel fills are opaque and deliberately very dark: they give the wireframe
volume without a translucency pass.
"""
from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int]


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def mix(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (_clamp(a[0] + (b[0] - a[0]) * t),
            _clamp(a[1] + (b[1] - a[1]) * t),
            _clamp(a[2] + (b[2] - a[2]) * t))


def scale(color: Color, f: float) -> Color:
    f = max(0.0, f)
    return (_clamp(color[0] * f), _clamp(color[1] * f), _clamp(color[2] * f))


@dataclass(frozen=True)
class Palette:
    name: str
    bg: Color
    ink_far: Color
    ink_mid: Color
    ink_near: Color
    accent: Color
    imperial: Color
    rebel: Color
    ship: Color
    hud: Color
    star: Color
    panel: Color


PALETTES = {
    "vector_blue": Palette(
        name="vector_blue",
        bg=(2, 4, 10),
        ink_far=(12, 40, 80),
        ink_mid=(45, 130, 205),
        ink_near=(150, 235, 255),
        accent=(255, 150, 70),
        imperial=(90, 255, 160),
        rebel=(255, 90, 70),
        ship=(235, 245, 255),
        hud=(120, 220, 180),
        star=(100, 140, 190),
        panel=(5, 12, 24),
    ),
    "phosphor_green": Palette(
        name="phosphor_green",
        bg=(1, 8, 3),
        ink_far=(12, 55, 28),
        ink_mid=(40, 150, 70),
        ink_near=(170, 255, 185),
        accent=(255, 190, 90),
        imperial=(120, 255, 160),
        rebel=(255, 110, 80),
        ship=(210, 255, 220),
        hud=(120, 255, 160),
        star=(90, 150, 105),
        panel=(3, 14, 7),
    ),
    "arcade": Palette(
        name="arcade",
        bg=(2, 2, 8),
        ink_far=(40, 20, 90),
        ink_mid=(40, 180, 220),
        ink_near=(240, 240, 255),
        accent=(255, 200, 60),
        imperial=(80, 255, 130),
        rebel=(255, 80, 120),
        ship=(255, 255, 255),
        hud=(120, 255, 220),
        star=(120, 130, 210),
        panel=(5, 7, 18),
    ),
    "amber": Palette(
        name="amber",
        bg=(8, 5, 2),
        ink_far=(70, 35, 10),
        ink_mid=(190, 110, 35),
        ink_near=(255, 220, 160),
        accent=(255, 90, 50),
        imperial=(220, 255, 160),
        rebel=(255, 90, 60),
        ship=(255, 240, 210),
        hud=(255, 190, 100),
        star=(160, 100, 45),
        panel=(16, 10, 4),
    ),
    "mono": Palette(
        name="mono",
        bg=(3, 3, 5),
        ink_far=(70, 74, 82),
        ink_mid=(150, 155, 165),
        ink_near=(245, 248, 255),
        accent=(255, 90, 80),
        imperial=(130, 255, 170),
        rebel=(255, 100, 90),
        ship=(255, 255, 255),
        hud=(220, 225, 235),
        star=(110, 115, 125),
        panel=(8, 9, 13),
    ),
}


def make_palette(name: str) -> Palette:
    return PALETTES.get(str(name).lower(), PALETTES["vector_blue"])


class DepthRamp:
    """Precomputed far-to-near colours, indexed by depth."""

    def __init__(self, palette: Palette, depth_fade: float, buckets: int = 32,
                 near: float = 15.0, far: float = 450.0):
        self.palette = palette
        self.depth_fade = max(0.0, min(1.0, depth_fade))
        self.near = near
        self.far = far
        self.buckets = buckets
        self.colors: list[Color] = []
        for i in range(buckets):
            t = i / (buckets - 1)
            if t < 0.5:
                base = mix(palette.ink_near, palette.ink_mid, t * 2.0)
            else:
                base = mix(palette.ink_mid, palette.ink_far, (t - 0.5) * 2.0)
            # Additional atmospheric fade keeps the far end from ending in a
            # hard line against the background.
            fog = max(0.0, (t - 0.45) / 0.55) ** 1.35 * self.depth_fade
            self.colors.append(mix(base, palette.bg, fog))
        self.panel_colors: list[Color] = []
        for i in range(buckets):
            t = i / (buckets - 1)
            base = mix(palette.bg, palette.ink_mid, 0.19 - 0.09 * t)
            self.panel_colors.append(base)

    def index(self, zv: float) -> int:
        t = (zv - self.near) / max(1.0, self.far - self.near)
        t = max(0.0, min(1.0, t))
        return int(t * (self.buckets - 1))

    def color(self, zv: float) -> Color:
        return self.colors[self.index(zv)]

    def panel(self, zv: float) -> Color:
        return self.panel_colors[self.index(zv)]

    def role(self, role: str, zv: float) -> Color:
        p = self.palette
        if role == "primary":
            return self.color(zv)
        if role == "secondary":
            return scale(self.color(zv), 0.70)
        if role == "detail":
            return scale(self.color(zv), 0.42)
        if role == "hazard":
            return mix(p.accent, p.bg, min(0.75, self.index(zv) / self.buckets))
        if role == "emissive":
            return mix(p.accent, p.bg, min(0.55, self.index(zv) / self.buckets))
        if role == "rebel":
            return mix(p.rebel, p.bg, min(0.6, self.index(zv) / self.buckets))
        if role == "ship":
            return p.ship
        return self.color(zv)

