# core/inkland.py
"""
Poured rice, and the outline traced around it.

The tutorials start a map by pouring rice onto the paper in clumps, nudging it about, and drawing
round the outside edge with a heavy pen. Three things make that work in code, and each of them was
measured rather than assumed (design doc §5):

  * **A grain is a physical size.** `field_metrics()` fixes the tracing grid in PHYSICAL terms, so
    the cost of tracing does not move when the grain-size dial does; the dial changes how many
    grid cells one grain spans, which is what sets the scale of the scalloped edge.
  * **The nudge is a morphological closing.** Welding the grains that merely touch into one mass is
    what turns a grainy scatter into a solid continent, and it does so WITHOUT rounding off the
    scalloped edge -- which is the difference between a traced pour and a blob. Done with surface
    blits, because a Python loop over a quarter of a million cells is ~50x slower.
  * **An outline that leaves the field is OPEN.** Appending its first point to close it draws a
    ruler-straight line across the picture, which is the single ugliest artefact this pipeline can
    produce. Every loop is therefore returned with a `closed` flag and the caller must respect it.
"""

from __future__ import annotations

import math

import pygame

#: A grain of rice on a 200 mm sheet, and the field resolution the grain dial is measured against.
#: `grain_size_cells` says how many grid cells one grain spans; 5 is the reference.
GRAIN_MM = 2.5
CELLS_AT_REFERENCE = 5.0

#: Grains lie flat and at all angles, so a pour is made of rotated ellipses rather than discs.
GRAIN_ASPECTS = (0.34, 0.45, 0.58)
GRAIN_ANGLES = 24

#: Grain footprints per field cell of clump. A flat grain covers ~9 cells at the reference size, but
#: they overlap by roughly 2x and the closing fills the gaps, so a solid clump needs about this many
#: grains per cell of its area. Calibrated by measuring the coverage a pour actually achieves.
FILL_PER_CELL = 0.25

#: What a single pour actually covers, measured against the clump footprint it was aimed at. The
#: pour saturates: a Gaussian clump's tail spreads land well beyond the clump's nominal area and the
#: closing welds loose grains into it, so aiming the footprint straight at the target overshoots
#: badly -- asking for 0.20 of the sheet produced 0.40 of it. Inverting this measured table means the
#: first attempt lands close and the one allowed correction pass only tidies up rounding.
#: Measured at the reference grain size on the 1080x1920 panel (design doc section 8).
FOOTPRINT_RESPONSE = (
    (0.00, 0.000),
    (0.20, 0.402),
    (0.30, 0.565),
    (0.45, 0.745),
    (0.55, 0.839),
    (0.70, 0.931),
    (0.85, 0.978),
    (1.00, 1.000),
)


def _footprint_for(coverage: float) -> float:
    """The clump footprint that makes one pour land on `coverage`, by inverting the table above."""
    target = min(0.985, max(0.0, float(coverage)))
    for i in range(1, len(FOOTPRINT_RESPONSE)):
        footprint_0, covered_0 = FOOTPRINT_RESPONSE[i - 1]
        footprint_1, covered_1 = FOOTPRINT_RESPONSE[i]
        if target <= covered_1:
            if covered_1 <= covered_0:
                return footprint_1
            t = (target - covered_0) / (covered_1 - covered_0)
            return footprint_0 + (footprint_1 - footprint_0) * t
    return FOOTPRINT_RESPONSE[-1][0]


def field_metrics(ink_w: float, ink_h: float, px_per_mm: float):
    """
    The tracing grid, in physical units.

    Fixed deliberately: the grid's resolution decides the cost of the marching-squares pass, so it
    must not follow the grain-size dial. Returns `(gw, gh, cell_px_x, cell_px_y)`.
    """
    cell = max(1.0, GRAIN_MM * float(px_per_mm) / CELLS_AT_REFERENCE)
    gw = max(48, int(round(ink_w / cell)))
    gh = max(48, int(round(ink_h / cell)))
    return gw, gh, ink_w / gw, ink_h / gh


