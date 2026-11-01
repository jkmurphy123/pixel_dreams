#!/usr/bin/env python3
"""Art-direction prototype: Terraform, mountain overlook (Slow Worlds 5.15).

This is a *design* script, not the mode.  It settles the mountain-top camera,
the two-orientation composition, the cartoon palette and the depth logic
before ``modes/terraform_mode.py`` is written, and it writes the review stills
in ``screenshots/terraform/``.

The design card asks for a world being terraformed over three minutes: ice
retreats, rivers branch toward the sea, green spreads from the coasts, and city
lights appear along the new waterways.  The requested tweak is the camera: not
a map view, but a first-person view from a summit looking *down* into the
valley.

That makes depth the organising idea of the still.  The scene is built as
layers, far to near:

* sky and a rounded, snow-capped range;
* the bay, its delta and the warm city at the mouth;
* the valley floor, its fields, town and winding river;
* a forested ridge on the left and a sunlit farm ridge on the right, which
  overlap the valley and hide parts of the river;
* the dark foreground ledge with three big pines and a footpath.

Every object shrinks with its layer and with its position in the frame, the
river is widest at the bottom and a thread at the delta, near land is
saturated, far land is hazed toward the sky, and each nearer ridge occludes
the one behind it.  A near farm, a middle town and a far delta city give three
readable steps of scale.

Everything is procedural pygame: no assets, no network, no numpy/PIL.
The still is rendered at 2x/3x and downsampled so the rim light, the far city
and the shoreline can be judged fairly.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/terraform_proto/gen_terraform.py
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/terraform_proto/gen_terraform.py --only strip
"""
from __future__ import annotations

import argparse
import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "terraform")

TAU = math.tau

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

RGB = tuple[int, int, int]


# ---------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------

def clamp8(value) -> int:
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def shade(c: RGB, f: float) -> RGB:
    return (clamp8(c[0] * f), clamp8(c[1] * f), clamp8(c[2] * f))


def rgba(c: RGB, a: int) -> tuple[int, int, int, int]:
    return (clamp8(c[0]), clamp8(c[1]), clamp8(c[2]), clamp8(a))


# ---------------------------------------------------------------------------
# Palette.  "biosphere" is the reviewed still: a cool, luminous dawn over a
# saturated green valley, a warm sun on the right, a hazy blue coast and warm
# city lights.  This is the bright end of the Slow Worlds set, close to
# Sunrise's flat cartoon finish rather than the near-black Leviathan register.
# ---------------------------------------------------------------------------

PALETTES = {
    "biosphere": dict(
        label="BIOSPHERE",
        note="dawn over the new valley · the design default",
        sky_top=(22, 62, 104),
        sky_high=(48, 112, 158),
        sky_mid=(102, 160, 186),
        sky_low=(180, 206, 196),
        sky_horizon=(255, 222, 174),
        sky_glow=(255, 202, 138),
        sun=(255, 244, 206),
        sun_core=(255, 253, 240),
        cloud=(255, 246, 230),
        cloud_shade=(188, 184, 184),
        cloud_warm=(255, 204, 170),
        haze=(176, 202, 200),
        far_mtn=(100, 134, 160),
        far_mtn_hi=(146, 174, 192),
        far_mtn_dark=(72, 106, 134),
        snow=(238, 242, 240),
        snow_shadow=(154, 184, 208),
        sea=(64, 136, 158),
        sea_deep=(24, 88, 122),
        sea_far=(130, 172, 176),
        sea_glint=(255, 236, 190),
        valley_far=(124, 156, 106),
        valley_mid=(70, 116, 78),
        valley_near=(30, 78, 52),
        meadow=(112, 158, 88),
        meadow_hi=(168, 196, 110),
        grass=(84, 138, 76),
        forest=(32, 86, 58),
        forest_dark=(16, 56, 42),
        forest_hi=(74, 130, 70),
        tundra=(150, 170, 144),
        tundra_hi=(188, 202, 160),
        rock=(98, 108, 98),
        rock_hi=(144, 152, 136),
        rock_dark=(66, 76, 72),
        ice=(226, 238, 240),
        ice_shadow=(144, 184, 204),
        ice_edge=(240, 248, 246),
        water=(54, 144, 162),
        water_deep=(20, 98, 132),
        water_light=(146, 204, 194),
        foam=(238, 248, 240),
        algae=(124, 182, 96),
        bloom=(186, 214, 112),
        sand=(198, 184, 138),
        silt=(176, 164, 124),
        city=(255, 206, 126),
        city_hot=(255, 242, 198),
        roof=(166, 78, 62),
        roof_dark=(116, 54, 48),
        wall=(228, 206, 164),
        pine=(14, 44, 38),
        pine_mid=(26, 64, 50),
        pine_hi=(96, 144, 84),
        pine_dark=(8, 28, 26),
        trunk=(76, 56, 42),
        ink=(250, 246, 232),
        ink_dim=(188, 198, 182),
        ink_faint=(126, 146, 134),
        accent=(250, 190, 112),
        shadow=(8, 28, 26),
    ),
}

PAL = PALETTES["biosphere"]


# ---------------------------------------------------------------------------
# Layouts.  Both are re-compositions, not crops.  The portrait raises the
# horizon a little, deepens the valley and grows the foreground pines.  Every
# layer is specified in normalised screen coordinates so the two orientations
# keep their own framing.
# ---------------------------------------------------------------------------

LAYOUTS = {
    "strip": dict(
        name="strip",
        size=(1280, 400),
        ss=3,
        horizon=0.270,
        obj=1.00,
        title_size=27,
        title_tracking=6.0,
        eyebrow_size=8,
        tele_size=9,
        title_x=30,
        title_y=30,
        eyebrow_y=15,
        subtitle_y=64,
        tele_x=1250,
        tele_y=19,
        timeline_x0=272,
        timeline_x1=1008,
        timeline_y=383,
        timeline_label_y=364,
        year_size=8,
        sun=(0.640, 0.032, 0.070),
        clouds=[(0.400, 0.075, 1.00, 1.00), (0.575, 0.160, 0.66, 0.88),
                (0.870, 0.105, 0.52, 0.76), (0.505, 0.225, 0.30, 0.42)],
        birds=[(0.560, 0.090, 1.0), (0.598, 0.112, 0.8),
               (0.532, 0.125, 0.7), (0.682, 0.078, 0.6)],
        mountains=dict(
            base=0.270,
            far=dict(peaks=[(0.300, 0.034, 0.060), (0.350, 0.030, 0.105),
                            (0.398, 0.030, 0.070), (0.442, 0.028, 0.145),
                            (0.482, 0.030, 0.095), (0.522, 0.028, 0.175),
                            (0.562, 0.030, 0.110), (0.600, 0.032, 0.150),
                            (0.638, 0.030, 0.075), (0.676, 0.034, 0.042),
                            (0.714, 0.038, 0.026), (0.752, 0.036, 0.048),
                            (0.792, 0.032, 0.090), (0.832, 0.030, 0.060),
                            (0.872, 0.032, 0.105), (0.912, 0.030, 0.070),
                            (0.952, 0.034, 0.048)],
                       snowline=0.128),
            near=dict(peaks=[(0.300, 0.050, 0.030), (0.360, 0.042, 0.055),
                             (0.420, 0.045, 0.078), (0.480, 0.040, 0.060),
                             (0.540, 0.045, 0.050), (0.600, 0.050, 0.032),
                             (0.700, 0.055, 0.024), (0.800, 0.048, 0.052),
                             (0.880, 0.045, 0.040), (0.950, 0.045, 0.030)],
                       snowline=0.155),
        ),
        sea=dict(top=0.270, bottom=0.365),
        coastline=0.365,
        delta=dict(x=0.548, y=0.352, width=0.060),
        river=[(0.548, 0.365), (0.520, 0.420), (0.470, 0.475),
               (0.455, 0.535), (0.500, 0.595), (0.550, 0.655),
               (0.555, 0.715), (0.520, 0.775), (0.475, 0.835),
               (0.495, 0.900), (0.510, 0.960), (0.500, 1.010)],
        river_width=38.0,
        fields=dict(x0=0.120, x1=0.880, y0=0.392, y1=0.848, count=54),
        town=dict(x=0.470, y=0.585, scale=1.00),
        left_hill=dict(
            crest=[(0.440, 0.500), (0.380, 0.545), (0.310, 0.600),
                   (0.235, 0.665), (0.160, 0.735), (0.095, 0.815),
                   (0.045, 0.900), (0.012, 1.020)],
            top_col="forest_hi", base_col="forest_dark", sunlit=True,
            tree_density=1.55, tree_scale=1.00, ice=False, fields=False,
        ),
        right_hill=dict(
            crest=[(0.580, 0.500), (0.640, 0.545), (0.710, 0.600),
                   (0.785, 0.665), (0.860, 0.735), (0.925, 0.815),
                   (0.970, 0.900), (0.992, 1.020)],
            top_col="meadow_hi", base_col="meadow", sunlit=False,
            tree_density=0.30, tree_scale=0.72, ice=False, fields=True,
        ),
        farm=dict(x=0.700, y=0.775, scale=0.95),
        ledge=dict(
            top=[(0.000, 0.808), (0.070, 0.832), (0.150, 0.858),
                 (0.240, 0.880), (0.340, 0.896), (0.440, 0.904),
                 (0.540, 0.902), (0.640, 0.892), (0.740, 0.874),
                 (0.830, 0.850), (0.920, 0.828), (1.000, 0.812)],
            pines=[(0.075, 0.958, 0.440, 1.00), (0.158, 0.928, 0.330, 0.90),
                   (0.220, 0.944, 0.235, 0.80)],
            rocks=[(0.930, 0.940, 0.075, 1.00), (0.975, 0.912, 0.055, 0.82)],
            cairn=(0.315, 0.900),
            path=[(0.020, 0.996), (0.110, 0.972), (0.205, 0.952),
                  (0.300, 0.930), (0.360, 0.912)],
        ),
    ),
    "portrait": dict(
        name="portrait",
        size=(1080, 1920),
        ss=2,
        horizon=0.400,
        obj=1.92,
        title_size=56,
        title_tracking=10.0,
        eyebrow_size=13,
        tele_size=14,
        title_x=56,
        title_y=104,
        eyebrow_y=68,
        subtitle_y=188,
        tele_x=1024,
        tele_y=68,
        timeline_x0=150,
        timeline_x1=930,
        timeline_y=1836,
        timeline_label_y=1802,
        year_size=12,
        sun=(0.700, 0.120, 0.030),
        clouds=[(0.480, 0.060, 0.52, 0.86), (0.720, 0.160, 0.44, 0.60),
                (0.120, 0.155, 0.55, 0.64), (0.900, 0.205, 0.40, 0.42)],
        birds=[(0.600, 0.115, 1.3), (0.640, 0.138, 1.0),
               (0.565, 0.152, 0.8), (0.690, 0.098, 0.7)],
        mountains=dict(
            base=0.400,
            far=dict(peaks=[(0.290, 0.035, 0.070), (0.340, 0.033, 0.100),
                            (0.390, 0.035, 0.080), (0.435, 0.032, 0.160),
                            (0.480, 0.035, 0.140), (0.520, 0.032, 0.180),
                            (0.560, 0.035, 0.180), (0.600, 0.032, 0.210),
                            (0.640, 0.035, 0.180), (0.680, 0.032, 0.150),
                            (0.720, 0.035, 0.100), (0.765, 0.032, 0.110),
                            (0.810, 0.032, 0.130), (0.855, 0.035, 0.090),
                            (0.900, 0.032, 0.110), (0.945, 0.035, 0.070)],
                       snowline=0.190),
            near=dict(peaks=[(0.300, 0.060, 0.055), (0.360, 0.050, 0.085),
                             (0.420, 0.055, 0.115), (0.480, 0.050, 0.090),
                             (0.540, 0.055, 0.075), (0.600, 0.060, 0.055),
                             (0.700, 0.065, 0.042), (0.800, 0.055, 0.080),
                             (0.880, 0.050, 0.060), (0.950, 0.052, 0.042)],
                       snowline=0.240),
        ),
        sea=dict(top=0.400, bottom=0.480),
        coastline=0.480,
        delta=dict(x=0.545, y=0.467, width=0.085),
        river=[(0.548, 0.480), (0.520, 0.520), (0.470, 0.560),
               (0.455, 0.600), (0.500, 0.640), (0.550, 0.680),
               (0.555, 0.725), (0.520, 0.790), (0.475, 0.855),
               (0.495, 0.920), (0.510, 0.975), (0.500, 1.010)],
        river_width=54.0,
        fields=dict(x0=0.120, x1=0.880, y0=0.492, y1=0.865, count=96),
        town=dict(x=0.470, y=0.575, scale=1.55),
        left_hill=dict(
            crest=[(0.440, 0.500), (0.375, 0.555), (0.305, 0.620),
                   (0.230, 0.695), (0.155, 0.775), (0.090, 0.860),
                   (0.035, 0.940), (0.012, 1.020)],
            top_col="forest_hi", base_col="forest_dark", sunlit=True,
            tree_density=1.55, tree_scale=1.00, ice=False, fields=False,
        ),
        right_hill=dict(
            crest=[(0.580, 0.500), (0.645, 0.555), (0.715, 0.620),
                   (0.790, 0.695), (0.865, 0.775), (0.930, 0.860),
                   (0.975, 0.940), (0.992, 1.020)],
            top_col="meadow_hi", base_col="forest_dark", sunlit=False,
            tree_density=0.50, tree_scale=0.62, ice=False, fields=True,
        ),
        farm=dict(x=0.710, y=0.790, scale=1.08),
        ledge=dict(
            top=[(0.000, 0.804), (0.070, 0.828), (0.150, 0.852),
                 (0.240, 0.874), (0.340, 0.890), (0.440, 0.898),
                 (0.540, 0.896), (0.640, 0.886), (0.740, 0.868),
                 (0.830, 0.846), (0.920, 0.824), (1.000, 0.808)],
            pines=[(0.160, 0.962, 0.420, 1.00), (0.250, 0.936, 0.310, 0.90),
                   (0.312, 0.950, 0.210, 0.80)],
            rocks=[(0.925, 0.942, 0.052, 1.00), (0.972, 0.916, 0.040, 0.82)],
            cairn=(0.330, 0.902),
            path=[(0.020, 0.996), (0.120, 0.972), (0.225, 0.950),
                  (0.320, 0.928), (0.372, 0.910)],
        ),
    ),
}


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

