"""Von Neumann Swarm — a self-replicating ecology, no people and no destination.

Slow Wireframe §4.13.  A seed probe sits on a wireframe asteroid.  Around it the
swarm it built: a loose lattice of probes, each a frame, a sensor head and a thin
solar panel, turning slowly and linked by laser lines between nearest neighbours.
Every couple of minutes one more copy unfolds from parts that drift in and snap
into place, its first light comes on, the unit count increments and the links
redraw to include it.

The camera surveys from a safe distance.  There is no destination and nobody on
board: the subject is the population count climbing.

The drawing is all line, but the probes are cached glyph surfaces rather than
per-frame geometry — a hundred glyphs is a hundred blits, not six hundred line
draws.  Farther probes are simplified, and one half-resolution additive bloom
carries the fresh lights (§2.8).

Camera behaviour (§2.3): survey.  A slow drift across the swarm.

Determinism (§2.9): the lattice, the links, the asteroid and the unfold schedule
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

#: Probe cap, link density, parts and bloom per tier (§2.8).
QUALITY = {
    "low": {"probes": 34, "links": 0.8, "parts": 3, "glow_div": 8},
    "medium": {"probes": 62, "links": 1.2, "parts": 5, "glow_div": 5},
    "high": {"probes": 96, "links": 1.6, "parts": 7, "glow_div": 4},
}

#: The swarm's spread and anchor, per aspect.
PRESETS = {
    "ultrawide": {"anchor": (0.500, 0.500), "radius": 0.420, "title_px": 21},
    "landscape": {"anchor": (0.500, 0.500), "radius": 0.380, "title_px": 30},
    "portrait": {"anchor": (0.500, 0.480), "radius": 0.340, "title_px": 34},
    "square": {"anchor": (0.510, 0.500), "radius": 0.340, "title_px": 26},
}

PALETTES = {
    "phosphor": {
        "bg_top": (1, 12, 5), "bg_bottom": (0, 4, 2), "haze": (8, 40, 16),
        "structure": (46, 160, 96), "hero": (217, 255, 232),
        "accent": (105, 240, 174), "glow": (168, 255, 208),
        "link": (92, 220, 140), "light": (240, 255, 240), "rock": (60, 110, 78),
        "hud": (217, 255, 232), "hud_dim": (86, 160, 116), "hud_faint": (26, 66, 38),
    },
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "link": (86, 170, 220), "light": (255, 250, 230), "rock": (40, 74, 104),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "link": (200, 140, 80), "light": (255, 244, 220), "rock": (96, 64, 36),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
}

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

TARGET_CATALOGUE = 128


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


class VonNeumannSwarmMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "phosphor"
        self._palette = PALETTES["phosphor"]
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._frame_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._hud_mode = "minimal"
        self._fill = "line"
        self._orientation = "auto"
        self._swarm_count = 128
        self._replication_rate = 0.5
        self._link_lasers = True
        self._camera_drift = 0.5
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "VON NEUMANN SWARM"
        self._subtitle = "NODE 7 · ASEXUAL REPLICATION"

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

        self._slots = []
        self._links = []
        self._parts = []
        self._rock = []
        self._seed = (0.0, 0.0)
        self._glyphs = {}
        self._centre = (0.0, 0.0)
        self._radius = 100.0
        self._units = 0
        self._newest = None
        self._drift = (0.0, 0.0)
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

        palette = str(cfg.get("palette", "phosphor")).lower()
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

        self._swarm_count = self._integer(cfg, "swarm_count", 128, 8, 512)
        self._replication_rate = self._number(cfg, "replication_rate", 0.5, 0.05, 10.0)
        self._link_lasers = self._bool(cfg, "link_lasers", True)
        self._camera_drift = self._number(cfg, "camera_drift", 0.5, 0.0, 4.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "VON NEUMANN SWARM", 30) or "VON NEUMANN SWARM"
        self._subtitle = self._text(cfg, "subtitle", "NODE 7 · ASEXUAL REPLICATION", 44)

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
            print(f"[Swarm] seed={self.seed} preset={self._preset} "
                  f"catalogue={self._swarm_count} rate={self._replication_rate:.2f}/min "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Swarm] configuration error: {exc}")

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
        self._slots = []
        self._links = []
        self._parts = []
        self._rock = []
        self._glyphs = {}
        self._newest = None
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
        self._radius = self._layout["radius"] * width * 0.5
        self._build_swarm()
        self._build_background()
        self._build_finish()
        self._build_glyphs()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_swarm(self):
        """A loose lattice of slots, the links between them, the rock and parts."""
        rng = random.Random(self.seed ^ 0x5A3E)
        slots = []
        # a jittered spiral lattice: denser in the middle, loose at the edge
        for index in range(QUALITY["high"]["probes"]):
            angle = rng.uniform(0.0, TAU)
            radius = self._radius * math.sqrt(rng.random()) * 0.94
            slots.append({
                "x": math.cos(angle) * radius * 1.22,
                "y": math.sin(angle) * radius * 0.58,
                "angle": angle,
                "scale": rng.uniform(0.75, 1.25),
                "lit_at": rng.uniform(0.0, 1.0),
            })
        self._slots = slots
        # nearest-neighbour links, culled when too long
        links = []
        for i in range(len(slots)):
            for j in range(i + 1, len(slots)):
                dx = slots[i]["x"] - slots[j]["x"]
                dy = slots[i]["y"] - slots[j]["y"]
                if dx * dx + dy * dy < (self._radius * 0.30) ** 2:
                    links.append((i, j, rng.uniform(0.0, TAU), rng.uniform(2.0, 4.0)))
        self._links = links
        # the seed on its rock, down and to the left of the swarm
        self._seed = (-self._radius * 0.95, self._radius * 0.42)
        rock = []
        for index in range(11):
            angle = TAU * index / 11.0
            wobble = 0.80 + 0.35 * rng.random()
            rock.append((self._seed[0] + math.cos(angle) * self._radius * 0.20 * wobble,
                         self._seed[1] + math.sin(angle) * self._radius * 0.15 * wobble))
        self._rock = rock
        parts = []
        for index in range(QUALITY["high"]["parts"]):
            parts.append({
                "angle": rng.uniform(0.0, TAU),
                "radius": rng.uniform(0.4, 0.9),
                "phase": rng.uniform(0.0, TAU),
                "speed": rng.uniform(0.02, 0.06),
            })
        self._parts = parts

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = y / max(1, height - 1)
            base = _mix(palette["bg_top"], palette["bg_bottom"], t ** 1.2)
            band = math.exp(-(((t - 0.5) / 0.60) ** 2))
            color = _mix(base, palette["haze"], band * 0.12)
            pygame.draw.line(surface, color, (0, y), (width, y))
        rng = random.Random(self.seed ^ 0x57A2)
        for _ in range(max(40, int(width * height / 18000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(14, 36) / 255.0))
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

    def _build_glyphs(self):
        """Three cached probe glyphs, at two sizes: frame, sensor head, panel."""
        palette = self._palette
        self._glyphs = {}
        for size in (7, 10, 14):
            surface = pygame.Surface((size * 2 + 4, size * 2 + 4), pygame.SRCALPHA)
            half = surface.get_width() // 2
            bright = _rgba(palette["hero"], 235)
            dim = _rgba(palette["structure"], 210)
            # the frame: a small box
            pygame.draw.rect(surface, bright,
                             pygame.Rect(half - size // 2, half - size // 2,
                                         size, size), 1)
            # the sensor head
            pygame.draw.circle(surface, bright, (half, half - size // 2 - 2), 2)
            # the panel, a thin parallelogram off the right side
            panel = [(half + size // 2, half - 2), (half + size // 2 + size // 2, half - 3),
                     (half + size // 2 + size // 2, half + 1), (half + size // 2, half + 2)]
            pygame.draw.lines(surface, dim, True, panel, 1)
            pygame.draw.line(surface, dim, (half + size // 2, half),
                             (half + size // 2 + size // 2, half - 1), 1)
            self._glyphs[size] = surface

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
        lines = [(f"UNITS {self._units:04d}", palette["hud"], 220),
                 (f"LINKS {int(len(self._links) * QUALITY[self._quality]['links']):03d}",
                  palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"RATE {self._replication_rate:.2f}/MIN",
                          palette["hud_dim"], 175))
            lines.append((f"DRIFT {self._camera_drift:.1f} PX/S",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._newest is not None and self._newest["unfold"] < 1.0:
            return "COPY UNFOLDING · FIRST LIGHT", True
        return "REPLICATION NOMINAL · QUIET", False

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

    # ---------------------------------------------------------------- swarm state

    def _visible_units(self) -> int:
        """How many probes exist now: the seed plus one per replication interval."""
        catalogue = max(8, self._swarm_count)
        base = max(4, int(catalogue * 0.78))
        interval = 60.0 / max(0.05, self._replication_rate)
        grown = int(self._time / interval)
        return min(catalogue, base + grown)

    def _unfold(self):
        """The newest copy, mid-unfold: its parts snap into place."""
        catalogue = max(8, self._swarm_count)
        base = max(4, int(catalogue * 0.78))
        interval = 60.0 / max(0.05, self._replication_rate)
        grown = int(self._time / interval)
        if grown <= 0:
            return None
        phase = (self._time % interval) / interval
        # the unfold runs for the first 12% of the interval, then the unit is done
        if phase > 0.12:
            return None
        index = (base + grown - 1) % len(self._slots)
        return {"index": index, "unfold": _clamp(phase / 0.12, 0.0, 1.0)}

    def _slot_screen(self, slot):
        """A slot's screen position, with the swarm's slow orbit and the drift."""
        spin = TAU * self._time / 60.0
        ca, sa = math.cos(spin * 0.25), math.sin(spin * 0.25)
        x = slot["x"] * ca - slot["y"] * sa
        y = slot["x"] * sa + slot["y"] * ca
        return (self._centre[0] + x + self._drift[0],
                self._centre[1] + y + self._drift[1])

    def _draw_links(self, screen, quality):
        if not self._link_lasers:
            return
        palette = self._palette
        count = int(len(self._links) * quality["links"])
        # draw only links whose both ends are visible
        units = self._units
        for index, (i, j, phase, period) in enumerate(self._links[:count]):
            if i >= units or j >= units:
                continue
            a = self._slot_screen(self._slots[i])
            b = self._slot_screen(self._slots[j])
            length = math.hypot(a[0] - b[0], a[1] - b[1])
            if length > self._radius * 0.30:
                continue
            flicker = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(TAU * self._time / period
                                                         + phase))
            pygame.draw.line(screen, _scale(palette["link"], flicker * 0.55),
                             (a[0], a[1]), (b[0], b[1]), 1)

    def _draw_probes(self, screen, quality):
        palette = self._palette
        units = self._units
        for index, slot in enumerate(self._slots[:min(units, quality["probes"])]):
            x, y = self._slot_screen(slot)
            if x < -30 or x > self._screen_size[0] + 30:
                continue
            if y < -30 or y > self._screen_size[1] + 30:
                continue
            # nearer the centre, bigger and brighter
            depth = _clamp(1.0 - (math.hypot(x - self._centre[0],
                                             y - self._centre[1])
                                  / (self._radius * 1.2)), 0.0, 1.0)
            size = 14 if depth > 0.72 else (10 if depth > 0.35 else 7)
            glyph = self._glyphs.get(size)
            if glyph is None:
                continue
            glow = 0.55 + 0.45 * depth
            if self._newest is not None and index == self._newest["index"]:
                glow = 1.0
            image = glyph.copy()
            image.set_alpha(int(120 + 135 * glow))
            screen.blit(image, (int(x - glyph.get_width() // 2),
                                int(y - glyph.get_height() // 2)))
        # the newest copy's first light
        if self._newest is not None:
            slot = self._slots[self._newest["index"]]
            x, y = self._slot_screen(slot)
            pygame.draw.circle(screen, palette["light"], (int(x), int(y)), 2)

    def _draw_parts(self, screen, quality):
        palette = self._palette
        for part in self._parts[:quality["parts"]]:
            t = (self._time * part["speed"] + part["phase"] / TAU) % 1.0
            radius = self._radius * part["radius"] * (1.0 - 0.5 * t)
            x = self._centre[0] + math.cos(part["angle"]) * radius + self._drift[0]
            y = self._centre[1] + math.sin(part["angle"]) * radius * 0.62 + self._drift[1]
            size = 2 + int(2 * (1.0 - t))
            pygame.draw.rect(screen, _scale(palette["guide"], 0.8),
                             pygame.Rect(int(x - size), int(y - size),
                                         size * 2, size * 2), 1)

    def _draw_rock(self, screen):
        palette = self._palette
        points = [(x + self._drift[0], y + self._drift[1]) for x, y in self._rock]
        pygame.draw.lines(screen, _scale(palette["rock"], 0.9), True, points, 1)
        # the seed probe on the rock
        sx = self._seed[0] + self._drift[0]
        sy = self._seed[1] + self._drift[1]
        pygame.draw.rect(screen, palette["hero"],
                         pygame.Rect(int(sx - 4), int(sy - 4), 8, 8), 1)
        pygame.draw.line(screen, palette["hero"], (sx, sy - 4), (sx, sy - 8), 1)
        pygame.draw.circle(screen, palette["light"], (int(sx), int(sy - 9)), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        if self._newest is not None:
            slot = self._slots[self._newest["index"]]
            x, y = self._slot_screen(slot)
            pygame.draw.circle(self._bloom,
                               _scale(palette["light"], 0.5 * self._glow_strength),
                               (int(x * sx), int(y * sy)), 1)
        for slot in self._slots[:8]:
            x, y = self._slot_screen(slot)
            pygame.draw.circle(self._bloom,
                               _scale(palette["glow"], 0.18 * self._glow_strength),
                               (int(x * sx), int(y * sy)), 1)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._units = self._visible_units()
        self._newest = self._unfold()
        drift_mag = self._camera_drift * 6.0
        self._drift = (drift_mag * math.sin(TAU * self._time / 70.0),
                       drift_mag * 0.4 * math.sin(TAU * self._time / 53.0))
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_links(screen, quality)
        self._draw_rock(screen)
        self._draw_parts(screen, quality)
        self._draw_probes(screen, quality)
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
                print(f"[Swarm] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("VON NEUMANN SWARM // CONFIGURATION REFUSED", True,
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
            "units": self._units,
            "catalogue": self._swarm_count,
            "slots": len(self._slots),
            "links": len(self._links),
            "newest": dict(self._newest) if self._newest else None,
            "seed_pos": self._seed,
            "centre": self._centre,
            "radius": self._radius,
            "drift": self._drift,
            "replication_rate": self._replication_rate,
            "link_lasers": self._link_lasers,
            "camera_drift": self._camera_drift,
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
