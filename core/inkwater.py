# core/inkwater.py
"""
The sea: a line traced parallel to the coast, and the video's four units hung off it.

The tutorials' water pass, in their own order:

  1. with the `005` nib, trace a line all the way round the coast, parallel to it, a little way out
     ("it does not have to be perfect"); continue round any islands before carrying on;
  2. hang little hashes off that line, going out to sea;
  3. between the lines, add more hashes and dots.
The four things they alternate between are **hash**, **hash + dot**, **hash-dot-hash** and
**dot-hash** -- and the alternation is the whole trick. The artist says it twice: a single pattern
"reads as a comb", and it is the random mixing of the four that makes the sea look like sea. Every
alternate treatment (squiggles, stippling, waves) keeps the same four-unit rhythm and swaps only the
mark itself.

Three calibration facts, all measured rather than chosen (`designs/inkmap_proto/WATER_SPIKE*.py`,
design doc section 5):

  * **Ring offsets are the design's measured 13 / 21 / 29 ink px** on this panel: 1.20 mm out from
    the coast, then every 0.75 mm. Held in millimetres so the sea reads the same on any surface.
  * **The marks must be SPARSE.** One unit every 2.4-4.8 mm, each hash only 0.9-1.7 mm long. A first
    attempt put a mark every 1.5 mm along the ring -- under three times the density -- and the sea
    came out reading as fur, because the hashes then overlapped one another. This is the dial that
    ruins the pass.
  * **Hashes shrink as the rings go out** (x0.84 per ring). Without that the outermost ring competes
    with the coastline and the coast stops reading as the darkest line on the sheet.

The parallel line is made by pushing the coast polyline out along its vertex normals. That folds over
where the coast is concave by more than the offset, and at these distances the folds are rare enough
to be invisible inside a light hatch -- but the distances are NOT free to raise: at 3.5 mm out the
same code turned the sea into barbed wire. The alternative that cannot fold is a morphological
dilation of the mask, and it was rejected on cost: 540 ms against 10 ms for every mass, because it
needs a marching-squares pass per ring (measured, `WATER_SPIKE2.py`).
"""

from __future__ import annotations

import math

import pygame

#: How far the first ring sits from the coast and the gap between rings, in millimetres.
#:
#: DEVIATION FROM THE DESIGN, ON LOOKING AT IT. The design carried 13 / 21 / 29 ink px here, measured
#: off the earlier prototype. Rendered for real, that band is 6.5-14.5 SCREEN px wide on a continent
#: 500 px across -- narrower than three line widths, so the sea read as a ruffled fringe trimming the
#: coast rather than as water the land sits in. Looking at the tutorial's own maps, the hatched band
#: is roughly 5-10% of the land's width, which on this panel is 4-9 mm. These are the widened values
#: (2.0 mm out, then every 1.6 mm) and the sea finally reads as sea.
RING_FIRST_MM = 2.00
RING_STEP_MM = 1.60

#: Hash length in millimetres (a range, drawn per hash) and the shrink per ring going out. The hashes
#: are sized against the RING STEP: a hash shorter than the gap between rings leaves a gap of bare
#: paper inside the band, and one much longer crosses two rings and reads as a comb.
HASH_MM = (1.40, 2.40)
HASH_SHRINK = 0.84

#: How far along a ring one unit sits, in millimetres. Sparse on purpose -- a first attempt at one
#: unit per 1.5 mm came out as fur -- but too sparse and the band reads as railway sleepers: two ruled
#: lines with a mark every few millimetres between them. This is the density that fills the band
#: without letting the hashes touch each other.
UNIT_PITCH_MM = (1.6, 3.2)

#: How far a hash may lean off the ring's normal, in radians (about 12 degrees). Every hash exactly
#: perpendicular is the tell that the sea is machine-made: a hand drawing ticks along a coast leans
#: each one a little, and the eye reads the variation as care rather than as error.
HASH_LEAN_RADIANS = 0.21

#: How much of a ring one plan item covers. The reveal paces per item, so this is the grain of the
#: sea's animation -- 4 mm keeps the pen's advance near the coast's own rate.
ARC_MM = 4.0

#: How finely the coast is resampled before it is offset, and over how many vertices the result is
#: averaged first. The averaging is the load-bearing part: this coast's scallops are the SAME ORDER OF
#: SIZE as the ring offsets, so a true parallel curve folds at nearly every one of them -- measured,
#: a 2 mm band without smoothing is a braid of doubled lines and dark knots. Smoothing over ~4 mm
#: makes the ring follow the shape a hand would see and trace, and the fold cutter then has almost
#: nothing to cut.
RING_SOURCE_STEP_MM = 0.65
RING_SOURCE_SMOOTH = 16

