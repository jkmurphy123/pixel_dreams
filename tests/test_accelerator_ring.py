"""tests/test_accelerator_ring.py -- Accelerator Ring, an instrument around a moon.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the ring is an ellipse around a moon, and `ring_radius` widens it;
  * a seed reproduces the halls and the stars;
  * the pulse travels the ring at the card's eighteen-second lap and `pulse_speed`
    scales it; when it reaches a hall, the hall lights and the status says so;
  * the palette variants change the mood without moving the ring;
  * `detector_count` sets the halls, inside its bounds;
  * the camera's orbit is periodic over 240 s, and `camera_orbit: 0` leaves only
    the ring's own 300 s precession;
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
from modes.accelerator_ring_mode import (                                  # noqa: E402
    AcceleratorRingMode,
    LAP_SECONDS,
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
    mode = AcceleratorRingMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["acceleratorring"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = AcceleratorRingMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def hall_moment(mode, index: int, speed: float = 1.0) -> float:
    """A time when the pulse is inside hall `index`."""
    hall = mode._halls[index]
    return hall["angle"] / (2.0 * math.pi) * (LAP_SECONDS / speed)


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
    assert stats["detectors"] == 12
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_ring_is_an_ellipse_around_the_moon():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    rx, ry = mode.stats()["ring"]
    cx, cy = mode.stats()["centre"]
    assert rx > 0.25 * 1280
    assert 0.25 < ry / rx < 0.55, "the ring is in perspective, not a circle"
    assert 0.30 * 1280 < cx < 0.65 * 1280
    assert 0.30 * 400 < cy < 0.65 * 400


def test_a_larger_ring_radius_widens_the_ring():
    small, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "ring_radius": 0.3},
                         frames=0)
    large, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "ring_radius": 1.4},
                         frames=0)
    assert small.stats()["ring"][0] < large.stats()["ring"][0]


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_halls_and_the_stars():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._halls == b._halls
    assert a._stars == b._stars
    assert pixels(screen_a) == pixels(screen_b)
    assert a._halls != c._halls
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_ring_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the pulse

def test_the_pulse_laps_the_ring_in_eighteen_seconds():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    mode._time = 0.0
    mode.render(screen)
    assert mode.stats()["pulse_angle"] == pytest.approx(0.0, abs=1e-6)
    mode._time = LAP_SECONDS / 4.0
    mode.render(screen)
    assert mode.stats()["pulse_angle"] == pytest.approx(math.pi / 2.0, abs=1e-6)
    mode._time = LAP_SECONDS
    mode.render(screen)
    assert mode.stats()["pulse_angle"] == pytest.approx(0.0, abs=1e-3)


def test_pulse_speed_scales_the_lap():
    fast, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "pulse_speed": 2.0},
                        frames=0)
    assert fast.stats()["lap_seconds"] == pytest.approx(LAP_SECONDS / 2.0)


def test_a_hall_lights_when_the_pulse_reaches_it():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._halls
    # a moment between halls: nothing is lit
    between = hall_moment(mode, 0) + (hall_moment(mode, 1) - hall_moment(mode, 0)) / 2.0
    mode._time = between
    mode.render(screen)
    assert mode.stats()["lit_hall"] is None
    assert mode._status_text()[1] is False

    mode._time = hall_moment(mode, 1)
    mode.render(screen)
    assert mode.stats()["lit_hall"] == 1
    status, alert = mode._status_text()
    assert alert is True and "HALL" in status


def test_detector_count_sets_the_halls():
    for count in (4, 12, 24):
        mode, screen = make_mode((640, 360), {
            "seed": 5, "quality": "low", "detector_count": count,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        assert mode.stats()["detectors"] == count


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["vector_blue", "phosphor", "amber"])
def test_palette_variants_render_and_keep_the_ring(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_ring():
    frames = {}
    framing = {}
    for palette in ("vector_blue", "phosphor", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = (mode.stats()["ring"], mode.stats()["centre"])
    assert frames["vector_blue"] != frames["phosphor"]
    assert frames["vector_blue"] != frames["amber"]
    assert framing["vector_blue"] == framing["phosphor"] == framing["amber"]


def test_a_fixed_quality_does_not_adapt_and_the_ring_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    halls = mode._halls
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._halls is halls


def test_auto_quality_steps_the_detail_not_the_ring():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._halls, mode._stars)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._halls, mode._stars) == before


# ---------------------------------------------------------------- camera

def test_the_camera_orbit_is_periodic_and_zero_leaves_only_the_precession():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_orbit": 2.0},
                        frames=0)
    mode._time = 0.0
    start = mode._precession()
    mode._time = 60.0
    assert abs(mode._precession() - start) > 1e-4
    mode._time = 1200.0          # the precession (300 s) and the orbit (240 s) meet here
    assert mode._precession() == pytest.approx(start, abs=1e-6)

    still, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_orbit": 0.0},
                         frames=0)
    still._time = 0.0
    base = still._precession()
    still._time = 300.0
    assert still._precession() == pytest.approx(base, abs=1e-6), \
        "only the 300 s precession remains"


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
    {"ring_radius": 0.1},
    {"ring_radius": 2.0},
    {"pulse_speed": 0.0},
    {"pulse_speed": 9.0},
    {"detector_count": 2},
    {"detector_count": 30},
    {"detector_count": 12.5},
    {"camera_orbit": -1},
    {"camera_orbit": 40},
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
    strip_ring = mode.stats()["ring"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["ring"] != strip_ring
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._halls == [] and mode._stars == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._halls)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._halls) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["acceleratorring"]
    assert spec["entrypoint"] == "modes.accelerator_ring_mode:AcceleratorRingMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "ring_radius", "pulse_speed", "detector_count", "camera_orbit",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"pulse_speed": 1.0}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["ring_radius"].widget == "number"
    assert by_key["detector_count"].widget == "number"
    assert by_key["pulse_speed"].widget == "number"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "37", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "41", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "81", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "23", (1920, 1080), "landscape"),
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
