"""Art-direction prototype for The Sleeping Dragon (SLOW_WORLDS_DESIGN.md 5.10).

This is a still-frame study, not the mode.  It draws the scene at the two
target aspect ratios -- the 1280x400 Pi strip and the 1080x1920 portrait wall
-- so the composition and palette can be reviewed before any mode, registry or
profile code is written.

The scene follows the card: a colossal dragon asleep on its hoard in a cavern;
one slow breath, a thin smoke plume, drifting embers, gold glints, and one eye
that opens for a few seconds every minute or two.  The still is the sleeping
pose; ``--eye-open`` renders the signature moment for comparison.

Everything is procedural: no assets, no network, no numpy/PIL.  One canonical
dragon is drawn at 1280x400 scale and transformed for the portrait wall, so
the anatomy is identical at both ratios.  Shapes are drawn 2x/3x and
smoothscaled down, then a half-resolution bloom, a vignette and crisp HUD text
are applied at the native size.

Run:
    ./.venv/bin/python designs/sleeping_dragon_proto/gen_dragon.py
    ./.venv/bin/python designs/sleeping_dragon_proto/gen_dragon.py --eye-open
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
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "sleeping_dragon")
SEED = 5107

RGB = tuple[int, int, int]


# ------------------------------------------------------------------ colour

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


class Palette:
    """Ember & Rust (design doc 4.1), the mode's default palette."""

    name = "ember"

    bg_top = (12, 7, 6)
    bg_bottom = (4, 2, 2)
    wall_high = (12, 7, 6)
    wall_low = (34, 18, 13)
    wall_line = (46, 24, 17)
    stone = (54, 29, 21)
    stone_dim = (28, 15, 11)
    cave_near = (7, 4, 3)
    cave_hi = (14, 8, 6)
    rock = (5, 3, 2)

    rust = (152, 66, 48)
    rust_dim = (84, 36, 27)
    ink = (233, 211, 180)
    gold = (201, 164, 92)
    gold_light = (242, 200, 121)
    gold_deep = (78, 50, 16)
    copper = (146, 78, 32)
    accent = (255, 122, 60)
    glow = (255, 208, 138)

    body = (10, 6, 5)
    body_hi = (17, 9, 7)
    body_low = (6, 3, 3)
    belly = (34, 16, 11)
    scale = (52, 26, 19)
    scale_hi = (96, 54, 32)

    horn = (64, 49, 36)
    horn_light = (156, 128, 94)
    horn_dark = (37, 29, 21)
    claw = (170, 145, 106)

    eye = (255, 168, 58)
    eye_deep = (146, 54, 10)
    pupil = (10, 4, 2)

    hud = (230, 211, 182)
    hud_dim = (152, 121, 92)
    hud_faint = (82, 59, 42)


P = Palette()

_glow_cache: dict[tuple, pygame.Surface] = {}
_haze_cache: dict[tuple, pygame.Surface] = {}


def glow_sprite(radius: int, color: RGB, power: float = 2.2) -> pygame.Surface:
    key = (radius, color, power)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached
    size = max(2, radius * 2)
    surf = pygame.Surface((size, size)).convert()
    surf.fill((0, 0, 0))
    for r in range(radius, 0, -1):
        f = (1.0 - r / radius) ** power
        pygame.draw.circle(surf, mul(color, f), (radius, radius), r)
    _glow_cache[key] = surf
    return surf


def haze_surface(color: RGB, max_alpha: int, power: float = 2.0,
                 res: int = 72) -> pygame.Surface:
    key = (color, max_alpha, power, res)
    cached = _haze_cache.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((res, res), pygame.SRCALPHA)
    half = res / 2.0
    for y in range(res):
        for x in range(res):
            d = math.hypot((x + 0.5 - half) / half, (y + 0.5 - half) / half)
            if d >= 1.0:
                continue
            a = int(max_alpha * (1.0 - d) ** power)
            if a > 0:
                surf.set_at((x, y), (color[0], color[1], color[2], a))
    _haze_cache[key] = surf
    return surf


# ------------------------------------------------------------------ curves

def cubic(p0, p1, p2, p3, n: int = 24):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = (u * u * u * p0[0] + 3 * u * u * t * p1[0]
             + 3 * u * t * t * p2[0] + t * t * t * p3[0])
        y = (u * u * u * p0[1] + 3 * u * u * t * p1[1]
             + 3 * u * t * t * p2[1] + t * t * t * p3[1])
        pts.append((x, y))
    return pts


def smooth(flat, n: int = 24, closed: bool = False):
    """Sample a flat [P0, C1, C2, P1, C3, C4, P2, ...] cubic chain."""
    rest = flat[1:]
    if len(rest) % 3 != 0:
        raise ValueError("curve control points must come in threes")
    pts = []
    start = flat[0]
    for index in range(0, len(rest), 3):
        p1, p2, p3 = rest[index], rest[index + 1], rest[index + 2]
        seg = cubic(start, p1, p2, p3, n)
        if pts:
            seg = seg[1:]
        pts.extend(seg)
        start = p3
    if closed and pts and pts[-1] != pts[0]:
        pts.append(pts[0])
    return pts


def resample(pts, per_segment: int = 8):
    """Linear resample of a polyline (used for scale rows and mouth seams)."""
    out = []
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        for j in range(per_segment):
            t = j / per_segment
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    out.append(pts[-1])
    return out


