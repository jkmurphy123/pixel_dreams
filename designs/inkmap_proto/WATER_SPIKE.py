"""WATER SPIKE -- how to get parallel rings that STAY parallel, and what they cost.

Throwaway probe, not application code (see this directory's README).

The video's water technique traces a line parallel to the coast, then fills between the lines with
hashes and dots. The design specified rings at 13/21/29 px but never said how to produce them, and
that is the whole risk in this phase, so it gets measured before anything is designed around it.

Two candidate mechanisms:

  A. OFFSET THE COAST POLYLINE. Push every vertex out along its local normal. O(n) arithmetic and no
     grid quantisation, but a parallel curve of a scalloped line folds over itself wherever the coast
     is concave by more than the offset -- and the offset here is comparable to the scallop size, so
     folds are expected, not hypothetical.

  B. DILATE THE MASK, THEN TRACE IT. A morphological dilation's boundary IS the parallel curve, by
     definition, and it cannot self-intersect. Costs a blit per step (incremental dilation: 8 blits
     per step, not (2r+1)^2) plus one marching-squares pass per ring, and quantises the ring to whole
     grid cells.

Run:  SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/WATER_SPIKE.py
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


def dilate_step(surface):
    """Grow by one cell: blit the surface onto itself at the 8 neighbour offsets."""
    out = surface.copy()
    w, h = surface.get_size()
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        out.blit(surface, (dx, dy), special_flags=pygame.BLEND_RGB_MAX)
    return out


def mask_of(surface, gw, gh):
    return inkland._read_mask(surface, gw, gh)


def rings_morphological(pour, steps):
    """Method B: dilate step by step, trace the contour at each wanted step."""
    timings = {}
    gw, gh = pour.gw, pour.gh
    field = pour.closed_surface
    if field is None:
        return {}, {}
    out = {}
    t0 = time.perf_counter()
    layer = field
    for step in range(1, max(steps) + 1):
        layer = dilate_step(layer)
        if step in steps:
            t1 = time.perf_counter()
            mask = mask_of(layer, gw, gh)
            loops = inkland.chain_loops(inkland.marching_squares(mask, gw, gh))
            scaled = []
            for points, closed in loops:
                if len(points) < 6:
                    continue
                scaled.append(([(x * pour.cell_x, y * pour.cell_y) for x, y in points], closed))
            out[step] = scaled
            timings[step] = (time.perf_counter() - t1) * 1000.0
    return out, {'total_ms': (time.perf_counter() - t0) * 1000.0, 'per_ring_ms': timings}


def normal_offset(points, distance, outward_sign, step=6.0):
    """Method A: push each vertex out along the local normal and resample."""
    n = len(points)
    if n < 4:
        return list(points)
    moved = []
    for i in range(n):
        px, py = points[i - 1]
        nx, ny = points[(i + 1) % n]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        moved.append((cx + (-dy / length) * distance * outward_sign,
                      cy + (dx / length) * distance * outward_sign))
    return inkland.resample(moved, step)


def which_side_is_sea(pour, points):
    """+1 or -1: which way the normal must point to leave the land. Tested, not assumed."""
    for i in range(0, len(points) - 2, max(1, len(points) // 40)):
        px, py = points[i - 1]
        nx, ny = points[i + 1]
        cx, cy = points[i]
        dx, dy = nx - px, ny - py
        length = math.hypot(dx, dy) or 1.0
        for sign in (1.0, -1.0):
            tx = cx + (-dy / length) * 40.0 * sign
            ty = cy + (dx / length) * 40.0 * sign
            if not pour.on_land(tx, ty):
                return sign
    return 1.0


def main():
    print('water spike at %dx%d (ink %dx%d), %.2f ink px per mm' % (W, H, INK_W, INK_H, PPM))
    print('field cell %.2f ink px = %.2f mm' % (inkland.field_metrics(INK_W, INK_H, PPM)[2],
                                                inkland.field_metrics(INK_W, INK_H, PPM)[2] / PPM))
    print()
    t0 = time.perf_counter()
    pour = inkland.pour_land(random.Random(4242), INK_W, INK_H, PPM, coverage=0.55, clumps=4)
    print('pour + trace + plan: %.0f ms' % ((time.perf_counter() - t0) * 1000.0))
    masses = pour.loops(min_area_cells=1200.0)
    print('%d land masses; the biggest is %.0f ink px of coastline'
          % (len(masses), sum(math.hypot(masses[0][0][i + 1][0] - masses[0][0][i][0],
                                         masses[0][0][i + 1][1] - masses[0][0][i][1])
                              for i in range(len(masses[0][0]) - 1))))
    print()

    steps = (3, 5, 7)
    rings, timing = rings_morphological(pour, steps)
    print('METHOD B (dilate + trace):')
    print('  dilation + tracing total: %.0f ms' % timing['total_ms'])
    for step in steps:
        n = sum(len(p) for p, _c in rings.get(step, []))
        print('    ring at %d cells (%.2f mm, %.0f ink px): %d outlines, %d vertices, %.0f ms to trace'
              % (step, step * pour.cell_x / PPM, step * pour.cell_x, len(rings.get(step, [])), n,
                 timing['per_ring_ms'][step]))
    print()

    print('METHOD A (offset the polyline):')
    for step in steps:
        distance = step * pour.cell_x
        t1 = time.perf_counter()
        total_pts = 0
        for points, _closed, _area in masses:
            sign = which_side_is_sea(pour, points)
            off = normal_offset(points, distance, sign, step=6.0)
            total_pts += len(off)
        print('    offset by %5.1f ink px: %6d vertices, %.1f ms for ALL masses'
              % (distance, total_pts, (time.perf_counter() - t1) * 1000.0))
    print()

    # ---- render both, on paper, side by side, and look ----
    paper = pygame.Surface((W, H))
    paper.fill((232, 217, 184))
    ink = pygame.Surface((INK_W, INK_H), pygame.SRCALPHA)
    pens = inkdraw.pen_widths(min(INK_W, INK_H), 1.0)
    hand = inkdraw.Hand(seed=4242, tremor=0.55, px_per_mm=PPM)
    coast_colour = (43, 33, 26, 255)
    water_colour = (43, 33, 26, 255)

    for points, _closed, _area in masses:
        inkdraw.stroke(ink, inkland.resample(points, 4.0), pens['05'], hand, colour=coast_colour)

    # Method B rings, with the hash/dot alternation, drawn as the real thing would be
    pattern = (('mark',), ('mark', 'dot'), ('mark', 'dot', 'mark'), ('dot', 'mark'))
    marks = 0
    t1 = time.perf_counter()
    for step in steps:
        for points, _closed in rings.get(step, []):
            smooth = inkland.resample(points, 5.0)
            # outward normal, tested per ring
            for i in range(0, len(smooth) - 1, 9):
                px, py = smooth[i - 1] if i else smooth[0]
                nx, ny = smooth[i + 1]
                cx, cy = smooth[i]
                dx, dy = nx - px, ny - py
                length = math.hypot(dx, dy) or 1.0
                ox, oy = -dy / length, dx / length
                if pour.on_land(cx + ox * 6.0, cy + oy * 6.0):
                    ox, oy = -ox, -oy
                unit = pattern[(i // 9) % len(pattern)]
                cursor = 0
                for token in unit:
                    if token == 'mark':
                        ln = pour.cell_x * 1.6
                        inkdraw.stroke(ink, [(cx + ox * cursor, cy + oy * cursor),
                                             (cx + ox * (cursor + ln), cy + oy * (cursor + ln))],
                                       pens['005'], hand, colour=water_colour)
                        marks += 1
                        cursor += ln * 1.5
                    else:
                        pygame.draw.circle(ink, water_colour,
                                           (int(cx + ox * cursor), int(cy + oy * cursor)), 2)
                        marks += 1
                        cursor += pour.cell_x
    draw_ms = (time.perf_counter() - t1) * 1000.0
    print('drawing the water by method B: %.0f ms for %d marks' % (draw_ms, marks))

    ink_small = pygame.transform.smoothscale(ink, (W, H))
    paper.blit(ink_small, (0, 0))
    full = os.path.join(os.path.dirname(OUT), 'inkmap_proto_water_spike.png')
    pygame.image.save(paper, full)
    crop = pygame.Surface((620, 620))
    crop.blit(paper, (0, 0), (300, 380, 620, 620))
    zoom = os.path.join(os.path.dirname(OUT), 'inkmap_proto_water_spike_zoom.png')
    pygame.image.save(pygame.transform.scale(crop, (1080, 1080)), zoom)
    print()
    print('wrote %s' % full)
    print('wrote %s' % zoom)
    return 0


if __name__ == '__main__':
    sys.exit(main())
