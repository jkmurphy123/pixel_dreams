#!/usr/bin/env python3
"""Prototype v2: the video's pen-and-ink techniques as code, one finished sheet.

Fixes over v1: grain stamping goes through pygame's C ellipse rasteriser (fast,
rotated), the land mass actually fills the sheet and bleeds off the edges, and
every feature is placed by asking the LAND MASK where it may go.

Run: SDL_VIDEODRIVER=dummy  python ink_proto2.py
Writes map_proto2.png next to itself and prints per-stage timings.
"""
import math
import os
import random
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1080, 1920))

SS = 2
VW, VH = 1080, 1920
W, H = VW * SS, VH * SS

INK = (43, 33, 26)
PAPER = (232, 217, 184)

# Pigma Micron nib sizes (mm) on a ~200 mm wide sheet
PX_PER_MM = VW / 200.0
PEN = {"003": 0.15, "005": 0.20, "01": 0.25, "02": 0.30, "03": 0.35, "05": 0.45}
PEN = {k: v * PX_PER_MM * SS for k, v in PEN.items()}

# field grid: 1 cell = 7.5 device px (at SS=2), i.e. ~3.75 px on the glass
GW, GH = 288, 512
CELL_X, CELL_Y = W / GW, H / GH
# coarse grid for the elevation field
EW, EH = GW // 2, GH // 2


def ms(t0):
    return (time.perf_counter() - t0) * 1000.0


# ═══════════════════════════════════════════════════════════════════════
# PEN PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════

class Hand:
    """A drawing hand. The video's 'hold the pen high up' trick = a line with
    less control, modelled as an AR(1) wander plus fine tremor."""

    def __init__(self, seed=0, wander=0.72, tremor=0.55):
        self.rng = random.Random(seed)
        self.drift = 0.0
        self.wander = wander
        self.tremor = tremor

    def jitter(self, pts, amp=1.7, fine=0.4):
        out = []
        for i, (x, y) in enumerate(pts):
            if i == 0:
                dx, dy = pts[1][0] - x, pts[1][1] - y
            elif i == len(pts) - 1:
                dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
            else:
                dx = pts[i + 1][0] - pts[i - 1][0]
                dy = pts[i + 1][1] - pts[i - 1][1]
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            self.drift = self.drift * self.wander + self.rng.gauss(0, 1.0)
            o = self.drift * amp + self.rng.gauss(0, fine)
            out.append((x + nx * o, y + ny * o))
        return out


