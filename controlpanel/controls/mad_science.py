# controlpanel/controls/mad_science.py
#
# Procedural electrical/mechanical controls for the Mad Scientist Control Panel.
# They are freeform overlays: artwork provides the brass, glass, rods and bezels;
# these classes draw the active electrical and mechanical parts inside their rects.

import math
import os
import random

import pygame

from .arcane import add_glow
from .base import Control


ARC_RGB = (150, 198, 255)
FILAMENT_RGB = (255, 174, 84)
SPARK_RGB = (126, 210, 255)
WHEEL_RGB = (225, 205, 155)
FACE_RGB = (25, 21, 15)


def _number(value, default):
    """Convert a panel value safely: malformed author input must not black out a mode."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(result):
        return float(default)
    return result


def _clamp(value, low, high):
    return max(low, min(high, value))


def _colour_scale(rgb, level):
    return tuple(max(0, min(255, int(channel * level))) for channel in rgb)


class JacobsLadderControl(Control):
    """
    A blue-violet electrical arc that starts at the close lower gap of two diverging electrodes,
    climbs upward, breaks at the wide gap, then restrikes from the bottom.

    Layout overrides: arc_rgb, cycle, climb, rest, jag, branches, glow, left_rail, right_rail.
    Each rail is two normalized points: [bottom, top].
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("arc_rgb", ARC_RGB)
        spec = self.spec
        self.climb = _clamp(_number(spec.get("climb", 1.25), 1.25), 0.15, 8.0)
        self.rest = _clamp(_number(spec.get("rest", 0.32), 0.32), 0.02, 4.0)
        self.jag = _clamp(_number(spec.get("jag", 0.16), 0.16), 0.02, 0.6)
        self.branches = int(_clamp(_number(spec.get("branches", 1), 1), 0, 4))
        self.glow = _clamp(_number(spec.get("glow", 0.55), 0.55), 0.0, 1.0)
        self.left_rail = self._rail(spec.get("left_rail"), ((0.42, 0.92), (0.10, 0.08)))
        self.right_rail = self._rail(spec.get("right_rail"), ((0.58, 0.92), (0.90, 0.08)))
        self.rng = random.Random(ctx.rng.randrange(1 << 30))
        self.t = 0.0
        self.progress = 0.05
        self.cooldown = 0.0
        self._bolt = []
        self._branches = []
        self._recompute_geometry()
        self._restrike()

    @staticmethod
    def _rail(value, default):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return default
        parsed = []
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return default
            parsed.append((_clamp(_number(point[0], 0.5), 0.0, 1.0),
                           _clamp(_number(point[1], 0.5), 0.0, 1.0)))
        return tuple(parsed)

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, width, height = self.rect
        self._clip = pygame.Rect(int(x), int(y), max(1, int(width)), max(1, int(height)))
        # The bolt caches absolute points. A live alignment nudge must carry the active strike with
        # the control rather than clipping the old geometry away until the next animation tick.
        if hasattr(self, "rng"):
            self._restrike()

    def _at_rail(self, rail, fraction):
        (x0, y0), (x1, y1) = rail
        x, y, width, height = self.rect
        return (x + (x0 + (x1 - x0) * fraction) * width,
                y + (y0 + (y1 - y0) * fraction) * height)

    def _jagged_line(self, left, right):
        dx, dy = right[0] - left[0], right[1] - left[1]
        distance = max(1.0, math.hypot(dx, dy))
        nx, ny = -dy / distance, dx / distance
        points = [left]
        steps = 9
        amplitude = distance * self.jag
        for index in range(1, steps):
            fraction = index / steps
            offset = self.rng.uniform(-amplitude, amplitude) * (0.45 + 0.55 * math.sin(math.pi * fraction))
            points.append((left[0] + dx * fraction + nx * offset,
                           left[1] + dy * fraction + ny * offset))
        points.append(right)
        return points

    def _restrike(self):
        left = self._at_rail(self.left_rail, self.progress)
        right = self._at_rail(self.right_rail, self.progress)
        self._bolt = self._jagged_line(left, right)
        self._branches = []
        for _ in range(self.branches):
            pivot = self._bolt[self.rng.randrange(2, len(self._bolt) - 2)]
            length = math.dist(left, right) * self.rng.uniform(0.12, 0.28)
            angle = self.rng.uniform(0.0, math.tau)
            tip = (pivot[0] + math.cos(angle) * length, pivot[1] + math.sin(angle) * length)
            self._branches.append(self._jagged_line(pivot, tip))

    def update(self, dt):
        self.t += max(0.0, dt)
        if self.cooldown > 0.0:
            self.cooldown = max(0.0, self.cooldown - dt)
            if self.cooldown == 0.0:
                self.progress = 0.03
                self._restrike()
            return
        self.progress += dt / self.climb
        if self.progress >= 1.0:
            self.progress = 1.0
            self.cooldown = self.rest
        else:
            self._restrike()

    def draw_overlay(self, surface):
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            # The lower contacts stay faintly charged while the real arc is between strikes.
            low_left = self._at_rail(self.left_rail, 0.0)
            low_right = self._at_rail(self.right_rail, 0.0)
            span = math.dist(low_left, low_right)
            if self.glow > 0.02:
                add_glow(surface, self.color, low_left, max(5.0, span * 0.45), 0.30 * self.glow)
                add_glow(surface, self.color, low_right, max(5.0, span * 0.45), 0.30 * self.glow)
            if len(self._bolt) < 2 or self.cooldown > 0.0:
                return
            brightness = 0.92 + 0.08 * math.sin(self.t * 25.0)
            for width, gain in ((7, 0.20), (3, 0.55), (1, 1.0)):
                pygame.draw.lines(surface, _colour_scale(self.color, gain * brightness), False,
                                  self._bolt, width)
            for branch in self._branches:
                pygame.draw.lines(surface, _colour_scale(self.color, 0.35 * brightness), False,
                                  branch, 1)
        finally:
            surface.set_clip(clip)


