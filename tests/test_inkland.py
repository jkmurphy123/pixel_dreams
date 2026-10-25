"""tests/test_inkland.py -- poured rice and the outline traced around it.

Three properties here are the difference between a map and a mess, and each one is checked in the
form the failure actually takes:

  * **An outline that runs off the sheet must stay OPEN.** Closing it appends the first point to the
    last and draws a ruler-straight line across the picture -- the ugliest thing this pipeline can
    do, and the reason `loops()` returns a `closed` flag that the mode has to respect.
  * **The saddle cases must use opposite pairings.** One pairing for both makes the two segments in
    a saddle cell cross; the chaining walk then meets a node with four segments and jumps between
    unrelated outlines, which shows up as straight lines leaping across the map.
  * **The tracing grid must be physical.** Marching squares only ever places a vertex at a cell
    midpoint, so a grid that followed the screen size would make the coastline's detail change with
    the display, and would make the trace cheaper or dearer for no reason.

The pour itself is measured, not asserted: the reference numbers are in `FOOTPRINT_RESPONSE` and the
tests here check that the dial lands where the table says it should.
"""

from __future__ import annotations

import math
import random

import pygame
import pytest

from core import inkland

#: The panel's real surfaces, so the pour tests measure what the kiosk will actually pour.
INK_W, INK_H = 2160, 3840
PX_PER_MM = min(INK_W, INK_H) / 200.0


@pytest.fixture(scope="module", autouse=True)
def _display():
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


# ── helpers ─────────────────────────────────────────────────────────────────

def mask_from_rows(rows):
    """Build a mask from ascii art: '#' is land, anything else is water."""
    gh = len(rows)
    gw = len(rows[0])
    mask = bytearray(gw * gh)
    for y, row in enumerate(rows):
        assert len(row) == gw
        for x, char in enumerate(row):
            if char == "#":
                mask[y * gw + x] = 1
    return mask, gw, gh


def pour_from_rows(rows, cell=5.0):
    mask, gw, gh = mask_from_rows(rows)
    return inkland.Pour(mask, gw, gh, cell, cell, grain_px=cell * 5.0, grains=0, attempts=1)


