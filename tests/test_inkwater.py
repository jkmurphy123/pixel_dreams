"""tests/test_inkwater.py -- the sea: rings parallel to the coast, and the video's four units.

What is worth pinning here, in the form each failure actually takes:

  * **The sea must be on the SEA side.** The ring normal's sign comes from a test, not from the
    contour's winding, because getting it backwards draws the whole hatch over the continent and the
    land vanishes under it.
  * **A parallel curve must not be left folded.** Where the coast is concave by more than the offset
    the ring doubles back, and the drawn result is barbed wire -- measured, not feared: the first
    attempt at a 2 mm band came out as a braid of dark knots. The smoothing and the fold cutter are
    both load-bearing, so both are tested directly.
  * **The four units must all appear.** The artist says a single pattern "reads as a comb" and it is
    the random mixing of the four that makes the sea read as sea, so a plan in which one unit never
    occurs is a defect even though it draws something.
  * **An open coast stays open.** Same rule as phase 2: a land mass running off the sheet has two
    real ends and the ring must not join them with a chord.
"""

from __future__ import annotations

import math
import random

import pygame
import pytest

from core import inkland, inkwater

INK_W, INK_H = 2160, 3840
PX_PER_MM = min(INK_W, INK_H) / 200.0
PENS = None


@pytest.fixture(scope="module", autouse=True)
def _display():
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


@pytest.fixture(scope="module")
def pens():
    from core import inkdraw
    return inkdraw.pen_widths(min(INK_W, INK_H), 1.0)


def pour_from_rows(rows, cell=5.0):
    """A Pour from ascii art: '#' is land, anything else is water (corner samples, as the mask is)."""
    gh = len(rows)
    gw = len(rows[0])
    mask = bytearray(gw * gh)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == '#':
                mask[y * gw + x] = 1
    pour = inkland.Pour(mask, gw, gh, cell, cell, grain_px=cell * 5.0, grains=0, attempts=1)
    surface = pygame.Surface((gw, gh))
    surface.fill((0, 0, 0))
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == '#':
                surface.set_at((x, y), (255, 255, 255))
    pour.closed_surface = surface
    return pour


def _island_rows(width=56, height=40, left=16, right=41, top=12, bottom=27):
    """A big rectangular island with margins wide enough for three rings AND a few cells of erosion.
    The first version of this fixture was 8x5 cells with a 3-cell margin, so every erosion test
    legitimately erased it and every ring test ran off the field."""
    return [''.join('#' if (left <= x <= right and top <= y <= bottom) else '.'
                    for x in range(width)) for y in range(height)]


ISLAND = _island_rows()

#: The island's centre in cell units -- the contour runs half a cell outside the samples.
ISLAND_CENTRE = ((16 + 41) / 2.0 + 0.5, (12 + 27) / 2.0 + 0.5)


def island():
    return pour_from_rows(ISLAND)


# ── ring geometry ───────────────────────────────────────────────────────────

def test_ring_offsets_count_and_grow_outward():
    offsets = inkwater.ring_offsets(4, 10.0)
    assert len(offsets) == 4
    assert offsets == sorted(offsets)
    assert offsets[0] == pytest.approx(inkwater.RING_FIRST_MM * 10.0)


def test_no_rings_means_no_offsets():
    assert inkwater.ring_offsets(0, 10.0) == []


def test_ring_offsets_are_physical():
    small = inkwater.ring_offsets(3, 5.0)
    large = inkwater.ring_offsets(3, 10.0)
    for a, b in zip(small, large):
        assert b == pytest.approx(a * 2.0, rel=0.001)