_SOFT_CACHE: dict[tuple, pygame.Surface] = {}


def _soft_master(color: RGB, alpha: int, power: float) -> pygame.Surface:
    key = (color, alpha, power)
    surf = _SOFT_CACHE.get(key)
    if surf is not None:
        return surf
    radius = 96
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        falloff = (1.0 - r / radius) ** power
        pygame.draw.circle(surf, (*color, clamp8(alpha * falloff)),
                           (radius, radius), r)
    _SOFT_CACHE[key] = surf
    return surf


def blit_soft(dst, cx, cy, w, h, color, alpha, power=2.0):
    w = max(2, int(w))
    h = max(2, int(h))
    master = _soft_master(color, alpha, power)
    scaled = (pygame.transform.smoothscale(master, (w, h))
              if (w, h) != (192, 192) else master)
    dst.blit(scaled, (int(cx - w / 2), int(cy - h / 2)))


def vgrad(w: int, h: int, stops: list[tuple[float, RGB]]) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    stops = sorted(stops)
    for y in range(h):
        t = y / max(1, h - 1)
        left, right = stops[0], stops[-1]
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i + 1][0]:
                left, right = stops[i], stops[i + 1]
                break
        span = right[0] - left[0]
        local = 0.0 if span <= 0 else (t - left[0]) / span
        pygame.draw.line(surf, mix(left[1], right[1], local), (0, y), (w, y))
    return surf


def catmull(points, closed=False, samples=10):
    pts = [tuple(p) for p in points]
    if len(pts) < 2:
        return pts
    if closed:
        ext = [pts[-1]] + pts + [pts[0], pts[1]]
    else:
        ext = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i:i + 4]
        n = samples if (i < len(ext) - 4 or closed) else max(2, samples // 2)
        for s in range(n):
            t = s / n
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(out[0] if closed else pts[-1])
    return out


def _surf(dst):
    return dst.surface if hasattr(dst, "surface") else dst


def _bbox(pts, w, h, pad=2):
    x0 = max(0, int(min(x for x, _ in pts)) - pad)
    y0 = max(0, int(min(y for _, y in pts)) - pad)
    x1 = min(w, int(max(x for x, _ in pts)) + pad)
    y1 = min(h, int(max(y for _, y in pts)) + pad)
    return x0, y0, x1, y1


def poly(dst, pts, color, alpha=255):
    surf = _surf(dst)
    pts = [(int(round(x)), int(round(y))) for x, y in pts]
    if len(pts) < 3:
        return
    if alpha >= 255:
        pygame.draw.polygon(surf, color, pts)
        return
    sw, sh = surf.get_size()
    x0, y0, x1, y1 = _bbox(pts, sw, sh)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    layer = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
    pygame.draw.polygon(layer, rgba(color, alpha),
                        [(x - x0, y - y0) for x, y in pts])
    surf.blit(layer, (x0, y0))


def circle(dst, cx, cy, r, color, alpha=255):
    surf = _surf(dst)
    r = max(1, int(round(r)))
    if alpha >= 255:
        pygame.draw.circle(surf, color, (int(cx), int(cy)), r)
        return
    sw, sh = surf.get_size()
    x0, y0 = max(0, int(cx) - r - 1), max(0, int(cy) - r - 1)
    x1, y1 = min(sw, int(cx) + r + 2), min(sh, int(cy) + r + 2)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    layer = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
    pygame.draw.circle(layer, rgba(color, alpha), (int(cx) - x0, int(cy) - y0), r)
    surf.blit(layer, (x0, y0))


def ellipse(dst, cx, cy, rx, ry, color, alpha=255):
    surf = _surf(dst)
    rx, ry = max(1, int(round(rx))), max(1, int(round(ry)))
    rect = pygame.Rect(int(cx - rx), int(cy - ry), rx * 2, ry * 2)
    if alpha >= 255:
        pygame.draw.ellipse(surf, color, rect)
        return
    sw, sh = surf.get_size()
    x0, y0 = max(0, rect.x - 1), max(0, rect.y - 1)
    x1, y1 = min(sw, rect.right + 2), min(sh, rect.bottom + 2)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    layer = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, rgba(color, alpha),
                        pygame.Rect(rect.x - x0, rect.y - y0, rect.w, rect.h))
    surf.blit(layer, (x0, y0))


def line(dst, a, b, color, width=1, alpha=255):
    surf = _surf(dst)
    width = max(1, int(width))
    if alpha >= 255:
        pygame.draw.line(surf, color, (int(a[0]), int(a[1])),
                         (int(b[0]), int(b[1])), width)
        return
    sw, sh = surf.get_size()
    x0, y0, x1, y1 = _bbox([a, b], sw, sh, pad=width + 2)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    layer = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
    pygame.draw.line(layer, rgba(color, alpha),
                     (int(a[0]) - x0, int(a[1]) - y0),
                     (int(b[0]) - x0, int(b[1]) - y0), width)
    surf.blit(layer, (x0, y0))


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------

class View:
    def __init__(self, layout):
        self.layout = layout
        self.W, self.H = layout["size"]
        self.ss = layout["ss"]
        self.w, self.h = self.W * self.ss, self.H * self.ss
        self.horizon = self.h * layout["horizon"]
        self.land = self.h - self.horizon
        self.obj = layout["obj"] * self.ss
        self.surface = None

    def __getattr__(self, name):
        surface = self.__dict__.get("surface")
        if surface is not None:
            return getattr(surface, name)
        raise AttributeError(name)

    def x(self, xf: float) -> float:
        return self.w * xf

    def y(self, yf: float) -> float:
        return self.h * yf

    def px(self, v: float) -> float:
        return v * self.ss

    def depth(self, y: float) -> float:
        return max(0.0, min(1.4, (y - self.horizon) / self.land))

    def sized(self, base: float, y: float, boost: float = 1.0) -> float:
        return base * self.obj * max(0.05, self.depth(y)) * boost


# ---------------------------------------------------------------------------
# sky
# ---------------------------------------------------------------------------

def draw_cloud(dst: View, cx: float, cy: float, scale: float, alpha: float):
    """A flat cartoon cumulus, centred on (cx, cy) and shaded top-to-bottom."""
    k = (dst.w * 0.030 if dst.layout["name"] == "strip"
         else dst.w * 0.050) * scale
    w, hh = int(k * 3.8), int(k * 1.30)
    if w < 8 or hh < 6:
        return
    mask = pygame.Surface((w, hh), pygame.SRCALPHA)
    pygame.draw.ellipse(mask, (255, 255, 255, 255),
                        pygame.Rect(int(w * 0.03), int(hh * 0.48),
                                    int(w * 0.94), int(hh * 0.38)))
    lobes = [(0.17, 0.62, 0.17), (0.30, 0.43, 0.22), (0.46, 0.33, 0.25),
             (0.62, 0.40, 0.21), (0.77, 0.55, 0.18), (0.88, 0.64, 0.12)]
    for fx, fy, fr in lobes:
        pygame.draw.circle(mask, (255, 255, 255, 255),
                           (int(w * fx), int(hh * fy)), int(hh * fr * 1.55))
    pygame.draw.rect(mask, (255, 255, 255, 255),
                     pygame.Rect(int(w * 0.05), int(hh * 0.62),
                                 int(w * 0.90), int(hh * 0.19)))
    grad = vgrad(w, hh, [
        (0.00, mix(PAL["cloud"], (255, 255, 255), 0.62)),
        (0.32, PAL["cloud"]),
        (0.66, mix(PAL["cloud"], PAL["cloud_shade"], 0.36)),
        (0.88, mix(PAL["cloud_shade"], PAL["cloud_warm"], 0.62)),
        (1.00, mix(PAL["cloud_warm"], PAL["cloud_shade"], 0.28)),
    ]).convert_alpha()
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if alpha < 1.0:
        grad.set_alpha(int(255 * alpha))
    dst.blit(grad, (int(cx - w * 0.5), int(cy - hh * 0.55)))


def draw_sky(dst: View, rng: random.Random):
    W, H, hor = dst.w, dst.h, dst.horizon
    sky = vgrad(W, int(hor) + 2, [
        (0.00, PAL["sky_top"]),
        (0.32, PAL["sky_high"]),
        (0.60, PAL["sky_mid"]),
        (0.80, PAL["sky_low"]),
        (0.93, mix(PAL["sky_low"], PAL["sky_horizon"], 0.74)),
        (1.00, PAL["sky_horizon"]),
    ])
    dst.blit(sky, (0, 0))

    sx, above, radius = dst.layout["sun"]
    sun_x = W * sx
    sun_y = hor - H * above
    sun_r = max(dst.px(14), H * radius)

    blit_soft(dst, sun_x, hor + H * 0.006, W * 0.95, H * 0.34,
              PAL["sky_glow"], 62, 2.2)
    blit_soft(dst, sun_x, sun_y, W * 0.38, W * 0.38,
              PAL["sky_glow"], 118, 1.9)
    blit_soft(dst, sun_x, sun_y, sun_r * 6.2, sun_r * 6.2,
              PAL["sun"], 100, 2.0)
    circle(dst, sun_x, sun_y, sun_r * 1.18,
           mix(PAL["sun"], PAL["sky_glow"], 0.28))
    circle(dst, sun_x, sun_y, sun_r, PAL["sun"])
    circle(dst, sun_x - sun_r * 0.08, sun_y - sun_r * 0.10, sun_r * 0.72,
           PAL["sun_core"])

    mh = max(2, int(dst.px(22)))
    face = pygame.Surface((W, mh), pygame.SRCALPHA)
    for row in range(mh):
        a = int(52 * math.sin(math.pi * row / max(1, mh - 1)))
        pygame.draw.line(face, rgba(PAL["sky_horizon"], a), (0, row), (W, row))
    dst.blit(face, (0, int(hor - mh * 0.72)))

    for cx, cy, scale, alpha in dst.layout["clouds"]:
        draw_cloud(dst, cx * W, cy * H, scale, alpha)

    bird_col = mix(PAL["sky_top"], (24, 44, 54), 0.42)
    for bx, by, bs in dst.layout["birds"]:
        x, y = bx * W, by * H
        s = dst.px(5.4) * bs if dst.layout["name"] == "strip" else dst.px(7.2) * bs
        for k in (-1, 1):
            pygame.draw.lines(
                dst.surface, bird_col, False,
                [(x - s * 1.5 * k, y), (x - s * 0.5 * k, y + s * 0.55),
                 (x, y), (x + s * 0.5 * k, y + s * 0.55),
                 (x + s * 1.5 * k, y)],
                max(1, int(dst.px(0.55)) + 1))


# ---------------------------------------------------------------------------
# mountains and sea
# ---------------------------------------------------------------------------

def _ridge_line(dst: View, base_y: float, peaks, height_scale: float):
    W = dst.w
    step = max(2, int(dst.px(2)))
    pts = []
    for x in range(0, W + step, step):
        h = 0.0
        for cx, width, height in peaks:
            cx_px = cx * W
            w_px = max(1.0, width * W)
            h += height * dst.h * math.exp(-((x - cx_px) / w_px) ** 2)
        h += dst.h * 0.006 * math.sin(x / W * 19.0 + 1.2)
        h += dst.h * 0.003 * math.sin(x / W * 43.0 + 0.4)
        h = min(h, dst.h * 0.365)
        pts.append((x, max(base_y - h * height_scale, dst.h * 0.045)))
    return pts


