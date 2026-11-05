"""Generation Ship — a city in section, inside a hull with no sky.

Slow Wireframe §4.10.  A long generation ship opened in cutaway: deck lines,
module bays — forest, fields, city, water, cryo, cargo, hangar, drive — a
habitat ring turning in its bay, thousands of tiny deck lights and transport
dots running the corridors.  The camera tracks along the hull from stern to bow,
and when it reaches the bow the ship's name resolves in hull lights one letter
at a time, then fades back to structure.

The drawing is all line.  The hull is a long outline with a darker cutaway panel
behind the deck lines (a fill, not a texture); modules are cached glyphs placed
along the decks; the ring is an ellipse with rotating spokes.  Scale is carried
by the repeated modules and the tiny lights, and by one half-resolution additive
bloom on the bow name and the drive (§2.8).

Camera behaviour (§2.3): track.  The card's 1 px/s along the hull, made a loop
over the ship's length so the pass repeats.  The anchor is recomputed per
aspect.

Determinism (§2.9): the modules, lights, transport dots and doors all come from
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

#: Deck detail, lights and bloom per tier (§2.8).
QUALITY = {
    "low": {"lights": 40, "dots": 6, "detail": 0.55, "glow_div": 8},
    "medium": {"lights": 80, "dots": 10, "detail": 0.78, "glow_div": 5},
    "high": {"lights": 130, "dots": 14, "detail": 1.0, "glow_div": 4},
}

#: The hull's height and where the camera looks, per aspect.
PRESETS = {
    "ultrawide": {"height": 0.520, "title_px": 21, "y": 0.500},
    "landscape": {"height": 0.560, "title_px": 30, "y": 0.500},
    "portrait": {"height": 0.420, "title_px": 34, "y": 0.470},
    "square": {"height": 0.540, "title_px": 26, "y": 0.500},
}

PALETTES = {
    "ice": {
        "bg_top": (3, 7, 12), "bg_bottom": (0, 2, 6), "haze": (8, 22, 34),
        "structure": (77, 127, 150), "hero": (232, 251, 255),
        "accent": (155, 232, 255), "glow": (212, 248, 255),
        "cut": (8, 18, 28), "warm": (255, 206, 148), "city": (255, 226, 180),
        "hud": (232, 251, 255), "hud_dim": (110, 152, 172), "hud_faint": (40, 66, 84),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "cut": (14, 8, 4), "warm": (255, 214, 160), "city": (255, 232, 190),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (18, 18, 18),
        "structure": (86, 86, 86), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "cut": (10, 10, 10), "warm": (226, 226, 226), "city": (240, 240, 240),
        "hud": (242, 242, 242), "hud_dim": (140, 140, 140), "hud_faint": (62, 62, 62),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

#: The hull in world units: x from 0 (stern) to 1 (bow).
SHIP_NAME = "ARK 9"
MODULE_KINDS = ("forest", "fields", "city", "water", "cryo", "cargo", "hangar", "drive")
MODULE_LABELS = {
    "forest": "FOREST", "fields": "FIELDS", "city": "CITY", "water": "WATER",
    "cryo": "CRYO", "cargo": "CARGO", "hangar": "HANGAR", "drive": "DRIVE",
}


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


class GenerationShipMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "ice"
        self._palette = PALETTES["ice"]
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._frame_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._hud_mode = "minimal"
        self._fill = "line"
        self._orientation = "auto"
        self._deck_count = 3
        self._camera_speed = 1.0
        self._ring_rotation = 120.0
        self._population_lights = True
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "GENERATION SHIP"
        self._subtitle = "ARK 9 · POP 12,400"

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

        self._modules = []
        self._lights = []
        self._dots = []
        self._doors = []
        self._names = []
        self._scroll = 0.0
        self._hull = (0.0, 0.0, 1.0, 1.0)
        self._name_progress = 0.0
        self._at_bow = False
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

        palette = str(cfg.get("palette", "ice")).lower()
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

        self._deck_count = self._integer(cfg, "deck_count", 3, 2, 5)
        self._camera_speed = self._number(cfg, "camera_speed", 1.0, 0.0, 12.0)
        self._ring_rotation = self._number(cfg, "ring_rotation", 120.0, 20.0, 600.0)
        self._population_lights = self._bool(cfg, "population_lights", True)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "GENERATION SHIP", 30) or "GENERATION SHIP"
        self._subtitle = self._text(cfg, "subtitle", "ARK 9 · POP 12,400", 44)

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
            print(f"[GenerationShip] seed={self.seed} preset={self._preset} "
                  f"decks={self._deck_count} speed={self._camera_speed:.1f}px/s "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[GenerationShip] configuration error: {exc}")

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
        self._modules = []
        self._lights = []
        self._dots = []
        self._doors = []
        self._names = []
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
        self._build_ship()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_ship(self):
        """Modules along the decks, the ring bay, lights, dots, doors and the name."""
        rng = random.Random(self.seed ^ 0x6E5A)
        # nine bays across the hull, each a module; the ring bay is the fourth
        bays = 9
        modules = []
        for index in range(bays):
            kind = MODULE_KINDS[index % len(MODULE_KINDS)]
            if index == 4:
                kind = "hab"
            modules.append({
                "x": (index + 0.5) / bays,
                "width": 0.9 / bays,
                "kind": kind,
                "phase": rng.uniform(0.0, TAU),
            })
        self._modules = modules
        lights = []
        for _ in range(QUALITY["high"]["lights"]):
            lights.append({
                "x": rng.uniform(0.03, 0.97),
                "deck": rng.randrange(self._deck_count),
                "offset": rng.uniform(0.15, 0.85),
                "phase": rng.uniform(0.0, TAU),
                "period": rng.uniform(3.0, 8.0),
            })
        self._lights = lights
        dots = []
        for _ in range(QUALITY["high"]["dots"]):
            dots.append({
                "x": rng.uniform(0.0, 1.0),
                "deck": rng.randrange(self._deck_count),
                "offset": rng.uniform(0.3, 0.7),
                "speed": rng.uniform(0.004, 0.010),
                "direction": 1 if rng.random() < 0.5 else -1,
            })
        self._dots = dots
        self._doors = [{"x": 0.62, "phase": rng.uniform(0.0, TAU)}]
        # the name letters, resolved one at a time when the bow is in view
        self._names = list(SHIP_NAME)

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
        rng = random.Random(self.seed ^ 0x57A2)
        for _ in range(max(40, int(width * height / 16000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(18, 44) / 255.0))
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
            bot_h = max(32, int(height * 0.08))
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

    def _frame_number(self) -> int:
        return 12 + int(self._scroll * 940)

    def _telemetry(self):
        palette = self._palette
        lines = [(f"POP {self._population():,}", palette["hud"], 220),
                 (f"DECKS {self._deck_count:02d}", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"FRAME {self._frame_number():04d}", palette["hud_dim"], 175))
            lines.append((f"TRACK {self._camera_speed:.1f} PX/S",
                          palette["hud_faint"], 150))
        return lines

    def _population(self) -> int:
        return 12400

    def _status_text(self):
        if self._at_bow and self._name_progress > 0.0:
            return "BOW · NAME RESOLVING", True
        return "TRACKING · DECKS NOMINAL", False

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

    def _scroll_state(self):
        """
        The camera's track along the hull: a loop over the ship's length, with a
        readable pause at the bow for the name to resolve.
        """
        lap = 240.0 / max(0.15, self._camera_speed)
        p = (self._time % lap) / lap
        # hold at the bow for the last 18% of the lap, so the name has time
        if p < 0.82:
            scroll = (p / 0.82) * 0.66
        else:
            scroll = 0.66
        return scroll, p

    def _spans(self):
        """The hull on screen: stern, bow, deck height, in pixels."""
        width, height = self._screen_size
        hull_h = self._layout["height"] * height
        top = self._layout["y"] * height - hull_h * 0.5
        return top, hull_h

    def _x(self, x: float) -> float:
        width, _height = self._screen_size
        return (x - self._scroll) * width * 1.06 + width * 0.06

    def _bow_x(self) -> float:
        return self._x(1.0)

    def _draw_hull(self, screen):
        palette = self._palette
        width, height = self._screen_size
        top, hull_h = self._spans()
        stern = self._x(0.0)
        bow = self._bow_x()
        if bow < -20 or stern > width + 20:
            return
        # the cutaway panel: a darker fill behind the decks, never a texture
        body = [(stern, top), (bow, top)]
        # the bow curve
        for step in range(1, 9):
            t = step / 8.0
            body.append((bow + math.sin(t * math.pi * 0.5) * hull_h * 0.10,
                         top + hull_h * t))
        body.append((bow, top + hull_h))
        body.append((stern, top + hull_h))
        pygame.draw.polygon(screen, palette["cut"], body)
        pygame.draw.lines(screen, palette["hero"], True,
                          [(stern, top), (bow, top)] + body[2:], 2)
        # deck lines
        for deck in range(1, self._deck_count):
            y = top + hull_h * deck / self._deck_count
            pygame.draw.line(screen, _mix(palette["structure"], palette["guide"], 0.5),
                             (stern, y), (bow, y), 1)
        # the frame rings along the hull, and the deck labels
        label_font = self._font(max(7, int(hull_h * 0.030)))
        for index in range(1, 12):
            x = self._x(index / 12.0)
            if x < -10 or x > width + 10:
                continue
            pygame.draw.line(screen, _scale(palette["guide"], 0.5),
                             (x, top + 2), (x, top + hull_h - 2), 1)

    def _draw_modules(self, screen):
        palette = self._palette
        width, _height = self._screen_size
        top, hull_h = self._spans()
        deck_h = hull_h / self._deck_count
        label_px = max(7, int(deck_h * 0.16))
        label_font = self._font(label_px)
        for module in self._modules:
            cx = self._x(module["x"])
            span = width * 1.06 * module["width"] * 0.5
            if cx + span < 0 or cx - span > width:
                continue
            kind = module["kind"]
            for deck in range(self._deck_count):
                y0 = top + deck_h * deck + 3
                y1 = top + deck_h * (deck + 1) - 3
                if kind == "hab" and deck == 1:
                    continue
                box = pygame.Rect(int(cx - span), int(y0), int(span * 2), int(y1 - y0))
                if box.width < 3 or box.height < 3:
                    continue
                pygame.draw.rect(screen, _mix(palette["far"], palette["structure"], 0.6),
                                 box, 1)
                self._draw_glyph(screen, kind, box, palette)
                if deck == 0:
                    label = MODULE_LABELS.get(kind, kind.upper())
                    surface = self._cached_text(label, label_px,
                                                _scale(palette["hud_dim"], 0.85), 190)
                    rect = surface.get_rect(midleft=(box.left + 3, box.bottom - label_px))
                    if rect.right < width and rect.left > 0:
                        screen.blit(surface, rect)
            if kind == "hab":
                self._draw_ring(screen, cx, top + deck_h * 1.5, min(span, deck_h * 0.9))

    def _draw_glyph(self, screen, kind, box, palette):
        """Two or three lines per module kind — enough to read at this size."""
        colour = _scale(palette["structure"], 0.9)
        left, right = box.left + 3, box.right - 3
        top, bottom = box.top + 3, box.bottom - 3
        if right <= left or bottom <= top:
            return
        if kind == "forest":
            for k in range(3):
                x = left + (right - left) * (k + 0.5) / 3.0
                pygame.draw.lines(screen, colour, False,
                                  [(x - 3, bottom), (x, top), (x + 3, bottom)], 1)
                pygame.draw.line(screen, colour, (x, bottom), (x, bottom + 2), 1)
        elif kind == "fields":
            step = 5
            for offset in range(0, right - left, step):
                pygame.draw.line(screen, _scale(colour, 0.7),
                                 (left + offset, bottom), (left + offset + 4, top), 1)
        elif kind == "city":
            bars = max(2, (right - left) // 4)
            for k in range(bars):
                x = left + (right - left) * k / bars
                h = (bottom - top) * (0.35 + 0.2 * ((k * 7) % 3))
                pygame.draw.line(screen, colour, (x, bottom), (x, bottom - h), 1)
        elif kind == "water":
            for k in range(2):
                y = top + (bottom - top) * (k + 1) / 3.0
                pygame.draw.lines(screen, colour, False,
                                  [(left, y), ((left + right) // 2, y - 2), (right, y)], 1)
        elif kind == "cryo":
            count = 3
            for k in range(count):
                x = left + (right - left) * (k + 0.5) / count
                pygame.draw.circle(screen, colour, (int(x), (top + bottom) // 2),
                                   max(1, min(3, (bottom - top) // 4)))
        elif kind == "cargo":
            for k in range(2):
                for j in range(2):
                    x = left + (right - left) * (k + 0.5) / 2.0
                    y = top + (bottom - top) * (j + 0.5) / 2.0
                    pygame.draw.rect(screen, colour,
                                     pygame.Rect(int(x - 2), int(y - 2), 4, 4), 1)
        elif kind == "hangar":
            pygame.draw.line(screen, colour, (left, bottom), (right, bottom), 1)
            pygame.draw.lines(screen, colour, False,
                              [(left + 3, bottom), ((left + right) // 2, top + 2),
                               (right - 3, bottom)], 1)
        elif kind == "drive":
            for k in range(3):
                x = left + (right - left) * (k + 1) / 4.0
                pygame.draw.line(screen, colour, (x, top), (x, bottom), 1)
            pygame.draw.line(screen, colour, (left, (top + bottom) // 2),
                             (right, (top + bottom) // 2), 1)

    def _draw_ring(self, screen, cx, cy, radius):
        """The habitat ring: an ellipse with radial spokes, turning."""
        palette = self._palette
        if radius < 4:
            return
        rx = radius
        ry = radius * 0.42
        pygame.draw.ellipse(screen, _mix(palette["structure"], palette["hero"], 0.25),
                            pygame.Rect(int(cx - rx), int(cy - ry), int(rx * 2),
                                        int(ry * 2)), 1)
        spin = TAU * self._time / max(1.0, self._ring_rotation)
        for k in range(8):
            angle = spin + TAU * k / 8.0
            pygame.draw.line(screen, _scale(palette["guide"], 0.8),
                             (cx, cy), (cx + math.cos(angle) * rx,
                                        cy + math.sin(angle) * ry), 1)
        pygame.draw.circle(screen, palette["city"], (int(cx), int(cy)), 2)

    def _draw_population(self, screen, quality):
        if not self._population_lights:
            return
        palette = self._palette
        top, hull_h = self._spans()
        deck_h = hull_h / self._deck_count
        dim = QUALITY[self._quality]["detail"]
        for index, light in enumerate(self._lights[:quality["lights"]]):
            x = self._x(light["x"])
            if x < -4 or x > self._screen_size[0] + 4:
                continue
            y = top + deck_h * (light["deck"] + light["offset"])
            twinkle = 0.5 + 0.5 * math.sin(TAU * self._time / light["period"]
                                           + light["phase"])
            level = 0.35 + 0.65 * twinkle * dim
            colour = _mix(palette["warm"], palette["city"], twinkle)
            pygame.draw.circle(screen, _scale(colour, level), (int(x), int(y)), 1)
        # transport dots: small points running the corridors
        for dot in self._dots[:quality["dots"]]:
            x = (dot["x"] + self._time * dot["speed"] * dot["direction"]) % 1.0
            sx = self._x(x)
            if sx < -4 or sx > self._screen_size[0] + 4:
                continue
            y = top + deck_h * (dot["deck"] + dot["offset"])
            pygame.draw.line(screen, palette["city"], (sx - 3, y), (sx, y), 1)
            pygame.draw.circle(screen, palette["hero"], (int(sx), int(y)), 1)

    def _draw_doors(self, screen):
        """A bay door opens as the camera passes, once a minute."""
        palette = self._palette
        top, hull_h = self._spans()
        cycle = (self._time % 60.0) / 60.0
        if cycle < 0.5:
            opening = 0.0
        elif cycle < 0.7:
            opening = (cycle - 0.5) / 0.2
        elif cycle < 0.85:
            opening = 1.0
        else:
            opening = max(0.0, (1.0 - cycle) / 0.15)
        for door in self._doors:
            x = self._x(door["x"])
            if x < -40 or x > self._screen_size[0] + 40:
                continue
            gap = hull_h * 0.22 * opening
            half = hull_h * 0.24
            pygame.draw.line(screen, palette["hero"],
                             (x, top + hull_h * 0.30 - half - gap),
                             (x, top + hull_h * 0.30), 2)
            pygame.draw.line(screen, palette["hero"],
                             (x, top + hull_h * 0.30 + gap),
                             (x, top + hull_h * 0.30 + half), 2)
            if opening > 0.2:
                pygame.draw.line(screen, _scale(palette["glow"], 0.5 * opening),
                                 (x, top + hull_h * 0.30 - gap),
                                 (x, top + hull_h * 0.30 + gap), 1)

    def _draw_name(self, screen):
        """The ship's name in hull lights, one letter at a time, at the bow."""
        palette = self._palette
        width, height = self._screen_size
        if not self._at_bow or self._name_progress <= 0.0:
            return
        size = max(8, int(height * 0.055))
        font = self._font(size, bold=True)
        full = "".join(self._names)
        letters = int(len(self._names) * _clamp(self._name_progress * 1.4, 0.0, 1.0))
        shown = full[:letters]
        if not shown:
            return
        surface = font.render(shown, True, palette["warm"])
        rect = surface.get_rect()
        bow_x = self._bow_x()
        rect.midright = (int(bow_x - self._spans()[1] * 0.18),
                         int(self._layout["y"] * height - self._spans()[1] * 0.30))
        if rect.left < width * 0.02:
            return
        screen.blit(surface, rect)
        # an underline of hull lights, and the last letter's own glow
        underline_y = rect.bottom + 4
        for k in range(letters * 3):
            x = rect.left + k * max(4, size // 3)
            if x > rect.right:
                break
            pygame.draw.line(screen, _scale(palette["glow"], 0.7), (x, underline_y),
                             (x + 2, underline_y), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        top, hull_h = self._spans()
        deck_h = hull_h / self._deck_count
        if self._population_lights:
            for light in self._lights[:quality["lights"] // 2]:
                x = self._x(light["x"])
                if x < 0 or x > width:
                    continue
                y = top + deck_h * (light["deck"] + light["offset"])
                pygame.draw.circle(self._bloom,
                                   _scale(palette["warm"], 0.30 * self._glow_strength),
                                   (int(x * sx), int(y * sy)), 1)
        if self._at_bow and self._name_progress > 0.0:
            bx = self._bow_x()
            pygame.draw.circle(self._bloom,
                               _scale(palette["warm"], 0.5 * self._glow_strength),
                               (int(max(0, bx - width * 0.06) * sx),
                                int((self._layout["y"] * height) * sy)), 2)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._scroll, phase = self._scroll_state()
        self._at_bow = phase >= 0.82
        if self._at_bow:
            self._name_progress = _clamp((phase - 0.82) / 0.18, 0.0, 1.0)
        else:
            self._name_progress = 0.0
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_hull(screen)
        self._draw_modules(screen)
        self._draw_population(screen, quality)
        self._draw_doors(screen)
        self._draw_name(screen)
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
                print(f"[GenerationShip] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("GENERATION SHIP // CONFIGURATION REFUSED", True,
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
            "scroll": self._scroll,
            "at_bow": self._at_bow,
            "name_progress": self._name_progress,
            "decks": self._deck_count,
            "modules": len(self._modules),
            "population": self._population(),
            "camera_speed": self._camera_speed,
            "ring_rotation": self._ring_rotation,
            "population_lights": self._population_lights,
            "hull": self._spans(),
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
