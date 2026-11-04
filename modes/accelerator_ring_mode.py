"""Accelerator Ring — an instrument around a moon, with one thing moving.

Slow Wireframe §4.9.  A particle accelerator encircles a moon: an ellipse in
perspective, detector halls at intervals, and a pulse of light that travels the
ring once every eighteen seconds.  The camera holds a slow orbit, the ring
precesses, the moon turns inside it — so the only fast thing in the frame is the
pulse, and it is small.  When the pulse reaches a hall, the hall's ring glyph
fills from the inside, segment by segment, and goes dark as the pulse moves on.

The drawing is all line.  The ring, the moon's graticule and the halls are
drawn per frame from a handful of angles; the pulse and its trail are short arcs
on the ring.  Depth is carried by the ellipse, the moon's terminator and one
half-resolution additive bloom on the pulse and the lit halls (§2.8).

Camera behaviour (§2.3): orbit.  The card's 2° over 240 s is a slow change of
the ellipse's tilt, which is what makes the ring read as a clock rather than a
circle.  The anchor is recomputed per aspect.

Determinism (§2.9): the halls, the stars and the pulse phase come from `seed`
and elapsed time.  A pinned seed reproduces a still exactly.

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

#: Ring segments, trail, stars and bloom per tier (§2.8).
QUALITY = {
    "low": {"segments": 64, "trail": 6, "stars": 30, "moon": 8, "glow_div": 8},
    "medium": {"segments": 96, "trail": 10, "stars": 48, "moon": 12, "glow_div": 5},
    "high": {"segments": 140, "trail": 14, "stars": 70, "moon": 16, "glow_div": 4},
}

#: Where the ring sits, how wide it is, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.470, 0.500), "rwidth": 0.720, "title_px": 21},
    "landscape": {"anchor": (0.480, 0.500), "rwidth": 0.620, "title_px": 30},
    "portrait": {"anchor": (0.500, 0.460), "rwidth": 0.820, "title_px": 34},
    "square": {"anchor": (0.480, 0.490), "rwidth": 0.700, "title_px": 26},
}

PALETTES = {
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "moon": (18, 34, 54), "moon_dark": (4, 9, 16), "pulse": (255, 250, 230),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "phosphor": {
        "bg_top": (1, 12, 5), "bg_bottom": (0, 4, 2), "haze": (8, 40, 16),
        "structure": (46, 160, 96), "hero": (217, 255, 232),
        "accent": (105, 240, 174), "glow": (168, 255, 208),
        "moon": (20, 48, 34), "moon_dark": (4, 14, 8), "pulse": (240, 255, 240),
        "hud": (217, 255, 232), "hud_dim": (86, 160, 116), "hud_faint": (26, 66, 38),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "moon": (46, 30, 16), "moon_dark": (12, 7, 3), "pulse": (255, 246, 226),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
}

LAP_SECONDS = 18.0

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


def _angle_delta(a: float, b: float) -> float:
    """Signed smallest difference between two angles."""
    d = (a - b + math.pi) % TAU - math.pi
    return d


class AcceleratorRingMode:
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
        self._ring_radius = 0.7
        self._pulse_speed = 1.0
        self._detector_count = 12
        self._camera_orbit = 2.0
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "ACCELERATOR RING"
        self._subtitle = "48 KM · BEAM LINE"

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

        self._halls = []
        self._stars = []
        self._centre = (0.0, 0.0)
        self._rx = 100.0
        self._ry = 40.0
        self._tilt = 0.0
        self._pulse_angle = 0.0
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

        self._ring_radius = self._number(cfg, "ring_radius", 0.7, 0.2, 1.5)
        self._pulse_speed = self._number(cfg, "pulse_speed", 1.0, 0.05, 8.0)
        self._detector_count = self._integer(cfg, "detector_count", 12, 4, 24)
        self._camera_orbit = self._number(cfg, "camera_orbit", 2.0, 0.0, 20.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "ACCELERATOR RING", 30) or "ACCELERATOR RING"
        self._subtitle = self._text(cfg, "subtitle", "48 KM · BEAM LINE", 44)

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
            print(f"[Accelerator] seed={self.seed} preset={self._preset} "
                  f"detectors={self._detector_count} pulse={self._pulse_speed:.1f}x "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Accelerator] configuration error: {exc}")

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
        self._halls = []
        self._stars = []
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
        self._rx = self._layout["rwidth"] * width * 0.5 * (self._ring_radius / 0.7)
        self._rx = min(self._rx, width * 0.48)
        self._ry = self._rx * 0.36
        self._build_halls()
        self._build_stars()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_halls(self):
        rng = random.Random(self.seed ^ 0xACE1)
        halls = []
        for index in range(self._detector_count):
            halls.append({
                "angle": TAU * index / self._detector_count,
                "size": rng.uniform(0.8, 1.15),
                "segments": rng.choice((6, 8, 8)),
            })
        self._halls = halls

    def _build_stars(self):
        rng = random.Random(self.seed ^ 0x57A2)
        width, height = self._screen_size
        self._stars = [
            (rng.uniform(0, width), rng.uniform(0, height), rng.randint(16, 46))
            for _ in range(QUALITY["high"]["stars"])
        ]

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = y / max(1, height - 1)
            base = _mix(palette["bg_top"], palette["bg_bottom"], t ** 1.2)
            band = math.exp(-(((t - 0.5) / 0.55) ** 2))
            color = _mix(base, palette["haze"], band * 0.16)
            pygame.draw.line(surface, color, (0, y), (width, y))
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

    def _beam_energy(self) -> float:
        base = 1.1 + 0.25 * math.sin(self._time * 0.07)
        return base

    def _telemetry(self):
        palette = self._palette
        lines = [(f"BEAM {self._beam_energy():.1f} TEV", palette["hud"], 220),
                 (f"HALLS {self._detector_count:02d}", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"LAP {LAP_SECONDS / self._pulse_speed:.0f} S",
                          palette["hud_dim"], 175))
            lines.append((f"ORBIT {self._camera_orbit:.1f}°",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        lit = self._lit_hall()
        if lit is not None:
            return f"HALL {lit:02d} · PULSE PASSING", True
        return "BEAM NOMINAL · RING QUIET", False

    def _lit_hall(self):
        """The hall the pulse is inside, if any."""
        best = None
        best_delta = 1e9
        for index, hall in enumerate(self._halls):
            delta = abs(_angle_delta(self._pulse_angle, hall["angle"]))
            if delta < best_delta:
                best_delta = delta
                best = index
        return best if best_delta < 0.16 else None

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

    def _precession(self) -> float:
        """The ring's slow turn, and the camera's 2° orbit, as one small tilt."""
        wobble = math.sin(TAU * self._time / 300.0) * 0.04
        orbit = math.sin(TAU * self._time / 240.0) * math.radians(self._camera_orbit)
        return wobble + orbit

    def _point(self, angle):
        """A point on the ring's ellipse, with the precession applied."""
        ca, sa = math.cos(angle), math.sin(angle)
        rx, ry = self._rx, self._ry
        x, y = ca * rx, sa * ry
        ct, st = math.cos(self._tilt), math.sin(self._tilt)
        return (self._centre[0] + x * ct - y * st,
                self._centre[1] + x * st + y * ct,
                sa)                              # depth: 1 = near, -1 = far

    def _draw_ring(self, screen, quality):
        palette = self._palette
        segments = quality["segments"]
        previous = None
        for step in range(segments + 1):
            angle = TAU * step / segments
            point = self._point(angle)
            if previous is not None:
                near = 0.45 + 0.55 * (0.5 + 0.5 * point[2])
                colour = _mix(palette["guide"], palette["structure"], 0.3 + 0.7 * near)
                pygame.draw.line(screen, colour, previous[:2], point[:2],
                                 2 if near > 0.70 else 1)
            previous = point

    def _draw_moon(self, screen, quality):
        palette = self._palette
        cx, cy = self._centre
        radius = self._rx * 0.24
        if radius < 4:
            return
        spin = TAU * self._time / 240.0
        # the night side, filled so the graticule reads against it
        pygame.draw.circle(screen, palette["moon_dark"], (int(cx), int(cy)), int(radius))
        # the lit limb: brighter on one side, fading to the terminator
        lit = []
        for step in range(25):
            angle = -1.35 + 2.70 * step / 24.0
            lit.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
        pygame.draw.lines(screen, palette["hero"], False, lit, 2)
        # the graticule, turning with the moon
        lines = quality["moon"]
        for k in range(1, 4):
            ry = radius * (k / 4.0)
            rect = pygame.Rect(cx - radius * 0.98, cy - ry, radius * 1.96, ry * 2)
            pygame.draw.ellipse(screen, _scale(palette["structure"], 0.55), rect, 1)
        for k in range(lines):
            lon = spin + TAU * k / lines
            rx = radius * 0.98 * abs(math.cos(lon))
            if rx < 1.5:
                continue
            rect = pygame.Rect(cx - rx, cy - radius * 0.98, rx * 2, radius * 1.96)
            pygame.draw.ellipse(screen, _scale(palette["structure"], 0.5), rect, 1)
        # the terminator
        pygame.draw.arc(screen, _scale(palette["guide"], 0.8),
                        pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2),
                        math.pi * 0.55, math.pi * 1.45, 1)

    def _draw_halls(self, screen, quality):
        palette = self._palette
        lit_index = self._lit_hall()
        for index, hall in enumerate(self._halls):
            x, y, depth = self._point(hall["angle"])
            near = 0.5 + 0.5 * depth
            size = 9.0 * hall["size"] * (0.6 + 0.7 * near)
            if size < 1.5:
                continue
            box = pygame.Rect(int(x - size), int(y - size * 0.7),
                              int(size * 2), int(size * 1.4))
            colour = _mix(palette["far"], palette["structure"], 0.4 + 0.5 * near)
            pygame.draw.rect(screen, colour, box, 1)
            # the ring glyph: it fills from the inside as the pulse passes
            segments = hall["segments"]
            filled = 0
            if lit_index == index:
                delta = abs(_angle_delta(self._pulse_angle, hall["angle"]))
                filled = int(segments * _clamp(1.0 - delta / 0.16, 0.0, 1.0))
            glyph_r = size * 0.58
            for k in range(segments):
                a0 = TAU * k / segments - math.pi / 2
                a1 = TAU * (k + 1) / segments - math.pi / 2
                hot = k < filled
                gcol = palette["pulse"] if hot else _scale(palette["guide"], 0.75)
                pygame.draw.line(screen, gcol,
                                 (x + math.cos(a0) * glyph_r, y + math.sin(a0) * glyph_r),
                                 (x + math.cos(a1) * glyph_r, y + math.sin(a1) * glyph_r),
                                 2 if hot else 1)

    def _draw_pulse(self, screen, quality):
        palette = self._palette
        head = self._pulse_angle
        # a short bright segment with a fading trail behind it
        for k in range(quality["trail"], 0, -1):
            angle = head - k * 0.038
            a = self._point(angle)
            b = self._point(angle - 0.038)
            level = 1.0 - k / (quality["trail"] + 1.0)
            colour = _mix(palette["accent"], palette["pulse"], level)
            pygame.draw.line(screen, _scale(colour, 0.25 + 0.75 * level),
                             a[:2], b[:2], 2 if level > 0.7 else 1)
        a = self._point(head)
        b = self._point(head + 0.030)
        pygame.draw.line(screen, palette["pulse"], a[:2], b[:2], 3)
        pygame.draw.circle(screen, palette["pulse"], (int(a[0]), int(a[1])), 2)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        head = self._point(self._pulse_angle)
        pygame.draw.circle(self._bloom,
                           _scale(palette["pulse"], 0.55 * self._glow_strength),
                           (int(head[0] * sx), int(head[1] * sy)), 2)
        lit = self._lit_hall()
        if lit is not None:
            hall = self._halls[lit]
            p = self._point(hall["angle"])
            pygame.draw.circle(self._bloom,
                               _scale(palette["glow"], 0.35 * self._glow_strength),
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
        self._tilt = self._precession()
        self._pulse_angle = (TAU * self._time / (LAP_SECONDS / self._pulse_speed)) % TAU
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_moon(screen, quality)
        self._draw_ring(screen, quality)
        self._draw_halls(screen, quality)
        self._draw_pulse(screen, quality)
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
                print(f"[Accelerator] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("ACCELERATOR RING // CONFIGURATION REFUSED", True,
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
            "detectors": len(self._halls),
            "ring": (self._rx, self._ry),
            "centre": self._centre,
            "pulse_angle": self._pulse_angle,
            "lit_hall": self._lit_hall(),
            "ring_radius": self._ring_radius,
            "pulse_speed": self._pulse_speed,
            "lap_seconds": LAP_SECONDS / self._pulse_speed,
            "camera_orbit": self._camera_orbit,
            "tilt": self._tilt,
            "beam_energy": self._beam_energy(),
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
