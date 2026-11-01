"""Portrait composition for the sunrise mode (1080x1920 and similar).

The landscape art is a 1280x400 strip.  Portrait does not crop that strip: it
keeps the forest as a band across the bottom (scaled to the screen width) and
grows a tall sky above it, with its own sun path, clouds and star field.  HUD
placement stays in the mode; this module only draws the scene.
"""

from __future__ import annotations

import math
import random

import pygame

from . import art
from .lighting import RampScene, mixf, smoothstep, TAU


def _c(col, a=255):
    return (int(col[0]), int(col[1]), int(col[2]), a)


def _circle(dst, x, y, r, col, alpha=255):
    pygame.draw.circle(dst, _c(col, alpha), (int(x), int(y)), max(1, int(r)))


def _line(dst, a, b, col, width=1, alpha=255):
    pygame.draw.line(dst, _c(col, alpha), (int(a[0]), int(a[1])),
                     (int(b[0]), int(b[1])), max(1, int(width)))


def _vgrad(dst, rect, stops):
    x, y, w, h = rect
    for row in range(h):
        t = row / max(1, h - 1)
        col = art._sample(stops, t)
        pygame.draw.line(dst, col, (x, y + row), (x + w - 1, y + row))


def _glow(dst, cx, cy, radius, col, strength=1.0, squash=1.0, steps=44):
    gw = max(2, int(radius * 2))
    gh = max(2, int(radius * squash * 2))
    g = pygame.Surface((gw, gh), pygame.SRCALPHA)
    for i in range(steps):
        f = 1.0 - i / steps
        t = 1.0 - f
        a = int(255 * (t ** 2.3) * min(1.0, strength) * 0.85)
        if a <= 0:
            continue
        rx = radius * f
        ry = radius * squash * f
        rect = pygame.Rect(gw // 2 - int(rx), gh // 2 - int(ry),
                           max(2, int(rx * 2)), max(2, int(ry * 2)))
        pygame.draw.ellipse(g, _c(col, a), rect)
    dst.blit(g, (int(cx - radius), int(cy - radius * squash)))


