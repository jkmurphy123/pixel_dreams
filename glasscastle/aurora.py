"""The aurora field for The Glass Castle.

The sky is an additive field of soft, overlapping curtains rendered at low
resolution and upscaled.  That division is what keeps the Pi alive: a
270x480 field refreshed six times a second costs a fraction of a full-screen
per-pixel pass, and the aurora is soft enough that the interpolation is
invisible.

The reviewed still is the field at REVIEW_TIME (15 s), its bright peak.  Time
moves the curtain centres, shifts the hue over a minute, and drives the
signature breath: every 47 s the field brightens for about six seconds, and the
renderer raises the clipped castle reflection with it.
"""
from __future__ import annotations

import math
import random

import pygame

from .palette import Palette, mix, smoothstep
from .layout import REVIEW_TIME

TAU = math.tau

#: divisor of the screen for the low-resolution field, and refreshes per second
QUALITY = {
    "low": {"div": 7, "refresh": 4.0},
    "medium": {"div": 5, "refresh": 5.0},
    "high": {"div": 4, "refresh": 6.0},
}
QUALITY_NAMES = tuple(QUALITY)

BREATH_PERIOD = 47.0
BREATH_WIDTH = 6.0

#: Slow per-curtain phase speeds (radians/second); the sign alternates so the
#: curtains do not all sway together.
CURTAIN_SPEEDS = (0.060, -0.045, 0.080, -0.032, 0.052)


def breath_at(time_s: float) -> float:
    """The signature brightening, 0..1, peaking at REVIEW_TIME + k*47 s."""
    phase = (float(time_s) - REVIEW_TIME) % BREATH_PERIOD
    if phase > BREATH_PERIOD * 0.5:
        phase -= BREATH_PERIOD
    return math.exp(-((phase / BREATH_WIDTH) ** 2))


