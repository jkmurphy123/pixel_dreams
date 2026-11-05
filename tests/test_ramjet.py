"""tests/test_ramjet.py -- Ramjet, an engine under power.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the funnel opens ahead of the throat and the ship sits inside it;
  * a seed reproduces the dust, the wakes and the clump schedule;
  * `dust_density: 0` leaves clean space;
  * the clump event flares the core and the status line reports it;
  * the palette variants change the mood without moving the funnel;
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
from modes.ramjet_mode import RamjetMode, aspect_preset                     # noqa: E402


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
    mode = RamjetMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["ramjet"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = RamjetMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def clump_moment(mode) -> float:
    start, duration = mode._clumps[0]
    return start + duration * 0.5


def steady_moment(mode) -> float:
    return max(start + duration for start, duration in mode._clumps) + 1.0


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
    assert stats["mouth_r"] > 20
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_funnel_opens_ahead_of_the_throat():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    mx, _my = mode.stats()["mouth"]
    tx, _ty = mode.stats()["throat"]
    assert mx > tx, "the mouth is ahead of the throat"
    cx, _cy = mode.stats()["centre"]
    assert tx < cx < mx


def test_a_larger_scoop_widens_the_funnel():
    small, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "scoop_size": 0.4},
                         frames=0)
    large, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "scoop_size": 1.8},
                         frames=0)
    assert small.stats()["mouth_r"] < large.stats()["mouth_r"]


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_dust_the_wakes_and_the_clumps():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._dust == b._dust
    assert a._wakes == b._wakes
    assert a._clumps == b._clumps
    assert pixels(screen_a) == pixels(screen_b)
    assert a._dust != c._dust
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_stream_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- intake

def test_clean_space_leaves_an_empty_intake():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "dust_density": 0.0})
    assert mode.error is None
    assert mode.stats()["dust_density"] == 0.0
    assert len(set(pixels(screen))) > 30


def test_the_dust_density_changes_the_stream():
    frames = {}
    for density in (0.0, 0.6, 1.0):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "dust_density": density,
        }, frames=0)
        mode.render(screen)
        frames[density] = pixels(screen)
    assert frames[0.0] != frames[0.6] != frames[1.0]


# ---------------------------------------------------------------- the signature beat

def test_a_clump_flares_the_core_and_the_status_says_so():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._clumps, "the schedule must have clumps"

    mode._time = steady_moment(mode)
    mode.render(screen)
    assert mode.stats()["clump"] is None
    steady_core = mode.stats()["core_level"]
    assert mode._status_text()[1] is False

    mode._time = clump_moment(mode)
    mode.render(screen)
    clump = mode.stats()["clump"]
    assert clump is not None
    assert clump["level"] > 0.8
    assert mode.stats()["core_level"] > steady_core
    status, alert = mode._status_text()
    assert alert is True and "CLUMP" in status


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["vector_blue", "amber", "phosphor"])
def test_palette_variants_render_and_keep_the_funnel(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_funnel():
    frames = {}
    framing = {}
    for palette in ("vector_blue", "amber", "phosphor"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = (mode.stats()["mouth"], mode.stats()["throat"])
    assert frames["vector_blue"] != frames["amber"]
    assert frames["vector_blue"] != frames["phosphor"]
    assert framing["vector_blue"] == framing["amber"] == framing["phosphor"]


def test_a_fixed_quality_does_not_adapt_and_the_stream_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    dust = mode._dust
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._dust is dust


def test_auto_quality_steps_the_detail_not_the_stream():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._dust, mode._wakes)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._dust, mode._wakes) == before


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
    {"ship_speed": -0.1},
    {"ship_speed": 1.2},
    {"scoop_size": 0.1},
    {"scoop_size": 3},
    {"dust_density": -0.1},
    {"dust_density": 1.5},
    {"camera_offset": -0.5},
    {"camera_offset": 2},
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
    strip_mouth = mode.stats()["mouth_r"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["mouth_r"] != strip_mouth
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._dust == [] and mode._wakes == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._dust)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._dust) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["ramjet"]
    assert spec["entrypoint"] == "modes.ramjet_mode:RamjetMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "ship_speed", "scoop_size", "dust_density", "camera_offset",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"scoop_size": 1.0}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["scoop_size"].widget == "number"
    assert by_key["dust_density"].widget == "number"
    assert by_key["camera_offset"].widget == "number"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "40", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "44", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "84", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "26", (1920, 1080), "landscape"),
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
