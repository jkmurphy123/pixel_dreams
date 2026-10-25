"""
tests/test_inkmap.py -- the ink-map mode: phase 1 (the sheet) and phase 2 (the coastline).

What is worth pinning here is not "the mode exists" but the behaviours the later phases depend on:

  * the paper is built ONCE at the screen size, and is not a flat wash;
  * every texture colour is DERIVED from `paper_tone`, so changing the tone changes the sheet
    instead of leaving blotches behind in the old colour;
  * the ink layer is supersampled and only the DIRTY RECT is composited -- that is what makes a
    smooth pen affordable, and it is invisible in the code;
  * the reveal cursor paces a plan over `draw_minutes` and never runs past its end;
  * the plan is the COASTLINE, drawn in runs that share one hand, so an outline drawn as many runs
    is still one continuous line;
  * a seed reproduces the whole sheet -- paper and pour and coast -- because a map worth looking at
    has to be a map you can get back.

The registry checks at the end of the file keep the panel honest: every control says which phase
draws with it, and the set of live controls is compared BOTH ways against the mode's own
`LIVE_PARAMS`, so a control can never quietly stop working or quietly claim to work.
"""

from __future__ import annotations

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from core import inkdraw  # noqa: E402
from core.inksheet import Reveal, Sheet  # noqa: E402
from core.loader import build_merged_config, load_entrypoint  # noqa: E402
from core.config import load_json  # noqa: E402
from core.cache import ResourceCache  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # Initialise, but do NOT pygame.quit() here: a MODULE-scoped quit tears the font module down
    # for every later module in the same session (it broke test_layout_align, which is
    # alphabetically after this file). test_smoke's session fixture owns init and quit.
    pygame.init()
    pygame.font.init()
    # A video mode so Surface.convert()/convert_alpha() take their real path rather than the
    # no-display fallback the probes use. Only if nothing has set one, so this cannot clobber a
    # display another module is relying on.
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


class FakeManager:
    """Minimal stand-in for ModeManager: screen, cache and the two size attributes."""

    def __init__(self, w=240, h=400):
        self.screen = pygame.Surface((w, h))
        self.cache = ResourceCache()
        self.width = w
        self.height = h


def _sheet(**kw):
    """A small sheet -- the real one is 1080x1920 and would make the suite crawl."""
    args = dict(width=240, height=400, seed=7, paper_age=0.35, supersample=2)
    args.update(kw)
    sheet = Sheet(**args)
    sheet.build_paper()
    return sheet


# ---------------------------------------------------------------- the paper

def test_paper_is_built_at_the_screen_size():
    sheet = _sheet()
    assert sheet.paper.get_size() == (240, 400)
    assert sheet.canvas.get_size() == (240, 400)


def test_the_paper_is_not_a_flat_wash():
    """A parchment with no blotching, fibre or vignette is just a coloured rectangle."""
    sheet = _sheet()
    data = pygame.image.tostring(sheet.paper, "RGB")
    assert len(set(data[i:i + 3] for i in range(0, len(data), 3))) > 60, \
        "the sheet should have many distinct colours, not one fill"


def test_the_ageing_is_low_frequency_mottling_and_not_only_speckle():
    """
    Averaging 8x8 blocks separates the two ageing layers: fibre is high frequency and averages
    away, blotching is low frequency and survives.

    This is the test that would have caught the first version of `build_paper`, where the
    blotches were composited once at 3-9/255 and moved a pixel by ONE level -- a sheet that
    looked flat while the code appeared to paint it.
    """
    # At a size that is representative of the wall: the blob density is scaled by AREA, so a
    # tiny sheet legitimately shows almost no mottling and would prove nothing either way.
    aged = _sheet(width=540, height=960, paper_age=1.0)
    plain = _sheet(width=540, height=960, paper_age=0.0)
    spread_aged, spread_plain = _block_spread(aged.paper), _block_spread(plain.paper)
    assert spread_aged > spread_plain + 8, \
        f"aged {spread_aged:.1f} vs plain {spread_plain:.1f}"