class AuroraField:
    def __init__(self, size, palette: Palette, layout, quality: str = "medium",
                 seed: int = 0, period: float = 60.0):
        self.sw, self.sh = int(size[0]), int(size[1])
        self.palette = palette
        self.layout = layout
        self.quality = quality if quality in QUALITY else "medium"
        self.seed = int(seed)
        self.period = max(20.0, min(180.0, float(period)))

        # Seed changes the curtain phases and the minute-scale hue offset; the
        # reviewed seed keeps the authored phases so the preview matches the
        # study.
        rng = random.Random(self.seed ^ 0xA0A0)
        if self.seed == 5130:
            self.phase_shift = 0.0
            self.hue_shift = 0.0
        else:
            self.phase_shift = rng.uniform(0.0, TAU)
            self.hue_shift = rng.uniform(0.0, TAU)

        self._low = None
        self._surface = None
        self._last_time = -1e9
        self._next_build = -1e9
        q = QUALITY[self.quality]
        self._field_size = (
            max(140, self.sw // q["div"]),
            max(64, self.sh // q["div"]),
        )
        self._refresh = float(q["refresh"])
        # The field is a pure function of the seed; the moving sky is a slow
        # drift + hue + breath on this base.  Building it once keeps the frame
        # loop free of a half-second per-pixel pass every few frames.
        self._base = self._build_low(REVIEW_TIME)

    # ------------------------------------------------------------- quality

    def set_quality(self, quality: str) -> None:
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        self._refresh = float(QUALITY[quality]["refresh"])
        self._next_build = -1e9
        self._surface = None

    @property
    def field_size(self):
        return self._field_size

    @property
    def low(self):
        return self._low

    def pulse(self, time_s: float) -> float:
        return 0.86 + 0.14 * breath_at(time_s)

    # --------------------------------------------------------------- field

    def _build_low(self, time_s: float) -> pygame.Surface:
        p = self.palette
        aw, ah = self._field_size
        buf = bytearray(aw * ah * 3)
        anim = (float(time_s) - REVIEW_TIME) * (60.0 / self.period)
        hue = 0.5 - 0.5 * math.cos(
            TAU * (float(time_s) - REVIEW_TIME) / self.period)
        breath = breath_at(time_s)

        # Palette colours with the slow hue drift; the still at REVIEW_TIME is
        # the authored ramp.
        violet = mix(p.aurora_violet, p.structure, 0.08 * hue)
        teal = mix(p.aurora_teal, p.aurora_mint, 0.10 * hue)
        mint = mix(p.aurora_mint, p.glow, 0.12 * hue)
        ramp = []
        for y in range(ah):
            v = y / max(1, ah - 1)
            if v < 0.35:
                col = mix(violet, teal, v / 0.35)
            else:
                col = mix(teal, mint, (v - 0.35) / 0.65)
            ramp.append(col)

        crown_u = self.layout.center_x / max(1.0, self.sw)
        crown_w = 0.17 if not self.layout.portrait else 0.24
        pulse = 0.86 + 0.14 * breath
        columns = []
        for x in range(aw):
            u = x / max(1, aw - 1)
            entries = []
            for idx, (base, a1, f1, ph1, a2, f2, ph2, slope, thick, inten,
                      ray_f, ray_w, ray_ph, crown) in enumerate(
                          self.layout.curtains):
                speed = CURTAIN_SPEEDS[idx % len(CURTAIN_SPEEDS)]
                phase = ph1 + self.phase_shift + anim * speed
                phase2 = ph2 + self.phase_shift * 0.5 + anim * speed * 0.7
                yc = (base + a1 * math.sin(u * f1 * TAU + phase)
                      + a2 * math.sin(u * f2 * TAU + phase2)
                      + slope * (u - 0.5)) * ah
                th = max(2.0, thick * ah * (
                    0.90 + 0.18 * math.sin(
                        u * 3.3 * TAU + ph1 * 1.7 + anim * 0.4)))
                stripe = 0.5 + 0.5 * math.sin(
                    u * ray_f * TAU
                    + 1.1 * math.sin(u * ray_w * TAU + ray_ph)
                    + phase2 + anim * 0.10)
                mod = 0.84 + 0.16 * math.sin(
                    u * 2.3 * TAU + ph1 * 3.1 + 1.7 + self.hue_shift)
                fine = 0.5 + 0.5 * math.sin(
                    u * 61.0 * TAU
                    + 1.6 * math.sin(u * 9.0 * TAU + ph1))
                gain = (inten * (0.58 + 0.42 * stripe ** 1.4) * mod
                        * (0.80 + 0.20 * fine))
                crown_boost = 1.0 + crown * math.exp(
                    -((u - crown_u) / crown_w) ** 2)
                entries.append((yc, 1.0 / th, gain * crown_boost))
            columns.append(entries)

        n = 256
        dmin, dmax = -3.0, 3.0
        lut = []
        for i in range(n):
            d = dmin + (dmax - dmin) * i / (n - 1)
            if d >= 0.0:
                value = math.exp(-(d / 1.25) ** 2)
            else:
                value = math.exp(-(d / 2.70) ** 2) * (
                    1.0 - 0.30 * smoothstep(-d / 2.70))
            lut.append(value)
        step = (n - 1) / (dmax - dmin)

        # 0.78 is the reviewed field gain; pulse carries the signature breath.
        gain = 0.78 * pulse
        top_fade = float(self.layout.aurora_top)
        floor_start, floor_amount = self.layout.aurora_floor
        for y in range(ah):
            v = y / max(1, ah - 1)
            env = smoothstep(min(1.0, v / max(0.01, top_fade)))
            env *= 1.0 - float(floor_amount) * smoothstep(
                max(0.0, (v - floor_start) / max(0.01, 1.0 - floor_start)))
            if env <= 0.001:
                continue
            cr, cg, cb = ramp[y]
            row = y * aw * 3
            for x in range(aw):
                acc = 0.0
                for (yc, invth, g) in columns[x]:
                    d = (y - yc) * invth
                    idx = int((d - dmin) * step)
                    if 0 <= idx < n:
                        acc += lut[idx] * g
                if acc <= 0.004:
                    continue
                if acc > 1.6:
                    acc = 1.6
                acc *= env
                pos = row + x * 3
                buf[pos] = 0 if cr * acc * gain < 0 else min(
                    255, int(cr * acc * gain))
                buf[pos + 1] = 0 if cg * acc * gain < 0 else min(
                    255, int(cg * acc * gain))
                buf[pos + 2] = 0 if cb * acc * gain < 0 else min(
                    255, int(cb * acc * gain))

        return pygame.image.frombuffer(
            bytes(buf), (aw, ah), "RGB").convert()

    def _make_display(self, time_s: float) -> pygame.Surface:
        """Drift, hue and breath applied to the base field at low resolution."""
        fw, fh = self._field_size
        low = pygame.Surface((fw, fh)).convert()
        low.fill((0, 0, 0))
        phase = TAU * (float(time_s) - REVIEW_TIME) / self.period
        dx = int(round(0.030 * fw * math.sin(phase)))
        dy = int(round(0.012 * fh * math.sin(
            TAU * (float(time_s) - REVIEW_TIME) / (self.period * 0.73))))
        for ox in (-fw, 0, fw):
            low.blit(self._base, (dx + ox, dy))
        hue = 0.5 - 0.5 * math.cos(phase)
        pulse = 0.86 + 0.14 * breath_at(time_s)
        tint = (
            min(255, int(255 * pulse * (1.00 + 0.08 * hue))),
            min(255, int(255 * pulse * (1.00 - 0.02 * hue))),
            min(255, int(255 * pulse * (1.00 - 0.06 * hue))),
        )
        low.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
        self._low = low
        return low

    def surface(self, time_s: float, force: bool = False) -> pygame.Surface:
        """The upscaled field, refreshed at the quality's rate."""
        time_s = float(time_s)
        if (not force and self._surface is not None
                and time_s < self._next_build):
            return self._surface
        low = self._make_display(time_s)
        self._surface = pygame.transform.smoothscale(low, (self.sw, self.sh))
        self._last_time = time_s
        self._next_build = time_s + 1.0 / self._refresh
        return self._surface
