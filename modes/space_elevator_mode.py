"""Space Elevator — a climber car going up a tether, very slowly.

Slow Wireframe §4.6.  A tether runs from a planet's surface to a counterweight
in orbit; a climber car ascends it while the planet's limb falls away below, the
distance ticks scroll past and the station ring grows from a dot to a structure.
The camera tracks the car, so the scale is told by what passes rather than by a
number.  At the top of the cycle the car passes through the ring, the camera
settles above it, the tether's shadow falls across the planet, and the climb
begins again.

The drawing is all line.  The planet's limb, clouds and the tether are drawn
per frame from a handful of parameters; the car and the station are small
cached shapes redrawn at their current scale.  Depth is carried by size, the
converging tether and one half-resolution additive bloom on the running lights
(§2.8).

Camera behaviour (§2.3): track.  The car holds its place in the frame at the
card's 6–12 px/s climb and the world scrolls; the camera rises to meet the
station ring for the pass.  The anchor is recomputed per aspect.

Determinism (§2.9): the ticks, beacons, clouds and the cycle phase all come
from `seed` and elapsed time.  A pinned seed reproduces a still exactly.

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

#: Ticks, clouds, beacons and bloom per tier (§2.8).
QUALITY = {
    "low": {"ticks": 18, "clouds": 4, "beacons": 3, "glow_div": 8, "ring_points": 28},
    "medium": {"ticks": 30, "clouds": 6, "beacons": 5, "glow_div": 5, "ring_points": 36},
    "high": {"ticks": 44, "clouds": 9, "beacons": 7, "glow_div": 4, "ring_points": 48},
}

#: Where the tether sits and how big the car and the ring read.
PRESETS = {
    "ultrawide": {"tether_x": 0.470, "car_y": 0.520, "car_px": 0.075, "title_px": 21,
                  "limb": 0.800},
    "landscape": {"tether_x": 0.480, "car_y": 0.510, "car_px": 0.066, "title_px": 30,
                  "limb": 0.800},
    "portrait": {"tether_x": 0.500, "car_y": 0.520, "car_px": 0.070, "title_px": 34,
                 "limb": 0.900},
    "square": {"tether_x": 0.480, "car_y": 0.510, "car_px": 0.070, "title_px": 26,
               "limb": 0.810},
}

PALETTES = {
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "planet": (16, 34, 54), "planet_low": (5, 10, 18), "cloud": (70, 130, 170),
        "car": (216, 242, 255), "warm": (255, 196, 118),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "ice": {
        "bg_top": (3, 7, 12), "bg_bottom": (0, 2, 6), "haze": (8, 22, 34),
        "structure": (77, 127, 150), "hero": (232, 251, 255),
        "accent": (155, 232, 255), "glow": (212, 248, 255),
        "planet": (20, 40, 54), "planet_low": (6, 12, 18), "cloud": (100, 150, 170),
        "car": (232, 251, 255), "warm": (255, 210, 150),
        "hud": (232, 251, 255), "hud_dim": (110, 152, 172), "hud_faint": (40, 66, 84),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "planet": (34, 20, 8), "planet_low": (10, 6, 2), "cloud": (170, 120, 60),
        "car": (255, 232, 199), "warm": (255, 214, 160),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

#: One climb: a long ascent, a pass through the ring, a settle above it.
CYCLE_SECONDS = 104.0
PASS_AT = 0.80
SETTLE_AT = 0.88


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


def _radial(size: int, color, peak: int, power: float = 2.4) -> pygame.Surface:
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


class SpaceElevatorMode:
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
        self._car_speed = 10.0
        self._altitude = 18400
        self._show_planet = True
        self._sway = 0.2
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "SPACE ELEVATOR"
        self._subtitle = "CAR 07 · ASCENT"

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

        self._ticks = []
        self._clouds = []
        self._beacons = []
        self._cycle = None
        self._car_xy = (0.0, 0.0)
        self._ring = (0.0, 0.0)
        self._ring_y = 0.0
        self._limb_y = 0.0
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

        self._car_speed = self._number(cfg, "car_speed", 10.0, 1.0, 40.0)
        self._altitude = self._integer(cfg, "altitude", 18400, 100, 40000)
        self._show_planet = self._bool(cfg, "show_planet", True)
        self._sway = self._number(cfg, "tether_sway", 0.2, 0.0, 5.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "SPACE ELEVATOR", 30) or "SPACE ELEVATOR"
        self._subtitle = self._text(cfg, "subtitle", "CAR 07 · ASCENT", 44)

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
            print(f"[SpaceElevator] seed={self.seed} preset={self._preset} "
                  f"speed={self._car_speed:.0f}px/s alt={self._altitude}km "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[SpaceElevator] configuration error: {exc}")

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
        self._ticks = []
        self._clouds = []
        self._beacons = []
        self._cycle = None
        self._rows = []
        self._shadow_layer = None
        self._fade_layer = None
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
        self._build_marks()
        self._build_background()
        self._shadow_layer = None
        self._fade_layer = pygame.Surface((width, height))
        self._fade_layer.fill((0, 0, 0))
        self._limb_y = self._layout["limb"] * height
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_marks(self):
        """Distance ticks up the tether, the beacons and the cloud strokes."""
        rng = random.Random(self.seed ^ 0x7A11)
        ticks = []
        for index in range(QUALITY["high"]["ticks"]):
            ticks.append({
                "offset": index * 78.0 + rng.uniform(-6.0, 6.0),
                "long": index % 5 == 0,
                "label": 40 * (index + 1),
            })
        self._ticks = ticks
        self._beacons = [{"offset": rng.uniform(0.0, 400.0),
                          "phase": rng.uniform(0.0, TAU)} for _ in
                         range(QUALITY["high"]["beacons"])]
        self._clouds = [{"x": rng.uniform(-0.2, 1.2), "width": rng.uniform(0.05, 0.22),
                         "speed": rng.uniform(0.4, 1.6), "alpha": rng.randint(20, 46),
                         "y": rng.uniform(-0.012, 0.012)} for _ in
                        range(QUALITY["high"]["clouds"])]

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.2
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - 0.78) / 0.40) ** 2)
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
                k = int(52 + 203 * t)
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

    def _altitude_km(self) -> int:
        if self._cycle is None:
            return self._altitude
        return int(self._altitude + self._cycle["climb_km"])

    def _telemetry(self):
        palette = self._palette
        lines = [(f"ALT {self._altitude_km():,} KM", palette["hud"], 220),
                 (f"CLIMB {self._car_speed:.0f} PX/S", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"SWAY {self._sway:.1f}°", palette["hud_dim"], 175))
            lines.append(("CAR 07 · TETHER 1", palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._cycle is None:
            return "ASCENT NOMINAL", False
        phase = self._cycle["phase"]
        if phase == "pass":
            return "STATION PASS · RING", True
        if phase == "settle":
            return "AT STATION · SHADOW BELOW", False
        return f"CLIMBING · {self._altitude_km():,} KM", False

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

    # ---------------------------------------------------------------- animation state

    def _cycle_state(self):
        """
        One climb.  `scroll` is how far the world has moved down the frame,
        `ring_scale` how large the station reads, `fade` the soft reset.
        """
        width, height = self._screen_size
        p = (self._time / CYCLE_SECONDS) % 1.0
        if p < PASS_AT:
            phase = "climb"
        elif p < SETTLE_AT:
            phase = "pass"
        else:
            phase = "settle"
        # the world scrolls at the car's speed; the climb is compressed for the
        # loop, so the ticks pass at a calm pace rather than 10 px a second
        scroll = (self._time % CYCLE_SECONDS) * (self._car_speed * 0.55)
        climb_km = p * 1240.0
        if phase == "climb":
            ring_scale = _lerp(0.015, 1.0, (p / PASS_AT) ** 2.1)
        elif phase == "pass":
            k = (p - PASS_AT) / (SETTLE_AT - PASS_AT)
            ring_scale = _lerp(1.0, 1.35, math.sin(k * math.pi) * 0.5 + k * 0.5)
        else:
            k = (p - SETTLE_AT) / (1.0 - SETTLE_AT)
            ring_scale = _lerp(1.35, 1.10, k)
        fade = 0.0
        if p > 0.965:
            fade = (p - 0.965) / 0.035
        return {"progress": p, "phase": phase, "scroll": scroll,
                "climb_km": climb_km, "ring_scale": ring_scale, "fade": fade}

    def _tether_x(self, y: float, height: float) -> float:
        """The tether leans a little with the sway, and hums."""
        width, _h = self._screen_size
        base = self._layout["tether_x"] * width
        sway = math.sin(TAU * self._time / 12.0) * math.radians(self._sway) * height * 3.0
        hum = math.sin(TAU * self._time * 7.0) * 0.8 * min(1.0, self._sway / 0.2)
        return base + sway * (y / max(1.0, height)) + hum

    def _draw_tether(self, screen, car_x, car_y, quality):
        palette = self._palette
        width, height = self._screen_size
        # the line: brighter near the car, with a faint far half
        points = []
        for step in range(13):
            y = height * step / 12.0
            points.append((self._tether_x(y, height), y))
        for k in range(len(points) - 1):
            y_mid = (points[k][1] + points[k + 1][1]) * 0.5
            near = 1.0 - _clamp(abs(y_mid - car_y) / (height * 0.75), 0.0, 1.0)
            color = _mix(palette["structure"], palette["hero"], 0.25 + 0.55 * near)
            pygame.draw.line(screen, color, points[k], points[k + 1],
                             3 if near > 0.80 else (2 if near > 0.45 else 1))

        # distance ticks scroll past the car
        for index, tick in enumerate(self._ticks[:quality["ticks"]]):
            offset = (tick["offset"] + self._cycle["scroll"]) % (height * 2.0)
            y = car_y + offset
            if y > height + 10:
                continue
            x = self._tether_x(y, height)
            length = 18 if tick["long"] else 8
            alpha = 210 if tick["long"] else 120
            pygame.draw.line(screen, _scale(palette["structure"], alpha / 255.0),
                             (x + 5, y), (x + 5 + length, y), 1)
            if tick["long"] and y < height * 0.92:
                surface = self._cached_text(f"{tick['label']}", max(7, int(self._metrics["tele_px"] * 0.8)),
                                            palette["hud_faint"], 120)
                rect = surface.get_rect(midleft=(int(x + 20), int(y)))
                screen.blit(surface, rect)

        # the altitude scale: a quiet measurement line beside the tether
        scale_x = self._layout["tether_x"] * width - width * 0.20
        previous = None
        for step in range(17):
            y = height * step / 16.0
            if previous is not None:
                pygame.draw.line(screen, _scale(palette["guide"], 0.55),
                                 (scale_x, previous), (scale_x, y), 1)
            previous = y
        for step in range(5):
            y = height * 0.18 + step * height * 0.16
            pygame.draw.line(screen, _scale(palette["structure"], 0.9),
                             (scale_x - 5, y), (scale_x + 5, y), 1)
            surface = self._cached_text(f"{self._altitude_km() - 40 * (step + 1):,}",
                                        max(7, int(self._metrics["tele_px"] * 0.85)),
                                        palette["hud_faint"], 150)
            rect = surface.get_rect(midright=(int(scale_x - 10), int(y)))
            screen.blit(surface, rect)

        # the beacons: a warm running light every so often
        for beacon in self._beacons[:quality["beacons"]]:
            offset = (beacon["offset"] + self._cycle["scroll"] * 0.8) % (height * 2.0)
            y = car_y + offset
            if y > height + 6:
                continue
            x = self._tether_x(y, height)
            twinkle = 0.5 + 0.5 * math.sin(self._time * 1.3 + beacon["phase"])
            pygame.draw.circle(screen, _mix(palette["warm"], palette["far"], 0.25),
                               (int(x + 8), int(y)), max(1, int(1 + 1.4 * twinkle)))

    def _draw_car(self, screen, cx, cy):
        palette = self._palette
        size = self._layout["car_px"] * min(self._screen_size)
        w, h = size * 0.62, size
        body = pygame.Rect(0, 0, int(w), int(h))
        body.center = (int(cx), int(cy))
        if self._fill in ("xray", "panel"):
            face = pygame.Surface((body.width + 4, body.height + 4), pygame.SRCALPHA)
            pygame.draw.rect(face, _rgba(_scale(palette["car"], 0.7),
                                         34 if self._fill == "xray" else 54), body)
            screen.blit(face, (body.left - 2, body.top - 2))
        pygame.draw.rect(screen, palette["car"], body, 1)
        # the window and the mast
        pygame.draw.line(screen, _scale(palette["car"], 0.85),
                         (body.left + 2, body.top + int(h * 0.32)),
                         (body.right - 2, body.top + int(h * 0.32)), 1)
        pygame.draw.line(screen, _scale(palette["car"], 0.85),
                         (body.centerx, body.top), (body.centerx, body.top - int(h * 0.28)), 1)
        # running light
        pygame.draw.circle(screen, palette["warm"],
                           (body.centerx, body.top - int(h * 0.34)), max(2, int(w * 0.22)))
        self._car_xy = (cx, cy)

    def _draw_ring(self, screen, cx, cy, scale, quality):
        """The station: a perspective ellipse that grows as the car approaches."""
        palette = self._palette
        width, height = self._screen_size
        rx = min(width, height) * 0.42 * scale
        ry = rx * 0.28
        if rx < 3:
            pygame.draw.circle(screen, palette["glow"], (int(cx), int(cy)), 1)
            return
        points = quality["ring_points"]
        previous = None
        for step in range(points + 1):
            angle = TAU * step / points
            px = cx + math.cos(angle) * rx
            py = cy + math.sin(angle) * ry
            if previous is not None:
                near = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(angle))
                color = _mix(palette["guide"], palette["hero"], near)
                width_px = 2 if near > 0.85 else 1
                pygame.draw.line(screen, color, previous, (px, py), width_px)
            previous = (px, py)
        # the ring's structure: four spokes and a hub
        for k in range(4):
            angle = TAU * k / 4 + 0.4
            pygame.draw.line(screen, _scale(palette["structure"], 0.9),
                             (cx + math.cos(angle) * rx * 0.55, cy + math.sin(angle) * ry * 0.55),
                             (cx + math.cos(angle) * rx, cy + math.sin(angle) * ry), 1)
        pygame.draw.circle(screen, palette["car"], (int(cx), int(cy)),
                           max(1, int(rx * 0.04)))
        self._ring = (rx, ry)

    def _draw_planet(self, screen, car_y, quality):
        """The limb falls away below as the car climbs; clouds drift over it."""
        palette = self._palette
        width, height = self._screen_size
        scroll = self._cycle["scroll"]
        base = self._layout["limb"] * height + self._cycle["progress"] * height * 0.10
        if base < height * 0.35:
            return
        self._limb_y = base
        arc = []
        step = 6
        for x in range(0, width + step, step):
            t = (x / max(1.0, width)) * 2.0 - 1.0
            arc.append((x, base + t * t * height * 0.10))
        if len(arc) > 2:
            body = arc + [(width, height), (0, height)]
            pygame.draw.polygon(screen, _mix(palette["planet"], palette["planet_low"], 0.45),
                                body)
            for k in range(len(arc) - 1):
                pygame.draw.line(screen, _mix(palette["hero"], palette["structure"], 0.30),
                                 arc[k], arc[k + 1], 2)
                pygame.draw.line(screen, _scale(palette["glow"], 0.20),
                                 (arc[k][0], arc[k][1] - 3), (arc[k + 1][0], arc[k + 1][1] - 3), 1)
        for cloud in self._clouds[:quality["clouds"]]:
            x = ((cloud["x"] + self._time * 0.02 * cloud["speed"]) % 1.5 - 0.25) * width
            span = cloud["width"] * width
            y = base + cloud["y"] * height + 6
            pygame.draw.line(screen, _rgba(palette["cloud"], cloud["alpha"]),
                             (x, y), (x + span, y), 1)

    def _draw_shadow(self, screen, car_x, car_y):
        """The tether's shadow, once the camera has settled above the station."""
        if self._cycle["phase"] != "settle":
            return
        palette = self._palette
        width, height = self._screen_size
        k = _clamp((self._cycle["progress"] - SETTLE_AT) / (1.0 - SETTLE_AT), 0.0, 1.0)
        base = self._layout["limb"] * height + self._cycle["progress"] * height * 0.10
        if base > height + 20:
            return
        # a dark line cast from the tether onto the limb
        x0 = car_x - width * (0.02 + 0.06 * k)
        x1 = x0 + width * 0.10
        y0 = base - 2
        layer = self._shadow_layer
        if layer is None:
            self._shadow_layer = layer = pygame.Surface((width, 80), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        oy = 0
        pygame.draw.line(layer, _rgba(palette["bg_bottom"], 120),
                         (x0, 30), (x1, 36), 6)
        pygame.draw.line(layer, _rgba(palette["bg_bottom"], 60),
                         (x0 - 8, 32), (x1 + 8, 39), 10)
        screen.blit(layer, (0, int(y0) - 30))

    def _bloom_pass(self, screen, car_x, car_y, ring_scale, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        # the car's running light
        pygame.draw.circle(self._bloom, _scale(palette["warm"], 0.6 * self._glow_strength),
                           (int(car_x * sx), int(car_y * sy)), 2)
        # the station's beacons once it is big enough to see
        if ring_scale > 0.10:
            rx = min(width, height) * 0.42 * ring_scale
            for k in range(4):
                angle = TAU * k / 4 + 0.4
                px = car_x + math.cos(angle) * rx
                py = car_y - height * 0.18 + math.sin(angle) * rx * 0.28
                pygame.draw.circle(self._bloom,
                                   _scale(palette["glow"], 0.35 * self._glow_strength),
                                   (int(px * sx), int(py * sy)), 1)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._cycle = self._cycle_state()
        width, height = self._screen_size
        car_x = self._tether_x(self._layout["car_y"] * height, height)
        car_y = self._layout["car_y"] * height
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, car_x, car_y, self._cycle["ring_scale"], quality)
        if self._show_planet:
            self._draw_planet(screen, car_y, quality)
        self._draw_shadow(screen, car_x, car_y)
        self._draw_tether(screen, car_x, car_y, quality)
        # the station descends to meet the car, then passes beneath it
        p = self._cycle["progress"]
        if p < PASS_AT:
            ring_y = car_y - height * 0.30 * (1.0 - p / PASS_AT)
        else:
            ring_y = car_y + height * 0.45 * (p - PASS_AT) / (1.0 - PASS_AT)
        self._ring_y = ring_y
        self._draw_ring(screen, car_x, ring_y, self._cycle["ring_scale"], quality)
        self._draw_car(screen, car_x, car_y)
        if self._finish is not None:
            screen.blit(self._finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        if self._cycle["fade"] > 0.0 and self._fade_layer is not None:
            # a quiet reset between climbs, never a cut
            self._fade_layer.set_alpha(int(255 * self._cycle["fade"]))
            screen.blit(self._fade_layer, (0, 0))

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
                print(f"[SpaceElevator] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("SPACE ELEVATOR // CONFIGURATION REFUSED", True,
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
            "cycle": dict(self._cycle) if self._cycle else None,
            "altitude": self._altitude,
            "altitude_km": self._altitude_km(),
            "car_speed": self._car_speed,
            "tether_sway": self._sway,
            "show_planet": self._show_planet,
            "car": self._car_xy,
            "ring": self._ring,
            "ring_y": self._ring_y,
            "limb_y": self._limb_y,
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
