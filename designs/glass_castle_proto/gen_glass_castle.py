#!/usr/bin/env python3
"""Art-direction study for The Glass Castle (SLOW_WORLDS_DESIGN.md 5.13).

This is a still-frame study, not the mode.  It draws the two target aspects --
the 1280x400 Pi strip and the 1080x1920 portrait wall -- so the composition,
palette and crystal read can be reviewed before any mode, registry or profile
code is written.

The scene is the design card's vista: a castle grown from crystal on a snow
ledge under an aurora, with detached shards, warm windows, two snow layers, and
the aurora reflected inside the glass.  The geometry is a layered silhouette,
not a 3D model: a far ridge, the castle (far towers, main keep, curtain wall,
buttress fins), and the near cliff, each at its own depth.  The study pins the
scene to the aurora's bright moment, so the "lit from within" signature is
visible in a single still.

Run:
    ./.venv/bin/python designs/glass_castle_proto/gen_glass_castle.py
"""
from __future__ import annotations

import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "glass_castle")

TAU = math.tau
SS = 2                    # supersample the vector scene, then downscale
SEED = 5130               # 5.13
REVIEW_TIME = 15.0        # seconds

RGB = tuple[int, int, int]

# ------------------------------------------------------------------ palette
# "Aurora & Ice" from SLOW_WORLDS_DESIGN.md 4.1, ice variant.


class Palette:
    name = "ice"

    bg_top = (3, 5, 13)
    bg_mid = (6, 10, 24)
    bg_horizon = (14, 23, 43)
    haze = (24, 54, 74)

    star = (168, 206, 220)
    star_bright = (226, 248, 248)

    ink = (230, 243, 242)
    ink_dim = (150, 184, 196)
    hud = (214, 234, 238)
    hud_dim = (122, 158, 174)
    hud_faint = (62, 96, 116)

    structure = (142, 124, 255)
    accent = (88, 224, 184)
    accent_dim = (40, 112, 104)
    glow = (191, 247, 228)

    aurora_violet = (94, 78, 196)
    aurora_teal = (56, 182, 172)
    aurora_mint = (88, 236, 178)

    face_base = (21, 32, 57)
    face_hi = (64, 88, 138)
    face_lit = (130, 178, 210)
    face_dark = (11, 17, 32)
    edge = (188, 230, 242)
    edge_dim = (88, 120, 160)

    snow = (200, 234, 240)
    snow_dim = (120, 162, 186)
    snow_shadow = (58, 84, 116)

    warm = (255, 196, 128)
    warm_hi = (255, 240, 202)
    warm_dim = (176, 112, 62)

    cliff_top = (19, 28, 45)
    cliff_bottom = (3, 5, 11)
    cliff_face = (9, 13, 23)
    cliff_edge = (68, 100, 128)

    ridge = (22, 34, 58)
    ridge_snow = (92, 126, 152)


P = Palette()


# -------------------------------------------------------------------- colour

def clamp8(v) -> int:
    return 0 if v < 0 else 255 if v > 255 else int(v)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def scale(c: RGB, f: float) -> RGB:
    if f <= 0.0:
        return (0, 0, 0)
    return (clamp8(c[0] * f), clamp8(c[1] * f), clamp8(c[2] * f))


def smoothstep(t: float) -> float:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3.0 - 2.0 * t)


def radial_sprite(size: int, power: float = 2.4) -> pygame.Surface:
    surf = pygame.Surface((size, size)).convert()
    surf.fill((0, 0, 0))
    c = (size - 1) * 0.5
    maxd = math.hypot(c, c)
    for y in range(size):
        for x in range(size):
            r = math.hypot(x - c, y - c) / maxd
            v = max(0.0, 1.0 - r) ** power
            k = int(255 * v)
            surf.set_at((x, y), (k, k, k))
    return surf


