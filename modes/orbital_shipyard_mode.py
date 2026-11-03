"""Orbital Shipyard — a construction site, not a finished station.

Slow Wireframe §4.7.  A skeletal gantry holds a half-built capital ship: the
keel runs the length of the berth under a truss of triangles, ribs stand where
the sections have locked, robotic arms reach in and weld with a bright tip and a
shower of sparks, drones run along the keel, and a crane lowers a section into
place.  Every so often the keel locks: the gantry lights run from red to white
along the spine and the hull's outline is one continuous line for a moment.

The drawing is all line, projected isometrically: the hull is a box lattice
drawn only where the current `hull_stage` has reached, so a low stage is a keel
and a few ribs and a high stage is a hollowed ship.  The camera cranes around
the berth (the isometric angle drifts a few degrees over the cycle), which is
what sells the scale (§2.8: no 3D engine, one vanishing point and a few cues).

Determinism (§2.9): the sections, gantry, arms, drones and the keel-lock
schedule all come from `seed`; everything else is a function of accumulated
elapsed time.  A pinned seed reproduces a still exactly.

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

#: Gantry, arms, sparks and bloom per tier (§2.8).
QUALITY = {
    "low": {"posts": 3, "arms": 4, "sparks": 14, "drones": 2, "glow_div": 8},
    "medium": {"posts": 5, "arms": 6, "sparks": 28, "drones": 3, "glow_div": 5},
    "high": {"posts": 7, "arms": 8, "sparks": 48, "drones": 4, "glow_div": 4},
}

#: The berth's size on screen, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.500, 0.575), "length": 0.620, "height": 0.400,
                  "title_px": 21},
    "landscape": {"anchor": (0.500, 0.585), "length": 0.600, "height": 0.380,
                  "title_px": 30},
    "portrait": {"anchor": (0.500, 0.560), "length": 0.640, "height": 0.260,
                 "title_px": 34},
    "square": {"anchor": (0.500, 0.600), "length": 0.620, "height": 0.360,
               "title_px": 26},
}

PALETTES = {
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "weld": (255, 96, 48), "spark": (255, 214, 150),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "weld": (255, 84, 72), "spark": (208, 244, 255),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (18, 18, 18),
        "structure": (86, 86, 86), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "weld": (210, 70, 70), "spark": (255, 255, 255),
        "hud": (242, 242, 242), "hud_dim": (140, 140, 140), "hud_faint": (62, 62, 62),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

SECTIONS = 12
KEEL_LOCK_EVERY = 78.0
KEEL_LOCK_FOR = 6.0


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


class OrbitalShipyardMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "amber"
        self._palette = PALETTES["amber"]
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._frame_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._hud_mode = "minimal"
        self._fill = "line"
        self._orientation = "auto"
        self._hull_stage = 0.62
        self._arm_count = 6
        self._camera_crane = 0.5
        self._sparks_on = True
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "ORBITAL SHIPYARD"
        self._subtitle = "BERTH 3 · KEEL 118"

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
        self._posts = []
        self._arms = []
        self._drones = []
        self._sparks = []
        self._locks = []
        self._lock_span = 0.0
        self._lock = None
        self._angle = 0.0
        self._centre = (0.0, 0.0)
        self._length = 400.0
        self._depth = 60.0
        self._height = 60.0
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

        palette = str(cfg.get("palette", "amber")).lower()
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

        self._hull_stage = self._number(cfg, "hull_stage", 0.62, 0.0, 1.0)
        self._arm_count = self._integer(cfg, "arm_count", 6, 2, 10)
        self._camera_crane = self._number(cfg, "camera_crane", 0.5, 0.0, 4.0)
        self._sparks_on = self._bool(cfg, "sparks", True)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "ORBITAL SHIPYARD", 30) or "ORBITAL SHIPYARD"
        self._subtitle = self._text(cfg, "subtitle", "BERTH 3 · KEEL 118", 44)

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
            print(f"[Shipyard] seed={self.seed} preset={self._preset} "
                  f"stage={self._hull_stage:.2f} arms={self._arm_count} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Shipyard] configuration error: {exc}")

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
        self._posts = []
        self._arms = []
        self._drones = []
        self._sparks = []
        self._locks = []
        self._lock = None
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
        self._depth = self._height * 0.85
        self._build_berth()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_berth(self):
        """Sections, gantry posts, arms, drones and the keel-lock schedule."""
        rng = random.Random(self.seed ^ 0x5A17)
        self._rng = rng
        self._sections = [
            {"x": -0.5 + (index + 0.5) / SECTIONS,
             "locked_at": (index + 1) / SECTIONS,
             "rib": 0.55 + 0.45 * math.sin(math.pi * (index + 0.5) / SECTIONS)}
            for index in range(SECTIONS)
        ]
        self._posts = [
            {"x": -0.5 + (index + 0.5) * (1.0 / QUALITY["high"]["posts"]),
             "lean": rng.uniform(-0.04, 0.04)}
            for index in range(QUALITY["high"]["posts"] + 1)
        ]
        arms = []
        for index in range(QUALITY["high"]["arms"]):
            arms.append({
                "x": -0.42 + 0.84 * (index + 0.5) / QUALITY["high"]["arms"],
                "side": 1 if index % 2 == 0 else -1,
                "period": rng.uniform(10.0, 20.0),
                "phase": rng.uniform(0.0, TAU),
                "reach": rng.uniform(0.55, 0.95),
            })
        self._arms = arms
        self._drones = [
            {"offset": rng.uniform(0.0, 1.0), "speed": rng.uniform(0.02, 0.05),
             "y": rng.uniform(0.05, 0.95), "phase": rng.uniform(0.0, TAU)}
            for _ in range(QUALITY["high"]["drones"])
        ]
        locks = []
        span = KEEL_LOCK_EVERY * 6.0
        for k in range(6):
            locks.append((k * KEEL_LOCK_EVERY + rng.uniform(-0.15, 0.15) * KEEL_LOCK_EVERY,
                          KEEL_LOCK_FOR, rng.randrange(SECTIONS)))
        self._locks = locks
        self._lock_span = span
        self._build_sparks()

    def _build_sparks(self):
        """A few welds are already sparking when the mode opens."""
        rng = self._rng
        self._sparks = []
        for _ in range(QUALITY["high"]["sparks"] // 2):
            arm = self._arms[rng.randrange(len(self._arms))]
            tip = self._project(arm["x"] + rng.uniform(-0.02, 0.02),
                                rng.uniform(0.14, 0.34),
                                arm["side"] * rng.uniform(0.18, 0.26))
            self._sparks.append({
                "x": tip[0], "y": tip[1],
                "vx": rng.uniform(-26.0, 26.0), "vy": rng.uniform(-34.0, 6.0),
                "life": rng.uniform(0.2, 1.0), "span": rng.uniform(1.0, 3.0),
            })

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.25
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - 0.52) / 0.55) ** 2)
            color = _mix(base, palette["haze"], band * 0.20)
            pygame.draw.line(surface, color, (0, y), (width, y))
        rng = random.Random(self.seed ^ 0x5EED)
        for _ in range(max(40, int(width * height / 14000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(20, 48) / 255.0))
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
                    dark = self._vignette * (max(0.0, r - 0.30) / 0.70) ** 1.7
                    k = int(255 * max(0.06, 1.0 - dark))
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
                k = int(50 + 205 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (width, y), 1)
            bot_h = max(34, int(height * 0.085))
            for y in range(bot_h):
                k = int(255 - 226 * (y / max(1, bot_h - 1)))
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
                                alpha=246)
        rule_y = int(y + m["title_px"] * 1.16)
        pygame.draw.line(layer, _rgba(self._palette["accent"], 150),
                         (m["title_x"], rule_y),
                         (m["title_x"] + int(title_w * 0.68), rule_y), 1)
        if self._hud_mode == "full":
            self._tracked(layer, self._subtitle, sub_font, self._palette["hud_dim"],
                          (m["title_x"], rule_y + 6), tracking=m["sub_px"] * 0.10,
                          alpha=200)
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

    def _hull_percent(self) -> int:
        return int(round(self._hull_stage * 100))

    def _telemetry(self):
        palette = self._palette
        lines = [(f"HULL {self._hull_percent()}%", palette["hud"], 220),
                 (f"ARMS {self._arm_count:02d}", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"STAGE {int(self._hull_stage * SECTIONS):02d}/{SECTIONS}",
                          palette["hud_dim"], 175))
            lines.append((f"CRANE {self._camera_crane:.1f} PX/S",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._lock is not None:
            return "KEEL LOCK · SPINE LIT", True
        return "WELDING · GANTRY NOMINAL", False

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
        surface = self._cached_text(status, m["status_px"], color, 205)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.75),
                         (rect.left, rect.bottom + 4), (rect.right, rect.bottom + 4), 1)

    # ---------------------------------------------------------------- projection

    def _camera_angle(self) -> float:
        """The crane: a few degrees of isometric angle over a 120 s cycle."""
        width, _height = self._screen_size
        amp = math.radians(7.0 * self._camera_crane)   # 0 = a locked-off camera
        return math.sin(TAU * self._time / 120.0) * amp

    def _project(self, x, y, z):
        """
        Isometric with the camera's crane: x along the keel, y up, z across the
        hull.  Two vanishing cues — the depth offset and the vertical shift.
        """
        ca, sa = math.cos(self._angle), math.sin(self._angle)
        sx = self._centre[0] + x * self._length + z * self._depth * ca
        sy = self._centre[1] - y * self._height - z * self._depth * sa * 0.30
        return (sx, sy)

    def _lock_state(self):
        if not self._locks or self._lock_span <= 0.0:
            return None
        local = self._time % self._lock_span
        for start, duration, section in self._locks:
            if start <= local < start + duration:
                p = (local - start) / duration
                return {"progress": p, "section": section,
                        "severity": math.sin(math.pi * p) ** 0.6}
        return None

    # ---------------------------------------------------------------- drawing

    def _unlocked(self, index: int) -> bool:
        return (index + 1) / SECTIONS <= self._hull_stage + 1e-6

    def _draw_hull(self, screen, quality):
        """
        The hull in side elevation with a hint of depth: keel, deck, ribs.  Only
        the sections the stage has reached are drawn, so the far end is bare keel.
        """
        palette = self._palette
        lock = self._lock
        near, far = 0.5, -0.5
        deck = 0.46

        def lit_at(x):
            if lock is None:
                return 0.0
            wave_x = -0.5 + lock["progress"] * 1.15
            return max(0.0, 1.0 - abs(x - wave_x) / 0.12) * lock["severity"]

        # the far keel, faint: the depth cue
        previous = None
        for index in range(SECTIONS + 1):
            x = -0.5 + index / SECTIONS
            point = self._project(x, 0.0, far)
            if previous is not None:
                pygame.draw.line(screen, _scale(palette["far"], 0.9), previous, point, 1)
            previous = point

        # the near keel: the length of the berth, and the lock wave runs along it
        previous = None
        for index in range(SECTIONS + 1):
            x = -0.5 + index / SECTIONS
            point = self._project(x, 0.0, near)
            if previous is not None:
                lit = lit_at(x)
                color = _mix(_mix(palette["structure"], palette["hero"], 0.55),
                             palette["hero"], lit)
                pygame.draw.line(screen, color, previous, point,
                                 3 if lit > 0.4 else 2)
            previous = point

        # the deck over the sections that have locked, and their ribs
        deck_points = []
        for index, section in enumerate(self._sections):
            if not self._unlocked(index):
                break
            x = section["x"]
            h = 0.16 + section["rib"] * 0.30
            b_near = self._project(x, 0.0, near)
            t_near = self._project(x, h, near)
            b_far = self._project(x, 0.0, far)
            t_far = self._project(x, h, far)
            pygame.draw.line(screen, _mix(palette["far"], palette["structure"], 0.8),
                             b_far, t_far, 1)
            pygame.draw.line(screen, _mix(palette["structure"], palette["hero"], 0.25),
                             b_near, t_near, 1)
            pygame.draw.line(screen, _scale(palette["guide"], 0.85),
                             t_far, t_near, 1)
            # the plate between this rib and the next: only on finished sections
            if index < max(0, int(self._hull_stage * SECTIONS) - 1):
                mid_far = self._project(x + 0.5 / SECTIONS, h * 0.55, far)
                mid_near = self._project(x + 0.5 / SECTIONS, h * 0.55, near)
                pygame.draw.line(screen, _scale(palette["guide"], 0.7), mid_far, mid_near, 1)
            deck_points.append(t_near)

        if len(deck_points) > 1:
            pygame.draw.lines(screen, _mix(palette["structure"], palette["hero"], 0.70),
                              False, deck_points, 2)

        # once the keel locks, the hull's outline is one continuous line
        if lock is not None and lock["severity"] > 0.35 and len(deck_points) > 1:
            pygame.draw.lines(screen, palette["hero"], False, deck_points, 2)

    def _draw_gantry(self, screen, quality):
        """Three portal arches over the berth, and the lamp on each apex."""
        palette = self._palette
        lock = self._lock
        arches = (-0.46, -0.02, 0.42)[:max(2, quality["posts"] // 2 + 1)]
        for index, x in enumerate(arches):
            left = self._project(x, -0.26, -0.9)
            right = self._project(x, -0.26, 0.9)
            apex = self._project(x, 0.92, 0.0)
            leg_left = self._project(x, 0.40, -0.55)
            leg_right = self._project(x, 0.40, 0.55)
            behind = index == 0
            color = _mix(palette["far"], palette["structure"], 0.75 if behind else 1.0)
            width = 1 if behind else 2
            pygame.draw.lines(screen, color, False,
                              [left, leg_left, apex, leg_right, right], width)
            # the truss: one diagonal per leg
            pygame.draw.line(screen, _scale(palette["guide"], 0.8), left, leg_left, 1)
            pygame.draw.line(screen, _scale(palette["guide"], 0.8), right, leg_right, 1)
            lit = 0.0
            if lock is not None:
                wave_x = -0.5 + lock["progress"] * 1.15
                lit = max(0.0, 1.0 - abs(x - wave_x) / 0.16) * lock["severity"]
            lamp = _mix(palette["weld"], palette["hero"], 0.2 + 0.8 * lit) \
                if lit > 0.02 else _mix(palette["weld"], palette["far"], 0.45)
            pygame.draw.circle(screen, lamp, (int(apex[0]), int(apex[1])),
                               3 if lit > 0.5 else 2)

    def _draw_crane(self, screen):
        """A mast over the middle arch, lowering a section every 45 s."""
        palette = self._palette
        cycle = (self._time % 45.0) / 45.0
        if cycle < 0.25:
            reach, drop = cycle / 0.25, 0.0
        elif cycle < 0.55:
            reach, drop = 1.0, (cycle - 0.25) / 0.30
        elif cycle < 0.75:
            reach, drop = 1.0, 1.0
        else:
            reach, drop = 1.0 - (cycle - 0.75) / 0.25, 0.35
        x = _lerp(-0.30, 0.16, reach)
        mast = self._project(-0.30, 1.16, 0.0)
        top = self._project(x, 1.16, 0.0)
        trolley = self._project(x, 1.00, 0.0)
        height = _lerp(1.00, 0.66, drop)
        block = self._project(x, height, 0.0)
        pygame.draw.line(screen, _scale(palette["structure"], 0.9), mast, top, 1)
        pygame.draw.line(screen, _scale(palette["accent"], 0.8), top, trolley, 1)
        pygame.draw.line(screen, _scale(palette["accent"], 0.6), trolley, block, 1)
        half = 0.05
        a = self._project(x - half, height - 0.03, -0.28)
        b = self._project(x + half, height - 0.03, -0.28)
        c = self._project(x + half, height - 0.03, 0.28)
        d = self._project(x - half, height - 0.03, 0.28)
        pygame.draw.lines(screen, palette["hero"], True, [a, b, c, d], 1)

    def _draw_arms(self, screen, quality):
        palette = self._palette
        for arm in self._arms[:quality["arms"]]:
            # weld and retract: the tip reaches in, holds, pulls back
            phase = (self._time / arm["period"] + arm["phase"] / TAU) % 1.0
            reach = arm["reach"] * (0.35 + 0.65 * math.sin(math.pi * phase) ** 0.8)
            base = self._project(arm["x"], 0.64, arm["side"] * 0.12)
            tip = self._project(arm["x"] + 0.02 * math.sin(phase * TAU),
                                _lerp(0.64, 0.38, reach), arm["side"] * 0.18)
            elbow = ((base[0] + tip[0]) * 0.5 + (10 if arm["side"] > 0 else -10),
                     (base[1] + tip[1]) * 0.5 - 12)
            color = _mix(palette["structure"], palette["hero"], 0.30 + 0.35 * reach)
            pygame.draw.lines(screen, color, False, [base, elbow, tip], 1)
            hot = reach > 0.72
            pygame.draw.circle(screen, palette["spark"] if hot else palette["accent"],
                               (int(tip[0]), int(tip[1])), 2 if hot else 1)
            if hot and self._sparks_on:
                self._emit_sparks(tip)

    def _draw_arms(self, screen, quality):
        palette = self._palette
        for arm in self._arms[:quality["arms"]]:
            # weld and retract: the tip reaches in, holds, pulls back
            phase = (self._time / arm["period"] + arm["phase"] / TAU) % 1.0
            reach = arm["reach"] * (0.35 + 0.65 * math.sin(math.pi * phase) ** 0.8)
            base = self._project(arm["x"], 0.96, arm["side"] * 0.30)
            tip = self._project(arm["x"] + 0.02 * math.sin(phase * TAU),
                                _lerp(0.96, 0.22, reach), arm["side"] * 0.30)
            elbow = ((base[0] + tip[0]) * 0.5 + (8 if arm["side"] > 0 else -8),
                     (base[1] + tip[1]) * 0.5 - 10)
            color = _mix(palette["structure"], palette["hero"], 0.30 + 0.35 * reach)
            pygame.draw.lines(screen, color, False, [base, elbow, tip], 1)
            hot = reach > 0.72
            pygame.draw.circle(screen, palette["spark"] if hot else palette["accent"],
                               (int(tip[0]), int(tip[1])), 2 if hot else 1)
            if hot and self._sparks_on:
                self._emit_sparks(tip)

    def _emit_sparks(self, tip):
        pool = self._sparks
        if not self._sparks_on or len(pool) >= QUALITY[self._quality]["sparks"]:
            return
        rng = self._rng
        for _ in range(2):
            pool.append({
                "x": tip[0], "y": tip[1],
                "vx": rng.uniform(-26.0, 26.0), "vy": rng.uniform(-34.0, 6.0),
                "life": 1.0, "span": rng.uniform(1.0, 3.0),
            })

    def _update_sparks(self, dt: float):
        if not self._sparks_on:
            self._sparks = []
            return
        alive = []
        for spark in self._sparks:
            spark["life"] -= dt / max(0.2, spark["span"])
            if spark["life"] <= 0.0:
                continue
            spark["x"] += spark["vx"] * dt
            spark["y"] += spark["vy"] * dt
            spark["vy"] += 26.0 * dt
            spark["vx"] *= 0.985
            alive.append(spark)
        self._sparks = alive[:QUALITY[self._quality]["sparks"]]

    def _draw_sparks(self, screen):
        palette = self._palette
        for spark in self._sparks:
            level = _clamp(spark["life"], 0.0, 1.0)
            color = _mix(palette["weld"], palette["spark"], level)
            pygame.draw.circle(screen, color, (int(spark["x"]), int(spark["y"])),
                               1 if level < 0.6 else 2)

    def _draw_drones(self, screen, quality):
        palette = self._palette
        for drone in self._drones[:quality["drones"]]:
            t = (drone["offset"] + self._time * drone["speed"]) % 1.0
            x = -0.48 + 0.96 * t
            y = 0.04 + drone["y"] * 0.16
            head = self._project(x, y, -0.32)
            tail = self._project(x - 0.03, y, -0.32)
            pygame.draw.circle(screen, palette["hero"], (int(head[0]), int(head[1])), 1)
            pygame.draw.line(screen, _scale(palette["accent"], 0.6), tail, head, 1)

    def _draw_crane(self, screen):
        """A gantry crane lowering a section every 45 s."""
        palette = self._palette
        cycle = (self._time % 45.0) / 45.0
        # the trolley runs out over the hull, then lowers, holds, and returns
        if cycle < 0.25:
            reach, drop = cycle / 0.25, 0.0
        elif cycle < 0.55:
            reach, drop = 1.0, (cycle - 0.25) / 0.30
        elif cycle < 0.75:
            reach, drop = 1.0, 1.0
        else:
            reach, drop = 1.0 - (cycle - 0.75) / 0.25, 0.35
        x = _lerp(-0.45, 0.10, reach)
        mast_top = self._project(x, 0.72, 0.0)
        trolley = self._project(x, 0.36, 0.0)
        block = self._project(x, _lerp(0.36, 0.16, drop), 0.0)
        pygame.draw.line(screen, _scale(palette["structure"], 0.9), mast_top, trolley, 1)
        pygame.draw.line(screen, _scale(palette["accent"], 0.75), trolley, block, 1)
        # the section being lowered
        half = 0.035
        a = self._project(x - half, _lerp(0.36, 0.16, drop) - 0.02, -0.12)
        b = self._project(x + half, _lerp(0.36, 0.16, drop) - 0.02, -0.12)
        c = self._project(x + half, _lerp(0.36, 0.16, drop) - 0.02, 0.12)
        d = self._project(x - half, _lerp(0.36, 0.16, drop) - 0.02, 0.12)
        pygame.draw.lines(screen, palette["hero"], True, [a, b, c, d], 1)
        pygame.draw.circle(screen, palette["spark"], (int(block[0]), int(block[1])), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        for arm in self._arms:
            phase = (self._time / arm["period"] + arm["phase"] / TAU) % 1.0
            if math.sin(math.pi * phase) < 0.7:
                continue
            base = self._project(arm["x"], 0.62, arm["side"] * 0.5)
            tip = self._project(arm["x"], 0.16, arm["side"] * 0.22)
            pygame.draw.circle(self._bloom, _scale(palette["spark"], 0.55 * self._glow_strength),
                               (int(tip[0] * sx), int(tip[1] * sy)), 1)
        if self._lock is not None:
            wave_x = -0.5 + self._lock["progress"] * 1.15
            point = self._project(wave_x, 0.0, 0.0)
            pygame.draw.circle(self._bloom,
                               _scale(palette["hero"], 0.5 * self._glow_strength),
                               (int(point[0] * sx), int(point[1] * sy)), 1)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_berth_rails(self, screen):
        """The berth itself: two rails below the keel, the floor of the site."""
        palette = self._palette
        for z in (-0.5, 0.5):
            a = self._project(-0.55, -0.42, z)
            b = self._project(0.55, -0.42, z)
            pygame.draw.line(screen, _scale(palette["structure"], 0.8), a, b, 1)
        for index in range(0, SECTIONS + 1, 2):
            x = -0.5 + index / SECTIONS
            a = self._project(x, -0.42, -0.5)
            b = self._project(x, -0.42, 0.5)
            pygame.draw.line(screen, _scale(palette["guide"], 0.7), a, b, 1)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._lock = self._lock_state()
        self._angle = self._camera_angle()
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_berth_rails(screen)
        self._draw_gantry(screen, quality)
        self._draw_hull(screen, quality)
        self._draw_crane(screen)
        self._draw_arms(screen, quality)
        self._draw_drones(screen, quality)
        self._draw_sparks(screen)
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
        self._update_sparks(dt)
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
                print(f"[Shipyard] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("SHIPYARD // CONFIGURATION REFUSED", True,
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
            "hull_stage": self._hull_stage,
            "hull_percent": self._hull_percent(),
            "sections_unlocked": sum(1 for i in range(SECTIONS) if self._unlocked(i)),
            "arms": self._arm_count,
            "lock": dict(self._lock) if self._lock else None,
            "angle": self._angle,
            "centre": self._centre,
            "length": self._length,
            "sparks": len(self._sparks),
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
