# controlpanel/controls/arcane.py
#
# Arcane control types for the "arcane laboratory" freeform layouts: candle flames,
# drifting embers, floating orbs (phase 1), then runes / smoke (phase 2) and arcs /
# potions (phase 3). See designs/ARCANE_LAB_DESIGN.md.
#
# Everything here is drawn procedurally: no sprites, no fonts, no images. A freeform
# layout never blits sprites, so these classes are pure overlay code on top of the
# artwork.
#
# Three rules were MEASURED before this module was written (designs/arcane_proto/
# arcane_spike.py, design §5) and each one is the reason a line below looks the way it
# does:
#
#   * Every cached surface is keyed by BUCKETED, QUANTISED inputs. A glow cache keyed by
#     the exact colour was a cache miss per particle: 120 embers cost 493 ms/frame. Same
#     pool, quantised keys: 0.9 ms.
#   * Additive blits (BLEND_RGB_ADD) are for LIGHT only. A sphere blitted additively
#     clips to a flat white disc with a hard ring, so bodies are alpha-blended and only
#     their halos are added. Halos are capped at a fraction of the colour because
#     overlapping additive layers saturate to white long before they look bright.
#   * Nothing allocates a Surface in update()/draw_overlay(). Scratch layers live as long
#     as the geometry, and the drawing is clipped to the control's own rect so a halo
#     cannot leak outside the box the alignment editor is positioning.

import math
import random

import pygame

from .base import Control

#: Class defaults. A layout's "color" (or the type's own *_rgb key) wins over these, so a
#: control dropped into an existing layout looks arcane before anyone picks a colour.
CANDLE_RGB = (255, 170, 80)
EMBER_RGB = (255, 150, 90)
ORB_RGB = (120, 226, 220)
RUNE_RGB = (176, 148, 255)
ARC_RGB = (208, 186, 255)
POTION_RGB = (150, 220, 200)
EYE_RGB = (120, 240, 140)
SMOKE_RGB = (150, 160, 190)

#: Peak additive contribution of a halo, as a fraction of its colour. 1.0 let two
#: overlapping halos clip to white (measured); 0.42 reads as light and still stacks.
GLOW_PEAK = 0.42

_MASTER = 64                      # px of the gradient masters (smoothscaled up, cached)
_GLOW_CACHE: dict = {}
_GLOW_CACHE_MAX = 256
_MASTER_CACHE: dict = {}          # quantised colour -> 64 px radial halo master
_SPHERE_MANAGER: dict = {}        # quantised colour -> 96 px sphere master
_SPHERE_CACHE: dict = {}
_SPHERE_CACHE_MAX = 96


# ---------------------------------------------------------------- value helpers


