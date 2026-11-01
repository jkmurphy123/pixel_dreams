"""The Orrery of Small Worlds — Slow Worlds §5.1.

A brass orrery of seven invented worlds turns in a dark observatory.  A camera
looks down on the instrument at an angle, so every circular rail projects to an
oval; the angle is chosen by the screen's aspect class rather than scaled from
one fixed view:

  * the 1280x400 strip looks down at 16 degrees (very wide ovals),
  * the portrait wall looks down at 33 degrees (rounder ovals, with a vertical
    meridian arch and a maker's plate),
  * 16:9 and square get their own presets.

The camera fit projects the plate, rails and arch once, measures their 2D
bounding box and fits it to a safe rectangle, so changing tilt or screen size
never clips the instrument.  The lower-left 80x32 px stays clear for the
controller's mode number.

The plaque is a real config switch (`show_plaque`, default false).  The narrow
strip turns it off; the portrait profile turns it on.  Its text is a made-up
description of the system on display ("THE AUREL SYSTEM"), not a maker's mark.

Static detail (background, plate, rim engraving, Latin dedication, armature,
rail geometry, vignette map, plaque, HUD text) is cached when the screen or
camera changes.  Only the worlds, moons, comet, dust, labels and the sun's glow
are drawn per frame.  The design stills in screenshots/orrery/ were rendered by
this mode at native resolution, not by the 2x prototype.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

TAU = math.tau

# ---------------------------------------------------------------------------
# Palette families — the collection's "Brass & Ink" and its two siblings.
# ---------------------------------------------------------------------------

RGB = tuple[int, int, int]


def _clamp8(value) -> int:
    return 0 if value < 0 else 255 if value > 255 else int(value)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else float(t)
    return (_clamp8(a[0] + (b[0] - a[0]) * t),
            _clamp8(a[1] + (b[1] - a[1]) * t),
            _clamp8(a[2] + (b[2] - a[2]) * t))


def scale(color: RGB, factor: float) -> RGB:
    if factor <= 0.0:
        return (0, 0, 0)
    return (_clamp8(color[0] * factor), _clamp8(color[1] * factor),
            _clamp8(color[2] * factor))


@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: RGB
    bg_bottom: RGB
    haze: RGB
    ink: RGB
    ink_dim: RGB
    ink_faint: RGB
    structure_hi: RGB
    structure: RGB
    structure_dim: RGB
    structure_deep: RGB
    accent: RGB
    glow: RGB
    warm_white: RGB
    plate_center: RGB
    plate_edge: RGB
    plate_side: RGB
    world_tints: tuple[RGB, ...]


PALETTES = {
    "brass": Palette(
        name="brass",
        bg_top=(11, 9, 9), bg_bottom=(2, 2, 3), haze=(46, 30, 14),
        ink=(232, 220, 192), ink_dim=(158, 144, 119), ink_faint=(96, 86, 70),
        structure_hi=(246, 207, 132), structure=(201, 164, 92),
        structure_dim=(95, 74, 42), structure_deep=(54, 41, 24),
        accent=(127, 183, 163), glow=(242, 200, 121),
        warm_white=(255, 238, 204),
        plate_center=(29, 23, 18), plate_edge=(11, 9, 8),
        plate_side=(43, 32, 21),
        world_tints=((236, 223, 198), (228, 190, 126), (208, 196, 172),
                     (147, 193, 174), (214, 158, 106)),
    ),
    "verdigris": Palette(
        name="verdigris",
        bg_top=(7, 12, 11), bg_bottom=(2, 4, 4), haze=(28, 46, 40),
        ink=(223, 236, 226), ink_dim=(150, 176, 160), ink_faint=(88, 112, 102),
        structure_hi=(180, 226, 208), structure=(112, 170, 154),
        structure_dim=(62, 100, 90), structure_deep=(34, 56, 50),
        accent=(226, 182, 106), glow=(230, 214, 166),
        warm_white=(244, 250, 240),
        plate_center=(22, 32, 29), plate_edge=(8, 12, 11),
        plate_side=(34, 48, 43),
        world_tints=((223, 236, 226), (232, 214, 168), (180, 208, 194),
                     (147, 193, 174), (210, 172, 124)),
    ),
    "bone": Palette(
        name="bone",
        bg_top=(12, 11, 9), bg_bottom=(3, 3, 3), haze=(52, 44, 30),
        ink=(236, 228, 212), ink_dim=(170, 158, 138), ink_faint=(104, 96, 82),
        structure_hi=(238, 224, 192), structure=(184, 169, 140),
        structure_dim=(118, 106, 84), structure_deep=(66, 59, 47),
        accent=(143, 168, 184), glow=(240, 220, 180),
        warm_white=(255, 246, 228),
        plate_center=(30, 27, 22), plate_edge=(12, 10, 9),
        plate_side=(46, 41, 33),
        world_tints=((236, 228, 212), (226, 206, 168), (200, 194, 180),
                     (143, 168, 184), (206, 172, 136)),
    ),
}


def get_palette(name: str) -> Palette:
    palette = PALETTES.get(str(name).lower())
    if palette is None:
        raise ValueError("palette must be " + ", ".join(sorted(PALETTES)))
    return palette


# ---------------------------------------------------------------------------
# Worlds — nine invented bodies on inclined, eccentric rails.
# ---------------------------------------------------------------------------

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")
NUMBER_WORDS = {5: "FIVE", 6: "SIX", 7: "SEVEN", 8: "EIGHT", 9: "NINE"}
LATIN_WORDS = {5: "QUINQUE", 6: "SEX", 7: "SEPTEM", 8: "OCTO", 9: "NOVEM"}


@dataclass(frozen=True)
class WorldSpec:
    name: str
    eccentricity: float
    inclination: float
    node: float
    phase: float
    period_mult: float
    size: float
    tint: int


WORLD_SPECS = (
    WorldSpec("TACE",   0.055, 12.0,  14.0, 300.0, 0.52, 0.0130, 0),
    WorldSpec("VELA",   0.080, 10.0,  -7.0, 143.0, 0.79, 0.0165, 1),
    WorldSpec("MORA",   0.065,  8.5,   4.0, 268.0, 1.26, 0.0190, 2),
    WorldSpec("ILUN",   0.050,  7.0, -15.0,  35.0, 1.46, 0.0175, 3),
    WorldSpec("SORREL", 0.075,  5.5,  10.0, 196.0, 1.86, 0.0215, 1),
    WorldSpec("NIX",    0.040,  4.0,  -2.0, 308.0, 2.21, 0.0160, 0),
    WorldSpec("ORMA",   0.055,  3.0,   7.0,  78.0, 2.66, 0.0225, 2),
    WorldSpec("THALE",  0.045,  2.5,  18.0, 120.0, 2.89, 0.0180, 4),
    WorldSpec("CIRRUS", 0.060,  2.0,  -4.0, 250.0, 3.11, 0.0195, 0),
)


@dataclass(frozen=True)
class World:
    index: int
    name: str
    a: float
    eccentricity: float
    inclination: float
    node: float
    phase: float
    period: float
    size: float
    tint: int

    def point(self, theta: float):
        b = self.a * math.sqrt(max(0.0, 1.0 - self.eccentricity ** 2))
        ex = self.a * math.cos(theta) - self.a * self.eccentricity
        ez = b * math.sin(theta)
        ey = ez * math.sin(math.radians(self.inclination))
        ez = ez * math.cos(math.radians(self.inclination))
        no = math.radians(self.node)
        wx = ex * math.cos(no) - ez * math.sin(no)
        wz = ex * math.sin(no) + ez * math.cos(no)
        return (wx, 0.105 + ey, wz)

    def position(self, t: float):
        return self.point(math.radians(self.phase) + TAU * (t / self.period))

    def rail(self, steps: int):
        return [self.point(TAU * i / steps) for i in range(steps + 1)]


def build_worlds(count: int, orbit_seconds: float) -> list[World]:
    worlds = []
    denom = max(1, count - 1)
    for index in range(count):
        spec = WORLD_SPECS[index]
        a = 0.25 + (0.92 - 0.25) * index / denom
        worlds.append(World(
            index=index,
            name=spec.name,
            a=a,
            eccentricity=spec.eccentricity,
            inclination=spec.inclination,
            node=spec.node,
            phase=spec.phase,
            period=orbit_seconds * spec.period_mult,
            size=spec.size,
            tint=spec.tint,
        ))
    return worlds


# ---------------------------------------------------------------------------
# Camera / projection
# ---------------------------------------------------------------------------

def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vmul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _vnorm(a):
    n = math.sqrt(_vdot(a, a))
    if n <= 1e-9:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


class View:
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
        self.pos = _vadd(target, _vmul(offset, distance))
        self.forward = _vnorm(_vsub(target, self.pos))
        self.right = _vnorm(_vcross(self.forward, (0.0, 1.0, 0.0)))
        self.up = _vcross(self.right, self.forward)

    def raw(self, point):
        rel = _vsub(point, self.pos)
        zv = _vdot(rel, self.forward)
        if zv <= 0.05:
            return None, zv
        return (_vdot(rel, self.right) / zv, _vdot(rel, self.up) / zv), zv

    def depth(self, point) -> float:
        return _vdot(_vsub(point, self.pos), self.forward)


class Frame:
    def __init__(self, view: View, rect: pygame.Rect, points):
        self.view = view
        self.rect = pygame.Rect(rect)
        raw = []
        for point in points:
            p, _zv = view.raw(point)
            if p is not None:
                raw.append(p)
        if not raw:
            raise ValueError("the instrument is entirely behind the camera")
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
        zv = self.view.depth(point)
        return self.focal / max(0.05, zv)


def circle_points(radius: float, y: float, steps: int = 180):
    return [(radius * math.cos(TAU * i / steps), y,
             radius * math.sin(TAU * i / steps)) for i in range(steps + 1)]


def armature_points(radius: float, yaw_deg: float, steps: int = 120):
    yaw = math.radians(yaw_deg)
    points = []
    for i in range(steps + 1):
        ang = math.pi * i / steps
        points.append((radius * math.cos(ang) * math.cos(yaw),
                       radius * math.sin(ang),
                       radius * math.cos(ang) * math.sin(yaw)))
    return points


# ---------------------------------------------------------------------------
# Layout presets
# ---------------------------------------------------------------------------

PRESETS = {
    # key: (elevation, azimuth, layout, armature, safe margins as fractions,
    #       base size, HUD sizes, label size, rim text size)
    "ultrawide": {
        "elevation": 16.0, "azimuth": -9.0, "layout": "wide",
        "armature": False, "safe": (0.050, 0.105, 0.950, 0.935),
        "base": (1280, 400), "hud_margin": 24, "title_px": 18,
        "sub_px": 12, "tele_px": 12, "lamp_px": 10, "label_px": 12,
        "rim_text_px": 12, "title_track": 2, "aux_track": 1,
    },
    "landscape": {
        "elevation": 20.0, "azimuth": -10.0, "layout": "wide",
        "armature": False, "safe": (0.060, 0.145, 0.940, 0.900),
        "base": (1920, 1080), "hud_margin": 40, "title_px": 26,
        "sub_px": 14, "tele_px": 13, "lamp_px": 12, "label_px": 15,
        "rim_text_px": 16, "title_track": 2, "aux_track": 1,
    },
    "portrait": {
        "elevation": 33.0, "azimuth": -13.0, "layout": "portrait",
        "armature": True, "safe": (0.045, 0.218, 0.955, 0.714),
        "base": (1080, 1920), "hud_margin": 48, "title_px": 40,
        "sub_px": 16, "tele_px": 16, "lamp_px": 14, "label_px": 16,
        "rim_text_px": 16, "title_track": 1, "aux_track": 2,
    },
    "square": {
        "elevation": 27.0, "azimuth": -11.0, "layout": "wide",
        "armature": False, "safe": (0.060, 0.130, 0.940, 0.900),
        "base": (720, 720), "hud_margin": 28, "title_px": 24,
        "sub_px": 13, "tele_px": 12, "lamp_px": 11, "label_px": 14,
        "rim_text_px": 14, "title_track": 2, "aux_track": 1,
    },
}
ORIENTATIONS = ("auto", "ultrawide", "landscape", "portrait", "square")

QUALITY = {
    "low": {"rail_steps": 96, "moons": 1, "glow_div": 8, "dust": 14,
            "stars": 50, "engraving": 0.55},
    "medium": {"rail_steps": 144, "moons": 2, "glow_div": 4, "dust": 26,
               "stars": 80, "engraving": 0.85},
    "high": {"rail_steps": 192, "moons": 2, "glow_div": 3, "dust": 36,
             "stars": 120, "engraving": 1.0},
}
QUALITY_NAMES = ("auto", "low", "medium", "high")
HUD_MODES = ("full", "minimal", "off")

_PLATE_RIM = 1.032
_PLATE_THICK = 0.018
_CACHE_MARGIN = 8


def aspect_class(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
    if aspect >= 1.2:
        return "landscape"
    if aspect <= 0.85:
        return "portrait"
    return "square"


# ---------------------------------------------------------------------------
# Text / light helpers
# ---------------------------------------------------------------------------

def tracked(text: str, font: pygame.font.Font, color, spacing: int = 0,
            alpha: int = 255):
    glyphs = [font.render(ch, True, color) for ch in text]
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


def radial_glow(radius_px: int, color: RGB, power: float = 2.2):
    base = 160
    small = pygame.Surface((base, base))
    small.fill((0, 0, 0))
    steps = 72
    for i in range(steps, 0, -1):
        t = i / steps
        k = (1.0 - t) ** power
        pygame.draw.circle(small, scale(color, k * 0.20),
                           (base // 2, base // 2), int(base * 0.5 * t))
    size = max(2, radius_px * 2)
    return pygame.transform.smoothscale(small, (size, size))


def blit_glow(dst, center, radius_px: int, color: RGB, power=2.2,
              strength=1.0):
    if radius_px < 2:
        return
    sprite = radial_glow(radius_px, scale(color, strength), power)
    dst.blit(sprite, (int(center[0]) - radius_px,
                      int(center[1]) - radius_px),
             special_flags=pygame.BLEND_RGB_ADD)


# ---------------------------------------------------------------------------
# The mode
# ---------------------------------------------------------------------------

class OrreryMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self.error_message = ""

        self._pinned_seed = None
        self._palette = PALETTES["brass"]
        self._world_count = 7
        self._orbit_seconds = 90.0
        self._show_labels = True
        self._show_comet = True
        self._show_conjunctions = True
        self._show_plaque = False
        self._camera_drift = 1.0
        self._camera_elevation_override = None
        self._camera_azimuth_override = None
        self._glow = 0.62
        self._scanlines = 7
        self._vignette = 0.42
        self._hud_mode = "full"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._orientation = "auto"
        self._title = "ORRERY OF SMALL WORLDS"
        self._subtitle = ""
        self._worlds: list[World] = []
        self._time = 0.0
        self._start_time = 0.0
        self._comet_phase = 0.0
        self._screen_size = None
        self._layout = None
        self._frame = None
        self._conj_pair = None
        self._conj_globals = []
        self._conj_until = 0.0
        self._conj_cooldown = 0.0
        self._conj_pair_cooldown = {}
        self._conj_label = None
        self._conj_rect = None
        self._last_label_boxes = []
        self._last_segments = 0
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
        value = value.strip()
        return value[:max_length]

    @staticmethod
    def _auto_number(config, key, lo, hi):
        value = config.get(key, "auto")
        if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
            return None
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f"{key} must be 'auto' or a number") from None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be 'auto' or a number")
        value = float(value)
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be 'auto' or a number in {lo}..{hi}")
        return value

    def _read_config(self):
        cfg = self.config
        seed = cfg.get("seed")
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
                raise ValueError("seed must be an integer in 0..2147483647 or null")
        self._pinned_seed = seed

        self._palette = get_palette(cfg.get("palette", "brass"))
        self._world_count = self._integer(cfg, "world_count", 7, 5, 9)
        self._orbit_seconds = self._number(cfg, "orbit_seconds", 90.0, 45.0, 300.0)
        self._show_labels = self._bool(cfg, "show_labels", True)
        self._show_comet = self._bool(cfg, "show_comet", True)
        self._show_conjunctions = self._bool(cfg, "show_conjunctions", True)
        self._show_plaque = self._bool(cfg, "show_plaque", False)
        self._camera_drift = self._number(cfg, "camera_drift", 1.0, 0.0, 3.0)
        self._camera_elevation_override = self._auto_number(
            cfg, "camera_elevation", 5.0, 60.0)
        self._camera_azimuth_override = self._auto_number(
            cfg, "camera_azimuth", -35.0, 35.0)
        self._glow = self._number(cfg, "glow_strength", 0.62, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 7.0, 0.0, 80.0))
        self._vignette = self._number(cfg, "vignette_strength", 0.42, 0.0, 1.0)

        hud = str(cfg.get("hud", "minimal")).lower()
        if hud not in HUD_MODES:
            raise ValueError("hud must be full, minimal, or off")
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

        self._title = self._text(cfg, "title", "ORRERY OF SMALL WORLDS", 48) \
            or "ORRERY OF SMALL WORLDS"
        self._subtitle = self._text(cfg, "subtitle", "", 72)

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            self._worlds = build_worlds(self._world_count, self._orbit_seconds)
            self.seed = self._next_seed()
            rng = random.Random(self.seed ^ 0x0A11E7)
            self._start_time = rng.uniform(0.0, 240.0)
            self._time = self._start_time
            self._comet_phase = rng.uniform(0.0, 360.0)
            self._quality = "medium" if self._auto_quality else self._quality_setting
            self._quality_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self._conj_pair = None
            self._conj_until = 0.0
            self._conj_cooldown = 0.0
            self._conj_pair_cooldown = {}
            self._conj_rect = None
            if not self._subtitle:
                self._subtitle = (f"A {self._palette.name.upper()} INSTRUMENT · "
                                  f"{NUMBER_WORDS[self._world_count]} INVENTED WORLDS")
            self._build(manager.screen.get_size())
            self._update_conjunction(force=True)
            print(f"[Orrery] seed={self.seed} preset={self._layout['preset']} "
                  f"elevation={self._layout['elevation']:.0f} "
                  f"worlds={self._world_count} quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"plaque={self._show_plaque} size={self._screen_size[0]}x"
                  f"{self._screen_size[1]}")
            self.error = None
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Orrery] configuration error: {exc}")

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def exit(self):
        self.manager = None
        self.error = None
        self._clear_caches()
        self._screen_size = None
        self._layout = None
        self._frame = None
        self._worlds = []
        self._time = 0.0
        self._conj_pair = None
        self._conj_label = None
        self._conj_rect = None
        self._last_label_boxes = []

    def _clear_caches(self):
        self._room = None
        self._rails_back = None
        self._rails_front = None
        self._finish = None
        self._rails_rect = None
        self._bloom_small = None
        self._bloom_mid = None
        self._bloom_up = None
        self._sun_glows = []
        self._comet_glow = None
        self._hud = None
        self._plaque = None
        self._label_surfaces = []
        self._dust = []
        self._last_segments = 0

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
        self._update_conjunction()

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
            self._set_quality(target)

    def _set_quality(self, quality: str) -> None:
        if quality == self._quality or quality not in QUALITY:
            return
        previous = self._quality
        self._quality = quality
        self._rebuild_rails()
        self._build_glow_sprites()
        self._build_dust()
        self._build_bloom()
        self.diagnostic = f"auto quality {previous} -> {quality}"
        print(f"[Orrery] {self.diagnostic}")

    def _offset(self):
        if self._camera_drift <= 0.0:
            return 0.0, 0.0
        amp = self._camera_drift
        return (amp * math.sin(self._time * TAU / 47.0),
                amp * 0.55 * math.sin(self._time * TAU / 71.0 + 1.1))

    def _epoch_minutes(self) -> int:
        elapsed = max(0, int(self._time - self._start_time))
        return (21 * 60 + 4 + elapsed // 60) % (24 * 60)

    def _epoch_text(self) -> str:
        minutes = self._epoch_minutes()
        return f"EPOCH  {minutes // 60:02d}:{minutes % 60:02d}"

    # ---------------------------------------------------------------- layout

    def _resolve_layout(self, size) -> dict:
        width, height = int(size[0]), int(size[1])
        preset_name = (aspect_class(width, height)
                       if self._orientation == "auto" else self._orientation)
        preset = PRESETS[preset_name]
        elevation = (preset["elevation"] if self._camera_elevation_override is None
                     else self._camera_elevation_override)
        azimuth = (preset["azimuth"] if self._camera_azimuth_override is None
                   else self._camera_azimuth_override)
        sx0, sy0, sx1, sy1 = preset["safe"]
        safe = pygame.Rect(int(sx0 * width), int(sy0 * height),
                           max(20, int((sx1 - sx0) * width)),
                           max(20, int((sy1 - sy0) * height)))
        base_w, base_h = preset["base"]
        scale = min(1.0, width / base_w, height / base_h)
        scale = max(0.30, scale)
        hud_margin = max(9, int(preset["hud_margin"] * scale))

        plaque = None
        if self._show_plaque:
            if preset_name == "portrait":
                pw = int(width * 0.82)
                ph = max(70, int(height * 0.092))
                px = (width - pw) // 2
                py = int(height * 0.752)
            else:
                pw = int(width * 0.62)
                ph = max(46, int(height * 0.14))
                px = (width - pw) // 2
                py = height - hud_margin - ph
            if py + ph > height - 8:
                py = max(8, height - ph - 8)
            plaque = pygame.Rect(px, py, pw, ph)
            if preset_name != "portrait":
                safe.height = max(20, plaque.top - 8 - safe.top)
        layout = dict(preset)
        layout.update({
            "preset": preset_name,
            "elevation": elevation,
            "azimuth": azimuth,
            "scale": scale,
            "hud_margin": hud_margin,
            "title_px": max(10, int(preset["title_px"] * scale)),
            "sub_px": max(8, int(preset["sub_px"] * scale)),
            "tele_px": max(8, int(preset["tele_px"] * scale)),
            "lamp_px": max(8, int(preset["lamp_px"] * scale)),
            "label_px": max(8, int(preset["label_px"] * scale)),
            "rim_text_px": max(8, int(preset["rim_text_px"] * scale)),
            "title_track": max(1, int(preset["title_track"] * scale)),
            "aux_track": max(1, int(preset["aux_track"] * scale)),
            "safe_rect": safe,
            "plaque_rect": plaque,
        })
        return layout

    def _fit_points(self):
        points = []
        for p in circle_points(_PLATE_RIM, 0.0, 120):
            points.append(p)
        for p in circle_points(_PLATE_RIM, -_PLATE_THICK, 120):
            points.append(p)
        for world in self._worlds:
            for i in range(120):
                points.append(world.point(TAU * i / 120))
        if self._layout["armature"]:
            points.extend(armature_points(1.02, -8.0, 120))
        points.append((0.0, 0.20, 0.0))  # lamp + finial
        return points

    def _build(self, size):
        self._screen_size = (int(size[0]), int(size[1]))
        self._layout = self._resolve_layout(size)
        self._frame = Frame(View(self._layout["elevation"],
                                 self._layout["azimuth"]),
                            self._layout["safe_rect"], self._fit_points())
        self._sun_center = (0.0, 0.155, 0.0)
        self._sun_base = (0.0, 0.0, 0.0)
        self._sun_screen = self._frame.project(self._sun_center)
        self._sun_px = max(5.0, self._frame.scale_at(self._sun_center) * 0.038)
        self._build_finish()
        self._build_room()
        self._rebuild_rails()
        self._build_bloom()
        self._build_glow_sprites()
        self._build_dust()
        self._build_hud()
        self._build_plaque()
        self._build_label_surfaces()
        self._conj_rect = None
        self._conj_label = None

    def _resize(self, size):
        if self.manager is None or size == self._screen_size:
            return
        self._build(size)

    # ---------------------------------------------------------------- room

    def _build_room(self):
        width, height = self._screen_size
        margin = _CACHE_MARGIN
        rw, rh = width + margin * 2, height + margin * 2
        room = pygame.Surface((rw, rh))
        top, bottom = self._palette.bg_top, self._palette.bg_bottom
        for y in range(rh):
            t = (y / max(1, rh - 1)) ** 1.35
            pygame.draw.line(room, mix(top, bottom, t), (0, y), (rw, y))

        sun = self._sun_screen
        if sun:
            blit_glow(room, (sun[0] + margin, sun[1] + margin),
                      int(min(rw, rh) * 0.55), self._palette.haze,
                      power=2.9, strength=0.26)
            blit_glow(room, (sun[0] + margin, sun[1] + margin),
                      int(min(rw, rh) * 0.26), self._palette.haze,
                      power=2.7, strength=0.22)

        rng = random.Random(self.seed ^ 0x51A7 if self.seed is not None else 2001)
        for _ in range(QUALITY[self._quality]["stars"]):
            x = rng.random() * rw
            y = rng.random() * rh
            if x < 90 and y > rh - 80:
                continue
            size = rng.choice((1, 1, 1, 2))
            brightness = rng.uniform(0.10, 0.55)
            color = scale(self._palette.warm_white, brightness * 0.55)
            pygame.draw.circle(room, color, (int(x), int(y)), size)

        self._draw_floor_rings(room, margin)
        self._draw_plate(room, margin)
        if self._finish is not None:
            room.blit(self._finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        self._room = room

    def _draw_floor_rings(self, dst, margin):
        overlay = pygame.Surface(dst.get_size(), pygame.SRCALPHA)
        for radius, alpha in ((1.26, 16), (1.42, 10)):
            pts = []
            for p in circle_points(radius, -_PLATE_THICK, 160):
                q = self._frame.project(p)
                if q is None:
                    pts = []
                    break
                pts.append((q[0] + margin, q[1] + margin))
            if pts:
                pygame.draw.lines(overlay, (*scale(self._palette.structure, 0.8),
                                           alpha), True, pts, 1)
        for i in range(72):
            ang = TAU * i / 72
            p0 = self._frame.project((1.415 * math.cos(ang), -_PLATE_THICK,
                                      1.415 * math.sin(ang)))
            p1 = self._frame.project((1.440 * math.cos(ang), -_PLATE_THICK,
                                      1.440 * math.sin(ang)))
            if p0 and p1:
                pygame.draw.line(overlay, (*scale(self._palette.structure, 0.7),
                                           9),
                                 (p0[0] + margin, p0[1] + margin),
                                 (p1[0] + margin, p1[1] + margin), 1)
        dst.blit(overlay, (0, 0))

    def _plate_bbox(self):
        points = []
        for p in circle_points(_PLATE_RIM, 0.0, 120):
            points.append(p)
        for p in circle_points(_PLATE_RIM, -_PLATE_THICK, 120):
            points.append(p)
        if self._layout["armature"]:
            points.extend(armature_points(1.02, -8.0, 120))
        points.append((0.0, 0.20, 0.0))
        xs, ys = [], []
        for p in points:
            q = self._frame.project(p)
            if q:
                xs.append(q[0])
                ys.append(q[1])
        if not xs:
            return pygame.Rect(0, 0, 1, 1)
        pad = 12
        left = max(0, int(min(xs) - pad))
        top = max(0, int(min(ys) - pad))
        right = min(self._screen_size[0], int(max(xs) + pad))
        bottom = min(self._screen_size[1], int(max(ys) + pad))
        return pygame.Rect(left, top, max(1, right - left),
                           max(1, bottom - top))

    def _draw_plate(self, dst, margin):
        bbox = self._plate_bbox()
        ss = 2
        pw, ph = bbox.width, bbox.height
        plate = pygame.Surface((pw * ss, ph * ss), pygame.SRCALPHA)

        def px(point):
            q = self._frame.project(point)
            if q is None:
                return None
            return ((q[0] - bbox.left) * ss, (q[1] - bbox.top) * ss)

        def poly(points):
            return [px(p) for p in points]

        # side wall and under-disc
        bottom = poly(circle_points(_PLATE_RIM, -_PLATE_THICK, 180))
        if bottom is None:
            return
        pygame.draw.polygon(plate, scale(self._palette.plate_side, 0.45), bottom)
        top_rim = poly(circle_points(_PLATE_RIM, 0.0, 180))
        if top_rim:
            for i in range(180):
                j = i + 1
                quad = [top_rim[i], top_rim[j], bottom[j], bottom[i]]
                angle = TAU * i / 180
                front = 0.5 + 0.5 * math.sin(angle)
                col = mix(scale(self._palette.plate_side, 0.30),
                          scale(self._palette.structure_dim, 0.50),
                          front * 0.8)
                pygame.draw.polygon(plate, col, quad)

        # top face gradient
        rings = 44
        for i in range(rings):
            t = i / (rings - 1)
            radius = _PLATE_RIM * (1.0 - t)
            pts = poly(circle_points(radius, 0.0, 150))
            if pts:
                pygame.draw.polygon(
                    plate, mix(self._palette.plate_edge,
                               self._palette.plate_center, t ** 0.62), pts)

        # lamp light pooling on the brass
        sun = px(self._sun_center)
        if sun:
            pool = max(40, int(min(bbox.width, bbox.height) * 0.55 * ss))
            blit_glow(plate, sun, pool, self._palette.haze,
                      power=2.6, strength=0.20)
            blit_glow(plate, sun, int(pool * 0.46), (62, 42, 18),
                      power=2.4, strength=0.35)

        # raised rim
        inner = 0.972
        ring_a = poly(circle_points(inner, 0.0, 180))
        if ring_a and top_rim:
            for i in range(180):
                j = i + 1
                quad = [ring_a[i], ring_a[j], top_rim[j], top_rim[i]]
                angle = TAU * i / 180
                front = 0.5 + 0.5 * math.sin(angle)
                col = mix(scale(self._palette.structure_dim, 0.52),
                          scale(self._palette.structure, 0.72), front ** 1.7)
                pygame.draw.polygon(plate, col, quad)
            pygame.draw.lines(plate, scale(self._palette.structure_dim, 0.9),
                              True, ring_a, max(1, ss // 2))
            pygame.draw.lines(plate, scale(self._palette.structure, 0.48),
                              True, top_rim, max(1, ss // 2))

        self._draw_plate_engraving(plate, px, ss)
        self._draw_sun_stalk(plate, px, ss)
        if self._layout["armature"]:
            self._draw_armature(plate, px, ss)

        smooth = pygame.transform.smoothscale(plate, (pw, ph))
        dst.blit(smooth, (bbox.left + margin, bbox.top + margin))

    def _draw_plate_engraving(self, dst, px, ss):
        overlay = pygame.Surface(dst.get_size(), pygame.SRCALPHA)

        def ring(radius, color, alpha, width=1):
            pts = [px(p) for p in circle_points(radius, 0.0, 150)]
            if all(pts):
                pygame.draw.lines(overlay, (*color, alpha), True, pts,
                                  max(1, int(width * ss)))

        ring(0.94, self._palette.structure, 78)
        ring(0.78, self._palette.structure_dim, 44)
        ring(0.56, self._palette.structure_dim, 38)
        ring(0.34, self._palette.structure_dim, 34)

        for i in range(24):
            ang = TAU * i / 24
            p0 = px((0.315 * math.cos(ang), 0.0, 0.315 * math.sin(ang)))
            p1 = px((0.955 * math.cos(ang), 0.0, 0.955 * math.sin(ang)))
            if p0 and p1:
                pygame.draw.aaline(overlay, (*self._palette.structure_dim,
                                             44 if i % 2 == 0 else 22), p0, p1)

        for i in range(120):
            ang = TAU * i / 120
            r0 = 0.955
            r1 = 0.978 if i % 5 else 0.988
            p0 = px((r0 * math.cos(ang), 0.0, r0 * math.sin(ang)))
            p1 = px((r1 * math.cos(ang), 0.0, r1 * math.sin(ang)))
            if p0 and p1:
                pygame.draw.line(overlay, (*scale(self._palette.structure_hi, 0.8),
                                           64 if i % 5 == 0 else 32), p0, p1, 1)

        for i in range(24):
            ang = TAU * (i + 0.5) / 24
            p = px((0.938 * math.cos(ang), 0.0, 0.938 * math.sin(ang)))
            if p:
                pygame.draw.circle(overlay, (*self._palette.structure_dim, 88),
                                   (int(p[0]), int(p[1])), max(1, ss))

        for i in range(16):
            ang = TAU * i / 16
            r0 = 0.10 if i % 2 == 0 else 0.13
            r1 = 0.30 if i % 2 == 0 else 0.24
            p0 = px((r0 * math.cos(ang), 0.0, r0 * math.sin(ang)))
            p1 = px((r1 * math.cos(ang), 0.0, r1 * math.sin(ang)))
            if p0 and p1:
                pygame.draw.aaline(overlay, (*scale(self._palette.structure_hi, 0.85),
                                             40), p0, p1)

        dst.blit(overlay, (0, 0))

        font = self.manager.cache.get_font(
            "dejavuserif", max(8, int(self._layout["rim_text_px"] * ss)))
        dedication = (f"{LATIN_WORDS[self._world_count]} MUNDI  ·  "
                      f"UNA LUCERNA")
        self._draw_arc_text(dst, px, ss, dedication,
                            radius=0.845, y=0.0015, center_deg=90.0, font=font,
                            color=scale(self._palette.structure, 0.80),
                            tracking=max(1, int(2.0 * ss)), alpha=200)

    def _draw_arc_text(self, dst, px, ss, text, radius, y, center_deg, font,
                       color, tracking=0, alpha=255):
        glyphs = [font.render(ch, True, color) for ch in text]
        total = sum(g.get_width() for g in glyphs) + tracking * max(0, len(text) - 1)
        scale_px = self._frame.scale_at((radius, y, 0.0)) * ss
        circumference = TAU * radius * scale_px
        span = TAU * (total / max(1.0, circumference))
        start = math.radians(center_deg) + span * 0.5
        x = 0
        for glyph in glyphs:
            frac = (x + glyph.get_width() * 0.5) / max(1e-6, total)
            ang = start - span * frac
            p = px((radius * math.cos(ang), y, radius * math.sin(ang)))
            pa = px((radius * math.cos(ang - 0.004), y,
                     radius * math.sin(ang - 0.004)))
            pb = px((radius * math.cos(ang + 0.004), y,
                     radius * math.sin(ang + 0.004)))
            if p and pa and pb:
                rot = math.degrees(math.atan2(-(pa[1] - pb[1]),
                                              pa[0] - pb[0]))
                g = pygame.transform.rotozoom(glyph, rot, 1.0)
                if alpha < 255:
                    g.set_alpha(alpha)
                dst.blit(g, (int(p[0] - g.get_width() * 0.5),
                             int(p[1] - g.get_height() * 0.5)))
            x += glyph.get_width() + tracking

    def _draw_sun_stalk(self, dst, px, ss):
        base = px(self._sun_base)
        top = px(self._sun_center)
        if not base or not top:
            return
        pygame.draw.line(dst, scale(self._palette.structure_dim, 0.8),
                         base, top, max(1, int(3 * ss)))
        pygame.draw.circle(dst, scale(self._palette.structure_dim, 0.9),
                           (int(base[0]), int(base[1])), max(1, int(5 * ss)))
        tip = px((0.0, self._sun_center[1] + 0.045, 0.0))
        if tip:
            pygame.draw.line(dst, scale(self._palette.structure, 0.65),
                             top, tip, max(1, int(1.4 * ss)))
            pygame.draw.circle(dst, scale(self._palette.structure_hi, 0.9),
                               (int(tip[0]), int(tip[1])), max(1, int(2 * ss)))

    def _draw_armature(self, dst, px, ss):
        outer = armature_points(1.02, -8.0, 140)
        inner = armature_points(1.02 - 0.035, -8.0, 140)
        outer_px = [px(p) for p in outer]
        inner_px = [px(p) for p in inner]
        for rail in (outer_px, inner_px):
            for i in range(len(rail) - 1):
                p0, p1 = rail[i], rail[i + 1]
                if p0 and p1:
                    pygame.draw.line(dst, (*scale(self._palette.structure_dim, 0.8),
                                           140), p0, p1, max(1, int(2.6 * ss)))
                    pygame.draw.line(dst, (*scale(self._palette.structure, 0.82),
                                           165), p0, p1, max(1, int(1.2 * ss)))
        for i in range(91):
            po, pi = outer_px[i], inner_px[i]
            if not (po and pi):
                continue
            long = i % 15 == 0
            mid = i % 5 == 0
            if i % 2 and not mid:
                continue
            k = 1.0 if long else 0.62 if mid else 0.35
            p1 = (po[0] + (pi[0] - po[0]) * k, po[1] + (pi[1] - po[1]) * k)
            fade = 0.55 + 0.45 * math.sin(math.pi * i / 90)
            pygame.draw.line(dst, (*scale(self._palette.structure_hi, 0.9),
                                   int((155 if long else 90) * fade)),
                             po, p1, max(1, int((1.4 if long else 1.0) * ss)))
        for end_point in (outer_px[0], outer_px[-1]):
            if end_point:
                pygame.draw.circle(dst, (*scale(self._palette.structure, 0.85),
                                         190), (int(end_point[0]), int(end_point[1])),
                                   max(1, int(3.6 * ss)))
        crown = outer_px[len(outer_px) // 2]
        if crown:
            r = max(2, int(3.4 * ss))
            pygame.draw.circle(dst, (*scale(self._palette.structure, 0.85), 210),
                               (int(crown[0]), int(crown[1])), r)
            pygame.draw.circle(dst, (*scale(self._palette.structure_hi, 0.95),
                                     180), (int(crown[0]), int(crown[1])),
                               max(1, r // 2))

    # ---------------------------------------------------------------- rails

    def _rebuild_rails(self):
        if self._frame is None or not self._worlds:
            return
        bbox = self._plate_bbox()
        ox, oy = bbox.left, bbox.top
        back = pygame.Surface((bbox.width, bbox.height), pygame.SRCALPHA)
        front = pygame.Surface((bbox.width, bbox.height), pygame.SRCALPHA)
        steps = QUALITY[self._quality]["rail_steps"]
        sun_depth = self._frame.view.depth(self._sun_center)
        near = sun_depth - 0.75
        far = sun_depth + 0.75
        segments = 0

        def nearness(depth):
            return max(0.0, min(1.0, (far - depth) / (far - near)))

        for world in self._worlds:
            points = world.rail(steps)
            projected = [self._frame.project(p) for p in points]
            depths = [self._frame.view.depth(p) for p in points]
            for i in range(len(points) - 1):
                p0, p1 = projected[i], projected[i + 1]
                if p0 is None or p1 is None:
                    continue
                depth = (depths[i] + depths[i + 1]) * 0.5
                target = back if depth > sun_depth else front
                t = nearness(depth)
                col = mix(scale(self._palette.structure, 0.30),
                          scale(self._palette.structure_hi, 0.80), t)
                a0 = (p0[0] - ox, p0[1] - oy)
                a1 = (p1[0] - ox, p1[1] - oy)
                pygame.draw.line(target, scale(col, 0.28), a0, a1, 3)
                pygame.draw.aaline(target, col, a0, a1)
                segments += 1

            for frac in (0.19, 0.71):
                rail_p = world.point(TAU * frac)
                depth = self._frame.view.depth(rail_p)
                target = back if depth > sun_depth else front
                foot = (rail_p[0], 0.0, rail_p[2])
                p0 = self._frame.project(foot)
                p1 = self._frame.project(rail_p)
                if p0 and p1:
                    pygame.draw.line(target,
                                     scale(self._palette.structure_dim, 0.55),
                                     (p0[0] - ox, p0[1] - oy),
                                     (p1[0] - ox, p1[1] - oy), 2)
                    pygame.draw.circle(target,
                                       scale(self._palette.structure_dim, 0.7),
                                       (int(p1[0] - ox), int(p1[1] - oy)), 2)
                    segments += 1
        self._rails_back = back
        self._rails_front = front
        self._rails_rect = bbox
        self._last_segments = segments

    # ---------------------------------------------------------------- finish / glow

    def _build_finish(self):
        width, height = self._screen_size
        m = _CACHE_MARGIN
        rw, rh = width + m * 2, height + m * 2
        if self._vignette <= 0.0 and self._scanlines <= 0:
            self._finish = None
            return
        qw, qh = max(2, rw // 4), max(2, rh // 4)
        small = pygame.Surface((qw, qh))
        cx, cy = (width * 0.5 + m) / 4.0, (height * 0.5 + m) / 4.0
        maxd = math.hypot(max(cx, qw - cx), max(cy, qh - cy))
        for y in range(qh):
            for x in range(qw):
                r = math.hypot(x - cx, y - cy) / maxd
                dark = self._vignette * (max(0.0, r - 0.26) / 0.74) ** 1.65
                k = int(255 * max(0.06, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (rw, rh))
        if self._scanlines > 0:
            k = int(255 * (1.0 - self._scanlines / 255.0))
            for y in range(0, rh, 3):
                pygame.draw.line(finish, (k, k, k), (0, y), (rw, y), 1)
        self._finish = finish

    def _build_glow_sprites(self):
        r = self._sun_px
        p = self._palette
        self._sun_glows = [
            (radial_glow(int(r * 15), scale(p.haze, 0.55), 2.6), int(r * 15)),
            (radial_glow(int(r * 7.5), scale(p.glow, 0.70), 2.3), int(r * 7.5)),
            (radial_glow(int(r * 3.2), scale((255, 214, 150), 0.85), 2.0),
             int(r * 3.2)),
        ]
        self._comet_glow = radial_glow(28, scale(p.accent, 0.55), 2.1)

    def _build_bloom(self):
        width, height = self._screen_size
        div = QUALITY[self._quality]["glow_div"]
        self._bloom_small = pygame.Surface((max(2, width // div),
                                            max(2, height // div)))
        self._bloom_mid = pygame.Surface((max(2, width // 2),
                                          max(2, height // 2)))
        self._bloom_up = pygame.Surface((width, height))

    def _build_dust(self):
        rng = random.Random(self.seed ^ 0xD057 if self.seed is not None else 2001)
        count = QUALITY[self._quality]["dust"]
        self._dust = [(rng.random(), rng.random(), rng.uniform(1.0, 3.0),
                       rng.uniform(0.0, TAU), rng.uniform(0.4, 1.4))
                      for _ in range(count)]

    # ---------------------------------------------------------------- HUD

    def _build_hud(self):
        layout = self._layout
        palette = self._palette
        size = self._screen_size
        margin = layout["hud_margin"]
        cache = self.manager.cache
        title_font = cache.get_font("dejavusansmono", layout["title_px"], bold=True)
        sub_font = cache.get_font("dejavusansmono", layout["sub_px"])
        tele_font = cache.get_font("dejavusansmono", layout["tele_px"])
        lamp_font = cache.get_font("dejavusansmono", layout["lamp_px"])
        eyebrow = "SLOW WORLDS  ·  THE LONG VIEW"
        title_lines = self._title_lines()
        hud = {
            "margin": margin,
            "fonts": (title_font, sub_font, tele_font, lamp_font),
            "title_lines": [tracked(line, title_font, palette.ink,
                                    layout["title_track"]) for line in title_lines],
            "title_y": [],
            "subtitle": tracked(self._subtitle, sub_font, palette.ink_dim,
                                layout["aux_track"], 235) if self._subtitle else None,
            "eyebrow": (tracked(eyebrow, sub_font, scale(palette.structure, 0.8),
                                layout["aux_track"], 220)
                        if self._hud_mode == "full" else None),
            "epoch": None,
            "epoch_surface": None,
            "tele": tracked("INSTR.  03/09", tele_font,
                            scale(palette.structure, 0.9), layout["aux_track"]),
            "lamp": tracked("THE LAMP", lamp_font,
                            scale(palette.structure, 0.75), 1, 190),
            "lamp_font": lamp_font,
            "tele_font": tele_font,
            "sub_font": sub_font,
            "reserved": [],
        }
        # title block geometry
        x = margin
        if layout["layout"] == "portrait":
            y = margin
            if hud["eyebrow"]:
                hud["eyebrow_y"] = y
                y += hud["eyebrow"].get_height() + 12
            for line in hud["title_lines"]:
                hud["title_y"].append(y)
                y += line.get_height() + 2
            y += 14
            hud["rule_y"] = y
            y += 12
            hud["subtitle_y"] = y
            block_h = (y - margin + (hud["subtitle"].get_height()
                                      if hud["subtitle"] else 0))
            title_w = max((line.get_width() for line in hud["title_lines"]),
                          default=200)
            hud["reserved"].append(pygame.Rect(margin - 8, margin - 8,
                                               min(size[0] - margin * 2,
                                                   max(int(size[0] * 0.62),
                                                       title_w + 16)),
                                               max(120, block_h + 8)))
        else:
            y = margin
            if hud["eyebrow"]:
                hud["eyebrow_y"] = y
                y += hud["eyebrow"].get_height() + 6
            title = hud["title_lines"][0]
            hud["title_y"].append(y)
            y += title.get_height() + 5
            hud["rule_y"] = y
            hud["rule_w"] = max(160, int(title.get_width() * 0.70))
            y += 7
            hud["subtitle_y"] = y
            block_w = max(title.get_width(),
                          hud["subtitle"].get_width() if hud["subtitle"] else 0)
            block_h = y + (hud["subtitle"].get_height()
                           if hud["subtitle"] else 0) - margin
            hud["reserved"].append(pygame.Rect(margin - 8, margin - 8,
                                               min(size[0] - margin * 2,
                                                   block_w + 16),
                                               block_h + 8))

        tele_w = max(hud["tele"].get_width(),
                     hud["sub_font"].size("EPOCH  21:04")[0])
        hud["tele_x"] = size[0] - margin - tele_w
        hud["tele_y"] = margin
        hud["reserved"].append(pygame.Rect(hud["tele_x"] - 8, margin - 8,
                                           tele_w + 16, 64))
        hud["reserved"].append(pygame.Rect(0, size[1] - 64, 120, 64))
        if self._show_plaque and layout["plaque_rect"] is not None:
            hud["reserved"].append(layout["plaque_rect"].inflate(16, 16))
        self._hud = hud

    def _title_lines(self):
        title = self._title
        if "\n" in title:
            lines = [line.strip() for line in title.splitlines() if line.strip()]
            return lines[:2] if lines else ["ORRERY"]
        if self._layout["layout"] == "portrait" \
                and title.upper() == "ORRERY OF SMALL WORLDS":
            return ["THE ORRERY", "OF SMALL WORLDS"]
        return [title]

    def _draw_hud(self, screen, offset):
        if self._hud_mode == "off" or self._hud is None:
            return
        hud = self._hud
        palette = self._palette
        size = self._screen_size
        margin = hud["margin"]
        dx, dy = offset
        # corner ticks, deliberately no lower-left tick
        ln = max(8, int(min(size) * 0.018))
        for x, y, sx, sy in ((margin, margin, 1, 1),
                             (size[0] - margin, margin, -1, 1),
                             (size[0] - margin, size[1] - margin, -1, -1)):
            pygame.draw.line(screen, scale(palette.structure_dim, 0.9),
                             (x, y), (x + sx * ln, y), 1)
            pygame.draw.line(screen, scale(palette.structure_dim, 0.9),
                             (x, y), (x, y + sy * ln), 1)

        if hud.get("eyebrow"):
            screen.blit(hud["eyebrow"], (margin, hud["eyebrow_y"]))
        if self._layout["layout"] == "portrait":
            for line, y in zip(hud["title_lines"], hud["title_y"]):
                screen.blit(line, (margin, y))
            pygame.draw.line(screen, scale(palette.structure, 0.55),
                             (margin, hud["rule_y"]),
                             (margin + int(size[0] * 0.33), hud["rule_y"]), 1)
        else:
            screen.blit(hud["title_lines"][0], (margin, hud["title_y"][0]))
            pygame.draw.line(screen, scale(palette.structure, 0.65),
                             (margin, hud["rule_y"]),
                             (margin + hud["rule_w"], hud["rule_y"]), 1)
        if hud["subtitle"]:
            screen.blit(hud["subtitle"], (margin, hud["subtitle_y"]))

        screen.blit(hud["tele"], (hud["tele_x"], hud["tele_y"]))
        epoch = self._epoch_text()
        if epoch != hud["epoch"]:
            hud["epoch"] = epoch
            hud["epoch_surface"] = tracked(
                epoch, hud["tele_font"], palette.ink_dim,
                self._layout["aux_track"], 220)
        epoch_surface = hud["epoch_surface"]
        screen.blit(epoch_surface,
                    (size[0] - margin - epoch_surface.get_width(),
                     hud["tele_y"] + hud["tele"].get_height() + 7))

        sun = self._sun_screen
        if sun and self._hud_mode != "off":
            lx = sun[0] + dx
            ly = sun[1] + dy + self._sun_px * 3.4
            lamp = hud["lamp"]
            rect = lamp.get_rect()
            rect.midtop = (int(lx), int(ly))
            pygame.draw.line(screen, scale(palette.structure_dim, 0.9),
                             (int(lx), int(sun[1] + dy + self._sun_px * 2.0)),
                             (int(lx), rect.top - 3), 1)
            screen.blit(lamp, rect)

    # ---------------------------------------------------------------- labels

    def _build_label_surfaces(self):
        layout = self._layout
        font = self.manager.cache.get_font("dejavusansmono", layout["label_px"])
        self._label_surfaces = []
        for world in self._worlds:
            numeral = ROMAN[world.index]
            body = tracked(f"{numeral}  {world.name}", font, self._palette.ink,
                           max(1, layout["aux_track"]), 225)
            shadow = tracked(f"{numeral}  {world.name}", font, (4, 3, 3),
                             max(1, layout["aux_track"]), 160)
            self._label_surfaces.append((world, body, shadow))

    def _draw_labels(self, screen, offset, reserved):
        if not self._show_labels or not self._label_surfaces:
            self._last_label_boxes = []
            return
        font_rects = list(reserved)
        boxes = []
        screen_rect = pygame.Rect(0, 0, self._screen_size[0], self._screen_size[1])
        margin = max(8, int(self._layout["label_px"] * 1.2))
        bounds = screen_rect.inflate(-2 * margin, -2 * margin)
        dx, dy = offset
        sun = self._sun_screen
        sun = (sun[0] + dx, sun[1] + dy) if sun else (screen_rect.centerx,
                                                      screen_rect.centery)
        order = sorted(self._label_surfaces,
                       key=lambda item: -self._frame.view.depth(
                           item[0].position(self._time)))
        for world, body, shadow in order:
            base = world.position(self._time)
            q = self._frame.project(base)
            if q is None:
                continue
            p = (q[0] + dx, q[1] + dy)
            r = max(2.0, self._frame.scale_at(base) * world.size)
            gap = r + self._layout["label_px"] * 1.1
            ddx, ddy = p[0] - sun[0], p[1] - sun[1]
            if abs(ddx) >= abs(ddy):
                order_dirs = ["right" if ddx >= 0 else "left",
                              "down" if ddy >= 0 else "up",
                              "up" if ddy >= 0 else "down",
                              "left" if ddx >= 0 else "right"]
            else:
                order_dirs = ["down" if ddy >= 0 else "up",
                              "right" if ddx >= 0 else "left",
                              "left" if ddx >= 0 else "right",
                              "up" if ddy >= 0 else "down"]
            by_dir = {
                "right": ((p[0] + gap, p[1] - body.get_height() * 0.5),
                          "left", 1),
                "left": ((p[0] - gap, p[1] - body.get_height() * 0.5),
                         "right", 1),
                "up": ((p[0] - body.get_width() * 0.5,
                        p[1] - gap - body.get_height()), "center", 0),
                "down": ((p[0] - body.get_width() * 0.5, p[1] + gap),
                         "center", -1),
            }
            chosen = None
            for direction in order_dirs:
                pos, align, leader = by_dir[direction]
                rect = body.get_rect()
                if align == "left":
                    rect.topleft = (int(pos[0]), int(pos[1]))
                elif align == "right":
                    rect.topright = (int(pos[0]), int(pos[1]))
                else:
                    rect.midtop = (int(pos[0]), int(pos[1]))
                if not bounds.contains(rect):
                    continue
                if any(rect.colliderect(other.inflate(8, 8)) for other in font_rects):
                    continue
                chosen = (rect, align, leader)
                break
            if chosen is None:
                continue
            rect, align, leader = chosen
            font_rects.append(rect.inflate(8, 8))
            boxes.append(rect.copy())
            col = scale(self._palette.structure_dim, 0.9)
            if align == "left":
                start = (p[0] + r * 1.2, p[1])
                knee = (rect.left - 5, rect.centery)
                pygame.draw.line(screen, col, start, (knee[0] - 7, knee[1]), 1)
                pygame.draw.line(screen, col, (knee[0] - 7, knee[1]), knee, 1)
                pygame.draw.circle(screen, scale(self._palette.structure, 0.75),
                                   (int(start[0]), int(start[1])), 1)
            elif align == "right":
                start = (p[0] - r * 1.2, p[1])
                knee = (rect.right + 5, rect.centery)
                pygame.draw.line(screen, col, start, (knee[0] + 7, knee[1]), 1)
                pygame.draw.line(screen, col, (knee[0] + 7, knee[1]), knee, 1)
                pygame.draw.circle(screen, scale(self._palette.structure, 0.75),
                                   (int(start[0]), int(start[1])), 1)
            elif leader == 0:
                pygame.draw.line(screen, col, (p[0], p[1] - r * 1.2),
                                 (rect.centerx, rect.bottom + 4), 1)
            else:
                pygame.draw.line(screen, col, (p[0], p[1] + r * 1.2),
                                 (rect.centerx, rect.top - 4), 1)
            screen.blit(shadow, (rect.left + 1, rect.top + 1))
            screen.blit(body, rect)
        self._last_label_boxes = boxes

    # ---------------------------------------------------------------- conjunction

    def _screen_world(self, world, offset):
        q = self._frame.project(world.position(self._time))
        if q is None:
            return None
        return (q[0] + offset[0], q[1] + offset[1])

    def _find_conjunction(self, offset):
        threshold = max(55.0, min(140.0,
                                  self._screen_size[0] * 0.10))
        target = threshold * 0.75
        best = None
        positions = []
        for world in self._worlds:
            p = self._screen_world(world, offset)
            if p:
                positions.append((world, p))
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                w0, p0 = positions[i]
                w1, p1 = positions[j]
                dist = math.hypot(p0[0] - p1[0], p0[1] - p1[1])
                if dist < 18.0 or dist > threshold:
                    continue
                score = abs(dist - target)
                if best is None or score < best[0]:
                    best = (score, dist, w0, w1, p0, p1)
        return best

    def _update_conjunction(self, force=False):
        if not self._show_conjunctions:
            self._conj_pair = None
            return
        if self._conj_pair is not None:
            if self._time < self._conj_until:
                return
            self._conj_pair = None
        if not force and self._time < self._conj_cooldown:
            return
        offset = self._offset()
        best = self._find_conjunction(offset)
        if best is None:
            return
        _score, _dist, w0, w1, _p0, _p1 = best
        key = (w0.index, w1.index)
        if not force and self._time < self._conj_pair_cooldown.get(key, -1e9):
            return
        self._conj_pair = (w0, w1)
        self._conj_until = self._time + 8.0
        self._conj_cooldown = self._time + 18.0
        self._conj_pair_cooldown[key] = self._time + 75.0
        self._conj_label = None

    def _conj_label_surface(self):
        if self._conj_label is None:
            font = self.manager.cache.get_font("dejavusansmono",
                                               max(9, self._layout["label_px"] - 2))
            text = f"CONJUNCTION  ·  {self._epoch_minutes() // 60:02d}:" \
                   f"{self._epoch_minutes() % 60:02d}"
            self._conj_label = tracked(text, font,
                                       mix(self._palette.accent,
                                           self._palette.ink, 0.35),
                                       2, 225)
        return self._conj_label

    def _draw_conjunction(self, screen, offset, reserved):
        self._conj_rect = None
        if not self._show_conjunctions or self._conj_pair is None:
            return
        if self._time >= self._conj_until:
            self._conj_pair = None
            return
        w0, w1 = self._conj_pair
        p0 = self._screen_world(w0, offset)
        p1 = self._screen_world(w1, offset)
        if not p0 or not p1:
            return
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        r0 = max(5.0, self._frame.scale_at(w0.position(self._time)) * w0.size)
        r1 = max(5.0, self._frame.scale_at(w1.position(self._time)) * w1.size)
        q0 = (p0[0] + ux * r0 * 1.3, p0[1] + uy * r0 * 1.3)
        q1 = (p1[0] - ux * r1 * 1.3, p1[1] - uy * r1 * 1.3)
        if math.hypot(q1[0] - q0[0], q1[1] - q0[1]) < 18.0:
            return
        pygame.draw.aaline(screen, self._palette.accent, q0, q1)
        for p in (q0, q1):
            pygame.draw.circle(screen, self._palette.accent,
                               (int(p[0]), int(p[1])), 3, 1)
        mid = ((q0[0] + q1[0]) * 0.5, (q0[1] + q1[1]) * 0.5)
        label = self._conj_label_surface()
        rect = label.get_rect()
        candidates = (
            (int(mid[0]), int(mid[1] - 10), "midbottom"),
            (int(mid[0]), int(mid[1] + 10), "midtop"),
            (int(mid[0]), int(mid[1] - 28), "midbottom"),
            (int(mid[0]), int(mid[1] + 28), "midtop"),
        )
        chosen = None
        for x, y, anchor in candidates:
            r = rect.copy()
            setattr(r, anchor, (x, y))
            if r.left < 8 or r.top < 8 or r.right > self._screen_size[0] - 8 \
                    or r.bottom > self._screen_size[1] - 8:
                continue
            if any(r.colliderect(other.inflate(10, 10)) for other in reserved):
                continue
            chosen = r
            break
        if chosen is None:
            return
        screen.blit(label, chosen)
        self._conj_rect = chosen.inflate(10, 6)
        reserved.append(self._conj_rect)

    # ---------------------------------------------------------------- plaque

    def _plaque_lines(self):
        periods = [w.period for w in self._worlds]
        incs = [w.inclination for w in self._worlds]
        return (
            "THE AUREL SYSTEM",
            f"{NUMBER_WORDS[self._world_count]} INVENTED WORLDS · "
            f"ONE LAMP AT THE FOCUS",
            f"PERIODS {min(periods):.0f}–{max(periods):.0f} s  ·  "
            f"INCLINATIONS {min(incs):.0f}°–{max(incs):.0f}°",
        )

    def _build_plaque(self):
        rect = self._layout["plaque_rect"]
        if not self._show_plaque or rect is None:
            self._plaque = None
            return
        ss = 2
        pw, ph = rect.width, rect.height
        plate = pygame.Surface((pw * ss, ph * ss), pygame.SRCALPHA)
        p = self._palette
        plate.fill((*scale(p.plate_center, 0.74), 246))
        pygame.draw.rect(plate, (*scale(p.structure_dim, 0.75), 210),
                         (0, 0, pw * ss, ph * ss), max(1, ss))
        pygame.draw.line(plate, (*scale(p.structure_hi, 0.55), 140),
                         (10 * ss, ss), ((pw - 10) * ss, ss), max(1, ss))
        pygame.draw.line(plate, (*scale(p.structure_deep, 0.85), 200),
                         (10 * ss, (ph - 2) * ss), ((pw - 10) * ss, (ph - 2) * ss),
                         max(1, ss))
        pygame.draw.rect(plate, (*scale(p.structure_dim, 0.55), 90),
                         (7 * ss, 7 * ss, (pw - 14) * ss, (ph - 14) * ss),
                         max(1, ss))

        rng = random.Random(31)
        for _ in range(90):
            gy = rng.randrange(8, max(9, ph - 8))
            gx = rng.randrange(8, max(9, pw - 30))
            gl = rng.randrange(12, 90)
            pygame.draw.line(plate, (*p.structure_dim, rng.choice((8, 10, 13))),
                             (gx * ss, gy * ss), ((gx + gl) * ss, gy * ss),
                             max(1, ss))
        for sx in (16, pw - 16):
            for sy in (16, ph - 16):
                pygame.draw.circle(plate, (*scale(p.structure_dim, 0.9), 190),
                                   (sx * ss, sy * ss), max(1, int(3 * ss)))
                pygame.draw.line(plate, (*scale(p.structure_hi, 0.7), 150),
                                 ((sx - 2) * ss, sy * ss),
                                 ((sx + 2) * ss, sy * ss), max(1, ss))

        lines = self._plaque_lines()
        serif = self.manager.cache.get_font(
            "dejavuserif", max(8, int(ph * 0.15 * ss)))
        mono = self.manager.cache.get_font(
            "dejavusansmono", max(8, int(ph * 0.090 * ss)))
        small = self.manager.cache.get_font(
            "dejavusansmono", max(7, int(ph * 0.078 * ss)))
        main = tracked(lines[0], serif, scale(p.structure, 0.98),
                       max(1, int(4 * ss)))
        sub = tracked(lines[1], mono, p.ink_dim, max(1, int(2 * ss)), 215)
        num = tracked(lines[2], small, p.ink_faint, max(1, ss), 175)
        main_rect = main.get_rect()
        main_rect.centerx = (pw * ss) // 2
        main_rect.top = int(ph * 0.17 * ss)
        rule_y = main_rect.bottom + int(ph * 0.12 * ss)
        pygame.draw.line(plate, (*scale(p.structure, 0.55), 130),
                         (int(pw * 0.18 * ss), rule_y),
                         (int(pw * 0.82 * ss), rule_y), max(1, ss))
        sub_rect = sub.get_rect()
        sub_rect.centerx = (pw * ss) // 2
        sub_rect.top = rule_y + int(ph * 0.12 * ss)
        num_rect = num.get_rect()
        num_rect.centerx = (pw * ss) // 2
        num_rect.top = sub_rect.bottom + int(ph * 0.08 * ss)
        plate.blit(main, main_rect)
        plate.blit(sub, sub_rect)
        plate.blit(num, num_rect)
        self._plaque = pygame.transform.smoothscale(plate, (pw, ph))

    def _draw_plaque(self, screen, offset):
        if not self._show_plaque or self._plaque is None:
            return
        rect = self._layout["plaque_rect"]
        screen.blit(self._plaque, (rect.x + int(offset[0]),
                                   rect.y + int(offset[1])))

    # ---------------------------------------------------------------- comet / dust

    def _comet_position(self, t=None):
        if not self._show_comet:
            return None
        a, e = 1.50, 0.60
        inc = math.radians(35.0)
        node = math.radians(105.0)
        period = 94.0
        t = self._time if t is None else t
        theta = math.radians(self._comet_phase) + TAU * t / period
        b = a * math.sqrt(1 - e * e)
        ex = a * math.cos(theta) - a * e
        ez = b * math.sin(theta)
        ey = ez * math.sin(inc)
        ez = ez * math.cos(inc)
        wx = ex * math.cos(node) - ez * math.sin(node)
        wz = ex * math.sin(node) + ez * math.cos(node)
        return (wx, 0.20 + ey, wz)

    def _draw_comet(self, screen, offset):
        if not self._show_comet:
            return
        head = self._comet_position()
        hp = self._frame.project(head)
        if not hp:
            return
        hp = (hp[0] + offset[0], hp[1] + offset[1])
        points = []
        for i in range(14):
            p = self._frame.project(self._comet_position(self._time - i * 0.22))
            if p:
                points.append((p[0] + offset[0], p[1] + offset[1]))
        if len(points) >= 2:
            for i in range(len(points) - 1):
                t = 1.0 - i / len(points)
                col = scale(mix(self._palette.accent,
                                self._palette.warm_white, 0.25), t * t)
                pygame.draw.line(screen, col, points[i], points[i + 1],
                                 max(1, int(1 + 3.0 * t)))
        if self._comet_glow:
            screen.blit(self._comet_glow, (int(hp[0]) - 28, int(hp[1]) - 28),
                        special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(screen, (208, 238, 224),
                           (int(hp[0]), int(hp[1])), max(2, int(2.6)))
        pygame.draw.circle(screen, (250, 255, 248),
                           (int(hp[0]), int(hp[1])), max(1, int(1.1)))

    def _draw_dust(self, screen, offset):
        for fx, fy, size, phase, speed in self._dust:
            x = (fx * self._screen_size[0]
                 + math.cos(phase + self._time * 0.03 * speed) * 6.0
                 + offset[0])
            y = (fy * self._screen_size[1]
                 + math.sin(phase * 1.7 + self._time * 0.021 * speed) * 4.0
                 + offset[1])
            col = scale(self._palette.warm_white, 0.12 + 0.10 * speed)
            pygame.draw.circle(screen, col, (int(x), int(y)),
                               max(1, int(size * 0.5)))

    # ---------------------------------------------------------------- render

    def render(self, screen):
        if self.manager is None:
            screen.fill(self._palette.bg_top)
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            self._render_scene(screen)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Orrery] render error: {exc}")
            self._draw_error(screen)

    def _render_scene(self, screen):
        width, height = self._screen_size
        palette = self._palette
        offset = self._offset()
        dx, dy = offset
        if self._room is not None:
            screen.blit(self._room, (-_CACHE_MARGIN + int(round(dx)),
                                     -_CACHE_MARGIN + int(round(dy))))
        else:
            screen.fill(palette.bg_top)
        rail_pos = ((self._rails_rect.x + int(round(dx)),
                     self._rails_rect.y + int(round(dy)))
                    if self._rails_rect is not None else (0, 0))
        if self._rails_back is not None:
            screen.blit(self._rails_back, rail_pos)

        sun_depth = self._frame.view.depth(self._sun_center)
        back_worlds = []
        front_worlds = []
        for world in self._worlds:
            base = world.position(self._time)
            (back_worlds if self._frame.view.depth(base) > sun_depth
             else front_worlds).append(world)

        for world in sorted(back_worlds,
                            key=lambda w: -self._frame.view.depth(
                                w.position(self._time))):
            self._draw_world(screen, world, offset)

        self._draw_sun(screen, offset)

        if self._rails_front is not None:
            screen.blit(self._rails_front,
                        (self._rails_rect.x + int(round(dx)),
                         self._rails_rect.y + int(round(dy))))
        for world in sorted(front_worlds,
                            key=lambda w: -self._frame.view.depth(
                                w.position(self._time))):
            self._draw_world(screen, world, offset)

        self._draw_comet(screen, offset)
        self._draw_dust(screen, offset)

        if self._glow > 0.0 and self._quality != "low":
            self._composite_glow(screen)

        reserved = list(self._hud["reserved"]) if self._hud else []
        if self._show_plaque and self._layout["plaque_rect"] is not None:
            reserved.append(self._layout["plaque_rect"].inflate(16, 16))
        self._draw_conjunction(screen, offset, reserved)
        self._draw_labels(screen, offset, reserved)
        self._draw_hud(screen, offset)
        self._draw_plaque(screen, offset)

    def _draw_sun(self, screen, offset):
        top = self._sun_screen
        if top is None:
            return
        cx, cy = top[0] + offset[0], top[1] + offset[1]
        for sprite, radius in self._sun_glows:
            screen.blit(sprite, (int(cx) - radius, int(cy) - radius),
                        special_flags=pygame.BLEND_RGB_ADD)
        r = self._sun_px
        pygame.draw.circle(screen, scale(self._palette.glow, 0.55),
                           (int(cx), int(cy)), int(r))
        pygame.draw.circle(screen, self._palette.warm_white,
                           (int(cx), int(cy)), max(2, int(r * 0.58)))
        pygame.draw.circle(screen, (255, 255, 242),
                           (int(cx), int(cy)), max(1, int(r * 0.28)))

    def _draw_world(self, screen, world, offset):
        base = world.position(self._time)
        p = self._frame.project(base)
        if p is None:
            return
        p = (p[0] + offset[0], p[1] + offset[1])
        radius = self._frame.scale_at(base) * world.size
        if radius < 0.7:
            return
        tint = self._palette.world_tints[world.tint % len(self._palette.world_tints)]
        depth = self._frame.view.depth(base)
        depth_t = max(0.0, min(1.0,
                               (depth - (self._frame.view.distance - 1.0)) / 2.0))
        r = max(2.0, radius * (1.0 - 0.16 * depth_t))
        sun = self._sun_screen
        if sun:
            sdx, sdy = sun[0] + offset[0] - p[0], sun[1] + offset[1] - p[1]
            slen = math.hypot(sdx, sdy) or 1.0
            ox, oy = sdx / slen * r * 0.18, sdy / slen * r * 0.18
        else:
            ox = oy = 0.0
        pygame.draw.circle(screen, scale(tint, 0.20 * (1.0 - 0.3 * depth_t)),
                           (int(p[0]), int(p[1])), max(2, int(r * 1.05)))
        pygame.draw.circle(screen, scale(tint, 0.86),
                           (int(p[0] + ox), int(p[1] + oy)),
                           max(2, int(r * 0.94)))
        pygame.draw.circle(screen, scale(tint, 1.08),
                           (int(p[0] + ox * 1.6), int(p[1] + oy * 1.6)),
                           max(1, int(r * 0.55)))
        pygame.draw.circle(screen, scale(tint, 1.28),
                           (int(p[0] + ox * 2.0 - r * 0.2),
                            int(p[1] + oy * 2.0 - r * 0.2)),
                           max(1, int(r * 0.24)))
        moon_count = QUALITY[self._quality]["moons"]
        for index in range(1 if world.size < 0.017 else moon_count):
            moon_r = world.size * (2.45 + 0.40 * index)
            moon_phase = 1.7 + 2.4 * index
            moon_inc = math.radians(24.0 + 19.0 * index)
            ang = moon_phase + TAU * self._time / (6.0 + 2.7 * index)
            mx = math.cos(ang) * moon_r
            mz = math.sin(ang) * moon_r
            my = mz * math.sin(moon_inc)
            mz = mz * math.cos(moon_inc)
            mp = self._frame.project((base[0] + mx,
                                      base[1] + my + world.size * 0.25,
                                      base[2] + mz))
            if mp:
                pygame.draw.circle(screen, scale(self._palette.ink_dim, 0.75),
                                   (int(mp[0] + offset[0]),
                                    int(mp[1] + offset[1])),
                                   max(1, int(r * 0.20)))

    def _composite_glow(self, screen):
        if self._bloom_small is None or self._bloom_up is None:
            return
        pygame.transform.smoothscale(screen, self._bloom_small.get_size(),
                                     self._bloom_small)
        k = int(22 + 96 * self._glow)
        self._bloom_small.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self._bloom_small,
                                     self._bloom_mid.get_size(),
                                     self._bloom_mid)
        pygame.transform.scale(self._bloom_mid, self._bloom_up.get_size(),
                               self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_error(self, screen):
        screen.fill(self._palette.bg_top)
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette.structure, rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("ORRERY OF SMALL WORLDS // CONFIGURATION REFUSED",
                                True, self._palette.ink)
            body = font.render((self.error or "unknown error")[:90], True,
                               self._palette.glow)
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- stats

    def stats(self):
        if self._frame is None or self.error:
            return {}
        return {
            "preset": self._layout["preset"],
            "layout": self._layout["layout"],
            "elevation": self._layout["elevation"],
            "azimuth": self._layout["azimuth"],
            "oval_ratio": math.sin(math.radians(self._layout["elevation"])),
            "worlds": [w.name for w in self._worlds],
            "world_count": len(self._worlds),
            "periods": [round(w.period, 2) for w in self._worlds],
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "seed": self.seed,
            "time": self._time,
            "start_time": self._start_time,
            "plaque": bool(self._show_plaque and self._plaque is not None),
            "plaque_rect": tuple(self._layout["plaque_rect"])
            if self._layout["plaque_rect"] else None,
            "plaque_lines": self._plaque_lines() if self._show_plaque else (),
            "safe_rect": tuple(self._layout["safe_rect"]),
            "segments": self._last_segments,
            "labels": len(self._last_label_boxes),
            "conjunction": tuple(w.name for w in self._conj_pair)
            if self._conj_pair else None,
            "hud": self._hud_mode,
            "palette": self._palette.name,
            "sun_px": round(self._sun_px, 2),
        }
