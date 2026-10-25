"""WATER SPIKE (2) -- the rings as the video actually draws them, at two spacings, by two methods.

Throwaway probe, not application code (see this directory's README).

Spike 1 measured the COST of the two ways to produce a line parallel to the coast and came out
lopsided: offsetting the polyline costs ~10 ms for every mass, dilating the mask and tracing each
ring costs 540 ms (three marching-squares passes over 400x711 cells). But it only drew the marks, not
the parallel LINES, and the video's first step is to trace the line round the coast. Without the lines
the marks read as scattered debris, so this spike draws the real thing and compares:

    method      how a parallel line is produced
    offset      push the coast polyline out along its vertex normals (folds over where the coast is
                concave by more than the offset -- expected, since the offset is a good fraction of
                the scallop size)
    dilate      grow the mask one cell at a time and trace each level (a true parallel curve that
                cannot fold, quantised to whole grid cells)

    spacing     1.00 mm between rings (3/5/7 cells, close to the design's 13/21/29 ink px)
                2.00 mm between rings (4/8/12 cells, a wider band)

Marks are the video's four alternating units -- hash / hash+dot / hash-dot-hash / dot-hash -- placed
along each ring, each hash spanning the gap to the next ring, dots between them.

Run:  SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/WATER_SPIKE2.py
"""

from __future__ import annotations

import math
import os
import random
import sys
import time

BASE = '/mnt/ssd/projects/pixel_dreams'
sys.path.insert(0, BASE)

import pygame  # noqa: E402

pygame.init()
pygame.font.init()
pygame.display.set_mode((64, 64))

from core import inkdraw, inkland  # noqa: E402

W, H, SS = 1080, 1920, 2
INK_W, INK_H = W * SS, H * SS
PPM = min(INK_W, INK_H) / inkdraw.REFERENCE_SHEET_MM
OUT = os.path.dirname(os.path.abspath(__file__))

#: The video's four units along a ring: a hash, a hash with a dot, hash-dot-hash, dot-hash.
UNITS = (('mark',), ('mark', 'dot'), ('mark', 'dot', 'mark'), ('dot', 'mark'))

#: How far along a ring one unit sits, in ink px (16 = 1.5 mm).
MARK_PITCH = 16.0

VARIANTS = (('offset', (3, 5, 7)), ('dilate', (3, 5, 7)),
            ('offset', (4, 8, 12)), ('dilate', (4, 8, 12)))


def dilate_step(surface):
    out = surface.copy()
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        out.blit(surface, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)
    return out


def dilated_levels(pour, wanted):
    """Dilate once, keeping the levels we want. One blit set per step, not (2r+1)^2."""
    levels = {}
    layer = pour.closed_surface
    for step in range(1, max(wanted) + 1):
        layer = dilate_step(layer)
        if step in wanted:
            levels[step] = layer.copy()
    return levels


def rings_from_levels(pour, levels, min_vertices=200):
    """Trace each dilated level. Costs a marching-squares pass per ring."""
    out = {}
    for step, surface in levels.items():
        mask = inkland._read_mask(surface, pour.gw, pour.gh)
        chains = []
        for points, closed in inkland.chain_loops(inkland.marching_squares(mask, pour.gw, pour.gh)):
            if len(points) >= min_vertices:
                chains.append(([(x * pour.cell_x, y * pour.cell_y) for x, y in points], closed))
        out[step] = chains
    return out


