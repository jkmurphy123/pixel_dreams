"""Lantern Procession — Slow Worlds §5.11.

A line of paper lanterns winds through a dark forest and along the edge of a
stream.  Each lantern is a warm paper sprite with an invented sigil, a small
bob and a reflection; fireflies drift between the trunks, mist sits low over
the water, and every couple of minutes one lantern leaves the line, drifts down
to the stream and goes out while its reflection lingers.

The composition is chosen by aspect class, not stretched from one frame:

  * the 1280x400 strip uses the width as distance - the trail recedes through a
    winding line and comes forward to the right, so the lanterns grow as they
    approach;
  * the 1080x1920 portrait sends the trail down from the trees to the near bank
    in an S, with the largest lanterns just above the water and their
    reflections at the bank;
  * 16:9 and square get their own presets.

The forest, trail, bank, water base and near framing are built once and cached;
only lanterns, glows, reflections, ripples, mist, fireflies and the signature
event are drawn per frame.  There is no disk I/O, network, audio or thread.
The lower-left 80x32 px stays dark for the controller's mode number.

Config: seed, palette (moss/indigo/mono), hud (none/minimal/full), quality
(auto/low/medium/high), orientation (auto/ultrawide/landscape/portrait/square),
lantern_count, speed, sigil_set, reflection, mist, departure_seconds, flicker,
title, subtitle, glow_strength, scanline_alpha, vignette_strength.
"""
from __future__ import annotations

import math
import random
import re

import pygame

TAU = math.tau
SIGIL_KINDS = 8


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


PRESETS = {
    "ultrawide": {
        "base": (1280, 400), "key": "strip",
        "path": [(-90, 262), (210, 276), (460, 262), (700, 278),
                 (950, 272), (1180, 288), (1370, 296)],
        "waterline": 300.0, "path_width": 31.0, "path_depth": 0.38,
        "lantern_w": 17.25, "hover": 27.0, "hover_fixed": True, "lane": 70.0,
        "scale_min": 0.34, "scale_max": 2.10, "curve": "recede",
        "refl_anchor": "waterline", "reeds": 26, "reflection_alpha": 0.70,
        "fireflies": 28, "margin": 26, "title_px": 24, "sub_px": 10,
        "tele_px": 10, "eyebrow_px": 9, "title_track": 2, "aux_track": 2,
        "event_x": 0.62, "event_dy": -9.0,
    },
    "portrait": {
        "base": (1080, 1920), "key": "portrait",
        "path": [(800, 360), (742, 540), (648, 760), (748, 960),
                 (612, 1170), (452, 1340), (300, 1468), (258, 1500)],
        "waterline": 1500.0, "path_width": 30.0, "path_depth": 0.88,
        "lantern_w": 25.5, "hover": 42.0, "hover_fixed": True, "lane": 90.0,
        "scale_min": 0.38, "scale_max": 1.70, "curve": "recede",
        "refl_anchor": "nearbank", "reeds": 20, "reflection_alpha": 0.74,
        "fireflies": 36, "margin": 48, "title_px": 46, "sub_px": 15,
        "tele_px": 14, "eyebrow_px": 12, "title_track": 2, "aux_track": 2,
        "event_x": 0.28, "event_dy": -10.0,
    },
    "landscape": {
        "base": (1920, 1080), "key": "strip",
        "path": [(-120, 590), (300, 640), (700, 585), (1060, 690),
                 (1420, 635), (1760, 770), (2040, 840)],
        "waterline": 860.0, "path_width": 38.0, "path_depth": 0.45,
        "lantern_w": 27.0, "hover": 60.0, "hover_fixed": True, "lane": 105.0,
        "scale_min": 0.34, "scale_max": 2.15, "curve": "recede",
        "refl_anchor": "waterline", "reeds": 34, "reflection_alpha": 0.70,
        "fireflies": 40, "margin": 40, "title_px": 30, "sub_px": 13,
        "tele_px": 12, "eyebrow_px": 11, "title_track": 2, "aux_track": 2,
        "event_x": 0.55, "event_dy": -12.0,
    },
    "square": {
        "base": (720, 720), "key": "portrait",
        "path": [(600, 120), (520, 260), (590, 380), (470, 500),
                 (360, 570), (280, 610)],
        "waterline": 630.0, "path_width": 20.0, "path_depth": 0.85,
        "lantern_w": 15.0, "hover": 24.0, "hover_fixed": True, "lane": 45.0,
        "scale_min": 0.40, "scale_max": 1.55, "curve": "recede",
        "refl_anchor": "nearbank", "reeds": 14, "reflection_alpha": 0.68,
        "fireflies": 22, "margin": 30, "title_px": 28, "sub_px": 11,
        "tele_px": 10, "eyebrow_px": 9, "title_track": 2, "aux_track": 1,
        "event_x": 0.30, "event_dy": -8.0,
    },
}


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


_GLOW_BLIT_CACHE: dict = {}
_GLOW_BLIT_LIMIT = 220