def perimeter(points):
    return sum(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


def bump_frequency(points, step=8):
    """
    How many times the outline reverses direction per 1000 px -- a proxy for how big its lobes are.
    Sampling every `step` vertices ignores the grid-scale zigzag and keeps the grain-scale bumps.
    """
    sampled = points[::step]
    reversals = 0
    length = 0.0
    previous_sign = None
    for i in range(1, len(sampled) - 1):
        ax, ay = sampled[i][0] - sampled[i - 1][0], sampled[i][1] - sampled[i - 1][1]
        bx, by = sampled[i + 1][0] - sampled[i][0], sampled[i + 1][1] - sampled[i][1]
        length += math.hypot(ax, ay)
        cross = ax * by - ay * bx
        if cross != 0.0:
            sign = 1 if cross > 0 else -1
            if previous_sign is not None and sign != previous_sign:
                reversals += 1
            previous_sign = sign
    return 1000.0 * reversals / max(1.0, length)


# ── the tracing grid ────────────────────────────────────────────────────────

def test_the_tracing_grid_is_physical_so_the_cost_does_not_follow_the_display():
    gw_a, gh_a, cell_a, _ = inkland.field_metrics(1000, 2000, 2.5)
    gw_b, gh_b, cell_b, _ = inkland.field_metrics(2000, 4000, 5.0)
    assert gw_a == gw_b and gh_a == gh_b, "doubling the surface and the resolution is the same map"
    assert cell_b == pytest.approx(cell_a * 2.0, rel=0.01)


def test_the_grid_covers_the_surface_exactly():
    gw, gh, cell_x, cell_y = inkland.field_metrics(INK_W, INK_H, PX_PER_MM)
    assert gw * cell_x == pytest.approx(INK_W, rel=0.001)
    assert gh * cell_y == pytest.approx(INK_H, rel=0.001)


def test_the_grid_resolution_does_not_move_when_the_grain_size_dial_does():
    # the dial changes how many cells a grain spans, never the grid: otherwise the most interesting
    # control on the panel would also be the one that decides how long a sheet takes to build
    gw, gh, _, _ = inkland.field_metrics(INK_W, INK_H, PX_PER_MM)
    assert (gw, gh) == (400, 711)


# ── rice ────────────────────────────────────────────────────────────────────

def test_grains_are_pre_rendered_at_every_angle_and_thickness():
    sprites = inkland.grain_sprites(24)
    assert len(sprites) == len(inkland.GRAIN_ASPECTS) * inkland.GRAIN_ANGLES
    for sprite in sprites[:5]:
        assert sprite.get_width() >= 3


def test_a_grain_is_an_ellipse_not_a_disc():
    grain = inkland.grain_sprites(40)[0]
    middle = sum(1 for x in range(grain.get_width()) if grain.get_at((x, 20))[3] > 0)
    top = sum(1 for x in range(grain.get_width()) if grain.get_at((x, 3))[3] > 0)
    assert middle > top, "a flat grain is wider across than it is near its end"


# ── marching squares ────────────────────────────────────────────────────────

def test_a_lone_block_of_land_traces_one_closed_loop_of_the_right_size():
    """
    Note the mask convention: a '#' is a SAMPLE at a grid corner, which is what the pour's pixel
    readback gives as well. The contour therefore runs through the cell midpoints around the block,
    spanning 4 cell units for a 4-sample block, and the staircase corners shave 0.5 off the area.
    """
    pour = pour_from_rows([
        "..........",
        "..........",
        "..####....",
        "..####....",
        "..####....",
        "..####....",
        "..........",
        "..........",
    ], cell=1.0)
    loops = pour.loops(min_area_cells=0.0)
    assert len(loops) == 1
    points, closed, area = loops[0]
    assert closed is True
    assert area == pytest.approx(15.5, abs=0.01)
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    assert (min(xs), max(xs)) == (1.5, 5.5)
    assert (min(ys), max(ys)) == (1.5, 5.5)


def test_land_that_runs_off_the_sheet_traces_an_open_outline():
    """
    The phase-2 acceptance criterion. A traced outline that reaches the edge of the field must come
    back open, with no vertex along the field boundary -- because that is exactly the line the
    tutorials never draw.
    """
    pour = pour_from_rows([
        "..........",
        "..........",
        "##########",
        "##########",
        "##########",
        "..........",
        "..........",
    ])
    loops = pour.loops(min_area_cells=0.0)
    assert loops, "a band of land across the sheet has to trace something"
    for points, closed, _area in loops:
        assert closed is False, "an outline that leaves the sheet must not be closed off"
        assert points[0] != points[-1]
        for x, y in points:
            assert y not in (0.0, 7.0), "no ink may be drawn along the edge of the sheet itself"


def test_the_two_saddle_cases_do_not_use_the_same_pairing():
    """
    The failing version used one pairing for both saddle cases, which made the segments cross
    inside the cell. The symptom was chained outlines that jumped between unrelated land masses.
    """
    def segments(rows):
        mask, gw, gh = mask_from_rows(rows)
        return inkland.marching_squares(mask, gw, gh)

    # case 5: the land is on the a and c corners (top-left and bottom-right)
    five = segments(["#.", ".#"])
    # case 10: the land is on the b and d corners (top-right and bottom-left)
    ten = segments([".#", "#."])
    assert len(five) == 2 and len(ten) == 2
    assert sorted(five) != sorted(ten), "the saddles must take opposite pairings"
    # and neither pairing may share an endpoint, or the walk arrives at a four-way node
    for pair in (five, ten):
        assert pair[0][0] != pair[1][0]
        assert pair[0][0] != pair[1][1]
        assert pair[0][1] != pair[1][0]
        assert pair[0][1] != pair[1][1]


def test_uniform_ground_produces_no_contour():
    mask, gw, gh = mask_from_rows(["....", "....", "...."])
    assert inkland.marching_squares(mask, gw, gh) == []
    mask, gw, gh = mask_from_rows(["####", "####", "####"])
    assert inkland.marching_squares(mask, gw, gh) == []


# ── chaining ────────────────────────────────────────────────────────────────

def test_chaining_keeps_an_open_chain_open():
    segments = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (1.0, 1.0))]
    loops = inkland.chain_loops(segments, min_len=1)
    assert len(loops) == 1
    points, closed = loops[0]
    assert closed is False
    assert points[0] != points[-1]
    assert len(points) == 3


