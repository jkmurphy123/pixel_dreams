#!/usr/bin/env python3
"""Design prototype: The Orrery of Small Worlds (slow_worlds 5.1).

This is a *design* script, not the mode.  It produced the camera study in
screenshots/orrery/camera_study.png while the camera was being chosen; the
shipping stills are rendered by the real mode through
scripts/orrery_preview.py.

The camera looks down on the instrument at an angle, so every circular rail
projects to an oval.  The angle is not fixed: each aspect class chooses an
elevation that makes the projected plate fill the frame the way a poster
would.  The 1280x400 strip is fitted at a shallow ~16 degrees (very wide
ovals, the instrument spans the strip); the portrait panel looks down steeper
at ~33 degrees (rounder ovals, room for a vertical title lockup and the
engraved dedication plate).

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python designs/orrery_proto/gen_orrery.py
"""
from __future__ import annotations

import math
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(BASE_DIR, "screenshots", "orrery")

TAU = math.tau
SS = 2  # render the scene at 2x, downsample for clean thin brass lines

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


# ---------------------------------------------------------------------------
# Palette — "Brass & Ink" from the collection's shared visual system.
# ---------------------------------------------------------------------------

BG_TOP = (11, 9, 9)
BG_BOTTOM = (2, 2, 3)
HAZE = (46, 30, 14)

INK = (232, 220, 192)
INK_DIM = (158, 144, 119)
INK_FAINT = (96, 86, 70)

BRASS_HI = (246, 207, 132)
BRASS = (201, 164, 92)
BRASS_MID = (146, 113, 61)
BRASS_DIM = (95, 74, 42)
BRASS_DEEP = (54, 41, 24)

PLATE_CENTER = (29, 23, 18)
PLATE_EDGE = (11, 9, 8)
PLATE_SIDE = (43, 32, 21)

ACCENT = (127, 183, 163)
GLOW = (242, 200, 121)
WARM_WHITE = (255, 238, 204)


def clamp8(value) -> int:
    return 0 if value < 0 else 255 if value > 255 else int(value)


def mix(a, b, t):
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (clamp8(a[0] + (b[0] - a[0]) * t),
            clamp8(a[1] + (b[1] - a[1]) * t),
            clamp8(a[2] + (b[2] - a[2]) * t))


def scale(color, factor):
    if factor <= 0.0:
        return (0, 0, 0)
    return (clamp8(color[0] * factor), clamp8(color[1] * factor),
            clamp8(color[2] * factor))


# ---------------------------------------------------------------------------
# Small vector / camera kit
# ---------------------------------------------------------------------------

def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vmul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vnorm(a):
    n = math.sqrt(vdot(a, a))
    if n <= 1e-9:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


class View:
    """A camera on a sphere looking at the instrument."""

    def __init__(self, elevation_deg: float, azimuth_deg: float,
                 distance: float = 7.0, target=(0.0, 0.0, 0.0)):
        self.elevation_deg = elevation_deg
        self.azimuth_deg = azimuth_deg
        self.distance = distance
        el = math.radians(elevation_deg)
        az = math.radians(azimuth_deg)
        offset = (math.cos(el) * math.sin(az), math.sin(el),
                  math.cos(el) * math.cos(az))
        self.target = target
        self.pos = vadd(target, vmul(offset, distance))
        self.forward = vnorm(vsub(target, self.pos))
        self.right = vnorm(vcross(self.forward, (0.0, 1.0, 0.0)))
        self.up = vcross(self.right, self.forward)

    def raw(self, point):
        rel = vsub(point, self.pos)
        zv = vdot(rel, self.forward)
        if zv <= 0.05:
            return None, zv
        return (vdot(rel, self.right) / zv,
                vdot(rel, self.up) / zv), zv

    def depth(self, point) -> float:
        return vdot(vsub(point, self.pos), self.forward)


class Frame:
    """A View fitted to a pixel rectangle by a single 2D zoom."""

    def __init__(self, view: View, rect, points):
        self.view = view
        self.rect = pygame.Rect(rect)
        raw = []
        for point in points:
            p, _zv = view.raw(point)
            if p is not None:
                raw.append(p)
        if not raw:
            raise ValueError("nothing in front of the camera")
        xs = [p[0] for p in raw]
        ys = [p[1] for p in raw]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        span_x = max(1e-6, self.max_x - self.min_x)
        span_y = max(1e-6, self.max_y - self.min_y)
        self.focal = min(self.rect.width / span_x, self.rect.height / span_y)
        self.cx = (self.min_x + self.max_x) * 0.5
        self.cy = (self.min_y + self.max_y) * 0.5
        self.screen_cx = self.rect.centerx
        self.screen_cy = self.rect.centery

    def project(self, point):
        raw, _zv = self.view.raw(point)
        if raw is None:
            return None
        return (self.screen_cx + self.focal * (raw[0] - self.cx),
                self.screen_cy - self.focal * (raw[1] - self.cy))

    def scale_at(self, point) -> float:
        """2x pixels per world unit at that point."""
        zv = self.view.depth(point)
        return self.focal / max(0.05, zv)


# ---------------------------------------------------------------------------
# Scene definition — deterministic, a pure function of (seed, time).
# ---------------------------------------------------------------------------

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")

# (name, a, eccentricity, inclination, node, phase, period_s, radius, tint)
WORLDS = (
    ("TACE",   0.255, 0.055, 12.0,  14.0, 300.0,  47.0, 0.0130, "ivory"),
    ("VELA",   0.360, 0.080, 10.0,  -7.0, 143.0,  71.0, 0.0165, "gold"),
    ("MORA",   0.475, 0.065,  8.5,   4.0, 268.0, 113.0, 0.0190, "bone"),
    ("ILUN",   0.590, 0.050,  7.0, -15.0,  35.0, 131.0, 0.0175, "accent"),
    ("SORREL", 0.705, 0.075,  5.5,  10.0, 196.0, 167.0, 0.0215, "gold"),
    ("NIX",    0.815, 0.040,  4.0,  -2.0, 308.0, 199.0, 0.0160, "ivory"),
    ("ORMA",   0.920, 0.055,  3.0,   7.0,  78.0, 239.0, 0.0225, "bone"),
)

WORLD_TINTS = {
    "ivory": (236, 223, 198),
    "gold": (228, 190, 126),
    "bone": (208, 196, 172),
    "accent": (147, 193, 174),
}

RAIL_HEIGHT = 0.105


def orbit_point(world, theta: float):
    """3D point on a world's rail.  theta is the mechanical orbit parameter."""
    _name, a, e, inc, node, _phase, _period, _radius, _tint = world
    b = a * math.sqrt(max(0.0, 1.0 - e * e))
    # Ellipse with the lamp at one focus.
    ex = a * math.cos(theta) - a * e
    ez = b * math.sin(theta)
    # Inclined about the ellipse's own major axis, then rotated in the plate.
    ey = ez * math.sin(math.radians(inc))
    ez = ez * math.cos(math.radians(inc))
    no = math.radians(node)
    wx = ex * math.cos(no) - ez * math.sin(no)
    wz = ex * math.sin(no) + ez * math.cos(no)
    return (wx, RAIL_HEIGHT + ey, wz)


