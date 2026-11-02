"""Orbital Mirror Array — a field of sails focusing sunlight onto a night-side city.

Slow Wireframe §4.3.  A shallow shell of orbital mirrors hangs above the night
side of a planet, banking to hold a beam on one city.  The planet's limb runs
across the lower frame with a warm cluster of city lights on it; the mirrors
fill the darkness above, each a thin lozenge with one bright edge and a glint
travelling along it.  The beams converge below, and now and then one sail loses
lock: its beam drifts across the limb, then snaps back and the city steadies.

The drawing is all line.  The planet's night side, the atmosphere strokes and
the terminator are cached once per build; the mirrors are a prebuilt table of
lozenges whose transforms animate (bank, glint, parallax), never their topology.
Depth is carried by size, the perspective of the field, draw order and one
half-resolution additive bloom on the beams and glints (§2.8).

Camera behaviour (§2.3): survey.  The camera glides laterally above the array at
the card's 1 px/s, made periodic over five minutes so a wall left running for a
week never slides out of the field.  The anchor is recomputed per aspect, so the
1280x400 strip, the portrait wall and 16:9 are each composed natively.

Determinism (§2.9): the mirror field, the city, the clouds and the lock-loss
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

#: Mirror draw cap, beam segments and bloom downscale, from §2.8.
QUALITY = {
    "low": {"mirrors": 24, "beam_rings": 0.86, "glow_div": 8},
    "medium": {"mirrors": 47, "beam_rings": 0.80, "glow_div": 5},
    "high": {"mirrors": 72, "beam_rings": 0.76, "glow_div": 4},
}

#: The frame per aspect: where the limb crosses, where the focus sits, and how
#: much of the height the array uses.
PRESETS = {
    "ultrawide": {"limb": 0.815, "focus": 0.585, "array_top": 0.205,
                  "spread": 0.62, "title_px": 21, "limb_curve": 0.62},
    "landscape": {"limb": 0.780, "focus": 0.560, "array_top": 0.180,
                  "spread": 0.58, "title_px": 30, "limb_curve": 0.55},
    "portrait": {"limb": 0.855, "focus": 0.500, "array_top": 0.140,
                 "spread": 0.74, "title_px": 34, "limb_curve": 0.42},
    "square": {"limb": 0.820, "focus": 0.540, "array_top": 0.180,
               "spread": 0.66, "title_px": 26, "limb_curve": 0.50},
}

#: The palette family is the array; the city is the one warm accent (§2.7).
PALETTES = {
    "ice": {
        "bg_top": (3, 7, 12), "bg_bottom": (0, 2, 6), "haze": (8, 20, 32),
        "planet": (9, 20, 30), "planet_low": (3, 7, 12),
        "structure": (77, 127, 150), "hero": (232, 251, 255),
        "accent": (155, 232, 255), "glow": (212, 248, 255),
        "city": (255, 198, 122), "city_core": (255, 238, 206),
        "hud": (232, 251, 255), "hud_dim": (110, 152, 172),
        "hud_faint": (40, 66, 84),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "planet": (18, 11, 5), "planet_low": (6, 3, 1),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "city": (255, 206, 140), "city_core": (255, 246, 226),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62),
        "hud_faint": (66, 42, 20),
    },
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "planet": (7, 16, 30), "planet_low": (2, 5, 10),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "city": (255, 196, 118), "city_core": (255, 240, 210),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178),
        "hud_faint": (36, 62, 88),
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
    """A soft round halo, built small once and scaled — never per frame."""
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


class OrbitalMirrorArrayMode:
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
        self._mirror_count = 47
        self._focus = 0.6
        self._beam_strength = 0.5
        self._camera_drift = 1.0
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "ORBITAL MIRROR ARRAY"
        self._subtitle = "NIGHT-SIDE FOCUS · ARRAY 04"

        self._time = 0.0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._planet = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}

        self._mirrors = []
        self._mirror_order = []
        self._tier_indices = {}
        self._city = []
        self._clouds = []
        self._locks = []
        self._lock_span = 0.0
        self._lock = None
        self._focus_xy = (0.0, 0.0)
        self._limb_x = []
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
    def _text(config, key, default, max_length=48):
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

        self._mirror_count = self._integer(cfg, "mirror_count", 47, 20, 80)
        self._focus = self._number(cfg, "focus", 0.6, 0.0, 1.0)
        self._beam_strength = self._number(cfg, "beam_strength", 0.5, 0.0, 1.0)
        self._camera_drift = self._number(cfg, "camera_drift", 1.0, 0.0, 4.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "ORBITAL MIRROR ARRAY", 32) or "ORBITAL MIRROR ARRAY"
        self._subtitle = self._text(cfg, "subtitle", "NIGHT-SIDE FOCUS · ARRAY 04", 48)

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
            print(f"[OrbitalMirrors] seed={self.seed} preset={self._preset} "
                  f"mirrors={self._mirror_count} quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[OrbitalMirrors] configuration error: {exc}")

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
        self._planet = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}
        self._mirrors = []
        self._mirror_order = []
        self._tier_indices = {}
        self._city = []
        self._clouds = []
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
        self._build_mirrors()
        self._build_city()
        self._build_background()
        self._build_planet()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_mirrors(self):
        """
        The array: mirrors on a shallow shell, arranged as a loose grid so the
        field reads as infrastructure rather than a scatter.  `u` is 0 at the
        far edge (small, near the limb) and 1 at the near edge (large, at the
        top of frame); the size and the parallax both scale with it.
        """
        rng = random.Random(self.seed ^ 0x3A11)
        count = int(self._mirror_count)
        rows = max(2, int(round(math.sqrt(count / 2.1))))
        cols = max(2, int(math.ceil(count / rows)))
        mirrors = []
        for index in range(count):
            row = index // cols
            col = index % cols
            u = (row + 0.55 + rng.uniform(-0.09, 0.09)) / rows
            side = ((col + 0.5) / cols) * 2.0 - 1.0
            mirrors.append({
                "u": _clamp(u, 0.0, 1.0),
                "side": side + rng.uniform(-0.03, 0.03),
                "row": row,
                "col": col,
                "phase": rng.uniform(0.0, TAU),
                "bank": -0.46 + rng.uniform(-0.12, 0.12),
                "bank_amp": rng.uniform(0.010, 0.045),
                "bank_period": rng.uniform(20.0, 40.0),
                "glint_period": rng.uniform(3.0, 6.0),
                "glint_phase": rng.uniform(0.0, 1.0),
                "size": rng.uniform(0.86, 1.16),
            })
        self._mirrors = mirrors
        order = list(range(len(mirrors)))
        rng.shuffle(order)
        self._tier_indices = {
            tier: order[:max(1, min(spec["mirrors"], len(order)))]
            for tier, spec in QUALITY.items()
        }

        # The lock-loss schedule: one sail loses lock every ~28 s for ~4.5 s.
        self._locks = []
        self._lock_span = 0.0
        if mirrors:
            gap = 28.0
            span = gap * 8.0
            for k in range(8):
                start = k * gap + rng.uniform(-0.25, 0.25) * gap
                self._locks.append((start, rng.uniform(3.6, 5.4),
                                    rng.randrange(len(mirrors))))
            self._lock_span = span

    def _build_city(self):
        rng = random.Random(self.seed ^ 0xC17E)
        width, height = self._screen_size
        focus_x = self._layout["focus"] * width
        limb_y = self._layout["limb"] * height
        points = []
        for _ in range(96):
            x = focus_x + rng.gauss(0.0, width * 0.030)
            y = limb_y + abs(rng.gauss(0.0, height * 0.011)) + 2
            points.append((x, y, rng.uniform(0.0, TAU), rng.uniform(0.55, 1.35)))
        for _ in range(14):
            # a few taller lights read as towers these points are the only cue to scale
            x = focus_x + rng.gauss(0.0, width * 0.022)
            y = limb_y + abs(rng.gauss(0.0, height * 0.010)) + 3
            points.append((x, y, rng.uniform(0.0, TAU), rng.uniform(1.30, 1.85)))
        self._city = points

        clouds = []
        for k in range(4):
            cy = limb_y - height * (0.020 + 0.020 * k) + rng.uniform(-3, 3)
            clouds.append({
                "y": cy,
                "x0": rng.uniform(-0.1, 0.25) * width,
                "x1": rng.uniform(0.40, 0.95) * width,
                "alpha": rng.randint(18, 40),
                "bend": rng.uniform(-0.012, 0.012) * height,
            })
        self._clouds = clouds

    def _limb_y(self, x: float) -> float:
        """The parabola that is the planet's limb on screen (cached curvature)."""
        width, height = self._screen_size
        curve = self._layout["limb_curve"]
        cx = width * 0.5
        half = max(1.0, width * 0.5)
        t = (x - cx) / half
        return self._layout["limb"] * height + curve * height * t * t

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.25
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - 0.72) / 0.42) ** 2)
            color = _mix(base, palette["haze"], band * 0.22)
            pygame.draw.line(surface, color, (0, y), (width, y))
        # a faint far field of dust above the array (the far role)
        rng = random.Random(self.seed ^ 0xD057)
        for _ in range(max(40, int(width * height / 12000))):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height * 0.7))
            surface.set_at((x, y), _scale(palette["far"], rng.randint(22, 52) / 255.0))
        self._background = surface

    def _build_planet(self):
        """
        The night side, cached: a filled body under the limb, warm toward the city,
        with the atmosphere strokes above it.  The limb is a parabola, so each row
        below it spans a computable x range — 400 line draws, not 500k set_at
        calls, which matters at 1920x1080.
        """
        palette = self._palette
        width, height = self._screen_size
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        focus_x = self._layout["focus"] * width
        apex = self._layout["limb"] * height
        curve = max(1e-3, self._layout["limb_curve"] * height)
        half = max(1.0, width * 0.5)
        cx = width * 0.5

        for y in range(int(apex), height):
            t = (y - apex) / max(1.0, height - apex)
            reach = math.sqrt(max(0.0, (y - apex) / curve)) * half
            x0 = max(0, int(cx - reach))
            x1 = min(width, int(cx + reach) + 1)
            if x1 <= x0:
                continue
            base = _mix(palette["planet"], palette["planet_low"], t)
            pygame.draw.line(layer, _rgba(base, 255), (x0, y), (x1, y), 1)
            if t < 0.26:
                # the atmosphere scattering just under the limb, fading down
                sheen = _mix(base, palette["structure"], 0.22 * (1.0 - t / 0.26) ** 2)
                pygame.draw.line(layer, _rgba(sheen, 255), (x0, y), (x1, y), 1)

        # the warm pool the beams and the city sit in
        glow_size = int(min(width, height) * 0.55)
        pool = _radial(glow_size, palette["city"], peak=48, power=2.0)
        layer.blit(pool, (int(focus_x - glow_size * 0.5),
                          int(apex - glow_size * 0.30)))

        # atmosphere: a few faint strokes just above the limb
        for cloud in self._clouds:
            x0, x1 = int(cloud["x0"]), int(cloud["x1"])
            if x1 <= x0:
                continue
            previous = None
            for x in range(x0, x1, 6):
                bend = cloud["bend"] * ((x / max(1.0, width)) - 0.5) * 2.0
                point = (x, cloud["y"] + bend)
                if previous is not None:
                    pygame.draw.line(layer, _rgba(palette["structure"], cloud["alpha"]),
                                     previous, point, 1)
                previous = point

        self._planet = layer

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
                k = int(54 + 201 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (width, y), 1)
            bot_h = max(38, int(height * 0.10))
            for y in range(bot_h):
                k = int(255 - 230 * (y / max(1, bot_h - 1)))
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
            "status_y": height - max(24, int(height * 0.075)),
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

    def _focus_percent(self, now: float) -> float:
        """A steady readout with a small wobble; the city flicker is a real dip."""
        base = 96.4 + 2.6 * math.sin(now * 0.07) + 0.6 * math.sin(now * 0.31)
        if self._lock is not None:
            base -= 6.5 * self._lock["severity"]
        return _clamp(base, 0.0, 100.0)

    def _telemetry(self):
        palette = self._palette
        lines = [(f"SAILS {self._mirror_count:02d}", palette["hud"], 220),
                 (f"FOCUS {self._focus_percent(self._time):.1f}%",
                  palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"BEAM {self._beam_strength:.1f}", palette["hud_dim"], 175))
            lines.append((f"GLIDE {self._camera_drift:.1f} PX/S",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._lock is not None:
            return f"SAIL {self._lock['index']:02d} — LOCK LOST", True
        return "LOCK NOMINAL · FOCUS ON THE DELTA", False

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
        color = palette["city_core"] if alert else palette["hud_dim"]
        surface = self._cached_text(status, m["status_px"], color, 205)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.75),
                         (rect.left, rect.bottom + 4), (rect.right, rect.bottom + 4), 1)

    # ---------------------------------------------------------------- animation state

    def _camera_offset(self) -> float:
        """
        The lateral glide: periodic over five minutes, so the array never slides
        away.  Near mirrors move more than far ones (parallax, applied per row).
        """
        if self._camera_drift <= 0.0:
            return 0.0
        width, height = self._screen_size
        period = 300.0
        amp = width * 0.030 * (self._camera_drift / 1.0)
        return amp * math.sin(TAU * self._time / period)

    def _lock_state(self):
        if not self._locks or self._lock_span <= 0.0:
            return None
        local = self._time % self._lock_span
        for start, duration, index in self._locks:
            if start <= local < start + duration:
                p = (local - start) / duration
                # drift out, hold, snap back: a quick recovery at the end
                if p < 0.75:
                    severity = math.sin(math.pi * (p / 0.75)) ** 0.7
                else:
                    severity = max(0.0, 1.0 - (p - 0.75) / 0.25) ** 3
                return {"progress": p, "severity": severity, "index": index}
        return None

    def _mirror_rows(self, now: float) -> list:
        """Project the drawn tier: screen position, bank, size and beam state."""
        width, height = self._screen_size
        palette = self._palette
        layout = self._layout
        focus_x = self._focus_target(now)
        limb_y = layout["limb"] * height
        top_y = layout["array_top"] * height
        drift = self._camera_offset()
        spread = layout["spread"] * width
        base = min(width, height) * 0.034
        lock = self._lock
        lock_index = lock["index"] if lock is not None else -1
        rows = []
        for index in self._tier_indices[self._quality]:
            mirror = self._mirrors[index]
            u = mirror["u"]
            size = base * mirror["size"] * (0.42 + 0.95 * u)
            if size < 0.7:
                continue
            x = (focus_x + mirror["side"] * spread * (0.55 + 0.55 * u)
                 + drift * (0.35 + 0.65 * u))
            y = limb_y - height * 0.035 - u * (limb_y - height * 0.035 - top_y)
            if x < -40 or x > width + 40:
                continue
            angle = (mirror["bank"] + math.sin(TAU * now / mirror["bank_period"]
                                               + mirror["phase"]) * mirror["bank_amp"])
            # the glint travels along the long axis, 3–6 s a pass
            glint = (now / mirror["glint_period"] + mirror["glint_phase"]) % 1.0
            glint = 0.5 - 0.5 * math.cos(TAU * glint)
            near = u
            color = _mix(palette["far"], palette["structure"], _clamp(near * 1.5, 0.0, 1.0))
            if near > 0.86:
                color = _mix(color, palette["hero"], (near - 0.86) / 0.14 * 0.35)
            alpha = int(150 + 100 * near)
            beam = (index == lock_index) or (u >= QUALITY[self._quality]["beam_rings"])
            rows.append((u, x, y, size, angle, color, alpha, glint, near,
                         index == lock_index, beam, index))
        rows.sort(key=lambda row: row[0])
        self._rows = rows
        return rows

    def _focus_target(self, now: float) -> float:
        """The city spot the beams converge on; it drifts a little along the limb."""
        width, height = self._screen_size
        base = self._layout["focus"] * width
        base += math.sin(now * 0.045) * width * 0.012
        if self._lock is not None:
            base += math.sin(self._lock["progress"] * math.pi) * width * 0.115 \
                * self._lock["severity"]
        return base

    def _lozenge(self, x, y, size, angle):
        """A thin sail: a long lozenge with one bright edge."""
        ca, sa = math.cos(angle), math.sin(angle)
        shape = [(-1.0, 0.0), (-0.45, -0.34), (1.0, 0.0), (-0.45, 0.34)]
        return [(x + px * size * ca - py * size * sa, y + px * size * sa + py * size * ca)
                for px, py in shape]

    def _draw_limb(self, screen):
        """The hero edge: the planet's limb, brightest where the beams land."""
        palette = self._palette
        width, height = self._screen_size
        focus_x = self._focus_target(self._time)
        step = 4
        previous = None
        for x in range(0, width + step, step):
            y = self._limb_y(x)
            if previous is not None:
                warm = math.exp(-(((x - focus_x) / max(1.0, width * 0.26)) ** 2))
                color = _mix(palette["hero"], palette["city_core"], warm * 0.55)
                pygame.draw.line(screen, color, previous, (x, y), 2)
                # a faint atmosphere above the limb
                pygame.draw.line(screen, _scale(palette["glow"], 0.16 + 0.16 * warm),
                                 (previous[0], previous[1] - 3), (x, y - 3), 1)
            previous = (x, y)


    def _draw_city(self, screen, now: float):
        palette = self._palette
        flicker = 1.0
        if self._lock is not None:
            flicker = 1.0 - 0.75 * self._lock["severity"]
        for x, y, phase, scale in self._city:
            tw = 0.55 + 0.45 * math.sin(TAU * now / 5.0 + phase)
            level = tw * flicker
            radius = max(1, int(scale * (self._screen_size[0] / 1280.0) * 1.4))
            pygame.draw.circle(screen, _mix(palette["city"], palette["city_core"], 0.45),
                               (int(x), int(y)), radius)
            if level > 0.55:
                pygame.draw.circle(screen, _scale(palette["city"], 0.35 * level),
                                   (int(x), int(y)), radius * 3, 1)

    def _draw_beams(self, screen, rows, now: float):
        if self._beam_strength <= 0.0:
            return
        palette = self._palette
        width, height = self._screen_size
        fx = self._focus_target(now)
        fy = self._limb_y(fx)
        for u, x, y, size, angle, color, alpha, glint, near, unlocked, beam, index in rows:
            if not beam:
                continue
            strength = self._beam_strength * (0.55 + 0.45 * near)
            if unlocked:
                strength *= 1.0 - 0.5 * self._lock["severity"] if self._lock else 1.0
            level = _clamp(strength, 0.0, 1.0)
            core = _mix(palette["accent"], palette["glow"], 0.35 * near)
            # the beam is a straight line to the focus with a soft head
            pygame.draw.line(screen, _scale(core, 0.12 + 0.22 * level),
                             (x, y + size * 0.2), (fx, fy - 2), 1)
            if level > 0.45:
                pygame.draw.circle(screen, _scale(palette["glow"], 0.30 * level),
                                   (int(fx), int(fy) - 2), max(1, int(size * 0.30)))

    def _draw_mirrors(self, screen, rows):
        palette = self._palette
        filled = self._fill in ("xray", "panel")
        fill_alpha = 30 if self._fill == "xray" else 52
        for u, x, y, size, angle, color, alpha, glint, near, unlocked, beam, index in rows:
            points = self._lozenge(x, y, size, angle)
            if filled and size >= 3.0:
                face = pygame.Surface((int(size * 3 + 6), int(size * 3 + 6)),
                                      pygame.SRCALPHA)
                ox = oy = size * 1.5 + 3
                local = [(px - x + ox, py - y + oy) for px, py in points]
                pygame.draw.polygon(face, _rgba(_scale(color, 0.8), fill_alpha), local)
                screen.blit(face, (x - ox, y - oy))
            if unlocked:
                # a sail that has lost lock is drawn dimmed, and its frame trembles
                color = _scale(color, 0.55)
            pygame.draw.lines(screen, color, True, points, 1)
            # the sunward edge: the sail's one bright line
            pygame.draw.line(screen, _mix(color, palette["hero"], 0.22 + 0.20 * near),
                             points[1], points[2], 1)
            # the glint travels along the long axis
            gx = _lerp(points[0][0], points[2][0], glint)
            gy = _lerp(points[0][1], points[2][1], glint)
            pygame.draw.circle(screen, _mix(palette["glow"], color, 0.35),
                               (int(gx), int(gy)), max(1, int(size * 0.13)))

    def _bloom_pass(self, screen, rows, now: float):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        fx = self._focus_target(now) * sx
        fy = self._limb_y(self._focus_target(now)) * sy
        # the focus glow and the beam shafts, in bloom space
        for u, x, y, size, angle, color, alpha, glint, near, unlocked, beam, index in rows:
            level = int(58 * self._glow_strength * (0.5 + 0.5 * near))
            if size >= 2.4:
                pygame.draw.circle(self._bloom,
                                   _scale(palette["glow"], (level * 0.6) / 255.0),
                                   (int(x * sx), int(y * sy)), 1)
        limb_level = int(120 * self._glow_strength)
        if limb_level > 0:
            previous = None
            for x in range(0, width + 12, 12):
                point = (int(x * sx), int(self._limb_y(x) * sy))
                if previous is not None:
                    pygame.draw.line(self._bloom,
                                     _scale(palette["glow"], limb_level / 255.0),
                                     previous, point, 1)
                previous = point
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_scene(self, screen):
        now = self._time
        self._lock = self._lock_state()
        rows = self._mirror_rows(now)
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        if self._planet is not None:
            screen.blit(self._planet, (0, 0))
        self._bloom_pass(screen, rows, now)
        self._draw_limb(screen)
        self._draw_city(screen, now)
        self._draw_beams(screen, rows, now)
        self._draw_mirrors(screen, rows)
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
                print(f"[OrbitalMirrors] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("ORBITAL MIRRORS // CONFIGURATION REFUSED", True,
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
            "mirrors": len(self._rows),
            "mirror_cap": QUALITY[self._quality]["mirrors"],
            "mirror_count": self._mirror_count,
            "focus": self._focus,
            "focus_percent": self._focus_percent(self._time),
            "beam_strength": self._beam_strength,
            "camera_drift": self._camera_drift,
            "lock": dict(self._lock) if self._lock else None,
            "limb_y": self._layout["limb"] * height,
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