def draw_range(dst: View, spec, color, *, snowline=None, alpha=255,
               height_scale=1.0, base_frac=0.270):
    W, H = dst.w, dst.h
    base_y = H * base_frac
    sun_x = W * dst.layout["sun"][0]
    ridge = _ridge_line(dst, base_y, spec["peaks"], height_scale)
    fill = ridge + [(W, base_y + dst.px(2)), (0, base_y + dst.px(2))]
    poly(dst, fill, color, alpha)

    # volume: cool on the left flank, warm on the sun side
    mask = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(int(x), int(y)) for x, y in fill])
    grad1 = pygame.Surface((W, 1), pygame.SRCALPHA)
    for x in range(W):
        t = x / max(1, W - 1)
        col = mix(mix(color, PAL["shadow"], 0.24),
                  mix(color, PAL["sky_glow"], 0.14), t)
        grad1.set_at((x, 0), rgba(col, 58))
    grad = pygame.transform.smoothscale(grad1, (W, H))
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(grad, (0, 0))

    for i in range(len(ridge) - 1):
        x, y = ridge[i]
        nx, ny = ridge[i + 1]
        if ny < y:
            lit = 1.0 - abs(x - sun_x) / W
            line(dst, (x, y + dst.px(0.4)), (nx, ny + dst.px(0.4)),
                 mix(color, PAL["sky_glow"], 0.28 + 0.22 * lit),
                 max(1, int(dst.px(0.65))), 90)

    if snowline is not None:
        snow_y = base_y - H * snowline
        span, spans = [], []
        for x, y in ridge:
            if y < snow_y:
                span.append((x, y))
            elif span:
                spans.append(span)
                span = []
        if span:
            spans.append(span)
        for span in spans:
            if len(span) < 3:
                continue
            cap = list(span)
            for x, _ in reversed(span):
                wob = (math.sin(x / dst.w * 37.0) * 0.30 +
                       math.sin(x / dst.w * 91.0 + 0.7) * 0.16)
                cap.append((x, snow_y + H * 0.020 * wob))
            poly(dst, cap, PAL["snow"], 236)
            shadow = [(x, y + H * 0.016) for x, y in cap[:len(span)]]
            shadow += [(x, y) for x, y in reversed(cap[len(span):])]
            poly(dst, shadow, PAL["snow_shadow"], 80)



    foot = pygame.Surface((W, int(dst.px(30))), pygame.SRCALPHA)
    for row in range(foot.get_height()):
        t = row / max(1, foot.get_height() - 1)
        a = int(96 * (1.0 - t) ** 1.5)
        pygame.draw.line(foot, rgba(PAL["haze"], a), (0, row), (W, row))
    dst.blit(foot, (0, int(base_y - dst.px(10))))


def draw_mountains(dst: View):
    spec = dst.layout["mountains"]
    draw_range(dst, spec["far"], PAL["far_mtn"],
               snowline=spec["far"]["snowline"], base_frac=spec["base"])
    draw_range(dst, spec["near"],
               mix(PAL["far_mtn"], PAL["valley_mid"], 0.30),
               snowline=spec["near"]["snowline"], base_frac=spec["base"],
               alpha=172, height_scale=0.56)

    W = dst.w
    base_y = dst.h * spec["base"]
    ridge = []
    for x in range(0, W + int(dst.px(3)), int(dst.px(3))):
        xf = x / W
        h = (math.sin(xf * 23 + 0.7) * 0.004 +
             math.sin(xf * 57 + 2.1) * 0.0025 +
             math.exp(-((xf - 0.18) / 0.16) ** 2) * 0.012 +
             math.exp(-((xf - 0.86) / 0.15) ** 2) * 0.015)
        ridge.append((x, base_y - dst.h * h))
    ridge += [(W, base_y + 2), (0, base_y + 2)]
    poly(dst, ridge, mix(PAL["far_mtn_dark"], PAL["haze"], 0.35), 235)


def draw_sea(dst: View, rng: random.Random):
    W, H = dst.w, dst.h
    spec = dst.layout["sea"]
    top = H * spec["top"]
    bottom = H * spec["bottom"]
    sea = vgrad(W, int(max(3, bottom - top)), [
        (0.00, mix(PAL["sea_far"], PAL["sky_horizon"], 0.55)),
        (0.14, PAL["sea_far"]),
        (0.50, PAL["sea"]),
        (0.82, mix(PAL["sea"], PAL["sea_deep"], 0.45)),
        (1.00, PAL["sea_deep"]),
    ])
    dst.blit(sea, (0, int(top)))

    refl = pygame.Surface((W, int(H * 0.10)), pygame.SRCALPHA)
    for _ in range(46):
        x = rng.uniform(0.02, 0.98) * W
        hgt = rng.uniform(0.004, 0.045) * H
        pygame.draw.line(refl, rgba(mix(PAL["far_mtn"], PAL["sea"], 0.42),
                                    rng.randint(10, 30)),
                         (int(x), 0), (int(x), int(hgt)))
    dst.blit(refl, (0, int(top)))

    sun_x = W * dst.layout["sun"][0]
    for i in range(13):
        yy = top + dst.px(1.8 + i * 2.6)
        ww = dst.px(10 + i * 16) * (1.0 - i * 0.045)
        line(dst, (sun_x - ww / 2, yy), (sun_x + ww / 2, yy),
             PAL["sea_glint"], max(1, int(dst.px(0.6))), 52 - i * 3)

    for _ in range(150 if dst.layout["name"] == "strip" else 280):
        y = rng.uniform(top + dst.px(2), bottom - dst.px(2))
        x = rng.uniform(0.02, 0.98) * W
        ln = rng.uniform(3, 22) * dst.obj * (0.4 + 0.6 * rng.random())
        line(dst, (x - ln / 2, y), (x + ln / 2, y), PAL["water_light"],
             max(1, int(dst.px(0.5))), rng.randint(16, 46))
    # a faint far shoreline with headlands
    shore_y = bottom - dst.px(2.0)
    for i in range(0, W, int(dst.px(6))):
        xf = i / W
        h = (math.sin(xf * 11 + 0.4) * 0.006 +
             math.sin(xf * 31 + 1.7) * 0.003 +
             math.exp(-((xf - 0.18) / 0.14) ** 2) * 0.008 +
             math.exp(-((xf - 0.84) / 0.13) ** 2) * 0.010)
        yy = shore_y - dst.h * max(0.0, h)
        if i == 0:
            prev = (i, yy)
            continue
        line(dst, prev, (i, yy), mix(PAL["far_mtn_dark"], PAL["sea_deep"], 0.30),
             max(1, int(dst.px(1.0))), 80)
        prev = (i, yy)

    for xf, yf, s in ((0.395, 0.305, 0.35), (0.660, 0.298, 0.42),
                      (0.745, 0.312, 0.28)):
        _sailboat(dst, xf, yf, s)
    for xf, yf, s in ((0.625, 0.322, 0.0045), (0.700, 0.316, 0.0030),
                      (0.300, 0.334, 0.0034)):
        x, y = xf * W, yf * H
        r = dst.w * s
        poly(dst, [(x - r, y), (x - r * 0.35, y - r * 1.1),
                   (x + r * 0.55, y - r * 0.65), (x + r, y)],
             mix(PAL["far_mtn_dark"], PAL["sea_deep"], 0.30), 230)


def _sailboat(dst: View, xf: float, yf: float, s: float):
    x, y = xf * dst.w, yf * dst.h
    size = max(dst.px(1.8), dst.px(8.0) * s)
    hull = mix(PAL["far_mtn_dark"], PAL["sea_deep"], 0.25)
    poly(dst, [(x - size * 0.55, y), (x + size * 0.55, y),
               (x + size * 0.35, y + size * 0.22),
               (x - size * 0.35, y + size * 0.22)], hull)
    line(dst, (x, y - size * 0.06), (x, y - size * 0.95), PAL["trunk"],
         max(1, int(size * 0.10)), 200)
    poly(dst, [(x + size * 0.04, y - size * 0.90),
               (x + size * 0.48, y - size * 0.16),
               (x + size * 0.04, y - size * 0.16)], PAL["wall"], 236)
    line(dst, (x - size * 0.55, y + size * 0.26),
         (x + size * 0.55, y + size * 0.26), PAL["foam"],
         max(1, int(size * 0.08)), 60)


# ---------------------------------------------------------------------------
# valley floor, fields, river
# ---------------------------------------------------------------------------

def draw_valley_floor(dst: View, rng: random.Random):
    W, H = dst.w, dst.h
    top = H * dst.layout["coastline"]
    coast = []
    for x in range(0, W + int(dst.px(2)), int(dst.px(2))):
        xf = x / W
        bay = math.exp(-((xf - dst.layout["delta"]["x"]) / 0.16) ** 2)
        wob = (math.sin(xf * 31 + 0.3) * 0.004 +
               math.sin(xf * 79 + 1.1) * 0.0025)
        coast.append((x, top + dst.h * (0.018 * bay + wob)))
    mask = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(int(x), int(y)) for x, y in coast] +
                        [(W, H), (0, H)])
    grad = pygame.Surface((W, H))
    for y in range(int(top) - 4, H):
        t = (y - top) / max(1.0, H - top)
        if t < 0.16:
            col = PAL["valley_far"]
        elif t < 0.50:
            col = mix(PAL["valley_far"], PAL["valley_mid"], (t - 0.16) / 0.34)
        else:
            col = mix(PAL["valley_mid"], PAL["valley_near"],
                      min(1.0, (t - 0.50) / 0.50))
        pygame.draw.line(grad, col, (0, y), (W, y))
    grad = grad.convert_alpha()
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(grad, (0, 0))

    for i in range(len(coast) - 1):
        line(dst, coast[i], coast[i + 1], mix(PAL["sand"], PAL["foam"], 0.45),
             max(1, int(dst.px(1.2))), 180)
        line(dst, (coast[i][0], coast[i][1] + dst.px(2.0)),
             (coast[i + 1][0], coast[i + 1][1] + dst.px(2.0)),
             PAL["foam"], max(1, int(dst.px(0.65))), 95)


def _river_points(dst: View):
    ctrl = [(xf * dst.w, yf * dst.h) for xf, yf in dst.layout["river"]]
    return catmull(ctrl, samples=14)


def _river_width(dst: View, y: float) -> float:
    t = (y - dst.h * dst.layout["delta"]["y"]) / max(
        1.0, dst.h - dst.h * dst.layout["delta"]["y"])
    return max(dst.px(1.2),
               dst.layout["river_width"] * dst.obj * max(0.04, t) ** 0.98)


def _river_x_at_y(dst: View, y: float) -> float:
    pts = _river_points(dst)
    if y <= pts[0][1]:
        return pts[0][0]
    if y >= pts[-1][1]:
        return pts[-1][0]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if y0 <= y <= y1 and abs(y1 - y0) > 1e-6:
            t = (y - y0) / (y1 - y0)
            return x0 + (x1 - x0) * t
    return pts[-1][0]


def _normals(p):
    out = []
    for i, (x, y) in enumerate(p):
        if i == 0:
            dx, dy = p[1][0] - x, p[1][1] - y
        elif i == len(p) - 1:
            dx, dy = x - p[-2][0], y - p[-2][1]
        else:
            dx, dy = p[i + 1][0] - p[i - 1][0], p[i + 1][1] - p[i - 1][1]
        ln = math.hypot(dx, dy) or 1.0
        out.append((-dy / ln, dx / ln))
    return out


def draw_river(dst: View, rng: random.Random):
    W, H = dst.w, dst.h
    pts = _river_points(dst)
    widths = [_river_width(dst, y) for _, y in pts]
    normals = _normals(pts)

    left, right = [], []
    for i, (x, y) in enumerate(pts):
        nx, ny = normals[i]
        half = widths[i] * 0.5
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))

    # a wide silt / shallow bank under the water
    bank_l, bank_r = [], []
    for i, (x, y) in enumerate(pts):
        nx, ny = normals[i]
        half = widths[i] * 0.95
        bank_l.append((x + nx * half, y + ny * half))
        bank_r.append((x - nx * half, y - ny * half))
    poly(dst, bank_l + list(reversed(bank_r)),
         mix(PAL["silt"], PAL["sand"], 0.20), 190)
    poly(dst, left + list(reversed(right)),
         mix(PAL["water_light"], PAL["water"], 0.20), 250)

    # the water column as one smooth gradient, clipped by the river polygon
    mask = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(int(x), int(y)) for x, y in left + list(reversed(right))])
    grad = pygame.Surface((W, H))
    top = dst.h * dst.layout["delta"]["y"]
    for y in range(int(top), H):
        t = (y - top) / max(1.0, H - top)
        col = mix(mix(PAL["water_light"], PAL["water"], min(1.0, t * 2.0)),
                  PAL["water_deep"], max(0.0, (t - 0.25) * 1.25))
        pygame.draw.line(grad, col, (0, y), (W, y))
    grad = grad.convert_alpha()
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(grad, (0, 0))

    # a soft sunlit band down the eastern bank, and a darker west edge
    for i in range(len(pts) - 1):
        x, y = pts[i]
        nx, ny = normals[i]
        w = widths[i]
        x1, y1 = pts[i + 1]
        nx2, ny2 = normals[i + 1]
        w2 = widths[i + 1]
        line(dst, (x + nx * w * 0.42, y + ny * w * 0.42),
             (x1 + nx2 * w2 * 0.42, y1 + ny2 * w2 * 0.42),
             mix(PAL["water_light"], PAL["foam"], 0.42),
             max(1, int(w * 0.10)), 80)
        line(dst, (x - nx * w * 0.44, y - ny * w * 0.44),
             (x1 - nx2 * w2 * 0.44, y1 - ny2 * w2 * 0.44),
             mix(PAL["water_deep"], PAL["shadow"], 0.18),
             max(1, int(w * 0.08)), 55)

    # sparse ripples, short and mostly horizontal
    for _ in range(30):
        i = rng.randrange(1, len(pts) - 2)
        x, y = pts[i]
        w = widths[i]
        ln = rng.uniform(0.14, 0.40) * w
        off = rng.uniform(-0.26, 0.26) * w
        line(dst, (x + off - ln / 2, y), (x + off + ln / 2, y), PAL["foam"],
             max(1, int(dst.px(0.55) + w * 0.025)), 80)

    _draw_delta(dst)

