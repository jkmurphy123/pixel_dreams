"""Solar Observatory Ring — an instrument ring, close in, around a star.

Slow Wireframe §4.5.  A bright star fills the frame with a faint grid turning
under it; a thin ring of scientific satellites rides just above the surface,
each a small cross with a sunshield; coronal loops arc off the limb and dissolve,
and the ring's shadow draws a chord across the disc.  The camera rides the ring,
so the star drifts slowly across the frame and the near arc of the ring sweeps
past in the foreground.

The drawing is all line.  The star's disc, grid and limb are cached; the ring is
a perspective ellipse; the loops are quadratic curves sampled per frame.  Depth
is carried by size, brightness and draw order, plus one half-resolution additive
bloom on the limb and the loops (§2.8).

Camera behaviour (§2.3): orbit / track.  The card's camera rides the ring over
240 s at 2 px/s, which here is a slow drift of the star's anchor plus a
foreground parallax on the ring's near arc.

Determinism (§2.9): the satellites, the loops and the signature schedule all come
from `seed`; everything else is a function of accumulated elapsed time.  A pinned
seed reproduces a still exactly.

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

#: Loops, satellites and bloom, from §2.8.
QUALITY = {
    "low": {"loops": 3, "loop_points": 8, "glow_div": 8, "ring_points": 40},
    "medium": {"loops": 5, "loop_points": 12, "glow_div": 5, "ring_points": 56},
    "high": {"loops": 8, "loop_points": 16, "glow_div": 4, "ring_points": 72},
}

#: Where the star sits and how big it is, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.560, 0.470), "star": 0.330, "title_px": 21},
    "landscape": {"anchor": (0.560, 0.470), "star": 0.300, "title_px": 30},
    "portrait": {"anchor": (0.500, 0.430), "star": 0.310, "title_px": 34},
    "square": {"anchor": (0.530, 0.450), "star": 0.300, "title_px": 26},
}

PALETTES = {
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (30, 16, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "star": (255, 214, 160), "star_core": (255, 250, 238),
        "shade": (40, 22, 8),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "ice": {
        "bg_top": (3, 7, 12), "bg_bottom": (0, 2, 6), "haze": (8, 22, 34),
        "structure": (77, 127, 150), "hero": (232, 251, 255),
        "accent": (155, 232, 255), "glow": (212, 248, 255),
        "star": (236, 248, 255), "star_core": (255, 255, 255),
        "shade": (10, 20, 30),
        "hud": (232, 251, 255), "hud_dim": (110, 152, 172), "hud_faint": (40, 66, 84),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (18, 18, 18),
        "structure": (86, 86, 86), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "star": (250, 250, 250), "star_core": (255, 255, 255),
        "shade": (24, 24, 24),
        "hud": (242, 242, 242), "hud_dim": (140, 140, 140), "hud_faint": (62, 62, 62),
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


def _radial(size: int, color, peak: int, power: float = 2.4) -> pygame.Surface:
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


def _bezier(p0, p1, p2, t):
    u = 1.0 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


class SolarObservatoryRingMode:
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
        self._satellite_count = 12
        self._ring_radius = 0.6
        self._orbit_seconds = 240.0
        self._loops_on = True
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "SOLAR OBSERVATORY RING"
        self._subtitle = "INSTRUMENT RING · CLOSE ORBIT"

        self._time = 0.0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._star = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}

        self._satellites = []
        self._loops = []
        self._events = []
        self._event_span = 0.0
        self._event = None
        self._star_xy = (0.0, 0.0)
        self._star_r = 100.0
        self._ring_r = (140.0, 60.0)
        self._rows = []
        self._shadow_layer = None
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

        self._satellite_count = self._integer(cfg, "satellite_count", 12, 6, 18)
        self._ring_radius = self._number(cfg, "ring_radius", 0.6, 0.15, 2.0)
        self._orbit_seconds = self._number(cfg, "orbit_seconds", 240.0, 60.0, 900.0)
        self._loops_on = self._bool(cfg, "loops", True)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "SOLAR OBSERVATORY RING", 30) \
            or "SOLAR OBSERVATORY RING"
        self._subtitle = self._text(cfg, "subtitle", "INSTRUMENT RING · CLOSE ORBIT", 44)

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
            print(f"[SolarRing] seed={self.seed} preset={self._preset} "
                  f"satellites={self._satellite_count} ring={self._ring_radius:.2f} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[SolarRing] configuration error: {exc}")

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
        self._star = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}
        self._satellites = []
        self._loops = []
        self._events = []
        self._event = None
        self._rows = []
        self._shadow_layer = None
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
        self._star_xy = (self._layout["anchor"][0] * width,
                         self._layout["anchor"][1] * height)
        self._star_r = self._layout["star"] * min(width, height)
        ring_x = self._star_r * (1.0 + self._ring_radius) * 1.24
        self._ring_r = (ring_x, ring_x * 0.40)
        self._build_ring()
        self._build_loops()
        self._build_background()
        self._build_star()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_ring(self):
        """Satellites at equal angles, with a small formation drift each."""
        rng = random.Random(self.seed ^ 0x51A7)
        satellites = []
        for index in range(self._satellite_count):
            angle = TAU * index / self._satellite_count
            satellites.append({
                "angle": angle,
                "drift": rng.uniform(-0.010, 0.010),
                "phase": rng.uniform(0.0, TAU),
                "size": rng.uniform(0.85, 1.20),
                "tilt": rng.uniform(-0.20, 0.20),
            })
        self._satellites = satellites

    def _build_loops(self):
        """Sparse coronal arcs: footpoints on the limb, an apex above it."""
        rng = random.Random(self.seed ^ 0x70BE)
        loops = []
        count = QUALITY["high"]["loops"]
        for index in range(count):
            a = rng.uniform(0.0, TAU)
            b = a + rng.uniform(0.35, 0.95)
            loops.append({
                "a": a, "b": b,
                "height": rng.uniform(0.20, 0.55),
                "phase": rng.uniform(0.0, TAU),
                "period": rng.uniform(16.0, 26.0),
                "width": rng.uniform(0.9, 1.6),
            })
        self._loops = loops

        # The signature: a loop reaches the ring, passes between two satellites,
        # and dissolves — every ~44 s for ~9 s.
        self._events = []
        self._event_span = 0.0
        if self._satellites:
            gap = 44.0
            span = gap * 6.0
            for k in range(6):
                start = k * gap + rng.uniform(-0.20, 0.20) * gap
                index = rng.randrange(len(self._satellites))
                self._events.append((start, rng.uniform(7.5, 10.5), index))
            self._event_span = span

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.25
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - 0.47) / 0.55) ** 2)
            color = _mix(base, palette["haze"], band * 0.22)
            pygame.draw.line(surface, color, (0, y), (width, y))
        rng = random.Random(self.seed ^ 0x5EED)
        for _ in range(max(40, int(width * height / 14000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(20, 46) / 255.0))
        self._background = surface

    def _build_star(self):
        """
        The star, cached: a soft halo, the disc, the core, the bright limb (the
        scene's hero edge) and a faint grid.  The grid turns per frame by
        re-projecting a few arcs, so only the disc and the halo are baked.
        """
        palette = self._palette
        radius = int(self._star_r)
        size = max(24, int(radius * 4.6))
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)
        surface.blit(_radial(size, palette["glow"], peak=62, power=3.0), (0, 0))
        corona = _radial(int(radius * 2.1), palette["star"], peak=58, power=2.4)
        surface.blit(corona, (centre[0] - radius * 1.05, centre[1] - radius * 1.05))
        pygame.draw.circle(surface, palette["star"], centre, int(radius * 0.90))
        pygame.draw.circle(surface, palette["star_core"], centre, int(radius * 0.42))
        pygame.draw.circle(surface, _rgba(palette["hero"], 238), centre, int(radius), 2)
        pygame.draw.circle(surface, _rgba(palette["glow"], 120), centre,
                           int(radius * 1.05), 1)
        self._star = surface.convert_alpha()

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
            top_h = max(46, int(height * 0.13))
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

    def _telemetry(self):
        palette = self._palette
        lines = [(f"SATELLITES {self._satellite_count:02d}", palette["hud"], 220),
                 (f"RING {self._ring_radius:.2f} R", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            flux = 7.4 + 0.3 * math.sin(self._time * 0.06)
            lines.append((f"FLUX {flux:.1f}e9", palette["hud_dim"], 175))
            lines.append((f"ORBIT {self._orbit_seconds:.0f} S", palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._event is not None:
            return "CORONAL LOOP · RING PASS", True
        return "INSTRUMENTS NOMINAL · FLUX STEADY", False

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

    def _star_offset(self):
        """The camera rides the ring: the star drifts across the frame, slowly."""
        phase = TAU * self._time / self._orbit_seconds
        return (math.sin(phase) * self._star_r * 0.34,
                math.sin(phase + 0.8) * self._star_r * 0.16)

    def _event_state(self):
        if not self._events or self._event_span <= 0.0 or not self._loops_on:
            return None
        local = self._time % self._event_span
        for start, duration, index in self._events:
            if start <= local < start + duration:
                p = (local - start) / duration
                return {"progress": p, "severity": math.sin(math.pi * p) ** 0.75,
                        "satellite": index}
        return None

    def _ring_point(self, angle, cx, cy):
        return (cx + math.cos(angle) * self._ring_r[0],
                cy + math.sin(angle) * self._ring_r[1],
                math.sin(angle))                 # depth: 1 = near, -1 = far

    def _draw_ring(self, screen, cx, cy, quality, front=True):
        palette = self._palette
        points = quality["ring_points"]
        previous = None
        for step in range(points + 1):
            angle = TAU * step / points
            px, py, depth = self._ring_point(angle, cx, cy)
            if previous is not None and (depth >= 0.0) == front:
                near = 0.55 + 0.45 * ((depth + previous[2]) * 0.5)
                color = _mix(palette["guide"], palette["structure"], near)
                width = 3 if near > 0.92 else (2 if near > 0.70 else 1)
                pygame.draw.line(screen, color, previous[:2], (px, py), width)
            previous = (px, py, depth)

    def _draw_satellites(self, screen, cx, cy, quality, front=True):
        palette = self._palette
        rows = []
        for index, satellite in enumerate(self._satellites):
            angle = (satellite["angle"] + satellite["drift"] * math.sin(
                TAU * self._time / 60.0 + satellite["phase"]))
            px, py, depth = self._ring_point(angle, cx, cy)
            near = 0.5 + 0.5 * depth
            size = self._star_r * 0.090 * satellite["size"] * (0.55 + 0.75 * near)
            rows.append((depth, px, py, size, near, index))
        rows.sort(key=lambda row: row[0])
        for depth, px, py, size, near, index in rows:
            if (depth >= 0.0) != front:
                continue
            color = _mix(palette["far"], palette["hero"], 0.30 + 0.55 * near)
            # a small cross with a sunshield: the shield is the bright line
            pygame.draw.line(screen, color, (px - size, py), (px + size, py), 1)
            pygame.draw.line(screen, color, (px, py - size * 0.8), (px, py + size * 0.8), 1)
            shield = [(px - size * 0.5, py - size * 1.25), (px + size * 0.5, py - size * 1.25)]
            pygame.draw.line(screen, _mix(color, palette["hero"], 0.55),
                             shield[0], shield[1], 2 if near > 0.7 else 1)
            if near > 0.55:
                pygame.draw.circle(screen, palette["glow"], (int(px + size * 0.3),
                                                             int(py - size * 0.3)),
                                   max(1, int(size * 0.22)))
        self._rows = rows

    def _draw_shadow(self, screen, cx, cy):
        """
        The ring's shadow: a faint dark chord crossing the star's disc.
        """
        palette = self._palette
        phase = TAU * self._time / 60.0
        offset = math.sin(phase) * self._star_r * 0.95
        angle = 0.42 + 0.10 * math.sin(phase * 0.5)
        ca, sa = math.cos(angle), math.sin(angle)
        # a chord at `offset` from the centre, perpendicular to (ca, sa)
        half = math.sqrt(max(0.0, self._star_r ** 2 - offset ** 2)) * 0.96
        nx, ny = ca, sa
        cx0 = cx + nx * offset - ny * half
        cy0 = cy + ny * offset + nx * half
        cx1 = cx + nx * offset + ny * half
        cy1 = cy + ny * offset - nx * half
        size = int(self._star_r * 2.2)
        layer = self._shadow_layer
        if layer is None or layer.get_width() < size:
            self._shadow_layer = layer = pygame.Surface((size, size), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        ox = cx - size * 0.5
        oy = cy - size * 0.5
        pygame.draw.line(layer, _rgba(palette["shade"], 96),
                         (cx0 - ox, cy0 - oy), (cx1 - ox, cy1 - oy), 5)
        pygame.draw.line(layer, _rgba(palette["shade"], 150),
                         (cx0 - ox, cy0 - oy), (cx1 - ox, cy1 - oy), 2)
        screen.blit(layer, (ox, oy))

    def _draw_grid(self, screen, cx, cy):
        """
        The star's faint grid, turning under the ring: a globe grid seen a little
        from above (the card's sphere, not a set of concentric rings).
        """
        palette = self._palette
        spin = TAU * self._time / 120.0
        tilt = math.radians(22.0)
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        radius = self._star_r * 0.965
        color = _scale(palette["hero"], 0.20)

        def project(lon, lat):
            cos_lat = math.cos(lat)
            x = cos_lat * math.cos(lon + spin)
            y = math.sin(lat)
            z = cos_lat * math.sin(lon + spin)
            y2 = y * cos_t - z * sin_t
            z2 = y * sin_t + z * cos_t
            return (cx + radius * x, cy - radius * y2, z2)

        for k in range(1, 5):
            lat = -0.9 + 1.8 * k / 5.0
            previous = None
            for step in range(29):
                lon = TAU * step / 28
                px, py, z = project(lon, lat)
                if previous is not None and (z > 0.0 or previous[2] > 0.0):
                    pygame.draw.line(screen, color, previous[:2], (px, py), 1)
                previous = (px, py, z)
        for k in range(5):
            lon = TAU * k / 5.0
            previous = None
            for step in range(17):
                lat = -1.35 + 2.7 * step / 16.0
                px, py, z = project(lon, lat)
                if previous is not None and (z > 0.0 or previous[2] > 0.0):
                    pygame.draw.line(screen, color, previous[:2], (px, py), 1)
                previous = (px, py, z)

    def _draw_loops(self, screen, cx, cy, quality):
        palette = self._palette
        limit = quality["loops"] if self._loops_on else 0
        steps = quality["loop_points"]
        event = self._event
        for index, loop in enumerate(self._loops[:limit]):
            cycle = (self._time / loop["period"] + loop["phase"] / TAU) % 1.0
            # grow over the first third, hold, fade over the last
            if cycle < 0.30:
                grow = cycle / 0.30
            elif cycle > 0.75:
                grow = max(0.0, (1.0 - cycle) / 0.25)
            else:
                grow = 1.0
            if grow <= 0.02:
                continue
            p0 = (cx + math.cos(loop["a"]) * self._star_r * 0.97,
                  cy + math.sin(loop["a"]) * self._star_r * 0.97)
            p2 = (cx + math.cos(loop["b"]) * self._star_r * 0.97,
                  cy + math.sin(loop["b"]) * self._star_r * 0.97)
            apex = ((p0[0] + p2[0]) * 0.5, (p0[1] + p2[1]) * 0.5)
            out = (apex[0] - cx, apex[1] - cy)
            length = math.hypot(*out) or 1.0
            height = self._star_r * (0.20 + 0.38 * loop["height"]) * grow
            p1 = (apex[0] + out[0] / length * height * 1.10,
                  apex[1] + out[1] / length * height * 1.10 - height * 0.40)
            points = [_bezier(p0, p1, p2, k / (steps - 1)) for k in range(steps)]
            # the loop is brightest at its apex and fades at the feet
            for k in range(len(points) - 1):
                t = k / max(1, len(points) - 2)
                fade = math.sin(math.pi * t) ** 0.7
                color = _mix(palette["accent"], palette["glow"], 0.25 + 0.55 * fade)
                pygame.draw.line(screen, color, points[k], points[k + 1],
                                 2 if fade > 0.8 else 1)
        if event is not None and self._satellites and self._loops_on:
            # the signature: one loop reaches out to the ring, between two
            # satellites, and dissolves
            target = self._satellites[event["satellite"] % len(self._satellites)]
            px, py, _depth = self._ring_point(target["angle"], cx, cy)
            foot = (cx + math.cos(target["angle"] + 0.5) * self._star_r * 0.97,
                    cy + math.sin(target["angle"] + 0.5) * self._star_r * 0.97)
            level = event["severity"]
            p1 = ((foot[0] + px) * 0.5 + self._star_r * 0.25,
                  (foot[1] + py) * 0.5 - self._star_r * 0.55)
            points = [_bezier(foot, p1, (px, py), k / (steps - 1)) for k in range(steps)]
            for k in range(len(points) - 1):
                t = k / max(1, len(points) - 2)
                fade = math.sin(math.pi * t) ** 0.8
                color = _mix(palette["glow"], palette["hero"], 0.35 + 0.5 * fade)
                pygame.draw.line(screen, color, points[k], points[k + 1],
                                 (2 if fade > 0.7 else 1))
            pygame.draw.circle(screen, palette["glow"], (int(px), int(py)),
                               max(1, int(self._star_r * 0.02 * level)))

    def _bloom_pass(self, screen, cx, cy, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        pygame.draw.circle(self._bloom, _scale(palette["glow"], 0.35 * self._glow_strength),
                           (int(cx * sx), int(cy * sy)),
                           max(2, int(self._star_r * 1.02 * sx)), 2)
        pygame.draw.circle(self._bloom, _scale(palette["glow"], 0.55 * self._glow_strength),
                           (int(cx * sx), int(cy * sy)),
                           max(2, int(self._star_r * 0.98 * sx)), 1)
        if self._event is not None and self._satellites:
            target = self._satellites[self._event["satellite"] % len(self._satellites)]
            px, py, _depth = self._ring_point(target["angle"], cx, cy)
            pygame.draw.circle(self._bloom, _scale(palette["hero"], 0.45 * self._glow_strength),
                               (int(px * sx), int(py * sy)), 2)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        now = self._time
        quality = QUALITY[self._quality]
        self._event = self._event_state()
        dx, dy = self._star_offset()
        cx, cy = self._star_xy[0] + dx, self._star_xy[1] + dy
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, cx, cy, quality)
        self._draw_ring(screen, cx, cy, quality, front=False)
        self._draw_satellites(screen, cx, cy, quality, front=False)
        if self._star is not None:
            rect = self._star.get_rect(center=(int(cx), int(cy)))
            screen.blit(self._star, rect)
        self._draw_grid(screen, cx, cy)
        self._draw_shadow(screen, cx, cy)
        self._draw_loops(screen, cx, cy, quality)
        self._draw_ring(screen, cx, cy, quality, front=True)
        self._draw_satellites(screen, cx, cy, quality, front=True)
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
                print(f"[SolarRing] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("SOLAR RING // CONFIGURATION REFUSED", True,
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
            "satellites": len(self._satellites),
            "satellites_drawn": len(self._rows),
            "loops": QUALITY[self._quality]["loops"] if self._loops_on else 0,
            "loops_on": self._loops_on,
            "event": dict(self._event) if self._event else None,
            "ring_radius": self._ring_radius,
            "ring": self._ring_r,
            "star": (self._star_xy, self._star_r),
            "orbit_seconds": self._orbit_seconds,
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
