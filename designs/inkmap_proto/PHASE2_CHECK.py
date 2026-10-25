"""PHASE 2 GATE -- the coastline, at the panel's real resolution.

Run it with:

    SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/PHASE2_CHECK.py

It checks the three acceptance criteria the design doc sets for phase 2, then measures the sheet and
writes the evidence images next to this file. Nothing here runs on the kiosk's display: everything is
off-screen, so it can be run while the wall is showing something else.

Acceptance, from section 7 of the design doc:
  * the outline is OPEN where it leaves the sheet -- no ruler lines;
  * the scallop scale follows the grain size;
  * the pour is reproducible from a seed.
Plus what phase 2 adds to the mode: the pen actually marks the paper, it travels rather than the sheet
appearing at once, and the whole coastline is drawn by one hand.
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
from core.cache import ResourceCache  # noqa: E402
from core.config import load_json  # noqa: E402
from core.loader import build_merged_config, load_entrypoint  # noqa: E402

W, H = 1080, 1920
SEED = 4242
TYPES = load_json(os.path.join(BASE, 'modes_registry.json'), {})['types']
BUILD = load_entrypoint(TYPES['inkmap']['entrypoint'])

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print('  %-4s %s%s' % ('PASS' if ok else 'FAIL', name, ('  -- ' + detail) if detail else ''))


class Manager:
    def __init__(self, w, h):
        self.screen = pygame.Surface((w, h))
        self.cache = ResourceCache()
        self.width = w
        self.height = h


def make(**cfg):
    return BUILD(build_merged_config(TYPES['inkmap'], dict({'type': 'inkmap'}, **cfg), None))


def ink_pixels(canvas, ink, stride=3):
    count = 0
    for x in range(0, canvas.get_width(), stride):
        for y in range(0, canvas.get_height(), stride):
            colour = canvas.get_at((x, y))
            if (abs(colour[0] - ink[0]) < 40 and abs(colour[1] - ink[1]) < 40
                    and abs(colour[2] - ink[2]) < 40):
                count += 1
    return count


def bump_frequency(points, step=8):
    """Direction reversals per 1000 px of outline -- smaller means bigger, lazier lobes."""
    sampled = points[::step]
    reversals = 0
    length = 0.0
    previous = None
    for i in range(1, len(sampled) - 1):
        ax, ay = sampled[i][0] - sampled[i - 1][0], sampled[i][1] - sampled[i - 1][1]
        bx, by = sampled[i + 1][0] - sampled[i][0], sampled[i + 1][1] - sampled[i][1]
        length += math.hypot(ax, ay)
        cross = ax * by - ay * bx
        if cross != 0.0:
            sign = 1 if cross > 0 else -1
            if previous is not None and sign != previous:
                reversals += 1
            previous = sign
    return 1000.0 * reversals / max(1.0, length)


def main():
    print('phase 2 gate: the coastline at %dx%d, seed %d' % (W, H, SEED))
    print()
    print('1. the sheet')
    manager = Manager(W, H)
    mode = make(seed=SEED)
    started = time.perf_counter()
    mode.enter(manager)
    enter_ms = (time.perf_counter() - started) * 1000.0
    status = mode.status()
    print('   enter() %.0f ms: paper + pour in %d attempt(s) + trace + plan' % (enter_ms, mode.land.attempts))
    print('   land %.1f%% (asked %.0f%%), %d grains, %d outlines traced -> %d masses'
          % (status['land_coverage'] * 100, mode.land_coverage * 100, status['grains'],
             mode.land.traced_loops, status['masses']))
    print('   %d pen strokes queued, ink layer %dx%d'
          % (status['planned'], *mode.sheet.ink.get_size()))
    check('the mode builds a coastline at the panel size', status['planned'] > 0 and status['masses'] >= 1,
          '%d strokes over %d masses' % (status['planned'], status['masses']))

    print()
    print('2. acceptance: an outline leaving the sheet stays open')
    closed = [m for m in mode.masses if m[1]]
    open_masses = [m for m in mode.masses if not m[1]]
    check('some outline runs off the edge and is left open', len(open_masses) > 0,
          '%d open, %d closed' % (len(open_masses), len(closed)))
    offenders = []
    for points, was_closed, _area in mode.masses:
        if was_closed:
            if points[0] != points[-1]:
                offenders.append('closed without repeating its first point')
        else:
            if points[0] == points[-1]:
                offenders.append('open but repeating its first point')
    check('no outline is closed off with a straight chord', not offenders, str(offenders[:3]))
    gw, gh, cell_x, cell_y = inkland.field_metrics(*mode.sheet.ink_size, mode.ink_px_per_mm)
    sheet_w, sheet_h = gw * cell_x, gh * cell_y

    def on_border(point):
        x, y = point
        return x == 0.0 or x == sheet_w or y == 0.0 or y == sheet_h

    along_edge = 0
    loose_ends = 0
    for points, was_closed, _area in mode.masses:
        border = [on_border(point) for point in points]
        for i in range(len(points) - 1):
            if border[i] and border[i + 1]:
                along_edge += 1
        # an outline may only touch the sheet edge where the pen goes off the page: at an end
        for index in (i for i, hit in enumerate(border) if hit):
            if was_closed or index not in (0, len(points) - 1):
                loose_ends += 1
    print('   %d vertices touch the sheet edge, all of them outline ends; %d segments run along it'
          % (sum(1 for points, _c, _a in mode.masses
                 for point in points if on_border(point)), along_edge))
    check('no segment is drawn along the edge of the sheet', along_edge == 0,
          '%d such segments' % along_edge)
    check('an outline only meets the sheet edge where it runs off the page', loose_ends == 0,
          '%d vertices touch the edge somewhere else' % loose_ends)

    print()
    print('3. acceptance: the scallop scale follows the grain size')
    rng = random.Random(77)
    rates = {}
    for grain_cells in (3.0, 12.0):
        pour = inkland.pour_land(rng, *mode.sheet.ink_size, mode.ink_px_per_mm,
                                 coverage=0.55, grain_cells=grain_cells, clumps=3, attempts=2)
        points = pour.loops(min_area_cells=400.0)[0][0]
        rates[grain_cells] = bump_frequency(points)
    print('   direction reversals per 1000 px of coast: %.1f at 3 cells (1.5 mm rice), '
          '%.1f at 12 cells (6 mm rice)' % (rates[3.0], rates[12.0]))
    check('coarser rice gives a lazier coastline', rates[3.0] > rates[12.0] * 1.2)

    print()
    print('4. acceptance: the pour is reproducible from a seed')
    again = make(seed=SEED)
    again.enter(manager)
    same = (bytes(mode.land.mask) == bytes(again.land.mask)
            and mode.land.coverage == again.land.coverage
            and mode.status()['planned'] == again.status()['planned'])
    other = make(seed=SEED + 1)
    other.enter(manager)
    different = bytes(mode.land.mask) != bytes(other.land.mask)
    check('the same seed pours the same land', same)
    check('a different seed pours different land', different)

    print()
    print('5. the pen')
    total = mode.reveal.total
    marks = []
    for stop in (0, total // 4, total // 2, total):
        while mode.reveal.index < stop:
            mode.reveal.advance(1.0, float(total), mode._draw_one)
        mode.sheet.flush()
        marks.append(ink_pixels(mode.sheet.canvas, mode.ink_rgb))
    print('   ink on the sheet at 0%%, 25%%, 50%%, 100%% of the pen strokes: %s px' % marks)
    # CORRECTED: this used to flush BEFORE timing the render, so the composite was never counted and
    # the number reported (1.47 ms) was the blit alone. Measured as the app runs -- one composite per
    # frame's worth of drawing -- below.
    while not mode.reveal.done:
        mode.reveal.advance(1.0 / mode.reveal_fps, mode.draw_seconds, mode._draw_one)
    per_frame = max(1, int(round(total / max(1.0, mode.draw_seconds) / mode.reveal_fps)))
    replay = make(seed=SEED)
    replay.enter(manager)
    frames = []
    while not replay.reveal.done:
        t0 = time.perf_counter()
        for _ in range(per_frame):
            if replay.reveal.done:
                break
            replay.reveal.advance(1.0 / replay.reveal_fps, replay.draw_seconds, replay._draw_one)
        replay.render(manager.screen)
        frames.append((time.perf_counter() - t0) * 1000.0)
    frames.sort()
    print('   %d frames simulated at %d items/frame; median %.2f ms, worst %.2f ms (draw+composite+blit)'
          % (len(frames), per_frame, frames[len(frames) // 2], frames[-1]))
    check('the pen marks the paper', marks[-1] > 0)
    check('the pen travels instead of the sheet appearing at once',
          marks[0] == 0 and marks[0] < marks[1] < marks[2] < marks[3])
    check('a frame stays inside a 60 fps budget', frames[-1] < 16.6, '%.2f ms worst' % frames[-1])
    check('the pen finished', mode.status()['finished'] is True)

    print()
    print('6. the evidence images')
    out_dir = os.path.join(BASE, 'designs')
    pygame.image.save(mode.sheet.canvas, os.path.join(out_dir, 'inkmap_phase02_coast.png'))
    crop = pygame.Surface((600, 600))
    crop.blit(mode.sheet.canvas, (0, 0), (240, 300, 600, 600))
    pygame.image.save(pygame.transform.scale(crop, (1080, 1080)),
                      os.path.join(out_dir, 'inkmap_phase02_coast_zoom.png'))

    # a mid-draw frame, for the same reason phase 1 kept one: the in-progress state is the feature
    partial = make(seed=SEED)
    partial.enter(manager)
    halfway = partial.reveal.total * 2 // 5
    while partial.reveal.index < halfway:
        partial.reveal.advance(1.0, float(partial.reveal.total), partial._draw_one)
    partial.sheet.flush()
    pygame.image.save(partial.sheet.canvas, os.path.join(out_dir, 'inkmap_phase02_in_progress.png'))
    print('   designs/inkmap_phase02_coast.png')
    print('   designs/inkmap_phase02_coast_zoom.png')
    print('   designs/inkmap_phase02_in_progress.png  (40 per cent of the strokes)')
    check('the evidence images were written',
          all(os.path.exists(os.path.join(out_dir, name)) for name in (
              'inkmap_phase02_coast.png', 'inkmap_phase02_coast_zoom.png',
              'inkmap_phase02_in_progress.png')))

    failed = [name for name, ok, _detail in results if not ok]
    print()
    print('VERDICT: %s (%d checks, %d failed)'
          % ('PASS' if not failed else 'FAIL', len(results), len(failed)))
    for name in failed:
        print('   FAILED: %s' % name)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
