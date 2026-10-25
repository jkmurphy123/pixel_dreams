# P0 spike for the arcane-lab design (designs/ARCANE_LAB_DESIGN.md §11).
#
# Throwaway. No project imports: it prototypes the four mechanisms the design leans on
# (additive glow cache, deterministic flicker, procedural glyphs, particle pool) and measures
# what they cost at the wall's real 1080x1920, so the phase-1 classes are written against
# numbers instead of hope.
#
# Run:  SDL_VIDEODRIVER=dummy .venv/bin/python arcane_spike.py

import math
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

W, H = 1080, 1920
OUT = os.path.dirname(os.path.abspath(__file__))

CANDLE = (255, 176, 84)
RUNE = (150, 124, 255)
ORB = (120, 226, 220)

# ---------------------------------------------------------------- deterministic flicker


def _hash01(n: float) -> float:
    """Deterministic 0..1 from a number — no RNG state, no allocation."""
    v = math.sin(n * 12.9898) * 43758.5453
    return v - math.floor(v)


def flicker(t: float, phase: float, rate: float = 1.0, depth: float = 0.22) -> float:
    """
    Brightness multiplier around 1.0: three incommensurate sines for the lazy flutter, plus a
    sample-and-hold gutter (a dip held for ~1/12 s) so it reads as fire and not as a sine wave.
    Deterministic in t and phase, which is what makes a screenshot reproducible.
    """
    s = (math.sin(t * 6.1 * rate + phase * 3.1) * 0.5
         + math.sin(t * 9.7 * rate + phase * 7.3) * 0.3
         + math.sin(t * 2.3 * rate + phase * 11.9) * 0.2)
    v = 1.0 - depth * (0.5 + 0.5 * s)
    step = int((t * 12.0) + phase * 5.0)
    if _hash01(step) < 0.14:
        v *= 0.74
    return v


# ---------------------------------------------------------------- additive glow cache

_GLOW: dict = {}
_GLOW_MAX = 256


def glow(color, radius: int) -> pygame.Surface:
    """
    Halo with the falloff PRE-MULTIPLIED into RGB and alpha fixed at 255, so it can be
    blitted with BLEND_RGB_ADD — a real additive light, and no per-frame alpha work.

    Cached by (colour, radius bucket), with the COLOUR QUANTISED to steps of 32 per channel.
    That quantisation is load-bearing: a particle pool that dims each mote individually produces a
    new exact colour per mote, which made every call a cache miss and cost 493 ms/frame for 120
    embers (measured in this spike). Quantised, the same pool costs ~2 ms.
    """
    bucket = max(4, int(radius / 8) * 8)
    q = tuple(min(255, 32 * round(c / 32)) for c in color)
    key = (q, bucket)
    surf = _GLOW.get(key)
    if surf is not None:
        return surf
    n = 64
    master = pygame.Surface((n, n), pygame.SRCALPHA)
    master.fill((0, 0, 0, 0))
    c = n / 2.0
    for y in range(n):
        for x in range(n):
            d = math.hypot(x + 0.5 - c, y + 0.5 - c) / c
            if d >= 1.0:
                continue
            a = 0.42 * (1.0 - d) ** 2.6      # capped peak: additive halos stack, so 1.0 clips
            master.set_at((x, y), (int(color[0] * a), int(color[1] * a), int(color[2] * a), 255))
    big = pygame.transform.smoothscale(master, (bucket * 2, bucket * 2))
    if len(_GLOW) >= _GLOW_MAX:
        _GLOW.pop(next(iter(_GLOW)))
    _GLOW[key] = big
    return big


def add_glow(surface, color, center, radius: float, level: float = 1.0):
    """Additive light. `level` scales by picking a dimmer bucket, never by building a surface."""
    if level <= 0.02 or radius < 2:
        return
    dim = tuple(int(c * min(1.0, level)) for c in color)
    surf = glow(dim, int(radius))
    surface.blit(surf, (int(center[0] - surf.get_width() / 2),
                        int(center[1] - surf.get_height() / 2)),
                 special_flags=pygame.BLEND_RGB_ADD)



_SPHERE: dict = {}


