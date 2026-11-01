"""The Space Station V renderer.

One dark frame, drawn in this order: a vertical space gradient, the starfield,
the pre-rendered planet disc, the Earth's graticule and coastlines, then the
station's wireframe with depth-coloured lines.  A single downscale-and-add
pass supplies bloom; a baked multiply map supplies the vignette, scanlines and
the darker bands that keep the HUD legible.

There is no depth buffer: the station is transparent, so every edge is drawn
and depth is carried by colour.  Edges are split into two passes, dim
structure first and bright hull/windows/beacons second, which keeps the
readable lines on top without sorting thousands of segments per frame.
"""
from __future__ import annotations

import math
import random

import pygame

from .earth import EarthGeometry
from .framing import Framing
from .palette import Palette, mix, scale
from .stations import station_mesh

QUALITY = {
    "low": {"edges": 3000, "glow_div": 8, "graticule": 30, "detail_bonus": -2},
    "medium": {"edges": 6000, "glow_div": 6, "graticule": 20, "detail_bonus": 0},
    "high": {"edges": 7600, "glow_div": 4, "graticule": 15, "detail_bonus": 1},
}

QUALITY_NAMES = tuple(QUALITY)

_DIM_ROLES = frozenset(("detail", "structure"))
_BRIGHT_ROLES = frozenset(("hull", "hull_hi", "window", "beacon", "dock"))

#: Camera distance in ring radii.  Larger is flatter; the perspective blend
#: below scales distortion, not the station's size.
_CAMERA_DISTANCE = 5.2
_BUCKET_MAX = 32
_BUCKET_SCALE = _BUCKET_MAX / 2.9


def effective_detail(station_detail: int, quality: str) -> int:
    spec = QUALITY.get(quality, QUALITY["medium"])
    return max(1, min(4, int(station_detail) + spec["detail_bonus"]))