def grain_sprites(diameter_px: float):
    """
    The rice, pre-rendered at every angle: flat ellipses, three thicknesses.

    Drawn oversampled and scaled down when the grain is only a few pixels across. A grain is a fixed
    number of field cells, but on a small surface those cells are only a few pixels wide, and a 6x2
    ellipse rasterised directly loses a good part of its area to integer rounding -- which quietly
    changed how much land a pour covered at small surface sizes and nowhere else.
    """
    size = max(3, int(round(diameter_px)))
    oversample = 4 if size < 12 else 1
    out = []
    for aspect in GRAIN_ASPECTS:
        base = pygame.Surface((size * oversample, size * oversample), pygame.SRCALPHA)
        height = max(2, int(round(base.get_height() * aspect)))
        pygame.draw.ellipse(base, (255, 255, 255, 255),
                            (0, (base.get_height() - height) // 2, base.get_width(), height))
        for a in range(GRAIN_ANGLES):
            rotated = pygame.transform.rotate(base, a * 180.0 / GRAIN_ANGLES)
            if oversample > 1:
                rotated = pygame.transform.smoothscale(
                    rotated, (max(3, rotated.get_width() // oversample),
                              max(3, rotated.get_height() // oversample)))
            out.append(rotated)
    return out


def _read_mask(surface, gw: int, gh: int) -> bytearray:
    """
    The mask as one byte per cell.

    One `tostring` and one stride-3 pass: reading a surface a pixel at a time from Python is the
    slow way to do this, and the C rasteriser can stamp tens of thousands of grains in tens of ms.
    """
    raw = pygame.image.tostring(surface, "RGB")
    mask = bytearray(gw * gh)
    for i in range(len(mask)):
        if raw[i * 3]:
            mask[i] = 1
    return mask


def close_mask(surface, r: int = 2):
    """Dilate then erode. Welds touching grains without rounding the outline."""
    gw, gh = surface.get_size()
    r = max(0, int(r))
    if r:
        dilated = surface.copy()
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx or dy:
                    dilated.blit(surface, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)

        inverted = pygame.Surface((gw, gh))
        inverted.fill((255, 255, 255))
        inverted.blit(dilated, (0, 0), special_flags=pygame.BLEND_RGB_SUB)

        regrown = inverted.copy()
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx or dy:
                    regrown.blit(inverted, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)

        out = pygame.Surface((gw, gh))
        out.fill((255, 255, 255))
        out.blit(regrown, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        return out
    return surface.copy()


def marching_squares(mask, gw: int, gh: int):
    """
    Cell corners -> the segments that separate land from water.

    The two saddle cases (5 and 10) take DIFFERENT pairs of edges. Using one pairing for both makes
    the segments cross each other, which leaves nodes with four segments meeting, and the chaining
    walk then jumps between unrelated loops: the symptom is straight lines leaping across the map.
    """
    segments = []
    append = segments.append
    for y in range(gh - 1):
        row = y * gw
        below = row + gw
        for x in range(gw - 1):
            a = mask[row + x]
            b = mask[row + x + 1]
            c = mask[below + x + 1]
            d = mask[below + x]
            if a == b == c == d:
                continue
            case = a | (b << 1) | (c << 2) | (d << 3)
            top = (x + 0.5, y)
            right = (x + 1.0, y + 0.5)
            bottom = (x + 0.5, y + 1.0)
            left = (x, y + 0.5)
            if case in (1, 14):
                append((left, top))
            elif case in (2, 13):
                append((top, right))
            elif case in (3, 12):
                append((left, right))
            elif case in (4, 11):
                append((right, bottom))
            elif case in (6, 9):
                append((top, bottom))
            elif case in (7, 8):
                append((left, bottom))
            elif case == 5:                      # a and c are land: the diagonal joins them
                if (a + b + c + d) * 0.25 > 0.5:
                    append((left, right)); append((top, bottom))
                else:
                    append((left, top)); append((right, bottom))
            elif case == 10:                     # b and d are land: the OTHER pairing
                if (a + b + c + d) * 0.25 > 0.5:
                    append((left, right)); append((top, bottom))
                else:
                    append((top, right)); append((left, bottom))
    return segments


def chain_loops(segments, min_len: int = 4):
    """
    Unordered segments -> `[(points, closed)]`. Open chains are NOT closed.

    `min_len` only drops degenerate fragments. It must stay low: a small closed island has a short
    contour, and at the original default of 10 the chaining walk threw such loops away before the
    caller's size filter ever saw them -- a second, invisible filter on top of the one that is
    supposed to decide what counts as an island.
    """
    from collections import defaultdict

    buckets = defaultdict(list)
    for index, (p, q) in enumerate(segments):
        buckets[p].append(index)
        buckets[q].append(index)
    used = bytearray(len(segments))
    loops = []
    for start in range(len(segments)):
        if used[start]:
            continue
        p, q = segments[start]
        used[start] = 1
        loop = [p, q]
        current = q
        closed = False
        while True:
            nxt = None
            for index in buckets[current]:
                if not used[index]:
                    nxt = index
                    break
            if nxt is None:
                break
            used[nxt] = 1
            a, b = segments[nxt]
            current = b if a == current else a
            loop.append(current)
            if current == loop[0]:
                closed = True
                break
        if len(loop) >= min_len:
            if closed:
                loop.append(loop[0])
            loops.append((loop, closed))
    return loops


def resample(points, step: float):
    """Even spacing along a polyline, so pen strokes are not drawn through 2000 tiny segments."""
    if len(points) < 2 or step <= 0:
        return list(points)
    out = [points[0]]
    carry = 0.0
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= 0.0:
            continue
        carry += seg
        while carry >= step:
            carry -= step
            t = 1.0 - carry / seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def split_run(points, run_length: float):
    """
    Cut a long outline into runs of about `run_length` units.

    The reveal is paced per item, so a whole coastline as one item would appear all at once while
    the rest of the sheet crept along. Chunks make the pen visibly travel. The caller must use ONE
    `Hand` across the runs of a single outline, or the wander restarts at every join.
    """
    if len(points) < 2 or run_length <= 0:
        return [list(points)]
    runs = []
    current = [points[0]]
    travelled = 0.0
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        current.append(points[i + 1])
        travelled += math.hypot(x1 - x0, y1 - y0)
        if travelled >= run_length:
            runs.append(current)
            current = [points[i + 1]]
            travelled = 0.0
    if len(current) > 1:
        runs.append(current)
    return runs


class Pour:
    """The poured rice: a land mask, the grid it lives on, and the outlines traced from it."""

    def __init__(self, mask: bytearray, gw: int, gh: int,
                 cell_x: float, cell_y: float, grain_px: float, grains: int, attempts: int):
        self.mask = mask
        self.gw = gw
        self.gh = gh
        self.cell_x = cell_x
        self.cell_y = cell_y
        self.grain_px = grain_px
        self.grains = grains
        self.attempts = attempts
        self.coverage = (sum(mask) / float(gw * gh)) if mask else 0.0
        self._traced = None
        #: The welded mask as a SURFACE, kept so a later pass can dilate or erode it with one blit
        #: per step rather than rebuilding a surface from the bytearray (a Python loop over a quarter
        #: of a million cells). This is what lets the water rings be true parallel contours and the
        #: lakes sit on land with clearance.
        self.closed_surface = None

    def on_land(self, x: float, y: float) -> bool:
        gx = int(x / self.cell_x)
        gy = int(y / self.cell_y)
        if 0 <= gx < self.gw and 0 <= gy < self.gh:
            return self.mask[gy * self.gw + gx] == 1
        return False

    def loops(self, min_area_cells: float = 120.0):
        """
        The traced outlines, biggest first, each as `(points_in_surface_units, closed, area)`.

        `min_area_cells` is what turns stray single grains into the little islands the tutorial
        describes, and drops the specks that are not worth a stroke. The trace itself is cached,
        because it costs a few hundred ms and the caller may want the total as well as the filtered
        list.
        """
        if self._traced is None:
            traced = []
            for points, closed in chain_loops(marching_squares(self.mask, self.gw, self.gh)):
                area = 0.0
                for i in range(len(points) - 1):
                    area += points[i][0] * points[i + 1][1] - points[i + 1][0] * points[i][1]
                traced.append((points, closed, abs(area) * 0.5))
            traced.sort(key=lambda item: -item[2])
            self._traced = traced
        out = []
        for points, closed, area in self._traced:
            if area >= min_area_cells:
                scaled = [(x * self.cell_x, y * self.cell_y) for (x, y) in points]
                out.append((scaled, closed, area))
        return out

    @property
    def traced_loops(self) -> int:
        """How many outlines the trace found, before the size filter."""
        if self._traced is None:
            self.loops(min_area_cells=math.inf)
        return len(self._traced or ())


def pour_land(rng, ink_w: float, ink_h: float, px_per_mm: float, *,
              coverage: float = 0.55, grain_cells: float = CELLS_AT_REFERENCE,
              clumps: int = 4, attempts: int = 3):
    """
    Pour until about `coverage` of the sheet is land.

    The dial works on the clumps' **footprint**, not on how many grains go into them. Pouring more
    rice into a clump that is already full fills it in and then stops adding any area at all, which
    is exactly how the first version of this function saturated: it asked for 55% and reported 77%
    on every attempt, however hard it scaled the grain count down. Grains per clump therefore
    follow the footprint, so a bigger clump is simply a bigger pour.

    One correction pass is allowed, scaled by `sqrt` because area goes with the square of the
    spread, and the closest pour wins. The coverage actually achieved is reported rather than
    assumed: a Gaussian clump bleeding off the edge of the field cannot be aimed exactly.
    """
    gw, gh, cell_x, cell_y = field_metrics(ink_w, ink_h, px_per_mm)
    grain_px = max(3.0, float(grain_cells) * GRAIN_MM * px_per_mm / CELLS_AT_REFERENCE)
    sprites = grain_sprites(grain_px)
    field_cells = float(gw * gh)
    clumps = max(1, int(clumps))

    clump_cells = max(64.0, _footprint_for(coverage) * field_cells / clumps)
    per_clump = max(24, int(clump_cells * FILL_PER_CELL))

    # The LAYOUT is drawn once: the clump centres, and a standard-normal offset per grain. An
    # attempt then only rescales those offsets, so it refines the same pour instead of rolling a new
    # one. That matters -- with fresh randomness per attempt the coverage jumped around (asking for
    # 0.30 produced 0.42, 0.15 and 0.60 in three tries) and the "correction" was noise.
    centres = [(rng.uniform(-0.10, 1.10) * gw, rng.uniform(-0.10, 1.10) * gh) for _ in range(clumps)]
    offsets = [[(rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)) for _ in range(per_clump)]
               for _ in range(clumps)]

    best = None
    spread_scale = 1.0
    for attempt in range(max(1, attempts)):
        # the Gaussian's effective footprint is a disc of radius 2 sigma; clumps are wider than tall
        sigma_x = math.sqrt(clump_cells / (4.0 * math.pi * 0.85)) * spread_scale
        sigma_y = sigma_x * 0.85

        surface = pygame.Surface((gw, gh))
        surface.fill((0, 0, 0))
        for (cx, cy), offsets_for_clump in zip(centres, offsets):
            # clump centres sit partly OFF the field, so the land runs off the page rather than
            # floating as one island in the middle of the sheet
            for zx, zy in offsets_for_clump:
                sprite = sprites[rng.randrange(len(sprites))]
                surface.blit(sprite, (int(cx + zx * sigma_x), int(cy + zy * sigma_y)),
                             special_flags=pygame.BLEND_RGB_MAX)
        mask = _read_mask(close_mask(surface, r=2), gw, gh)
        pour = Pour(mask, gw, gh, cell_x, cell_y, grain_px, per_clump * clumps, attempt + 1)
        pour.closed_surface = close_mask(surface, r=2)
        if best is None or abs(pour.coverage - coverage) < abs(best.coverage - coverage):
            best = pour
        if abs(pour.coverage - coverage) <= 0.045:
            break
        if pour.coverage > 0.01:
            spread_scale *= min(1.7, max(0.55, math.sqrt(coverage / pour.coverage)))
    return best
