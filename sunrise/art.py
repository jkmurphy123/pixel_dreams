#!/usr/bin/env python3
"""Four Seasons forest-line art, extracted from the sunrise prototype.

Draws one 1280x400 cartoon forest panorama per season. The same tree/ground
layout is reused for all four so a later season cross-fade will not jump, and
the scene is built as separate depth layers (sky / far / mid / ground / near)
so each layer can be multiplied down to a silhouette for dawn and dusk.

No numpy, no PIL: everything is pygame, supersampled 3x and smoothscaled.

    python designs/sunrise_proto/gen_forest.py
    python designs/sunrise_proto/gen_forest.py --layers   # also dump layers
"""

from __future__ import annotations

import argparse
import math
import os
import random

import pygame

W, H = 1280, 400
SS = 2
SW, SH = W * SS, H * SS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "seasons")

HORIZON = 288.0
SUN_X = 930.0

# --------------------------------------------------------------------------
# palettes
# --------------------------------------------------------------------------

_PALETTES = {
    "winter": dict(
        label="WINTER",
        sky=[(0.00, (40, 78, 124)), (0.50, (104, 150, 186)),
             (0.78, (238, 214, 208)), (1.00, (255, 242, 232))],
        horizon_mist=(255, 236, 224),
        sun=(SUN_X, 238.0, 27.0),
        sun_color=(255, 250, 236),
        glow_color=(255, 212, 184), glow_strength=0.95,
        cloud=(250, 252, 255), cloud_shade=(198, 194, 202), cloud_tint=(255, 226, 206),
        ridge_far=(176, 198, 212), ridge_near=(150, 176, 194),
        far_tree=(124, 154, 176),
        mid_hill=(212, 224, 230), mid_tree=(92, 116, 126), near_tree=(30, 40, 48),
        ground_top=(228, 238, 246), ground_bottom=(150, 174, 198),
        ground_rim=(252, 254, 255),
        grass=(196, 210, 220), grass_light=(240, 246, 250),
        bark=(66, 58, 54), bark_light=(112, 98, 86),
        canopy=None, canopy_hi=None, canopy_shadow=None, accent_canopy=None,
        accent_hi=None, accent_shadow=None, style="bare",
    ),
    "spring": dict(
        label="SPRING",
        sky=[(0.00, (68, 138, 198)), (0.48, (150, 200, 230)),
             (0.78, (255, 224, 196)), (1.00, (255, 238, 216))],
        horizon_mist=(255, 238, 218),
        sun=(SUN_X, 214.0, 28.0),
        sun_color=(255, 246, 218),
        glow_color=(255, 212, 164), glow_strength=1.05,
        cloud=(255, 250, 246), cloud_shade=(220, 202, 202), cloud_tint=(255, 226, 200),
        ridge_far=(176, 202, 196), ridge_near=(148, 180, 164),
        far_tree=(124, 164, 132),
        mid_hill=(122, 172, 104), mid_tree=(78, 126, 76), near_tree=(30, 64, 40),
        ground_top=(112, 170, 88), ground_bottom=(38, 82, 44),
        ground_rim=(186, 226, 128),
        grass=(76, 132, 64), grass_light=(170, 214, 112),
        bark=(88, 68, 54), bark_light=(128, 102, 78),
        canopy=(96, 164, 76), canopy_hi=(178, 224, 112), canopy_shadow=(46, 100, 46),
        accent_canopy=(250, 222, 234), accent_hi=(255, 248, 252),
        accent_shadow=(216, 176, 196), accent_style="blossom", style="leaf",
    ),
    "summer": dict(
        label="SUMMER",
        sky=[(0.00, (28, 100, 180)), (0.46, (96, 170, 224)),
             (0.78, (204, 232, 238)), (1.00, (238, 246, 238))],
        horizon_mist=(232, 246, 242),
        sun=(SUN_X, 160.0, 29.0),
        sun_color=(255, 252, 230),
        glow_color=(255, 240, 184), glow_strength=1.10,
        cloud=(255, 255, 252), cloud_shade=(202, 224, 234), cloud_tint=(255, 248, 222),
        ridge_far=(158, 190, 172), ridge_near=(122, 164, 132),
        far_tree=(94, 150, 100),
        mid_hill=(82, 146, 82), mid_tree=(46, 102, 56), near_tree=(18, 50, 32),
        ground_top=(72, 142, 64), ground_bottom=(24, 62, 36),
        ground_rim=(160, 208, 106),
        grass=(44, 104, 52), grass_light=(126, 184, 82),
        bark=(70, 56, 42), bark_light=(110, 90, 66),
        canopy=(42, 112, 54), canopy_hi=(126, 186, 88), canopy_shadow=(20, 70, 38),
        accent_canopy=(78, 150, 64), accent_hi=(150, 200, 110),
        accent_shadow=(28, 80, 42), accent_style="foliage", style="leaf",
    ),
    "autumn": dict(
        label="AUTUMN",
        sky=[(0.00, (58, 100, 150)), (0.46, (146, 166, 186)),
             (0.78, (248, 190, 138)), (1.00, (255, 216, 162))],
        horizon_mist=(255, 222, 178),
        sun=(SUN_X, 228.0, 28.0),
        sun_color=(255, 224, 162),
        glow_color=(255, 176, 96), glow_strength=1.20,
        cloud=(252, 238, 220), cloud_shade=(208, 172, 154), cloud_tint=(255, 206, 160),
        ridge_far=(182, 170, 154), ridge_near=(158, 142, 120),
        far_tree=(152, 128, 100),
        mid_hill=(152, 128, 80), mid_tree=(110, 74, 46), near_tree=(46, 28, 20),
        ground_top=(138, 112, 62), ground_bottom=(56, 42, 28),
        ground_rim=(208, 178, 102),
        grass=(108, 84, 48), grass_light=(196, 162, 84),
        bark=(76, 52, 38), bark_light=(118, 86, 58),
        canopy=(206, 110, 44), canopy_hi=(250, 190, 90), canopy_shadow=(92, 44, 24),
        accent_canopy=(184, 54, 40), accent_hi=(238, 136, 74),
        accent_shadow=(86, 30, 24), accent_style="foliage",
        canopy_list=[(208, 100, 38), (182, 66, 34), (228, 142, 50), (156, 84, 40)],
        style="leaf",
    ),
}


