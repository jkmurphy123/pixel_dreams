"""tests/test_orrery.py -- The Orrery of Small Worlds.

What is worth pinning beyond "it draws something":

  * the projected oval ratio really follows sin(elevation) on the strip and
    the portrait wall, and the aspect presets choose the expected camera;
  * a seed reproduces the entry moment, comet phase and dust;
  * world_count changes the rail count and the plaque description;
  * the plaque is a real switch: absent from the narrow instance, present in
    portrait, and it reserves a different safe rectangle when enabled;
  * labels stay out of the controller's lower-left 80x32 mode-number corner;
  * the mode renders at the four target sizes, survives a resize, and releases
    its caches on exit;
  * the registry schema and the two shipped profile instances are wired.

The narrow slot 21 and the portrait slot 26 are the real wiring; those cases
build through build_merged_config, not just the class.
"""

from __future__ import annotations

import math
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
from core.params import resolve_params                                     # noqa: E402
from core.validation import validate_instance                              # noqa: E402
from modes.orrery_mode import (                                            # noqa: E402
    NUMBER_WORDS, OrreryMode, aspect_class, build_worlds,
)


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # Do not quit at module scope: a quit tears the font module down for later
    # modules. test_smoke owns the session's init/quit.
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


def make_mode(size=(1280, 400), config=None, frames=2):
    config = dict(config if config is not None else {"seed": 2001})
    config.setdefault("orientation", "auto")
    screen = pygame.Surface(size)
    mode = OrreryMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["orrery"], cfg)
    merged["seed"] = 2001
    screen = pygame.Surface(size)
    mode = OrreryMode(merged)
    mode.enter(FakeManager(screen))
    mode.update(1.0 / 60.0)
    mode.render(screen)
    return mode, screen, merged


# ---------------------------------------------------------------- camera / framing

@pytest.mark.parametrize("size,preset,elevation", [
    ((1280, 400), "ultrawide", 16.0),
    ((1080, 1920), "portrait", 33.0),
    ((1920, 1080), "landscape", 20.0),
    ((480, 270), "landscape", 20.0),
    ((360, 360), "square", 27.0),
])
def test_the_camera_projects_an_oval_on_every_aspect(size, preset, elevation):
    mode, screen = make_mode(size, {"seed": 5})
    assert mode.error is None
    stats = mode.stats()
    assert stats["preset"] == preset
    assert stats["elevation"] == pytest.approx(elevation)
    # A circle seen from e degrees above its plane has h:w = sin(e).
    assert stats["oval_ratio"] == pytest.approx(math.sin(math.radians(elevation)))
    assert stats["segments"] > 600, stats
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 30
    assert mode._frame is not None


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((270, 480), {"seed": 1, "orientation": "landscape"})
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"
    assert mode.stats()["layout"] == "wide"


def test_the_portrait_preset_has_the_arch_and_the_strip_does_not():
    strip, _ = make_mode((1280, 400), {"seed": 1})
    portrait, _ = make_mode((1080, 1920), {"seed": 1})
    assert strip.stats()["layout"] == "wide"
    assert portrait.stats()["layout"] == "portrait"
    assert strip._layout["armature"] is False
    assert portrait._layout["armature"] is True


def test_camera_overrides_change_the_oval_and_are_reported():
    mode, _ = make_mode((1280, 400), {
        "seed": 1, "camera_elevation": "24", "camera_azimuth": "-21",
    })
    assert mode.error is None
    stats = mode.stats()
    assert stats["elevation"] == pytest.approx(24.0)
    assert stats["azimuth"] == pytest.approx(-21.0)
    assert stats["oval_ratio"] == pytest.approx(math.sin(math.radians(24.0)))


def test_aspect_class_boundaries():
    assert aspect_class(1280, 400) == "ultrawide"
    assert aspect_class(1920, 1080) == "landscape"
    assert aspect_class(1080, 1920) == "portrait"
    assert aspect_class(800, 800) == "square"


# ---------------------------------------------------------------- plaque

def test_the_plaque_is_off_in_the_strip_and_on_in_portrait():
    strip, strip_screen = make_mode((1280, 400), {"seed": 2})
    portrait, portrait_screen = make_mode((1080, 1920),
                                          {"seed": 2, "show_plaque": True})
    assert strip.stats()["plaque"] is False
    assert strip.stats()["plaque_rect"] is None
    assert portrait.stats()["plaque"] is True
    assert portrait.stats()["plaque_rect"] is not None
    # The plaque is outside the portrait's safe rectangle.
    safe = pygame.Rect(portrait.stats()["safe_rect"])
    plaque = pygame.Rect(portrait.stats()["plaque_rect"])
    assert not safe.colliderect(plaque)
    assert strip_screen.get_size() == (1280, 400)
    assert portrait_screen.get_size() == (1080, 1920)