def _num(value, default: float) -> float:
    """
    A spec value as a float, or the default.

    Never raises: these values can come from the panel's own form, and an exception while a
    control is being BUILT leaves the whole mode with no compositor at all — a black wall
    instead of one wrong-looking control.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if v != v or v in (float("inf"), float("-inf")):
        return float(default)
    return v


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


def _quantise(color):
    """A colour snapped to 32-level steps — the cache key that makes halos reusable."""
    return tuple(min(255, 32 * round(float(c) / 32.0)) for c in color)


def _level8(level: float) -> float:
    """
    A brightness snapped to eighths.

    Deliberate: without it, a fading particle asks for a new colour on every frame, which is
    the cache-miss-per-particle bug in its other form. Eight steps is more than the eye can
    separate on a 60 px glow.
    """
    return round(_clamp(level, 0.0, 1.0) * 8.0) / 8.0


def _keep(cache: dict, key, surf, limit: int) -> pygame.Surface:
    if len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = surf
    return surf


# ---------------------------------------------------------------- flicker


def _hash01(n: float) -> float:
    """Deterministic 0..1 from a number: no RNG state, no allocation."""
    v = math.sin(n * 12.9898) * 43758.5453
    return v - math.floor(v)


def flicker(t: float, phase: float, rate: float = 1.0, depth: float = 0.22) -> float:
    """
    A brightness multiplier around 1.0 for firelight.

    Three incommensurate sines give the lazy flutter; a sample-and-hold dip every ~1/12 s
    gives the gutter. A single sine reads as a pulsing LED, which is the one thing a candle
    must not look like. Deterministic in (t, phase), so a screenshot of a pinned seed is
    reproducible.
    """
    s = (math.sin(t * 6.1 * rate + phase * 3.1) * 0.50
         + math.sin(t * 9.7 * rate + phase * 7.3) * 0.30
         + math.sin(t * 2.3 * rate + phase * 11.9) * 0.20)
    v = 1.0 - depth * (0.5 + 0.5 * s)
    if _hash01(int(t * 12.0) + phase * 5.0) < 0.14:
        v *= 0.74
    return v


# ---------------------------------------------------------------- cached surfaces


def _radial_master(color) -> pygame.Surface:
    """The one per-colour radial gradient, at the small master size."""
    key = _quantise(color)
    master = _MASTER_CACHE.get(key)
    if master is not None:
        return master
    n = _MASTER
    master = pygame.Surface((n, n), pygame.SRCALPHA)
    master.fill((0, 0, 0, 0))
    half = n / 2.0
    for y in range(n):
        for x in range(n):
            d = math.hypot(x + 0.5 - half, y + 0.5 - half) / half
            if d >= 1.0:
                continue
            a = GLOW_PEAK * (1.0 - d) ** 2.6
            master.set_at((x, y), (int(color[0] * a), int(color[1] * a), int(color[2] * a), 255))
    return _keep(_MASTER_CACHE, key, master, _GLOW_CACHE_MAX)


def glow_surface(color, radius: float) -> pygame.Surface:
    """
    An additive halo, premultiplied so it can be blitted with BLEND_RGB_ADD.

    Keyed by (quantised colour, 8 px radius bucket): a 70 px halo and a 74 px halo share one
    surface, and a per-mote dimmed colour does not create a new entry per frame.
    """
    bucket = max(8, int(radius / 8.0) * 8)
    key = (_quantise(color), bucket)
    surf = _GLOW_CACHE.get(key)
    if surf is None:
        surf = pygame.transform.smoothscale(_radial_master(color), (bucket * 2, bucket * 2))
        _keep(_GLOW_CACHE, key, surf, _GLOW_CACHE_MAX)
    return surf


def add_glow(surface, color, center, radius: float, level: float = 1.0) -> None:
    """Additive light. Nothing is built here: the cache is keyed on quantised inputs."""
    radius = _num(radius, 0.0)
    level = _level8(level)
    if radius < 3.0 or level <= 0.0:
        return
    dim = tuple(int(c * level) for c in color)
    surf = glow_surface(dim, radius)
    surface.blit(surf, (int(center[0] - surf.get_width() / 2),
                        int(center[1] - surf.get_height() / 2)),
                 special_flags=pygame.BLEND_RGB_ADD)


def sphere_surface(color, diameter: float) -> pygame.Surface:
    """
    A glowing BODY: radial limb darkening, a specular highlight, an antialiased limb.

    Alpha-blended by the caller, never added: an additive body loses its form and clips to a
    flat white shape (measured on the orb in P0).

    The 96 px master is cached PER COLOUR: a breathing orb walks through several size buckets, and
    rebuilding the master for each one put a 96×96 surface into the steady-state draw path (found by
    tests/test_arcane.py's allocation test).
    """
    bucket = max(8, int(diameter / 8.0) * 8)
    key = (_quantise(color), bucket)
    surf = _SPHERE_CACHE.get(key)
    if surf is None:
        master = _SPHERE_MANAGER.get(_quantise(color))
        if master is None:
            n = 96
            master = pygame.Surface((n, n), pygame.SRCALPHA)
            master.fill((0, 0, 0, 0))
            half = n / 2.0
            for y in range(n):
                for x in range(n):
                    dx = (x + 0.5 - half) / half
                    dy = (y + 0.5 - half) / half
                    dist = math.hypot(dx, dy)
                    if dist >= 1.0:
                        continue
                    edge = min(1.0, (1.0 - dist) / 0.06)
                    shade = 0.30 + 0.70 * (1.0 - dist) ** 0.55
                    spec = max(0.0, 1.0 - math.hypot(dx + 0.34, dy + 0.38) / 0.52) ** 2.2
                    r = min(255, int(color[0] * shade + 255.0 * spec * 0.85))
                    g = min(255, int(color[1] * shade + 255.0 * spec * 0.85))
                    b = min(255, int(color[2] * shade + 255.0 * spec * 0.85))
                    master.set_at((x, y), (r, g, b, int(255 * edge)))
            _keep(_SPHERE_MANAGER, _quantise(color), master, _SPHERE_CACHE_MAX)
        surf = pygame.transform.smoothscale(master, (bucket, bucket))
        _keep(_SPHERE_CACHE, key, surf, _SPHERE_CACHE_MAX)
    return surf



_SOFT: dict = {}
_SOFT_MAX = 96


def soft_dot(color, radius: float) -> pygame.Surface:
    """
    A soft-edged puff with a per-pixel alpha falloff.

    Used for smoke: pygame's draw functions REPLACE the alpha of an SRCALPHA surface, so overlapping
    circles do not accumulate and a plume built from them comes out as thin wires. A BLIT of this
    surface blends, so a chain of overlapping puffs thickens into smoke.
    """
    bucket = max(8, int(radius / 8) * 8)
    key = (_quantise(color), bucket)
    surf = _SOFT.get(key)
    if surf is None:
        n = 64
        master = pygame.Surface((n, n), pygame.SRCALPHA)
        master.fill((0, 0, 0, 0))
        half = n / 2.0
        for y in range(n):
            for x in range(n):
                d = math.hypot(x + 0.5 - half, y + 0.5 - half) / half
                if d >= 1.0:
                    continue
                a = int(155 * (1.0 - d) ** 1.8)
                if a:
                    master.set_at((x, y), (color[0], color[1], color[2], a))
        surf = pygame.transform.smoothscale(master, (bucket * 2, bucket * 2))
        _keep(_SOFT, key, surf, _SOFT_MAX)
    return surf


# ---------------------------------------------------------------- particles


class ParticlePool:
    """
    A fixed set of motes, recycled in place.

    Parallel lists rather than objects: no allocation after __init__, no per-frame garbage,
    and `step()` is a plain loop over floats. Indices wrap, so the pool is bounded by the
    layout author's `count`, not by time.
    """

    __slots__ = ("n", "x", "y", "vy", "sway", "phase", "radius", "bright")

    def __init__(self, n: int, rng, width: float, height: float,
                 rise=(18.0, 58.0), sway=(2.0, 14.0), size=(1.4, 4.2)):
        self.n = max(1, int(n))
        self.x = [0.0] * self.n
        self.y = [0.0] * self.n          # 0..1 of the box height, 0 = bottom
        self.vy = [0.0] * self.n
        self.sway = [0.0] * self.n
        self.phase = [0.0] * self.n
        self.radius = [0.0] * self.n
        self.bright = [1.0] * self.n
        self.reseed(rng, width, height, rise, sway, size, scatter=1.0)

    def reseed(self, rng, width, height, rise, sway, size, scatter: float = 0.0) -> None:
        """(Re)populate the pool for a box of this size; `scatter` spreads the heights."""
        for i in range(self.n):
            self.x[i] = rng.uniform(0.0, 1.0)          # fraction of the width
            self.y[i] = rng.uniform(0.0, 1.0) if scatter else 0.0
            self.vy[i] = rng.uniform(*rise)
            self.sway[i] = rng.uniform(*sway)
            self.phase[i] = rng.uniform(0.0, math.tau)
            self.radius[i] = rng.uniform(*size)

    def step(self, dt: float, height: float) -> None:
        """Rise, wrapping at the top. `height` is the box height in px."""
        span = max(1.0, float(height))
        for i in range(self.n):
            self.y[i] += self.vy[i] * dt / span
            if self.y[i] > 1.0:
                self.y[i] -= 1.0
                self.phase[i] += 1.7                    # a different sway on the next pass


# ---------------------------------------------------------------- candle flames


class CandleFlameControl(Control):
    """
    A guttering candle flame: three nested profiles (smoky edge, warm body, white-hot core)
    with a soft halo behind them. Flicker is three incommensurate sines plus a random
    gutter, so it reads as fire rather than as a pulsing light.

    `count` spreads a row of independent flames across the box — one control is a candle, a
    rack, a chandelier ring or a candelabra arm, which is cheaper than many controls and
    keeps the whole assembly aligned as one thing.

    Layout overrides: flame_rgb, count, flicker, glow, lean.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("flame_rgb", CANDLE_RGB)
        spec = self.spec
        self.count = int(_clamp(_num(spec.get("count", 1), 1.0), 1, 9))
        self.rate = _clamp(_num(spec.get("flicker", 1.0), 1.0), 0.1, 4.0)
        self.lean = _clamp(_num(spec.get("lean", 0.35), 0.35), 0.0, 1.0)
        self.glow = _clamp(_num(spec.get("glow", 0.9), 0.9), 0.0, 1.0)
        self.t = 0.0
        self.phases = [ctx.rng.uniform(0.0, math.tau) for _ in range(self.count)]
        self.levels = [1.0] * self.count
        self._recompute_geometry()          # base __init__ ran it before count/glow existed

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)
        # The halo must die out before the box edge: the drawing is clipped to the rect, and a
        # halo still bright at the edge would show the clip as a hard square.
        glow = float(getattr(self, "glow", 0.9))
        count = max(1, int(getattr(self, "count", 1)))
        self._halo_r = min(self._w / float(count), min(self._w, self._h)) * 0.5 * glow

    def update(self, dt: float):
        self.t += dt
        for i in range(self.count):
            self.levels[i] = flicker(self.t, self.phases[i], self.rate)

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            # 1) the light goes down first, so the bodies sit inside it
            for i in range(self.count):
                lv = self.levels[i]
                if self._halo_r >= 3.0 and lv > 0.05:
                    cx = x + w * (i + 0.5) / self.count
                    add_glow(surface, self.color, (cx, y + h * 0.55), self._halo_r, 0.55 * lv)

            # 2) the flame bodies, on the scratch layer in LOCAL coordinates
            self._scratch.fill((0, 0, 0, 0))
            for i in range(self.count):
                lv = self.levels[i]
                fx = w * (i + 0.5) / self.count
                fh = h * 0.62 * lv
                fw = min(w / float(self.count) * 0.55, fh * 0.42)
                sway = math.sin(self.t * 2.6 + self.phases[i]) * self.lean * fw * 0.5
                base_y = h * 0.92
                for scale, rgb, alpha in ((1.00, (255, 120, 40), 70),
                                          (0.66, (255, 178, 90), 150),
                                          (0.36, (255, 244, 220), 220)):
                    self._flame_polygon(fx, base_y, fw * scale, fh * scale, sway, rgb, alpha)
            surface.blit(self._scratch, (x, y))
        finally:
            surface.set_clip(clip)

    def _flame_polygon(self, fx, base_y, half_w, height, sway, rgb, alpha):
        """One teardrop: a curved left flank and its mirror, narrowing to a point."""
        left, right = [], []
        steps = 7
        for k in range(steps + 1):
            u = k / steps
            taper = math.sin(math.pi * (0.10 + 0.85 * u)) ** 0.85
            half = half_w * taper * (1.0 - u) ** 0.35
            yy = base_y - height * u
            xx = fx + sway * u
            left.append((xx - half, yy))
            right.append((xx + half, yy))
        pygame.draw.polygon(self._scratch, (*rgb, alpha), left + right[::-1])


