"""Small reusable sprites for The Glass Castle."""
from __future__ import annotations

import math

import pygame

from .palette import RGB, scale


def radial(size: int, power: float = 2.4) -> pygame.Surface:
    """A white radial falloff; tint it with `tint` for additive glows."""
    size = max(4, int(size))
    surf = pygame.Surface((size, size)).convert()
    surf.fill((0, 0, 0))
    c = (size - 1) * 0.5
    maxd = math.hypot(c, c)
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - c, y - c) / maxd
            v = max(0.0, 1.0 - r) ** power
            k = int(255 * v)
            surf.set_at((x, y), (k, k, k))
    return surf


def tint(sprite: pygame.Surface, color: RGB) -> pygame.Surface:
    out = sprite.copy()
    out.fill(scale(color, 1.0), special_flags=pygame.BLEND_RGB_MULT)
    return out


class GlowCache:
    """Cache the smoothscaled glow sprites the per-frame draws reuse."""

    def __init__(self):
        self._cache = {}

    def get(self, sprite: pygame.Surface, size) -> pygame.Surface:
        if isinstance(size, (tuple, list)):
            w, h = max(2, int(size[0])), max(2, int(size[1]))
        else:
            w = h = max(2, int(size))
        key = (id(sprite), w, h)
        surf = self._cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(sprite, (w, h))
            self._cache[key] = surf
        return surf

    def clear(self) -> None:
        self._cache.clear()