def test_turning_the_plaque_on_in_a_wide_layout_reserves_room_for_it():
    without, _ = make_mode((1280, 400), {"seed": 2, "show_plaque": False})
    with_plaque, _ = make_mode((1280, 400), {"seed": 2, "show_plaque": True})
    assert without.stats()["plaque"] is False
    assert with_plaque.stats()["plaque"] is True
    without_safe = pygame.Rect(without.stats()["safe_rect"])
    with_safe = pygame.Rect(with_plaque.stats()["safe_rect"])
    assert with_safe.bottom < without_safe.bottom
    assert with_plaque.stats()["plaque_rect"][1] > with_safe.bottom


def test_the_plaque_describes_the_system_not_the_maker():
    mode, _ = make_mode((1080, 1920), {"seed": 2, "show_plaque": True})
    lines = mode.stats()["plaque_lines"]
    assert lines[0] == "THE AUREL SYSTEM"
    assert "SEVEN INVENTED WORLDS" in lines[1]
    assert "ONE LAMP AT THE FOCUS" in lines[1]
    assert "PERIODS" in lines[2] and "INCLINATIONS" in lines[2]
    assert "HALE" not in " ".join(lines)


def test_world_count_feeds_the_plaque_description():
    five, _ = make_mode((1080, 1920), {"seed": 2, "show_plaque": True,
                                        "world_count": 5})
    nine, _ = make_mode((1080, 1920), {"seed": 2, "show_plaque": True,
                                       "world_count": 9})
    assert NUMBER_WORDS[5] in five.stats()["plaque_lines"][1]
    assert NUMBER_WORDS[9] in nine.stats()["plaque_lines"][1]
    assert len(five.stats()["worlds"]) == 5
    assert len(nine.stats()["worlds"]) == 9


def test_show_plaque_is_a_switch_in_the_schema():
    spec = registry()["orrery"]
    params, _warnings = resolve_params({"show_plaque": False}, spec)
    spec_by_key = {p.key: p for p in params}
    assert spec_by_key["show_plaque"].widget == "switch"
    assert spec_by_key["show_plaque"].default is False
    assert "plaque" in spec_by_key["show_plaque"].help.lower()


# ---------------------------------------------------------------- worlds / seed

def test_world_count_builds_that_many_distinct_worlds():
    for count in (5, 7, 9):
        worlds = build_worlds(count, 90.0)
        assert len(worlds) == count
        assert len({w.name for w in worlds}) == count
        assert worlds[0].a < worlds[-1].a
        assert all(w.period >= 45.0 for w in worlds)


def test_a_seed_reproduces_the_entry_moment_and_the_dust():
    a, _ = make_mode((1280, 400), {"seed": 99}, frames=0)
    b, _ = make_mode((1280, 400), {"seed": 99}, frames=0)
    c, _ = make_mode((1280, 400), {"seed": 100}, frames=0)
    assert a.seed == b.seed == 99
    assert a._start_time == b._start_time
    assert a._comet_phase == b._comet_phase
    assert a._dust == b._dust
    assert c.seed == 100
    assert (c._start_time != a._start_time
            or c._comet_phase != a._comet_phase
            or c._dust != a._dust)


def test_the_world_positions_are_a_function_of_time_not_frame_rate():
    a, _ = make_mode((1280, 400), {"seed": 4}, frames=0)
    a._time = 37.0
    first = [tuple(round(c, 6) for c in w.position(a._time)) for w in a._worlds]
    b, _ = make_mode((1280, 400), {"seed": 4}, frames=0)
    b._time = 37.0
    second = [tuple(round(c, 6) for c in w.position(b._time)) for w in b._worlds]
    assert first == second


# ---------------------------------------------------------------- labels / HUD

def test_labels_are_drawn_and_stay_out_of_the_mode_number_corner():
    mode, screen = make_mode((1280, 400), {"seed": 5})
    assert mode._last_label_boxes, "no world labels were placed"
    corner = pygame.Rect(0, 400 - 64, 120, 64)
    for rect in mode._last_label_boxes:
        assert not rect.colliderect(corner), (rect, corner)
        assert 0 <= rect.left and rect.right <= 1280
        assert 0 <= rect.top and rect.bottom <= 400


def test_labels_can_be_turned_off():
    mode, _ = make_mode((1280, 400), {"seed": 5, "show_labels": False})
    assert mode.stats()["labels"] == 0
    assert mode._last_label_boxes == []


