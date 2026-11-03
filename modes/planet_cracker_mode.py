"""Planet Cracker — a world being taken apart, not blown up.

Slow Wireframe §4.4.  A wireframe sphere turns under a lattice of glowing cuts,
a ring of mining rigs orbits its equator, and the crust has begun to come off in
plates: polygon shards that separate slowly, drift outward, and leave a dark seam
where the cut was.  Now and then a plate lets go — its cut line goes dark, then
relights deeper in the planet, and the rigs shift to follow the seam.

The drawing is all line.  The sphere is a latitude/meridian graticule projected
orthographically with a slow camera tilt; only the front hemisphere is drawn, and
depth is carried by that fade plus line weight and the additive bloom on the cuts
and the rig lights (§2.2, §2.8).  Nothing is a texture and nothing is a
lighting simulation: the "glow" of a cut is a brighter line.

Camera behaviour (§2.3): orbit.  The camera arcs the card's 2° around the site
over 180 s, which reads as a very slow change of the tilt, and a small parallax
slide.  The anchor is recomputed per aspect, so the strip, the portrait wall and
16:9 are each composed natively.

Determinism (§2.9): the plates, the cuts, the rigs and the separation schedule
all come from `seed`; everything else is a function of accumulated elapsed time.
A pinned seed reproduces a still exactly.

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

#: Graticule density, plate count, debris and bloom, from §2.8.
QUALITY = {
    "low": {"rings": 4, "meridians": 6, "plates": 12, "debris": 26, "glow_div": 8,
            "ring_points": 22},
    "medium": {"rings": 5, "meridians": 8, "plates": 18, "debris": 52, "glow_div": 5,
               "ring_points": 28},
    "high": {"rings": 7, "meridians": 12, "plates": 22, "debris": 88, "glow_div": 4,
             "ring_points": 34},
}

#: The frame per aspect: where the planet sits and how big it is.
PRESETS = {
    "ultrawide": {"anchor": (0.335, 0.505), "radius": 0.300, "title_px": 21},
    "landscape": {"anchor": (0.355, 0.505), "radius": 0.315, "title_px": 30},
    "portrait": {"anchor": (0.500, 0.430), "radius": 0.330, "title_px": 34},
    "square": {"anchor": (0.470, 0.480), "radius": 0.310, "title_px": 26},
}

PALETTES = {
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "cut": (255, 236, 206), "rig": (255, 244, 224),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62), "hud_faint": (66, 42, 20),
    },
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "cut": (200, 240, 255), "rig": (240, 252, 255),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178), "hud_faint": (36, 62, 88),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (18, 18, 18),
        "structure": (86, 86, 86), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "cut": (255, 255, 255), "rig": (255, 255, 255),
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


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(v):
    length = math.sqrt(max(1e-9, v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))
    return (v[0] / length, v[1] / length, v[2] / length)


def _radial(size: int, color, peak: int, power: float = 2.4) -> pygame.Surface:
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


class PlanetCrackerMode:
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
        self._rig_count = 8
        self._fracture = 0.4
        self._chunk_drift = 0.2
        self._camera_orbit = 2.0
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "PLANET CRACKER"
        self._subtitle = "SITE 12 · EQUATORIAL WORKS"

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

        self._plates = []
        self._cuts = []
        self._rigs = []
        self._debris = []
        self._separations = []
        self._separation_span = 0.0
        self._separation = None
        self._centre = (0.0, 0.0)
        self._radius = 100.0
        self._spin = 0.0
        self._tilt = 0.0
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

        self._rig_count = self._integer(cfg, "rig_count", 8, 4, 16)
        self._fracture = self._number(cfg, "fracture_stage", 0.4, 0.0, 1.0)
        self._chunk_drift = self._number(cfg, "chunk_drift", 0.2, 0.0, 3.0)
        self._camera_orbit = self._number(cfg, "camera_orbit", 2.0, 0.0, 20.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "PLANET CRACKER", 32) or "PLANET CRACKER"
        self._subtitle = self._text(cfg, "subtitle", "SITE 12 · EQUATORIAL WORKS", 48)

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
            print(f"[PlanetCracker] seed={self.seed} preset={self._preset} "
                  f"rigs={self._rig_count} fracture={self._fracture:.2f} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[PlanetCracker] configuration error: {exc}")

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
        self._plates = []
        self._cuts = []
        self._rigs = []
        self._debris = []
        self._separations = []
        self._separation = None
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
        self._radius = self._layout["radius"] * min(width, height) * 1.45
        self._build_worksite()
        self._build_background()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_worksite(self):
        """
        The work site: plates (polygon shards with precomputed vertices), cut
        arcs, the equatorial rig ring, a sparse debris ring, and the schedule of
        plate separations.  All of it comes from the seed.
        """
        rng = random.Random(self.seed ^ 0x9C4A)
        f = self._fracture
        plates = []
        count = QUALITY["high"]["plates"]
        for index in range(count):
            lon = rng.uniform(0.0, TAU)
            lat = math.asin(rng.uniform(-0.75, 0.75))
            spread = rng.uniform(0.16, 0.34)
            verts = []
            sides = rng.choice((3, 4, 4, 5))
            for k in range(sides):
                angle = TAU * k / sides + rng.uniform(-0.25, 0.25)
                verts.append((math.cos(angle) * spread * rng.uniform(0.7, 1.2),
                              math.sin(angle) * spread * rng.uniform(0.5, 1.0)))
            plates.append({
                "lon": lon,
                "lat": lat,
                "verts": verts,
                "phase": rng.uniform(0.0, TAU),
                # the more fractured the world, the further the plates have gone
                "drift": (0.15 + 0.55 * f) * rng.uniform(0.55, 1.30),
                "tumble": rng.uniform(-1.0, 1.0),
            })
        self._plates = plates

        cuts = []
        for index in range(6):
            # a random great circle, and a short arc of incision along it
            u = _unit((rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0),
                       rng.uniform(-1.0, 1.0)))
            reference = (0.0, 0.0, 1.0) if abs(u[2]) < 0.85 else (0.0, 1.0, 0.0)
            w = _unit(_cross(u, reference))
            cuts.append({
                "u": u, "w": w,
                "t0": rng.uniform(0.0, TAU),
                "length": rng.uniform(0.40, 0.95),
                "phase": rng.uniform(0.0, TAU),
                "period": rng.uniform(4.0, 8.0),
            })
        self._cuts = cuts

        rigs = []
        for index in range(self._rig_count):
            rigs.append({
                "lon": TAU * index / self._rig_count,
                "size": rng.uniform(0.9, 1.25),
                "phase": rng.uniform(0.0, TAU),
            })
        self._rigs = rigs

        debris = []
        for _ in range(QUALITY["high"]["debris"]):
            debris.append({
                "angle": rng.uniform(0.0, TAU),
                "radius": rng.uniform(1.14, 1.42),
                "tilt": rng.uniform(-0.22, 0.22),
                "speed": rng.uniform(0.6, 1.4),
                "size": rng.uniform(0.5, 1.6),
            })
        self._debris = debris

        # One plate lets go every ~34 s for ~6 s: the signature beat.
        self._separations = []
        self._separation_span = 0.0
        if plates:
            gap = 34.0
            span = gap * 6.0
            for k in range(6):
                start = k * gap + rng.uniform(-0.22, 0.22) * gap
                self._separations.append((start, rng.uniform(4.8, 7.2),
                                          rng.randrange(len(plates))))
            self._separation_span = span

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.3
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - 0.5) / 0.55) ** 2)
            color = _mix(base, palette["haze"], band * 0.18)
            pygame.draw.line(surface, color, (0, y), (width, y))
        rng = random.Random(self.seed ^ 0xB1A5)
        for _ in range(max(40, int(width * height / 12000))):
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
            bot_h = max(36, int(height * 0.09))
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

    def _yield_text(self) -> str:
        base = 3.2 + 1.1 * self._fracture
        wobble = 0.06 * math.sin(self._time * 0.09)
        if self._separation is not None:
            wobble -= 0.05 * self._separation["severity"]
        return f"YIELD {base + wobble:.1f} GT"

    def _telemetry(self):
        palette = self._palette
        lines = [(f"RIGS {self._rig_count:02d}", palette["hud"], 220),
                 (f"FRACTURE {self._fracture:.2f}", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((self._yield_text(), palette["hud_dim"], 175))
            lines.append((f"ORBIT {self._camera_orbit:.1f}°", palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._separation is not None:
            plate = self._separation["plate"]
            return f"PLATE {plate:02d} SEPARATING · CUT DARK", True
        return "EXTRACTION NOMINAL · CUT LATTICE HOT", False

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
        color = palette["cut"] if alert else palette["hud_dim"]
        surface = self._cached_text(status, m["status_px"], color, 205)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.75),
                         (rect.left, rect.bottom + 4), (rect.right, rect.bottom + 4), 1)

    # ---------------------------------------------------------------- projection

    def _camera(self):
        """
        The 2° orbit: a very slow change of the tilt, plus a small parallax slide.
        The planet's spin is its own 300 s turn, independent of the camera.
        """
        tilt = math.radians(17.0) + math.radians(self._camera_orbit) * math.sin(
            TAU * self._time / 180.0)
        slide = math.sin(TAU * self._time / 300.0) * self._radius * 0.03
        cx = self._centre[0] + slide
        cy = self._centre[1] + math.sin(TAU * self._time / 240.0) * self._radius * 0.02
        return cx, cy, tilt

    def _sphere(self, lon, lat, spin, tilt):
        """A point on the unit sphere, rotated by the planet's spin then the tilt."""
        cos_lat = math.cos(lat)
        x = cos_lat * math.cos(lon + spin)
        y = math.sin(lat)
        z = cos_lat * math.sin(lon + spin)
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        y2 = y * cos_t - z * sin_t
        z2 = y * sin_t + z * cos_t
        return x, y2, z2

    def _project_vec(self, v, spin, tilt, cx, cy, radius):
        """A unit vector rotated by the planet's spin, then the camera tilt."""
        cos_s, sin_s = math.cos(spin), math.sin(spin)
        x = v[0] * cos_s - v[2] * sin_s
        z = v[0] * sin_s + v[2] * cos_s
        y = v[1]
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        y2 = y * cos_t - z * sin_t
        z2 = y * sin_t + z * cos_t
        return (cx + radius * x, cy - radius * y2, z2)

    def _cut_point(self, cut, t):
        ct, st = math.cos(t), math.sin(t)
        u, w = cut["u"], cut["w"]
        return (u[0] * ct + w[0] * st, u[1] * ct + w[1] * st, u[2] * ct + w[2] * st)

    def _project(self, lon, lat, spin, tilt, cx, cy, radius):
        x, y, z = self._sphere(lon, lat, spin, tilt)
        return (cx + radius * x, cy - radius * y, z)

    def _separation_state(self):
        if not self._separations or self._separation_span <= 0.0:
            return None
        local = self._time % self._separation_span
        for start, duration, plate in self._separations:
            if start <= local < start + duration:
                p = (local - start) / duration
                severity = math.sin(math.pi * p) ** 0.8
                return {"progress": p, "severity": severity, "plate": plate}
        return None

    def _cut_pulse(self, cut, now):
        return 0.55 + 0.45 * math.sin(TAU * now / cut["period"] + cut["phase"])

    def _draw_sphere(self, screen, cx, cy, tilt, spin, radius, quality):
        palette = self._palette
        rings = quality["rings"]
        meridians = quality["meridians"]
        points = quality["ring_points"]
        lats = []
        for k in range(rings):
            lats.append(-0.9 + 1.8 * (k + 0.5) / rings)
        for lat in lats:
            previous = None
            for step in range(points + 1):
                lon = TAU * step / points
                sx, sy, z = self._project(lon, lat, spin, tilt, cx, cy, radius)
                if previous is not None and (z > 0.0 or previous[2] > 0.0):
                    level = 0.55 + 0.45 * max(0.0, min(1.0, (z + previous[2]) * 0.5))
                    pygame.draw.line(screen, _mix(palette["far"], palette["structure"],
                                                  level), previous[:2], (sx, sy), 1)
                previous = (sx, sy, z)
        for k in range(meridians):
            lon = TAU * k / meridians
            previous = None
            for step in range(13):
                lat = -1.35 + 2.7 * step / 12.0
                sx, sy, z = self._project(lon, lat, spin, tilt, cx, cy, radius)
                if previous is not None and (z > 0.0 or previous[2] > 0.0):
                    level = 0.55 + 0.45 * max(0.0, min(1.0, (z + previous[2]) * 0.5))
                    pygame.draw.line(screen, _mix(palette["far"], palette["structure"],
                                                  level), previous[:2], (sx, sy), 1)
                previous = (sx, sy, z)
        # the limb: the hero edge
        pygame.draw.circle(screen, _mix(palette["hero"], palette["structure"], 0.25),
                           (int(cx), int(cy)), int(radius), 2)

    def _draw_cuts(self, screen, cx, cy, tilt, spin, radius, now):
        palette = self._palette
        darkest = self._separation["plate"] if self._separation else -1
        for index, cut in enumerate(self._cuts):
            pulse = self._cut_pulse(cut, now)
            if self._separation is not None and index == darkest % len(self._cuts):
                pulse *= 1.0 - 0.85 * self._separation["severity"]
            color = _mix(palette["accent"], palette["cut"], 0.30 + 0.60 * pulse)
            steps = 9
            previous = None
            for k in range(steps):
                t = cut["t0"] + cut["length"] * k / (steps - 1)
                sx, sy, z = self._project_vec(self._cut_point(cut, t), spin, tilt,
                                              cx, cy, radius * 1.002)
                if previous is not None and z > 0.0 and previous[2] > 0.0:
                    pygame.draw.line(screen, color, previous[:2], (sx, sy),
                                     2 if pulse > 0.82 else 1)
                previous = (sx, sy, z)
            if pulse > 0.85 and previous is not None and previous[2] > 0.0:
                pygame.draw.circle(screen, palette["cut"], (int(previous[0]),
                                                            int(previous[1])), 1)

    def _draw_plates(self, screen, cx, cy, tilt, spin, radius, quality):
        palette = self._palette
        limit = quality["plates"]
        drift_extra = 0.0
        if self._separation is not None:
            sep = self._separation
            if sep["plate"] < len(self._plates):
                drift_extra = sep["severity"] * (0.10 + 0.60 * self._chunk_drift) * radius
        rows = []
        for index, plate in enumerate(self._plates[:limit]):
            base = self._project(plate["lon"], plate["lat"], spin, tilt, cx, cy, radius)
            if base[2] <= 0.0:
                continue
            drift = plate["drift"] * radius * 0.50
            if self._separation is not None and self._separation["plate"] == index:
                drift += drift_extra
            # the shard moves outward from the core along its own normal
            nx = (base[0] - cx) / max(1e-3, radius)
            ny = (base[1] - cy) / max(1e-3, radius)
            ox = base[0] + nx * drift
            oy = base[1] + ny * drift
            tumble = math.sin(self._time * 0.20 * plate["tumble"] + plate["phase"]) * 0.12
            scale = radius * 0.26
            points = []
            for dx, dy in plate["verts"]:
                ca, sa = math.cos(tumble), math.sin(tumble)
                points.append((ox + (dx * ca - dy * sa) * scale,
                               oy + (dx * sa + dy * ca) * scale))
            rows.append((base[2], points, index == (self._separation or {}).get("plate"),
                         drift / max(1.0, radius)))
        rows.sort(key=lambda row: row[0])
        # the sockets: where each shard came from, a dark seam on the surface
        for depth, points, separating, drift_fraction in rows:
            if drift_fraction <= 0.02:
                continue
            socket = [(x + (cx - x) * drift_fraction * 0.35,
                       y + (cy - y) * drift_fraction * 0.35) for x, y in points]
            if separating and self._separation is not None:
                # the cut line goes dark, then relights deeper in the planet
                level = self._separation["severity"]
                pygame.draw.lines(screen, _mix(palette["far"], palette["cut"], 0.35 + 0.6 * level),
                                  True, socket, 2)
            else:
                pygame.draw.lines(screen, _scale(palette["bg_top"], 1.0), True, socket, 1)
                pygame.draw.lines(screen, _scale(palette["far"], 0.7), True, socket, 1)
        filled = self._fill in ("xray", "panel")
        fill_alpha = 26 if self._fill == "xray" else 46
        for depth, points, separating, drift_fraction in rows:
            level = _clamp(depth, 0.0, 1.0)
            color = _mix(palette["far"], palette["hero"], 0.30 + 0.55 * level)
            if separating:
                color = _mix(color, palette["cut"], 0.45)
            if filled:
                face = pygame.Surface((self._screen_size[0], self._screen_size[1]),
                                      pygame.SRCALPHA)
                pygame.draw.polygon(face, _rgba(_scale(color, 0.7), fill_alpha), points)
                screen.blit(face, (0, 0))
            pygame.draw.lines(screen, color, True, points, 1)
            # the cut edge: the shard's brightest line, and it goes dark when the
            # plate lets go
            edge = palette["hero"] if not separating else _scale(palette["far"], 0.8)
            pygame.draw.line(screen, edge, points[0], points[1], 2)
        self._rows = rows

    def _draw_rig_ring(self, screen, cx, cy, tilt, spin, radius):
        """The guide role: the rigs' orbit, dashed, just outside the limb."""
        palette = self._palette
        previous = None
        for step in range(72):
            lon = TAU * step / 72
            sx, sy, z = self._project(lon, 0.30, spin, tilt, cx, cy, radius * 1.16)
            if previous is not None and step % 4 < 2:
                front = max(0.0, (z + previous[2]) * 0.5 + 0.5)
                level = 0.35 + 0.65 * max(0.0, min(1.0, front))
                pygame.draw.line(screen, _scale(palette["guide"], level * 0.9),
                                 previous[:2], (sx, sy), 1)
            previous = (sx, sy, z)

    def _draw_rigs(self, screen, cx, cy, tilt, spin, radius, quality):
        palette = self._palette
        shift = 0.0
        if self._separation is not None:
            shift = self._separation["severity"] * 0.10
        for index, rig in enumerate(self._rigs):
            lon = rig["lon"] + TAU * self._time / 90.0 + shift
            sx, sy, z = self._project(lon, 0.30, spin, tilt, cx, cy, radius * 1.16)
            if z <= -0.2:
                continue
            level = _clamp(0.35 + 0.65 * (z * 0.5 + 0.5), 0.0, 1.0)
            size = max(2.4, radius * 0.030 * rig["size"] * (0.6 + 0.4 * level))
            color = _mix(palette["far"], palette["hero"], 0.35 + 0.55 * level)
            # a small wireframe box with a working light
            box = [(sx - size, sy - size * 0.6), (sx + size * 0.2, sy - size),
                   (sx + size, sy - size * 0.4), (sx + size * 0.3, sy + size * 0.6),
                   (sx - size * 0.8, sy + size * 0.5)]
            pygame.draw.lines(screen, color, True, box, 1)
            pygame.draw.line(screen, _scale(palette["accent"], 0.8),
                             (sx - size, sy - size * 0.6), (sx - size * 0.8, sy + size * 0.5), 1)
            twinkle = 0.6 + 0.4 * math.sin(self._time * 0.9 + rig["phase"])
            pygame.draw.circle(screen, palette["rig"], (int(sx + size * 0.4), int(sy - size * 0.2)),
                               max(1, int(size * 0.30 * twinkle)))

    def _draw_debris(self, screen, cx, cy, tilt, radius, quality, front=False):
        palette = self._palette
        limit = quality["debris"]
        for index in range(min(limit, len(self._debris))):
            piece = self._debris[index]
            angle = piece["angle"] + TAU * self._time / (240.0 / piece["speed"])
            x = math.cos(angle) * radius * piece["radius"]
            z = math.sin(angle) * radius * piece["radius"]
            y = z * math.sin(piece["tilt"])
            z *= math.cos(piece["tilt"])
            if (z >= 0.0) != front:
                continue
            size = max(0.8, piece["size"] * radius * 0.006)
            color = _mix(palette["far"], palette["structure"],
                         _clamp(0.5 + 0.5 * (z / max(1.0, radius)), 0.0, 1.0))
            pygame.draw.line(screen, color, (cx + x - size, cy - y),
                             (cx + x + size, cy - y), 1)

    def _bloom_pass(self, screen, cx, cy, radius, now):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        spin = self._spin
        tilt = self._tilt
        # the cut lattice's heat, the rig lights and the limb
        for cut in self._cuts:
            pulse = self._cut_pulse(cut, now)
            level = int((40 + 70 * pulse) * self._glow_strength)
            previous = None
            for k in range(0, 9, 2):
                t = cut["t0"] + cut["length"] * k / 8.0
                px, py, z = self._project_vec(self._cut_point(cut, t), spin, tilt,
                                              cx, cy, radius * 1.002)
                if previous is not None and z > 0.0 and previous[2] > 0.0:
                    pygame.draw.line(self._bloom, _scale(palette["cut"], level / 255.0),
                                     (previous[0] * sx, previous[1] * sy),
                                     (px * sx, py * sy), 1)
                previous = (px, py, z)
        for index in range(len(self._rigs)):
            lon = self._rigs[index]["lon"] + TAU * now / 90.0
            px, py, z = self._project(lon, 0.30, spin, tilt, cx, cy, radius * 1.16)
            if z <= -0.2:
                continue
            pygame.draw.circle(self._bloom, _scale(palette["rig"], 0.5 * self._glow_strength),
                               (int(px * sx), int(py * sy)), 1)
        pygame.draw.circle(self._bloom, _scale(palette["glow"], 0.45 * self._glow_strength),
                           (int(cx * sx), int(cy * sy)), max(2, int(radius * 1.02 * sx)), 1)
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
        self._separation = self._separation_state()
        cx, cy, tilt = self._camera()
        self._spin = TAU * now / 300.0
        self._tilt = tilt
        radius = self._radius
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._draw_debris(screen, cx, cy, tilt, radius, quality, front=False)
        self._bloom_pass(screen, cx, cy, radius, now)
        self._draw_sphere(screen, cx, cy, tilt, self._spin, radius, quality)
        self._draw_cuts(screen, cx, cy, tilt, self._spin, radius, now)
        self._draw_plates(screen, cx, cy, tilt, self._spin, radius, quality)
        self._draw_rig_ring(screen, cx, cy, tilt, self._spin, radius)
        self._draw_rigs(screen, cx, cy, tilt, self._spin, radius, quality)
        self._draw_debris(screen, cx, cy, tilt, radius, quality, front=True)
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
                print(f"[PlanetCracker] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("PLANET CRACKER // CONFIGURATION REFUSED", True,
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
            "plates": len(self._rows),
            "plate_cap": QUALITY[self._quality]["plates"],
            "rigs": len(self._rigs),
            "fracture": self._fracture,
            "chunk_drift": self._chunk_drift,
            "camera_orbit": self._camera_orbit,
            "separation": dict(self._separation) if self._separation else None,
            "centre": self._centre,
            "radius": self._radius,
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