def side_that_is_sea(pour, points, closed):
    """Test, never assume, which way the normal points to leave the land."""
    n = len(points)
    if n < 4:
        return 1.0
    for i in range(2, n - 2, max(1, n // 30)):
        px, py = points[i - 1]
        nx, ny = points[i + 1]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        for sign in (1.0, -1.0):
            if not pour.on_land(cx + (-dy / length) * 40.0 * sign, cy + (dx / length) * 40.0 * sign):
                return sign
    return 1.0


def offset_ring(points, closed, distance, sign, step=5.0):
    """Push each vertex out along its local normal. Open chains are NOT wrapped."""
    n = len(points)
    out = []
    for i in range(n):
        left = i - 1 if i > 0 else (n - 1 if closed else i)
        right = i + 1 if i < n - 1 else (0 if closed else i)
        px, py = points[left]
        nx, ny = points[right]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        out.append((cx + (-dy / length) * distance * sign, cy + (dx / length) * distance * sign))
    return inkland.resample(out, step)


def draw_ring(ink, points, closed, pour, spacing, pens, hand, colour, unit_index):
    """The parallel line, then the marks along it -- the video's two steps."""
    if len(points) < 3:
        return 0
    inkdraw.stroke(ink, points, pens['005'], hand, colour=colour)
    marks = 0
    travelled = 0.0
    unit = 0
    for i in range(1, len(points) - 1):
        px, py = points[i - 1]
        cx, cy = points[i]
        nx, ny = points[i + 1]
        travelled += math.hypot(cx - px, cy - py)
        if travelled < MARK_PITCH:
            continue
        travelled = 0.0
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        ox, oy = -dy / length, dx / length
        if pour.on_land(cx + ox * spacing * 0.6, cy + oy * spacing * 0.6):
            ox, oy = -ox, -oy
        cursor = 0.0
        for token in UNITS[(unit_index + unit) % len(UNITS)]:
            if token == 'mark':
                inkdraw.stroke(ink, [(cx + ox * cursor, cy + oy * cursor),
                                     (cx + ox * (cursor + spacing * 0.95),
                                      cy + oy * (cursor + spacing * 0.95))],
                               pens['005'], hand, colour=colour)
                cursor += spacing * 0.75
            else:
                pygame.draw.circle(ink, colour,
                                   (int(cx + ox * cursor), int(cy + oy * cursor)), 2)
                cursor += spacing * 0.5
            marks += 1
        unit += 1
    return marks


def main():
    field = inkland.field_metrics(INK_W, INK_H, PPM)
    print('cell %.2f ink px = %.2f mm' % (field[2], field[2] / PPM))
    pour = inkland.pour_land(random.Random(4242), INK_W, INK_H, PPM, coverage=0.55, clumps=4)
    masses = pour.loops(min_area_cells=1200.0)
    print('%d masses, coastline %.0f ink px'
          % (len(masses), sum(sum(math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1])
                                  for i in range(len(p) - 1)) for p, _c, _a in masses)))
    print()

    pens = inkdraw.pen_widths(min(INK_W, INK_H), 1.0)
    colour = (43, 33, 26, 255)
    paper = pygame.Surface((W, H))
    paper.fill((232, 217, 184))

    tiles = []
    for method, steps in VARIANTS:
        spacing = (steps[1] - steps[0]) * field[2]
        ink = pygame.Surface((INK_W, INK_H), pygame.SRCALPHA)
        hand = inkdraw.Hand(seed=4242, tremor=0.55, px_per_mm=PPM)
        t0 = time.perf_counter()

        if method == 'dilate':
            levels = dilated_levels(pour, steps)
            t_levels = time.perf_counter() - t0
            rings = rings_from_levels(pour, levels)
            t_trace = time.perf_counter() - t0 - t_levels
            todo = [(pts, True) for step in steps for pts, _c in rings[step]]
        else:
            todo = []
            t_levels = t_trace = 0.0
            for points, closed, _area in masses:
                sign = side_that_is_sea(pour, points, closed)
                for step in steps:
                    todo.append((offset_ring(points, closed, step * field[2], sign), closed))
            t_levels = time.perf_counter() - t0

        marks = 0
        t_draw = time.perf_counter()
        for index, (points, closed) in enumerate(todo):
            marks += draw_ring(ink, points, closed, pour, spacing, pens, hand, colour, index)
        t_draw = time.perf_counter() - t_draw
        t_all = time.perf_counter() - t0

        print('%-7s steps %-10s spacing %.2f mm:  rings %3d  marks %5d'
              % (method, str(steps), spacing, len(todo), marks))
        print('           levels %6.0f ms  trace %6.0f ms  draw %6.0f ms  TOTAL %6.0f ms'
              % (t_levels * 1000, t_trace * 1000, t_draw * 1000, t_all * 1000))

        ink_small = pygame.transform.smoothscale(ink, (W, H))
        tile = pygame.Surface((W, H))
        tile.blit(paper, (0, 0))
        tile.blit(ink_small, (0, 0))
        tiles.append(('%s  spacing %.2f mm' % (method, spacing), tile))

    # one comparison sheet: the same crop of the sheet under each variant, labelled
    crop_box = (300, 380, 620, 620)
    cols, rows = 2, 2
    sheet = pygame.Surface((cols * 620, rows * 620 + 60))
    sheet.fill((20, 20, 20))
    font = pygame.font.SysFont('dejavusans', 26)
    for index, (label, tile) in enumerate(tiles):
        cx = (index % cols) * 620
        cy = (index // cols) * (620 + 30) + 30
        crop = pygame.Surface((620, 620))
        crop.blit(tile, (0, 0), crop_box)
        sheet.blit(crop, (cx, cy))
        sheet.blit(font.render(label, True, (255, 255, 255)), (cx + 10, cy - 28))
    out = os.path.join(os.path.dirname(OUT), 'inkmap_proto_water_compare.png')
    pygame.image.save(sheet, out)
    print()
    print('wrote %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