def world_position(world, t: float):
    _name, _a, _e, _inc, _node, phase, period, _radius, _tint = world
    theta = math.radians(phase) + TAU * (t / period)
    return orbit_point(world, theta)


def world_rail(world, steps: int = 180):
    return [orbit_point(world, TAU * i / steps) for i in range(steps + 1)]


def moon_offset(index: int, t: float, radius: float):
    moon_r = radius * (2.45 + 0.40 * index)
    moon_phase = 1.7 + 2.4 * index
    moon_inc = math.radians(24.0 + 19.0 * index)
    ang = moon_phase + TAU * t / (6.0 + 2.7 * index)
    mx = math.cos(ang) * moon_r
    mz = math.sin(ang) * moon_r
    my = mz * math.sin(moon_inc)
    mz = mz * math.cos(moon_inc)
    return (mx, my, mz)


# ---------------------------------------------------------------------------
# Text / light helpers
# ---------------------------------------------------------------------------

_fonts: dict[tuple[str, int], pygame.font.Font] = {}


def font(path: str, px: int) -> pygame.font.Font:
    key = (path, max(1, int(px)))
    f = _fonts.get(key)
    if f is None:
        f = pygame.font.Font(path, max(1, int(px)))
        _fonts[key] = f
    return f


def tracked(text: str, f: pygame.font.Font, color, tracking: int = 0,
            alpha: int = 255):
    glyphs = [f.render(ch, True, color) for ch in text]
    if not glyphs:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    width = sum(g.get_width() for g in glyphs) + tracking * (len(glyphs) - 1)
    height = max(g.get_height() for g in glyphs)
    surf = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    x = 0
    for g in glyphs:
        surf.blit(g, (x, 0))
        x += g.get_width() + tracking
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