def _draw_delta(dst: View):
    """A wide estuary at the river mouth, with sandbars and a harbour."""
    spec = dst.layout["delta"]
    coast = dst.layout["coastline"]
    mx = spec["x"] * dst.w
    my = (coast + 0.006) * dst.h
    rx = dst.w * (0.080 if dst.layout["name"] == "strip" else 0.095)
    ry = dst.h * (0.018 if dst.layout["name"] == "strip" else 0.015)
    # lagoon
    ellipse(dst, mx, my, rx, ry, mix(PAL["water"], PAL["water_light"], 0.20), 245)
    ellipse(dst, mx - rx * 0.10, my - ry * 0.20, rx * 0.74, ry * 0.52,
            PAL["water_light"], 90)
    # the river's last reach splits into two small channels
    for side in (-1, 1):
        pts = [(mx + side * rx * 0.10, my - ry * 0.2),
               (mx + side * rx * 0.50, my - ry * 0.8),
               (mx + side * rx * 0.82, my - ry * 0.3)]
        pts = catmull(pts, samples=6)
        for i in range(len(pts) - 1):
            line(dst, pts[i], pts[i + 1],
                 mix(PAL["water"], PAL["water_light"], 0.25),
                 max(1, int(dst.px(1.2) + dst.px(1.6) * (1 - i / len(pts)))), 200)
    # sandbars
    for k, (ox, oy, sx, sy) in enumerate((
            (-0.46, -0.12, 0.32, 0.42), (-0.10, 0.18, 0.26, 0.30),
            (0.30, -0.22, 0.30, 0.34), (0.58, 0.12, 0.22, 0.26))):
        ellipse(dst, mx + rx * ox, my + ry * oy, rx * sx, ry * sy,
                mix(PAL["sand"], PAL["silt"], 0.50), 210)
    # the river itself enters the lagoon at its centre
    ellipse(dst, mx, my + ry * 0.7, rx * 0.22, ry * 0.45,
            mix(PAL["water"], PAL["water_light"], 0.12), 220)


def draw_fields(dst: View, rng: random.Random):
    """A perspective patchwork.  Rows follow the converging ridges, so the
    near fields are wide and the far ones are chips, and the whole floor reads
    as farmland seen from above rather than a flat map."""
    W, H = dst.w, dst.h
    left = _crest_points(dst, dst.layout["left_hill"]["crest"])
    right = _crest_points(dst, dst.layout["right_hill"]["crest"])
    colors = [
        (208, 190, 122), (168, 198, 104), (140, 168, 86),
        (184, 204, 124), (118, 154, 86), (88, 132, 76),
        (196, 176, 122), (152, 186, 120),
    ]
    fs = dst.layout["fields"]
    y = fs["y0"] * H
    row = 0
    while y < fs["y1"] * H:
        d = dst.depth(y)
        rh = (0.015 + 0.038 * d) * H
        yc = y + rh * 0.5
        xl = _crest_x_at(left, yc) + 0.014 * W
        xr = _crest_x_at(right, yc) - 0.014 * W
        rx = _river_x_at_y(dst, yc)
        corridor = max(0.012 * W, _river_width(dst, yc) * 1.5)
        segments = [(xl, rx - corridor), (rx + corridor, xr)]
        for seg_i, (sx0, sx1) in enumerate(segments):
            if sx1 - sx0 < 0.025 * W:
                continue
            target = (0.070 + 0.060 * d) * W
            x = sx0
            col = 0
            while x < sx1 - 0.012 * W:
                w = min(sx1 - x, target * rng.uniform(0.70, 1.30))
                if w < 0.018 * W:
                    break
                # small jitter on the corners
                jt = (rng.uniform(-0.003, 0.003) * W,
                      rng.uniform(-0.003, 0.003) * W)
                x0, x1 = x + jt[0], x + w + jt[1]
                top = y + rng.uniform(-0.002, 0.002) * H
                bot = y + rh + rng.uniform(-0.001, 0.001) * H
                if x1 > sx1:
                    x1 = sx1
                colr = colors[(row * 3 + col + seg_i) % len(colors)]
                if d < 0.55:
                    colr = mix(colr, PAL["haze"], 0.18)
                pts = [(x0, top), (x1, top),
                       (x1 + rng.uniform(-0.002, 0.002) * W, bot),
                       (x0 + rng.uniform(-0.002, 0.002) * W, bot)]
                poly(dst, pts, colr, 244)
                # furrows
                rows = 3 if rh > dst.px(9) else 2
                for k in range(rows):
                    yy = top + rh * (0.25 + 0.50 * k / max(1, rows - 1))
                    line(dst, (x0 + w * 0.06, yy), (x1 - w * 0.06, yy),
                         mix(colr, PAL["forest_dark"], 0.46),
                         max(1, int(dst.px(0.7) + d * dst.px(0.6))), 95)
                edge = mix(PAL["forest_dark"], colr, 0.22)
                for k in range(4):
                    line(dst, pts[k], pts[(k + 1) % 4], edge,
                         max(1, int(dst.px(0.8) + d * dst.px(0.7))), 135)
                # a hedgerow on some boundaries
                if rng.random() < 0.62:
                    for j in range(rng.randint(3, 6)):
                        tx = x0 + (x1 - x0) * (j + 0.5) / 6
                        _draw_tree(dst, tx, top + rh * 0.06,
                                   rng.uniform(4.0, 9.0) * dst.obj * max(0.2, d),
                                   "round", rng)
                x += w
                col += 1
        y += rh
        row += 1


def draw_forest_patches(dst: View, rng: random.Random):
    patches = [
        (0.355, 0.520, 0.060, 0.055, "dark"),
        (0.665, 0.500, 0.052, 0.048, "dark"),
        (0.405, 0.650, 0.048, 0.045, "mid"),
        (0.690, 0.625, 0.042, 0.040, "mid"),
        (0.300, 0.445, 0.038, 0.030, "mid"),
        (0.745, 0.430, 0.034, 0.026, "dark"),
    ]
    shift = max(0.0, dst.layout["coastline"] - 0.365)
    for cx, cy, rx, ry, tone in patches:
        cxp, cyp = cx * dst.w, (cy + shift) * dst.h
        rxp, ryp = rx * dst.w, ry * dst.h
        pts = []
        for k in range(16):
            a = TAU * k / 16
            wob = 1.0 + 0.15 * math.sin(k * 2.3 + cx * 7) + rng.uniform(-0.05, 0.05)
            pts.append((cxp + math.cos(a) * rxp * wob,
                        cyp + math.sin(a) * ryp * wob))
        base = PAL["forest_dark"] if tone == "dark" else PAL["forest"]
        col = mix(base, PAL["valley_mid"], 0.18)
        poly(dst, pts, col, 235)
        for i in range(9):
            a = rng.uniform(0, TAU)
            px = cxp + math.cos(a) * rxp * rng.uniform(0.6, 1.0)
            py = cyp + math.sin(a) * ryp * rng.uniform(0.6, 1.0)
            d = dst.depth(py)
            h = 40.0 * (d ** 1.35) * dst.obj * rng.uniform(0.55, 1.05)
            if h > dst.px(2.0):
                _draw_tree(dst, px, py, h,
                           "pine" if rng.random() < 0.65 else "round", rng)


def draw_pond(dst: View, rng: random.Random):
    d = 0.575
    x, y = 0.655 * dst.w, d * dst.h
    rx = dst.obj * dst.ss * 28 * max(0.2, d)
    ry = max(dst.px(2.0), rx * 0.22)
    ellipse(dst, x, y, rx * 1.20, ry * 1.40,
            mix(PAL["silt"], PAL["valley_mid"], 0.35), 150)
    ellipse(dst, x, y, rx, ry, mix(PAL["water"], PAL["water_light"], 0.20), 240)
    ellipse(dst, x - rx * 0.10, y - ry * 0.12, rx * 0.58, ry * 0.42,
            PAL["water_light"], 100)
    for _ in range(9):
        a = rng.uniform(0, TAU)
        sx = x + math.cos(a) * rx * 0.92
        sy = y + math.sin(a) * ry * 0.80
        line(dst, (sx, sy), (sx, sy - rng.uniform(2, 6) * dst.obj * 0.7),
             mix(PAL["meadow"], PAL["forest_dark"], 0.40),
             max(1, int(dst.px(0.6))), 170)
    line(dst, (x + rx * 0.2, y + ry * 0.2), (x + rx * 0.8, y + ry * 0.1),
         PAL["trunk"], max(1, int(dst.px(1.0))), 180)


def draw_roads(dst: View, rng: random.Random):
    # town -> delta, on the east bank
    town_y = dst.layout["town"]["y"]
    end_y = dst.layout["delta"]["y"] + 0.015
    road = []
    for i in range(7):
        yf = town_y + (end_y - town_y) * i / 6
        y = yf * dst.h
        road.append((_river_x_at_y(dst, y) + 0.020 * dst.w, y))
    draw_path(dst, road, 1.6, 150)

    # farm -> river bridge -> town
    farm = dst.layout["farm"]
    fx, fy = farm["x"] * dst.w, farm["y"] * dst.h
    road2 = [(fx - 0.015 * dst.w, fy + 0.085 * dst.h),
             (fx - 0.055 * dst.w, fy + 0.070 * dst.h),
             (fx - 0.120 * dst.w, fy + 0.060 * dst.h),
             (0.580 * dst.w, 0.635 * dst.h),
             (0.520 * dst.w, 0.615 * dst.h)]
    draw_path(dst, catmull(road2, samples=9), 1.9, 130)

    # bridge over the river
    by = 0.612 * dst.h
    bx = _river_x_at_y(dst, by)
    bw = max(dst.px(7.0), dst.obj * 13.0)
    line(dst, (bx - bw, by), (bx + bw, by),
         mix(PAL["wall"], PAL["sand"], 0.30), max(1, int(dst.px(2.0))), 240)
    for k in (-0.55, 0.0, 0.55):
        line(dst, (bx + bw * k, by - dst.px(2.0)),
             (bx + bw * k, by + dst.px(2.0)), PAL["roof_dark"],
             max(1, int(dst.px(0.8))), 160)


def draw_path(dst: View, pts, width, alpha=160):
    if len(pts) < 2:
        return
    for i in range(len(pts) - 1):
        y = pts[i][1]
        w = max(dst.px(0.7), width * dst.obj * max(0.15, dst.depth(y)))
        line(dst, pts[i], pts[i + 1], mix(PAL["sand"], PAL["meadow"], 0.32),
             max(1, int(w)), alpha)
        line(dst, (pts[i][0], pts[i][1] + w * 0.6),
             (pts[i + 1][0], pts[i + 1][1] + w * 0.6),
             mix(PAL["rock_hi"], PAL["sand"], 0.35),
             max(1, int(w * 0.55)), int(alpha * 0.55))


def draw_valley_mist(dst: View, rng: random.Random):
    W, H = dst.w, dst.h
    # aerial haze over the far half of the valley
    top = int(dst.h * dst.layout["coastline"])
    bottom = int(dst.h * 0.575)
    hz = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(top, bottom):
        t = (y - top) / max(1, bottom - top)
        a = int(78 * (1.0 - t) ** 1.35)
        if a:
            pygame.draw.line(hz, rgba(PAL["haze"], a), (0, y), (W, y))
    dst.blit(hz, (0, 0))
    # low cloud pooled over the far floor and the river bend
    for xf, off, wf, hf, a in ((0.500, 0.020, 0.90, 0.022, 68),
                               (0.470, 0.075, 0.72, 0.030, 56),
                               (0.540, 0.140, 0.60, 0.034, 42),
                               (0.430, 0.195, 0.42, 0.030, 24)):
        yf = dst.layout["coastline"] + off
        blit_soft(dst, xf * W, yf * H, wf * W, hf * H, PAL["haze"], a, 2.0)
    # cloud shadows crossing the open valley
    for xf, yf, wf, hf, a in ((0.600, 0.470, 0.32, 0.060, 22),
                              (0.380, 0.600, 0.28, 0.050, 18)):
        blit_soft(dst, xf * W, yf * H, wf * W, hf * H, PAL["shadow"], a, 2.0)


