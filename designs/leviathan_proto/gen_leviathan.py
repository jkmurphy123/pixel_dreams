#!/usr/bin/env python3
"""Art-direction prototype: Leviathan Passage (Slow Worlds 5.14).

This is a *design* script, not the mode.  It settles the two-orientation
composition, the palette and the creature treatment before
``modes/leviathan_mode.py`` is written, and it writes the review stills in
``screenshots/leviathan/``.

The card asks for a dusk sea, a pod of leviathans crossing a low horizon, mist,
a low moon, a small boat for scale, and one signature event: the largest
leviathan crossing the moon and eclipsing it.

The scene is a pure function of ``(seed, layout, palette, moment)``.  The stills
are rendered at 2x/3x and downsampled so the thin rim light and the waterline
mist can be judged fairly.  Everything is procedural pygame: no assets, no
network, no numpy/PIL.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/leviathan_proto/gen_leviathan.py
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/leviathan_proto/gen_leviathan.py --only strip
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
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "leviathan")

TAU = math.tau

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

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


def mul(c: RGB, factor: float) -> RGB:
    return (clamp8(c[0] * factor), clamp8(c[1] * factor),
            clamp8(c[2] * factor))


# ---------------------------------------------------------------------------
# Palettes.  "dusk" is the card default and is keyed to the Moon & Moss family
# in SLOW_WORLDS 4.1: near-black green, moss structure, amber accent, pale
# bone glow.  "bone" and "ember" change the mood, never the layout.
# ---------------------------------------------------------------------------

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
# layouts.  The strip and the portrait are separate compositions, not crops.
# ---------------------------------------------------------------------------

LAYOUTS = {
    "strip": {
        "size": (1280, 400),
        "ss": 3,
        "horizon": 0.600,
        "moon": {"x": 0.552, "r": 20.0, "above": 42.0},
        "boat": {"x": 0.515, "w": 25.0, "mast": 30.0},
        "meteor": {"start": (0.530, 0.220), "end": (0.680, 0.400),
                   "length": 0.110},
        "pod": (
            # start x, length, peak (all fractions of W / H), phase, variant
            (0.040, 0.360, 0.235, 0.11, 0),
            (0.410, 0.100, 0.060, 0.53, 2),
            (0.595, 0.380, 0.170, 0.79, 1),
        ),
        "spouts": (0, 1, 2),
        "title_size": 29,
        "title_tracking": 1.6,
        "title_xy": (42, 46),
        "eyebrow_size": 10,
        "eyebrow_xy": (43, 26),
        "telemetry_size": 11,
        "telemetry_xy": (1280 - 42, 30),
        "title_lines": None,
        "corner": 80,          # controller watermark width, bottom-left
    },
    "portrait": {
        "size": (1080, 1920),
        "ss": 2,
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
        "spouts": (0, 1, 2),
        "title_size": 84,
        "title_tracking": 3.0,
        "title_xy": (72, 152),
        "eyebrow_size": 15,
        "eyebrow_xy": (74, 120),
        "telemetry_size": 16,
        "telemetry_xy": (1080 - 72, 134),
        "title_lines": ("LEVIATHAN", "PASSAGE"),
        "corner": 80,
    },
}


# ---------------------------------------------------------------------------
# cached soft sprites and gradients
# ---------------------------------------------------------------------------

_SOFT_CACHE: dict[tuple, pygame.Surface] = {}
_WHITE_SOFT: pygame.Surface | None = None


def _soft_master(color: RGB, alpha: int, power: float) -> pygame.Surface:
    key = (color, alpha, power)
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


def blit_soft(dest: pygame.Surface, cx: float, cy: float, w: float, h: float,
              color: RGB, alpha: int, power: float = 2.0) -> None:
    """Blit a soft elliptical light/mist sprite centred on (cx, cy)."""
    w = max(2, int(w))
    h = max(2, int(h))
    master = _soft_master(color, alpha, power)
    scaled = pygame.transform.smoothscale(master, (w, h)) if (w, h) != (192, 192) else master
    dest.blit(scaled, (int(cx - w / 2), int(cy - h / 2)))


def vgrad(w: int, h: int, stops: list[tuple[float, RGB]],
          srcalpha: bool = False) -> pygame.Surface:
    """Vertical gradient surface; stops are (0..1, colour)."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA if srcalpha else 0)
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


def alpha_band(w: int, h: int, color: RGB, alpha_top: int,
               alpha_bottom: int) -> pygame.Surface:
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        a = clamp8(alpha_top + (alpha_bottom - alpha_top) * t)
        pygame.draw.line(surf, (*color, a), (0, y), (w, y))
    return surf


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def catmull_rom(points: list[tuple[float, float]],
                samples: int = 18) -> list[tuple[float, float]]:
    """Centripetal-ish Catmull-Rom through the given points (x is monotonic)."""
    padded = [points[0]] + list(points) + [points[-1]]
    out: list[tuple[float, float]] = []
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


# The canonical back: a low head/shoulder hump, a long saddle, a big main
# hump and a tail that lifts out of the water into a thin fluke.
# The canonical serpent.  The spine rises for the head, dips under the
# waterline for the neck, lifts two humps and finally a whip tail.  The
# thickness table gives the tube its mass: heavy through the back, thin at the
# snout and the tail.  Both are sampled through the same Catmull-Rom helper, so
# the silhouette is one continuous animal, not a row of hills.
SPINE = [
    (0.000, 0.340),
    (0.025, 0.460),
    (0.050, 0.550),
    (0.085, 0.580),
    (0.115, 0.530),
    (0.145, 0.330),
    (0.175, 0.020),
    (0.200, -0.100),
    (0.240, -0.030),
    (0.300, 0.150),
    (0.360, 0.400),
    (0.410, 0.500),
    (0.460, 0.460),
    (0.510, 0.280),
    (0.550, 0.020),
    (0.585, -0.100),
    (0.625, -0.020),
    (0.675, 0.220),
    (0.725, 0.550),
    (0.775, 0.720),
    (0.820, 0.700),
    (0.860, 0.550),
    (0.895, 0.300),
    (0.925, 0.020),
    (0.950, -0.060),
    (0.970, 0.020),
    (0.985, 0.100),
    (1.000, 0.120),
]

