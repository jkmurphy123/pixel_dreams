#!/usr/bin/env python3
"""Design prototype: Lantern Procession (Slow Worlds 5.11).

This is a *design* script, not the mode.  It settles the two-orientation
composition, the palette and the lantern treatment before
`modes/lantern_procession_mode.py` is written, and it writes the review stills
in screenshots/lantern_procession/.

What the stills are for:

  * the 1280x400 strip, re-composed for the Pi kiosk (not a crop),
  * the 1080x1920 portrait wall, re-composed again for a vertical frame,
  * a three-palette study (moss / indigo / mono) on the strip,
  * the signature moment: one lantern leaves the line and goes out over the
    water while its reflection lingers.

The scene is a pure function of (seed, layout, palette, moment).  The mode
will share the geometry and palette tables, but render at native resolution
and cache the static forest, path, water and lantern sprites.  This script
deliberately renders at 2x and downsamples so thin paper rims and brush-like
moss edges can be judged fairly.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/lantern_proto/gen_lantern.py
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/lantern_proto/gen_lantern.py --only strip
"""
from __future__ import annotations

import argparse
import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "lantern_procession")

TAU = math.tau
SS = 2  # supersample factor for the still

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


# ---------------------------------------------------------------------------
# Palettes.  Moss is the design default: the "Moon & Moss" family from
# SLOW_WORLDS_DESIGN.md section 4.1, keyed to its five semantic roles.
# ---------------------------------------------------------------------------

PALETTES = {
    "moss": {
        "label": "MOSS",
        "note": "Moon & Moss · the design default",
        "bg_top": (3, 7, 6),
        "bg_mid": (5, 12, 10),
        "sky_low": (11, 24, 20),
        "haze": (120, 145, 105),
        "moon": (168, 198, 172),
        "far_tree": (24, 42, 35),
        "far_leaf": (31, 52, 43),
        "mid_tree": (11, 23, 19),
        "mid_lean": (18, 34, 28),
        "near_tree": (4, 7, 5),
        "near_leaf": (3, 5, 4),
        "bark_hi": (58, 76, 52),
        "bark_lo": (9, 15, 10),
        "path": (24, 30, 19),
        "path_hi": (46, 55, 35),
        "bank": (8, 13, 9),
        "water_top": (10, 23, 20),
        "water_mid": (5, 14, 12),
        "water_bot": (2, 7, 6),
        "water_line": (44, 72, 62),
        "mist": (132, 160, 138),
        "mist_lo": (98, 124, 106),
        "ink": (221, 230, 208),
        "ink_dim": (150, 166, 138),
        "ink_faint": (92, 108, 82),
        "structure": (111, 135, 87),
        "accent": (221, 157, 84),
        "glow": (238, 218, 164),
        "core": (255, 246, 207),
        "paper_top": (250, 227, 176),
        "paper_mid": (234, 181, 108),
        "paper_bot": (181, 112, 52),
        "paper_rim": (255, 236, 188),
        "sigil": (74, 38, 20),
        "tassel": (70, 46, 28),
        "cap": (52, 34, 22),
        "firefly": (215, 232, 160),
        "firefly_warm": (240, 228, 166),
        "reflect": (255, 190, 120),
    },
    "indigo": {
        "label": "INDIGO",
        "note": "cold moonlight · the lanterns keep their warmth",
        "bg_top": (3, 4, 10),
        "bg_mid": (6, 8, 18),
        "sky_low": (15, 19, 33),
        "haze": (116, 132, 166),
        "moon": (168, 188, 220),
        "far_tree": (33, 44, 63),
        "far_leaf": (38, 50, 72),
        "mid_tree": (18, 25, 40),
        "mid_lean": (25, 34, 52),
        "near_tree": (4, 6, 11),
        "near_leaf": (3, 4, 8),
        "bark_hi": (58, 72, 98),
        "bark_lo": (9, 13, 21),
        "path": (9, 12, 18),
        "path_hi": (26, 33, 46),
        "bank": (7, 10, 16),
        "water_top": (14, 21, 35),
        "water_mid": (7, 12, 22),
        "water_bot": (3, 5, 10),
        "water_line": (55, 74, 106),
        "mist": (134, 150, 184),
        "mist_lo": (98, 112, 146),
        "ink": (221, 228, 242),
        "ink_dim": (148, 160, 184),
        "ink_faint": (88, 100, 124),
        "structure": (108, 124, 166),
        "accent": (217, 160, 91),
        "glow": (235, 219, 172),
        "core": (255, 246, 212),
        "paper_top": (244, 233, 199),
        "paper_mid": (222, 193, 145),
        "paper_bot": (170, 120, 72),
        "paper_rim": (250, 241, 214),
        "sigil": (82, 48, 32),
        "tassel": (66, 44, 30),
        "cap": (48, 32, 24),
        "firefly": (196, 216, 222),
        "firefly_warm": (238, 226, 172),
        "reflect": (255, 192, 128),
    },
    "mono": {
        "label": "MONO",
        "note": "sepia silver print · no green, no blue",
        "bg_top": (6, 6, 5),
        "bg_mid": (9, 9, 8),
        "sky_low": (20, 19, 16),
        "haze": (148, 144, 128),
        "moon": (196, 190, 168),
        "far_tree": (40, 39, 34),
        "far_leaf": (47, 46, 40),
        "mid_tree": (24, 23, 20),
        "mid_lean": (32, 31, 27),
        "near_tree": (6, 6, 5),
        "near_leaf": (4, 4, 4),
        "bark_hi": (76, 73, 62),
        "bark_lo": (14, 14, 12),
        "path": (14, 13, 11),
        "path_hi": (36, 34, 28),
        "bank": (11, 11, 9),
        "water_top": (23, 22, 19),
        "water_mid": (13, 13, 11),
        "water_bot": (5, 5, 5),
        "water_line": (74, 70, 58),
        "mist": (166, 161, 143),
        "mist_lo": (122, 118, 104),
        "ink": (230, 225, 211),
        "ink_dim": (160, 155, 139),
        "ink_faint": (100, 96, 85),
        "structure": (138, 133, 114),
        "accent": (217, 180, 124),
        "glow": (238, 224, 186),
        "core": (255, 248, 219),
        "paper_top": (248, 238, 210),
        "paper_mid": (229, 203, 157),
        "paper_bot": (178, 133, 86),
        "paper_rim": (252, 244, 222),
        "sigil": (90, 58, 38),
        "tassel": (72, 52, 36),
        "cap": (54, 40, 29),
        "firefly": (226, 218, 184),
        "firefly_warm": (245, 232, 190),
        "reflect": (255, 198, 138),
    },
}


# ---------------------------------------------------------------------------
# Layout presets.  These are re-compositions, not crops: the strip uses a
# shallow winding line with the water in the foreground band; the portrait
# sends the path down from the canopy into the near bank, so the eye travels
# vertically and the nearest lanterns get long reflections.
# ---------------------------------------------------------------------------

STRIP = {
    "key": "strip",
    "size": (1280, 400),
    "hud_margin": 26,
    "title_px": 24,
    "sub_px": 10,
    "tele_px": 10,
    "eyebrow_px": 9,
    "title_track": 2,
    "aux_track": 2,
    "serif_title": True,
    "title_lines": ("LANTERN PROCESSION",),
    "subtitle": "A PROCESSION THROUGH THE NIGHT WOOD",
    "tele": ("NIGHT  //  412 STEPS", "LANTERNS  13 / 14"),
    "waterline": 300.0,
    "path": [(-90, 262), (210, 276), (460, 262), (700, 278),
             (950, 272), (1180, 288), (1370, 296)],
    "path_width": 31.0,
    "path_depth": 0.38,
    "canopy_band": 0.34,
    "lane": 70.0,
    "lantern_count": 14,
    "lantern_w": 11.5,
    "hover": 22.0,
    "hover_fixed": True,
    "scale_min": 0.34,
    "scale_max": 2.10,
    "u_span": 0.80,
    "curve": "recede",
    "fireflies": 28,
    "far_trees": 30,
    "mid_trees": 13,
    "near_trees": 3,
    "reeds": 26,
    "refl_alpha": 0.58,
    "seed": 412,
}

PORTRAIT = {
    "key": "portrait",
    "size": (1080, 1920),
    "hud_margin": 48,
    "title_px": 46,
    "sub_px": 15,
    "tele_px": 14,
    "eyebrow_px": 12,
    "title_track": 2,
    "aux_track": 2,
    "serif_title": True,
    "title_lines": ("LANTERN", "PROCESSION"),
    "subtitle": "A PROCESSION THROUGH THE NIGHT WOOD",
    "tele": ("NIGHT  //  412 STEPS", "LANTERNS  13 / 14"),
    "waterline": 1500.0,
    "path": [(742, 540), (648, 760), (748, 960), (612, 1170),
             (452, 1340), (300, 1472)],
    "path_width": 30.0,
    "path_depth": 0.88,
    "canopy_band": 0.20,
    "lane": 90.0,
    "lantern_count": 14,
    "lantern_w": 17.0,
    "hover": 42.0,
    "hover_fixed": True,
    "scale_min": 0.38,
    "scale_max": 1.70,
    "u_span": 0.86,
    "curve": "recede",
    "fireflies": 36,
    "far_trees": 26,
    "mid_trees": 12,
    "near_trees": 3,
    "reeds": 20,
    "refl_alpha": 0.82,
    "seed": 412,
}


# ---------------------------------------------------------------------------
# Small maths / colour / text kit
# ---------------------------------------------------------------------------

def clamp8(value) -> int:
    return 0 if value < 0 else 255 if value > 255 else int(value)


def mix(a, b, t):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def shade(color, factor):
    return (clamp8(color[0] * factor), clamp8(color[1] * factor),
            clamp8(color[2] * factor))


def with_alpha(color, alpha):
    return (int(color[0]), int(color[1]), int(color[2]),
            max(0, min(255, int(alpha))))


def smoothstep(t):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


_fonts: dict[tuple[str, int], pygame.font.Font] = {}


def font(path: str, px: int) -> pygame.font.Font:
    key = (path, max(1, int(px)))
    cached = _fonts.get(key)
    if cached is None:
        cached = pygame.font.Font(path, max(1, int(px)))
        _fonts[key] = cached
    return cached


def tracked(text: str, f: pygame.font.Font, color, spacing: int = 0,
            alpha: int = 255):
    glyphs = [f.render(ch, True, color) for ch in text]
    if not glyphs:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    width = sum(g.get_width() for g in glyphs) + spacing * (len(glyphs) - 1)
    height = max(g.get_height() for g in glyphs)
    surf = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    x = 0
    for glyph in glyphs:
        surf.blit(glyph, (x, 0))
        x += glyph.get_width() + spacing
    if alpha < 255:
        surf.set_alpha(alpha)
    return surf


def blit_text(dst, text, pos, f, color, tracking=0, alpha=255, align="left"):
    surf = tracked(text, f, color, tracking, alpha)
    rect = surf.get_rect()
    if align == "right":
        rect.topright = (int(pos[0]), int(pos[1]))
    elif align == "center":
        rect.midtop = (int(pos[0]), int(pos[1]))
    else:
        rect.topleft = (int(pos[0]), int(pos[1]))
    dst.blit(surf, rect)
    return rect


