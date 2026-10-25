"""tests/test_inkdraw.py -- the drawing vocabulary: nib sizes, nib pressure, and the hand.

The reason these are tested rather than eyeballed is that two of them are the difference between a
sheet that reads as hand-inked and one that reads as machine-drawn, and both are silent failures:

  * nib widths must follow the SHEET, not the screen. If they are fixed pixel counts the drawing
    gets a spider-web look on a bigger display and nothing errors.
  * the hand's wander must PERSIST between strokes. If each stroke restarts the drift, a long
    outline drawn in runs develops a kink at every join -- and the mode draws every outline in runs.
"""

from __future__ import annotations

import math

import pygame
import pytest

from core import inkdraw

WIDTH, HEIGHT = 200, 200


@pytest.fixture(scope="module", autouse=True)
def _display():
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((WIDTH, HEIGHT))
    yield


@pytest.fixture()
def surface():
    out = pygame.Surface((WIDTH, HEIGHT))
    out.fill((0, 0, 0))
    return out


def _white_pixels(surface, column=None, row=None):
    if column is not None:
        return sum(1 for y in range(surface.get_height())
                   if surface.get_at((column, y))[0] > 120)
    return sum(1 for x in range(surface.get_width())
               if surface.get_at((x, row))[0] > 120)


# ── nibs ────────────────────────────────────────────────────────────────────

def test_the_nib_table_is_the_real_micron_sizes():
    assert inkdraw.NIB_MM["003"] == 0.15
    assert inkdraw.NIB_MM["05"] == 0.45
    # heaviest last, so pens()["05"] is always the boldest line
    widths = [inkdraw.NIB_MM[k] for k in ("003", "005", "01", "02", "03", "05")]
    assert widths == sorted(widths)


def test_nib_widths_follow_the_sheet_not_the_screen():
    small = inkdraw.pen_widths(1080)
    large = inkdraw.pen_widths(2160)
    for name in inkdraw.NIB_MM:
        assert large[name] == pytest.approx(small[name] * 2.0, rel=0.01)


def test_a_nib_comes_out_as_its_millimetres_on_the_panel():
    widths = inkdraw.pen_widths(1080)          # a 1080 px sheet is the 200 mm reference page
    px_per_mm = 1080 / inkdraw.REFERENCE_SHEET_MM
    for name, mm in inkdraw.NIB_MM.items():
        assert widths[name] == pytest.approx(mm * px_per_mm, rel=0.01), name


def test_pen_scale_multiplies_every_nib_equally():
    plain = inkdraw.pen_widths(1080, 1.0)
    heavy = inkdraw.pen_widths(1080, 2.0)
    for name in inkdraw.NIB_MM:
        assert heavy[name] == pytest.approx(plain[name] * 2.0, rel=0.01)


def test_a_nib_never_shrinks_below_a_visible_width():
    # 003 on a tiny surface would otherwise round away to nothing and the pen would draw nothing
    assert min(inkdraw.pen_widths(20).values()) >= 0.6


# ── nib pressure ────────────────────────────────────────────────────────────

def test_pressure_is_lightest_at_the_ends_and_fullest_in_the_middle():
    assert inkdraw.pressure(0.0) < 0.5
    assert inkdraw.pressure(1.0) < 0.5
    assert inkdraw.pressure(0.5) == pytest.approx(1.0, abs=0.01)
    assert inkdraw.pressure(0.5) > inkdraw.pressure(0.25) > inkdraw.pressure(0.0)


def test_pressure_is_clamped_outside_zero_to_one():
    assert inkdraw.pressure(-3.0) == inkdraw.pressure(0.0)
    assert inkdraw.pressure(4.0) == inkdraw.pressure(1.0)


# ── the hand ────────────────────────────────────────────────────────────────

def test_a_hand_with_no_tremor_does_not_wander():
    hand = inkdraw.Hand(seed=3, tremor=0.0)
    points = [(x, 100.0) for x in range(0, 200, 4)]
    assert hand.jitter(points) == [(float(x), 100.0) for x in range(0, 200, 4)]