_DAWN = {
    "winter": dict(
        stops=[(0.00, (16, 24, 48)), (0.48, (48, 62, 98)),
               (0.70, (148, 112, 130)), (0.86, (255, 190, 168))],
        glow=(255, 176, 136), mist=(255, 210, 186)),
    "spring": dict(
        stops=[(0.00, (18, 28, 54)), (0.48, (58, 66, 102)),
               (0.70, (174, 126, 140)), (0.86, (255, 198, 168))],
        glow=(255, 178, 132), mist=(255, 216, 190)),
    "summer": dict(
        stops=[(0.00, (16, 30, 60)), (0.46, (52, 84, 120)),
               (0.70, (186, 138, 136)), (0.86, (255, 210, 166))],
        glow=(255, 188, 128), mist=(255, 224, 184)),
    "autumn": dict(
        stops=[(0.00, (22, 26, 50)), (0.46, (80, 66, 98)),
               (0.70, (196, 126, 110)), (0.86, (255, 176, 126))],
        glow=(255, 156, 92), mist=(255, 196, 150)),
}

_DAWN_LIGHTS = {
    "far": (0.20, 0.21, 0.27),
    "mid": (0.13, 0.14, 0.19),
    "ground": (0.075, 0.085, 0.115),
    "near": (0.042, 0.048, 0.070),
}


# --------------------------------------------------------------------------
# drawing kit (layout coordinates are final 1280x400 pixels)
# --------------------------------------------------------------------------

def _i(v):
    return int(round(v * SS))


def _c(col, a=255):
    return (int(col[0]), int(col[1]), int(col[2]), a)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(col, f):
    return tuple(max(0, min(255, int(c * f))) for c in col)


def circle(dst, x, y, r, col, alpha=255):
    pygame.draw.circle(dst, _c(col, alpha), (_i(x), _i(y)), max(1, _i(r)))


def ellipse(dst, x, y, rx, ry, col, alpha=255):
    rect = pygame.Rect(_i(x - rx), _i(y - ry), max(1, _i(rx * 2)), max(1, _i(ry * 2)))
    pygame.draw.ellipse(dst, _c(col, alpha), rect)


def poly(dst, pts, col, alpha=255):
    pygame.draw.polygon(dst, _c(col, alpha), [(_i(x), _i(y)) for x, y in pts])


def line(dst, a, b, col, width=1.0, alpha=255):
    pygame.draw.line(dst, _c(col, alpha), (_i(a[0]), _i(a[1])),
                     (_i(b[0]), _i(b[1])), max(1, _i(width)))


def vgrad(dst, rect, stops):
    x, y, w, h = rect
    for row in range(h):
        t = row / max(1, h - 1)
        pygame.draw.line(dst, _sample(stops, t), (x, y + row), (x + w - 1, y + row))


def _sample(stops, t):
    if t <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            u = (t - p0) / max(1e-6, p1 - p0)
            return mix(c0, c1, u)
    return stops[-1][1]


def radial_glow(dst, cx, cy, radius, col, strength=1.0, squash=1.0, steps=44):
    """Soft elliptical glow: stepped radial alpha, blitted over the sky."""
    gw = max(2, _i(radius * 2))
    gh = max(2, _i(radius * squash * 2))
    g = pygame.Surface((gw, gh), pygame.SRCALPHA)
    for i in range(steps):
        f = 1.0 - i / steps          # 1 = outer edge, -> 0 = centre
        t = 1.0 - f
        a = int(255 * (t ** 2.3) * min(1.0, strength) * 0.85)
        if a <= 0:
            continue
        rx = radius * f
        ry = radius * squash * f
        rect = pygame.Rect(gw // 2 - _i(rx), gh // 2 - _i(ry),
                           max(2, _i(rx * 2)), max(2, _i(ry * 2)))
        pygame.draw.ellipse(g, _c(col, a), rect)
    dst.blit(g, (_i(cx - radius), _i(cy - radius * squash)))


def clip_to(mask, surface):
    out = surface.copy()
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def tint(surface, mult):
    out = surface.copy()
    out.fill((int(255 * mult[0]), int(255 * mult[1]), int(255 * mult[2])),
             special_flags=pygame.BLEND_RGB_MULT)
    return out


# --------------------------------------------------------------------------
# layout: generated once, reused by every season
# --------------------------------------------------------------------------

def _hill(y0, a1, f1, p1, a2, f2, p2, x):
    return y0 + a1 * math.sin(f1 * x + p1) + a2 * math.sin(f2 * x + p2)


