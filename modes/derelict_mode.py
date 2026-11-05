"""Derelict — a dead ship, turning, with one window still flickering.

Slow Wireframe §4.11.  A capital ship broken across its spine and torn open on
one side, adrift in the dark.  Debris turns slowly around it, a single window
flickers — irregularly, weakly — and once a minute a vent breathes a little gas.
The camera drifts around the wreck as an observer; nothing arrives, nothing
explains it.

This is a quiet mode: the emptiness is the point.  There is no monster, no
signal, no flash (§4.11 "build notes").  The drawing is all line on near black:
wireframe box sections, the broken spine, the jagged tear cut into the hull, and
shards of debris on slow orbits.  Depth is carried by the boxes' projection and
by one small additive bloom on the window.

Camera behaviour (§2.3): orbit.  The card's 0.5 px/s drift is a slow change of
viewing angle around the wreck, and the ship's own 0.05°/s tumble is a second
slower turn on top, so the silhouette never quite repeats.

Determinism (§2.9): the sections, the tear, the debris and the flicker schedule
all come from `seed` and elapsed time.  A pinned seed reproduces a still exactly.

No disk I/O, no network, no threads.  The lower-left 80x32 px stays clear for
the controller's mode number.
"""
from __future__ import annotations

import math
import random

import pygame

TAU = math.tau

QUALITY_MODES = ("auto", "low", "medium", "high")
HUD_MODES = ("full", "minimal", "off")
FILL_MODES = ("line", "xray", "panel")
ORIENTATIONS = ("auto", "ultrawide", "landscape", "portrait", "square")

#: Debris, tear jag, stars and bloom per tier (§2.8).
QUALITY = {
    "low": {"debris": 18, "jag": 7, "stars": 30, "glow_div": 8},
    "medium": {"debris": 30, "jag": 10, "stars": 46, "glow_div": 5},
    "high": {"debris": 44, "jag": 13, "stars": 64, "glow_div": 4},
}

#: Where the wreck sits on screen, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.500, 0.500), "length": 0.560, "height": 0.340,
                  "title_px": 21},
    "landscape": {"anchor": (0.500, 0.500), "length": 0.540, "height": 0.330,
                  "title_px": 30},
    "portrait": {"anchor": (0.500, 0.460), "length": 0.520, "height": 0.240,
                 "title_px": 34},
    "square": {"anchor": (0.500, 0.490), "length": 0.540, "height": 0.320,
               "title_px": 26},
}