def test_a_shakier_hand_wanders_further():
    # tremor is physical: the same dial on a bigger ink layer is the same wobble in millimetres
    spans = {}
    for tremor in (0.25, 0.55, 1.5):
        hand = inkdraw.Hand(seed=11, tremor=tremor, px_per_mm=10.8)
        points = [(x, 100.0) for x in range(0, 200, 4)]
        offsets = [abs(y - 100.0) for _, y in hand.jitter(points)]
        spans[tremor] = sum(offsets) / len(offsets)
    assert spans[0.25] > 0.0, "a little tremor must still be visible"
    assert spans[0.25] < spans[0.55] < spans[1.5]


def test_tremor_is_in_millimetres_so_it_scales_with_the_surface():
    small = inkdraw.Hand(seed=7, tremor=0.55, px_per_mm=5.4)
    large = inkdraw.Hand(seed=7, tremor=0.55, px_per_mm=10.8)
    assert large.amplitude == pytest.approx(small.amplitude * 2.0, rel=0.01)


def test_the_wander_is_an_ar1_walk_so_it_persists_instead_of_being_white_noise():
    """
    This is the property that makes a shared Hand necessary across the runs of one outline. A
    white-noise jitter has zero correlation between successive offsets; a wander drifts.
    """
    hand = inkdraw.Hand(seed=5, tremor=1.0, px_per_mm=10.0)
    steps = [hand.offset() for _ in range(400)]
    mean = sum(steps) / len(steps)
    var = sum((s - mean) ** 2 for s in steps) / len(steps)
    covariance = sum((steps[i] - mean) * (steps[i + 1] - mean)
                     for i in range(len(steps) - 1)) / (len(steps) - 1)
    assert var > 0.0
    assert covariance / var > 0.4, "successive offsets must be strongly correlated"


def test_the_same_seed_gives_the_same_hand():
    first = inkdraw.Hand(seed=99, tremor=0.8, px_per_mm=10.0)
    second = inkdraw.Hand(seed=99, tremor=0.8, px_per_mm=10.0)
    assert [first.offset() for _ in range(50)] == [second.offset() for _ in range(50)]


def test_jitter_displaces_perpendicular_to_the_direction_of_travel():
    hand = inkdraw.Hand(seed=2, tremor=1.0, px_per_mm=10.0)
    along_x = hand.jitter([(0.0, 50.0), (10.0, 50.0), (20.0, 50.0)])
    # travelling along x, so the displacements must be mostly in y
    assert all(abs(y - 50.0) > abs(x - px) for px, (x, y) in zip((0, 10, 20), along_x))
    hand2 = inkdraw.Hand(seed=2, tremor=1.0, px_per_mm=10.0)
    along_y = hand2.jitter([(50.0, 0.0), (50.0, 10.0), (50.0, 20.0)])
    assert all(abs(x - 50.0) > abs(y - py) for py, (x, y) in zip((0, 10, 20), along_y))


def test_jitter_keeps_the_first_and_last_vertex_count():
    hand = inkdraw.Hand(seed=1, tremor=0.5)
    points = [(x, 20.0) for x in range(9)]
    assert len(hand.jitter(points)) == len(points)


def test_jitter_passes_through_a_single_point_untouched():
    hand = inkdraw.Hand(seed=1, tremor=1.0)
    assert hand.jitter([(5.0, 6.0)]) == [(5.0, 6.0)]


# ── strokes ─────────────────────────────────────────────────────────────────

def _flat_points(count=60, y=100.0, step=2.0):
    return [(i * step, y) for i in range(count)]