def vertical_gradient(size, stops):
    """An opaque vertical gradient. `stops` is [(pos, color), ...]."""
    width, height = size
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        color = stops[0][1]
        for index in range(1, len(stops)):
            p0, c0 = stops[index - 1]
            p1, c1 = stops[index]
            if t <= p1 or index == len(stops) - 1:
                local = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
                color = mix(c0, c1, local)
                break
        pygame.draw.line(surf, color, (0, y), (width, y))
    return surf


_glow_cache: dict[tuple[int, tuple, float], pygame.Surface] = {}


def glow_sprite(radius_px: int, color, power: float = 2.2) -> pygame.Surface:
    key = (max(2, int(radius_px)), tuple(color), power)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached
    base = 128
    small = pygame.Surface((base, base))
    small.fill((0, 0, 0))
    steps = 64
    for i in range(steps, 0, -1):
        t = i / steps
        k = (1.0 - t) ** power
        pygame.draw.circle(small, shade(color, k),
                           (base // 2, base // 2), int(base * 0.5 * t))
    size = max(2, int(radius_px) * 2)
    surf = pygame.transform.smoothscale(small, (size, size))
    _glow_cache[key] = surf
    return surf


def blit_glow(dst, center, radius_px, color, power=2.2, strength=1.0,
              squash=1.0):
    radius_px = int(radius_px)
    if radius_px < 2:
        return
    sprite = glow_sprite(radius_px, color, power)
    if squash != 1.0:
        sprite = pygame.transform.smoothscale(
            sprite, (sprite.get_width(), max(2, int(sprite.get_height() * squash))))
    if strength != 1.0:
        sprite = sprite.copy()
        sprite.fill(shade((255, 255, 255), strength),
                    special_flags=pygame.BLEND_RGB_MULT)
    dst.blit(sprite, (int(center[0]) - sprite.get_width() // 2,
                      int(center[1]) - sprite.get_height() // 2),
             special_flags=pygame.BLEND_RGB_ADD)


def blur_surface(surf: pygame.Surface, factor: int = 2) -> pygame.Surface:
    w, h = surf.get_size()
    small = pygame.transform.smoothscale(surf, (max(2, w // factor),
                                                max(2, h // factor)))
    return pygame.transform.smoothscale(small, (w, h))


def alpha_mul(surf: pygame.Surface, factor: float) -> pygame.Surface:
    out = surf.copy()
    out.fill((255, 255, 255, max(0, min(255, int(255 * factor)))),
             special_flags=pygame.BLEND_RGBA_MULT)
    return out


def spoints(points, scale):
    return [(int(x * scale), int(y * scale)) for x, y in points]


# ---------------------------------------------------------------------------
# Spline
# ---------------------------------------------------------------------------

def catmull_rom(points, samples_per_segment=26):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(samples_per_segment):
            t = j / samples_per_segment
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


def path_lengths(points):
    lengths = [0.0]
    for a, b in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    return lengths


def sample_path(points, lengths, distance):
    total = lengths[-1]
    d = distance % total if total > 0 else 0.0
    lo, hi = 0, len(lengths) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if lengths[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    seg = lengths[i] - lengths[i - 1] or 1.0
    t = (d - lengths[i - 1]) / seg
    a, b = points[i - 1], points[i]
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t)), (b[0] - a[0], b[1] - a[1])


# ---------------------------------------------------------------------------
# Lanterns
# ---------------------------------------------------------------------------

SIGIL_KINDS = 8


def draw_sigil(dst, kind: int, cx: float, cy: float, w: float, h: float, color,
               width: int):
    """One invented glyph, small and stamped on the paper."""
    lw = max(1, int(width))
    x0, x1 = cx - w * 0.5, cx + w * 0.5
    y0, y1 = cy - h * 0.5, cy + h * 0.5
    if kind == 0:      # fir: a spine with three drooping ticks
        pygame.draw.line(dst, color, (cx, y0), (cx, y1), lw)
        for k in range(3):
            yy = y0 + h * (0.28 + 0.22 * k)
            pygame.draw.line(dst, color, (cx, yy), (x1 - w * 0.06, yy + h * 0.14), lw)
            pygame.draw.line(dst, color, (cx, yy), (x0 + w * 0.06, yy + h * 0.14), lw)
    elif kind == 1:    # ring crossed by a bar
        pygame.draw.circle(dst, color, (int(cx), int(cy)), int(w * 0.30), lw)
        pygame.draw.line(dst, color, (x0, cy), (x1, cy), lw)
    elif kind == 2:    # triangle over a dot
        pygame.draw.polygon(dst, color, [(cx, y0), (x1, cy + h * 0.22),
                                         (x0, cy + h * 0.22)], lw)
        pygame.draw.circle(dst, color, (int(cx), int(y1 - h * 0.10)),
                           max(1, int(w * 0.07)))
    elif kind == 3:    # three slow waves
        for k in range(3):
            yy = lerp(y0, y1, (k + 0.5) / 3.0)
            pts = [(lerp(x0, x1, s / 8.0),
                    yy + math.sin(s * 0.9 + k) * h * 0.055) for s in range(9)]
            pygame.draw.lines(dst, color, False, pts, lw)
    elif kind == 4:    # diamond + hanging line
        pygame.draw.polygon(dst, color, [(cx, y0), (x1, cy - h * 0.10),
                                         (cx, cy + h * 0.18), (x0, cy - h * 0.10)], lw)
        pygame.draw.line(dst, color, (cx, cy + h * 0.18), (cx, y1), lw)
    elif kind == 5:    # crescent and a spark
        pygame.draw.arc(dst, color, (int(x0), int(y0), int(w), int(h)),
                        math.radians(40), math.radians(320), lw)
        pygame.draw.circle(dst, color, (int(cx + w * 0.22), int(cy)),
                           max(1, int(w * 0.06)))
    elif kind == 6:    # rune: upright with a looped shoulder
        pygame.draw.line(dst, color, (cx - w * 0.22, y1),
                         (cx - w * 0.22, y0), lw)
        pygame.draw.lines(dst, color, False,
                          [(cx - w * 0.22, y0),
                           (cx + w * 0.24, y0 + h * 0.10),
                           (cx + w * 0.24, y0 + h * 0.34),
                           (cx - w * 0.22, y0 + h * 0.44)], lw)
        pygame.draw.line(dst, color, (cx - w * 0.22, cy + h * 0.10),
                         (cx + w * 0.28, y1), lw)
    else:              # cross, four points
        pygame.draw.line(dst, color, (cx, y0), (cx, y1), lw)
        pygame.draw.line(dst, color, (x0, cy), (x1, cy), lw)
        for px, py in ((cx, y0), (x1, cy), (cx, y1), (x0, cy)):
            pygame.draw.circle(dst, color, (int(px), int(py)),
                               max(1, int(w * 0.045)))


def paper_polygon(half_w, half_h, segments=44):
    pts = []
    for i in range(segments):
        a = TAU * i / segments
        c, s = math.cos(a), math.sin(a)
        x = half_w * math.copysign(abs(c) ** 0.74, c)
        y = half_h * math.copysign(abs(s) ** 0.88, s)
        pts.append((x, y))
    return pts


def make_lantern(half_w: float, palette: dict, sigil: int,
                 detail: int = 2, height_ratio: float = 1.36) -> pygame.Surface:
    """A paper lantern sprite, centred on the paper, with cap and tassel.

    half_w is in *device* pixels (the caller has already applied the
    supersample factor), so the same routine serves the strip, the portrait
    and the eventual mode's size buckets.
    """
    half_w = max(4.0, half_w)
    half_h = half_w * height_ratio
    pad = int(half_w * 1.05) + 2
    tassel = int(half_h * 0.62)
    width = int(half_w * 2) + pad * 2
    height = int(half_h * 2) + pad * 2 + tassel
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    cx = width * 0.5
    cy = pad + half_h - int(half_h * 0.06)

    # Paper body: a vertical paper gradient masked to the lantern silhouette.
    wpx, hpx = int(half_w * 2) + 2, int(half_h * 2) + 2
    paper = vertical_gradient(
        (wpx, hpx),
        [(0.0, palette["paper_top"]), (0.26, palette["paper_mid"]),
         (0.66, palette["paper_bot"]), (1.0, shade(palette["paper_bot"], 0.62))]
    ).convert_alpha()
    mask = pygame.Surface((wpx, hpx), pygame.SRCALPHA)
    local = [(x + wpx * 0.5, y + hpx * 0.5)
             for x, y in paper_polygon(half_w, half_h)]
    pygame.draw.polygon(mask, (255, 255, 255, 255), local)
    paper.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(paper, (int(cx - wpx * 0.5), int(cy - hpx * 0.5)))

    # Hot core, kept inside the paper because it is drawn before the ribs.
    # Deliberately not white-hot: the paper must still read as paper.
    for k, factor in enumerate((0.66, 0.50, 0.34, 0.20)):
        col = mix(palette["paper_mid"], palette["core"], 0.18 + k * 0.18)
        rx = max(2, int(half_w * factor))
        ry = max(2, int(half_h * factor))
        ellipse = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(ellipse, col, (0, 0, rx * 2, ry * 2))
        surf.blit(ellipse, (int(cx - rx), int(cy - ry)),
                  special_flags=pygame.BLEND_RGBA_ADD)

    # Ribs and the horizontal seam.
    if detail >= 1:
        rib_color = shade(palette["paper_bot"], 0.62)
        for k in (-0.58, -0.20, 0.20, 0.58):
            pts = []
            for j in range(13):
                yy = -1.0 + 2.0 * j / 12.0
                xx = k * half_w * (1.0 - 0.10 * yy * yy)
                pts.append((cx + xx, cy + yy * half_h * 0.965))
            pygame.draw.lines(surf, rib_color, False, pts, 1)
        seam = shade(palette["paper_bot"], 0.72)
        pygame.draw.line(surf, seam, (cx - half_w * 0.86, cy),
                         (cx + half_w * 0.86, cy), 1)

    # Dark inner edge, then the bright rim on the upper-left.
    inner = [(cx + x * 0.955, cy + y * 0.955)
             for x, y in paper_polygon(half_w, half_h)]
    pygame.draw.polygon(surf, shade(palette["paper_bot"], 0.55), inner, 1)
    outline = [(cx + x, cy + y) for x, y in paper_polygon(half_w, half_h)]
    pygame.draw.polygon(surf, palette["paper_rim"], outline, 1)
    arc_rect = (int(cx - half_w * 0.985), int(cy - half_h * 0.985),
                int(half_w * 1.97), int(half_h * 1.97))
    pygame.draw.arc(surf, palette["core"], arc_rect,
                    math.radians(116), math.radians(214),
                    max(1, int(half_w * 0.11)))

    # Sigil, stamped on the paper. Large enough to read on the near lanterns.
    draw_sigil(surf, sigil, cx, cy + half_h * 0.02,
               half_w * 1.34, half_h * 1.08, palette["sigil"],
               max(1, int(half_w * 0.115)))

    # Wooden caps and hanging ring.
    cap_w = half_w * 0.60
    cap_h = max(2, int(half_h * 0.075))
    for y in (cy - half_h * 0.985, cy + half_h * 0.985):
        pygame.draw.rect(surf, palette["cap"],
                         (int(cx - cap_w), int(y - cap_h * 0.5),
                          int(cap_w * 2), cap_h), border_radius=max(1, cap_h // 2))
        pygame.draw.line(surf, shade(palette["cap"], 1.8),
                         (cx - cap_w * 0.78, y), (cx + cap_w * 0.78, y), 1)
    if detail >= 2:
        ring_r = max(2, int(half_w * 0.17))
        pygame.draw.circle(surf, shade(palette["cap"], 1.45),
                           (int(cx), int(cy - half_h - ring_r * 1.4)),
                           ring_r, 1)
        pygame.draw.line(surf, shade(palette["cap"], 1.25),
                         (cx, cy - half_h - ring_r * 0.4),
                         (cx, cy - half_h * 0.99), 1)

    # Tassel: one thread and a small bead.
    ty = cy + half_h + cap_h * 0.5
    pygame.draw.line(surf, palette["tassel"], (cx, ty),
                     (cx, ty + tassel * 0.55), 1)
    bead_r = max(1, int(half_w * 0.10))
    pygame.draw.circle(surf, palette["tassel"],
                       (int(cx), int(ty + tassel * 0.60)), bead_r)
    for k in (-1, 0, 1):
        pygame.draw.line(surf, palette["tassel"],
                         (cx, ty + tassel * 0.62),
                         (cx + k * half_w * 0.14, ty + tassel * 0.95), 1)
    return surf


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class Lantern:
    __slots__ = ("u", "x", "y", "scale", "half_w", "sigil", "phase", "tilt",
                 "dim", "reflection", "reflection_bias", "sprite", "index",
                 "path_y")

    def __init__(self, index, u, x, y, scale, half_w, sigil, phase, tilt,
                 dim=1.0, reflection=True, reflection_bias=0.0, path_y=0.0):
        self.index = index
        self.u = u
        self.x = x
        self.y = y
        self.scale = scale
        self.half_w = half_w
        self.sigil = sigil
        self.phase = phase
        self.tilt = tilt
        self.dim = dim
        self.reflection = reflection
        self.reflection_bias = reflection_bias
        self.path_y = path_y
        self.sprite = None


class Scene:
    def __init__(self, preset, palette, seed):
        self.preset = preset
        self.palette = palette
        self.rng = random.Random(seed)
        self.width, self.height = preset["size"]
        self.waterline = preset["waterline"]
        self.path = catmull_rom(preset["path"])
        self.lengths = path_lengths(self.path)
        self.total_len = self.lengths[-1]
        self.lanterns: list[Lantern] = []
        self.fireflies = []
        self.mist_layers = []
        self.canopy_clusters = []
        self.event = None
        self._build()

    # -- geometry ---------------------------------------------------------

    def point_at(self, distance):
        return sample_path(self.path, self.lengths, distance)

    def scale_for(self, u):
        cfg = self.preset
        if cfg["curve"] == "edges":
            t = (abs(u - 0.5) * 2.0) ** 1.55
        else:
            t = max(0.0, min(1.0, u)) ** 1.28
        return lerp(cfg["scale_min"], cfg["scale_max"], t)

    def _build(self):
        cfg = self.preset
        rng = self.rng
        count = cfg["lantern_count"]
        for i in range(count):
            # even spacing along the arc, with a little shuffle so the line
            # never reads as a ruler
            u = 0.03 + ((i + 0.5) / count) * cfg.get("u_span", 0.86)
            u += rng.uniform(-0.006, 0.006)
            u = max(0.02, min(0.98, u))
            (px, py), (tx, ty) = self.point_at(u * self.total_len)
            scale = self.scale_for(u)
            half_w = cfg["lantern_w"] * scale * rng.uniform(0.94, 1.07)
            # hover above the path; side offset along the normal keeps them
            # from sitting on one invisible rail
            nx, ny = (-ty, tx)
            norm = math.hypot(nx, ny) or 1.0
            lane = rng.uniform(-0.32, 0.32) * cfg["lane"] * scale
            x = px + nx / norm * lane
            hover = cfg["hover"] if cfg.get("hover_fixed") else cfg["hover"] * scale
            y = py + ny / norm * abs(lane) * 0.10 - hover
            phase = rng.uniform(0.0, TAU)
            tilt = math.sin(phase * 1.37) * 3.2
            y += math.sin(phase) * 4.0 * scale
            self.lanterns.append(Lantern(
                i, u, x, y, scale, half_w,
                rng.choice((0, 1, 2, 3, 4, 5, 6, 7)), phase, tilt,
                path_y=py))

        # fireflies: depth layers, a few over the water
        for i in range(cfg["fireflies"]):
            layer = rng.choices((0, 1, 2), weights=(0.30, 0.45, 0.25))[0]
            if layer == 0:
                x = rng.uniform(0, self.width)
                y = rng.uniform(110, 260)
                brightness = rng.uniform(0.35, 0.75)
                radius = rng.uniform(3.0, 7.0)
            elif layer == 1:
                x = rng.uniform(0, self.width)
                y = rng.uniform(150, self.waterline - 10)
                brightness = rng.uniform(0.55, 1.0)
                radius = rng.uniform(5.0, 11.0)
            else:
                x = rng.uniform(30, self.width - 30)
                y = rng.uniform(self.waterline + 8, self.waterline + 70)
                brightness = rng.uniform(0.4, 0.85)
                radius = rng.uniform(4.0, 9.0)
            blink = rng.uniform(0.55, 1.0)
            warm = rng.random() < 0.25
            self.fireflies.append((x, y, radius, brightness * blink, warm, layer))

        # canopy clusters: branch ends that carry leaves, mostly at the edges
        for i in range(46):
            side = rng.choices(("left", "right", "top"), weights=(0.34, 0.34, 0.32))[0]
            if side == "left":
                x = rng.uniform(-20, self.width * 0.26)
                y = rng.uniform(-40, 190)
            elif side == "right":
                x = rng.uniform(self.width * 0.74, self.width + 20)
                y = rng.uniform(-40, 190)
            else:
                x = rng.uniform(0, self.width)
                y = rng.uniform(-60, 120)
            self.canopy_clusters.append((x, y, rng.uniform(0.6, 1.5),
                                         rng.uniform(0, TAU)))

        # three soft mist layers, one at the far bank, two over the water
        self.mist_layers = [
            (self.waterline - 44.0, self.width * 1.12, 62.0, 0.19, 0.0),
            (self.waterline + 34.0, self.width * 1.04, 42.0,
             0.20 if self.preset["key"] == "strip" else 0.26, 1.7),
            (self.height - 20.0, self.width * 1.1, 76.0, 0.09, 3.1),
        ]

    # -- event ------------------------------------------------------------

    def plan_event(self, lantern_index=None):
        """One lantern leaves the line over the water and dims.

        The still keeps the line intact apart from this one; the mode will
        animate the departure over ~18 s and let the reflection linger.
        """
        if lantern_index is None:
            lantern_index = len(self.lanterns) - 4
        lantern = self.lanterns[lantern_index]
        # move it off the line, down toward the water, slightly downstream
        lantern.x -= 16.0
        lantern.y = self.waterline - 9.0
        lantern.scale *= 1.16
        lantern.half_w *= 1.16
        lantern.dim = 0.55
        lantern.reflection_bias = 58.0
        self.event = lantern

    # -- cached art -------------------------------------------------------

    def build_sprites(self, scale=SS):
        for lantern in self.lanterns:
            ratio = 1.30 + 0.11 * math.sin(lantern.index * 2.1 + 0.6)
            lantern.sprite = make_lantern(lantern.half_w * scale, self.palette,
                                          lantern.sigil, height_ratio=ratio)


# ---------------------------------------------------------------------------
# Forest / ground / water painting
# ---------------------------------------------------------------------------

def draw_far_treeline(dst, rng, palette, scene, scale):
    """A distant, soft tree-line: a dark mass with a bumpy, leafy top edge."""
    width, wl = scene.width, scene.waterline
    steps = 80
    top_pts = []
    for i in range(steps + 1):
        x = -40 + (width + 80) * i / steps
        top = (wl - 78
               - 26.0 * math.sin(x * 0.009 + 1.2)
               - 13.0 * math.sin(x * 0.031 + 0.4)
               - rng.uniform(0, 5))
        top_pts.append((x, top))
    poly = [(x * scale, y * scale) for x, y in top_pts]
    poly += [(int((width + 60) * scale), int(wl * scale)),
             (int(-60 * scale), int(wl * scale))]
    pygame.draw.polygon(dst, palette["far_tree"], poly)
    # rounded crowns along the crest, and a few bright leaf catches
    for x, y in top_pts[::2]:
        rx = rng.uniform(7, 16)
        ry = rng.uniform(5, 11)
        pygame.draw.ellipse(dst, shade(palette["far_tree"], rng.uniform(0.65, 1.1)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), int(ry * 2 * scale)))
    for _ in range(260):
        x = rng.uniform(-10, width + 10)
        top = (wl - 78
               - 26.0 * math.sin(x * 0.009 + 1.2)
               - 13.0 * math.sin(x * 0.031 + 0.4))
        y = top + rng.uniform(-12, 16)
        er = rng.uniform(1.5, 5.0)
        pygame.draw.ellipse(dst, shade(palette["far_leaf"], rng.uniform(0.55, 1.1)),
                            (int((x - er) * scale), int((y - er * 0.6) * scale),
                             max(2, int(er * 2 * scale)),
                             max(1, int(er * 1.2 * scale))))
    # a few tall, faint trunks rising from the line into the canopy
    for _ in range(9 if scene.preset["key"] == "strip" else 2):
        x = rng.uniform(0, width)
        w = rng.uniform(5.0, 10.0)
        pygame.draw.line(dst, shade(palette["far_tree"], 0.42),
                         (int(x * scale), int(wl * scale)),
                         (int((x + rng.uniform(-18, 18)) * scale), int((30 + rng.uniform(-10, 30)) * scale)),
                         max(1, int(w * scale)))


def draw_crown(dst, rng, palette, cx, cy, spread_x, spread_y, base, layer,
               scale, lobes=7, fluff=26):
    """A tree crown: a few big overlapping lobes, then a leafy fringe."""
    if layer == 0:
        shade_lo, shade_hi = 0.42, 0.80
    elif layer == 1:
        shade_lo, shade_hi = 0.40, 0.85
    else:
        shade_lo, shade_hi = 0.55, 1.20
    for _ in range(lobes):
        ox = rng.uniform(-spread_x, spread_x)
        oy = rng.uniform(-spread_y * 0.55, spread_y * 0.55)
        rx = spread_x * rng.uniform(0.28, 0.60)
        ry = spread_y * rng.uniform(0.32, 0.65)
        pygame.draw.ellipse(dst, shade(base, rng.uniform(shade_lo, shade_hi)),
                            (int((cx + ox - rx) * scale),
                             int((cy + oy - ry) * scale),
                             max(2, int(rx * 2 * scale)),
                             max(2, int(ry * 2 * scale))))
    for _ in range(fluff):
        a = rng.uniform(0.0, 1.0) * math.pi
        r = rng.uniform(0.35, 1.05)
        lx = cx + math.cos(a) * spread_x * r * rng.choice((-1, 1))
        ly = cy + math.sin(a) * spread_y * r
        er = rng.uniform(1.8, 6.0) * (1.0 if layer == 0 else 1.15)
        pygame.draw.ellipse(dst, shade(base, rng.uniform(shade_lo, shade_hi)),
                            (int((lx - er) * scale),
                             int((ly - er * 0.55) * scale),
                             max(2, int(er * 2 * scale)),
                             max(1, int(er * 1.15 * scale))))


def draw_tree(dst, rng, palette, x, base_y, top_y, trunk_w, layer, scale,
              crown_cy=None, crown_rx=60.0, crown_ry=32.0, lobe_count=7):
    """One deliberate tree: trunk, branches, crown."""
    color = (palette["far_tree"] if layer == 0 else
             palette["mid_tree"] if layer == 1 else palette["near_tree"])
    highlight = None
    if layer == 1:
        highlight = shade(palette["bark_hi"], 0.42)
    elif layer == 2:
        highlight = shade(palette["bark_hi"], 0.22)
    draw_trunk(dst, rng, x * scale, base_y * scale, top_y * scale,
               trunk_w * scale, color, rng.uniform(-1.0, 1.0), layer,
               palette, highlight=highlight)
    if crown_cy is None:
        crown_cy = top_y + (base_y - top_y) * 0.18
    crown_base = (palette["far_tree"] if layer == 0 else
                  palette["mid_lean"] if layer == 1 else palette["near_leaf"])
    draw_crown(dst, rng, palette, x, crown_cy, crown_rx, crown_ry, crown_base,
               layer, scale, lobes=lobe_count,
               fluff=70 if layer == 0 else 90 if layer == 1 else 50)


def draw_canopy_roof(dst, rng, palette, width, height, layer, scale):
    """A few huge dark lobes across the top, not a field of small leaves."""
    if layer == 0:
        base = palette["far_tree"]
        big, medium, fluff = 7, 12, 120
        shade_lo, shade_hi = 0.38, 0.72
        top = height * 0.02
    else:
        base = palette["mid_tree"]
        big, medium, fluff = 8, 14, 150
        shade_lo, shade_hi = 0.26, 0.55
        top = height * 0.015
    for _ in range(big):
        x = rng.uniform(-0.08, 1.08) * width
        y = rng.uniform(-0.16, 0.02) * height + top
        rx = rng.uniform(0.10, 0.24) * width
        ry = rng.uniform(0.05, 0.10) * height
        pygame.draw.ellipse(dst, shade(base, rng.uniform(shade_lo, shade_hi)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), int(ry * 2 * scale)))
    for _ in range(medium):
        x = rng.uniform(-0.04, 1.04) * width
        y = rng.uniform(-0.02, 0.16) * height + top
        rx = rng.uniform(0.035, 0.09) * width
        ry = rx * rng.uniform(0.35, 0.65)
        pygame.draw.ellipse(dst, shade(base, rng.uniform(shade_lo, shade_hi)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), max(2, int(ry * 2 * scale))))
    for _ in range(fluff):
        x = rng.uniform(-0.03, 1.03) * width
        y = rng.gauss(0.12 * height + top, 0.05 * height)
        er = rng.uniform(2.0, 6.5)
        pygame.draw.ellipse(dst, shade(base, rng.uniform(shade_lo, shade_hi)),
                            (int((x - er) * scale), int((y - er * 0.55) * scale),
                             max(2, int(er * 2 * scale)),
                             max(1, int(er * 1.0 * scale))))


def draw_trunk(dst, rng, x, base_y, top_y, width, color, lean, layer,
               palette, highlight=None):
    """A tapered, slightly crooked trunk with bark, moss and branch stubs.

    All coordinates and the width are device pixels (the caller has already
    applied the supersample factor).
    """
    height = base_y - top_y
    if height <= 4 or width <= 1:
        return
    steps = 16
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        y = lerp(top_y, base_y, t)
        bend = math.sin(t * 2.4 + x * 0.013) * lean * 0.55
        cx = x + lean * (1.0 - t) + bend
        taper = lerp(0.50, 1.0, t ** 1.35)
        flare = 1.0 + 0.30 * smoothstep((t - 0.82) / 0.18)
        wobble = 1.0 + 0.09 * math.sin(t * 8.0 + x * 0.07)
        half = width * 0.5 * taper * wobble * flare
        left.append((cx - half, y))
        right.append((cx + half, y))
    poly = left + right[::-1]
    pygame.draw.polygon(dst, color, poly)

    if layer >= 1:
        # bark streaks: long, low-contrast strokes
        streaks = max(1, int(width * 0.40))
        for _ in range(streaks):
            t0 = rng.uniform(0.02, 0.82)
            t1 = min(1.0, t0 + rng.uniform(0.10, 0.36))
            off = rng.uniform(-0.36, 0.36)
            streak = shade(color, rng.uniform(0.55, 1.55))
            pts = []
            for k in range(4):
                t = lerp(t0, t1, k / 3.0)
                y = lerp(top_y, base_y, t)
                bend = math.sin(t * 2.4 + x * 0.013) * lean * 0.55
                cx = x + lean * (1.0 - t) + bend
                half = width * 0.5 * lerp(0.50, 1.0, t ** 1.35)
                pts.append((cx + off * half, y))
            pygame.draw.lines(dst, streak, False, pts, 1)

        # moss patches on the shaded side
        for _ in range(max(1, int(width * 0.22))):
            t = rng.uniform(0.12, 0.7)
            y = lerp(top_y, base_y, t)
            bend = math.sin(t * 2.4 + x * 0.013) * lean * 0.55
            cx = x + lean * (1.0 - t) + bend
            half = width * 0.5 * lerp(0.50, 1.0, t ** 1.35)
            mx = cx + rng.uniform(-0.30, 0.10) * half
            rx = max(1, int(width * rng.uniform(0.06, 0.16)))
            ry = max(1, int(rx * rng.uniform(0.5, 1.4)))
            pygame.draw.ellipse(dst, shade(palette["bark_hi"], rng.uniform(0.35, 0.7)),
                                (int(mx - rx), int(y - ry), rx * 2, ry * 2))

        if highlight is not None:
            # moonlit edge on one side of the trunk
            edge = []
            for i in range(0, steps + 1, 2):
                t = i / steps
                y = lerp(top_y, base_y, t)
                bend = math.sin(t * 2.4 + x * 0.013) * lean * 0.55
                cx = x + lean * (1.0 - t) + bend
                half = width * 0.5 * lerp(0.50, 1.0, t ** 1.35)
                edge.append((cx - half + 0.8, y))
            pygame.draw.lines(dst, highlight, False, edge, 1)

    # Branches. Far trunks get none (they are only a line in the mist);
    # mid trunks get a couple with leaf clusters; near trunks get heavy arms
    # that leave the frame.
    branches = 2 if layer == 0 else (3 if layer == 1 else 4)
    for _ in range(branches):
        lo = 0.04 if layer == 0 else 0.18 if layer == 1 else 0.10
        hi = 0.45 if layer == 0 else 0.68 if layer == 1 else 0.50
        by = rng.uniform(top_y + height * lo, top_y + height * hi)
        side = rng.choice((-1, 1))
        length = rng.uniform(0.4, 1.0) * (width * (6.0 if layer == 1 else 9.5))
        t0 = max(0.0, min(1.0, (by - top_y) / height))
        trunk_cx = x + lean * (1.0 - t0)
        start = (trunk_cx + side * width * 0.32, by)
        elbow = (start[0] + side * length * 0.50, by - length * 0.16)
        tip = (start[0] + side * length, by - length * 0.52)
        pygame.draw.lines(dst, shade(color, 0.9), False,
                          [start, elbow, tip],
                          max(1, int(width * (0.24 if layer == 1 else 0.34))))
        if layer >= 1:
            for _ in range(int(14 * rng.uniform(0.7, 1.8))):
                t = rng.uniform(0.35, 1.0)
                bx = lerp(elbow[0], tip[0], t) + rng.uniform(-length * 0.18, length * 0.10)
                byy = lerp(elbow[1], tip[1], t) + rng.uniform(-length * 0.10, length * 0.14)
                rx = max(2, int(width * rng.uniform(0.14, 0.30)))
                ry = max(1, int(rx * rng.uniform(0.45, 0.9)))
                pygame.draw.ellipse(
                    dst, shade(palette["mid_lean"] if layer == 1 else color,
                               rng.uniform(0.8, 1.35)),
                    (int(bx - rx), int(byy - ry), rx * 2, ry * 2))

    # Hanging moss on the big near trunks.
    if layer >= 2:
        for _ in range(max(2, int(width * 0.25))):
            t = rng.uniform(0.05, 0.55)
            y = lerp(top_y, base_y, t)
            cx = x + lean * (1.0 - t) + rng.uniform(-0.45, 0.45) * width
            length = rng.uniform(6, 30)
            pts = []
            for k in range(4):
                tt = k / 3.0
                pts.append((cx + math.sin(tt * 3.0 + t * 9) * 1.6,
                            y + length * tt))
            pygame.draw.lines(dst, shade(palette["bark_hi"], 0.3), False, pts, 1)


def draw_path(dst, scene, scale):
    preset = scene.preset
    palette = scene.palette
    layer = pygame.Surface(dst.get_size(), pygame.SRCALPHA)
    target = layer
    pts = scene.path
    rng = random.Random(preset["seed"] + 17)
    normals = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(tx, ty) or 1.0
        normals.append((-ty / norm, tx / norm))
    depth = preset.get("path_depth", 0.45)
    widths = []
    for i, p in enumerate(pts):
        u = i / max(1, len(pts) - 1)
        wobble = 1.0 + 0.12 * math.sin(u * 17.0 + 0.7)
        widths.append(preset["path_width"] * lerp(0.76, 1.28, u) * wobble)

    def ribbon(offset, factor, color):
        left = [(p[0] + n[0] * w * factor, p[1] + n[1] * w * factor * depth)
                for p, n, w in zip(pts, normals, widths)]
        right = [(p[0] - n[0] * w * factor, p[1] - n[1] * w * factor * depth)
                 for p, n, w in zip(pts, normals, widths)]
        polygon = [(x * scale, y * scale) for x, y in left + right[::-1]]
        pygame.draw.polygon(target, color, polygon)

    # a dark moss edge, then the trodden earth, then a worn centre line
    ribbon(0.0, 1.10, shade(palette["bank"], 0.9))
    ribbon(0.0, 1.00, palette["path"])
    ribbon(0.0, 0.54, shade(palette["path"], 1.25))
    inner = []
    for p, n in zip(pts, normals):
        inner.append((p[0] + n[0] * 0.6, p[1] + n[1] * 1.2 * depth))
    pygame.draw.lines(target, palette["path_hi"], False,
                      spoints(inner, scale), max(1, int(1.0 * scale)))

    # dark moss patches break the ribbon up
    for _ in range(40):
        i = rng.randrange(len(pts))
        p = pts[i]
        n = normals[i]
        w = widths[i] * rng.uniform(-0.35, 0.35)
        x = p[0] + n[0] * w
        y = p[1] + n[1] * w * depth
        rx = rng.uniform(3, 12)
        ry = rx * rng.uniform(0.15, 0.35)
        pygame.draw.ellipse(target, shade(palette["path"], rng.uniform(0.55, 0.85)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), max(1, int(ry * 2 * scale))))
    # leaf litter and stones, heavier at the edges
    for i in range(0, len(pts), 2):
        p = pts[i]
        n = normals[i]
        for _ in range(3):
            side = rng.choice((-1, 1))
            w = widths[i] * rng.uniform(0.55, 1.05) * side
            x = p[0] + n[0] * w + rng.uniform(-2, 2)
            y = p[1] + n[1] * w * depth + rng.uniform(-1.5, 1.5)
            if rng.random() < 0.55:
                rx = rng.uniform(0.8, 2.4)
                ry = rx * rng.uniform(0.35, 0.7)
                col = mix(palette["path_hi"],
                          palette["accent"], rng.uniform(0.0, 0.22))
                col = shade(col, rng.uniform(0.6, 1.0))
                pygame.draw.ellipse(target, col,
                                    (int((x - rx) * scale), int((y - ry) * scale),
                                     max(1, int(rx * 2 * scale)),
                                     max(1, int(ry * 2 * scale))))
            else:
                pygame.draw.ellipse(target, shade(palette["bank"], 1.35),
                                    (int((x - 1.2) * scale), int((y - 0.8) * scale),
                                     int(2.4 * scale), int(1.6 * scale)))
    # grass tufts at the edges, in ragged groups rather than a trim
    for group in range(round(len(pts) / 22) * (1 if preset["key"] == "strip" else 2)):
        base_i = rng.randrange(len(pts))
        p = pts[base_i]
        n = normals[base_i]
        side = rng.choice((-1, 1))
        w = widths[base_i] * side
        gx = p[0] + n[0] * w
        gy = p[1] + n[1] * w * depth
        for _ in range(rng.randint(3, 8)):
            bx = gx + rng.uniform(-9, 9)
            by = gy + rng.uniform(-1, 5)
            h = rng.uniform(4, 13)
            lean = rng.uniform(-4, 4)
            blade = [(bx + lean * (k / 3.0) ** 2, by - h * (k / 3.0))
                     for k in range(4)]
            pygame.draw.lines(target, shade(palette["bank"], rng.uniform(0.8, 1.3)),
                              False, spoints(blade, scale), 1)

    if preset["key"] == "portrait":
        # fade the trail into the mist at the top and the bank at the bottom
        start_y = preset["path"][0][1] + 70
        end_y = preset["path"][-1][1] + 20
        fade_in = start_y + 250
        fade_out = end_y - 150
        # NB: pygame.draw/fill ignore the alpha byte on SRCALPHA surfaces,
        # so the ramp has to be written per pixel and then stretched.
        ramp = pygame.Surface((1, layer.get_height()), pygame.SRCALPHA)
        for y in range(ramp.get_height()):
            if y <= start_y or y >= end_y:
                a = 0
            elif y < fade_in:
                a = int(255 * smoothstep((y - start_y) / max(1, fade_in - start_y)))
            elif y > fade_out:
                a = int(255 * (1.0 - smoothstep((y - fade_out) / max(1, end_y - fade_out))))
            else:
                a = 255
            ramp.set_at((0, y), (255, 255, 255, a))
        mask = pygame.transform.scale(ramp, layer.get_size())
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(layer, (0, 0))


def draw_bank(dst, scene, scale):
    preset = scene.preset
    palette = scene.palette
    wl = scene.waterline
    rng = random.Random(preset["seed"] + 29)
    # the far bank: a dark moss strip with a ragged lower edge
    pts_top = [(-20, wl - 16), (scene.width + 20, wl - 16)]
    pts_bottom = []
    x = scene.width + 30
    while x > -50:
        pts_bottom.append((x, wl + rng.uniform(-3.5, 3.0)))
        x -= rng.uniform(12, 34)
    poly = [(px * scale, py * scale) for px, py in pts_top + pts_bottom]
    pygame.draw.polygon(dst, palette["bank"], poly)

    # rocks half in the water break the waterline
    for _ in range(16):
        x = rng.uniform(-5, scene.width + 5)
        y = wl + rng.uniform(-1, 6)
        rx = rng.uniform(4, 16)
        ry = rx * rng.uniform(0.22, 0.45)
        pygame.draw.ellipse(dst, shade(palette["near_tree"], rng.uniform(1.1, 1.6)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), max(2, int(ry * 2 * scale))))
    # moss and stone clumps on the bank
    for _ in range(26):
        x = rng.uniform(-10, scene.width + 10)
        y = wl - rng.uniform(4, 16)
        rx = rng.uniform(5, 26)
        ry = rx * rng.uniform(0.18, 0.4)
        pygame.draw.ellipse(dst, shade(palette["bank"], rng.uniform(0.75, 1.35)),
                            (int((x - rx) * scale), int((y - ry) * scale),
                             int(rx * 2 * scale), max(2, int(ry * 2 * scale))))

    # reeds and grass clusters, not a fringe along the whole width
    clusters = max(4, preset["reeds"] // 2)
    for _ in range(clusters):
        cx = rng.uniform(-10, scene.width + 10)
        base_y = wl - rng.uniform(1, 12)
        h_max = rng.uniform(20, 46)
        for _ in range(rng.randint(4, 10)):
            x = cx + rng.uniform(-12, 12)
            base = base_y + rng.uniform(-2, 2)
            h = h_max * rng.uniform(0.45, 1.0)
            lean = rng.uniform(-9, 9)
            color = shade(palette["bank"], rng.uniform(0.8, 1.3))
            pts = []
            for j in range(6):
                t = j / 5.0
                pts.append((x + lean * t * t, base - h * t))
            pygame.draw.lines(dst, color, False, spoints(pts, scale),
                              max(1, int(1.0 * scale)))
            if rng.random() < 0.4:
                hx, hy = pts[-1]
                pygame.draw.ellipse(dst, shade(color, 1.2),
                                    (int((hx - 1) * scale), int((hy - 3) * scale),
                                     int(2 * scale), int(5 * scale)))

    if preset["key"] == "portrait":
        # a reed clump where the trail meets the water hides the trail's end
        end_x = preset["path"][-1][0]
        for _ in range(22):
            bx = end_x + rng.uniform(-46, 40)
            bh = rng.uniform(16, 46)
            lean = rng.uniform(-12, 12)
            pts = [(bx + lean * (k / 4.0) ** 2,
                    (wl + 3) - bh * (k / 4.0)) for k in range(5)]
            pygame.draw.lines(dst, palette["near_leaf"], False,
                              spoints(pts, scale), max(1, int(1.2 * scale)))

    # foreground reed clusters at the corners, kept out of the mode-number
    # corner (lower-left 80x32)
    corners = [(96, wl + 62, 1), (scene.width + 6, wl + 46, -1)]
    if preset["key"] == "portrait":
        corners = [(-10, wl + 250, 1), (scene.width + 10, wl + 210, -1),
                   (110, scene.height + 8, 1), (scene.width - 40, scene.height + 12, -1)]
    for cx, cy, side in corners:
        for i in range(18):
            base_x = cx + side * rng.uniform(-10, 60)
            base_y = cy + rng.uniform(-30, 26)
            h = rng.uniform(40, 130)
            lean = rng.uniform(-18, 18)
            pts = []
            for j in range(6):
                t = j / 5.0
                pts.append((base_x + lean * t * t, base_y - h * t))
            pygame.draw.lines(dst, palette["near_leaf"], False,
                              spoints(pts, scale), max(1, int(1.4 * scale)))
            if rng.random() < 0.5:
                hx, hy = pts[-1]
                pygame.draw.ellipse(dst, shade(palette["near_leaf"], 1.35),
                                    (int((hx - 1.5) * scale), int((hy - 4) * scale),
                                     int(3 * scale), int(8 * scale)))


def draw_water(dst, scene, scale):
    preset = scene.preset
    palette = scene.palette
    wl = scene.waterline
    width, height = scene.width, scene.height
    # base gradient, clipped to the water band
    band = vertical_gradient(
        (int(width * scale), int((height - wl) * scale)),
        [(0.0, palette["water_top"]),
         (0.10, palette["water_top"] if preset["key"] == "portrait" else palette["water_mid"]),
         (0.45, palette["water_mid"] if preset["key"] == "portrait" else palette["water_bot"]),
         (1.0, shade(palette["water_bot"], 0.6))])
    dst.blit(band, (0, int(wl * scale)))

    rng = random.Random(preset["seed"] + 43)
    overlay = pygame.Surface((int(width * scale), int((height - wl) * scale)),
                             pygame.SRCALPHA)
    # the far bank, mirrored: a dark, ragged band under the waterline
    top_edge = [(0, 3)]
    x = 0
    while x < width:
        top_edge.append((x, rng.uniform(2, 10)))
        x += rng.uniform(18, 44)
    top_edge.append((width, 3))
    mirror = [(int(px * scale), int(py * scale)) for px, py in top_edge]
    mirror += [(int(width * scale), int(30 * scale)), (0, int(30 * scale))]
    pygame.draw.polygon(overlay, with_alpha(shade(palette["near_tree"], 1.6), 150),
                        mirror)

    # horizontal ripples, denser and longer toward the near edge
    count = int(190 * (1.35 if preset["key"] == "portrait" else 1.0))
    for _ in range(count):
        t = rng.random() ** 1.55
        y = t * (height - wl - 2)
        x = rng.uniform(-30, width)
        length = rng.uniform(8, 130) * (0.45 + t * 1.8)
        col = mix(palette["water_line"], palette["water_top"],
                  rng.uniform(0.0, 0.65))
        alpha = int(rng.uniform(8, 52) * (0.45 + 0.55 * (1.0 - t)))
        pygame.draw.line(overlay, with_alpha(col, alpha),
                         (int(x * scale), int(y * scale)),
                         (int((x + length) * scale), int(y * scale)),
                         max(1, int(rng.uniform(1.0, 2.2) * scale)))
    # a pale reflected sky just under the bank
    sky_mirror = pygame.Surface((int(width * scale), int(26 * scale)),
                                pygame.SRCALPHA)
    for yy in range(sky_mirror.get_height()):
        a = int(26 * (1.0 - yy / max(1, sky_mirror.get_height() - 1)) ** 1.4)
        pygame.draw.line(sky_mirror, with_alpha(palette["mist"], a),
                         (0, yy), (sky_mirror.get_width(), yy))
    overlay.blit(sky_mirror, (0, 0))
    # pale glints where the water catches the sky, mostly near the far bank
    for _ in range(26):
        y = rng.uniform(1, 30)
        x0 = rng.uniform(0, width * 0.92)
        pygame.draw.line(overlay, with_alpha(palette["mist"], rng.uniform(6, 22)),
                         (int(x0 * scale), int(y * scale)),
                         (int((x0 + rng.uniform(20, 180)) * scale), int(y * scale)),
                         max(1, int(1.0 * scale)))
    dst.blit(overlay, (0, int(wl * scale)))


def make_mist_sprite(width, height, color, rng):
    """A soft horizontal fog band (low-res noise upscaled, then masked)."""
    lw, lh = max(12, int(width // 26)), max(4, int(height // 8))
    small = pygame.Surface((lw, lh), pygame.SRCALPHA)
    for y in range(lh):
        for x in range(lw):
            edge = math.sin(math.pi * (y + 0.5) / lh) ** 1.4
            a = int(255 * edge * rng.uniform(0.25, 1.0))
            small.set_at((x, y), with_alpha(color, a))
    soft = pygame.transform.smoothscale(small, (max(2, int(width)), max(2, int(height))))
    return blur_surface(soft, 3)


def draw_horizon_mist(dst, scene, scale):
    """Pale fog behind the tree-line: the only cool light in the wood."""
    rng = random.Random(scene.preset["seed"] + 67)
    wl = scene.waterline
    bands = ((-116, 150, 0.13), (-76, 110, 0.17), (-46, 70, 0.12))
    for dy, height, alpha in bands:
        sprite = make_mist_sprite((scene.width * 1.16) * scale,
                                  height * scale, scene.palette["mist"], rng)
        sprite = alpha_mul(sprite, alpha)
        dst.blit(sprite, (int((-40 + math.sin(dy) * 24) * scale),
                          int((wl + dy - height * 0.5) * scale)))


def draw_mist(dst, scene, scale, under_lanterns=True):
    rng = random.Random(scene.preset["seed"] + 71)
    layers = scene.mist_layers[1:] if under_lanterns else scene.mist_layers[:1]
    for index, (y, w, h, alpha, phase) in enumerate(layers):
        sprite = make_mist_sprite(w * scale, h * scale, scene.palette["mist"], rng)
        sprite = alpha_mul(sprite, alpha)
        x = -20 + math.sin(phase) * 30
        dst.blit(sprite, (int(x * scale), int((y - h * 0.5) * scale)))
    # a low fog bank at the waterline: three offset bands, no hard edge
    boost = 1.0 if scene.preset["key"] == "strip" else 1.45
    for i, (dy, alpha) in enumerate(((-14, 0.30 * boost), (-2, 0.42 * boost),
                                     (14, 0.26 * boost))):
        line = make_mist_sprite((scene.width * 1.2) * scale,
                                (18 + i * 6) * scale,
                                scene.palette["mist_lo"], rng)
        line = alpha_mul(line, alpha)
        dst.blit(line, (int((-40 + i * 18) * scale),
                        int((scene.waterline + dy) * scale)))


def draw_reflections(dst, scene, scale):
    wl = scene.waterline
    palette = scene.palette
    water_h = (scene.height - wl) * scale
    clip = pygame.Rect(0, int(wl * scale), int(scene.width * scale),
                       int(water_h))
    dst.set_clip(clip)
    ordered = sorted(scene.lanterns, key=lambda l: l.scale)
    for lantern in ordered:
        if not lantern.reflection or lantern.dim < 0.12:
            continue
        if scene.preset["key"] == "portrait" and lantern.path_y < 1180.0:
            continue
        sprite = lantern.sprite
        if sprite is None:
            continue
        rw, rh = sprite.get_size()
        refl = pygame.transform.flip(sprite, False, True)
        refl = blur_surface(refl, 2)
        refl = pygame.transform.smoothscale(
            refl, (max(2, int(rw * 1.0)), max(2, int(rh * 0.88))))
        refl_alpha = scene.preset["refl_alpha"] * lantern.dim
        if lantern.reflection_bias:
            # the signature: the lantern goes out, its reflection lingers
            refl_alpha = scene.preset["refl_alpha"] * 0.85
        if scene.preset["key"] == "portrait":
            nearness = max(0.0, min(1.0, (lantern.path_y - 1180.0) / 280.0)) ** 1.25
            refl_alpha *= 0.05 + 0.95 * nearness
        refl = alpha_mul(refl, refl_alpha)
        # vertical fade: strongest just under the source, then gone
        rw, rh = refl.get_size()
        fade = pygame.Surface((rw, rh), pygame.SRCALPHA)
        for y in range(rh):
            t = y / max(1, rh - 1)
            a = int(255 * (1.0 - t) ** (1.1 if scene.preset["key"] == "strip" else 0.75))
            pygame.draw.line(fade, (255, 255, 255, a), (0, y), (rw, y))
        refl.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        if scene.preset["key"] == "portrait":
            # The near bank is the reflecting edge; mirror each lantern just
            # past it instead of across the far horizon line, which would
            # throw the high lanterns' reflections to the bottom of the frame.
            center_y = max(wl + rh / (2.0 * scale) + 5.0,
                           lantern.path_y + 72.0)
        else:
            center_y = 2 * wl - lantern.y
        if lantern.reflection_bias:
            # a lantern already out over the water reflects below itself,
            # not across the far bank
            center_y = lantern.y + lantern.reflection_bias
        center_y *= scale
        top = center_y - rh * 0.5
        left = lantern.x * scale - rw * 0.5
        # warm pool, then the paper shape
        blit_glow(dst, (lantern.x * scale, center_y + rh * 0.10),
                  max(8, int(lantern.half_w * 4.6 * scale)),
                  palette["reflect"], power=1.6,
                  strength=(0.20 if scene.preset["key"] == "strip" else 0.38)
                  * lantern.dim, squash=2.1)
        # sliced paper reflection with a gentle ripple offset
        band = max(2, int(2.0 * scale))
        amp = 2.1 * lantern.scale * (0.55 if lantern.dim < 0.5 else 1.0) * scale
        phase = lantern.phase
        wl_dev = wl * scale
        for by in range(0, rh, band):
            dy = top + by
            if dy + band < wl_dev:
                continue
            depth = max(0.0, (dy - wl_dev) / max(1.0, water_h))
            dx = math.sin((dy - wl_dev) * 0.055 + phase) * amp * (0.35 + depth * 1.3)
            dst.blit(refl,
                     (int(left + dx), int(dy)),
                     area=(0, by, rw, min(band, rh - by)))
    # warm shimmer across the reflections
    shimmer = random.Random(scene.preset["seed"] + 133)
    for _ in range(90):
        ly = shimmer.uniform(wl + 3, scene.height)
        lx = shimmer.uniform(0, scene.width)
        length = shimmer.uniform(6, 40) * (1.0 + (ly - wl) / 80.0)
        alpha = int(shimmer.uniform(6, 22))
        col = mix(palette["reflect"], palette["accent"], shimmer.uniform(0.1, 0.6))
        layer = pygame.Surface((int(length * scale), max(1, int(1.2 * scale))),
                               pygame.SRCALPHA)
        layer.fill(with_alpha(col, alpha))
        dst.blit(layer, (int(lx * scale), int(ly * scale)))
    # broken ripple lines over the reflections, so they sit *in* the water
    rng = random.Random(scene.preset["seed"] + 131)
    for _ in range(70):
        y = rng.uniform(wl + 2, scene.height)
        x = rng.uniform(0, scene.width)
        length = rng.uniform(8, 55)
        pygame.draw.line(dst, shade(palette["water_top"], 1.35),
                         (int(x * scale), int(y * scale)),
                         (int((x + length) * scale), int(y * scale)),
                         1)
    dst.set_clip(None)


def draw_light_pools(dst, scene, scale):
    """Warm spill along the trodden path, under the whole procession."""
    for lantern in sorted(scene.lanterns, key=lambda l: l.scale):
        if lantern.dim < 0.5:
            continue
        y = lantern.path_y + 4.0
        wide = min(lantern.half_w * 11.0, 150.0 if scene.preset["key"] == "strip" else 190.0)
        tight = min(lantern.half_w * 4.2, 62.0 if scene.preset["key"] == "strip" else 74.0)
        blit_glow(dst, (lantern.x * scale, y * scale),
                  wide * scale, scene.palette["accent"],
                  power=1.8, strength=0.055 * lantern.dim, squash=0.18)
        blit_glow(dst, (lantern.x * scale, y * scale),
                  tight * scale, scene.palette["glow"],
                  power=2.0, strength=0.13 * lantern.dim, squash=0.22)


def draw_lanterns(dst, scene, scale):
    for lantern in sorted(scene.lanterns, key=lambda l: l.scale):
        strength = lantern.dim
        # ambient halo, then a hot core
        blit_glow(dst, (lantern.x * scale, lantern.y * scale),
                  lantern.half_w * (7.0 if lantern.scale > 1.0 else 5.8) * scale,
                  scene.palette["accent"], power=2.1,
                  strength=0.20 * strength)
        blit_glow(dst, (lantern.x * scale, lantern.y * scale),
                  lantern.half_w * 4.8 * scale, scene.palette["glow"],
                  power=2.2, strength=0.30 * strength)
        blit_glow(dst, (lantern.x * scale, lantern.y * scale),
                  lantern.half_w * 2.7 * scale, scene.palette["core"],
                  power=2.4, strength=0.48 * strength)
        sprite = lantern.sprite
        if sprite is None:
            continue
        rot = pygame.transform.rotozoom(sprite, lantern.tilt, 1.0)
        if lantern.dim < 1.0:
            rot = alpha_mul(rot, lantern.dim)
        dst.blit(rot, (int(lantern.x * scale - rot.get_width() * 0.5),
                       int(lantern.y * scale - rot.get_height() * 0.45)))


def draw_fireflies(dst, scene, scale, layer_filter=None):
    for x, y, radius, brightness, warm, layer in scene.fireflies:
        if layer_filter is not None and layer != layer_filter:
            continue
        color = scene.palette["firefly_warm"] if warm else scene.palette["firefly"]
        blit_glow(dst, (x * scale, y * scale), radius * 3.1 * scale, color,
                  power=2.0, strength=0.38 * brightness)
        blit_glow(dst, (x * scale, y * scale), radius * 0.95 * scale, color,
                  power=2.4, strength=1.0 * brightness)
        pygame.draw.circle(dst, mix(color, (255, 255, 255), 0.55),
                           (int(x * scale), int(y * scale)),
                           max(1, int(1.1 * scale * brightness)))


def draw_fern(dst, rng, x, base_y, size, color, scale):
    """A dark foreground fern: a few arcing stems with paired pinnae."""
    for _ in range(rng.randint(4, 7)):
        angle = rng.uniform(-1.25, 1.25) - math.pi / 2
        length = size * rng.uniform(0.55, 1.0)
        stem = []
        for j in range(7):
            t = j / 6.0
            sx = x + math.cos(angle) * length * t
            sy = base_y + math.sin(angle) * length * t + length * 0.30 * t * t
            stem.append((sx, sy))
        pygame.draw.lines(dst, color, False, spoints(stem, scale),
                          max(1, int(1.0 * scale)))
        for j in range(2, 6):
            t = j / 6.0
            sx, sy = stem[j]
            leaf_len = size * 0.22 * (1.0 - t) * rng.uniform(0.7, 1.2)
            for side in (-1, 1):
                ex = sx + side * leaf_len * math.cos(angle + 0.9)
                ey = sy + abs(leaf_len * math.sin(angle + 0.9)) * 0.55
                pygame.draw.line(dst, color, (int(sx * scale), int(sy * scale)),
                                 (int(ex * scale), int(ey * scale)),
                                 max(1, int(1.0 * scale)))


def draw_near_forest(dst, scene, scale):
    preset = scene.preset
    palette = scene.palette
    rng = random.Random(preset["seed"] + 101)
    width, height = scene.width, scene.height
    near = palette["near_tree"]
    # two very near trunks that frame the scene
    if preset["key"] == "strip":
        trunks = ((-26, 34, -0.2), (width + 20, 30, 0.45),
                  (8, 26, 0.02))
        for x, w, lean in trunks:
            draw_trunk(dst, rng, x * scale, (scene.waterline + 46) * scale,
                       -30 * scale, w * scale, near, lean, 2, palette,
                       highlight=shade(palette["bark_hi"], 0.28))
        # a forward trunk inside the frame breaks the even line of lanterns
        fx, fw = width * 0.705, 20.0
        draw_trunk(dst, rng, fx * scale, (scene.waterline + 22) * scale,
                   -30 * scale, fw * scale, shade(near, 1.25), 0.18, 2,
                   palette, highlight=shade(palette["bark_hi"], 0.24))
        rim = pygame.Surface(dst.get_size(), pygame.SRCALPHA)
        pygame.draw.line(rim, with_alpha(mix(palette["bark_hi"],
                                             palette["accent"], 0.30), 90),
                         (int((fx - fw * 0.45) * scale), int(30 * scale)),
                         (int((fx - fw * 0.55) * scale),
                          int((scene.waterline + 20) * scale)), 1)
        pygame.draw.line(rim, with_alpha(mix(palette["bark_hi"],
                                             palette["accent"], 0.20), 45),
                         (int((fx - fw * 0.20) * scale), int(30 * scale)),
                         (int((fx - fw * 0.25) * scale),
                          int((scene.waterline + 20) * scale)), 1)
        dst.blit(rim, (0, 0))
    else:
        trunks = ((-34, 52, 0.6), (width + 24, 48, -0.5),
                  (70, 24, 0.2), (width - 74, 28, -0.3))
        for x, w, lean in trunks:
            draw_trunk(dst, rng, x * scale, (height + 70) * scale,
                       -50 * scale, w * scale, near, lean, 2, palette,
                       highlight=shade(palette["bark_hi"], 0.24))

    # a heavy branch overhanging the top-right corner
    arm_rng = random.Random(preset["seed"] + 211)
    if preset["key"] == "strip":
        start = (width + 24, 40)
        elbow = (width * 0.90, 52)
        tip = (width * 0.735, 120)
    else:
        start = (width + 30, 190)
        elbow = (width * 0.88, 236)
        tip = (width * 0.66, 380)
    arm = [(start[0], start[1]), (elbow[0], elbow[1]), (tip[0], tip[1])]
    pygame.draw.lines(dst, near, False, spoints(arm, scale),
                      max(2, int(7 * scale)))
    pygame.draw.lines(dst, shade(near, 1.6), False, spoints(arm, scale),
                      max(1, int(1.0 * scale)))
    for i in range(9):
        t = i / 8.0
        bx = lerp(elbow[0], tip[0], t) + arm_rng.uniform(-30, 30)
        by = lerp(elbow[1], tip[1], t) + arm_rng.uniform(-26, 26)
        for _ in range(9):
            rx = arm_rng.uniform(5, 18) * (scale * 0.8)
            ry = rx * arm_rng.uniform(0.35, 0.7)
            pygame.draw.ellipse(dst, shade(near, arm_rng.uniform(0.8, 1.8)),
                                (int(bx * scale - rx), int(by * scale - ry),
                                 max(2, int(rx * 2)), max(1, int(ry * 2))))

    # dark leaf masses at the corners
    corners = ((0, -20, 1.4), (width, -20, 1.4),
               (0, height * 0.30, 0.8), (width, height * 0.26, 0.8))
    if preset["key"] == "portrait":
        corners = ((0, -40, 1.9), (width, -40, 1.9),
                   (0, height * 0.34, 1.1), (width, height * 0.30, 1.1),
                   (width * 0.32, -30, 0.7))
    for cxp, cyp, spread in corners:
        for _ in range(90):
            a = arm_rng.uniform(0, TAU)
            r = spread * arm_rng.uniform(0, 1.0) ** 0.6 * width * 0.075
            x = cxp + math.cos(a) * r * 1.7
            y = cyp + math.sin(a) * r
            rx = arm_rng.uniform(4, 17) * scale
            ry = rx * arm_rng.uniform(0.35, 0.7)
            pygame.draw.ellipse(dst, shade(palette["near_leaf"],
                                           arm_rng.uniform(0.8, 1.5)),
                                (int(x * scale - rx), int(y * scale - ry),
                                 max(2, int(rx * 2)), max(1, int(ry * 2))))

    # heavy overhanging boughs: the canopy must touch the trunks
    bough_rng = random.Random(preset["seed"] + 307)
    if preset["key"] == "strip":
        boughs = [((0.06, -30), (0.20, 55), (0.315, 118)),
                  ((0.49, -36), (0.405, 58), (0.355, 126)),
                  ((0.79, -26), (0.685, 72), (0.615, 148))]
    else:
        boughs = [((0.10, -40), (0.24, 150), (0.34, 310)),
                  ((0.58, -30), (0.47, 170), (0.40, 335)),
                  ((0.96, -30), (0.82, 200), (0.72, 360))]
    for start_u, elbow_u, tip_u in boughs:
        start = (start_u[0] * width, start_u[1])
        elbow = (elbow_u[0] * width, elbow_u[1])
        tip = (tip_u[0] * width, tip_u[1])
        pygame.draw.lines(dst, palette["near_tree"], False,
                          spoints([start, elbow, tip], scale),
                          max(2, int(5.5 * scale)))
        pygame.draw.lines(dst, shade(palette["near_tree"], 1.8), False,
                          spoints([start, elbow, tip], scale), 1)
        for i in range(7):
            t = i / 6.0
            bx = lerp(elbow[0], tip[0], t)
            by = lerp(elbow[1], tip[1], t)
            for _ in range(14):
                rx = bough_rng.uniform(4, 12) * scale
                ry = rx * bough_rng.uniform(0.3, 0.55)
                ox = bough_rng.uniform(-24, 24)
                oy = bough_rng.uniform(-14, 20)
                pygame.draw.ellipse(
                    dst, shade(palette["near_leaf"], bough_rng.uniform(0.9, 1.6)),
                    (int((bx + ox) * scale - rx), int((by + oy) * scale - ry),
                     max(2, int(rx * 2)), max(1, int(ry * 2))))

    # a broken reed line at the water's edge: it keeps the bank from reading
    # as a straight shelf and gives the reflections something to pass behind
    reed_rng = random.Random(preset["seed"] + 401)
    for _ in range(34 if preset["key"] == "strip" else 62):
        x = reed_rng.uniform(-10, width + 10)
        base_y = scene.waterline + reed_rng.uniform(0, 5)
        height = reed_rng.uniform(7, 24) if preset["key"] == "strip" else reed_rng.uniform(10, 32)
        for _ in range(reed_rng.randint(3, 7)):
            bx = x + reed_rng.uniform(-7, 7)
            bh = height * reed_rng.uniform(0.5, 1.0)
            lean = reed_rng.uniform(-5, 5)
            blade = [(bx + lean * (k / 3.0) ** 2, base_y - bh * (k / 3.0))
                     for k in range(4)]
            pygame.draw.lines(dst, palette["near_leaf"], False,
                              spoints(blade, scale), 1)

    # dark foreground ferns, anchored in the corners
    if preset["key"] == "strip":
        anchors = ((60, height + 6, 54), (width - 40, height + 10, 62),
                   (250, height + 2, 40))
    else:
        anchors = ((58, height + 12, 96), (width - 54, height + 16, 88),
                   (140, height - 130, 56), (width - 120, height - 160, 48))
    for x, y, size in anchors:
        draw_fern(dst, arm_rng, x, y, size, palette["near_leaf"], scale)


# ---------------------------------------------------------------------------
# Finish
# ---------------------------------------------------------------------------

def composite_bloom(screen, strength=0.55, threshold=86):
    w, h = screen.get_size()
    small = pygame.Surface((max(2, w // 4), max(2, h // 4)))
    pygame.transform.smoothscale(screen, small.get_size(), small)
    small.fill((threshold, threshold, threshold), special_flags=pygame.BLEND_RGB_SUB)
    k = int(140 + 160 * strength)
    small.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
    mid = pygame.Surface((max(2, w // 2), max(2, h // 2)))
    pygame.transform.smoothscale(small, mid.get_size(), mid)
    up = pygame.Surface((w, h))
    pygame.transform.scale(mid, (w, h), up)
    screen.blit(up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def apply_finish(screen, vignette=0.44, scanline_alpha=6):
    w, h = screen.get_size()
    qw, qh = max(2, w // 4), max(2, h // 4)
    small = pygame.Surface((qw, qh))
    cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
    maxd = math.hypot(cx, cy)
    for y in range(qh):
        for x in range(qw):
            r = math.hypot(x - cx, y - cy) / maxd
            dark = vignette * (max(0.0, r - 0.24) / 0.76) ** 1.6
            k = int(255 * max(0.05, 1.0 - dark))
            small.set_at((x, y), (k, k, k))
    finish = pygame.transform.smoothscale(small, (w, h))
    if scanline_alpha > 0:
        line_hex = 255 - scanline_alpha
        for y in range(0, h, 3):
            pygame.draw.line(finish, (line_hex, line_hex, line_hex), (0, y), (w, y), 1)
    screen.blit(finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


def add_grain(screen, amount=6):
    w, h = screen.get_size()
    rng = random.Random(9001)
    sw, sh = max(2, w // 3), max(2, h // 3)
    noise = pygame.Surface((sw, sh))
    for y in range(sh):
        for x in range(sw):
            v = rng.randint(236, 255)
            noise.set_at((x, y), (v, v, v))
    noise = pygame.transform.smoothscale(noise, (w, h))
    screen.blit(noise, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


# ---------------------------------------------------------------------------
# HUD (native resolution, after the downsample)
# ---------------------------------------------------------------------------

def draw_hud(screen, scene):
    preset = scene.preset
    palette = scene.palette
    width, height = screen.get_size()
    margin = preset["hud_margin"]
    title_font = font(SERIF_BOLD if preset["serif_title"] else MONO_BOLD,
                      preset["title_px"])
    sub_font = font(MONO, preset["sub_px"])
    tele_font = font(MONO, preset["tele_px"])
    eyebrow_font = font(MONO, preset["eyebrow_px"])

    # a very soft scrim under the top corners, so the title reads on canopy
    scrim_h = int(height * (0.20 if preset["key"] == "portrait" else 0.24))
    scrim = pygame.Surface((width, scrim_h), pygame.SRCALPHA)
    for y in range(scrim_h):
        a = int(112 * (1.0 - y / max(1, scrim_h - 1)) ** 1.7)
        pygame.draw.line(scrim, (2, 4, 3, a), (0, y), (width, y))
    screen.blit(scrim, (0, 0))

    x = margin
    y = margin
    eyebrow = tracked("SLOW WORLDS   ·   FANTASY", eyebrow_font,
                      shade(palette["structure"], 0.9),
                      preset["aux_track"] + 1, 190)
    screen.blit(eyebrow, (x, y))
    y += eyebrow.get_height() + (16 if preset["key"] == "portrait" else 8)

    lines = []
    for line in preset["title_lines"]:
        lines.append(tracked(line, title_font, palette["ink"],
                             preset["title_track"]))
    line_gap = 6 if preset["key"] == "strip" else 8
    for line in lines:
        screen.blit(line, (x, y))
        y += line.get_height() - 2 + line_gap
    y += 2
    rule_w = min(lines[0].get_width(), int(width * 0.34))
    pygame.draw.line(screen, shade(palette["structure"], 0.62),
                     (x, y), (x + rule_w, y), 1)
    y += 8
    subtitle = tracked(preset["subtitle"], sub_font,
                       mix(palette["ink_dim"], palette["ink"], 0.25),
                       preset["aux_track"], 235)
    screen.blit(subtitle, (x, y))

    # telemetry, top right
    tx = width - margin
    ty = margin
    first, second = preset["tele"]
    one = tracked(first, tele_font, palette["ink_dim"], preset["aux_track"], 225)
    two = tracked(second, tele_font, shade(palette["structure"], 0.95),
                  preset["aux_track"], 205)
    screen.blit(one, (tx - one.get_width(), ty))
    ty += one.get_height() + 7
    screen.blit(two, (tx - two.get_width(), ty))

    # a small moon-mark beside the telemetry, like a stamped seal
    seal_r = 2 if preset["key"] == "strip" else 3
    seal_x = tx - one.get_width() - 14
    pygame.draw.circle(screen, shade(palette["structure"], 1.1),
                       (seal_x, margin + one.get_height() // 2), seal_r, 1)
    pygame.draw.circle(screen, shade(palette["accent"], 0.9),
                       (seal_x, margin + one.get_height() // 2), 1)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(preset, palette_name="moss", event=False):
    palette = PALETTES[palette_name]
    scene = Scene(preset, palette, preset["seed"])
    if event:
        scene.plan_event()
    scene.build_sprites(SS)

    width, height = preset["size"]
    big_size = (width * SS, height * SS)
    big = pygame.Surface(big_size)
    big.fill(palette["bg_top"])

    # 1. sky, moon haze
    sky = vertical_gradient(
        big_size,
        [(0.0, palette["bg_top"]), (0.42, palette["bg_mid"]),
         (0.74, palette["sky_low"]), (1.0, shade(palette["sky_low"], 1.1))])
    big.blit(sky, (0, 0))
    moon_x = width * (0.60 if preset["key"] == "strip" else 0.66)
    moon_y = height * (0.10 if preset["key"] == "strip" else 0.15)
    blit_glow(big, (moon_x * SS, moon_y * SS), 210 * SS, palette["moon"],
              power=2.4, strength=0.13)
    blit_glow(big, (moon_x * SS, moon_y * SS), 78 * SS, palette["haze"],
              power=2.6, strength=0.10)
    # a pale moon-glow, far behind the trees: no disc, just the light it
    # leaves in the mist (the lanterns are the only bright objects on purpose)
    fog_x = width * (0.64 if preset["key"] == "strip" else 0.60)
    fog_y = height * (0.30 if preset["key"] == "strip" else 0.26)
    blit_glow(big, (fog_x * SS, fog_y * SS),
              (width * (0.22 if preset["key"] == "strip" else 0.34)) * SS,
              palette["moon"], power=2.6, strength=0.045)
    star_rng = random.Random(preset["seed"] + 3)
    for _ in range(18):
        sx = star_rng.uniform(0.12, 0.88) * width
        sy = star_rng.uniform(0.02, 0.12) * height
        a = star_rng.uniform(0.10, 0.35)
        pygame.draw.circle(big, mix(palette["bg_top"], palette["ink"], a),
                           (int(sx * SS), int(sy * SS)),
                           max(1, int(star_rng.uniform(0.6, 1.3) * SS)))

    # 2. a pale fog band behind the tree-line
    draw_horizon_mist(big, scene, SS)

    # 3. far forest: a handful of trees in the mist
    far = pygame.Surface(big_size, pygame.SRCALPHA)
    rng = random.Random(preset["seed"] + 5)
    draw_canopy_roof(far, rng, palette, width, height, 0, SS)
    draw_far_treeline(far, rng, palette, scene, SS)
    # two or three taller far trees give the line some timber
    for u in (0.18, 0.70):
        x = u * width + rng.uniform(-24, 24)
        base = scene.waterline + rng.uniform(-10, 2)
        top = rng.uniform(45, 80)
        crown_cy = rng.uniform(150, 185) if preset["key"] == "strip" else rng.uniform(260, 340)
        draw_tree(far, rng, palette, x, base, top, rng.uniform(4, 7), 0, SS,
                  crown_cy=crown_cy, crown_rx=rng.uniform(38, 60),
                  crown_ry=rng.uniform(20, 30), lobe_count=5)
    for anchor in ((0.10, 0.30, 0.50, 0.70, 0.90)
                   if preset["key"] == "strip" else ()):
        for _ in range(2 if preset["key"] == "strip" else 1):
            x = anchor * width + rng.uniform(-48, 48)
            top = rng.uniform(60, 150)
            w = rng.uniform(2.0, 6.0)
            lean = rng.uniform(-14, 14)
            pts = [(x, scene.waterline), (x + lean * 0.4, (top + scene.waterline) * 0.5),
                   (x + lean, top)]
            pygame.draw.lines(far, shade(palette["far_tree"], rng.uniform(0.30, 0.55)),
                              False, spoints(pts, SS),
                              max(1, int(w * SS)))
    far = blur_surface(far, 3)
    big.blit(far, (0, 0))

    # 4. mid forest: fewer, heavier trees with undergrowth
    mid = pygame.Surface(big_size, pygame.SRCALPHA)
    rng = random.Random(preset["seed"] + 11)
    draw_canopy_roof(mid, rng, palette, width, height, 1, SS)
    mid_x = ([0.135, 0.345, 0.565, 0.760, 0.905]
             if preset["key"] == "strip" else
             [0.12, 0.62, 0.88])
    for u in mid_x:
        x = u * width + rng.uniform(-24, 24)
        for _ in range(2 if preset["key"] == "strip" else 1):
            cx = x + rng.choice((-1, 1)) * rng.uniform(24, 70)
            cw = rng.uniform(5, 12)
            draw_trunk(mid, rng, cx * SS,
                       (scene.waterline + rng.uniform(-4, 12)) * SS,
                       -30 * SS, cw * SS,
                       shade(palette["mid_tree"], rng.uniform(0.7, 1.1)),
                       rng.uniform(-0.6, 0.6), 1, palette)
        base = scene.waterline + rng.uniform(-6, 10)
        top = -30
        trunk_w = rng.uniform(12, 24) if preset["key"] == "strip" else rng.uniform(24, 40)
        crown_cy = rng.uniform(40, 110) if preset["key"] == "strip" else rng.uniform(90, 230)
        crown_rx = rng.uniform(60, 110) if preset["key"] == "strip" else rng.uniform(90, 160)
        crown_ry = crown_rx * rng.uniform(0.42, 0.60)
        draw_tree(mid, rng, palette, x, base, top, trunk_w, 1, SS,
                  crown_cy=crown_cy, crown_rx=crown_rx, crown_ry=crown_ry,
                  lobe_count=7)
    # low understory along the forest floor
    for _ in range(46):
        x = rng.uniform(-20, width + 20)
        y = scene.waterline - rng.uniform(-2, 46)
        rx = rng.uniform(10, 40)
        ry = rx * rng.uniform(0.35, 0.65)
        pygame.draw.ellipse(mid, shade(palette["mid_lean"],
                                       rng.uniform(0.5, 0.95)),
                            (int((x - rx) * SS), int((y - ry) * SS),
                             int(rx * 2 * SS), int(ry * 2 * SS)))
    big.blit(mid, (0, 0))

    # 4b. a wide fog band where the trail comes out of the trees
    if preset["key"] == "portrait":
        fog_rng = random.Random(preset["seed"] + 311)
        fog = make_mist_sprite(width * 1.3 * SS, 150 * SS,
                               palette["mist"], fog_rng)
        fog = alpha_mul(fog, 0.20)
        big.blit(fog, (int(-width * 0.12 * SS),
                       int((scene.path[0][1] + 110) * SS)))

    # 5. path and bank, with a low warm lift behind the procession
    for lantern in scene.lanterns:
        if lantern.scale < 0.6:
            continue
        blit_glow(big, (lantern.x * SS, (lantern.y + 26) * SS),
                  lantern.half_w * 13.0 * SS, palette["accent"],
                  power=2.1, strength=0.045, squash=0.55)
    draw_path(big, scene, SS)
    draw_bank(big, scene, SS)

    # 6. water
    draw_water(big, scene, SS)

    # 7. reflections and their light streaks
    draw_reflections(big, scene, SS)

    # 8. mist over the water
    draw_mist(big, scene, SS, under_lanterns=True)

    # 9. lantern light
    draw_light_pools(big, scene, SS)
    sheen = []
    for lantern in scene.lanterns:
        if lantern.dim >= 0.5:
            sheen.append((lantern.x, lantern.path_y + 2.0))
    if len(sheen) > 1:
        pygame.draw.lines(big, palette["path_hi"], False,
                          spoints(sheen, SS), max(1, int(1.2 * SS)))
    draw_lanterns(big, scene, SS)

    # 10. fireflies behind the near frame
    draw_fireflies(big, scene, SS, layer_filter=0)
    draw_fireflies(big, scene, SS, layer_filter=1)
    draw_fireflies(big, scene, SS, layer_filter=2)

    # 11. near forest frame and a couple of fireflies in front
    draw_near_forest(big, scene, SS)
    for x, y, radius, brightness, warm, layer in scene.fireflies[:3]:
        color = palette["firefly_warm"] if warm else palette["firefly"]
        blit_glow(big, (x * SS, y * SS), radius * 2.0 * SS, color,
                  power=2.0, strength=0.4 * brightness)

    # 12. downsample, bloom, grade, grain
    screen = pygame.transform.smoothscale(big, (width, height))
    composite_bloom(screen, strength=0.34, threshold=82)
    apply_finish(screen, vignette=0.52, scanline_alpha=2)
    add_grain(screen, 5)

    # 13. crisp HUD
    draw_hud(screen, scene)
    return screen


def palette_study():
    """Three palettes on the strip, stacked with small labels."""
    panel_w, panel_h = 1280, 400
    gap = 30
    sheet = pygame.Surface((panel_w, panel_h * 3 + gap * 2))
    sheet.fill((2, 3, 2))
    label_font = font(MONO_BOLD, 13)
    note_font = font(MONO, 10)
    for index, name in enumerate(("moss", "indigo", "mono")):
        image = render(STRIP, name)
        y = index * (panel_h + gap)
        sheet.blit(image, (0, y))
        palette = PALETTES[name]
        blit_text(sheet, palette["label"], (16, y + panel_h + 8), label_font,
                  palette["ink"], 3)
        blit_text(sheet, palette["note"], (110, y + panel_h + 10), note_font,
                  palette["ink_faint"], 1)
        pygame.draw.line(sheet, shade(palette["structure"], 0.6),
                         (0, y + panel_h + gap - 1),
                         (panel_w, y + panel_h + gap - 1), 1)
    return sheet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=("strip", "portrait", "palette",
                                           "event", "all"), default="all")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    jobs = []
    if args.only in ("strip", "all"):
        jobs.append((STRIP, "moss", False, "lantern_1280x400.png"))
    if args.only in ("portrait", "all"):
        jobs.append((PORTRAIT, "moss", False, "lantern_1080x1920.png"))
    if args.only in ("event", "all"):
        jobs.append((STRIP, "moss", True, "lantern_1280x400_lantern_out.png"))
    for preset, palette_name, event, filename in jobs:
        image = render(preset, palette_name, event)
        path = os.path.join(OUT_DIR, filename)
        pygame.image.save(image, path)
        print(f"wrote {os.path.relpath(path, BASE_DIR)}")

    if args.only in ("palette", "all"):
        sheet = palette_study()
        path = os.path.join(OUT_DIR, "palette_study.png")
        pygame.image.save(sheet, path)
        print(f"wrote {os.path.relpath(path, BASE_DIR)}")

    pygame.quit()


if __name__ == "__main__":
    main()