class StationRenderer:
    def __init__(self, size: tuple[int, int], palette: Palette,
                 coastlines, station_detail: int = 3,
                 station_tilt_deg: float = 62.0, station_yaw_deg: float = 26.0,
                 earth_tilt_deg: float = 23.4,
                 perspective: float = 0.72, glow_strength: float = 0.72,
                 scanline_alpha: int = 8, vignette: float = 0.30,
                 quality: str = "medium", seed: int = 1,
                 show_stars: bool = True, show_graticule: bool = True,
                 show_continents: bool = True, hud_bands: bool = True):
        self.palette = palette
        self.station_detail = max(1, min(4, int(station_detail)))
        self.tilt_deg = float(station_tilt_deg)
        self.yaw_deg = float(station_yaw_deg)
        self.earth_tilt_deg = float(earth_tilt_deg)
        self.perspective = max(0.0, min(1.0, float(perspective)))
        self.glow_strength = max(0.0, min(1.0, float(glow_strength)))
        self.scanline_alpha = max(0, min(80, int(scanline_alpha)))
        self.vignette = max(0.0, min(1.0, float(vignette)))
        self.quality = quality if quality in QUALITY else "medium"
        self.seed = int(seed) & 0x7FFFFFFF
        self.show_stars = bool(show_stars)
        self.show_graticule = bool(show_graticule)
        self.show_continents = bool(show_continents)
        self.hud_bands = bool(hud_bands)

        self.earth = EarthGeometry(coastlines, QUALITY[self.quality]["graticule"])
        self.meshes = {level: station_mesh(level, self.seed)
                       for level in (1, 2, 3, 4)}
        # Colour by depth is a 33-entry ramp per role, not a mix() per edge:
        # ~4,000 edges a frame made the arithmetic the most expensive part of
        # the render.  Beacons alone still pulse per edge (there are 18 of them).
        self._ramps = {role: self._build_ramp(role, palette)
                       for role in _DIM_ROLES | _BRIGHT_ROLES}
        self._passes = {
            level: (
                tuple((e.a, e.b, self._ramps[e.role], e.role == "beacon")
                      for e in mesh.edges if e.role in _DIM_ROLES),
                tuple((e.a, e.b, self._ramps[e.role], e.role == "beacon")
                      for e in mesh.edges if e.role in _BRIGHT_ROLES),
            )
            for level, mesh in self.meshes.items()
        }
        self.sw = self.sh = 0
        self.background = None
        self.finish = None
        self.bloom = None
        self.bloom_mid = None
        self.bloom_up = None
        self.stars: list[tuple[float, float, int, float, float]] = []
        self.last_station_segments = 0
        self.last_earth_segments = 0
        self.last_land_segments = 0
        self.last_grid_segments = 0
        self.last_detail = self.station_detail
        self.edge_cap = QUALITY[self.quality]["edges"]
        self._resize(size)

    # ---------------------------------------------------------------- caches

    def _resize(self, size: tuple[int, int]) -> None:
        self.sw, self.sh = max(1, int(size[0])), max(1, int(size[1]))
        self._build_background()
        self._build_finish()
        self._build_glow()
        self._build_stars()

    def resize(self, size: tuple[int, int], framing: Framing | None = None) -> None:
        if int(size[0]) != self.sw or int(size[1]) != self.sh:
            self._resize(size)

    def set_quality(self, quality: str) -> None:
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        self.edge_cap = QUALITY[quality]["edges"]
        self.earth.set_graticule(QUALITY[quality]["graticule"])
        self._build_glow()

    def _build_background(self) -> None:
        p = self.palette
        surf = pygame.Surface((self.sw, self.sh)).convert()
        for y in range(self.sh):
            t = (y / max(1, self.sh - 1)) ** 1.45
            pygame.draw.line(surf, mix(p.bg_top, p.bg_bottom, t),
                             (0, y), (self.sw, y))
        self.background = surf

    def _build_finish(self) -> None:
        """Vignette + scanlines + HUD bands in one multiply map."""
        if self.vignette <= 0.0 and self.scanline_alpha <= 0 and not self.hud_bands:
            self.finish = None
            return
        qw = max(2, self.sw // 4)
        qh = max(2, self.sh // 4)
        small = pygame.Surface((qw, qh)).convert()
        if self.vignette <= 0.0:
            small.fill((255, 255, 255))
        else:
            cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
            maxd = math.hypot(cx, cy)
            for y in range(qh):
                for x in range(qw):
                    r = math.hypot(x - cx, y - cy) / maxd
                    dark = self.vignette * (max(0.0, r - 0.30) / 0.70) ** 1.7
                    k = int(255 * max(0.08, 1.0 - dark))
                    small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (self.sw, self.sh))
        if self.scanline_alpha > 0:
            k = int(255 * (1.0 - self.scanline_alpha / 255.0))
            for y in range(0, self.sh, 3):
                pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
        if self.hud_bands:
            top_h = max(46, int(self.sh * 0.085))
            for y in range(top_h):
                t = (y / max(1, top_h - 1)) ** 2
                k = int(46 + 209 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
            bot_h = max(86, int(self.sh * (0.25 if self.sh > self.sw else 0.19)))
            for y in range(bot_h):
                k = int(255 - 238 * (y / max(1, bot_h - 1)))
                pygame.draw.line(finish, (k, k, k), (0, self.sh - bot_h + y),
                                 (self.sw, self.sh - bot_h + y), 1)
        self.finish = finish

    def _build_glow(self) -> None:
        self.bloom = None
        self.bloom_mid = None
        self.bloom_up = None
        if self.glow_strength <= 0.0:
            return
        div = QUALITY[self.quality]["glow_div"]
        self.bloom = pygame.Surface(
            (max(1, self.sw // div), max(1, self.sh // div))).convert()
        # Two-stage upscale, the same trick cyberspace uses: smoothscale to
        # half size, then a cheap nearest scale to native.  A direct
        # smoothscale to 1080p cost about 11 ms a frame here; the half-size
        # destination costs a fraction of that and the 2 px bloom steps are
        # invisible inside the glow.
        self.bloom_mid = pygame.Surface(
            (max(1, self.sw // 2), max(1, self.sh // 2))).convert()
        self.bloom_up = pygame.Surface((self.sw, self.sh)).convert()

    def _build_stars(self) -> None:
        rng = random.Random(self.seed ^ 0x2001)
        count = max(70, min(220, (self.sw * self.sh) // 5200))
        self.stars = [(rng.random(), rng.random(),
                       rng.choice((1, 1, 1, 1, 2, 2, 3)),
                       rng.uniform(0.25, 0.95),
                       rng.uniform(0.0, math.tau))
                      for _ in range(count)]

    # ---------------------------------------------------------------- frame

    def render(self, screen: pygame.Surface, framing: Framing,
               spin_deg: float, earth_spin_deg: float, time_s: float,
               detail: int | None = None) -> None:
        p = self.palette
        if self.background is not None:
            screen.blit(self.background, (0, 0))
        self._draw_stars(screen, time_s)

        earth_center = (framing.earth_anchor_x * self.sw,
                        framing.earth_anchor_y * self.sh)
        self.earth.draw(screen, earth_center, framing.earth_radius_px,
                        earth_spin_deg, self.earth_tilt_deg, p,
                        show_land=self.show_continents,
                        show_graticule=self.show_graticule)
        self.last_land_segments = self.earth.last_land_segments
        self.last_grid_segments = self.earth.last_grid_segments
        self.last_earth_segments = (self.last_land_segments
                                    + self.last_grid_segments)

        level = self.station_detail if detail is None else int(detail)
        level = max(1, min(4, level))
        self.last_detail = level
        self._draw_station(screen, framing, spin_deg, time_s, level)

        self._composite_glow(screen)
        if self.finish is not None:
            screen.blit(self.finish, (0, 0),
                        special_flags=pygame.BLEND_RGB_MULT)

    def _draw_stars(self, screen: pygame.Surface, time_s: float) -> None:
        if not self.show_stars:
            return
        for fx, fy, size, brightness, phase in self.stars:
            x = int(fx * (self.sw - 1))
            y = int(fy * (self.sh - 1))
            twinkle = 1.0 + 0.18 * math.sin(time_s * 0.55 + phase)
            color = scale(self.palette.star,
                          max(0.06, min(1.0, brightness * twinkle)))
            if size <= 1:
                screen.set_at((x, y), color)
            elif size == 2:
                screen.set_at((x, y), color)
                screen.set_at((min(self.sw - 1, x + 1), y),
                              scale(color, 0.55))
            else:
                pygame.draw.line(screen, color, (x - 2, y), (x + 2, y), 1)
                pygame.draw.line(screen, color, (x, y - 2), (x, y + 2), 1)

    # ---------------------------------------------------------------- station

    def _draw_station(self, screen: pygame.Surface, framing: Framing,
                      spin_deg: float, time_s: float, level: int) -> None:
        mesh = self.meshes[level]
        dim_edges, bright_edges = self._passes[level]
        p = self.palette
        cx = framing.station_anchor_x * self.sw
        cy = framing.station_anchor_y * self.sh
        radius = framing.station_radius_px

        spin = math.radians(spin_deg)
        cs, ss = math.cos(spin), math.sin(spin)
        tilt = math.radians(self.tilt_deg)
        ct, st = math.cos(tilt), math.sin(tilt)
        yaw = math.radians(self.yaw_deg)
        cyaw, syaw = math.cos(yaw), math.sin(yaw)
        strength = self.perspective
        distance = _CAMERA_DISTANCE

        projected: list[tuple[float, float, float]] = []
        append = projected.append
        for x, y, z in mesh.verts:
            x1 = x * cs - y * ss
            y1 = x * ss + y * cs
            y2 = y1 * ct - z * st
            z2 = y1 * st + z * ct
            x3 = x1 * cyaw + z2 * syaw
            z3 = -x1 * syaw + z2 * cyaw
            depth = distance + strength * z3
            if depth < 0.15:
                depth = 0.15
            k = radius * distance / depth
            append((cx + k * x3, cy - k * y2, z3))

        self.last_station_segments = 0
        draw_line = pygame.draw.line
        sw, sh = self.sw, self.sh
        beacon = p.beacon
        for edges in (dim_edges, bright_edges):
            for index, (a, b, ramp, is_beacon) in enumerate(edges):
                pa = projected[a]
                pb = projected[b]
                x1, y1 = pa[0], pa[1]
                x2, y2 = pb[0], pb[1]
                if ((x1 < 0.0 and x2 < 0.0) or (x1 > sw and x2 > sw)
                        or (y1 < 0.0 and y2 < 0.0)
                        or (y1 > sh and y2 > sh)):
                    continue
                depth = (pa[2] + pb[2]) * 0.5
                bucket = int((1.45 - depth) * _BUCKET_SCALE)
                if bucket < 0:
                    bucket = 0
                elif bucket > _BUCKET_MAX:
                    bucket = _BUCKET_MAX
                if is_beacon:
                    pulse = 0.48 + 0.52 * (0.5 + 0.5 * math.sin(
                        time_s * 2.4 + index * 1.7))
                    color = scale(beacon, 0.55 + 0.45 * pulse)
                else:
                    color = ramp[bucket]
                draw_line(screen, color, (x1, y1), (x2, y2), 1)
                self.last_station_segments += 1

    def _build_ramp(self, role: str, palette: Palette):
        if role == "window":
            base = palette.window
        elif role == "dock":
            base = palette.dock
        elif role == "hull_hi":
            base = palette.hull_hi
        elif role == "hull":
            base = palette.hull
        elif role == "structure":
            base = palette.structure
        else:
            base = palette.detail
        fade = 0.52 if role in _BRIGHT_ROLES else 0.70
        ramp = []
        for bucket in range(_BUCKET_MAX + 1):
            near = bucket / _BUCKET_MAX
            color = mix(base, palette.bg_top, fade * (1.0 - near))
            ramp.append(scale(color, 0.42 + 0.58 * near))
        return tuple(ramp)

    # ---------------------------------------------------------------- glow

    def _composite_glow(self, screen: pygame.Surface) -> None:
        if self.bloom is None or self.glow_strength <= 0.0:
            return
        pygame.transform.smoothscale(screen, self.bloom.get_size(), self.bloom)
        k = int(28 + 104 * self.glow_strength)
        self.bloom.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self.bloom, self.bloom_mid.get_size(),
                                     self.bloom_mid)
        pygame.transform.scale(self.bloom_mid, (self.sw, self.sh),
                               self.bloom_up)
        screen.blit(self.bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    # ---------------------------------------------------------------- stats

    def stats(self) -> dict:
        return {
            "station_segments": self.last_station_segments,
            "earth_segments": self.last_earth_segments,
            "land_segments": self.last_land_segments,
            "grid_segments": self.last_grid_segments,
            "segments": self.last_station_segments + self.last_earth_segments,
            "station_edges": self.meshes[self.last_detail].edge_count,
            "station_detail": self.last_detail,
            "earth_rings": self.earth.ring_count,
            "earth_points": self.earth.point_count,
            "edge_cap": self.edge_cap,
            "quality": self.quality,
        }