#: Lake radius in millimetres, and how far a lake's centre must be from the coast (in radii) so the
#: inward rings have room. The vertical squash is the prototype's: a true circle reads as a hole punch.
LAKE_RADIUS_MM = (2.8, 5.1)
LAKE_CLEARANCE_FACTOR = 1.15
LAKE_SQUASH = 0.78

#: The video's four units, as the tokens that make them up.
UNITS = (
    ('hash',),
    ('hash', 'dot'),
    ('hash', 'dot', 'hash'),
    ('dot', 'hash'),
)

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1))

#: Dots are pre-rendered per radius and colour. A sea has thousands of them, and building a fresh
#: surface per dot is the kind of cost that turns a 50 ms pass into a second.
_DOT_CACHE: dict = {}


def _stroke(surface, points, width, hand, colour):
    """`inkdraw.stroke`, imported lazily so this module keeps no import cycle with it."""
    from core import inkdraw
    return inkdraw.stroke(surface, points, width, hand, colour=colour)


def _dot(surface, x, y, radius, colour):
    key = (round(float(radius) * 2) / 2, tuple(colour))
    sprite = _DOT_CACHE.get(key)
    if sprite is None:
        size = max(1, int(round(radius)))
        sprite = pygame.Surface((size * 2 + 1, size * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(sprite, colour, (size, size), size)
        _DOT_CACHE[key] = sprite
    left = int(x - sprite.get_width() / 2.0)
    top = int(y - sprite.get_height() / 2.0)
    surface.blit(sprite, (left, top))
    return pygame.Rect(left, top, sprite.get_width(), sprite.get_height())


def _invert(surface):
    out = pygame.Surface(surface.get_size())
    out.fill((255, 255, 255))
    out.blit(surface, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    return out


def dilate(surface, steps: int):
    """Grow by `steps` cells. One blit set per step: 8 blits, not (2r+1)^2."""
    layer = surface.copy()
    for _ in range(max(0, int(steps))):
        base = layer
        grown = base.copy()
        for dx, dy in _NEIGHBOURS:
            grown.blit(base, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)
        layer = grown
    return layer


def erode(surface, steps: int):
    """Shrink by `steps` cells: grow the water into the land, keep what is left."""
    return _invert(dilate(_invert(surface), steps))


def ring_offsets(count: int, px_per_mm: float) -> list:
    """The ring distances out from the coast, in surface units, nearest first."""
    count = max(0, int(count))
    return [(RING_FIRST_MM + RING_STEP_MM * i) * px_per_mm for i in range(count)]


def outward_sign(pour, points, closed: bool) -> float:
    """
    +1 or -1: which way a normal must point to leave the land. Tested, never assumed.

    The contour's winding depends on which side the land fell, and getting it backwards draws the
    whole sea on top of the continent.
    """
    n = len(points)
    if n < 4:
        return 1.0
    probe = 0.6 * (pour.cell_x + pour.cell_y)
    for i in range(2, n - 2, max(1, n // 40)):
        px, py = points[i - 1]
        nx, ny = points[i + 1]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        for sign in (1.0, -1.0):
            if not pour.on_land(cx + (-dy / length) * probe * sign,
                                cy + (dx / length) * probe * sign):
                return sign
    return 1.0


def offset_ring(points, closed: bool, distance: float, sign: float) -> list:
    """
    A parallel curve `distance` out from the polyline.

    Open chains are NOT wrapped: a coast that runs off the sheet has two real ends, and joining them
    would draw the chord across the picture that phase 2 exists to avoid.
    """
    n = len(points)
    if n < 3:
        return []
    out = []
    for i in range(n):
        left = i - 1 if i > 0 else (n - 1 if closed else 0)
        right = i + 1 if i < n - 1 else (0 if closed else n - 1)
        px, py = points[left]
        nx, ny = points[right]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        out.append((cx + (-dy / length) * distance * sign,
                    cy + (dx / length) * distance * sign))
    return out


def smooth(points, window: int, closed: bool = False) -> list:
    """
    A moving average over the polyline, ends clamped (and wrapped when the chain is closed).

    This is the single most important step for the parallel curve, and it is what a hand does: nobody
    traces every scallop of the coast again in the water line, they draw a line parallel to the shape
    they SEE. Mechanically it removes the fine concavities that a parallel curve folds into -- and the
    coast's scallops are the same order of size as the ring offsets, so without it the sea is a braid
    no matter how the lines are drawn.
    """
    window = max(1, int(window))
    n = len(points)
    if window <= 1 or n < window * 2:
        return list(points)
    half = window // 2
    # prefix sums, not a sum per window: the naive form is O(n * window) and this runs three times
    # over every vertex of every ring -- ~600 000 operations for one sheet, which is 300 ms of the
    # build. Written this way it is a single pass.
    if closed:
        extended = [points[(i - half) % n] for i in range(n + window)]
    else:
        extended = [points[min(max(i - half, 0), n - 1)] for i in range(n + window)]
    xs = [0.0] * (len(extended) + 1)
    ys = [0.0] * (len(extended) + 1)
    for i, (x, y) in enumerate(extended):
        xs[i + 1] = xs[i] + x
        ys[i + 1] = ys[i] + y
    return [((xs[i + window] - xs[i]) / window, (ys[i + window] - ys[i]) / window)
            for i in range(n)]


def water_length(pour, base, nx, ny, length: float, steps: int = 5) -> float:
    """
    How far a hash may run from `base` along `(nx, ny)` before it would be drawn on the land.

    Measured: without this, 162 of 1696 hashes ended on the continent. The cause is bays -- the ring
    runs outside the coast, but across a narrow inlet the outward normal points at the far shore, so a
    full-length hash crosses the water and inks the land. Clipping costs a handful of point tests per
    hash and is the difference between "the sea surrounds the land" and "the sea is scribbled over it".
    """
    safe = 0.0
    for i in range(1, max(1, steps) + 1):
        reach = length * i / max(1, steps)
        if pour.on_land(base[0] + nx * reach, base[1] + ny * reach):
            break
        safe = reach
    return safe


def cut_folds(source, ring, cos_limit: float = 0.05) -> list:
    """
    Split a parallel curve where it folds over itself, and return the runs.

    Where the coast is concave by more than the offset, the parallel curve doubles back and crosses
    itself; drawn, those crossings are the tangle that makes hatched water look like barbed wire.
    At a fold the curve's local direction REVERSES relative to the coast's, so the test is the sign
    of the dot product of the two local directions. Cutting there is a pen lift, which is exactly what
    the video means by "it does not have to be perfect" -- and the alternate styles deliberately add
    "natural breaks" too.

    Without this, a sea band wide enough to read as sea (2.0 mm and out) is a braid: the ring step is
    then larger than the coast's own scallops, so almost every concave wiggle folds.
    """
    if len(ring) < 3:
        return [list(ring)] if len(ring) >= 2 else []
    runs = []
    current = [ring[0]]
    for i in range(1, min(len(ring), len(source))):
        sx, sy = source[i][0] - source[i - 1][0], source[i][1] - source[i - 1][1]
        rx, ry = ring[i][0] - ring[i - 1][0], ring[i][1] - ring[i - 1][1]
        source_len = math.hypot(sx, sy)
        ring_len = math.hypot(rx, ry)
        if source_len > 1e-9 and ring_len > 1e-9:
            if (sx * rx + sy * ry) / (source_len * ring_len) < cos_limit:
                if len(current) >= 2:
                    runs.append(current)
                current = []
        current.append(ring[i])
    if len(current) >= 2:
        runs.append(current)
    return runs


def style_mark(style: str, base, tip, rng, width: float) -> list:
    """
    One hash position, drawn in the chosen sea style, as `('line', points, width)` or
    `('dot', (x, y), radius)` tokens.

    Every style keeps the same four-unit rhythm and the same dots between units; only the hash
    changes. That is what the video does -- its alternates are "the same technique, adding breaks and
    dots", "just squiggles instead of rigid straight lines", stippling, and waves.
    """
    bx, by = base
    tx, ty = tip
    dx, dy = tx - bx, ty - by
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length               # along the hash
    sx, sy = -uy, ux                                # across it

    if style == 'stipple':
        return [('dot', (bx + ux * length * f, by + uy * length * f), 1.5)
                for f in (0.08, 0.40, 0.72, 0.97)]

    if style == 'squiggle':
        wobble = length * rng.uniform(0.18, 0.34)
        first = [(bx, by),
                 (bx + ux * length * 0.20 + sx * wobble, by + uy * length * 0.20 + sy * wobble),
                 (bx + ux * length * 0.38, by + uy * length * 0.38)]
        second = [(bx + ux * length * 0.58 - sx * wobble * 0.7,
                   by + uy * length * 0.58 - sy * wobble * 0.7),
                  (bx + ux * length * 0.80, by + uy * length * 0.80),
                  (tx, ty)]
        return [('line', first, width), ('line', second, width)]

    if style == 'wave':
        swing = length * rng.choice((-1.0, 1.0)) * rng.uniform(0.25, 0.45)
        return [('line', [(bx, by),
                          (bx + ux * length * 0.33 + sx * swing, by + uy * length * 0.33 + sy * swing),
                          (bx + ux * length * 0.67 + sx * swing, by + uy * length * 0.67 + sy * swing),
                          (tx, ty)], width)]

    return [('line', [(bx, by), (tx, ty)], width)]


class WaterItem:
    """One arc of a ring (or a lake ring): its parallel line, and the units hung off it."""

    __slots__ = ('points', 'marks', 'width')

    def __init__(self, points, marks, width):
        self.points = points
        self.marks = marks
        self.width = width

    def draw(self, surface, hand, pens, colour) -> list:
        """Draw it, and return the rects it touched -- which is what the caller marks dirty."""
        rects = []
        if len(self.points) >= 2:
            rect = _stroke(surface, self.points, self.width, hand, colour)
            if rect is not None:
                rects.append(rect)
        for token in self.marks:
            if token[0] == 'line':
                _kind, points, width = token
                rect = _stroke(surface, points, width, hand, colour)
                if rect is not None:
                    rects.append(rect)
            else:
                _kind, (x, y), radius = token
                rects.append(_dot(surface, x, y, radius, colour))
        return rects


def ring_items(points, closed: bool, distance: float, sign: float, *, pour, pens, hand,
               ring_index: int, style: str, px_per_mm: float) -> list:
    """
    One ring: the parallel line cut into arcs, each arc carrying the units that fall on it.

    Items rather than drawing, because the reveal paces per item and the sea is most of the plan.
    """
    from core import inkland

    step = max(1.0, RING_SOURCE_STEP_MM * px_per_mm)
    source = smooth(inkland.resample(points, step), RING_SOURCE_SMOOTH, closed=closed)
    raw = offset_ring(source, closed, distance, sign)
    runs = [inkland.resample(run, step) for run in cut_folds(source, raw)]
    runs = [run for run in runs if len(run) >= 3]
    if not runs:
        return []

    rng = hand.rng
    width = pens['005'] * 0.9
    hash_len = [h * px_per_mm * (HASH_SHRINK ** ring_index) for h in HASH_MM]
    arc_limit = ARC_MM * px_per_mm
    pitch = rng.uniform(*UNIT_PITCH_MM) * px_per_mm

    items = []
    unit = 0
    for run in runs:
        arc_points = [run[0]]
        arc_marks = []
        arc_length = 0.0
        travelled = 0.0
        for i in range(1, len(run)):
            px, py = run[i - 1]
            cx, cy = run[i]
            seg = math.hypot(cx - px, cy - py)
            arc_points.append(run[i])
            arc_length += seg
            travelled += seg

            if travelled >= pitch and 2 <= i < len(run) - 2:
                travelled = 0.0
                pitch = rng.uniform(*UNIT_PITCH_MM) * px_per_mm
                ax, ay = run[i - 2]
                bx, by = run[i + 1]
                dx, dy = bx - ax, by - ay
                length = math.hypot(dx, dy) or 1.0
                nx, ny = -dy / length, dx / length
                if pour.on_land(cx + nx * distance * 0.35, cy + ny * distance * 0.35):
                    nx, ny = -nx, -ny
                lean = math.atan2(ny, nx) + rng.uniform(-HASH_LEAN_RADIANS, HASH_LEAN_RADIANS)
                nx, ny = math.cos(lean), math.sin(lean)
                ln = water_length(pour, (cx, cy), nx, ny, rng.uniform(*hash_len))
                if ln <= 0.0:
                    continue                      # the ring is already over land here: nothing to hang
                base = (cx, cy)
                tip = (cx + nx * ln, cy + ny * ln)
                for token in UNITS[unit % len(UNITS)]:
                    if token == 'hash':
                        arc_marks.extend(style_mark(style, base, tip, rng, pens['005']))
                    else:
                        arc_marks.append(('dot', (cx + nx * ln * 0.55, cy + ny * ln * 0.55), 1.8))
                unit += 1

            if arc_length >= arc_limit:
                items.append(WaterItem(arc_points, arc_marks, width))
                arc_points = [run[i]]
                arc_marks = []
                arc_length = 0.0

        if len(arc_points) >= 2 or arc_marks:
            items.append(WaterItem(arc_points, arc_marks, width))
    return items


def coast_water(masses, pour, *, pens, hand, style: str, rings: int, px_per_mm: float) -> list:
    """The whole sea: every ring of every land mass, biggest mass first, nearest ring first."""
    items = []
    distances = ring_offsets(rings, px_per_mm)
    if not distances:
        return items
    for points, closed, _area in masses:
        sign = outward_sign(pour, points, closed)
        for index, distance in enumerate(distances):
            items.extend(ring_items(points, closed, distance, sign, pour=pour, pens=pens,
                                    hand=hand, ring_index=index, style=style,
                                    px_per_mm=px_per_mm))
    return items


def lake_items(pour, rng, count: int, *, pens, hand, style: str, px_per_mm: float) -> list:
    """
    Lakes inland: the same water pass run on the INSIDE of a small closed contour, which is exactly
    what the video says a lake is.

    Placement is by EROSION rather than a distance field: growing the water into the land by `r` and
    keeping what survives is literally "land at least r from the coast", and it costs a blit per step
    instead of a Python loop over a quarter of a million cells.
    """
    count = max(0, int(count))
    if count == 0 or pour.closed_surface is None:
        return []

    radius = rng.uniform(*LAKE_RADIUS_MM) * px_per_mm
    clearance = int(math.ceil(radius * LAKE_CLEARANCE_FACTOR / max(1e-6, pour.cell_x)))
    spots = clear_land_spots(pour, clearance, rng, count, min_separation=radius * 2.4)

    items = []
    for cx, cy in spots:
        r = rng.uniform(*LAKE_RADIUS_MM) * px_per_mm
        outline = lake_outline(cx, cy, r, rng)
        items.append(WaterItem(outline, [], pens['01']))
        items.extend(lake_contents(outline, (cx, cy), pens))
    return items


def lake_outline(cx, cy, r, rng) -> list:
    """A wobbly closed blob, squashed vertically so it reads as a lake and not as a hole punch."""
    from core import inkland

    count = 16
    start = rng.uniform(0.0, math.tau)
    points = []
    for i in range(count + 1):
        angle = start + math.tau * i / count
        rr = r * rng.uniform(0.70, 1.20)
        points.append((cx + math.cos(angle) * rr, cy + math.sin(angle) * rr * LAKE_SQUASH))
    points.append(points[0])
    return inkland.resample(points, max(4.0, r * 0.22))


def lake_contents(outline, centre, pens) -> list:
    """
    The inward rings: the same sea pass, stepping toward the middle of the lake.

    No style and no hand: the prototype's recipe for a small lake is three shrinking rings with dots
    along them, and at 6-12 screen px across there is no room for the coast's four-unit rhythm. The
    dots ARE the lake's texture.
    """
    from core import inkland

    items = []
    for k in range(3):
        fraction = 0.16 + 0.15 * k
        inner = []
        for x, y in outline:
            dx, dy = centre[0] - x, centre[1] - y
            inner.append((x + dx * fraction, y + dy * fraction))
        if k == 2:
            items.append(WaterItem([], [('dot', (x, y), 1.4) for x, y in inner[::3]], pens['005']))
            continue
        ring = inkland.resample(inner, 12.0)
        items.append(WaterItem(ring, [('dot', (x, y), 1.5) for x, y in ring[::2]],
                               pens['005'] * 0.8))
    return items


def clear_land_spots(pour, clearance_cells: int, rng, wanted: int, min_separation: float):
    """
    `wanted` points on land, each at least `clearance_cells` from the water and `min_separation`
    apart. Erode, list what survives, then pick greedily with spacing.
    """
    from core import inkland

    if pour.closed_surface is None:
        return []
    left = erode(pour.closed_surface, clearance_cells)
    mask = inkland._read_mask(left, pour.gw, pour.gh)
    order = [index for index in range(pour.gw * pour.gh) if mask[index]]
    if not order:
        return []
    rng.shuffle(order)

    separation_cells = max(1.0, min_separation / max(1e-6, pour.cell_x))
    chosen = []
    chosen_cells = []
    for index in order:
        gx = index % pour.gw
        gy = index // pour.gw
        # Compare in CELLS, the units the separation is expressed in. Comparing a squared distance in
        # surface units against a squared threshold in cells silently passes almost anything: measured,
        # two lakes 45 px apart sailed through a 60 px minimum and could overlap on the sheet.
        if all((gx - ox) ** 2 + (gy - oy) ** 2 >= separation_cells ** 2 for ox, oy in chosen_cells):
            chosen.append(((gx + 0.5) * pour.cell_x, (gy + 0.5) * pour.cell_y))
            chosen_cells.append((gx, gy))
            if len(chosen) >= wanted:
                break
    return chosen