def test_the_sea_is_put_on_the_sea_side():
    """The sign is tested against the land, so the hatch cannot end up over the continent."""
    pour = island()
    points = pour.loops(min_area_cells=0.0)[0][0]
    sign = inkwater.outward_sign(pour, points, True)
    centre = (ISLAND_CENTRE[0] * pour.cell_x, ISLAND_CENTRE[1] * pour.cell_y)
    ring = inkwater.offset_ring(points, True, 3.0 * pour.cell_x, sign)
    # the island's centre is land; the ring must be further from it than the coast is
    coast_reach = min(math.hypot(x - centre[0], y - centre[1]) for x, y in points)
    ring_reach = min(math.hypot(x - centre[0], y - centre[1]) for x, y in ring)
    assert ring_reach > coast_reach


def test_offset_ring_moves_every_vertex_the_same_distance():
    points = [(float(x), 0.0) for x in range(0, 100, 10)]
    ring = inkwater.offset_ring(points, False, 7.0, 1.0)
    assert len(ring) == len(points)
    for (_px, py), (_rx, ry) in zip(points, ring):
        assert abs(ry - py) == pytest.approx(7.0, abs=0.001)


def test_offset_ring_does_not_join_the_ends_of_an_open_coast():
    """
    A coast that runs off the sheet has two real ends. Wrapping them would draw the chord across the
    picture -- the same artefact phase 2 exists to prevent, one ring further out.
    """
    points = [(float(x), 0.0) for x in range(0, 100, 10)]
    ring = inkwater.offset_ring(points, False, 5.0, 1.0)
    assert ring[0] != ring[-1]
    assert math.hypot(ring[-1][0] - ring[0][0], ring[-1][1] - ring[0][1]) > 50.0


def test_a_single_point_offsets_to_nothing():
    assert inkwater.offset_ring([(0.0, 0.0)], True, 5.0, 1.0) == []


def test_smoothing_removes_the_fine_zigzag_and_keeps_the_shape():
    """
    The interior is what smoothing is for. The two ends keep more of the zigzag on purpose: a clamped
    window there averages the same vertex several times, which is correct for an open coast (the end
    of a line has no neighbours beyond it) and is why this test measures the middle.
    """
    zigzag = [(float(x), 10.0 if i % 2 else -10.0) for i, x in enumerate(range(0, 200))]
    window = 9
    smoothed = inkwater.smooth(zigzag, window, closed=False)
    interior = smoothed[window:-window]
    spread_before = max(y for _x, y in zigzag) - min(y for _x, y in zigzag)
    spread_inside = max(y for _x, y in interior) - min(y for _x, y in interior)
    assert spread_inside < spread_before * 0.25, spread_inside
    assert len(smoothed) == len(zigzag)
    # and the whole line is still there, not collapsed
    assert max(abs(y) for _x, y in smoothed) < spread_before


def test_smoothing_preserves_the_mean_height():
    points = [(float(x), 5.0) for x in range(60)]
    smoothed = inkwater.smooth(points, 7, closed=False)
    assert all(y == pytest.approx(5.0) for _x, y in smoothed)


def test_smoothing_a_short_path_leaves_it_alone():
    points = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    assert inkwater.smooth(points, 9, closed=False) == points


# ── the fold cutter ─────────────────────────────────────────────────────────

def test_a_clean_parallel_line_is_not_cut():
    source = [(float(x), 0.0) for x in range(0, 100, 5)]
    ring = inkwater.offset_ring(source, False, 10.0, 1.0)
    runs = inkwater.cut_folds(source, ring)
    assert len(runs) == 1
    assert len(runs[0]) == len(ring)


def test_a_folded_parallel_line_is_cut_where_it_doubles_back():
    """
    An explicit fold: the coast runs right, turns back on itself, and runs right again, with the
    offset larger than the notch is deep. The parallel curve crosses itself there, and the cutter has
    to break the line rather than draw the crossing.
    """
    source = []
    for x in range(0, 60):
        source.append((float(x), 0.0))
    for x in range(60, 50, -1):
        source.append((float(x), 4.0))
    for x in range(50, 100):
        source.append((float(x), 0.0))
    ring = inkwater.offset_ring(source, False, 20.0, 1.0)
    runs = inkwater.cut_folds(source, ring)
    total = sum(len(run) for run in runs)
    assert total > 0
    # some vertices are dropped at the fold, and the survivors come back as more than one run
    assert len(runs) >= 2, 'a folded ring must be cut into runs'


