# controlpanel/controls/lamps.py
#
# Lamp controls: blinking indicator lights drawn as primitive glows
# (decision D3 — no "lit" sprites required from skins).

import pygame

from ..signals import build_signal
from .base import Control

# Lamp color is inferred from the sprite ID when the layout doesn't give
# one: LED_LAMP_RED -> red, etc. Falls back to the mode's lamp_rgb.
_SPRITE_COLORS = {
    "RED": (255, 60, 50),
    "GREEN": (70, 255, 110),
    "AMBER": (255, 176, 64),
    "BLUE": (80, 170, 255),
}


class LampControl(Control):
    """
    Blinking indicator lamp: an outer halo + bright core whose intensity
    follows a signal (default: square wave — a steady blink). Intensity is
    smoothed so lamps fade in/out instead of popping.

    Layout overrides: signal, color_rgb, center, radius.
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        self.signal = build_signal(self.spec.get("signal"), ctx.rng,
                                   default_kind="square")
        self.color = self._resolve_color(ctx)
        self.level = 0.0  # smoothed 0..1 intensity

    def _recompute_geometry(self):
        super()._recompute_geometry()
        # centre + glow radius follow the rect (see Control._recompute_geometry)
        self.center = self._anchor("center", (0.5, 0.5))
        _, _, w, h = self.rect
        self.radius = float(self.spec.get("radius", 0.20)) * min(w, h)

    def _resolve_color(self, ctx):
        # generic "color" wins, then the lamp-specific "color_rgb",
        # then the color named by the sprite ID, then the mode default
        if "color" in self.spec:
            return tuple(self.spec["color"])
        if "color_rgb" in self.spec:
            return tuple(self.spec["color_rgb"])
        for key, rgb in _SPRITE_COLORS.items():
            if key in self.sprite_id:
                return rgb
        return ctx.lamp_rgb

    def update(self, dt: float):
        self.signal.update(dt)
        # attack is fast, release slower — looks like a real filament/LED
        target = self.signal.value
        rate = 18.0 if target > self.level else 7.0
        self.level += (target - self.level) * min(1.0, rate * dt)

    def draw_overlay(self, surface):
        if self.level < 0.02:
            return
        cx, cy = int(self.center[0]), int(self.center[1])
        lv = self.level
        r_core = max(1, int(self.radius))
        r_halo = int(self.radius * 1.8)
        halo = tuple(int(c * 0.35 * lv) for c in self.color)
        core = tuple(int(c * lv) for c in self.color)
        pygame.draw.circle(surface, halo, (cx, cy), r_halo)
        pygame.draw.circle(surface, core, (cx, cy), r_core)


def _fraction(value, span: int) -> float:
    """
    A size value as a fraction of `span` pixels.

    The "size" key carries two meanings and both must work: the lamp family's fraction of the box
    (0.30, or the rectangles' [0.60, 0.35]) and the layout's pixel size ([160, 160], which is what the
    add dialog writes and what every other control uses). They overlap for the rectangles' own default,
    so the split is by VALUE rather than by type: a fraction is at most 1, a pixel size is at least 1 —
    a one-pixel control is not a thing, and a fraction of 1 is the whole box.

    Getting this wrong is not cosmetic: float([160, 160]) raised inside the mode's enter(), and the
    whole panel went black over one newly added lamp.
    """
    number = float(value)
    return number / max(1, span) if number > 1.0 else number


def _glow_half(size, w: int, h: int) -> float:
    """Half the glow's extent in pixels, from either form of the size value."""
    shorter = min(w, h)
    if isinstance(size, (list, tuple)):
        return _fraction(size[0], shorter) * shorter / 2.0
    return float(size) * shorter / 2.0


class SquareLampControl(LampControl):
    """
    Square indicator lamp. Same blink/fade behavior as LampControl, but the
    glow is drawn as a centered square.

    Layout overrides: signal, color_rgb, center, size (a fraction of the shorter side, or the
    layout's pixel [w, h] — see _glow_half).
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        _, _, w, h = self.rect
        self.half = max(1, int(_glow_half(self.spec.get("size", 0.30), w, h)))

    def draw_overlay(self, surface):
        if self.level < 0.02:
            return
        cx, cy = int(self.center[0]), int(self.center[1])
        lv = self.level
        half_halo = max(1, int(self.half * 1.6))
        halo = tuple(int(c * 0.35 * lv) for c in self.color)
        core = tuple(int(c * lv) for c in self.color)
        pygame.draw.rect(surface, halo,
                         (cx - half_halo, cy - half_halo,
                          half_halo * 2, half_halo * 2))
        pygame.draw.rect(surface, core,
                         (cx - self.half, cy - self.half,
                          self.half * 2, self.half * 2))


class RectLampControl(LampControl):
    """
    Rectangular indicator lamp. Same blink/fade behavior as LampControl, but
    the glow is drawn as a centered rectangle whose aspect ratio matches the
    sprite footprint.

    Layout overrides: signal, color_rgb, center, size (either [frac_w, frac_h] of the box, or
    the layout's pixel [w, h]).
    """

    def __init__(self, placed, ctx):
        super().__init__(placed, ctx)
        _, _, w, h = self.rect
        size = self.spec.get("size", [0.60, 0.35])
        if isinstance(size, (list, tuple)):
            frac_w, frac_h = _fraction(size[0], w), _fraction(size[1], h)
        else:
            frac_w = frac_h = float(size)
        self.half_w = max(1, int(frac_w * w / 2))
        self.half_h = max(1, int(frac_h * h / 2))

    def draw_overlay(self, surface):
        if self.level < 0.02:
            return
        cx, cy = int(self.center[0]), int(self.center[1])
        lv = self.level
        hw_halo = max(1, int(self.half_w * 1.5))
        hh_halo = max(1, int(self.half_h * 1.5))
        halo = tuple(int(c * 0.35 * lv) for c in self.color)
        core = tuple(int(c * lv) for c in self.color)
        pygame.draw.rect(surface, halo,
                         (cx - hw_halo, cy - hh_halo,
                          hw_halo * 2, hh_halo * 2))
        pygame.draw.rect(surface, core,
                         (cx - self.half_w, cy - self.half_h,
                          self.half_w * 2, self.half_h * 2))