class PortraitScene:
    def __init__(self, season: str, width: int, height: int):
        self.season = season
        self.pal = art._PALETTES[season]
        self.w = int(width)
        self.h = int(height)

        # the landscape strip keeps its aspect; the forest sits on the bottom
        self.strip_h = max(90, int(round(art.H * self.w / art.W)))
        self.strip_h = min(self.strip_h, int(self.h * 0.55))
        self.strip_y = self.h - self.strip_h
        self.horizon = self.strip_y + art.HORIZON * (self.strip_h / art.H)

        layers = art.build_layers(art.Layout(), season)
        self.layers = {
            name: pygame.transform.smoothscale(layers[name], (self.w, self.strip_h))
            for name in ("far", "mid", "ground", "near")
        }

        self.clouds = self._build_clouds()
        self.stars = self._build_stars()
        self._grad_cache = {}

    # ------------------------------------------------------------------
    def _build_clouds(self):
        ss = art.SS
        surf = pygame.Surface((self.w * ss, self.h * ss), pygame.SRCALPHA)
        specs = (
            (0.18, 0.18, 0.85), (0.74, 0.12, 0.60), (0.46, 0.32, 1.00),
            (0.84, 0.43, 0.50), (0.22, 0.52, 0.65), (0.62, 0.62, 0.48),
        )
        for fx, fy, scale in specs:
            art.draw_cloud(surf, {"cx": fx * self.w, "base": fy * self.h,
                                  "s": scale}, self.pal)
        return pygame.transform.smoothscale(surf, (self.w, self.h))

    def _build_stars(self):
        rng = random.Random(991)
        out = []
        for _ in range(240):
            x = rng.uniform(0, self.w)
            y = rng.uniform(0, max(40, self.horizon - 120))
            fade = max(0.0, 1.0 - y / max(1.0, self.horizon))
            out.append((x, y, rng.uniform(0.35, 1.55),
                        rng.choice([(208, 222, 255), (255, 244, 226)]),
                        0.2 + 0.8 * fade))
        return out

    # ------------------------------------------------------------------
    def mood(self, phase):
        m = RampScene.mood(self, phase)
        alt = m["alt"]
        up = max(0.0, min(1.0, alt))
        # the sun keeps the landscape's clearing (right of centre) and drifts left
        m["sun_x"] = art.SUN_X * (self.w / art.W) - 80.0 * up
        m["sun_y"] = self.horizon + 10 - max(-0.15, up) * (self.horizon - 140)
        m["sun_r"] = 42.0 * (self.w / 1080.0) * (1.0 + 0.22 * m["warm"])
        return m

    def _gradient(self, top, bottom):
        key = (tuple(int(c * 255) for c in top), tuple(int(c * 255) for c in bottom))
        g1 = self._grad_cache.get(key)
        if g1 is None:
            g1 = pygame.Surface((1, self.strip_h))
            for y in range(self.strip_h):
                t = y / max(1, self.strip_h - 1)
                g1.set_at((0, y), art.mix(key[0], key[1], t))
            self._grad_cache[key] = g1
        return pygame.transform.scale(g1, (self.w, self.strip_h))

    def _lit_layer(self, name, mood):
        alt = mood["alt"]
        level = 0.05 + 0.95 * smoothstep(0.0, 0.34, alt)
        depth = {"far": 1.10, "mid": 1.0, "ground": 0.94, "near": 0.89}[name]
        level *= 1.0 - (1.0 - depth) * (1.0 - level)

        warm_tint = mixf((1.0, 1.0, 1.0), (1.02, 0.87, 0.73), mood["warm"])
        tint = mixf(warm_tint, (0.56, 0.64, 0.98), mood["night"])
        grad_amt = 0.40 * mood["warm"] + 0.18 * mood["night"]

        top = [min(1.0, level * (1.0 + grad_amt) * tint[i]) for i in range(3)]
        bottom = [min(1.0, level * (1.0 - grad_amt) * tint[i]) for i in range(3)]

        out = self.layers[name].copy()
        out.blit(self._gradient(top, bottom), (0, 0),
                 special_flags=pygame.BLEND_RGB_MULT)
        return out

    # ------------------------------------------------------------------
    def _sky(self, phase, mood):
        sky = pygame.Surface((self.w, self.h))
        stops = [
            (0.00, mood["stops"][0][1]),
            (0.55, mood["stops"][1][1]),
            (0.82, mood["stops"][2][1]),
            (0.96, mood["stops"][3][1]),
        ]
        _vgrad(sky, (0, 0, self.w, self.h), stops)

        if mood["night"] > 0.01:
            stars = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            for x, y, r, col, bright in self.stars:
                a = int(220 * mood["night"] * bright)
                if a > 2:
                    _circle(stars, x, y, r, col, a)
            sky.blit(stars, (0, 0))

        sx = mood["sun_x"]
        _glow(sky, sx, self.horizon + 30, self.w * 0.80,
              mood["glow_col"], mood["glow_strength"] * 0.75, squash=0.20)
        _glow(sky, sx, mood["sun_y"], self.w * 0.32,
              mood["glow_col"], mood["glow_strength"], squash=0.95)
        _glow(sky, sx, mood["sun_y"], self.w * 0.10,
              mood["sun_col"], mood["glow_strength"] * 1.10, squash=0.95)
        if mood["alt"] > -0.04:
            r = mood["sun_r"]
            _circle(sky, sx, mood["sun_y"], r, mood["sun_col"])
            _circle(sky, sx - r * 0.10, mood["sun_y"] - r * 0.10, r * 0.78,
                    art.mix(mood["sun_col"], (255, 255, 255), 0.55))

        mist_col = art.mix(self.pal["horizon_mist"], mood["horizon"], mood["warm"])
        mist_col = art.mix(mist_col, (74, 88, 112), mood["night"] * 0.8)
        mist = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        mh = max(60, int(self.h * 0.05))
        for row in range(mh):
            t = row / max(1, mh - 1)
            a = int((60 - 28 * mood["night"]) * math.sin(math.pi * t))
            y = int(self.horizon - mh * 0.6) + row
            _line(mist, (0, y), (self.w, y), mist_col, 1, a)
        sky.blit(mist, (0, 0))

        cloud_rgb = art.mix((255, 255, 255),
                            art.mix(mood["horizon"], (255, 255, 255), 0.15),
                            0.65 * mood["warm"])
        cloud_rgb = art.mix(cloud_rgb, (26, 32, 50), mood["night"])
        clouds = art.tint(self.clouds, tuple(c / 255.0 for c in cloud_rgb))
        alpha = int(255 * (1.0 - 0.62 * mood["night"]))
        clouds.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        sky.blit(clouds, (0, 0))

        if mood["alt"] > 0.10:
            bird_col = art.mix(mood["stops"][0][1], (24, 28, 38), 0.72)
            for bx, by in ((0.30 * self.w, 0.36 * self.h),
                           (0.35 * self.w, 0.33 * self.h),
                           (0.66 * self.w, 0.30 * self.h)):
                for k in (-1, 1):
                    pygame.draw.lines(
                        sky, bird_col, False,
                        [(int(bx - 10 * k), int(by)), (int(bx - 3 * k), int(by + 3)),
                         (int(bx), int(by)), (int(bx + 3 * k), int(by + 3)),
                         (int(bx + 10 * k), int(by))], 1)
        return sky

    # ------------------------------------------------------------------
    def render(self, phase):
        mood = self.mood(phase)
        canvas = pygame.Surface((self.w, self.h))
        canvas.blit(self._sky(phase, mood), (0, 0))
        for name in ("far", "mid", "ground", "near"):
            canvas.blit(self._lit_layer(name, mood), (0, self.strip_y))
        return canvas, mood
