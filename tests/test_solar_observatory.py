"""tests/test_solar_observatory.py -- Solar Observatory Ring, instruments close in.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the star is the subject: it sits off-centre at the preset's radius, and the
    ring is an ellipse outside its limb;
  * a seed reproduces the satellites, the loops and the loop-pass schedule;
  * the signature beat exists: a loop reaches the ring and the status reports it;
  * `loops: false` removes them and the beat with them;
  * the palette variants change the mood without moving the star;
  * the camera's ride is periodic over `orbit_seconds`, so the star cannot drift
    out of frame;
  * bad values are refused once, and the error panel draws;
  * the registry entry resolves and all four shipped profile instances are
    valid and build through `build_merged_config`.

Most cases use quality="low": the contract is the point, not the frame time.
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
from modes.solar_observatory_mode import (                                 # noqa: E402
    SolarObservatoryRingMode,
    QUALITY,
    aspect_preset,
)


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
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


def make_mode(size=(640, 360), config=None, frames=1):
    config = dict(config if config is not None else {"seed": 5151})
    config.setdefault("quality", "low")
    screen = pygame.Surface(size)
    mode = SolarObservatoryRingMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["solarobservatory"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = SolarObservatoryRingMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def event_moment(mode) -> float:
    start, duration, _index = mode._events[0]
    return start + duration * 0.5


def nominal_moment(mode) -> float:
    return max(start + duration for start, duration, _index in mode._events) + 1.0


# ---------------------------------------------------------------- aspect / framing

def test_aspect_presets_choose_the_expected_frame():
    assert aspect_preset(1280, 400) == "ultrawide"
    assert aspect_preset(1920, 1080) == "landscape"
    assert aspect_preset(1080, 1920) == "portrait"
    assert aspect_preset(800, 800) == "square"


@pytest.mark.parametrize("size,preset", [
    ((1280, 400), "ultrawide"),
    ((1080, 1920), "portrait"),
    ((1920, 1080), "landscape"),
    ((800, 800), "square"),
])
def test_the_mode_renders_at_every_target_and_keeps_the_corner_clear(size, preset):
    mode, screen = make_mode(size, {"seed": 5151, "quality": "low", "hud": "full"})
    assert mode.error is None
    stats = mode.stats()
    assert stats["preset"] == preset
    assert stats["satellites"] == 12
    assert stats["satellites_drawn"] == 12
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_star_is_the_subject_and_the_ring_sits_outside_its_limb():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    (sx, sy), star_r = mode.stats()["star"]
    assert 0.35 * 1280 < sx < 0.75 * 1280
    assert 0.30 * 400 < sy < 0.65 * 400
    assert 0.20 * 400 < star_r < 0.45 * 400
    ring_x, ring_y = mode.stats()["ring"]
    assert ring_x > star_r, "the ring must orbit outside the disc"
    assert ring_y < ring_x, "the ring is a perspective ellipse, not a circle"


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_satellites_the_loops_and_the_schedule():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._satellites == b._satellites
    assert a._loops == b._loops
    assert a._events == b._events
    assert pixels(screen_a) == pixels(screen_b)
    assert a._satellites != c._satellites
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_observatory_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the signature beat

def test_a_loop_reaches_the_ring_and_the_status_reports_it():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._events, "the schedule must have loop passes"

    mode._time = nominal_moment(mode)
    mode.render(screen)
    assert mode.stats()["event"] is None
    assert mode._status_text()[1] is False

    mode._time = event_moment(mode)
    mode.render(screen)
    event = mode.stats()["event"]
    assert event is not None
    assert 0.0 < event["severity"] <= 1.0
    assert 0 <= event["satellite"] < len(mode._satellites)
    status, alert = mode._status_text()
    assert alert is True and "RING PASS" in status


def test_loops_off_removes_them_and_the_beat():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "loops": False,
    }, frames=0)
    assert mode.error is None
    assert mode.stats()["loops"] == 0
    mode._time = event_moment(mode)
    mode.render(screen)
    assert mode.stats()["event"] is None
    assert len(set(pixels(screen))) > 40


def test_the_event_schedule_repeats_over_a_pinned_span():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    assert len(mode._events) == 6
    assert mode._event_span > 0.0
    starts = [start for start, _duration, _index in mode._events]
    assert starts == sorted(starts)


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["amber", "ice", "mono"])
def test_palette_variants_render_and_keep_the_star(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_framing():
    frames = {}
    framing = {}
    for palette in ("amber", "ice", "mono"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["star"]
    assert frames["amber"] != frames["ice"]
    assert frames["amber"] != frames["mono"]
    assert framing["amber"] == framing["ice"] == framing["mono"]


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_the_quality_tier_sets_the_loop_budget(quality):
    mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality})
    assert mode.error is None
    stats = mode.stats()
    assert stats["quality"] == quality
    assert stats["loops"] == QUALITY[quality]["loops"]


def test_a_fixed_quality_does_not_adapt_and_the_ring_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    satellites = mode._satellites
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._satellites is satellites


def test_auto_quality_steps_the_detail_not_the_observatory():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._satellites, mode._loops, mode._events)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._satellites, mode._loops, mode._events) == before


# ---------------------------------------------------------------- camera

def test_the_camera_ride_is_periodic_over_the_ring_period():
    mode, _ = make_mode((1280, 400), {"seed": 5, "quality": "low",
                                      "orbit_seconds": 240.0}, frames=0)
    mode._time = 0.0
    start = mode._star_offset()
    mode._time = 240.0
    again = mode._star_offset()
    assert again == pytest.approx(start, abs=1e-6)
    assert abs(start[0]) <= mode._star_r * 0.34 + 0.001
    mode._time = 86400.0
    assert abs(mode._star_offset()[0]) <= mode._star_r * 0.34 + 0.001


# ---------------------------------------------------------------- HUD / switches

def test_hud_modes_and_fill_modes_are_accepted():
    for hud in ("off", "minimal", "full"):
        for fill in ("line", "xray", "panel"):
            mode, screen = make_mode((640, 360), {
                "seed": 5, "quality": "low", "hud": hud, "fill": fill,
            }, frames=0)
            assert mode.error is None, (hud, fill, mode.error)
            mode.render(screen)
            stats = mode.stats()
            assert stats["hud"] == hud
            assert stats["fill"] == fill
            assert stats["corner_clear"] is True


def test_the_scene_reads_with_the_glow_off():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "glow_strength": 0.0,
    })
    assert mode.error is None
    assert mode._bloom is None
    assert len(set(pixels(screen))) > 40


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"satellite_count": 2},
    {"satellite_count": 24},
    {"satellite_count": 12.5},
    {"ring_radius": 0.05},
    {"ring_radius": 3.0},
    {"orbit_seconds": 20},
    {"orbit_seconds": 1000},
    {"loops": 1},
    {"glow_strength": 2},
    {"scanline_alpha": -1},
    {"scanline_alpha": 100},
    {"vignette_strength": 2},
    {"seed": -1},
    {"seed": 2 ** 31},
    {"title": 42},
    {"subtitle": 7},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    cfg = dict(bad)
    cfg.setdefault("quality", "low")
    mode, screen = make_mode((640, 360), cfg, frames=0)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)
    assert mode.error


# ---------------------------------------------------------------- lifecycle

def test_resize_recomposes_natively_and_exit_releases_the_surfaces():
    mode, _ = make_mode((1280, 400), {"seed": 7, "quality": "low"})
    assert mode.error is None
    strip_star = mode.stats()["star"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["star"] != strip_star
    mode.exit()
    assert mode.manager is None
    assert mode._background is None and mode._star is None
    assert mode._satellites == [] and mode._loops == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._satellites)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._satellites) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["solarobservatory"]
    assert spec["entrypoint"] == "modes.solar_observatory_mode:SolarObservatoryRingMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "satellite_count", "ring_radius", "orbit_seconds", "loops",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"satellite_count": 12}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["satellite_count"].widget == "number"
    assert by_key["ring_radius"].widget == "number"
    assert by_key["loops"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "32", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "37", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "76", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "19", (1920, 1080), "landscape"),
])
def test_the_four_profiles_are_wired_and_valid(profile, slot, size, preset):
    reg = registry()
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    issues = validate_instance(slot, cfg, reg, base_dir=BASE_DIR)
    assert not [i for i in issues if i.is_error], issues
    mode, screen, merged = profile_mode(profile, slot, size)
    assert mode.error is None
    assert merged["orientation"] == preset
    assert mode.stats()["preset"] == preset
    assert mode.stats()["corner_clear"] is True
    assert len(set(pixels(screen))) > 40
    mode.exit()