def draw_valley_rows(dst: View, rng: random.Random):
    """Tree rows along the river and the field boundaries: the strongest
    near/far cue in the middle distance."""
    # east and west banks of the river
    top = (dst.layout["coastline"] + 0.020) * dst.h
    for side, xoff, step in ((1, 0.024, 0.018), (-1, 0.024, 0.024)):
        y = 0.735 * dst.h
        while y > top:
            x = _river_x_at_y(dst, y) + side * xoff * dst.w
            h = 26.0 * dst.obj * max(0.18, dst.depth(y)) * rng.uniform(0.55, 1.1)
            if h > dst.px(2.0):
                _draw_tree(dst, x, y, h,
                           "round" if rng.random() < 0.55 else "pine", rng)
            y -= step * dst.h
    # hedgerows converging on the delta
    for side in (-1, 1):
        y = 0.700 * dst.h
        while y > dst.layout["coastline"] * dst.h + 0.030 * dst.h:
            t = (0.700 - y / dst.h) / 0.280
            x = (0.548 + side * (0.20 - 0.10 * t)) * dst.w
            h = 22.0 * dst.obj * max(0.18, dst.depth(y)) * rng.uniform(0.5, 1.0)
            if h > dst.px(2.0) and rng.random() < 0.75:
                _draw_tree(dst, x, y, h, "round", rng)
            y -= 0.020 * dst.h
    # a couple of large near trees on the valley floor, for scale
    for xf, yf, hf in ((0.585, 0.690, 0.110), (0.430, 0.715, 0.085),
                       (0.735, 0.600, 0.070)):
        _draw_tree(dst, xf * dst.w, yf * dst.h, hf * dst.h, "round", rng, hero=True)


# ---------------------------------------------------------------------------
# settlements
# ---------------------------------------------------------------------------

def draw_town(dst: View, rng: random.Random):
    spec = dst.layout["town"]
    cx, cy = spec["x"] * dst.w, spec["y"] * dst.h
    s = dst.obj * dst.ss * spec["scale"] * 0.55
    for i in range(20):
        y = cy + rng.uniform(-0.035, 0.045) * dst.h
        x = cx + rng.uniform(-0.045, 0.045) * dst.w
        if abs(x - _river_x_at_y(dst, y)) < dst.px(14):
            x += dst.px(16) * (1 if x > _river_x_at_y(dst, y) else -1)
        d = dst.depth(y)
        w = rng.uniform(4.5, 9.0) * s * max(0.4, d)
        h = rng.uniform(5.0, 11.0) * s * max(0.4, d)
        col = PAL["wall"] if i % 3 else mix(PAL["wall"], PAL["sand"], 0.35)
        poly(dst, [(x - w, y), (x + w, y), (x + w, y - h), (x - w, y - h)], col)
        poly(dst, [(x - w * 1.16, y - h), (x, y - h * 1.55),
                   (x + w * 1.16, y - h)], PAL["roof"])
        if i % 2 == 0:
            circle(dst, x, y - h * 0.44, max(1, 0.9 * s * d), PAL["city"], 210)
    tx, ty = cx + 0.012 * dst.w, cy - 0.020 * dst.h
    tw, th = 2.4 * s, 18 * s
    poly(dst, [(tx - tw, ty), (tx + tw, ty), (tx + tw, ty - th), (tx - tw, ty - th)],
         PAL["wall"])
    poly(dst, [(tx - tw * 1.5, ty - th), (tx, ty - th * 1.9),
               (tx + tw * 1.5, ty - th)], PAL["roof_dark"])
    circle(dst, tx, ty - th * 0.55, 1.2 * s, PAL["city"], 200)


def draw_delta_city(dst: View, rng: random.Random):
    """The far city at the river mouth: a warm constellation with towers."""
    spec = dst.layout["delta"]
    coast = dst.layout["coastline"]
    cx = spec["x"] * dst.w
    s = (dst.px(1.55) if dst.layout["name"] == "strip" else dst.px(2.8))
    # a warm halo behind the city, so it reads at dawn
    blit_soft(dst, cx, (coast + 0.010) * dst.h, 0.28 * dst.w, 0.10 * dst.h,
              PAL["city"], 34, 2.0)
    glow = pygame.Surface((dst.w, dst.h), pygame.SRCALPHA)
    for i in range(130):
        x = cx + rng.gauss(0, 0.060) * dst.w
        y = (coast + rng.uniform(-0.010, 0.042)) * dst.h
        w = rng.uniform(1.0, 2.6) * s
        h = rng.uniform(1.6, 7.0) * s
        if i < 2:
            w, h = 2.8 * s, (9.0 + i * 3.0) * s
        col = rng.choice((PAL["wall"], PAL["wall"], PAL["roof"],
                          mix(PAL["wall"], PAL["sand"], 0.4)))
        poly(dst, [(x - w, y), (x + w, y), (x + w, y - h), (x - w, y - h)], col)
        # a roof, a tower cap or a lamp
        if h > 10 * s:
            poly(dst, [(x - w * 1.25, y - h), (x, y - h - h * 0.45),
                       (x + w * 1.25, y - h)], PAL["roof_dark"])
        if rng.random() < 0.82:
            pygame.draw.circle(glow, rgba(PAL["city_hot"], rng.randint(160, 250)),
                               (int(x), int(y - h * 0.55)), max(1, int(1.4 * s)))
    dst.blit(glow, (0, 0))
    # lighthouse on the harbour spit
    lx, ly = cx + 0.085 * dst.w, (coast + 0.010) * dst.h
    lw, lh = 1.9 * s, 16.0 * s
    poly(dst, [(lx - lw, ly), (lx + lw, ly), (lx + lw * 0.62, ly - lh),
               (lx - lw * 0.62, ly - lh)], PAL["wall"])
    poly(dst, [(lx - lw * 0.72, ly - lh * 0.78), (lx + lw * 0.72, ly - lh * 0.78),
               (lx + lw * 0.72, ly - lh * 0.64), (lx - lw * 0.72, ly - lh * 0.64)],
         PAL["roof"])
    poly(dst, [(lx - lw * 0.70, ly - lh * 1.10), (lx + lw * 0.70, ly - lh * 1.10),
               (lx + lw * 0.46, ly - lh), (lx - lw * 0.46, ly - lh)],
         mix(PAL["city"], PAL["city_hot"], 0.35))
    blit_soft(dst, lx, ly - lh * 1.05, 10 * s, 8 * s, PAL["city_hot"], 95, 2.0)
    # a warm reflection on the estuary
    for _ in range(24):
        x = cx + rng.gauss(0, 0.050) * dst.w
        y = (coast - rng.uniform(0.000, 0.028)) * dst.h
        line(dst, (x, y), (x, y - rng.uniform(1.5, 4.0) * s), PAL["city"],
             max(1, int(0.9 * s)), rng.randint(30, 80))
    # harbour piers
    for k in (-0.035, 0.005, 0.040):
        x = cx + k * dst.w
        y = (coast + 0.006) * dst.h
        line(dst, (x, y), (x, y - 0.026 * dst.h), PAL["trunk"],
             max(1, int(1.0 * s)), 190)
        line(dst, (x, y - 0.026 * dst.h),
             (x + 0.010 * dst.w, y - 0.026 * dst.h), PAL["trunk"],
             max(1, int(0.8 * s)), 160)




def draw_farm(dst: View, rng: random.Random):
    """The nearest settlement.  Big enough that windows, fences and smoke read."""
    spec = dst.layout["farm"]
    cx, cy = spec["x"] * dst.w, spec["y"] * dst.h
    s = dst.obj * dst.ss * spec["scale"] * 0.52

    # fields around the farm, sized to the near ridge
    for i in range(7):
        x = cx + rng.uniform(-0.095, 0.090) * dst.w
        y = cy + rng.uniform(0.018, 0.085) * dst.h
        w = rng.uniform(0.024, 0.058) * dst.w
        h = w * rng.uniform(0.18, 0.30)
        col = rng.choice((mix(PAL["meadow_hi"], PAL["bloom"], 0.36),
                          mix(PAL["sand"], PAL["meadow_hi"], 0.38),
                          mix(PAL["meadow"], PAL["bloom"], 0.24),
                          mix(PAL["meadow_hi"], PAL["wall"], 0.12)))
        pts = [(x - w, y - h), (x + w, y - h * 0.9),
               (x + w, y + h * 0.9), (x - w, y + h)]
        poly(dst, pts, col, 225)
        rows = 4 if h > dst.px(6) else 2
        for k in range(rows):
            yy = y - h * 0.66 + h * 1.32 * k / (rows - 1)
            line(dst, (x - w * 0.84, yy), (x + w * 0.84, yy),
                 mix(col, PAL["forest_dark"], 0.25),
                 max(1, int(dst.px(0.6))), 60)
        for k in range(4):
            line(dst, pts[k], pts[(k + 1) % 4],
                 mix(PAL["forest_dark"], PAL["meadow"], 0.30),
                 max(1, int(dst.px(0.8))), 95)
        # a hedgerow along one side
        if i % 2 == 0:
            for j in range(5):
                hx = x - w + (2 * w) * j / 4
                _draw_tree(dst, hx, y - h, 4.0 * s * rng.uniform(0.5, 0.9),
                           "round", rng)

    # orchard: a little grid of round trees
    ox, oy = cx + 0.095 * dst.w, cy + 0.060 * dst.h
    for row in range(2):
        for col in range(4):
            tx = ox + col * 5.6 * s
            ty = oy - row * 5.0 * s
            _draw_tree(dst, tx, ty, 7.0 * s * rng.uniform(0.8, 1.1),
                       "round", rng)

    def building(x, y, w, h, kind):
        ellipse(dst, x + w * 0.10, y + h * 0.10, w * 0.65, h * 0.16,
                PAL["shadow"], 45)
        wall = mix(PAL["wall"], PAL["sand"], 0.20)
        # gable roof: front triangle + a side plane for a little volume
        depth = w * 0.28
        lift = h * 0.18
        if kind == "barn":
            poly(dst, [(x - w, y), (x + w, y), (x + w, y - h), (x - w, y - h)], wall)
            poly(dst, [(x - w, y - h), (x, y - h - h * 0.55), (x + w, y - h),
                       (x + w - depth, y - h - lift),
                       (x + depth, y - h - h * 0.70), (x - w - depth, y - h - lift)],
                 PAL["roof_dark"])
            poly(dst, [(x - w, y - h), (x, y - h - h * 0.55),
                       (x + w, y - h), (x + w - depth, y - h - lift),
                       (x + depth, y - h - h * 0.70), (x - w - depth, y - h - lift)],
                 mix(PAL["roof_dark"], PAL["shadow"], 0.25))
            # big barn door + hayloft opening
            poly(dst, [(x - w * 0.16, y), (x + w * 0.16, y),
                       (x + w * 0.16, y - h * 0.62), (x - w * 0.16, y - h * 0.62)],
                 mix(PAL["roof_dark"], PAL["trunk"], 0.25))
            poly(dst, [(x - w * 0.10, y - h * 0.72), (x + w * 0.10, y - h * 0.72),
                       (x + w * 0.10, y - h * 0.92), (x - w * 0.10, y - h * 0.92)],
                 PAL["trunk"])
            line(dst, (x, y - h * 0.62), (x, y), PAL["trunk"],
                 max(1, int(0.8 * s)), 180)
        else:
            poly(dst, [(x - w, y), (x + w, y), (x + w, y - h), (x - w, y - h)], wall)
            poly(dst, [(x - w, y - h), (x, y - h - h * 0.62), (x + w, y - h)],
                 PAL["roof"])
            poly(dst, [(x + w, y - h), (x, y - h - h * 0.62),
                       (x + w - depth, y - h - lift), (x + w, y - h - lift)],
                 mix(PAL["roof"], PAL["roof_dark"], 0.35))
            # door and two warm windows
            poly(dst, [(x - w * 0.12, y), (x + w * 0.12, y),
                       (x + w * 0.12, y - h * 0.52), (x - w * 0.12, y - h * 0.52)],
                 mix(PAL["roof_dark"], PAL["trunk"], 0.25))
            for k in (-0.55, 0.55):
                wx = x + k * w * 0.62
                circle(dst, wx, y - h * 0.58, max(1.0, 1.8 * s),
                       PAL["city"], 235)
                line(dst, (wx, y - h * 0.58 + 1.8 * s),
                     (wx, y - h * 0.58 - 1.8 * s), PAL["trunk"],
                     max(1, int(0.6 * s)), 160)
            # chimney
            chx = x + w * 0.55
            poly(dst, [(chx - w * 0.05, y - h * 0.88),
                       (chx + w * 0.05, y - h * 0.88),
                       (chx + w * 0.05, y - h * 1.35),
                       (chx - w * 0.05, y - h * 1.35)],
                 mix(PAL["wall"], PAL["rock_dark"], 0.35))
        # timber framing
        if kind == "house" or kind == "barn":
            for k in (-0.55, 0.55):
                line(dst, (x + k * w, y), (x + k * w, y - h),
                     mix(PAL["trunk"], PAL["wall"], 0.45),
                     max(1, int(0.8 * s)), 70)

    def silo(x, y, w, h):
        pygame.draw.rect(dst.surface, mix(PAL["rock_hi"], PAL["wall"], 0.55),
                         pygame.Rect(int(x - w * 0.5), int(y - h), int(w), int(h)))
        pygame.draw.ellipse(dst.surface, mix(PAL["rock_hi"], PAL["wall"], 0.75),
                            pygame.Rect(int(x - w * 0.5), int(y - h - w * 0.25),
                                        int(w), int(w * 0.5)))
        pygame.draw.ellipse(dst.surface, PAL["roof"],
                            pygame.Rect(int(x - w * 0.56), int(y - h - w * 0.55),
                                        int(w * 1.12), int(w * 0.7)))
        for k in range(3):
            line(dst, (x - w * 0.45, y - h * (0.15 + k * 0.26)),
                 (x + w * 0.45, y - h * (0.15 + k * 0.26)),
                 mix(PAL["rock_dark"], PAL["wall"], 0.45),
                 max(1, int(0.6 * s)), 90)

    # a dirt yard grounds the buildings
    ellipse(dst, cx + 0.018 * dst.w, cy + 0.040 * dst.h,
            0.085 * dst.w, 0.022 * dst.h, mix(PAL["sand"], PAL["silt"], 0.42), 150)
    # a windbreak / orchard line behind the farm
    for k in range(6):
        tx = cx + (-0.055 + k * 0.024) * dst.w
        ty = cy - 0.005 * dst.h + rng.uniform(-0.004, 0.004) * dst.h
        _draw_tree(dst, tx, ty, rng.uniform(10, 17) * s, "round", rng)

    # place the buildings on the slope
    hx, hy = cx - 0.030 * dst.w, cy + 0.012 * dst.h
    bx, by = cx + 0.028 * dst.w, cy + 0.030 * dst.h
    building(hx, hy, 20 * s, 8.5 * s, "house")
    building(bx, by, 27 * s, 9.5 * s, "barn")
    silo(cx + 0.070 * dst.w, cy + 0.016 * dst.h, 8 * s, 22 * s)
    # a small side roof plane reads as depth on the house gable
    poly(dst, [(hx + 20 * s, hy - 8.5 * s),
               (hx + 26 * s, hy - 10.2 * s),
               (hx + 26 * s, hy - 8.5 * s)],
         mix(PAL["roof"], PAL["roof_dark"], 0.45), 200)

    # fence along the near field
    fx0, fx1 = cx - 0.095 * dst.w, cx + 0.105 * dst.w
    fy = cy + 0.095 * dst.h
    for i in range(13):
        x = fx0 + (fx1 - fx0) * i / 12
        line(dst, (x, fy), (x, fy - 4.0 * s * 0.7), PAL["trunk"],
             max(1, int(0.75 * s)), 190)
    line(dst, (fx0, fy - 3.2 * s * 0.7), (fx1, fy - 3.2 * s * 0.7),
         PAL["trunk"], max(1, int(0.75 * s)), 170)
    line(dst, (fx0, fy - 1.5 * s * 0.7), (fx1, fy - 1.5 * s * 0.7),
         PAL["trunk"], max(1, int(0.6 * s)), 130)

    # chimney smoke
    for k in range(3):
        bx2 = hx + 20 * s * 0.55 + k * dst.px(1.8)
        by2 = hy - 12 * s * 1.35
        pts = [(bx2, by2)]
        for i in range(1, 8):
            pts.append((bx2 + math.sin(i * 0.8 + k) * dst.px(2.2) * i,
                        by2 - i * dst.px(4.2)))
        for i in range(len(pts) - 1):
            line(dst, pts[i], pts[i + 1], mix(PAL["cloud"], PAL["haze"], 0.45),
                 max(1, int(dst.px(1.0))), 30 + k * 8)

    # a track from the farm down the ridge
    track = catmull([(cx - 0.055 * dst.w, cy + 0.095 * dst.h),
                     (cx - 0.020 * dst.w, cy + 0.070 * dst.h),
                     (cx + 0.030 * dst.w, cy + 0.060 * dst.h),
                     (cx + 0.080 * dst.w, cy + 0.075 * dst.h)], samples=7)
    for i in range(len(track) - 1):
        line(dst, track[i], track[i + 1], mix(PAL["sand"], PAL["meadow"], 0.30),
             max(1, int(1.0 * s)), 110)