def taper_tube(center, radii):
    """A tapered tube profile and its upper edge, for a horn."""
    top, bottom = [], []
    n = len(center)
    for i, (x, y) in enumerate(center):
        if i == 0:
            dx, dy = center[1][0] - x, center[1][1] - y
        elif i == n - 1:
            dx, dy = x - center[-2][0], y - center[-2][1]
        else:
            dx = center[i+1][0] - center[i-1][0]
            dy = center[i+1][1] - center[i-1][1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        r = radii[i]
        top.append((x + nx * r, y + ny * r))
        bottom.append((x - nx * r, y - ny * r))
    return top + bottom[::-1], top


def transform_geo(value, scale: float, dx: float, dy: float):
    """Recursively translate every coordinate pair in a geometry structure."""
    if isinstance(value, tuple):
        if len(value) == 2 and all(isinstance(v, (int, float))
                                   for v in value):
            return (value[0] * scale + dx, value[1] * scale + dy)
        return tuple(transform_geo(v, scale, dx, dy) for v in value)
    if isinstance(value, list):
        return [transform_geo(v, scale, dx, dy) for v in value]
    if isinstance(value, dict):
        return {k: transform_geo(v, scale, dx, dy) for k, v in value.items()}
    return value


# ------------------------------------------------------------------ scene

class DragonScene:
    def __init__(self, size, layout: str, seed: int = SEED):
        self.W, self.H = size
        self.layout = layout
        self.portrait = layout in ("portrait", "portrait_close", "portrait_mid")
        self.close = layout == "portrait_close"
        self.ss = 2 if self.portrait else 3
        self.SW = self.W * self.ss
        self.SH = self.H * self.ss
        self.seed = seed
        self.rng = random.Random(seed * 131 + (71 if self.portrait else 0))
        self.time_s = 0.0
        self.eye_open = False
        self.eye_glow = 0.8
        self._coin_glints = []

        if self.close:
            self.dragon_scale = 2.0
            self.dragon_dx = -600.0
            self.dragon_dy = 850.0
        elif layout == "portrait_mid":
            self.dragon_scale = 1.55
            self.dragon_dx = -440.0
            self.dragon_dy = 900.0
        elif self.portrait:
            self.dragon_scale = 1.30
            self.dragon_dx = -340.0
            self.dragon_dy = 1000.0
        else:
            self.dragon_scale = 1.0
            self.dragon_dx = 0.0
            self.dragon_dy = 0.0

        self.floor_y = 330.0 if not self.portrait else 1465.0
        self.rock_y = 372.0 if not self.portrait else 1806.0
        self.margin = 20 if not self.portrait else 34

        self._build_fonts()
        self._build_background()
        self._build_hoard()
        self._build_embers()
        self._build_dust()
        self._build_finish()
        self.geo = self._transform_geometry(self._canonical_geometry())

    # ---------------------------------------------------------- primitives

    def P(self, x: float, y: float):
        return (int(round(x * self.ss)), int(round(y * self.ss)))

    def G(self, x: float, y: float):
        """Map a canonical dragon coordinate into the current layout."""
        if self.portrait:
            return (x * self.dragon_scale + self.dragon_dx,
                    y * self.dragon_scale + self.dragon_dy)
        return (x, y)

    def GP(self, pts):
        return [self.G(x, y) for x, y in pts]

    def S(self, value: float) -> int:
        return max(1, int(round(value * self.ss)))

    def poly(self, surface, pts, color):
        if len(pts) >= 3:
            pygame.draw.polygon(surface, color, [self.P(x, y) for x, y in pts])

    def stroke(self, surface, pts, color, width: float = 1.0,
               closed: bool = False):
        if len(pts) < 2:
            return
        pygame.draw.lines(surface, color, closed,
                          [self.P(x, y) for x, y in pts], self.S(width))

    def stroke_alpha(self, surface, pts, color, alpha: int, width: float = 1.0,
                     closed: bool = False):
        if len(pts) < 2 or alpha <= 0:
            return
        pygame.draw.lines(surface, (*color, min(255, int(alpha))), closed,
                          [self.P(x, y) for x, y in pts], self.S(width))

    def rim_path(self, layer, pts, color, width=1.5, glow=5.0, alpha=210,
                 power=1.1, floor=0.10):
        """A tapered, luminous edge: wide soft pass + narrow bright pass."""
        if len(pts) < 2:
            return
        n = len(pts)
        for i in range(n - 1):
            t = i / max(1, n - 2)
            f = floor + (1.0 - floor) * math.sin(math.pi * t) ** power
            a_glow = int(alpha * 0.22 * f)
            a_core = int(alpha * f)
            if a_glow > 0:
                self.stroke_alpha(layer, [pts[i], pts[i + 1]], color,
                                  a_glow, glow)
            if a_core > 0:
                self.stroke_alpha(layer, [pts[i], pts[i + 1]], color,
                                  a_core, width)

    def haze(self, surface, center, rx, ry, color, alpha, power=2.0):
        sprite = haze_surface(color, alpha, power)
        width = max(2, int(rx * 2 * self.ss))
        height = max(2, int(ry * 2 * self.ss))
        scaled = pygame.transform.smoothscale(sprite, (width, height))
        x, y = self.P(center[0] - rx, center[1] - ry)
        surface.blit(scaled, (x, y))

    def glow(self, surface, center, radius, color, power=2.2):
        sprite = glow_sprite(max(2, int(radius * self.ss)), color, power)
        x, y = self.P(center[0] - radius, center[1] - radius)
        surface.blit(sprite, (x, y), special_flags=pygame.BLEND_RGB_ADD)

    def add_line(self, surface, a, b, color, width=1.0):
        pygame.draw.line(surface, color, self.P(*a), self.P(*b), self.S(width))

    def glint(self, surface, center, size, color, intensity=1.0):
        x, y = center
        c = mul(color, intensity)
        if intensity > 0.25:
            self.glow(surface, (x, y), size * 2.4, mul(color, 0.55), 1.9)
        self.add_line(surface, (x - size, y), (x + size, y), c, 1.0)
        self.add_line(surface, (x, y - size * 0.72),
                      (x, y + size * 0.72), c, 1.0)

    # --------------------------------------------------------- dragon paths

    def _canonical_geometry(self):
        body = [
            (660, 250),
            (690, 212), (740, 194), (795, 190),
            (865, 186), (930, 198), (985, 228),
            (1035, 256), (1065, 298), (1058, 334),
            (1050, 355), (1010, 365), (950, 363),
            (860, 361), (770, 353), (700, 341),
            (640, 331), (612, 312), (602, 289),
            (596, 273), (604, 258), (620, 252),
            (635, 247), (650, 247), (660, 250),
        ]
        neck = [
            (395, 240),
            (430, 226), (500, 216), (565, 214),
            (620, 212), (655, 218), (675, 232),
            (680, 258), (668, 278), (640, 290),
            (600, 300), (540, 304), (485, 296),
            (440, 290), (410, 278), (395, 262),
            (390, 252), (390, 245), (395, 240),
        ]
        head = [
            (372, 238),
            (392, 216), (430, 208), (462, 213),
            (494, 218), (525, 225), (548, 235),
            (563, 241), (573, 248), (575, 255),
            (576, 261), (569, 266), (559, 269),
            (541, 273), (520, 276), (500, 278),
            (475, 283), (448, 286), (428, 285),
            (405, 284), (388, 276), (380, 265),
            (372, 255), (368, 246), (372, 238),
        ]
        jaw = [
            (568, 261),
            (558, 270), (538, 276), (515, 279),
            (490, 283), (463, 287), (440, 286),
            (452, 278), (478, 274), (503, 271),
            (528, 267), (550, 264), (568, 261),
        ]
        frill = [
            (410, 258),
            (380, 252), (350, 246), (338, 250),
            (358, 260), (352, 270), (378, 268),
            (398, 270), (410, 266), (410, 258),
        ]
        horn_main, horn_main_top = taper_tube(
            [(420, 214), (400, 200), (372, 192), (344, 196)],
            [18, 13, 7, 1.5])
        brow_horn, brow_horn_top = taper_tube(
            [(420, 214), (404, 196), (382, 178), (356, 170),
             (334, 176)],
            [16, 12, 8, 4, 1])
        wing = [
            (660, 232),
            (690, 185), (720, 150), (755, 126),
            (770, 118), (785, 122), (795, 132),
            (830, 155), (870, 178), (905, 205),
            (935, 235), (955, 265), (965, 292),
            (940, 302), (918, 286), (895, 298),
            (873, 280), (850, 292), (828, 274),
            (806, 258), (782, 268), (762, 252),
            (740, 242), (712, 240), (690, 235),
            (674, 234), (660, 232), (660, 232),
        ]
        wing_ribs = [
            [(780, 126), (850, 170), (920, 230), (965, 292)],
            [(780, 126), (825, 170), (865, 230), (895, 298)],
            [(780, 126), (800, 170), (815, 225), (828, 274)],
            [(780, 126), (775, 170), (768, 210), (762, 252)],
        ]
        foreleg = [
            (632, 278),
            (642, 306), (638, 326), (620, 340),
            (600, 352), (568, 355), (548, 348),
            (534, 342), (534, 332), (548, 326),
            (570, 318), (590, 306), (598, 290),
            (602, 282), (610, 278), (620, 276),
        ]
        haunch = [
            (926, 246), (962, 236), (998, 244), (1024, 268),
            (1030, 300), (1016, 330), (988, 344), (958, 340),
            (936, 318), (928, 288), (926, 246),
        ]
        hind_leg = [
            (944, 280), (982, 268), (1022, 280), (1042, 310),
            (1040, 340), (1024, 358), (994, 364), (966, 352),
            (950, 328), (944, 300),
        ]
        belly = [
            (642, 318), (690, 332), (750, 344), (820, 352),
            (890, 356), (950, 358), (1010, 354), (1030, 345),
            (1000, 360), (940, 366), (860, 364), (780, 356),
            (710, 344), (652, 330),
        ]
        tail, tail_top_edge = taper_tube(
            [(1044, 312), (1100, 326), (1130, 346), (1120, 366),
             (1050, 374), (970, 368), (900, 358), (850, 346),
             (820, 336)],
            [24, 22, 17, 12, 8, 5, 3, 2, 1])
        # the lower side of the same tube, for the warm rim
        tail_bottom_edge = []
        for i, (x, y) in enumerate(
                [(1044, 312), (1100, 326), (1130, 346), (1120, 366),
                 (1050, 374), (970, 368), (900, 358), (850, 346),
                 (820, 336)]):
            radii = [24, 22, 17, 12, 8, 5, 3, 2, 1]
            if i == 0:
                dx, dy = 1100 - x, 326 - y
            elif i == len(radii) - 1:
                dx, dy = x - 850, y - 346
            else:
                pts = [(1044, 312), (1100, 326), (1130, 346),
                       (1120, 366), (1050, 374), (970, 368),
                       (900, 358), (850, 346), (820, 336)]
                dx = pts[i+1][0] - pts[i-1][0]
                dy = pts[i+1][1] - pts[i-1][1]
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            r = radii[i]
            tail_bottom_edge.append((x - nx * r, y - ny * r))
        tail_ridge = [(1100, 330), (1080, 344), (1040, 354),
                      (990, 362), (940, 364), (890, 360),
                      (846, 352), (820, 340)]
        spikes = [
            ((452, 212), (466, 186), (486, 216)),
            ((488, 214), (502, 184), (524, 220)),
            ((528, 218), (542, 188), (564, 226)),
            ((570, 223), (584, 194), (606, 232)),
            ((614, 218), (630, 192), (650, 230)),
            ((656, 222), (674, 200), (690, 238)),
        ]
        chin_spikes = [
            ((430, 284), (414, 306), (446, 288)),
            ((456, 286), (444, 310), (470, 290)),
            ((482, 287), (474, 310), (496, 291)),
        ]
        claws = [
            [(548, 346), (512, 358), (544, 355)],
            [(562, 352), (534, 366), (561, 360)],
            [(576, 352), (558, 366), (578, 360)],
            [(990, 356), (964, 368), (988, 366)],
            [(1006, 360), (982, 372), (1004, 370)],
            [(1022, 358), (1004, 372), (1022, 368)],
        ]
        scale_rows = [
            [(452, 250), (500, 260), (552, 268), (604, 276),
             (646, 282)],
            [(438, 268), (490, 280), (548, 290), (600, 297),
             (638, 300)],
            [(700, 312), (760, 326), (835, 338), (915, 344),
             (980, 344)],
            [(718, 292), (785, 307), (860, 318), (935, 324),
             (990, 320)],
            [(750, 276), (810, 290), (875, 300), (935, 302),
             (975, 296)],
        ]
        rim_head_top = [
            (372, 238), (400, 214), (440, 208), (480, 214),
            (520, 224), (552, 236), (570, 248), (575, 258),
        ]
        rim_lip = [
            (575, 258), (562, 268), (538, 273), (510, 277),
            (482, 281), (458, 282), (438, 280),
        ]
        rim_jaw_lower = [
            (572, 260), (558, 270), (538, 277), (514, 282),
            (490, 286), (466, 288), (446, 286),
        ]
        rim_brow = [(428, 214), (448, 210), (472, 212), (490, 219)]
        rim_neck_top = [
            (415, 237), (450, 222), (500, 214), (560, 212),
            (620, 213), (660, 223), (674, 234),
        ]
        rim_wing_lead = [
            (672, 218), (700, 182), (748, 156), (798, 148),
            (845, 148), (885, 168), (918, 192),
        ]
        rim_wing_trail = [
            (918, 192), (955, 230), (985, 270), (996, 300),
            (975, 306), (948, 302), (922, 296), (902, 306),
            (872, 308), (850, 300), (845, 292), (820, 284),
            (802, 274), (775, 264), (740, 248), (712, 236),
        ]
        rim_body_back = [(710, 205), (770, 192), (840, 188),
                         (910, 197), (960, 214)]
        rim_haunch = [(930, 252), (966, 240), (1004, 252),
                      (1026, 280), (1028, 312)]
        rim_foreleg = [
            (632, 278), (642, 306), (638, 326), (620, 340),
            (600, 352), (568, 355), (548, 348),
        ]
        rim_cheek = [(412, 258), (440, 262), (470, 264), (500, 266)]
        eye = {"center": (452, 232), "rx": 14.0, "ry": 7.5}
        nostril = (558, 250)
        smoke_curve = [
            (560, 244), (558, 220), (572, 196), (596, 178),
            (624, 160), (650, 146), (674, 136),
        ]
        mouth = [(566, 264), (540, 272), (505, 278), (470, 281),
                 (444, 282)]
        fangs = []
        drips = [((1084, 172), (1084, 214))]
        return dict(
            body=body, neck=neck, head=head, jaw=jaw, frill=frill,
            horn_main=horn_main, wing=wing,
            wing_ribs=wing_ribs, foreleg=foreleg, haunch=haunch,
            hind_leg=hind_leg, belly=belly,
            tail=tail, tail_top_edge=tail_top_edge,
            tail_bottom_edge=tail_bottom_edge, tail_ridge=tail_ridge,
            spikes=spikes, chin_spikes=chin_spikes, claws=claws,
            scale_rows=scale_rows, rim_head_top=rim_head_top,
            rim_lip=rim_lip, rim_jaw_lower=rim_jaw_lower, rim_brow=rim_brow,
            horn_main_top=horn_main_top,
            brow_horn=brow_horn, brow_horn_top=brow_horn_top,
            horn_main_center=[(420, 214), (400, 200), (372, 192),
                              (344, 196)],
            rim_neck_top=rim_neck_top, rim_wing_lead=rim_wing_lead,
            rim_wing_trail=rim_wing_trail, rim_body_back=rim_body_back,
            rim_haunch=rim_haunch,
            rim_foreleg=rim_foreleg, rim_cheek=rim_cheek, eye=eye,
            nostril=nostril, smoke_curve=smoke_curve, mouth=mouth,
            fangs=fangs, drips=drips,
        )

    def _transform_geometry(self, geo):
        if not self.portrait:
            return geo
        out = transform_geo(geo, self.dragon_scale,
                            self.dragon_dx, self.dragon_dy)
        out["eye"]["rx"] = geo["eye"]["rx"] * self.dragon_scale
        out["eye"]["ry"] = geo["eye"]["ry"] * self.dragon_scale
        return out

    # -------------------------------------------------------------- static

    def _build_background(self):
        w, h = self.SW, self.SH
        bg = pygame.Surface((w, h)).convert()
        for y in range(h):
            t = y / max(1, h - 1)
            pygame.draw.line(bg, mix(P.bg_top, P.bg_bottom, t ** 0.85),
                             (0, y), (w, y))

        if self.portrait:
            self.haze(bg, (540, 1680), 600, 760, (126, 57, 24), 94, 2.2)
            self.haze(bg, (540, 1300), 480, 620, (68, 32, 20), 50, 2.0)
            self.haze(bg, (540, 760), 360, 340, (52, 26, 18), 26, 2.4)
        else:
            self.haze(bg, (620, 360), 600, 270, (132, 60, 24), 98, 2.2)
            self.haze(bg, (690, 250), 440, 220, (78, 36, 22), 48, 2.0)
            self.haze(bg, (250, 130), 330, 160, (48, 24, 16), 22, 2.4)

        # A couple of broad, barely-there wall washes.  No line drawing.
        rng = random.Random(self.seed * 17 + 3)
        for i in range(2):
            base_y = (0.34 + 0.22 * i) * self.H
            pts = []
            for j in range(5):
                x = -100 + (self.W + 200) * j / 4.0
                y = base_y + math.sin(j * 0.8 + i * 1.7) * (
                    40 if self.portrait else 18)
                y += rng.uniform(-14, 14)
                pts.append((x, y))
            self.stroke_alpha(bg, pts, mix(P.wall_line, P.bg_top, 0.55),
                              6, 26.0)

        # More light behind the sleeper, so the silhouette reads.
        if self.portrait:
            self.haze(bg, (540, 1360), 500, 400, (74, 36, 22), 54, 2.0)
        else:
            self.haze(bg, (620, 280), 440, 200, (70, 33, 20), 44, 2.0)

        if self.portrait:
            self._draw_shaft(bg)
        self._draw_ceiling(bg)
        if self.portrait:
            self._draw_walls(bg)
        self._draw_floor(bg)
        self.bg = bg

    # ------------------------------------------------------------- cavern

    def _ceiling_edge(self):
        if self.portrait:
            return [(0, 430), (90, 402), (180, 452), (280, 412),
                    (380, 434), (480, 384), (560, 362), (650, 384),
                    (740, 352), (820, 394), (900, 424), (1000, 392),
                    (1080, 434)]
        return [(0, 108), (120, 94), (250, 118), (390, 80),
                (540, 60), (700, 56), (860, 78), (1010, 62),
                (1150, 90), (1280, 106)]

    def _stalactites(self):
        if self.portrait:
            return [
                (160, 450, 420, 86),
                (386, 420, 210, 56),
                (758, 388, 540, 74),
                (938, 420, 360, 82),
            ]
        return [
            (178, 104, 104, 54),
            (430, 84, 72, 36),
            (1052, 88, 108, 60),
        ]

    def _draw_ceiling(self, surface):
        edge = self._ceiling_edge()
        polygon = [(0, 0), (self.W, 0)] + list(reversed(edge))
        self.poly(surface, polygon, P.cave_near)
        # A broad, soft underside; no bright contour line.
        shelf = [(x, y - (14 if self.portrait else 8)) for x, y in edge]
        self.stroke_alpha(surface, shelf, P.stone_dim, 26, 12.0)
        for i in range(0, len(edge) - 1, 2):
            self.haze(surface, ((edge[i][0] + edge[i + 1][0]) / 2,
                                (edge[i][1] + edge[i + 1][1]) / 2 + 16),
                      70, 26, (74, 36, 20), 10, 1.6)

        for x, base_y, length, half_w in self._stalactites():
            outer = [
                (x - half_w, base_y),
                (x - half_w * 0.56, base_y + length * 0.52),
                (x - half_w * 0.16, base_y + length * 0.88),
                (x, base_y + length),
                (x + half_w * 0.20, base_y + length * 0.82),
                (x + half_w * 0.60, base_y + length * 0.46),
                (x + half_w, base_y),
            ]
            self.poly(surface, outer, mix(P.cave_near, P.cave_hi, 0.55))
            lit = [
                (x - half_w, base_y),
                (x - half_w * 0.56, base_y + length * 0.52),
                (x - half_w * 0.16, base_y + length * 0.88),
                (x, base_y + length),
            ]
            self.stroke_alpha(surface, lit, mix(P.stone, P.rust_dim, 0.25),
                              24, 12.0)
            self.stroke_alpha(surface, lit, mix(P.rust_dim, P.stone, 0.3),
                              26, 2.0)
            tip = (x, base_y + length)
            self.glow(surface, tip, 9, (74, 34, 18), 2.5)
            if length > (200 if self.portrait else 60):
                self.glow(surface, (x, tip[1] + 4), 4, (90, 54, 28), 2.0)

    def _draw_walls(self, surface):
        left = [(0, 430), (60, 470), (112, 570), (88, 740), (134, 930),
                (98, 1120), (142, 1330), (92, 1520), (0, 1630)]
        right = [(1080, 420), (1010, 470), (988, 610), (1020, 790),
                 (978, 990), (1020, 1190), (982, 1390), (1034, 1580),
                 (1080, 1680)]
        self.poly(surface, left + [(0, 1920), (0, 430)], (7, 4, 3))
        self.poly(surface, right + [(1080, 1920)], (7, 4, 3))


    def _draw_shaft(self, surface):
        """A pale shaft from a crack in the roof, down into the dragon's dust."""
        low = pygame.Surface((96, 320), pygame.SRCALPHA)
        for y in range(320):
            fade = (1.0 - y / 320.0) ** 0.70
            for x in range(96):
                dx = (x + 0.5 - 48.0) / 26.0
                a = int(10.0 * fade * math.exp(-dx * dx))
                if a > 0:
                    low.set_at((x, y), (176, 146, 108, a))
        tall = pygame.transform.smoothscale(low, (620, 1220))
        tall = pygame.transform.rotate(tall, -4.0)
        surface.blit(tall, (self.P(230, 410)))
        core = pygame.transform.smoothscale(low, (230, 1180))
        core = pygame.transform.rotate(core, -4.0)
        surface.blit(core, (self.P(400, 430)))
        crack = [(506, 352), (500, 390), (512, 424), (504, 452)]
        self.stroke_alpha(surface, crack, (216, 184, 142), 120, 1.2)
        self.glow(surface, (506, 380), 34, (54, 40, 24), 2.0)

    def _draw_floor(self, surface):
        if self.portrait:
            heights = [(0, 1468), (140, 1458), (300, 1476),
                       (460, 1462), (620, 1480), (780, 1460),
                       (940, 1478), (1080, 1466)]
        else:
            heights = [(0, 332), (150, 326), (300, 336), (460, 328),
                       (620, 338), (780, 330), (940, 338),
                       (1100, 332), (1280, 338)]
        poly = list(heights) + [(self.W + 10, self.H + 10),
                                (-10, self.H + 10)]
        self.poly(surface, poly, (10, 5, 4))
        self.stroke_alpha(surface, heights, mix(P.rust_dim, P.gold_deep, 0.4),
                          48, 2.0)
        if self.portrait:
            humps = [(120, 1470, 130, 26), (540, 1476, 190, 22),
                     (990, 1470, 120, 24)]
        else:
            humps = [(90, 330, 120, 18), (640, 334, 190, 16),
                     (1210, 330, 90, 15)]
        for cx, cy, rx, ry in humps:
            pygame.draw.ellipse(
                surface, (12, 6, 5),
                (self.P(cx - rx, cy - ry)[0], self.P(cx - rx, cy - ry)[1],
                 self.S(rx * 2), self.S(ry * 2)))
            self.stroke_alpha(surface, [(cx - rx * 0.7, cy - ry * 0.1),
                                        (cx, cy - ry * 0.7),
                                        (cx + rx * 0.7, cy - ry * 0.1)],
                              mix(P.rust_dim, P.stone, 0.3), 34, 1.2)

    def _draw_foreground(self, surface):
        if self.portrait:
            top = [(0, 1810), (90, 1802), (190, 1814), (300, 1806),
                   (420, 1820), (540, 1812), (660, 1822), (780, 1808),
                   (900, 1820), (1010, 1810), (1080, 1800)]
        else:
            top = [(0, 374), (60, 370), (140, 378), (220, 372),
                   (320, 380), (430, 374), (540, 382), (650, 376),
                   (760, 383), (870, 377), (980, 384), (1090, 374),
                   (1190, 381), (1280, 373)]
        poly = list(top) + [(self.W + 10, self.H + 10),
                            (-10, self.H + 10)]
        self.poly(surface, poly, P.rock)
        self.stroke_alpha(surface, top, P.stone_dim, 80, 4.0)
        self.stroke_alpha(surface, top, mul(P.rust_dim, 0.6), 40, 1.0)
        if self.portrait:
            facets = [[(180, 1812), (250, 1850), (360, 1840)],
                      [(820, 1820), (900, 1860), (1010, 1846)]]
            kisses = [(320, 1808), (880, 1814)]
        else:
            facets = [[(180, 376), (260, 394), (390, 386)],
                      [(900, 378), (1000, 396), (1120, 386)]]
            kisses = [(250, 376), (1020, 382)]
        for pts in facets:
            self.stroke_alpha(surface, pts, P.stone_dim, 50, 1.4)
        for x, y in kisses:
            self.haze(surface, (x, y + 6), 60, 15, (92, 40, 16), 46, 1.8)

    # --------------------------------------------------------------- hoard

    def _build_hoard(self):
        if self.portrait:
            spec = [
                (285, 1542, 250, 72, 190, 22),
                (905, 1548, 195, 68, 160, 18),
            ]
        else:
            spec = [
                (206, 354, 202, 62, 250, 34),
                (1078, 358, 208, 64, 250, 38),
            ]
        self.piles = []
        for index, (cx, cy, rx, ry, count, front_count) in enumerate(spec):
            rng = random.Random(self.seed * 977 + index * 613)
            coins = []
            for _ in range(count):
                u = rng.random() * 2.0 - 1.0
                x = cx + rx * u
                k = max(0.0, 1.0 - u * u)
                top = cy - ry * math.sqrt(k) * 0.95
                y = top + (cy + ry * 0.34 - top) * (rng.random() ** 1.30)
                w = rng.uniform(8.0, 15.0)
                h = rng.uniform(3.0, 5.6)
                if rng.random() < 0.10:
                    w *= rng.uniform(1.4, 1.9)
                    h *= rng.uniform(1.2, 1.6)
                base = rng.choice((mul(P.gold_deep, 0.80),
                                   mul(P.gold_deep, 1.25),
                                   mul(P.gold, 0.42), mul(P.copper, 0.72)))
                if rng.random() < 0.06:
                    base = mix(base, P.gold, rng.uniform(0.25, 0.45))
                shine = rng.random() < 0.22
                glint = rng.random() < 0.016
                coins.append((x, y, w, h, base, shine, glint,
                              rng.random()))
            coins.sort(key=lambda c: c[1])
            front = set()
            if front_count:
                order = sorted(range(len(coins)),
                               key=lambda i: coins[i][1] + coins[i][3],
                               reverse=True)
                front = set(order[:front_count])
            self.piles.append(dict(coins=coins, front=front,
                                   cx=cx, cy=cy, rx=rx, ry=ry,
                                   index=index))

    def _draw_mound(self, surface, pile):
        self.haze(surface, (pile["cx"], pile["cy"] - pile["ry"] * 0.2),
                  pile["rx"] * 0.95, pile["ry"] * 0.72,
                  (132, 66, 24), 18, 1.9)
        self.haze(surface, (pile["cx"], pile["cy"] - pile["ry"] * 0.12),
                  pile["rx"] * 0.58, pile["ry"] * 0.46,
                  (196, 108, 40), 12, 1.7)

    def _draw_coins(self, surface, front: bool):
        for pile in self.piles:
            if not front:
                self._draw_mound(surface, pile)
                if pile["index"] == 0:
                    self._draw_goblet(surface, pile)
            for index, coin in enumerate(pile["coins"]):
                if (index in pile["front"]) != front:
                    continue
                x, y, cw, ch, color, shine, glint, phase = coin
                rect = (int((x - cw / 2) * self.ss),
                        int((y - ch / 2) * self.ss),
                        max(2, int(cw * self.ss)),
                        max(2, int(ch * self.ss)))
                pygame.draw.ellipse(surface, mul(P.gold_deep, 0.45),
                                    (rect[0] - 1, rect[1] - 1,
                                     rect[2] + 2, rect[3] + 2))
                pygame.draw.ellipse(surface, color, rect)
                if shine:
                    self.add_line(surface,
                                  (x - cw * 0.28, y - ch * 0.10),
                                  (x + cw * 0.10, y - ch * 0.36),
                                  mix(color, P.gold_light, 0.50), 0.8)
        if front:
            for pile in self.piles:
                self.haze(surface, (pile["cx"], pile["cy"] - 4),
                          pile["rx"] * 0.9, pile["ry"] * 0.50,
                          (180, 98, 36), 6, 1.6)

    def _draw_goblet(self, surface, pile):
        cx = pile["cx"] - pile["rx"] * 0.58
        cy = pile["cy"] + 2
        s = 1.35 if self.portrait else 1.0
        top = cy - 44 * s
        bowl = [
            (cx - 20 * s, top + 2 * s), (cx - 18 * s, top + 14 * s),
            (cx - 10 * s, top + 23 * s), (cx, top + 25 * s),
            (cx + 10 * s, top + 23 * s), (cx + 18 * s, top + 14 * s),
            (cx + 20 * s, top + 2 * s),
        ]
        self.poly(surface, bowl, mul(P.gold_deep, 0.9))
        pygame.draw.ellipse(
            surface, mul(P.gold, 0.55),
            (self.P(cx - 20 * s, top - 3 * s)[0],
             self.P(cx - 20 * s, top - 3 * s)[1],
             self.S(40 * s), self.S(9 * s)))
        pygame.draw.ellipse(
            surface, P.rust_dim,
            (self.P(cx - 16 * s, top - 1 * s)[0],
             self.P(cx - 16 * s, top - 1 * s)[1],
             self.S(32 * s), self.S(5 * s)))
        self.poly(surface, [(cx - 3 * s, top + 24 * s),
                            (cx + 3 * s, top + 24 * s),
                            (cx + 2 * s, cy - 7 * s),
                            (cx - 2 * s, cy - 7 * s)],
                  mul(P.gold_deep, 0.8))
        pygame.draw.ellipse(
            surface, mul(P.gold, 0.35),
            (self.P(cx - 17 * s, cy - 10 * s)[0],
             self.P(cx - 17 * s, cy - 10 * s)[1],
             self.S(34 * s), self.S(8 * s)))
        self.stroke_alpha(surface, [(cx - 19 * s, top + 4 * s),
                                    (cx - 13 * s, top + 16 * s),
                                    (cx - 3 * s, top + 22 * s)],
                          P.gold_light, 120, 1.2 * s)
        self.stroke_alpha(surface, [(cx - 15 * s, top - 1 * s),
                                    (cx + 2 * s, top - 3 * s),
                                    (cx + 16 * s, top - 1 * s)],
                          P.gold_light, 150, 1.0 * s)
        self.glow(surface, (cx - 10 * s, top + 4 * s), 12, (74, 36, 14), 2.0)

    def _collect_glints(self):
        self._coin_glints = []
        for pile in self.piles:
            for coin in pile["coins"]:
                if coin[6]:
                    self._coin_glints.append((coin[0], coin[1], coin[7]))

    # --------------------------------------------------------------- dragon

    def _draw_dragon(self, surface, geo):
        body = smooth(geo["body"])
        neck = smooth(geo["neck"])
        head = smooth(geo["head"])
        jaw = smooth(geo["jaw"])
        frill = smooth(geo["frill"])
        wing = smooth(geo["wing"])
        foreleg = smooth(geo["foreleg"])
        haunch = geo["haunch"]
        belly = geo["belly"]
        tail = geo["tail"]
        horn_main = geo["horn_main"]
        brow_horn = geo["brow_horn"]

        self.glow(surface, (600 if not self.portrait else 560,
                            345 if not self.portrait else 1470),
                  270 if not self.portrait else 330,
                  (40, 17, 7), 2.2)

        self.poly(surface, body, P.body)
        self.poly(surface, belly, mix(P.body, P.belly, 0.45))
        self.poly(surface, haunch, mix(P.body, P.body_hi, 0.55))
        self.poly(surface, tail, P.body)
        self.poly(surface, geo["hind_leg"], mix(P.body, P.body_hi, 0.55))
        self.poly(surface, neck, P.body)
        self.poly(surface, frill, P.body_low)
        for a, tip, b in geo["spikes"]:
            self.poly(surface, [a, tip, b], P.body_hi)
        self.poly(surface, head, P.body)
        self.poly(surface, jaw, mix(P.body, P.body_hi, 0.7))
        self.poly(surface, foreleg, P.body)
        self.poly(surface, wing, mix(P.body, P.body_hi, 0.65))

        shade = pygame.Surface((self.SW, self.SH), pygame.SRCALPHA)
        ss = self.ss
        if self.portrait:
            for rect, a in (
                ((760, 1180, 300, 200), 105),
                ((300, 1280, 220, 100), 80),
                ((900, 1320, 170, 170), 70),
            ):
                pygame.draw.ellipse(shade, (0, 0, 0, a),
                                    (ss * rect[0], ss * rect[1],
                                     ss * rect[2], ss * rect[3]))
        else:
            for rect, a in (
                ((760, 230, 260, 110), 105),
                ((410, 258, 160, 58), 78),
                ((940, 270, 120, 100), 70),
            ):
                pygame.draw.ellipse(shade, (0, 0, 0, a),
                                    (ss * rect[0], ss * rect[1],
                                     ss * rect[2], ss * rect[3]))
        surface.blit(shade, (0, 0))

        self.stroke(surface, self.GP(smooth([(944, 330), (976, 344),
                                             (1012, 334), (1026, 312)], n=16)),
                    mul(P.scale, 0.55), width=1.1)

        self.poly(surface, wing, mix(P.body, P.body_hi, 0.65))
        lead_band = self.GP(smooth([(672, 218), (700, 182), (748, 156),
                                    (798, 148), (845, 148), (885, 168),
                                    (918, 192)]))
        off = 10 if not self.portrait else 10 * self.dragon_scale
        off_y = 20 if not self.portrait else 20 * self.dragon_scale
        inner = [(x + off, y + off_y) for x, y in lead_band]
        band = lead_band + list(reversed(inner))
        self.poly(surface, band, mix(P.body_hi, P.scale, 0.25))
        for rib in geo["wing_ribs"]:
            self.stroke(surface, smooth(rib, n=20),
                        mix(P.scale_hi, P.body, 0.30), width=1.6)
        wrist = self.G(798, 148)
        for a, b in (((900, 288), (930, 230)), ((850, 292), (880, 240)),
                     ((815, 268), (842, 226))):
            self.stroke(surface, [wrist, self.G(*a), self.G(*b)],
                        mul(P.scale, 0.55), width=0.7)
        claw = self.GP([(794, 146), (814, 166), (797, 159)])
        self.poly(surface, claw, P.horn_dark)
        self.stroke(surface, claw[:2], mul(P.horn_light, 0.35), width=0.8)

        self.poly(surface, self.GP([(642, 252), (668, 240), (700, 244),
                                    (716, 264), (708, 292), (686, 306),
                                    (660, 302), (646, 278)]),
                  mix(P.body, P.body_hi, 0.55))
        self.stroke(surface, self.GP([(650, 268), (668, 292), (676, 310)]),
                    mul(P.scale, 0.5), width=1.0)
        self.stroke(surface, self.GP([(968, 300), (1000, 320), (1014, 344)]),
                    mul(P.scale, 0.55), width=1.1)
        for claw in geo["claws"]:
            self.poly(surface, claw, P.horn_dark)
            self.stroke(surface, claw, mul(P.claw, 0.55), width=0.7)

        for row in geo["scale_rows"]:
            pts = resample(row, 9)
            for i in range(3, len(pts) - 3, 3):
                x, y = pts[i]
                self.stroke(surface, [(x - 5.5, y), (x, y + 4.5),
                                      (x + 5.5, y)],
                            mul(P.scale, 0.58), width=0.9)
        hcx, hcy = self.G(984, 300)
        for radius in (18, 30, 42):
            radius *= self.dragon_scale
            arc = []
            for step in range(13):
                a = math.pi * 0.15 + math.pi * 0.62 * step / 12.0
                arc.append((hcx + radius * math.cos(a),
                            hcy + radius * 0.8 * math.sin(a)))
            self.stroke_alpha(surface, arc, P.scale, 52, 0.9)
        self.stroke(surface, self.GP([(426, 230), (452, 225), (478, 229)]),
                    mul(P.scale, 0.65), width=1.0)
        self.stroke(surface, geo["rim_cheek"], mul(P.scale, 0.55), width=0.9)



        for spike in geo["chin_spikes"]:
            self.poly(surface, spike, P.body_hi)

        for i in range(3):
            t = (i + 1) / 4.0
            self.stroke(surface, [(350 + 18 * t, 252 + 3 * t),
                                  (380 + 10 * t, 260 + 4 * t),
                                  (406, 263 + 2 * t)],
                        mul(P.scale, 0.55), width=0.8)

        for t in (0.22, 0.44, 0.66):
            self.stroke_alpha(
                surface,
                self.GP([(400 + 30 * t, 238 + 10 * t),
                         (450 + 20 * t, 236 + 12 * t),
                         (500 + 12 * t, 240 + 14 * t)]),
                P.scale, 40, 0.8)

        rim = pygame.Surface((self.SW, self.SH), pygame.SRCALPHA)
        warm = P.rust
        warm_hi = mix(P.rust, P.accent, 0.55)
        gold = mix(P.gold_light, P.glow, 0.5)
        bone = mix(P.horn_light, P.ink, 0.25)

        self.rim_path(rim, geo["rim_head_top"], warm_hi, width=1.7,
                      glow=5.5, alpha=195, power=0.9)
        self.rim_path(rim, geo["rim_brow"], bone, width=1.1, glow=3.5,
                      alpha=120, power=1.4)
        self.rim_path(rim, geo["rim_neck_top"], warm, width=1.5, glow=5.0,
                      alpha=215, power=1.1)
        self.rim_path(rim, geo["rim_wing_lead"], warm_hi, width=1.8,
                      glow=6.0, alpha=215, power=1.0)
        self.rim_path(rim, geo["rim_body_back"], warm, width=1.4, glow=5.0,
                      alpha=195, power=1.1)
        self.rim_path(rim, geo["rim_haunch"], warm, width=1.4, glow=5.0,
                      alpha=180, power=1.1)
        self.rim_path(rim, geo["tail_top_edge"], warm, width=1.4, glow=5.0,
                      alpha=180, power=1.1)

        self.rim_path(rim, geo["rim_lip"], warm, width=1.0, glow=3.0,
                      alpha=80, power=1.2)
        self.rim_path(rim, geo["rim_foreleg"], gold, width=1.5, glow=5.0,
                      alpha=205, power=1.0)
        self.rim_path(rim, geo["tail_bottom_edge"], gold,
                      width=1.3, glow=4.0, alpha=140, power=1.0)
        self.rim_path(rim, geo["rim_wing_trail"], gold, width=1.1, glow=3.5,
                      alpha=110, power=1.2)
        self.rim_path(rim, self.GP([(1016, 336), (1040, 350), (1058, 340)]),
                      gold, width=1.1, glow=3.2, alpha=110, power=1.2)

        for x, y in ((706, 324), (750, 334), (800, 342), (850, 346),
                     (900, 347), (946, 344)):
            gx, gy = self.G(x, y)
            r = 6 * self.dragon_scale
            self.rim_path(rim, [(gx - r, gy), (gx, gy + 5 * self.dragon_scale),
                                (gx + r, gy)],
                          gold, width=1.0, glow=3.0, alpha=110, power=1.0)
        # dorsal crest: the row of plates along the neck
        for a, tip, b in geo["spikes"]:
            self.rim_path(rim, [a, tip], mix(P.rust, P.accent, 0.35),
                          width=1.3, glow=3.8, alpha=170, power=0.9)
        # cheek frill spikes
        for path in (
            [(420, 254), (390, 244), (362, 236), (344, 238)],
            [(418, 258), (390, 250), (362, 256), (342, 258)],
            [(414, 266), (388, 268), (366, 264), (352, 278)],
        ):
            self.rim_path(rim, self.GP(path), mix(P.rust, P.accent, 0.25),
                          width=1.2, glow=3.5, alpha=135, power=1.1)
        surface.blit(rim, (0, 0))

        mouth = resample(geo["mouth"], 10)
        self.stroke(surface, mouth, (6, 3, 2), width=1.7)
        self.stroke_alpha(surface, mouth, mix(P.rust, P.gold, 0.4), 80, 0.6)
        for fang in geo["fangs"]:
            self.poly(surface, fang, P.claw)
            self.stroke(surface, fang, mul(P.claw, 0.5), width=0.6)
        nx, ny = geo["nostril"]
        pygame.draw.ellipse(surface, (5, 2, 2),
                            (self.P(nx - 4, ny - 2)[0],
                             self.P(nx - 4, ny - 2)[1],
                             self.S(8), self.S(5)))
        self.stroke(surface, [(nx - 4, ny - 1), (nx, ny - 3),
                              (nx + 4, ny - 1)],
                    mul(P.rust, 0.65), width=0.9)
        self._draw_eye(surface, geo["eye"])

    def _draw_eye(self, surface, eye):
        cx, cy = eye["center"]
        rx, ry = eye["rx"], eye["ry"]

        pygame.draw.ellipse(
            surface, (12, 7, 6),
            (self.P(cx - rx * 1.35, cy - ry * 1.15)[0],
             self.P(cx - rx * 1.35, cy - ry * 1.15)[1],
             self.S(rx * 2.7), self.S(ry * 2.3)))

        if self.eye_open:
            self.glow(surface, (cx, cy), max(26, rx * 3.6),
                      (130, 54, 12), 2.0)
            pygame.draw.ellipse(
                surface, P.eye_deep,
                (self.P(cx - rx * 1.35, cy - ry * 1.05)[0],
                 self.P(cx - rx * 1.35, cy - ry * 1.05)[1],
                 self.S(rx * 2.7), self.S(ry * 2.1)))
            pygame.draw.ellipse(
                surface, mul(P.eye, 0.78 + 0.22 * self.eye_glow),
                (self.P(cx - rx, cy - ry * 0.82)[0],
                 self.P(cx - rx, cy - ry * 0.82)[1],
                 self.S(rx * 2.0), self.S(ry * 1.64)))
            pygame.draw.ellipse(
                surface, P.pupil,
                (self.P(cx - rx * 0.28, cy - ry * 0.78)[0],
                 self.P(cx - rx * 0.28, cy - ry * 0.78)[1],
                 self.S(rx * 0.56), self.S(ry * 1.56)))
            self.glint(surface, (cx - rx * 0.62, cy - ry * 0.25),
                       max(1.8, rx * 0.18), P.glow, 0.9)
            self.glint(surface, (cx + rx * 0.55, cy + ry * 0.28),
                       max(1.4, rx * 0.13), P.eye, 0.6)
            self.stroke_alpha(surface,
                              [(cx - rx * 1.35, cy - ry * 1.02),
                               (cx, cy - ry * 1.52),
                               (cx + rx * 1.35, cy - ry * 0.92)],
                              P.scale_hi, 150, 1.6)
            self.stroke_alpha(surface,
                              [(cx - rx * 1.2, cy + ry * 1.0),
                               (cx, cy + ry * 1.42),
                               (cx + rx * 1.2, cy + ry * 0.9)],
                              P.scale, 130, 1.2)
        else:
            self.stroke_alpha(surface,
                              [(cx - rx * 1.25, cy - ry * 0.12),
                               (cx - rx * 0.1, cy + ry * 0.38),
                               (cx + rx * 1.15, cy - ry * 0.08)],
                              P.scale_hi, 100, 2.2)
            self.stroke_alpha(surface,
                              [(cx - rx * 1.10, cy - ry * 0.04),
                               (cx - rx * 0.05, cy + ry * 0.44),
                               (cx + rx * 1.02, cy + ry * 0.00)],
                              mix(P.rust, P.gold, 0.55), 165, 1.1)
            self.stroke_alpha(surface,
                              [(cx - rx * 0.8, cy + ry * 0.10),
                               (cx, cy + ry * 0.36),
                               (cx + rx * 0.75, cy + ry * 0.08)],
                              P.gold_light, 70, 0.6)
            self.glint(surface, (cx + rx * 0.92, cy - ry * 0.02),
                       max(1.2, rx * 0.10), P.glow, 0.14)

        self.stroke(surface,
                    [(cx - rx * 2.1, cy - ry * 1.7),
                     (cx - rx * 0.3, cy - ry * 2.2),
                     (cx + rx * 1.6, cy - ry * 1.5)],
                    P.body_low, width=3.4)
        self.stroke_alpha(surface,
                          [(cx - rx * 2.0, cy - ry * 1.8),
                           (cx - rx * 0.3, cy - ry * 2.3),
                           (cx + rx * 1.5, cy - ry * 1.6)],
                          P.rust, 95, 1.1)

    # ----------------------------------------------------------- atmosphere

    def _build_embers(self):
        rng = random.Random(self.seed * 271 + 11)
        count = 170 if self.portrait else 100
        self.embers = []
        for _ in range(count):
            if self.portrait:
                if rng.random() < 0.72:
                    x0 = rng.uniform(40, 1040)
                    y0 = rng.uniform(1480, 1800)
                else:
                    x0 = rng.uniform(220, 900)
                    y0 = rng.uniform(1360, 1580)
            else:
                if rng.random() < 0.78:
                    x0 = rng.uniform(20, 1260)
                    y0 = rng.uniform(316, 386)
                else:
                    x0 = rng.uniform(420, 1000)
                    y0 = rng.uniform(270, 330)
            life = rng.uniform(5.5, 14.0)
            speed = rng.uniform(4.0, 9.0)
            drift = rng.uniform(-2.6, 2.6)
            wobble = rng.uniform(2.0, 8.0)
            phase = rng.uniform(0.0, life)
            size = rng.uniform(0.8, 2.7)
            color = rng.choice((P.accent, P.glow, P.gold_light,
                                mix(P.accent, P.copper, 0.5)))
            self.embers.append(dict(x0=x0, y0=y0, life=life, speed=speed,
                                    drift=drift, wobble=wobble, phase=phase,
                                    size=size, color=color,
                                    freq=rng.uniform(0.4, 1.1)))

    def _build_dust(self):
        rng = random.Random(self.seed * 313 + 5)
        count = 150 if self.portrait else 70
        self.dust = []
        for _ in range(count):
            self.dust.append(dict(
                x=rng.uniform(0.02, 0.98) * self.W,
                y=rng.uniform(0.12 if self.portrait else 0.20,
                              0.84 if self.portrait else 0.90) * self.H,
                size=rng.uniform(0.4, 1.4),
                bright=rng.uniform(0.07, 0.30),
                drift=rng.uniform(-0.6, 0.6),
                phase=rng.uniform(0, math.tau),
                speed=rng.uniform(0.15, 0.60),
            ))

    def _draw_embers(self, surface):
        t = self.time_s
        for ember in self.embers:
            life = ember["life"]
            age = (t + ember["phase"]) % life
            x = (ember["x0"] + ember["drift"] * age
                 + math.sin(age * ember["freq"] * math.tau / life * 2.0)
                 * ember["wobble"])
            y = ember["y0"] - ember["speed"] * age
            fade = math.sin(math.pi * age / life) ** 0.75
            if fade <= 0.02:
                continue
            color = mul(ember["color"], 0.46 + 0.55 * fade)
            size = ember["size"] * (0.65 + 0.5 * fade)
            self.glow(surface, (x, y), size * 4.2, mul(color, 0.30), 2.2)
            pygame.draw.circle(surface, color, self.P(x, y),
                               max(1, self.S(size * 0.7)))

    def _draw_dust(self, surface):
        t = self.time_s
        for mote in self.dust:
            x = (mote["x"] + mote["drift"] * t
                 + math.sin(t * mote["speed"] + mote["phase"]) * 4.0)
            y = (mote["y"] - t * mote["speed"] * 0.8) % self.H
            c = mul(P.ink, mote["bright"])
            if mote["size"] > 1.0:
                pygame.draw.circle(surface, c, self.P(x, y),
                                   self.S(mote["size"] * 0.6))
            else:
                surface.set_at(self.P(x, y), c)

    def _draw_smoke(self, surface, geo):
        pts = smooth(geo["smoke_curve"], n=24)
        layer = pygame.Surface((self.SW, self.SH), pygame.SRCALPHA)
        for i in range(4, len(pts), 2):
            t = i / (len(pts) - 1)
            x, y = pts[i]
            radius = (4.0 + 20.0 * t) * (1.35 if self.portrait else 1.0)
            alpha = int(14 * (1.0 - t) ** 1.3 + 2)
            sprite = haze_surface((124, 104, 88), alpha, 1.6)
            size = max(4, int(radius * 2 * self.ss))
            scaled = pygame.transform.smoothscale(sprite, (size, size))
            layer.blit(scaled, (self.P(x - radius, y - radius)))
        surface.blit(layer, (0, 0))
        self.glow(surface, geo["smoke_curve"][0], 16,
                  (60, 28, 12), 2.1)

    def _draw_drips(self, surface, geo):
        water = (92, 98, 90)
        for top, bottom in geo["drips"]:
            self.stroke_alpha(surface, [top, (top[0], top[1] + 8)],
                              P.stone, 70, 1.0)
            mid = (bottom[0], (top[1] + bottom[1]) * 0.5)
            self.glow(surface, mid, 7, (80, 46, 24), 2.0)
            pygame.draw.ellipse(
                surface, mix(water, P.glow, 0.22),
                (self.P(mid[0] - 2, mid[1] - 3)[0],
                 self.P(mid[0] - 2, mid[1] - 3)[1],
                 self.S(4), self.S(6)))

    def _draw_glints(self, surface):
        t = self.time_s
        for x, y, phase in self._coin_glints:
            period = 2.6 + 2.2 * phase
            pulse = 0.5 + 0.5 * math.sin(math.tau * (t / period + phase))
            pulse = max(0.0, pulse - 0.18)
            if pulse <= 0.03:
                continue
            self.glint(surface, (x, y - 2), 2.0 + 2.4 * pulse,
                       P.gold_light, 0.30 + 0.65 * pulse)

    # ------------------------------------------------------------ compositing

    def _bloom(self, scene):
        small = pygame.transform.smoothscale(
            scene, (max(1, self.SW // 7), max(1, self.SH // 7)))
        small.fill((62, 62, 62), special_flags=pygame.BLEND_RGB_MULT)
        mid = pygame.transform.smoothscale(
            small, (max(1, self.SW // 4), max(1, self.SH // 4)))
        up = pygame.transform.smoothscale(mid, (self.SW, self.SH))
        scene.blit(up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _build_finish(self):
        w, h = self.W, self.H
        res = 96
        vig = pygame.Surface((res, res), pygame.SRCALPHA)
        for y in range(res):
            for x in range(res):
                dx = (x + 0.5) / res * 2.0 - 1.0
                dy = (y + 0.5) / res * 2.0 - 1.0
                d = math.hypot(dx, dy) / 1.414
                a = int(150 * max(0.0, d - 0.26) ** 1.8)
                if a > 0:
                    vig.set_at((x, y), (0, 0, 0, min(150, a)))
        self.vignette = pygame.transform.smoothscale(vig, (w, h))

        scan = pygame.Surface((w, h), pygame.SRCALPHA)
        alpha = 7 if not self.portrait else 6
        for y in range(0, h, 3):
            pygame.draw.line(scan, (0, 0, 0, alpha), (0, y), (w, y))
        self.scanlines = scan

        band = pygame.Surface((w, h), pygame.SRCALPHA)
        band_h = int(h * 0.16) if self.portrait else int(h * 0.18)
        for y in range(band_h):
            a = int(100 * (1.0 - y / band_h) ** 1.5)
            pygame.draw.line(band, (0, 0, 0, a), (0, y), (w, y))
        bottom_h = int(h * 0.055)
        for y in range(bottom_h):
            a = int(54 * (y / bottom_h) ** 1.4)
            pygame.draw.line(band, (0, 0, 0, a), (0, h - bottom_h + y),
                             (w, h - bottom_h + y))
        self.hud_band = band

        # Ground shadow: pushes the hoard and the near rock down so the
        # silhouette and the glints do the work, not a bright gold carpet.
        bottom = pygame.Surface((w, h), pygame.SRCALPHA)
        start = int(h * 0.68)
        for y in range(start, h):
            t = (y - start) / max(1, h - start)
            a = int(88 * t ** 1.5)
            pygame.draw.line(bottom, (0, 0, 0, a), (0, y), (w, y))
        self.bottom_shadow = bottom

        rng = random.Random(self.seed * 419)
        tile = pygame.Surface((96, 96), pygame.SRCALPHA)
        for y in range(96):
            for x in range(96):
                a = rng.randrange(0, 9)
                if a:
                    tile.set_at((x, y), (255, 236, 210, a))
        self.grain = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 96):
            for x in range(0, w, 96):
                self.grain.blit(tile, (x, y))

    def _build_fonts(self):
        title_px = 31 if self.portrait else 19
        sub_px = 14 if self.portrait else 10
        body_px = 18 if self.portrait else 11
        small_px = 13 if self.portrait else 9
        self.font_title = pygame.font.SysFont("dejavuserif", title_px, bold=True)
        self.font_sub = pygame.font.SysFont("dejavusansmono", sub_px, bold=True)
        self.font_body = pygame.font.SysFont("dejavusansmono", body_px)
        self.font_small = pygame.font.SysFont("dejavusansmono", small_px)

    def _text(self, surface, text, pos, color, font, align="left"):
        img = font.render(text, True, color)
        rect = img.get_rect()
        if align == "right":
            rect.topright = pos
        elif align == "center":
            rect.midtop = pos
        else:
            rect.topleft = pos
        surface.blit(img, rect)
        return rect

    def _draw_hud(self, surface):
        m = self.margin
        if self.portrait:
            title = self._text(surface, "THE SLEEPING DRAGON", (m, m),
                               P.hud, self.font_title)
            rule_y = title.bottom + 6
            pygame.draw.line(surface, mul(P.hud_faint, 0.9), (m, rule_y),
                             (m + int(title.width * 0.72), rule_y), 1)
            self._text(surface, "CAVERN 04 // THE HOARD", (m, rule_y + 8),
                       P.hud_dim, self.font_sub)
            x = self.W - m
            self._text(surface, "03:04 AM", (x, m), P.hud, self.font_body,
                       "right")
            self._text(surface, "BREATH 07.0 S", (x, m + 25),
                       P.hud_dim, self.font_small, "right")
            self._text(surface, "ONE EYE / " + ("OPEN" if self.eye_open
                                                else "CLOSED"),
                       (x, m + 44), P.hud_faint, self.font_small, "right")
            pygame.draw.line(surface, mul(P.hud_faint, 0.75),
                             (x - 150, m + 21), (x, m + 21), 1)
            self._text(surface, "EMBER DRIFT 0.5", (x, self.H - m - 14),
                       P.hud_faint, self.font_small, "right")
        else:
            title = self._text(surface, "THE SLEEPING DRAGON", (m, m - 2),
                               P.hud, self.font_title)
            rule_y = title.bottom + 3
            pygame.draw.line(surface, mul(P.hud_faint, 0.9), (m, rule_y),
                             (m + int(title.width * 0.72), rule_y), 1)
            self._text(surface, "CAVERN 04 // THE HOARD", (m, rule_y + 4),
                       P.hud_dim, self.font_sub)
            x = self.W - m
            self._text(surface, "03:04 AM", (x, m - 2), P.hud_dim,
                       self.font_body, "right")
            self._text(surface, "BREATH 07.0 S", (x, m + 13),
                       P.hud_faint, self.font_small, "right")
            self._text(surface, "ONE EYE / " + ("OPEN" if self.eye_open
                                                else "CLOSED"),
                       (x, m + 27), P.hud_faint, self.font_small, "right")
            self._text(surface, "EMBER DRIFT 0.5", (x, self.H - m - 3),
                       P.hud_faint, self.font_small, "right")

    # ---------------------------------------------------------------- frame

    def render(self, time_s: float = 0.0, eye_open: bool = False,
               study: bool = False):
        self.time_s = float(time_s)
        self.eye_open = bool(eye_open)
        self.eye_glow = 0.72 + 0.28 * math.sin(self.time_s * 1.1)
        self._collect_glints()

        if study:
            scene = pygame.Surface((self.SW, self.SH)).convert()
            scene.fill((58, 50, 44))
            self._draw_dragon(scene, self.geo)
            out = pygame.transform.smoothscale(scene, (self.W, self.H))
            return out

        scene = self.bg.copy()
        self._draw_coins(scene, front=False)
        self._draw_dragon(scene, self.geo)
        self._draw_coins(scene, front=True)
        self._draw_foreground(scene)
        scene.blit(self.bottom_shadow, (0, 0))
        self._draw_smoke(scene, self.geo)
        self._draw_drips(scene, self.geo)
        self._draw_embers(scene)
        self._draw_glints(scene)
        self._draw_dust(scene)
        self._bloom(scene)

        out = pygame.transform.smoothscale(scene, (self.W, self.H))
        out.blit(self.vignette, (0, 0))
        out.blit(self.scanlines, (0, 0))
        out.blit(self.grain, (0, 0))
        out.blit(self.hud_band, (0, 0))
        self._draw_hud(out)
        return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eye-open", action="store_true",
                        help="render the signature open-eye moment")
    parser.add_argument("--time", type=float, default=28.4)
    parser.add_argument("--portrait-time", type=float, default=41.2)
    parser.add_argument("--study", action="store_true")
    parser.add_argument("--wide", action="store_true",
                        help="also render the wide tall-cavern portrait")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((64, 64))
    os.makedirs(OUT_DIR, exist_ok=True)
    study_dir = os.path.dirname(os.path.abspath(__file__))

    suffix = "_eye_open" if args.eye_open else ""
    cases = [
        ((1280, 400), "landscape", args.time,
         f"sleeping_dragon_1280x400{suffix}.png"),
        ((1080, 1920), "portrait_mid", args.portrait_time,
         f"sleeping_dragon_1080x1920{suffix}.png"),
    ]
    if args.wide:
        cases.append(((1080, 1920), "portrait", args.portrait_time,
                      f"sleeping_dragon_1080x1920_wide{suffix}.png"))
    for size, layout, seconds, name in cases:
        scene = DragonScene(size, layout)
        frame = scene.render(seconds, eye_open=args.eye_open,
                             study=args.study)
        out_dir = study_dir if args.study else OUT_DIR
        path = os.path.join(out_dir, ("study_" if args.study else "") + name)
        pygame.image.save(frame, path)
        print(f"{name}: {size[0]}x{size[1]} t={seconds:.1f}s "
              f"embers={len(scene.embers)} glints={len(scene._coin_glints)}")
    pygame.quit()


if __name__ == "__main__":
    main()