def sphere(color, diameter: int) -> pygame.Surface:
    """
    A glowing sphere as an alpha-blended BODY: radial limb darkening, a specular highlight, an
    antialiased edge. Additive is wrong for this — blitting the body additively clipped it to a
    white disc with a hard ring around it (measured in the first scene render).
    """
    bucket = max(8, int(diameter / 8) * 8)
    q = tuple(min(255, 32 * round(c / 32)) for c in color)
    key = (q, bucket)
    surf = _SPHERE.get(key)
    if surf is not None:
        return surf
    n = 96
    master = pygame.Surface((n, n), pygame.SRCALPHA)
    master.fill((0, 0, 0, 0))
    c = n / 2.0
    for y in range(n):
        for x in range(n):
            dx = (x + 0.5 - c) / c
            dy = (y + 0.5 - c) / c
            dist = math.hypot(dx, dy)
            if dist >= 1.0:
                continue
            edge = min(1.0, (1.0 - dist) / 0.06)          # antialiased limb
            shade = 0.30 + 0.70 * (1.0 - dist) ** 0.55    # limb darkening
            spec = max(0.0, 1.0 - math.hypot(dx + 0.34, dy + 0.38) / 0.52) ** 2.2
            r = min(255, int(color[0] * shade + 255 * spec * 0.85))
            g = min(255, int(color[1] * shade + 255 * spec * 0.85))
            b = min(255, int(color[2] * shade + 255 * spec * 0.85))
            master.set_at((x, y), (r, g, b, int(255 * edge)))
    big = pygame.transform.smoothscale(master, (bucket, bucket))
    if len(_SPHERE) >= 96:
        _SPHERE.pop(next(iter(_SPHERE)))
    _SPHERE[key] = big
    return big

# ---------------------------------------------------------------- glyphs

# Rune polylines in unit space. Angular strokes only: they survive a 20 px render and read as
# writing rather than as decoration, and no font is involved.
GLYPHS = [
    [[(0.30, 0.10), (0.30, 0.90)], [(0.30, 0.10), (0.75, 0.45), (0.30, 0.80)]],
    [[(0.25, 0.10), (0.25, 0.90)], [(0.25, 0.10), (0.75, 0.10)], [(0.25, 0.50), (0.70, 0.85)]],
    [[(0.25, 0.90), (0.25, 0.30), (0.60, 0.10), (0.80, 0.45)], [(0.60, 0.10), (0.60, 0.60)]],
    [[(0.20, 0.20), (0.80, 0.20)], [(0.50, 0.20), (0.50, 0.90)], [(0.34, 0.62), (0.66, 0.62)]],
    [[(0.20, 0.10), (0.50, 0.50), (0.80, 0.10)], [(0.50, 0.50), (0.50, 0.90)]],
    [[(0.30, 0.10), (0.70, 0.90)], [(0.70, 0.10), (0.30, 0.90)]],
    [[(0.50, 0.10), (0.50, 0.90)], [(0.50, 0.10), (0.80, 0.35)], [(0.50, 0.45), (0.22, 0.20)]],
    [[(0.25, 0.90), (0.25, 0.35), (0.50, 0.10), (0.75, 0.35), (0.75, 0.90)], [(0.25, 0.62), (0.75, 0.62)]],
    [[(0.20, 0.70), (0.50, 0.10), (0.80, 0.70)], [(0.35, 0.48), (0.65, 0.48)]],
    [[(0.30, 0.10), (0.30, 0.55), (0.70, 0.30)], [(0.30, 0.55), (0.70, 0.90)]],
    [[(0.20, 0.50), (0.50, 0.10), (0.80, 0.50), (0.50, 0.90), (0.20, 0.50)], [(0.35, 0.50), (0.65, 0.50)]],
    [[(0.25, 0.20), (0.75, 0.20), (0.25, 0.80), (0.75, 0.80)]],
]


def draw_glyph(surface, glyph, center, size: float, angle: float, color, width: int):
    """One rune: rotate its unit-space polylines about `center` and stroke them."""
    ca, sa = math.cos(angle), math.sin(angle)
    for stroke in glyph:
        pts = []
        for ux, uy in stroke:
            lx = (ux - 0.5) * size
            ly = (uy - 0.5) * size
            pts.append((center[0] + lx * ca - ly * sa, center[1] + lx * sa + ly * ca))
        if len(pts) > 1:
            pygame.draw.lines(surface, color, False, pts, width)


# ---------------------------------------------------------------- the three shapes


_SCRATCH: dict = {}


def _scratch(w: int, h: int) -> pygame.Surface:
    """One reusable scratch layer per rect SIZE — allocated on first use, cleared per frame."""
    key = (int(w), int(h))
    surf = _SCRATCH.get(key)
    if surf is None:
        surf = pygame.Surface(key, pygame.SRCALPHA)
        _SCRATCH[key] = surf
    return surf