def polygon_mask(size, points) -> pygame.Surface:
    mask = pygame.Surface(size, pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.polygon(mask, (255, 255, 255, 255), points)
    return mask


# ------------------------------------------------------------------- layouts
# Geometry is authored in final pixels; every draw multiplies by SS.

LAYOUTS = {
    "landscape": {
        "size": (1280, 400),
        "plateau": ((0, 300), (90, 296), (210, 303), (330, 294),
                    (450, 300), (570, 296), (690, 300), (810, 294),
                    (930, 301), (1050, 296), (1180, 301), (1280, 298)),
        "lip": ((0, 346), (320, 342), (640, 345), (960, 342), (1280, 346)),
        "ridge": ((-40, 300), (60, 286), (110, 248), (160, 278),
                  (220, 238), (280, 270), (330, 300), (360, 314), (0, 314)),
        "ridge_right": ((920, 314), (970, 282), (1030, 244), (1090, 274),
                        (1150, 236), (1210, 268), (1280, 300),
                        (1320, 314)),
        "castle": {
            "base_y": 336,
            # cx, base_w, shoulder_y, top_w, tip_y, lean
            "far": ((438, 34, 300, 10, 246, -1),
                    (852, 32, 302, 10, 250, 1),
                    (706, 26, 314, 8, 276, 0)),
            "main": ((640, 124, 208, 46, 96, 0),
                     (548, 78, 246, 26, 142, -3),
                     (734, 80, 252, 28, 154, 3),
                     (478, 56, 286, 18, 212, -2),
                     (804, 54, 290, 18, 220, 2),
                     (598, 46, 272, 16, 190, -1),
                     (684, 44, 276, 15, 198, 1)),
            "wall": (456, 826, 340, 298, 16),
            "plinth": (444, 836, 340, 322, 12),
            "waists": {0: (266, 112), 1: (292, 66), 2: (296, 68)},
            "gatehouse": ((600, 38, 316, 14, 288, 0),
                          (680, 38, 316, 14, 288, 0)),
            "gate": (640, 340, 24, 28),
            "fins": ((578, 337, 552, 302, 590, 308),
                     (702, 337, 728, 302, 692, 308),
                     (450, 338, 424, 312, 464, 318),
                     (830, 338, 856, 314, 818, 320),
                     (509, 337, 492, 310, 524, 316),
                     (771, 337, 788, 312, 758, 318)),
        },
        "shards": ((596, 180, 20, 8, -28, 1.0),
                   (700, 168, 16, 7, 24, 0.95),
                   (548, 238, 11, 4, 12, 0.70),
                   (760, 248, 12, 5, -16, 0.65),
                   (612, 300, 13, 5, 38, 0.60),
                   (672, 130, 10, 4, -42, 0.90),
                   (500, 270, 8, 3, 18, 0.50),
                   (792, 206, 7, 3, -20, 0.50)),
        "buttresses": (((0, 338), (40, 326), (86, 342), (120, 332),
                        (160, 356), (190, 400), (0, 400)),
                       ((1280, 330), (1232, 320), (1190, 340),
                        (1150, 330), (1110, 354), (1085, 400),
                        (1280, 400))),
        # base, amp1, f1, ph1, amp2, f2, ph2, slope, thick, inten,
        # ray_f, ray_warp, ray_ph, crown
        "curtains": (
            (0.400, 0.050, 1.3, 0.4, 0.018, 3.7, 2.1, -0.010, 0.085, 0.85,
             9.0, 2.1, 0.7, 0.30),
            (0.505, 0.060, 0.9, 2.4, 0.024, 3.1, 0.9, 0.020, 0.110, 0.55,
             12.0, 3.3, 2.0, 0.25),
            (0.290, 0.070, 0.7, 4.0, 0.028, 2.3, 1.7, -0.020, 0.170, 0.26,
             7.0, 1.6, 3.4, 0.20),
            (0.580, 0.030, 1.8, 5.2, 0.012, 4.6, 3.0, 0.000, 0.040, 0.40,
             15.0, 4.0, 1.1, 0.15),
            (0.350, 0.090, 2.5, 1.2, 0.040, 6.0, 3.7, 0.000, 0.220, 0.15,
             5.0, 1.2, 2.8, 0.20),
        ),
        "aurora_top": 0.10,
        "aurora_floor": (0.64, 0.32),
        "stars": 130,
        "snow_far": 290,
        "snow_near": 72,
        "mass_left": ((0, 312), (30, 300), (64, 316), (102, 304),
                      (140, 322), (182, 310), (226, 330), (262, 400),
                      (0, 400)),
        "mass_right": ((1280, 304), (1244, 296), (1206, 314), (1166, 302),
                       (1124, 322), (1082, 310), (1044, 332), (1016, 400),
                       (1280, 400)),
        "margin": 26,
        "title_px": 26,
        "telemetry_px": 12,
        "small_px": 10,
        "title_track": 2.4,
        "bloom": 0.34,
        "reflection": 0.72,
    },
    "portrait": {
        "size": (1080, 1920),
        "plateau": ((0, 1392), (120, 1382), (250, 1390), (390, 1376),
                    (520, 1386), (650, 1378), (780, 1388), (910, 1376),
                    (1010, 1390), (1080, 1384)),
        "lip": ((0, 1456), (300, 1452), (540, 1454), (800, 1450),
                (1080, 1456)),
        "ridge": ((-60, 1410), (80, 1330), (160, 1250), (240, 1310),
                  (330, 1240), (400, 1300), (470, 1400), (0, 1410)),
        "ridge_right": ((620, 1410), (700, 1330), (780, 1260),
                        (860, 1320), (940, 1250), (1020, 1310),
                        (1140, 1400), (1140, 1410)),
        "castle": {
            "base_y": 1444,
            "far": ((248, 64, 1344, 18, 1156, -2),
                    (832, 62, 1352, 18, 1174, 2),
                    (430, 42, 1384, 12, 1290, 1)),
            "main": ((540, 196, 1090, 74, 690, 0),
                     (358, 120, 1180, 40, 980, -4),
                     (716, 126, 1190, 42, 1010, 4),
                     (268, 84, 1310, 26, 1180, -2),
                     (812, 82, 1318, 26, 1200, 2),
                     (462, 70, 1250, 22, 900, -2),
                     (620, 68, 1256, 22, 930, 2)),
            "wall": (250, 830, 1446, 1352, 26),
            "plinth": (238, 842, 1448, 1424, 14),
            "waists": {0: (1282, 172), 1: (1330, 104), 2: (1338, 108)},
            "gatehouse": ((480, 64, 1400, 22, 1332, 0),
                          (600, 64, 1400, 22, 1332, 0)),
            "gate": (540, 1448, 38, 44),
            "fins": ((452, 1445, 418, 1394, 466, 1406),
                     (628, 1445, 662, 1394, 614, 1406),
                     (238, 1446, 206, 1400, 252, 1412),
                     (842, 1446, 874, 1402, 828, 1414),
                     (310, 1445, 286, 1394, 330, 1408),
                     (770, 1445, 794, 1396, 750, 1410)),
        },
        "shards": ((420, 1040, 30, 12, -26, 1.0),
                   (674, 900, 26, 10, 22, 0.95),
                   (300, 1180, 16, 6, 10, 0.65),
                   (770, 1120, 18, 7, -15, 0.70),
                   (500, 1210, 22, 8, 40, 0.60),
                   (596, 660, 15, 6, -38, 0.90),
                   (250, 1280, 12, 4, 20, 0.50),
                   (724, 790, 14, 5, -24, 0.60)),
        "buttresses": (((0, 1600), (64, 1560), (112, 1610), (160, 1690),
                        (150, 1920), (0, 1920)),
                       ((1080, 1570), (1010, 1530), (960, 1590),
                        (910, 1670), (930, 1920), (1080, 1920)),
                       ((400, 1730), (455, 1690), (520, 1720),
                        (585, 1680), (650, 1740), (700, 1810),
                        (660, 1920), (420, 1920))),
        "curtains": (
            (0.330, 0.062, 1.2, 0.4, 0.026, 3.4, 2.1, -0.020, 0.085, 0.90,
             10.0, 2.3, 0.7, 0.28),
            (0.425, 0.070, 0.9, 2.4, 0.032, 2.9, 0.9, 0.020, 0.110, 0.55,
             13.0, 3.5, 2.0, 0.24),
            (0.205, 0.085, 0.7, 4.0, 0.036, 2.4, 1.7, -0.030, 0.175, 0.26,
             8.0, 1.7, 3.4, 0.20),
            (0.505, 0.040, 1.7, 5.2, 0.016, 4.4, 3.0, 0.000, 0.045, 0.40,
             16.0, 4.2, 1.1, 0.15),
            (0.290, 0.100, 2.2, 1.2, 0.045, 5.6, 3.7, 0.000, 0.230, 0.14,
             5.5, 1.3, 2.8, 0.20),
        ),
        "aurora_top": 0.12,
        "aurora_floor": (0.58, 0.50),
        "stars": 280,
        "snow_far": 580,
        "snow_near": 160,
        "mass_left": ((0, 1512), (44, 1482), (86, 1516), (132, 1488),
                      (180, 1526), (228, 1500), (276, 1544), (320, 1920),
                      (0, 1920)),
        "mass_right": ((1080, 1480), (1034, 1458), (988, 1496),
                       (940, 1472), (892, 1510), (844, 1486),
                       (792, 1560), (742, 1920), (1080, 1920)),
        "margin": 44,
        "title_px": 42,
        "telemetry_px": 17,
        "small_px": 13,
        "title_track": 4.0,
        "bloom": 0.38,
        "reflection": 0.78,
    },
}


def _scale_castle(lay: dict, sx: float, sy: float,
                  ax: float = 640.0, ay: float = 340.0) -> None:
    """Scale the castle mass around its footing, leaving the ledge alone.

    The strip review asked for a slightly larger subject; rather than hand-
    editing every coordinate, one transform keeps the far towers, keep, wall,
    plinth, gate, fins and shards in register.
    """
    def px(x):
        return ax + (x - ax) * sx

    def py(y):
        return ay + (y - ay) * sy

    c = lay["castle"]
    c["far"] = tuple((px(cx), bw * sx, py(sy_), tw * sx, py(ty), lean * sx)
                     for (cx, bw, sy_, tw, ty, lean) in c["far"])
    c["main"] = tuple((px(cx), bw * sx, py(sy_), tw * sx, py(ty), lean * sx)
                      for (cx, bw, sy_, tw, ty, lean) in c["main"])
    c["wall"] = (px(c["wall"][0]), px(c["wall"][1]), py(c["wall"][2]),
                 py(c["wall"][3]), c["wall"][4] * sy)
    c["plinth"] = (px(c["plinth"][0]), px(c["plinth"][1]),
                   py(c["plinth"][2]), py(c["plinth"][3]),
                   c["plinth"][4] * sy)
    c["gatehouse"] = tuple((px(cx), bw * sx, py(sy_), tw * sx, py(ty),
                            lean * sx)
                           for (cx, bw, sy_, tw, ty, lean) in c["gatehouse"])
    c["gate"] = (px(c["gate"][0]), py(c["gate"][1]), c["gate"][2] * sx,
                 c["gate"][3] * sy)
    c["fins"] = tuple(tuple(px(v) if i % 2 == 0 else py(v)
                            for i, v in enumerate(fin))
                      for fin in c["fins"])
    c["waists"] = {i: (py(wy), ww * sx)
                   for i, (wy, ww) in c["waists"].items()}
    lay["shards"] = tuple((px(x), py(y), length * sx, width * sx, angle, b)
                          for (x, y, length, width, angle, b)
                          in lay["shards"])
    lay["buttresses"] = tuple(tuple((px(x), py(y)) for x, y in poly)
                              for poly in lay["buttresses"])


_scale_castle(LAYOUTS["landscape"], 1.40, 1.18)


# --------------------------------------------------------------------- tower

class Tower:
    """One crystal tower: a tapered body, a spire, facet lines and windows."""

    def __init__(self, cx, base_y, base_w, shoulder_y, top_w, tip_y, lean=0.0,
                 *, dim=1.0, far=False, lit=0.8, waist=None, rng=None):
        self.cx = cx
        self.base_y = base_y
        self.base_w = base_w
        self.shoulder_y = shoulder_y
        self.top_w = top_w
        self.tip_y = tip_y
        self.lean = lean
        self.dim = dim
        self.far = far
        self.lit = lit
        self.waist_y = waist[0] if waist else None
        self.waist_w = waist[1] if waist else None
        self.rng = rng or random.Random(1)
        if waist:
            wy, ww = waist
            self.poly = (
                (cx - base_w * 0.5, base_y),
                (cx - ww * 0.5, wy),
                (cx - top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + lean, tip_y),
                (cx + top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + ww * 0.5, wy),
                (cx + base_w * 0.5, base_y),
            )
        else:
            self.poly = (
                (cx - base_w * 0.5, base_y),
                (cx + base_w * 0.5, base_y),
                (cx + top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + lean, tip_y),
                (cx - top_w * 0.5 + lean * 0.22, shoulder_y),
            )

    def _t_waist(self) -> float:
        return ((self.base_y - self.waist_y)
                / max(1.0, self.base_y - self.shoulder_y))

    def edges_at(self, t: float) -> tuple[float, float]:
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        if self.waist_y is None:
            width = self.base_w * (1.0 - t) + self.top_w * t
        else:
            tw = self._t_waist()
            if t <= tw:
                width = self.base_w + (self.waist_w - self.base_w) * (t / tw)
            else:
                u = (t - tw) / max(0.001, 1.0 - tw)
                width = self.waist_w + (self.top_w - self.waist_w) * u
        cx = self.cx + self.lean * 0.22 * t
        return cx - width * 0.5, cx + width * 0.5

    def window_anchor(self, v: float, u: float) -> tuple[float, float]:
        xl, xr = self.edges_at(v)
        return xl + (xr - xl) * u, self.base_y - (self.base_y - self.shoulder_y) * v


# --------------------------------------------------------------------- study

class GlassCastleStudy:
    def __init__(self, layout: str):
        self.layout_name = layout
        self.lay = LAYOUTS[layout]
        self.W, self.H = self.lay["size"]
        self.S = SS
        self.pw, self.ph = self.W * SS, self.H * SS

        self.time = REVIEW_TIME
        self.rng = random.Random(SEED)

        self.aurora_ss = None
        self.mask_polys = []
        self.window_sprites = []
        self.glow = radial_sprite(64, 2.2)
        self.flake = radial_sprite(24, 1.7)

        self.stars = []
        self.glints = []
        self.snow_far = []
        self.snow_near = []
        self.sparkles = []

        self._build_towers()
        self._build_atmosphere()
        self._build_snow()

    # ------------------------------------------------------------------ build

    def _build_towers(self) -> None:
        cfg = self.lay["castle"]
        self.far_towers = []
        for i, (cx, bw, sy, tw, ty, lean) in enumerate(cfg["far"]):
            self.far_towers.append(Tower(
                cx, cfg["base_y"], bw, sy, tw, ty, lean,
                dim=0.46, far=True, lit=0.35,
                rng=random.Random(SEED * 31 + i * 7)))

        self.towers = []
        dims = (1.0, 0.92, 0.92, 0.74, 0.74, 0.82, 0.82)
        lits = (0.98, 0.88, 0.88, 0.70, 0.70, 0.82, 0.82)
        for i, (cx, bw, sy, tw, ty, lean) in enumerate(cfg["main"]):
            tower = Tower(cx, cfg["base_y"], bw, sy, tw, ty, lean,
                          dim=dims[i], lit=lits[i],
                          waist=cfg.get("waists", {}).get(i),
                          rng=random.Random(SEED * 17 + i + 1))
            self.towers.append(tower)

            rng = random.Random(SEED * 17 + i + 1)
            if i == 0:
                cols, rows = 4, 4
            elif i in (1, 2):
                cols, rows = 3, 3
            else:
                cols, rows = 2, 2
            for row in range(rows):
                v = 0.14 + 0.19 * row
                for col in range(cols):
                    if rng.random() < 0.16:
                        continue
                    u = 0.30 + 0.40 * (col / max(1, cols - 1))
                    period = rng.uniform(2.8, 7.2)
                    phase = rng.uniform(0.0, TAU)
                    b = 0.18 + 0.82 * (0.5 + 0.5 * math.sin(
                        TAU * self.time / period + phase)) ** 1.6
                    if rng.random() < 0.12:
                        b *= 0.25
                    x, y = tower.window_anchor(v, u)
                    w = 3.6 if i == 0 else 3.0
                    self.window_sprites.append((x, y, w, b, tower.dim))

        # The great window over the gate, and two flanking lancets.
        keep = self.towers[0]
        for u, w, b in ((0.50, 7.4, 0.98), (0.30, 3.6, 0.76),
                        (0.70, 3.6, 0.76)):
            x, y = keep.window_anchor(0.24, u)
            self.window_sprites.append((x, y, w, b, 1.0))

        for i, tower in enumerate(self.far_towers):
            x, y = tower.window_anchor(0.28, 0.5)
            self.window_sprites.append((x, y, 2.2, 0.34, 0.5))

        # Two short gate towers stand in front of the plinth and frame the
        # warm gate; they give the massing a castle entrance rather than a
        # row of needles.
        self.gatehouses = []
        for i, (cx, bw, sy, tw, ty, lean) in enumerate(
                cfg.get("gatehouse", ())):
            tower = Tower(cx, cfg["base_y"], bw, sy, tw, ty, lean,
                          dim=0.86, lit=0.90,
                          rng=random.Random(SEED * 41 + i))
            self.gatehouses.append(tower)
            for v in (0.18, 0.44, 0.68):
                x, y = tower.window_anchor(v, 0.5)
                self.window_sprites.append((x, y, 2.6, 0.72, 0.86))

    def _build_atmosphere(self) -> None:
        rng = random.Random(SEED ^ 0x51AB)
        horizon = self.H * (0.75 if self.layout_name == "landscape" else 0.72)
        for _ in range(self.lay["stars"]):
            self.stars.append((rng.uniform(0, self.W),
                               rng.uniform(0, horizon),
                               rng.choice((1, 1, 1, 2, 2, 3)),
                               rng.uniform(0.18, 1.0)))
        for _ in range(3):
            self.glints.append((rng.uniform(self.W * 0.08, self.W * 0.92),
                                rng.uniform(self.H * 0.04, horizon * 0.55),
                                rng.uniform(0.6, 1.0)))

    def _build_snow(self) -> None:
        rng = random.Random(SEED ^ 0x91F3)
        for _ in range(self.lay["snow_far"]):
            self.snow_far.append((rng.uniform(0, self.W),
                                  rng.uniform(0, self.H),
                                  rng.choice((1, 1, 1, 2)),
                                  rng.uniform(0.24, 0.78)))
        for _ in range(self.lay["snow_near"]):
            self.snow_near.append((rng.uniform(0, self.W),
                                   rng.uniform(0, self.H),
                                   rng.choice((2, 2, 3, 4)),
                                   rng.uniform(0.34, 0.92)))
        for _ in range(6 if self.layout_name == "landscape" else 12):
            self.snow_near.append((rng.uniform(0, self.W),
                                   rng.uniform(0, self.H),
                                   rng.choice((6, 7, 9)),
                                   rng.uniform(0.20, 0.34)))
        for _ in range(14 if self.layout_name == "landscape" else 36):
            self.sparkles.append((rng.uniform(0, self.W),
                                  rng.uniform(self.H * 0.70, self.H * 0.845),
                                  rng.uniform(0.25, 0.7)))

    # ---------------------------------------------------------------- aurora

    def _render_aurora(self) -> pygame.Surface:
        """A low-res additive aurora field, smoothly upscaled to the scene.

        Layered, soft ribbons rather than a hard band: each curtain has a
        long veil above its centre and a soft hem below, plus low-contrast
        ray striations.  The result is a glowing sky, not a light show.
        """
        W, H = self.W, self.H
        aw = max(200, W // 2)
        ah = max(96, H // 3)
        buf = bytearray(aw * ah * 3)

        ramp = []
        for y in range(ah):
            v = y / (ah - 1)
            if v < 0.35:
                col = mix(P.aurora_violet, P.aurora_teal, v / 0.35)
            else:
                col = mix(P.aurora_teal, P.aurora_mint, (v - 0.35) / 0.65)
            ramp.append(col)

        crown_u = self.lay["castle"]["main"][0][0] / W
        crown_w = 0.17 if self.layout_name == "landscape" else 0.24
        columns = []
        for x in range(aw):
            u = x / (aw - 1)
            entries = []
            for (base, a1, f1, ph1, a2, f2, ph2, slope, thick, inten,
                 ray_f, ray_w, ray_ph, crown) in self.lay["curtains"]:
                yc = (base + a1 * math.sin(u * f1 * TAU + ph1)
                      + a2 * math.sin(u * f2 * TAU + ph2)
                      + slope * (u - 0.5)) * ah
                th = max(2.0, thick * ah * (
                    0.90 + 0.18 * math.sin(u * 3.3 * TAU + ph1 * 1.7)))
                stripe = 0.5 + 0.5 * math.sin(
                    u * ray_f * TAU + 1.1 * math.sin(u * ray_w * TAU + ray_ph)
                    + ph2)
                mod = 0.84 + 0.16 * math.sin(u * 2.3 * TAU + ph1 * 3.1 + 1.7)
                fine = 0.5 + 0.5 * math.sin(
                    u * 61.0 * TAU + 1.6 * math.sin(u * 9.0 * TAU + ph1))
                gain = (inten * (0.58 + 0.42 * stripe ** 1.4) * mod
                        * (0.80 + 0.20 * fine))
                crown_boost = 1.0 + crown * math.exp(
                    -((u - crown_u) / crown_w) ** 2)
                entries.append((yc, 1.0 / th, gain * crown_boost))
            columns.append(entries)

        n = 256
        dmin, dmax = -3.0, 3.0
        lut = []
        for i in range(n):
            d = dmin + (dmax - dmin) * i / (n - 1)
            if d >= 0.0:
                p = math.exp(-(d / 1.25) ** 2)
            else:
                p = math.exp(-(d / 2.70) ** 2) * (
                    1.0 - 0.30 * smoothstep(-d / 2.70))
            lut.append(p)
        step = (n - 1) / (dmax - dmin)

        gain = 0.78
        for y in range(ah):
            v = y / (ah - 1)
            env = smoothstep(min(
                1.0, v / self.lay.get("aurora_top", 0.08)))
            floor_start, floor_amount = self.lay.get(
                "aurora_floor", (0.64, 0.32))
            env *= 1.0 - floor_amount * smoothstep(
                max(0.0, (v - floor_start) / (1.0 - floor_start)))
            if env <= 0.001:
                continue
            cr, cg, cb = ramp[y]
            row = y * aw * 3
            for x in range(aw):
                acc = 0.0
                for (yc, invth, g) in columns[x]:
                    d = (y - yc) * invth
                    idx = int((d - dmin) * step)
                    if 0 <= idx < n:
                        acc += lut[idx] * g
                if acc <= 0.004:
                    continue
                if acc > 1.6:
                    acc = 1.6
                acc *= env
                p = row + x * 3
                buf[p] = clamp8(cr * acc * gain)
                buf[p + 1] = clamp8(cg * acc * gain)
                buf[p + 2] = clamp8(cb * acc * gain)

        small = pygame.image.frombuffer(bytes(buf), (aw, ah), "RGB").convert()
        return pygame.transform.smoothscale(small, (self.pw, self.ph))

    # ------------------------------------------------------------------ sky

    def _draw_sky(self, screen: pygame.Surface) -> None:
        w, h = self.pw, self.ph
        for y in range(h):
            t = y / (h - 1)
            if t < 0.55:
                col = mix(P.bg_top, P.bg_mid, smoothstep(t / 0.55))
            else:
                col = mix(P.bg_mid, P.bg_horizon,
                          smoothstep((t - 0.55) / 0.45) * 0.6)
            pygame.draw.line(screen, col, (0, y), (w, y))

        for (cx, cy, size, color, strength) in (
            (self.W * 0.5, self.H * 0.40, self.W * 0.86, P.haze, 0.42),
            (self.W * 0.18, self.H * 0.20, self.W * 0.34, (38, 26, 70), 0.30),
            (self.W * 0.84, self.H * 0.26, self.W * 0.30, (18, 52, 60), 0.26),
            (self.W * 0.5, self.H * (0.735 if self.layout_name == "landscape"
                                     else 0.700),
             self.W * 0.95, (16, 46, 52), 0.30),
        ):
            tint = scale(color, strength)
            sprite = self._tint(self.glow, tint)
            sw = int(size * self.S)
            scaled = pygame.transform.smoothscale(sprite, (sw, sw))
            screen.blit(scaled, (int(cx * self.S - sw * 0.5),
                                 int(cy * self.S - sw * 0.5)),
                        special_flags=pygame.BLEND_RGB_ADD)

        for (x, y, size, b) in self.stars:
            twinkle = 0.82 + 0.18 * math.sin(TAU * self.time / 7.3 + x * 0.05)
            col = scale(P.star, b * twinkle)
            pygame.draw.circle(screen, col,
                               (int(x * self.S), int(y * self.S)),
                               max(1, size // 2))
        for (x, y, b) in self.glints:
            col = scale(P.star_bright, b * 0.8)
            cx, cy = int(x * self.S), int(y * self.S)
            arm = int(7 * self.S)
            pygame.draw.line(screen, scale(col, 0.35), (cx - arm, cy),
                             (cx + arm, cy), 1)
            pygame.draw.line(screen, scale(col, 0.35), (cx, cy - arm),
                             (cx, cy + arm), 1)
            pygame.draw.circle(screen, col, (cx, cy), 1)

    @staticmethod
    def _tint(src: pygame.Surface, color: RGB) -> pygame.Surface:
        out = src.copy()
        out.fill(color, special_flags=pygame.BLEND_RGB_MULT)
        return out

    def _poly_mask(self, points) -> pygame.Surface:
        return polygon_mask((self.pw, self.ph), points)

    # ----------------------------------------------------------- background

    def _draw_ridge(self, screen: pygame.Surface) -> None:
        for points in (self.lay["ridge"], self.lay["ridge_right"]):
            pts = [(x * self.S, y * self.S) for x, y in points]
            pygame.draw.polygon(screen, P.ridge, pts)
            pygame.draw.aalines(screen, scale(P.ridge_snow, 0.40), True, pts)
            for i in range(1, len(points) - 2):
                (x, y), (nx, ny) = points[i], points[i + 1]
                if ny > y:
                    continue
                pygame.draw.aaline(screen, scale(P.ridge_snow, 0.55),
                                   (x * self.S, y * self.S),
                                   ((x + nx) * 0.5 * self.S,
                                    (y + ny) * 0.5 * self.S))

    def _plateau_poly(self) -> list[tuple[float, float]]:
        top = list(self.lay["plateau"])
        lip = list(self.lay["lip"])
        return top + lip[::-1]

    def _draw_plateau(self, screen: pygame.Surface) -> None:
        poly = [(x * self.S, y * self.S) for x, y in self._plateau_poly()]
        pygame.draw.polygon(screen, (21, 32, 52), poly)

        y0 = min(y for _, y in self.lay["plateau"])
        y1 = max(y for _, y in self.lay["lip"])
        band = pygame.Surface((self.pw, self.ph), pygame.SRCALPHA)
        for y in range(int(y0 * self.S), int(y1 * self.S) + 1):
            t = (y / self.S - y0) / max(1.0, y1 - y0)
            col = mix((33, 51, 74), (15, 23, 38), smoothstep(t))
            pygame.draw.line(band, (*col, 255), (0, y), (self.pw, y))
        band.blit(self._poly_mask(poly), (0, 0),
                  special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(band, (0, 0))

        top = [(x * self.S, y * self.S) for x, y in self.lay["plateau"]]
        pygame.draw.aalines(screen, mix(P.snow_dim, P.snow, 0.55),
                            False, top)
        pygame.draw.lines(screen, scale(P.snow, 0.62), False, top, 1)

        rng = random.Random(SEED ^ 0x77A1)
        for _ in range(80 if self.layout_name == "landscape" else 210):
            x = rng.uniform(0, self.W)
            y = rng.uniform(y0 + 4, y1 - 2)
            length = rng.uniform(8, 38)
            col = mix((20, 31, 50), P.snow_dim, rng.uniform(0.08, 0.30))
            pygame.draw.line(screen, col,
                             (x * self.S, y * self.S),
                             ((x + length) * self.S, y * self.S), 1)

        lip = [(x * self.S, y * self.S) for x, y in self.lay["lip"]]
        pygame.draw.aalines(screen, mix(P.cliff_edge, P.snow_dim, 0.45),
                            False, lip)

    def _soft_shadow(self, screen, cx, cy, w, h, alpha=150):
        surf = pygame.Surface((max(2, int(w)), max(2, int(h))),
                              pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        pygame.draw.ellipse(surf, (2, 4, 9, alpha), surf.get_rect())
        screen.blit(surf, (int(cx - w * 0.5), int(cy - h * 0.5)))

    def _draw_ground_shadows(self, screen: pygame.Surface) -> None:
        S = self.S
        x0, x1, base_y, _, _ = self.lay["castle"]["wall"]
        self._soft_shadow(screen, (x0 + x1) * 0.5 * S,
                          base_y * S - 2 * S, (x1 - x0) * 1.05 * S, 12 * S,
                          110)
        for tower in self.towers:
            self._soft_shadow(screen, tower.cx * S, tower.base_y * S - 1 * S,
                              tower.base_w * 1.5 * S, 12 * S, 150)
        for tower in self.far_towers:
            self._soft_shadow(screen, tower.cx * S, tower.base_y * S - 1 * S,
                              tower.base_w * 1.7 * S, 8 * S, 90)

    # --------------------------------------------------------------- castle

    def _tower_colors(self, tower: Tower, t: float):
        base = mix(P.face_base, P.face_hi, t ** 0.75)
        if tower.far:
            base = mix(P.bg_mid, base, 0.55)
        base = scale(base, tower.dim)
        lit = mix(base, P.face_lit, 0.26 * tower.dim)
        dark = scale(base, 0.62)
        return base, lit, dark

    def _draw_tower(self, screen: pygame.Surface, tower: Tower,
                    record: bool = False) -> None:
        S = self.S
        base_y = tower.base_y
        sh_y = tower.shoulder_y

        for y in range(int(sh_y * S), int(base_y * S) + 1):
            fy = y / S
            t = (base_y - fy) / max(1.0, base_y - sh_y)
            xl, xr = tower.edges_at(t)
            base, lit, dark = self._tower_colors(tower, t)
            x1, x2 = int(xl * S), int(xr * S)
            if x2 <= x1:
                continue
            pygame.draw.line(screen, base, (x1, y), (x2, y))
            pygame.draw.line(screen, lit, (x1, y),
                             (x1 + int((x2 - x1) * 0.26), y))
            pygame.draw.line(screen, dark,
                             (x1 + int((x2 - x1) * 0.74), y), (x2, y))

        apex = (tower.cx + tower.lean, tower.tip_y)
        for y in range(int(tower.tip_y * S), int(sh_y * S) + 1):
            fy = y / S
            t = 1.0 - (fy - tower.tip_y) / max(1.0, sh_y - tower.tip_y)
            half = (tower.top_w * 0.5) * (1.0 - t)
            cx = tower.cx + tower.lean * t
            xl, xr = cx - half, cx + half
            base, lit, dark = self._tower_colors(tower, 0.85 + 0.15 * t)
            base = mix(base, P.edge_dim, 0.10 + 0.22 * t)
            x1, x2 = int(xl * S), int(xr * S)
            if x2 <= x1:
                x2 = x1 + 1
            pygame.draw.line(screen, base, (x1, y), (x2, y))
            if t < 0.55:
                pygame.draw.line(screen, lit, (x1, y),
                                 (x1 + max(1, int((x2 - x1) * 0.30)), y))

        left = [(tower.cx - tower.base_w * 0.5, base_y),
                (tower.cx - tower.top_w * 0.5 + tower.lean * 0.22, sh_y),
                apex]
        right = [(tower.cx + tower.base_w * 0.5, base_y),
                 (tower.cx + tower.top_w * 0.5 + tower.lean * 0.22, sh_y),
                 apex]
        rim = mix(P.edge, P.glow, 0.30) if not tower.far else P.edge_dim
        pygame.draw.lines(screen, scale(rim, 0.40 + 0.60 * tower.dim),
                          False, [(x * S, y * S) for x, y in left], 2)
        pygame.draw.lines(screen, scale(P.edge_dim, 0.24 + 0.5 * tower.dim),
                          False, [(x * S, y * S) for x, y in right], 1)
        pygame.draw.line(screen, scale(P.edge_dim, 0.35 * tower.dim),
                         (tower.cx - tower.top_w * 0.5 * S, sh_y * S),
                         (tower.cx + tower.top_w * 0.5 * S, sh_y * S), 1)

        if record:
            self.mask_polys.append(tower.poly)

    def _draw_fins(self, screen: pygame.Surface) -> None:
        S = self.S
        for (x1, y1, x2, y2, x3, y3) in self.lay["castle"]["fins"]:
            pts = [(x1 * S, y1 * S), (x2 * S, y2 * S), (x3 * S, y3 * S)]
            pygame.draw.polygon(screen, (13, 20, 37), pts)
            pygame.draw.aalines(screen, scale(P.edge_dim, 0.55), True, pts)
            pygame.draw.aaline(screen, scale(P.face_lit, 0.55),
                               (x1 * S, y1 * S), (x2 * S, y2 * S))
            self.mask_polys.append(((x1, y1), (x2, y2), (x3, y3)))

    def _draw_wall(self, screen: pygame.Surface) -> None:
        x0, x1, base_y, top_y, spike = self.lay["castle"]["wall"]
        S = self.S
        points = [(x0, base_y)]
        x = x0
        step = (x1 - x0) / 9.0
        i = 0
        while x <= x1 + 0.1:
            h = spike + (7 if i % 2 == 0 else 0)
            points.append((x, top_y))
            points.append((x + step * 0.26, top_y - h))
            points.append((x + step * 0.52, top_y))
            x += step
            i += 1
        points.append((x1, base_y))

        pygame.draw.polygon(screen, (14, 21, 38),
                            [(px * S, py * S) for px, py in points])
        for y in range(int(top_y * S), int(base_y * S)):
            t = (y / S - top_y) / max(1.0, base_y - top_y)
            col = mix((34, 49, 78), (14, 20, 36), smoothstep(t))
            pygame.draw.line(screen, col, (x0 * S, y), (x1 * S, y))
        top_pts = [(px * S, py * S) for px, py in points]
        pygame.draw.aalines(screen, mix(P.edge_dim, P.edge, 0.40), False,
                            top_pts[1:-1])

        for i in range(8):
            bx = x0 + (x1 - x0) * (i + 0.5) / 8
            pygame.draw.line(screen, (10, 15, 28),
                             (bx * S, top_y * S), (bx * S, base_y * S), 2)
            pygame.draw.aaline(screen, scale(P.edge_dim, 0.35),
                               (bx * S, top_y * S), (bx * S, base_y * S))
        for i in range(7):
            wx = x0 + (x1 - x0) * (i + 0.5) / 7
            wy = top_y + 16
            self._warm_window(screen, wx, wy, 2.6, 0.50, 0.55)
        self.mask_polys.append(tuple(points))

    def _draw_plinth(self, screen: pygame.Surface) -> None:
        """A low crenellated terrace in front of the tower feet."""
        S = self.S
        x0, x1, base_y, top_y, spike = self.lay["castle"]["plinth"]
        points = [(x0, base_y)]
        x = x0
        step = (x1 - x0) / 11.0
        i = 0
        while x <= x1 + 0.1:
            h = spike + (4 if i % 2 == 0 else 0)
            points.append((x, top_y))
            points.append((x + step * 0.30, top_y - h))
            points.append((x + step * 0.60, top_y))
            x += step
            i += 1
        points.append((x1, base_y))
        pygame.draw.polygon(screen, (16, 24, 42),
                            [(px * S, py * S) for px, py in points])
        for y in range(int(top_y * S), int(base_y * S)):
            t = (y / S - top_y) / max(1.0, base_y - top_y)
            col = mix((38, 54, 84), (15, 22, 39), smoothstep(t))
            pygame.draw.line(screen, col, (x0 * S, y), (x1 * S, y))
        top_pts = [(px * S, py * S) for px, py in points]
        pygame.draw.aalines(screen, mix(P.edge_dim, P.edge, 0.55), False,
                            top_pts[1:-1])
        for i in range(5):
            wx = x0 + (x1 - x0) * (i + 0.5) / 5
            pygame.draw.line(screen, (9, 14, 26),
                             (wx * S, top_y * S), (wx * S, base_y * S), 2)
        self.mask_polys.append(tuple(points))

    def _draw_reflection(self, screen: pygame.Surface) -> None:
        if not self.mask_polys:
            return
        mask = pygame.Surface((self.pw, self.ph), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        for poly in self.mask_polys:
            pygame.draw.polygon(mask, (255, 255, 255, 255),
                                [(x * self.S, y * self.S) for x, y in poly])

        ref = pygame.Surface((self.pw, self.ph), pygame.SRCALPHA)
        ref.blit(self.aurora_ss, (0, 0))
        ref.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        k = int(255 * self.lay["reflection"])
        ref.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(ref, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    # ---------------------------------------------------------------- lights

    def _warm_window(self, screen: pygame.Surface, x: float, y: float,
                     w: float, brightness: float, glow_scale: float) -> None:
        S = self.S
        w = max(1.0, w)
        h = w * 2.7
        gw = int(26 * glow_scale * S * 0.5)
        if gw > 2:
            sprite = self._tint(self.glow, scale(P.warm, 0.55 * brightness))
            sprite = pygame.transform.smoothscale(sprite, (gw, gw))
            screen.blit(sprite, (int(x * S - gw * 0.5),
                                 int(y * S - gw * 0.5)),
                        special_flags=pygame.BLEND_RGB_ADD)
        col = mix(P.warm_dim, P.warm_hi, 0.35 + 0.65 * brightness)
        rect = pygame.Rect(int((x - w * 0.5) * S), int((y - h * 0.5) * S),
                           max(1, int(w * S)), max(1, int(h * S)))
        pygame.draw.rect(screen, col, rect,
                         border_radius=max(1, int(w * S * 0.4)))
        if brightness > 0.7:
            inner = rect.inflate(-max(1, rect.w // 2), -max(1, rect.h // 3))
            pygame.draw.rect(screen, mix(P.warm, P.warm_hi, 0.55), inner,
                             border_radius=max(1, rect.w // 3))

    def _draw_windows(self, screen: pygame.Surface) -> None:
        for (x, y, w, b, dim) in self.window_sprites:
            self._warm_window(screen, x, y, w, b, 0.55 + 0.65 * dim)

        gx, gy, gw, gh = self.lay["castle"]["gate"]
        S = self.S
        pool = self._tint(self.glow, (46, 32, 19))
        pool = pygame.transform.smoothscale(pool, (int(gw * 3.8 * S),
                                                  int(gw * 1.8 * S)))
        screen.blit(pool, (int(gx * S - gw * 1.9 * S),
                           int((gy - 2) * S - gw * 0.9 * S)),
                    special_flags=pygame.BLEND_RGB_ADD)
        rect = pygame.Rect(int((gx - gw * 0.5) * S), int((gy - gh) * S),
                           int(gw * S), int(gh * S))
        pygame.draw.rect(screen, (120, 74, 42), rect,
                         border_radius=int(gw * 0.20 * S))
        outer = rect.inflate(int(gw * 0.18 * S), int(gw * 0.18 * S))
        pygame.draw.rect(screen, (232, 168, 104), outer, 2,
                         border_radius=int(gw * 0.22 * S))
        inner = pygame.Rect(rect.x + max(1, rect.w // 5),
                            rect.y + max(1, rect.h // 4),
                            max(1, rect.w * 3 // 5), max(1, rect.h * 3 // 4))
        pygame.draw.rect(screen, P.warm_hi, inner,
                         border_radius=int(gw * 0.18 * S))
        sprite = self._tint(self.glow, (54, 36, 18))
        sprite = pygame.transform.smoothscale(sprite,
                                              (int(gw * 2.4 * S),
                                               int(gw * 2.4 * S)))
        screen.blit(sprite, (int(gx * S - gw * 1.2 * S),
                             int((gy - gh * 0.5) * S - gw * 1.2 * S)),
                    special_flags=pygame.BLEND_RGB_ADD)

    def _draw_tips(self, screen: pygame.Surface) -> None:
        S = self.S
        for i, tower in enumerate(self.towers):
            x = (tower.cx + tower.lean) * S
            y = tower.tip_y * S
            brightness = 0.55 if i == 0 else 0.34 if i in (1, 2) else 0.22
            g = int((10 if i == 0 else 7) * S)
            sprite = self._tint(self.glow, scale(P.glow, brightness))
            sprite = pygame.transform.smoothscale(sprite, (g, g))
            screen.blit(sprite, (int(x - g * 0.5), int(y - g * 0.5)),
                        special_flags=pygame.BLEND_RGB_ADD)
            d = 2 if i == 0 else 1
            pygame.draw.polygon(screen, scale(mix(P.edge, P.glow, 0.5),
                                             0.55 + brightness),
                                [(x, y - d * S), (x + d * S, y),
                                 (x, y + d * S), (x - d * S, y)])
        for i in (0, 1, 2):
            tower = self.towers[i]
            x = (tower.cx + tower.lean) * S
            y = tower.tip_y * S
            arm = int(6 * S)
            pygame.draw.line(screen, scale(P.glow, 0.20),
                             (x - arm, y), (x + arm, y), 1)
            pygame.draw.line(screen, scale(P.glow, 0.20),
                             (x, y - arm), (x, y + arm), 1)

    # ---------------------------------------------------------------- shards

    def _draw_shard(self, screen: pygame.Surface, x: float, y: float,
                    length: float, width: float, angle: float,
                    bright: float) -> None:
        S = self.S
        a = math.radians(angle)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        tip = (x + ux * length * 0.5, y + uy * length * 0.5)
        tail = (x - ux * length * 0.5, y - uy * length * 0.5)
        mid = (x + ux * length * 0.05, y + uy * length * 0.05)
        left = (mid[0] + px * width * 0.5, mid[1] + py * width * 0.5)
        right = (mid[0] - px * width * 0.5, mid[1] - py * width * 0.5)
        poly = [tip, left, tail, right]
        fill = mix((28, 42, 70), P.glow, 0.20 * bright)
        pygame.draw.polygon(screen, fill,
                            [(p[0] * S, p[1] * S) for p in poly])
        pygame.draw.aalines(screen, scale(mix(P.edge, P.glow, 0.55), bright),
                            True, [(p[0] * S, p[1] * S) for p in poly])
        pygame.draw.aaline(screen, scale(P.face_lit, bright * 0.85),
                           (tail[0] * S, tail[1] * S),
                           (tip[0] * S, tip[1] * S))
        pygame.draw.aaline(screen, scale(P.glow, bright * 0.35),
                           (left[0] * S, left[1] * S),
                           ((tail[0] + tip[0]) * 0.5 * S,
                            (tail[1] + tip[1]) * 0.5 * S))
        g = max(2, int(width * 1.8 * S))
        sprite = self._tint(self.glow, scale(P.glow, bright * 0.75))
        sprite = pygame.transform.smoothscale(sprite, (g, g))
        screen.blit(sprite, (int(tip[0] * S - g * 0.5),
                             int(tip[1] * S - g * 0.5)),
                    special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(screen, scale(P.glow, bright),
                           (int(tip[0] * S), int(tip[1] * S)), 1)

    def _draw_shards(self, screen: pygame.Surface) -> None:
        for (x, y, length, width, angle, bright) in self.lay["shards"]:
            self._draw_shard(screen, x, y, length, width, angle, bright)

    # ----------------------------------------------------------------- cliff

    def _draw_cliff(self, screen: pygame.Surface) -> None:
        S = self.S
        lip = [(x * S, y * S) for x, y in self.lay["lip"]]
        face = lip + [(self.pw, self.ph), (0, self.ph)]
        pygame.draw.polygon(screen, P.cliff_face, face)

        y0 = min(y for _, y in self.lay["lip"])
        for y in range(int(y0 * S), self.ph):
            t = (y / S - y0) / max(1.0, self.H - y0)
            col = mix(P.cliff_top, P.cliff_bottom, smoothstep(t))
            pygame.draw.line(screen, col, (0, y), (self.pw, y))

        rng = random.Random(SEED ^ 0x1CE)
        for _ in range(42 if self.layout_name == "landscape" else 96):
            x = rng.uniform(-20, self.W + 20)
            top = rng.uniform(y0 + 2, y0 + (self.H - y0) * 0.30)
            length = rng.uniform((self.H - y0) * 0.18, (self.H - y0) * 0.55)
            drift = rng.uniform(-34, 34)
            col = mix(P.cliff_face, P.cliff_edge, rng.uniform(0.10, 0.40))
            pygame.draw.aaline(screen, col, (x * S, top * S),
                               ((x + drift) * S,
                                min(self.H, top + length) * S))
        for _ in range(18 if self.layout_name == "landscape" else 52):
            y = rng.uniform(y0 + 8, self.H - 10)
            x = rng.uniform(0, self.W)
            w = rng.uniform(14, 96)
            col = mix(P.cliff_face, P.snow_dim, rng.uniform(0.12, 0.34))
            pygame.draw.line(screen, col, (x * S, y * S),
                             ((x + w) * S, (y + rng.uniform(-2, 2)) * S), 1)
        for _ in range(3 if self.layout_name == "landscape" else 7):
            x = rng.uniform(self.W * 0.05, self.W * 0.95)
            top = rng.uniform(y0 + 6, y0 + 24)
            bottom = rng.uniform(top + 30, self.H - 12)
            col = mix(P.cliff_face, P.accent_dim, rng.uniform(0.12, 0.26))
            pygame.draw.line(screen, col, (x * S, top * S),
                             ((x + rng.uniform(-3, 3)) * S, bottom * S), 1)

        pygame.draw.aalines(screen, mix(P.snow_dim, P.snow, 0.35), False, lip)
        for i in range(len(lip) - 1):
            xa, ya = lip[i]
            xb, yb = lip[i + 1]
            pygame.draw.line(screen, (8, 12, 22),
                             (xa, ya + 2 * S), (xb, yb + 2 * S), 2)

    def _draw_buttresses(self, screen: pygame.Surface) -> None:
        """Near rock shoulders climbing the cliff, in front of the face."""
        S = self.S
        rng = random.Random(SEED ^ 0x2B7)
        for i, points in enumerate(self.lay.get("buttresses", ())):
            pts = [(x * S, y * S) for x, y in points]
            pygame.draw.polygon(screen, (13, 19, 32), pts)
            top = [(x * S, y * S) for x, y in points[:len(points) - 2]]
            pygame.draw.aalines(screen, scale(P.snow_dim, 0.58), False, top)
            for j in range(len(points) - 3):
                (x, y), (nx, ny) = points[j], points[j + 1]
                if ny < y:
                    pygame.draw.aaline(screen, scale(P.snow, 0.58),
                                       (x * S, y * S), (nx * S, ny * S))
            for _ in range(8):
                x = rng.uniform(points[0][0], points[len(points) // 2][0])
                y = rng.uniform(points[0][1], self.H - 20)
                pygame.draw.aaline(screen, scale(P.cliff_edge, 0.34),
                                   (x * S, y * S),
                                   ((x + rng.uniform(-30, 30)) * S,
                                    min(self.H, y + rng.uniform(30, 120)) * S))
            for _ in range(2):
                x = rng.uniform(points[0][0], points[len(points) // 2][0])
                y = rng.uniform(points[0][1] + 10, self.H - 24)
                pygame.draw.line(screen, scale(P.snow_dim, 0.22),
                                 (x * S, y * S),
                                 ((x + rng.uniform(10, 46)) * S, y * S), 1)

    def _draw_masses(self, screen: pygame.Surface) -> None:
        S = self.S
        for points, dim in ((self.lay["mass_left"], 1.0),
                            (self.lay["mass_right"], 0.9)):
            pts = [(x * S, y * S) for x, y in points]
            pygame.draw.polygon(screen, (7, 11, 20), pts)
            pygame.draw.aalines(screen, scale(P.cliff_edge, 0.58), False, pts)
            top = pts[:-2]
            pygame.draw.aalines(screen, scale(P.snow_dim, 0.58), False, top)
            for i in range(len(points) - 3):
                (x, y), (nx, ny) = points[i], points[i + 1]
                if ny < y:
                    pygame.draw.aaline(screen, scale(P.snow, 0.28),
                                       (x * S, y * S), (nx * S, ny * S))

        if "foreground_ridge" in self.lay:
            points = self.lay["foreground_ridge"]
            pts = [(x * S, y * S) for x, y in points]
            pygame.draw.polygon(screen, (3, 5, 10), pts)
            pygame.draw.aalines(screen, scale(P.snow_dim, 0.22), False,
                                pts[:-2])

    # ------------------------------------------------------------------ snow

    def _draw_snow(self, screen: pygame.Surface) -> None:
        S = self.S
        guard = pygame.Rect(0, self.H - 40, 100, 40)
        for (x, y, size, b) in self.snow_far:
            if guard.collidepoint(x, y):
                continue
            col = scale(P.snow, b * 0.74)
            pygame.draw.circle(screen, col, (int(x * S), int(y * S)),
                               max(1, size // 2))
        for (x, y, size, b) in self.snow_near:
            if guard.collidepoint(x, y):
                continue
            col = scale(mix(P.snow, P.glow, 0.4), b * 0.70)
            if size >= 5:
                gw = int(size * S * 1.6)
                sprite = self._tint(self.flake, col)
                sprite = pygame.transform.smoothscale(sprite, (gw, gw))
                screen.blit(sprite, (int(x * S - gw * 0.5),
                                     int(y * S - gw * 0.5)),
                            special_flags=pygame.BLEND_RGB_ADD)
            else:
                pygame.draw.circle(screen, col, (int(x * S), int(y * S)),
                                   max(1, size // 2))
        for (x, y, b) in self.sparkles:
            g = max(2, int(5 * S))
            sprite = self._tint(self.glow, scale(P.glow, b * 0.55))
            sprite = pygame.transform.smoothscale(sprite, (g, g))
            screen.blit(sprite, (int(x * S - g * 0.5), int(y * S - g * 0.5)),
                        special_flags=pygame.BLEND_RGB_ADD)

    # --------------------------------------------------------------- compose

    def render(self) -> pygame.Surface:
        screen = pygame.Surface((self.pw, self.ph)).convert()
        self._draw_sky(screen)
        self.aurora_ss = self._render_aurora()
        screen.blit(self.aurora_ss, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self._draw_ridge(screen)
        self._draw_plateau(screen)
        self._draw_ground_shadows(screen)

        for tower in self.far_towers:
            self._draw_tower(screen, tower, record=False)
        self._draw_wall(screen)
        for tower in self.towers:
            self._draw_tower(screen, tower, record=True)
        self._draw_fins(screen)
        self._draw_plinth(screen)
        for tower in self.gatehouses:
            self._draw_tower(screen, tower, record=True)

        self._draw_reflection(screen)
        for tower in self.towers:
            self._draw_facets(screen, tower)
        self._draw_windows(screen)
        self._draw_tips(screen)
        self._draw_shards(screen)
        self._draw_cliff(screen)
        self._draw_buttresses(screen)
        self._draw_masses(screen)
        self._draw_snow(screen)

        frame = pygame.transform.smoothscale(screen, (self.W, self.H))
        self._apply_bloom(frame)
        self._apply_finish(frame)
        self._draw_hud(frame)
        return frame

    def _draw_facets(self, screen: pygame.Surface, tower: Tower) -> None:
        S = self.S
        apex = ((tower.cx + tower.lean) * S, tower.tip_y * S)
        for u in (0.34, 0.68):
            xb = tower.cx + (u - 0.5) * tower.base_w
            pygame.draw.aaline(screen,
                               scale(mix(P.face_hi, P.ink, 0.30),
                                     0.40 + 0.50 * tower.dim),
                               (xb * S, tower.base_y * S), apex)
        # One long, cool highlight: the glass catching the aurora.
        xl, xr = tower.edges_at(0.08)
        hx = (xl + (xr - xl) * 0.20) * S
        pygame.draw.aaline(screen, scale(mix(P.glow, P.ink, 0.30),
                                         0.30 * tower.dim),
                           (hx, tower.base_y * S),
                           (hx + tower.lean * 0.5 * S,
                            tower.shoulder_y * S))
        for v in (0.32, 0.58, 0.80):
            xl, xr = tower.edges_at(v)
            yy = (tower.base_y - (tower.base_y - tower.shoulder_y) * v) * S
            pygame.draw.aaline(screen,
                               scale(mix(P.face_hi, P.ink, 0.25),
                                     0.18 + 0.25 * tower.dim),
                               (xl * S, yy), (xr * S, yy))
            pygame.draw.aaline(screen,
                               scale(P.face_lit, 0.22 * tower.dim),
                               ((xl + (xr - xl) * 0.12) * S, yy - 2 * S),
                               ((xl + (xr - xl) * 0.30) * S, yy - 2 * S))
        for (u0, v0, u1, v1) in ((0.26, 0.10, 0.58, 0.48),
                                 (0.74, 0.10, 0.42, 0.48),
                                 (0.34, 0.56, 0.56, 0.84)):
            xa0, xa1 = tower.edges_at(v0)
            xb0, xb1 = tower.edges_at(v1)
            xa = xa0 + (xa1 - xa0) * u0
            xb = xb0 + (xb1 - xb0) * u1
            ya = (tower.base_y - (tower.base_y - tower.shoulder_y) * v0) * S
            yb = (tower.base_y - (tower.base_y - tower.shoulder_y) * v1) * S
            pygame.draw.aaline(screen, scale(mix(P.face_hi, P.glow, 0.30),
                                             0.44 * tower.dim),
                               (xa * S, ya), (xb * S, yb))

    def _apply_bloom(self, frame: pygame.Surface) -> None:
        w, h = frame.get_size()
        div = 6
        small = pygame.transform.smoothscale(
            frame, (max(2, w // div), max(2, h // div)))
        k = int(24 + 112 * self.lay["bloom"])
        small.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        mid = pygame.transform.smoothscale(small, (max(2, w // 2),
                                                   max(2, h // 2)))
        up = pygame.transform.smoothscale(mid, (w, h))
        frame.blit(up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _apply_finish(self, frame: pygame.Surface) -> None:
        w, h = frame.get_size()
        qw, qh = max(2, w // 4), max(2, h // 4)
        small = pygame.Surface((qw, qh)).convert()
        cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(qh):
            for x in range(qw):
                r = math.hypot(x - cx, y - cy) / maxd
                dark = 0.34 * (max(0.0, r - 0.22) / 0.78) ** 1.6
                k = int(255 * max(0.10, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (w, h))
        for y in range(0, h, 3):
            k = int(255 * (1.0 - 4.0 / 255.0))
            pygame.draw.line(finish, (k, k, k), (0, y), (w, y), 1)
        top_h = max(44, int(h * 0.10))
        for y in range(top_h):
            t = (y / max(1, top_h - 1)) ** 2.0
            k = int(52 + 203 * t)
            pygame.draw.line(finish, (k, k, k), (0, y), (w, y))
        frame.blit(finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # ------------------------------------------------------------------- HUD

    def _text(self, screen, text, pos, color, font, align="left", shadow=True):
        if shadow:
            sh = font.render(text, True, (2, 4, 8))
            r = sh.get_rect()
            if align == "right":
                r.topright = (int(pos[0]) + 1, int(pos[1]) + 1)
            elif align == "center":
                r.midtop = (int(pos[0]) + 1, int(pos[1]) + 1)
            else:
                r.topleft = (int(pos[0]) + 1, int(pos[1]) + 1)
            screen.blit(sh, r)
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if align == "right":
            rect.topright = (int(pos[0]), int(pos[1]))
        elif align == "center":
            rect.midtop = (int(pos[0]), int(pos[1]))
        else:
            rect.topleft = (int(pos[0]), int(pos[1]))
        screen.blit(surf, rect)
        return rect

    def _tracked(self, screen, text, font, color, topleft, tracking):
        x, y = topleft
        for ch in text:
            surf = font.render(ch, True, color)
            screen.blit(surf, (int(x), int(y)))
            x += surf.get_width() + tracking
        return x

    def _tracked_width(self, text, font, tracking):
        return sum(font.size(ch)[0] + tracking for ch in text) - tracking

    def _draw_hud(self, frame: pygame.Surface) -> None:
        w, h = self.W, self.H
        m = self.lay["margin"]
        tiny = max(11, self.lay["small_px"])

        title_font = pygame.font.SysFont("dejavuserif", self.lay["title_px"])
        body_font = pygame.font.SysFont("dejavusansmono",
                                        self.lay["telemetry_px"])
        small_font = pygame.font.SysFont("dejavusansmono", tiny)

        arm = 12 if self.layout_name == "landscape" else 20
        for x, y, dx, dy in ((m, m, 1, 1),
                             (w - m - 1, m, -1, 1),
                             (w - m - 1, h - m - 1, -1, -1),
                             (m, h - m - 1, 1, -1)):
            pygame.draw.line(frame, P.hud_faint, (x, y), (x + dx * arm, y), 1)
            pygame.draw.line(frame, P.hud_faint, (x, y), (x, y + dy * arm), 1)

        title = "THE GLASS CASTLE"
        tw = self._tracked_width(title, title_font, self.lay["title_track"])
        self._tracked(frame, title, title_font, P.hud,
                      (m, m - 1), self.lay["title_track"])
        rule_y = m + title_font.get_height() + 2
        pygame.draw.line(frame, P.accent_dim, (m, rule_y),
                         (m + int(tw * 0.78), rule_y), 1)
        pygame.draw.line(frame, mix(P.accent, P.glow, 0.4),
                         (m, rule_y), (m + int(tw * 0.18), rule_y), 1)

        tele = "AURORA 07 // -12 C"
        tr = self._text(frame, tele, (w - m, m + 1), P.hud_dim, body_font,
                        "right")
        dx = tr.left - 12 if self.layout_name == "landscape" else tr.left - 18
        dy = tr.centery
        d = 3 if self.layout_name == "landscape" else 5
        pygame.draw.polygon(frame, P.accent,
                            [(dx, dy - d), (dx + d, dy),
                             (dx, dy + d), (dx - d, dy)])

        if self.layout_name == "portrait":
            self._text(frame, "WIND CALM // 2 SNOW LAYERS",
                       (w - m, tr.bottom + 6), P.hud_faint, small_font,
                       "right")
        self._text(frame, "CAMERA +0.5 PX/S", (w - m, h - m - tiny - 1),
                   P.hud_faint, small_font, "right")


# --------------------------------------------------------------------- main

def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((64, 64))

    cases = (
        ("landscape", "study_1280x400.png"),
        ("portrait", "study_1080x1920.png"),
    )
    for layout, name in cases:
        study = GlassCastleStudy(layout)
        frame = study.render()
        path = os.path.join(OUT_DIR, name)
        pygame.image.save(frame, path)

        corner = frame.subsurface(pygame.Rect(0, study.H - 32, 80, 32))
        avg = pygame.transform.average_color(corner)
        mean = sum(avg[:3]) / 3.0
        peak = max(sum(corner.get_at((x, y))[:3]) / 3.0
                   for x in range(0, 80, 4) for y in range(0, 32, 4))
        print(f"{name}: {study.W}x{study.H}  seed={SEED} t={REVIEW_TIME:g}s  "
              f"corner_mean={mean:.1f} corner_max={peak:.1f}  -> {path}")

    pygame.quit()


if __name__ == "__main__":
    main()
