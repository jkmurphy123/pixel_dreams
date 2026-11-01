"""Dyson Swarm — a star inside a civilization's collector swarm.

Slow Wireframe §4.1.  A star sits in the middle of a nest of collectors: thin
polygonal sails on three inclined orbit families, seen from a camera drifting
through the outer shell.  The star is the only warm thing in the frame; a
foreground sail crosses it now and then and throws a shadow band outward
through the swarm, which is the signature beat.

The drawing is all line: no textures, no depth buffer.  Depth is carried by
distance fade, line weight, draw order (far shells first, the star between
them) and a half-resolution additive bloom.  The star itself — disc, limb,
graticule and corona — is rendered once per build into a cached surface; only
the swarm, the foreground sail and the shadow band move per frame.

Performance shape (§2.8): the drawn sail count is capped by quality (240 / 600
/ 1000), collectors outside the frame are culled, the starfield and the finish
map are cached, and nothing is laid out as text per frame.

Determinism (§2.9): the collector table, the transit schedule and the
starfield all come from `seed`; everything else is a function of accumulated
elapsed time.  A pinned seed reproduces a still exactly, an unset seed gives a
new swarm on entry.

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

#: Drawn sail caps and bloom downscale, straight out of §2.8.  600 at medium is
#: the card's ceiling; the catalogue number in the HUD is fiction.
QUALITY = {
    "low": {"sails": 240, "glow_div": 8, "ring_points": 40},
    "medium": {"sails": 600, "glow_div": 5, "ring_points": 56},
    "high": {"sails": 1000, "glow_div": 4, "ring_points": 72},
}

#: Camera per aspect.  `focal` is a multiple of the short side, `dist` and
#: `elev` place the camera outside the swarm (elev is a fraction of dist),
#: `anchor` is where the star lands, `ring_alpha` is the guide's brightness.
PRESETS = {
    "ultrawide": {"focal": 1.50, "dist": 3.40, "elev": 0.52, "anchor": (0.40, 0.47),
                  "ring_alpha": 34, "title_px": 22},
    "landscape": {"focal": 1.10, "dist": 3.95, "elev": 0.60, "anchor": (0.41, 0.46),
                  "ring_alpha": 30, "title_px": 30},
    "portrait": {"focal": 1.25, "dist": 4.00, "elev": 0.95, "anchor": (0.50, 0.36),
                 "ring_alpha": 26, "title_px": 34},
    "square": {"focal": 1.05, "dist": 4.00, "elev": 0.70, "anchor": (0.45, 0.44),
               "ring_alpha": 30, "title_px": 26},
}

#: The star's world radius, in units where the outer shell is at r=3.3.
STAR_RADIUS = 0.42
SHELL_INNER = 2.05
SHELL_OUTER = 3.30

#: The three palettes on the card: the swarm is the palette family, the star is
#: always the warm exception (one warm accent per scene, §2.7).
PALETTES = {
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "star": (255, 214, 160), "star_core": (255, 248, 236),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178),
        "hud_faint": (36, 62, 88),
    },
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "star": (255, 226, 178), "star_core": (255, 250, 238),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62),
        "hud_faint": (66, 42, 20),
    },
    "ice": {
        "bg_top": (3, 7, 12), "bg_bottom": (0, 2, 6), "haze": (8, 22, 34),
        "structure": (77, 127, 150), "hero": (232, 251, 255),
        "accent": (155, 232, 255), "glow": (212, 248, 255),
        "star": (255, 208, 150), "star_core": (255, 246, 228),
        "hud": (232, 251, 255), "hud_dim": (110, 152, 172),
        "hud_faint": (40, 66, 84),
    },
}

#: Derived role colours: the far and guide roles are the palette family at the
#: brightness the line-role table asks for (§2.2).
for _pal in PALETTES.values():
    _bgt = _pal["bg_top"]
    _st = _pal["structure"]
    _pal["far"] = tuple(int(_bgt[i] + (_st[i] - _bgt[i]) * 0.42) for i in range(3))
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


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(v):
    length = math.sqrt(max(1e-9, _dot(v, v)))
    return (v[0] / length, v[1] / length, v[2] / length)


def _radial(size: int, color, peak: int, power: float = 2.4) -> pygame.Surface:
    """A soft round halo, built at 48x48 and scaled once — no per-frame gradient."""
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


def _collector(shell, radius, tilt, node, phase, omega, size) -> dict:
    """
    One record.  The orbit's tilt and node never change, so their trigonometry is
    folded in here rather than recomputed 900 times a frame.
    """
    return {
        "shell": shell,
        "radius": radius,
        "phase": phase,
        "omega": omega,
        "size": size,
        "cost": math.cos(tilt),
        "sint": math.sin(tilt),
        "cosn": math.cos(node),
        "sinn": math.sin(node),
    }


class DysonSwarmMode:
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
        self._collector_count = 900
        self._shells = 3
        self._orbit_seconds = 180.0
        self._transit_chance = 0.5
        self._camera_drift = 0.5
        self._glow_strength = 0.55
        self._scanline_alpha = 4
        self._vignette = 0.22
        self._title = "DYSON SWARM"
        self._subtitle = "SHELL 4 · OUTER DRIFT"

        self._time = 0.0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._star_surface = None
        self._star_nominal_r = 40
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}

        self._collectors = []
        self._foreground = []
        self._hero = None
        self._band_layer = None
        self._tier_indices = {}
        self._transits = []
        self._transit_span = 0.0
        self._transit = None
        self._rows = []
        self._star_xy = (0.0, 0.0)
        self._star_r = 40.0
        self._star_depth = 1.0
        self._cam_pos = (0.0, 0.0, 1.0)
        self._basis = None
        self._focal = 1.0
        self._offset = (0.0, 0.0)
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
    def _text(config, key, default, max_length=56):
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

        self._collector_count = self._integer(cfg, "collector_count", 900, 60, 5000)
        self._shells = self._integer(cfg, "shells", 3, 1, 4)
        self._orbit_seconds = self._number(cfg, "orbit_seconds", 180.0, 40.0, 900.0)
        self._transit_chance = self._number(cfg, "transit_chance", 0.5, 0.0, 6.0)
        self._camera_drift = self._number(cfg, "camera_drift", 0.5, 0.0, 4.0)
        self._glow_strength = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)
        self._vignette = self._number(cfg, "vignette_strength", 0.22, 0.0, 1.0)

        self._title = self._text(cfg, "title", "DYSON SWARM", 40) or "DYSON SWARM"
        self._subtitle = self._text(cfg, "subtitle", "SHELL 4 · OUTER DRIFT", 56)

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
            print(f"[DysonSwarm] seed={self.seed} preset={self._preset} "
                  f"shells={self._shells} collectors={self._collector_count} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[DysonSwarm] configuration error: {exc}")

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
        self._star_surface = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}
        self._collectors = []
        self._foreground = []
        self._hero = None
        self._band_layer = None
        self._tier_indices = {}
        self._transits = []
        self._transit = None
        self._rows = []
        self._time = 0.0
        self._last_error_logged = False
        self._clear()

    def _clear(self):
        self._rows = []
        self._hud_rects = []
        self._bloom = None

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
        self._build_collectors()
        self._build_ramp()
        hero_rng = random.Random(self.seed ^ 0x6E17)
        self._hero = {
            "x0": hero_rng.uniform(0.0, 1.0),
            "y": hero_rng.uniform(0.42, 0.68),
            "scale": hero_rng.uniform(0.85, 1.25),
            "angle": hero_rng.choice((-0.42, -0.26, 0.30, 0.18)),
        }
        self._band_layer = pygame.Surface((width, height), pygame.SRCALPHA)
        self._build_camera()
        self._build_background()
        self._build_star()
        self._build_finish()
        self._build_bloom()
        self._build_hud()
        self._last_error_logged = False

    def _build_collectors(self):
        """
        The swarm table: one row per catalogue collector, generated once from the
        seed.  Shells are spaced evenly between the inner and outer radius; each
        collector gets an inclination, a node rotation, a phase, a size and an
        orbital period, so the whole scene is a function of (seed, time).
        """
        rng = random.Random(self.seed ^ 0x5A17)
        count = int(self._collector_count)
        shells = int(self._shells)
        radii = []
        for shell in range(shells):
            t = 0.0 if shells == 1 else shell / (shells - 1)
            radii.append(_lerp(SHELL_INNER, SHELL_OUTER, t))
        # Inner shells hold fewer collectors: less area, and they sit nearest the
        # star where the eye already has the light.
        weights = [0.5 + 0.5 * (shell + 1) for shell in range(shells)]
        total = sum(weights)
        counts = [max(1, int(round(count * weight / total))) for weight in weights]

        rows = []
        for shell, (radius, n) in enumerate(zip(radii, counts)):
            tilt = rng.uniform(-0.16, 0.16)          # the family's common plane
            omega = TAU / (self._orbit_seconds * (1.0 + 0.55 * shell))
            for _ in range(n):
                rows.append(_collector(
                    shell, radius * (1.0 + rng.uniform(-0.05, 0.05)),
                    tilt + rng.gauss(0.0, 0.17), rng.uniform(0.0, TAU),
                    rng.uniform(0.0, TAU), omega * (1.0 + rng.gauss(0.0, 0.03)),
                    0.016 + 0.024 * rng.random()))
        self._collectors = rows

        # The near family: a handful of large sails between the camera and the
        # outer shell.  They are what gives the frame its foreground parallax and
        # its scale cue, so they are never culled by the quality tier.
        self._foreground = []
        for _ in range(6):
            self._foreground.append(_collector(
                -1, rng.uniform(3.42, 4.05), rng.gauss(0.0, 0.30),
                rng.uniform(0.0, TAU), rng.uniform(0.0, TAU),
                TAU / (self._orbit_seconds * rng.uniform(0.55, 0.90)),
                rng.uniform(0.030, 0.055)))
        order = list(range(len(rows)))
        rng.shuffle(order)
        self._tier_indices = {
            tier: order[:min(spec["sails"], len(order))]
            for tier, spec in QUALITY.items()
        }

        # Transit schedule: eight windows repeated over a span derived from the
        # per-minute chance, so a pinned seed reproduces the same beats forever.
        self._transits = []
        self._transit_span = 0.0
        if self._transit_chance > 0.0 and rows:
            gap = max(24.0, 60.0 / self._transit_chance)
            span = gap * 8.0
            for index in range(8):
                start = index * gap + rng.uniform(-0.38, 0.38) * gap
                self._transits.append((max(0.0, start), rng.uniform(15.0, 30.0), index))
            self._transit_span = span

    def _build_ramp(self):
        palette = self._palette
        ramp = []
        for step in range(24):
            near = step / 23.0
            color = _mix(palette["far"], palette["structure"], _clamp(near * 1.5, 0.0, 1.0))
            weight = 1
            if near > 0.88:
                color = _mix(color, palette["hero"], (near - 0.88) / 0.12 * 0.55)
                weight = 2
            ramp.append((color, int(150 + 105 * near), weight))
        self._ramp = ramp
        self._fg_color = _mix(palette["structure"], palette["hero"], 0.42)

    def _build_camera(self):
        """The nominal camera basis and the offset that puts the star on its anchor."""
        width, height = self._screen_size
        layout = self._layout
        dist = layout["dist"]
        self._cam_pos = (0.0, layout["elev"] * dist, dist)
        self._focal = layout["focal"] * min(width, height)
        self._basis = (self._cam_pos,) + self._basis_for(self._cam_pos, (0.0, 0.0, 0.0))
        star_xy = self._project((0.0, 0.0, 0.0))
        ax, ay = layout["anchor"]
        self._offset = (ax * width - star_xy[0], ay * height - star_xy[1])
        self._star_xy = (star_xy[0] + self._offset[0], star_xy[1] + self._offset[1])
        self._star_depth = self._depth((0.0, 0.0, 0.0))
        self._star_r = self._focal * STAR_RADIUS / max(0.2, self._star_depth)
        self._star_nominal_r = max(8, int(self._star_r))

    @staticmethod
    def _basis_for(cam, target):
        fwd = _norm((target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]))
        world_up = (0.0, 1.0, 0.0)
        right = _norm(_cross(fwd, world_up))
        up = _norm(_cross(right, fwd))
        return fwd, right, up

    def _basis_at(self, cam):
        fwd, right, up = self._basis_for(cam, (0.0, 0.0, 0.0))
        return cam, fwd, right, up

    def _depth(self, point) -> float:
        cam, fwd, _right, _up = self._basis
        return _dot((point[0] - cam[0], point[1] - cam[1], point[2] - cam[2]), fwd)

    def _project(self, point):
        cam, fwd, right, up = self._basis
        rel = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
        depth = _dot(rel, fwd)
        if depth < 0.12:
            return None
        return (self._focal * _dot(rel, right) / depth,
                -self._focal * _dot(rel, up) / depth)

    # ---------------------------------------------------------------- cached layers

    def _build_background(self):
        palette = self._palette
        width, height = self._screen_size
        surface = pygame.Surface((width, height)).convert()
        horizon = 0.46
        for y in range(height):
            t = (y / max(1, height - 1)) ** 1.35
            base = _mix(palette["bg_top"], palette["bg_bottom"], t)
            band = math.exp(-(((y / max(1, height - 1)) - horizon) / 0.30) ** 2)
            color = _mix(base, palette["haze"], band * 0.30)
            pygame.draw.line(surface, color, (0, y), (width, y))
        self._background = surface
        self._paint_starfield()

    def _paint_starfield(self):
        """The far role: faint dust, painted into the background once, not blitted."""
        width, height = self._screen_size
        palette = self._palette
        rng = random.Random(self.seed ^ 0xF00D)
        count = max(60, int(width * height / 9000))
        for _ in range(count):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            level = rng.randint(16, 46) / 255.0
            self._background.set_at((x, y), _scale(palette["far"], level))

    def _build_star(self):
        """
        The star, cached: two radial gradients (halo, corona), the disc, the core,
        the bright limb — the scene's one hero edge — and a faint graticule.
        """
        palette = self._palette
        radius = self._star_nominal_r
        size = max(24, int(radius * 4.5))
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)

        surface.blit(_radial(size, palette["glow"], peak=64, power=3.0), (0, 0))
        corona = _radial(int(radius * 2.0), palette["star"], peak=62, power=2.4)
        surface.blit(corona, (centre[0] - radius, centre[1] - radius))

        pygame.draw.circle(surface, palette["star"], centre, int(radius * 0.88))
        pygame.draw.circle(surface, palette["star_core"], centre, int(radius * 0.52))
        pygame.draw.circle(surface, _rgba(palette["hero"], 238), centre,
                           int(radius), 2)
        pygame.draw.circle(surface, _rgba(palette["glow"], 120), centre,
                           int(radius * 1.06), 1)

        guide = _rgba(palette["guide"], 86)
        for sw, sh in ((0.62, 0.20), (0.32, 0.66), (0.84, 0.34)):
            rect = pygame.Rect(centre[0] - radius * sw, centre[1] - radius * sh,
                               radius * sw * 2, radius * sh * 2)
            pygame.draw.ellipse(surface, guide, rect, 1)
        for step in range(8):
            angle = TAU * step / 8.0 + 0.22
            inner = radius * 1.04
            outer = radius * (1.26 if step % 2 else 1.15)
            pygame.draw.line(
                surface, _rgba(palette["glow"], 58 if step % 2 else 36),
                (centre[0] + math.cos(angle) * inner, centre[1] + math.sin(angle) * inner),
                (centre[0] + math.cos(angle) * outer, centre[1] + math.sin(angle) * outer),
                1)
        self._star_surface = surface.convert_alpha()

    def _build_finish(self):
        """
        One multiply map: vignette, scanlines and the two quiet HUD bands.  Baking
        them into a single blit is what keeps the frame cheap (see cyberspace's
        renderer for the same trade).
        """
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
                k = int(52 + 203 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (width, y), 1)
            bot_h = max(40, int(height * 0.11))
            for y in range(bot_h):
                k = int(255 - 232 * (y / max(1, bot_h - 1)))
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
            "status_y": height - max(26, int(height * 0.095)),
            "status_x": max(96, int(width * (0.10 if self._preset == "ultrawide" else 0.06))),
            "status_px": max(7, min(13, int(title_px * 0.38))),
        }

    def _font(self, size, bold=False):
        return self.manager.cache.get_font("dejavusansmono", max(7, int(size)), bold=bold)

    def _tracked(self, surface, text, font, color, pos, tracking=0.0, alpha=255):
        """Small mono type, uppercase, wide tracking (§2.6).  Returns the width."""
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
                                (m["title_x"], y), tracking=m["title_px"] * 0.14,
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
        """Telemetry strings are cached: the countdown repaints once a second."""
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
        catalogue = self._collector_count * 1337
        if catalogue >= 1_000_000:
            count_text = f"{catalogue / 1_000_000:.1f}M"
        elif catalogue >= 1000:
            count_text = f"{catalogue / 1000:.0f}K"
        else:
            count_text = str(catalogue)
        shell_no = self._shells + 1
        lines = [(f"COLLECTORS {count_text}", palette["hud"], 220),
                 (f"SHELL {shell_no:02d} / {self._shells:02d}", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"ORBIT {self._orbit_seconds:.0f} S", palette["hud_dim"], 175))
            lines.append((f"TRANSIT ×{self._transit_chance:.1f} / MIN",
                          palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._transit is not None:
            remaining = self._transit["remaining"]
            return f"TRANSIT T−{int(remaining) // 60:01d}:{int(remaining) % 60:02d}", True
        return f"DRIFT {self._camera_drift:.1f} PX/S · ALT {self._layout['dist']:.1f} AU", False

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

        # The reticle brackets the star: annotation, not a panel.
        if self._transit is None:
            self._draw_brackets(screen)

        # One status line, kept clear of the controller's mode-number corner.
        status, transit = self._status_text()
        color = palette["accent"] if transit else palette["hud_dim"]
        surface = self._cached_text(status, m["status_px"], color, 205)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())
        tick = pygame.Rect(m["status_x"], m["status_y"] + m["status_px"] + 5,
                           max(24, int(m["status_px"] * 3.2)), 1)
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.75),
                         (tick.left, tick.top), (tick.right, tick.top), 1)

    def _draw_brackets(self, screen):
        palette = self._palette
        x, y = self._star_xy
        r = self._star_r * 1.55
        length = max(4.0, r * 0.22)
        color = palette["guide"]
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cx, cy = x + sx * r, y + sy * r
            pygame.draw.line(screen, color, (cx, cy), (cx - sx * length, cy), 1)
            pygame.draw.line(screen, color, (cx, cy), (cx, cy - sy * length), 1)
        rect = pygame.Rect(int(x - r), int(y - r), int(r * 2), int(r * 2))
        self._hud_rects.append(rect)

    # ---------------------------------------------------------------- animation state

    def _camera_now(self):
        """
        The camera is the nominal one plus a slow lateral oscillation: the card's
        0.5 px/s drift, made periodic so a wall left running for a week never
        parks the camera outside the swarm.
        """
        width, height = self._screen_size
        base = self._cam_pos
        if self._camera_drift <= 0.0:
            return base
        period = 300.0
        px_per_unit = self._focal / max(0.5, base[2])
        amp = (self._camera_drift * period / (TAU * max(1e-3, px_per_unit)))
        amp = min(0.55, amp)
        phase = TAU * self._time / period
        drift_x = amp * math.sin(phase)
        drift_y = 0.32 * amp * math.sin(phase + 1.1)
        aim_x = 0.10 * amp * math.sin(phase + 0.4)
        return (base[0] + drift_x + aim_x, base[1] + drift_y, base[2])

    def _transit_state(self):
        if not self._transits or self._transit_span <= 0.0:
            return None
        local = self._time % self._transit_span
        for start, duration, index in self._transits:
            if start <= local < start + duration:
                progress = (local - start) / duration
                return {
                    "progress": progress,
                    "remaining": (start + duration) - local,
                    "duration": duration,
                    "index": index,
                }
        return None

    def _orbit_point(self, collector, time_s):
        """
        Position and velocity.  The orbit's tilt and node trigonometry is folded in
        at build time; only the phase turns here.  The velocity is what gives a
        sail its orientation on screen, so it has to be the real one: a radial
        perpendicular makes half the swarm read as vertical ticks.
        """
        theta = collector["phase"] + collector["omega"] * time_s
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        radius = collector["radius"]
        cost, sint = collector["cost"], collector["sint"]
        cosn, sinn = collector["cosn"], collector["sinn"]
        x, z = cos_t * radius, sin_t * radius
        y = z * sint
        z *= cost
        dx, dz = -sin_t * radius, cos_t * radius
        dy = dz * sint
        dz *= cost
        return ((x * cosn + z * sinn, y, -x * sinn + z * cosn),
                (dx * cosn + dz * sinn, dy, -dx * sinn + dz * cosn))

    def _shadow_band(self, transit):
        """Where the shadow is on screen, in pixels from the star, and its width."""
        if transit is None:
            return None
        width, height = self._screen_size
        reach = max(width, height) * 0.62
        progress = transit["progress"]
        radius = self._star_r + (reach - self._star_r) * (progress ** 0.85)
        band = max(18.0, reach * 0.20 * (1.0 - 0.45 * progress))
        return radius, band

    def _row_for(self, collector, now, palette, band):
        """Project one collector; None when it is behind the camera or off-frame."""
        width, height = self._screen_size
        cam, fwd, right, up = self._basis_now
        point, direction = self._orbit_point(collector, now)
        relx = point[0] - cam[0]
        rely = point[1] - cam[1]
        relz = point[2] - cam[2]
        depth = relx * fwd[0] + rely * fwd[1] + relz * fwd[2]
        if depth < 0.22:
            return None
        sx = self._focal * (relx * right[0] + rely * right[1] + relz * right[2]) / depth + self._offset[0]
        sy = -self._focal * (relx * up[0] + rely * up[1] + relz * up[2]) / depth + self._offset[1]
        margin = 44
        if sx < -margin or sx > width + margin or sy < -margin or sy > height + margin:
            return None
        size = self._focal * collector["size"] / depth
        if size < 0.62:
            return None
        if collector["shell"] < 0:
            size = min(size, min(width, height) * 0.30)

        # The tangent of the orbit at this instant: the sail's long axis, and the
        # reason the swarm reads as orbiting rather than scattered.  It comes from
        # the orbit's derivative, so no second set of trigonometry is needed.
        # The sail's long axis: the velocity, projected.  The depth of the near
        # point stands in for the far one — over a 0.02-unit step the difference is
        # smaller than a pixel, and this costs two dot products instead of a second
        # full projection.
        dirx, diry, dirz = direction
        dxs = self._focal * (dirx * right[0] + diry * right[1] + dirz * right[2]) / depth
        dys = -self._focal * (dirx * up[0] + diry * up[1] + dirz * up[2]) / depth
        length = math.hypot(dxs, dys)
        if length > 1e-6:
            tx, ty = dxs / length, dys / length
        else:
            tx, ty = 0.0, -1.0


        near = _clamp((4.6 - depth) / 3.1, 0.0, 1.0)
        color, alpha, weight = self._ramp[int(near * 23)]
        if collector["shell"] < 0:
            color = self._fg_color
            alpha = 205
            weight = 1
        if band is not None:
            distance = math.hypot(sx - self._star_xy[0], sy - self._star_xy[1])
            if abs(distance - band[0]) < band[1]:
                # The shadow band: a darker pass over the collectors, not a
                # lighting simulation (card, build notes).
                color = _scale(color, 0.42)
                alpha = int(alpha * 0.55)
        if self._transit is not None and depth < self._star_depth_now:
            # Backlit while a sail crosses the star: the near lines go dark and
            # their rim stays bright.
            color = _mix(palette["bg_bottom"], color, 0.14)
            alpha = 232
        return (depth, sx, sy, size, color, alpha, weight, tx, ty,
                collector["shell"], self._sail_shape(sx, sy, size, tx, ty))

    def _project_rows(self, now):
        """
        Project the drawn tier plus the near family, cull what is off-frame, and
        shade each sail for its role.  Far sails are drawn first, so the star and
        the near shells occlude them: that is the whole depth buffer (§2.1).
        """
        self._basis_now = self._basis_at(self._camera_now())
        cam, fwd, _right, _up = self._basis_now
        self._star_depth_now = _dot((-cam[0], -cam[1], -cam[2]), fwd)
        band = self._shadow_band(self._transit)
        palette = self._palette
        rows = []
        for index in self._tier_indices[self._quality]:
            row = self._row_for(self._collectors[index], now, palette, band)
            if row is not None:
                rows.append(row)
        for collector in self._foreground:
            row = self._row_for(collector, now, palette, band)
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda row: -row[0])
        self._rows = rows
        return rows

    # ---------------------------------------------------------------- drawing

    def _sail_shape(self, sx, sy, size, tx, ty):
        """A sail: a dash along the orbit for the dust, a thin kite for the near ones."""
        if size < 3.0:
            half = max(0.7, size)
            return [(sx - tx * half, sy - ty * half), (sx + tx * half, sy + ty * half)]
        nx, ny = -ty, tx
        long = size * 1.7
        wide = max(0.8, size * 0.42)
        return [
            (sx + tx * long, sy + ty * long),
            (sx + nx * wide - tx * long * 0.25, sy + ny * wide - ty * long * 0.25),
            (sx - tx * long * 0.75, sy - ty * long * 0.75),
            (sx - nx * wide - tx * long * 0.25, sy - ny * wide - ty * long * 0.25),
        ]

    def _bloom_pass(self, screen, rows, now):
        """
        A half-resolution additive pass: the star's halo and the near sails' own
        lines, scaled up.  Drawing rings here was what turned the star into a
        bullseye; the upscale does the softening, so the source stays flat.
        """
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        bw, bh = self._bloom.get_size()
        sx, sy = bw / width, bh / height
        self._bloom.fill((0, 0, 0))
        palette = self._palette
        for row in rows:
            depth, px, py, size, color, alpha, weight, tx, ty, shell, points = row
            if size < 3.0 or len(points) < 3:
                continue
            level = int(132 * self._glow_strength) + (26 if weight > 1 else 0)
            pygame.draw.lines(self._bloom, _scale(color, level / 255.0), True,
                              [(int(x * sx), int(y * sy)) for x, y in points], 1)
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_guide_rings(self, screen):
        """
        The guide role: the orbit families as dashed ellipses with a tick every 45
        degrees, plus one construction line running out from the star.  20–35%
        brightness (§2.2) — quiet enough that the sails stay the subject.
        """
        palette = self._palette
        width, height = self._screen_size
        cam, fwd, right, up = self._basis_now
        points = QUALITY[self._quality]["ring_points"]
        alpha = int(self._layout["ring_alpha"] * 1.35)
        for shell in range(self._shells):
            t = 0.0 if self._shells == 1 else shell / (self._shells - 1)
            radius = _lerp(SHELL_INNER, SHELL_OUTER, t)
            previous = None
            for step in range(points + 1):
                theta = TAU * step / points
                point = (math.cos(theta) * radius, 0.0, math.sin(theta) * radius)
                rel = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
                depth = _dot(rel, fwd)
                if depth < 0.2:
                    previous = None
                    continue
                sx = self._focal * _dot(rel, right) / depth + self._offset[0]
                sy = -self._focal * _dot(rel, up) / depth + self._offset[1]
                if previous is not None and step % 5 < 3:
                    pygame.draw.line(screen, palette["guide"],
                                     previous, (sx, sy), 1)
                if step % points == 0 or (points >= 48 and step % (points // 8) == 0):
                    pygame.draw.line(screen, _mix(palette["guide"], palette["hero"], 0.22),
                                     (sx, sy - 2), (sx, sy + 2), 1)
                previous = (sx, sy)
        # One construction line: the scan plane through the star, dashed, with ticks.
        star_x, star_y = self._star_xy
        reach = self._screen_size[0] * 0.34
        end = (star_x + reach, star_y + reach * 0.30)
        steps = 26
        for step in range(steps):
            if step % 3 == 2:
                continue
            t0, t1 = step / steps, (step + 0.55) / steps
            pygame.draw.line(
                screen, _scale(palette["guide"], 0.85),
                (star_x + (end[0] - star_x) * t0, star_y + (end[1] - star_y) * t0),
                (star_x + (end[0] - star_x) * t1, star_y + (end[1] - star_y) * t1), 1)
        for step in range(1, 5):
            t = step / 4.0
            px = star_x + (end[0] - star_x) * t
            py = star_y + (end[1] - star_y) * t
            pygame.draw.line(screen, _mix(palette["guide"], palette["hero"], 0.22),
                             (px, py - 3), (px, py + 3), 1)
        if self._preset in ("portrait", "square"):
            # The portrait is a re-composition, not a crop: the guide runs down the
            # tall frame instead of across it (§2.5).
            top = star_y + self._star_r * 1.55
            bottom = height * 0.86
            if bottom > top:
                steps = 20
                for step in range(steps):
                    if step % 3 == 2:
                        continue
                    t0, t1 = step / steps, (step + 0.5) / steps
                    pygame.draw.line(screen, _scale(palette["guide"], 0.8),
                                     (star_x, top + (bottom - top) * t0),
                                     (star_x, top + (bottom - top) * t1), 1)
                for step in range(1, 5):
                    py = top + (bottom - top) * step / 4.0
                    pygame.draw.line(screen, palette["guide"],
                                     (star_x - 4, py), (star_x + 4, py), 1)

    def _draw_sails(self, screen, rows):
        filled = self._fill in ("xray", "panel")
        fill_alpha = 30 if self._fill == "xray" else 52
        for depth, sx, sy, size, color, alpha, weight, tx, ty, shell, points in rows:
            if filled and size >= 3.5:
                face = pygame.Surface((int(size * 4 + 6), int(size * 4 + 6)),
                                      pygame.SRCALPHA)
                ox, oy = size * 2 + 3, size * 2 + 3
                local = [(px - sx + ox, py - sy + oy) for px, py in points]
                pygame.draw.polygon(face, _rgba(_scale(color, 0.8), fill_alpha), local)
                screen.blit(face, (sx - ox, sy - oy))
            if len(points) == 2:
                pygame.draw.line(screen, color, points[0], points[1], weight)
            else:
                pygame.draw.lines(screen, color, True, points, weight)

    def _sail_outline(self, cx, cy, r, angle):
        """A thin polygonal sail: four corners, a long leading edge, a short boom."""
        ca, sa = math.cos(angle), math.sin(angle)
        shape = [(-1.15 * r, 0.20 * r), (-0.55 * r, -0.47 * r),
                 (0.28 * r, -0.33 * r), (0.95 * r, 0.10 * r), (0.55 * r, 0.52 * r)]
        return [(cx + px * ca - py * sa, cy + px * sa + py * ca) for px, py in shape]

    def _draw_sail_body(self, screen, points, *, hero_width=1):
        """
        A sail is an outline.  The fill is a deliberate mode (xray/panel), never the
        default: this is a wireframe, and the star must stay visible through it.
        """
        palette = self._palette
        if self._fill in ("xray", "panel"):
            layer = pygame.Surface(self._screen_size, pygame.SRCALPHA)
            alpha = 34 if self._fill == "xray" else 54
            pygame.draw.polygon(layer, _rgba(palette["bg_bottom"], alpha), points)
            screen.blit(layer, (0, 0))
        pygame.draw.lines(screen, _mix(palette["structure"], palette["hero"], 0.30),
                          True, points, 1)
        # the leading edge: the brightest line on a sail.  The star's limb is the
        # scene's hero; a sail's edge is allowed to be the hero only mid-transit.
        pygame.draw.line(screen, palette["hero"], points[0], points[1], hero_width)
        pygame.draw.line(screen, _scale(palette["accent"], 0.80), points[1],
                         points[2], 1)
        pygame.draw.line(screen, _scale(palette["guide"], 0.85),
                         points[0], points[2], 1)

    def _draw_hero_sail(self, screen, now):
        """
        The persistent foreground sail: a slow drift across the frame at the card's
        0.5 px/s, dark against the star, its leading edge the brightest line in the
        outer field.  A triangle wave keeps it on screen instead of gone for the
        forty minutes a real crossing would take.
        """
        if not self._hero:
            return
        width, height = self._screen_size
        span = width * 0.62
        phase = (self._time * 0.5 / span + self._hero["x0"]) % 1.0
        tri = 1.0 - abs(2.0 * phase - 1.0)
        cx = width * (0.19 + 0.62 * tri)
        cy = height * self._hero["y"] + math.sin(self._time * 0.037) * height * 0.03
        r = min(width, height) * 0.155 * self._hero["scale"]
        points = self._sail_outline(cx, cy, r, self._hero["angle"])
        self._draw_sail_body(screen, points)

    def _transit_cx(self):
        """Where the transit sail's centre is, in screen x (the eclipse uses it)."""
        if self._transit is None:
            return self._star_xy[0]
        return self._star_xy[0] + _lerp(-2.3 * self._star_r, 2.3 * self._star_r,
                                        self._transit["progress"])

    def _draw_transit_sail(self, screen, transit):
        """The signature beat: a sail crosses the star, and the star goes behind it."""
        star_x, star_y = self._star_xy
        r = self._star_r * 1.35
        progress = transit["progress"]
        cx = self._transit_cx()
        cy = star_y + _lerp(0.55 * self._star_r, -0.42 * self._star_r, progress)
        points = self._sail_outline(cx, cy, r, -0.34)
        if abs(cx - star_x) < self._star_r * 1.7:
            # Crossing the disc: backlit, so the sail reads dark against the light
            # (card: "every line dark against the light").  This overlay is the
            # shadow the sail casts, not a fill of the sail.
            left = max(0, int(min(p[0] for p in points)) - 2)
            top = max(0, int(min(p[1] for p in points)) - 2)
            box = (min(self._screen_size[0] - left,
                       max(1, int(max(p[0] for p in points) - left + 4))),
                   min(self._screen_size[1] - top,
                       max(1, int(max(p[1] for p in points) - top + 4))))
            shadow = pygame.Surface(box, pygame.SRCALPHA)
            pygame.draw.polygon(shadow, _rgba(self._palette["bg_bottom"], 128),
                                [(px - left, py - top) for px, py in points])
            screen.blit(shadow, (left, top))
            pygame.draw.lines(screen, self._palette["bg_bottom"], True, points, 2)
            pygame.draw.line(screen, _scale(self._palette["accent"], 0.62),
                             points[0], points[1], 1)
        else:
            self._draw_sail_body(screen, points, hero_width=2)

    def _draw_shadow_band(self, screen):
        """The shadow: a wide, very faint dark ring travelling outward from the star."""
        band = self._shadow_band(self._transit)
        if band is None or self._band_layer is None:
            return
        radius, width = band
        layer = self._band_layer
        layer.fill((0, 0, 0, 0))
        pygame.draw.circle(layer, (0, 0, 0, 58),
                           (int(self._star_xy[0]), int(self._star_xy[1])),
                           int(radius), max(8, int(width)))
        screen.blit(layer, (0, 0))
        rim = _scale(self._palette["guide"], 0.8)
        cx, cy = self._star_xy
        for step in range(48):
            if step % 3 == 2:
                continue
            start = TAU * step / 48.0
            end = TAU * (step + 1.1) / 48.0
            pygame.draw.line(
                screen, rim,
                (cx + math.cos(start) * radius, cy + math.sin(start) * radius),
                (cx + math.cos(end) * radius, cy + math.sin(end) * radius), 1)

    def _draw_scan(self, screen):
        """The scan tick that runs from the star to the frame edge: annotation."""
        palette = self._palette
        star_x, star_y = self._star_xy
        width, height = self._screen_size
        y = max(30, int(height * 0.70))
        x0 = max(96, int(width * 0.30))
        pygame.draw.line(screen, _scale(palette["hud_faint"], 0.85),
                         (x0, y), (width - max(20, int(width * 0.05)), y), 1)
        self._hud_rects.append(pygame.Rect(x0, y - 1, width - x0, 3))

    def _draw_scene(self, screen):
        now = self._time
        self._transit = self._transit_state()
        rows = self._project_rows(now)
        if self._background is not None:
            screen.blit(self._background, (0, 0))
        self._bloom_pass(screen, rows, now)
        self._draw_guide_rings(screen)

        far = [row for row in rows if row[0] > self._star_depth_now]
        near = [row for row in rows if row[0] <= self._star_depth_now]
        self._draw_sails(screen, far)

        if self._star_surface is not None:
            if self._transit is not None:
                # the eclipse: the disc dims by how much the sail covers it
                cover = _clamp(1.0 - abs(self._transit_cx() - self._star_xy[0])
                               / (self._star_r * 2.4), 0.0, 1.0)
                self._star_surface.set_alpha(int(255 - 88 * cover))
            else:
                self._star_surface.set_alpha(255)
            rect = self._star_surface.get_rect(center=(int(self._star_xy[0]),
                                                      int(self._star_xy[1])))
            screen.blit(self._star_surface, rect)

        self._draw_sails(screen, near)
        if self._transit is not None:
            self._draw_shadow_band(screen)
            self._draw_transit_sail(screen, self._transit)
        self._draw_hero_sail(screen, now)
        self._draw_scan(screen)
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
        # Only detail changes: the camera path and the subject stay put (§2.8).
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
                print(f"[DysonSwarm] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("DYSON SWARM // CONFIGURATION REFUSED", True,
                                self._palette["hud"])
            body = font.render((self.error or "unknown error")[:90], True,
                               self._palette["accent"])
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- stats

    def stats(self):
        if self.error or not self._rows and self._background is None:
            return {}
        width, height = self._screen_size
        corner = pygame.Rect(0, max(0, height - 32), 80, 32)
        corner_clear = all(not pygame.Rect(r).colliderect(corner) for r in self._hud_rects)
        return {
            "preset": self._preset,
            "layout": self._preset,
            "time": self._time,
            "sails": len(self._rows),
            "sail_cap": QUALITY[self._quality]["sails"],
            "collectors": self._collector_count,
            "shells": self._shells,
            "orbit_seconds": self._orbit_seconds,
            "transit_chance": self._transit_chance,
            "transit": dict(self._transit) if self._transit else None,
            "camera_drift": self._camera_drift,
            "cam_pos": self._basis_now[0] if getattr(self, "_basis_now", None) else None,
            "star": (self._star_xy, self._star_r),
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
