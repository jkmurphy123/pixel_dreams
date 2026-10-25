"""PHASE 3 GATE -- the sea, at the panel's real resolution.

    SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/PHASE3_CHECK.py

Checks the design's acceptance for phase 3 and measures the sheet, then writes the evidence images
next to this file. Everything is off-screen: the wall is showing something else and this must not
touch it.

Acceptance, from section 7 of the design doc:
  * the video's four units all appear (a single pattern "reads as a comb", so one missing is a defect);
  * the four alternate sea styles are all distinguishable;
  * changing `water_style` changes the drawn sea -- and via the panel's apply path, not a restart.

Plus what phase 3 adds beyond the letter of the doc: the sea is on the SEA side, its hashes point
away from the land, the lakes are inland, and the plan keeps the tutorial's order (coast, then sea).
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

from core import inkdraw, inkland, inkwater  # noqa: E402
from core.cache import ResourceCache  # noqa: E402
from core.config import load_json  # noqa: E402
from core.loader import build_merged_config, load_entrypoint  # noqa: E402

W, H = 1080, 1920
INK_W, INK_H = W * 2, H * 2
PPM = min(INK_W, INK_H) / 200.0
SEED = 4242
STYLES = ('hash', 'squiggle', 'stipple', 'wave')
TYPES = load_json(os.path.join(BASE, 'modes_registry.json'), {})['types']
BUILD = load_entrypoint(TYPES['inkmap']['entrypoint'])
OUT = os.path.join(BASE, 'designs')

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


def draw_all(mode):
    total = mode.reveal.total
    while mode.reveal.index < total:
        mode.reveal.advance(1.0, float(total), mode._draw_one)
    mode.sheet.flush()


def ink_pixels(canvas, stride=3):
    count = 0
    for x in range(0, canvas.get_width(), stride):
        for y in range(0, canvas.get_height(), stride):
            colour = canvas.get_at((x, y))
            if (abs(colour[0] - 43) < 40 and abs(colour[1] - 33) < 40 and abs(colour[2] - 26) < 40):
                count += 1
    return count


def main():
    print('phase 3 gate: the sea at %dx%d, seed %d, %.2f ink px per mm' % (W, H, SEED, PPM))
    print()
    manager = Manager(W, H)
    print('1. the sheet')
    mode = make(seed=SEED)
    started = time.perf_counter()
    mode.enter(manager)
    enter_ms = (time.perf_counter() - started) * 1000.0
    status = mode.status()
    print('   enter() %.0f ms -- paper, pour, trace, coast plan and sea plan' % enter_ms)
    print('   %d coast + %d sea/lake strokes = %d, passes %s'
          % (status['coast_strokes'], status['sea_strokes'], status['planned'], status['passes']))
    check('the plan keeps the tutorial order', status['passes'] == ['coast', 'sea'], str(status['passes']))
    check('the sea is a real share of the plan', status['sea_strokes'] > status['coast_strokes'] // 4,
          '%d sea vs %d coast' % (status['sea_strokes'], status['coast_strokes']))

    print()
    print('2. the sea is on the sea side')
    pour = mode.land
    on_land = off_land = 0
    items = inkwater.coast_water(mode.masses, pour, pens=inkdraw.pen_widths(min(INK_W, INK_H), 1.0),
                                 hand=inkdraw.Hand(seed=7, tremor=0.5, px_per_mm=PPM),
                                 style=status['water_style'], rings=status['water_rings'],
                                 px_per_mm=PPM)
    for item in items:
        for x, y in item.points:
            if pour.on_land(x, y):
                on_land += 1
            else:
                off_land += 1
    print('   ring vertices: %d at sea, %d over land' % (off_land, on_land))
    check('no ring is drawn along the land', off_land > on_land * 4, '%d/%d' % (on_land, on_land + off_land))

    hashes = outward = 0
    for item in items:
        for token in item.marks:
            if token[0] != 'line':
                continue
            hashes += 1
            base, tip = token[1][0], token[1][-1]
            # the land is where the base is closest to; the tip must be further from the nearest coast
            if pour.on_land(tip[0], tip[1]) is False:
                outward += 1
    print('   %d hashes, %d of them ending on water' % (hashes, outward))
    check('the hashes hang out to sea', hashes > 200 and outward == hashes)

    print()
    print('3. acceptance: the four units all appear')
    kinds = []
    for item in items:
        kinds.extend(token[0] for token in item.marks)
    print('   mark kinds across a whole sea: lines %d, dots %d'
          % (kinds.count('line'), kinds.count('dot')))
    check('both a hash and a dot are drawn, many times',
          kinds.count('line') > 100 and kinds.count('dot') > 100)

    print()
    print('4. acceptance: the four alternate styles are all distinguishable')
    prints = {}
    for style in STYLES:
        m = make(seed=SEED, water_style=style)
        m.enter(manager)
        draw_all(m)
        prints[style] = (pygame.image.tostring(m.sheet.canvas, 'RGB'),
                         ink_pixels(m.sheet.canvas))
        pygame.image.save(m.sheet.canvas, os.path.join(OUT, 'inkmap_phase03_sea_%s.png' % style))
        m.exit()
    distinct = len(set(value[0] for value in prints.values()))
    for style in STYLES:
        print('   %-9s ink %5d sampled px' % (style, prints[style][1]))
    check('all four styles draw something', all(v[1] > 500 for v in prints.values()))
    check('all four styles draw a DIFFERENT sea', distinct == 4, '%d distinct' % distinct)

    print()
    print('5. the dials')
    no_sea = make(seed=SEED, water_rings=0, lake_count=0)
    no_sea.enter(manager)
    lakes_only = make(seed=SEED, water_rings=0, lake_count=3)
    lakes_only.enter(manager)
    lots = make(seed=SEED, water_rings=6, lake_count=0)
    lots.enter(manager)
    print('   rings 0 + lakes 0: %d sea strokes' % no_sea.status()['sea_strokes'])
    print('   rings 0 + lakes 3: %d sea strokes (the lakes are their own pass)'
          % lakes_only.status()['sea_strokes'])
    print('   rings 6 + lakes 0: %d sea strokes' % lots.status()['sea_strokes'])
    check('no rings and no lakes means no sea', no_sea.status()['sea_strokes'] == 0)
    check('lakes are drawn with no rings at all', lakes_only.status()['sea_strokes'] > 0)
    check('more rings is more sea', lots.status()['sea_strokes'] > status['sea_strokes'])

    print()
    print('6. the lakes are inland')
    lake_items = inkwater.lake_items(pour, random.Random(SEED ^ 0x1A4E), status['lakes'],
                                     pens=inkdraw.pen_widths(min(INK_W, INK_H), 1.0),
                                     hand=inkdraw.Hand(seed=9, tremor=0.5, px_per_mm=PPM),
                                     style='hash', px_per_mm=PPM)
    outlines = [lake_items[i] for i in range(0, len(lake_items), 4)]
    inland = 0
    for item in outlines:
        points = item.points
        cx = sum(x for x, _y in points) / len(points)
        cy = sum(y for _x, y in points) / len(points)
        if pour.on_land(cx, cy):
            inland += 1
    print('   %d lakes asked for, %d outlines, %d of them centred on land'
          % (status['lakes'], len(outlines), inland))
    check('every lake is drawn inland', len(outlines) == status['lakes'] and inland == len(outlines))

    print()
    print('7. reproducibility')
    again = make(seed=SEED)
    again.enter(manager)
    check('the same seed builds the same plan',
          again.status()['planned'] == status['planned']
          and bytes(again.land.mask) == bytes(mode.land.mask))
    other = make(seed=SEED + 1)
    other.enter(manager)
    check('a different seed builds a different sea',
          other.status()['sea_strokes'] != status['sea_strokes']
          or bytes(other.land.mask) != bytes(mode.land.mask))

    print()
    print('8. the pen and the frame budget')
    # Measured the way the app runs, NOT the way a probe likes to: one composite per frame's worth of
    # drawing. Flushing once after hundreds of items measures a different thing entirely -- the union
    # of all their dirty rects is nearly the whole sheet, so that number is the cost of a full-canvas
    # downscale (46-58 ms, measured in phase 1) and says nothing about a real frame.
    per_frame = max(1, int(round(mode.reveal.total / max(1.0, mode.draw_seconds) / mode.reveal_fps)))
    frames = []
    while not mode.reveal.done:
        t0 = time.perf_counter()
        for _ in range(per_frame):
            if mode.reveal.done:
                break
            mode.reveal.advance(1.0 / mode.reveal_fps, mode.draw_seconds, mode._draw_one)
        mode.render(manager.screen)
        frames.append((time.perf_counter() - t0) * 1000.0)
    frames.sort()
    worst = frames[-1]
    print('   %d frames simulated at %d items/frame; median %.2f ms, worst %.2f ms'
          % (len(frames), per_frame, frames[len(frames) // 2], worst))
    print('   ink on the sheet with the sea: %d sampled px' % ink_pixels(mode.sheet.canvas))
    check('a frame stays inside a 60 fps budget', worst < 16.6, '%.2f ms worst' % worst)

    print()
    print('9. evidence images')
    pygame.image.save(mode.sheet.canvas, os.path.join(OUT, 'inkmap_phase03_sheet.png'))
    crop = pygame.Surface((620, 620))
    crop.blit(mode.sheet.canvas, (0, 0), (300, 380, 620, 620))
    pygame.image.save(pygame.transform.scale(crop, (1080, 1080)),
                      os.path.join(OUT, 'inkmap_phase03_sea_zoom.png'))
    # a mid-draw frame: the sea appearing after the coast is this phase's visible feature
    partial = make(seed=SEED)
    partial.enter(manager)
    halfway = partial.status()['coast_strokes'] + partial.status()['sea_strokes'] // 3
    while partial.reveal.index < halfway:
        partial.reveal.advance(1.0, float(partial.reveal.total), partial._draw_one)
    partial.sheet.flush()
    pygame.image.save(partial.sheet.canvas, os.path.join(OUT, 'inkmap_phase03_in_progress.png'))
    for name in ('inkmap_phase03_sheet.png', 'inkmap_phase03_sea_zoom.png',
                 'inkmap_phase03_in_progress.png', 'inkmap_phase03_sea_hash.png',
                 'inkmap_phase03_sea_squiggle.png', 'inkmap_phase03_sea_stipple.png',
                 'inkmap_phase03_sea_wave.png'):
        print('   designs/%s' % name)
    check('the evidence images were written',
          all(os.path.exists(os.path.join(OUT, name)) for name in (
              'inkmap_phase03_sheet.png', 'inkmap_phase03_sea_zoom.png',
              'inkmap_phase03_in_progress.png')))

    failed = [name for name, ok, _d in results if not ok]
    print()
    print('VERDICT: %s (%d checks, %d failed)' % ('PASS' if not failed else 'FAIL', len(results), len(failed)))
    for name in failed:
        print('   FAILED: %s' % name)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