# ---------------------------------------------------------------- embers


class EmberFieldControl(Control):
    """
    Slow motes of light drifting upward and dying out, swaying as they rise.

    Sized to cover the whole artwork it turns a still painting into a room with air in it;
    sized small it is a brazier's sparks. The pool is fixed and recycled, so cost is set by
    `count` and never grows.

    Layout overrides: ember_rgb, count, rise, sway, mote, glow.

    The mote size is `mote`, NOT `size`: in a freeform layout `size` is the control's
    box, and one key meaning two things is the bug that blacked out the whole panel once.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("ember_rgb", EMBER_RGB)
        spec = self.spec
        self.count = int(_clamp(_num(spec.get("count", 90), 90.0), 1, 400))
        self.rise = _clamp(_num(spec.get("rise", 34.0), 34.0), 4.0, 160.0)
        self.sway = _clamp(_num(spec.get("sway", 8.0), 8.0), 0.0, 40.0)
        self.mote = _clamp(_num(spec.get("mote", 2.6), 2.6), 0.6, 8.0)
        self.glow = _clamp(_num(spec.get("glow", 3.4), 3.4), 1.0, 8.0)
        self.t = 0.0
        x, y, w, h = self.rect
        self.pool = ParticlePool(self.count, ctx.rng, w, h,
                                 rise=(self.rise * 0.55, self.rise * 1.45),
                                 sway=(self.sway * 0.3, self.sway),
                                 size=(self.mote * 0.55, self.mote * 1.45))
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)

    def update(self, dt: float):
        self.t += dt
        self.pool.step(dt, self._h)

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            for i in range(self.pool.n):
                u = self.pool.y[i]
                if u >= 1.0:
                    continue
                age = math.sin(math.pi * _clamp(u, 0.0, 1.0))       # fade in and out
                if age <= 0.02:
                    continue
                tw = 0.75 + 0.25 * math.sin(self.t * 3.1 + self.pool.phase[i])
                px = x + (self.pool.x[i] * w
                          + math.sin(self.t * 0.9 + self.pool.phase[i]) * self.pool.sway[i])
                py = y + h - u * h
                add_glow(surface, self.color, (px, py),
                         self.pool.radius[i] * self.glow, age * tw * 0.7)
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- floating orbs


class FloatingOrbControl(Control):
    """
    A floating sphere of light: limb-darkened body, specular highlight and a soft halo,
    drifting on a slow Lissajous path inside its box and breathing as it goes.

    `count` fills the box with a swarm, spread around an ellipse with independent phases —
    the same class is one scrying orb or a handful of motes of power.

    Layout overrides: orb_rgb, count, drift, pulse, glow.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("orb_rgb", ORB_RGB)
        spec = self.spec
        self.count = int(_clamp(_num(spec.get("count", 1), 1.0), 1, 5))
        self.drift = _clamp(_num(spec.get("drift", 0.18), 0.18), 0.0, 0.45)
        self.pulse = _clamp(_num(spec.get("pulse", 0.05), 0.05), 0.0, 0.25)
        self.glow = _clamp(_num(spec.get("glow", 0.85), 0.85), 0.0, 1.0)
        self.t = 0.0
        self.phases = [ctx.rng.uniform(0.0, math.tau) for _ in range(self.count)]
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        shorter = float(min(self._w, self._h))
        count = max(1, int(getattr(self, "count", 1)))
        # one orb owns most of the box; a swarm shares it
        self._radius = shorter * (0.42 if count == 1 else 0.19)
        self._rx = max(0.0, self._w / 2.0 - self._radius)
        self._ry = max(0.0, self._h / 2.0 - self._radius)
        glow = float(getattr(self, "glow", 0.85))
        self._halo_r = shorter * 0.5 * glow

    def update(self, dt: float):
        self.t += dt

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            cx0, cy0 = x + w / 2.0, y + h / 2.0
            for i in range(self.count):
                phase = self.phases[i]
                if self.count == 1:
                    ox = math.sin(self.t * 0.55 + phase) * self._rx * self.drift
                    oy = math.sin(self.t * 0.37 + phase * 2.1) * self._ry * self.drift
                else:
                    ang = math.tau * i / self.count + self.t * 0.18
                    ox = math.cos(ang) * self._rx * 0.7 + math.sin(self.t * 0.5 + phase) * self._rx * 0.2
                    oy = math.sin(ang) * self._ry * 0.7 + math.sin(self.t * 0.41 + phase) * self._ry * 0.2
                cx, cy = cx0 + ox, cy0 + oy
                breathe = 1.0 + self.pulse * math.sin(self.t * 0.9 + phase * 1.7)
                r = self._radius * breathe
                if self._halo_r >= 3.0:
                    add_glow(surface, self.color, (cx, cy), min(self._halo_r, self._rx + r), 0.5)
                body = sphere_surface(self.color, r * 2.0)
                surface.blit(body, (int(cx - body.get_width() / 2),
                                    int(cy - body.get_height() / 2)))
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- glyphs


