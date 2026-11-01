"""The cached renderer for The Glass Castle.

Static art is built once into three transparent layers (far ridge, castle,
near cliff), each on a canvas wider than the screen so the camera can drift
without revealing an edge.  A frame is then: background, stars, the low-res
aurora, far snow, the three layer blits at their own parallax offsets, the
castled reflection, the warm windows and gate spill, the shards, near snow,
one downscaled bloom and the baked finish.  The HUD is drawn afterwards by the
adapter.

The aurora field is the only expensive moving part; it is refreshed at 4-6 Hz
depending on quality and reused between refreshes.
"""
from __future__ import annotations

import math
import random

import pygame

from .aurora import AuroraField, breath_at
from .castle import (
    build_castle, draw_far_layer, draw_gate_glow, draw_mid_layer,
    draw_near_layer, draw_shards, draw_windows,
)
from .layout import SceneLayout, REVIEW_TIME
from .palette import Palette, mix, scale, smoothstep
from .snow import SnowField
from .sprites import GlowCache, radial, tint

TAU = math.tau

QUALITY = {
    "low": {"aurora": "low", "snow": "low", "bloom_div": None, "stars": 0.72},
    "medium": {"aurora": "medium", "snow": "medium", "bloom_div": 6,
               "stars": 1.0},
    "high": {"aurora": "high", "snow": "high", "bloom_div": 4, "stars": 1.2},
}
QUALITY_NAMES = tuple(QUALITY)

#: 240 s lateral camera cycle; at the default 0.5 px/s multiplier the peak
#: travel is 20 px, comfortably inside layer_margin.
DRIFT_SECONDS = 240.0
DRIFT_TRAVEL = 40.0
PARALLAX = (0.35, 0.55, 0.80)