def test_the_vignette_is_a_gradient_and_not_a_set_of_hard_bands():
    """
    Brightness falls smoothly toward the edge.

    This is the test that would have caught the second `build_paper` bug: drawing the shade rings
    ONTO the paper replaces the pixels instead of blending into them, which paints OPAQUE bands --
    and an opaque band is exactly what shows up as a discontinuity, two flat populations of
    brightness with a huge gap between them, instead of a continuum. The low-frequency blotching
    legitimately wobbles by a few levels, so this asserts the SHAPE of the distribution rather
    than a strictly monotone walk.
    """
    sheet = _sheet()
    levels = [_column_brightness(sheet.paper, x) for x in range(1, sheet.width // 2, 2)]
    distinct = sorted({round(v) for v in levels})

    assert len(distinct) >= 10, f"a gradient has many steps, bands have few: {distinct}"
    gaps = [b - a for a, b in zip(distinct, distinct[1:])]
    assert max(gaps) < 20, \
        f"a gap this wide means flat bands, not a ramp: {distinct} (max gap {max(gaps)})"
    edge = sum(levels[:6]) / 6
    middle = sum(levels[-6:]) / 6
    assert middle > edge + 15, f"edge {edge:.1f} should be clearly darker than middle {middle:.1f}"


def test_a_stronger_vignette_darkens_the_edge_more():
    light = _sheet(vignette=0.3)
    heavy = _sheet(vignette=2.5)
    assert _column_brightness(heavy.paper, 2) < _column_brightness(light.paper, 2)


def test_paper_age_zero_still_gives_a_usable_sheet():
    sheet = _sheet(paper_age=0.0)
    assert sheet.paper.get_size() == (240, 400)
    assert sheet.canvas is not None


def test_every_texture_colour_follows_the_configured_tone():
    """
    Darkening the tone must darken the blotches and the vignette too.

    This is the difference between a parameter and a lie: if the blotches were hardcoded, the
    panel's `paper_tone` would change the base fill and leave the texture in the old colour.
    """
    pale = _sheet(paper_tone=(240, 230, 210))
    dark = _sheet(paper_tone=(150, 120, 80))
    assert sum(dark.tone(-0.3)) < sum(pale.tone(-0.3))
    assert sum(dark.tone(-0.48)) < sum(pale.tone(-0.48))
    assert sum(dark.tone(0.2)) < sum(pale.tone(0.2))
    # and the built sheet really is darker overall
    assert sum(pygame.image.tostring(dark.paper, "RGB")) < \
        sum(pygame.image.tostring(pale.paper, "RGB"))


def test_the_same_seed_reproduces_the_same_sheet():
    """A map worth keeping has to be reproducible from its seed."""
    a = _sheet(seed=1234)
    b = _sheet(seed=1234)
    c = _sheet(seed=4321)
    assert pygame.image.tostring(a.paper, "RGB") == pygame.image.tostring(b.paper, "RGB")
    assert pygame.image.tostring(a.paper, "RGB") != pygame.image.tostring(c.paper, "RGB")


# ---------------------------------------------------------------- the ink layer and the flush

def test_the_ink_layer_is_supersampled():
    sheet = _sheet(supersample=2)
    ink = sheet.ensure_ink()
    assert ink.get_size() == (480, 800)
    assert sheet.ink_rect(pygame.Rect(10, 10, 20, 20)) == pygame.Rect(20, 20, 40, 40)


def test_only_the_dirty_rect_is_composited_onto_the_canvas():
    """
    CONTAINMENT, not an offset: after flushing one small rect, ink is inside it and nowhere else.

    A region the stroke never went near must be byte-identical to the untouched paper -- that is
    what "only the dirty rect" means, and it is the reason a supersampled pen is affordable.
    """
    sheet = _sheet()
    untouched = pygame.image.tostring(sheet.canvas, "RGB")

    ink = sheet.ensure_ink()
    pygame.draw.rect(ink, sheet.ink_colour(), sheet.ink_rect(pygame.Rect(40, 60, 30, 30)))
    sheet.mark_dirty(pygame.Rect(40, 60, 30, 30))
    sheet.flush()

    inside = pygame.Rect(45, 65, 20, 20)
    outside = pygame.Rect(150, 250, 40, 40)
    assert sheet.composites == 1
    assert sheet.canvas.get_at(inside.center)[:3] != sheet.paper.get_at(inside.center)[:3], \
        "the stroke should have landed inside the dirty rect"
    assert _region(sheet.canvas, outside) == _region(sheet.paper, outside), \
        "a region outside the dirty rect must be untouched"
    assert _region(sheet.canvas, outside) == _region_bytes(untouched, outside, sheet.width), \
        "and unchanged from before the flush"


def test_a_finished_sheet_does_no_work():
    """The idle guard: with nothing dirty there is no composite at all, frame after frame."""
    sheet = _sheet()
    sheet.ensure_ink()
    for _ in range(5):
        sheet.flush()
    assert sheet.composites == 0


def test_supersample_one_still_composites():
    sheet = _sheet(supersample=1)
    assert sheet.ensure_ink().get_size() == (240, 400)
    ink = sheet.ensure_ink()
    pygame.draw.rect(ink, sheet.ink_colour(), (10, 10, 12, 12))
    sheet.mark_dirty(pygame.Rect(10, 10, 12, 12))
    sheet.flush()
    assert sheet.composites == 1
    assert sheet.canvas.get_at((15, 15))[:3] != sheet.paper.get_at((15, 15))[:3]


def test_an_empty_dirty_rect_is_ignored():
    sheet = _sheet()
    sheet.mark_dirty(pygame.Rect(-50, -50, 10, 10))
    assert sheet.pending_dirty() is None
    sheet.flush()
    assert sheet.composites == 0


def test_clear_ink_starts_the_sheet_again():
    sheet = _sheet()
    ink = sheet.ensure_ink()
    pygame.draw.rect(ink, sheet.ink_colour(), sheet.ink_rect(pygame.Rect(20, 20, 40, 40)))
    sheet.mark_dirty(pygame.Rect(20, 20, 40, 40))
    sheet.flush()
    assert sheet.canvas.get_at((40, 40))[:3] != sheet.paper.get_at((40, 40))[:3]

    sheet.clear_ink()
    assert pygame.image.tostring(sheet.canvas, "RGB") == \
        pygame.image.tostring(sheet.paper, "RGB"), "a wiped sheet is just paper again"


def test_release_drops_the_surfaces():
    sheet = _sheet()
    sheet.ensure_ink()
    sheet.release()
    assert sheet.paper is None and sheet.canvas is None and sheet.ink is None


# ---------------------------------------------------------------- the reveal

def test_an_empty_plan_is_finished_immediately():
    reveal = Reveal()
    assert reveal.total == 0 and reveal.done and reveal.progress == 1.0
    assert reveal.advance(0.1, 60.0, lambda item: None) == 0


def test_the_reveal_paces_a_plan_over_the_configured_time():
    """100 strokes over 10 s at 1 s per call: about ten a call, and 100 when it is over."""
    drawn = []
    reveal = Reveal(range(100))
    for _ in range(5):
        reveal.advance(1.0, 10.0, drawn.append)
    assert 45 <= len(drawn) <= 55, len(drawn)
    for _ in range(5):
        reveal.advance(1.0, 10.0, drawn.append)
    assert len(drawn) == 100
    assert reveal.done and reveal.progress == 1.0


def test_a_short_frame_carries_instead_of_losing_its_share():
    """A frame smaller than one stroke's worth must not drop that time on the floor."""
    drawn = []
    reveal = Reveal(range(10))
    # 10 strokes over 1 s = 10 per second; 0.05 s is half a stroke
    assert reveal.advance(0.05, 1.0, drawn.append) == 0
    assert drawn == []
    assert reveal.advance(0.05, 1.0, drawn.append) == 1
    assert drawn == [0]


def test_a_zero_duration_draws_everything_at_once():
    drawn = []
    reveal = Reveal(range(500))
    assert reveal.advance(0.016, 0.0, drawn.append) == 500
    assert len(drawn) == 500 and reveal.done


def test_the_reveal_never_runs_past_the_end():
    drawn = []
    reveal = Reveal(range(5))
    reveal.advance(1000.0, 1.0, drawn.append)
    assert drawn == [0, 1, 2, 3, 4]
    assert reveal.advance(1000.0, 1.0, drawn.append) == 0
    assert len(drawn) == 5


def test_a_new_plan_puts_the_pen_back_at_the_start():
    reveal = Reveal(range(3))
    reveal.advance(10.0, 1.0, lambda item: None)
    assert reveal.done
    reveal.set_plan(range(2))
    assert reveal.index == 0 and not reveal.done and reveal.total == 2


# ---------------------------------------------------------------- the mode

def _mode(**config):
    cfg = build_merged_config(_spec(), config, None)
    return load_entrypoint(_spec()["entrypoint"])(cfg)


def _spec():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    return registry["types"]["inkmap"]


def test_the_mode_constructs_from_a_merged_config():
    mode = _mode()
    assert mode.paper_tone == (232, 217, 184)
    assert mode.supersample == 2


def test_enter_builds_a_sheet_and_queues_the_coastline():
    mode = _mode(seed=99)
    manager = FakeManager()
    mode.enter(manager)
    try:
        assert mode.sheet is not None
        assert mode.sheet.paper.get_size() == (240, 400)
        assert mode.sheet.ink.get_size() == (480, 800)
        assert mode.status()["seed"] == 99
        # phase 2: the pour has happened, outlines were traced, and strokes are queued but NOT yet
        # drawn -- the pen has not touched the paper until the reveal cursor moves
        assert mode.status()["masses"] >= 1
        assert mode.status()["planned"] > 0
        assert mode.status()["drawn"] == 0
        assert mode.status()["land_coverage"] is not None
    finally:
        mode.exit()


def test_render_shows_the_paper_rather_than_a_black_screen():
    mode = _mode(seed=5, paper_tone=[233, 220, 190])
    manager = FakeManager()
    mode.enter(manager)
    try:
        manager.screen.fill((0, 0, 0))
        mode.render(manager.screen)
        centre = manager.screen.get_at((120, 200))[:3]
        assert centre != (0, 0, 0), "the whole point of phase 1 is that the panel is not blank"
        # it is a parchment in the configured family, not an arbitrary colour
        assert abs(centre[0] - 233) < 20 and abs(centre[2] - 190) < 20, centre
    finally:
        mode.exit()


def test_the_redraw_key_pours_a_new_sheet():
    mode = _mode(seed=0)
    manager = FakeManager()
    mode.enter(manager)
    try:
        first_seed = mode.seed
        mode.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        assert mode.seed != first_seed, "with no seed pinned, R/space is a new sheet"
        assert mode.status()["planned"] > 0, "the new sheet needs its own coastline queued"
        assert mode.status()["drawn"] == 0, "and the pen starts at the beginning of it"
    finally:
        mode.exit()


def test_a_pinned_seed_pours_the_same_sheet_again():
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        before = pygame.image.tostring(mode.sheet.paper, "RGB")
        mode.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        assert mode.seed == 4242
        assert pygame.image.tostring(mode.sheet.paper, "RGB") == before
    finally:
        mode.exit()


def test_update_paces_at_reveal_fps_and_survives_an_empty_plan():
    """
    The drawing runs at `reveal_fps`, not at the controller's frame rate -- a hand-drawn sheet looks
    no better at 60 fps and this leaves the frame loop to the rest of the app. Two seconds of 60 fps
    frames must therefore be about two seconds of pen travel, not 120 strokes.
    """
    mode = _mode(seed=3, reveal_fps=20, draw_minutes=5)
    manager = FakeManager()
    mode.enter(manager)
    try:
        for _ in range(120):
            mode.update(1 / 60.0)
        planned = mode.status()["planned"]
        drawn = mode.status()["drawn"]
        expected = planned * 2.0 / (5 * 60)
        assert 0 < drawn <= max(2, int(expected) + 2), (drawn, expected, planned)
        manager.screen.fill((0, 0, 0))
        mode.render(manager.screen)
        assert manager.screen.get_at((120, 200))[:3] != (0, 0, 0)
    finally:
        mode.exit()


def test_an_empty_plan_is_finished_immediately_and_draws_nothing():
    mode = _mode(seed=3)
    manager = FakeManager()
    mode.enter(manager)
    try:
        mode.reveal.set_plan([])
        for _ in range(120):
            mode.update(1 / 60.0)
        assert mode.status()["drawn"] == 0
        assert mode.status()["finished"] is True
    finally:
        mode.exit()


def test_exit_releases_the_sheet():
    mode = _mode(seed=11)
    manager = FakeManager()
    mode.enter(manager)
    mode.exit()
    assert mode.sheet is None
    # and rendering after exit must not raise: the controller calls render() once more after a
    # mode switch in some paths, and a crash there lands in the manager's except branch
    manager.screen.fill((0, 0, 0))
    mode.render(manager.screen)


def test_status_is_json_safe():
    import json
    mode = _mode(seed=77)
    manager = FakeManager()
    mode.enter(manager)
    try:
        json.dumps(mode.status())
    finally:
        mode.exit()


# ---------------------------------------------------------------- the coastline (phase 2)

def _draw_everything(mode):
    """Run the reveal to its end without pretending to be a frame loop."""
    total = mode.reveal.total
    while mode.reveal.index < total:
        # total_seconds = total makes the cursor advance exactly one item per second of dt
        mode.reveal.advance(1.0, float(total), mode._draw_one)
    mode.sheet.flush()


def _ink_pixels(surface, ink=(43, 33, 26), tolerance=40):
    """How much of the surface is ink rather than paper. Samples every other pixel."""
    count = 0
    for x in range(0, surface.get_width(), 2):
        for y in range(0, surface.get_height(), 2):
            colour = surface.get_at((x, y))
            if (abs(colour[0] - ink[0]) < tolerance and abs(colour[1] - ink[1]) < tolerance
                    and abs(colour[2] - ink[2]) < tolerance):
                count += 1
    return count


def test_the_pen_actually_marks_the_paper():
    """
    Queueing a plan is not drawing it. The parchment is a light warm tone and the ink is nearly
    black, so counting near-black pixels is a direct measure of whether the strokes reached the
    canvas -- which they only do through the dirty-rect composite.
    """
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        assert _ink_pixels(mode.sheet.canvas) == 0, "nothing is drawn until the cursor moves"
        _draw_everything(mode)
        assert _ink_pixels(mode.sheet.canvas) > 20, "the coastline should be visible on the paper"
        assert mode.status()["finished"] is True
    finally:
        mode.exit()


def test_the_pen_travels_so_the_sheet_is_drawn_a_piece_at_a_time():
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        marks = []
        total = mode.reveal.total
        for stop in (0, total // 4, total // 2, total):
            while mode.reveal.index < stop:
                mode.reveal.advance(1.0, float(total), mode._draw_one)
            mode.sheet.flush()
            marks.append(_ink_pixels(mode.sheet.canvas))
        assert marks[0] == 0
        assert marks[0] < marks[1] < marks[2] < marks[3], marks
    finally:
        mode.exit()


def test_a_seed_reproduces_the_whole_sheet_not_just_the_paper():
    """
    The paper was already reproducible in phase 1. What has to hold now is that the POUR, the traced
    outlines and therefore the finished drawing all come from the same seed -- otherwise a map worth
    keeping could not be got back.
    """
    def render(seed):
        mode = _mode(seed=seed)
        manager = FakeManager()
        mode.enter(manager)
        try:
            _draw_everything(mode)
            status = mode.status()
            return (pygame.image.tostring(mode.sheet.canvas, "RGB"),
                    status["masses"], status["planned"])
        finally:
            mode.exit()

    first, second, other = render(31337), render(31337), render(31338)
    assert first == second, "the same seed must draw the same map"
    assert first[0] != other[0], "a different seed must not draw the same map"


def test_the_land_dial_moves_the_sheet_between_land_and_sea():
    low = _mode(seed=4242, land_coverage=0.22)
    high = _mode(seed=4242, land_coverage=0.80)
    manager = FakeManager()
    for mode in (low, high):
        mode.enter(manager)
    try:
        assert low.status()["land_coverage"] < high.status()["land_coverage"]
    finally:
        for mode in (low, high):
            mode.exit()


def test_each_pass_of_the_plan_is_drawn_by_one_hand(monkeypatch):
    """
    Every outline is drawn as many short runs. The hand's wander is an AR(1) walk, so a fresh hand
    per run would restart the drift at every join and leave a kink there -- which is why a pass
    shares one hand. Phase 3 makes that "one hand PER PASS" rather than one for the whole plan: the
    sea is its own pass with its own hand, seeded off the sheet's seed, so the sea's wander does not
    depend on how many strokes the coast happened to need. Two hands, not one, and not one per stroke.
    """
    seen = []
    real_stroke = inkdraw.stroke

    def recorder(surface, points, width, hand, **kw):
        seen.append((id(hand), bool(kw.get("taper", False))))
        return real_stroke(surface, points, width, hand, **kw)

    monkeypatch.setattr(inkdraw, "stroke", recorder)
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        _draw_everything(mode)
        status = mode.status()
        hands = {hand_id for hand_id, _taper in seen}
        assert len(hands) == 2, f"one hand per pass: coast and sea, got {len(hands)}"
        assert len(seen) >= status["planned"], "items may make several strokes each"
        tapers = sum(1 for _hand_id, taper in seen if taper)
        assert 0 < tapers <= 2 * status["masses"], (tapers, status["masses"])
    finally:
        mode.exit()


def test_an_outline_leaving_the_sheet_is_not_closed_with_a_straight_line():
    """
    The phase-2 acceptance criterion, checked where it matters: on the outlines the mode actually
    hands to the pen. A closed outline may repeat its first point; an outline that runs off the edge
    may not.
    """
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        masses = mode.masses
        assert masses, "the sheet should have at least one land mass"
        for points, closed, _area in masses:
            if closed:
                assert points[0] == points[-1]
            else:
                assert points[0] != points[-1]
    finally:
        mode.exit()


def test_status_reports_what_the_pour_did():
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        status = mode.status()
        assert status["grains"] > 0
        assert status["masses"] >= 1
        assert 0.0 < status["land_coverage"] < 1.0
    finally:
        mode.exit()


# ---------------------------------------------------------------- the sea (phase 3)

def test_the_plan_is_the_videos_order_coast_then_sea():
    """
    The plan exists so the drawing follows the tutorial's sequence. Phase 3 adds the second pass, so
    the coast strokes must all come before any sea stroke -- the sea is drawn around a coastline that
    is already there.
    """
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        status = mode.status()
        assert status["passes"] == ["coast", "sea"], status["passes"]
        assert status["coast_strokes"] > 0
        assert status["sea_strokes"] > 0
        assert status["coast_strokes"] + status["sea_strokes"] == status["planned"]
    finally:
        mode.exit()


def test_no_rings_and_no_lakes_means_no_sea_is_queued():
    """
    A lake is its own water pass, not a ring: ask for no rings and the lakes are still drawn, which is
    correct -- and means the "no sea" case has to switch both off.
    """
    mode = _mode(seed=4242, water_rings=0, lake_count=0)
    manager = FakeManager()
    mode.enter(manager)
    try:
        status = mode.status()
        assert status["sea_strokes"] == 0
        assert status["coast_strokes"] > 0
        assert status["passes"] == ["coast"]
    finally:
        mode.exit()


def test_lakes_are_drawn_even_with_no_rings():
    mode = _mode(seed=4242, water_rings=0, lake_count=3)
    manager = FakeManager()
    mode.enter(manager)
    try:
        status = mode.status()
        assert status["coast_strokes"] > 0
        assert status["sea_strokes"] > 0, "the lakes are a water pass of their own"
        assert status["passes"] == ["coast", "sea"]
    finally:
        mode.exit()


def test_more_rings_queue_more_sea():
    counts = []
    for rings in (1, 4):
        mode = _mode(seed=4242, water_rings=rings)
        manager = FakeManager()
        mode.enter(manager)
        try:
            counts.append(mode.status()["sea_strokes"])
        finally:
            mode.exit()
    assert counts[0] > 0 and counts[1] > counts[0]


def test_no_lakes_asked_for_means_no_lakes_queued():
    few = _mode(seed=4242, lake_count=0, water_rings=0)
    many = _mode(seed=4242, lake_count=4, water_rings=0)
    manager = FakeManager()
    results = []
    for mode in (few, many):
        mode.enter(manager)
        results.append(mode.status()["sea_strokes"])
        mode.exit()
    # with no rings, every sea stroke is a lake stroke
    assert results[0] == 0
    assert results[1] > 0


def test_the_sea_style_changes_what_is_drawn():
    """
    The design's acceptance for this phase: changing `water_style` changes the drawn sea. The panel
    reaches this by re-applying the config, which re-enters the mode -- so what has to hold is that
    the same sheet, drawn with two styles, produces two different pictures.
    """
    pictures = {}
    for style in ("hash", "stipple"):
        mode = _mode(seed=4242, water_style=style)
        manager = FakeManager()
        mode.enter(manager)
        try:
            _draw_everything(mode)
            pictures[style] = (pygame.image.tostring(mode.sheet.canvas, "RGB"),
                               mode.status()["water_style"])
        finally:
            mode.exit()
    assert pictures["hash"][1] == "hash" and pictures["stipple"][1] == "stipple"
    assert pictures["hash"][0] != pictures["stipple"][0], "the two styles must not draw the same sea"


def test_an_unknown_sea_style_falls_back_instead_of_losing_the_sea():
    mode = _mode(seed=4242, water_style="nonsense")
    manager = FakeManager()
    mode.enter(manager)
    try:
        status = mode.status()
        assert status["water_style"] == "hash"
        assert status["sea_strokes"] > 0
    finally:
        mode.exit()


def test_every_sea_style_draws_something():
    for style in ("hash", "squiggle", "stipple", "wave"):
        mode = _mode(seed=4242, water_style=style)
        manager = FakeManager()
        mode.enter(manager)
        try:
            assert mode.status()["sea_strokes"] > 0, style
            _draw_everything(mode)
            assert _ink_pixels(mode.sheet.canvas) > 20, style
        finally:
            mode.exit()


def test_the_sea_is_drawn_after_the_coast_on_the_canvas():
    """Ink the coast alone, then the whole sheet: the picture must gain the sea and keep the coast."""
    mode = _mode(seed=4242)
    manager = FakeManager()
    mode.enter(manager)
    try:
        total = mode.reveal.total
        coast_only = mode.status()["coast_strokes"]
        while mode.reveal.index < coast_only:
            mode.reveal.advance(1.0, float(total), mode._draw_one)
        mode.sheet.flush()
        after_coast = _ink_pixels(mode.sheet.canvas)
        while mode.reveal.index < total:
            mode.reveal.advance(1.0, float(total), mode._draw_one)
        mode.sheet.flush()
        after_sea = _ink_pixels(mode.sheet.canvas)
        assert after_coast > 0
        assert after_sea > after_coast * 1.5, (after_coast, after_sea)
    finally:
        mode.exit()


# ---------------------------------------------------------------- the registry entry

def test_the_registry_entry_is_internally_consistent():
    spec = _spec()
    assert spec["entrypoint"] == "modes.ink_map_mode:InkMapMode"
    assert spec["required"] == []
    optional = set(spec["optional"])
    params = set(spec["params"])
    assert optional == params, {
        "declared but no schema entry": sorted(optional - params),
        "schema entry but not declared": sorted(params - optional),
    }
    for key, entry in spec["params"].items():
        assert entry.get("widget") in (
            "switch", "number", "text", "choice", "path", "color", "range",
            "stringlist", "palette", "json", "secret"), key
        assert entry.get("group") in ("appearance", "layout", "behaviour", "data"), key
        assert "default" in entry, f"{key} has no recorded default"


def test_every_control_says_which_phase_draws_with_it():
    """
    A knob that does nothing and does not say so is a trap: the user sets it, sees no change,
    and concludes the mode is broken. Every field's help must name its phase.
    """
    spec = _spec()
    silent = []
    for key, entry in spec["params"].items():
        help_text = entry.get("help", "")
        if "phase" not in help_text.lower():
            silent.append(key)
    assert not silent, f"these controls do not say when they take effect: {silent}"


def test_the_new_type_passes_the_apps_own_validators():
    from core.validation import errors, validate_profile, validate_registry, warnings
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    assert not errors(validate_registry(registry, check_imports=False))
    cfg = {"type": "inkmap", "seed": 42, "paper_age": 0.5}
    issues = validate_profile({"0": cfg}, registry["types"], base_dir=BASE_DIR)
    assert not errors(issues), [i.render() for i in errors(issues)]
    assert not warnings(issues), [i.render() for i in warnings(issues)]


def test_the_parameter_audit_finds_no_hardcoded_appearance_value_in_the_new_codes():
    """
    Phase 1's acceptance, in the design's own words: the audit must be clean for this type.

    A hardcoded colour, alpha or font size here would be a value the panel cannot reach. Counts
    and proportions that derive the paper's own texture are implementation detail, not knobs --
    the auditor already classifies those as geometry and keeps them out of the review list.
    """
    from core.param_audit import audit_source, group_candidates

    offenders = []
    for rel, type_key in (("modes/ink_map_mode.py", "inkmap"), ("core/inksheet.py", "")):
        with open(os.path.join(BASE_DIR, rel), "r", encoding="utf-8") as fh:
            result = audit_source(fh.read(), mode=os.path.basename(rel), type_key=type_key)
        for cand in result.candidates:
            if cand.status == "operative" and cand.kind in ("colour", "alpha", "font_size"):
                offenders.append(f"{rel}:{cand.line} {cand.attr} = {cand.literal}")
        # and nothing routed to the review list that is not a real knob
        for group in group_candidates(result, used_only=False):
            if group["kind"] in ("colour", "alpha"):
                offenders.append(f"{rel}:{group['attr']} ({group['kind']})")
    assert not offenders, offenders


# ---------------------------------------------------------------- helpers

def _column_brightness(surface, x, half_band=12):
    """Mean R+G+B down a short vertical band, so the fibre speckle averages out."""
    mid = surface.get_height() // 2
    total = 0
    for y in range(mid - half_band, mid + half_band):
        r, g, b = surface.get_at((x, y))[:3]
        total += r + g + b
    return total / (2 * half_band)


def _block_spread(surface, margin=120, step=20, block=8):
    """
    The spread of 8x8 block averages: how much the sheet varies at a LOW frequency.

    The margin keeps the sample clear of the vignette (10% of the short side), so this measures
    the motttling and not the edge shading -- otherwise a plain sheet scores 4.7 and the
    comparison means nothing.
    """
    averages = []
    for bx in range(margin, surface.get_width() - margin, step):
        for by in range(margin, surface.get_height() - margin, step):
            total = 0
            count = 0
            for x in range(bx, min(bx + block, surface.get_width())):
                for y in range(by, min(by + block, surface.get_height())):
                    r, g, b = surface.get_at((x, y))[:3]
                    total += r
                    count += 1
            if count:
                averages.append(total / count)
    return (max(averages) - min(averages)) if averages else 0.0


def _region(surface, rect):
    return _region_bytes(pygame.image.tostring(surface, "RGB"), rect, surface.get_width())


def _region_bytes(data, rect, width):
    rows = []
    for y in range(rect.top, rect.bottom):
        start = (y * width + rect.left) * 3
        rows.append(data[start:start + rect.width * 3])
    return b"".join(rows)


def test_the_live_controls_are_exactly_the_ones_the_mode_says_are_live():
    """
    Both directions at once. If the mode honours a control without listing it, nobody notices it
    working; if it lists one whose help still says "not drawn yet", the panel is lying to the user
    about what the dial will do.
    """
    from modes.ink_map_mode import LIVE_PARAMS

    spec = _spec()
    live = set(LIVE_PARAMS)
    unknown = live - set(spec["params"])
    assert not unknown, f"listed as live but not a declared parameter: {sorted(unknown)}"
    assert live, "a mode that draws has to honour something"

    wrong = []
    for key, entry in spec["params"].items():
        says_live = "Active now" in entry.get("help", "")
        if says_live != (key in live):
            wrong.append((key, says_live, key in live))
    assert not wrong, f"(key, help says live, mode says live) mismatches: {wrong}"