def draw_flame(surface, rect, t, phase, color=CANDLE, count=1, lean=0.35, glow_frac=1.1):
    """
    A guttering teardrop. Three nested profiles (smoky outer, warm body, white-hot core) on a
    scratch layer the size of the rect, plus an additive halo underneath. Local coordinates in the
    scratch — an absolute-coordinate scratch blitted at (x, y) draws the flame at twice the offset
    (this spike did exactly that before it was fixed).
    """
    x, y, w, h = rect
    scratch = _scratch(w, h)
    scratch.fill((0, 0, 0, 0))
    for i in range(count):
        fx = w * (i + 0.5) / count
        lv = flicker(t, phase + i * 2.7)
        fh = h * 0.62 * lv
        fw = min(w / count * 0.55, fh * 0.42)
        sway = math.sin(t * 2.6 + phase + i * 1.9) * lean * fw * 0.5
        base_y = h * 0.92
        add_glow(surface, color, (x + fx, y + h * 0.55), min(w, h) * 0.55 * glow_frac * lv, 0.5 * lv)

        for scale, col, alpha in ((1.0, (255, 120, 40), 70),
                                  (0.66, (255, 178, 90), 150),
                                  (0.36, (255, 244, 220), 220)):
            ww = fw * scale
            hh = fh * scale
            left, right = [], []
            steps = 7
            for k in range(steps + 1):
                u = k / steps
                half = ww * (math.sin(math.pi * (0.10 + 0.85 * u)) ** 0.85) * (1.0 - u) ** 0.35
                yy = base_y - hh * u
                xx = fx + sway * u
                left.append((xx - half, yy))
                right.append((xx + half, yy))
            pts = left + right[::-1]
            pygame.draw.polygon(scratch, (*col, alpha), pts)
    surface.blit(scratch, (x, y))


def draw_orb(surface, rect, t, phase, color=ORB, drift=0.18, glow_frac=1.35):
    """A floating sphere: additive halo behind an alpha-blended body with limb darkening."""
    x, y, w, h = rect
    d = min(w, h) * 0.5
    cx = x + w / 2 + math.sin(t * 0.55 + phase) * drift * (w / 2 - d / 2)
    cy = y + h / 2 + math.sin(t * 0.37 + phase * 2.1) * drift * (h / 2 - d / 2)
    add_glow(surface, color, (cx, cy), d * glow_frac, 0.55)
    body = sphere(color, int(d * 2))
    surface.blit(body, (int(cx - d), int(cy - d)))


def draw_rune_ring(surface, rect, t, rings=((0.92, 18), (0.68, 12), (0.44, 8)),
                   color=RUNE, spin=14.0, pulse=1.0):
    """Counter-rotating glyph rings with a travelling brightness wave."""
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    r_max = min(w, h) / 2
    add_glow(surface, color, (cx, cy), r_max * 1.05, 0.20 * pulse)
    for ring_i, (frac, n) in enumerate(rings):
        r = r_max * frac
        speed = math.radians(spin) * (1 if ring_i % 2 == 0 else -1) * (1.0 + 0.35 * ring_i)
        size = r * 0.20
        pygame.draw.circle(surface, tuple(int(c * 0.16) for c in color),
                           (int(cx), int(cy)), int(r), 1)
        for k in range(n):
            ang = math.tau * k / n + t * speed
            bright = 0.42 + 0.58 * max(0.0, math.sin(math.tau * (k / n * 2.0 - t * 0.30)))
            col = tuple(int(c * bright) for c in color)
            center = (cx + math.cos(ang) * r, cy + math.sin(ang) * r)
            draw_glyph(surface, GLYPHS[(k * 5 + ring_i * 3) % len(GLYPHS)], center, size,
                       ang + math.pi / 2, col, max(1, int(size * 0.14)))


def draw_rune_line(surface, rect, t, count=10, color=RUNE, speed=0.5, orient="h"):
    """A row of runes lit by a travelling flare — an inscription being read."""
    x, y, w, h = rect
    span = w if orient == "h" else h
    size = min(span / count * 0.8, (h if orient == "h" else w) * 0.8)
    for k in range(count):
        u = (k + 0.5) / count
        cx = x + span * u if orient == "h" else x + w / 2
        cy = y + h / 2 if orient == "h" else y + span * u
        phase = (u * 2.0 - t * speed) % 1.0
        bright = 0.30 + 0.70 * max(0.0, 1.0 - abs(phase - 0.5) * 3.0)
        col = tuple(int(c * bright) for c in color)
        draw_glyph(surface, GLYPHS[k % len(GLYPHS)], (cx, cy), size,
                   math.pi / 2 if orient == "v" else 0.0, col, max(1, int(size * 0.13)))