def blit_glow(dst, center, radius_px, color, power=2.2, strength=1.0,
              squash=1.0):
    """Add a tinted, cached radial glow.

    The tint (strength) is baked into the cache key.  Building a new sprite is
    cheap and happens once per (radius, colour, power, squash) bucket; per-frame
    blits must never copy or fill a large surface.
    """
    if radius_px < 2 or strength <= 0.004:
        return
    radius_px = max(2, int(round(radius_px / 8.0)) * 8)
    strength = max(0.0, min(1.0, round(strength * 10.0) / 10.0))
    key = (radius_px, shade(color, strength), power, round(squash, 2))
    sprite = _GLOW_BLIT_CACHE.get(key)
    if sprite is None:
        sprite = glow_sprite(radius_px, shade(color, strength), power)
        if squash != 1.0:
            sprite = pygame.transform.smoothscale(
                sprite, (sprite.get_width(),
                         max(2, int(sprite.get_height() * squash))))
        if len(_GLOW_BLIT_CACHE) >= _GLOW_BLIT_LIMIT:
            for old_key in list(_GLOW_BLIT_CACHE)[: _GLOW_BLIT_LIMIT // 2]:
                _GLOW_BLIT_CACHE.pop(old_key, None)
        _GLOW_BLIT_CACHE[key] = sprite
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
    if isinstance(sigil, str):
        glyph_font = pygame.font.Font(None, max(8, int(half_h * 1.25)))
        glyph = glyph_font.render(sigil[:2], True, palette["sigil"])
        gw, gh = max(1, int(half_w * 1.25)), max(1, int(half_h * 0.90))
        if glyph.get_width() > gw or glyph.get_height() > gh:
            k = min(gw / max(1, glyph.get_width()), gh / max(1, glyph.get_height()))
            glyph = pygame.transform.smoothscale(
                glyph, (max(1, int(glyph.get_width() * k)),
                        max(1, int(glyph.get_height() * k))))
        surf.blit(glyph, (int(cx - glyph.get_width() * 0.5),
                          int(cy + half_h * 0.02 - glyph.get_height() * 0.5)))
    else:
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
    return surf, cx, cy


class BuildScene:
    """The static geometry bundle the painting functions expect."""

    def __init__(self, layout, palette, seed):
        self.width = layout["width"]
        self.height = layout["height"]
        self.waterline = layout["waterline"]
        self.path = layout["path"]
        self.preset = layout
        self.palette = palette
        self.seed = seed


# ---------------------------------------------------------------------------
# The mode
# ---------------------------------------------------------------------------

DEFAULT_TITLE = "LANTERN PROCESSION"
DEFAULT_SUBTITLE = "A PROCESSION THROUGH THE NIGHT WOOD"
HUD_MODES = ("none", "minimal", "full")
QUALITY_NAMES = ("auto", "low", "medium", "high")
ORIENTATIONS = ("auto", "ultrawide", "landscape", "portrait", "square")

QUALITY = {
    "low": {"fireflies": 14, "reflection_bands": 6, "bloom": False,
            "grain": False, "mist": 2},
    "medium": {"fireflies": 26, "reflection_bands": 10, "bloom": True,
               "grain": False, "mist": 3},
    "high": {"fireflies": 40, "reflection_bands": 14, "bloom": True,
             "grain": True, "mist": 3},
}


def aspect_class(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
    if aspect >= 1.2:
        return "landscape"
    if aspect <= 0.85:
        return "portrait"
    return "square"


class LanternMeta:
    """One lantern's fixed identity and its offset along the cached path."""

    __slots__ = ("index", "offset", "sigil", "phase", "lane", "size_jitter",
                 "height_ratio", "tilt_phase")

    def __init__(self, index, offset, sigil, phase, lane, size_jitter,
                 height_ratio, tilt_phase):
        self.index = index
        self.offset = offset
        self.sigil = sigil
        self.phase = phase
        self.lane = lane
        self.size_jitter = size_jitter
        self.height_ratio = height_ratio
        self.tilt_phase = tilt_phase


class LanternState:
    """One lantern's position for one frame (normal or signature event)."""

    __slots__ = ("index", "sigil", "x", "y", "scale", "half_w", "bucket",
                 "phase", "tilt", "dim", "path_y", "u", "reflection_alpha",
                 "event", "height_ratio")

    def __init__(self, index, sigil, x, y, scale, half_w, bucket, phase, tilt,
                 dim, path_y, u, reflection_alpha, event, height_ratio):
        self.index = index
        self.sigil = sigil
        self.x = x
        self.y = y
        self.scale = scale
        self.half_w = half_w
        self.bucket = bucket
        self.phase = phase
        self.tilt = tilt
        self.dim = dim
        self.path_y = path_y
        self.u = u
        self.reflection_alpha = reflection_alpha
        self.event = event
        self.height_ratio = height_ratio


class LanternProcessionMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.diagnostic = ""
        self.seed = None

        self._pinned_seed = None
        self._palette_name = "moss"
        self._palette = PALETTES["moss"]
        self._lantern_count = 14
        self._speed = 6.0
        self._reflection = True
        self._mist = True
        self._flicker = True
        self._departure_seconds = 120.0
        self._glow_strength = 0.75
        self._scanlines = 2
        self._vignette = 0.40
        self._hud_mode = "minimal"
        self._orientation = "auto"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._title = DEFAULT_TITLE
        self._subtitle = DEFAULT_SUBTITLE
        self._sigils = list(range(SIGIL_KINDS))

        self._time = 0.0
        self._start_time = 0.0
        self._screen_size = None
        self._built_size = None
        self._layout = None
        self._path = []
        self._lengths = []
        self._path_len = 0.0
        self._lantern_meta = []
        self._fireflies = []
        self._mist_layers = []
        self._ripples = []
        self._event = None
        self._event_count = 0
        self._next_event = float("inf")
        self._event_rng = None
        self._last_states = []
        self._states = []
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
    def _text(config, key, default, max_length=48):
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

        palette_name = str(cfg.get("palette", "moss")).lower()
        if palette_name not in PALETTES:
            raise ValueError("palette must be " + ", ".join(PALETTES))
        self._palette_name = palette_name
        self._palette = PALETTES[palette_name]

        self._lantern_count = self._integer(cfg, "lantern_count", 14, 8, 20)
        self._speed = self._number(cfg, "speed", 6.0, 1.0, 12.0)
        self._reflection = self._bool(cfg, "reflection", True)
        self._mist = self._bool(cfg, "mist", True)
        self._flicker = self._bool(cfg, "flicker", True)
        self._departure_seconds = self._number(cfg, "departure_seconds", 120.0,
                                               0.0, 600.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.75, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 2.0, 0.0, 40.0))
        self._vignette = self._number(cfg, "vignette_strength", 0.40, 0.0, 1.0)

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

        self._title = self._text(cfg, "title", DEFAULT_TITLE, 48) or DEFAULT_TITLE
        self._subtitle = self._text(cfg, "subtitle", DEFAULT_SUBTITLE, 72) \
            or DEFAULT_SUBTITLE
        self._sigils = self._parse_sigils(cfg.get("sigil_set"))

    def _parse_sigils(self, raw):
        builtin = list(range(SIGIL_KINDS))
        if raw is None or raw == "":
            return builtin
        if isinstance(raw, str):
            items = [part for part in re.split(r"[,\s]+", raw) if part]
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            print("[Lantern] sigil_set ignored: expected a list of 1-3 character glyphs")
            return builtin
        out = []
        for item in items:
            if isinstance(item, str):
                item = item.strip()
                if 1 <= len(item) <= 3:
                    out.append(item)
                else:
                    print("[Lantern] sigil_set ignored: each glyph must be 1-3 characters")
                    return builtin
            elif type(item) is int and 0 <= item < SIGIL_KINDS:
                out.append(item)
            else:
                print("[Lantern] sigil_set ignored: use 1-3 character strings")
                return builtin
        return out[:16] or builtin

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            self.seed = self._next_seed()
            rng = random.Random(self.seed)
            self._time = rng.uniform(0.0, 900.0)
            self._start_time = self._time
            self._event_rng = random.Random(self.seed ^ 0x1A27E7)
            self._event_count = 0
            self._event = None
            if self._departure_seconds > 0.0:
                self._next_event = self._time + self._event_rng.uniform(35.0, 75.0)
            else:
                self._next_event = float("inf")
            self._quality = ("medium" if self._auto_quality
                             else self._quality_setting)
            self._quality_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self._build(manager.screen.get_size())
            self.error = None
            print(f"[Lantern] seed={self.seed} preset={self._layout['preset']} "
                  f"lanterns={self._lantern_count} palette={self._palette_name} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Lantern] configuration error: {exc}")

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def exit(self):
        self.manager = None
        self.error = None
        self._clear_caches()
        _GLOW_BLIT_CACHE.clear()
        self._built_size = None
        self._screen_size = None
        self._layout = None
        self._path = []
        self._lengths = []
        self._path_len = 0.0
        self._lantern_meta = []
        self._fireflies = []
        self._mist_layers = []
        self._ripples = []
        self._event = None
        self._last_states = []
        self._time = 0.0

    def _clear_caches(self):
        self._back = None
        self._front = None
        self._sprite_cache = {}
        self._reflection_cache = {}
        self._hud = None
        self._scrim = None
        self._finish = None
        self._grain = None
        self._bloom_small = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_steps_key = None
        self._hud_steps_surface = None
        self._hud_count_key = None
        self._hud_count_surface = None

    def handle_event(self, event):
        """The controller owns input; this mode has none."""

    # ---------------------------------------------------------------- frame state

    def update(self, dt: float):
        if self.manager is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._time += dt
        self._update_quality(dt)
        self._update_event()

    def _update_quality(self, dt: float) -> None:
        if not self._auto_quality:
            return
        self._quality_ema += (dt - self._quality_ema) * 0.06
        target = self._quality
        if self._quality == "high":
            if self._quality_ema > (1.0 / 26.0):
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
            elif self._quality_ema < (1.0 / 30.0):
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
            print(f"[Lantern] {self.diagnostic}")

    # ---------------------------------------------------------------- event

    def _lit_count(self) -> int:
        if self._event is not None:
            end = (self._event["start"] + self._event["duration"]
                   + self._event["afterglow"])
            if self._time <= end:
                return max(0, self._lantern_count - 1)
        return self._lantern_count

    def _update_event(self):
        if self._event is not None:
            end = (self._event["start"] + self._event["duration"]
                   + self._event["afterglow"])
            if self._time > end:
                self._finish_event()
            return
        if self._departure_seconds <= 0.0:
            return
        if self._time >= self._next_event:
            self.start_departure()

    def start_departure(self, index=None):
        """Send one lantern out over the water (also used by the preview still)."""
        if self._layout is None or self._event is not None:
            return
        states = self._compute_states(self._time, with_event=False)
        candidates = [s for s in states if 0.18 < s.u < 0.82 and s.dim > 0.6]
        if index is None:
            if not candidates:
                return
            state = self._event_rng.choice(candidates) if self._event_rng else candidates[0]
        else:
            state = next((s for s in states if s.index == index), None)
            if state is None:
                return
        target = self._layout["event_target"]
        self._event = {
            "index": state.index,
            "start": self._time,
            "duration": 18.0,
            "afterglow": 3.0,
            "start_x": state.x,
            "start_y": state.y,
            "start_scale": state.scale,
            "start_half_w": state.half_w,
            "start_u": state.u,
            "target_x": target[0],
            "target_y": target[1],
        }
        self._event_count += 1
        self._next_event = float("inf")

    def _finish_event(self):
        event = self._event
        if event is None:
            return
        meta = self._lantern_meta[event["index"]]
        # Re-enter beyond the start of the path; the edge fade hides the pop.
        meta.offset = (-self._speed * self._time) % self._path_len
        self._event = None
        if self._departure_seconds > 0.0 and self._event_rng is not None:
            self._next_event = (self._time
                                + self._event_rng.uniform(0.75, 1.33)
                                * self._departure_seconds)

    # ---------------------------------------------------------------- geometry

    def _resolve_layout(self, size) -> dict:
        width, height = int(size[0]), int(size[1])
        name = (aspect_class(width, height)
                if self._orientation == "auto" else self._orientation)
        preset = PRESETS[name]
        base_w, base_h = preset["base"]
        sx = width / base_w
        sy = height / base_h
        pscale = min(sx, sy)
        margin = max(9, int(round(preset["margin"] * pscale)))
        path = [(x * sx, y * sy) for x, y in preset["path"]]
        waterline = preset["waterline"] * sy
        layout = {
            "preset": name,
            "key": preset["key"],
            "width": width,
            "height": height,
            "base": (base_w, base_h),
            "sx": sx,
            "sy": sy,
            "pscale": pscale,
            "path": path,
            "waterline": waterline,
            "water_rect": pygame.Rect(0, int(waterline), width,
                                      max(1, height - int(waterline))),
            "path_width": preset["path_width"] * sx,
            "path_depth": preset["path_depth"],
            "path_fade": preset.get("path_fade", False),
            "lantern_w": preset["lantern_w"] * sx,
            "hover": preset["hover"] * sy,
            "hover_fixed": preset.get("hover_fixed", True),
            "lane": preset["lane"] * sx,
            "scale_min": preset["scale_min"],
            "scale_max": preset["scale_max"],
            "curve": preset["curve"],
            "refl_anchor": preset["refl_anchor"],
            "reeds": preset["reeds"],
            "reflection_alpha": preset["reflection_alpha"],
            "margin": margin,
            "title_px": max(12, int(round(preset["title_px"] * pscale))),
            "sub_px": max(8, int(round(preset["sub_px"] * pscale))),
            "tele_px": max(8, int(round(preset["tele_px"] * pscale))),
            "eyebrow_px": max(7, int(round(preset["eyebrow_px"] * pscale))),
            "title_track": preset["title_track"],
            "aux_track": preset["aux_track"],
            "event_target": (preset["event_x"] * width,
                             waterline + preset["event_dy"] * sy),
            "seed": self.seed,
        }
        return layout

    def _scale_for(self, u: float) -> float:
        layout = self._layout
        if layout["curve"] == "edges":
            t = (abs(u - 0.5) * 2.0) ** 1.55
        else:
            t = max(0.0, min(1.0, u)) ** 1.28
        return lerp(layout["scale_min"], layout["scale_max"], t)

    # ---------------------------------------------------------------- build

    def _build(self, size):
        size = (int(size[0]), int(size[1]))
        if self._built_size == size and self._back is not None:
            return
        self._clear_caches()
        self._screen_size = size
        self._layout = self._resolve_layout(size)
        self._path = catmull_rom(self._layout["path"])
        self._lengths = path_lengths(self._path)
        self._path_len = self._lengths[-1]
        self._build_lanterns()
        self._build_fireflies()
        self._build_mist()
        self._build_ripples()
        self._build_scrim()
        self._build_background()
        self._build_finish()
        self._build_hud()
        self._event = None
        self._next_event = (self._time
                            + self._event_rng.uniform(35.0, 75.0)
                            if self._event_rng is not None
                            and self._departure_seconds > 0.0
                            else float("inf"))
        self._built_size = size
        self._last_states = []

    def _build_lanterns(self):
        layout = self._layout
        count = self._lantern_count
        spacing = self._path_len / max(1, count)
        rng = random.Random(self.seed ^ 0x51A9E)
        self._lantern_meta = []
        for i in range(count):
            sigil = self._sigils[i % len(self._sigils)]
            phase = rng.uniform(0.0, TAU)
            meta = LanternMeta(
                i,
                i * spacing + rng.uniform(-0.025, 0.025) * spacing,
                sigil,
                phase,
                rng.uniform(-0.32, 0.32),
                rng.uniform(0.94, 1.07),
                1.30 + 0.11 * math.sin(i * 2.1 + 0.6),
                rng.uniform(0.0, TAU),
            )
            self._lantern_meta.append(meta)

    def _build_fireflies(self):
        layout = self._layout
        rng = random.Random(self.seed ^ 0xF17E)
        width, height, wl = layout["width"], layout["height"], layout["waterline"]
        count = max(36, int(PRESETS[layout["preset"]]["fireflies"] * 1.3))
        self._fireflies = []
        for _ in range(count):
            layer = rng.choices((0, 1, 2), weights=(0.30, 0.45, 0.25))[0]
            if layer == 0:
                x = rng.uniform(0, width)
                y = rng.uniform(height * 0.26, wl - 120)
                brightness = rng.uniform(0.35, 0.75)
                radius = rng.uniform(2.5, 5.5)
            elif layer == 1:
                x = rng.uniform(0, width)
                y = rng.uniform(height * 0.32, wl - 18)
                brightness = rng.uniform(0.55, 1.0)
                radius = rng.uniform(4.0, 9.0)
            else:
                x = rng.uniform(20, width - 20)
                y = rng.uniform(wl + 8, min(height - 8, wl + height * 0.10))
                brightness = rng.uniform(0.4, 0.85)
                radius = rng.uniform(3.5, 7.5)
            self._fireflies.append({
                "x": x, "y": y, "radius": radius,
                "brightness": brightness * rng.uniform(0.6, 1.0),
                "warm": rng.random() < 0.25,
                "layer": layer,
                "period": rng.uniform(4.0, 9.0),
                "phase": rng.uniform(0.0, TAU),
                "drift": rng.uniform(0.5, 2.2),
            })

    def _build_mist(self):
        layout = self._layout
        if not self._mist:
            self._mist_layers = []
            return
        rng = random.Random(self.seed ^ 0xA157)
        width, height, wl = layout["width"], layout["height"], layout["waterline"]
        bands = (
            (wl - 44 * layout["sy"], width * 1.12, 62 * layout["sy"], 0.19, 0.5),
            (wl + 34 * layout["sy"], width * 1.04, 44 * layout["sy"], 0.20, 1.7),
            (height - 20 * layout["sy"], width * 1.10, 76 * layout["sy"], 0.09, 3.1),
        )
        self._mist_layers = []
        for y, w, h, alpha, drift in bands:
            sprite = make_mist_sprite(w, h, self._palette["mist"], rng)
            sprite = alpha_mul(sprite, alpha)
            self._mist_layers.append({
                "sprite": sprite,
                "y": y,
                "x": rng.uniform(-width * 0.12, -20),
                "drift": drift,
                "wrap": width * 1.3,
            })

    def _build_ripples(self):
        layout = self._layout
        rng = random.Random(self.seed ^ 0x21FF)
        width = layout["width"]
        water_h = layout["height"] - layout["waterline"]
        self._ripples = []
        for _ in range(34):
            t = rng.random() ** 1.55
            self._ripples.append({
                "x": rng.uniform(-30, width),
                "y": layout["waterline"] + 2 + t * max(2.0, water_h - 4),
                "length": rng.uniform(8, 120) * (0.45 + t * 1.7),
                "phase": rng.uniform(0.0, TAU),
                "speed": rng.uniform(0.05, 0.22),
                "alpha": int(rng.uniform(8, 38) * (0.5 + 0.5 * (1.0 - t))),
                "tint": rng.uniform(0.0, 0.65),
                "width": rng.choice((1, 1, 2)),
            })

    # ---------------------------------------------------------------- static art

    def _build_background(self):
        layout = self._layout
        palette = self._palette
        scene = BuildScene(layout, palette, self.seed)
        width, height = layout["width"], layout["height"]
        back = pygame.Surface((width, height))
        back.fill(palette["bg_top"])

        sky = vertical_gradient(
            (width, height),
            [(0.0, palette["bg_top"]), (0.42, palette["bg_mid"]),
             (0.74, palette["sky_low"]),
             (1.0, shade(palette["sky_low"], 1.1))])
        back.blit(sky, (0, 0))

        fog_x = width * (0.64 if layout["key"] == "strip" else 0.60)
        fog_y = height * (0.30 if layout["key"] == "strip" else 0.26)
        blit_glow(back, (fog_x, fog_y), width * (0.22 if layout["key"] == "strip"
                                                 else 0.34),
                  palette["moon"], power=2.6, strength=0.045)

        star_rng = random.Random(self.seed + 3)
        for _ in range(18):
            sx = star_rng.uniform(0.12, 0.88) * width
            sy = star_rng.uniform(0.02, 0.12) * height
            a = star_rng.uniform(0.10, 0.35)
            pygame.draw.circle(back, mix(palette["bg_top"], palette["ink"], a),
                               (int(sx), int(sy)),
                               max(1, int(star_rng.uniform(0.6, 1.3))))

        if self._mist:
            draw_horizon_mist(back, scene, 1)

        far = pygame.Surface((width, height), pygame.SRCALPHA)
        rng = random.Random(self.seed + 5)
        draw_canopy_roof(far, rng, palette, width, height, 0, 1)
        draw_far_treeline(far, rng, palette, scene, 1)
        for u in ((0.18, 0.70) if layout["key"] == "strip"
                  else (0.18, 0.52, 0.86)):
            x = u * width + rng.uniform(-24, 24)
            base = layout["waterline"] + rng.uniform(-10, 2)
            top = rng.uniform(height * 0.11, height * 0.20)
            crown_cy = (rng.uniform(height * 0.38, height * 0.47)
                        if layout["key"] == "strip"
                        else rng.uniform(height * 0.13, height * 0.18))
            draw_tree(far, rng, palette, x, base, top,
                      rng.uniform(4, 7) * layout["sx"], 0, 1,
                      crown_cy=crown_cy,
                      crown_rx=rng.uniform(38, 60) * layout["sx"],
                      crown_ry=rng.uniform(20, 30) * layout["sy"],
                      lobe_count=5)
        far = blur_surface(far, 3)
        back.blit(far, (0, 0))

        mid = pygame.Surface((width, height), pygame.SRCALPHA)
        rng = random.Random(self.seed + 11)
        draw_canopy_roof(mid, rng, palette, width, height, 1, 1)
        mid_x = ((0.135, 0.345, 0.565, 0.760, 0.905)
                 if layout["key"] == "strip"
                 else (0.12, 0.62, 0.88))
        for u in mid_x:
            x = u * width + rng.uniform(-24, 24)
            for _ in range(2 if layout["key"] == "strip" else 1):
                cx = x + rng.choice((-1, 1)) * rng.uniform(24, 70) * layout["sx"]
                draw_trunk(mid, rng, cx,
                           (layout["waterline"] + rng.uniform(-4, 12)) * 1.0,
                           -30 * layout["sy"], rng.uniform(5, 12) * layout["sx"],
                           shade(palette["mid_tree"], rng.uniform(0.7, 1.1)),
                           rng.uniform(-0.6, 0.6), 1, palette)
            base = layout["waterline"] + rng.uniform(-6, 10)
            top = -30 * layout["sy"]
            trunk_w = (rng.uniform(12, 24) if layout["key"] == "strip"
                       else rng.uniform(24, 40)) * layout["sx"]
            crown_cy = (rng.uniform(height * 0.10, height * 0.27)
                        if layout["key"] == "strip"
                        else rng.uniform(height * 0.05, height * 0.12))
            crown_rx = (rng.uniform(60, 110) if layout["key"] == "strip"
                        else rng.uniform(90, 160)) * layout["sx"]
            draw_tree(mid, rng, palette, x, base, top, trunk_w, 1, 1,
                      crown_cy=crown_cy, crown_rx=crown_rx,
                      crown_ry=crown_rx * rng.uniform(0.42, 0.60),
                      lobe_count=7)
        for _ in range(46):
            x = rng.uniform(-20, width + 20)
            y = layout["waterline"] - rng.uniform(-2, 46) * layout["sy"]
            rx = rng.uniform(10, 40) * layout["sx"]
            ry = rx * rng.uniform(0.35, 0.65)
            pygame.draw.ellipse(
                mid, shade(palette["mid_lean"], rng.uniform(0.5, 0.95)),
                (int(x - rx), int(y - ry), int(rx * 2), int(ry * 2)))
        back.blit(mid, (0, 0))

        draw_path(back, scene, 1)
        draw_bank(back, scene, 1)
        draw_water(back, scene, 1)
        self._back = back

        if self._scrim is not None:
            back.blit(self._scrim, (0, 0))
        front = pygame.Surface((width, height), pygame.SRCALPHA)
        draw_near_forest(front, scene, 1)
        self._front = front

    def _build_finish(self):
        layout = self._layout
        width, height = layout["width"], layout["height"]
        qw, qh = max(2, width // 4), max(2, height // 4)
        small = pygame.Surface((qw, qh))
        cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
        maxd = math.hypot(cx, cy)
        corner_x = 46.0 * layout["pscale"]
        corner_y = height - 18.0 * layout["pscale"]
        corner_rx = max(40.0, 90.0 * layout["pscale"])
        corner_ry = max(20.0, 44.0 * layout["pscale"])
        for y in range(qh):
            ny = y * height / qh
            for x in range(qw):
                nx = x * width / qw
                r = math.hypot(x - cx, y - cy) / maxd
                dark = self._vignette * (max(0.0, r - 0.24) / 0.76) ** 1.6
                cd = (((nx - corner_x) / corner_rx) ** 2
                      + ((ny - corner_y) / corner_ry) ** 2)
                if cd < 1.0:
                    dark += 0.46 * (1.0 - cd) ** 1.5
                k = int(255 * max(0.05, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (width, height))
        if self._scanlines > 0:
            # Multiply the scanlines in instead of drawing them over the map:
            # drawing would erase the vignette (and the watermark corner) on
            # every line.
            line_hex = 255 - self._scanlines
            lines = pygame.Surface((1, height))
            lines.fill((255, 255, 255))
            for y in range(0, height, 3):
                lines.set_at((0, y), (line_hex, line_hex, line_hex))
            lines = pygame.transform.scale(lines, (width, height))
            finish.blit(lines, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self._finish = finish

        if width * height <= 1_000_000:
            self._bloom_small = pygame.Surface((max(2, width // 6),
                                                max(2, height // 6)))
            self._bloom_up = pygame.Surface((width, height))
        else:
            # The large portrait/16:9 frames already get their glow from the
            # cached additive halos; a full-screen bloom costs ~15 ms there.
            self._bloom_small = None
            self._bloom_up = None

        if width * height <= 1_100_000:
            nw, nh = max(2, width // 3), max(2, height // 3)
            noise = pygame.Surface((nw, nh))
            nrng = random.Random(self.seed ^ 0x6A17)
            for y in range(nh):
                for x in range(nw):
                    v = nrng.randint(236, 255)
                    noise.set_at((x, y), (v, v, v))
            self._grain = pygame.transform.smoothscale(noise, (width, height))

    def _build_scrim(self):
        layout = self._layout
        if self._hud_mode == "none":
            self._scrim = None
            return
        width, height = layout["width"], layout["height"]
        scrim_h = max(2, int(height * (0.20 if layout["key"] == "portrait"
                                       else 0.24)))
        ramp = pygame.Surface((1, scrim_h), pygame.SRCALPHA)
        for y in range(scrim_h):
            a = int(112 * (1.0 - y / max(1, scrim_h - 1)) ** 1.7)
            ramp.set_at((0, y), (2, 4, 3, a))
        self._scrim = pygame.transform.scale(ramp, (width, scrim_h))

    # ---------------------------------------------------------------- HUD

    def _title_lines(self):
        if "\n" in self._title:
            return [line for line in self._title.split("\n") if line.strip()]
        if (self._layout["key"] == "portrait"
                and self._title == DEFAULT_TITLE):
            return ["LANTERN", "PROCESSION"]
        return [self._title]

    def _build_hud(self):
        if self._hud_mode == "none":
            self._hud = None
            return
        layout = self._layout
        cache = self.manager.cache
        width, height = layout["width"], layout["height"]
        title_px = layout["title_px"]
        lines = self._title_lines()
        title_font = cache.get_font("dejavuserif", title_px, bold=True)
        while title_px > 12:
            widest = max(title_font.size(line)[0] for line in lines) \
                if lines else 0
            if widest <= width * 0.78:
                break
            title_px -= 2
            title_font = cache.get_font("dejavuserif", title_px, bold=True)
        sub_font = cache.get_font("dejavusansmono", layout["sub_px"])
        tele_font = cache.get_font("dejavusansmono", layout["tele_px"])
        eyebrow_font = cache.get_font("dejavusansmono", layout["eyebrow_px"])

        margin = layout["margin"]
        x = margin
        y = margin
        eyebrow = None
        if self._hud_mode == "full":
            eyebrow = tracked("SLOW WORLDS   ·   FANTASY", eyebrow_font,
                              shade(self._palette["structure"], 0.9),
                              layout["aux_track"] + 1, 190)
            y += eyebrow.get_height() + (16 if layout["key"] == "portrait" else 8)
        title_surfaces = [tracked(line, title_font, self._palette["ink"],
                                  layout["title_track"]) for line in lines]
        title_ys = []
        line_gap = 6 if layout["key"] == "strip" else 8
        for surface in title_surfaces:
            title_ys.append(y)
            y += surface.get_height() - 2 + line_gap
        y += 2
        rule_y = y
        rule_w = min(title_surfaces[0].get_width() if title_surfaces else 0,
                     int(width * 0.34))
        y += 9
        subtitle = tracked(self._subtitle, sub_font,
                           mix(self._palette["ink_dim"],
                               self._palette["ink"], 0.25),
                           layout["aux_track"], 235)
        subtitle_y = y

        tele_x = width - margin
        self._hud = {
            "margin": margin,
            "eyebrow": eyebrow,
            "eyebrow_y": margin,
            "title": title_surfaces,
            "title_y": title_ys,
            "rule_y": rule_y,
            "rule_w": rule_w,
            "subtitle": subtitle,
            "subtitle_y": subtitle_y,
            "tele_font": tele_font,
            "tele_x": tele_x,
            "tele_y": margin,
            "aux_track": layout["aux_track"],
            "seal": True,
        }

    def _hud_steps(self):
        hud = self._hud
        if hud is None:
            return None
        elapsed = max(0, int(self._time - self._start_time))
        key = elapsed
        if key != self._hud_steps_key:
            steps = (412 + int(elapsed * 1.4)) % 10000
            text = f"NIGHT  //  {steps:04d} STEPS"
            self._hud_steps_surface = tracked(
                text, hud["tele_font"], self._palette["ink_dim"],
                hud["aux_track"], 225)
            self._hud_steps_key = key
        return self._hud_steps_surface

    def _hud_lanterns(self):
        hud = self._hud
        if hud is None:
            return None
        lit = self._lit_count()
        key = (lit, self._lantern_count)
        if key != self._hud_count_key:
            text = f"LANTERNS  {lit:02d} / {self._lantern_count:02d}"
            self._hud_count_surface = tracked(
                text, hud["tele_font"], shade(self._palette["structure"], 0.95),
                hud["aux_track"], 205)
            self._hud_count_key = key
        return self._hud_count_surface

    def _draw_hud(self, screen):
        hud = self._hud
        if hud is None:
            return
        palette = self._palette
        if hud["eyebrow"] is not None:
            screen.blit(hud["eyebrow"], (hud["margin"], hud["eyebrow_y"]))
        for surface, y in zip(hud["title"], hud["title_y"]):
            screen.blit(surface, (hud["margin"], y))
        pygame.draw.line(screen, shade(palette["structure"], 0.62),
                         (hud["margin"], hud["rule_y"]),
                         (hud["margin"] + hud["rule_w"], hud["rule_y"]), 1)
        screen.blit(hud["subtitle"], (hud["margin"], hud["subtitle_y"]))

        one = self._hud_steps()
        two = self._hud_lanterns()
        tx = hud["tele_x"]
        ty = hud["tele_y"]
        if one is not None:
            screen.blit(one, (tx - one.get_width(), ty))
            ty += one.get_height() + 7
        if two is not None:
            screen.blit(two, (tx - two.get_width(), ty))
        if one is not None:
            seal_x = tx - one.get_width() - 14
            seal_y = hud["tele_y"] + one.get_height() // 2
            pygame.draw.circle(screen, shade(palette["structure"], 1.1),
                               (seal_x, seal_y), 2 if self._layout["key"] == "strip" else 3, 1)
            pygame.draw.circle(screen, shade(palette["accent"], 0.9),
                               (seal_x, seal_y), 1)

    # ---------------------------------------------------------------- per-frame lanterns

    def _compute_states(self, now: float, with_event: bool = True):
        layout = self._layout
        states = []
        event = self._event if with_event else None
        event_index = event["index"] if event else -1
        for meta in self._lantern_meta:
            u = ((meta.offset + self._speed * now) % self._path_len) \
                / self._path_len if self._path_len > 0 else 0.0
            (px, py), (tx, ty) = sample_path(self._path, self._lengths,
                                             meta.offset + self._speed * now)
            norm = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / norm, tx / norm
            scale = self._scale_for(u)
            half_w = layout["lantern_w"] * scale * meta.size_jitter
            bucket = max(4.0, round(half_w / 2.0) * 2.0)
            hover = (layout["hover"] if layout["hover_fixed"]
                     else layout["hover"] * scale)
            lane = meta.lane * layout["lane"] * scale
            bob = math.sin(TAU * now / 3.0 + meta.phase) * min(5.0, 1.5 + scale * 1.5)
            x = px + nx * lane
            y = py + ny * abs(lane) * 0.10 - hover + bob
            tilt = math.sin(TAU * now / 7.0 + meta.tilt_phase) * 3.2
            edge = min(u, 1.0 - u)
            fade = smoothstep(edge / 0.04) if edge < 0.04 else 1.0
            # Fade a lantern as its paper reaches any frame edge, so a larger
            # body is not sliced by the screen.
            half_extent_x = half_w * 1.30
            half_extent_y = half_w * 1.60
            margin = min(x - half_extent_x,
                         layout["width"] - x - half_extent_x,
                         y - half_extent_y,
                         layout["height"] - y - half_extent_y)
            screen_fade = smoothstep(margin / max(6.0, 34.0 * layout["pscale"]))
            fade = min(fade, screen_fade)
            dim = fade
            refl = fade
            path_y = py
            is_event = False

            if event is not None and meta.index == event_index:
                elapsed = now - event["start"]
                e = elapsed / event["duration"]
                if e <= 1.0:
                    p = smoothstep(e)
                    x = lerp(event["start_x"], event["target_x"], p)
                    y = (lerp(event["start_y"], event["target_y"], p)
                         - 10.0 * math.sin(math.pi * p))
                    scale = event["start_scale"]
                    half_w = event["start_half_w"]
                    bucket = max(4.0, round(half_w / 2.0) * 2.0)
                    u = event["start_u"]
                    dim = (1.0 if e < 0.62
                           else 1.0 - smoothstep((e - 0.62) / 0.38))
                    refl = 0.86
                    path_y = event["target_y"]
                    is_event = True
                elif e <= 1.0 + event["afterglow"] / event["duration"]:
                    x = event["target_x"]
                    y = event["target_y"]
                    scale = event["start_scale"]
                    half_w = event["start_half_w"]
                    bucket = max(4.0, round(half_w / 2.0) * 2.0)
                    u = event["start_u"]
                    dim = 0.0
                    refl = 0.55 * max(0.0, 1.0 - (e - 1.0)
                                      / (event["afterglow"] / event["duration"]))
                    path_y = event["target_y"]
                    is_event = True

            states.append(LanternState(
                meta.index, meta.sigil, x, y, scale, half_w, bucket,
                meta.phase, tilt, dim, path_y, u, refl, is_event,
                meta.height_ratio))
        return states

    # ---------------------------------------------------------------- sprites

    def _lantern_sprite(self, state):
        key = (state.sigil if isinstance(state.sigil, str)
               else int(state.sigil), int(state.bucket),
               int(round(state.height_ratio * 100)))
        entry = self._sprite_cache.get(key)
        if entry is not None:
            return entry
        half = state.bucket
        ss = 3 if half <= 18.0 else 2
        surface = make_lantern(half * ss, self._palette, state.sigil,
                               detail=2, height_ratio=state.height_ratio)
        if isinstance(surface, tuple):
            surface, cx, cy = surface
        else:
            cx, cy = surface.get_width() * 0.5, surface.get_height() * 0.5
        surface = pygame.transform.smoothscale(
            surface, (max(1, surface.get_width() // ss),
                      max(1, surface.get_height() // ss)))
        entry = (surface, cx / ss, cy / ss)
        if len(self._sprite_cache) >= 360:
            for old_key in list(self._sprite_cache)[:110]:
                self._sprite_cache.pop(old_key, None)
        self._sprite_cache[key] = entry
        return entry

    def _reflection_sprite(self, state):
        key = (state.sigil if isinstance(state.sigil, str)
               else int(state.sigil), int(state.bucket),
               int(round(state.height_ratio * 100)))
        entry = self._reflection_cache.get(key)
        if entry is not None:
            return entry
        sprite, _cx, _cy = self._lantern_sprite(state)
        w, h = sprite.get_size()
        refl = pygame.transform.flip(sprite, False, True)
        refl = blur_surface(refl, 2)
        refl = pygame.transform.smoothscale(
            refl, (max(2, int(w * 1.0)), max(2, int(h * 0.88))))
        refl = alpha_mul(refl, self._layout["reflection_alpha"])
        rw, rh = refl.get_size()
        fade = pygame.Surface((rw, rh), pygame.SRCALPHA)
        ramp = pygame.Surface((1, rh), pygame.SRCALPHA)
        for y in range(rh):
            t = y / max(1, rh - 1)
            a = int(255 * (1.0 - t) ** (1.1 if self._layout["key"] == "strip" else 0.75))
            ramp.set_at((0, y), (255, 255, 255, a))
        fade = pygame.transform.scale(ramp, (rw, rh))
        refl.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        entry = refl
        if len(self._reflection_cache) >= 360:
            for old_key in list(self._reflection_cache)[:110]:
                self._reflection_cache.pop(old_key, None)
        self._reflection_cache[key] = entry
        return entry

    # ---------------------------------------------------------------- drawing

    def _draw_ripples(self, screen):
        layout = self._layout
        palette = self._palette
        screen.set_clip(layout["water_rect"])
        water_h = max(1, layout["height"] - layout["waterline"])
        for r in self._ripples:
            x = r["x"] + math.sin(self._time * r["speed"] + r["phase"]) * 3.0
            col = mix(palette["water_top"], palette["water_line"],
                      0.30 + r["tint"] * 0.20)
            pygame.draw.line(screen, col,
                             (int(x), int(r["y"])),
                             (int(x + r["length"]), int(r["y"])),
                             r["width"])
        # a few warm glints in the near water
        for i in range(6):
            phase = i * 2.17
            y = layout["waterline"] + water_h * (0.30 + 0.09 * (i % 4))
            x = (layout["width"] * (0.58 + 0.05 * math.sin(phase + self._time * 0.1))
                 - 30)
            length = 10 + 8 * (i % 3)
            pygame.draw.line(screen, mix(palette["water_top"],
                                         palette["accent"], 0.16),
                             (int(x), int(y)), (int(x + length), int(y)), 1)
        screen.set_clip(None)

    def _draw_reflections(self, screen, states):
        if not self._reflection:
            return
        layout = self._layout
        palette = self._palette
        screen.set_clip(layout["water_rect"])
        water_h = layout["height"] - layout["waterline"]
        bands = QUALITY[self._quality]["reflection_bands"]
        for state in sorted(states, key=lambda s: s.scale):
            if state.reflection_alpha <= 0.02:
                continue
            if layout["key"] == "portrait" and not state.event \
                    and state.path_y < layout["waterline"] - 260 * layout["sy"]:
                continue
            refl = self._reflection_sprite(state)
            if state.reflection_alpha < 0.98:
                refl = alpha_mul(refl, state.reflection_alpha)
            rw, rh = refl.get_size()
            if state.event:
                center_y = max(layout["waterline"] + rh * 0.5 + 5.0,
                               state.y + 58.0)
            elif layout["refl_anchor"] == "nearbank":
                center_y = max(layout["waterline"] + rh * 0.5 + 5.0,
                               state.path_y + 72.0)
            else:
                center_y = 2.0 * layout["waterline"] - state.y
            top = center_y - rh * 0.5
            left = state.x - rw * 0.5
            strength = (0.20 if layout["key"] == "strip" else 0.38) \
                * state.reflection_alpha
            blit_glow(screen, (state.x, center_y + rh * 0.10),
                      max(8, int(state.half_w * 4.6)),
                      palette["reflect"], power=1.6,
                      strength=strength * self._glow_strength, squash=2.1)
            amp = 1.4 * state.scale * (0.55 if state.dim < 0.5 else 1.0)
            if layout["key"] != "strip":
                amp = 2.1 * state.scale * (0.55 if state.dim < 0.5 else 1.0)
            band = max(2, int(round(rh / max(1, bands))))
            wl = layout["waterline"]
            for by in range(0, rh, band):
                dy = top + by
                if dy + band < wl:
                    continue
                depth = max(0.0, (dy - wl) / max(1.0, water_h))
                dx = math.sin((dy - wl) * 0.055 + state.phase) \
                    * amp * (0.35 + depth * 1.3)
                screen.blit(refl, (int(left + dx), int(dy)),
                            area=(0, by, rw, min(band, rh - by)))
        screen.set_clip(None)

    def _draw_mist(self, screen):
        if not self._mist:
            return
        count = QUALITY[self._quality]["mist"]
        width = self._layout["width"]
        for layer in self._mist_layers[:count]:
            span = layer["wrap"] + layer["sprite"].get_width()
            x = (layer["x"] + layer["drift"] * self._time) % span
            screen.blit(layer["sprite"], (int(x - layer["wrap"] * 0.5),
                                          int(layer["y"]
                                              - layer["sprite"].get_height() * 0.5)))

    def _draw_pools(self, screen):
        layout = self._layout
        for state in self._states:
            if state.dim < 0.3:
                continue
            y = state.path_y + 4.0
            wide = min(state.half_w * 11.0, 150.0 if layout["key"] == "strip" else 190.0)
            tight = min(state.half_w * 4.2, 62.0 if layout["key"] == "strip" else 74.0)
            blit_glow(screen, (state.x, y), wide,
                      self._palette["accent"], power=1.8,
                      strength=0.040 * state.dim * self._glow_strength,
                      squash=0.18)
            blit_glow(screen, (state.x, y), tight,
                      self._palette["glow"], power=2.0,
                      strength=0.105 * state.dim * self._glow_strength,
                      squash=0.22)

    def _draw_lanterns(self, screen):
        flicker_phase = self._time
        for state in sorted(self._states, key=lambda s: s.scale):
            if state.dim <= 0.01:
                continue
            strength = state.dim * self._glow_strength
            flick = 1.0
            if self._flicker:
                flick = 1.0 + 0.07 * math.sin(TAU * flicker_phase * 1.6
                                             + state.phase * 3.0)
            blit_glow(screen, (state.x, state.y),
                      state.half_w * (7.0 if state.scale > 1.0 else 5.8),
                      self._palette["accent"], power=2.1,
                      strength=0.20 * strength)
            blit_glow(screen, (state.x, state.y),
                      state.half_w * 4.8, self._palette["glow"], power=2.2,
                      strength=0.30 * strength * flick)
            blit_glow(screen, (state.x, state.y),
                      state.half_w * 2.7, self._palette["core"], power=2.4,
                      strength=0.48 * strength * flick)
            sprite, cx, cy = self._lantern_sprite(state)
            rot = pygame.transform.rotozoom(sprite, state.tilt, 1.0)
            if state.dim < 1.0:
                rot = alpha_mul(rot, state.dim)
            screen.blit(rot, (int(state.x - cx), int(state.y - cy)))

    def _draw_fireflies(self, screen):
        layout = self._layout
        palette = self._palette
        count = QUALITY[self._quality]["fireflies"]
        for fly in self._fireflies[:count]:
            blink = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(
                TAU * self._time / fly["period"] + fly["phase"]))
            b = fly["brightness"] * blink
            if b < 0.05:
                continue
            x = fly["x"] + math.sin(self._time * 0.4 + fly["phase"]) * fly["drift"]
            y = fly["y"] + math.cos(self._time * 0.31 + fly["phase"] * 1.3) * 1.2
            if not (-10 <= x <= layout["width"] + 10 and -10 <= y <= layout["height"] + 10):
                continue
            color = palette["firefly_warm"] if fly["warm"] else palette["firefly"]
            blit_glow(screen, (x, y), fly["radius"] * 3.1, color,
                      power=2.0, strength=0.38 * b)
            blit_glow(screen, (x, y), fly["radius"] * 0.95, color,
                      power=2.4, strength=1.0 * b)
            pygame.draw.circle(screen, mix(color, (255, 255, 255), 0.55),
                               (int(x), int(y)),
                               max(1, int(1.1 * b)))

    # ---------------------------------------------------------------- finish

    def _composite_bloom(self, screen):
        if (self._bloom_small is None or self._bloom_up is None
                or not QUALITY[self._quality]["bloom"]):
            return
        small = self._bloom_small
        pygame.transform.smoothscale(screen, small.get_size(), small)
        small.fill((82, 82, 82), special_flags=pygame.BLEND_RGB_SUB)
        small.fill((220, 220, 220), special_flags=pygame.BLEND_RGB_MULT)
        up = self._bloom_up
        pygame.transform.scale(small, up.get_size(), up)
        screen.blit(up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_finish(self, screen):
        screen.blit(self._finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        if self._grain is not None and QUALITY[self._quality]["grain"]:
            screen.blit(self._grain, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    # ---------------------------------------------------------------- render

    def render(self, screen):
        if self.manager is None:
            screen.fill(self._palette["bg_top"])
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            self._render_scene(screen)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Lantern] render error: {exc}")
            self._draw_error(screen)

    def _resize(self, size):
        if self._built_size != (int(size[0]), int(size[1])):
            self._build(size)

    def _render_scene(self, screen):
        if self._back is None:
            screen.fill(self._palette["bg_top"])
            return
        screen.blit(self._back, (0, 0))
        self._states = self._compute_states(self._time)
        self._last_states = self._states
        self._draw_ripples(screen)
        self._draw_reflections(screen, self._states)
        self._draw_mist(screen)
        self._draw_pools(screen)
        self._draw_lanterns(screen)
        self._draw_fireflies(screen)
        if self._front is not None:
            screen.blit(self._front, (0, 0))
        self._composite_bloom(screen)
        self._draw_finish(screen)
        self._draw_hud(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["structure"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("LANTERN PROCESSION // CONFIGURATION REFUSED",
                                True, self._palette["ink"])
            body = font.render((self.error or "unknown error")[:90], True,
                               self._palette["glow"])
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- stats

    def stats(self):
        if self._layout is None or self.error:
            return {}
        return {
            "preset": self._layout["preset"],
            "size": self._screen_size,
            "palette": self._palette_name,
            "seed": self.seed,
            "time": self._time,
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "lanterns": self._lantern_count,
            "lit": self._lit_count(),
            "event": self._event is not None,
            "event_count": self._event_count,
            "reflection": self._reflection,
            "mist": self._mist,
            "sprite_cache": len(self._sprite_cache),
            "reflection_cache": len(self._reflection_cache),
            "positions": [(round(s.x, 1), round(s.y, 1)) for s in self._last_states],
        }


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
