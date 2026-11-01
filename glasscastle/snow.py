"""Two parallax snow layers for The Glass Castle.

The flakes are a pure function of (seed, time): no accumulated state, so the
preview at t=15 is the same frame the mode shows at t=15.  The far layer sits
behind the castle, the near layer in front of the cliff; both avoid the
controller's lower-left 80x32 mode-number corner.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .palette import Palette, mix, scale

TAU = math.tau

QUALITY = {
    "low": (90, 22),
    "medium": (160, 36),
    "high": (210, 48),
}
QUALITY_NAMES = tuple(QUALITY)


@dataclass
class Flake:
    x: float
    y: float
    speed: float
    size: int
    bright: float
    phase: float
    wind: float
    soft: bool = False


class SnowField:
    def __init__(self, size, seed: int, quality: str = "medium",
                 speed: float = 12.0):
        self.sw, self.sh = int(size[0]), int(size[1])
        self.seed = int(seed)
        self.quality = quality if quality in QUALITY else "medium"
        self.speed = max(2.0, min(24.0, float(speed)))
        self.far: list[Flake] = []
        self.near: list[Flake] = []
        self._build()

    def _build(self) -> None:
        rng = random.Random(self.seed ^ 0x91F3)
        far_n, near_n = QUALITY[self.quality]
        self.far = []
        self.near = []
        for _ in range(far_n):
            self.far.append(Flake(
                x=rng.uniform(0.0, self.sw),
                y=rng.uniform(0.0, self.sh),
                speed=rng.uniform(7.0, 10.5),
                size=rng.choice((1, 1, 1, 2)),
                bright=rng.uniform(0.20, 0.72),
                phase=rng.uniform(0.0, TAU),
                wind=rng.uniform(-1.6, 1.6)))
        for _ in range(near_n):
            size = rng.choice((2, 2, 3, 4))
            self.near.append(Flake(
                x=rng.uniform(0.0, self.sw),
                y=rng.uniform(0.0, self.sh),
                speed=rng.uniform(10.0, 17.0),
                size=size,
                bright=rng.uniform(0.30, 0.82),
                phase=rng.uniform(0.0, TAU),
                wind=rng.uniform(-2.4, 2.4)))
        for _ in range(3 if self.sw < 1500 else 6):
            self.near.append(Flake(
                x=rng.uniform(0.0, self.sw),
                y=rng.uniform(0.0, self.sh),
                speed=rng.uniform(6.0, 11.0),
                size=rng.choice((5, 6, 7)),
                bright=rng.uniform(0.10, 0.20),
                phase=rng.uniform(0.0, TAU),
                wind=rng.uniform(-1.0, 1.0),
                soft=True))

    def set_quality(self, quality: str) -> None:
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        self._build()

    def _position(self, flake: Flake, time_s: float):
        scale_ = self.speed / 12.0
        y = (flake.y + flake.speed * scale_ * time_s) % (self.sh + 24) - 12
        x = (flake.x + flake.wind * time_s
             + math.sin(time_s * 0.12 + flake.phase) * 5.0) % (self.sw + 20)
        return x - 10, y

    @staticmethod
    def _blocked(guard, x, y) -> bool:
        return (guard[0] <= x < guard[0] + guard[2]
                and guard[1] <= y < guard[1] + guard[3])

    def draw_far(self, screen, palette: Palette, time_s: float,
                 guard) -> None:
        for flake in self.far:
            x, y = self._position(flake, time_s)
            if self._blocked(guard, x, y):
                continue
            col = scale(palette.snow, flake.bright * 0.74)
            pygame.draw.circle(screen, col,
                               (int(x), int(y)), max(1, flake.size // 2))

    def draw_near(self, screen, palette: Palette, time_s: float,
                  guard, flake_glow: pygame.Surface, glow_cache=None) -> None:
        for flake in self.near:
            x, y = self._position(flake, time_s)
            if self._blocked(guard, x, y):
                continue
            col = scale(mix(palette.snow, palette.glow, 0.40),
                        flake.bright * 0.70)
            if flake.soft:
                g = int(flake.size * 1.7)
                sprite = (glow_cache.get(flake_glow, g)
                          if glow_cache is not None
                          else pygame.transform.smoothscale(flake_glow, (g, g)))
                screen.blit(sprite, (int(x - g * 0.5), int(y - g * 0.5)),
                            special_flags=pygame.BLEND_RGB_ADD)
            else:
                pygame.draw.circle(screen, col, (int(x), int(y)),
                                   max(1, flake.size // 2))
