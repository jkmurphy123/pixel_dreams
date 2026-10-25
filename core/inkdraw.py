# core/inkdraw.py
"""
The drawing vocabulary: nib sizes, the hand, and the marks it makes.

Everything here is deliberately small and physical. Two facts drive it:

  * A **nib is a millimetre size**, not a pixel count. The tutorials use Sakura Pigma Microns in
    six weights, and what makes a drawing look hand-inked is that the heavier passes are visibly
    heavier. `pen_widths()` converts the real nib table against the sheet, so the same drawing on
    a bigger screen gets proportionally heavier lines rather than a spider web.
  * A hand-drawn line is **not a straight line with noise on it**. What the artist gets by holding
    the pen higher up is a low-frequency wander -- the line drifts off course and comes back -- plus
    a fine tremor on top. `Hand` models exactly that, as an AR(1) walk, so consecutive strokes
    carry on from where the last one drifted to instead of each restarting.

Coordinates, widths and amplitudes are all in the coordinate system of the surface being drawn
onto (for this mode, the supersampled ink layer), so nothing here needs to know about the screen.
"""

from __future__ import annotations

import math
import random

import pygame

#: Real Sakura Pigma Micron nibs in millimetres, plus the soft brush tip the tutorials use when
#: they want a stroke that swells and tapers. The numbers are the manufacturer's.
NIB_MM = {
    "003": 0.15,
    "005": 0.20,
    "01": 0.25,
    "02": 0.30,
    "03": 0.35,
    "05": 0.45,
}

#: The sheet the nibs were measured against: a 200 mm wide page of drawing paper.
REFERENCE_SHEET_MM = 200.0

#: Light comes from the LEFT, so every feature shades on its RIGHT-hand side. The tutorials say
#: this twice ("you do want them to match the shading of your mountains"). One constant, obeyed by
#: every recipe in every phase -- a sheet that shades both ways at once looks machine-made
#: whatever the texture is like.
LIGHT = "left"

#: Per-segment width wobble, and how a nib's pressure falls off at the ends of a stroke. A real
#: stroke is heaviest in the middle because that is where the hand presses and the arm is moving.
WIDTH_WOBBLE = 0.10
_PRESSURE_FLOOR = 0.30

#: How far the pen wanders off course, in millimetres on the reference sheet, at `tremor = 1.0`
#: (the AR(1) walk below has a std of ~1.44, so the real excursion is about 1.4x this).
#: Expressed physically for the same reason the nibs are: the dial should mean the same thing on
#: any display. 0.45 mm is chosen so the default 0.55 reads as a scraggly hand-drawn line at arm's
#: length without looking like a mistake.
TREMOR_MM = 0.45
FINE_FRACTION = 0.25


def pen_widths(short_side_px: float, scale: float = 1.0) -> dict:
    """
    The nib table as stroke widths in the surface's own units.

    `short_side_px` is the surface being drawn on, so a 2160 px wide ink layer gets widths twice
    what a 1080 px screen would. `scale` is the `pen_scale` parameter: a fair way to make the whole
    drawing lighter or heavier without pretending to be a different nib.
    """
    px_per_mm = max(0.1, float(short_side_px)) / REFERENCE_SHEET_MM
    return {name: max(0.6, mm * px_per_mm * float(scale)) for name, mm in NIB_MM.items()}


class Hand:
    """
    The hand holding the pen.

    `offset()` is an AR(1) process: each call nudges the drift, and the drift persists, so a run of
    strokes wanders the way a line drawn without a ruler wanders. Drawing a long outline in chunks
    therefore needs ONE Hand for the whole outline, not one per chunk -- otherwise the wander
    restarts at every chunk boundary and the line develops a visible kink there.
    """

    def __init__(self, seed: int = 0, tremor: float = 0.55, px_per_mm: float = 5.4,
                 wander: float = 0.72):
        self.rng = random.Random(seed)
        self.tremor = max(0.0, float(tremor))
        self.wander = float(wander)
        self.drift = 0.0
        #: Lateral amplitude of the wander and of the fine tremor, in surface units.
        self.amplitude = self.tremor * TREMOR_MM * float(px_per_mm)
        self.fine = self.amplitude * FINE_FRACTION

    def offset(self) -> float:
        self.drift = self.drift * self.wander + self.rng.gauss(0.0, 1.0)
        return self.drift

    def jitter(self, points) -> list:
        """Displace each vertex perpendicular to the local direction of travel."""
        count = len(points)
        if count < 2:
            return list(points)
        out = []
        for i, (x, y) in enumerate(points):
            if i == 0:
                dx, dy = points[1][0] - x, points[1][1] - y
            elif i == count - 1:
                dx, dy = x - points[i - 1][0], y - points[i - 1][1]
            else:
                dx = points[i + 1][0] - points[i - 1][0]
                dy = points[i + 1][1] - points[i - 1][1]
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            shift = self.offset() * self.amplitude + self.rng.gauss(0.0, self.fine)
            out.append((x + nx * shift, y + ny * shift))
        return out


def pressure(t: float) -> float:
    """Nib pressure along a stroke: light at the ends, full in the middle."""
    t = min(1.0, max(0.0, t))
    return _PRESSURE_FLOOR + (1.0 - _PRESSURE_FLOOR) * math.sin(math.pi * t) ** 0.45


def stroke(surface, points, width, hand: Hand, *, taper: bool = False, colour=(0, 0, 0, 255)):
    """
    One pen stroke: the jittered path, drawn segment by segment as a tapered quad.

    Returns the bounding rect it drew into, in the surface's units, so the caller can mark exactly
    that much of the sheet dirty -- which is what keeps a supersampled reveal cheap. Per-segment
    polygons rather than `draw.line`, because `draw.line` cannot vary its width along a stroke and
    a pen line that never varies is the thing this module exists to avoid.
    """
    if len(points) < 2 or width <= 0:
        return None
    path = hand.jitter(points)
    segs = len(path) - 1
    left = top = math.inf
    right = bottom = -math.inf
    for i in range(segs):
        x0, y0 = path[i]
        x1, y1 = path[i + 1]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 0.02:
            continue
        w = width * (1.0 + hand.rng.gauss(0.0, WIDTH_WOBBLE))
        if taper:
            w *= pressure(i / max(1, segs - 1))
        half = max(0.35, w * 0.5)
        nx, ny = -dy / length * half, dx / length * half
        quad = ((x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                (x1 - nx, y1 - ny), (x0 - nx, y0 - ny))
        pygame.draw.polygon(surface, colour, quad)
        # Over ALL FOUR corners: which pair is "top" depends on which way the segment runs, and
        # assuming otherwise under-reports the rect for horizontal or vertical strokes. That is not
        # a cosmetic error -- the caller composites only what this rect covers, so ink outside it
        # simply never reaches the paper.
        left = min(left, quad[0][0], quad[1][0], quad[2][0], quad[3][0])
        top = min(top, quad[0][1], quad[1][1], quad[2][1], quad[3][1])
        right = max(right, quad[0][0], quad[1][0], quad[2][0], quad[3][0])
        bottom = max(bottom, quad[0][1], quad[1][1], quad[2][1], quad[3][1])
    if left is math.inf:
        return None
    return pygame.Rect(int(math.floor(left)), int(math.floor(top)),
                       int(math.ceil(right - left)) + 2, int(math.ceil(bottom - top)) + 2)