# ---------------------------------------------------------------------------
# layered hills
# ---------------------------------------------------------------------------

def _crest_points(dst: View, crest):
    return catmull([(xf * dst.w, yf * dst.h) for xf, yf in crest], samples=9)


def _crest_x_at(crest, y: float) -> float:
    if y <= crest[0][1]:
        return crest[0][0]
    if y >= crest[-1][1]:
        return crest[-1][0]
    for i in range(len(crest) - 1):
        x0, y0 = crest[i]
        x1, y1 = crest[i + 1]
        if y0 <= y <= y1 and abs(y1 - y0) > 1e-6:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return crest[-1][0]


def draw_hill(dst: View, spec, crest_norm, rng: random.Random, *, side: str,
              visible_bottom: float, farm_spec=None):
    W, H = dst.w, dst.h
    crest = _crest_points(dst, crest_norm)
    if side == "left":
        fill = crest + [(0, H)]
    else:
        fill = list(reversed(crest)) + [(W, H)]

    mask = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(int(x), int(y)) for x, y in fill])
    top_col = PAL[spec["top_col"]]
    base_col = PAL[spec["base_col"]]
    if not spec["sunlit"]:
        top_col = mix(top_col, PAL["haze"], 0.12)
        base_col = mix(base_col, PAL["shadow"], 0.22)
    grad = pygame.Surface((W, H))
    top_y = min(y for _, y in crest)
    for y in range(max(0, int(top_y) - 2), H):
        t = (y - top_y) / max(1.0, H - top_y)
        col = mix(top_col, base_col, min(1.0, t * 1.15))
        if spec["sunlit"]:
            col = mix(col, PAL["sky_glow"], 0.05 * (1.0 - t))
        pygame.draw.line(grad, col, (0, y), (W, y))
    grad = grad.convert_alpha()
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(grad, (0, 0))

    shadow_pts = [(x, y + dst.px(6)) for x, y in crest]
    for i in range(len(shadow_pts) - 1):
        line(dst, shadow_pts[i], shadow_pts[i + 1],
             mix(PAL["shadow"], PAL["forest_dark"], 0.30),
             max(1, int(dst.px(9.0))), 55)

    # canopy fringe: a ragged line of tree silhouettes that makes the crest a
    # forest edge instead of a drawn arc
    n = len(crest)
    for i in range(n - 1):
        x0, y0 = crest[i]
        x1, y1 = crest[i + 1]
        span = math.hypot(x1 - x0, y1 - y0)
        if span < 0.5:
            continue
        spacing = max(2.0, dst.px(4.5)) if dst.layout["name"] == "strip" else max(3.0, dst.px(5.0))
        steps = max(1, int(span / spacing))
        t = i / max(1, n - 2)
        for k in range(steps):
            if not spec["sunlit"] and rng.random() > 0.32:
                continue
            u = (k + 0.5) / steps
            x = x0 + (x1 - x0) * u
            y = y0 + (y1 - y0) * u
            near = 0.15 + 0.85 * t
            h = dst.obj * dst.ss * (2.2 + 11.0 * near) * rng.uniform(0.55, 1.15)
            if h < dst.px(2.0):
                continue
            w = h * rng.uniform(0.30, 0.46)
            tone = mix(PAL["forest_dark"], PAL["shadow"], 0.18)
            if rng.random() < 0.35:
                circle(dst, x, y - h * 0.45, h * 0.36, tone)
            else:
                poly(dst, [(x - w, y + 1), (x, y - h), (x + w, y + 1)], tone)
            if h > dst.px(7):
                line(dst, (x + w * 0.2, y - h * 0.72), (x + w * 0.75, y - h * 0.10),
                     mix(PAL["forest_hi"], PAL["pine_hi"], 0.4),
                     max(1, int(dst.px(0.5))), 80)
        # occasional taller emergent tree, so the fringe is not a comb
        if rng.random() < 0.10:
            x = x0 + (x1 - x0) * rng.uniform(0.1, 0.9)
            y = y0 + (y1 - y0) * rng.uniform(0.1, 0.9)
            h = dst.obj * dst.ss * (8.0 + 12.0 * t) * rng.uniform(0.7, 1.1)
            poly(dst, [(x - h * 0.22, y + 1), (x, y - h), (x + h * 0.22, y + 1)],
                 mix(PAL["forest_dark"], PAL["shadow"], 0.10))

    # rock outcrops on the high, forested ridge
    if spec["sunlit"]:
        for _ in range(3):
            i = rng.randrange(1, max(2, n // 2))
            x, y = crest[i]
            w = dst.obj * dst.ss * rng.uniform(10, 26)
            h = w * rng.uniform(0.32, 0.50)
            pts = [(x - w, y + 2), (x - w * 0.45, y - h),
                   (x + w * 0.20, y - h * 0.82), (x + w, y + 2)]
            poly(dst, pts, mix(PAL["rock"], PAL["forest_dark"], 0.35))
            line(dst, (x - w * 0.45, y - h), (x - w * 0.10, y - h * 0.30),
                 mix(PAL["rock_hi"], PAL["accent"], 0.18),
                 max(1, int(dst.px(1.0))), 100)

    for off, tone, alpha in (
            (0.035, mix(top_col, PAL["meadow_hi"], 0.30), 28),
            (0.095, mix(base_col, PAL["shadow"], 0.35), 34),
            (0.175, mix(top_col, PAL["meadow_hi"], 0.18), 22),
            (0.280, mix(base_col, PAL["shadow"], 0.45), 30)):
        pts = [(x, y + off * H) for x, y in crest if y + off * H <= H + 10]
        for i in range(len(pts) - 1):
            line(dst, pts[i], pts[i + 1], tone,
                 max(1, int(dst.px(7.0 + 22.0 * off))), alpha)

    rim_col = (mix(PAL["meadow_hi"], PAL["sky_glow"], 0.42)
               if spec["sunlit"] else
               mix(PAL["meadow_hi"], PAL["haze"], 0.38))
    for i in range(len(crest) - 1):
        line(dst, crest[i], crest[i + 1], rim_col,
             max(1, int(dst.px(1.8))), 150 if spec["sunlit"] else 95)

    # meadow clearings on the sunlit hill
    if spec["sunlit"]:
        for _ in range(3):
            y = rng.uniform(crest[0][1] + 0.06 * H, min(H * 0.82, visible_bottom))
            xb = _crest_x_at(crest, y)
            if xb < W * 0.10:
                continue
            x = rng.uniform(0.03 * W, max(0.04 * W, xb - 0.03 * W))
            rx = rng.uniform(0.035, 0.070) * W
            ry = rx * 0.28
            pts = []
            for k in range(14):
                a = TAU * k / 14
                wob = 1.0 + 0.12 * math.sin(k * 2.3)
                pts.append((x + math.cos(a) * rx * wob,
                            y + math.sin(a) * ry * wob))
            poly(dst, pts, mix(PAL["meadow_hi"], PAL["meadow"], 0.30), 120)

    bottom = min(H, visible_bottom)
    trees = []
    count = int((34 if dst.layout["name"] == "strip" else 58)
                * spec["tree_density"])
    for _ in range(count):
        y = rng.uniform(crest[0][1] + dst.px(3), bottom)
        xb = _crest_x_at(crest, y)
        if side == "left":
            if xb < dst.px(2):
                continue
            x = rng.uniform(-0.02, xb / W - 0.004) * W
            if x > xb - dst.px(2):
                continue
        else:
            if xb > W - dst.px(2):
                continue
            x = rng.uniform(xb / W + 0.004, 1.02) * W
            if x < xb + dst.px(2):
                continue
        if farm_spec is not None:
            fx, fy = farm_spec["x"] * W, farm_spec["y"] * H
            if abs(x - fx) < 0.10 * W and abs(y - fy) < 0.060 * H:
                continue
        d = dst.depth(y)
        h = 92.0 * (d ** 1.42) * dst.obj * spec["tree_scale"] * \
            rng.uniform(0.45, 1.05)
        if h < dst.px(2.0):
            continue
        trees.append((y, x, h))
    for y, x, h in sorted(trees):
        species = "pine" if rng.random() < (0.78 if side == "left" else 0.45) else "round"
        _draw_tree(dst, x, y, h, species, rng)
        if h > dst.px(18) and rng.random() < 0.22:
            _draw_tree(dst, x + rng.uniform(-0.7, 0.7) * h,
                       y + rng.uniform(0.0, 0.20) * h,
                       h * rng.uniform(0.55, 0.80), "pine", rng)

    hero = ([(0.10, 0.660, 0.090), (0.235, 0.720, 0.075)] if side == "left"
            else [(0.865, 0.710, 0.080), (0.805, 0.790, 0.065)])
    for xf, yf, hf in hero:
        _draw_tree(dst, xf * W, yf * H, hf * H, "pine", rng, hero=True)

    if spec.get("ice"):
        _hill_ice(dst, crest, rng)


def _hill_ice(dst: View, crest, rng: random.Random):
    idx = max(1, len(crest) // 6)
    x = sum(p[0] for p in crest[idx:idx + 3]) / 3
    y = sum(p[1] for p in crest[idx:idx + 3]) / 3 + dst.h * 0.012
    rx = dst.w * 0.036
    ry = dst.h * 0.016
    pts = []
    for k in range(18):
        a = TAU * k / 18
        wob = 1.0 + 0.18 * math.sin(k * 2.1) + rng.uniform(-0.08, 0.08)
        pts.append((x + math.cos(a) * rx * wob, y + math.sin(a) * ry * wob))
    poly(dst, pts, mix(PAL["ice"], PAL["tundra_hi"], 0.22), 235)
    poly(dst, [(px, py + ry * 0.12) for px, py in pts],
         mix(PAL["ice_shadow"], PAL["snow_shadow"], 0.40), 90)
    for _ in range(4):
        cx = x + rng.uniform(-0.6, 0.6) * rx
        cy = y + rng.uniform(-0.3, 0.3) * ry
        line(dst, (cx - rx * 0.12, cy), (cx + rx * 0.18, cy + ry * 0.25),
             mix(PAL["ice_shadow"], PAL["haze"], 0.25),
             max(1, int(dst.px(1.0))), 90)
    pts = catmull([(x + rx * 0.30, y + ry * 0.60),
                   (x + rx * 0.55, y + dst.h * 0.045),
                   (x + rx * 0.20, y + dst.h * 0.080),
                   (x + rx * 0.65, y + dst.h * 0.110)], samples=7)
    for i in range(len(pts) - 1):
        line(dst, pts[i], pts[i + 1], mix(PAL["water_light"], PAL["foam"], 0.3),
             max(1, int(dst.px(0.9))), 170)


# ---------------------------------------------------------------------------
# trees and foreground
# ---------------------------------------------------------------------------

def _draw_tree(dst: View, x, base, h, species, rng, hero=False):
    if h <= 0.8:
        return
    d = dst.depth(base)
    ellipse(dst, x + h * 0.05, base + h * 0.01, h * 0.30,
            max(0.6, h * 0.075), PAL["shadow"], int(24 + 34 * d))

    if species == "round":
        trunk_h = h * 0.40
        line(dst, (x, base), (x, base - trunk_h),
             mix(PAL["trunk"], PAL["forest_dark"], 0.35),
             max(1, int(h * 0.045)))
        tone = mix(PAL["forest"], PAL["forest_dark"], 0.30)
        if hero:
            tone = mix(tone, PAL["forest_hi"], 0.12)
        rad = h * 0.30
        for dx, dy, rr in ((-0.42, -0.70, 0.52), (0.34, -0.80, 0.48),
                           (-0.05, -1.02, 0.44), (0.06, -0.48, 0.48),
                           (-0.48, -0.42, 0.34), (0.52, -0.38, 0.30)):
            circle(dst, x + dx * rad, base - trunk_h + dy * rad,
                   rr * rad, mix(tone, PAL["forest_dark"], 0.16),
                   int(150 + 70 * min(1.0, d)))
        for dx, dy, rr in ((-0.30, -0.86, 0.34), (0.16, -1.06, 0.30),
                           (0.34, -0.66, 0.26), (-0.08, -0.56, 0.28)):
            circle(dst, x + dx * rad, base - trunk_h + dy * rad,
                   rr * rad, tone, int(170 + 60 * min(1.0, d)))
        if d > 0.3:
            circle(dst, x + rad * 0.38, base - trunk_h - rad * 0.78,
                   rad * 0.22, mix(tone, PAL["meadow_hi"], 0.42), 180)
        return

    trunk_col = mix(PAL["trunk"], PAL["forest_dark"], 0.30)
    line(dst, (x, base), (x, base - h * 0.34), trunk_col,
         max(1, int(h * 0.040)))
    tone = mix(PAL["pine"], PAL["forest_dark"], 0.22)
    if hero:
        tone = mix(tone, PAL["pine_mid"], 0.22)
    tiers = 4 if h < dst.px(18) else 5 if h < dst.px(42) else 6
    for i in range(tiers):
        frac = i / tiers
        t_base = base - h * (0.10 + 0.76 * frac)
        t_top = base - h * (0.44 + 0.78 * frac)
        half = h * 0.27 * (1.0 - 0.62 * frac)
        droop = h * 0.030 * (1.0 - 0.35 * frac)
        pts = [(x - half, t_base), (x, t_top), (x + half, t_base)]
        for k in range(3):
            t = (k + 1) / 4
            pts.append((x + half - 2 * half * t,
                        t_base + droop * math.sin(math.pi * t)))
        c = mix(tone, PAL["pine_hi"], 0.05 + 0.18 * frac)
        poly(dst, pts, c, int(150 + 75 * min(1.0, d)))
        poly(dst, [(x - half * 0.92, t_base - h * 0.008),
                   (x + half * 0.92, t_base - h * 0.008),
                   (x + half * 0.45, t_base + h * 0.030),
                   (x, t_base + h * 0.042),
                   (x - half * 0.45, t_base + h * 0.030)],
             mix(c, PAL["pine_dark"], 0.42), int(80 + 70 * min(1.0, d)))
        if d > 0.22 and h > dst.px(11):
            line(dst, (x + half * 0.20, t_top + h * 0.10),
                 (x + half * 0.78, t_base - h * 0.01),
                 mix(c, PAL["pine_hi"], 0.55),
                 max(1, int(dst.px(0.55) + d * dst.px(0.5))), 105)


def _draw_hero_pine(dst: View, x, base, h, scale, rng):
    trunk_col = PAL["trunk"]
    line(dst, (x, base), (x, base - h * 0.30), trunk_col,
         max(1, int(dst.px(2.6) * scale)))
    line(dst, (x, base), (x + h * 0.04, base + h * 0.01),
         PAL["trunk"], max(1, int(dst.px(3.0) * scale)))
    tone = mix(PAL["pine_dark"], PAL["pine"], 0.42)
    tiers = 7
    for i in range(tiers):
        frac = i / tiers
        t_base = base - h * (0.08 + 0.74 * frac)
        t_top = base - h * (0.46 + 0.72 * frac)
        half = h * 0.30 * (1.0 - 0.60 * frac) * scale
        droop = h * 0.035 * (1.0 - 0.4 * frac)
        pts = [(x - half, t_base), (x, t_top), (x + half, t_base)]
        for k in range(4):
            t = (k + 1) / 5
            pts.append((x + half - 2 * half * t,
                        t_base + droop * math.sin(math.pi * t)))
        c = mix(tone, PAL["pine_hi"], 0.05 + 0.18 * frac)
        poly(dst, pts, c)
        poly(dst, [(x - half * 0.92, t_base - h * 0.008),
                   (x + half * 0.92, t_base - h * 0.008),
                   (x + half * 0.46, t_base + h * 0.028),
                   (x, t_base + h * 0.040),
                   (x - half * 0.46, t_base + h * 0.028)],
             mix(c, PAL["pine_dark"], 0.45))
        line(dst, (x + half * 0.22, t_top + h * 0.095),
             (x + half * 0.82, t_base - h * 0.008),
             mix(PAL["pine_hi"], PAL["accent"], 0.55),
             max(1, int(dst.px(0.9) * scale)), 185)
    for i in range(3):
        yy = base - h * (0.18 + 0.15 * i)
        line(dst, (x, yy), (x + h * 0.085, yy - h * 0.028),
             trunk_col, max(1, int(dst.px(1.4) * scale)), 170)
    ellipse(dst, x + h * 0.12, base + h * 0.005, h * 0.34, h * 0.055,
            PAL["shadow"], 100)


def _draw_boulder(dst: View, x, base, w, scale, rng):
    h = w * 0.55 * scale
    ellipse(dst, x + w * 0.10, base + h * 0.02, w * 0.48, h * 0.13,
            PAL["shadow"], 80)
    pts = []
    for k in range(9):
        a = math.pi + math.pi * k / 8
        r = 1.0 + rng.uniform(-0.10, 0.05)
        pts.append((x + math.cos(a) * w * 0.5 * r,
                    base + math.sin(a) * h * r))
    poly(dst, pts, mix(PAL["rock"], PAL["forest_dark"], 0.35))
    hi = [(x - w * 0.22, base - h * 0.52), (x + w * 0.08, base - h * 0.62),
          (x + w * 0.28, base - h * 0.38), (x - w * 0.02, base - h * 0.28)]
    poly(dst, hi, mix(PAL["rock_hi"], PAL["accent"], 0.12), 120)
    line(dst, (x - w * 0.36, base - h * 0.08),
         (x + w * 0.30, base - h * 0.14), PAL["rock_dark"],
         max(1, int(dst.px(1.0) * scale)), 90)


def _ledge_y(dst: View, xf: float) -> float:
    pts = dst.layout["ledge"]["top"]
    if xf <= pts[0][0]:
        return pts[0][1] * dst.h
    if xf >= pts[-1][0]:
        return pts[-1][1] * dst.h
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if a[0] <= xf <= b[0]:
            t = (xf - a[0]) / max(1e-6, b[0] - a[0])
            t = t * t * (3 - 2 * t)
            return (a[1] + (b[1] - a[1]) * t) * dst.h
    return pts[-1][1] * dst.h


def draw_foreground(dst: View, rng: random.Random):
    """The summit itself: a dark rock shelf, a grass lip, pines and a path."""
    W, H = dst.w, dst.h
    ledge = dst.layout["ledge"]
    edge = []
    xf = -0.01
    while xf <= 1.011:
        n = (math.sin(xf * 51.0) * 0.0028 + math.sin(xf * 17.0 + 1.2) * 0.0036)
        edge.append((xf * W, _ledge_y(dst, xf) + n * H))
        xf += 0.008

    # the cliff face below the lip
    poly(dst, edge + [(W, H), (0, H)],
         mix(PAL["rock_dark"], PAL["shadow"], 0.55))
    top_band = [(x, y + dst.px(9)) for x, y in edge] + [(0, H), (W, H)]
    poly(dst, top_band, mix(PAL["rock_dark"], PAL["valley_near"], 0.35), 190)

    # strata following the lip
    for k, off in enumerate((0.012, 0.032, 0.060, 0.096, 0.142, 0.200)):
        pts = [(x, y + off * H) for x, y in edge if y + off * H <= H]
        for i in range(len(pts) - 1):
            tone = (mix(PAL["rock"], PAL["rock_hi"], 0.25) if k % 2 == 0
                    else mix(PAL["rock_dark"], PAL["shadow"], 0.30))
            line(dst, pts[i], pts[i + 1], tone,
                 max(1, int(dst.px(1.2 + 1.8 * off * 10))), 55)

    # vertical cracks
    for _ in range(12):
        xf = rng.uniform(0.02, 0.98)
        x = xf * W
        y0 = _ledge_y(dst, xf) + rng.uniform(6, 22) * dst.obj * dst.ss * 0.5
        y1 = min(H, y0 + rng.uniform(0.05, 0.16) * H)
        line(dst, (x, y0), (x + rng.uniform(-3, 3) * dst.px(1.0), y1),
             mix(PAL["shadow"], PAL["rock_dark"], 0.25),
             max(1, int(dst.px(1.0))), 50)

    # the grass lip: a bright edge and a dark shadow below it
    for i in range(len(edge) - 1):
        p0, p1 = edge[i], edge[i + 1]
        line(dst, (p0[0], p0[1] + dst.px(4.0)),
             (p1[0], p1[1] + dst.px(4.0)),
             mix(PAL["shadow"], PAL["pine_dark"], 0.30),
             max(1, int(dst.px(4.0))), 110)
        line(dst, p0, p1, mix(PAL["meadow_hi"], PAL["pine_hi"], 0.22),
             max(1, int(dst.px(2.0))), 210)
        line(dst, (p0[0], p0[1] - dst.px(1.2)),
             (p1[0], p1[1] - dst.px(1.2)),
             mix(PAL["meadow_hi"], PAL["sky_glow"], 0.30),
             max(1, int(dst.px(0.8))), 140)

    # path along the rim, leading toward the overlook
    path = catmull([(xf * W, yf * H) for xf, yf in ledge["path"]], samples=8)
    for i in range(len(path) - 1):
        line(dst, path[i], path[i + 1],
             mix(PAL["sand"], PAL["meadow"], 0.30),
             max(1, int(dst.px(2.6))), 105)
        line(dst, (path[i][0], path[i][1] + dst.px(1.2)),
             (path[i + 1][0], path[i + 1][1] + dst.px(1.2)),
             mix(PAL["rock_hi"], PAL["sand"], 0.35),
             max(1, int(dst.px(0.9))), 75)

    # grass tufts and flowers on the lip
    for _ in range(int(130 * (0.7 + 0.4 * dst.obj))):
        xf = rng.uniform(0.0, 1.0)
        x = xf * W
        y = _ledge_y(dst, xf) + rng.uniform(-1.0, 7.0) * dst.obj * dst.ss * 0.4
        tuft = rng.uniform(2.2, 7.0) * dst.obj * dst.ss * 0.55
        col = mix(PAL["pine_hi"], PAL["meadow_hi"], rng.uniform(0.0, 0.6))
        for k in range(rng.randint(2, 4)):
            xx = x + (k - 1.5) * tuft * 0.22
            line(dst, (xx, y), (xx + (k - 1.5) * tuft * 0.12, y - tuft),
                 col, max(1, int(dst.px(0.55))), 170)
        if rng.random() < 0.15:
            circle(dst, x + tuft * 0.2, y - tuft * 0.75,
                   max(1, tuft * 0.13),
                   rng.choice((PAL["city"], PAL["accent"], PAL["foam"])), 210)

    # mossy / rocky patches on the lip
    for _ in range(9):
        xf = rng.uniform(0.0, 1.0)
        x, y = xf * W, _ledge_y(dst, xf) + rng.uniform(8, 26) * dst.obj * dst.ss * 0.5
        ellipse(dst, x, y, rng.uniform(18, 58) * dst.obj * dst.ss * 0.5,
                rng.uniform(4, 12) * dst.obj * dst.ss * 0.5,
                mix(PAL["rock"], PAL["valley_near"], rng.uniform(0.2, 0.7)), 65)

    # a few bushes on the rim
    for _ in range(4):
        xf = rng.uniform(0.02, 0.98)
        x = xf * W
        y = _ledge_y(dst, xf) + rng.uniform(1, 4) * dst.px(1.0)
        _draw_tree(dst, x, y, rng.uniform(9, 18) * dst.obj * dst.ss * 0.5,
                   "round", rng)

    # cairn at the overlook
    cx, cy = ledge["cairn"][0] * W, ledge["cairn"][1] * H
    stone_h = dst.obj * dst.ss * 2.4
    for k in range(4):
        w = stone_h * (2.4 - k * 0.35)
        h = stone_h * (1.5 - k * 0.18)
        ellipse(dst, cx + rng.uniform(-1, 1), cy - k * h * 0.72 + h * 0.5,
                w, h * 0.55, mix(PAL["rock"], PAL["rock_dark"], 0.25))
        ellipse(dst, cx - w * 0.15, cy - k * h * 0.72 + h * 0.25,
                w * 0.55, h * 0.28, mix(PAL["rock_hi"], PAL["accent"], 0.10), 110)
    line(dst, (cx - stone_h * 0.6, cy + stone_h * 0.6),
         (cx + stone_h * 0.6, cy + stone_h * 0.6),
         mix(PAL["rock_dark"], PAL["shadow"], 0.4),
         max(1, int(dst.px(1.2))), 80)

    # pines stand on the rim, not halfway down the slope
    for xf, base, hf, scale in ledge["pines"]:
        rim = _ledge_y(dst, xf) + 0.018 * H
        _draw_hero_pine(dst, xf * W, rim, hf * H * 0.72, scale, rng)
    for xf, base, wf, scale in ledge["rocks"]:
        _draw_boulder(dst, xf * W, base * H, wf * W, scale, rng)
    _draw_hero_pine(dst, 0.902 * W, _ledge_y(dst, 0.902) + 0.016 * H,
                    0.155 * H, 0.78, rng)
    _draw_hero_pine(dst, 0.952 * W, _ledge_y(dst, 0.952) + 0.012 * H,
                    0.105 * H, 0.66, rng)
    _draw_hero_pine(dst, 0.982 * W, _ledge_y(dst, 0.982) + 0.010 * H,
                    0.072 * H, 0.58, rng)

# ---------------------------------------------------------------------------
# atmosphere and finish
# ---------------------------------------------------------------------------

def draw_atmosphere(dst: View, rng: random.Random):
    W, H = dst.w, dst.h
    for off, wf, hf, a in ((0.030, 0.70, 0.030, 46),
                           (0.095, 0.56, 0.026, 34),
                           (0.165, 0.42, 0.022, 22)):
        yf = dst.layout["coastline"] + off
        blit_soft(dst, W * (0.47 + 0.05 * math.sin(yf * 30)),
                  H * yf, W * wf, H * hf, PAL["haze"], a, 2.0)

    for xf, yf, wf, hf, a in ((0.560, 0.470, 0.34, 0.055, 22),
                              (0.400, 0.605, 0.28, 0.045, 18),
                              (0.690, 0.560, 0.24, 0.040, 16)):
        blit_soft(dst, xf * W, yf * H, wf * W, hf * H, PAL["shadow"], a, 2.0)

    sun_x, _, _ = dst.layout["sun"]
    blit_soft(dst, sun_x * W, H * 0.38, W * 0.55, H * 0.40,
              PAL["sky_glow"], 22, 2.0)

    band = pygame.Surface((W, int(H * 0.13)), pygame.SRCALPHA)
    for row in range(band.get_height()):
        t = row / max(1, band.get_height() - 1)
        pygame.draw.line(band, rgba(PAL["shadow"], int(70 * t ** 1.3)),
                         (0, row), (W, row))
    dst.blit(band, (0, H - band.get_height()))


def add_bloom(surface, strength=12):
    small = pygame.transform.smoothscale(
        surface, (max(2, surface.get_width() // 4),
                  max(2, surface.get_height() // 4)))
    blur = pygame.transform.smoothscale(small, surface.get_size())
    blur.set_alpha(strength)
    dimmed = pygame.Surface(surface.get_size())
    dimmed.fill((0, 0, 0))
    dimmed.blit(blur, (0, 0))
    surface.blit(dimmed, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def add_vignette(surface, strength=58):
    W, H = surface.get_size()
    sw, sh = 72, max(12, int(72 * H / W))
    mask = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for y in range(sh):
        ny = (y / (sh - 1) - 0.5) * 2
        for x in range(sw):
            nx = (x / (sw - 1) - 0.5) * 2
            d = math.sqrt(nx * nx * 0.92 + ny * ny * 0.78)
            v = max(0.0, (d - 0.58) / 0.85)
            a = int(strength * (v ** 1.8))
            if a:
                mask.set_at((x, y), (0, 0, 0, min(255, a)))
    surface.blit(pygame.transform.smoothscale(mask, (W, H)), (0, 0))


def add_grain(surface, rng, amount=0.005, alpha=8):
    W, H = surface.get_size()
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(int(W * H * amount)):
        x, y = rng.randrange(W), rng.randrange(H)
        v = rng.randint(90, 210)
        layer.set_at((x, y), (v, v, v, alpha))
    surface.blit(layer, (0, 0))


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------

_FONTS: dict[tuple, pygame.font.Font] = {}


def font(path: str, size: int) -> pygame.font.Font:
    key = (path, size)
    f = _FONTS.get(key)
    if f is None:
        f = pygame.font.Font(path, size)
        _FONTS[key] = f
    return f


def tracked_width(text: str, f: pygame.font.Font, tracking: float) -> int:
    return sum(f.size(ch)[0] for ch in text) + tracking * max(0, len(text) - 1)


def draw_tracked(surface, text, f, color, pos, tracking=0.0, alpha=255,
                 align="left"):
    total = tracked_width(text, f, tracking)
    x = pos[0]
    if align == "right":
        x -= total
    elif align == "center":
        x -= total / 2
    y = pos[1]
    for ch in text:
        glyph = f.render(ch, True, color)
        if alpha < 255:
            glyph.set_alpha(alpha)
        surface.blit(glyph, (int(x), int(y)))
        x += f.size(ch)[0] + tracking
    return total


STAGES = [("ICE", 0.00), ("WATER", 0.25), ("ALGAE", 0.50),
          ("FOREST", 0.75), ("CITIES", 1.00)]


def draw_hud(surface, layout, progress=0.80, stage=4, year=96, total_years=120):
    W, H = surface.get_size()
    ink, dim, faint = PAL["ink"], PAL["ink_dim"], PAL["ink_faint"]
    accent = PAL["accent"]

    title_f = font(MONO_BOLD, layout["title_size"])
    eyebrow_f = font(MONO, layout["eyebrow_size"])
    sub_f = font(MONO, max(7, layout["eyebrow_size"]))
    tele_f = font(MONO_BOLD, layout["tele_size"])
    tele_small = font(MONO, max(7, layout["tele_size"] - 1))
    stage_f = font(MONO_BOLD, max(7, layout["year_size"]))
    year_f = font(MONO, layout["year_size"])

    draw_tracked(surface, "SLOW WORLDS · SCIENCE FICTION", eyebrow_f, accent,
                 (layout["title_x"], layout["eyebrow_y"]),
                 tracking=layout["eyebrow_size"] * 0.20, alpha=185)
    title_w = draw_tracked(surface, "TERRAFORM", title_f, ink,
                           (layout["title_x"], layout["title_y"]),
                           tracking=layout["title_tracking"], alpha=246)
    rule_y = int(layout["title_y"] + layout["title_size"] * 1.20)
    pygame.draw.line(surface, mix(accent, PAL["sky_top"], 0.55),
                     (layout["title_x"], rule_y),
                     (layout["title_x"] + int(title_w * 0.74), rule_y), 1)
    pygame.draw.line(surface, mix(dim, PAL["sky_top"], 0.65),
                     (layout["title_x"], rule_y + 4),
                     (layout["title_x"] + int(title_w * 0.32), rule_y + 4), 1)
    draw_tracked(surface, "A WORLD IN PROGRESS · SITE 07", sub_f, dim,
                 (layout["title_x"], layout["subtitle_y"]),
                 tracking=layout["eyebrow_size"] * 0.12, alpha=175)

    tx, ty = layout["tele_x"], layout["tele_y"]
    ts = layout["tele_size"]
    lines = [
        (f"STAGE {stage:02d} / {STAGES[stage][0]}", tele_f, ink, 205),
        (f"YEAR {year:03d} / {total_years:03d}", tele_small, dim, 185),
        ("MEAN SURFACE +12.4 °C", tele_small, faint, 145),
        ("ALT 2,140 M · N 072°", tele_small, faint, 130),
    ]
    for i, (txt, f, col, a) in enumerate(lines):
        draw_tracked(surface, txt, f, col, (tx, ty + i * int(ts * 1.55)),
                     tracking=ts * 0.10, alpha=a, align="right")

    x0, x1 = layout["timeline_x0"], layout["timeline_x1"]
    y = layout["timeline_y"]
    label_y = layout["timeline_label_y"]
    track = mix(dim, PAL["sky_low"], 0.62)
    pygame.draw.line(surface, track, (x0, y), (x1, y), 1)
    progress_x = x0 + (x1 - x0) * progress
    pygame.draw.line(surface, mix(accent, PAL["sky_low"], 0.35),
                     (x0, y), (int(progress_x), y), 2)
    for i, (nm, _) in enumerate(STAGES):
        tick_x = x0 + (x1 - x0) * i / (len(STAGES) - 1)
        active = i == stage
        passed = i <= stage
        pygame.draw.line(surface, (ink if active else track),
                         (int(tick_x), y - 3), (int(tick_x), y + 3),
                         1 if not active else 2)
        draw_tracked(surface, nm, stage_f,
                     ink if active else (dim if passed else faint),
                     (tick_x, label_y),
                     tracking=stage_f.get_height() * 0.10,
                     alpha=215 if active else 120, align="center")
    pygame.draw.polygon(surface, accent, [
        (int(progress_x), int(y - 4)), (int(progress_x + 4), int(y)),
        (int(progress_x), int(y + 4)), (int(progress_x - 4), int(y))])
    line(surface, (progress_x, y - 8), (progress_x, y - 13),
         mix(accent, PAL["sky_low"], 0.2), 1, 170)
    draw_tracked(surface, "YEAR 000", year_f, faint,
                 (x0 - 14, y - 5), tracking=1.2, alpha=155, align="right")
    draw_tracked(surface, "YEAR 120", year_f, faint,
                 (x1 + 14, y - 5), tracking=1.2, alpha=155, align="left")


# ---------------------------------------------------------------------------
# scene assembly
# ---------------------------------------------------------------------------

def render(layout_name: str, palette_name: str = "biosphere",
           seed: int = 5151) -> pygame.Surface:
    global PAL
    PAL = PALETTES[palette_name]
    layout = LAYOUTS[layout_name]
    view = View(layout)
    scene = pygame.Surface((view.w, view.h))
    view.surface = scene
    scene.fill(PAL["sky_top"])

    draw_sky(view, random.Random(seed + 1))
    draw_mountains(view)
    draw_sea(view, random.Random(seed + 5))
    draw_valley_floor(view, random.Random(seed + 7))
    draw_fields(view, random.Random(seed + 9))
    draw_forest_patches(view, random.Random(seed + 10))
    draw_pond(view, random.Random(seed + 10))
    draw_roads(view, random.Random(seed + 10))
    draw_river(view, random.Random(seed + 11))
    draw_valley_rows(view, random.Random(seed + 12))
    draw_delta_city(view, random.Random(seed + 13))
    draw_town(view, random.Random(seed + 15))
    draw_valley_mist(view, random.Random(seed + 16))

    left = layout["left_hill"]
    right = layout["right_hill"]
    draw_hill(view, left, left["crest"], random.Random(seed + 17),
              side="left", visible_bottom=view.h * 0.84)
    draw_hill(view, right, right["crest"], random.Random(seed + 19),
              side="right", visible_bottom=view.h * 0.86,
              farm_spec=layout["farm"])
    draw_farm(view, random.Random(seed + 21))

    draw_atmosphere(view, random.Random(seed + 23))
    draw_foreground(view, random.Random(seed + 25))

    native = pygame.transform.smoothscale(scene, (view.W, view.H))
    add_bloom(native, 10 if layout_name == "strip" else 12)
    add_vignette(native, 54 if layout_name == "strip" else 64)
    add_grain(native, random.Random(seed + 71), 0.005, 8)
    draw_hud(native, layout)
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("strip", "portrait", "all"),
                        default="all")
    parser.add_argument("--seed", type=int, default=5151)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((64, 64))

    def save(surface, name):
        path = os.path.join(OUT_DIR, name)
        pygame.image.save(surface, path)
        print(f"{name}: {surface.get_width()}x{surface.get_height()}")

    if args.only in ("all", "strip"):
        save(render("strip", seed=args.seed), "terraform_1280x400.png")
    if args.only in ("all", "portrait"):
        save(render("portrait", seed=args.seed), "terraform_1080x1920.png")

    pygame.quit()


if __name__ == "__main__":
    main()
