"""Leviathan Passage — Slow Worlds §5.14.

A pod of sea-serpents crosses a dusk horizon.  Each animal is a serpentine
tube on a sampled spine: a blunt head, a submerged neck, two broad humps and a
whip tail.  The submerged sections are clipped at the waterline, so the pod
reads as arches with water between them.  The sea, mist, stars and a small
boat do the scale work; every few minutes the largest hump crosses the low
moon and leaves a thin corona.

The sky is alive between pod crossings: a seeded star field with a handful of
bright anchors that twinkle, and a single occasional meteor.  The stills in
designs/leviathan_proto/ are the art reference; this file is the mode.

Composition is chosen by aspect class, not stretched from one frame:

  * 1280x400 strip  - horizon at 60 %, pod across the width, moon/boat in the
    gap, title top-left;
  * 1080x1920 portrait - horizon at 70 %, two-line title, tall sky, long moon
    path;
  * 1920x1080 landscape and 720x720 square get their own presets.

Static layers (sky, base stars, sea base, mist, moon sprite, boat, finish, HUD)
are cached; only the pod, reflections, spouts, live sea, beacon twinkle, meteor,
moon arc and bloom are drawn per frame.  No disk I/O, network, audio or thread.
The lower-left 80x32 px stays dark for the controller's mode number.

Config: title, subtitle, palette (dusk/bone/ember), seed, quality, hud,
orientation, pod_size, crossing_seconds, mist, moon, moon_arc_seconds,
scale_reference, show_reflections, show_spouts, eclipse_seconds, swell_speed,
star_density, meteor, meteor_seconds, meteor_duration, glow_strength,
scanline_alpha, vignette_strength.
"""
from __future__ import annotations

import math
import random

import pygame
import pygame.gfxdraw

TAU = math.tau

ORIENTATIONS = ("auto", "ultrawide", "landscape", "portrait", "square")
QUALITY_NAMES = ("auto", "low", "medium", "high")
HUD_MODES = ("none", "minimal", "full")
SCALE_REFERENCES = ("boat", "lighthouse", "none")
MAX_POD = 5
A_HUMP = 0.775          # local x of the tallest hump along the spine
POD_CYCLE_START = 1.08  # A's head x at cycle t=0, in frame widths
DEFAULT_TITLE = "LEVIATHAN PASSAGE"

PALETTES = {
    "dusk": {
        "label": "DUSK",
        "note": "Moon & Moss · the design default",
        "sky_top": (4, 9, 12),
        "sky_high": (9, 20, 25),
        "sky_mid": (20, 36, 40),
        "sky_low": (50, 55, 48),
        "sky_warm": (74, 62, 48),
        "horizon": (150, 108, 72),
        "horizon_hot": (186, 134, 86),
        "sea_top": (62, 55, 44),
        "sea_mid": (24, 33, 30),
        "sea_bottom": (5, 9, 9),
        "swell_far": (140, 120, 90),
        "swell_near": (40, 58, 52),
        "moon": (238, 228, 200),
        "moon_edge": (190, 178, 150),
        "moon_dark": (140, 130, 108),
        "moon_glow": (214, 172, 114),
        "star": (196, 210, 204),
        "star_dim": (128, 148, 146),
        "cloud": (86, 86, 78),
        "body": (4, 8, 7),
        "body_hi": (10, 17, 14),
        "body_low": (2, 4, 4),
        "rim": (148, 148, 112),
        "rim_hot": (206, 162, 108),
        "rib": (48, 56, 44),
        "mist": (166, 172, 156),
        "mist_hot": (212, 182, 140),
        "wake": (108, 112, 90),
        "boat": (5, 8, 7),
        "sail": (196, 180, 144),
        "lantern": (255, 198, 122),
        "ink": (224, 230, 212),
        "ink_dim": (150, 160, 142),
        "ink_faint": (92, 104, 92),
        "accent": (217, 160, 91),
        "corona": (232, 194, 138),
    },
    "bone": {
        "label": "BONE",
        "note": "cold moonlight · a silver print with no green",
        "sky_top": (8, 9, 13),
        "sky_high": (13, 15, 21),
        "sky_mid": (26, 29, 36),
        "sky_low": (50, 52, 56),
        "sky_warm": (104, 101, 94),
        "horizon": (166, 158, 142),
        "horizon_hot": (196, 188, 168),
        "sea_top": (58, 58, 57),
        "sea_mid": (24, 27, 29),
        "sea_bottom": (6, 8, 10),
        "swell_far": (150, 146, 130),
        "swell_near": (52, 58, 60),
        "moon": (246, 244, 232),
        "moon_edge": (204, 203, 188),
        "moon_dark": (150, 151, 142),
        "moon_glow": (188, 184, 166),
        "star": (210, 214, 218),
        "star_dim": (140, 146, 154),
        "cloud": (94, 94, 92),
        "body": (5, 7, 8),
        "body_hi": (12, 14, 16),
        "body_low": (2, 3, 4),
        "rim": (164, 162, 146),
        "rim_hot": (208, 202, 180),
        "rib": (48, 50, 48),
        "mist": (156, 158, 152),
        "mist_hot": (186, 182, 166),
        "wake": (116, 116, 108),
        "boat": (5, 7, 8),
        "sail": (182, 178, 162),
        "lantern": (240, 226, 190),
        "ink": (226, 228, 222),
        "ink_dim": (154, 158, 156),
        "ink_faint": (94, 98, 98),
        "accent": (196, 190, 168),
        "corona": (224, 220, 204),
    },
    "ember": {
        "label": "EMBER",
        "note": "a volcanic afterglow · rust and copper",
        "sky_top": (10, 4, 6),
        "sky_high": (18, 7, 9),
        "sky_mid": (38, 13, 13),
        "sky_low": (72, 27, 20),
        "sky_warm": (112, 45, 26),
        "horizon": (162, 66, 34),
        "horizon_hot": (206, 104, 50),
        "sea_top": (54, 32, 24),
        "sea_mid": (22, 15, 13),
        "sea_bottom": (6, 5, 5),
        "swell_far": (140, 76, 42),
        "swell_near": (62, 38, 28),
        "moon": (246, 206, 158),
        "moon_edge": (204, 152, 104),
        "moon_dark": (148, 98, 62),
        "moon_glow": (230, 118, 56),
        "star": (222, 190, 168),
        "star_dim": (150, 112, 96),
        "cloud": (84, 44, 36),
        "body": (7, 5, 5),
        "body_hi": (18, 9, 8),
        "body_low": (3, 2, 2),
        "rim": (186, 104, 62),
        "rim_hot": (232, 146, 80),
        "rib": (62, 28, 20),
        "mist": (150, 100, 78),
        "mist_hot": (218, 124, 70),
        "wake": (116, 70, 42),
        "boat": (7, 5, 5),
        "sail": (188, 138, 94),
        "lantern": (255, 176, 96),
        "ink": (240, 218, 194),
        "ink_dim": (176, 132, 108),
        "ink_faint": (112, 78, 64),
        "accent": (226, 132, 68),
        "corona": (240, 160, 96),
    },
}


# ---------------------------------------------------------------------------
# Layout presets.  Every spatial value is in the preset's base pixels; the
# mode scales x by width/base_w, y by height/base_h, and object sizes by the
# smaller of the two.  Pod entries are (offset from A, length frac of W,
# peak frac of H, phase, variant).
# ---------------------------------------------------------------------------

LAYOUTS = {
    "ultrawide": {
        "base": (1280, 400),
        "horizon": 0.600,
        "moon": {"x": 0.552, "r": 20.0, "above": 50.0},
        "boat": {"x": 0.515, "w": 25.0, "mast": 30.0},
        "meteor": {"start": (0.530, 0.220), "end": (0.680, 0.400),
                   "length": 0.110},
        "pod": (
            (0.040, 0.360, 0.235, 0.11, 0),
            (0.410, 0.100, 0.060, 0.53, 2),
            (0.595, 0.380, 0.170, 0.79, 1),
        ),
        "stars": 460, "beacons": 7,
        "title_size": 29, "title_tracking": 1.6,
        "eyebrow_size": 10, "telemetry_size": 11,
        "title_xy": (42, 46), "eyebrow_xy": (43, 26),
        "telemetry_xy": (1238, 30), "two_line": False,
    },
    "portrait": {
        "base": (1080, 1920),
        "horizon": 0.700,
        "moon": {"x": 0.755, "r": 27.0, "above": 48.0},
        "boat": {"x": 0.715, "w": 28.0, "mast": 40.0},
        "meteor": {"start": (0.470, 0.250), "end": (0.620, 0.400),
                   "length": 0.140},
        "pod": (
            (0.035, 0.520, 0.115, 0.21, 0),
            (0.600, 0.085, 0.035, 0.61, 2),
            (0.800, 0.280, 0.070, 0.87, 1),
        ),
        "stars": 950, "beacons": 16,
        "title_size": 84, "title_tracking": 3.0,
        "eyebrow_size": 15, "telemetry_size": 16,
        "title_xy": (72, 152), "eyebrow_xy": (74, 120),
        "telemetry_xy": (1008, 134), "two_line": True,
    },
    "landscape": {
        "base": (1920, 1080),
        "horizon": 0.640,
        "moon": {"x": 0.552, "r": 26.0, "above": 150.0},
        "boat": {"x": 0.515, "w": 34.0, "mast": 42.0},
        "meteor": {"start": (0.530, 0.200), "end": (0.680, 0.360),
                   "length": 0.100},
        "pod": (
            (0.030, 0.360, 0.200, 0.11, 0),
            (0.405, 0.090, 0.055, 0.53, 2),
            (0.590, 0.380, 0.145, 0.79, 1),
        ),
        "stars": 900, "beacons": 12,
        "title_size": 40, "title_tracking": 2.0,
        "eyebrow_size": 13, "telemetry_size": 14,
        "title_xy": (54, 58), "eyebrow_xy": (54, 34),
        "telemetry_xy": (1866, 42), "two_line": False,
    },
    "square": {
        "base": (720, 720),
        "horizon": 0.700,
        "moon": {"x": 0.550, "r": 20.0, "above": 69.0},
        "boat": {"x": 0.515, "w": 24.0, "mast": 30.0},
        "meteor": {"start": (0.520, 0.220), "end": (0.670, 0.400),
                   "length": 0.120},
        "pod": (
            (0.030, 0.400, 0.160, 0.11, 0),
            (0.440, 0.100, 0.050, 0.53, 2),
            (0.600, 0.360, 0.120, 0.79, 1),
        ),
        "stars": 500, "beacons": 8,
        "title_size": 30, "title_tracking": 1.6,
        "eyebrow_size": 10, "telemetry_size": 11,
        "title_xy": (32, 38), "eyebrow_xy": (32, 22),
        "telemetry_xy": (688, 26), "two_line": False,
    },
}