class Embers:
    """Fixed pool, recycled in place: no allocation after construction."""

    def __init__(self, rect, n=120, color=ORB, seed=1.0):
        self.rect = rect
        self.color = color
        self.n = n
        self.motes = [[0.0] * 7 for _ in range(n)]
        for i in range(n):
            self._respawn(self.motes[i], seed + i * 0.37, first=True)

    def _respawn(self, m, phase, first=False):
        x, y, w, h = self.rect
        m[0] = phase * 7919.0 % w                     # base x
        m[1] = (0.0 if first else 1.0)                # normalised height, 0 = bottom
        m[2] = 22.0 + (phase * 53.0 % 38.0)           # rise px/s
        m[3] = 0.6 + phase * 1.9 % 1.6                # sway px
        m[4] = phase * math.tau                       # sway phase
        m[5] = 1.5 + (phase * 31.0 % 2.6)             # radius
        m[6] = phase * 17.0                           # twinkle phase

    def step(self, dt, t):
        x, y, w, h = self.rect
        for m in self.motes:
            m[1] += m[2] * dt / h
            if m[1] > 1.0:
                m[1] -= 1.0
                m[0] = (m[0] * 1.618 + 13.0) % w
                m[4] += 1.7

    def draw(self, surface, t):
        x, y, w, h = self.rect
        for m in self.motes:
            px = x + (m[0] + math.sin(t * 0.9 + m[4]) * m[3]) % w
            py = y + h - m[1] * h
            life = math.sin(math.pi * min(1.0, max(0.0, m[1]))) * 0.85
            tw = 0.75 + 0.25 * math.sin(t * 3.1 + m[6])
            add_glow(surface, self.color, (px, py), m[5] * 3.2, max(0.04, life * tw * 0.7))


# ---------------------------------------------------------------- the two renders


def contact_sheet(surface):
    surface.fill((14, 12, 18))
    font = pygame.font.Font(None, 30)
    small = pygame.font.Font(None, 22)

    def label(text, x, y):
        surface.blit(small.render(text, True, (170, 160, 180)), (x, y))

    surface.blit(font.render("arcane P0 — shapes at the sizes the layout will use", True,
                             (230, 220, 240)), (24, 18))

    # flames: a single 70 px candle, a 3-candle rack, a 34 px candle far away
    surface.blit(small.render("candle_flame 70px / count 3 / 34px distant", True,
                              (170, 160, 180)), (24, 60))
    for rect, count in (((30, 90, 70, 120), 1), ((130, 90, 210, 120), 3), ((380, 130, 34, 60), 1)):
        draw_flame(surface, rect, 3.2, 1.1, count=count)
    pygame.draw.rect(surface, (60, 55, 70), (30, 90, 70, 120), 1)
    pygame.draw.rect(surface, (60, 55, 70), (130, 90, 210, 120), 1)
    pygame.draw.rect(surface, (60, 55, 70), (380, 130, 34, 60), 1)

    # orbs
    surface.blit(small.render("floating_orb 60 / 120 / 240 px", True, (170, 160, 180)), (460, 60))
    for i, d in enumerate((60, 120, 240)):
        draw_orb(surface, (450 + i * 200, 100, d, d), 3.2, 0.7 + i)

    # rune ring at two sizes, and a rune line
    surface.blit(small.render("rune_circle 180 / 300 px", True, (170, 160, 180)), (24, 250))
    draw_rune_ring(surface, (30, 280, 180, 180), 3.2)
    draw_rune_ring(surface, (240, 250, 300, 300), 3.2)
    surface.blit(small.render("rune_line horizontal / vertical", True, (170, 160, 180)), (580, 250))
    draw_rune_line(surface, (580, 290, 420, 60), 3.2, count=9)
    draw_rune_line(surface, (1020, 270, 40, 300), 3.2, count=7, orient="v")

    # glyph legibility strip at the sizes used above
    surface.blit(small.render("glyphs at 14 / 22 / 34 / 60 px", True, (170, 160, 180)), (24, 600))
    for row, size in enumerate((14, 22, 34, 60)):
        for g in range(len(GLYPHS)):
            draw_glyph(surface, GLYPHS[g], (60 + g * (size * 1.3), 660 + row * 80), size, 0.0,
                       RUNE, max(1, int(size * 0.12)))
    label(f"{len(GLYPHS)} glyphs", 24, 980)