class Layout:
    def __init__(self):
        rng = random.Random(20261031)

        self.clouds = [
            dict(cx=168, base=128, s=1.05),
            dict(cx=470, base=100, s=0.66),
            dict(cx=712, base=146, s=0.46),
            dict(cx=1148, base=118, s=0.80),
        ]

        # distant continuous treeline
        self.far_trees = []
        x = -12.0
        i = 0
        while x < W + 20:
            h = rng.uniform(12, 28)
            self.far_trees.append(dict(
                x=x, base=HORIZON + rng.uniform(0, 4), h=h,
                w=h * rng.uniform(0.50, 0.66),
                kind="pine" if rng.random() < 0.70 else "blob",
                seed=3000 + i))
            x += rng.uniform(11, 22)
            i += 1

        # main forest band on the mid hill
        self.mid_trees = []
        x = -18.0
        i = 0
        while x < W + 30:
            dip = 1.0 - 0.55 * math.exp(-((x - SUN_X) / 260) ** 2)
            h = rng.uniform(44, 96) * dip
            self.mid_trees.append(dict(
                x=x, base=302 + rng.uniform(0, 12), h=h,
                w=h * rng.uniform(0.54, 0.72),
                kind="pine" if rng.random() < 0.52 else "deciduous",
                seed=2000 + i))
            x += rng.uniform(30, 66)
            i += 1

        # nearer row behind the meadow; low under the sun so it stays clear
        self.ridge_trees = []
        x = 300.0
        i = 0
        while x < 1050:
            dip = 1.0 - 0.72 * math.exp(-((x - SUN_X) / 190) ** 2)
            h = rng.uniform(70, 138) * dip
            self.ridge_trees.append(dict(
                x=x, base=350 + rng.uniform(0, 14), h=h,
                w=h * rng.uniform(0.54, 0.72),
                kind="pine" if rng.random() < 0.45 else "deciduous",
                seed=1500 + i, accent=False))
            x += rng.uniform(56, 104)
            i += 1

        # big framing trees, rooted below the screen edge
        near_specs = [
            (-96, 432, 300, "pine", False, 0.66),
            (-6, 420, 250, "deciduous", False, 0.82),
            (88, 412, 210, "pine", False, 0.60),
            (178, 420, 188, "deciduous", True, 0.80),
            (268, 410, 152, "pine", False, 0.58),
            (1010, 414, 126, "deciduous", False, 0.74),
            (1092, 408, 170, "pine", False, 0.62),
            (1176, 420, 208, "deciduous", False, 0.80),
            (1256, 410, 248, "pine", False, 0.68),
            (1340, 424, 296, "deciduous", True, 0.82),
        ]
        self.near_trees = [
            dict(x=x, base=b, h=h, w=h * wf, kind=k, accent=a, seed=1000 + i)
            for i, (x, b, h, k, a, wf) in enumerate(near_specs)
        ]

        self.bushes = [
            dict(x=420, y=390, rx=30, ry=15, seed=77, accent=False),
            dict(x=548, y=399, rx=44, ry=20, seed=78, accent=False),
            dict(x=690, y=392, rx=34, ry=16, seed=79, accent=False),
            dict(x=812, y=402, rx=28, ry=13, seed=80, accent=False),
            dict(x=944, y=396, rx=36, ry=15, seed=81, accent=False),
        ]

        self.birds = [(318, 120), (348, 104), (378, 128), (704, 90)]

        self.scatter = []
        for _ in range(220):
            self.scatter.append((rng.uniform(0, W), rng.uniform(332, 400),
                                 rng.uniform(0.5, 1.5), rng.uniform(0, math.tau)))

        self.ground_top = lambda x: _hill(332, 6.0, 0.0055, 1.1, 2.6, 0.018, 0.3, x)
        self.mid_top = lambda x: _hill(301, 5.0, 0.0050, 2.4, 2.2, 0.016, 1.4, x)
        self.ridge_a = lambda x: _hill(258, 10.0, 0.0038, 0.6, 4.0, 0.011, 2.2, x)
        self.ridge_b = lambda x: _hill(272, 8.0, 0.0052, 2.1, 3.0, 0.013, 0.2, x)


# --------------------------------------------------------------------------
# trees
# --------------------------------------------------------------------------

def _pine_tier(cx, base_y, top_y, half_w, droop=0.16, scallops=3):
    pts = [(cx - half_w, base_y), (cx, top_y), (cx + half_w, base_y)]
    for k in range(scallops):
        t = (k + 1) / (scallops + 1)
        x = cx + half_w - 2 * half_w * t
        y = base_y + half_w * droop * math.sin(math.pi * t)
        pts.append((x, y))
    return pts


def draw_pine(dst, tree, pal, *, far=False):
    h, w, base = tree["h"], tree["w"], tree["base"]
    cx = tree["x"]
    body = tree.get("color")
    if body is None:
        body = pal["far_tree"] if far else pal["mid_tree"]

    dark = shade(body, 0.74)
    light = mix(body, (255, 255, 240), 0.28)

    if not far:
        poly(dst, [(cx - w * 0.05, base + 2), (cx + w * 0.05, base + 2),
                   (cx + w * 0.035, base - h * 0.34), (cx - w * 0.035, base - h * 0.34)],
             mix(pal["bark"], body, 0.25))

    tiers = 5 if not far else 3
    for i in range(tiers):
        frac = i / tiers
        t_base = base - h * (0.12 + 0.74 * frac)
        t_top = base - h * (0.48 + 0.74 * frac)
        half = (w * 0.5) * (1.0 - 0.68 * frac)
        tone = mix(body, light, 0.08 + 0.30 * frac)
        poly(dst, _pine_tier(cx, t_base, t_top, half, droop=0.16 if not far else 0.08), tone)

        # shadow tucked under the branch tier
        shadow = [(cx - half * 0.90, t_base - h * 0.010),
                  (cx + half * 0.90, t_base - h * 0.010),
                  (cx + half * 0.55, t_base + half * 0.12),
                  (cx, t_base + half * 0.17),
                  (cx - half * 0.55, t_base + half * 0.12)]
        poly(dst, shadow, mix(tone, dark, 0.55))

        # sun-side rim
        line(dst, (cx + half * 0.16, t_top + h * 0.10),
             (cx + half * 0.80, t_base - h * 0.02),
             mix(tone, (255, 255, 240), 0.20), 0.5 if far else 0.8)

        if pal["style"] == "bare" and not far and i < 3:
            snow = [(cx, t_top + h * 0.015),
                    (cx - half * 0.70, t_base - (t_base - t_top) * 0.28),
                    (cx - half * 0.36, t_base - (t_base - t_top) * 0.42),
                    (cx, t_base - (t_base - t_top) * 0.52),
                    (cx + half * 0.40, t_base - (t_base - t_top) * 0.40),
                    (cx + half * 0.72, t_base - (t_base - t_top) * 0.26)]
            poly(dst, snow, mix(pal["ground_top"], (255, 255, 255), 0.6), 240)


def _segment(dst, p0, p1, w0, w1, col):
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / ln, dx / ln
    poly(dst, [(x0 + nx * w0 / 2, y0 + ny * w0 / 2),
               (x1 + nx * w1 / 2, y1 + ny * w1 / 2),
               (x1 - nx * w1 / 2, y1 - ny * w1 / 2),
               (x0 - nx * w0 / 2, y0 - ny * w0 / 2)], col)