POD_EXTRAS = (
    (0.780, 0.34, 0.34, 0.33, 2),
    (0.930, 0.30, 0.30, 0.67, 1),
)


def aspect_class(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
    if aspect >= 1.2:
        return "landscape"
    if aspect <= 0.85:
        return "portrait"
    return "square"


# ---------------------------------------------------------------------------
# Colour, gradient and soft-sprite helpers
# ---------------------------------------------------------------------------

def clamp8(value) -> int:
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def mix(a, b, t: float):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def interp(points, x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if x0 <= x <= x1 and x1 > x0:
            t = (x - x0) / (x1 - x0)
            return y0 + (y1 - y0) * t
    return points[-1][1]


_SOFT_CACHE: dict = {}
_SOFT_SCALED: dict = {}


def _soft_master(color, alpha, power):
    key = (color, int(alpha), round(float(power), 2))
    surf = _SOFT_CACHE.get(key)
    if surf is not None:
        return surf
    radius = 96
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        falloff = (1.0 - r / radius) ** power
        a = clamp8(alpha * falloff)
        pygame.draw.circle(surf, (*color, a), (radius, radius), r)
    _SOFT_CACHE[key] = surf
    return surf


def blit_soft(dest, cx: float, cy: float, w: float, h: float,
              color, alpha: int, power: float = 2.0) -> None:
    w = max(2, int(w))
    h = max(2, int(h))
    key = (color, int(alpha), round(float(power), 2), w, h)
    sprite = _SOFT_SCALED.get(key)
    if sprite is None:
        master = _soft_master(color, int(alpha), power)
        sprite = (master if (w, h) == (192, 192)
                  else pygame.transform.smoothscale(master, (w, h)))
        _SOFT_SCALED[key] = sprite
    dest.blit(sprite, (int(cx - w / 2), int(cy - h / 2)))


def vgrad(w: int, h: int, stops, srcalpha: bool = False):
    surf = pygame.Surface((max(1, w), max(1, h)),
                          pygame.SRCALPHA if srcalpha else 0)
    stops = sorted(stops)
    for y in range(max(1, h)):
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


def alpha_band(w: int, h: int, color, alpha_top: int, alpha_bottom: int):
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    for y in range(max(1, h)):
        t = y / max(1, h - 1)
        a = clamp8(alpha_top + (alpha_bottom - alpha_top) * t)
        pygame.draw.line(surf, (*color, a), (0, y), (w, y))
    return surf


def catmull_rom(points, samples: int = 16):
    padded = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


SPINE = [
    (0.000, 0.340), (0.025, 0.460), (0.050, 0.550), (0.085, 0.580),
    (0.115, 0.530), (0.145, 0.330), (0.175, 0.020), (0.200, -0.100),
    (0.240, -0.030), (0.300, 0.150), (0.360, 0.400), (0.410, 0.500),
    (0.460, 0.460), (0.510, 0.280), (0.550, 0.020), (0.585, -0.100),
    (0.625, -0.020), (0.675, 0.220), (0.725, 0.550), (0.775, 0.720),
    (0.820, 0.700), (0.860, 0.550), (0.895, 0.300), (0.925, 0.020),
    (0.950, -0.060), (0.970, 0.020), (0.985, 0.100), (1.000, 0.120),
]

THICK = [
    (0.000, 0.190), (0.025, 0.270), (0.050, 0.320), (0.085, 0.310),
    (0.115, 0.270), (0.145, 0.230), (0.180, 0.190), (0.240, 0.240),
    (0.300, 0.300), (0.360, 0.360), (0.410, 0.380), (0.460, 0.360),
    (0.510, 0.300), (0.550, 0.240), (0.585, 0.200), (0.625, 0.220),
    (0.675, 0.300), (0.725, 0.360), (0.775, 0.370), (0.820, 0.350),
    (0.860, 0.300), (0.895, 0.230), (0.925, 0.160), (0.950, 0.120),
    (0.970, 0.080), (0.985, 0.040), (1.000, 0.008),
]


class Body:
    """One leviathan: a serpentine spine sampled in scene pixels."""

    def __init__(self, offset: float, length_frac: float, peak_frac: float,
                 phase: float, variant: int, rng: random.Random):
        self.offset = float(offset)
        self.length_frac = float(length_frac)
        self.peak_frac = float(peak_frac)
        self.phase = float(phase)
        self.variant = int(variant)
        wobble = [rng.uniform(-0.018, 0.018) for _ in SPINE]
        anchors = [(x, y + wobble[i]) for i, (x, y) in enumerate(SPINE)]
        self.raw_top = catmull_rom(anchors, 14)
        # The tube half-width and the undulation phase are fixed for a given
        # sample; precomputing them keeps the per-frame contour cheap.
        self.raw_pts = [(x, y, interp(THICK, x) * 0.5,
                         TAU * x * 1.35) for x, y in self.raw_top]
        self.start = 0.0
        self.length = 1.0
        self.peak = 1.0
        self.horizon = 0.0
        self.top = []
        self.bottom = []
        self.top_min = 0.0
        self.spout_x = 0.0
        self.update(0.0, 1.0, 1.0, 0.0, 0.0)

    def update(self, start: float, length: float, peak: float,
               horizon: float, time: float) -> None:
        self.start = start
        self.length = max(1.0, length)
        self.peak = max(1.0, peak)
        self.horizon = horizon
        self.top = []
        self.bottom = []
        phase = TAU * self.phase + TAU * time / 12.0
        for x, y, half_frac, wave_base in self.raw_pts:
            wave = 0.010 * math.sin(wave_base + phase)
            cy = horizon - self.peak * (y + wave)
            half = max(0.4, self.peak * half_frac)
            self.top.append((start + x * self.length, cy - half))
            self.bottom.append((start + x * self.length, cy + half))
        self.top_min = min(p[1] for p in self.top)
        self.tip_x = self.top[-1][0]
        self.spout_x = start + 0.055 * self.length

    def top_at(self, x: float) -> float:
        if x <= self.top[0][0]:
            return self.top[0][1]
        if x >= self.top[-1][0]:
            return self.top[-1][1]
        for i in range(len(self.top) - 1):
            x0, y0 = self.top[i]
            x1, y1 = self.top[i + 1]
            if x0 <= x <= x1 and x1 > x0:
                t = (x - x0) / (x1 - x0)
                return y0 + (y1 - y0) * t
        return self.top[-1][1]

    def thick_at(self, x: float) -> float:
        t = (x - self.start) / max(1.0, self.length)
        return max(0.8, self.peak * interp(THICK, min(1.0, max(0.0, t))))

    def polygon(self):
        return list(self.top) + list(reversed(self.bottom))

    def hump_x(self) -> float:
        return self.start + A_HUMP * self.length


# ---------------------------------------------------------------------------
# Static layer builders
# ---------------------------------------------------------------------------

def build_sky(W: int, sky_h: int, pal, rng: random.Random, layout_name: str,
              hud_rects, star_count: int, beacon_count: int):
    """Cached sky: gradient, clouds and the base star field.

    The bright anchors are returned, not drawn; the mode twinkles them per
    frame on top of this surface.
    """
    surface = vgrad(W, sky_h, [
        (0.00, pal["sky_top"]), (0.22, pal["sky_high"]),
        (0.48, pal["sky_mid"]), (0.72, pal["sky_low"]),
        (0.88, mix(pal["sky_low"], pal["horizon"], 0.45)),
        (0.96, mix(pal["sky_low"], pal["horizon"], 0.82)),
        (1.00, pal["horizon"]),
    ])
    overlay = pygame.Surface((W, sky_h), pygame.SRCALPHA)
    cloud_count = 4 if layout_name == "ultrawide" else (
        6 if layout_name == "portrait" else 5)
    for i in range(cloud_count):
        cy = sky_h * (0.16 + 0.105 * i) + rng.uniform(-8, 8)
        cx = W * rng.uniform(0.12, 0.88)
        cw = W * rng.uniform(0.30, 0.55)
        ch = max(6, sky_h * rng.uniform(0.018, 0.040))
        blit_soft(overlay, cx, cy, cw, ch, pal["cloud"],
                  rng.randint(8, 16), 2.2)
    if layout_name == "portrait":
        blit_soft(overlay, W * 0.58, sky_h * 0.47, W * 1.05,
                  max(6, sky_h * 0.012), pal["cloud"], 9, 2.3)
        blit_soft(overlay, W * 0.30, sky_h * 0.58, W * 0.75,
                  max(5, sky_h * 0.009), pal["mist"], 7, 2.3)
    for i in range(2):
        cy = sky_h * (0.76 + 0.085 * i) + rng.uniform(-6, 6)
        blit_soft(overlay, W * rng.uniform(0.25, 0.75), cy,
                  W * rng.uniform(0.55, 0.85), max(5, sky_h * 0.016),
                  mix(pal["cloud"], pal["horizon_hot"], 0.45),
                  rng.randint(9, 18), 2.4)
    surface.blit(overlay, (0, 0))

    star_layer = pygame.Surface((W, sky_h), pygame.SRCALPHA)
    for _ in range(max(0, int(star_count))):
        x = rng.uniform(0, W)
        y = rng.uniform(0, sky_h * 0.94)
        if y > sky_h * 0.62 and rng.random() < 0.55:
            continue
        if y > sky_h * 0.84 and rng.random() < 0.70:
            continue
        if any(rect.inflate(56, 36).collidepoint(x, y) for rect in hud_rects):
            continue
        roll = rng.random()
        if roll < 0.855:
            r, base = 1, rng.randint(20, 82)
        elif roll < 0.990:
            r, base = 2, rng.randint(38, 112)
        else:
            r, base = 3, rng.randint(62, 146)
        col = pal["star"] if rng.random() < 0.34 else pal["star_dim"]
        pygame.draw.circle(star_layer, (*col, base), (int(x), int(y)), r)
        if r == 3:
            blit_soft(star_layer, x, y, r * 8, r * 8, col,
                      max(5, base // 5), 2.0)
    surface.blit(star_layer, (0, 0))

    beacons = []
    guard = 0
    while len(beacons) < max(0, int(beacon_count)) and guard < beacon_count * 50:
        guard += 1
        x = rng.uniform(W * 0.04, W * 0.96)
        y = rng.uniform(sky_h * 0.06, sky_h * 0.78)
        if any(rect.inflate(60, 40).collidepoint(x, y) for rect in hud_rects):
            continue
        if any(math.hypot(x - bx, y - by) < W * 0.055
               for bx, by, *_ in beacons):
            continue
        beacons.append((x, y, rng.choice((2, 2, 3)),
                        rng.uniform(3.5, 9.0), rng.uniform(0, TAU)))
    return surface, beacons


def build_beacon_sprite(pal):
    """A cross-glint star: soft halo, hot core and four short rays."""
    col = mix(pal["star"], pal["moon"], 0.32)
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    blit_soft(surf, 32, 32, 48, 48, col, 38, 2.0)
    pygame.draw.circle(surf, (*col, 190), (32, 32), 3)
    pygame.draw.circle(surf, (*col, 245), (32, 32), 1)
    pygame.draw.line(surf, (*col, 140), (16, 32), (48, 32), 1)
    pygame.draw.line(surf, (*col, 140), (32, 16), (32, 48), 1)
    return surf


def build_moon_sprite(pal, r: float, rng: random.Random, glow: float = 0.8):
    """Cached moon + halo, drawn at 2x and downsampled for a soft limb."""
    r = max(3.0, float(r))
    half = int(max(8, r * 6))
    size = half * 2
    ss = 2
    big = pygame.Surface((size * ss, size * ss), pygame.SRCALPHA)
    cx = cy = half * ss
    rr = r * ss
    blit_soft(big, cx, cy, rr * 11, rr * 11, pal["moon_glow"],
              int(16 * glow), 2.0)
    blit_soft(big, cx, cy, rr * 5.2, rr * 5.2, pal["moon_glow"],
              int(28 * glow), 2.2)
    blit_soft(big, cx, cy, rr * 2.6, rr * 2.6, pal["moon_glow"],
              int(46 * glow), 2.4)
    blit_soft(big, cx, cy, rr * 1.55, rr * 1.55, pal["moon"],
              int(72 * glow), 2.2)
    steps = max(12, int(rr))
    for i in range(steps, 0, -1):
        t = i / steps
        col = mix(pal["moon"], pal["moon_edge"], t ** 1.5)
        pygame.draw.circle(big, col, (int(cx), int(cy)), int(rr * t))
    craters = pygame.Surface((int(rr * 4), int(rr * 4)), pygame.SRCALPHA)
    ox = oy = int(rr * 2)
    for _ in range(7):
        ang = rng.uniform(0, TAU)
        dist = rng.uniform(0, rr * 0.62)
        ex = ox + math.cos(ang) * dist
        ey = oy + math.sin(ang) * dist * 0.9
        ew = rr * rng.uniform(0.16, 0.40)
        eh = ew * rng.uniform(0.55, 1.0)
        pygame.draw.ellipse(craters, (*pal["moon_dark"], rng.randint(14, 28)),
                            (int(ex - ew / 2), int(ey - eh / 2),
                             int(ew), int(eh)))
    mask = pygame.Surface((int(rr * 4), int(rr * 4)), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (ox, oy), int(rr))
    craters.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    big.blit(craters, (int(cx - rr * 2), int(cy - rr * 2)))
    pygame.draw.arc(big, mix(pal["moon"], (255, 255, 255), 0.35),
                    (int(cx - rr), int(cy - rr), int(rr * 2), int(rr * 2)),
                    math.radians(70), math.radians(190), max(1, int(rr * 0.06)))
    out = pygame.transform.smoothscale(big, (size, size))
    return out, half


def build_boat_sprite(pal, w: float, mast: float, kind: str):
    """Cached waterline reference.  Returns (sprite, anchor, reflection)."""
    if kind == "none":
        return None, (0, 0), None
    w = max(6.0, float(w))
    mast = max(6.0, float(mast))
    ss = 2
    if kind == "lighthouse":
        native_w = int(max(46, w * 3.2))
        native_h = int(max(70, mast * 3.0))
        big = pygame.Surface((native_w * ss, native_h * ss), pygame.SRCALPHA)
        cx = native_w * ss // 2
        base = native_h * ss - 4
        tw = max(3, int(w * 0.16)) * ss
        th = int(mast * 1.35) * ss
        pygame.draw.polygon(big, (*pal["boat"], 255), [
            (cx - tw, base), (cx + tw, base),
            (cx + tw * 0.55, base - th), (cx - tw * 0.55, base - th)])
        pygame.draw.polygon(big, (*pal["boat"], 255), [
            (cx - tw * 1.6, base - th), (cx + tw * 1.6, base - th),
            (cx + tw * 1.1, base - th - tw * 1.2),
            (cx - tw * 1.1, base - th - tw * 1.2)])
        lx, ly = cx, base - th - tw * 2.2
        blit_soft(big, lx, ly, w * 5.0, w * 5.0, pal["lantern"], 46, 2.0)
        pygame.draw.circle(big, (*pal["lantern"], 230),
                           (int(lx), int(ly)), max(1, int(w * 0.08) * ss))
        sprite = pygame.transform.smoothscale(big, (native_w, native_h))
        refl = pygame.Surface((native_w, max(6, native_w // 2)),
                              pygame.SRCALPHA)
        for i in range(refl.get_height()):
            t = i / refl.get_height()
            pygame.draw.line(refl, (*pal["boat"], int(24 * (1 - t))),
                             (int(native_w * 0.48 - t * 6), i),
                             (int(native_w * 0.52 + t * 6), i), 1)
        return sprite, (native_w // 2, native_h - 4), refl
    native_w = int(max(18, w * 4.0))
    native_h = int(max(24, mast + w * 2.2))
    big = pygame.Surface((native_w * ss, native_h * ss), pygame.SRCALPHA)
    cx = native_w * ss // 2
    base = native_h * ss - int(w * 0.55) * ss
    ww = w * ss
    hull = [(cx - ww / 2, base - ww * 0.07),
            (cx - ww * 0.30, base + ww * 0.16),
            (cx + ww * 0.30, base + ww * 0.16),
            (cx + ww / 2, base - ww * 0.07)]
    pygame.draw.polygon(big, (*pal["boat"], 255), hull)
    pygame.draw.lines(big, mix(pal["sail"], pal["sea_top"], 0.45), False,
                      hull, 1)
    mast_top = base - mast * ss
    pygame.draw.line(big, (*pal["boat"], 255),
                     (cx + ww * 0.04, base - ss), (cx + ww * 0.04, mast_top),
                     max(1, int(ww / 9)))
    sail = [(cx + ww * 0.04, mast_top + ss),
            (cx + ww * 0.04, base - ww * 0.20),
            (cx - ww * 0.34, base - ww * 0.26)]
    pygame.draw.polygon(big, mix(pal["sail"], pal["sea_top"], 0.48), sail)
    pygame.draw.lines(big, mix(pal["sail"], pal["horizon"], 0.30), False,
                      sail, 1)
    lx, ly = cx + ww * 0.33, base - ww * 0.18
    blit_soft(big, lx, ly, ww * 1.4, ww * 1.4, pal["lantern"], 66, 2.0)
    pygame.draw.circle(big, (*pal["lantern"], 220), (int(lx), int(ly)),
                       max(1, int(ww * 0.045)))
    sprite = pygame.transform.smoothscale(big, (native_w, native_h))
    refl = pygame.Surface((native_w, max(8, int(native_w * 0.5))),
                          pygame.SRCALPHA)
    for i in range(refl.get_height()):
        t = i / refl.get_height()
        pygame.draw.line(refl, (*pal["boat"], int(30 * (1 - t))),
                         (int(native_w * 0.48 - t * 3), i),
                         (int(native_w * 0.52 + t * 3), i), 1)
    blit_soft(refl, native_w * 0.52, 3, w * 0.8, w * 0.8,
              pal["lantern"], 40, 2.0)
    return sprite, (native_w // 2, base // ss), refl


MIST_BAND = 200
MIST_HORIZON = 100


def build_mist(W: int, H: int, horizon: float, pal, rng: random.Random,
               layout_name: str, amount: float):
    margin = 16
    w2 = W + margin * 2
    overlay = pygame.Surface((w2, MIST_BAND), pygame.SRCALPHA)
    band_w = w2 * (1.7 if layout_name == "ultrawide" else 1.5)
    local = float(MIST_HORIZON)
    for dy, h, a in ((-26, 44, 54), (-8, 30, 76), (12, 34, 46)):
        blit_soft(overlay, w2 * 0.5, local + dy, band_w, h * 2.2,
                  pal["mist"], int(a * amount), 2.1)
    blit_soft(overlay, w2 * 0.52, local - 6, w2 * 0.9, 30,
              pal["mist_hot"], int(26 * amount), 2.3)
    pygame.draw.line(overlay, (*pal["mist_hot"], int(34 * amount)),
                     (0, local), (w2, local), 2)
    count = 12 if layout_name in ("ultrawide", "landscape") else 18
    for _ in range(count):
        cx = rng.uniform(-w2 * 0.10, w2 * 1.10)
        cy = local + rng.uniform(-26, 22)
        cw = w2 * rng.uniform(0.14, 0.36)
        ch = rng.uniform(8, 26)
        col = pal["mist_hot"] if rng.random() < 0.35 else pal["mist"]
        blit_soft(overlay, cx, cy, cw, ch * 2.0, col,
                  int(rng.randint(10, 22) * amount), 2.0)
    return overlay


def build_finish(W: int, H: int, vignette: float, scanlines: int,
                 grain: bool, seed: int):
    sw, sh = 72, max(12, int(72 * H / W))
    mask = pygame.Surface((sw, sh), pygame.SRCALPHA)
    strength = int(200 * max(0.0, min(1.0, vignette)))
    for y in range(sh):
        ny = (y / (sh - 1) - 0.5) * 2
        for x in range(sw):
            nx = (x / (sw - 1) - 0.5) * 2
            d = math.sqrt(nx * nx * 0.92 + ny * ny * 0.78)
            v = max(0.0, (d - 0.58) / 0.85)
            a = int(strength * (v ** 1.8))
            if a:
                mask.set_at((x, y), (0, 0, 0, min(255, a)))
    vignette_surface = pygame.transform.smoothscale(mask, (W, H))
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    if scanlines > 0:
        for y in range(0, H, 2):
            pygame.draw.line(overlay, (0, 0, 0, scanlines),
                             (0, y), (W, y), 1)
    if grain:
        rng = random.Random(seed ^ 0x6A1E)
        for _ in range(int(W * H * 0.015)):
            x = rng.randrange(W)
            y = rng.randrange(H)
            v = rng.randint(90, 210)
            overlay.set_at((x, y), (v, v, v, 10))
    return vignette_surface, overlay


def add_bloom(surface, strength: int, glow: float = 1.0) -> None:
    if strength <= 0:
        return
    small = pygame.transform.smoothscale(
        surface, (max(2, surface.get_width() // 4),
                  max(2, surface.get_height() // 4)))
    factor = max(0, min(255, int(strength * glow)))
    if factor <= 0:
        return
    small.fill((factor, factor, factor, 255),
               special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(pygame.transform.smoothscale(small, surface.get_size()),
                 (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def text_surface(text: str, font, color, tracking: float, alpha: int):
    if not text:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    widths = [font.size(ch)[0] for ch in text]
    w = sum(widths) + int(tracking * max(0, len(text) - 1))
    h = font.get_height()
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    x = 0
    for ch, cw in zip(text, widths):
        glyph = font.render(ch, True, color)
        glyph.set_alpha(alpha)
        surf.blit(glyph, (x, 0))
        x += cw + tracking
    return surf


# ---------------------------------------------------------------------------
# Live layers
# ---------------------------------------------------------------------------

def build_sea_data(W: int, sea_h: int, pal, rng: random.Random,
                   layout_name: str, moon_x: float):
    """Precomputed glitter, swell and sparkle tables (no per-frame RNG)."""
    glitter = []
    count = 170 if layout_name == "ultrawide" else (
        230 if layout_name == "portrait" else 190)
    for i in range(count):
        t = i / count
        y = 2 + (t ** 1.40) * sea_h * 0.80
        spread = 12 + t * (W * 0.105)
        dx = rng.gauss(0, spread * 0.52)
        dash = (3 + t * (34 if layout_name == "ultrawide" else 52)) \
            * rng.uniform(0.35, 1.45)
        a = int((138 if layout_name == "ultrawide" else 146)
                * (1 - t) ** 1.35 * rng.uniform(0.65, 1.05))
        glitter.append((dx, y, dash, rng.uniform(0, TAU),
                        rng.uniform(0.8, 2.4), a))
    swells = []
    y = 6.0
    step = 4.5 if layout_name == "ultrawide" else 8.0
    index = 0
    while y < sea_h:
        t = y / sea_h
        swells.append((y, 0.7 + t * (3.8 if layout_name == "ultrawide" else 6.8),
                       0.005 + rng.uniform(0.0, 0.004), rng.uniform(0, TAU),
                       int((20 if layout_name == "ultrawide" else 18)
                           * (1.0 - t) ** 1.0) + 4,
                       mix(pal["swell_far"], pal["swell_near"], t),
                       index % 3 == 1))
        y += step
        step *= 1.13
        index += 1
    specks = []
    count = 90 if layout_name not in ("portrait",) else 130
    for _ in range(count):
        t = rng.random() ** 0.7
        specks.append((rng.uniform(0, W), 6 + t * sea_h * 0.9,
                       rng.uniform(2, 8), rng.uniform(0, TAU),
                       rng.randint(4, 11), rng.uniform(1.2, 4.0)))
    return glitter, swells, specks


def draw_sea_live(overlay, W: int, sea_h: int, pal, moon_x: float,
                  glitter, swells, specks, time: float, swell_speed: float,
                  layout_name: str, moon_on: bool = True) -> None:
    overlay.fill((0, 0, 0, 0))
    if moon_on:
        # the moon's column
        blit_soft(overlay, moon_x, sea_h * 0.24, W * 0.34, sea_h * 0.85,
                  pal["moon_glow"], 42, 2.0)
        blit_soft(overlay, moon_x, 4, W * 0.16, sea_h * 0.12,
                  pal["moon"], 100, 2.4)
    for dx, y, dash, phase, rate, a in (glitter if moon_on else ()):
        x = moon_x + dx
        if x < -20 or x > W + 20:
            continue
        alpha = int(a * (0.58 + 0.42 * math.sin(time * rate + phase)))
        if alpha <= 2:
            continue
        yy = y + math.sin(time * 0.7 + phase) * 1.2
        pygame.draw.line(overlay, (*pal["moon"], alpha),
                         (x - dash / 2, yy), (x + dash / 2, yy), 1)
    for (y, amp, freq, phase, a, col, crest) in swells:
        scroll = time * swell_speed * freq
        pts = []
        for x in range(-8, W + 9, 9):
            yy = (y + math.sin(x * freq + phase + scroll) * amp
                  + math.sin(x * freq * 2.3 + phase * 1.7 + scroll * 1.4)
                  * amp * 0.35)
            pts.append((x, yy))
        t = y / max(1.0, sea_h)
        alpha = max(2, int(a * (0.70 + 0.30 * math.sin(time * 0.35 + phase))))
        pygame.draw.lines(overlay, (*col, alpha), False, pts, 1)
        if crest:
            cx = moon_x + math.sin(time * 0.22 + phase) * W * 0.10
            half = (18 + t * 90) * (0.6 + 0.4 * math.sin(phase))
            cpts = []
            for x in range(int(cx - half), int(cx + half) + 3, 3):
                if not (0 <= x <= W):
                    continue
                yy = (y + math.sin(x * freq + phase + scroll) * amp
                      + math.sin(x * freq * 2.3 + phase * 1.7 + scroll * 1.4)
                      * amp * 0.35)
                cpts.append((x, yy))
            if len(cpts) > 1:
                pygame.draw.lines(overlay, (*pal["moon"],
                                            min(90, alpha * 3 + 10)),
                                  False, cpts, 1)
    for x, y, dash, phase, a, rate in specks:
        alpha = int(a * (0.55 + 0.45 * math.sin(time * rate + phase)))
        if alpha <= 2:
            continue
        yy = y + math.sin(time * 0.5 + phase) * 1.0
        pygame.draw.line(overlay, (*pal["swell_far"], alpha),
                         (x - dash / 2, yy), (x + dash / 2, yy), 1)


def draw_wakes_on(overlay, W: int, sea_h: int, pal, bodies) -> None:
    for body in bodies:
        start = body.start + body.length * (1.02 + 0.02 * body.variant)
        length = body.length * (0.55 + 0.15 * ((body.phase * 7.0) % 1.0))
        for k in range(3):
            y = 2 + k * (2.2 + body.peak * 0.012)
            pts = []
            span = length * (1.0 - 0.18 * k)
            for j in range(26):
                t = j / 25.0
                x = start + t * span
                if x > W + 20:
                    break
                yy = y + t * (2.0 + k * 1.3) + math.sin(t * 9 + body.phase) * 0.8
                pts.append((x, yy))
            if len(pts) > 1:
                pygame.draw.lines(overlay, (*pal["wake"], int(32 * (1.0 - k * 0.26))),
                                  False, pts, 1)


def draw_meteor(surface, W: int, H: int, pal, spec, progress: float,
                quality: int = 2) -> None:
    if progress <= 0.0 or progress >= 1.0:
        return
    sx, sy = spec["start"]
    ex, ey = spec["end"]
    hx = (sx + (ex - sx) * progress) * W
    hy = (sy + (ey - sy) * progress) * H
    dx = (ex - sx) * W
    dy = (ey - sy) * H
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return
    ux, uy = dx / dist, dy / dist
    length = spec["length"] * W
    tx, ty = hx - ux * length, hy - uy * length
    fade = min(1.0, progress / 0.10) * min(1.0, (1.0 - progress) / 0.20)
    fade = max(0.0, fade) ** 0.7
    head_col = mix(pal["star"], (255, 255, 255), 0.50)
    pygame.draw.line(surface, (*head_col, int(15 * fade)), (tx, ty),
                     (hx, hy), max(2, int(1.4 * quality)))
    segs = 28
    for i in range(segs):
        t0 = i / segs
        t1 = (i + 1) / segs
        x0 = tx + (hx - tx) * t0
        y0 = ty + (hy - ty) * t0
        x1 = tx + (hx - tx) * t1
        y1 = ty + (hy - ty) * t1
        a = int(218 * (t1 ** 2.4) * fade)
        if a <= 2:
            continue
        width = max(1, int((0.5 + 2.2 * t1) * quality * 0.8))
        pygame.draw.line(surface, (*head_col, a), (x0, y0), (x1, y1), width)
    blit_soft(surface, hx, hy, 13.0 * quality, 13.0 * quality,
              pal["moon"], int(66 * fade), 2.0)
    pygame.draw.circle(surface, (*head_col, int(238 * fade)),
                       (int(hx), int(hy)), max(1, int(quality * 0.62)))


# ---------------------------------------------------------------------------
# Creature and water detail
# ---------------------------------------------------------------------------

def render_body_layer(body: Body, pal, W: int, H: int, moon_x: float,
                      ss: int = 1):
    x0 = max(0, int(body.start - 10))
    x1 = min(W, int(body.tip_x + 12))
    y0 = max(0, int(body.top_min - 12))
    y1 = min(H, int(body.horizon + 3))
    bw, bh = x1 - x0, y1 - y0
    if bw <= 2 or bh <= 2:
        return None
    sw, sh = bw * ss, bh * ss
    layer = pygame.Surface((sw, sh), pygame.SRCALPHA)
    ox, oy = x0, y0
    poly = [((x - ox) * ss, (y - oy) * ss) for x, y in body.polygon()]
    mask = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), poly)
    if ss == 1:
        # A cheap anti-aliased silhouette edge for the medium/low tiers, which
        # draw at native resolution rather than supersampling.
        pygame.gfxdraw.aapolygon(
            mask, [(int(px), int(py)) for px, py in poly], (255, 255, 255))
    grad = vgrad(sw, sh, [
        (0.00, pal["body_hi"]), (0.26, pal["body"]),
        (0.78, pal["body"]), (1.00, pal["body_low"]),
    ], srcalpha=True)
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    layer.blit(grad, (0, 0))
    top = body.top
    horizon = body.horizon

    hx = body.start + 0.010 * body.length
    hx2 = body.start + 0.070 * body.length
    if body.top_at(hx2) < horizon - 8:
        jaw = [((hx - ox) * ss, (body.top_at(hx) - oy
                                 + body.thick_at(hx) * 0.62) * ss),
               ((hx2 - ox) * ss, (body.top_at(hx2) - oy
                                  + body.thick_at(hx2) * 0.42) * ss)]
        pygame.draw.line(layer, (*mix(pal["body"], pal["rim"], 0.45), 42),
                         jaw[0], jaw[1], 1)

    for i in range(len(top) - 1):
        x, y = top[i]
        nx, ny = top[i + 1]
        if nx - x <= 0 or y > horizon - 3:
            continue
        closeness = 1.0 - min(1.0, abs((x - moon_x) / (W * 0.52)))
        facing = 1.0 if ((ny - y) > 0) == (moon_x > x) else 0.28
        breather = 0.35 + 0.65 * math.sin(x * 0.031 + body.phase * 9.0) ** 2
        a = int((11 + 74 * closeness) * breather * facing)
        col = mix(pal["rim"], pal["rim_hot"], closeness * closeness)
        pygame.draw.line(layer, (*col, a),
                         ((x - ox) * ss, (y - oy) * ss),
                         ((nx - ox) * ss, (ny - oy) * ss),
                         max(1, int(0.75 * ss)))
        if facing > 0.5 and a > 24:
            pygame.draw.line(layer, (*col, int(a * 0.20)),
                             ((x - ox) * ss, (y - oy - 1) * ss),
                             ((nx - ox) * ss, (ny - oy - 1) * ss),
                             max(2, int(1.4 * ss)))

    ex = body.start + 0.055 * body.length
    ey = body.top_at(ex) + body.peak * 0.070
    er = max(1, int(body.peak * 0.020 * ss))
    pygame.draw.circle(layer, (0, 0, 0, 140),
                       (int((ex - ox) * ss), int((ey - oy) * ss)), er + 2 * ss)
    pygame.draw.circle(layer, (*pal["rim_hot"], 120),
                       (int((ex - ox) * ss), int((ey - oy) * ss)), er)
    if ss != 1:
        layer = pygame.transform.smoothscale(layer, (bw, bh))
    return layer, ox, oy


def draw_reflection(surface, body: Body, pal, H: int, ratio: float,
                    slices: int) -> None:
    sea_h = max(1, int(H - body.horizon))
    top_h = max(2.0, body.horizon - body.top_min + 2)
    reflect_h = min(sea_h * ratio, body.peak * 0.72, top_h)
    if reflect_h < 4:
        return
    x0 = max(0, int(body.start))
    x1 = min(surface.get_width(), int(body.tip_x + 4))
    bw = x1 - x0
    if bw <= 2:
        return
    layer = pygame.Surface((bw, int(top_h)), pygame.SRCALPHA)
    poly = [(x - x0, body.horizon - y)
            for x, y in body.polygon() if y <= body.horizon + 1]
    if len(poly) < 3:
        return
    pygame.draw.polygon(layer, (*pal["body"], 255), poly)
    small = pygame.transform.smoothscale(
        layer, (max(1, bw // 3), max(1, layer.get_height() // 3)))
    blur = pygame.transform.smoothscale(small, layer.get_size())
    flip = pygame.transform.flip(blur, False, True)
    flip = pygame.transform.smoothscale(flip, (bw, max(2, int(reflect_h))))
    slice_h = max(1, flip.get_height() // max(1, slices))
    for i in range(slices):
        sy = i * slice_h
        if sy >= flip.get_height():
            break
        sh = min(slice_h, flip.get_height() - sy)
        strip = flip.subsurface((0, sy, bw, sh)).copy()
        fade = (1.0 - i / slices) ** 1.9
        strip.fill((255, 255, 255, int(88 * fade)),
                   special_flags=pygame.BLEND_RGBA_MULT)
        drift = int(math.sin(i * 0.55 + body.phase * 5) * (1.6 + i * 0.14))
        surface.blit(strip, (x0 + drift, int(body.horizon) + sy))
    for t in (0.20, 0.50, 0.86):
        gx = body.start + t * body.length
        if not (0 <= gx <= surface.get_width()):
            continue
        pygame.draw.line(surface, mix(pal["rim"], pal["sea_top"], 0.82),
                         (gx - body.length * 0.02, body.horizon),
                         (gx + body.length * 0.02, body.horizon), 1)
        blit_soft(surface, gx, body.horizon - 2, body.length * 0.10,
                  max(5, body.peak * 0.10), pal["mist"], 12, 2.0)


def draw_spout(surface, body: Body, pal, detail: int = 2,
               strength: float = 1.0, time: float = 0.0) -> None:
    x = body.spout_x
    base = body.top_at(x) + body.peak * 0.01
    height = body.peak * (0.58 * strength)
    drift = body.peak * 0.20
    puffs = (3, 6, 11)[max(0, min(2, detail))]
    # A puff is born at the blowhole, rises, drifts and fades; the plume has a
    # 20 s cycle, staggered per animal.
    phase = (time / 20.0 + body.phase * 0.37) % 1.0
    for i in range(puffs):
        t = (i / puffs + phase) % 1.0
        px = x + t * drift + math.sin(t * 4.5) * body.peak * 0.02
        py = base - t * height
        size = body.peak * (0.05 + 0.16 * t)
        a = int(46 * (1.0 - t) ** 1.3 * strength)
        if a <= 1:
            continue
        blit_soft(surface, px, py, size * 3.4, size * 2.6,
                  pal["mist"], a, 1.8)
    blit_soft(surface, x, base - height * 0.08, body.peak * 0.12,
              body.peak * 0.10, pal["mist_hot"], 46, 1.8)


def draw_eclipse_corona(surface, body: Body, moon_xy, moon_r: float,
                        pal, strength: float, quality: int = 1) -> None:
    if strength <= 0.02:
        return
    cx, cy = moon_xy
    top = body.top
    for i in range(len(top) - 1):
        x0, y0 = top[i]
        x1, y1 = top[i + 1]
        d = abs((x0 + x1) / 2 - cx)
        if d > moon_r * 1.15:
            continue
        glow = max(0.0, 1.0 - d / (moon_r * 1.15)) * strength
        col = mix(pal["corona"], pal["sky_top"],
                  0.10 + 0.60 * (1.0 - glow))
        pygame.draw.line(surface, col, (x0, y0 - 1), (x1, y1 - 1),
                         max(1, quality + 1))
        pygame.draw.line(surface, mix(col, pal["sky_top"], 0.55),
                         (x0, y0 - 2), (x1, y1 - 2),
                         max(2, quality * 2 + 2))
    for dx, a in ((-0.9, 14), (-0.45, 22), (0.0, 30), (0.45, 20), (0.9, 12)):
        blit_soft(surface, cx + moon_r * dx, cy - moon_r * 0.55,
                  moon_r * 3.0, moon_r * 2.6, pal["corona"],
                  int(a * strength), 2.0)


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class LeviathanMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.diagnostic = ""
        self.seed = None

        self._pinned_seed = None
        self._palette_name = "dusk"
        self._palette = PALETTES["dusk"]
        self._title = DEFAULT_TITLE
        self._subtitle = ""
        self._pod_size = 3
        self._crossing_seconds = 120.0
        self._mist = True
        self._moon = True
        self._moon_arc_seconds = 600.0
        self._scale_reference = "boat"
        self._show_reflections = True
        self._show_spouts = True
        self._eclipse_seconds = 4.0
        self._swell_speed = 1.0
        self._star_density = 1.0
        self._meteor = True
        self._meteor_seconds = 90.0
        self._meteor_duration = 1.2
        self._glow_strength = 0.8
        self._scanlines = 4
        self._vignette = 0.55
        self._hud_mode = "minimal"
        self._orientation = "auto"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0

        self._time = 0.0
        self._start_time = 0.0
        self._screen_size = None
        self._built_size = None
        self._layout = None
        self._preset = None
        self._pod_specs = []
        self._bodies = []
        self._visible_bodies = []
        self._pod_count = 0
        self._cycle_gap = 40.0
        self._phase_frac = 0.35
        self._cycle_length = 300.0
        self._cycle_offset = 0.0
        self._moon_phase = 0.0
        self._boat_phase = 0.0
        self._speed_px = 1280.0 / 120.0
        self._visible_exit = 240.0
        self._hero_at_cycle = 0.0
        self._eclipse_at_cycle = 0.0
        self._eclipse = 0.0
        self._eclipse_active = False
        self._pod_x = 0.0
        self._moon_x = 0.0
        self._moon_y = 0.0

        self._meteor_rng = None
        self._active_meteor = None
        self._meteor_progress = 0.0
        self._next_meteor = float("inf")
        self._meteor_count = 0

        self._star_total = 0
        self._beacons = []
        self._beacon_sprite = None
        self._beacon_scaled = {}
        self._glitter = []
        self._swells = []
        self._specks = []
        self._hud = {}
        self._hud_rects = []
        self._clear_caches()

    # ---------------------------------------------------------------- config

    @staticmethod
    def _number(config, key, default, lo, hi):
        value = config.get(key, default)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        value = float(value)
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be finite and in {lo}..{hi}")
        return value

    @staticmethod
    def _integer(config, key, default, lo, hi):
        value = config.get(key, default)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a whole number")
        if float(value) != int(value):
            raise ValueError(f"{key} must be a whole number")
        value = int(value)
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be in {lo}..{hi}")
        return value

    @staticmethod
    def _bool(config, key, default):
        value = config.get(key, default)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false")
        return value

    @staticmethod
    def _text(config, key, default, max_length=64):
        value = config.get(key, default)
        if value is None:
            value = default
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        return value.strip()[:max_length]

    def _read_config(self):
        cfg = self.config
        seed = cfg.get("seed")
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
                raise ValueError("seed must be an integer in 0..2147483647 or null")
        self._pinned_seed = seed

        palette_name = str(cfg.get("palette", "dusk")).lower()
        if palette_name not in PALETTES:
            raise ValueError("palette must be " + ", ".join(PALETTES))
        self._palette_name = palette_name
        self._palette = PALETTES[palette_name]

        self._title = self._text(cfg, "title", DEFAULT_TITLE, 64) or DEFAULT_TITLE
        self._subtitle = self._text(cfg, "subtitle", "", 80)
        self._pod_size = self._integer(cfg, "pod_size", 3, 2, MAX_POD)
        self._crossing_seconds = self._number(cfg, "crossing_seconds", 120.0,
                                             60.0, 300.0)
        self._mist = self._bool(cfg, "mist", True)
        self._moon = self._bool(cfg, "moon", True)
        self._moon_arc_seconds = self._number(cfg, "moon_arc_seconds", 600.0,
                                             0.0, 1200.0)
        self._scale_reference = str(cfg.get("scale_reference", "boat")).lower()
        if self._scale_reference not in SCALE_REFERENCES:
            raise ValueError("scale_reference must be "
                             + ", ".join(SCALE_REFERENCES))
        self._show_reflections = self._bool(cfg, "show_reflections", True)
        self._show_spouts = self._bool(cfg, "show_spouts", True)
        self._eclipse_seconds = self._number(cfg, "eclipse_seconds", 4.0,
                                             0.0, 10.0)
        self._swell_speed = self._number(cfg, "swell_speed", 1.0, 0.0, 4.0)
        self._star_density = self._number(cfg, "star_density", 1.0, 0.0, 2.0)
        self._meteor = self._bool(cfg, "meteor", True)
        self._meteor_seconds = self._number(cfg, "meteor_seconds", 90.0,
                                            0.0, 300.0)
        self._meteor_duration = self._number(cfg, "meteor_duration", 1.2,
                                             0.4, 3.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.8, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 4.0, 0.0, 40.0))
        self._vignette = self._number(cfg, "vignette_strength", 0.55, 0.0, 1.0)

        hud = str(cfg.get("hud", "minimal")).lower()
        if hud == "off":
            hud = "none"
        if hud not in HUD_MODES:
            raise ValueError("hud must be none, minimal, or full")
        self._hud_mode = hud

        orientation = str(cfg.get("orientation", "auto")).lower()
        if orientation not in ORIENTATIONS:
            raise ValueError("orientation must be " + ", ".join(ORIENTATIONS))
        self._orientation = orientation

        quality = str(cfg.get("quality", "auto")).lower()
        if quality not in QUALITY_NAMES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            self.seed = self._next_seed()
            rng = random.Random(self.seed)
            self._cycle_gap = rng.uniform(28.0, 62.0)
            self._phase_frac = rng.uniform(0.10, 0.72)
            self._moon_phase = rng.uniform(0, TAU)
            self._boat_phase = rng.uniform(0, TAU)
            self._meteor_rng = random.Random(self.seed ^ 0x5EA17)
            self._time = 0.0
            self._start_time = 0.0
            self._active_meteor = None
            self._meteor_count = 0
            self._quality = ("medium" if self._auto_quality
                             else self._quality_setting)
            self._quality_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self._build(manager.screen.get_size())
            self._schedule_first_meteor(rng)
            self.error = None
            print(f"[Leviathan] seed={self.seed} preset={self._preset} "
                  f"pod={self._pod_count} palette={self._palette_name} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Leviathan] configuration error: {exc}")

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def _schedule_first_meteor(self, rng: random.Random) -> None:
        if not self._meteor or self._meteor_seconds <= 0.0:
            self._next_meteor = float("inf")
            return
        self._next_meteor = self._time + rng.uniform(
            12.0, max(18.0, self._meteor_seconds * 1.35))

    def exit(self):
        self.manager = None
        self.error = None
        self._clear_caches()
        _SOFT_CACHE.clear()
        _SOFT_SCALED.clear()
        self._built_size = None
        self._screen_size = None
        self._layout = None
        self._preset = None
        self._time = 0.0
        self._start_time = 0.0
        self._bodies = []
        self._visible_bodies = []
        self._pod_specs = []
        self._active_meteor = None
        self._hud = {}

    def _clear_caches(self):
        self._sky = None
        self._sea_base = None
        self._sea_overlay = None
        self._mist_far = None
        self._mist_near = None
        self._moon_sprite = None
        self._moon_half = 0
        self._boat_sprite = None
        self._boat_anchor = (0, 0)
        self._boat_reflection = None
        self._finish_surface = None
        self._beacons = []
        self._beacon_scaled = {}
        self._glitter = []
        self._swells = []
        self._specks = []
        self._hud = {}
        self._hud_rects = []
        self._bodies = []
        self._visible_bodies = []
        self._body_layers = []

    # ---------------------------------------------------------------- layout

    def _resolve_layout(self, size):
        W, H = int(size[0]), int(size[1])
        preset_name = (aspect_class(W, H) if self._orientation == "auto"
                       else self._orientation)
        preset = LAYOUTS[preset_name]
        bw, bh = preset["base"]
        sx, sy = W / bw, H / bh
        ps = min(sx, sy)
        horizon = H * preset["horizon"]
        return {
            "preset": preset_name,
            "base": (bw, bh),
            "width": W, "height": H,
            "sx": sx, "sy": sy, "ps": ps,
            "horizon": horizon,
            "moon": {
                "x": preset["moon"]["x"] * W,
                "r": preset["moon"]["r"] * ps,
                "above": preset["moon"]["above"] * ps,
            },
            "boat": {
                "x": preset["boat"]["x"] * W,
                "w": preset["boat"]["w"] * ps,
                "mast": preset["boat"]["mast"] * ps,
            },
            "meteor": dict(preset["meteor"]),
            "pod": tuple(preset["pod"]),
            "stars": preset["stars"],
            "beacons": preset["beacons"],
            "title_px": max(8, int(round(preset["title_size"] * ps))),
            "title_track": preset["title_tracking"] * ps,
            "eyebrow_px": max(7, int(round(preset["eyebrow_size"] * ps))),
            "tele_px": max(8, int(round(preset["telemetry_size"] * ps))),
            "title_xy": (preset["title_xy"][0] * sx,
                         preset["title_xy"][1] * sy),
            "eyebrow_xy": (preset["eyebrow_xy"][0] * sx,
                           preset["eyebrow_xy"][1] * sy),
            "telemetry_xy": (preset["telemetry_xy"][0] * sx,
                             preset["telemetry_xy"][1] * sy),
            "two_line": bool(preset["two_line"]),
        }

    def _build_pod(self):
        base = list(self._layout["pod"])
        a_base = base[0][0]
        a_len = base[0][1]
        a_peak = base[0][2]
        if self._pod_size == 2:
            chosen = [base[0], base[2]]
        else:
            chosen = list(base)
            for off, lf, pf, ph, var in POD_EXTRAS[:max(0, self._pod_size - 3)]:
                chosen.append((off, a_len * lf, a_peak * pf, ph, var))
        self._pod_specs = [(entry[0] - a_base, entry[1], entry[2],
                            entry[3], entry[4]) for entry in chosen]
        self._pod_count = len(self._pod_specs)
        rng = random.Random(self.seed ^ 0xB0D1E5)
        self._bodies = [Body(offset, length, peak, phase, variant, rng)
                        for offset, length, peak, phase, variant
                        in self._pod_specs]
        self._body_layers = [None] * len(self._bodies)

    def _manager_font(self, name, size, bold=False):
        cache = getattr(self.manager, "cache", None) if self.manager else None
        if cache is not None:
            try:
                return cache.get_font(name, int(size), bold=bool(bold))
            except (pygame.error, TypeError):
                pass
        return pygame.font.SysFont(name, int(size), bold=bool(bold))

    def _build_hud(self):
        if self._hud_mode == "none":
            self._hud = {}
            self._hud_rects = []
            return
        layout = self._layout
        pal = self._palette
        title_px = layout["title_px"]
        title_font = self._manager_font("dejavuserif", title_px, bold=True)
        eyebrow_font = self._manager_font(
            "dejavusansmono", layout["eyebrow_px"], bold=True)
        tele_font = self._manager_font(
            "dejavusansmono", layout["tele_px"], bold=True)
        sub_font = self._manager_font(
            "dejavusansmono", max(8, int(layout["tele_px"] * 0.95)))

        raw_title = self._title
        if "\n" in raw_title:
            lines = [line for line in raw_title.split("\n") if line]
        elif layout["two_line"] and " " in raw_title:
            words = raw_title.split()
            k = max(1, len(words) // 2)
            lines = [" ".join(words[:k]), " ".join(words[k:])]
        else:
            lines = [raw_title]
        if not lines:
            lines = [DEFAULT_TITLE]

        title_items = []
        tx, ty = int(layout["title_xy"][0]), int(layout["title_xy"][1])
        line_gap = int(title_px * 1.02)
        title_w = 0
        for i, line in enumerate(lines):
            surf = text_surface(line, title_font, pal["ink"],
                                 layout["title_track"], 242)
            title_items.append((surf, tx, ty + i * line_gap))
            title_w = max(title_w, surf.get_width())
        last_y = ty + (len(lines) - 1) * line_gap
        eyebrow = None
        if self._hud_mode == "full":
            eyebrow = text_surface("SLOW WORLDS · FANTASY", eyebrow_font,
                                   pal["accent"],
                                   layout["eyebrow_px"] * 0.22, 150)
            ex, ey = layout["eyebrow_xy"]
            eyebrow = (eyebrow, int(ex), int(ey))

        tele_x, tele_y = layout["telemetry_xy"]
        tele_line = max(1, int(layout["tele_px"] * 1.7))
        telemetry = []
        line1 = text_surface("DUSK // MIGRATION 07", tele_font,
                             pal["ink_dim"], layout["tele_px"] * 0.12, 190)
        telemetry.append((line1, int(tele_x - line1.get_width()), int(tele_y)))
        line2 = text_surface(f"POD {self._pod_count:02d} · WESTWARD", tele_font,
                             pal["ink_dim"], layout["tele_px"] * 0.12, 190)
        line2e = text_surface(f"POD {self._pod_count:02d} · CROSSING THE MOON",
                              tele_font, pal["ink_dim"],
                              layout["tele_px"] * 0.12, 190)
        telemetry.append((line2, int(tele_x - line2.get_width()),
                          int(tele_y + tele_line)))
        telemetry.append((line2e, int(tele_x - line2e.get_width()),
                          int(tele_y + tele_line)))

        subtitle = None
        if self._hud_mode == "full" and self._subtitle:
            sub = text_surface(self._subtitle, sub_font, pal["ink_dim"],
                               layout["tele_px"] * 0.10, 160)
            subtitle = (sub, tx, int(last_y + title_px + 10))

        rule_y = int(last_y + title_px + 12)
        if layout["two_line"]:
            rule_w = min(title_w, int(340 * layout["ps"]))
        else:
            rule_w = title_w
        rules = [(tx, rule_y, rule_w,
                  mix(pal["accent"], pal["sky_top"], 0.55))]
        if layout["two_line"]:
            rules.append((tx, rule_y + 4, int(rule_w * 0.45),
                          mix(pal["ink_faint"], pal["sky_top"], 0.65)))

        self._hud = {
            "title": title_items,
            "eyebrow": eyebrow,
            "telemetry": telemetry,
            "subtitle": subtitle,
            "rules": rules,
        }
        rects = []
        for surf, x, y in title_items:
            rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
        if eyebrow is not None and self._hud_mode == "full":
            surf, x, y = eyebrow
            rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
        if self._hud_mode == "full":
            for surf, x, y in telemetry:
                rects.append(pygame.Rect(x, y, surf.get_width(),
                                         surf.get_height()))
        else:
            surf, x, y = telemetry[0]
            rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
        if subtitle is not None:
            surf, x, y = subtitle
            rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
        self._hud_rects = rects

    def _build(self, size):
        size = (int(size[0]), int(size[1]))
        if self._built_size == size and self._sky is not None:
            return
        self._clear_caches()
        self._screen_size = size
        self._layout = self._resolve_layout(size)
        self._preset = self._layout["preset"]
        W, H = size
        layout = self._layout
        pal = self._palette
        horizon = layout["horizon"]

        self._build_pod()
        self._speed_px = 1280.0 / max(1.0, self._crossing_seconds)
        max_tail = max(offset + length for offset, length, *_ in self._pod_specs)
        self._visible_exit = ((POD_CYCLE_START + max_tail) * W
                              / self._speed_px)
        self._cycle_length = max(120.0, self._visible_exit + self._cycle_gap)
        self._cycle_offset = (self._phase_frac * self._visible_exit) % self._cycle_length
        a_base = layout["pod"][0][0]
        a_len = layout["pod"][0][1]
        self._hero_at_cycle = ((POD_CYCLE_START - a_base) * W
                               / self._speed_px)
        moon_base = layout["moon"]["x"]
        self._eclipse_at_cycle = ((POD_CYCLE_START
                                   - (moon_base / W - A_HUMP * a_len))
                                  * W / self._speed_px)

        self._build_hud()
        self._beacon_sprite = build_beacon_sprite(pal)
        self._beacon_scaled = {}
        for r in (2, 3):
            size_px = max(14, int(14 + r * 9))
            self._beacon_scaled[r] = pygame.transform.smoothscale(
                self._beacon_sprite, (size_px, size_px))

        base_w, base_h = layout["base"]
        area = (W * H) / float(base_w * base_h)
        area_factor = max(0.25, min(2.0, area))
        star_count = int(layout["stars"] * self._star_density * area_factor)
        beacon_count = int(layout["beacons"] * min(1.0, self._star_density)
                           * area_factor)
        self._sky, self._beacons = build_sky(
            W, max(2, int(horizon)), pal,
            random.Random(self.seed ^ 0x57A2),
            self._preset, self._hud_rects, star_count, beacon_count)
        self._star_total = star_count

        sea_h = max(2, int(H - horizon))
        self._sea_base = vgrad(W, sea_h, [
            (0.00, pal["sea_top"]), (0.08, pal["sea_mid"]),
            (0.30, mix(pal["sea_mid"], pal["sea_bottom"], 0.45)),
            (0.68, mix(pal["sea_mid"], pal["sea_bottom"], 0.78)),
            (1.00, pal["sea_bottom"]),
        ])
        self._sea_base.blit(alpha_band(W, max(2, int(sea_h * 0.20)),
                                       pal["horizon"], 46, 0), (0, 0))
        self._sea_base.blit(alpha_band(W, max(2, int(sea_h * 0.07)),
                                       pal["horizon_hot"], 40, 0), (0, 0))
        self._sea_overlay = pygame.Surface((W, sea_h), pygame.SRCALPHA)
        self._glitter, self._swells, self._specks = build_sea_data(
            W, sea_h, pal, random.Random(self.seed ^ 0x5EA),
            self._preset, layout["moon"]["x"])

        self._mist_far = build_mist(W, H, horizon, pal,
                                    random.Random(self.seed ^ 0x315A),
                                    self._preset, 0.45)
        self._mist_near = build_mist(W, H, horizon, pal,
                                     random.Random(self.seed ^ 0x315B),
                                     self._preset, 1.0)
        self._moon_sprite, self._moon_half = build_moon_sprite(
            pal, layout["moon"]["r"], random.Random(self.seed ^ 0x300A),
            self._glow_strength)
        (self._boat_sprite, self._boat_anchor,
         self._boat_reflection) = build_boat_sprite(
            pal, layout["boat"]["w"], layout["boat"]["mast"],
            self._scale_reference)
        vignette, finish_overlay = build_finish(
            W, H, self._vignette, self._scanlines, True, self.seed)
        sky_h = max(2, int(horizon))
        if self._sky is not None:
            self._sky.blit(vignette.subsurface((0, 0, W, sky_h)), (0, 0))
        sea_h = max(2, int(H - horizon))
        if self._sea_base is not None:
            self._sea_base.blit(
                vignette.subsurface((0, int(horizon), W, sea_h)), (0, 0))
        self._finish_surface = finish_overlay

        self._built_size = size
        self._sync_scene()

    # ---------------------------------------------------------------- frame state

    def _sync_scene(self):
        if self._built_size is None or self._layout is None:
            return
        W, H = self._screen_size
        layout = self._layout
        horizon = layout["horizon"]
        cycle_t = (self._time + self._cycle_offset) % self._cycle_length
        a_start = POD_CYCLE_START * W - self._speed_px * cycle_t
        self._pod_x = a_start / max(1.0, W)
        visible = []
        for spec, body in zip(self._pod_specs, self._bodies):
            offset, length_frac, peak_frac = spec[0], spec[1], spec[2]
            start = a_start + offset * W
            length = length_frac * W
            peak = peak_frac * H
            body.update(start, length, peak, horizon, self._time)
            if start < W + 80 and start + length > -80:
                visible.append(body)
        self._visible_bodies = visible

        moon_x = layout["moon"]["x"]
        if self._moon_arc_seconds > 0.0:
            moon_x += (0.012 * W * math.sin(
                TAU * self._time / self._moon_arc_seconds + self._moon_phase))
        self._moon_x = moon_x
        self._moon_y = horizon - layout["moon"]["above"] - layout["moon"]["r"]
        eclipse = 0.0
        if self._moon and self._eclipse_seconds > 0.0 and self._bodies:
            a = self._bodies[0]
            hump = a.hump_x()
            r = layout["moon"]["r"]
            half = max(r * 1.4, self._speed_px * self._eclipse_seconds * 0.5)
            if half > 0.0:
                horiz = 1.0 - abs(hump - moon_x) / half
                if horiz > 0.0:
                    top = a.top_at(hump)
                    thick = a.thick_at(hump)
                    if top < self._moon_y < top + thick:
                        eclipse = min(1.0, horiz)
        self._eclipse = eclipse
        self._eclipse_active = eclipse > 0.08

    def handle_event(self, event):
        """The controller owns input; this mode has none."""

    def update(self, dt: float):
        if self.manager is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._time += dt
        self._update_quality(dt)
        self._update_meteor()

    def _update_quality(self, dt: float) -> None:
        if not self._auto_quality:
            return
        self._quality_ema += (dt - self._quality_ema) * 0.06
        target = self._quality
        if self._quality == "high":
            if self._quality_ema > (1.0 / 27.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        elif self._quality == "medium":
            if self._quality_ema > (1.0 / 16.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "low"
            elif self._quality_ema < (1.0 / 42.0):
                self._quality_timer += dt
                if self._quality_timer >= 6.0:
                    target = "high"
            else:
                self._quality_timer = 0.0
        else:
            if self._quality_ema < (1.0 / 30.0):
                self._quality_timer += dt
                if self._quality_timer >= 4.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        if target != self._quality:
            self._quality_timer = 0.0
            previous = self._quality
            self._quality = target
            self.diagnostic = f"auto quality {previous} -> {target}"
            print(f"[Leviathan] {self.diagnostic}")

    def _update_meteor(self) -> None:
        if self._active_meteor is not None:
            end = (self._active_meteor["start"]
                   + self._active_meteor["duration"])
            if self._time > end:
                self._active_meteor = None
                self._schedule_meteor()
            return
        if (self._meteor and self._meteor_seconds > 0.0
                and self._time >= self._next_meteor):
            self.start_meteor()

    def _schedule_meteor(self) -> None:
        if not self._meteor or self._meteor_seconds <= 0.0:
            self._next_meteor = float("inf")
            return
        rng = self._meteor_rng or random.Random(self.seed or 0)
        self._next_meteor = (self._time
                             + self._meteor_seconds * rng.uniform(0.65, 1.35))

    def start_meteor(self, progress: float = 0.0) -> None:
        if not self._meteor or self._meteor_seconds <= 0.0:
            return
        rng = self._meteor_rng or random.Random(self.seed or 0)
        base = self._layout["meteor"] if self._layout else LAYOUTS["ultrawide"]["meteor"]
        jx = rng.uniform(-0.018, 0.018)
        jy = rng.uniform(-0.012, 0.012)
        spec = {
            "start": (max(0.02, min(0.96, base["start"][0] + jx)),
                      max(0.02, min(0.96, base["start"][1] + jy))),
            "end": (max(0.02, min(0.98, base["end"][0] + jx)),
                    max(0.02, min(0.98, base["end"][1] + jy))),
            "length": base["length"] * rng.uniform(0.90, 1.10),
        }
        duration = self._meteor_duration * rng.uniform(0.85, 1.15)
        start = self._time - max(0.0, min(0.95, progress)) * duration
        self._active_meteor = {"start": start, "duration": duration,
                               "spec": spec}
        self._next_meteor = float("inf")
        self._meteor_count += 1

    def _meteor_now(self):
        if self._active_meteor is None:
            return None
        m = self._active_meteor
        p = (self._time - m["start"]) / max(0.01, m["duration"])
        if p < 0.0 or p > 1.0:
            return None
        return p, m["spec"]

    def _body_ss(self) -> int:
        return 2 if self._quality == "high" else 1

    def _reflection_slices(self) -> int:
        return {"low": 6, "medium": 10, "high": 16}.get(self._quality, 10)

    def _spout_detail(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}.get(self._quality, 1)

    def _bloom_strength(self) -> int:
        return 42 if self._quality == "high" else 0

    def _reflection_ratio(self) -> float:
        return {"ultrawide": 0.56, "portrait": 0.46,
                "landscape": 0.50, "square": 0.48}.get(self._preset, 0.50)

    # ---------------------------------------------------------------- render

    def render(self, screen):
        if self.error:
            self._draw_error(screen)
            return
        if self.manager is None:
            return
        if screen.get_size() != self._built_size:
            self._build(screen.get_size())
        self._sync_scene()
        W, H = screen.get_size()
        layout = self._layout
        pal = self._palette
        horizon = layout["horizon"]

        screen.blit(self._sky, (0, 0))
        self._draw_beacons(screen)
        meteor = self._meteor_now()
        if meteor is not None:
            p, spec = meteor
            draw_meteor(screen, W, H, pal, spec, p,
                        quality=2 if self._quality != "low" else 1)
        if self._moon and self._moon_sprite is not None:
            screen.blit(self._moon_sprite,
                        (int(self._moon_x - self._moon_half),
                         int(self._moon_y - self._moon_half)))
        screen.blit(self._sea_base, (0, int(horizon)))
        sea_h = max(1, int(H - horizon))
        draw_sea_live(self._sea_overlay, W, sea_h, pal, self._moon_x,
                      self._glitter, self._swells, self._specks,
                      self._time, self._swell_speed, self._preset,
                      moon_on=self._moon)
        draw_wakes_on(self._sea_overlay, W, sea_h, pal, self._visible_bodies)
        screen.blit(self._sea_overlay, (0, int(horizon)))
        if self._mist:
            drift = int((self._time * 0.5) % 16)
            screen.blit(self._mist_far,
                        (-16 + drift, int(horizon) - MIST_HORIZON))
        if self._show_reflections:
            for body in self._visible_bodies:
                draw_reflection(screen, body, pal, H,
                                self._reflection_ratio(),
                                self._reflection_slices())
        ss = self._body_ss()
        for index, body in enumerate(self._bodies):
            if body.start < W + 80 and body.start + body.length > -80:
                self._draw_body_layer(screen, index, body, pal, W, H, ss)
        if self._show_spouts:
            detail = self._spout_detail()
            for index, body in enumerate(self._visible_bodies):
                strength = 1.0 if index == 0 else 0.62
                draw_spout(screen, body, pal, detail, strength,
                           self._time)
        self._draw_reference(screen)
        if self._mist:
            drift = int((self._time * 0.5 + 8) % 16)
            screen.blit(self._mist_near,
                        (-16 + drift, int(horizon) - MIST_HORIZON))
        if self._eclipse_active:
            a = self._bodies[0] if self._bodies else None
            if a is not None:
                draw_eclipse_corona(screen, a,
                                    (self._moon_x, self._moon_y),
                                    layout["moon"]["r"], pal,
                                    self._eclipse,
                                    quality=2 if self._quality != "low" else 1)
        add_bloom(screen, self._bloom_strength(), self._glow_strength)
        if self._finish_surface is not None and self._quality == "high":
            screen.blit(self._finish_surface, (0, 0))
        self._draw_hud(screen)

    def _draw_body_layer(self, screen, index, body, pal, W, H, ss) -> None:
        bucket = int(self._time * 6.0)
        cache = self._body_layers[index] if index < len(self._body_layers) else None
        if (cache is not None and cache["bucket"] == bucket
                and cache["ss"] == ss
                and abs(body.start - cache["start"]) < 8):
            layer = cache["layer"]
            ox = cache["x0"] + int(round(body.start - cache["start"]))
            oy = cache["y0"]
        else:
            rendered = render_body_layer(body, pal, W, H,
                                         self._moon_x, ss)
            if rendered is None:
                return
            layer, ox, oy = rendered
            if index < len(self._body_layers):
                self._body_layers[index] = {
                    "bucket": bucket, "ss": ss, "start": body.start,
                    "layer": layer, "x0": ox, "y0": oy,
                }
        old_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(0, 0, W, int(body.horizon)))
        screen.blit(layer, (ox, oy))
        screen.set_clip(old_clip)

    def _draw_beacons(self, screen) -> None:
        if not self._beacons or not self._beacon_sprite:
            return
        for x, y, r, period, phase in self._beacons:
            a = int(118 * (0.66 + 0.34 * math.sin(
                TAU * self._time / period + phase)))
            if a <= 4:
                continue
            sprite = self._beacon_scaled.get(int(r))
            if sprite is None:
                continue
            sprite.set_alpha(a)
            screen.blit(sprite, (int(x - sprite.get_width() / 2),
                                 int(y - sprite.get_height() / 2)))

    def _draw_reference(self, screen) -> None:
        if self._boat_sprite is None:
            return
        layout = self._layout
        cx = layout["boat"]["x"]
        bob = (math.sin(TAU * self._time / 5.5 + self._boat_phase) * 2.0
               if self._scale_reference == "boat" else 0.0)
        ax, ay = self._boat_anchor
        screen.blit(self._boat_sprite,
                    (int(cx - ax), int(layout["horizon"] - ay + bob)))
        if self._boat_reflection is not None:
            screen.blit(self._boat_reflection,
                        (int(cx - ax), int(layout["horizon"] + 2)))

    def _draw_hud(self, screen) -> None:
        if not self._hud or self._hud_mode == "none":
            return
        for x, y, w, col in self._hud.get("rules", []):
            pygame.draw.line(screen, col, (x, y), (x + w, y), 1)
        for surf, x, y in self._hud.get("title", []):
            screen.blit(surf, (x, y))
        if self._hud_mode == "full":
            eyebrow = self._hud.get("eyebrow")
            if eyebrow is not None:
                screen.blit(eyebrow[0], (eyebrow[1], eyebrow[2]))
            subtitle = self._hud.get("subtitle")
            if subtitle is not None:
                screen.blit(subtitle[0], (subtitle[1], subtitle[2]))
            tele = self._hud.get("telemetry", [])
            if tele:
                screen.blit(tele[0][0], (tele[0][1], tele[0][2]))
                if self._eclipse_active and len(tele) >= 3:
                    screen.blit(tele[2][0], (tele[2][1], tele[2][2]))
                elif len(tele) >= 2:
                    screen.blit(tele[1][0], (tele[1][1], tele[1][2]))
        else:
            tele = self._hud.get("telemetry", [])
            if tele:
                screen.blit(tele[0][0], (tele[0][1], tele[0][2]))

    def _draw_error(self, screen) -> None:
        W, H = screen.get_size()
        screen.fill((5, 9, 9))
        font = self._manager_font("dejavusansmono", max(11, min(22, W // 44)),
                                  bold=True)
        small = self._manager_font("dejavusansmono",
                                   max(9, min(15, W // 74)))
        title = font.render("LEVIATHAN PASSAGE", True, (222, 228, 210))
        screen.blit(title, (max(12, W // 24), max(12, H // 12)))
        message = self.error_message or "configuration error"
        words = message.split()
        lines = []
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if small.size(trial)[0] > W * 0.78 and current:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        y = max(12, H // 12) + font.get_height() + 12
        for line in lines[:6]:
            glyph = small.render(line, True, (218, 168, 110))
            screen.blit(glyph, (max(12, W // 24), y))
            y += small.get_height() + 4

    def stats(self):
        if self._built_size is not None:
            self._sync_scene()
        positions = [(round(b.start, 2), round(b.peak, 2))
                     for b in self._visible_bodies]
        return {
            "preset": self._preset,
            "seed": self.seed,
            "pod": self._pod_count,
            "quality": self._quality,
            "eclipse": round(self._eclipse, 3),
            "eclipse_active": self._eclipse_active,
            "meteor": self._active_meteor is not None,
            "meteor_count": self._meteor_count,
            "positions": positions,
            "silhouette": [round(b.top_min, 2) for b in self._bodies],
            "stars": self._star_total,
            "beacons": len(self._beacons),
            "time": round(self._time, 3),
            "size": self._screen_size,
        }

    def seek(self, cycle_seconds: float) -> None:
        """Set the clock so the pod is at a chosen cycle time (previews/tests)."""
        if self._built_size is None:
            return
        self._time = ((float(cycle_seconds) - self._cycle_offset)
                      % self._cycle_length)
        self._active_meteor = None
        self._schedule_meteor()
        self._sync_scene()

    def hero_time(self) -> float:
        """Cycle time at which the hero still is composed."""
        return self._hero_at_cycle

    def eclipse_time(self) -> float:
        """Cycle time at which the largest hump reaches the base moon x."""
        return self._eclipse_at_cycle

    def force_meteor(self, progress: float = 0.62) -> None:
        self.start_meteor(progress)
