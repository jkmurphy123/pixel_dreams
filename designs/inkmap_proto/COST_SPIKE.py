#!/usr/bin/env python3
"""Off-display spike: is a pen-and-ink fantasy map affordable on this host?

Measures the risky mechanisms of a hand-drawn map mode at supersampled
1080x1920 (the kiosk panel's real resolution, rotated):
  A. continent outline from "grains of rice"  (bytearray stamp + marching squares)
  B. pen polyline drawing with jitter + variable width
  C. stipple dots (ink-blob sprite blits)
  D. coast hatching (offset loops + perpendicular hashes)
  E. 2x supersample -> 1080x1920 downscale
  F. per-frame blit cost + surface memory

Control measurement: an empty loop and a plain fill, so a "fast" number
cannot be an artefact of the loop overhead.
"""
import os
import time
import math
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402
import pygame.gfxdraw as gfx  # noqa: E402

pygame.init()
pygame.font.init()
# dummy driver still needs a video mode for .convert() / blitting
pygame.display.set_mode((1080, 1920))
print(f"pygame {pygame.version.ver}  python {sys.version.split()[0]}")

SS = 2                      # supersample factor
W, H = 1080 * SS, 1920 * SS  # 2160 x 3840
print(f"target surface {W}x{H} ({W*H/1e6:.1f} Mpx, {W*H*4/1e6:.0f} MB raw)")

# fonts/timers -------------------------------------------------------------
def ms(t0):
    return (time.perf_counter() - t0) * 1000.0

def report(name, t0, extra=""):
    print(f"  {name:<46} {ms(t0):9.1f} ms  {extra}")

# ── control: loop + fill overhead ────────────────────────────────────────
N = 20000
t0 = time.perf_counter()
acc = 0
for i in range(N):
    acc += i
report(f"CONTROL: empty loop x{N}", t0, f"acc={acc}")

surf = pygame.Surface((W, H)).convert()
t0 = time.perf_counter()
surf.fill((240, 230, 205))
report("CONTROL: full-surface fill", t0)

# ── A: continent from grains of rice ─────────────────────────────────────
# Grid resolution for the scalar field (one grid cell = GRID_PX device px).
GRID_PX = 8
GW, GH = W // GRID_PX, H // GRID_PX
print(f"\nA. rice-clump continents: field {GW}x{GH} cells ({GW*GH/1000:.0f}k)")

def stamp_grains(rng, gw, gh, clumps=4, grains_per_clump=(90, 160), reach=26):
    """Deposit overlapping rice-grain ellipses into a bytearray mask (1 = land)."""
    mask = bytearray(gw * gh)
    grains = []
    for _ in range(clumps):
        cx = rng.uniform(gw * 0.15, gw * 0.85)
        cy = rng.uniform(gh * 0.15, gh * 0.85)
        n = rng.randint(*grains_per_clump)
        for _ in range(n):
            # grains scatter around the clump centre: tight core, loose skirt
            a = rng.uniform(0, math.tau)
            r = abs(rng.gauss(0, reach * 0.5))
            gx = cx + math.cos(a) * r
            gy = cy + math.sin(a) * r * 0.6
            rx = rng.uniform(3.5, 6.0)      # grain half-length (cells)
            ry = rx * rng.uniform(0.35, 0.7)  # rice is a flat ellipse
            th = rng.uniform(0, math.pi)
            grains.append((gx, gy, rx, ry, th))
            ca, sa = math.cos(th), math.sin(th)
            x0, x1 = int(gx - rx - 1), int(gx + rx + 2)
            y0, y1 = int(gy - rx - 1), int(gy + rx + 2)
            for y in range(max(0, y0), min(gh, y1)):
                dy = y - gy
                row = y * gw
                for x in range(max(0, x0), min(gw, x1)):
                    dx = x - gx
                    u = dx * ca + dy * sa
                    v = -dx * sa + dy * ca
                    if (u / rx) ** 2 + (v / ry) ** 2 <= 1.0:
                        mask[row + x] = 1
    return mask, grains

rng = random.Random(1234)
t0 = time.perf_counter()
mask, grains = stamp_grains(rng, GW, GH)
n_land = sum(mask)
report("A1 rice stamping (bytearray)", t0, f"{len(grains)} grains, {n_land} land cells")