#: Rune polylines in unit space. Angular strokes only: they read as writing rather than as
#: decoration at 20 px and up, and no font is involved (a font would also have to carry every
#: alphabet's worth of shapes for nothing).
GLYPHS = [
    [[(0.30, 0.10), (0.30, 0.90)], [(0.30, 0.10), (0.75, 0.45), (0.30, 0.80)]],
    [[(0.25, 0.10), (0.25, 0.90)], [(0.25, 0.10), (0.75, 0.10)], [(0.25, 0.50), (0.70, 0.85)]],
    [[(0.25, 0.90), (0.25, 0.30), (0.60, 0.10), (0.80, 0.45)], [(0.60, 0.10), (0.60, 0.60)]],
    [[(0.20, 0.20), (0.80, 0.20)], [(0.50, 0.20), (0.50, 0.90)], [(0.34, 0.62), (0.66, 0.62)]],
    [[(0.20, 0.10), (0.50, 0.50), (0.80, 0.10)], [(0.50, 0.50), (0.50, 0.90)]],
    [[(0.30, 0.10), (0.70, 0.90)], [(0.70, 0.10), (0.30, 0.90)]],
    [[(0.50, 0.10), (0.50, 0.90)], [(0.50, 0.10), (0.80, 0.35)], [(0.50, 0.45), (0.22, 0.20)]],
    [[(0.25, 0.90), (0.25, 0.35), (0.50, 0.10), (0.75, 0.35), (0.75, 0.90)],
     [(0.25, 0.62), (0.75, 0.62)]],
    [[(0.20, 0.70), (0.50, 0.10), (0.80, 0.70)], [(0.35, 0.48), (0.65, 0.48)]],
    [[(0.30, 0.10), (0.30, 0.55), (0.70, 0.30)], [(0.30, 0.55), (0.70, 0.90)]],
    [[(0.20, 0.50), (0.50, 0.10), (0.80, 0.50), (0.50, 0.90), (0.20, 0.50)],
     [(0.35, 0.50), (0.65, 0.50)]],
    [[(0.25, 0.20), (0.75, 0.20), (0.25, 0.80), (0.75, 0.80)]],
]


def draw_glyph(surface, glyph, center, size: float, angle: float, color, width: int) -> None:
    """One rune: rotate its unit-space polylines about `center` and stroke them."""
    ca, sa = math.cos(angle), math.sin(angle)
    for stroke in glyph:
        pts = []
        for ux, uy in stroke:
            lx = (ux - 0.5) * size
            ly = (uy - 0.5) * size
            pts.append((center[0] + lx * ca - ly * sa, center[1] + lx * sa + ly * ca))
        if len(pts) > 1:
            pygame.draw.lines(surface, color, False, pts, max(1, int(width)))


# ---------------------------------------------------------------- runes