class GlassCastleRenderer:
    def __init__(self, size, palette: Palette, layout: SceneLayout,
                 seed: int, quality: str, settings: dict):
        self.sw, self.sh = int(size[0]), int(size[1])
        self.palette = palette
        self.layout = layout
        self.seed = int(seed)
        self.quality = quality if quality in QUALITY else "medium"

        self.aurora_on = bool(settings.get("aurora", True))
        self.snow_on = bool(settings.get("snow", True))
        self.window_lights = bool(settings.get("window_lights", True))
        self.window_flicker = float(settings.get("window_flicker", 1.0))
        self.camera_drift = float(settings.get("camera_drift", 0.5))
        self.shard_count = int(settings.get("shard_count", 6))
        self.aurora_period = float(settings.get("aurora_period", 60.0))
        self.reflection_strength = float(
            settings.get("reflection_strength", 0.72))
        self.snow_speed = float(settings.get("snow_speed", 12.0))
        self.glow_strength = float(settings.get("glow_strength", 0.36))
        self.scanline_alpha = int(settings.get("scanline_alpha", 4))
        self.vignette = float(settings.get("vignette_strength", 0.34))

        self.scene = build_castle(layout, self.seed, self.shard_count)
        self.aurora = (AuroraField(self._size(), palette, layout,
                                   QUALITY[self.quality]["aurora"], self.seed,
                                   self.aurora_period)
                       if self.aurora_on else None)
        self.snow = (SnowField(self._size(), self.seed,
                               QUALITY[self.quality]["snow"], self.snow_speed)
                     if self.snow_on else None)

        self.glow_cache = GlowCache()
        self.warm_glow = tint(radial(64, 2.2), scale(palette.warm, 0.45))
        self.gate_glow = tint(radial(64, 2.2), scale(palette.warm, 0.30))
        self.cool_glow = tint(radial(64, 2.2), palette.glow)
        self.flake_glow = tint(radial(24, 1.7),
                               scale(mix(palette.snow, palette.glow, 0.40),
                                     0.45))
        self._radial = radial(160, 2.4)
        self._refl = None
        self._refl_key = None
        self.last_stats = {}

        self.background = None
        self.finish = None
        self.far_layer = None
        self.mid_layer = None
        self.near_layer = None
        self._bloom = self._bloom_mid = self._bloom_up = None
        self._stars = []
        self._glints = []
        self._build_background()
        self._build_layers()
        self._build_finish()
        self._build_bloom()
        self._build_stars()

    # ---------------------------------------------------------------- setup

    def _size(self):
        return (self.sw, self.sh)

    def _build_stars(self) -> None:
        rng = random.Random(self.seed ^ 0x51AB)
        count = max(40, int(self.layout.star_count
                            * QUALITY[self.quality]["stars"]))
        horizon = self.sh * (0.75 if not self.layout.portrait else 0.72)
        self._stars = [(rng.uniform(0.0, self.sw),
                        rng.uniform(0.0, horizon),
                        rng.choice((1, 1, 1, 2, 2, 3)),
                        rng.uniform(0.18, 1.0))
                       for _ in range(count)]
        self._glints = [(rng.uniform(self.sw * 0.08, self.sw * 0.92),
                         rng.uniform(self.sh * 0.04, horizon * 0.55),
                         rng.uniform(0.55, 1.0)) for _ in range(3)]

    def _build_background(self) -> None:
        p = self.palette
        surf = pygame.Surface((self.sw, self.sh)).convert()
        for y in range(self.sh):
            t = y / max(1, self.sh - 1)
            if t < 0.55:
                col = mix(p.bg_top, p.bg_mid, smoothstep(t / 0.55))
            else:
                col = mix(p.bg_mid, p.bg_horizon,
                          smoothstep((t - 0.55) / 0.45) * 0.6)
            pygame.draw.line(surf, col, (0, y), (self.sw, y))

        violet = mix(p.bg_top, p.aurora_violet, 0.35)
        teal = mix(p.bg_top, p.aurora_teal, 0.35)
        mist = mix(p.bg_top, p.haze, 0.55)
        blobs = (
            (self.sw * 0.50, self.sh * 0.40, self.sw * 0.86, p.haze, 0.42),
            (self.sw * 0.18, self.sh * 0.20, self.sw * 0.34, violet, 0.30),
            (self.sw * 0.84, self.sh * 0.26, self.sw * 0.30, teal, 0.26),
            (self.sw * 0.50,
             self.sh * (0.735 if not self.layout.portrait else 0.700),
             self.sw * 0.95, mist, 0.30),
        )
        for cx, cy, size, color, strength in blobs:
            sprite = tint(self._radial, scale(color, strength))
            w = max(8, int(size))
            scaled = pygame.transform.smoothscale(sprite, (w, w))
            surf.blit(scaled, (int(cx - w * 0.5), int(cy - w * 0.5)),
                      special_flags=pygame.BLEND_RGB_ADD)
        self.background = surf

    def _build_layers(self) -> None:
        m = self.layout.layer_margin
        cw = self.sw + 2 * m
        far = pygame.Surface((cw, self.sh), pygame.SRCALPHA)
        far.fill((0, 0, 0, 0))
        draw_far_layer(far, self.layout, self.palette, self.scene, float(m))
        mid = pygame.Surface((cw, self.sh), pygame.SRCALPHA)
        mid.fill((0, 0, 0, 0))
        draw_mid_layer(mid, self.layout, self.palette, self.scene,
                       self.seed, float(m))
        near = pygame.Surface((cw, self.sh), pygame.SRCALPHA)
        near.fill((0, 0, 0, 0))
        draw_near_layer(near, self.layout, self.palette, self.seed, float(m))
        self.far_layer = self._crop_layer(
            far, min([t.tip_y for t in self.scene.far_towers]
                     + [y for _, y in self.layout.ridge]
                     + [y for _, y in self.layout.ridge_right]) - 14,
            max([t.base_y for t in self.scene.far_towers]
                + [y for _, y in self.layout.ridge]
                + [y for _, y in self.layout.ridge_right]) + 10)
        self.mid_layer = self._crop_layer(
            mid, min([t.tip_y for t in self.scene.towers]
                     + [t.tip_y for t in self.scene.gatehouses]
                     + [y for _, y in self.layout.plateau]) - 14,
            max(y for _, y in self.layout.lip) + 10)
        self.near_layer = self._crop_layer(
            near, min(y for _, y in self.layout.lip) - 14, self.sh)

    @staticmethod
    def _crop_layer(layer, y0, y1):
        y0 = max(0, int(math.floor(y0)))
        y1 = min(layer.get_height(), int(math.ceil(y1)))
        if y1 <= y0:
            y1 = min(layer.get_height(), y0 + 1)
        return layer.subsurface((0, y0, layer.get_width(), y1 - y0)).copy(), y0

    def _build_finish(self) -> None:
        w, h = self.sw, self.sh
        qw, qh = max(2, w // 4), max(2, h // 4)
        small = pygame.Surface((qw, qh)).convert()
        cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(qh):
            for x in range(qw):
                r = math.hypot(x - cx, y - cy) / maxd
                dark = self.vignette * (max(0.0, r - 0.24) / 0.76) ** 1.6
                k = int(255 * max(0.10, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (w, h))
        if self.scanline_alpha > 0:
            k = int(255 * (1.0 - min(40, self.scanline_alpha) / 255.0))
            for y in range(0, h, 3):
                pygame.draw.line(finish, (k, k, k), (0, y), (w, y), 1)
        top_h = max(44, int(h * 0.10))
        for y in range(top_h):
            t = (y / max(1, top_h - 1)) ** 2.0
            k = int(52 + 203 * t)
            pygame.draw.line(finish, (k, k, k), (0, y), (w, y))
        self.finish = finish

    def _build_bloom(self) -> None:
        div = QUALITY[self.quality]["bloom_div"]
        if div is None or self.glow_strength <= 0.0:
            self._bloom = self._bloom_mid = self._bloom_up = None
            return
        self._bloom = pygame.Surface(
            (max(1, self.sw // div), max(1, self.sh // div))).convert()
        self._bloom_mid = None
        self._bloom_up = pygame.Surface((self.sw, self.sh)).convert()

    # --------------------------------------------------------------- motion

    def _offsets(self, time_s: float):
        amp = self.camera_drift * DRIFT_TRAVEL
        phase = -TAU * REVIEW_TIME / DRIFT_SECONDS
        base = amp * math.sin(TAU * time_s / DRIFT_SECONDS + phase)
        return tuple(int(round(base * k)) for k in PARALLAX)

    def _reflection(self, time_s: float, off_mid: int):
        if not self.aurora_on or self.aurora is None:
            return None
        if self.reflection_strength <= 0.0:
            return None
        low = self.aurora.low
        if low is None:
            return None
        key = (id(low), off_mid)
        if key == self._refl_key and self._refl is not None:
            return self._refl
        fw, fh = self.aurora.field_size
        mask = pygame.Surface((fw, fh), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        sx = fw / max(1.0, self.sw)
        sy = fh / max(1.0, self.sh)
        for poly in self.scene.silhouette:
            pts = [((x + off_mid) * sx, y * sy) for x, y in poly]
            pygame.draw.polygon(mask, (255, 255, 255, 255), pts)
        ref = pygame.Surface((fw, fh), pygame.SRCALPHA)
        ref.blit(low, (0, 0))
        ref.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        strength = self.reflection_strength * (
            0.82 + 0.18 * breath_at(time_s))
        k = int(255 * max(0.0, min(1.0, strength)))
        ref.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._refl = pygame.transform.smoothscale(ref, (self.sw, self.sh))
        self._refl_key = key
        return self._refl

    # ---------------------------------------------------------------- frame

    def _draw_stars(self, screen, time_s: float) -> None:
        p = self.palette
        for (x, y, size, b) in self._stars:
            twinkle = 0.82 + 0.18 * math.sin(
                TAU * time_s / 7.3 + x * 0.05)
            col = scale(p.star, b * twinkle)
            pygame.draw.circle(screen, col, (int(x), int(y)),
                               max(1, size // 2))
        for (x, y, b) in self._glints:
            col = scale(p.star_bright, b * 0.8)
            cx, cy = int(x), int(y)
            arm = 7
            pygame.draw.line(screen, scale(col, 0.35),
                             (cx - arm, cy), (cx + arm, cy), 1)
            pygame.draw.line(screen, scale(col, 0.35),
                             (cx, cy - arm), (cx, cy + arm), 1)
            pygame.draw.circle(screen, col, (cx, cy), 1)

    def _composite_bloom(self, screen) -> None:
        if (self._bloom is None or self._bloom_up is None
                or self.glow_strength <= 0.0):
            return
        pygame.transform.smoothscale(screen, self._bloom.get_size(),
                                     self._bloom)
        k = int(24 + 112 * max(0.0, min(1.0, self.glow_strength)))
        self._bloom.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self._bloom, (self.sw, self.sh),
                                     self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def render(self, screen, time_s: float) -> None:
        time_s = float(time_s)
        off_far, off_mid, off_near = self._offsets(time_s)
        m = self.layout.layer_margin

        screen.blit(self.background, (0, 0))
        self._draw_stars(screen, time_s)
        if self.aurora_on and self.aurora is not None:
            screen.blit(self.aurora.surface(time_s), (0, 0),
                        special_flags=pygame.BLEND_RGB_ADD)
        guard = (0, self.sh - 40, 100, 40)
        if self.snow_on and self.snow is not None:
            self.snow.draw_far(screen, self.palette, time_s, guard)

        far, far_y = self.far_layer
        mid, mid_y = self.mid_layer
        near, near_y = self.near_layer
        screen.blit(far, (-m + off_far, far_y))
        screen.blit(mid, (-m + off_mid, mid_y))
        refl = self._reflection(time_s, off_mid)
        if refl is not None:
            screen.blit(refl, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        screen.blit(near, (-m + off_near, near_y))

        draw_windows(screen, self.scene, self.palette, time_s, float(off_mid),
                     self.warm_glow, self.window_lights, self.window_flicker,
                     self.glow_cache)
        draw_gate_glow(screen, self.layout, self.palette, float(off_mid),
                       self.gate_glow, self.glow_cache)
        draw_shards(screen, self.scene, self.palette, time_s,
                    float(off_mid), self.cool_glow, self.glow_cache)
        if self.snow_on and self.snow is not None:
            self.snow.draw_near(screen, self.palette, time_s, guard,
                                self.flake_glow, self.glow_cache)

        self._composite_bloom(screen)
        if self.finish is not None:
            screen.blit(self.finish, (0, 0),
                        special_flags=pygame.BLEND_RGB_MULT)

        self.last_stats = {
            "layout": self.layout.name,
            "size": (self.sw, self.sh),
            "castle_bounds": self.layout.castle_bounds,
            "shards": len(self.scene.shards),
            "windows": len(self.scene.windows),
            "snow_flakes": ((len(self.snow.far) + len(self.snow.near))
                            if self.snow is not None else 0),
            "quality": self.quality,
            "drift": off_mid,
            "aurora_on": self.aurora_on,
            "aurora_refresh": (self.aurora._refresh
                               if self.aurora is not None else 0.0),
        }

    # -------------------------------------------------------------- quality

    def set_quality(self, quality: str) -> None:
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        if self.aurora is not None:
            self.aurora.set_quality(QUALITY[quality]["aurora"])
        if self.snow is not None:
            self.snow.set_quality(QUALITY[quality]["snow"])
        self._build_bloom()
        self._build_stars()
        self._refl = None
        self._refl_key = None
        if self.last_stats:
            self.last_stats["quality"] = quality

    def stats(self) -> dict:
        if not self.last_stats:
            self.last_stats = {
                "layout": self.layout.name,
                "size": (self.sw, self.sh),
                "castle_bounds": self.layout.castle_bounds,
                "shards": len(self.scene.shards),
                "windows": len(self.scene.windows),
                "snow_flakes": ((len(self.snow.far) + len(self.snow.near))
                                if self.snow is not None else 0),
                "quality": self.quality,
                "drift": 0,
                "aurora_on": self.aurora_on,
                "aurora_refresh": (self.aurora._refresh
                                   if self.aurora is not None else 0.0),
            }
        return dict(self.last_stats)

    def close(self) -> None:
        self.background = None
        self.finish = None
        self.far_layer = None
        self.mid_layer = None
        self.near_layer = None
        self._bloom = self._bloom_mid = self._bloom_up = None
        self._refl = None
        self.scene = None
        self.aurora = None
        self.snow = None
        self._stars = []
        self._glints = []