def marching_squares(mask, gw, gh, level_iso=True):
    """Extract closed contours from a 0/1 mask, midpoint-rule, as polylines."""
    segs = []
    for y in range(gh - 1):
        row = y * gw
        nrow = row + gw
        # hoist per-row locals; skip the vast majority of cells cheaply
        for x in range(gw - 1):
            a = mask[row + x]
            b = mask[row + x + 1]
            c = mask[nrow + x + 1]
            d = mask[nrow + x]
            if a == b == c == d:
                continue
            # midpoint crossings on the four edges
            top = (x + 0.5, y)
            right = (x + 1, y + 0.5)
            bot = (x + 0.5, y + 1)
            left = (x, y + 0.5)
            idx = a | (b << 1) | (c << 2) | (d << 3)
            if idx in (1, 14):   segs.append((left, top))
            elif idx in (2, 13): segs.append((top, right))
            elif idx in (3, 12): segs.append((left, right))
            elif idx in (4, 11): segs.append((right, bot))
            elif idx in (6, 9):  segs.append((top, bot))
            elif idx in (7, 8):  segs.append((left, bot))
            elif idx in (5, 10):
                segs.append((left, top)); segs.append((right, bot))
    return segs

t0 = time.perf_counter()
segs = marching_squares(mask, GW, GH)
report("A2 marching squares", t0, f"{len(segs)} segments")

def chain(segs):
    """Chain unordered segments into polyline loops."""
    from collections import defaultdict
    bucket = defaultdict(list)
    for i, (p, q) in enumerate(segs):
        bucket[p].append(i)
        bucket[q].append(i)
    used = [False] * len(segs)
    loops = []
    for start in range(len(segs)):
        if used[start]:
            continue
        p, q = segs[start]
        used[start] = True
        loop = [p, q]
        cur = q
        while True:
            nxt = None
            for i in bucket[cur]:
                if not used[i]:
                    nxt = i
                    break
            if nxt is None:
                break
            used[nxt] = True
            a, b = segs[nxt]
            cur = b if a == cur else a
            loop.append(cur)
            if cur == loop[0]:
                break
        if len(loop) > 4:
            loops.append(loop)
    return loops

t0 = time.perf_counter()
loops = chain(segs)
report("A3 chaining into loops", t0, f"{len(loops)} loops, "
       f"{sum(len(l) for l in loops)} verts, largest {max(len(l) for l in loops)}")

# simplify: keep every k-th vertex (Douglas-Peucker is a later refinement)
def resample(loop, step):
    out = []
    acc = 0.0
    for i in range(len(loop) - 1):
        x0, y0 = loop[i]
        x1, y1 = loop[i + 1]
        d = math.hypot(x1 - x0, y1 - y0)
        if d == 0:
            continue
        acc += d
        if acc >= step:
            out.append((x1 * GRID_PX, y1 * GRID_PX))
            acc = 0.0
    return out

t0 = time.perf_counter()
paths = [resample(l, 4.0) for l in loops]
paths = [p for p in paths if len(p) > 8]
report("A4 resample to device px", t0, f"{len(paths)} paths, "
       f"{sum(len(p) for p in paths)} points")