def test_cutting_never_loses_the_line_entirely():
    pour = island()
    points = pour.loops(min_area_cells=0.0)[0][0]
    sign = inkwater.outward_sign(pour, points, True)
    source = inkwater.smooth(points, 16, closed=True)
    ring = inkwater.offset_ring(source, True, 6.0 * pour.cell_x, sign)
    runs = inkwater.cut_folds(source, ring)
    assert runs
    assert sum(len(run) for run in runs) > len(ring) * 0.6


# ── the four units, and the styles ──────────────────────────────────────────

def test_the_four_units_are_the_videos_four():
    assert inkwater.UNITS == (('hash',), ('hash', 'dot'), ('hash', 'dot', 'hash'), ('dot', 'hash'))
    # and they are all different, which is the whole point of alternating them
    assert len(set(inkwater.UNITS)) == 4


def test_every_unit_contains_at_least_one_hash():
    for unit in inkwater.UNITS:
        assert 'hash' in unit


def test_a_hash_is_one_straight_line(pens):
    rng = random.Random(1)
    tokens = inkwater.style_mark('hash', (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    assert len(tokens) == 1
    kind, points, width = tokens[0]
    assert kind == 'line' and len(points) == 2


def test_stipple_replaces_the_hash_with_dots(pens):
    rng = random.Random(1)
    tokens = inkwater.style_mark('stipple', (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    assert tokens and all(token[0] == 'dot' for token in tokens)
    assert len(tokens) >= 3


def test_the_squiggle_style_is_broken_into_two_pieces():
    rng = random.Random(1)
    tokens = inkwater.style_mark('squiggle', (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    lines = [t for t in tokens if t[0] == 'line']
    assert len(lines) == 2, 'the video\'s alternate is "the same technique, adding breaks"'
    assert all(len(t[1]) >= 2 for t in lines)


def test_the_wave_style_swings_across_the_line():
    rng = random.Random(1)
    tokens = inkwater.style_mark('wave', (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    assert len(tokens) == 1
    _kind, points, _width = tokens[0]
    assert len(points) == 4
    # an S: the middle two points are displaced across the line, and both the same way
    assert abs(points[1][0]) > 0.1 and abs(points[2][0]) > 0.1
    assert (points[1][0] > 0) == (points[2][0] > 0)


def test_the_four_styles_all_produce_their_own_marks():
    rng = random.Random(3)
    shapes = {}
    for style in ('hash', 'squiggle', 'stipple', 'wave'):
        shapes[style] = inkwater.style_mark(style, (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    assert len({repr(v) for v in shapes.values()}) >= 3, 'the styles must not all draw the same thing'


def test_an_unknown_style_draws_a_plain_hash():
    rng = random.Random(3)
    tokens = inkwater.style_mark('nonsense', (0.0, 0.0), (0.0, 20.0), rng, 3.0)
    assert len(tokens) == 1 and tokens[0][0] == 'line'


# ── drawing ─────────────────────────────────────────────────────────────────

def test_a_water_item_draws_its_line_and_its_marks(pens):
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    hand = __import__('core.inkdraw', fromlist=['Hand']).Hand(seed=1, tremor=0.0)
    item = inkwater.WaterItem([(10.0, 10.0), (100.0, 10.0)],
                              [('line', [(20.0, 20.0), (20.0, 40.0)], 3.0),
                               ('dot', (60.0, 20.0), 2.0)], 3.0)
    rects = item.draw(surface, hand, pens, (0, 0, 0, 255))
    assert rects
    assert surface.get_at((50, 10))[3] > 0, 'the parallel line should be drawn'
    assert surface.get_at((20, 30))[3] > 0, 'the hash should be drawn'
    # a dot lands within a pixel or so of where it was asked -- pygame rasterises an even-radius
    # circle across the pixel boundary, so the centre is not exactly the requested point
    landed = any(surface.get_at((60 + dx, 20 + dy))[3] > 0
                 for dx in (0, 1, -1) for dy in (0, 1, -1))
    assert landed, 'the dot should be drawn'


def test_a_water_item_with_nothing_in_it_draws_nothing(pens):
    surface = pygame.Surface((50, 50), pygame.SRCALPHA)
    hand = __import__('core.inkdraw', fromlist=['Hand']).Hand(seed=1, tremor=0.0)
    assert inkwater.WaterItem([], [], 3.0).draw(surface, hand, pens, (0, 0, 0, 255)) == []


# ── dilate / erode ──────────────────────────────────────────────────────────

def test_dilating_grows_the_land_and_eroding_shrinks_it():
    pour = island()
    start = sum(1 for value in pour.mask if value)
    grown = inkwater.dilate(pour.closed_surface, 3)
    eroded = inkwater.erode(pour.closed_surface, 3)
    grown_mask = inkland._read_mask(grown, pour.gw, pour.gh)
    eroded_mask = inkland._read_mask(eroded, pour.gw, pour.gh)
    assert sum(grown_mask) > start
    assert 0 < sum(eroded_mask) < start


def test_eroding_far_enough_removes_a_thin_feature_entirely():
    pour = pour_from_rows(['...........', '.....#####.', '.....#####.', '...........'])
    gone = inkwater.erode(pour.closed_surface, 4)
    assert sum(inkland._read_mask(gone, pour.gw, pour.gh)) == 0


# ── lakes ───────────────────────────────────────────────────────────────────

def test_clear_land_spots_finds_land_with_room_around_it():
    pour = island()
    spots = inkwater.clear_land_spots(pour, 3, random.Random(1), 4, min_separation=20.0)
    assert spots
    for x, y in spots:
        assert pour.on_land(x, y), 'a lake has to be on land'


def test_clear_land_spots_respects_the_separation():
    pour = island()
    spots = inkwater.clear_land_spots(pour, 2, random.Random(2), 8, min_separation=60.0)
    for i in range(len(spots)):
        for j in range(i + 1, len(spots)):
            assert math.hypot(spots[i][0] - spots[j][0], spots[i][1] - spots[j][1]) >= 60.0


def test_clear_land_spots_gives_up_instead_of_lying_when_there_is_no_room():
    pour = pour_from_rows(['........', '..####..', '..####..', '........'])
    assert inkwater.clear_land_spots(pour, 20, random.Random(1), 3, min_separation=5.0) == []
    assert inkwater.clear_land_spots(pour, 30, random.Random(1), 3, min_separation=5.0) == []


def test_a_lake_outline_is_a_closed_wobbly_blob_of_the_right_size():
    rng = random.Random(5)
    radius = 40.0
    points = inkwater.lake_outline(100.0, 100.0, radius, rng)
    assert points[0] == points[-1], 'a lake outline closes'
    reaches = [math.hypot(x - 100.0, y - 100.0) for x, y in points]
    assert max(reaches) < radius * 1.5
    assert min(reaches) > radius * 0.4
    # squashed: wider than it is tall
    xs = [abs(x - 100.0) for x, _y in points]
    ys = [abs(y - 100.0) for _x, y in points]
    assert max(xs) > max(ys)


def test_a_lake_gets_three_inward_rings_and_the_innermost_is_dots(pens):
    from core import inkdraw
    rng = random.Random(7)
    outline = inkwater.lake_outline(100.0, 100.0, 45.0, rng)
    hand = inkdraw.Hand(seed=1, tremor=0.4)
    items = inkwater.lake_contents(outline, (100.0, 100.0), pens)
    assert len(items) == 3
    assert items[0].points and items[1].points
    assert items[2].points == [], 'the innermost ring is dots, as the prototype had it'
    assert items[2].marks
    # each ring is smaller than the one before it
    def reach(item):
        return max(math.hypot(x - 100.0, y - 100.0) for x, y in item.points) if item.points else 0
    assert reach(items[0]) > reach(items[1])


def test_asking_for_no_lakes_gets_none(pens):
    from core import inkdraw
    pour = island()
    hand = inkdraw.Hand(seed=1, tremor=0.4)
    assert inkwater.lake_items(pour, random.Random(1), 0, pens=pens, hand=hand, style='hash',
                               px_per_mm=PX_PER_MM) == []


def test_lakes_are_placed_on_the_real_land(pens):
    from core import inkdraw
    pour = inkland.pour_land(random.Random(4242), INK_W, INK_H, PX_PER_MM, coverage=0.55, clumps=4)
    hand = inkdraw.Hand(seed=1, tremor=0.4)
    items = inkwater.lake_items(pour, random.Random(9), 3, pens=pens, hand=hand, style='hash',
                                px_per_mm=PX_PER_MM)
    assert items, 'three lakes were asked for on a sheet that is half land'
    # the first item of each lake is its outline; its centre must be on land
    for index in range(0, len(items) - 3, 4):
        outline = items[index].points
        cx = sum(x for x, _y in outline) / len(outline)
        cy = sum(y for _x, y in outline) / len(outline)
        assert pour.on_land(cx, cy), 'a lake has to be drawn inland'


# ── the whole sea ───────────────────────────────────────────────────────────

def test_no_rings_asked_for_means_no_sea(pens):
    from core import inkdraw
    pour = island()
    hand = inkdraw.Hand(seed=1, tremor=0.4)
    masses = pour.loops(min_area_cells=0.0)
    assert inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=0,
                                px_per_mm=PX_PER_MM) == []


def test_more_rings_means_more_sea(pens):
    from core import inkdraw
    pour = island()
    masses = pour.loops(min_area_cells=0.0)
    counts = []
    for rings in (1, 3):
        hand = inkdraw.Hand(seed=1, tremor=0.4)
        counts.append(len(inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash',
                                               rings=rings, px_per_mm=PX_PER_MM)))
    assert counts[0] > 0
    assert counts[1] > counts[0]


def test_the_sea_keeps_off_the_land(pens):
    """
    The acceptance criterion in the form it fails: hatch drawn over the continent. The ring is offset
    from the coast, so most of its vertices must sit on water -- the ones that do not are the corners
    the offset cuts across in a tight bay.
    """
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    hand = inkdraw.Hand(seed=1, tremor=0.4)
    items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=3,
                                 px_per_mm=PX_PER_MM)
    assert items
    on_land = off_land = 0
    for item in items:
        for x, y in item.points:
            if pour.on_land(x, y):
                on_land += 1
            else:
                off_land += 1
    assert off_land > on_land * 4, (on_land, off_land)


def test_the_hashes_point_away_from_the_land(pens):
    """Every hash in the innermost ring must END further from the island than it STARTS."""
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    centre = (ISLAND_CENTRE[0] * pour.cell_x, ISLAND_CENTRE[1] * pour.cell_y)
    masses = pour.loops(min_area_cells=0.0)
    hand = inkdraw.Hand(seed=1, tremor=0.0)
    items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=1,
                                 px_per_mm=PX_PER_MM)
    checked = 0
    for item in items:
        for token in item.marks:
            if token[0] != 'line':
                continue
            points = token[1]
            base = points[0]
            tip = points[-1]
            before = math.hypot(base[0] - centre[0], base[1] - centre[1])
            after = math.hypot(tip[0] - centre[0], tip[1] - centre[1])
            assert after > before, (base, tip)
            checked += 1
    assert checked > 0, 'the sea should have hung some hashes'


def test_every_one_of_the_four_units_appears_in_a_plan(pens):
    """
    The video says a single pattern reads as a comb and the alternation IS the illusion, so a plan
    that never draws one of the four is a defect even though it produces ink.
    """
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    hand = inkdraw.Hand(seed=2, tremor=0.4)
    items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=2,
                                 px_per_mm=PX_PER_MM)
    counts = {'line': 0, 'dot': 0}
    for item in items:
        for token in item.marks:
            counts[token[0]] += 1
    assert counts['line'] > 3, counts
    assert counts['dot'] > 3, counts


def test_a_hash_is_clipped_rather_than_inked_onto_the_land():
    """
    Found by measuring a whole sea: 162 of 1696 hashes ended on the continent, because across a narrow
    inlet the outward normal points at the FAR shore. The fixture for that is a narrow channel with
    land on both sides -- an island has no far shore to overshoot onto, which is why the first version
    of this test could not reproduce it.
    """
    pour = island()
    # from the island's centre every direction is land: a hash from there is refused outright
    centre = (ISLAND_CENTRE[0] * pour.cell_x, ISLAND_CENTRE[1] * pour.cell_y)
    assert inkwater.water_length(pour, centre, 1.0, 0.0, 40.0) == 0.0
    # from a point well out at sea the full length is allowed
    assert inkwater.water_length(pour, (2.0 * pour.cell_x, 2.0 * pour.cell_y), 0.0, 1.0, 40.0) == 40.0

    # a narrow channel: land above, water in the middle, land below
    channel = pour_from_rows(['##########', '##########',
                              '..........', '..........', '..........', '..........',
                              '##########', '##########'])
    base = (5.0 * channel.cell_x, 3.0 * channel.cell_y)      # in the channel, nearer its top
    across = inkwater.water_length(channel, base, 0.0, 1.0, 20.0)
    assert 0.0 < across < 20.0, 'a hash across a channel must be cut to the channel'
    # and the same walk the other way is cut too: the channel is narrow both ways
    back = inkwater.water_length(channel, base, 0.0, -1.0, 20.0)
    assert 0.0 < back < 20.0
    assert back < across, 'the base sits nearer the top of the channel, so less room that way'


def test_no_hash_in_a_real_sea_ends_on_the_land(pens):
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    hand = inkdraw.Hand(seed=4, tremor=0.4)
    items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=3,
                                 px_per_mm=PX_PER_MM)
    checked = 0
    for item in items:
        for token in item.marks:
            if token[0] != 'line':
                continue
            tip = token[1][-1]
            assert not pour.on_land(tip[0], tip[1]), tip
            checked += 1
    assert checked > 20


def test_the_same_seed_builds_the_same_sea(pens):
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    built = []
    for _ in range(2):
        hand = inkdraw.Hand(seed=11, tremor=0.4)
        items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=2,
                                     px_per_mm=PX_PER_MM)
        built.append([(item.points, repr(item.marks)) for item in items])
    assert built[0] == built[1]


def test_a_different_seed_builds_a_different_sea(pens):
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    shapes = []
    for seed in (11, 12):
        hand = inkdraw.Hand(seed=seed, tremor=0.4)
        items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style='hash', rings=2,
                                     px_per_mm=PX_PER_MM)
        shapes.append([repr(item.marks) for item in items])
    assert shapes[0] != shapes[1]


def test_the_styles_produce_different_seas(pens):
    from core import inkdraw
    pour = pour_from_rows(ISLAND)
    masses = pour.loops(min_area_cells=0.0)
    shapes = {}
    for style in ('hash', 'squiggle', 'stipple', 'wave'):
        hand = inkdraw.Hand(seed=21, tremor=0.4)
        items = inkwater.coast_water(masses, pour, pens=pens, hand=hand, style=style, rings=2,
                                     px_per_mm=PX_PER_MM)
        shapes[style] = repr([item.marks for item in items])
    assert len(set(shapes.values())) == 4, 'each style has to draw its own sea'