THICK = [
    (0.000, 0.190),
    (0.025, 0.270),
    (0.050, 0.320),
    (0.085, 0.310),
    (0.115, 0.270),
    (0.145, 0.230),
    (0.180, 0.190),
    (0.240, 0.240),
    (0.300, 0.300),
    (0.360, 0.360),
    (0.410, 0.380),
    (0.460, 0.360),
    (0.510, 0.300),
    (0.550, 0.240),
    (0.585, 0.200),
    (0.625, 0.220),
    (0.675, 0.300),
    (0.725, 0.360),
    (0.775, 0.370),
    (0.820, 0.350),
    (0.860, 0.300),
    (0.895, 0.230),
    (0.925, 0.160),
    (0.950, 0.120),
    (0.970, 0.080),
    (0.985, 0.040),
    (1.000, 0.008),
]


def interp(points: list[tuple[float, float]], x: float) -> float:
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


class Body:
    """One leviathan: a serpentine spine sampled in scene pixels."""

    def __init__(self, start: float, length: float, peak: float,
                 horizon: float, phase: float, variant: int,
                 rng: random.Random):
        self.start = start
        self.length = length
        self.peak = peak
        self.horizon = horizon
        self.phase = phase
        self.variant = variant
        self.rng = rng
        self.spout_t = 0.055
        # Per-animal variation: a few centimetres on the hump heights, never
        # enough to break the species.
        wobble = [rng.uniform(-0.018, 0.018) for _ in SPINE]
        anchors = [(x, y + wobble[i]) for i, (x, y) in enumerate(SPINE)]
        self.spine = catmull_rom(anchors, 14)
        self.top: list[tuple[float, float]] = []
        self.bottom: list[tuple[float, float]] = []
        for x, y in self.spine:
            wave = 0.010 * math.sin(TAU * (x * 1.35 + phase))
            cy = horizon - peak * (y + wave)
            half = max(0.4, peak * interp(THICK, x) * 0.5)
            self.top.append((start + x * length, cy - half))
            self.bottom.append((start + x * length, cy + half))
        self.tip_x = self.top[-1][0]
        self.top_min = min(p[1] for p in self.top)
        self.spout_x = start + self.spout_t * length

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

    def polygon(self) -> list[tuple[float, float]]:
        # top contour left-to-right, then the underside right-to-left
        return list(self.top) + list(reversed(self.bottom))


# ---------------------------------------------------------------------------
# scene pieces
# ---------------------------------------------------------------------------

