"""Asteroid Foundry — inside a hollowed asteroid, riding toward the ore.

Slow Wireframe §4.8.  A cylindrical cavern runs away from the camera: ellipse
rings recede to a vanishing point and pass, machinery stands along the walls —
crucibles pulsing with heat, conveyors carrying ore toward the smelter — and a
shaft of sunlight comes down through the entry mirror, with dust turning in it.
The camera glides along the axis, so the rhythm of the rings is the subject:
this is a ride, and the tunnel is the tune.

Every so often the camera reaches a fresh vein: the cavern's light shifts from
cold blue to amber for a few seconds and the conveyor runs faster.  That is the
signature.

The drawing is all line.  The cavern is a set of projected ellipse rings with a
wandering axis; the machines are small wireframe boxes; the light shaft is one
translucent cone.  Depth is carried by scale, brightness and draw order, plus
one half-resolution additive bloom on the crucibles and the shaft (§2.8).

Camera behaviour (§2.3): ride.  The card's 4 px/s along the axis, made a loop of
`cavern_length` so the ride never runs out.  The anchor is recomputed per
aspect.

Determinism (§2.9): the rings, the machines, the ore and the vein schedule all
come from `seed` and elapsed time.  A pinned seed reproduces a still exactly.

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

#: Ring segments, machine detail, ore and bloom per tier (§2.8).
QUALITY = {
    "low": {"rings": 10, "segments": 18, "machines": 6, "ore": 14, "dust": 18,
            "glow_div": 8},
    "medium": {"rings": 14, "segments": 24, "machines": 9, "ore": 24, "dust": 30,
               "glow_div": 5},
    "high": {"rings": 20, "segments": 32, "machines": 13, "ore": 36, "dust": 44,
             "glow_div": 4},
}

#: The vanishing point and the cavern's girth, per aspect.
PRESETS = {
    "ultrawide": {"vp": (0.470, 0.470), "focal": 0.760, "title_px": 21},
    "landscape": {"vp": (0.470, 0.480), "focal": 0.720, "title_px": 30},
    "portrait": {"vp": (0.500, 0.440), "focal": 0.780, "title_px": 34},
    "square": {"vp": (0.480, 0.470), "focal": 0.740, "title_px": 26},
}

PALETTES = {
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "ore": (255, 196, 120), "heat": (255, 120, 60), "light": (255, 236, 190),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "phosphor": {
        "bg_top": (1, 12, 5), "bg_bottom": (0, 4, 2), "haze": (8, 40, 16),
        "structure": (46, 160, 96), "hero": (217, 255, 232),
        "accent": (105, 240, 174), "glow": (168, 255, 208),
        "ore": (190, 255, 150), "heat": (255, 190, 90), "light": (226, 255, 236),
        "hud": (217, 255, 232), "hud_dim": (86, 160, 116), "hud_faint": (26, 66, 38),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (18, 18, 18),
        "structure": (86, 86, 86), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "ore": (236, 236, 236), "heat": (200, 200, 200), "light": (255, 255, 255),
        "hud": (242, 242, 242), "hud_dim": (140, 140, 140), "hud_faint": (62, 62, 62),
    },
}

#: During a fresh vein the whole cavern warms toward this.
VEIN_TINT = (255, 190, 110)
VEIN_EVERY = 62.0
VEIN_FOR = 11.0

for _pal in PALETTES.values():
    _bgt, _st = _pal["bg_top"], _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.40) for i in range(3))
    _pal["guide"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.62) for i in range(3))

PALETTE_NAMES = tuple(PALETTES)

NEAR_Z = 0.55          # anything closer than this has passed the camera
CAVERN_RADIUS = 0.62   # in world units, at the near plane


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


class AsteroidFoundryMode:
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
        self._cavern_length = 900.0
        self._ore_rate = 0.5
        self._camera_speed = 4.0
        self._mirror_shaft = True
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "ASTEROID FOUNDRY"
        self._subtitle = "SHAFT 2 · ORE FLOW"

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
        self._shaft_layer = None

        self._rings = []
        self._machines = []
        self._ore = []
        self._dust = []
        self._veins = []
        self._vein_span = 0.0
        self._vein = None
        self._vp = (0.0, 0.0)
        self._focal = 1.0
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

        self._cavern_length = self._number(cfg, "cavern_length", 900.0, 200.0, 4000.0)
        self._ore_rate = self._number(cfg, "ore_rate", 0.5, 0.0, 2.0)
        self._camera_speed = self._number(cfg, "camera_speed", 4.0, 0.0, 30.0)
        self._mirror_shaft = self._bool(cfg, "mirror_shaft", True)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "ASTEROID FOUNDRY", 30) or "ASTEROID FOUNDRY"
        self._subtitle = self._text(cfg, "subtitle", "SHAFT 2 · ORE FLOW", 44)

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
            print(f"[Foundry] seed={self.seed} preset={self._preset} "
                  f"cavern={self._cavern_length:.0f}u speed={self._camera_speed:.0f}px/s "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Foundry] configuration error: {exc}")

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
        self._shaft_layer = None
        self._rings = []
        self._machines = []
        self._ore = []
        self._dust = []
        self._veins = []
        self._vein = None
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
        self._vp = (self._layout["vp"][0] * width, self._layout["vp"][1] * height)
        self._focal = self._layout["focal"] * min(width, height)
        self._build_cavern()
        self._build_background()
        self._build_shaft()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_cavern(self):
        """Rings along the axis, machines on the walls, ore on the belt, dust."""
        rng = random.Random(self.seed ^ 0x4F0D)
        length = self._cavern_length
        ring_count = max(24, int(length / 4.0))
        spacing = length / ring_count
        rings = []
        for index in range(ring_count):
            rings.append({
                "z": index * spacing,
                "wobble": rng.uniform(-0.10, 0.10),
                "tilt": rng.uniform(-0.05, 0.05),
                "radius": rng.uniform(0.90, 1.10),
                "ribs": rng.randint(3, 5),
            })
        self._rings = rings
        self._ring_count = ring_count
        self._machine_count = None
        machines = []
        machine_count = max(12, int(length / 10.0))
        for index in range(machine_count):
            machines.append({
                "z": rng.uniform(0.10, 0.98) * length,
                "side": -1 if index % 2 == 0 else 1,
                "size": rng.uniform(0.18, 0.38),
                "phase": rng.uniform(0.0, TAU),
                "period": rng.uniform(4.0, 8.0),
                "kind": "crucible" if index % 3 == 0 else "box",
            })
        self._machines = machines
        self._machine_count = machine_count
        ore = []
        for index in range(QUALITY["high"]["ore"]):
            ore.append({
                "z": rng.uniform(0.0, 1.0),
                "lateral": rng.uniform(-0.10, 0.10),
                "size": rng.uniform(0.6, 1.4),
                "phase": rng.uniform(0.0, 1.0),
            })
        self._ore = ore
        self._dust = [
            {"x": rng.uniform(-0.5, 0.5), "y": rng.uniform(-0.4, 0.6),
             "z": rng.uniform(0.2, 1.0), "phase": rng.uniform(0.0, TAU),
             "speed": rng.uniform(0.01, 0.04)}
            for _ in range(QUALITY["high"]["dust"])
        ]
        # the vein schedule: the cavern warms and the belt speeds up
        veins = []
        span = VEIN_EVERY * 5.0
        for k in range(5):
            veins.append((k * VEIN_EVERY + rng.uniform(-0.15, 0.15) * VEIN_EVERY, VEIN_FOR))
        self._veins = veins
        self._vein_span = span

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        vx, vy = self._vp
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = y / max(1, height - 1)
            base = _mix(palette["bg_top"], palette["bg_bottom"], t ** 1.2)
            # the tunnel's own falloff: a haze band around the vanishing point
            glow = math.exp(-(((y - vy) / max(1.0, height * 0.55)) ** 2))
            color = _mix(base, palette["haze"], 0.10 + 0.30 * glow)
            pygame.draw.line(surface, color, (0, y), (width, y))
        rng = random.Random(self.seed ^ 0x5EED)
        for _ in range(max(40, int(width * height / 16000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(18, 42) / 255.0))
        self._background = surface

    def _build_shaft(self):
        """The cone of sunlight from the entry mirror, cached as one surface."""
        width, height = self._screen_size
        self._shaft_layer = pygame.Surface((width, height), pygame.SRCALPHA)
        if not self._mirror_shaft:
            return
        palette = self._palette
        vx, vy = self._vp
        top = (vx + width * 0.06, -height * 0.10)
        spread = width * 0.045
        floor = (vx - width * 0.02, vy + height * 0.34)
        cone = [(top[0] - spread * 0.35, top[1]), (top[0] + spread * 0.35, top[1]),
                (floor[0] + spread, floor[1]), (floor[0] - spread, floor[1])]
        pygame.draw.polygon(self._shaft_layer, _rgba(palette["light"], 10), cone)
        pygame.draw.polygon(self._shaft_layer, _rgba(palette["light"], 16), cone, 1)
        pygame.draw.line(self._shaft_layer, _rgba(palette["hero"], 90), top, floor, 1)

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
                k = int(48 + 207 * t)
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

    def _ore_text(self) -> str:
        base = 15200 + self._ore_rate * 2400
        wobble = 0.5 + 0.5 * math.sin(self._time * 0.11)
        return f"ORE {int(base * (1.0 + 0.06 * wobble)):,} T"

    def _telemetry(self):
        palette = self._palette
        lines = [("SHAFT 02", palette["hud"], 220),
                 (self._ore_text(), palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"RATE {self._ore_rate:.1f}", palette["hud_dim"], 175))
            lines.append((f"GLIDE {self._camera_speed:.1f} PX/S",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._vein is not None:
            return "FRESH VEIN · BELT RUNNING", True
        return "EXTRACTION NOMINAL · BELT SLOW", False

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

    def _scroll(self) -> float:
        return self._time * self._camera_speed * 6.0      # world units

    def _vein_state(self):
        if not self._veins or self._vein_span <= 0.0:
            return None
        local = self._time % self._vein_span
        for start, duration in self._veins:
            if start <= local < start + duration:
                p = (local - start) / duration
                # warm up quickly, hold, cool down
                if p < 0.25:
                    level = p / 0.25
                elif p > 0.8:
                    level = max(0.0, (1.0 - p) / 0.20)
                else:
                    level = 1.0
                return {"progress": p, "level": level, "remaining": duration * (1.0 - p)}
        return None

    def _tint(self, color):
        """During a fresh vein the whole cavern warms."""
        if self._vein is None:
            return color
        return _mix(color, VEIN_TINT, 0.45 * self._vein["level"])

    def _project(self, lateral, vertical, z):
        """A point at depth z, in the cavern's cross-section coordinates."""
        if z <= NEAR_Z:
            return None
        scale = self._focal / z
        vx, vy = self._vp
        return (vx + lateral * scale, vy + vertical * scale, scale)

    def _ring_radius(self, ring, z):
        return CAVERN_RADIUS * ring["radius"] * (1.0 + ring["wobble"])

    def _draw_rings(self, screen, quality):
        palette = self._palette
        length = self._cavern_length
        scroll = self._scroll()
        segments = quality["segments"]
        visible = []
        for ring in self._rings:
            z = (ring["z"] - scroll) % length
            if z <= NEAR_Z:
                continue
            visible.append((z, ring))
        # the wall at the camera: without it the nearest hoop is metres away and
        # the tunnel closes to a dot.  It is what the rails and the walls open out to.
        visible.append((NEAR_Z * 1.02, {"radius": 1.9, "wobble": 0.0, "tilt": 0.0,
                                        "ribs": 0}))
        visible.sort(key=lambda item: -item[0])
        for z, ring in visible:
            scale = self._focal / z
            radius = self._ring_radius(ring, z)
            centre = (self._vp[0] + ring["wobble"] * scale * 0.1,
                      self._vp[1] + ring["tilt"] * scale)
            rx = radius * scale
            ry = radius * scale * 0.78
            if rx < 1.5 or rx > self._screen_size[0] * 3:
                continue
            near = _clamp(1.0 - z / (length * 0.55), 0.0, 1.0)
            if rx > self._screen_size[0] * 2.2:
                continue                      # the near wall: only the rails need it
            points = []
            for step in range(segments):
                angle = TAU * step / segments
                points.append((centre[0] + math.cos(angle) * rx,
                               centre[1] + math.sin(angle) * ry))
            color = _mix(palette["far"], palette["structure"], 0.35 + 0.55 * near)
            pygame.draw.lines(screen, self._tint(color), True, points,
                              2 if near > 0.75 else 1)
            # the wall ribs, only on the closer rings
            if near > 0.35:
                for k in range(ring["ribs"]):
                    angle = TAU * k / ring["ribs"] + ring["tilt"]
                    a = (centre[0] + math.cos(angle) * rx, centre[1] + math.sin(angle) * ry)
                    b = (centre[0] + math.cos(angle) * rx * 1.22,
                         centre[1] + math.sin(angle) * ry * 1.22)
                    pygame.draw.line(screen, _scale(palette["guide"], 0.7 + 0.3 * near),
                                     a, b, 1)

        # the walls themselves: rails running down the axis through the rings,
        # which is what turns a row of hoops into a tunnel
        if len(visible) > 1:
            rails = 10
            for k in range(rails):
                angle = TAU * k / rails
                ca, sa = math.cos(angle), math.sin(angle)
                previous = None
                for z, ring in visible:
                    scale = self._focal / z
                    radius = self._ring_radius(ring, z)
                    centre = (self._vp[0] + ring["wobble"] * scale * 0.1,
                              self._vp[1] + ring["tilt"] * scale)
                    point = (centre[0] + ca * radius * scale,
                             centre[1] + sa * radius * scale * 0.78)
                    if previous is not None:
                        near = _clamp(1.0 - z / (length * 0.55), 0.0, 1.0)
                        colour = _mix(palette["far"], palette["guide"], 0.25 + 0.6 * near)
                        pygame.draw.line(screen, self._tint(colour), previous, point, 1)
                    previous = point

    def _draw_machines(self, screen, quality):
        palette = self._palette
        length = self._cavern_length
        scroll = self._scroll()
        for index, machine in enumerate(self._machines[:quality["machines"]]):
            z = (machine["z"] - scroll) % length
            if z <= NEAR_Z:
                continue
            side = machine["side"]
            lateral = side * (CAVERN_RADIUS * 0.62)
            base = self._project(lateral, 0.16, z)
            if base is None:
                continue
            bx, by, scale = base
            size = machine["size"] * scale * 0.5
            if size < 1.5:
                continue
            top = (bx, by - size)
            pygame.draw.rect(screen, self._tint(_mix(palette["far"], palette["structure"], 0.55)),
                             pygame.Rect(int(bx - size), int(by - size),
                                         int(size * 2), int(size)), 1)
            pygame.draw.line(screen, _scale(palette["structure"], 0.8), (bx, by), top, 1)
            if machine["kind"] == "crucible":
                pulse = 0.5 + 0.5 * math.sin(TAU * self._time / machine["period"]
                                             + machine["phase"])
                heat = _mix(palette["heat"], palette["glow"], pulse)
                pygame.draw.circle(screen, self._tint(heat),
                                   (int(bx), int(by - size * 0.5)),
                                   max(1, int(size * 0.42)))

    def _draw_conveyor(self, screen, quality):
        """The belt: a dashed line on the floor, with ore moving along it."""
        palette = self._palette
        dashes = 22
        for step in range(dashes):
            z0 = 1.2 + step * 1.9
            z1 = z0 + 1.1
            p0 = self._project(-0.02, 0.42, z0)
            p1 = self._project(-0.02, 0.42, z1)
            if p0 is None or p1 is None:
                continue
            if step % 2 == 0:
                pygame.draw.line(screen, _scale(palette["guide"], 0.65),
                                 (p0[0], p0[1]), (p1[0], p1[1]), 1)
        # the ore polygons, moving toward the smelter
        speed = 1.0 + (3.0 if self._vein is not None else 0.0)
        count = int(len(self._ore) * _clamp(self._ore_rate, 0.0, 2.0))
        for index in range(min(count, quality["ore"])):
            chunk = self._ore[index]
            t = (chunk["z"] + (self._scroll() + self._time * speed * 8.0) / self._cavern_length) % 1.0
            z = 1.4 + t * 8.0
            p = self._project(chunk["lateral"], 0.42, z)
            if p is None:
                continue
            size = max(1, int(chunk["size"] * p[2] * 0.035))
            colour = self._tint(_mix(palette["ore"], palette["glow"], 0.5))
            pygame.draw.polygon(screen, colour, [
                (p[0] - size, p[1]), (p[0], p[1] - size), (p[0] + size, p[1]),
                (p[0], p[1] + size)], 1)

    def _draw_shaft(self, screen):
        if not self._mirror_shaft or self._shaft_layer is None:
            return
        # the shaft breathes a little, and brightens during a vein
        level = 0.75 + 0.25 * math.sin(self._time * 0.12)
        if self._vein is not None:
            level = min(1.0, level + 0.25 * self._vein["level"])
        self._shaft_layer.set_alpha(int(180 * level))
        screen.blit(self._shaft_layer, (0, 0))
        # dust turning in the light
        palette = self._palette
        for mote in self._dust:
            t = (self._time * mote["speed"] + mote["phase"] / TAU) % 1.0
            x = self._vp[0] + mote["x"] * self._screen_size[0] * (0.25 + 0.6 * t)
            y = self._vp[1] + mote["y"] * self._screen_size[1] * (0.20 + 0.7 * t)
            level_mote = 0.35 + 0.65 * math.sin(math.pi * t)
            pygame.draw.circle(screen, _scale(palette["light"], level_mote),
                               (int(x), int(y)), 1)

    def _bloom_pass(self, screen, quality):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        length = self._cavern_length
        scroll = self._scroll()
        for index, machine in enumerate(self._machines[:quality["machines"]]):
            if machine["kind"] != "crucible":
                continue
            z = (machine["z"] - scroll) % length
            if z <= NEAR_Z:
                continue
            p = self._project(machine["side"] * CAVERN_RADIUS * 0.62, 0.16, z)
            if p is None:
                continue
            pulse = 0.5 + 0.5 * math.sin(TAU * self._time / machine["period"]
                                        + machine["phase"])
            pygame.draw.circle(self._bloom,
                               _scale(palette["heat"], 0.25 + 0.35 * pulse),
                               (int(p[0] * sx), int(p[1] * sy)), 1)
        vx, vy = self._vp
        pygame.draw.circle(self._bloom,
                           _scale(palette["glow"], 0.35 * self._glow_strength),
                           (int(vx * sx), int(vy * sy)), 2)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        quality = QUALITY[self._quality]
        self._vein = self._vein_state()
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, quality)
        self._draw_rings(screen, quality)
        self._draw_machines(screen, quality)
        self._draw_conveyor(screen, quality)
        self._draw_shaft(screen)
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
                print(f"[Foundry] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("FOUNDRY // CONFIGURATION REFUSED", True,
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
            "vein": dict(self._vein) if self._vein else None,
            "rings": len(self._rings),
            "machines": len(self._machines),
            "ore": len(self._ore),
            "cavern_length": self._cavern_length,
            "ore_rate": self._ore_rate,
            "camera_speed": self._camera_speed,
            "mirror_shaft": self._mirror_shaft,
            "vp": self._vp,
            "focal": self._focal,
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