def grow_tree(x, base, h, seed, depth=3):
    """One deterministic skeleton shared by every season.

    Returns (segments, tips). Leaves are clusters hung on the tips, so the
    winter bare tree and the summer canopy are the same tree.
    """
    rng = random.Random(seed)
    segs, tips = [], []

    def rec(px, py, ang, length, width, d):
        for i in range(3):
            a = ang + rng.uniform(-0.09, 0.09)
            step = length / 3.0
            nx = px + math.sin(a) * step
            ny = py - math.cos(a) * step
            w2 = width * (1.0 - 0.22 * (i + 1) / 3.0)
            segs.append((px, py, nx, ny, width, w2))
            px, py, width = nx, ny, w2
        if d <= 0:
            tips.append((px, py, width))
            return
        n = 3 if d >= 2 else 2
        spread = rng.uniform(0.50, 0.72)
        for k in range(n):
            ca = (ang + (k - (n - 1) / 2.0) * spread + rng.uniform(-0.10, 0.10)) * 0.94
            rec(px, py, ca, length * rng.uniform(0.58, 0.70),
                max(0.55, width * 0.58), d - 1)

    rec(x, base, rng.uniform(-0.04, 0.04), h * 0.42, max(1.6, h * 0.072), depth)
    return segs, tips


def draw_foliage(dst, tips, h, tone, rng, hi_tint, shadow_tint, cluster_list=None,
                 r_scale=1.0):
    pts = [(x, y) for x, y, _ in tips]
    if not pts:
        return
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    for _ in range(3 if h > 140 else 2):
        pts.append((cx + rng.uniform(-0.12, 0.12) * h,
                    cy + rng.uniform(-0.06, 0.12) * h))

    for x, y in pts:
        ct = rng.choice(cluster_list) if cluster_list else tone
        r = h * rng.uniform(0.085, 0.118) * r_scale
        hi = mix(ct, hi_tint, 0.40)
        shadow = mix(ct, shadow_tint, 0.52)
        blobs = [(-0.34, 0.16, 0.82), (0.28, 0.04, 0.72),
                 (-0.06, -0.34, 0.64), (0.10, 0.36, 0.52)]
        for dx, dy, rr in blobs:
            circle(dst, x + dx * r - r * 0.14, y + dy * r + r * 0.18,
                   rr * r, shadow)
        for dx, dy, rr in blobs:
            circle(dst, x + dx * r, y + dy * r, rr * r, ct)
        # light only the sun side of the crown, and only some clusters
        if (x - cx) + (cy - y) > 0.0 and rng.random() < 0.65:
            circle(dst, x + 0.18 * r, y - 0.26 * r, 0.40 * r, hi)
        for _ in range(3):
            a = rng.uniform(0, math.tau)
            circle(dst, x + math.cos(a) * r * 0.95, y + math.sin(a) * r * 0.95,
                   r * rng.uniform(0.18, 0.30), ct)


def draw_tree(dst, tree, pal, *, leafy, tone=None, cluster_list=None, far=False):
    x, base, h = tree["x"], tree["base"], tree["h"]
    depth = 3 if h >= 90 else 2
    segs, tips = grow_tree(x, base + 2, h, tree["seed"], depth)

    bark = tree.get("bark") or pal["bark"]
    if far:
        bark = mix(bark, pal["mid_tree"], 0.35)
    flare = h * 0.045
    poly(dst, [(x - flare, base + 3), (x + flare, base + 3),
               (x + h * 0.018, base - h * 0.10), (x - h * 0.018, base - h * 0.10)],
         shade(bark, 0.92))
    for p0, p1, w0, w1 in ((s[0:2], s[2:4], s[4], s[5]) for s in segs):
        _segment(dst, p0, p1, max(0.55, w0), max(0.55, w1), bark)

    for s in (-1, 1):
        _segment(dst, (x, base + 1), (x + s * h * 0.085, base + 4),
                 max(1.0, h * 0.024), max(0.6, h * 0.008), shade(bark, 0.85))

    if not leafy:
        return

    accent = tree.get("accent")
    if accent and pal.get("accent_style") == "blossom":
        # green crown with blossom dabs clustered on the sunlit side
        draw_foliage(dst, tips, h, tone or pal["canopy"],
                     random.Random(tree["seed"] + 7),
                     pal["canopy_hi"], pal["canopy_shadow"], cluster_list)
        brng = random.Random(tree["seed"] + 13)
        cx = sum(p[0] for p in tips) / len(tips)
        cy = sum(p[1] for p in tips) / len(tips)
        for tx, ty, _ in tips:
            if (tx - cx) + (cy - ty) < -h * 0.05:
                continue
            for _ in range(6):
                circle(dst, tx + brng.uniform(-0.9, 0.9) * h * 0.05,
                       ty + brng.uniform(-0.9, 0.9) * h * 0.05,
                       h * brng.uniform(0.014, 0.028),
                       mix(brng.choice([pal["accent_canopy"],
                                        pal["accent_hi"],
                                        pal["accent_shadow"]]),
                           (255, 255, 255), brng.uniform(0.0, 0.35)))
        return

    if tone is None:
        tone = pal["accent_canopy"] if accent else pal["canopy"]
    if accent:
        hi_tint = pal.get("accent_hi") or pal["canopy_hi"]
        sh_tint = pal.get("accent_shadow") or pal["canopy_shadow"]
    else:
        hi_tint, sh_tint = pal["canopy_hi"], pal["canopy_shadow"]
    draw_foliage(dst, tips, h, tone, random.Random(tree["seed"] + 7),
                 hi_tint, sh_tint, cluster_list,
                 r_scale=0.86 if accent else 1.0)


def draw_bush(dst, bush, pal):
    tone = pal["canopy"] if pal["style"] == "leaf" else pal["grass"]
    if bush.get("accent"):
        tone = pal["accent_canopy"] or tone
    shadow = mix(tone, (16, 26, 18), 0.55)
    hi = mix(tone, pal["canopy_hi"] or (210, 226, 170), 0.45)
    rng = random.Random(bush["seed"])
    for _ in range(8):
        bx = bush["x"] + rng.uniform(-0.7, 0.7) * bush["rx"]
        by = bush["y"] + rng.uniform(-0.5, 0.2) * bush["ry"]
        r = rng.uniform(0.45, 0.9) * bush["ry"]
        circle(dst, bx, by, r, shadow if pal["style"] == "leaf" else tone)
    for _ in range(8):
        bx = bush["x"] + rng.uniform(-0.7, 0.7) * bush["rx"]
        by = bush["y"] + rng.uniform(-0.5, 0.2) * bush["ry"]
        r = rng.uniform(0.42, 0.82) * bush["ry"]
        circle(dst, bx, by - 1, r, tone)
        if pal["style"] == "leaf":
            circle(dst, bx + r * 0.25, by - r * 0.4, r * 0.5, hi)