def draw_sky(surface, W, H, horizon, pal, rng, layout_name, hud_rects,
             sky_time: float = 0.0):
    sky_h = max(2, int(horizon))
    stops = [
        (0.00, pal["sky_top"]),
        (0.22, pal["sky_high"]),
        (0.48, pal["sky_mid"]),
        (0.72, pal["sky_low"]),
        (0.88, mix(pal["sky_low"], pal["horizon"], 0.45)),
        (0.96, mix(pal["sky_low"], pal["horizon"], 0.82)),
        (1.00, pal["horizon"]),
    ]
    surface.blit(vgrad(W, sky_h, stops), (0, 0))

    # faint high cloud bands, stretched soft sprites
    overlay = pygame.Surface((W, sky_h), pygame.SRCALPHA)
    cloud_count = 4 if layout_name == "strip" else 6
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
    # two long, low bands catching the last warm light
    for i in range(2):
        cy = sky_h * (0.76 + 0.085 * i) + rng.uniform(-6, 6)
        blit_soft(overlay, W * rng.uniform(0.25, 0.75), cy,
                  W * rng.uniform(0.55, 0.85), max(5, sky_h * 0.016),
                  mix(pal["cloud"], pal["horizon_hot"], 0.45),
                  rng.randint(9, 18), 2.4)
    surface.blit(overlay, (0, 0))

    # A real star field: a mostly small, cool field, a handful of bright
    # stars with a cross glint, and a slow twinkle.  The base is a still
    # layer; the mode will redraw only the bright twinklers.
    star_layer = pygame.Surface((W, sky_h), pygame.SRCALPHA)
    count = 460 if layout_name == "strip" else 950
    for _ in range(count):
        x = rng.uniform(0, W)
        y = rng.uniform(0, sky_h * 0.94)
        if y > sky_h * 0.62 and rng.random() < 0.55:
            continue
        if y > sky_h * 0.84 and rng.random() < 0.70:
            continue
        if any(rect.inflate(24, 12).collidepoint(x, y) for rect in hud_rects):
            continue
        roll = rng.random()
        if roll < 0.835:
            r, base = 1, rng.randint(34, 126)
        elif roll < 0.972:
            r, base = 2, rng.randint(66, 174)
        else:
            r, base = 3, rng.randint(112, 232)
        period = rng.uniform(3.5, 9.0)
        phase = rng.uniform(0, TAU)
        twinkle = 0.66 + 0.34 * math.sin(TAU * sky_time / period + phase)
        a = max(8, int(base * twinkle))
        col = pal["star"] if rng.random() < 0.34 else pal["star_dim"]
        pygame.draw.circle(star_layer, (*col, a), (int(x), int(y)), r)
        if r >= 2:
            blit_soft(star_layer, x, y, r * 11, r * 11, col,
                      max(6, a // 4), 2.0)
        if r == 3:
            span = r * 3
            pygame.draw.line(star_layer, (*col, max(10, a // 2)),
                             (int(x - span), int(y)), (int(x + span), int(y)), 1)
            pygame.draw.line(star_layer, (*col, max(10, a // 2)),
                             (int(x), int(y - span)), (int(x), int(y + span)), 1)
    # a handful of deliberate bright stars: the eye needs a few anchors in a
    # field this sparse, and the mode will twinkle these per frame
    beacons = 7 if layout_name == "strip" else 16
    placed = 0
    guard = 0
    beacon_positions: list[tuple[float, float]] = []
    while placed < beacons and guard < beacons * 40:
        guard += 1
        x = rng.uniform(W * 0.04, W * 0.96)
        y = rng.uniform(sky_h * 0.06, sky_h * 0.78)
        if any(rect.inflate(30, 16).collidepoint(x, y) for rect in hud_rects):
            continue
        if any(math.hypot(x - bx, y - by) < W * 0.055
               for bx, by in beacon_positions):
            continue
        beacon_positions.append((x, y))
        placed += 1
        col = mix(pal["star"], pal["moon"], 0.32)
        blit_soft(star_layer, x, y, 34, 34, col, 26, 2.0)
        pygame.draw.circle(star_layer, (*col, 150), (int(x), int(y)), 2)
        pygame.draw.circle(star_layer, (*col, 235), (int(x), int(y)), 1)
        span = 7
        pygame.draw.line(star_layer, (*col, 120),
                         (int(x - span), int(y)), (int(x + span), int(y)), 1)
        pygame.draw.line(star_layer, (*col, 120),
                         (int(x), int(y - span)), (int(x), int(y + span)), 1)
    surface.blit(star_layer, (0, 0))


def draw_meteor(surface, W, H, pal, spec, progress: float, quality: int = 2):
    """One short, soft streak.  It is an event, not a permanent feature."""
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
    # fade in fast, fade out at the end; never a hard flash
    fade = min(1.0, progress / 0.10) * min(1.0, (1.0 - progress) / 0.20)
    fade = max(0.0, fade) ** 0.7
    head_col = mix(pal["star"], (255, 255, 255), 0.50)
    # a faint, wide aura keeps the streak from reading as a scratch
    pygame.draw.line(surface, (*head_col, int(15 * fade)), (tx, ty),
                     (hx, hy), max(2, int(2.4 * quality)))
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
    # a soft head glow and a crisp core
    blit_soft(surface, hx, hy, 13.0 * quality, 13.0 * quality,
              pal["moon"], int(66 * fade), 2.0)
    pygame.draw.circle(surface, (*head_col, int(238 * fade)),
                       (int(hx), int(hy)), max(1, int(quality * 0.62)))


def draw_moon(surface, W, H, horizon, pal, moon, rng):
    cx = W * moon["x"]
    r = float(moon["r"])
    cy = horizon - moon["above"] - r

    # halo first: it will remain visible around a crossing body (the eclipse)
    blit_soft(surface, cx, cy, r * 11, r * 11, pal["moon_glow"], 16, 2.0)
    blit_soft(surface, cx, cy, r * 5.2, r * 5.2, pal["moon_glow"], 28, 2.2)
    blit_soft(surface, cx, cy, r * 2.6, r * 2.6, pal["moon_glow"], 46, 2.4)
    blit_soft(surface, cx, cy, r * 1.55, r * 1.55, pal["moon"], 72, 2.2)

    # disc: concentric colour steps read as a soft sphere
    steps = max(12, int(r))
    for i in range(steps, 0, -1):
        t = i / steps
        col = mix(pal["moon"], pal["moon_edge"], t ** 1.5)
        pygame.draw.circle(surface, col, (int(cx), int(cy)), int(r * t))

    # a hint of maria and a bright limb
    craters = pygame.Surface((int(r * 4), int(r * 4)), pygame.SRCALPHA)
    ox = oy = int(r * 2)
    for _ in range(7):
        ang = rng.uniform(0, TAU)
        dist = rng.uniform(0, r * 0.62)
        ex = ox + math.cos(ang) * dist
        ey = oy + math.sin(ang) * dist * 0.9
        ew = r * rng.uniform(0.16, 0.40)
        eh = ew * rng.uniform(0.55, 1.0)
        pygame.draw.ellipse(craters, (*pal["moon_dark"], rng.randint(14, 28)),
                            (int(ex - ew / 2), int(ey - eh / 2),
                             int(ew), int(eh)))
    # only keep the crater layer inside the disc
    mask = pygame.Surface((int(r * 4), int(r * 4)), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (ox, oy), int(r))
    craters.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(craters, (int(cx - r * 2), int(cy - r * 2)))

    pygame.draw.arc(surface, mix(pal["moon"], (255, 255, 255), 0.35),
                    (int(cx - r), int(cy - r), int(r * 2), int(r * 2)),
                    math.radians(70), math.radians(190), max(1, int(r * 0.06)))
    return cx, cy


def draw_sea(surface, W, H, horizon, pal, moon_xy, rng, layout_name):
    sea_h = max(2, int(H - horizon))
    sea = vgrad(W, sea_h, [
        (0.00, pal["sea_top"]),
        (0.08, pal["sea_mid"]),
        (0.30, mix(pal["sea_mid"], pal["sea_bottom"], 0.45)),
        (0.68, mix(pal["sea_mid"], pal["sea_bottom"], 0.78)),
        (1.00, pal["sea_bottom"]),
    ])
    surface.blit(sea, (0, int(horizon)))

    # the sky's warm band, reflected on the top of the water
    surface.blit(alpha_band(W, max(2, int(sea_h * 0.20)),
                            pal["horizon"], 46, 0), (0, int(horizon)))
    surface.blit(alpha_band(W, max(2, int(sea_h * 0.07)),
                            pal["horizon_hot"], 40, 0), (0, int(horizon)))

    moon_x = moon_xy[0]
    overlay = pygame.Surface((W, sea_h), pygame.SRCALPHA)

    # moon path: a loose column of short horizontal glints, widening with
    # distance; the brightest handful sit right under the disc
    count = 170 if layout_name == "strip" else 230
    for i in range(count):
        t = i / count
        if rng.random() < 0.16:
            continue
        y = 2 + (t ** 1.40) * sea_h * 0.80 + rng.uniform(-1.6, 1.6)
        spread = 12 + t * (W * 0.105)
        x = moon_x + rng.gauss(0, spread * 0.52)
        if not (0 <= x <= W):
            continue
        dash = (3 + t * (34 if layout_name == "strip" else 52)) \
            * rng.uniform(0.35, 1.45)
        a = int((138 if layout_name == "strip" else 146) * (1 - t) ** 1.35
                * rng.uniform(0.65, 1.05))
        if a <= 2:
            continue
        pygame.draw.line(overlay, (*pal["moon"], a),
                         (x - dash / 2, y), (x + dash / 2, y), 1)
    blit_soft(overlay, moon_x, sea_h * 0.24, W * 0.34, sea_h * 0.85,
              pal["moon_glow"], 42, 2.0)
    # a hot horizontal knot at the waterline under the moon
    blit_soft(overlay, moon_x, 4, W * 0.16, sea_h * 0.12,
              pal["moon"], 100, 2.4)

    # long swell lines, spacing opening with distance
    y = 6.0
    step = 4.5 if layout_name == "strip" else 8.0
    index = 0
    while y < sea_h:
        t = y / sea_h
        amp = 0.7 + t * (3.8 if layout_name == "strip" else 6.8)
        freq = 0.005 + rng.uniform(0.0, 0.004)
        phase = rng.uniform(0, TAU)
        pts = []
        for x in range(-8, W + 9, 9):
            yy = (y + math.sin(x * freq + phase) * amp
                  + math.sin(x * freq * 2.3 + phase * 1.7) * amp * 0.35)
            pts.append((x, yy))
        a = int((38 if layout_name == "strip" else 32) * (1.0 - t) ** 1.0) + 6
        col = mix(pal["swell_far"], pal["swell_near"], t)
        pygame.draw.lines(overlay, (*col, a), False, pts, 1)
        # an occasional brighter crest near the moon's column
        if index % 3 == 1 and rng.random() < 0.75:
            cx = moon_x + rng.gauss(0, W * 0.11)
            half = (18 + t * 90) * rng.uniform(0.5, 1.0)
            crest = []
            for x in range(int(cx - half), int(cx + half) + 3, 3):
                if not (0 <= x <= W):
                    continue
                yy = (y + math.sin(x * freq + phase) * amp
                      + math.sin(x * freq * 2.3 + phase * 1.7) * amp * 0.35)
                crest.append((x, yy))
            if len(crest) > 1:
                pygame.draw.lines(overlay, (*pal["moon"], min(90, a * 3 + 10)),
                                  False, crest, 1)
        y += step
        step *= 1.13
        index += 1

    # broad, very soft currents: the water is not a flat field
    for i, t in enumerate((0.22, 0.48, 0.74)):
        blit_soft(overlay, W * (0.32 + 0.17 * i), sea_h * t,
                  W * 0.9, sea_h * 0.12, pal["swell_near"], 6, 2.2)

    # sparse specular glints away from the moon path
    for _ in range(90 if layout_name == "strip" else 130):
        t = rng.random() ** 0.7
        y = 6 + t * sea_h * 0.9
        x = rng.uniform(0, W)
        if abs(x - moon_x) < W * 0.06:
            continue
        dash = rng.uniform(2, 9)
        a = rng.randint(6, 20)
        pygame.draw.line(overlay, (*pal["swell_far"], a),
                         (x - dash / 2, y), (x + dash / 2, y), 1)

    # a fine second layer of ripples, only in the near half
    y = sea_h * 0.42
    while y < sea_h:
        t = (y - sea_h * 0.42) / (sea_h * 0.58)
        a = int(7 * (1.0 - t) ** 1.2) + 2
        phase = rng.uniform(0, TAU)
        pts = [(x, y + math.sin(x * 0.020 + phase) * (1.2 + t * 2.4))
               for x in range(0, W + 9, 12)]
        pygame.draw.lines(overlay, (*pal["swell_near"], a), False, pts, 1)
        y += 11 + t * 10

    surface.blit(overlay, (0, int(horizon)))


def draw_wakes(surface, W, H, horizon, pal, bodies, rng):
    """Long, low wake lines: the only evidence that the sea notices."""
    overlay = pygame.Surface((W, int(H - horizon) + 8), pygame.SRCALPHA)
    for body in bodies:
        tail_x = body.tip_x
        # these animals face left; the wake trails right, behind the tail
        start = tail_x + body.length * 0.02
        length = body.length * (0.55 + 0.15 * rng.random())
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
                a = int(32 * (1.0 - k * 0.26))
                pygame.draw.lines(overlay, (*pal["wake"], a), False, pts, 1)
    surface.blit(overlay, (0, int(horizon)))


def draw_body(surface, body: Body, pal, W, H, moon_x, rng, quality=2):
    """Draw one serpent into a bbox surface, clipped at the waterline."""
    x0 = max(0, int(body.start - 10))
    x1 = min(W, int(body.tip_x + 12))
    y0 = max(0, int(body.top_min - 12))
    y1 = min(H, int(body.horizon + 3))
    bw, bh = x1 - x0, y1 - y0
    if bw <= 2 or bh <= 2:
        return None
    layer = pygame.Surface((bw, bh), pygame.SRCALPHA)
    ox, oy = x0, y0

    poly = [(x - ox, y - oy) for x, y in body.polygon()]
    mask = pygame.Surface((bw, bh), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), poly)
    grad = vgrad(bw, bh, [
        (0.00, pal["body_hi"]),
        (0.26, pal["body"]),
        (0.78, pal["body"]),
        (1.00, pal["body_low"]),
    ], srcalpha=True)
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    layer.blit(grad, (0, 0))

    top = body.top
    horizon = body.horizon
    rib_col = mix(pal["body"], pal["rim"], 0.18)

    # Jaw: a shallow line along the lower front of the head, enough to read
    # as a mouth at one metre without drawing a face.
    hx = body.start + 0.010 * body.length
    hx2 = body.start + 0.070 * body.length
    if body.top_at(hx2) < body.horizon - 8:
        jaw = [(hx - ox, body.top_at(hx) - oy + body.thick_at(hx) * 0.62),
               (hx2 - ox, body.top_at(hx2) - oy + body.thick_at(hx2) * 0.42)]
        pygame.draw.line(layer, (*mix(pal["body"], pal["rim"], 0.45), 42),
                         jaw[0], jaw[1], 1)

    # Rim light: a thin, broken catch on the water-facing edge, warmer toward
    # the moon.  The far side of each hump stays dark, so the animal does not
    # acquire a drawn outline.
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
                         (x - ox, y - oy), (nx - ox, ny - oy),
                         max(1, int(0.55 * quality)))
        if facing > 0.5 and a > 24:
            pygame.draw.line(layer, (*col, int(a * 0.20)),
                             (x - ox, y - oy - 1), (nx - ox, ny - oy - 1),
                             max(2, int(1.4 * quality)))

    # The eye: a dark socket with the last warm glint, set into the head.
    ex = body.start + 0.055 * body.length
    ey = body.top_at(ex) + body.peak * 0.070
    er = max(1, int(body.peak * 0.020))
    pygame.draw.circle(layer, (0, 0, 0, 140),
                       (int(ex - ox), int(ey - oy)), er + 2)
    pygame.draw.circle(layer, (*pal["rim_hot"], 120),
                       (int(ex - ox), int(ey - oy)), er)

    old_clip = surface.get_clip()
    surface.set_clip(pygame.Rect(0, 0, W, int(horizon)))
    surface.blit(layer, (ox, oy))
    surface.set_clip(old_clip)
    return layer




def draw_reflection(surface, body: Body, pal, W, H, rng, layout_name):
    sea_h = H - body.horizon
    top_h = max(2.0, body.horizon - body.top_min + 2)
    reflect_h = min(sea_h * (0.56 if layout_name == "strip" else 0.46),
                    body.peak * 0.66, top_h)
    if reflect_h < 4:
        return
    x0 = max(0, int(body.start))
    x1 = min(W, int(body.tip_x + 4))
    bw = x1 - x0
    if bw <= 2:
        return
    # The above-water silhouette, mirrored.  Points in the submerged dips map
    # above the layer and are simply not part of the reflection.
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

    slices = 20 if layout_name == "strip" else 28
    slice_h = max(1, flip.get_height() // slices)
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
        if i % 3 == 0:
            pygame.draw.line(surface, mix(pal["sea_mid"], pal["swell_far"], 0.35),
                             (x0 - 4, body.horizon + sy),
                             (x1 + 4, body.horizon + sy), 1)
    # warm contact glints and a little spray where each hump meets the sea
    for t in (0.20, 0.50, 0.86):
        gx = body.start + t * body.length
        if not (0 <= gx <= W):
            continue
        pygame.draw.line(surface, mix(pal["rim"], pal["sea_top"], 0.82),
                         (gx - body.length * 0.02, body.horizon),
                         (gx + body.length * 0.02, body.horizon), 1)
        blit_soft(surface, gx, body.horizon - 2, body.length * 0.10,
                  max(5, body.peak * 0.10), pal["mist"], 12, 2.0)




def draw_spout(surface, body: Body, pal, rng, strength=1.0):
    x = body.spout_x
    base = body.top_at(x) + body.peak * 0.01
    height = body.peak * (0.58 * strength)
    drift = body.peak * 0.20
    # plume of soft puffs
    for i in range(16):
        t = i / 15.0
        px = x + t * drift + math.sin(t * 4.5) * body.peak * 0.02
        py = base - t * height
        size = body.peak * (0.05 + 0.16 * t)
        a = int(46 * (1.0 - t) ** 1.3 * strength)
        blit_soft(surface, px, py, size * 3.4, size * 2.6,
                  pal["mist"], a, 1.8)
    blit_soft(surface, x, base - height * 0.08, body.peak * 0.12,
              body.peak * 0.10, pal["mist_hot"], 46, 1.8)


def draw_boat(surface, W, H, horizon, pal, boat):
    cx = W * boat["x"]
    w = boat["w"]
    y = horizon + 1.0
    hull = [(cx - w / 2, y - w * 0.07),
            (cx - w * 0.30, y + w * 0.16),
            (cx + w * 0.30, y + w * 0.16),
            (cx + w / 2, y - w * 0.07)]
    pygame.draw.polygon(surface, (*pal["boat"], 255), hull)
    pygame.draw.lines(surface, mix(pal["sail"], pal["sea_top"], 0.45), False,
                      [hull[0], hull[1], hull[2], hull[3]], 1)
    mast_top = y - boat["mast"]
    pygame.draw.line(surface, (*pal["boat"], 255),
                     (cx + w * 0.04, y - 1), (cx + w * 0.04, mast_top),
                     max(1, int(w / 9)))
    sail = [(cx + w * 0.04, mast_top + 1),
            (cx + w * 0.04, y - w * 0.20),
            (cx - w * 0.34, y - w * 0.26)]
    pygame.draw.polygon(surface, mix(pal["sail"], pal["sea_top"], 0.48), sail)
    pygame.draw.lines(surface, mix(pal["sail"], pal["horizon"], 0.30), False,
                      sail, 1)
    # lantern at the stern
    lx, ly = cx + w * 0.33, y - w * 0.18
    blit_soft(surface, lx, ly, w * 1.4, w * 1.4, pal["lantern"], 66, 2.0)
    pygame.draw.circle(surface, (*pal["lantern"], 220), (int(lx), int(ly)),
                       max(1, int(w * 0.045)))
    # reflection: a thin vertical smear and a lantern glint
    refl = pygame.Surface((int(w * 2), int(w * 1.8) + 2), pygame.SRCALPHA)
    for i in range(int(w * 1.4)):
        t = i / max(1, int(w * 1.4))
        a = int(30 * (1 - t) ** 1.4)
        pygame.draw.line(refl, (*pal["boat"], a),
                         (int(w * 0.85 - t * 2), i),
                         (int(w * 1.15 + t * 2), i), 1)
    surface.blit(refl, (int(cx - w), int(y + 2)))
    blit_soft(surface, lx, y + 3, w * 0.8, w * 0.8,
              pal["lantern"], 40, 2.0)


def draw_mist(surface, W, H, horizon, pal, rng, layout_name, amount=1.0):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    band_w = W * (1.7 if layout_name == "strip" else 1.5)
    # three horizontal bands, one above, one on, one below the waterline
    for dy, h, a in ((-26, 44, 54), (-8, 30, 76), (12, 34, 46)):
        blit_soft(overlay, W * 0.5, horizon + dy, band_w, h * 2.2,
                  pal["mist"], int(a * amount), 2.1)
    blit_soft(overlay, W * 0.52, horizon - 6, W * 0.9, 30,
              pal["mist_hot"], int(26 * amount), 2.3)
    pygame.draw.line(overlay, (*pal["mist_hot"], int(34 * amount)),
                     (0, horizon), (W, horizon), 2)
    # drifting wisps
    count = 12 if layout_name == "strip" else 18
    for _ in range(count):
        cx = rng.uniform(-W * 0.10, W * 1.10)
        cy = horizon + rng.uniform(-26, 22)
        cw = W * rng.uniform(0.14, 0.36)
        ch = rng.uniform(8, 26)
        a = rng.randint(10, 22)
        col = pal["mist_hot"] if rng.random() < 0.35 else pal["mist"]
        blit_soft(overlay, cx, cy, cw, ch * 2.0, col, int(a * amount), 2.0)
    surface.blit(overlay, (0, 0))


def draw_horizon_glow(surface, W, horizon, pal, moon_x):
    glow = pygame.Surface((W, max(2, int(horizon * 0.45))), pygame.SRCALPHA)
    blit_soft(glow, W * 0.5, glow.get_height(), W * 1.2,
              glow.get_height() * 1.6, pal["horizon_hot"], 26, 2.0)
    blit_soft(glow, moon_x, glow.get_height(), W * 0.26,
              glow.get_height() * 0.9, pal["moon_glow"], 34, 2.0)
    surface.blit(glow, (0, int(horizon) - glow.get_height()))


def add_eclipse_corona(surface, body: Body, W, horizon, pal, moon, moon_xy):
    """A thin bright limb over the crossing back, plus a soft spill above it."""
    cx, cy = moon_xy
    r = moon["r"]
    top = body.top
    segment = [(x, y) for x, y in top if abs(x - cx) < r * 2.4]
    if len(segment) < 2:
        return
    for i in range(len(segment) - 1):
        x0, y0 = segment[i]
        x1, y1 = segment[i + 1]
        d = abs((x0 + x1) / 2 - cx)
        if d > r * 1.15:
            continue
        glow = max(0.0, 1.0 - d / (r * 1.15))
        pygame.draw.line(surface, (*pal["corona"], int(230 * glow)),
                         (x0, y0 - 1), (x1, y1 - 1), 2)
        pygame.draw.line(surface, (*pal["corona"], int(60 * glow)),
                         (x0, y0 - 2), (x1, y1 - 2), 5)
    # soft corona spill just above the silhouette
    for dx, a in ((-0.9, 14), (-0.45, 22), (0.0, 30), (0.45, 20), (0.9, 12)):
        blit_soft(surface, cx + r * dx, cy - r * 0.55, r * 3.0, r * 2.6,
                  pal["corona"], a, 2.0)


def add_bloom(surface, strength=34):
    small = pygame.transform.smoothscale(
        surface, (max(2, surface.get_width() // 4),
                  max(2, surface.get_height() // 4)))
    blur = pygame.transform.smoothscale(small, surface.get_size())
    blur.set_alpha(strength)
    dimmed = pygame.Surface(surface.get_size())
    dimmed.fill((0, 0, 0))
    dimmed.blit(blur, (0, 0))
    surface.blit(dimmed, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def add_vignette(surface, strength=120):
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


def add_scanlines(surface, alpha=5):
    W, H = surface.get_size()
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(0, H, 2):
        pygame.draw.line(layer, (0, 0, 0, alpha), (0, y), (W, y), 1)
    surface.blit(layer, (0, 0))


def add_grain(surface, rng, amount=0.018, alpha=12):
    W, H = surface.get_size()
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(int(W * H * amount)):
        x = rng.randrange(W)
        y = rng.randrange(H)
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


def draw_hud(surface, layout, pal, eclipse=False):
    W, H = surface.get_size()
    title_font = font(SERIF_BOLD, layout["title_size"])
    eyebrow_font = font(MONO_BOLD, layout["eyebrow_size"])
    tele_font = font(MONO_BOLD, layout["telemetry_size"])

    draw_tracked(surface, "SLOW WORLDS · FANTASY", eyebrow_font,
                 pal["accent"], layout["eyebrow_xy"],
                 tracking=layout["eyebrow_size"] * 0.22, alpha=150)

    if layout["title_lines"]:
        x, y = layout["title_xy"]
        line_gap = layout["title_size"] * 1.02
        for i, line in enumerate(layout["title_lines"]):
            draw_tracked(surface, line, title_font, pal["ink"],
                         (x, y + i * line_gap),
                         tracking=layout["title_tracking"], alpha=242)
        rule_y = int(y + len(layout["title_lines"]) * line_gap + 14)
        pygame.draw.line(surface, mix(pal["accent"], pal["sky_top"], 0.55),
                         (x, rule_y), (x + 330, rule_y), 1)
        # a second, shorter rule keeps the lockup from looking like a box
        pygame.draw.line(surface, mix(pal["ink_faint"], pal["sky_top"], 0.65),
                         (x, rule_y + 4), (x + 150, rule_y + 4), 1)
    else:
        x, y = layout["title_xy"]
        width = draw_tracked(surface, "LEVIATHAN PASSAGE", title_font,
                             pal["ink"], (x, y),
                             tracking=layout["title_tracking"], alpha=242)
        rule_y = int(y + layout["title_size"] * 1.15)
        pygame.draw.line(surface, mix(pal["accent"], pal["sky_top"], 0.55),
                         (x, rule_y), (x + width, rule_y), 1)

    tx, ty = layout["telemetry_xy"]
    ts = layout["telemetry_size"]
    lines = ["DUSK // MIGRATION 07", "POD 03 · WESTWARD"]
    if eclipse:
        lines[1] = "POD 03 · CROSSING THE MOON"
    for i, line in enumerate(lines):
        draw_tracked(surface, line, tele_font, pal["ink_dim"],
                     (tx, ty + i * int(ts * 1.7)),
                     tracking=ts * 0.12, alpha=190, align="right")




# ---------------------------------------------------------------------------
# scene assembly
# ---------------------------------------------------------------------------

def render(layout_name: str, palette_name: str = "dusk", seed: int = 5140,
           eclipse: bool = False, meteor: bool = False,
           meteor_progress: float = 0.62,
           sky_time: float = 0.0) -> pygame.Surface:
    layout = LAYOUTS[layout_name]
    pal = PALETTES[palette_name]
    W, H = layout["size"]
    ss = layout["ss"]
    SW, SH = W * ss, H * ss
    horizon = SH * layout["horizon"]
    rng = random.Random(seed)

    # HUD rectangles are needed before stars so stars do not litter the type
    if layout["title_lines"]:
        hud_rects = [
            pygame.Rect(55 * ss, 90 * ss, 650 * ss, 300 * ss),
            pygame.Rect((W - 420) * ss, 105 * ss, 380 * ss, 110 * ss),
        ]
    else:
        hud_rects = [
            pygame.Rect(28 * ss, 14 * ss, 450 * ss, 78 * ss),
            pygame.Rect((W - 340) * ss, 20 * ss, 310 * ss, 55 * ss),
        ]

    scene = pygame.Surface((SW, SH))
    scene.fill(pal["sky_top"])
    draw_sky(scene, SW, SH, horizon, pal, rng, layout_name,
             [pygame.Rect(r.x, r.y, r.w, r.h) for r in hud_rects],
             sky_time=sky_time)
    if meteor and not eclipse:
        draw_meteor(scene, SW, SH, pal, layout["meteor"],
                    meteor_progress, quality=ss)

    moon = dict(layout["moon"])
    if eclipse and layout_name == "strip":
        moon["above"] += 9.0
    moon["r"] *= ss
    moon["above"] *= ss
    moon_xy = draw_moon(scene, SW, SH, horizon, pal, moon, rng)
    draw_horizon_glow(scene, SW, horizon, pal, moon_xy[0])
    draw_sea(scene, SW, SH, horizon, pal, moon_xy, rng, layout_name)

    # The pod.  On the eclipse still the largest animal is moved so its main
    # hump crosses the moon; the calf is out of frame and the boat has drifted
    # clear.  Everything else stays where it was.
    pod_specs = list(layout["pod"])
    if eclipse:
        if layout_name == "strip":
            pod_specs[0] = (0.273, 0.360, 0.235, 0.11, 0)
            pod_specs[1] = (0.0, 0.0, 0.0, 0.53, 2)   # calf hidden
            boat_x = 0.205
        else:
            pod_specs[0] = (0.150, 0.560, 0.090, 0.21, 0)
            pod_specs[1] = (0.0, 0.0, 0.0, 0.61, 2)
            boat_x = 0.110
    else:
        boat_x = layout["boat"]["x"]

    bodies = []
    for start, length, peak, phase, variant in pod_specs:
        if length <= 0 or peak <= 0:
            continue
        b = Body(start * SW, length * SW, peak * SH, horizon, phase,
                 variant, rng)
        bodies.append(b)

    draw_wakes(scene, SW, SH, horizon, pal, bodies, rng)
    draw_mist(scene, SW, SH, horizon, pal, rng, layout_name, amount=0.45)
    for b in bodies:
        draw_reflection(scene, b, pal, SW, SH, rng, layout_name)
    for b in bodies:
        draw_body(scene, b, pal, SW, SH, moon_xy[0], rng,
                  quality=ss)
    # spouts: the lead animal and the far one
    for index in layout["spouts"]:
        if index < len(bodies) and not (eclipse and index == 0):
            draw_spout(scene, bodies[index], pal, rng,
                       strength=1.0 if index == 0 else 0.7)

    draw_boat(scene, SW, SH, horizon, pal,
              {"x": boat_x, "w": layout["boat"]["w"] * ss,
               "mast": layout["boat"]["mast"] * ss})
    draw_mist(scene, SW, SH, horizon, pal, rng, layout_name)

    if eclipse and bodies:
        # draw the moon's corona over the crossing back, and a little spill
        add_eclipse_corona(scene, bodies[0], SW, horizon, pal,
                           moon, moon_xy)

    # star glints near the moon path, after the mist so they stay crisp
    native = pygame.transform.smoothscale(scene, (W, H))

    add_bloom(native, 32 if layout_name == "strip" else 40)
    add_vignette(native, 110 if layout_name == "strip" else 130)
    add_scanlines(native, 4)
    add_grain(native, random.Random(seed + 77), 0.015, 10)
    draw_hud(native, {
        "title_size": layout["title_size"],
        "title_tracking": layout["title_tracking"],
        "title_xy": layout["title_xy"],
        "eyebrow_size": layout["eyebrow_size"],
        "eyebrow_xy": layout["eyebrow_xy"],
        "telemetry_size": layout["telemetry_size"],
        "telemetry_xy": layout["telemetry_xy"],
        "title_lines": layout["title_lines"],
    }, pal, eclipse=eclipse)
    return native


def palette_study(seed=5140) -> pygame.Surface:
    layout = LAYOUTS["strip"]
    w, h = layout["size"]
    strip_h = h
    label_h = 30
    sheet = pygame.Surface((w, (strip_h + label_h) * 3))
    sheet.fill((3, 6, 7))
    mono = font(MONO_BOLD, 13)
    serif = font(SERIF_BOLD, 16)
    for i, key in enumerate(("dusk", "bone", "ember")):
        y = i * (strip_h + label_h)
        pal = PALETTES[key]
        still = render("strip", key, seed + i, meteor=True,
                        meteor_progress=0.62)
        sheet.blit(still, (0, y + label_h))
        draw_tracked(sheet, pal["label"], serif, pal["ink"],
                     (24, y + 8), tracking=2.0, alpha=220)
        draw_tracked(sheet, "  " + pal["note"], mono, pal["ink_dim"],
                     (24 + 100, y + 9), tracking=1.0, alpha=150)
        pygame.draw.line(sheet, mix(pal["accent"], (3, 6, 7), 0.45),
                         (24, y + 29), (w - 24, y + 29), 1)
    return sheet


def meteor_sheet(seed=5140) -> pygame.Surface:
    """Four moments of the strip sky: stars, twinkle and the meteor pass."""
    w, h = LAYOUTS["strip"]["size"]
    panel_w, panel_h = w // 2, h // 2
    label_h = 22
    sheet = pygame.Surface((w, (panel_h + label_h) * 2 + 4))
    sheet.fill((3, 6, 7))
    mono = font(MONO_BOLD, 14)
    frames = ((0.0, 0.0), (0.35, 1.8), (0.70, 3.6), (0.88, 4.8))
    for i, (progress, sky_time) in enumerate(frames):
        still = render("strip", "dusk", seed, meteor=True,
                       meteor_progress=progress, sky_time=sky_time)
        small = pygame.transform.smoothscale(still, (panel_w, panel_h))
        x = (i % 2) * panel_w
        y = (i // 2) * (panel_h + label_h) + label_h
        sheet.blit(small, (x, y))
        label = (f"T+{sky_time:03.1f}s   METEOR {int(progress * 100):02d}%   "
                 f"STARS TWINKLE")
        sheet.blit(mono.render(label, True, (172, 194, 184)), (x + 10, y - 18))
    return sheet


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("strip", "portrait", "eclipse",
                                           "palette", "meteor", "all"),
                        default="all")
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
        save(render("strip", "dusk", 5140, meteor=True),
             "leviathan_1280x400.png")
    if args.only in ("all", "portrait"):
        save(render("portrait", "dusk", 5140, meteor=True,
                    meteor_progress=0.55),
             "leviathan_1080x1920.png")
    if args.only in ("all", "eclipse"):
        save(render("strip", "dusk", 5140, eclipse=True),
             "leviathan_1280x400_eclipse.png")
    if args.only in ("all", "palette"):
        save(palette_study(5140), "palette_study.png")
    if args.only in ("all", "meteor"):
        save(meteor_sheet(5140), "meteor_sheet.png")

    pygame.quit()


if __name__ == "__main__":
    main()
