"""Art-direction prototype for The Long Archive (SLOW_WORLDS_DESIGN.md 5.7).

This is a still-frame study, not the mode.  It draws the scene at the two
target aspect ratios (1280x400 strip, 1080x1920 portrait) so the composition
can be reviewed before any mode/registry/profile code is written.

The scene: a deep-space vault of floating monoliths, one slab lit by a
traveling bar of light, its glyphs resolving into one readable line.  No
floor, no shelves, no reader.  The readable line sits beneath the lit slab,
as an archival translation rather than on-screen UI.

Run:
    ./.venv/bin/python designs/long_archive_proto/gen_archive.py
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
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "long_archive")
SEED = 5709

# ------------------------------------------------------------------ palette

RGB = tuple[int, int, int]


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


class Palette:
    """Deep Blue & Bone (design doc 4.1), bone variant."""

    name = "bone"
    bg_top = (1, 4, 10)
    bg_bottom = (0, 1, 3)
    haze = (14, 30, 54)
    star = (140, 166, 198)

    face_top = (8, 15, 26)
    face_bottom = (2, 4, 8)
    side = (1, 3, 6)

    ink = (220, 230, 242)
    ink_dim = (102, 132, 160)
    structure = (56, 112, 162)
    detail = (26, 58, 92)
    accent = (127, 224, 232)
    accent_dim = (52, 104, 114)
    glow = (169, 216, 232)
    warm = (242, 200, 121)
    lore = (236, 232, 218)

    hud = (198, 218, 236)
    hud_dim = (96, 136, 168)
    hud_faint = (38, 74, 108)


P = Palette()


# ------------------------------------------------------------------ geometry

class Slab:
    def __init__(self, sid: int, cx: float, cy: float, w: float, h: float,
                 depth: float, brightness: float, *, yaw: float = 0.0,
                 taper: float = 0.05, thickness: int = 8,
                 focus: bool = False, label: str = "", text: float = 1.0):
        self.id = sid
        self.cx = cx
        self.cy = cy
        self.w = w
        self.h = h
        self.depth = depth
        self.brightness = brightness
        self.yaw = yaw
        self.taper = taper
        self.thickness = thickness
        self.focus = focus
        self.label = label
        self.text_density = max(0.0, min(1.0, text))

        self.y0 = cy - h
        self.y1 = cy + h
        top_half = w * (1.0 - taper * 0.5)
        bot_half = w * (1.0 + taper * 0.5)
        self.qx = (cx - top_half + yaw * 0.5, cx + top_half + yaw * 0.5,
                   cx + bot_half - yaw * 0.5, cx - bot_half - yaw * 0.5)
        self.qy = (self.y0, self.y0, self.y1, self.y1)
        self.rng = random.Random((SEED * 7349 + sid * 911) & 0x7FFFFFFF)
        self.rows = []
        self.pad_x = 0.0
        self.pad_y = 0.0
        self.pad_bottom = 0.0

    def edges_at(self, y: float):
        t = (y - self.y0) / max(1.0, self.y1 - self.y0)
        xl = self.qx[0] + (self.qx[3] - self.qx[0]) * t
        xr = self.qx[1] + (self.qx[2] - self.qx[1]) * t
        return xl, xr


#: A small alphabet of invented strokes.  The script is deliberately made of
#: line segments, so it reads as etching rather than as corrupted Latin.
GLYPHS = (
    (((0.5, 0.12), (0.5, 0.88)),),
    (((0.18, 0.5), (0.82, 0.5)),),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.3), (0.8, 0.3))),
    (((0.25, 0.12), (0.25, 0.88)), ((0.25, 0.5), (0.8, 0.5))),
    (((0.2, 0.18), (0.8, 0.82)), ((0.2, 0.82), (0.8, 0.18))),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.3, 0.12), (0.7, 0.12))),
    (((0.2, 0.15), (0.2, 0.85)), ((0.2, 0.85), (0.8, 0.85))),
    (((0.2, 0.15), (0.8, 0.15)), ((0.2, 0.15), (0.5, 0.5)),
     ((0.8, 0.15), (0.5, 0.5)), ((0.5, 0.5), (0.5, 0.88))),
    (((0.25, 0.25), (0.75, 0.25)), ((0.25, 0.5), (0.75, 0.5)),
     ((0.25, 0.75), (0.75, 0.75))),
    (((0.5, 0.1), (0.5, 0.55)), ((0.5, 0.55), (0.25, 0.9)),
     ((0.5, 0.55), (0.75, 0.9))),
    (((0.2, 0.2), (0.2, 0.8)), ((0.2, 0.2), (0.8, 0.2)),
     ((0.8, 0.2), (0.8, 0.8))),
    (((0.2, 0.5), (0.8, 0.5)), ((0.5, 0.2), (0.5, 0.8)),
     ((0.2, 0.2), (0.8, 0.8))),
    (((0.3, 0.15), (0.7, 0.15)), ((0.3, 0.4), (0.7, 0.4)),
     ((0.5, 0.4), (0.5, 0.88))),
    (((0.2, 0.15), (0.2, 0.85)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.8, 0.2), (0.8, 0.8))),
    (((0.5, 0.15), (0.5, 0.85)), ((0.2, 0.7), (0.8, 0.3))),
    (((0.25, 0.2), (0.75, 0.5)), ((0.75, 0.5), (0.25, 0.8))),
    (((0.2, 0.2), (0.8, 0.2)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.2, 0.8), (0.8, 0.8))),
    (((0.35, 0.15), (0.35, 0.85)), ((0.65, 0.15), (0.65, 0.85)),
     ((0.2, 0.5), (0.8, 0.5))),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.8), (0.8, 0.8))),
    (((0.2, 0.3), (0.8, 0.3)), ((0.2, 0.3), (0.2, 0.8)),
     ((0.2, 0.8), (0.5, 0.55))),
    (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8)),
     ((0.2, 0.5), (0.8, 0.5))),
    (((0.5, 0.15), (0.5, 0.5)), ((0.2, 0.85), (0.8, 0.85))),
    (((0.25, 0.5), (0.75, 0.5)), ((0.5, 0.15), (0.5, 0.85)),
     ((0.25, 0.15), (0.25, 0.85))),
    (((0.15, 0.35), (0.85, 0.35)), ((0.15, 0.65), (0.85, 0.65)),
     ((0.5, 0.15), (0.5, 0.85))),
    (((0.2, 0.2), (0.5, 0.5)), ((0.5, 0.5), (0.8, 0.2)),
     ((0.5, 0.5), (0.5, 0.85))),
    (((0.5, 0.1), (0.5, 0.9)), ((0.2, 0.1), (0.8, 0.1)),
     ((0.2, 0.9), (0.8, 0.9))),
    (((0.2, 0.5), (0.8, 0.5)), ((0.65, 0.2), (0.8, 0.5)),
     ((0.65, 0.8), (0.8, 0.5))),
    (((0.3, 0.2), (0.7, 0.2)), ((0.3, 0.2), (0.3, 0.55)),
     ((0.7, 0.2), (0.7, 0.55)), ((0.3, 0.55), (0.7, 0.9))),
)


def build_rows(slab: Slab, cell_px: float, pitch_px: float,
               pad_x: float, pad_y: float, pad_bottom: float | None = None) -> None:
    """Lay out etched rows in local face space.

    Rows are broken into short entries with indents and gaps, so the face
    reads as an inscription rather than a spreadsheet.  `text` lets the far
    slabs keep only a suggestion of writing, which is what keeps them from
    reading as UI cards.
    """
    slab.rows = []
    if pad_bottom is None:
        pad_bottom = pad_y
    slab.pad_x = pad_x
    slab.pad_y = pad_y
    slab.pad_bottom = pad_bottom
    inner_w = 2 * slab.w - 2 * pad_x
    inner_h = 2 * slab.h - pad_y - pad_bottom
    if inner_w <= 8 or inner_h <= 8 or slab.text_density <= 0.0:
        return
    cells = max(3, int(inner_w / cell_px))
    count = max(2, int(inner_h / pitch_px))
    rng = slab.rng

    row = 0
    while row < count:
        # Paragraph breaks give the inscription a rhythm.  The monument is
        # dense; the side panels are allowed to weather away.
        if row and rng.random() < (0.05 if slab.focus else 0.20):
            row += rng.choice((1, 1, 2))
            continue
        if rng.random() > slab.text_density:
            row += 1
            continue
        v = (row + 0.5) / count
        indent = rng.choice((0, 0, 0, 1, 1, 2, 3, 4, 5))
        if slab.focus:
            trim = rng.choice((0, 0, 1, 1, 2, 3, 6))
        else:
            trim = rng.choice((0, 1, 2, 4, 7, 10, 14))
        length = cells - indent - trim
        if length < 3:
            row += 1
            continue
        glyphs = [rng.randrange(len(GLYPHS)) for _ in range(length)]
        # Weathered rows: a fraction of the inscription is almost gone.
        if slab.focus:
            wear = rng.choice((1.0, 1.0, 1.0, 1.0, 1.0, 0.92))
        else:
            wear = rng.choice((1.0, 0.85, 0.65, 0.45, 0.28))
        slab.rows.append((v, indent, cells, glyphs, wear))
        # Occasional double-spaced line.
        row += 2 if rng.random() < (0.03 if slab.focus else 0.12) else 1


# ------------------------------------------------------------------ renderer

class ArchiveRenderer:
    def __init__(self, size, layout: str):
        self.sw, self.sh = size
        self.layout = layout
        self.portrait = layout == "portrait"
        self.unit = max(10, min(28, int(min(self.sw, self.sh) * 0.028)))
        self.margin = max(16, int(min(self.sw, self.sh) * 0.036))
        self.slabs: list[Slab] = []
        self.bar_fraction = 0.72 if self.portrait else 0.66
        self.focus_id = 4
        self.time_s = 0.0
        self._cache: dict = {}
        self.caption = "we kept the light on for whoever came next"
        self.caption_font_px = 28 if self.portrait else 18
        self.caption_gap = 58 if self.portrait else 24
        self._build_layout()
        self._build_background()
        self._build_finish()
        self._build_glow()
        self._build_stars()
        self._build_motes()
        self._build_fonts()

    # -------------------------------------------------------------- layout

    def _flat_slab(self, x: float, width: float, top: float, bottom: float,
                   brightness: float, text: float, *, focus: bool = False,
                   label: str = "") -> Slab:
        """One panel of the archive wall: frontal, same plane, common top/bottom."""
        return Slab(0, x + width * 0.5, (top + bottom) * 0.5, width * 0.5,
                    (bottom - top) * 0.5, 0.0, brightness,
                    yaw=0.0, taper=0.0, thickness=0, focus=focus,
                    label=label, text=text)

    def _build_layout(self):
        """A flat wall with the active panel at 75% of the display width.

        The current slab is the wide centre tablet.  What remains of the frame
        is taken by two narrow neighbours that run off the sides, so the wall
        still reads as one plane and one continuous archive.  Everything shares
        the same top line and bottom line; there is no depth scatter.
        """
        if self.portrait:
            top, bottom = 360.0, 1540.0
            self.focus = self._flat_slab(135, 810, top, bottom, 1.0, 1.0,
                                         focus=True, label="TL-0447")
            self.focus.id = 4
            self.focus.rng = random.Random(SEED * 7349 + 4 * 911)
            self.slabs = [
                self._flat_slab(-45, 160, top, bottom, 0.24, 0.55),
                self.focus,
                self._flat_slab(965, 160, top, bottom, 0.24, 0.55),
            ]
            self.slabs[0].id, self.slabs[2].id = 3, 5
            self.slabs[0].rng = random.Random(SEED * 7349 + 3 * 911)
            self.slabs[2].rng = random.Random(SEED * 7349 + 5 * 911)
            for slab in self.slabs:
                if slab.focus:
                    build_rows(slab, 19.0, 25.0, 26.0, 30.0, pad_bottom=60.0)
                else:
                    build_rows(slab, 13.0, 22.0, 12.0, 24.0, pad_bottom=22.0)
        else:
            top, bottom = 64.0, 328.0
            self.focus = self._flat_slab(160, 960, top, bottom, 1.0, 1.0,
                                         focus=True, label="TL-0447")
            self.focus.id = 4
            self.focus.rng = random.Random(SEED * 7349 + 4 * 911)
            self.slabs = [
                self._flat_slab(-64, 200, top, bottom, 0.24, 0.55),
                self.focus,
                self._flat_slab(1144, 200, top, bottom, 0.24, 0.55),
            ]
            self.slabs[0].id, self.slabs[2].id = 3, 5
            self.slabs[0].rng = random.Random(SEED * 7349 + 3 * 911)
            self.slabs[2].rng = random.Random(SEED * 7349 + 5 * 911)
            for slab in self.slabs:
                if slab.focus:
                    build_rows(slab, 14.0, 15.0, 18.0, 16.0, pad_bottom=34.0)
                else:
                    build_rows(slab, 10.0, 13.0, 10.0, 14.0, pad_bottom=14.0)

    # ------------------------------------------------------------- caches

    def _build_background(self):
        surf = pygame.Surface((self.sw, self.sh)).convert()
        for y in range(self.sh):
            t = (y / max(1, self.sh - 1)) ** 1.35
            pygame.draw.line(surf, mix(P.bg_top, P.bg_bottom, t),
                             (0, y), (self.sw, y))
        self.background = surf
        clouds = pygame.Surface((self.sw, self.sh)).convert()
        clouds.fill((0, 0, 0))
        sprite = self._radial((256, 256), 3.0)
        if self.portrait:
            blobs = (
                ((540, 940), 1120, (20, 42, 70), 55),
                ((240, 260), 600, (9, 22, 38), 20),
                ((860, 1720), 660, (7, 16, 30), 16),
            )
        else:
            blobs = (
                ((640, 196), 780, (22, 44, 70), 52),
                ((240, 190), 520, (8, 20, 36), 16),
                ((1080, 190), 520, (8, 20, 36), 16),
            )
        for (cx, cy), size, color, strength in blobs:
            tinted = sprite.copy()
            tinted.fill((clamp8(color[0] * strength / 60),
                         clamp8(color[1] * strength / 60),
                         clamp8(color[2] * strength / 60)),
                        special_flags=pygame.BLEND_RGB_MULT)
            w = int(size)
            scaled = pygame.transform.smoothscale(tinted, (w, w))
            scaled.set_alpha(215)
            clouds.blit(scaled, (cx - w // 2, cy - w // 2),
                        special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(clouds, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        self.background = surf

    def _radial(self, size, power):
        key = (size, round(power, 3))
        if key in self._cache:
            return self._cache[key]
        w, h = size
        surf = pygame.Surface((w, h)).convert()
        surf.fill((0, 0, 0))
        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(0, h):
            for x in range(0, w):
                r = math.hypot(x - cx, y - cy) / maxd
                v = max(0.0, 1.0 - r) ** power
                k = int(255 * v)
                surf.set_at((x, y), (k, k, k))
        self._cache[key] = surf
        return surf

    def _build_finish(self):
        qw = max(2, self.sw // 4)
        qh = max(2, self.sh // 4)
        small = pygame.Surface((qw, qh)).convert()
        cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(qh):
            for x in range(qw):
                r = math.hypot(x - cx, y - cy) / maxd
                dark = 0.46 * (max(0.0, r - 0.24) / 0.76) ** 1.5
                k = int(255 * max(0.08, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (self.sw, self.sh))
        for y in range(0, self.sh, 3):
            k = int(255 * (1.0 - 6.0 / 255.0))
            pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
        top_h = max(48, int(self.sh * 0.11))
        for y in range(top_h):
            t = (y / max(1, top_h - 1)) ** 2.1
            k = int(32 + 223 * t)
            pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
        bot_h = max(60, int(self.sh * (0.13 if self.portrait else 0.18)))
        for y in range(bot_h):
            k = int(255 - 232 * (y / max(1, bot_h - 1)))
            pygame.draw.line(finish, (k, k, k),
                             (0, self.sh - bot_h + y),
                             (self.sw, self.sh - bot_h + y), 1)
        self.finish = finish

    def _build_glow(self):
        div = 6 if self.portrait else 5
        self.bloom = pygame.Surface(
            (max(1, self.sw // div), max(1, self.sh // div))).convert()
        self.bloom_mid = pygame.Surface(
            (max(1, self.sw // 2), max(1, self.sh // 2))).convert()
        self.bloom_up = pygame.Surface((self.sw, self.sh)).convert()
        self.glow_strength = 0.46 if self.portrait else 0.42

    def _build_stars(self):
        rng = random.Random(SEED ^ 0x51AB)
        count = 600 if self.portrait else 230
        self.stars = []
        for _ in range(count):
            fx = rng.random()
            fy = rng.random()
            size = rng.choice((1, 1, 1, 1, 2, 2, 3))
            bright = rng.uniform(0.14, 0.9)
            self.stars.append((fx, fy, size, bright))

    def _build_motes(self):
        rng = random.Random(SEED ^ 0x91F3)
        self.motes = []
        self.fore_motes = []
        count = 260 if self.portrait else 135
        fx0, fy0 = self.focus.cx, self.focus.cy
        for _ in range(count):
            if rng.random() < 0.7:
                x = fx0 + rng.gauss(0, (self.focus.w * 2.2)
                                    if self.portrait else self.focus.w * 2.0)
                y = fy0 + rng.gauss(0, (self.focus.h * 1.5)
                                    if self.portrait else self.focus.h * 1.6)
            else:
                x = rng.uniform(0, self.sw)
                y = rng.uniform(0, self.sh)
            size = rng.choice((1, 1, 1, 1, 1, 2, 2, 3))
            bright = rng.uniform(0.12, 0.78)
            warm = rng.random() < 0.18
            if rng.random() < 0.24:
                self.fore_motes.append((x, y, rng.choice((1, 1, 2)),
                                        bright * 0.55, warm))
            else:
                self.motes.append((x, y, size, bright, warm))

    def _build_fonts(self):
        self.font_title = pygame.font.SysFont(
            "dejavusansmono", max(16 if not self.portrait else 25,
                                  int(self.unit * 1.18)), bold=True)
        self.font_body = pygame.font.SysFont(
            "dejavusansmono", max(10 if not self.portrait else 15,
                                  int(self.unit * 0.92)))
        self.font_small = pygame.font.SysFont(
            "dejavusansmono", max(8 if not self.portrait else 12,
                                  int(self.unit * 0.70)))
        self.font_catalog = pygame.font.SysFont(
            "dejavusansmono", max(9 if not self.portrait else 11,
                                  int(self.unit * 0.62)))
        self.font_lore = pygame.font.SysFont("dejavuserif",
                                             self.caption_font_px)
        # The readable line is the only true sentence on the wall; make it
        # fit the frame with a graceful margin.
        max_w = self.sw * (0.66 if not self.portrait else 0.64)
        size = self.caption_font_px
        while size > 10 and self.font_lore.size(self.caption)[0] > max_w:
            size -= 1
            self.font_lore = pygame.font.SysFont("dejavuserif", size)
        self.caption_font_px = size

    # -------------------------------------------------------------- drawing

    def _text(self, screen, text, pos, color, font, align="left"):
        if not text:
            return
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if align == "right":
            rect.topright = (int(pos[0]), int(pos[1]))
        elif align == "center":
            rect.midtop = (int(pos[0]), int(pos[1]))
        else:
            rect.topleft = (int(pos[0]), int(pos[1]))
        screen.blit(surf, rect)

    def _draw_face(self, screen, slab: Slab):
        p = P
        dim = slab.brightness
        if slab.focus:
            top = mix(p.face_top, p.haze, 0.10)
            bottom = mix(p.face_bottom, p.bg_bottom, 0.25)
        else:
            top = mix(p.bg_top, p.face_top, 0.10 + 0.45 * dim)
            bottom = mix(p.bg_bottom, p.face_bottom, 0.12 + 0.42 * dim)
        th = slab.thickness
        xrt, xrb = slab.qx[1], slab.qx[2]
        if th > 0:
            side_color = mix(p.bg_bottom, p.side, 0.2 + 0.6 * dim)
            pygame.draw.polygon(screen, side_color, (
                (xrt, slab.y0), (xrt + th, slab.y0 + 3),
                (xrb + th, slab.y1 - 2), (xrb, slab.y1)))
            pygame.draw.aaline(
                screen, mix(p.bg_bottom, p.detail, 0.12 + 0.35 * dim),
                (xrt + th * 0.55, slab.y0 + 2),
                (xrb + th * 0.55, slab.y1 - 1))
        hgt = max(1.0, slab.y1 - slab.y0)
        for y in range(int(slab.y0), int(slab.y1) + 1):
            t = (y - slab.y0) / hgt
            xl, xr = slab.edges_at(y)
            color = mix(top, bottom, t ** 0.82)
            if not slab.focus:
                color = mix(color, p.bg_top, slab.depth * 0.22)
            pygame.draw.line(screen, color, (int(xl), y), (int(xr), y), 1)

        # A couple of vertical seams, barely there: worked stone, not a card.
        seam = mix(p.bg_bottom, p.detail, 0.12 + 0.35 * dim)
        for frac in (0.32, 0.71):
            sx = slab.qx[0] + frac * (slab.qx[1] - slab.qx[0])
            ex = slab.qx[3] + frac * (slab.qx[2] - slab.qx[3])
            pygame.draw.aaline(screen, seam, (sx, slab.y0 + 4),
                               (ex, slab.y1 - 4))

        edge = mix(p.bg_bottom, p.structure, 0.06 + 0.62 * dim ** 1.15)
        hi = mix(p.detail, p.ink, 0.10 + 0.62 * dim ** 1.2)
        pygame.draw.aaline(screen, edge, (slab.qx[0], slab.y0),
                           (slab.qx[3], slab.y1))
        pygame.draw.aaline(screen, hi, (slab.qx[1], slab.y0),
                           (slab.qx[2], slab.y1))
        pygame.draw.aaline(screen, mix(p.detail, p.structure, 0.4),
                           (slab.qx[0], slab.y0), (slab.qx[1], slab.y0))
        pygame.draw.aaline(screen, mix(p.bg_bottom, p.detail, 0.25 + 0.35 * dim),
                           (slab.qx[3], slab.y1), (slab.qx[2], slab.y1))
        inset = max(3.0, slab.w * 0.045)
        xlt, xrt_i = slab.qx[0] + inset, slab.qx[1] - inset
        xlb, xrb_i = slab.qx[3] + inset, slab.qx[2] - inset
        inner = mix(p.bg_top, p.detail, 0.10 + 0.32 * dim)
        pygame.draw.aaline(screen, inner, (xlt, slab.y0 + inset),
                           (xrt_i, slab.y0 + inset))
        pygame.draw.aaline(screen, inner, (xlt, slab.y0 + inset),
                           (xlb, slab.y1 - inset))
        pygame.draw.aaline(screen, inner, (xrt_i, slab.y0 + inset),
                           (xrb_i, slab.y1 - inset))

    def _glyph_color(self, slab: Slab, x: float, bar_x: float) -> RGB:
        if slab.focus:
            sigma = max(80.0, min(130.0, slab.w * 0.28))
            near = math.exp(-((x - bar_x) / sigma) ** 2)
            brightness = 0.145 + 0.78 * near
            return mix(P.ink_dim, P.ink, brightness)
        base = 0.04 + 0.24 * slab.brightness
        return mix(P.bg_bottom, P.ink_dim, base)

    def _draw_glyphs(self, screen, slab: Slab):
        if not slab.rows:
            return
        pad_y = slab.pad_y
        inner_h = 2 * slab.h - slab.pad_y - slab.pad_bottom
        row_pitch = 12.4 if slab.focus else max(9.0, min(16.0, slab.h * 0.075))
        top = slab.y0 + pad_y
        for (v, indent, cells, glyphs, wear) in slab.rows:
            y = top + v * inner_h
            xl, xr = slab.edges_at(y)
            cell_w = (xr - xl) / max(1, cells)
            start = xl + indent * cell_w
            count = min(len(glyphs), int((xr - start - 2) / max(1.0, cell_w)))
            bar_x = 0.0
            if slab.focus:
                bar_x = xl + self.bar_fraction * (xr - xl)
            for i in range(count):
                gx = start + i * cell_w
                color = self._glyph_color(slab, gx, bar_x)
                if color != (0, 0, 0) and wear < 1.0:
                    color = scale(color, 0.45 + 0.55 * wear)
                if color == (0, 0, 0):
                    continue
                for stroke in GLYPHS[glyphs[i]]:
                    (ax, ay), (bx, by) = stroke
                    gx1 = int(gx + ax * cell_w * 0.62)
                    gx2 = int(gx + bx * cell_w * 0.62)
                    gy1 = int(y + (ay - 0.5) * row_pitch * 0.62)
                    gy2 = int(y + (by - 0.5) * row_pitch * 0.62)
                    pygame.draw.line(screen, color, (gx1, gy1),
                                     (gx2, gy2), 1)

    def _draw_bar(self, screen, slab: Slab):
        """A raking bar of light, soft-edged and mostly on the face."""
        if not slab.focus:
            return
        spill = 14 if not self.portrait else 26
        outer = 76 if not self.portrait else 150
        core = 6.0 if not self.portrait else 10.0
        xl, xr = slab.edges_at(slab.cy)
        bx = xl + self.bar_fraction * (xr - xl)
        bar_w = int(outer * 2) + 2
        bar_h = int(slab.y1 - slab.y0) + spill * 2
        bar = pygame.Surface((bar_w, bar_h)).convert()
        bar.fill((0, 0, 0))

        # One horizontal light profile, drawn down the face.  The bar follows
        # the slab's slant by shifting its centre per scanline.
        for wy in range(int(slab.y0) - spill, int(slab.y1) + spill + 1):
            if wy < slab.y0:
                fade = max(0.0, 1.0 - (slab.y0 - wy) / spill)
            elif wy > slab.y1:
                fade = max(0.0, 1.0 - (wy - slab.y1) / spill)
            else:
                fade = 1.0
            if fade <= 0.0:
                continue
            xl, xr = slab.edges_at(min(max(wy, slab.y0), slab.y1))
            bxc = xl + self.bar_fraction * (xr - xl)
            yy = wy - (int(slab.y0) - spill)
            for dx in range(-int(outer), int(outer) + 1):
                r = abs(dx)
                profile = (
                    math.exp(-(r / core) ** 2) * 0.52
                    + math.exp(-(r / (core * 4.0)) ** 2) * 0.27
                    + math.exp(-(r / (core * 14.0)) ** 2) * 0.12
                )
                if profile < 0.0015:
                    continue
                xx = int(bxc - bx + bar_w * 0.5) + dx
                if 0 <= xx < bar_w:
                    # Bone-white core, teal falloff.  The core is allowed to
                    # reach near-white only in a narrow band.
                    color = mix((42, 86, 98),
                                (242, 234, 212),
                                min(1.0, profile * 1.45))
                    vertical = 0.88 + 0.12 * math.sin(
                        math.pi * (wy - slab.y0) / max(1.0, slab.y1 - slab.y0))
                    bar.set_at((xx, yy),
                               scale(color, profile * fade * vertical))
        screen.blit(bar, (int(bx - bar_w * 0.5), int(slab.y0) - spill),
                    special_flags=pygame.BLEND_RGB_ADD)

        # The lit right edge of the slab, where the bar leaves the face.
        edge_x, edge_xb = slab.qx[1], slab.qx[2]
        t = (bx - slab.qx[0]) / max(1.0, slab.qx[1] - slab.qx[0])
        if t > 0.55:
            segments = 18
            for i in range(segments):
                a = i / segments
                b = (i + 1) / segments
                ya = slab.y0 + 2 + (slab.y1 - slab.y0 - 4) * a
                yb = slab.y0 + 2 + (slab.y1 - slab.y0 - 4) * b
                xa = edge_x + (edge_xb - edge_x) * a
                xb = edge_x + (edge_xb - edge_x) * b
                fade = 1.0 - 0.55 * abs((a + b) * 0.5 - 0.5) * 2.0
                pygame.draw.aaline(screen, scale(
                    mix(P.structure, P.glow, 0.55), 0.35 + 0.65 * fade),
                    (xa, ya), (xb, yb))

    def _draw_caption(self, screen):
        f = self.font_lore
        text = self.caption
        surf = f.render(text, True, P.lore)
        rect = surf.get_rect()
        cx = self.focus.cx
        top = self.focus.y1 + self.caption_gap
        rect.midtop = (int(cx), int(top))
        half = surf.get_width() // 2 + 15
        # Leader from the foot of the slab down to the annotation.
        pygame.draw.line(screen, mix(P.accent_dim, P.detail, 0.35),
                         (int(cx), int(self.focus.y1 + 3)),
                         (int(cx), int(rect.top - 7)), 1)
        pygame.draw.line(screen, mix(P.accent_dim, P.detail, 0.35),
                         (int(cx), int(rect.top - 7)),
                         (int(cx - 4), int(rect.top - 7)), 1)
        pygame.draw.line(screen, mix(P.accent_dim, P.detail, 0.35),
                         (int(cx), int(rect.top - 7)),
                         (int(cx + 4), int(rect.top - 7)), 1)

        top_y = rect.top - max(6, self.caption_font_px // 3)
        bot_y = rect.bottom + max(5, self.caption_font_px // 4)
        for yy in (top_y, bot_y):
            pygame.draw.line(screen, mix(P.accent_dim, P.accent, 0.22),
                             (rect.centerx - half, yy),
                             (rect.centerx + half, yy), 1)
        for xx in (rect.centerx - half, rect.centerx + half):
            for yy, direction in ((top_y, 1), (bot_y, -1)):
                pygame.draw.line(screen, mix(P.accent_dim, P.accent, 0.30),
                                 (xx, yy), (xx, yy + direction * 3), 1)
        label = "SLAB 04 // TRANSLATION"
        lsurf = self.font_catalog.render(label, True,
                                         mix(P.warm, P.accent_dim, 0.55))
        screen.blit(lsurf, (rect.centerx - half, top_y - lsurf.get_height() - 2))
        screen.blit(surf, rect)

        # Catalog mark inside the lit face.
        mark = self.focus.label or "TL-0000"
        msurf = self.font_catalog.render(mark, True,
                                         mix(P.structure, P.warm, 0.35))
        mrect = msurf.get_rect()
        mrect.bottomright = (int(self.focus.edges_at(self.focus.y1 - 8)[1] - 8),
                             int(self.focus.y1 - 7))
        screen.blit(msurf, mrect)

    def _draw_background_slabs(self, screen):
        for slab in self.slabs:
            if slab.focus:
                continue
            self._draw_face(screen, slab)
            self._draw_glyphs(screen, slab)

    def _draw_atmosphere(self, screen):
        for fx, fy, size, bright in self.stars:
            x = int(fx * (self.sw - 1))
            y = int(fy * (self.sh - 1))
            color = scale(P.star, bright * 0.6)
            if size >= 2:
                pygame.draw.circle(screen, color, (x, y), size - 1)
            else:
                screen.set_at((x, y), color)
        for x, y, size, bright, warm in self.motes:
            color = scale(P.accent if not warm else P.warm, bright * 0.55)
            if size >= 3:
                pygame.draw.line(screen, scale(color, 0.45),
                                 (int(x - 2), int(y)), (int(x + 2), int(y)), 1)
            elif size == 2:
                pygame.draw.circle(screen, color, (int(x), int(y)), 1)
            else:
                screen.set_at((int(x), int(y)), color)

    def _draw_foreground_motes(self, screen):
        # A handful of motes sit in front of the slabs, so the vault has air
        # rather than a flat backdrop.  The caption and HUD stay clear.
        f = self.font_lore
        cap_w, cap_h = f.size(self.caption)
        cap_cx = int(self.focus.cx)
        cap_top = int(self.focus.y1 + self.caption_gap - 4)
        for x, y, size, bright, warm in self.fore_motes:
            if (abs(x - cap_cx) < cap_w * 0.5 + 24
                    and cap_top - 18 < y < cap_top + cap_h + 34):
                continue
            if y > self.sh - self.margin - 22 and x > self.sw - 280:
                continue
            color = scale(P.accent if not warm else P.warm, bright * 0.5)
            if size >= 3:
                pygame.draw.line(screen, scale(color, 0.4),
                                 (int(x - 2), int(y)), (int(x + 2), int(y)), 1)
            elif size == 2:
                pygame.draw.circle(screen, color, (int(x), int(y)), 1)
            else:
                screen.set_at((int(x), int(y)), color)

    def _composite_glow(self, screen):
        pygame.transform.smoothscale(screen, self.bloom.get_size(), self.bloom)
        k = int(20 + 86 * self.glow_strength)
        self.bloom.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self.bloom, self.bloom_mid.get_size(),
                                     self.bloom_mid)
        pygame.transform.scale(self.bloom_mid, (self.sw, self.sh),
                               self.bloom_up)
        screen.blit(self.bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------------------------ HUD

    def _corner_ticks(self, screen):
        m = self.margin
        arm = max(8, int(min(self.sw, self.sh) * 0.018))
        color = P.hud_faint
        for x, y, dx, dy in ((m, m, 1, 1),
                             (self.sw - m - 1, m, -1, 1),
                             (self.sw - m - 1, self.sh - m - 1, -1, -1)):
            pygame.draw.line(screen, color, (x, y), (x + dx * arm, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y + dy * arm), 1)

    def _draw_hud(self, screen):
        m = self.margin
        self._corner_ticks(screen)
        title = "THE LONG ARCHIVE"
        subtitle = "VAULT 9 // MONOLITH FIELD"
        trect = self.font_title.render(title, True, P.hud).get_rect()
        self._text(screen, title, (m, m), P.hud, self.font_title)
        rule_y = m + trect.height + 4
        pygame.draw.line(screen, P.hud_dim, (m, rule_y),
                         (m + max(90, trect.width * 0.74), rule_y), 1)
        self._text(screen, subtitle, (m, rule_y + 5), P.hud_dim,
                   self.font_small)

        lines = (
            ("ENTRIES 1,204", P.hud, self.font_body),
            ("FOCUS SLAB 04 / 09", P.hud_dim, self.font_small),
            ("LIGHT BAR 08.0 S", P.hud_faint, self.font_small),
        )
        y = m
        for text, color, font in lines:
            self._text(screen, text, (self.sw - m, y), color, font, "right")
            y += font.get_height() + 2
        track_w = max(72, min(170, int(self.sw * 0.10)))
        tx = self.sw - m - track_w
        ty = y + 3
        pygame.draw.line(screen, P.hud_faint, (tx, ty), (tx + track_w, ty), 1)
        pygame.draw.line(screen, P.accent, (tx, ty),
                         (tx + int(track_w * self.bar_fraction), ty), 1)
        pygame.draw.line(screen, mix(P.accent_dim, P.accent, 0.5),
                         (tx + int(track_w * self.bar_fraction), ty - 2),
                         (tx + int(track_w * self.bar_fraction), ty + 2), 1)

        # One quiet line bottom-right; the lower-left belongs to the controller.
        fy = self.sh - m - self.font_small.get_height()
        self._text(screen, "CAMERA +2.0 PX/S", (self.sw - m, fy),
                   P.hud_faint, self.font_small, "right")
        if self.portrait:
            self._text(screen, "09 SLABS // NO READER",
                       (self.sw - m, fy - self.font_small.get_height() - 2),
                       P.hud_faint, self.font_small, "right")

    # --------------------------------------------------------------- frame

    def render(self, time_s: float = 0.0) -> pygame.Surface:
        self.time_s = time_s
        screen = pygame.Surface((self.sw, self.sh)).convert()
        screen.blit(self.background, (0, 0))
        self._draw_atmosphere(screen)
        self._draw_background_slabs(screen)
        self._draw_face(screen, self.focus)
        self._draw_glyphs(screen, self.focus)
        self._draw_bar(screen, self.focus)
        self._draw_caption(screen)
        self._draw_foreground_motes(screen)
        self._composite_glow(screen)
        screen.blit(self.finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self._draw_hud(screen)
        return screen


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))
    cases = (
        ((1280, 400), "landscape", "long_archive_1280x400.png"),
        ((1080, 1920), "portrait", "long_archive_1080x1920.png"),
    )
    for size, layout, name in cases:
        renderer = ArchiveRenderer(size, layout)
        frame = renderer.render(28.0)
        path = os.path.join(OUT_DIR, name)
        pygame.image.save(frame, path)
        print(f"{name}: {size[0]}x{size[1]}  slabs={len(renderer.slabs)} "
              f"rows={sum(len(s.rows) for s in renderer.slabs)} "
              f"lore_px={renderer.caption_font_px}")
    pygame.quit()


if __name__ == "__main__":
    main()