def test_a_stroke_puts_ink_on_the_surface(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    rect = inkdraw.stroke(surface, _flat_points(), 6.0, hand, colour=(255, 255, 255, 255))
    assert rect is not None
    assert _white_pixels(surface, row=100) > 50


def test_a_stroke_reports_where_it_drew(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    rect = inkdraw.stroke(surface, [(10.0, 40.0), (60.0, 40.0)], 4.0, hand,
                          colour=(255, 255, 255, 255))
    assert rect.left <= 10 and rect.right >= 60
    assert rect.top <= 40 - 2 and rect.bottom >= 40 + 2
    # and everything it drew is inside the rect it reported: this is what the dirty-rect composite
    # relies on, so a stroke that draws outside it corrupts the sheet silently
    for x in range(rect.left - 3, rect.right + 4):
        for y in range(rect.top - 3, rect.bottom + 4):
            if 0 <= x < WIDTH and 0 <= y < HEIGHT and surface.get_at((x, y))[0] > 120:
                assert rect.inflate(2, 2).collidepoint(x, y), (x, y)


def test_a_stroke_leaves_everything_outside_its_reported_rect_alone(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    inkdraw.stroke(surface, _flat_points(), 5.0, hand, colour=(255, 255, 255, 255))
    # sample well away from the line, which runs along y=100 from x=0 to x=118
    for point in ((2, 2), (197, 2), (2, 197), (197, 197), (60, 20), (60, 180)):
        assert surface.get_at(point)[0] == 0, point


def test_a_longer_stroke_draws_proportionally_more_ink(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    short = pygame.Surface((WIDTH, HEIGHT)); short.fill((0, 0, 0))
    long = pygame.Surface((WIDTH, HEIGHT)); long.fill((0, 0, 0))
    inkdraw.stroke(short, [(10.0, 100.0), (60.0, 100.0)], 5.0, hand, colour=(255, 255, 255, 255))
    inkdraw.stroke(long, [(10.0, 100.0), (160.0, 100.0)], 5.0, hand, colour=(255, 255, 255, 255))
    assert _white_pixels(long, row=100) > _white_pixels(short, row=100) * 2


def test_taper_thins_the_ends_of_a_stroke(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    points = [(float(x), 100.0) for x in range(0, 120, 2)]
    inkdraw.stroke(surface, points, 14.0, hand, taper=True, colour=(255, 255, 255, 255))
    def column_width(x):
        return sum(1 for y in range(HEIGHT) if surface.get_at((x, y))[0] > 120)
    assert column_width(3) < column_width(60)
    assert column_width(116) < column_width(60)


def test_without_taper_the_stroke_keeps_its_weight(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    points = [(float(x), 100.0) for x in range(0, 120, 2)]
    inkdraw.stroke(surface, points, 14.0, hand, taper=False, colour=(255, 255, 255, 255))
    def column_width(x):
        return sum(1 for y in range(HEIGHT) if surface.get_at((x, y))[0] > 120)
    assert abs(column_width(3) - column_width(60)) <= 3


def test_a_stroke_that_cannot_be_drawn_reports_nothing(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    assert inkdraw.stroke(surface, [(1.0, 1.0)], 4.0, hand) is None
    assert inkdraw.stroke(surface, [], 4.0, hand) is None
    assert inkdraw.stroke(surface, _flat_points(), 0.0, hand) is None


def test_a_stroke_uses_the_colour_it_is_given(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    inkdraw.stroke(surface, _flat_points(), 8.0, hand, colour=(255, 0, 0, 255))
    assert surface.get_at((60, 100))[:3] == (255, 0, 0)


def test_zero_length_segments_do_not_break_a_stroke(surface):
    hand = inkdraw.Hand(seed=4, tremor=0.0)
    rect = inkdraw.stroke(surface, [(10.0, 10.0), (10.0, 10.0), (60.0, 10.0)], 4.0, hand,
                          colour=(255, 255, 255, 255))
    assert rect is not None and rect.right >= 60


def test_the_hand_is_advanced_by_drawing_so_the_next_stroke_carries_on(surface):
    """
    The mode draws a whole outline as many short runs. If drawing did not advance the hand, every
    run would restart at the same drift and the outline would show a repeated wobble.
    """
    hand = inkdraw.Hand(seed=4, tremor=0.6, px_per_mm=10.0)
    drift_before = hand.drift
    inkdraw.stroke(surface, _flat_points(), 4.0, hand, colour=(255, 255, 255, 255))
    assert hand.drift != drift_before