def test_chaining_closes_a_chain_that_comes_back_to_its_start():
    segments = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (0.0, 1.0)), ((0.0, 1.0), (0.0, 0.0))]
    loops = inkland.chain_loops(segments, min_len=1)
    assert len(loops) == 1
    points, closed = loops[0]
    assert closed is True
    assert points[0] == points[-1]


def test_chaining_drops_fragments_shorter_than_the_minimum():
    segments = [((0.0, 0.0), (1.0, 0.0))]
    assert inkland.chain_loops(segments, min_len=4) == []
    assert len(inkland.chain_loops(segments, min_len=2)) == 1


def test_a_small_closed_island_survives_the_chaining_walk():
    """
    A 2x2 island's contour is only five points long. The chaining walk used to require ten and threw
    it away, which made the size filter look like the thing that dropped small islands when in fact
    they never reached it.
    """
    pour = pour_from_rows(["....", ".##.", ".##.", "...."], cell=1.0)
    loops = pour.loops(min_area_cells=0.0)
    assert len(loops) == 1 and loops[0][1] is True
    points = loops[0][0]
    # The walk tests its minimum against the chain BEFORE it repeats the first point to mark the
    # closure, so this island presented a length of 9 to the old default of 10 and was dropped
    # before the caller's size filter ever ran.
    assert len(points) - 1 == 9
    assert set(points) <= set(points[:-1])


def test_a_closed_loop_has_no_straight_chord_across_it():
    """
    A closed loop repeats its first point at the end -- that is the loop closing on itself, not a
    chord drawn across the map. This checks the two are distinguishable, because mistaking one for
    the other is how the straight-line artefact gets introduced.
    """
    pour = pour_from_rows([
        "..........",
        "..####....",
        "..####....",
        "..####....",
        "..........",
    ])
    points, closed, _area = pour.loops(min_area_cells=0.0)[0]
    assert closed is True
    assert points[0] == points[-1]
    # the closing point is adjacent to its predecessor, so the final segment is a real edge
    assert math.hypot(points[-1][0] - points[-2][0], points[-1][1] - points[-2][1]) < 2.0


# ── closing ─────────────────────────────────────────────────────────────────

def test_the_closing_welds_grains_that_merely_touch():
    """
    This is the tutorial's "nudge the rice before you trace it", and it is why the traced edge keeps
    its scallops instead of coming out as a smooth blob.
    """
    surface = pygame.Surface((30, 30))
    surface.fill((0, 0, 0))
    pygame.draw.rect(surface, (255, 255, 255), (5, 5, 1, 1))
    pygame.draw.rect(surface, (255, 255, 255), (9, 5, 1, 1))       # a 3-cell gap
    closed = inkland.close_mask(surface, r=2)
    assert closed.get_at((7, 5))[0] == 255, "the two grains should now be one mass"


def test_the_closing_does_not_weld_grains_that_are_apart():
    surface = pygame.Surface((60, 30))
    surface.fill((0, 0, 0))
    pygame.draw.rect(surface, (255, 255, 255), (5, 5, 1, 1))
    pygame.draw.rect(surface, (255, 255, 255), (35, 5, 1, 1))      # a 29-cell gap
    closed = inkland.close_mask(surface, r=2)
    assert closed.get_at((20, 5))[0] == 0, "distant grains must stay separate islands"


def test_closing_with_no_radius_changes_nothing():
    surface = pygame.Surface((20, 20))
    surface.fill((0, 0, 0))
    pygame.draw.rect(surface, (255, 255, 255), (5, 5, 3, 3))
    same = inkland.close_mask(surface, r=0)
    assert pygame.image.tostring(same, "RGB") == pygame.image.tostring(surface, "RGB")