def pen(surf, pts, width, hand, taper=False, color=INK):
    """One hand-drawn stroke: jittered path, per-segment width wobble,
    optional nib-pressure taper at the ends."""
    if len(pts) < 2:
        return
    j = hand.jitter(pts)
    n = len(j) - 1
    for i in range(n):
        x0, y0 = j[i]
        x1, y1 = j[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 0.02:
            continue
        w = width * (1.0 + hand.rng.gauss(0, 0.10))
        if taper:
            t = i / max(1, n - 1)
            w *= 0.30 + 0.70 * math.sin(math.pi * t) ** 0.45
        half = max(0.35, w * 0.5)
        nx, ny = -dy / L * half, dx / L * half
        pygame.draw.polygon(surf, color, [
            (x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])


def curve(surf, pts, width, hand, n_sub=6, taper=False, color=INK):
    """Catmull-Rom through the control points, then pen it (the big squiggle)."""
    if len(pts) < 2:
        return
    dense = []
    for i in range(len(pts) - 1):
        p0 = pts[max(0, i - 1)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(len(pts) - 1, i + 2)]
        for k in range(n_sub):
            t = k / n_sub
            t2, t3 = t * t, t * t * t
            dense.append((
                0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    dense.append(pts[-1])
    pen(surf, dense, width, hand, taper=taper, color=color)


_dots = {}


def dot(surf, x, y, r, alpha=255, color=INK):
    key = (round(r * 2) / 2, alpha, color)
    s = _dots.get(key)
    if s is None:
        ri = max(1, int(round(r)))
        s = pygame.Surface((ri * 2 + 1, ri * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(s, color + (alpha,), (ri, ri), ri)
        _dots[key] = s
    surf.blit(s, (int(x - s.get_width() / 2), int(y - s.get_height() / 2)))


# ═══════════════════════════════════════════════════════════════════════
# 1. THE LAND MASS — pour the rice, trace the outline
# ═══════════════════════════════════════════════════════════════════════

GRAINS = []


def build_grains():
    """Pre-render rice grains: flat ellipses at 24 rotations, 3 sizes."""
    for size in (4, 5, 6, 7):
        for a in range(24):
            g = pygame.Surface((size, size), pygame.SRCALPHA)
            rw = size // 2 + 1
            rh = max(1, int(size * 0.20))
            pygame.draw.ellipse(g, (255, 255, 255, 255),
                                (0, size // 2 - rh, size, rh * 2))
            GRAINS.append(pygame.transform.rotate(g, a * 15))


def pour_rice(rng, clumps, grain_target, sigma=(0.22, 0.34)):
    """Pour rice: blit grain sprites into a surface, in clumps.

    The video's 'move it around and adjust what the rice looks like before you
    trace' step is the closing (dilate then erode): it welds grains that merely
    touch into one solid mass WITHOUT rounding off the scalloped outline, which
    is what keeps the traced border scraggly rather than blobby.
    """
    surf = pygame.Surface((GW, GH))
    surf.fill((0, 0, 0))
    for _ in range(clumps):
        cx = rng.uniform(-0.10, 1.10) * GW
        cy = rng.uniform(-0.10, 1.10) * GH
        sx = GW * rng.uniform(*sigma)
        sy = GH * rng.uniform(*sigma) * 0.85
        for _ in range(grain_target):
            surf.blit(GRAINS[rng.randrange(len(GRAINS))],
                      (int(rng.gauss(cx, sx)), int(rng.gauss(cy, sy))),
                      special_flags=pygame.BLEND_RGB_MAX)
    return close(surf)


def close(surf, r=2):
    """Morphological closing via blits (C speed): dilate, then erode."""
    dil = surf.copy()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx or dy:
                dil.blit(surf, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)
    inv = pygame.Surface((GW, GH))
    inv.fill((255, 255, 255))
    inv.blit(dil, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    dil2 = inv.copy()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx or dy:
                dil2.blit(inv, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)
    out = pygame.Surface((GW, GH))
    out.fill((255, 255, 255))
    out.blit(dil2, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    raw = pygame.image.tostring(out, "RGB")
    mask = bytearray(len(raw) // 3)
    for i in range(len(mask)):
        if raw[i * 3]:
            mask[i] = 1
    return mask, out


def pour_region(rng, rw, rh, clumps, grain_target, sigma=0.16):
    """Any organic REGION (a desert, a lake basin, a forest) is the same pour,
    at grid resolution. Returns a bytearray on the rw x rh grid."""
    s = pygame.Surface((rw, rh))
    s.fill((0, 0, 0))
    for _ in range(clumps):
        cx = rng.uniform(0.15, 0.85) * rw
        cy = rng.uniform(0.15, 0.85) * rh
        sx, sy = rw * sigma, rh * sigma
        for _ in range(grain_target):
            g = GRAINS[rng.randrange(len(GRAINS))]
            g = pygame.transform.smoothscale(g, (max(3, g.get_width() // 3),
                                                 max(3, g.get_height() // 3)))
            s.blit(g, (int(rng.gauss(cx, sx)), int(rng.gauss(cy, sy))),
                   special_flags=pygame.BLEND_RGB_MAX)
    raw = pygame.image.tostring(s, "RGB")
    return bytearray(1 if raw[i * 3] else 0 for i in range(rw * rh))


def marching_squares(mask, gw, gh):
    segs = []
    ap = segs.append
    for y in range(gh - 1):
        row = y * gw
        nrow = row + gw
        for x in range(gw - 1):
            a = mask[row + x]
            b = mask[row + x + 1]
            c = mask[nrow + x + 1]
            d = mask[nrow + x]
            if a == b == c == d:
                continue
            top = (x + 0.5, y)
            right = (x + 1, y + 0.5)
            bot = (x + 0.5, y + 1)
            left = (x, y + 0.5)
            idx = a | (b << 1) | (c << 2) | (d << 3)
            if idx in (1, 14):   ap((left, top))
            elif idx in (2, 13): ap((top, right))
            elif idx in (3, 12): ap((left, right))
            elif idx in (4, 11): ap((right, bot))
            elif idx in (6, 9):  ap((top, bot))
            elif idx in (7, 8):  ap((left, bot))
            elif idx == 5:      # saddle: a and c inside
                if (a + b + c + d) * 0.25 > 0.5:
                    ap((left, right)); ap((top, bot))
                else:
                    ap((left, top)); ap((right, bot))
            elif idx == 10:     # saddle: b and d inside - the OTHER pairing
                if (a + b + c + d) * 0.25 > 0.5:
                    ap((left, right)); ap((top, bot))
                else:
                    ap((top, right)); ap((left, bot))
    return segs


def chain(segs, min_len=10):
    """Chain unordered segments into loops. Returns (loop, closed) - a chain
    that ends where the land runs off the traced field is OPEN, and must NOT be
    closed with a straight line (that is the single ugliest artefact: a ruler
    line across the sea)."""
    from collections import defaultdict
    bucket = defaultdict(list)
    for i, (p, q) in enumerate(segs):
        bucket[p].append(i)
        bucket[q].append(i)
    used = bytearray(len(segs))
    loops = []
    for start in range(len(segs)):
        if used[start]:
            continue
        p, q = segs[start]
        used[start] = 1
        loop = [p, q]
        cur = q
        closed = False
        while True:
            nxt = None
            for i in bucket[cur]:
                if not used[i]:
                    nxt = i
                    break
            if nxt is None:
                break
            used[nxt] = 1
            a, b = segs[nxt]
            cur = b if a == cur else a
            loop.append(cur)
            if cur == loop[0]:
                closed = True
                break
        if len(loop) >= min_len:
            if closed:
                loop.append(loop[0])
            loops.append((loop, closed))
    return loops


def loops_sorted(mask, min_cells=140):
    out = []
    for l, closed in chain(marching_squares(mask, GW, GH)):
        area = 0.0
        for i in range(len(l) - 1):
            area += l[i][0] * l[i + 1][1] - l[i + 1][0] * l[i][1]
        area = abs(area) * 0.5
        if area >= min_cells:
            out.append((area, l, closed))
    out.sort(key=lambda t: -t[0])
    return out


def to_dev(loop):
    return [(x * CELL_X, y * CELL_Y) for (x, y) in loop]


def resample(pts, step):
    out = [pts[0]]
    acc = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d = math.hypot(x1 - x0, y1 - y0)
        if d == 0:
            continue
        acc += d
        if acc >= step:
            out.append((x1, y1))
            acc = 0.0
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


class Land:
    """The poured rice, plus the queries every later pass needs."""

    def __init__(self, mask, surf):
        self.mask = mask
        self.surf = surf
        self.rng = None

        # chamfer (2-pass) distance to the nearest water, on the coarse grid,
        # used as a stand-in for elevation: inland = high ground.
        INF = 1 << 20
        d = [INF] * (EW * EH)
        for y in range(EH):
            for x in range(EW):
                if not mask[(y * 2 + 1) * GW + x * 2 + 1]:
                    d[y * EW + x] = 0
        for y in range(EH):
            row = y * EW
            for x in range(EW):
                v = d[row + x]
                if v == 0:
                    continue
                best = v
                if x: best = min(best, d[row + x - 1] + 3)
                if y: best = min(best, d[row - EW + x] + 3)
                if x and y: best = min(best, d[row - EW + x - 1] + 4)
                if x + 1 < EW and y: best = min(best, d[row - EW + x + 1] + 4)
                d[row + x] = best
        for y in range(EH - 1, -1, -1):
            row = y * EW
            for x in range(EW - 1, -1, -1):
                v = d[row + x]
                if v == 0:
                    continue
                best = v
                if x + 1 < EW: best = min(best, d[row + x + 1] + 3)
                if y + 1 < EH: best = min(best, d[row + EW + x] + 3)
                if x + 1 < EW and y + 1 < EH: best = min(best, d[row + EW + x + 1] + 4)
                if x and y + 1 < EH: best = min(best, d[row + EW + x - 1] + 4)
                d[row + x] = best
        self.dist = d

    def on_land(self, x, y):
        gx, gy = int(x / CELL_X), int(y / CELL_Y)
        if 0 <= gx < GW and 0 <= gy < GH:
            return self.mask[gy * GW + gx] == 1
        return False

    def elevation(self, x, y):
        gx, gy = int(x / CELL_X) // 2, int(y / CELL_Y) // 2
        if 0 <= gx < EW and 0 <= gy < EH:
            return self.dist[gy * EW + gx]
        return 0

    def land_points(self, n, margin=70, min_elev=0, rng=None,
                    min_sep=0.0):
        """Rejection-sample land points in DEVICE px.

        min_sep is enforced through an occupancy HASH, not a scan over the
        accepted list: with a plain `any(...)` scan a restrictive min_sep
        makes the sampler thrash against its try cap and the pass costs
        seconds while producing fewer points than asked for.
        """
        rng = rng or random
        out = []
        tries = 0
        if min_sep > 0:
            cell = min_sep
            grid = {}
            def far_enough(x, y):
                gx, gy = int(x / cell), int(y / cell)
                for ax in (gx - 1, gx, gx + 1):
                    for ay in (gy - 1, gy, gy + 1):
                        for (px, py) in grid.get((ax, ay), ()):
                            if (x - px) ** 2 + (y - py) ** 2 < min_sep * min_sep:
                                return False
                return True
            def remember(x, y):
                grid.setdefault((int(x / cell), int(y / cell)), []).append((x, y))
        else:
            far_enough = lambda x, y: True
            remember = lambda x, y: None
        while len(out) < n and tries < n * 400:
            tries += 1
            x = rng.uniform(margin, VW - margin)
            y = rng.uniform(margin, VH - margin)
            if not self.on_land(x, y):
                continue
            if self.elevation(x, y) < min_elev:
                continue
            if not far_enough(x, y):
                continue
            out.append((x, y))
            remember(x, y)
        return out


# ═══════════════════════════════════════════════════════════════════════
# 2. THE WATER ILLUSION
# ═══════════════════════════════════════════════════════════════════════

def offset_ring(pts, d):
    """Parallel curve at distance d. Handles OPEN polylines too (clamped
    one-sided normals at the ends), which is what a coast that runs off the
    page needs."""
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i - 1] if i > 0 else pts[i]
        b = pts[i + 1] if i + 1 < n else pts[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        out.append((pts[i][0] - dy / L * d, pts[i][1] + dx / L * d))
    return out


def coast_water(surf, path, hand, rings=(13.0, 21.0, 29.0)):
    """Trace a line parallel to the coast, then alternate the video's four
    patterns along it: hash / hash+dot / hash-dot-hash / dot-hash."""
    rng = hand.rng
    for ri, d in enumerate(rings):
        ring = resample(offset_ring(path, d), 6.5)
        pen(surf, ring, PEN["005"] * 0.9, hand)
        i = 0
        while i < len(ring) - 4:
            j = min(len(ring) - 3, i + rng.randint(3, 5))
            x0, y0 = ring[i]
            x1, y1 = ring[j]
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L, dx / L
            ln = rng.uniform(10.0, 18.0) * (1.0 - 0.16 * ri)
            ex, ey = x0 + nx * ln, y0 + ny * ln
            k = rng.random()
            if k < 0.30:
                pen(surf, [(x0, y0), (ex, ey)], PEN["005"], hand)
            elif k < 0.55:
                pen(surf, [(x0, y0), (ex, ey)], PEN["005"], hand)
                dot(surf, ex + nx * 4, ey + ny * 4, 1.6)
            elif k < 0.80:
                pen(surf, [(x0, y0), (ex, ey)], PEN["005"], hand)
                dot(surf, ex + nx * 4, ey + ny * 4, 1.6)
                pen(surf, [(x0 + nx * 4, y0 + ny * 4),
                           (ex - nx * 4, ey - ny * 4)], PEN["005"], hand)
            else:
                dot(surf, (x0 + ex) / 2, (y0 + ey) / 2, 1.7)
                pen(surf, [(x0, y0), (ex, ey)], PEN["005"], hand)
            i = j + rng.randint(1, 3)


def lake(surf, center, r, hand):
    rng = hand.rng
    n = 16
    a0 = rng.uniform(0, math.tau)
    pts = []
    for i in range(n + 1):
        a = a0 + math.tau * i / n
        rr = r * (0.70 + 0.5 * rng.random())
        pts.append((center[0] + math.cos(a) * rr, center[1] + math.sin(a) * rr * 0.78))
    pts.append(pts[0])
    dense = resample(pts, 7.0)
    pen(surf, dense, PEN["005"], hand)
    for k in range(3):
        inner = []
        for (x, y) in dense:
            dx, dy = center[0] - x, center[1] - y
            L = math.hypot(dx, dy) or 1.0
            f = 0.16 + 0.15 * k
            inner.append((x + dx * f, y + dy * f))
        if k == 2:
            for (x, y) in resample(inner, 10.0):
                dot(surf, x, y, 1.4)
            break
        pen(surf, inner, PEN["005"] * 0.8, hand)
        for (x, y) in resample(inner, 12.0):
            dot(surf, x, y, 1.5)


# ═══════════════════════════════════════════════════════════════════════
# 3. FEATURE RECIPES
# ═══════════════════════════════════════════════════════════════════════

def mountain(surf, cx, base_y, size, hand, tall=False):
    rng = hand.rng
    h = size * (1.55 if tall else 1.0)
    half = size * (0.60 if tall else 0.85)
    peak = (cx + rng.gauss(0, size * 0.06), base_y - h)
    lft = (cx - half + rng.gauss(0, size * 0.05), base_y + rng.gauss(0, size * .1))
    rgt = (cx + half + rng.gauss(0, size * 0.05), base_y + rng.gauss(0, size * .1))
    fl, fr = [], []
    for i in range(9):
        t = i / 8.0
        fl.append((lft[0] + (peak[0] - lft[0]) * t + rng.gauss(0, size * 0.035),
                   lft[1] + (peak[1] - lft[1]) * t))
        fr.append((rgt[0] + (peak[0] - rgt[0]) * t + rng.gauss(0, size * 0.035),
                   rgt[1] + (peak[1] - rgt[1]) * t))
    pen(surf, fl, PEN["02"], hand, taper=True)
    pen(surf, fr, PEN["02"], hand, taper=True)
    # zigzags near the peak, 01 pen
    for zi in range(1 + (1 if (tall or rng.random() < 0.45) else 0)):
        f = 0.28 + 0.22 * zi
        lx = lft[0] + (peak[0] - lft[0]) * f
        rx = rgt[0] + (peak[0] - rgt[0]) * f
        zy = lft[1] + (peak[1] - lft[1]) * f
        mx = (lx + rx) / 2
        pen(surf, [(lx, zy),
                   (lx + (mx - lx) * 0.45, zy - size * 0.14),
                   (mx, zy + size * 0.02),
                   (mx + (rx - mx) * 0.55, zy - size * 0.13),
                   (rx, zy - size * 0.01)], PEN["01"], hand)
    # hatches hanging off the points on the LEFT flank
    dx_, dy_ = peak[0] - lft[0], peak[1] - lft[1]
    L = math.hypot(dx_, dy_) or 1.0
    nxp, nyp = dy_ / L, -dx_ / L
    for i in range(2, 8):
        t = i / 9.0
        x = lft[0] + (peak[0] - lft[0]) * t
        y = lft[1] + (peak[1] - lft[1]) * t
        ln = size * rng.uniform(0.11, 0.21)
        pen(surf, [(x, y), (x + nxp * ln, y + nyp * ln)], PEN["01"], hand)
    # shading: hairlines down the RIGHT slope (light comes from the left)
    n_sh = 3 if not tall else 6
    for i in range(n_sh):
        f = 0.30 + 0.58 * (i / max(1, n_sh - 1))
        x = peak[0] + (rgt[0] - peak[0]) * f
        y = peak[1] + (rgt[1] - peak[1]) * f
        pen(surf, [(x, y), (peak[0] + (rgt[0] - peak[0]) * (f * 0.70),
                            y + (base_y - peak[1]) * rng.uniform(0.18, 0.36))],
            PEN["005"], hand)
    # texture dashes on the left, 05 pen
    for _ in range(rng.randint(2, 4)):
        t = rng.uniform(0.35, 0.9)
        x = lft[0] + (peak[0] - lft[0]) * t
        y = lft[1] + (peak[1] - lft[1]) * t
        pen(surf, [(x, y), (x + rng.gauss(0, size * .07), y + size * .07)],
            PEN["05"], hand)
    # 1-3 signature dots on the edges
    for _ in range(rng.randint(1, 3)):
        side = fl if rng.random() < 0.5 else fr
        p = side[rng.randrange(1, len(side) - 1)]
        dot(surf, p[0] + rng.gauss(0, 2), p[1] + rng.gauss(0, 2), 2.1)


def hill(surf, cx, base_y, size, hand):
    rng = hand.rng
    half, h = size * 0.85, size * 0.42
    curve(surf, [(cx - half, base_y), (cx - half * 0.5, base_y - h * 1.3),
                 (cx + half * 0.5, base_y - h * 1.3), (cx + half, base_y)],
          PEN["02"], hand, n_sub=7, taper=True)
    for _ in range(int(size * 0.5)):
        t = rng.uniform(0.45, 1.0)
        dot(surf, cx - half + 2 * half * t,
            base_y - h * math.sin(math.pi * t) * rng.uniform(0.25, 1.0),
            1.5 if rng.random() < 0.7 else 2.0)
    grass(surf, cx + half * rng.uniform(-0.4, 0.95),
          base_y + rng.gauss(0, 4), size * 0.17, hand)


def grass(surf, cx, cy, size, hand):
    rng = hand.rng
    n = rng.randint(2, 3)
    for i in range(n):
        x = cx + (i - (n - 1) / 2) * size * 0.45
        pen(surf, [(x, cy), (x + rng.gauss(0, size * .12),
                             cy - size * rng.uniform(.8, 1.35))], PEN["005"], hand)
    for side in (-1, 1):
        if rng.random() < 0.8:
            dot(surf, cx + side * size * 0.9, cy - size * rng.uniform(0.1, 0.6), 1.5)


def dune(surf, cx, cy, size, hand):
    rng = hand.rng
    half = size * 0.95
    n_s = rng.randint(2, 4)
    pts = [(cx - half, cy)]
    for i in range(n_s):
        sx = cx - half + (2 * half) * ((i + 0.5) / n_s)
        pts += [(sx - size * 0.26, cy - size * 0.32),
                (sx + size * 0.26, cy + size * 0.32),
                (sx + size * 0.52, cy - size * 0.02)]
    curve(surf, pts, PEN["01"], hand, n_sub=5)
    for i in range(n_s):
        sx = cx - half + (2 * half) * ((i + 0.72) / n_s)
        pen(surf, [(sx, cy - size * 0.02), (sx + size * 0.32, cy + size * 0.28)],
            PEN["01"], hand)
        for k in range(2):
            pen(surf, [(sx - size * (0.32 + 0.11 * k), cy - size * 0.26),
                       (sx - size * (0.15 + 0.11 * k), cy + size * 0.06)],
                PEN["01"], hand)


def pine(surf, cx, cy, size, hand):
    """Two stacked zigzag triangles + stem; stipple the RIGHT side."""
    rng = hand.rng
    w0 = size * 0.44
    for tier in range(2):
        f = 1.0 - tier * 0.42
        top_y = cy - size * (1.0 - tier * 0.42)
        mid_y = cy - size * 0.30
        w = w0 * f
        zig = 3
        left, right = [(cx, top_y)], [(cx, top_y)]
        for i in range(1, zig + 1):
            t = i / zig
            yy = top_y + (mid_y - top_y) * t
            left.append((cx - w * t - (w * 0.30 if i % 2 else 0), yy))
            right.append((cx + w * t + (w * 0.30 if i % 2 else 0), yy))
        pen(surf, left, PEN["005"], hand)
        pen(surf, right, PEN["005"], hand)
    pen(surf, [(cx, cy - size * 0.30), (cx, cy)], PEN["005"], hand)
    for _ in range(int(size * 1.0)):
        t = rng.uniform(0.35, 1.0)
        dot(surf, cx + w0 * t * 0.85, cy - size * rng.uniform(0.15, 0.85),
            1.2 if rng.random() < 0.65 else 1.6)
    for _ in range(rng.randint(1, 3)):
        dot(surf, cx + rng.gauss(0, size * .25), cy + rng.uniform(1, size * .2), 1.4)


def oak(surf, cx, cy, size, hand):
    rng = hand.rng
    a0 = rng.uniform(0, math.tau)
    pts = []
    for i in range(11):
        a = a0 + math.tau * i / 10
        rr = size * (0.45 + 0.30 * rng.random())
        pts.append((cx + math.cos(a) * rr, cy - size * 0.55 + math.sin(a) * rr * 0.8))
    pen(surf, pts, PEN["005"], hand)
    pen(surf, [(cx, cy - size * 0.18), (cx, cy)], PEN["005"], hand)
    for _ in range(int(size * 1.2)):
        t = rng.uniform(0.4, 1.0)
        dot(surf, cx + math.cos(rng.uniform(-1.2, 1.2)) * size * 0.5 * t,
            cy - size * rng.uniform(0.2, 1.0), 1.25)


# ═══════════════════════════════════════════════════════════════════════
# 4. PAPER
# ═══════════════════════════════════════════════════════════════════════

def make_paper(seed=4):
    rng = random.Random(seed)
    s = pygame.Surface((VW, VH)).convert()
    s.fill(PAPER)
    bl = pygame.Surface((VW, VH), pygame.SRCALPHA)
    for _ in range(170):
        pygame.draw.circle(bl, rng.choice([(196, 170, 128), (212, 192, 152),
                                           (243, 233, 210)]) + (rng.randint(3, 9),),
                           (int(rng.uniform(0, VW)), int(rng.uniform(0, VH))),
                           int(rng.uniform(30, 190)))
    s.blit(bl, (0, 0))
    for _ in range(2800):
        x, y = rng.uniform(0, VW), rng.uniform(0, VH)
        if rng.random() < 0.5:
            pygame.draw.line(s, (152, 130, 94), (x, y),
                             (x + rng.gauss(0, 5), y + rng.gauss(0, 1.2)), 1)
        else:
            s.set_at((int(x), int(y)), (170, 148, 110))
    v = pygame.Surface((VW, VH), pygame.SRCALPHA)
    for i in range(100):
        a = int(30 * (1 - i / 100.0) ** 2)
        if a <= 0:
            continue
        pygame.draw.rect(v, (120, 96, 60, a),
                         (int(i * 1.1), int(i * 1.9),
                          VW - int(i * 2.2), VH - int(i * 3.8)), 2)
    s.blit(v, (0, 0))
    return s


# ═══════════════════════════════════════════════════════════════════════
# 5. COMPOSE
# ═══════════════════════════════════════════════════════════════════════

def main():
    t_all = time.perf_counter()
    rng = random.Random(20261016)
    hand = Hand(seed=7)
    build_grains()

    print("1. land mass")
    t = time.perf_counter()
    mask, surf = pour_rice(rng, clumps=4, grain_target=26000,
                           sigma=(0.13, 0.21))
    print(f"   pour rice: {ms(t):.0f} ms  land {sum(mask)/len(mask)*100:.1f}%")
    land = Land(mask, surf)

    t = time.perf_counter()
    shapes = loops_sorted(mask)
    dev = [(a, to_dev(l), c) for a, l, c in shapes]
    n_open = sum(1 for _, _, c in dev if not c)
    print(f"   trace contour: {ms(t):.0f} ms  {len(dev)} land masses "
          f"({n_open} running off the page), largest {len(dev[0][1])} verts")

    ink = pygame.Surface((W, H), pygame.SRCALPHA)
    ink.fill((0, 0, 0, 0))

    t = time.perf_counter()
    for _, l, _ in dev:
        pen(ink, resample(l, 3.6), PEN["05"], hand, taper=True)
    print(f"   continent border (05): {ms(t):.0f} ms  ({len(dev)} land masses)")

    t = time.perf_counter()
    for _, l, _ in dev[:3]:
        coast_water(ink, resample(l, 5.0), hand)
    print(f"   water illusion: {ms(t):.0f} ms")

    t = time.perf_counter()
    n_lake = 0
    for p in land.land_points(6, margin=170, min_elev=14, rng=rng, min_sep=200):
        lake(ink, p, rng.uniform(30, 55), hand)
        n_lake += 1
    print(f"   lakes: {ms(t):.0f} ms ({n_lake})")

    # ── mountain ranges: walk a line, overlap peaks, taper both ends ──
    print("2. mountains (highest ground, overlapping, tapering)")
    t = time.perf_counter()
    n_mtn, n_rng = 0, 0
    starts = land.land_points(6, margin=150, min_elev=34, rng=rng, min_sep=280)
    for sx, sy in starts:
        ang = rng.uniform(0, math.tau)
        cx, cy = sx, sy
        total = rng.randint(12, 22)
        step = 0
        while step < total:
            step += 1
            ang += rng.gauss(0, 0.16)
            cx += math.cos(ang) * rng.uniform(66, 104)
            cy += math.sin(ang) * rng.uniform(66, 104)
            if not (30 < cx < VW - 30 and 30 < cy < VH - 30):
                break
            if not land.on_land(cx, cy):
                continue
            f = min(step / 6.0, (total - step) / 6.0, 1.0)
            size = 86 + 118 * max(0.10, f)
            mountain(ink, cx, cy, size, hand, tall=(rng.random() < 0.16))
            n_mtn += 1
        n_rng += 1
    print(f"   ranges: {ms(t):.0f} ms ({n_rng} ranges, {n_mtn} peaks)")

    print("3. hills as the transition, then forest")
    t = time.perf_counter()
    n_hill = 0
    for p in land.land_points(55, margin=70, min_elev=8, rng=rng, min_sep=118):
        hill(ink, p[0], p[1], rng.uniform(88, 150), hand)
        n_hill += 1
    print(f"   hills: {ms(t):.0f} ms ({n_hill})")

    t = time.perf_counter()
    n_tree = 0
    for fx, fy in land.land_points(3, margin=230, min_elev=24, rng=rng, min_sep=430):
        for _ in range(170):
            x = fx + rng.gauss(0, 235)
            y = fy + rng.gauss(0, 300)
            if not (28 < x < VW - 28 and 28 < y < VH - 28):
                continue
            if not land.on_land(x, y):
                continue
            if rng.random() < 0.80:
                pine(ink, x, y, rng.uniform(44, 66), hand)
            else:
                oak(ink, x, y, rng.uniform(40, 58), hand)
            n_tree += 1
    print(f"   forest: {ms(t):.0f} ms ({n_tree} trees)")

    print("4. desert: its own rice pour, dense 01 rim, lighter 005 field, dunes")
    t = time.perf_counter()
    n_dot, n_dune, n_des = 0, 0, 0
    DW, DH = 96, 170
    dcell = (VW / DW, VH / DH)
    for _ in range(2):
        reg = pour_region(rng, DW, DH, clumps=2, grain_target=900)

        def in_desert(x, y):
            gx, gy = int(x / dcell[0]), int(y / dcell[1])
            if 0 <= gx < DW and 0 <= gy < DH:
                return reg[gy * DW + gx] == 1
            return False

        pts = [(x * dcell[0], y * dcell[1])
               for y in range(0, DH, 2) for x in range(0, DW, 2)
               if reg[y * DW + x] and land.on_land(x * dcell[0], y * dcell[1])]
        if len(pts) < 40:
            continue
        n_des += 1
        # the field: lighter 005 dots inside the region
        for (x, y) in pts:
            for _ in range(9):
                px = x + rng.gauss(0, dcell[0] * 1.2)
                py = y + rng.gauss(0, dcell[1] * 1.2)
                if in_desert(px, py) and land.on_land(px, py) and rng.random() < 0.16:
                    dot(ink, px, py, rng.uniform(1.0, 1.4))
                    n_dot += 1
        # the border: a heavier 01 stipple rim, where the region meets other land
        for (x, y) in pts:
            for _ in range(6):
                a = rng.uniform(0, math.tau)
                px = x + math.cos(a) * dcell[0] * rng.uniform(0.7, 1.6)
                py = y + math.sin(a) * dcell[1] * rng.uniform(0.7, 1.6)
                if not in_desert(px, py):
                    if land.on_land(px, py):
                        dot(ink, px, py, rng.uniform(1.5, 2.3))
                        n_dot += 1
        for _ in range(6):
            x, y = pts[rng.randrange(len(pts))]
            dune(ink, x, y, rng.uniform(70, 110), hand)
            n_dune += 1
    print(f"   desert: {ms(t):.0f} ms ({n_des} regions, {n_dot} dots, {n_dune} dunes)")

    print("5. rivers: downhill from the high ground, no splitting")
    t = time.perf_counter()
    n_riv = 0
    for sx, sy in land.land_points(14, margin=140, min_elev=30, rng=rng, min_sep=120):
        pts = [(sx, sy)]
        x, y = sx, sy
        for _ in range(260):
            best, bp = land.elevation(x, y), None
            for k in range(16):
                a = rng.uniform(0, math.tau)
                dstep = rng.uniform(24.0, 40.0)
                nx_ = x + math.cos(a) * dstep
                ny_ = y + math.sin(a) * dstep
                if not (10 < nx_ < VW - 10 and 10 < ny_ < VH - 10):
                    continue
                if not land.on_land(nx_, ny_):
                    # reached the coast: let the river run into the water
                    pts.append((nx_, ny_))
                    best, bp = -1, (nx_, ny_)
                    break
                e = land.elevation(nx_, ny_)
                if e < best:
                    best, bp = e, (nx_, ny_)
            if bp is None:
                break
            pts.append(bp)
            x, y = bp
            if best <= 0:
                break
        if len(pts) < 8:
            continue
        # the big squiggle: shove the control points sideways
        squig = []
        for i, (x, y) in enumerate(pts):
            if i == 0:
                squig.append((x, y)); continue
            px, py = pts[i - 1]
            dx_, dy_ = x - px, y - py
            L = math.hypot(dx_, dy_) or 1.0
            o = rng.gauss(0, 11)
            squig.append((x - dy_ / L * o, y + dx_ / L * o))
        curve(ink, squig, PEN["02"], hand, n_sub=4, taper=True)
        # thicken the curves, taper the tail
        for i in range(1, len(squig) - 1):
            p0, p1, p2 = squig[i - 1], squig[i], squig[i + 1]
            a1 = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
            a2 = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
            if abs(a2 - a1) > 0.5 and rng.random() < 0.45:
                pen(ink, [p1, ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)],
                    PEN["03"], hand, taper=True)
        n_riv += 1
    print(f"   rivers: {ms(t):.0f} ms ({n_riv})")

    print("6. grass in the empty spaces")
    t = time.perf_counter()
    n_g = 0
    for p in land.land_points(150, margin=50, min_elev=4, rng=rng, min_sep=78):
        grass(ink, p[0], p[1], rng.uniform(22, 34), hand)
        n_g += 1
    print(f"   tufts: {ms(t):.0f} ms ({n_g})")

    t = time.perf_counter()
    paper = make_paper()
    paper.blit(pygame.transform.smoothscale(ink, (VW, VH)), (0, 0))
    print(f"7. paper + flatten: {ms(t):.0f} ms")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_proto2.png")
    pygame.image.save(paper, out)
    print(f"\nTOTAL {ms(t_all):.0f} ms -> {out}")


if __name__ == "__main__":
    main()
