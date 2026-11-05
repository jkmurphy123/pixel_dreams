"""tests/test_generation_ship.py -- Generation Ship, a city in section.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * `deck_count` sets the deck lines, and the hull fills the frame at strip size;
  * the camera tracks along the hull and stops at the bow with the name resolving
    one letter at a time, then reports it in the status line;
  * a seed reproduces the modules, lights, dots and doors;
  * the palette variants change the mood without moving the hull;
  * `population_lights: false` drops the lights and dots;
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
from modes.generation_ship_mode import (                                   # noqa: E402
    GenerationShipMode,
    SHIP_NAME,
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
    mode = GenerationShipMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["generationship"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = GenerationShipMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def lap(mode) -> float:
    return 240.0 / max(0.15, mode._camera_speed)


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
    assert stats["modules"] >= 8
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_hull_fills_the_strip():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    top, height = mode.stats()["hull"]
    assert 0.35 * 400 < height < 0.75 * 400
    assert top > 0.05 * 400
    assert top + height < 0.98 * 400


def test_deck_count_sets_the_decks():
    for count in (2, 3, 5):
        mode, screen = make_mode((640, 360), {
            "seed": 5, "quality": "low", "deck_count": count,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        assert mode.stats()["decks"] == count


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_modules_the_lights_and_the_doors():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._modules == b._modules
    assert a._lights == b._lights
    assert a._dots == b._dots
    assert pixels(screen_a) == pixels(screen_b)
    assert a._lights != c._lights
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_ship_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the track and the bow

def test_the_camera_tracks_along_the_hull():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    mode._time = 0.0
    mode.render(screen)
    start = pixels(screen)
    mode._time = lap(mode) * 0.25
    mode.render(screen)
    assert pixels(screen) != start
    assert mode.stats()["scroll"] > 0.05


def test_the_bow_is_the_end_of_the_track_and_the_name_resolves_there():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    mode._time = lap(mode) * 0.85
    mode.render(screen)
    assert mode.stats()["scroll"] == pytest.approx(0.66, abs=1e-6)
    assert mode.stats()["at_bow"] is True
    assert mode.stats()["name_progress"] > 0.0
    status, alert = mode._status_text()
    assert alert is True and "BOW" in status

    # earlier in the lap the name is not showing
    mode._time = lap(mode) * 0.5
    mode.render(screen)
    assert mode.stats()["at_bow"] is False
    assert mode.stats()["name_progress"] == 0.0
    assert mode._status_text()[1] is False


def test_the_name_appears_one_letter_at_a_time():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low"}, frames=0)
    seen = []
    for fraction in (0.83, 0.88, 0.95):
        mode._time = lap(mode) * fraction
        mode.render(screen)
        progress = mode.stats()["name_progress"]
        letters = int(len(SHIP_NAME) * min(1.0, progress * 1.4))
        seen.append(letters)
    assert seen == sorted(seen)
    assert seen[-1] > seen[0]


def test_a_faster_track_shortens_the_lap():
    slow, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_speed": 1.0},
                        frames=0)
    fast, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_speed": 4.0},
                        frames=0)
    assert lap(fast) < lap(slow)


# ---------------------------------------------------------------- palette / lights

@pytest.mark.parametrize("palette", ["ice", "amber", "mono"])
def test_palette_variants_render_and_keep_the_hull(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_hull():
    frames = {}
    framing = {}
    for palette in ("ice", "amber", "mono"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["hull"]
    assert frames["ice"] != frames["amber"]
    assert frames["ice"] != frames["mono"]
    assert framing["ice"] == framing["amber"] == framing["mono"]


def test_population_lights_can_be_switched_off():
    on, screen_on = make_mode((640, 360), {"seed": 5151, "quality": "low"})
    off, screen_off = make_mode((640, 360), {"seed": 5151, "quality": "low",
                                             "population_lights": False})
    assert off.error is None
    assert off.stats()["population_lights"] is False
    assert pixels(screen_on) != pixels(screen_off)


def test_a_fixed_quality_does_not_adapt_and_the_ship_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    modules = mode._modules
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._modules is modules


def test_auto_quality_steps_the_detail_not_the_ship():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._modules, mode._lights, mode._dots)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._modules, mode._lights, mode._dots) == before


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
    {"deck_count": 1},
    {"deck_count": 6},
    {"deck_count": 3.5},
    {"camera_speed": -1},
    {"camera_speed": 20},
    {"ring_rotation": 5},
    {"ring_rotation": 900},
    {"population_lights": 1},
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
    strip_hull = mode.stats()["hull"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["hull"] != strip_hull
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._modules == [] and mode._lights == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._modules)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._modules) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["generationship"]
    assert spec["entrypoint"] == "modes.generation_ship_mode:GenerationShipMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "deck_count", "camera_speed", "ring_rotation", "population_lights",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"deck_count": 3}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["deck_count"].widget == "number"
    assert by_key["population_lights"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "38", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "42", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "82", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "24", (1920, 1080), "landscape"),
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