def radial_glow(radius_px: int, color, power: float = 2.2) -> pygame.Surface:
    """A soft additive light sprite (RGB carries the intensity)."""
    base = 160
    small = pygame.Surface((base, base))
    small.fill((0, 0, 0))
    steps = 72
    for i in range(steps, 0, -1):
        t = i / steps
        k = (1.0 - t) ** power
        r = int(base * 0.5 * t)
        pygame.draw.circle(small, scale(color, k * 0.20),
                           (base // 2, base // 2), r)
    size = max(2, radius_px * 2)
    return pygame.transform.smoothscale(small, (size, size))


def blit_glow(dst, center, radius_px: int, color, power=2.2, strength=1.0):
    if radius_px < 2:
        return
    sprite = radial_glow(radius_px, color, power)
    if strength != 1.0:
        sprite.fill(scale((255, 255, 255), strength),
                    special_flags=pygame.BLEND_RGB_MULT)
    dst.blit(sprite, (int(center[0]) - radius_px, int(center[1]) - radius_px),
             special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

RIM_R = 1.032
PLATE_THICK = 0.018


def circle_points(radius: float, y: float, steps: int = 180):
    return [(radius * math.cos(TAU * i / steps), y,
             radius * math.sin(TAU * i / steps))
            for i in range(steps + 1)]


def project_poly(frame: Frame, points):
    out = []
    for p in points:
        q = frame.project(p)
        if q is None:
            return None
        out.append(q)
    return out


def armature_points(cfg: dict, steps: int = 90):
    radius = cfg.get("radius", 1.28)
    yaw = math.radians(cfg.get("yaw", 74.0))
    lift = cfg.get("lift", 0.0)
    points = []
    for i in range(steps + 1):
        ang = math.pi * i / steps  # upper half only
        x = radius * math.cos(ang) * math.cos(yaw)
        z = radius * math.cos(ang) * math.sin(yaw)
        y = radius * math.sin(ang) + lift
        points.append((x, y, z))
    return points


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class Scene:
    def __init__(self, size, preset: dict, time_s: float = 21.0):
        self.width, self.height = int(size[0]), int(size[1])
        self.w, self.h = self.width * SS, self.height * SS
        self.preset = preset
        self.time = float(time_s)
        self.view = View(preset["elevation"], preset["azimuth"])
        self.ss = SS

        fit_points = []
        for p in circle_points(RIM_R, 0.0, 120):
            fit_points.append(p)
        for p in circle_points(RIM_R, -PLATE_THICK, 120):
            fit_points.append(p)
        for world in WORLDS:
            for i in range(0, 120, 1):
                fit_points.append(orbit_point(world, TAU * i / 120))
        if preset.get("armature"):
            fit_points.extend(armature_points(preset["armature"]))
        x, y, rx, by = preset["rect"]
        rect = pygame.Rect(int(x * SS), int(y * SS),
                           int((rx - x) * SS), int((by - y) * SS))
        self.frame = Frame(self.view, rect, fit_points)

        self.sun_base = (0.0, 0.0, 0.0)
        self.sun_center = (0.0, 0.155, 0.0)
        self.sun_px = max(6.0, self.frame.scale_at(self.sun_center) * 0.038)

        rng = random.Random(preset.get("seed", 2001))
        self.specks = []
        for _ in range(preset.get("specks", 90)):
            x = rng.random()
            y = rng.random()
            if x < 0.13 and y > 0.86:
                continue  # keep the mode-number corner clean
            self.specks.append((x, y, rng.choice((1, 1, 1, 2)),
                                rng.uniform(0.10, 0.55)))
        self.dust = []
        for _ in range(preset.get("dust", 26)):
            x = rng.uniform(0.05, 0.95)
            y = rng.uniform(0.12, 0.88)
            if 0.55 < x < 0.72 and 0.35 < y < 0.72:
                continue
            self.dust.append((x, y, rng.uniform(1.0, 3.0),
                              rng.uniform(0.12, 0.45)))

    def screen(self, point):
        p = self.frame.project(point)
        return None if p is None else (p[0], p[1])

    def screen_native(self, point):
        p = self.frame.project(point)
        return None if p is None else (p[0] / SS, p[1] / SS)


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

def draw_background(scene: Scene, dst):
    w, h = scene.w, scene.h
    for y in range(h):
        t = (y / max(1, h - 1)) ** 1.35
        pygame.draw.line(dst, mix(BG_TOP, BG_BOTTOM, t), (0, y), (w, y))
    sun = scene.screen(scene.sun_center)
    if sun:
        blit_glow(dst, sun, int(min(w, h) * 0.62), HAZE, power=2.9,
                  strength=0.26)
        blit_glow(dst, sun, int(min(w, h) * 0.28), HAZE, power=2.7,
                  strength=0.22)

    for x, y, size, a in scene.specks:
        px = int(x * w)
        py = int(y * h)
        c = scale(WARM_WHITE, a * 0.55)
        pygame.draw.circle(dst, c, (px, py), size)
        if size > 1:
            pygame.draw.circle(dst, scale(c, 0.35), (px, py), size + 1, 1)


def draw_floor_rings(scene: Scene, dst):
    """Faint table rings beyond the instrument; the dark room reads as a place."""
    overlay = pygame.Surface((scene.w, scene.h), pygame.SRCALPHA)
    for radius, alpha in ((1.26, 16), (1.42, 10)):
        points = project_poly(scene.frame, circle_points(radius, -PLATE_THICK, 160))
        if points:
            pygame.draw.lines(overlay, (150, 118, 70, alpha), True, points, 2)
    for i in range(72):
        ang = TAU * i / 72
        p0 = scene.screen((1.415 * math.cos(ang), -PLATE_THICK,
                           1.415 * math.sin(ang)))
        p1 = scene.screen((1.44 * math.cos(ang), -PLATE_THICK,
                           1.44 * math.sin(ang)))
        if p0 and p1:
            pygame.draw.line(overlay, (150, 118, 70, 9), p0, p1, 1)
    dst.blit(overlay, (0, 0))


# ---------------------------------------------------------------------------
# The brass plate
# ---------------------------------------------------------------------------

def draw_plate(scene: Scene, dst):
    frame = scene.frame
    bottom_rim = project_poly(frame, circle_points(RIM_R, -PLATE_THICK, 180))
    if bottom_rim is None:
        return
    pygame.draw.polygon(dst, scale(PLATE_SIDE, 0.45), bottom_rim)

    top_rim = project_poly(frame, circle_points(RIM_R, 0.0, 180))
    if top_rim:
        for i in range(180):
            j = i + 1
            quad = [top_rim[i], top_rim[j], bottom_rim[j], bottom_rim[i]]
            angle = TAU * i / 180
            front = 0.5 + 0.5 * math.sin(angle)  # +z is the near side
            col = mix(scale(PLATE_SIDE, 0.30), scale(BRASS_DIM, 0.50),
                      front * 0.8)
            pygame.draw.polygon(dst, col, quad)

    # top surface: nested projected rings make a soft radial gradient,
    # warm at the lamp and dark at the rim.
    rings = 44
    for i in range(rings):
        t = i / (rings - 1)
        radius = RIM_R * (1.0 - t)
        points = project_poly(frame, circle_points(radius, 0.0, 150))
        if not points:
            continue
        col = mix(PLATE_EDGE, PLATE_CENTER, (t ** 0.62))
        pygame.draw.polygon(dst, col, points)

    sun = scene.screen(scene.sun_center)
    if sun:
        blit_glow(dst, sun, int(scene.frame.focal * 0.78), HAZE, power=2.6,
                  strength=0.20)
        blit_glow(dst, sun, int(scene.frame.focal * 0.38), (62, 42, 18),
                  power=2.4, strength=0.35)

    inner = 0.972
    ring_a = project_poly(frame, circle_points(inner, 0.0, 180))
    if ring_a and top_rim:
        for i in range(180):
            j = i + 1
            quad = [ring_a[i], ring_a[j], top_rim[j], top_rim[i]]
            angle = TAU * i / 180
            front = 0.5 + 0.5 * math.sin(angle)
            col = mix(scale(BRASS_DIM, 0.52), scale(BRASS, 0.72),
                      front ** 1.7)
            pygame.draw.polygon(dst, col, quad)
        pygame.draw.lines(dst, scale(BRASS_DIM, 0.9), True, ring_a, 1)
        pygame.draw.lines(dst, scale(BRASS, 0.48), True, top_rim, 1)

    draw_plate_engraving(scene, dst)


def draw_plate_engraving(scene: Scene, dst):
    frame = scene.frame
    overlay = pygame.Surface((scene.w, scene.h), pygame.SRCALPHA)

    def ring(radius, color, width=1, alpha=255):
        pts = project_poly(frame, circle_points(radius, 0.0, 150))
        if pts:
            pygame.draw.lines(overlay, (*color, alpha), True, pts, width)

    ring(0.94, BRASS_MID, 1, 78)
    ring(0.78, BRASS_DIM, 1, 44)
    ring(0.56, BRASS_DIM, 1, 38)
    ring(0.34, BRASS_DIM, 1, 34)

    for i in range(24):
        ang = TAU * i / 24
        p0 = scene.screen((0.315 * math.cos(ang), 0.0, 0.315 * math.sin(ang)))
        p1 = scene.screen((0.955 * math.cos(ang), 0.0, 0.955 * math.sin(ang)))
        if p0 and p1:
            alpha = 44 if i % 2 == 0 else 22
            pygame.draw.aaline(overlay, (*BRASS_DIM, alpha), p0, p1)

    for i in range(120):
        ang = TAU * i / 120
        r0 = 0.955
        r1 = 0.978 if i % 5 else 0.988
        p0 = scene.screen((r0 * math.cos(ang), 0.0, r0 * math.sin(ang)))
        p1 = scene.screen((r1 * math.cos(ang), 0.0, r1 * math.sin(ang)))
        if p0 and p1:
            alpha = 64 if i % 5 == 0 else 32
            pygame.draw.line(overlay, (*scale(BRASS_HI, 0.8), alpha), p0, p1, 1)

    for i in range(24):
        ang = TAU * (i + 0.5) / 24
        p = scene.screen((0.938 * math.cos(ang), 0.0, 0.938 * math.sin(ang)))
        if p:
            pygame.draw.circle(overlay, (*BRASS_MID, 88), (int(p[0]), int(p[1])), 2)

    # a small engraved star around the lamp
    for i in range(16):
        ang = TAU * i / 16
        r0 = 0.10 if i % 2 == 0 else 0.13
        r1 = 0.30 if i % 2 == 0 else 0.24
        p0 = scene.screen((r0 * math.cos(ang), 0.0, r0 * math.sin(ang)))
        p1 = scene.screen((r1 * math.cos(ang), 0.0, r1 * math.sin(ang)))
        if p0 and p1:
            pygame.draw.aaline(overlay, (*scale(BRASS_HI, 0.85), 40), p0, p1)

    dst.blit(overlay, (0, 0))

    f = font(SERIF, int(scene.preset["plaque_text_px"] * SS))
    draw_arc_text(scene, dst, "SEPTEM MUNDI  ·  UNA LUCERNA",
                  radius=0.845, y=0.0015, center_deg=90.0, f=f,
                  color=scale(BRASS, 0.80), tracking=int(2.0 * SS), alpha=200)


def draw_arc_text(scene: Scene, dst, text: str, radius: float, y: float,
                  center_deg: float, f: pygame.font.Font, color,
                  tracking: int = 0, alpha: int = 255):
    glyphs = [f.render(ch, True, color) for ch in text]
    total = sum(g.get_width() for g in glyphs) + tracking * max(0, len(text) - 1)
    scale_px = scene.frame.scale_at((radius, y, 0.0))
    circumference = TAU * radius * scale_px
    span = TAU * (total / max(1.0, circumference))
    start = math.radians(center_deg) + span * 0.5
    x = 0
    for glyph in glyphs:
        frac = (x + glyph.get_width() * 0.5) / max(1e-6, total)
        ang = start - span * frac
        p = scene.screen((radius * math.cos(ang), y, radius * math.sin(ang)))
        pa = scene.screen((radius * math.cos(ang - 0.004), y,
                           radius * math.sin(ang - 0.004)))
        pb = scene.screen((radius * math.cos(ang + 0.004), y,
                           radius * math.sin(ang + 0.004)))
        if p and pa and pb:
            rot = math.degrees(math.atan2(-(pa[1] - pb[1]), pa[0] - pb[0]))
            g = pygame.transform.rotozoom(glyph, rot, 1.0)
            if alpha < 255:
                g.set_alpha(alpha)
            dst.blit(g, (int(p[0] - g.get_width() * 0.5),
                         int(p[1] - g.get_height() * 0.5)))
        x += glyph.get_width() + tracking


# ---------------------------------------------------------------------------
# Rails, lamp, worlds
# ---------------------------------------------------------------------------

def depth_nearness(scene: Scene, depth: float) -> float:
    near = scene.view.depth(scene.sun_center) - 0.75
    far = scene.view.depth(scene.sun_center) + 0.75
    return max(0.0, min(1.0, (far - depth) / (far - near)))


def draw_rail_segments(scene: Scene, dst, world, sun_depth: float, front: bool):
    pts = world_rail(world)
    projected = [scene.frame.project(p) for p in pts]
    depths = [scene.view.depth(p) for p in pts]
    for i in range(len(pts) - 1):
        p0, p1 = projected[i], projected[i + 1]
        if p0 is None or p1 is None:
            continue
        mid = (depths[i] + depths[i + 1]) * 0.5
        if (mid <= sun_depth) != front:
            continue
        t = depth_nearness(scene, mid)
        col = mix(scale(BRASS, 0.30), scale(BRASS_HI, 0.80), t)
        pygame.draw.line(dst, scale(col, 0.28), p0, p1, max(2, int(3 * SS)))
        pygame.draw.line(dst, col, p0, p1, max(1, int(2 * SS)))

    # two support struts per ring, joining rail to plate
    for frac in (0.19, 0.71):
        rail_p = orbit_point(world, TAU * frac)
        depth = scene.view.depth(rail_p)
        if (depth <= sun_depth) != front:
            continue
        foot = (rail_p[0], 0.0, rail_p[2])
        p0 = scene.frame.project(foot)
        p1 = scene.frame.project(rail_p)
        if p0 and p1:
            pygame.draw.line(dst, scale(BRASS_DIM, 0.55), p0, p1,
                             max(2, int(2 * SS)))
            pygame.draw.circle(dst, scale(BRASS_MID, 0.7),
                               (int(p1[0]), int(p1[1])), max(2, int(2 * SS)))


def draw_sun(scene: Scene, dst):
    base = scene.screen(scene.sun_base)
    top = scene.screen(scene.sun_center)
    if not base or not top:
        return
    pygame.draw.line(dst, scale(BRASS_DIM, 0.8), base, top, max(2, int(3 * SS)))
    pygame.draw.circle(dst, scale(BRASS_DIM, 0.9),
                       (int(base[0]), int(base[1])), max(3, int(5 * SS)))

    r = scene.sun_px
    blit_glow(dst, top, int(r * 15), (70, 48, 20), power=2.6, strength=0.55)
    blit_glow(dst, top, int(r * 7.5), GLOW, power=2.3, strength=0.70)
    blit_glow(dst, top, int(r * 3.2), (255, 214, 150), power=2.0, strength=0.85)
    pygame.draw.circle(dst, scale(GLOW, 0.55), (int(top[0]), int(top[1])), int(r))
    pygame.draw.circle(dst, WARM_WHITE, (int(top[0]), int(top[1])),
                       max(2, int(r * 0.58)))
    pygame.draw.circle(dst, (255, 255, 242), (int(top[0]), int(top[1])),
                       max(1, int(r * 0.28)))
    # a slender finial, so the lamp reads as part of an instrument
    tip = scene.screen((0.0, scene.sun_center[1] + 0.045, 0.0))
    if tip:
        pygame.draw.line(dst, scale(BRASS, 0.65), top, tip, max(1, int(1.4 * SS)))
        pygame.draw.circle(dst, scale(BRASS_HI, 0.9), (int(tip[0]), int(tip[1])),
                           max(1, int(2.0 * SS)))
        blit_glow(dst, tip, int(scene.sun_px * 1.4), GLOW, power=2.2,
                  strength=0.25)


def world_screen(scene: Scene, world):
    base = world_position(world, scene.time)
    return base, scene.screen(base)


def draw_world_body(scene: Scene, dst, world):
    base, p = world_screen(scene, world)
    if p is None:
        return
    _name, _a, _e, _inc, _node, _phase, _period, radius, tint_name = world
    px = scene.frame.scale_at(base) * radius
    if px < 0.7:
        return
    tint = WORLD_TINTS.get(tint_name, INK)
    depth = scene.view.depth(base)
    depth_t = max(0.0, min(1.0, (depth - (scene.view.distance - 1.0)) / 2.0))
    r = max(2.0, px * (1.0 - 0.16 * depth_t))

    blit_glow(dst, p, int(r * 5.5), scale(tint, 0.55), power=2.4, strength=0.40)

    sun_pos = scene.screen(scene.sun_center)
    if sun_pos:
        sdx, sdy = sun_pos[0] - p[0], sun_pos[1] - p[1]
        slen = math.hypot(sdx, sdy) or 1.0
        ox, oy = sdx / slen * r * 0.18, sdy / slen * r * 0.18
    else:
        ox = oy = 0.0

    pygame.draw.circle(dst, scale(tint, 0.20 * (1.0 - 0.3 * depth_t)),
                       (int(p[0]), int(p[1])), max(2, int(r * 1.05)))
    pygame.draw.circle(dst, scale(tint, 0.86),
                       (int(p[0] + ox), int(p[1] + oy)), max(2, int(r * 0.94)))
    pygame.draw.circle(dst, scale(tint, 1.08),
                       (int(p[0] + ox * 1.6), int(p[1] + oy * 1.6)),
                       max(1, int(r * 0.55)))
    pygame.draw.circle(dst, scale(tint, 1.28),
                       (int(p[0] + ox * 2.0 - r * 0.2),
                        int(p[1] + oy * 2.0 - r * 0.2)),
                       max(1, int(r * 0.24)))

    for moon_index in range(1 if radius < 0.017 else 2):
        mx, my, mz = moon_offset(moon_index, scene.time, radius)
        mp = scene.screen((base[0] + mx, base[1] + my + radius * 0.25,
                           base[2] + mz))
        if mp:
            mr = max(1.2, r * 0.20)
            pygame.draw.circle(dst, scale(INK_DIM, 0.75),
                               (int(mp[0]), int(mp[1])), max(1, int(mr)))


# ---------------------------------------------------------------------------
# Comet, conjunction, dust (line work kept in the 2x scene)
# ---------------------------------------------------------------------------

def comet_state(scene: Scene, at_time=None):
    """A long, steep ellipse that visits every few minutes.

    The plane is lifted above the plate and steeply inclined, so the head
    spends the middle of its pass in open sky rather than across the rails.
    """
    a, e = 1.50, 0.60
    inc = math.radians(35.0)
    node = math.radians(105.0)
    lift = 0.20
    period = 94.0
    phase = math.radians(scene.preset.get("comet_phase", 150.0))
    t = scene.time if at_time is None else at_time
    theta = phase + TAU * t / period
    b = a * math.sqrt(1 - e * e)
    ex = a * math.cos(theta) - a * e
    ez = b * math.sin(theta)
    ey = ez * math.sin(inc)
    ez = ez * math.cos(inc)
    wx = ex * math.cos(node) - ez * math.sin(node)
    wz = ex * math.sin(node) + ez * math.cos(node)
    return (wx, lift + ey, wz)


def draw_comet(scene: Scene, dst):
    if not scene.preset.get("comet", True):
        return
    hp = scene.screen(comet_state(scene))
    if not hp:
        return
    points = []
    for i in range(14):
        p = scene.screen(comet_state(scene, scene.time - i * 0.22))
        if p:
            points.append(p)
    if len(points) >= 2:
        overlay = pygame.Surface((scene.w, scene.h), pygame.SRCALPHA)
        for i in range(len(points) - 1):
            t = 1.0 - i / len(points)
            col = (*mix(ACCENT, WARM_WHITE, 0.25), int(170 * t * t))
            pygame.draw.line(overlay, col, points[i], points[i + 1],
                             max(1, int((1 + 3.0 * t) * SS)))
        dst.blit(overlay, (0, 0))
    blit_glow(dst, hp, int(scene.frame.scale_at(comet_state(scene)) * 0.08 * 3.1),
              ACCENT, power=2.1, strength=0.55)
    pygame.draw.circle(dst, (208, 238, 224), (int(hp[0]), int(hp[1])),
                       max(2, int(2.6 * SS)))
    pygame.draw.circle(dst, (250, 255, 248), (int(hp[0]), int(hp[1])),
                       max(1, int(1.1 * SS)))


def conjunction_pair(scene: Scene):
    """The pair whose on-screen separation is closest to the label target.

    Choosing the nearest pair can pick two worlds almost on top of each other,
    which hides both the line and the label.  A pair around ~95 px reads as a
    conjunction and leaves room for the caption.
    """
    positions = []
    for world in WORLDS:
        p = scene.screen(world_position(world, scene.time))
        if p:
            positions.append((world[0], p))
    target = scene.preset.get("conjunction_target_px", 95.0) * SS
    limit = scene.preset["conjunction_px"] * SS
    best = None
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            d = math.hypot(positions[i][1][0] - positions[j][1][0],
                           positions[i][1][1] - positions[j][1][1])
            if d > limit:
                continue
            score = abs(d - target)
            if best is None or score < best[0]:
                best = (score, d, positions[i], positions[j])
    if best is None:
        return None
    return (best[1], best[2], best[3])


def draw_dust(scene: Scene, dst):
    for x, y, size, a in scene.dust:
        px = int(x * scene.w)
        py = int(y * scene.h)
        pygame.draw.circle(dst, scale(WARM_WHITE, a * 0.35), (px, py),
                           max(1, int(size * SS * 0.5)))
    # three or four out-of-focus motes near the lens, barely there
    for x, y, radius, strength in scene.preset.get("bokeh", ()):
        blit_glow(dst, (x * scene.w, y * scene.h), int(radius * SS),
                  (96, 70, 36), power=1.6, strength=strength)


# ---------------------------------------------------------------------------
# Finish: bloom, vignette, scanlines
# ---------------------------------------------------------------------------

def composite_glow(screen, strength=0.62):
    w, h = screen.get_size()
    small = pygame.Surface((max(2, w // 4), max(2, h // 4)))
    pygame.transform.smoothscale(screen, small.get_size(), small)
    k = int(22 + 96 * strength)
    small.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
    mid = pygame.Surface((max(2, w // 2), max(2, h // 2)))
    pygame.transform.smoothscale(small, mid.get_size(), mid)
    up = pygame.Surface((w, h))
    pygame.transform.scale(mid, (w, h), up)
    screen.blit(up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def apply_finish(screen, vignette=0.38, scanline_alpha=7):
    w, h = screen.get_size()
    qw, qh = max(2, w // 4), max(2, h // 4)
    small = pygame.Surface((qw, qh))
    cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
    maxd = math.hypot(cx, cy)
    for y in range(qh):
        for x in range(qw):
            r = math.hypot(x - cx, y - cy) / maxd
            dark = vignette * (max(0.0, r - 0.26) / 0.74) ** 1.65
            k = int(255 * max(0.06, 1.0 - dark))
            small.set_at((x, y), (k, k, k))
    finish = pygame.transform.smoothscale(small, (w, h))
    if scanline_alpha > 0:
        k = int(255 * (1.0 - scanline_alpha / 255.0))
        for y in range(0, h, 3):
            pygame.draw.line(finish, (k, k, k), (0, y), (w, y), 1)
    screen.blit(finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


# ---------------------------------------------------------------------------
# Native-resolution text: world labels, conjunction, HUD, plaque
# ---------------------------------------------------------------------------

def draw_corner_ticks(screen, margin, color):
    w, h = screen.get_size()
    ln = max(8, int(min(w, h) * 0.018))
    # deliberately no lower-left tick: that corner belongs to the
    # controller's mode-number watermark (80x32 px).
    for x, y, sx, sy in ((margin, margin, 1, 1),
                         (w - margin, margin, -1, 1),
                         (w - margin, h - margin, -1, -1)):
        pygame.draw.line(screen, color, (x, y), (x + sx * ln, y), 1)
        pygame.draw.line(screen, color, (x, y), (x, y + sy * ln), 1)


def draw_world_labels(scene: Scene, screen, reserved):
    preset = scene.preset
    labels = set(preset.get("labels", ()))
    f = font(MONO, preset["label_px"])
    boxes: list[pygame.Rect] = list(reserved)
    order = sorted(WORLDS, key=lambda w: -scene.view.depth(
        world_position(w, scene.time)))
    for world in order:
        name = world[0]
        if name not in labels:
            continue
        base, p = world_screen(scene, world)
        if p is None:
            continue
        p = (p[0] / SS, p[1] / SS)
        r = max(2.0, scene.frame.scale_at(base) * world[7] / SS)
        idx = next(i for i, w in enumerate(WORLDS) if w[0] == name)
        numeral = ROMAN[idx]
        body = tracked(f"{numeral}  {name}", f, INK, 2, 225)
        gap = r + preset["label_gap"]
        sun = scene.screen_native(scene.sun_center) or (scene.width * 0.5,
                                                       scene.height * 0.5)
        dx, dy = p[0] - sun[0], p[1] - sun[1]
        order = []
        if abs(dx) >= abs(dy):
            order = ["right" if dx >= 0 else "left",
                     "down" if dy >= 0 else "up",
                     "up" if dy >= 0 else "down",
                     "left" if dx >= 0 else "right"]
        else:
            order = ["down" if dy >= 0 else "up",
                     "right" if dx >= 0 else "left",
                     "left" if dx >= 0 else "right",
                     "up" if dy >= 0 else "down"]
        by_dir = {
            # "right" means the label sits to the right of the world
            "right": ((p[0] + gap, p[1] - body.get_height() * 0.5), "left", 1),
            "left": ((p[0] - gap, p[1] - body.get_height() * 0.5), "right", 1),
            "up": ((p[0] - body.get_width() * 0.5,
                    p[1] - gap - body.get_height()), "center", 0),
            "down": ((p[0] - body.get_width() * 0.5, p[1] + gap), "center", -1),
        }
        candidates = tuple(by_dir[d] for d in order)
        margin = preset["label_margin"]
        bounds = pygame.Rect(0, 0, scene.width, scene.height).inflate(
            -2 * margin, -2 * margin)
        chosen = None
        for pos, align, direction in candidates:
            rect = body.get_rect()
            if align == "left":
                rect.topleft = (int(pos[0]), int(pos[1]))
            elif align == "right":
                rect.topright = (int(pos[0]), int(pos[1]))
            else:
                rect.midtop = (int(pos[0]), int(pos[1]))
            if not bounds.contains(rect):
                continue
            if any(rect.colliderect(other.inflate(8, 8)) for other in boxes):
                continue
            chosen = (rect, align, direction)
            break
        if chosen is None:
            continue
        rect, align, direction = chosen
        boxes.append(rect.inflate(8, 8))

        col = scale(BRASS_DIM, 0.9)
        if align == "left":
            start = (p[0] + r * 1.2, p[1])
            knee = (rect.left - 5, rect.centery)
            pygame.draw.line(screen, col, start, (knee[0] - 7, knee[1]), 1)
            pygame.draw.line(screen, col, (knee[0] - 7, knee[1]), knee, 1)
            pygame.draw.circle(screen, scale(BRASS, 0.75),
                               (int(start[0]), int(start[1])), 1)
        elif align == "right":
            start = (p[0] - r * 1.2, p[1])
            knee = (rect.right + 5, rect.centery)
            pygame.draw.line(screen, col, start, (knee[0] + 7, knee[1]), 1)
            pygame.draw.line(screen, col, (knee[0] + 7, knee[1]), knee, 1)
            pygame.draw.circle(screen, scale(BRASS, 0.75),
                               (int(start[0]), int(start[1])), 1)
        elif direction == 0:
            pygame.draw.line(screen, col, (p[0], p[1] - r * 1.2),
                             (rect.centerx, rect.bottom + 4), 1)
        else:
            pygame.draw.line(screen, col, (p[0], p[1] + r * 1.2),
                             (rect.centerx, rect.top - 4), 1)

        shadow = tracked(f"{numeral}  {name}", f, (4, 3, 3), 2, 160)
        for ox, oy in ((1, 1), (-1, 0), (0, -1), (1, 0), (0, 1)):
            screen.blit(shadow, (rect.left + ox, rect.top + oy))
        screen.blit(body, rect)


def draw_conjunction(scene: Scene, screen, reserved):
    """The signature moment: two worlds line up, a hairline joins them."""
    best = conjunction_pair(scene)
    if not best:
        return None
    d, a, b = best
    if d / SS > scene.preset["conjunction_px"]:
        return None
    p0 = (a[1][0] / SS, a[1][1] / SS)
    p1 = (b[1][0] / SS, b[1][1] / SS)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    # start and end at the spheres, not their centres
    r0 = max(5.0, scene.frame.scale_at(world_position(
        next(w for w in WORLDS if w[0] == a[0]), scene.time)) * WORLDS[
            next(i for i, w in enumerate(WORLDS) if w[0] == a[0])][7] / SS)
    r1 = max(5.0, scene.frame.scale_at(world_position(
        next(w for w in WORLDS if w[0] == b[0]), scene.time)) * WORLDS[
            next(i for i, w in enumerate(WORLDS) if w[0] == b[0])][7] / SS)
    q0 = (p0[0] + ux * r0 * 1.3, p0[1] + uy * r0 * 1.3)
    q1 = (p1[0] - ux * r1 * 1.3, p1[1] - uy * r1 * 1.3)
    if math.hypot(q1[0] - q0[0], q1[1] - q0[1]) < 18:
        return None
    overlay = pygame.Surface((scene.width, scene.height), pygame.SRCALPHA)
    pygame.draw.aaline(overlay, (*ACCENT, 195), q0, q1)
    pygame.draw.line(overlay, (*ACCENT, 55), q0, q1, 1)
    for p in (q0, q1):
        pygame.draw.circle(overlay, (*ACCENT, 120), (int(p[0]), int(p[1])),
                           3, 1)
    screen.blit(overlay, (0, 0))
    mid = ((q0[0] + q1[0]) * 0.5, (q0[1] + q1[1]) * 0.5)
    f = font(MONO, scene.preset["conjunction_label_px"])
    label = tracked("CONJUNCTION  ·  21:04", f, mix(ACCENT, INK, 0.35), 2, 225)
    rect = label.get_rect()
    candidates = [
        ("midbottom", (int(mid[0]), int(mid[1] - 10))),
        ("midtop", (int(mid[0]), int(mid[1] + 10))),
        ("midbottom", (int(mid[0]), int(mid[1] - 28))),
        ("midtop", (int(mid[0]), int(mid[1] + 28))),
    ]
    chosen = None
    for anchor, pos in candidates:
        r = rect.copy()
        setattr(r, anchor, pos)
        if r.left < 8 or r.top < 8 or r.right > scene.width - 8                 or r.bottom > scene.height - 8:
            continue
        if any(r.colliderect(other.inflate(10, 10)) for other in reserved):
            continue
        chosen = r
        break
    if chosen is None:
        return None
    shadow = tracked("CONJUNCTION  ·  21:04", f, (4, 3, 3), 2, 150)
    for ox, oy in ((1, 1), (-1, 0), (0, -1), (1, 0), (0, 1)):
        screen.blit(shadow, (chosen.left + ox, chosen.top + oy))
    screen.blit(label, chosen)
    return chosen.inflate(10, 6)


def hud_reserved(scene: Scene) -> list[pygame.Rect]:
    preset = scene.preset
    w, h = scene.width, scene.height
    m = preset["hud_margin"]
    if preset.get("title_layout") == "portrait":
        boxes = [pygame.Rect(m - 8, m - 8, int(w * 0.62), 220)]
    else:
        boxes = [pygame.Rect(m - 8, m - 8, int(w * 0.40), 74)]
    boxes.append(pygame.Rect(w - m - 220, m - 8, 228, 66))
    # controller's mode-number strip: lower left
    boxes.append(pygame.Rect(0, h - 64, 120, 64))
    if preset.get("bottom_plaque"):
        boxes.append(pygame.Rect(0, int(h * preset["plaque_y"]) - 10, w, h))
    return boxes


def draw_hud(scene: Scene, screen):
    w, h = screen.get_size()
    preset = scene.preset
    m = preset["hud_margin"]
    p_title = font(MONO_BOLD, preset["title_px"])
    p_sub = font(MONO, preset["sub_px"])
    p_tele = font(MONO, preset["tele_px"])

    draw_corner_ticks(screen, m, scale(BRASS_DIM, 0.9))

    if preset.get("title_layout") == "portrait":
        eyebrow = tracked("SLOW WORLDS  ·  THE LONG VIEW", p_sub,
                          scale(BRASS, 0.8), 2, 220)
        screen.blit(eyebrow, (m, m))
        y = m + eyebrow.get_height() + 12
        line1 = tracked("THE ORRERY", p_title, INK, preset.get("title_track", 1))
        line2 = tracked("OF SMALL WORLDS", p_title, INK,
                        preset.get("title_track", 1))
        screen.blit(line1, (m, y))
        y += line1.get_height() + preset.get("title_leading", 4)
        screen.blit(line2, (m, y))
        y += line2.get_height() + 16
        pygame.draw.line(screen, scale(BRASS, 0.55), (m, y),
                         (m + int(w * 0.33), y), 1)
        sub = tracked("A BRASS INSTRUMENT  ·  SEVEN INVENTED WORLDS",
                      p_sub, INK_DIM, 1, 235)
        screen.blit(sub, (m, y + 14))

        tele = tracked("INSTR. 03/09", p_tele, scale(BRASS, 0.9), 1)
        screen.blit(tele, (w - m - tele.get_width(), m))
        epoch = tracked("EPOCH  21:04", p_tele, INK_DIM, 1, 220)
        screen.blit(epoch, (w - m - epoch.get_width(),
                            m + tele.get_height() + 8))
    else:
        title = tracked(preset["title"], p_title, INK,
                        preset.get("title_track", 2))
        screen.blit(title, (m, m))
        rule_y = m + title.get_height() + 5
        pygame.draw.line(screen, scale(BRASS, 0.65), (m, rule_y),
                         (m + max(160, int(title.get_width() * 0.70)), rule_y),
                         1)
        sub = tracked(preset["subtitle"], p_sub, INK_DIM, 1, 235)
        screen.blit(sub, (m, rule_y + 7))
        tele1 = tracked("INSTR.  03/09", p_tele, scale(BRASS, 0.9), 1)
        screen.blit(tele1, (w - m - tele1.get_width(), m))
        tele2 = tracked("EPOCH  21:04", p_tele, INK_DIM, 1, 220)
        screen.blit(tele2, (w - m - tele2.get_width(),
                            m + tele1.get_height() + 7))

    # a small label for the lamp itself
    sun = scene.screen_native(scene.sun_center)
    if sun:
        f = font(MONO, preset["lamp_label_px"])
        lamp = tracked("THE LAMP", f, scale(BRASS, 0.75), 1, 190)
        lr = lamp.get_rect()
        lr.midtop = (int(sun[0]), int(sun[1] + scene.sun_px / SS * 3.4))
        pygame.draw.line(screen, scale(BRASS_DIM, 0.9),
                         (sun[0], sun[1] + scene.sun_px / SS * 2.0),
                         (sun[0], lr.top - 3), 1)
        screen.blit(lamp, lr)


def draw_plaque(scene: Scene, screen):
    """Portrait only: the maker's plate under the instrument."""
    preset = scene.preset
    if not preset.get("bottom_plaque"):
        return
    w, h = screen.get_size()
    cx = w // 2
    y = int(h * preset["plaque_y"])
    pw = int(w * preset["plaque_width"])
    ph = int(preset["plaque_h"])

    plate = pygame.Surface((pw, ph), pygame.SRCALPHA)
    # dark brass ground, lit from above, with a shallow bevel
    plate.fill((19, 14, 10, 246))
    pygame.draw.rect(plate, (*scale(BRASS_DIM, 0.75), 210), (0, 0, pw, ph), 1)
    pygame.draw.line(plate, (*scale(BRASS_HI, 0.55), 140), (10, 1),
                     (pw - 10, 1), 1)
    pygame.draw.line(plate, (*scale(BRASS, 0.35), 120), (1, 8),
                     (1, ph - 8), 1)
    pygame.draw.line(plate, (*scale(BRASS_DEEP, 0.85), 200), (10, ph - 2),
                     (pw - 10, ph - 2), 1)
    pygame.draw.rect(plate, (*scale(BRASS_DIM, 0.55), 90),
                     (7, 7, pw - 14, ph - 14), 1)
    # fine brushed grain
    rng = random.Random(31)
    for _ in range(90):
        gy = rng.randrange(8, ph - 8)
        gx = rng.randrange(8, pw - 30)
        gl = rng.randrange(12, 90)
        pygame.draw.line(plate, (*BRASS_MID, rng.choice((8, 10, 13))),
                         (gx, gy), (gx + gl, gy), 1)
    # corner screws
    for sx in (16, pw - 16):
        for sy in (16, ph - 16):
            pygame.draw.circle(plate, (*scale(BRASS_DIM, 0.9), 190),
                               (sx, sy), 3)
            pygame.draw.line(plate, (*scale(BRASS_HI, 0.7), 150),
                             (sx - 2, sy), (sx + 2, sy), 1)

    f_serif = font(SERIF, preset["plaque_serif_px"])
    f_mono = font(MONO, preset["plaque_mono_px"])
    f_small = font(MONO, max(9, preset["plaque_mono_px"] - 2))
    main = tracked("THE AUREL SYSTEM", f_serif, scale(BRASS, 0.98),
                   preset["plaque_track"])
    sub = tracked("SEVEN INVENTED WORLDS  ·  ONE LAMP AT THE FOCUS", f_mono,
                  INK_DIM, 2, 215)
    num = tracked("PERIODS 47–239 s  ·  INCLINATIONS 3°–12°", f_small,
                  INK_FAINT, 1, 170)

    main_rect = main.get_rect()
    main_rect.centerx = pw // 2
    main_rect.top = int(ph * 0.17)
    rule_y = main_rect.bottom + int(ph * 0.12)
    pygame.draw.line(plate, (*scale(BRASS, 0.55), 130), (int(pw * 0.18), rule_y),
                     (int(pw * 0.82), rule_y), 1)
    sub_rect = sub.get_rect()
    sub_rect.centerx = pw // 2
    sub_rect.top = rule_y + int(ph * 0.14)
    num_rect = num.get_rect()
    num_rect.centerx = pw // 2
    num_rect.top = sub_rect.bottom + int(ph * 0.08)

    plate.blit(main, main_rect)
    plate.blit(sub, sub_rect)
    plate.blit(num, num_rect)
    screen.blit(plate, (cx - pw // 2, y))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(size, preset, time_s=21.0):
    scene = Scene(size, preset, time_s)
    big = pygame.Surface((scene.w, scene.h))
    draw_background(scene, big)
    draw_floor_rings(scene, big)
    draw_plate(scene, big)

    sun_depth = scene.view.depth(scene.sun_center)

    if preset.get("armature"):
        draw_armature(scene, big)

    ordered = sorted(WORLDS, key=lambda w: -scene.view.depth(
        world_position(w, time_s)))
    for world in ordered:
        draw_rail_segments(scene, big, world, sun_depth, front=False)
    for world in ordered:
        if scene.view.depth(world_position(world, time_s)) > sun_depth:
            draw_world_body(scene, big, world)

    draw_sun(scene, big)

    for world in ordered:
        draw_rail_segments(scene, big, world, sun_depth, front=True)
    for world in ordered:
        if scene.view.depth(world_position(world, time_s)) <= sun_depth:
            draw_world_body(scene, big, world)

    draw_comet(scene, big)
    draw_dust(scene, big)

    screen = pygame.transform.smoothscale(big, (scene.width, scene.height))
    composite_glow(screen, preset.get("glow", 0.62))
    apply_finish(screen, preset.get("vignette", 0.38),
                 preset.get("scanlines", 7))
    reserved = hud_reserved(scene)
    conj = draw_conjunction(scene, screen, reserved)
    if conj is not None:
        reserved.append(conj)
    draw_world_labels(scene, screen, reserved)
    draw_hud(scene, screen)
    draw_plaque(scene, screen)
    return screen


def draw_armature(scene: Scene, dst):
    """A brass meridian arch standing on the plate; portrait only."""
    cfg = scene.preset["armature"]
    outer = armature_points(cfg, steps=140)
    inner_cfg = dict(cfg)
    inner_cfg["radius"] = float(cfg.get("radius", 1.02)) - 0.035
    inner = armature_points(inner_cfg, steps=140)
    overlay = pygame.Surface((scene.w, scene.h), pygame.SRCALPHA)

    for rail in (outer, inner):
        for i in range(len(rail) - 1):
            p0 = scene.frame.project(rail[i])
            p1 = scene.frame.project(rail[i + 1])
            if p0 and p1:
                pygame.draw.line(overlay, (*scale(BRASS_DIM, 0.8), 140), p0, p1,
                                 max(2, int(2.6 * SS)))
                pygame.draw.line(overlay, (*scale(BRASS, 0.82), 165), p0, p1,
                                 max(1, int(1.2 * SS)))

    # graduations between the two rails
    count = 90
    for i in range(count + 1):
        t = i / count
        po = scene.frame.project(outer[i])
        pi = scene.frame.project(inner[i])
        if not (po and pi):
            continue
        long = (i % 15 == 0)
        mid = (i % 5 == 0)
        if i % 2 and not mid:
            continue
        # slide the tick in from the outer rail by a varying amount
        k = 1.0 if long else 0.62 if mid else 0.35
        p1 = (po[0] + (pi[0] - po[0]) * k, po[1] + (pi[1] - po[1]) * k)
        fade = 0.55 + 0.45 * math.sin(math.pi * t)
        pygame.draw.line(overlay, (*scale(BRASS_HI, 0.9),
                                   int((155 if long else 90) * fade)),
                         po, p1, max(1, int((1.4 if long else 1.0) * SS)))

    # feet where the arch meets the rim, and a finial at the crown
    for end_point in (outer[0], outer[-1]):
        sp = scene.frame.project(end_point)
        if sp:
            pygame.draw.circle(overlay, (*scale(BRASS_MID, 0.85), 190),
                               (int(sp[0]), int(sp[1])), max(2, int(3.6 * SS)))
    crown = scene.frame.project(outer[len(outer) // 2])
    if crown:
        r = max(3, int(3.4 * SS))
        pygame.draw.circle(overlay, (*scale(BRASS, 0.85), 210),
                           (int(crown[0]), int(crown[1])), r)
        pygame.draw.circle(overlay, (*scale(BRASS_HI, 0.95), 180),
                           (int(crown[0]), int(crown[1])), max(1, r // 2))
    dst.blit(overlay, (0, 0))


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

LANDSCAPE = {
    "name": "ultrawide_1280x400",
    "size": (1280, 400),
    "elevation": 16.0,
    "azimuth": -9.0,
    "rect": (64, 42, 1216, 374),
    "seed": 2001,
    "time": 21.0,
    "title": "ORRERY OF SMALL WORLDS",
    "subtitle": "A BRASS INSTRUMENT  ·  SEVEN INVENTED WORLDS",
    "title_layout": "wide",
    "hud_margin": 24,
    "title_px": 18,
    "title_track": 2,
    "sub_px": 11,
    "tele_px": 11,
    "lamp_label_px": 10,
    "label_px": 12,
    "label_gap": 12,
    "label_margin": 18,
    "plaque_text_px": 12,
    "conjunction_label_px": 10,
    "conjunction_px": 130,
    "labels": ("TACE", "VELA", "MORA", "ILUN", "SORREL", "ORMA", "NIX"),
    "specks": 80,
    "dust": 20,
    "bokeh": ((0.115, 0.79, 9, 0.16), (0.905, 0.66, 13, 0.14),
              (0.79, 0.30, 7, 0.12), (0.22, 0.20, 6, 0.10)),
    "glow": 0.60,
    "vignette": 0.42,
    "scanlines": 7,
    "comet_phase": 150.0,
}

PORTRAIT = {
    "name": "portrait_1080x1920",
    "size": (1080, 1920),
    "elevation": 33.0,
    "azimuth": -13.0,
    "rect": (48, 420, 1032, 1370),
    "seed": 2001,
    "time": 21.0,
    "title": "ORRERY OF SMALL WORLDS",
    "subtitle": "A BRASS INSTRUMENT",
    "title_layout": "portrait",
    "hud_margin": 48,
    "title_px": 40,
    "title_track": 1,
    "title_leading": 4,
    "sub_px": 16,
    "tele_px": 15,
    "lamp_label_px": 14,
    "label_px": 16,
    "label_gap": 16,
    "label_margin": 26,
    "plaque_text_px": 16,
    "conjunction_label_px": 13,
    "conjunction_px": 175,
    "conjunction_target_px": 140,
    "labels": ("TACE", "VELA", "MORA", "ILUN", "SORREL", "ORMA", "NIX"),
    "specks": 150,
    "dust": 32,
    "bokeh": ((0.10, 0.70, 13, 0.14), (0.90, 0.62, 18, 0.12),
              (0.18, 0.47, 9, 0.10), (0.82, 0.27, 11, 0.10),
              (0.12, 0.87, 15, 0.10)),
    "glow": 0.62,
    "vignette": 0.42,
    "scanlines": 7,
    "comet_phase": 40.0,
    "armature": {"radius": 1.02, "yaw": -8.0, "lift": 0.0},
    "bottom_plaque": True,
    "plaque_y": 0.752,
    "plaque_width": 0.82,
    "plaque_h": 176,
    "plaque_serif_px": 26,
    "plaque_mono_px": 15,
    "plaque_track": 4,
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    # The hero stills are deliberately not written here:
    # scripts/orrery_preview.py renders them from modes/orrery_mode.py, so this
    # design tool can never overwrite the shipping frames with a prototype.

    # Camera study: the same instrument at three elevations, for review.
    study_size = (1080, 560)
    rows = ((13.0, "13 deg  ·  shallow glance"),
            (19.0, "19 deg"),
            (27.0, "27 deg  ·  steeper, rounder ovals"))
    sheet = pygame.Surface((study_size[0], (study_size[1] + 26) * len(rows)))
    sheet.fill((4, 3, 4))
    f = pygame.font.Font(MONO_BOLD, 16)
    f2 = pygame.font.Font(MONO, 12)
    for index, (elev, note) in enumerate(rows):
        preset = dict(LANDSCAPE)
        preset.update({"size": study_size,
                       "elevation": elev,
                       "rect": (24, 34, 1056, 550),
                       "title_px": 14, "sub_px": 9, "tele_px": 9,
                       "label_px": 10, "plaque_text_px": 10,
                       "conjunction_px": 70,
                       "labels": ("VELA", "MORA", "ILUN", "ORMA")})
        img = render(study_size, preset, 21.0)
        y = index * (study_size[1] + 26) + 26
        sheet.blit(img, (0, y))
        pygame.draw.line(sheet, (60, 48, 30), (0, y - 5),
                         (study_size[0], y - 5), 1)
        sheet.blit(f.render(note, True, (214, 197, 160)), (16, y - 23))
        sheet.blit(f2.render("oval ratio  w : h = 1 : %.2f" %
                             math.sin(math.radians(elev)),
                             True, (140, 125, 100)), (380, y - 22))
    path = os.path.join(OUT_DIR, "camera_study.png")
    pygame.image.save(sheet, path)
    print(f"wrote {os.path.relpath(path, BASE_DIR)}")

    pygame.quit()


if __name__ == "__main__":
    main()