class RuneCircleControl(Control):
    """
    Concentric rings of glyphs, counter-rotating at different speeds, with a travelling
    brightness wave running around each ring and a faint additive glow underneath.

    A ritual circle, a sigil frame around a portal, the face of an astrolabe: the ring count,
    glyph count, spin and radius are all spec keys, so one class serves all three.

    Layout overrides: rune_rgb, rings, glyphs, glyph, radius, spin, pulse, glow, aspect,
    upright, guides.

    `aspect` squashes the rings vertically (1.0 = a circle), which is what a sigil painted on a FLOOR
    needs: the artwork draws it in perspective, and a circle laid over an ellipse puts half its glyphs
    on the bare floor. `upright` keeps the glyphs vertical instead of turning each one to face outward,
    which is how floor runes read.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("rune_rgb", RUNE_RGB)
        spec = self.spec
        self.rings = int(_clamp(_num(spec.get("rings", 3), 3.0), 1, 4))
        self.glyphs = int(_clamp(_num(spec.get("glyphs", 16), 16.0), 3, 40))
        self.radius = _clamp(_num(spec.get("radius", 0.92), 0.92), 0.2, 1.0)
        self.spin = _clamp(_num(spec.get("spin", 12.0), 12.0), -90.0, 90.0)
        self.pulse = _clamp(_num(spec.get("pulse", 0.16), 0.16), 0.0, 0.5)
        self.glow = _clamp(_num(spec.get("glow", 0.35), 0.35), 0.0, 1.0)
        self.aspect = _clamp(_num(spec.get("aspect", 1.0), 1.0), 0.12, 1.0)
        self.upright = bool(spec.get("upright", False))
        # glyph size as a fraction of the ring's shorter axis; a floor band needs smaller glyphs
        # than a big upright ring, and `guides` draws the faint ring outlines (off over painted art)
        self.glyph = _clamp(_num(spec.get("glyph", 0.20), 0.20), 0.05, 0.5)
        self.guides = bool(spec.get("guides", True))
        self.t = 0.0
        self._offsets = [ctx.rng.uniform(0.0, math.tau) for _ in range(self.glyphs)]
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self.center = (x + w / 2.0, y + h / 2.0)
        # the rings are drawn as an ellipse: rx from the box width, ry = rx * aspect (<= 1)
        radius = float(getattr(self, "radius", 0.92))
        aspect = float(getattr(self, "aspect", 1.0))
        self._rx = (w / 2.0) * radius
        self._ry = min(h / 2.0, self._rx * aspect)

    def update(self, dt: float):
        self.t += dt

    def draw_overlay(self, surface):
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            breathing = 1.0 + self.pulse * math.sin(self.t * 0.8)
            if self.glow > 0.02:
                add_glow(surface, self.color, self.center,
                         max(self._rx, self._ry) * 1.05, self.glow * breathing)
            for ring in range(self.rings):
                frac = (1.0 - 0.26 * ring) * breathing
                rx = self._rx * frac
                ry = self._ry * frac
                speed = math.radians(self.spin) * (1 if ring % 2 == 0 else -1) * (1.0 + 0.3 * ring)
                size = max(7.0, min(rx, ry * 1.6) * float(getattr(self, "glyph", 0.20)))
                if getattr(self, "guides", True):
                    guide = pygame.Rect(int(self.center[0] - rx), int(self.center[1] - ry),
                                        max(2, int(rx * 2)), max(2, int(ry * 2)))
                    pygame.draw.ellipse(surface, tuple(int(c * 0.16) for c in self.color), guide, 1)
                count = max(3, self.glyphs - 2 * ring)
                for k in range(count):
                    ang = math.tau * k / count + self.t * speed
                    wave = max(0.0, math.sin(math.tau * (k / count * 2.0 - self.t * 0.25)))
                    bright = 0.34 + 0.66 * wave
                    col = tuple(int(c * bright) for c in self.color)
                    pos = (self.center[0] + math.cos(ang) * rx,
                           self.center[1] + math.sin(ang) * ry)
                    rot = 0.0 if getattr(self, "upright", False) else ang + math.pi / 2
                    draw_glyph(surface, GLYPHS[(k * 5 + ring * 3) % len(GLYPHS)], pos, size,
                               rot, col, max(1, size * 0.12))
        finally:
            surface.set_clip(clip)


class RuneLineControl(Control):
    """
    A line of runes lit in sequence by a travelling flare — an inscription being read along a
    desk edge, an arch band, a book page or a rim.

    Layout overrides: rune_rgb, count, speed, orient ("h" or "v"), hold, glow.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("rune_rgb", RUNE_RGB)
        spec = self.spec
        self.count = int(_clamp(_num(spec.get("count", 8), 8.0), 1, 32))
        self.speed = _clamp(_num(spec.get("speed", 0.4), 0.4), 0.02, 2.0)
        self.orient = str(spec.get("orient", "h")).strip().lower()
        self.hold = _clamp(_num(spec.get("hold", 0.35), 0.35), 0.0, 1.0)
        self.glow = _clamp(_num(spec.get("glow", 0.5), 0.5), 0.0, 1.0)
        self.t = 0.0
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        vertical = getattr(self, "orient", "h") == "v"
        count = max(1, int(getattr(self, "count", 8)))
        span = self._h if vertical else self._w
        cross = self._w if vertical else self._h
        self._size = max(7.0, min(span / float(count) * 0.78, cross * 0.78))

    def update(self, dt: float):
        self.t += dt

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            vertical = self.orient == "v"
            span = h if vertical else w
            for k in range(self.count):
                u = (k + 0.5) / self.count
                pos = ((x + w / 2.0, y + span * u) if vertical else (x + span * u, y + h / 2.0))
                phase = (u * 2.0 - self.t * self.speed) % 1.0
                lit = max(0.0, 1.0 - abs(phase - 0.5) * 3.0)
                bright = 0.26 + 0.74 * lit
                if self.glow > 0.02 and lit > 0.35:
                    add_glow(surface, self.color, pos, self._size * 0.9, self.glow * lit)
                col = tuple(int(c * bright) for c in self.color)
                draw_glyph(surface, GLYPHS[k % len(GLYPHS)], pos, self._size,
                           math.pi / 2 if vertical else 0.0, col, max(1, self._size * 0.12))
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- smoke


