"""tests/test_terraform.py -- Terraform, the mountain-overlook world.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * a seed reproduces the field jitter, city lights and bird paths;
  * the five-stage cycle is a function of time, and start_stage enters at the
    requested stage;
  * the palette variants and the quality settings are accepted without
    changing the composition;
  * bad values are refused once, and the error panel draws;
  * the registry entry resolves and the three shipped profile instances
    (narrow 26, portrait 31, vert 70) are valid and build through
    build_merged_config.

Most cases use quality="low": the mode caches five stage keyframes on entry,
and the tests do not need the finest upscale.
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
from modes.terraform_mode import TerraformMode, aspect_preset              # noqa: E402


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
    mode = TerraformMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["terraform"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = TerraformMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


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
    assert stats["stages"] == 5
    assert stats["stage"] == 0
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 40


def test_the_portrait_horizon_uses_the_forty_percent_mountain_band():
    mode, _ = make_mode((1080, 1920), {"seed": 5151, "quality": "low"})
    assert mode.error is None
    layout = mode._layout
    assert layout["horizon"] == pytest.approx(0.400)
    assert layout["coastline"] == pytest.approx(0.480)
    strip, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"})
    assert strip._layout["horizon"] == pytest.approx(0.270)


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / stage

def test_a_seed_reproduces_the_lights_and_birds():
    a, _ = make_mode((640, 360), {"seed": 99}, frames=0)
    b, _ = make_mode((640, 360), {"seed": 99}, frames=0)
    c, _ = make_mode((640, 360), {"seed": 100}, frames=0)
    assert a.error is None and b.error is None and c.error is None
    assert a.seed == b.seed == 99
    assert a._birds == b._birds
    assert a._city_points == b._city_points
    assert c._birds != a._birds or c._city_points != a._city_points


def test_the_stage_cycle_is_a_function_of_time():
    mode, screen = make_mode((640, 360), {"seed": 5}, frames=0)
    mode._time = mode._cycle_seconds * 0.8
    mode.render(screen)
    stats = mode.stats()
    assert stats["stage"] == 4
    assert stats["stage_name"] == "CITIES"
    assert stats["year"] == pytest.approx(96, abs=1)
    assert stats["progress"] == pytest.approx(0.8, abs=0.01)


def test_start_stage_enters_on_the_requested_stage():
    mode, screen = make_mode((640, 360), {
        "seed": 5, "quality": "low", "start_stage": 2,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    stats = mode.stats()
    assert stats["stage"] == 2
    assert stats["stage_name"] == "ALGAE"
    assert stats["start_stage"] == 2


def test_a_crossfade_is_visible_at_a_stage_boundary():
    mode, screen = make_mode((640, 360), {"seed": 5}, frames=0)
    stage_seconds = mode._cycle_seconds / 5.0
    mode._time = stage_seconds * 0.97
    mode.render(screen)
    assert mode.error is None
    # The render path is allowed to be mid-blend; the HUD has moved on by then.
    assert mode.stats()["stage"] in (0, 1)


def test_start_stage_is_bounded_and_validated():
    mode, screen = make_mode((640, 360), {
        "seed": 5, "quality": "low", "start_stage": 5,
    }, frames=0)
    assert mode.error and "start_stage" in mode.error
    mode.render(screen)
    assert mode.error


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["biosphere", "ice", "desert"])
def test_palette_variants_render(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode._time = mode._cycle_seconds * 0.8
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 40


def test_fixed_quality_does_not_adapt_and_is_reported():
    mode, _ = make_mode((640, 360), {
        "seed": 3, "quality": "high",
    }, frames=0)
    assert mode.error is None
    assert mode._auto_quality is False
    for _ in range(100):
        mode.update(0.08)
    assert mode.stats()["quality"] == "high"
    assert mode.stats()["auto_quality"] is False


def test_auto_quality_reduces_overlay_detail_without_rebuilding_the_scene():
    mode, _ = make_mode((640, 360), {
        "seed": 3, "quality": "auto",
    }, frames=0)
    initial = mode._overlay_detail
    surfaces = list(mode._stage_scaled)
    for _ in range(80):
        mode.update(0.08)
    assert mode.stats()["auto_quality"] is True
    assert mode._overlay_detail < initial
    assert len(mode._stage_scaled) == 5
    assert mode._stage_scaled[0] is surfaces[0]


# ---------------------------------------------------------------- HUD / switches

def test_hud_can_be_minimal_or_off_and_the_timeline_can_be_hidden():
    for hud, timeline in (("minimal", True), ("off", True), ("full", False)):
        mode, screen = make_mode((640, 360), {
            "seed": 5, "quality": "low", "hud": hud,
            "show_timeline": timeline,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        assert mode.stats()["hud"] == hud
        assert mode.stats()["show_timeline"] is timeline
        assert mode.stats()["corner_clear"] is True


def test_foreground_and_lights_switches_are_accepted():
    mode, screen = make_mode((640, 360), {
        "seed": 5, "quality": "low", "show_foreground": False,
        "show_city_lights": False, "show_lighthouse": False, "mist": False,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    stats = mode.stats()
    assert stats["foreground"] is False
    assert stats["city_lights"] is False
    assert stats["lighthouse"] is False
    assert stats["mist"] is False


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"orientation": "diagonal"},
    {"cycle_seconds": 10},
    {"cycle_seconds": 1000},
    {"start_stage": -1},
    {"start_stage": 5},
    {"start_stage": 1.5},
    {"show_timeline": 1},
    {"show_city_lights": "yes"},
    {"show_lighthouse": 0},
    {"show_foreground": 1},
    {"mist": 1},
    {"seed": -1},
    {"seed": 2 ** 31},
    {"title": 42},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    cfg = dict(bad)
    cfg.setdefault("quality", "low")
    mode, screen = make_mode((640, 360), cfg, frames=0)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)
    assert mode.error


# ---------------------------------------------------------------- lifecycle

def test_resize_rebuilds_all_five_stages_and_exit_releases_them():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"})
    assert mode.error is None
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert len(mode._stage_scaled) == 5
    mode.exit()
    assert mode.manager is None
    assert mode._stage_scaled == [] and mode._stage_surfaces == []
    assert mode._hud_title is None and mode._hud is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["terraform"]
    assert spec["entrypoint"] == "modes.terraform_mode:TerraformMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "orientation", "cycle_seconds",
                "start_stage", "show_timeline", "show_city_lights",
                "show_lighthouse", "show_foreground", "mist", "seed"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"start_stage": 0}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["start_stage"].widget == "number"
    assert by_key["show_timeline"].widget == "switch"
    assert by_key["cycle_seconds"].widget == "number"


def test_the_narrow_portrait_and_vert_profiles_are_wired_and_valid():
    reg = registry()
    for profile, slot, size, preset, orientation in (
            ("configs/modes_config_narrow_horz.json", "26", (1280, 400),
             "ultrawide", "ultrawide"),
            ("configs/modes_config_portrait.json", "31", (1080, 1920),
             "portrait", "portrait"),
            ("configs/modes_config_vert.json", "70", (1080, 1920),
             "portrait", "portrait")):
        cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
        issues = validate_instance(slot, cfg, reg, base_dir=BASE_DIR)
        assert not [i for i in issues if i.is_error], issues
        mode, screen, merged = profile_mode(profile, slot, size)
        assert mode.error is None
        assert merged["orientation"] == orientation
        assert mode.stats()["preset"] == preset
        assert mode.stats()["hud"] == "full"
        assert mode.stats()["corner_clear"] is True
        assert len(set(pygame.image.tostring(screen, "RGB"))) > 40
        mode.exit()