# --------------------------------------------------------------------------
# scene layers
# --------------------------------------------------------------------------

def draw_cloud(dst, cloud, pal):
    cx, base, s = cloud["cx"], cloud["base"], cloud["s"]
    k = 100.0 * s
    k *= SS
    w, hh = int(2.05 * k), int(1.02 * k)
    ox, oy = w * 0.5, hh * 0.88

    mask = pygame.Surface((w, hh), pygame.SRCALPHA)
    # two overlapping base masses guarantee a solid, gap-free silhouette
    pygame.draw.ellipse(mask, (255, 255, 255, 255),
                        pygame.Rect(int(ox - 0.80 * k), int(oy - 0.38 * k),
                                    int(1.60 * k), int(0.42 * k)))
    pygame.draw.ellipse(mask, (255, 255, 255, 255),
                        pygame.Rect(int(ox - 0.58 * k), int(oy - 0.56 * k),
                                    int(1.16 * k), int(0.40 * k)))
    # flatten the base the way a cumulus sits on the horizon
    pygame.draw.rect(mask, (255, 255, 255, 255),
                     pygame.Rect(int(ox - 0.60 * k), int(oy - 0.14 * k),
                                 int(1.20 * k), int(0.14 * k)))
    for dx, dy, r in ((-0.54, -0.34, 0.26), (-0.30, -0.48, 0.31),
                      (0.00, -0.56, 0.34), (0.30, -0.48, 0.30),
                      (0.54, -0.32, 0.25), (0.42, -0.56, 0.22)):
        pygame.draw.circle(mask, (255, 255, 255, 255),
                           (int(ox + dx * k), int(oy + dy * k)), int(r * k))

    body = pal["cloud"]
    under = mix(pal["cloud_shade"], pal["cloud_tint"], 0.78)
    lit = mix(body, (255, 255, 255), 0.55)
    grad = pygame.Surface((w, hh), pygame.SRCALPHA)
    vgrad(grad, (0, 0, w, hh), [(0.00, lit), (0.34, body),
                                (0.82, body), (0.98, under), (1.00, under)])
    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    dst.blit(grad, (int(cx * SS - ox), int(base * SS - oy)))


def layer_sky(layout, pal):
    sky = pygame.Surface((SW, SH))
    vgrad(sky, (0, 0, SW, SH), [(p, c) for p, c in pal["sky"]])

    sunx, suny, sunr = pal["sun"]
    radial_glow(sky, sunx, HORIZON + 22, 460, pal["glow_color"],
                pal["glow_strength"] * 0.55, squash=0.30)
    radial_glow(sky, sunx, suny, 210, pal["glow_color"],
                pal["glow_strength"] * 0.95, squash=0.95)
    radial_glow(sky, sunx, suny, 66, pal["sun_color"],
                pal["glow_strength"] * 1.10, squash=0.95)

    circle(sky, sunx, suny, sunr * 1.10, pal["glow_color"])
    circle(sky, sunx, suny, sunr, pal["sun_color"])
    circle(sky, sunx - sunr * 0.10, suny - sunr * 0.10, sunr * 0.78,
           mix(pal["sun_color"], (255, 255, 255), 0.60))

    mist = pygame.Surface((SW, SH), pygame.SRCALPHA)
    mh = _i(46)
    for row in range(mh):
        t = row / max(1, mh - 1)
        a = int(64 * math.sin(math.pi * t))
        y = _i(HORIZON - 22) + row
        pygame.draw.line(mist, _c(pal["horizon_mist"], a), (0, y), (SW, y))
    sky.blit(mist, (0, 0))

    clouds = pygame.Surface((SW, SH), pygame.SRCALPHA)
    for c in layout.clouds:
        draw_cloud(clouds, c, pal)
    sky.blit(clouds, (0, 0))

    bird_col = mix(pal["sky"][0][1], (30, 34, 46), 0.62)
    for bx, by in layout.birds:
        for k in (-1, 1):
            pygame.draw.lines(
                sky, bird_col, False,
                [(_i(bx - 9 * k), _i(by)), (_i(bx - 3 * k), _i(by + 3)),
                 (_i(bx), _i(by)), (_i(bx + 3 * k), _i(by + 3)),
                 (_i(bx + 9 * k), _i(by))],
                max(1, _i(0.55)))
    return sky


def layer_far(layout, pal):
    surf = pygame.Surface((SW, SH), pygame.SRCALPHA)

    for fn, col in ((layout.ridge_a, pal["ridge_far"]), (layout.ridge_b, pal["ridge_near"])):
        pts = [(x, fn(x)) for x in range(-10, W + 30, 8)]
        pts += [(W + 30, HORIZON + 30), (-10, HORIZON + 30)]
        poly(surf, pts, col)

    for t in layout.far_trees:
        col = pal["far_tree"]
        if t["kind"] == "pine":
            h, w, base = t["h"], t["w"], t["base"]
            for i in range(3):
                frac = i / 3
                poly(surf, _pine_tier(t["x"], base - h * (0.16 + 0.60 * frac),
                                      base - h * (0.64 + 0.60 * frac),
                                      w * 0.5 * (1 - 0.6 * frac), 0.08),
                     mix(col, pal["ridge_far"], 0.10 + 0.28 * frac))
        else:
            circle(surf, t["x"], t["base"] - t["h"] * 0.60, t["h"] * 0.44, col)
            circle(surf, t["x"] - t["h"] * 0.22, t["base"] - t["h"] * 0.46,
                   t["h"] * 0.30, shade(col, 0.94))

    haze = pygame.Surface((SW, SH), pygame.SRCALPHA)
    hh = _i(72)
    for row in range(hh):
        t = row / max(1, hh - 1)
        a = int(78 * t)
        y = _i(236) + row
        pygame.draw.line(haze, _c(pal["horizon_mist"], a), (0, y), (SW, y))
    surf.blit(haze, (0, 0))
    return surf


