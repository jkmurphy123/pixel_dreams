"""tests/test_lantern_procession.py -- Slow Worlds §5.11.

What is worth pinning:

  * the four aspect presets choose their own composition, not one stretched frame;
  * a seed reproduces the procession, and a different seed moves it;
  * the optional sigil list accepts strings and falls back cleanly;
  * the signature event dims one lantern, reports 13/14, and completes;
  * the controller's lower-left 80x32 corner stays dark;
  * the static forest/trail layers are cached, and exit releases everything;
  * the narrow slot 23 and portrait slot 28 are really wired through the registry.
"""

from __future__ import annotations

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402

from core.cache import ResourceCache                                       # noqa: E402
from core.config import load_json                                          # noqa: E402
from core.loader import build_merged_config                                # noqa: E402
from modes.lantern_procession_mode import (                                # noqa: E402
    LanternProcessionMode, aspect_class,
)


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # test_smoke owns the session's init/quit; do not quit here.
    pygame.init()
    pygame.font.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def make_mode(size=(1280, 400), config=None, frames=1):
    config = dict(config if config is not None else {"seed": 412})
    config.setdefault("quality", "low")
    screen = pygame.Surface(size)
    mode = LanternProcessionMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["lanternprocession"], cfg)
    merged["seed"] = 412
    merged["quality"] = "low"
    screen = pygame.Surface(size)
    mode = LanternProcessionMode(merged)
    mode.enter(FakeManager(screen))
    mode.update(1.0 / 60.0)
    mode.render(screen)
    return mode, screen, merged


# ---------------------------------------------------------------- framing

@pytest.mark.parametrize("size,preset", [
    ((1280, 400), "ultrawide"),
    ((1080, 1920), "portrait"),
    ((1920, 1080), "landscape"),
    ((720, 720), "square"),
])
def test_each_aspect_has_its_own_preset(size, preset):
    mode, screen = make_mode(size, {"seed": 5})
    assert mode.error is None
    assert mode.stats()["preset"] == preset
    assert screen.get_size() == size
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 30


def test_aspect_class_boundaries():
    assert aspect_class(1280, 400) == "ultrawide"
    assert aspect_class(1920, 1080) == "landscape"
    assert aspect_class(1080, 1920) == "portrait"
    assert aspect_class(800, 800) == "square"


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((270, 480), {"seed": 1, "orientation": "landscape"})
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- wiring

def test_the_narrow_and_portrait_instances_are_wired():
    narrow, narrow_screen, narrow_cfg = profile_mode(
        "configs/modes_config_narrow_horz.json", "23", (1280, 400))
    portrait, portrait_screen, portrait_cfg = profile_mode(
        "configs/modes_config_portrait.json", "28", (1080, 1920))
    assert narrow.error is None and portrait.error is None
    assert narrow_cfg["type"] == "lanternprocession"
    assert portrait_cfg["type"] == "lanternprocession"
    assert narrow.stats()["preset"] == "ultrawide"
    assert portrait.stats()["preset"] == "portrait"
    assert narrow_screen.get_size() == (1280, 400)
    assert portrait_screen.get_size() == (1080, 1920)


# ---------------------------------------------------------------- seed / values

def test_a_seed_reproduces_the_procession():
    one, screen_one = make_mode((1280, 400), {"seed": 2001})
    two, screen_two = make_mode((1280, 400), {"seed": 2001})
    one._time = two._time = 123.4
    one._start_time = two._start_time = 123.4
    one.render(screen_one)
    two.render(screen_two)
    assert one.stats()["positions"] == two.stats()["positions"]


def test_a_different_seed_moves_the_line():
    one, _ = make_mode((1280, 400), {"seed": 1})
    two, _ = make_mode((1280, 400), {"seed": 2})
    assert one.stats()["positions"] != two.stats()["positions"]


def test_the_sigil_set_accepts_strings_and_falls_back():
    ok, _ = make_mode((640, 400), {"seed": 3, "sigil_set": ["A", "BC", "D"]})
    assert ok.error is None
    assert ok._sigils == ["A", "BC", "D"]
    bad, _ = make_mode((640, 400), {"seed": 3, "sigil_set": ["TOOLONG"]})
    assert bad.error is None
    assert bad._sigils == list(range(8))


def test_a_comma_string_is_also_accepted():
    mode, _ = make_mode((640, 400), {"seed": 3, "sigil_set": "A, BC"})
    assert mode.error is None
    assert mode._sigils == ["A", "BC"]


def test_a_bad_palette_is_refused_not_guessed():
    mode, screen = make_mode((1280, 400), {"seed": 1, "palette": "nope"})
    assert mode.error is not None
    mode.render(screen)          # the error card must draw, not raise
    assert screen.get_size() == (1280, 400)


# ---------------------------------------------------------------- signature

def test_the_departure_dims_one_lantern_and_completes():
    mode, screen = make_mode(
        (1280, 400), {"seed": 412, "departure_seconds": 0})
    assert mode.error is None
    mode._time = 120.0
    mode._start_time = 120.0
    mode.render(screen)
    states = mode._compute_states(mode._time)
    target = max((s for s in states if 0.2 < s.u < 0.8), key=lambda s: s.scale)
    mode.start_departure(target.index)
    assert mode.stats()["event"] is True
    assert mode.stats()["lit"] == mode._lantern_count - 1
    for _ in range(220):                 # 22 s: 18 s drift + 3 s afterglow
        mode.update(0.1)
    assert mode.stats()["event"] is False
    assert mode.stats()["lit"] == mode._lantern_count


def test_departures_can_be_disabled():
    mode, _ = make_mode((1280, 400), {"seed": 1, "departure_seconds": 0})
    mode._time = 10000.0
    mode.update(0.1)
    assert mode.stats()["event"] is False
    assert mode.stats()["lit"] == mode._lantern_count


# ---------------------------------------------------------------- corners / lifecycle

@pytest.mark.parametrize("size", [(1280, 400), (1080, 1920)])
def test_the_mode_number_corner_stays_dark(size):
    mode, screen = make_mode(size, {"seed": 7})
    mode._time = 90.0
    mode.render(screen)
    corner = screen.subsurface(pygame.Rect(0, size[1] - 32, 80, 32))
    values = [sum(corner.get_at((x, y))[:3]) / 3.0
              for y in range(32) for x in range(80)]
    assert sum(values) / len(values) < 30.0
    assert max(values) < 60.0


def test_static_layers_are_cached_between_frames():
    mode, screen = make_mode(
        (1280, 400), {"seed": 4, "quality": "medium"})
    back = mode._back
    front = mode._front
    assert back is not None and front is not None
    mode.update(1.0 / 60.0)
    mode.render(screen)
    assert mode._back is back
    assert mode._front is front


def test_exit_releases_its_caches():
    mode, screen = make_mode((1280, 400), {"seed": 4})
    assert mode._sprite_cache
    mode.exit()
    assert mode._back is None
    assert mode._front is None
    assert mode._sprite_cache == {}
    assert mode._reflection_cache == {}
    assert mode.manager is None


def test_reflection_can_be_turned_off():
    mode, screen = make_mode(
        (1280, 400), {"seed": 4, "reflection": False, "mist": False})
    assert mode.error is None
    assert mode.stats()["reflection"] is False
    assert mode.stats()["mist"] is False
    mode.render(screen)