class ElectricFilamentControl(Control):
    """
    A warm tungsten coil with a wandering bright section, usable upright in a vacuum tube or
    sideways in a bulb. Glass, sockets, and metal are intentionally left to the artwork.

    Layout overrides: filament_rgb, orient ("v" or "h"), turns, thickness, heat, surge, glow, inset.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("filament_rgb", FILAMENT_RGB)
        spec = self.spec
        self.orient = str(spec.get("orient", "v")).strip().lower()
        self.turns = int(_clamp(_number(spec.get("turns", 13), 13), 3, 36))
        self.thickness = int(_clamp(_number(spec.get("thickness", 2), 2), 1, 6))
        self.heat = _clamp(_number(spec.get("heat", 0.82), 0.82), 0.10, 1.0)
        self.surge = _clamp(_number(spec.get("surge", 0.24), 0.24), 0.0, 1.0)
        self.glow = _clamp(_number(spec.get("glow", 0.55), 0.55), 0.0, 1.0)
        self.inset = _clamp(_number(spec.get("inset", 0.17), 0.17), 0.02, 0.42)
        self.phase = ctx.rng.uniform(0.0, math.tau)
        self.t = 0.0
        self._coil = []
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, width, height = self.rect
        self._clip = pygame.Rect(int(x), int(y), max(1, int(width)), max(1, int(height)))
        vertical = getattr(self, "orient", "v") != "h"
        long_span = height if vertical else width
        short_span = width if vertical else height
        inset = short_span * float(getattr(self, "inset", 0.17))
        radius = max(2.0, (short_span - inset * 2.0) * 0.42)
        points = []
        samples = int(getattr(self, "turns", 13)) * 12
        for index in range(samples + 1):
            fraction = index / samples
            angle = fraction * math.tau * int(getattr(self, "turns", 13))
            if vertical:
                points.append((x + width / 2.0 + math.sin(angle) * radius,
                               y + long_span * (0.10 + 0.80 * fraction)))
            else:
                points.append((x + long_span * (0.10 + 0.80 * fraction),
                               y + height / 2.0 + math.sin(angle) * radius))
        self._coil = points
        self._center = (x + width / 2.0, y + height / 2.0)
        self._halo = min(width, height) * 0.48 * float(getattr(self, "glow", 0.55))

    def update(self, dt):
        self.t += max(0.0, dt)

    def draw_overlay(self, surface):
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            heat = self.heat * (1.0 - self.surge * 0.22 + self.surge * 0.22 * math.sin(self.t * 4.2 + self.phase))
            if self._halo >= 3.0:
                add_glow(surface, self.color, self._center, self._halo, heat * 0.58)
            if len(self._coil) > 1:
                pygame.draw.lines(surface, _colour_scale(self.color, heat * 0.35), False,
                                  self._coil, self.thickness + 2)
                pygame.draw.lines(surface, _colour_scale(self.color, heat), False,
                                  self._coil, self.thickness)
        finally:
            surface.set_clip(clip)


class SparkTerminalControl(Control):
    """
    A compact shower of sparks emitting from one point. Every visible mark is a moving particle —
    there is no glowing terminal body or persistent central lamp. Its fixed particle pool puts a
    hard ceiling on work, and the initial burst makes a newly added control visible immediately.

    Layout overrides: spark_rgb, rate, count, speed, spread, life.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.color = self._color("spark_rgb", SPARK_RGB)
        spec = self.spec
        self.rate = _clamp(_number(spec.get("rate", 1.4), 1.4), 0.08, 12.0)
        self.count = int(_clamp(_number(spec.get("count", 18), 18), 2, 80))
        self.speed = _clamp(_number(spec.get("speed", 80), 80), 8.0, 420.0)
        self.spread = _clamp(_number(spec.get("spread", 0.8), 0.8), 0.05, math.tau)
        self.life = _clamp(_number(spec.get("life", 0.32), 0.32), 0.04, 2.0)
        # `rate` is the particle re-emission multiplier: higher values renew a denser-looking
        # shower more often without adding particles or allowing a dark gap between bursts.
        self.duration = self.life / self.rate
        self.rng = random.Random(ctx.rng.randrange(1 << 30))
        self.t = 0.0
        self.age = [self.life] * self.count
        self.dx = [0.0] * self.count
        self.dy = [0.0] * self.count
        self.scale = [1.0] * self.count
        self._recompute_geometry()
        self._seed_particles()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, width, height = self.rect
        self._clip = pygame.Rect(int(x), int(y), max(1, int(width)), max(1, int(height)))
        self.center = (x + width / 2.0, y + height / 2.0)
        self.radius = max(3.0, min(width, height) * 0.11)

    def _launch(self, index, age):
        """Give one particle a new trajectory from the shared emission point."""
        angle = -math.pi / 2.0 + self.rng.uniform(-self.spread, self.spread)
        velocity = self.speed * self.rng.uniform(0.35, 1.0)
        self.age[index] = age
        self.dx[index] = math.cos(angle) * velocity
        self.dy[index] = math.sin(angle) * velocity
        self.scale[index] = self.rng.uniform(0.35, 1.0)

    def _seed_particles(self):
        """Stagger the initial shower so it is visibly active without a fake glowing terminal."""
        for index in range(self.count):
            self._launch(index, self.rng.uniform(0.0, self.duration))

    def update(self, dt):
        dt = max(0.0, dt)
        self.t += dt
        for index in range(self.count):
            self.age[index] += dt
            if self.age[index] >= self.duration:
                self._launch(index, 0.0)

    def draw_overlay(self, surface):
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            for index in range(self.count):
                fraction = self.age[index] / self.duration
                if fraction >= 1.0:
                    continue
                fade = 1.0 - fraction
                px = self.center[0] + self.dx[index] * self.age[index]
                py = self.center[1] + self.dy[index] * self.age[index] + 48.0 * self.age[index] ** 2
                length = max(2.0, self.radius * 1.75 * self.scale[index] * fade)
                speed = max(1.0, math.hypot(self.dx[index], self.dy[index]))
                ex = px - self.dx[index] / speed * length
                ey = py - self.dy[index] / speed * length
                pygame.draw.line(surface, _colour_scale(self.color, fade), (px, py), (ex, ey), 1)
        finally:
            surface.set_clip(clip)