def layer_mid(layout, pal):
    surf = pygame.Surface((SW, SH), pygame.SRCALPHA)

    pts = [(x, layout.mid_top(x)) for x in range(-10, W + 30, 8)]
    pts += [(W + 30, 380), (-10, 380)]
    poly(surf, pts, pal["mid_hill"])
    crest = [(x, layout.mid_top(x)) for x in range(-10, W + 30, 8)]
    for a, b in zip(crest, crest[1:]):
        line(surf, a, b, mix(pal["mid_hill"], (255, 255, 255), 0.42), 0.8)

    tones = pal.get("canopy_list")
    if tones:
        tones = [mix(c, pal["mid_tree"], 0.45) for c in tones]
    for t in layout.mid_trees:
        if t["kind"] == "pine":
            draw_pine(surf, {**t, "color": pal["mid_tree"]}, pal, far=True)
        elif pal["style"] == "bare":
            draw_tree(surf, t, pal, leafy=False, far=True)
        else:
            draw_tree(surf, t, pal, leafy=True, far=True,
                      tone=mix(pal["canopy"], pal["mid_tree"], 0.55),
                      cluster_list=tones)
    return surf


def _ground_points(layout):
    pts = [(x, layout.ground_top(x)) for x in range(-10, W + 30, 8)]
    pts += [(W + 30, H + 30), (-10, H + 30)]
    return pts


def layer_ground(layout, pal):
    surf = pygame.Surface((SW, SH), pygame.SRCALPHA)
    mask = pygame.Surface((SW, SH), pygame.SRCALPHA)
    poly(mask, _ground_points(layout), (255, 255, 255, 255))

    grad = pygame.Surface((SW, SH), pygame.SRCALPHA)
    vgrad(grad, (0, 0, SW, SH), [
        (0.80, pal["ground_top"]), (0.90, mix(pal["ground_top"], pal["ground_bottom"], 0.55)),
        (1.0, pal["ground_bottom"])])
    surf.blit(clip_to(mask, grad), (0, 0))

    detail = pygame.Surface((SW, SH), pygame.SRCALPHA)
    rng = random.Random(4242)
    for _ in range(14):
        cx = rng.uniform(-40, W + 40)
        cy = rng.uniform(340, 416)
        rx = rng.uniform(130, 320)
        ry = rng.uniform(7, 20)
        col = mix(pal["ground_top"], pal["ground_bottom"], rng.uniform(0.1, 0.7))
        ellipse(detail, cx, cy, rx, ry, col, 95)
    if pal["style"] == "bare":
        for _ in range(9):
            cx = rng.uniform(-60, W + 60)
            cy = rng.uniform(344, 402)
            rx = rng.uniform(90, 260)
            ry = rng.uniform(6, 15)
            ellipse(detail, cx, cy + ry * 0.5, rx, ry,
                    mix(pal["ground_top"], pal["ground_bottom"], 0.55), 90)
            ellipse(detail, cx, cy, rx, ry * 0.7,
                    mix(pal["ground_top"], (255, 255, 255), 0.5), 110)
    surf.blit(clip_to(mask, detail), (0, 0))

    # soft contact shadows where the near trees meet the meadow
    shadow = pygame.Surface((SW, SH), pygame.SRCALPHA)
    for t in layout.near_trees + layout.ridge_trees:
        if t["base"] < 330:
            continue
        ellipse(shadow, t["x"], t["base"] - 1, t["h"] * 0.30, 5.5,
                shade(pal["ground_bottom"], 0.62), 45)
    surf.blit(clip_to(mask, shadow), (0, 0))

    crest = [(x, layout.ground_top(x)) for x in range(-10, W + 30, 8)]
    for a, b in zip(crest, crest[1:]):
        line(surf, a, b, pal["ground_rim"], 1.4)

    for gx, gy, s, _ in layout.scatter:
        if gy < layout.ground_top(gx) + 2:
            continue
        if pal["style"] == "bare":
            col = pal["grass"] if rng.random() < 0.5 else pal["grass_light"]
            hgt = 4.0 * s
            for k in (-1, 0, 1):
                line(surf, (gx + k * 1.1 * s, gy), (gx + k * 2.2 * s, gy - hgt),
                     col, 0.45)
        else:
            col = pal["grass"] if rng.random() < 0.72 else pal["grass_light"]
            hgt = 5.0 * s
            for k in (-1, 0, 1, 2):
                sway = rng.uniform(-1.5, 1.5)
                line(surf, (gx + k * 1.1 * s, gy),
                     (gx + k * 2.3 * s + sway * s, gy - hgt * rng.uniform(0.65, 1.0)),
                     col, 0.5)
    return surf


