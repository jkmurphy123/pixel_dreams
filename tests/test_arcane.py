# tests/test_arcane.py
#
# Arcane control family (designs/ARCANE_LAB_DESIGN.md §5, §10).
#
# These tests exist because the P0 spike (designs/arcane_proto/arcane_spike.py) found three
# bugs that a "does it draw?" test would have missed:
#
#   * a glow cache keyed by an exact colour was a cache miss per particle (493 ms/frame for
#     120 embers) — so the steady-state rule below asserts that drawing allocates NOTHING;
#   * an orb body blitted additively clipped to a white disc — so every type is checked for
#     drawing INSIDE its own rect, which is also the alignment editor's contract;
#   * a halo leaking past the rect would make the alignment box a lie — same containment test.
#
# Run headless:
#   SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/test_arcane.py -q

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from controlpanel.controls import (CONTROL_CLASSES, COLOUR_KEYS,  # noqa: E402
                                   ControlContext, make_control)
from controlpanel.controls import arcane  # noqa: E402
from controlpanel.layout import PlacedControl, layout_from_data  # noqa: E402
from controlpanel.registry import CONTROL_TYPES  # noqa: E402

#: The arcane types that exist so far. Phases 2 and 3 append to this tuple.
ARCANE_TYPES = ("candle_flame", "ember_field", "floating_orb",
                "rune_circle", "rune_line", "smoke_wisp",
                "lightning_arc", "potion_bubbles", "drifting_runes",
                "glowing_eyes")

BLACK = (0, 0, 0)


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    pygame.init()
    pygame.font.init()
    yield
    pygame.quit()


def _ctx(seed=7):
    return ControlContext(seed=seed, accent_rgb=(255, 176, 64),
                          trace_rgb=(80, 255, 120), lamp_rgb=(255, 60, 50))


def _placed(ctype, rect, raw=None):
    x, y, w, h = rect
    spec = dict(raw or {})
    spec.setdefault("type", ctype)
    return PlacedControl(ctype, CONTROL_TYPES[ctype], None, (x, y), (w, h), spec, rect_px=rect)


def _build(ctype, rect=(200, 200, 180, 180), raw=None, seed=7):
    control = make_control(_placed(ctype, rect, raw), _ctx(seed))
    assert control is not None, f"{ctype} is in the catalogue but make_control returned None"
    return control


def _extent(control, surface):
    """Where the control actually draws: alone on black, the background colorkeyed away."""
    surface.fill(BLACK)
    surface.set_colorkey(BLACK)
    control.draw_overlay(surface)
    return surface.get_bounding_rect()


# ---------------------------------------------------------------- registration


def test_every_arcane_type_is_registered_in_all_three_tables():
    """
    A type is only fully wired when it is in the type table, has a class and has a colour row:
    the panel's Add dialog reads the class catalogue, its colour pickers read COLOUR_KEYS, and the
    layout loader sizes a control from the sprite the type table names.
    """
    for ctype in ARCANE_TYPES:
        assert ctype in CONTROL_TYPES, f"{ctype} missing from CONTROL_TYPES"
        assert ctype in CONTROL_CLASSES, f"{ctype} missing from CONTROL_CLASSES"
        assert ctype in COLOUR_KEYS, f"{ctype} missing from COLOUR_KEYS"
        assert CONTROL_TYPES[ctype] in arcane_glossary(), \
            f"{ctype}'s default sprite is not in sprite_defs.json"


def arcane_glossary():
    from controlpanel.skin import load_sprite_defs
    return load_sprite_defs()["sprites"]


def test_each_arcane_type_offers_only_colours_it_reads():
    """The table may not offer a dead knob; the panel's picker is built from it."""
    for ctype in ARCANE_TYPES:
        keys = set(COLOUR_KEYS[ctype])
        assert "color" in keys, f"{ctype}: the generic colour key must be offered"
        for key in keys - {"color"}:
            assert key.endswith("_rgb"), f"{ctype}: {key} is not a colour key name"


# ---------------------------------------------------------------- drawing


def test_each_arcane_type_draws_on_its_first_frame_and_stays_inside_its_box():
    """
    Frame 0 matters: the mode can render before the first update(), and the alignment page shows
    the overlay you are about to move. Containment matters more: a halo outside the rect makes the
    editor's box (and its marker) describe something the wall is not doing.
    """
    surface = pygame.Surface((900, 900))
    rect = (200, 200, 180, 180)
    box = pygame.Rect(*rect)
    for ctype in ARCANE_TYPES:
        control = _build(ctype, rect)
        extent = _extent(control, surface)
        assert extent.width > 0 and extent.height > 0, f"{ctype} drew nothing on frame 0"
        assert box.contains(extent), f"{ctype} drew outside its rect: {extent} not inside {box}"


def test_each_arcane_type_still_draws_and_stays_inside_after_a_minute():
    surface = pygame.Surface((900, 900))
    rect = (200, 200, 180, 180)
    box = pygame.Rect(*rect)
    for ctype in ARCANE_TYPES:
        control = _build(ctype, rect)
        for _ in range(60 * 60):                    # one simulated minute at 60 fps
            control.update(1 / 60)
        extent = _extent(control, surface)
        assert extent.width > 0 and extent.height > 0, f"{ctype} stopped drawing"
        assert box.contains(extent), f"{ctype} drifted outside its rect: {extent} vs {box}"


