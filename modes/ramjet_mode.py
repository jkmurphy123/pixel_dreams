"""Ramjet — an interstellar ramjet under power, seen from behind and to one side.

Slow Wireframe §4.12.  A magnetic scoop opens ahead of the ship as a funnel of
wireframe rings, interstellar gas streaks into the throat, a core burns there,
and a long wake trails behind.  The camera follows from just behind and one
side, so the funnel opens across the frame and the wake runs out of it.

The card calls this the mode about velocity: the subject is the engine working.
The dust converges, the core breathes, and every so often a dense clump is
ingested — the core flares, the wake lengthens and the hull sharpens against the
glare.

The drawing is all line.  The scoop is a set of projected ellipse rings with a
few radial field lines; dust is a stream of short streaks converging on the
throat; the wake is a handful of long fading lines.  One half-resolution
additive bloom carries the core (§2.8).

Camera behaviour (§2.3): follow.  The card's 5 px/s is a smoothed side offset
that keeps the ship in frame without gluing it, plus the ship's own slight yaw.

Determinism (§2.9): the rings, dust, wakes and clump schedule all come from
`seed` and elapsed time.  A pinned seed reproduces a still exactly.

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

#: Scoop rings, dust, wake lines and bloom per tier (§2.8).
QUALITY = {
    "low": {"rings": 4, "dust": 30, "wake": 4, "glow_div": 8},
    "medium": {"rings": 6, "dust": 54, "wake": 6, "glow_div": 5},
    "high": {"rings": 8, "dust": 84, "wake": 8, "glow_div": 4},
}

#: Where the funnel and the ship sit, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.560, 0.500), "mouth": 0.230, "title_px": 21},
    "landscape": {"anchor": (0.560, 0.500), "mouth": 0.220, "title_px": 30},
    "portrait": {"anchor": (0.540, 0.520), "mouth": 0.260, "title_px": 34},
    "square": {"anchor": (0.550, 0.500), "mouth": 0.240, "title_px": 26},
}

PALETTES = {
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "core": (255, 250, 230), "dust": (150, 210, 240), "wake": (120, 190, 230),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "core": (255, 248, 232), "dust": (240, 200, 150), "wake": (220, 170, 120),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "phosphor": {
        "bg_top": (1, 12, 5), "bg_bottom": (0, 4, 2), "haze": (8, 40, 16),
        "structure": (46, 160, 96), "hero": (217, 255, 232),
        "accent": (105, 240, 174), "glow": (168, 255, 208),
        "core": (240, 255, 240), "dust": (170, 255, 200), "wake": (120, 220, 160),
        "hud": (217, 255, 232), "hud_dim": (86, 160, 116), "hud_faint": (26, 66, 38),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

CLUMP_EVERY = 15.0
CLUMP_FOR = 3.0


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


class RamjetMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "vector_blue"
        self._palette = PALETTES["vector_blue"]
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._frame_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._hud_mode = "minimal"
        self._fill = "line"
        self._orientation = "auto"
        self._ship_speed = 0.12
        self._scoop_size = 1.0
        self._dust_density = 0.6
        self._camera_offset = 0.3
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "RAMJET"
        self._subtitle = "ISV-4 · UNDER POWER"

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

        self._centre = (0.0, 0.0)
        self._mouth_r = 100.0
        self._throat = (0.0, 0.0)
        self._mouth = (0.0, 0.0)
        self._dust = []
        self._wakes = []
        self._stars = []
        self._clumps = []
        self._clump_span = 0.0
        self._clump = None
        self._core_level = 0.0
        self._yaw = 0.0
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

        palette = str(cfg.get("palette", "vector_blue")).lower()
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

        self._ship_speed = self._number(cfg, "ship_speed", 0.12, 0.0, 0.99)
        self._scoop_size = self._number(cfg, "scoop_size", 1.0, 0.3, 2.0)
        self._dust_density = self._number(cfg, "dust_density", 0.6, 0.0, 1.0)
        self._camera_offset = self._number(cfg, "camera_offset", 0.3, 0.0, 1.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer_compat(cfg, "scanline_alpha", 4)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "RAMJET", 30) or "RAMJET"
        self._subtitle = self._text(cfg, "subtitle", "ISV-4 · UNDER POWER", 44)

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
            print(f"[Ramjet] seed={self.seed} preset={self._preset} "
                  f"scoop={self._scoop_size:.1f} dust={self._dust_density:.2f} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Ramjet] configuration error: {exc}")

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
        self._dust = []
        self._wakes = []
        self._stars = []
        self._clumps = []
        self._clump = None
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
        self._mouth_r = self._layout["mouth"] * min(width, height) * self._scoop_size
        # the funnel opens to the right: the mouth is ahead of the ship
        self._mouth = (self._centre[0] + self._mouth_r * 1.02, self._centre[1])
        self._throat = (self._centre[0] - self._mouth_r * 0.55, self._centre[1])
        self._build_streams()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_streams(self):
        rng = random.Random(self.seed ^ 0x2A3E7)
        dust = []
        for _ in range(QUALITY["high"]["dust"]):
            dust.append({
                "x": rng.uniform(0.0, 1.0),          # 0 at the throat, 1 at the mouth
                "y": rng.uniform(-1.0, 1.0),
                "speed": rng.uniform(0.9, 2.4),
                "phase": rng.uniform(0.0, TAU),
            })
        self._dust = dust
        wakes = []
        for index in range(QUALITY["high"]["wake"]):
            wakes.append({
                "offset": rng.uniform(-0.35, 0.35),
                "length": rng.uniform(0.7, 1.4),
                "phase": rng.uniform(0.0, TAU),
                "speed": rng.uniform(0.6, 1.2),
            })
        self._wakes = wakes
        clumps = []
        span = CLUMP_EVERY * 6.0
        for k in range(6):
            clumps.append((k * CLUMP_EVERY + rng.uniform(-0.12, 0.12) * CLUMP_EVERY,
                           CLUMP_FOR))
        self._clumps = clumps
        self._clump_span = span

    def _build_stars(self):
        rng = random.Random(self.seed ^ 0x57A2)
        width, height = self._screen_size
        self._stars = [
            (rng.uniform(0, width), rng.uniform(0, height), rng.randint(16, 46))
            for _ in range(60)
        ]

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = y / max(1, height - 1)
            base = _mix(palette["bg_top"], palette["bg_bottom"], t ** 1.2)
            band = math.exp(-(((t - 0.5) / 0.55) ** 2))
            color = _mix(base, palette["haze"], band * 0.14)
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

    def _telemetry(self):
        palette = self._palette
        lines = [(f"V {self._ship_speed:.2f} C", palette["hud"], 220),
                 (f"INTAKE {int(self._dust_density * 100):02d}%", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"SCOOP {self._scoop_size:.1f}", palette["hud_dim"], 175))
            lines.append((f"CORE {self._core_level * 100:3.0f}%",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._clump is not None and self._clump["level"] > 0.4:
            return "CLUMP INGEST · CORE FLARE", True
        return "INTAKE STEADY · WAKE NOMINAL", False

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

    # ---------------------------------------------------------------- geometry

    def _clump_state(self):
        if not self._clumps or self._clump_span <= 0.0:
            return None
        local = self._time % self._clump_span
        for start, duration in self._clumps:
            if start <= local < start + duration:
                p = (local - start) / duration
                # a fast brighten, then a decay
                level = math.sin(math.pi * p) ** 0.7
                return {"progress": p, "level": level}
        return None

    def _scoop_radius(self, t: float) -> float:
        """t = 0 at the throat, 1 at the mouth."""
        return self._mouth_r * (0.10 + 0.90 * t ** 0.85)

    def _scoop_point(self, t: float, angle: float, depth: float = 0.0):
        x = _lerp(self._throat[0], self._mouth[0], t)
        y = self._centre[1]
        radius = self._scoop_radius(t)
        return (x + math.cos(angle) * radius * 0.28,
                y + math.sin(angle) * radius,
                depth)

    def _draw_scoop(self, screen, quality):
        palette = self._palette
        rings = quality["rings"]
        pulse = 1.0 + 0.06 * math.sin(TAU * self._time / 6.0)
        previous = None
        for index in range(rings):
            t = index / (rings - 1.0)
            radius = self._scoop_radius(t) * pulse
            x = _lerp(self._throat[0], self._mouth[0], t)
            ellipse = pygame.Rect(int(x - radius * 0.28), int(self._centre[1] - radius),
                                  int(radius * 0.56), int(radius * 2))
            near = 0.35 + 0.65 * t
            colour = _mix(palette["far"], palette["structure"], 0.45 + 0.55 * near)
            pygame.draw.ellipse(screen, colour, ellipse, 2 if index == rings - 1 else 1)
        # a few field lines running from the mouth to the throat
        for k in range(8):
            angle = TAU * k / 8.0 + self._time * 0.25
            a = self._scoop_point(1.0, angle)
            b = self._scoop_point(0.06, angle)
            pygame.draw.line(screen, _scale(palette["accent"], 0.30),
                             (a[0], a[1]), (b[0], b[1]), 1)

    def _draw_ship(self, screen):
        """A small hull inside the funnel, nose at the throat."""
        palette = self._palette
        nose = self._throat
        yaw = self._yaw
        length = self._mouth_r * 0.95
        tail_x = nose[0] - length
        body = [
            (nose[0] + 8, nose[1]),
            (tail_x + length * 0.35, nose[1] - length * 0.085 + yaw),
            (tail_x, nose[1] - length * 0.13 + yaw),
            (tail_x, nose[1] + length * 0.13 + yaw),
            (tail_x + length * 0.35, nose[1] + length * 0.085 + yaw),
        ]
        glare = 0.35 + 0.65 * self._core_level
        colour = _mix(palette["structure"], palette["hero"], 0.55 + 0.40 * glare)
        pygame.draw.lines(screen, colour, True, body, 1)
        # the fins and a spine
        pygame.draw.line(screen, _scale(palette["guide"], 0.85),
                         (nose[0] + 6, nose[1]), (tail_x + 4, nose[1] + yaw), 1)
        for sign in (-1, 1):
            pygame.draw.line(screen, _scale(palette["guide"], 0.8),
                             (tail_x + length * 0.1, nose[1] + sign * length * 0.10 + yaw),
                             (tail_x - length * 0.08, nose[1] + sign * length * 0.20 + yaw), 1)
        # one lit window, so the hull has a scale
        pygame.draw.circle(screen, _scale(palette["hero"], 0.7 * glare),
                           (int(nose[0] - length * 0.45), int(nose[1] + yaw)), 1)

    def _draw_dust(self, screen, quality):
        palette = self._palette
        density = self._dust_density
        if density <= 0.0:
            return
        count = int(quality["dust"] * density)
        for particle in self._dust[:count]:
            t = (particle["x"] + self._time * particle["speed"] * 0.16) % 1.0
            # converging on the throat: y shrinks as t goes to 0
            radius = self._scoop_radius(max(0.02, t))
            y = self._centre[1] + particle["y"] * radius
            x = _lerp(self._throat[0], self._mouth[0], t)
            streak = max(2.0, 11.0 * particle["speed"] * (0.35 + 0.65 * t))
            level = 0.35 + 0.65 * t
            jitter = math.sin(particle["phase"] + self._time * 3.0) * 1.6
            pygame.draw.line(screen, _scale(palette["dust"], level),
                             (x, y + jitter), (x + streak, y + jitter), 1)

    def _draw_wake(self, screen, quality):
        palette = self._palette
        length_mul = 1.0 + 0.8 * (self._clump["level"] if self._clump else 0.0)
        for index, wake in enumerate(self._wakes[:quality["wake"]]):
            t = (self._time * wake["speed"] * 0.25 + wake["phase"]) % 1.0
            start = (self._throat[0] - self._mouth_r * 0.95,
                     self._centre[1] + wake["offset"] * self._mouth_r * 0.5)
            span = self._mouth_r * 1.8 * wake["length"] * length_mul
            end = (start[0] - span, start[1] + 2.0 * math.sin(t * TAU))
            level = 0.25 + 0.45 * (0.5 + 0.5 * math.sin(t * TAU))
            pygame.draw.line(screen, _scale(palette["wake"], level), start, end, 1)

    def _draw_core(self, screen):
        palette = self._palette
        level = self._core_level
        x, y = self._throat
        radius = 2 + int(4 * level)
        pygame.draw.circle(screen, _scale(palette["core"], 0.55 + 0.45 * level),
                           (int(x), int(y)), radius)
        if level > 0.4:
            for k in range(4):
                angle = TAU * k / 4.0 + self._time
                pygame.draw.line(screen, _scale(palette["core"], level * 0.8),
                                 (x, y), (x + math.cos(angle) * radius * 3.2,
                                          y + math.sin(angle) * radius * 3.2), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        x, y = self._throat
        pygame.draw.circle(self._bloom,
                           _scale(palette["core"], (0.30 + 0.55 * self._core_level)
                                  * self._glow_strength),
                           (int(x * sx), int(y * sy)), 2)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._clump = self._clump_state()
        # the camera's smoothed side offset, and the ship's slight yaw
        offset = self._camera_offset * math.sin(TAU * self._time / 90.0)
        self._centre = (self._layout["anchor"][0] * self._screen_size[0] + offset * 12.0,
                        self._layout["anchor"][1] * self._screen_size[1])
        self._mouth = (self._centre[0] + self._mouth_r * 1.02, self._centre[1])
        self._throat = (self._centre[0] - self._mouth_r * 0.55, self._centre[1])
        self._yaw = math.sin(TAU * self._time / 7.0) * 1.6
        base = 0.55 + 0.15 * math.sin(TAU * self._time / 5.0)
        if self._clump is not None:
            base += 0.55 * self._clump["level"]
        self._core_level = _clamp(base, 0.0, 1.0)
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_wake(screen, quality)
        self._draw_scoop(screen, quality)
        self._draw_dust(screen, quality)
        self._draw_ship(screen)
        self._draw_core(screen)
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
                print(f"[Ramjet] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("RAMJET // CONFIGURATION REFUSED", True,
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
            "centre": self._centre,
            "mouth": self._mouth,
            "throat": self._throat,
            "mouth_r": self._mouth_r,
            "dust": len(self._dust),
            "wake": len(self._wakes),
            "clump": dict(self._clump) if self._clump else None,
            "core_level": self._core_level,
            "yaw": self._yaw,
            "ship_speed": self._ship_speed,
            "scoop_size": self._scoop_size,
            "dust_density": self._dust_density,
            "camera_offset": self._camera_offset,
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