def layer_near(layout, pal):
    surf = pygame.Surface((SW, SH), pygame.SRCALPHA)

    tones = pal.get("canopy_list")
    for t in layout.ridge_trees:
        trng = random.Random(t["seed"] + 3)
        if t["kind"] == "pine":
            draw_pine(surf, {**t, "color": mix(pal["near_tree"], pal["mid_tree"],
                                               trng.uniform(0.15, 0.55))}, pal)
        elif pal["style"] == "bare":
            draw_tree(surf, t, pal, leafy=False)
        else:
            tone = mix(pal["canopy"], pal["canopy_shadow"], 0.38)
            tone = mix(tone, pal["canopy_hi"], trng.uniform(0.0, 0.16))
            draw_tree(surf, t, pal, leafy=True, tone=tone, cluster_list=tones)

    for t in layout.near_trees:
        trng = random.Random(t["seed"] + 5)
        if t["kind"] == "pine":
            draw_pine(surf, {**t, "color": mix(pal["near_tree"], pal["mid_tree"],
                                               trng.uniform(0.0, 0.30))}, pal)
        elif pal["style"] == "bare":
            draw_tree(surf, t, pal, leafy=False)
        else:
            if t.get("accent"):
                tone = None
            else:
                tone = mix(pal["canopy"], pal["canopy_shadow"], 0.22)
                tone = mix(tone, pal["canopy_hi"], trng.uniform(0.0, 0.22))
            draw_tree(surf, t, pal, leafy=True, tone=tone,
                      cluster_list=None if t.get("accent") else tones)

    for b in layout.bushes:
        if pal["style"] == "bare":
            ellipse(surf, b["x"] + 2, b["y"] + 5, b["rx"] * 1.6, b["ry"] * 0.55,
                    mix(pal["ground_bottom"], pal["ground_top"], 0.45))
            ellipse(surf, b["x"], b["y"] + 1, b["rx"] * 1.35, b["ry"] * 0.45,
                    mix(pal["ground_top"], (255, 255, 255), 0.35))
            ellipse(surf, b["x"] - b["rx"] * 0.1, b["y"] - b["ry"] * 0.10,
                    b["rx"] * 0.9, b["ry"] * 0.35,
                    mix(pal["ground_top"], (255, 255, 255), 0.65))
        else:
            draw_bush(surf, b, pal)

    rng = random.Random(90210)
    if pal is _PALETTES["autumn"]:
        for _ in range(110):
            x, y = rng.uniform(-10, W + 10), rng.uniform(340, 405)
            col = rng.choice([(212, 118, 46), (188, 74, 38), (234, 160, 58), (158, 92, 44)])
            ellipse(surf, x, y, rng.uniform(1.4, 3.0), rng.uniform(0.7, 1.5), col)
        for _ in range(12):
            x, y = rng.uniform(0, W), rng.uniform(110, 320)
            ellipse(surf, x, y, rng.uniform(1.2, 2.4), rng.uniform(0.6, 1.1),
                    rng.choice([(226, 140, 48), (196, 86, 40)]), rng.randint(110, 190))
    elif pal is _PALETTES["spring"]:
        for _ in range(75):
            x, y = rng.uniform(0, W), rng.uniform(344, 404)
            stem_top = y - rng.uniform(3, 6)
            line(surf, (x, y), (x, stem_top), pal["grass"], 0.45)
            circle(surf, x, stem_top, rng.uniform(1.0, 1.8),
                   rng.choice([(255, 255, 255), (255, 226, 238), (255, 236, 160), (255, 210, 225)]))
        for _ in range(18):
            x, y = rng.uniform(0, W), rng.uniform(90, 300)
            ellipse(surf, x, y, rng.uniform(1.0, 2.0), rng.uniform(0.6, 1.2),
                    (255, 222, 235), rng.randint(110, 170))
    elif pal is _PALETTES["summer"]:
        for _ in range(40):
            x, y = rng.uniform(0, W), rng.uniform(344, 404)
            circle(surf, x, y, rng.uniform(1.0, 1.8), (250, 250, 240))
    else:
        for _ in range(46):
            x, y = rng.uniform(0, W), rng.uniform(338, 404)
            col = (112, 102, 92)
            hgt = rng.uniform(5, 12)
            for k in (-1, 0, 1):
                line(surf, (x, y), (x + k * 2.2, y - hgt), col, 0.4)
    # dark grass clumps along the bottom edge frame the meadow
    fg = shade(pal["ground_bottom"], 0.62)
    for _ in range(30):
        gx = rng.uniform(0, W)
        gy = 405
        for k in range(6):
            bx = gx + rng.uniform(-9, 9)
            line(surf, (bx, gy), (bx + rng.uniform(-7, 7), gy - rng.uniform(10, 26)),
                 fg, 0.9)

    return surf


def layer_night_sky(layout):
    sky = pygame.Surface((SW, SH))
    vgrad(sky, (0, 0, SW, SH), [
        (0.00, (6, 9, 22)), (0.42, (12, 20, 44)),
        (0.68, (26, 40, 68)), (0.86, (46, 58, 84))])

    radial_glow(sky, SUN_X, HORIZON + 34, 460, (26, 48, 88), 0.85, squash=0.36)

    stars = pygame.Surface((SW, SH), pygame.SRCALPHA)
    rng = random.Random(991)
    for _ in range(260):
        x, y = rng.uniform(0, W), rng.uniform(0, 280)
        fade = max(0.0, 1.0 - y / 330.0)
        a = int(rng.uniform(90, 255) * (0.2 + 0.8 * fade))
        circle(stars, x, y, rng.uniform(0.3, 1.5),
               rng.choice([(210, 224, 255), (255, 244, 226), (190, 210, 255)]), a)
    # a few brighter stars with a tiny glint
    for x, y in ((214, 62), (612, 44), (1044, 78), (402, 118), (862, 152)):
        circle(stars, x, y, 1.7, (255, 250, 236), 255)
        for dx, dy in ((4, 0), (-4, 0), (0, 4), (0, -4)):
            circle(stars, x + dx, y + dy, 0.6, (210, 224, 255), 120)
    sky.blit(stars, (0, 0))

    mist = pygame.Surface((SW, SH), pygame.SRCALPHA)
    mh = _i(40)
    for row in range(mh):
        t = row / max(1, mh - 1)
        a = int(40 * math.sin(math.pi * t))
        y = _i(HORIZON - 24) + row
        pygame.draw.line(mist, _c((90, 108, 132), a), (0, y), (SW, y))
    sky.blit(mist, (0, 0))
    return sky


_NIGHT_LIGHTS = {
    "far": (0.055, 0.065, 0.095),
    "mid": (0.035, 0.042, 0.065),
    "ground": (0.024, 0.030, 0.050),
    "near": (0.014, 0.018, 0.032),
}


def compose_night(layers):
    canvas = pygame.Surface((SW, SH), pygame.SRCALPHA)
    canvas.blit(layers["night_sky"], (0, 0))
    for name in ("far", "mid", "ground", "near"):
        canvas.blit(tint(layers[name], _NIGHT_LIGHTS[name]), (0, 0))
    final = pygame.Surface((W, H))
    final.blit(pygame.transform.smoothscale(canvas, (W, H)), (0, 0))
    return final


def layer_dawn_sky(layout, season):
    cfg = _DAWN[season]
    sky = pygame.Surface((SW, SH))
    vgrad(sky, (0, 0, SW, SH), cfg["stops"])

    # stars, denser and brighter high in the sky
    stars = pygame.Surface((SW, SH), pygame.SRCALPHA)
    rng = random.Random(7100 + len(season))
    for _ in range(130):
        x, y = rng.uniform(0, W), rng.uniform(4, 268)
        fade = max(0.0, 1.0 - y / 300.0)
        a = int(rng.uniform(70, 215) * (0.25 + 0.75 * fade))
        circle(stars, x, y, rng.uniform(0.35, 1.15),
               rng.choice([(216, 228, 255), (255, 240, 220)]), a)
    sky.blit(stars, (0, 0))

    # horizon bloom + the sun just clearing the distant treeline
    radial_glow(sky, SUN_X, HORIZON + 26, 430, cfg["glow"], 1.30, squash=0.40)
    radial_glow(sky, SUN_X, 278, 150, cfg["glow"], 1.20, squash=0.95)
    circle(sky, SUN_X, 272, 31, cfg["glow"])
    circle(sky, SUN_X, 272, 26, (255, 238, 202))
    circle(sky, SUN_X - 3, 269, 19, (255, 250, 232))

    mist = pygame.Surface((SW, SH), pygame.SRCALPHA)
    mh = _i(54)
    for row in range(mh):
        t = row / max(1, mh - 1)
        a = int(96 * math.sin(math.pi * t))
        y = _i(HORIZON - 30) + row
        pygame.draw.line(mist, _c(cfg["mist"], a), (0, y), (SW, y))
    sky.blit(mist, (0, 0))
    return sky


