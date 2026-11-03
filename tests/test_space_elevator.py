"""tests/test_space_elevator.py -- Space Elevator, a very long way up.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the tether is the spine: it sits near the middle, the car holds its place
    and the altitude readout climbs;
  * a seed reproduces the ticks, the beacons and the clouds;
  * the cycle has its three phases and the station ring descends to meet the
    car, then passes beneath it;
  * `show_planet: false` removes the limb and the clouds;
  * the palette variants change the mood without moving the tether;
  * `tether_sway: 0` makes the line rigid;
  * bad values are refused once, and the error panel draws;
  * the registry entry resolves and all four shipped profile instances are
    valid and build through `build_merged_config`.

Most cases use quality="low": the contract is the point, not the frame time.
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
from core.params import resolve_params                                     # noqa: E402
from core.validation import validate_instance                              # noqa: E402
from modes.space_elevator_mode import (                                    # noqa: E402
    SpaceElevatorMode,
    CYCLE_SECONDS,
    PASS_AT,
    SETTLE_AT,
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
    mode = SpaceElevatorMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["spaceelevator"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = SpaceElevatorMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


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
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_tether_holds_the_middle_and_the_car_its_place():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=1)
    assert mode.error is None
    cx, cy = mode.stats()["car"]
    assert 0.35 * 1280 < cx < 0.60 * 1280
    assert 0.40 * 400 < cy < 0.65 * 400
    # the tether is vertical: its x barely moves from the car's
    assert abs(mode._tether_x(0, 400) - cx) < 12
    assert abs(mode._tether_x(400, 400) - cx) < 12


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_ticks_the_beacons_and_the_clouds():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._ticks == b._ticks
    assert a._beacons == b._beacons
    assert a._clouds == b._clouds
    assert pixels(screen_a) == pixels(screen_b)
    assert a._ticks != c._ticks
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_climb_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the cycle

def test_the_cycle_has_its_three_phases():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    mode._time = CYCLE_SECONDS * 0.25
    mode.render(screen)
    assert mode.stats()["cycle"]["phase"] == "climb"
    mode._time = CYCLE_SECONDS * (PASS_AT + (SETTLE_AT - PASS_AT) * 0.5)
    mode.render(screen)
    assert mode.stats()["cycle"]["phase"] == "pass"
    mode._time = CYCLE_SECONDS * 0.95
    mode.render(screen)
    assert mode.stats()["cycle"]["phase"] == "settle"


def test_the_altitude_readout_climbs_with_the_cycle():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "altitude": 18400}, frames=0)
    mode._time = 0.0
    mode.render(screen)
    low = mode.stats()["altitude_km"]
    mode._time = CYCLE_SECONDS * 0.75
    mode.render(screen)
    high = mode.stats()["altitude_km"]
    assert low >= 18400
    assert high > low


def test_the_station_descends_to_meet_the_car_then_passes_below():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    _, car_y = mode.stats()["car"]
    heights = {}
    for label, p in (("early", 0.10), ("approach", 0.70), ("pass", PASS_AT + 0.02),
                     ("settle", 0.95)):
        mode._time = CYCLE_SECONDS * p
        mode.render(screen)
        ring_rx, _ring_ry = mode.stats()["ring"]
        heights[label] = (mode.stats()["ring_y"], ring_rx)
    assert heights["approach"][0] > heights["early"][0], "the station descends"
    assert heights["pass"][0] >= heights["approach"][0]
    assert heights["settle"][0] > heights["pass"][0], "and passes beneath the car"
    assert heights["pass"][1] > heights["early"][1], "and grows as it comes"


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["vector_blue", "ice", "amber"])
def test_palette_variants_render_and_keep_the_tether(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_tether():
    frames = {}
    tether = {}
    for palette in ("vector_blue", "ice", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        tether[palette] = mode.stats()["car"]
    assert frames["vector_blue"] != frames["ice"]
    assert frames["vector_blue"] != frames["amber"]
    assert tether["vector_blue"] == tether["ice"] == tether["amber"]


def test_the_planet_and_its_clouds_can_be_switched_off():
    on, screen_on = make_mode((640, 360), {"seed": 5151, "quality": "low"})
    off, screen_off = make_mode((640, 360), {"seed": 5151, "quality": "low",
                                             "show_planet": False})
    assert off.error is None
    assert off.stats()["show_planet"] is False
    assert pixels(screen_on) != pixels(screen_off)


def test_a_fixed_quality_does_not_adapt_and_the_marks_are_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    ticks = mode._ticks
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._ticks is ticks


def test_auto_quality_steps_the_detail_not_the_climb():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._ticks, mode._clouds, mode._beacons)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._ticks, mode._clouds, mode._beacons) == before


# ---------------------------------------------------------------- tether

def test_zero_sway_makes_the_tether_rigid():
    rigid, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "tether_sway": 0.0},
                         frames=0)
    rigid._time = 0.0
    still_x = rigid._tether_x(200, 360)
    rigid._time = 3.7
    assert rigid._tether_x(200, 360) == pytest.approx(still_x, abs=1e-9)

    swaying, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "tether_sway": 2.0},
                           frames=0)
    swaying._time = 0.0
    a = swaying._tether_x(200, 360)
    swaying._time = 3.0
    assert abs(swaying._tether_x(200, 360) - a) > 0.5


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
    {"car_speed": 0},
    {"car_speed": 80},
    {"altitude": 10},
    {"altitude": 99999},
    {"altitude": 18400.5},
    {"show_planet": 1},
    {"tether_sway": -1},
    {"tether_sway": 9},
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
    strip_car = mode.stats()["car"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["car"] != strip_car
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._ticks == [] and mode._clouds == [] and mode._beacons == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._ticks)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._ticks) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["spaceelevator"]
    assert spec["entrypoint"] == "modes.space_elevator_mode:SpaceElevatorMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "car_speed", "altitude", "show_planet", "tether_sway",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"car_speed": 10}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["car_speed"].widget == "number"
    assert by_key["altitude"].widget == "number"
    assert by_key["show_planet"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "33", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "38", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "77", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "20", (1920, 1080), "landscape"),
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