class SmokeWispControl(Control):
    """
    A few curling ribbons of smoke, widening and fading as they rise — incense, a cauldron's
    steam, mist over the floor.

    Drawn on a scratch layer the size of the box so the alpha falloff survives the blit: pygame's
    draw functions ignore alpha on an opaque surface, which would turn smoke into wires.

    Layout overrides: smoke_rgb, wisps, drift, speed, fade.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("smoke_rgb", SMOKE_RGB)
        spec = self.spec
        self.wisps = int(_clamp(_num(spec.get("wisps", 2), 2.0), 1, 4))
        self.drift = _clamp(_num(spec.get("drift", 0.5), 0.5), 0.0, 1.0)
        self.speed = _clamp(_num(spec.get("speed", 1.0), 1.0), 0.1, 3.0)
        self.fade = _clamp(_num(spec.get("fade", 0.75), 0.75), 0.1, 1.0)
        self.t = 0.0
        self.phases = [ctx.rng.uniform(0.0, math.tau) for _ in range(self.wisps)]
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)

    def update(self, dt: float):
        self.t += dt

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            self._scratch.fill((0, 0, 0, 0))
            steps = 22
            for i in range(self.wisps):
                base_x = w * (0.5 if self.wisps == 1 else 0.20 + 0.60 * i / (self.wisps - 1))
                phase = self.phases[i]
                # `fade` = how much of the column's height the plume survives: at 0.8 it thins out
                # well before the top, which is what makes it look like it is dissipating.
                top = max(0.25, 1.0 - self.fade)
                for k in range(steps + 1):
                    u = k / steps
                    if u > top:
                        break
                    rise = h * (0.96 - 0.90 * u)
                    sway = (math.sin(u * 1.7 + self.t * 1.2 * self.speed + phase)
                            * w * 0.14 * self.drift * (0.25 + u))
                    curl = math.sin(u * 6.5 - self.t * 0.8 * self.speed + phase * 2.0) * w * 0.015
                    # a per-puff jitter so the column is ragged rather than a smooth band
                    jitter = (math.sin((k * 7 + i * 13) * 1.7 + self.t * 2.1) * w * 0.012
                              + _hash01(k * 3.1 + i * 5.7 + int(self.t * 2.0)) * w * 0.02 - w * 0.01)
                    px = base_x + sway + curl + jitter + u * u * w * 0.05
                    radius = max(8.0, w * 0.026 * (0.7 + 3.4 * u))     # flares as it rises, like smoke
                    dot = soft_dot(self.color, radius)
                    self._scratch.blit(dot, (px - dot.get_width() / 2.0, rise - dot.get_height() / 2.0))
            surface.blit(self._scratch, (x, y))
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- lightning


class LightningArcControl(Control):
    """
    A jagged arc between two anchors, restriking every second or two with a decaying afterglow:
    energy crackling across an apparatus, between two posts, inside a portal.

    The bolt is a midpoint-displacement polyline regenerated only when it STRIKES, never per
    frame, so the cost is a handful of line draws. Draws three passes (wide dim, medium, thin
    bright core) — a single 1 px line reads as a scratch, not as electricity.

    Layout overrides: arc_rgb, strike, branches, jag, anchors, decay, glow.
    """

    #: Midpoint displacement starts at this fraction of the anchor distance and halves per level.
    _ROUGHNESS = 0.20
    _LEVELS = 5

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("arc_rgb", ARC_RGB)
        spec = self.spec
        self.strike = _clamp(_num(spec.get("strike", 0.8), 0.8), 0.05, 5.0)
        self.branches = int(_clamp(_num(spec.get("branches", 2), 2.0), 0, 4))
        self.jag = _clamp(_num(spec.get("jag", 0.55), 0.55), 0.05, 1.0)
        self.decay = _clamp(_num(spec.get("decay", 9.0), 9.0), 1.0, 40.0)
        self.glow = _clamp(_num(spec.get("glow", 0.35), 0.35), 0.0, 1.0)
        # "add" (default) is right over dark artwork; over something already BRIGHT (a lit
        # portal) adding light is invisible — the bolt just vanishes. "over" draws a solid
        # bolt instead, so a dark violet one reads against white-hot gold.
        self.blend = str(spec.get("blend", "add")).strip().lower()
        self.anchors = self._read_anchors(spec.get("anchors"))
        self.rng = random.Random(int(abs(_num(spec.get("arc_seed", 17.0), 17.0)) * 1000) + 7)
        self.t = 0.0
        self._next = 0.0
        self.level = 0.0
        self._bolt = []
        self._arms = []
        self._recompute_geometry()
        self._restrike()                      # frame 0 draws: the arc is lit at build time

    @staticmethod
    def _read_anchors(value):
        """Two points as fractions of the box; anything malformed falls back to bottom-left -> top-right."""
        default = ((0.18, 0.86), (0.82, 0.14))
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return default
        out = []
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return default
            try:
                out.append((_clamp(float(point[0]), 0.0, 1.0), _clamp(float(point[1]), 0.0, 1.0)))
            except (TypeError, ValueError):
                return default
        return (out[0], out[1])

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)
        a, b = getattr(self, "anchors", ((0.18, 0.86), (0.82, 0.14)))
        self._a = (x + a[0] * w, y + a[1] * h)
        self._b = (x + b[0] * w, y + b[1] * h)

    def _jag_line(self, a, b, roughness, levels):
        """Midpoint displacement: displace each segment's midpoint sideways, then halve the noise."""
        pts = [a, b]
        disp = math.dist(a, b) * roughness
        for _ in range(levels):
            nxt = [pts[0]]
            for i in range(len(pts) - 1):
                p, q = pts[i], pts[i + 1]
                mx = (p[0] + q[0]) / 2.0 + self.rng.uniform(-disp, disp)
                my = (p[1] + q[1]) / 2.0 + self.rng.uniform(-disp, disp)
                nxt.extend(((mx, my), q))
            pts = nxt
            disp *= 0.55
        return pts

    def _restrike(self):
        self._bolt = self._jag_line(self._a, self._b, self._ROUGHNESS * self.jag, self._LEVELS)
        self._arms = []
        for _ in range(self.branches):
            if len(self._bolt) < 4:
                break
            base = self._bolt[self.rng.randrange(1, len(self._bolt) - 1)]
            reach = math.dist(self._a, self._b) * self.rng.uniform(0.12, 0.3)
            ang = self.rng.uniform(0.0, math.tau)
            tip = (base[0] + math.cos(ang) * reach, base[1] + math.sin(ang) * reach)
            self._arms.append(self._jag_line(base, tip, self._ROUGHNESS * self.jag, 3))
        self.level = 1.0

    def update(self, dt: float):
        self.t += dt
        self.level *= math.exp(-self.decay * dt)
        if self.t >= self._next:
            self._restrike()
            self._next = self.t + max(0.06, self.rng.uniform(0.55, 1.5) / self.strike)

    def draw_overlay(self, surface):
        lv = self.level
        if len(self._bolt) < 2:
            return
        x, y = self.rect[0], self.rect[1]
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            # The electrodes stay faintly charged between strikes. Lightning is dark most of the
            # time, but a control that draws NOTHING for a second reads as broken while you are
            # aligning it — so the anchors always glow.
            if self.glow > 0.02:
                span = math.dist(self._a, self._b) * 0.18 * self.glow
                charge = 0.13 + 0.30 * lv     # >= 1/8: a smaller level rounds away in _level8
                add_glow(surface, self.color, self._a, span, charge)
                add_glow(surface, self.color, self._b, span, charge)
            if lv < 0.02:
                return
            # ADDITIVE, on a scratch layer: the bolt is light. Drawn as an opaque polyline its wide
            # pass was darker than the lit portal behind it and read as a black scribble (P3 render).
            local = [(px - x, py - y) for px, py in self._bolt]
            self._scratch.fill((0, 0, 0, 0))
            if self.blend == "over":
                body = tuple(int(c * (0.55 + 0.45 * lv)) for c in self.color)
                rim = tuple(min(255, int(c * 0.4 + 200 * 0.75 * lv)) for c in self.color)
                pygame.draw.lines(self._scratch, (*body, int(235 * lv)), False, local, 4)
                pygame.draw.lines(self._scratch, (*rim, int(255 * lv)), False, local, 2)
                for arm in self._arms:
                    pygame.draw.lines(self._scratch, (*body, int(190 * lv)), False,
                                      [(px - x, py - y) for px, py in arm], 2)
                surface.blit(self._scratch, (x, y))
            else:
                for width, gain in ((9, 0.16), (4, 0.42), (1, 1.0)):
                    colour = tuple(min(255, int((c * 0.55 + 255 * 0.45) * gain * lv)) for c in self.color)
                    if any(colour):
                        pygame.draw.lines(self._scratch, (*colour, 255), False, local, width)
                for arm in self._arms:
                    pygame.draw.lines(self._scratch, (*tuple(int(c * 0.4 * lv) for c in self.color), 255),
                                      False, [(px - x, py - y) for px, py in arm], 2)
                surface.blit(self._scratch, (x, y), special_flags=pygame.BLEND_RGB_ADD)
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- potions