def compose_dawn(layers):
    canvas = pygame.Surface((SW, SH), pygame.SRCALPHA)
    canvas.blit(layers["dawn_sky"], (0, 0))
    for name in ("far", "mid", "ground", "near"):
        canvas.blit(tint(layers[name], _DAWN_LIGHTS[name]), (0, 0))
    final = pygame.Surface((W, H))
    final.blit(pygame.transform.smoothscale(canvas, (W, H)), (0, 0))
    return final


# --------------------------------------------------------------------------
# composition
# --------------------------------------------------------------------------

def build_layers(layout, season):
    pal = _PALETTES[season]
    return {
        "sky": layer_sky(layout, pal),
        "far": layer_far(layout, pal),
        "mid": layer_mid(layout, pal),
        "ground": layer_ground(layout, pal),
        "near": layer_near(layout, pal),
    }


def compose(layers, lights=None):
    canvas = pygame.Surface((SW, SH), pygame.SRCALPHA)
    canvas.blit(layers["sky"], (0, 0))
    for name in ("far", "mid", "ground", "near"):
        l = layers[name]
        if lights and name in lights:
            l = tint(l, lights[name])
        canvas.blit(l, (0, 0))
    final = pygame.Surface((W, H))
    final.blit(pygame.transform.smoothscale(canvas, (W, H)), (0, 0))
    return final


def make_strip(tiles, labels, path, pad=18, label_h=34):
    tw, th = tiles[0].get_size()
    w = tw + pad * 2
    h = len(tiles) * (th + label_h) + (len(tiles) + 1) * pad
    strip = pygame.Surface((w, h))
    strip.fill((10, 13, 18))
    font = pygame.font.SysFont("dejavusans", 19, bold=True)
    for idx, (img, label) in enumerate(zip(tiles, labels)):
        y = pad + idx * (th + label_h + pad)
        strip.blit(img, (pad, y + label_h))
        pygame.draw.rect(strip, (40, 48, 60), (pad - 1, y + label_h - 1, tw + 2, th + 2), 1)
        strip.blit(font.render(label, True, (222, 230, 240)), (pad, y + 8))
    pygame.image.save(strip, path)
    return strip


def make_sheet(tiles, labels, path, cols=2, pad=18, label_h=34):
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].get_size()
    w = cols * tw + (cols + 1) * pad
    h = rows * (th + label_h) + (rows + 1) * pad
    sheet = pygame.Surface((w, h))
    sheet.fill((10, 13, 18))
    font = pygame.font.SysFont("dejavusans", 19, bold=True)
    for idx, (img, label) in enumerate(zip(tiles, labels)):
        r, c = divmod(idx, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + label_h + pad)
        sheet.blit(img, (x, y + label_h))
        pygame.draw.rect(sheet, (40, 48, 60), (x - 1, y + label_h - 1, tw + 2, th + 2), 1)
        sheet.blit(font.render(label, True, (222, 230, 240)), (x, y + 8))
    pygame.image.save(sheet, path)
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", action="store_true", help="also save the depth layers")
    args = ap.parse_args()

    pygame.init()
    os.makedirs(OUT_DIR, exist_ok=True)
    layout = Layout()

    tiles, labels = [], []
    for season in ("spring", "summer", "autumn", "winter"):
        layers = build_layers(layout, season)
        img = compose(layers)
        path = os.path.join(OUT_DIR, f"{season}.png")
        pygame.image.save(img, path)
        print("wrote", path)
        tiles.append(img)
        labels.append(_PALETTES[season]["label"])
        if args.layers:
            for name, surf in layers.items():
                small = pygame.transform.smoothscale(surf, (W, H))
                pygame.image.save(small, os.path.join(OUT_DIR, f"{season}_{name}.png"))

    make_sheet(tiles, labels, os.path.join(HERE, "seasons_sheet.png"))
    print("wrote", os.path.join(HERE, "seasons_sheet.png"))

    dawn_tiles, dawn_labels = [], []
    for season in ("spring", "summer", "autumn", "winter"):
        layers = build_layers(layout, season)
        layers["dawn_sky"] = layer_dawn_sky(layout, season)
        img = compose_dawn(layers)
        path = os.path.join(OUT_DIR, f"{season}_dawn.png")
        pygame.image.save(img, path)
        print("wrote", path)
        dawn_tiles.append(img)
        dawn_labels.append(_PALETTES[season]["label"] + "  \u00b7  FIRST LIGHT")

    make_sheet(dawn_tiles, dawn_labels, os.path.join(HERE, "dawn_sheet.png"))
    print("wrote", os.path.join(HERE, "dawn_sheet.png"))

    layers = build_layers(layout, "winter")
    layers["night_sky"] = layer_night_sky(layout)
    night = compose_night(layers)
    pygame.image.save(night, os.path.join(OUT_DIR, "winter_night.png"))
    print("wrote", os.path.join(OUT_DIR, "winter_night.png"))

    day = pygame.image.load(os.path.join(OUT_DIR, "winter.png"))
    dawn = pygame.image.load(os.path.join(OUT_DIR, "winter_dawn.png"))
    make_strip([night, dawn, day],
               ["WINTER  \u00b7  NIGHT", "WINTER  \u00b7  FIRST LIGHT", "WINTER  \u00b7  DAY"],
               os.path.join(HERE, "winter_light_cycle.png"))
    print("wrote", os.path.join(HERE, "winter_light_cycle.png"))


if __name__ == "__main__":
    main()
