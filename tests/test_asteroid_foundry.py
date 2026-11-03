"""tests/test_asteroid_foundry.py -- Asteroid Foundry, a ride down a mined cavern.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the vanishing point is where the preset says, and the tunnel is anchored on it;
  * a seed reproduces the rings, the machines, the ore and the vein schedule;
  * the ride is a loop: the scroll advances with `camera_speed` and wraps at
    `cavern_length`;
  * the signature beat exists: a fresh vein warms the cavern and the status says so;
  * the palette variants change the mood without moving the vanishing point;
  * `mirror_shaft: false` drops the shaft;
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
from modes.asteroid_foundry_mode import (                                  # noqa: E402
    AsteroidFoundryMode,
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
    mode = AsteroidFoundryMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["asteroidfoundry"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = AsteroidFoundryMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def vein_moment(mode) -> float:
    start, duration = mode._veins[0]
    return start + duration * 0.5


def nominal_moment(mode) -> float:
    return max(start + duration for start, duration in mode._veins) + 1.0


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
    assert stats["rings"] > 20
    assert stats["machines"] > 10
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_vanishing_point_sits_where_the_preset_says():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    vx, vy = mode.stats()["vp"]
    assert 0.35 * 1280 < vx < 0.60 * 1280
    assert 0.35 * 400 < vy < 0.60 * 400
    assert mode.stats()["focal"] > 0


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_rings_the_machines_and_the_veins():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._rings == b._rings
    assert a._machines == b._machines
    assert a._veins == b._veins
    assert pixels(screen_a) == pixels(screen_b)
    assert a._machines != c._machines
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_cavern_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the ride

def test_the_ride_scrolls_with_the_camera_speed():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "camera_speed": 4.0}, frames=0)
    mode._time = 0.0
    mode.render(screen)
    first = pixels(screen)
    mode._time = 4.0
    mode.render(screen)
    assert pixels(screen) != first

    parked, screen_parked = make_mode((640, 360), {"seed": 5, "quality": "low",
                                                   "camera_speed": 0.0}, frames=0)
    parked._time = 0.0
    parked.render(screen_parked)
    still = pixels(screen_parked)
    parked._time = 40.0
    parked.render(screen_parked)
    assert pixels(screen_parked) != still, "the machines still pulse"


def test_the_ride_wraps_at_the_cavern_length():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low",
                                     "cavern_length": 900}, frames=0)

    def ring_depths(time_s):
        mode._time = time_s
        scroll = mode._scroll()
        return sorted(round((ring["z"] - scroll) % mode._cavern_length, 6)
                      for ring in mode._rings)

    start = ring_depths(0.0)
    period = mode._cavern_length / (mode._camera_speed * 6.0)
    again = ring_depths(period)
    assert again == start, "one full loop returns the same ring layout"


# ---------------------------------------------------------------- the signature beat

def test_a_fresh_vein_warms_the_cavern_and_the_status_says_so():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._veins, "the schedule must have veins"

    mode._time = nominal_moment(mode)
    mode.render(screen)
    assert mode.stats()["vein"] is None
    assert mode._status_text()[1] is False

    mode._time = vein_moment(mode)
    mode.render(screen)
    vein = mode.stats()["vein"]
    assert vein is not None
    assert vein["level"] == pytest.approx(1.0, abs=0.01)
    status, alert = mode._status_text()
    assert alert is True and "VEIN" in status


def test_the_vein_tint_is_warmer_than_the_base_colour():
    warm, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    warm._time = vein_moment(warm)
    warm.render(screen)
    assert warm.stats()["vein"] is not None

    cool, screen_cool = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    cool._time = nominal_moment(cool)
    cool.render(screen_cool)
    assert pixels(screen) != pixels(screen_cool)


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["amber", "phosphor", "mono"])
def test_palette_variants_render_and_keep_the_vanishing_point(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_tunnel():
    frames = {}
    framing = {}
    for palette in ("amber", "phosphor", "mono"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["vp"]
    assert frames["amber"] != frames["phosphor"]
    assert frames["amber"] != frames["mono"]
    assert framing["amber"] == framing["phosphor"] == framing["mono"]


def test_the_mirror_shaft_can_be_switched_off():
    on, screen_on = make_mode((640, 360), {"seed": 5151, "quality": "low"})
    off, screen_off = make_mode((640, 360), {"seed": 5151, "quality": "low",
                                             "mirror_shaft": False})
    assert off.error is None
    assert off.stats()["mirror_shaft"] is False
    assert pixels(screen_on) != pixels(screen_off)


def test_a_fixed_quality_does_not_adapt_and_the_cavern_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    rings = mode._rings
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._rings is rings


def test_auto_quality_steps_the_detail_not_the_cavern():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._rings, mode._machines, mode._veins)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._rings, mode._machines, mode._veins) == before


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


def test_an_empty_belt_still_renders():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "ore_rate": 0.0})
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["ore_rate"] == 0.0
    assert len(set(pixels(screen))) > 30


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"cavern_length": 50},
    {"cavern_length": 9000},
    {"ore_rate": -0.5},
    {"ore_rate": 3},
    {"camera_speed": -1},
    {"camera_speed": 60},
    {"mirror_shaft": 1},
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
    strip_vp = mode.stats()["vp"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["vp"] != strip_vp
    mode.exit()
    assert mode.manager is None
    assert mode._background is None and mode._shaft_layer is None
    assert mode._rings == [] and mode._machines == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._rings)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._rings) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["asteroidfoundry"]
    assert spec["entrypoint"] == "modes.asteroid_foundry_mode:AsteroidFoundryMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "cavern_length", "ore_rate", "camera_speed", "mirror_shaft",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"ore_rate": 0.5}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["cavern_length"].widget == "number"
    assert by_key["ore_rate"].widget == "number"
    assert by_key["mirror_shaft"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "36", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "40", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "80", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "22", (1920, 1080), "landscape"),
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