# ── B: pen polyline with jitter + variable width ─────────────────────────
def pen_path(surface, pts, color, base_w, rng, jitter=1.1, tremor=0.22):
    """Draw a polyline as a hand-drawn pen stroke: perpendicular tremor +
    per-segment width wobble, as a tapered quad per segment."""
    if len(pts) < 2:
        return 0
    # jitter the points (hand tremor), smoothed so it wanders rather than buzzes
    j = []
    drift = 0.0
    for i, (x, y) in enumerate(pts):
        drift = drift * 0.72 + rng.gauss(0, 1.0) * 0.55
        if i == 0:
            dx, dy = pts[1][0] - x, pts[1][1] - y
        else:
            dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        o = drift * jitter + rng.gauss(0, tremor)
        j.append((x + nx * o, y + ny * o))
    n_seg = 0
    for i in range(len(j) - 1):
        x0, y0 = j[i]
        x1, y1 = j[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 0.01:
            continue
        w = base_w * (1.0 + 0.28 * math.sin(i * 0.7) + rng.gauss(0, 0.07))
        w = max(0.6, w) * 0.5
        nx, ny = -dy / L * w, dx / L * w
        surface.fill((0, 0, 0, 0), (int(x0) - 4, int(y0) - 4, 9, 9))
        pygame.draw.polygon(surface, color, [
            (x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])
        n_seg += 1
    return n_seg

ink = pygame.Surface((W, H), pygame.SRCALPHA)
INK = (38, 30, 24, 255)

# coast: one long path
coast = [p for p in paths if len(p) > 200]
if not coast:
    coast = [paths[0]]
rng = random.Random(7)
t0 = time.perf_counter()
total_seg = 0
for p in coast[:6]:
    total_seg += pen_path(ink, p, INK, 4.6, rng)   # ~05 pen at SS2
report("B1 pen stroke, long coast paths", t0, f"{total_seg} quad segments")

# control: same loop with a plain draw.line
rng = random.Random(8)
t0 = time.perf_counter()
c2 = 0
for p in coast[:6]:
    for i in range(len(p) - 1):
        pygame.draw.line(ink, INK, p[i], p[i + 1], 4)
        c2 += 1
report(f"B2 CONTROL: plain draw.line x{c2}", t0)

# ── C: stipple dots via a pre-rendered ink blob ─────────────────────────
DOT = pygame.Surface((5, 5), pygame.SRCALPHA)
pygame.draw.circle(DOT, (32, 26, 20, 255), (2, 2), 2)
NDOT = 12000
rng = random.Random(9)
t0 = time.perf_counter()
for _ in range(NDOT):
    ink.blit(DOT, (rng.randrange(W), rng.randrange(H)), special_flags=pygame.BLEND_RGBA_MAX)
report(f"C1 stipple blit x{NDOT}", t0)

t0 = time.perf_counter()
for _ in range(NDOT):
    pygame.draw.circle(ink, INK, (rng.randrange(W), rng.randrange(H)), 2)
report(f"C2 CONTROL: draw.circle x{NDOT}", t0)

# ── D: coast hatching (offset loop + perpendicular hashes) ──────────────
def offset_loop(pts, d):
    """Crude inward/outward normal offset of a closed polyline."""
    out = []
    for i, (x, y) in enumerate(pts):
        px, py = pts[i - 1]
        nx_, ny_ = pts[(i + 1) % len(pts)]
        dx, dy = nx_ - px, ny_ - py
        L = math.hypot(dx, dy) or 1.0
        out.append((x - dy / L * d, y + dx / L * d))
    return out

base = coast[0]
rng = random.Random(11)
t0 = time.perf_counter()
hcount = 0
for k, dist in enumerate((14.0, 22.0, 30.0)):
    ring = offset_loop(base, dist)
    hcount += len(ring)
    # hash marks perpendicular to the ring, alternating hash/dot/hash-dot
    for i in range(0, len(ring) - 1, 2):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        ln = rng.uniform(9, 19)
        pygame.draw.line(ink, INK, (x0, y0), (x0 + nx * ln, y0 + ny * ln), 2)
report("D1 coast hatching, 3 offset rings", t0, f"{hcount} ring verts")

# ── E: the stroke budget that a full map implies ────────────────────────
print("\nE. projected full-map stroke budget (measured per-op costs applied)")
def timed(op, n):
    t = time.perf_counter()
    for _ in range(n):
        op()
    return ms(t)

dummy_line = lambda: pygame.draw.line(ink, INK, (100, 100), (140, 160), 2)
dummy_quad = lambda: pygame.draw.polygon(ink, INK, [(100, 100), (140, 160), (150, 170), (110, 110)])
dummy_dot = lambda: ink.blit(DOT, (100, 100), special_flags=pygame.BLEND_RGBA_MAX)
per_line = timed(dummy_line, 3000) / 3000
per_quad = timed(dummy_quad, 3000) / 3000
per_dot = timed(dummy_dot, 3000) / 3000
print(f"   per draw.line {per_line*1000:.2f} us | per tapered quad {per_quad*1000:.2f} us"
      f" | per stipple blit {per_dot*1000:.2f} us")
BUDGET = {"line": 20000, "quad": 12000, "dot": 14000}
est = BUDGET["line"] * per_line + BUDGET["quad"] * per_quad + BUDGET["dot"] * per_dot
print(f"   budget {BUDGET} -> {est/1000:.2f} s of drawing")

# ── F: supersample downscale + per-frame blit + memory ─────────────────
t0 = time.perf_counter()
small = pygame.transform.smoothscale(ink, (1080, 1920))
report("F1 smoothscale 2160x3840 -> 1080x1920", t0)

t0 = time.perf_counter()
small = pygame.transform.scale(ink, (1080, 1920))
report("F2 nearest scale (for comparison)", t0)

screen = pygame.Surface((1080, 1920)).convert()
t0 = time.perf_counter()
for _ in range(60):
    screen.blit(small, (0, 0))
report("F3 60 full-screen blits (1 s of frames)", t0,
       f"{(ms(t0)/60):.2f} ms/frame")

import ctypes  # noqa: E402
del small, screen
sf = ink.get_bytesize() * ink.get_width() * ink.get_height()
print(f"\nsurface bytes: supersampled SRCALPHA {sf/1e6:.1f} MB "
      f"(+1080x1920 final {1080*1920*4/1e6:.1f} MB)")

# ── G: gfxdraw anti-aliased quality check ──────────────────────────────
t0 = time.perf_counter()
for i in range(4000):
    gfx.aaline(ink, 200, 200 + i % 500, 900, 700 + i % 500, INK)
report("G1 gfxdraw.aaline x4000", t0)

t0 = time.perf_counter()
for i in range(2000):
    gfx.aaellipse(ink, 500, 500, 60 + i % 40, 30, INK)
report("G2 gfxdraw.aaellipse x2000", t0)

print("\ndone")