PALETTES = {
    "mono": {
        "bg_top": (6, 6, 7), "bg_bottom": (1, 1, 2), "haze": (14, 14, 16),
        "structure": (92, 92, 96), "hero": (226, 226, 230),
        "accent": (150, 150, 156), "glow": (214, 214, 218),
        "window": (255, 214, 150), "hud": (226, 226, 230),
        "hud_dim": (120, 120, 126), "hud_faint": (52, 52, 56),
    },
    "vector_blue": {
        "bg_top": (2, 5, 10), "bg_bottom": (0, 1, 3), "haze": (6, 14, 24),
        "structure": (54, 96, 126), "hero": (208, 230, 244),
        "accent": (96, 160, 196), "glow": (160, 214, 244),
        "window": (255, 206, 150), "hud": (208, 230, 244),
        "hud_dim": (96, 132, 156), "hud_faint": (34, 52, 68),
    },
    "amber": {
        "bg_top": (10, 6, 4), "bg_bottom": (3, 2, 1), "haze": (22, 12, 6),
        "structure": (122, 82, 44), "hero": (246, 224, 196),
        "accent": (196, 140, 80), "glow": (246, 200, 140),
        "window": (255, 222, 170), "hud": (246, 224, 196),
        "hud_dim": (140, 100, 60), "hud_faint": (58, 38, 20),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)


def aspect_preset(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
    if aspect <= 0.82:
        return "portrait"
    if aspect >= 1.25:
        return "landscape"
    return "square"


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(a, b, t: float):
    t = _clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _scale(color, factor: float):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _rgba(color, alpha: int):
    return (color[0], color[1], color[2], int(_clamp(alpha, 0, 255)))


class DerelictMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "mono"
        self._palette = PALETTES["mono"]
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._frame_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._hud_mode = "minimal"
        self._fill = "line"
        self._orientation = "auto"
        self._hull_damage = 0.6
        self._debris_on = True
        self._flicker_on = True
        self._camera_drift = 0.5
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.24
        self._title = "DERELICT"
        self._subtitle = "UNKNOWN · SIGNAL NONE"

        self._time = 0.0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}

        self._sections = []
        self._debris = []
        self._stars = []
        self._tear = []
        self._window = (0.0, 0.0)
        self._vents = []
        self._centre = (0.0, 0.0)
        self._length = 1.0
        self._height = 1.0
        self._angle = 0.0
        self._roll = 0.0
        self._window_level = 0.0
        self._rows = []
        self._last_error_logged = False
        self._clear()

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
    def _bool(config, key, default):
        value = config.get(key, default)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false")
        return value

    @staticmethod
    def _text(config, key, default, max_length=44):
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

        palette = str(cfg.get("palette", "mono")).lower()
        if palette not in PALETTES:
            raise ValueError("palette must be " + ", ".join(PALETTE_NAMES))
        self._palette_name = palette
        self._palette = PALETTES[palette]

        quality = str(cfg.get("quality", "auto")).lower()
        if quality not in QUALITY_MODES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"

        hud = str(cfg.get("hud", "minimal")).lower()
        if hud not in HUD_MODES:
            raise ValueError("hud must be full, minimal, or off")
        self._hud_mode = hud

        fill = str(cfg.get("fill", "line")).lower()
        if fill not in FILL_MODES:
            raise ValueError("fill must be line, xray, or panel")
        self._fill = fill

        orientation = str(cfg.get("orientation", "auto")).lower()
        if orientation not in ORIENTATIONS:
            raise ValueError("orientation must be " + ", ".join(ORIENTATIONS))
        self._orientation = orientation

        self._hull_damage = self._number(cfg, "hull_damage", 0.6, 0.0, 1.0)
        self._debris_on = self._bool(cfg, "debris", True)
        self._flicker_on = self._bool(cfg, "flicker", True)
        self._camera_drift = self._number(cfg, "camera_drift", 0.5, 0.0, 6.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer_compat(cfg, "scanline_alpha", 4)
        self._vignette = self._number(cfg, "vignette_strength", 0.24, 0.0, 1.0)

        self._title = self._text(cfg, "title", "DERELICT", 30) or "DERELICT"
        self._subtitle = self._text(cfg, "subtitle", "UNKNOWN · SIGNAL NONE", 44)

    @staticmethod
    def _integer_compat(config, key, default):
        value = config.get(key, default)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a whole number")
        if float(value) != int(value):
            raise ValueError(f"{key} must be a whole number")
        value = int(value)
        if not 0 <= value <= 40:
            raise ValueError(f"{key} must be in 0..40")
        return value

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            self.seed = self._next_seed()
            self._time = 0.0
            self._quality = "medium" if self._auto_quality else self._quality_setting
            self._frame_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self._build(manager.screen.get_size())
            self.error = None
            print(f"[Derelict] seed={self.seed} preset={self._preset} "
                  f"damage={self._hull_damage:.2f} drift={self._camera_drift:.1f}px/s "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Derelict] configuration error: {exc}")

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def exit(self):
        self.manager = None
        self.error = None
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}
        self._sections = []
        self._debris = []
        self._stars = []
        self._tear = []
        self._vents = []
        self._rows = []
        self._time = 0.0
        self._last_error_logged = False
        self._clear()

    def _clear(self):
        self._rows = []
        self._hud_rects = []

    def handle_event(self, event):
        """The controller owns input; this mode has none."""

    # ---------------------------------------------------------------- build

    def _resolve_preset(self, size):
        width, height = int(size[0]), int(size[1])
        if self._orientation == "auto":
            return aspect_preset(width, height)
        return self._orientation

    def _build(self, size):
        width, height = int(size[0]), int(size[1])
        preset = self._resolve_preset((width, height))
        self._screen_size = (width, height)
        self._preset = preset
        self._layout = dict(PRESETS[preset])
        self._text_cache = {}
        self._centre = (self._layout["anchor"][0] * width,
                        self._layout["anchor"][1] * height)
        self._length = self._layout["length"] * width
        self._height = self._layout["height"] * height
        self._build_wreck()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_wreck(self):
        """Box sections along a broken spine, the tear, debris and the window."""
        rng = random.Random(self.seed ^ 0xDEAD)
        damage = self._hull_damage
        sections = []
        # bow, a mid section twisted off the axis, and the stern
        layout = (
            {"x0": 0.44, "x1": 1.00, "tilt": 0.06, "drop": 0.10, "w": 0.30},
            {"x0": 0.18, "x1": 0.44, "tilt": -0.10, "drop": -0.06, "w": 0.34},
            {"x0": -0.18, "x1": 0.18, "tilt": 0.02, "drop": 0.02, "w": 0.30},
        )
        for spec in layout:
            sections.append({
                "x0": spec["x0"], "x1": spec["x1"],
                "tilt": spec["tilt"], "drop": spec["drop"], "w": spec["w"],
                "ribs": rng.randint(2, 4),
            })
        self._sections = sections
        # the tear: a jagged polygon on the bow section's near face
        jag = QUALITY["high"]["jag"]
        tear = []
        for index in range(jag):
            angle = TAU * index / jag
            radius = 0.045 + 0.030 * rng.random() * damage
            tear.append((0.62 + math.cos(angle) * radius * 1.5,
                         0.06 + math.sin(angle) * radius))
        self._tear = tear
        self._window = (0.86, 0.02)
        debris = []
        for _ in range(QUALITY["high"]["debris"]):
            debris.append({
                "radius": rng.uniform(0.32, 0.75),
                "angle": rng.uniform(0.0, TAU),
                "z": rng.uniform(-0.5, 0.5),
                "size": rng.uniform(1.5, 4.5),
                "spin": rng.uniform(-1.0, 1.0),
            })
        self._debris = debris
        vents = []
        for index in range(2):
            vents.append({"x": 0.30 + index * 0.34, "y": 0.08, "phase": index * 0.5})
        self._vents = vents

    def _build_stars(self):
        rng = random.Random(self.seed ^ 0x57A2)
        width, height = self._screen_size
        self._stars = [
            (rng.uniform(0, width), rng.uniform(0, height), rng.randint(14, 40))
            for _ in range(QUALITY["high"]["stars"])
        ]

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = y / max(1, height - 1)
            base = _mix(palette["bg_top"], palette["bg_bottom"], t ** 1.3)
            band = math.exp(-(((t - 0.48) / 0.50) ** 2))
            color = _mix(base, palette["haze"], band * 0.10)
            pygame.draw.line(surface, color, (0, y), (width, y))
        self._build_stars()
        for x, y, level in self._stars:
            surface.set_at((int(x), int(y)), _scale(palette["far"], level / 255.0))
        self._background = surface

    def _build_finish(self):
        width, height = self._screen_size
        if self._vignette <= 0.0 and self._scanline_alpha <= 0:
            self._finish = None
            return
        qw, qh = max(2, width // 4), max(2, height // 4)
        small = pygame.Surface((qw, qh)).convert()
        if self._vignette <= 0.0:
            small.fill((255, 255, 255))
        else:
            cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
            maxd = math.hypot(cx, cy)
            for y in range(qh):
                for x in range(qw):
                    r = math.hypot(x - cx, y - cy) / maxd
                    dark = self._vignette * (max(0.0, r - 0.28) / 0.72) ** 1.6
                    k = int(255 * max(0.05, 1.0 - dark))
                    small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (width, height))
        if self._scanline_alpha > 0:
            k = int(255 * (1.0 - self._scanline_alpha / 255.0))
            for y in range(0, height, 3):
                pygame.draw.line(finish, (k, k, k), (0, y), (width, y), 1)
        if self._hud_mode != "off":
            top_h = max(44, int(height * 0.12))
            for y in range(top_h):
                t = (y / max(1, top_h - 1)) ** 2
                k = int(48 + 207 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (width, y), 1)
            bot_h = max(30, int(height * 0.075))
            for y in range(bot_h):
                k = int(255 - 228 * (y / max(1, bot_h - 1)))
                pygame.draw.line(finish, (k, k, k), (0, height - bot_h + y),
                                 (width, height - bot_h + y), 1)
        self._finish = finish

    def _build_bloom(self):
        width, height = self._screen_size
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        if self._glow_strength <= 0.0:
            return
        div = QUALITY[self._quality]["glow_div"]
        self._bloom = pygame.Surface((max(2, width // div), max(2, height // div)))
        self._bloom.fill((0, 0, 0))
        self._bloom_mid = pygame.Surface((max(2, width // 2), max(2, height // 2)))
        self._bloom_up = pygame.Surface((width, height))

    # ---------------------------------------------------------------- HUD

    def _hud_metrics(self):
        width, height = self._screen_size
        short = min(width, height)
        title_px = int(_clamp(short * 0.055, 14, 40))
        pad = max(10, int(short * 0.045))
        portrait = self._preset == "portrait"
        return {
            "pad": pad,
            "title_x": pad,
            "title_y": int(height * (0.050 if portrait else 0.075)),
            "title_px": title_px,
            "sub_px": max(7, int(title_px * 0.40)),
            "tele_px": max(7, min(15, int(title_px * 0.42))),
            "tele_x": width - pad,
            "tele_y": int(height * (0.048 if portrait else 0.055)),
            "status_y": height - max(24, int(height * 0.072)),
            "status_x": max(96, int(width * (0.10 if self._preset == "ultrawide" else 0.06))),
            "status_px": max(7, min(13, int(title_px * 0.38))),
        }

    def _font(self, size, bold=False):
        return self.manager.cache.get_font("dejavusansmono", max(7, int(size)), bold=bold)

    def _tracked(self, surface, text, font, color, pos, tracking=0.0, alpha=255):
        x, y = pos
        if tracking <= 0.0:
            glyph = font.render(text, True, color)
            if alpha < 255:
                glyph.set_alpha(alpha)
            surface.blit(glyph, (x, y))
            return glyph.get_width()
        width = 0
        for char in text:
            glyph = font.render(char, True, color)
            if alpha < 255:
                glyph.set_alpha(alpha)
            surface.blit(glyph, (x + width, y))
            width += glyph.get_width() + tracking
        return width - tracking

    def _build_hud(self):
        self._metrics = self._hud_metrics()
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        if self._hud_mode == "off":
            return
        m = self._metrics
        width, height = self._screen_size
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        title_font = self._font(m["title_px"], bold=True)
        sub_font = self._font(m["sub_px"])
        y = m["title_y"]
        title_w = self._tracked(layer, self._title, title_font, self._palette["hud"],
                                (m["title_x"], y), tracking=m["title_px"] * 0.10,
                                alpha=240)
        rule_y = int(y + m["title_px"] * 1.16)
        pygame.draw.line(layer, _rgba(self._palette["accent"], 120),
                         (m["title_x"], rule_y),
                         (m["title_x"] + int(title_w * 0.68), rule_y), 1)
        if self._hud_mode == "full":
            self._tracked(layer, self._subtitle, sub_font, self._palette["hud_dim"],
                          (m["title_x"], rule_y + 6), tracking=m["sub_px"] * 0.10,
                          alpha=190)
        self._hud_title = layer
        self._hud_title_rect = pygame.Rect(
            m["title_x"], y, max(80, int(title_w) + 8),
            max(18, rule_y - y + m["sub_px"] + 8))

    def _cached_text(self, text, size, color, alpha, bold=False):
        key = (text, size, color, alpha, bold)
        surface = self._text_cache.get(key)
        if surface is None:
            font = self._font(size, bold=bold)
            surface = font.render(text, True, color)
            if alpha < 255:
                surface.set_alpha(alpha)
            if len(self._text_cache) > 64:
                self._text_cache.clear()
            self._text_cache[key] = surface
        return surface

    def _telemetry(self):
        palette = self._palette
        lines = [("SIGNAL NONE", palette["hud"], 210),
                 ("DEBRIS 044", palette["hud_dim"], 180)]
        if self._hud_mode == "full":
            lines.append((f"DRIFT {self._camera_drift:.1f} PX/S",
                          palette["hud_dim"], 165))
            lines.append((f"HULL {int((1.0 - self._hull_damage) * 100):02d}%",
                          palette["hud_faint"], 140))
        return lines

    def _status_text(self):
        if self._window_level > 0.25:
            return "WINDOW FLICKER · NO RESPONSE", True
        return "NO SIGNAL · ADRIFT", False

    def _draw_hud(self, screen):
        if self._hud_mode == "off" or self._metrics is None:
            return
        m = self._metrics
        palette = self._palette
        self._hud_rects = []
        if self._hud_title is not None:
            screen.blit(self._hud_title, (0, 0))
            if self._hud_title_rect is not None:
                self._hud_rects.append(self._hud_title_rect)

        tele_size = m["tele_px"]
        y = m["tele_y"]
        for index, (text, color, alpha) in enumerate(self._telemetry()):
            surface = self._cached_text(text, tele_size, color, alpha, bold=True)
            rect = surface.get_rect()
            rect.topright = (m["tele_x"], y + index * int(tele_size * 1.7))
            screen.blit(surface, rect)
            self._hud_rects.append(rect.copy())

        status, alert = self._status_text()
        color = palette["glow"] if alert else palette["hud_dim"]
        surface = self._cached_text(status, m["status_px"], color, 190)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.7),
                         (rect.left, rect.bottom + 4), (rect.right, rect.bottom + 4), 1)

    # ---------------------------------------------------------------- geometry

    def _camera_angle(self) -> float:
        """The observer's drift around the wreck, and the wreck's own tumble."""
        drift = math.sin(TAU * self._time / 420.0) * math.radians(6.0 * self._camera_drift)
        tumble = TAU * self._time / 7200.0                # 0.05°/s
        return drift + tumble

    def _project(self, x, y, z):
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        sx = self._centre[0] + (x - 0.5) * self._length + z * self._height * 0.55 * ca
        sy = self._centre[1] - y * self._height + z * self._height * 0.24 * sa
        return (sx, sy)

    def _draw_section(self, screen, section):
        palette = self._palette
        x0, x1 = section["x0"], section["x1"]
        tilt, drop, w = section["tilt"], section["drop"], section["w"]
        top, bottom = 0.17, -0.17
        corners = []
        for x in (x0, x1):
            for y in (top, bottom):
                for z in (-w, w):
                    corners.append((x + tilt * (y + 0.2), y + drop, z))
        # the near face, the far face and the long edges
        points = [self._project(*corner) for corner in corners]
        near = [points[1], points[3], points[7], points[5]]
        far = [points[0], points[2], points[6], points[4]]
        pygame.draw.lines(screen, _scale(palette["structure"], 0.55), True, far, 1)
        pygame.draw.lines(screen, _mix(palette["structure"], palette["hero"], 0.45),
                          True, near, 1)
        for index in range(4):
            pygame.draw.line(screen, _scale(palette["structure"], 0.7),
                             far[index], near[index], 1)
        # ribs and a couple of deck lines, only on the near face
        for k in range(1, section["ribs"] + 1):
            t = k / (section["ribs"] + 1.0)
            a = _lerp(near[0][0], near[1][0], t), _lerp(near[0][1], near[1][1], t)
            b = _lerp(near[3][0], near[2][0], t), _lerp(near[3][1], near[2][1], t)
            pygame.draw.line(screen, _scale(palette["guide"], 0.8), a, b, 1)

    def _draw_spine(self, screen):
        """The broken spine: a line over the top of each section that stops at the break."""
        palette = self._palette
        for index, section in enumerate(self._sections):
            a = self._project(section["x0"], section["drop"] + 0.18, 0.0)
            b = self._project(section["x1"], section["drop"] + 0.18, 0.0)
            pygame.draw.line(screen, _scale(palette["hero"], 0.55), a, b, 1)
            if index < len(self._sections) - 1:
                # the break: the two spines do not meet
                nxt = self._sections[index + 1]
                c = self._project(nxt["x1"], nxt["drop"] + 0.18, 0.0)
                mid = ((b[0] + c[0]) * 0.5, (b[1] + c[1]) * 0.5 + 2)
                pygame.draw.line(screen, _scale(palette["guide"], 0.7), b, mid, 1)
                pygame.draw.line(screen, _scale(palette["guide"], 0.7), mid, c, 1)

    def _draw_tear(self, screen):
        """The open polygon where the hull is torn."""
        palette = self._palette
        if not self._tear:
            return
        points = [self._project(x, y, 0.31) for x, y in self._tear]
        pygame.draw.lines(screen, _mix(palette["structure"], palette["hero"], 0.35),
                          True, points, 1)
        # the dark inside, and a couple of snapped lines hanging off the edge
        core = [self._project(x * 0.92 + 0.56 * 0.08, y * 0.9, 0.30)
                for x, y in self._tear]
        for index in range(0, len(self._tear), 2):
            pygame.draw.line(screen, _scale(palette["guide"], 0.6),
                             points[index],
                             ((points[index][0] + core[index][0]) * 0.5,
                              (points[index][1] + core[index][1]) * 0.5), 1)

    def _draw_debris(self, screen, quality):
        if not self._debris_on:
            return
        palette = self._palette
        for shard in self._debris[:quality["debris"]]:
            angle = shard["angle"] + self._time * 0.012 * shard["spin"]
            x = 0.5 + math.cos(angle) * shard["radius"]
            y = math.sin(angle) * shard["radius"] * 0.45 + shard["z"] * 0.12
            p = self._project(x, y, shard["z"])
            size = shard["size"]
            if size < 1.0:
                continue
            spin = shard["spin"] * self._time * 0.4
            dx, dy = math.cos(spin) * size, math.sin(spin) * size
            pygame.draw.line(screen, _scale(palette["structure"], 0.8),
                             (p[0] - dx, p[1] - dy), (p[0] + dx, p[1] + dy), 1)

    def _window_alpha(self) -> float:
        """A weak, irregular flicker that dies as the camera drifts past."""
        if not self._flicker_on:
            return 0.0
        t = self._time
        noise = (0.5 * math.sin(t * 2.7) + 0.3 * math.sin(t * 6.1 + 1.7)
                 + 0.2 * math.sin(t * 11.3 + 0.4))
        level = _clamp(0.5 + 0.5 * noise, 0.0, 1.0)
        # the camera's pass: bright while the window faces it, then dark
        pass_phase = (self._time % 60.0) / 60.0
        if pass_phase < 0.45:
            envelope = _clamp(pass_phase / 0.25, 0.0, 1.0)
        elif pass_phase < 0.55:
            envelope = 1.0
        else:
            envelope = _clamp((0.85 - pass_phase) / 0.30, 0.0, 1.0)
        return level * envelope * (0.9 if self._hull_damage > 0.5 else 0.6)

    def _draw_window(self, screen):
        if self._window_level <= 0.02:
            return
        palette = self._palette
        p = self._project(self._window[0], self._window[1], 0.30)
        level = self._window_level
        pygame.draw.rect(screen, _scale(palette["window"], level),
                         pygame.Rect(int(p[0]) - 1, int(p[1]) - 1, 3, 2), 1)
        if level > 0.5:
            pygame.draw.circle(screen, _scale(palette["window"], level * 0.9),
                               (int(p[0]), int(p[1])), 1)

    def _draw_vents(self, screen):
        """A faint vent plume, once a minute, from one hull seam."""
        palette = self._palette
        cycle = (self._time % 60.0) / 60.0
        if cycle > 0.09:
            return
        phase = cycle / 0.09
        for vent in self._vents[:1]:
            base = self._project(vent["x"], vent["y"], 0.20)
            for k in range(5):
                t = phase - k * 0.06
                if t <= 0.0:
                    continue
                p = (base[0] + t * 18.0, base[1] - t * 26.0 + 4.0 * t * t)
                pygame.draw.circle(screen, _scale(palette["guide"], 0.5 * (1.0 - t)),
                                   (int(p[0]), int(p[1])), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        if self._window_level > 0.05:
            p = self._project(self._window[0], self._window[1], 0.30)
            pygame.draw.circle(self._bloom,
                               _scale(palette["window"], 0.5 * self._glow_strength
                                      * self._window_level),
                               (int(p[0] * sx), int(p[1] * sy)), 1)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._angle = self._camera_angle()
        self._window_level = self._window_alpha()
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        for section in self._sections:
            self._draw_section(screen, section)
        self._draw_spine(screen)
        self._draw_tear(screen)
        self._draw_vents(screen)
        self._draw_debris(screen, quality)
        self._draw_window(screen)
        if self._finish is not None:
            screen.blit(self._finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # ---------------------------------------------------------------- update / render

    def update(self, dt: float):
        if self.manager is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._time += dt
        if not self._auto_quality:
            return
        self._frame_ema += (dt - self._frame_ema) * 0.06
        if self._frame_ema > (1.0 / 18.0):
            self._quality_timer += dt
            if self._quality_timer >= 2.0:
                self._step_quality(-1)
                self._quality_timer = 0.0
        elif self._frame_ema < (1.0 / 30.0):
            self._quality_timer += dt
            if self._quality_timer >= 6.0:
                self._step_quality(1)
                self._quality_timer = 0.0
        else:
            self._quality_timer = 0.0

    def _step_quality(self, direction: int):
        tiers = ("low", "medium", "high")
        index = tiers.index(self._quality)
        index = int(_clamp(index + direction, 0, len(tiers) - 1))
        if tiers[index] == self._quality:
            return
        self._quality = tiers[index]
        self._build_bloom()

    def _resize(self, size):
        if self.manager is None or size == self._screen_size:
            return
        self._build(size)

    def render(self, screen):
        if self.manager is None:
            screen.fill(self._palette["bg_top"])
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            if self._background is None:
                screen.fill(self._palette["bg_top"])
                return
            self._draw_scene(screen)
            self._draw_hud(screen)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            if not self._last_error_logged:
                print(f"[Derelict] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("DERELICT // CONFIGURATION REFUSED", True,
                                self._palette["hud"])
            body = font.render((self.error or "unknown error")[:90], True,
                               self._palette["accent"])
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- stats

    def stats(self):
        if self.error or self._background is None:
            return {}
        width, height = self._screen_size
        corner = pygame.Rect(0, max(0, height - 32), 80, 32)
        corner_clear = all(not pygame.Rect(r).colliderect(corner) for r in self._hud_rects)
        return {
            "preset": self._preset,
            "layout": self._preset,
            "time": self._time,
            "sections": len(self._sections),
            "hull_damage": self._hull_damage,
            "debris": len(self._debris),
            "debris_on": self._debris_on,
            "flicker": self._flicker_on,
            "window_level": self._window_level,
            "camera_drift": self._camera_drift,
            "angle": self._angle,
            "centre": self._centre,
            "length": self._length,
            "seed": self.seed,
            "palette": self._palette_name,
            "hud": self._hud_mode,
            "fill": self._fill,
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "glow_strength": self._glow_strength,
            "screen_size": self._screen_size,
            "hud_rects": [tuple(r) for r in self._hud_rects],
            "corner_clear": corner_clear,
        }
