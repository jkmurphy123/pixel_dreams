"""Stellar Engine — a star with a planet-sized mirror held over one hemisphere.

Slow Wireframe §4.2.  A star sits in the left of the frame; a planet-sized
mirror, held over one hemisphere by a truss, reflects the star's light into a
beam that runs off to the upper right.  The whole engine precesses a few
degrees over minutes, so the only obvious motion is the beam sweeping across a
lane of dust — which is the signature beat.

The drawing is all line: no textures, no depth buffer.  Depth is carried by
distance fade, line weight, draw order and a half-resolution additive bloom.
The star — disc, limb, graticule and halo — is cached once; the mirror mesh and
truss are prebuilt in engine-local space and only their transforms animate
(§2.8: animate transforms, not topology).  Convection-cell shimmer, the beam
cone and the dust lane are the only per-frame geometry.

Camera behaviour (§2.3): orbit.  The camera arcs 3° around the engine over 180
s, looking at the star; the anchor is recomputed per aspect so the strip, the
portrait and 16:9 are each composed natively, never stretched or cropped.

Determinism (§2.9): the mirror mesh, truss, starfield, convection cells and
dust all come from `seed`; everything else is a function of accumulated
elapsed time.  A pinned seed reproduces a still exactly, an unset seed gives a
new engine on entry.

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

#: Per-quality budgets straight out of §2.8: mirror facet counts, bloom
#: downscale and the dust-particle cap.  The scene is small (an M build), so it
#: sits comfortably under the 1,500 / 3,000 / 5,000 edge ceilings.
QUALITY = {
    "low": {"facets": (6, 4), "rim": 40, "glow_div": 8, "dust": 44},
    "medium": {"facets": (9, 5), "rim": 56, "glow_div": 5, "dust": 96},
    "high": {"facets": (12, 7), "rim": 72, "glow_div": 4, "dust": 168},
}

#: Camera per aspect.  `focal` is a multiple of the short side, `dist`/`elev`
#: place the camera outside the engine, `anchor` is where the star lands, and
#: `roll` tips the whole engine (star stays at the centre of rotation) so the
#: portrait stacks the subject vertically instead of cropping the strip.
PRESETS = {
    "ultrawide": {"focal": 1.35, "dist": 3.20, "elev": 0.42, "anchor": (0.28, 0.47),
                  "roll": 0.0, "title_px": 22},
    "landscape": {"focal": 1.15, "dist": 3.40, "elev": 0.48, "anchor": (0.40, 0.47),
                  "roll": 0.0, "title_px": 30},
    "portrait": {"focal": 1.20, "dist": 3.60, "elev": 0.60, "anchor": (0.50, 0.70),
                 "roll": math.pi / 2.0, "title_px": 34},
    "square": {"focal": 1.05, "dist": 3.60, "elev": 0.55, "anchor": (0.45, 0.46),
               "roll": 0.12, "title_px": 26},
}

#: World geometry, in units where the star's radius is 0.42.  The mirror is
#: planet-sized (roughly twice the star) and sits off to one side; its centre is
#: the engine-local mirror position before the per-aspect roll and the slow
#: precession rotation.
STAR_RADIUS = 0.42
MIRROR_CENTER = (2.05, -0.05, 0.20)
MIRROR_BASE_RADIUS = 1.35
MIRROR_SAG = 0.20
#: The dish's normal in engine-local space: up-left toward the star and toward
#: the camera, so the concave face reads at a three-quarter angle.
DISH_NORMAL = (-0.60, -0.30, 0.74)
BEAM_LENGTH = 1.80
BEAM_DIR = (0.97, 0.24, 0.0)  # engine-local beam axis, normalised at import
PRECESSION_AMP = math.radians(5.0)
VIGNETTE = 0.20

#: The three palettes on the card.  The star is always the one warm accent in
#: every palette (§2.7): even in vector_blue the beam is the star's warm light.
PALETTES = {
    "amber": {
        "bg_top": (12, 7, 4), "bg_bottom": (4, 2, 0), "haze": (26, 14, 6),
        "structure": (138, 90, 43), "hero": (255, 232, 199),
        "accent": (255, 180, 91), "glow": (255, 208, 138),
        "star": (255, 226, 178), "star_core": (255, 250, 238),
        "hud": (255, 232, 199), "hud_dim": (158, 112, 62),
        "hud_faint": (66, 42, 20),
    },
    "vector_blue": {
        "bg_top": (2, 8, 20), "bg_bottom": (0, 2, 6), "haze": (8, 20, 38),
        "structure": (46, 111, 163), "hero": (216, 242, 255),
        "accent": (91, 214, 232), "glow": (143, 232, 255),
        "star": (255, 214, 160), "star_core": (255, 248, 236),
        "hud": (216, 242, 255), "hud_dim": (94, 140, 178),
        "hud_faint": (36, 62, 88),
    },
    "mono": {
        "bg_top": (7, 7, 7), "bg_bottom": (2, 2, 2), "haze": (14, 14, 14),
        "structure": (85, 85, 85), "hero": (242, 242, 242),
        "accent": (170, 170, 170), "glow": (221, 221, 221),
        "star": (232, 232, 232), "star_core": (255, 255, 255),
        "hud": (242, 242, 242), "hud_dim": (140, 140, 140),
        "hud_faint": (56, 56, 56),
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
    """A soft round halo, built once and scaled — no per-frame gradient."""
    size = max(4, int(size))
    small = pygame.Surface((48, 48), pygame.SRCALPHA)
    for y in range(48):
        for x in range(48):
            r = math.hypot((x - 23.5) / 23.5, (y - 23.5) / 23.5)
            alpha = 0 if r >= 1.0 else int(peak * (1.0 - r) ** power)
            small.set_at((x, y), _rgba(color, alpha))
    return pygame.transform.smoothscale(small, (size, size))


#: Normalised beam axis, computed once at import.
_BEAM_DIR_UNIT = _norm(BEAM_DIR)


class StellarEngineMode:
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
        self._mirror_span = 0.7
        self._precession_seconds = 300.0
        self._beam_width = 0.4
        self._show_star = True
        self._glow_strength = 0.5
        self._scanline_alpha = 4
        self._vignette = VIGNETTE
        self._title = "STELLAR ENGINE"
        self._subtitle = "MIRROR 01 · THRUST 0.004 C"

        self._time = 0.0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._background = None
        self._star_surface = None
        self._finish = None
        self._bloom = None
        self._bloom_mid = None
        self._bloom_up = None
        self._beam_layer = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}

        self._mirror_r = MIRROR_BASE_RADIUS * 0.7
        self._mirror_grid = []       # list of rows of local (x,y,z)
        self._mirror_rows = []       # row polylines: list of list-of-indices
        self._mirror_cols = []       # column polylines
        self._rim_pts = []           # local rim ring points
        self._truss = []             # list of (local a, local b, phase)
        self._convection = []        # (u, v, size, phase) in the star disc
        self._dust = []              # (fx, fy, phase, mag) in screen fractions
        self._beam_color = (255, 255, 255)

        self._cam_nominal = (0.0, 0.0, 1.0)
        self._offset = (0.0, 0.0)
        self._focal = 1.0
        self._basis_now = None
        self._star_xy = (0.0, 0.0)
        self._star_r = 40.0
        self._mirror_xy = (0.0, 0.0)
        self._beam_tip = (0.0, 0.0)
        self._beam_edges = ((0.0, 0.0), (0.0, 0.0))
        self._beam_half_px = 0.0
        self._beam_lit = 0.0
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

        self._mirror_span = self._number(cfg, "mirror_span", 0.7, 0.3, 1.4)
        self._precession_seconds = self._number(
            cfg, "precession_seconds", 300.0, 60.0, 900.0)
        self._beam_width = self._number(cfg, "beam_width", 0.4, 0.0, 1.5)
        self._show_star = self._bool(cfg, "show_star", True)
        self._glow_strength = self._number(cfg, "glow_strength", 0.5, 0.0, 1.0)
        self._scanline_alpha = self._integer(cfg, "scanline_alpha", 4, 0, 40)

        self._title = self._text(cfg, "title", "STELLAR ENGINE", 40) or "STELLAR ENGINE"
        self._subtitle = self._text(cfg, "subtitle", "MIRROR 01 · THRUST 0.004 C", 56)

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
            print(f"[StellarEngine] seed={self.seed} preset={self._preset} "
                  f"span={self._mirror_span:.2f} precession={self._precession_seconds:.0f}s "
                  f"beam={self._beam_width:.2f} quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[StellarEngine] configuration error: {exc}")

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
        self._beam_layer = None
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._metrics = None
        self._text_cache = {}
        self._time = 0.0
        self._last_error_logged = False
        self._clear()

    def _clear(self):
        self._mirror_grid = []
        self._mirror_rows = []
        self._mirror_cols = []
        self._rim_pts = []
        self._truss = []
        self._convection = []
        self._dust = []
        self._hud_rects = []

    def handle_event(self, event):
        """The controller owns input; this mode has none."""

    # ---------------------------------------------------------------- build

    def _resolve_preset(self, size):
        width, height = int(size[0]), int(size[1])
        return aspect_preset(width, height)

    def _build(self, size):
        width, height = int(size[0]), int(size[1])
        preset = self._resolve_preset((width, height))
        self._screen_size = (width, height)
        self._preset = preset
        self._layout = dict(PRESETS[preset])
        self._text_cache = {}
        self._mirror_r = MIRROR_BASE_RADIUS * self._mirror_span
        self._beam_color = _mix(self._palette["star"], self._palette["glow"], 0.35)
        self._build_mirror_mesh()
        self._build_camera()
        self._build_background()
        self._build_star()
        self._build_finish()
        self._build_bloom()
        self._beam_layer = pygame.Surface((width, height), pygame.SRCALPHA)
        self._build_hud()
        self._last_error_logged = False

    def _build_mirror_mesh(self):
        """Prebuild the dish lattice, rim ring and truss in engine-local space."""
        n0 = _norm(DISH_NORMAL)
        t1 = _norm(_cross(n0, (0.0, 0.0, 1.0)))
        t2 = _cross(t1, n0)
        rm = self._mirror_r
        sag = MIRROR_SAG
        nu, nv = QUALITY[self._quality]["facets"]
        rim_n = QUALITY[self._quality]["rim"]

        grid = []
        for j in range(nv + 1):
            v = -1.0 + 2.0 * j / nv
            row = []
            for i in range(nu + 1):
                u = -1.0 + 2.0 * i / nu
                d = u * u + v * v
                row.append((
                    MIRROR_CENTER[0] + t1[0] * u * rm + t2[0] * v * rm - n0[0] * sag * d * rm,
                    MIRROR_CENTER[1] + t1[1] * u * rm + t2[1] * v * rm - n0[1] * sag * d * rm,
                    MIRROR_CENTER[2] + t1[2] * u * rm + t2[2] * v * rm - n0[2] * sag * d * rm,
                ))
            grid.append(row)
        self._mirror_grid = grid
        self._mirror_rows = [[(j, i) for i in range(nu + 1)] for j in range(nv + 1)]
        self._mirror_cols = [[(j, i) for j in range(nv + 1)] for i in range(nu + 1)]

        rim = []
        for k in range(rim_n):
            a = TAU * k / rim_n
            u, v = math.cos(a), math.sin(a)
            rim.append((
                MIRROR_CENTER[0] + t1[0] * u * rm + t2[0] * v * rm - n0[0] * sag * rm,
                MIRROR_CENTER[1] + t1[1] * u * rm + t2[1] * v * rm - n0[1] * sag * rm,
                MIRROR_CENTER[2] + t1[2] * u * rm + t2[2] * v * rm - n0[2] * sag * rm,
            ))
        self._rim_pts = rim

        hub = _norm(MIRROR_CENTER)
        hub = (hub[0] * STAR_RADIUS * 1.02, hub[1] * STAR_RADIUS * 1.02, 0.0)
        truss = []
        struts = max(5, rim_n // 8)
        for s in range(struts):
            k = s * rim_n // struts
            truss.append((hub, rim[k], s * 0.9 + 0.3))
        # A near-mirror rim ring and two diagonals: "a few triangles and struts".
        for k in range(0, rim_n, max(2, rim_n // 8)):
            truss.append((rim[k], rim[(k + rim_n // 8) % rim_n], k * 0.4))
        self._truss = truss

        # Convection cells on the star disc (unit disc, u/v fractions).
        rng = random.Random(self.seed ^ 0xC0FF)
        cells = []
        for _ in range(18):
            a = rng.uniform(0.0, TAU)
            r = math.sqrt(rng.random()) * 0.62
            cells.append((math.cos(a) * r, math.sin(a) * r,
                          rng.uniform(0.10, 0.22), rng.uniform(0.0, TAU)))
        self._convection = cells

        rng = random.Random(self.seed ^ 0xD057)
        n = QUALITY[self._quality]["dust"]
        dust = []
        for _ in range(n):
            dust.append((rng.uniform(0.30, 0.98), rng.uniform(0.08, 0.42),
                         rng.uniform(0.0, TAU), rng.uniform(0.30, 0.95)))
        self._dust = dust

    def _build_camera(self):
        """The nominal camera and the offset that puts the star on its anchor."""
        width, height = self._screen_size
        layout = self._layout
        dist = layout["dist"]
        self._cam_nominal = (0.0, layout["elev"] * dist, dist)
        self._focal = layout["focal"] * min(width, height)
        basis = self._basis_at(self._cam_nominal)
        star_xy = self._project((0.0, 0.0, 0.0), basis, offset=(0.0, 0.0))
        ax, ay = layout["anchor"]
        self._offset = (ax * width - star_xy[0], ay * height - star_xy[1])
        self._star_xy = (star_xy[0] + self._offset[0], star_xy[1] + self._offset[1])
        depth = _dot((-self._cam_nominal[0], -self._cam_nominal[1],
                      -self._cam_nominal[2]), basis[1])
        self._star_r_nominal = self._focal * STAR_RADIUS / max(0.2, depth)

    # ---------------------------------------------------------------- camera / projection

    @staticmethod
    def _basis_for(cam, target):
        fwd = _norm((target[0] - cam[0], target[1] - cam[1], target[2] - cam[2]))
        world_up = (0.0, 1.0, 0.0)
        right = _norm(_cross(fwd, world_up))
        up = _norm(_cross(right, fwd))
        return cam, fwd, right, up

    def _basis_at(self, cam):
        return self._basis_for(cam, (0.0, 0.0, 0.0))

    def _camera_now(self):
        """A 3° arc around the engine over 180 s (§2.3 orbit, §2.4 envelope)."""
        if self._layout is None:
            return self._cam_nominal
        yaw = math.radians(1.5) * math.sin(TAU * self._time / 180.0)
        cx, cy, cz = self._cam_nominal
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        return (cx * cos_y + cz * sin_y, cy, -cx * sin_y + cz * cos_y)

    def _project(self, point, basis, offset=None):
        cam, fwd, right, up = basis
        rel = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
        depth = _dot(rel, fwd)
        if depth < 0.15:
            return None
        off = self._offset if offset is None else offset
        return (self._focal * _dot(rel, right) / depth + off[0],
                -self._focal * _dot(rel, up) / depth + off[1])

    @staticmethod
    def _rot(point, cos_a, sin_a):
        return (point[0] * cos_a - point[1] * sin_a,
                point[0] * sin_a + point[1] * cos_a,
                point[2])

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
        width, height = self._screen_size
        palette = self._palette
        rng = random.Random(self.seed ^ 0xF00D)
        count = max(60, int(width * height / 9000))
        for _ in range(count):
            x = int(rng.uniform(0, width))
            y = int(rng.uniform(0, height))
            level = rng.randint(14, 44) / 255.0
            self._background.set_at((x, y), _scale(palette["far"], level))

    def _build_star(self):
        """The star, cached: halo, corona, disc, limb and graticule.

        The limb is drawn at exactly `radius` (the projected star radius) and the
        halo reaches 1.5x that, so the surface is 3x radius on a side with the
        centre at its middle.  _draw_star scales by (current/nominal), which is
        ~1.0, so nothing is upscaled and diluted.
        """
        palette = self._palette
        radius = max(24, int(self._star_r_nominal))
        size = max(72, int(radius * 3))
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)

        surface.blit(_radial(size, palette["glow"], peak=58, power=2.9), (0, 0))
        corona = _radial(int(radius * 1.6), palette["star"], peak=66, power=2.3)
        surface.blit(corona, (centre[0] - corona.get_width() // 2,
                              centre[1] - corona.get_height() // 2))

        if self._fill in ("xray", "panel"):
            fill_alpha = 44 if self._fill == "xray" else 66
            pygame.draw.circle(surface, _rgba(palette["star"], fill_alpha),
                               centre, radius)
        pygame.draw.circle(surface, _rgba(palette["star"], 238), centre, radius, 1)
        pygame.draw.circle(surface, _rgba(palette["star_core"], 120), centre,
                           int(radius * 0.46), 1)

        # The graticule: lat/long arcs and radial ticks, quiet structure lines.
        guide = _rgba(palette["guide"], 78)
        for sw, sh in ((0.62, 0.20), (0.32, 0.66), (0.84, 0.34)):
            rect = pygame.Rect(centre[0] - radius * sw, centre[1] - radius * sh,
                               radius * sw * 2, radius * sh * 2)
            pygame.draw.ellipse(surface, guide, rect, 1)
        pygame.draw.line(surface, guide, (centre[0] - radius, centre[1]),
                         (centre[0] + radius, centre[1]), 1)
        pygame.draw.line(surface, guide, (centre[0], centre[1] - radius),
                         (centre[0], centre[1] + radius), 1)
        for step in range(8):
            angle = TAU * step / 8.0 + 0.22
            inner = radius * 1.0
            outer = radius * (1.28 if step % 2 else 1.16)
            pygame.draw.line(
                surface, _rgba(palette["glow"], 52 if step % 2 else 34),
                (centre[0] + math.cos(angle) * inner, centre[1] + math.sin(angle) * inner),
                (centre[0] + math.cos(angle) * outer, centre[1] + math.sin(angle) * outer),
                1)
        self._star_surface = surface.convert_alpha()

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
        lines = [(f"MIRROR {self._mirror_span:.2f} D", palette["hud"], 220),
                 (f"PRECESSION {self._precession_seconds:.0f} S", palette["hud_dim"], 190)]
        if self._hud_mode == "full":
            lines.append((f"BEAM {self._beam_width:.2f}", palette["hud_dim"], 175))
            lines.append((f"CAM ORBIT 3.0°", palette["hud_faint"], 150))
        return lines

    def _status_text(self):
        if self._beam_lit > 0.5:
            return "BEAM // DUST LANE", True
        return "PRECESSION · CAM 3° ARC", False

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

        status, lit = self._status_text()
        color = palette["accent"] if lit else palette["hud_dim"]
        surface = self._cached_text(status, m["status_px"], color, 205)
        rect = surface.get_rect()
        rect.topleft = (m["status_x"], m["status_y"])
        screen.blit(surface, rect)
        self._hud_rects.append(rect.copy())

    # ---------------------------------------------------------------- per-frame geometry

    def _project_scene(self):
        """Project the engine once per frame into screen coordinates."""
        t = self._time
        cam = self._camera_now()
        basis = self._basis_at(cam)
        self._basis_now = basis

        star = self._project((0.0, 0.0, 0.0), basis)
        self._star_xy = star
        self._star_r = self._focal * STAR_RADIUS / max(0.2, _dot(
            (-cam[0], -cam[1], -cam[2]), basis[1]))

        phi = self._layout["roll"] + PRECESSION_AMP * math.sin(
            TAU * t / max(1.0, self._precession_seconds))
        cos_p, sin_p = math.cos(phi), math.sin(phi)

        mirror = self._project(self._rot(MIRROR_CENTER, cos_p, sin_p), basis)
        self._mirror_xy = mirror

        b_dir = _BEAM_DIR_UNIT
        beam_world = self._rot(b_dir, cos_p, sin_p)
        tip_world = (self._rot(MIRROR_CENTER, cos_p, sin_p)[0] + beam_world[0] * BEAM_LENGTH,
                     self._rot(MIRROR_CENTER, cos_p, sin_p)[1] + beam_world[1] * BEAM_LENGTH,
                     0.0)
        tip = self._project(tip_world, basis)
        self._beam_tip = tip
        self._beam_edges = (None, None)
        self._beam_half_px = 0.0
        if self._beam_width > 0.0:
            perp_world = _norm(_cross(beam_world, (0.0, 0.0, 1.0)))
            half_world = self._beam_width * 0.95
            edge_a = self._project((
                tip_world[0] + perp_world[0] * half_world,
                tip_world[1] + perp_world[1] * half_world, 0.0), basis)
            edge_b = self._project((
                tip_world[0] - perp_world[0] * half_world,
                tip_world[1] - perp_world[1] * half_world, 0.0), basis)
            self._beam_edges = (edge_a, edge_b)
            if edge_a is not None and edge_b is not None:
                self._beam_half_px = math.hypot(
                    edge_a[0] - edge_b[0], edge_a[1] - edge_b[1]) / 2.0

        return cos_p, sin_p, basis

    def _screen_of(self, local, cos_p, sin_p, basis):
        return self._project(self._rot(local, cos_p, sin_p), basis)

    # ---------------------------------------------------------------- drawing

    def _bloom_line(self, color, a, b, width=1):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        bw, bh = self._bloom.get_size()
        sx, sy = bw / self._screen_size[0], bh / self._screen_size[1]
        level = self._glow_strength
        pygame.draw.line(self._bloom, _scale(color, 0.9 * level + 0.08),
                         (int(a[0] * sx), int(a[1] * sy)),
                         (int(b[0] * sx), int(b[1] * sy)), max(1, width))

    def _draw_guide(self, screen):
        palette = self._palette
        sx, sy = self._star_xy
        mx, my = self._mirror_xy
        if None in (sx, sy, mx, my):
            return
        cx = (sx + mx) / 2.0
        cy = (sy + my) / 2.0
        rx = max(12.0, abs(mx - sx) * 0.62)
        ry = max(12.0, abs(my - sy) * 0.62 + 18.0)
        # A dashed construction ellipse bracketing the engine (the guide role).
        steps = 56
        for k in range(steps):
            if k % 3 == 2:
                continue
            a0 = TAU * k / steps
            a1 = TAU * (k + 0.55) / steps
            pygame.draw.line(
                screen, palette["guide"],
                (cx + math.cos(a0) * rx, cy + math.sin(a0) * ry),
                (cx + math.cos(a1) * rx, cy + math.sin(a1) * ry), 1)
        # The star -> mirror construction line, dashed, with a tick at the mirror.
        steps = 22
        for k in range(steps):
            if k % 3 == 2:
                continue
            t0, t1 = k / steps, (k + 0.5) / steps
            pygame.draw.line(
                screen, _scale(palette["guide"], 0.85),
                (sx + (mx - sx) * t0, sy + (my - sy) * t0),
                (sx + (mx - sx) * t1, sy + (my - sy) * t1), 1)

    def _draw_star(self, screen):
        if not self._show_star or self._star_surface is None:
            return
        x, y = self._star_xy
        r = max(6.0, self._star_r)
        side = max(8, int(round(r * 3.0)))
        scaled = pygame.transform.smoothscale(self._star_surface, (side, side))
        screen.blit(scaled, (int(x - side // 2), int(y - side // 2)))
        # Convection-cell shimmer (60 s): faint cells pulse across the disc.
        palette = self._palette
        for u, v, size, phase in self._convection:
            cx = x + u * r * 0.92
            cy = y + v * r * 0.92
            s = size * r * 0.92
            a = 20 + int(34 * (0.5 + 0.5 * math.sin(
                TAU * self._time / 60.0 + phase)))
            color = _rgba(_mix(palette["star"], palette["glow"], 0.4), a)
            pygame.draw.polygon(screen, color, [
                (cx, cy - s), (cx + s * 0.72, cy), (cx, cy + s), (cx - s * 0.72, cy)], 1)

    def _draw_mirror(self, screen, cos_p, sin_p, basis):
        palette = self._palette
        margin = 40
        sw, sh = self._screen_size

        # Project the grid once.
        proj = [[self._screen_of(self._mirror_grid[j][i], cos_p, sin_p, basis)
                 for i in range(len(self._mirror_grid[0]))]
                for j in range(len(self._mirror_grid))]

        def _off(p):
            return p is None or p[0] < -margin or p[0] > sw + margin or \
                p[1] < -margin or p[1] > sh + margin

        # Structure role: the lattice lines.
        for row in self._mirror_rows:
            prev = None
            for j, i in row:
                p = proj[j][i]
                if p is None:
                    prev = None
                    continue
                if prev is not None:
                    if not (_off(prev) and _off(p)):
                        pygame.draw.line(screen, palette["structure"],
                                         prev, p, 1)
                prev = p
        for col in self._mirror_cols:
            prev = None
            for j, i in col:
                p = proj[j][i]
                if p is None:
                    prev = None
                    continue
                if prev is not None:
                    if not (_off(prev) and _off(p)):
                        pygame.draw.line(screen, _scale(palette["structure"], 0.82),
                                         prev, p, 1)
                prev = p

        # Hero role: the rim, the one bright edge the eye follows.
        rim = [self._screen_of(p, cos_p, sin_p, basis) for p in self._rim_pts]
        prev = None
        for p in rim:
            if p is None:
                prev = None
                continue
            if prev is not None:
                if not (_off(prev) and _off(p)):
                    pygame.draw.line(screen, palette["hero"], prev, p, 2)
                    self._bloom_line(palette["hero"], prev, p, 2)
            prev = p
        if rim and rim[0] is not None and rim[-1] is not None:
            pygame.draw.line(screen, palette["hero"], rim[-1], rim[0], 2)
            self._bloom_line(palette["hero"], rim[-1], rim[0], 2)

        # Truss: struts from the star's hub to the mirror rim, with thermal flex.
        for a, b, phase in self._truss:
            pa = self._screen_of(a, cos_p, sin_p, basis)
            pb = self._screen_of(b, cos_p, sin_p, basis)
            if pa is None or pb is None or (_off(pa) and _off(pb)):
                continue
            flex = math.sin(TAU * self._time / 40.0 + phase) * 3.0
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            mid = ((pa[0] + pb[0]) / 2 + nx * flex, (pa[1] + pb[1]) / 2 + ny * flex)
            pygame.draw.line(screen, _scale(palette["structure"], 0.9), pa, mid, 1)
            pygame.draw.line(screen, _scale(palette["structure"], 0.9), mid, pb, 1)

    def _draw_beam(self, screen):
        if self._beam_width <= 0.0 or self._beam_layer is None:
            return
        m = self._mirror_xy
        tip = self._beam_tip
        edge_a, edge_b = self._beam_edges
        if None in (m, tip, edge_a, edge_b):
            return
        palette = self._palette
        self._beam_layer.fill((0, 0, 0, 0))
        fill_alpha = 26 if self._fill == "line" else 38
        pygame.draw.polygon(self._beam_layer,
                            _rgba(self._beam_color, fill_alpha),
                            [m, edge_a, edge_b])
        screen.blit(self._beam_layer, (0, 0))
        # Crisp cone edges + the bright core ray, then their bloom.
        pygame.draw.line(screen, _scale(palette["accent"], 0.75), m, edge_a, 1)
        pygame.draw.line(screen, _scale(palette["accent"], 0.75), m, edge_b, 1)
        pygame.draw.line(screen, self._beam_color, m, tip, 1)
        self._bloom_line(self._beam_color, m, tip, 1)
        self._bloom_line(palette["accent"], m, edge_a, 1)
        self._bloom_line(palette["accent"], m, edge_b, 1)

    def _draw_dust(self, screen):
        self._beam_lit = 0.0
        if self._beam_width <= 0.0:
            return
        palette = self._palette
        width, height = self._screen_size
        m = self._mirror_xy
        tip = self._beam_tip
        if m is None or tip is None:
            return
        mx, my = m
        dx, dy = tip[0] - mx, tip[1] - my
        seg_len = math.hypot(dx, dy) or 1.0
        half = self._beam_half_px * 0.85
        for fx, fy, phase, mag in self._dust:
            x = ((fx + self._time * 0.5 / max(1, width)) % 1.0) * width
            y = fy * height + math.sin(self._time * 0.05 + phase) * 2.0
            # Distance from the dust point to the beam axis segment.
            wx, wy = x - mx, y - my
            tpos = _clamp((wx * dx + wy * dy) / (seg_len * seg_len), 0.0, 1.0)
            cx, cy = mx + dx * tpos, my + dy * tpos
            d = math.hypot(x - cx, y - cy)
            lit = 0.0 if half <= 0.0 else max(0.0, 1.0 - d / (half * 1.3))
            if lit > self._beam_lit:
                self._beam_lit = lit
            base = 0.22 + 0.30 * mag
            if lit > 0.02:
                color = _mix(_scale(palette["far"], base),
                             self._beam_color, lit * (0.55 + 0.35 * mag))
                pygame.draw.circle(screen, color, (int(x), int(y)), 1)
                if lit > 0.35:
                    nx, ny = -dy / seg_len, dx / seg_len
                    streak = 2 + int(4 * lit)
                    pygame.draw.line(
                        screen, color,
                        (int(x - nx * streak), int(y - ny * streak)),
                        (int(x + nx * streak), int(y + ny * streak)), 1)
            else:
                color = _scale(palette["far"], base)
                if color != (0, 0, 0):
                    screen.set_at((int(x), int(y)), color)

    def _draw_scene(self, screen):
        cos_p, sin_p, basis = self._project_scene()
        if self._background is not None:
            screen.blit(self._background, (0, 0))

        self._draw_guide(screen)
        if self._bloom is not None:
            self._bloom.fill((0, 0, 0))
        self._draw_star(screen)
        self._draw_beam(screen)
        self._draw_mirror(screen, cos_p, sin_p, basis)
        self._draw_dust(screen)
        self._bloom_pass(screen)

        if self._finish is not None:
            screen.blit(self._finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _bloom_pass(self, screen):
        if self._bloom is None or self._glow_strength <= 0.0:
            return
        width, height = self._screen_size
        if self._quality == "high":
            pygame.transform.smoothscale(self._bloom, (width, height), self._bloom_up)
        else:
            pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                         self._bloom_mid)
            pygame.transform.scale(self._bloom_mid, (width, height), self._bloom_up)
        screen.blit(self._bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

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
                print(f"[StellarEngine] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["bg_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("STELLAR ENGINE // CONFIGURATION REFUSED", True,
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
            "mirror_span": self._mirror_span,
            "precession_seconds": self._precession_seconds,
            "beam_width": self._beam_width,
            "show_star": self._show_star,
            "beam_lit": self._beam_lit,
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