def test_hud_off_leaves_the_scene_running():
    mode, screen = make_mode((1280, 400), {"seed": 5, "hud": "off"})
    assert mode.error is None
    assert mode.stats()["hud"] == "off"
    assert mode.stats()["segments"] > 600
    mode.render(screen)
    assert mode.error is None


# ---------------------------------------------------------------- config handling

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"orientation": "diagonal"},
    {"world_count": 4},
    {"world_count": 10},
    {"world_count": 7.5},
    {"orbit_seconds": 10},
    {"orbit_seconds": 1000},
    {"camera_drift": -1},
    {"camera_drift": 5},
    {"camera_elevation": "steep"},
    {"camera_elevation": 80},
    {"camera_azimuth": "left"},
    {"camera_azimuth": 40},
    {"show_labels": 1},
    {"show_comet": 1},
    {"show_conjunctions": "yes"},
    {"show_plaque": 1},
    {"seed": -1},
    {"seed": 2 ** 31},
    {"scanline_alpha": 900},
    {"vignette_strength": 2},
    {"glow_strength": 2},
    {"title": 42},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    mode, screen = make_mode((640, 360), bad)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)
    assert mode.error


def test_the_error_panel_is_drawn_when_the_config_is_refused():
    mode, screen = make_mode((640, 360), {"palette": "neon"})
    assert "palette" in mode.error
    assert mode.stats() == {}
    mode.render(screen)
    assert mode.error


# ---------------------------------------------------------------- lifecycle / quality

def test_a_resize_rebuilds_the_camera_and_the_caches():
    mode, _ = make_mode((1280, 400), {"seed": 7})
    assert mode.stats()["preset"] == "ultrawide"
    portrait = pygame.Surface((1080, 1920))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (1080, 1920)
    assert mode.stats()["preset"] == "portrait"
    assert mode._room is not None
    assert mode._room.get_size()[0] > 1080


def test_exit_releases_every_surface_and_reference():
    mode, _ = make_mode((1280, 400), {"seed": 7})
    mode.exit()
    assert mode.manager is None
    assert mode._room is None and mode._rails_front is None
    assert mode._hud is None and mode._plaque is None
    assert mode._worlds == []
    assert mode._screen_size is None


def test_auto_quality_steps_down_when_frames_are_slow():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    assert mode._quality == "medium"
    medium_segments = mode._last_segments
    for _ in range(80):
        mode.update(0.08)
    assert mode._quality == "low"
    assert mode._last_segments < medium_segments
    assert "medium -> low" in mode.diagnostic


def test_a_fixed_quality_does_not_adapt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "high"}, frames=0)
    for _ in range(120):
        mode.update(0.033)
    assert mode._quality == "high"
    assert mode._auto_quality is False


def test_conjunctions_can_be_turned_off():
    mode, _ = make_mode((1280, 400), {"seed": 5, "show_conjunctions": False},
                        frames=0)
    mode.update(1 / 60)
    assert mode.stats()["conjunction"] is None
    assert mode._conj_pair is None


def test_a_comet_can_be_turned_off():
    mode, _ = make_mode((1280, 400), {"seed": 5, "show_comet": False}, frames=0)
    assert mode._comet_position() is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_is_typed_and_the_schema_resolves():
    spec = registry()["orrery"]
    assert spec["entrypoint"] == "modes.orrery_mode:OrreryMode"
    assert spec["required"] == []
    for key in ("show_plaque", "show_labels", "camera_elevation",
                "camera_azimuth", "world_count", "orbit_seconds"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"show_plaque": False}, spec)
    spec_by_key = {p.key: p for p in params}
    assert spec_by_key["show_plaque"].widget == "switch"
    assert spec_by_key["world_count"].widget == "number"
    assert spec_by_key["camera_elevation"].widget == "text"


def test_the_narrow_portrait_and_vert_profiles_are_wired_and_valid():
    reg = registry()
    for profile, slot, size, show_plaque, preset in (
            ("configs/modes_config_narrow_horz.json", "21", (1280, 400),
             False, "ultrawide"),
            ("configs/modes_config_portrait.json", "26", (1080, 1920),
             True, "portrait"),
            ("configs/modes_config_vert.json", "66", (1080, 1920),
             True, "portrait")):
        cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
        issues = validate_instance(slot, cfg, reg, base_dir=BASE_DIR)
        assert not [i for i in issues if i.is_error], issues
        mode, screen, merged = profile_mode(profile, slot, size)
        assert mode.error is None
        assert merged["show_plaque"] is show_plaque
        assert mode.stats()["plaque"] is show_plaque
        assert mode.stats()["preset"] == preset
        assert mode.stats()["world_count"] == 7
        assert mode.stats()["segments"] > 600
        assert len(set(pygame.image.tostring(screen, "RGB"))) > 30
        mode.exit()