class MechanicalWheelsControl(Control):
    """
    A recessed row of mechanical number drums. Each digit is a real rolling strip: when a value steps,
    the outgoing and incoming numbers slide through a clipped individual wheel window.

    Layout overrides: wheel_rgb, face_rgb, digits, start, per_sec, step_time, direction, window, bezel,
    font_name (a system-family name or a path to a .ttf/.otf file).
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.wheel_rgb = self._color("wheel_rgb", WHEEL_RGB)
        self.face_rgb = self._color("face_rgb", FACE_RGB)
        spec = self.spec
        self.digits = int(_clamp(_number(spec.get("digits", 5), 5), 1, 12))
        self.start = int(_number(spec.get("start", 18420), 18420))
        self.per_sec = _clamp(_number(spec.get("per_sec", 0.7), 0.7), 0.02, 60.0)
        self.step_time = _clamp(_number(spec.get("step_time", 0.26), 0.26), 0.05, 1.5)
        self.direction = -1 if str(spec.get("direction", "up")).lower() == "down" else 1
        self.bezel = _clamp(_number(spec.get("bezel", 0.08), 0.08), 0.02, 0.25)
        raw_font_name = spec.get("font_name", "")
        self.font_name = str(raw_font_name).strip() if raw_font_name is not None else ""
        self.t = 0.0
        self._glyphs = []
        self._recompute_geometry()

    def _recompute_geometry(self):
        super()._recompute_geometry()
        x, y, width, height = self.rect
        self._clip = pygame.Rect(int(x), int(y), max(1, int(width)), max(1, int(height)))
        bezel = min(width, height) * float(getattr(self, "bezel", 0.08))
        self._wheel_window = pygame.Rect(int(x + bezel), int(y + bezel),
                                         max(1, int(width - bezel * 2)), max(1, int(height - bezel * 2)))
        self._wheel_width = max(1, self._wheel_window.width // max(1, getattr(self, "digits", 5)))
        self._font = self._load_font(max(12, int(self._wheel_window.height * 1.34)))
        color = getattr(self, "wheel_rgb", WHEEL_RGB)
        self._glyphs = [self._font.render(str(number), True, color) for number in range(10)]

    def _load_font(self, size):
        """A named system font or explicit font file, with the pygame default as a safe fallback."""
        name = getattr(self, "font_name", "")
        if name:
            if os.path.isfile(name):
                try:
                    self._font_source = f"path:{name}"
                    return pygame.font.Font(name, size)
                except pygame.error:
                    pass
            try:
                self._font_source = f"system:{name}"
                return pygame.font.SysFont(name, size)
            except pygame.error:
                pass
        self._font_source = "default"
        return pygame.font.Font(None, size)

    def update(self, dt):
        self.t += max(0.0, dt)

    def _roll_for(self, fraction):
        """0 while a digit is held; 0..1 only during the final rolling window."""
        window = _clamp(self.step_time * self.per_sec, 0.02, 0.45)
        start = 1.0 - window
        if fraction <= start:
            return 0.0
        return _clamp((fraction - start) / window, 0.0, 1.0)

    def draw_overlay(self, surface):
        clip = surface.get_clip()
        surface.set_clip(self._clip)
        try:
            pygame.draw.rect(surface, _colour_scale(self.face_rgb, 0.58), self._clip, border_radius=4)
            pygame.draw.rect(surface, _colour_scale(self.wheel_rgb, 0.32), self._clip, 2, border_radius=4)
            value = self.start + self.direction * self.t * self.per_sec
            whole = math.floor(value)
            fraction = value - whole
            text = str(abs(whole)).zfill(self.digits)[-self.digits:]
            for index, char in enumerate(text):
                wheel = pygame.Rect(self._wheel_window.x + index * self._wheel_width,
                                    self._wheel_window.y, self._wheel_width - 1,
                                    self._wheel_window.height)
                old_clip = surface.get_clip()
                surface.set_clip(wheel)
                try:
                    digit = int(char)
                    roll = self._roll_for(fraction) if index == self.digits - 1 else 0.0
                    current = self._glyphs[digit]
                    next_glyph = self._glyphs[(digit + self.direction) % 10]
                    cy = wheel.centery - current.get_height() // 2
                    offset = int(roll * wheel.height) * self.direction
                    surface.blit(current, (wheel.centerx - current.get_width() // 2, cy - offset))
                    surface.blit(next_glyph, (wheel.centerx - next_glyph.get_width() // 2,
                                              cy + wheel.height * self.direction - offset))
                finally:
                    surface.set_clip(old_clip)
                pygame.draw.rect(surface, _colour_scale(self.wheel_rgb, 0.16), wheel, 1)
        finally:
            surface.set_clip(clip)