# ── resampling and runs ─────────────────────────────────────────────────────

def test_resampling_spaces_points_evenly_and_keeps_the_ends():
    points = [(float(x), 0.0) for x in range(0, 101, 5)]
    out = inkland.resample(points, 10.0)
    assert out[0] == (0.0, 0.0)
    assert out[-1] == (100.0, 0.0)
    gaps = [out[i + 1][0] - out[i][0] for i in range(len(out) - 1)]
    assert all(abs(gap - 10.0) < 0.01 for gap in gaps), gaps


def test_resampling_a_path_thinner_than_the_step_leaves_it_alone():
    points = [(0.0, 0.0), (1.0, 0.0)]
    assert inkland.resample(points, 10.0) == points


def test_splitting_a_run_keeps_every_vertex_and_the_run_lengths():
    points = [(float(x) * 3.0, 0.0) for x in range(40)]        # 117 px long
    runs = inkland.split_run(points, 30.0)
    assert len(runs) > 3
    joined = []
    for run in runs:
        joined.extend(run if not joined else run[1:])
    assert joined == points, "splitting must not lose or duplicate a vertex"
    assert all(perimeter(run) <= 30.0 + 3.0 + 1e-6 for run in runs), "runs stay near the run length"


def test_splitting_is_linear_in_the_number_of_vertices():
    # the first version recomputed the whole run length on every step, which is quadratic and made a
    # 2000-vertex outline the slowest thing on the sheet
    points = [(float(x), 0.0) for x in range(4000)]
    runs = inkland.split_run(points, 16.0)
    assert len(runs) > 200


# ── the pour ────────────────────────────────────────────────────────────────

def test_the_grain_dial_is_a_physical_size():
    for grain_cells in (2.0, 5.0, 14.0):
        pour = inkland.pour_land(random.Random(1), INK_W, INK_H, PX_PER_MM,
                                 coverage=0.5, grain_cells=grain_cells, attempts=1)
        assert pour.grain_px / PX_PER_MM == pytest.approx(grain_cells * 2.5 / 5.0, rel=0.05)


@pytest.mark.parametrize("target", [0.30, 0.55, 0.75])
def test_the_pour_lands_where_the_coverage_dial_points(target):
    """
    The dial is calibrated by the measured response table, so a single pour should be close. Before
    that table existed the dial worked on the grain count instead of the clump footprint and
    saturated: it asked for 0.55 and reported 0.77 however hard it tried.
    """
    pour = inkland.pour_land(random.Random(4242), INK_W, INK_H, PX_PER_MM,
                             coverage=target, grain_cells=5.0, attempts=1)
    assert abs(pour.coverage - target) < 0.06, pour.coverage


def test_a_heavier_cover_of_land_stays_heavier_across_the_dial():
    covers = [inkland.pour_land(random.Random(9), INK_W, INK_H, PX_PER_MM,
                                coverage=target, attempts=1).coverage
              for target in (0.25, 0.50, 0.80)]
    assert covers[0] < covers[1] < covers[2], covers


def test_the_same_seed_pours_the_same_land():
    first = inkland.pour_land(random.Random(31337), INK_W, INK_H, PX_PER_MM, coverage=0.5, attempts=1)
    second = inkland.pour_land(random.Random(31337), INK_W, INK_H, PX_PER_MM, coverage=0.5, attempts=1)
    assert first.coverage == second.coverage
    assert bytes(first.mask) == bytes(second.mask)
    assert len(first.loops(min_area_cells=100.0)) == len(second.loops(min_area_cells=100.0))


def test_a_different_seed_pours_different_land():
    first = inkland.pour_land(random.Random(1), INK_W, INK_H, PX_PER_MM, coverage=0.5, attempts=1)
    second = inkland.pour_land(random.Random(2), INK_W, INK_H, PX_PER_MM, coverage=0.5, attempts=1)
    assert bytes(first.mask) != bytes(second.mask)