def test_a_moved_arcane_control_draws_only_in_its_new_box():
    """The catalogue-wide version of this lives in test_layout_align; this is the per-type read."""
    surface = pygame.Surface((1200, 900))
    old_rect, new_rect = (100, 100, 160, 160), (800, 600, 160, 160)
    for ctype in ARCANE_TYPES:
        control = _build(ctype, old_rect)
        for _ in range(20):
            control.update(0.3)
        control.set_rect(new_rect)
        extent = _extent(control, surface)
        assert pygame.Rect(*new_rect).contains(extent), f"{ctype} after a move: {extent}"
        assert not extent.colliderect(pygame.Rect(*old_rect)), f"{ctype} still drawing in the old box"


def test_a_pinned_seed_reproduces_the_frame():
    """The mode's `seed` must reproduce a screenshot, or judging a change becomes guesswork."""
    surface = pygame.Surface((640, 480))
    for ctype in ARCANE_TYPES:
        a, b = _build(ctype, (100, 100, 220, 220), seed=11), _build(ctype, (100, 100, 220, 220), seed=11)
        for _ in range(90):
            a.update(1 / 60)
            b.update(1 / 60)
        surface.fill(BLACK)
        a.draw_overlay(surface)
        first = pygame.image.tostring(surface, "RGB")
        surface.fill(BLACK)
        b.draw_overlay(surface)
        assert pygame.image.tostring(surface, "RGB") == first, f"{ctype} is not seed-reproducible"


def test_the_cloud_of_embers_and_orbs_leave_nothing_on_their_neighbours():
    """A clipped control must restore the surface's clip, or everything drawn after it is cut."""
    surface = pygame.Surface((400, 300))
    control = _build("ember_field", (50, 50, 120, 120))
    control.update(1 / 60)
    control.draw_overlay(surface)
    assert surface.get_clip() == pygame.Rect(0, 0, 400, 300)


# ---------------------------------------------------------------- cost


def test_drawing_allocates_nothing_once_the_caches_are_warm(monkeypatch):
    """
    The P0 bug, as a test: a glow cache keyed by an exact per-particle colour rebuilt a gradient
    per mote and cost 493 ms/frame. Steady state must allocate ZERO surfaces — if a class starts
    building one per frame, this fails long before the wall drops frames.
    """
    built = []

    class _Counting(pygame.Surface):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(args)

    surface = pygame.Surface((1080, 1920))
    controls = [_build(ctype, (60, 60, 300, 300)) for ctype in ARCANE_TYPES]
    for _ in range(600):        # warm every bucket: the orb breathes through a ~7 s cycle
        for control in controls:
            control.update(1 / 60)
            control.draw_overlay(surface)

    monkeypatch.setattr(pygame, "Surface", _Counting)
    del built[:]
    for _ in range(600):
        for control in controls:
            control.update(1 / 60)
            control.draw_overlay(surface)
    assert built == [], f"{len(built)} surfaces built in 600 frames: the caches are not settling"


# ---------------------------------------------------------------- junk specs


def test_junk_numbers_fall_back_instead_of_raising():
    """
    These values can come from the panel's own form. An exception while a control is BUILT leaves
    the mode with no compositor at all — a black wall, not one wrong-looking overlay.
    """
    junk = {"count": "lots", "glow": "big", "flicker": None, "lean": [1, 2],
            "rise": "fast", "sway": -9, "mote": 0, "drift": "far", "pulse": -1,
            "rings": "many", "glyphs": 0, "radius": "wide", "spin": "fast",
            "orient": 7, "hold": None, "wisps": -3, "speed": "quick", "fade": 9,
            "strike": "often", "branches": -2, "jag": None, "anchors": "corners",
            "decay": 0, "bubbles": "lots", "rise": -1, "surface": 4, "wobble": None,
            "sway": "wide", "fade": 9, "pairs": "many", "eye": 0, "gap": "wide",
            "slant": None, "period": -4, "hold": 9, "blink": "often"}
    surface = pygame.Surface((400, 400))
    for ctype in ARCANE_TYPES:
        control = _build(ctype, (100, 100, 160, 160), raw=dict(junk))
        control.update(1 / 60)
        control.draw_overlay(surface)          # must not raise


def test_extreme_counts_are_clamped_rather_than_honoured():
    """A layout author typing count: 100000 must not build a hundred thousand particles."""
    for ctype, ceiling in (("candle_flame", 9), ("ember_field", 400), ("floating_orb", 5)):
        control = _build(ctype, (0, 0, 300, 300), raw={"count": 100000})
        assert control is not None
        count = control.pool.n if ctype == "ember_field" else control.count
        assert count <= ceiling, f"{ctype} honoured count={count}"


# ---------------------------------------------------------------- a layout that uses them


def test_a_freeform_layout_of_arcane_types_loads():
    """
    The real path: a layout document, the loader, and the mode's control factory. This is the
    closest thing to "the wall builds it" that runs without a display.
    """
    doc = {
        "name": "arcane_smoke_test",
        "mode": "freeform",
        "design_resolution": [1080, 1920],
        "controls": [
            {"type": "ember_field", "at": [0, 0], "size": [1080, 1920], "count": 40},
            {"type": "candle_flame", "at": [100, 300], "size": [240, 140], "count": 3},
            {"type": "floating_orb", "at": [700, 400], "size": [200, 200]},
        ],
    }
    layout = layout_from_data(doc, name="arcane_smoke_test")
    assert layout.mode == "freeform"
    ctx = _ctx()
    controls = [make_control(placed, ctx) for placed in layout.controls]
    assert all(c is not None for c in controls)
    built = [c for c in controls if c is not None]
    surface = pygame.Surface((1080, 1920))
    for _ in range(10):
        for control in built:
            control.update(1 / 60)
            control.draw_overlay(surface)