class PotionBubblesControl(Control):
    """
    A bubbling liquid: a shimmering meniscus at the top and small bubbles rising, wobbling and
    popping at the surface, with a faint glow inside the glass.

    The box is the LIQUID, not the whole vessel: the artwork draws the bottle, this draws what
    moves inside it. Bubbles are drawn as thin rings on a scratch layer (alpha, so they read as
    bubbles rather than as dots), and the pool is fixed.

    Layout overrides: potion_rgb, bubbles, rise, surface, wobble, glow.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("potion_rgb", POTION_RGB)
        spec = self.spec
        self.bubbles = int(_clamp(_num(spec.get("bubbles", 8), 8.0), 1, 20))
        self.rise = _clamp(_num(spec.get("rise", 0.22), 0.22), 0.03, 1.2)
        self.surface = _clamp(_num(spec.get("surface", 0.7), 0.7), 0.0, 1.0)
        self.wobble = _clamp(_num(spec.get("wobble", 1.0), 1.0), 0.0, 3.0)
        self.glow = _clamp(_num(spec.get("glow", 0.45), 0.45), 0.0, 1.0)
        self.t = 0.0
        rng = ctx.rng
        self._bx = [rng.uniform(0.12, 0.88) for _ in range(self.bubbles)]
        self._by = [rng.uniform(0.05, 0.95) for _ in range(self.bubbles)]
        self._br = [rng.uniform(1.6, 3.6) for _ in range(self.bubbles)]
        self._bp = [rng.uniform(0.0, math.tau) for _ in range(self.bubbles)]
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)

    def update(self, dt: float):
        self.t += dt
        for i in range(self.bubbles):
            self._by[i] -= self.rise * dt
            if self._by[i] < 0.04:                    # popped at the meniscus: restart at the bottom
                self._by[i] = 0.96
                self._bp[i] += 1.9

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            if self.glow > 0.02:
                add_glow(surface, self.color, (x + w / 2.0, y + h * 0.45),
                         max(w, h) * 0.55 * self.glow, 0.45)
            self._scratch.fill((0, 0, 0, 0))
            if self.surface > 0.02:
                pts = []
                steps = max(6, self._w // 8)
                for k in range(steps + 1):
                    u = k / steps
                    yy = h * 0.10 + math.sin(u * 7.0 + self.t * 1.8) * (1.0 + 1.6 * self.surface)
                    pts.append((u * self._w, yy))
                if len(pts) > 1:
                    pygame.draw.lines(self._scratch,
                                      (*self.color, int(70 + 90 * self.surface)), False, pts, 2)
            for i in range(self.bubbles):
                cx = self._bx[i] * w + math.sin(self.t * 2.2 + self._bp[i]) * self.wobble * 1.6
                cy = self._by[i] * h
                r = max(1, int(self._br[i]))
                pygame.draw.circle(self._scratch, (*self.color, 195), (int(cx), int(cy)), r, 1)
                if r >= 2:
                    pygame.draw.circle(self._scratch, (255, 255, 255, 210),
                                       (int(cx) - 1, int(cy) - 1), 1)
            surface.blit(self._scratch, (x, y))
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- drifting runes


class DriftingRunesControl(Control):
    """
    Glyphs that fade in low in the box, drift upward as they brighten, and fade out near the top —
    an incantation rising off a book, a bowl or an apparatus.

    The glyphs are STAGGERED in time, so they read as a sequence passing upward rather than as one
    block of symbols, and each carries its own glyph, size jitter and sway so no two look stamped.
    Every bit of that is fixed at construction from the mode's seed: nothing is randomised per frame,
    so a pinned seed reproduces the picture.

    Layout overrides: rune_rgb, count, glyph, rise, sway, fade, glow.

    The glyph size is `glyph`, NOT `size`: in a freeform layout `size` is the control's
    BOX, and one key meaning two things is the bug that blacked out the whole panel once.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("rune_rgb", RUNE_RGB)
        spec = self.spec
        self.count = int(_clamp(_num(spec.get("count", 4), 4.0), 1, 12))
        self.size = _clamp(_num(spec.get("glyph", 0.24), 0.24), 0.06, 0.6)
        self.rise = _clamp(_num(spec.get("rise", 6.0), 6.0), 1.0, 40.0)
        self.sway = _clamp(_num(spec.get("sway", 0.10), 0.10), 0.0, 0.5)
        self.fade = _clamp(_num(spec.get("fade", 0.30), 0.30), 0.05, 0.5)
        self.glow = _clamp(_num(spec.get("glow", 0.6), 0.6), 0.0, 1.0)
        self.t = 0.0
        rng = ctx.rng
        self._glyph = [rng.randrange(len(GLYPHS)) for _ in range(self.count)]
        self._x0 = [rng.uniform(0.25, 0.75) for _ in range(self.count)]
        self._phase = [rng.uniform(0.0, math.tau) for _ in range(self.count)]
        self._jitter = [rng.uniform(0.85, 1.2) for _ in range(self.count)]
        self._life = [(i / self.count) for i in range(self.count)]   # staggered sequence
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)
        self._px = max(7.0, min(self._w, self._h) * float(getattr(self, "size", 0.24)))

    def update(self, dt: float):
        """One field: every glyph advances at the same rate, so the sequence keeps its spacing."""
        self.t += dt
        step = dt / max(0.1, self.rise)
        for i in range(self.count):
            self._life[i] = (self._life[i] + step) % 1.0

    def draw_overlay(self, surface):
        x, y, w, h = self.rect
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            self._scratch.fill((0, 0, 0, 0))
            fade = self.fade
            for i in range(self.count):
                u = self._life[i]
                # envelope: rise in, hold, fall away — smoothstepped so it never pops
                if u < fade:
                    env = u / fade
                elif u > 1.0 - fade:
                    env = (1.0 - u) / fade
                else:
                    env = 1.0
                env = _clamp(env, 0.0, 1.0)
                env = env * env * (3.0 - 2.0 * env)
                if env <= 0.02:
                    continue
                size = self._px * self._jitter[i]
                cy = h * (1.02 - 1.06 * u)
                cx = self._x0[i] * w + math.sin(u * 4.4 + self._phase[i]) * self.sway * w
                dim = (*self.color, int(95 * env))
                bright = (*tuple(min(255, int(c * 0.72 + 235 * 0.32)) for c in self.color), int(225 * env))
                # wide dim halo stroke under a thin bright core: that is what makes it glow rather
                # than look like a chalk mark (draw replaces alpha, so the core overwrites the middle)
                draw_glyph(self._scratch, GLYPHS[self._glyph[i]], (cx, cy), size, 0.0, dim,
                           max(2, size * 0.24))
                draw_glyph(self._scratch, GLYPHS[self._glyph[i]], (cx, cy), size, 0.0, bright,
                           max(1, size * 0.085))
                if self.glow > 0.02:
                    # two scales of halo: a tight one that hugs the strokes and a broad bloom, so the
                    # glyph reads as light rather than as a pale mark on the stone
                    add_glow(surface, self.color, (x + cx, y + cy), size * 1.2, self.glow * 0.8 * env)
                    add_glow(surface, self.color, (x + cx, y + cy), size * 2.5, self.glow * 0.45 * env)
            surface.blit(self._scratch, (x, y))
        finally:
            surface.set_clip(clip)