def test_bigger_rice_gives_a_lazier_coastline():
    """
    What the grain dial is actually for: measured on the reference pour, the number of direction
    reversals per 1000 px of coast fell 12.8, 12.5, 9.6, 8.7 as the grain went 3, 5, 8, 12 cells.
    Bigger rice means bigger, lazier lobes -- which is what "the scallop scale matches the grain
    size" means in something a test can hold on to.
    """
    wavelengths = []
    for grain_cells in (3.0, 12.0):
        pour = inkland.pour_land(random.Random(77), INK_W, INK_H, PX_PER_MM,
                                 coverage=0.55, grain_cells=grain_cells, clumps=3, attempts=2)
        points = pour.loops(min_area_cells=400.0)[0][0]
        wavelengths.append(bump_frequency(points))
    assert wavelengths[0] > wavelengths[1] * 1.2, wavelengths


def test_pouring_puts_land_where_the_mask_says():
    pour = inkland.pour_land(random.Random(5), INK_W, INK_H, PX_PER_MM, coverage=0.5, attempts=1)
    land_cells = sum(pour.mask)
    assert land_cells > 0
    # walk the mask through on_land and count what it agrees with
    agreed = 0
    for gy in range(0, pour.gh, 7):
        for gx in range(0, pour.gw, 7):
            x = (gx + 0.5) * pour.cell_x
            y = (gy + 0.5) * pour.cell_y
            if pour.on_land(x, y) == (pour.mask[gy * pour.gw + gx] == 1):
                agreed += 1
    assert agreed == len(range(0, pour.gh, 7)) * len(range(0, pour.gw, 7))


def test_on_land_is_false_off_the_field():
    pour = pour_from_rows(["##", "##"])
    assert pour.on_land(-5.0, -5.0) is False
    assert pour.on_land(1e6, 1e6) is False


# ── what the pour reports back ──────────────────────────────────────────────

def test_outlines_come_back_biggest_first():
    pour = pour_from_rows([
        "....................",
        ".####...............",
        ".####...............",
        "....................",
        "...............####.",
        "...............####.",
        "...............####.",
        "...............####.",
        "....................",
    ])
    areas = [area for _points, _closed, area in pour.loops(min_area_cells=0.0)]
    assert len(areas) == 2
    assert areas == sorted(areas, reverse=True)


def test_the_trace_is_only_done_once():
    pour = pour_from_rows([
        "..........", "..####....", "..####....", "..####....", "..........",
    ])
    assert pour._traced is None
    pour.loops(min_area_cells=0.0)
    traced = pour._traced
    assert traced is not None
    pour.loops(min_area_cells=0.0)
    assert pour._traced is traced, "the second call must reuse the trace, not redo it"


def test_the_size_filter_keeps_and_drops_the_right_outlines():
    pour = pour_from_rows([
        "..........",
        "..####....",
        "..####....",
        "..####....",
        "..####....",
        "..........",
        ".......##.",
        ".......##.",
        "..........",
    ], cell=1.0)
    everything = pour.loops(min_area_cells=0.0)
    assert len(everything) == 2
    assert [round(area, 1) for _p, _c, area in everything] == [15.5, 3.5]
    # a filter between the two areas keeps the continent and drops the islet
    assert len(pour.loops(min_area_cells=5.0)) == 1


def test_traced_loops_counts_the_outlines_the_size_filter_would_drop():
    pour = pour_from_rows([
        "..........",
        "..####....",
        "..####....",
        "..####....",
        "..####....",
        "..........",
        ".......##.",
        ".......##.",
        "..........",
    ], cell=1.0)
    assert pour.traced_loops == 2
    assert pour.traced_loops >= len(pour.loops(min_area_cells=5.0))


def test_outlines_are_scaled_out_of_cell_units_into_the_surface():
    pour = pour_from_rows(["....", ".##.", ".##.", "...."], cell=7.5)
    points, _closed, area = pour.loops(min_area_cells=0.0)[0]
    assert area == pytest.approx(3.5, abs=0.01), "area is measured in cells, not pixels"
    xs = [x for x, _y in points]
    assert (min(xs), max(xs)) == pytest.approx((3.75, 18.75)), "0.5 and 2.5 cells * 7.5 px"
    assert all(0.0 <= y <= 30.0 for _x, y in points)