def main():
    pygame.init()
    pygame.display.set_mode((W, H))
    sheet = pygame.Surface((W, 1040))
    contact_sheet(sheet)
    sheet_path = os.path.join(OUT, "arcane_p0_sheet.png")
    pygame.image.save(sheet, sheet_path)

    # ---- the scene test: the real canvas size, a plausible overlay set
    canvas = pygame.Surface((W, H))
    canvas.fill((20, 16, 24))
    frame = pygame.Surface((W, H))
    embers = Embers((0, 0, W, H), n=90, color=(255, 170, 110), seed=2.0)
    flames = [((60 + i * 120, 260, 90, 150), 2) for i in range(8)]
    ring_rect = (330, 1000, 420, 420)

    def one_frame(t):
        frame.blit(canvas, (0, 0))
        embers.draw(frame, t)
        for rect, count in flames:
            draw_flame(frame, rect, t, rect[0] * 0.01, count=count)
        draw_orb(frame, (700, 700, 240, 240), t, 0.4)
        draw_rune_ring(frame, ring_rect, t)
        draw_rune_line(frame, (120, 1650, 840, 70), t, count=12)
        add_glow(frame, CANDLE, (540, 950), 260, 0.16)

    # warm up (caches, glyph surfaces)
    for i in range(10):
        embers.step(1 / 60, i / 60)
        one_frame(i / 60)

    N = 120
    t0 = time.perf_counter()
    t = 0.0
    for _ in range(N):
        t += 1 / 60
        embers.step(1 / 60, t)
        frame.blit(canvas, (0, 0))
    copy_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    t = 0.0
    for _ in range(N):
        t += 1 / 60
        embers.step(1 / 60, t)
        one_frame(t)
    scene_ms = (time.perf_counter() - t0) / N * 1000
    # Snapshot HERE, before the per-piece benchmarks below: each of them draws 120 times on
    # `frame`, and their additive halos accumulated into a white disc in an earlier version of
    # this spike. Any acceptance screenshot has the same trap.
    scene_img = frame.copy()

    t0 = time.perf_counter()
    for _ in range(N):
        embers.draw(frame, 1.0)
    ember_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    for _ in range(N):
        draw_rune_ring(frame, ring_rect, 1.0)
    ring_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    for _ in range(N):
        for rect, count in flames:
            draw_flame(frame, rect, 1.0, rect[0] * 0.01, count=count)
    flame_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    for _ in range(N):
        draw_orb(frame, (700, 700, 240, 240), 1.0, 0.4)
    orb_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    for _ in range(N):
        draw_rune_line(frame, (120, 1650, 840, 70), 1.0, count=12)
    line_ms = (time.perf_counter() - t0) / N * 1000

    # one big ambient halo: this is the knob that decides whether a "light spill" is affordable
    t0 = time.perf_counter()
    for _ in range(N):
        add_glow(frame, CANDLE, (540, 950), 260, 0.16)
    halo_ms = (time.perf_counter() - t0) / N * 1000

    t0 = time.perf_counter()
    for _ in range(N):
        add_glow(frame, CANDLE, (540, 950), 120, 0.30)
    halo_small_ms = (time.perf_counter() - t0) / N * 1000

    heavy = Embers((0, 0, W, H), n=240, seed=5.0)
    for _ in range(10):
        heavy.draw(frame, 1.0)
    t0 = time.perf_counter()
    for _ in range(N):
        heavy.draw(frame, 1.0)
    ember240_ms = (time.perf_counter() - t0) / N * 1000

    scene_path = os.path.join(OUT, "arcane_p0_scene.png")
    pygame.image.save(scene_img, scene_path)

    print(f"glow cache entries: {len(_GLOW)}")
    print(f"surface copy only        : {copy_ms:.2f} ms/frame")
    print(f"embers 120 (additive)    : {ember_ms:.2f} ms/frame")
    print(f"embers 240 (additive)    : {ember240_ms:.2f} ms/frame")
    print(f"8 flames x2 (halo+3 poly): {flame_ms:.2f} ms/frame")
    print(f"rune ring 3x18           : {ring_ms:.2f} ms/frame")
    print(f"rune line 12 glyphs      : {line_ms:.2f} ms/frame")
    print(f"orb 240 px               : {orb_ms:.2f} ms/frame")
    print(f"halo r=120 (additive)    : {halo_small_ms:.2f} ms/frame")
    print(f"halo r=260 (additive)    : {halo_ms:.2f} ms/frame")
    print(f"FULL SCENE (copy+all)    : {scene_ms:.2f} ms/frame  -> {1000/max(scene_ms,0.001):.0f} fps ceiling")
    print(f"sheet: {sheet_path}")
    print(f"scene: {scene_path}")


if __name__ == "__main__":
    main()
