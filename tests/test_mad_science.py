# tests/test_mad_science.py
#
# Procedural freeform controls for the Mad Scientist Control Panel.

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from controlpanel.controls import (CONTROL_CLASSES, COLOUR_KEYS, ControlContext,  # noqa: E402
                                   make_control)
from controlpanel.layout import PlacedControl, load_layout  # noqa: E402
from controlpanel.registry import CONTROL_TYPES  # noqa: E402
from controlpanel.skin import load_sprite_defs  # noqa: E402


MAD_SCIENCE_TYPES = (
    "jacobs_ladder",
    "electric_filament",
    "spark_terminal",
    "mechanical_wheels",
)


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    pygame.init()
    pygame.font.init()
    yield
    pygame.quit()


def test_every_mad_science_type_is_registered_in_the_catalogue():
    """A new type must be usable by the loader, animator, and colour-picker editor."""
    sprites = load_sprite_defs()["sprites"]
    for ctype in MAD_SCIENCE_TYPES:
        assert ctype in CONTROL_TYPES
        assert ctype in CONTROL_CLASSES
        assert ctype in COLOUR_KEYS
        assert CONTROL_TYPES[ctype] in sprites
        assert "color" in COLOUR_KEYS[ctype]


def _build(ctype, rect=(200, 200, 240, 240), raw=None, seed=19):
    x, y, width, height = rect
    spec = {"type": ctype}
    spec.update(raw or {})
    placed = PlacedControl(ctype, CONTROL_TYPES[ctype], None, (x, y),
                           (width, height), spec, rect_px=rect)
    control = make_control(placed, ControlContext(seed=seed))
    assert control is not None
    return control


def _extent(control, surface):
    surface.fill((0, 0, 0))
    surface.set_colorkey((0, 0, 0))
    control.draw_overlay(surface)
    return surface.get_bounding_rect()


def test_every_mad_science_control_draws_on_frame_zero_inside_its_box():
    surface = pygame.Surface((900, 900))
    rect = (200, 200, 240, 240)
    box = pygame.Rect(*rect)
    for ctype in MAD_SCIENCE_TYPES:
        extent = _extent(_build(ctype, rect), surface)
        assert extent.width > 0 and extent.height > 0, f"{ctype} drew nothing on frame zero"
        assert box.contains(extent), f"{ctype} escaped its placement box: {extent}"


def test_mad_science_controls_move_all_drawn_pixels_to_the_new_box():
    surface = pygame.Surface((1200, 900))
    old_rect = (100, 100, 180, 180)
    new_rect = (800, 600, 180, 180)
    for ctype in MAD_SCIENCE_TYPES:
        control = _build(ctype, old_rect)
        for _ in range(10):
            control.update(1 / 30)
        control.set_rect(new_rect)
        extent = _extent(control, surface)
        assert pygame.Rect(*new_rect).contains(extent), f"{ctype} drew outside its new box: {extent}"
        assert not extent.colliderect(pygame.Rect(*old_rect)), f"{ctype} still drew in its old box"


def test_moving_a_ladder_keeps_its_live_bolt_inside_the_new_box():
    ladder = _build("jacobs_ladder", (100, 100, 240, 300))
    ladder.update(0.5)
    ladder.set_rect((700, 400, 240, 300))
    assert ladder._bolt
    assert all(pygame.Rect(700, 400, 240, 300).collidepoint(point) for point in ladder._bolt)


def test_mad_scientist_layout_uses_the_wall_sized_background_and_new_controls():
    layout = load_layout("mad_scientist_lab")
    assert layout.mode == "freeform"
    assert layout.design_resolution == (1080, 1920)
    assert layout.background_image is not None
    assert layout.background_image.endswith("mad_lab_1_wall.png")
    assert {control.type for control in layout.controls}.issuperset(MAD_SCIENCE_TYPES)


def test_mad_science_controls_remain_visible_and_contained_after_a_minute():
    surface = pygame.Surface((900, 900))
    rect = (200, 200, 240, 240)
    box = pygame.Rect(*rect)
    for ctype in MAD_SCIENCE_TYPES:
        control = _build(ctype, rect)
        for _ in range(60 * 60):
            control.update(1 / 60)
        extent = _extent(control, surface)
        assert extent.width > 0 and extent.height > 0, f"{ctype} stopped drawing"
        assert box.contains(extent), f"{ctype} escaped its box after animating: {extent}"


def test_mad_science_controls_allocate_no_surfaces_after_warmup(monkeypatch):
    controls = [_build(ctype, (100, 100, 280, 280)) for ctype in MAD_SCIENCE_TYPES]
    surface = pygame.Surface((720, 720))
    for _ in range(240):
        for control in controls:
            control.update(1 / 60)
            control.draw_overlay(surface)

    built = []
    real_surface = pygame.Surface

    class CountingSurface(real_surface):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(args)

    monkeypatch.setattr(pygame, "Surface", CountingSurface)
    for _ in range(240):
        for control in controls:
            control.update(1 / 60)
            control.draw_overlay(surface)
    assert built == []


def test_mechanical_wheels_hold_a_digit_until_the_end_of_each_step():
    wheels = _build("mechanical_wheels", raw={"per_sec": 1.0, "step_time": 0.20})
    assert wheels._roll_for(0.50) == 0.0
    assert 0.0 < wheels._roll_for(0.90) < 1.0


def test_mechanical_wheels_accept_a_system_font_name_or_ttf_path():
    named = _build("mechanical_wheels", raw={"font_name": "dejavusansmono"})
    assert named.font_name == "dejavusansmono"
    assert named._font_source == "system:dejavusansmono"

    path = pygame.font.match_font("dejavusansmono")
    assert path is not None
    from_path = _build("mechanical_wheels", raw={"font_name": path})
    assert from_path._font_source == f"path:{path}"


def test_spark_terminal_is_a_continuous_particle_shower_without_a_terminal_body():
    terminal = _build("spark_terminal", (200, 200, 160, 160))
    for _ in range(60):
        terminal.update(1 / 60)
    surface = pygame.Surface((600, 600))
    surface.fill((0, 0, 0))
    terminal.draw_overlay(surface)
    assert not hasattr(terminal, "glow")
    assert all(0.0 <= age < terminal.duration for age in terminal.age)
    assert surface.get_bounding_rect().width > 0