# ---------------------------------------------------------------- eyes


class GlowingEyesControl(Control):
    """
    A pair of eyes that fade in out of the dark, hold, and fade away again — something watching from
    a shadow. Almond lenses with a slit pupil, slanted so they read as predatory rather than friendly.

    The fade is the point: `period` is one full cycle (fade in, hold, fade out, wait), and `hold` is
    the fraction of it spent fully lit. `blink` closes the eyes for a fifth of a second every so often
    (0 disables it) — a pair that never blinks reads as a painted sign; one that blinks reads as alive.

    Layout overrides: eye_rgb, pairs, eye, gap, slant, period, hold, blink, glow.

    The eye SIZE is `eye`, not `size`: in a freeform layout `size` is the control's box.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("eye_rgb", EYE_RGB)
        spec = self.spec
        self.pairs = int(_clamp(_num(spec.get("pairs", 1), 1.0), 1, 3))
        self.eye = _clamp(_num(spec.get("eye", 0.34), 0.34), 0.05, 0.9)
        self.gap = _clamp(_num(spec.get("gap", 1.25), 1.25), 0.8, 3.0)
        self.slant = _clamp(_num(spec.get("slant", 0.30), 0.30), 0.0, 0.6)
        self.period = _clamp(_num(spec.get("period", 9.0), 9.0), 2.0, 60.0)
        self.hold = _clamp(_num(spec.get("hold", 0.35), 0.35), 0.0, 0.9)
        self.blink = _clamp(_num(spec.get("blink", 0.0), 0.0), 0.0, 30.0)
        self.glow = _clamp(_num(spec.get("glow", 0.7), 0.7), 0.0, 1.0)
        # Start INSIDE the lit part of the cycle: at t=0 the eyes must be visible, or a control you
        # just placed looks broken while you are aligning it. The jitter desynchronises instances.
        self.t = self.period * ctx.rng.uniform(0.38, 0.62)
        self._blink_left = 0.0
        self._next_blink = self.blink * (0.4 + ctx.rng.random()) if self.blink > 0 else 0.0
        self._phase = [ctx.rng.uniform(0.0, math.tau) for _ in range(self.pairs)]
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, w, h = self.rect
        self._w, self._h = max(1, int(w)), max(1, int(h))
        self._clip = pygame.Rect(int(x), int(y), self._w, self._h)
        self._scratch = pygame.Surface((self._w, self._h), pygame.SRCALPHA)
        shorter = float(min(self._w, self._h))
        self._eye_w = shorter * float(getattr(self, "eye", 0.34))
        self._eye_h = self._eye_w * 0.46
        self._spacing = self._eye_w * float(getattr(self, "gap", 1.25))

    def update(self, dt: float):
        self.t += dt
        if self._blink_left > 0.0:
            self._blink_left = max(0.0, self._blink_left - dt)
        elif self.blink > 0.0:
            self._next_blink -= dt
            if self._next_blink <= 0.0:
                self._blink_left = 0.18
                self._next_blink = self.blink * (0.6 + 0.8 * (self.t % 1.0))

    # ---------------------------------------------------------------- envelope

    def _brightness(self) -> float:
        """0..1 over one cycle: smooth fade in, hold, smooth fade out, then dark."""
        u = (self.t % self.period) / self.period
        fade = max(0.02, (1.0 - self.hold) / 2.0)
        if u < fade:
            e = u / fade
        elif u > 1.0 - fade:
            e = (1.0 - u) / fade
        else:
            e = 1.0
        e = _clamp(e, 0.0, 1.0)
        return e * e * (3.0 - 2.0 * e)

    def _lid(self) -> float:
        """1.0 open, down to ~0.05 mid-blink."""
        if self._blink_left <= 0.0:
            return 1.0
        progress = 1.0 - (self._blink_left / 0.18)      # 0 at the start of the blink
        return max(0.05, 1.0 - math.sin(math.pi * progress))

    # ---------------------------------------------------------------- drawing

    @staticmethod
    def _almond(cx, cy, w, h, tilt):
        """A lens shape: two mirrored arcs meeting at the corners, rotated by `tilt`."""
        pts = []
        steps = 12
        for side in (-1, 1):
            rng = range(0, steps + 1) if side < 0 else range(steps, -1, -1)
            for k in rng:
                u = -1.0 + 2.0 * k / steps
                x = u * w / 2.0
                y = side * (h / 2.0) * (1.0 - u * u) ** 0.62
                ca, sa = math.cos(tilt), math.sin(tilt)
                pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
        return pts

    def draw_overlay(self, surface):
        env = self._brightness()
        if env <= 0.02:
            return
        x, y = self.rect[0], self.rect[1]
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            self._scratch.fill((0, 0, 0, 0))
            lid = self._lid()
            eye_w = self._eye_w
            eye_h = max(1.0, self._eye_h * lid)
            core_rgb = tuple(min(255, int(c * 0.62 + 255 * 0.45)) for c in self.color)
            dark = (8, 6, 10)
            for pair in range(self.pairs):
                cy = self._h * (0.5 if self.pairs == 1 else 0.25 + 0.5 * pair / (self.pairs - 1))
                cx = self._w / 2.0
                drift = math.sin(self.t * 0.55 + self._phase[pair]) * eye_w * 0.10
                for side in (-1, 1):
                    ex = cx + side * self._spacing / 2.0 + drift
                    tilt = side * self.slant
                    # outer lens
                    pygame.draw.polygon(self._scratch, (*self.color, int(120 * env)),
                                        self._almond(ex, cy, eye_w, eye_h, tilt))
                    # bright iris
                    pygame.draw.ellipse(self._scratch, (*core_rgb, int(225 * env)),
                                        pygame.Rect(int(ex - eye_w * 0.30), int(cy - eye_h * 0.34),
                                                    max(2, int(eye_w * 0.56)), max(2, int(eye_h * 0.66))))
                    # slit pupil: what makes them sinister rather than cute
                    pygame.draw.ellipse(self._scratch, (*dark, int(240 * env)),
                                        pygame.Rect(int(ex - eye_w * 0.055), int(cy - eye_h * 0.32),
                                                    max(1, int(eye_w * 0.11)), max(2, int(eye_h * 0.64))))
                    if self.glow > 0.02:
                        add_glow(surface, self.color, (x + ex, y + cy), eye_w * 1.25,
                                 self.glow * env)
            surface.blit(self._scratch, (x, y))
        finally:
            surface.set_clip(clip)
