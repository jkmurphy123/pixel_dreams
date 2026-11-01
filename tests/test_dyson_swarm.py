"""tests/test_dyson_swarm.py -- Dyson Swarm, the star inside a collector swarm.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * a seed reproduces the swarm and the transit schedule exactly, and a
    different seed gives a different one;
  * the transit beat exists, dims the star and puts a sail across it, and
    `transit_chance: 0` removes it entirely;
  * the palette variants change the mood without moving the star, so the
    composition is the same picture in three colour families;
  * the quality tiers cap the drawn sails at the tier's budget and `auto`
    never rebuilds the camera path;
  * the camera's drift is periodic, so a wall left running for a week cannot
    park the camera outside the swarm;
  * bad values are refused once, and the error panel draws;
  * the registry entry resolves and all four shipped profile instances are
    valid and build through `build_merged_config`.

Most cases use quality="low": the tests are about the contract, not the frame
time, and the swarm table is the same at every tier.
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
from modes.dyson_swarm_mode import (                                       # noqa: E402
    DysonSwarmMode,
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
    mode = DysonSwarmMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["dysonswarm"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = DysonSwarmMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def mid_transit(mode) -> float:
    """A time inside the first transit window, at its most legible moment."""
    start, duration, _index = mode._transits[0]
    return start + duration * 0.5


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
    assert stats["sails"] > 40
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_star_is_composed_off_centre_on_the_strip():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"})
    star_x, star_y = mode.stats()["star"][0]
    assert 0.25 * 1280 < star_x < 0.55 * 1280
    assert 0.30 * 400 < star_y < 0.62 * 400


def test_each_aspect_gets_its_own_camera_not_a_crop():
    strip, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"})
    portrait, _ = make_mode((1080, 1920), {"seed": 5151, "quality": "low"})
    assert strip._layout["dist"] != portrait._layout["dist"]
    assert strip.stats()["star"][1] != portrait.stats()["star"][1]
    # portrait stacks the subject above the guide; the strip keeps it mid-height
    assert portrait.stats()["star"][0][1] / 1920 < strip.stats()["star"][0][1] / 400


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_swarm_and_the_transit_schedule():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a.seed == b.seed == 99
    assert a._collectors == b._collectors
    assert a._transits == b._transits
    assert a._hero == b._hero
    assert pixels(screen_a) == pixels(screen_b)
    assert a._collectors != c._collectors
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_swarm_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the transit beat

def test_a_transit_dims_the_star_and_puts_a_sail_across_it():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._transits, "a 0.5/min chance must schedule transits"
    assert mode.stats()["transit"] is None

    mode._time = mid_transit(mode)
    mode.render(screen)
    transit = mode.stats()["transit"]
    assert transit is not None
    assert 0.0 < transit["progress"] < 1.0
    assert 15.0 <= transit["duration"] <= 30.0
    assert mode._star_surface.get_alpha() < 255, "the eclipse must dim the disc"


def test_transit_chance_zero_removes_the_beat():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "transit_chance": 0.0,
    }, frames=0)
    assert mode.error is None
    assert mode._transits == []
    mode._time = 600.0
    mode.render(screen)
    assert mode.stats()["transit"] is None
    assert mode._star_surface.get_alpha() == 255


def test_transits_repeat_over_a_pinned_span():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    assert len(mode._transits) == 8
    assert mode._transit_span > 0.0
    starts = [start for start, _duration, _index in mode._transits]
    assert starts == sorted(starts), "the windows are in time order"


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["vector_blue", "amber", "ice"])
def test_palette_variants_render_and_keep_the_layout(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_composition():
    frames = {}
    for palette in ("vector_blue", "ice", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        star = mode.stats()["star"]
        if palette == "vector_blue":
            reference_star = star
        else:
            assert star[0] == pytest.approx(reference_star[0])
            assert star[1] == pytest.approx(reference_star[1])
    assert frames["vector_blue"] != frames["ice"]
    assert frames["vector_blue"] != frames["amber"]


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_the_quality_tier_caps_the_drawn_sails(quality):
    mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality})
    assert mode.error is None
    stats = mode.stats()
    assert stats["quality"] == quality
    assert stats["sail_cap"] == QUALITY[quality]["sails"]
    assert stats["sails"] <= QUALITY[quality]["sails"]
    assert abs(mode._star_r - mode._star_nominal_r) < 1.5   # int-truncated cache


def test_a_fixed_quality_does_not_adapt_and_the_scene_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    collectors = mode._collectors
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._collectors is collectors


def test_auto_quality_steps_the_detail_not_the_camera():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    start_quality = mode.stats()["quality"]
    for _ in range(120):
        mode.update(0.2)                        # 24s of very slow frames
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] != "high"
    assert mode.stats()["quality"] in ("low", "medium")
    assert mode._collectors                      # the table survives a tier change
    assert mode._hero is not None
    assert start_quality in ("low", "medium", "high")


# ---------------------------------------------------------------- camera

def test_the_camera_drift_is_periodic_not_a_runaway():
    mode, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "camera_drift": 2.0},
                        frames=0)
    mode._time = 0.0
    start = mode._camera_now()
    mode._time = 300.0                          # one drift period
    again = mode._camera_now()
    assert again == pytest.approx(start, abs=1e-6)

    mode._time = 86400.0                        # a wall left running for a day
    late = mode._camera_now()
    assert abs(late[0] - mode._cam_pos[0]) < 0.6
    assert abs(late[2] - mode._cam_pos[2]) < 0.05


def test_zero_drift_holds_the_camera_still():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_drift": 0.0},
                        frames=0)
    mode._time = 0.0
    first = mode._camera_now()
    mode._time = 97.0
    assert mode._camera_now() == first


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


def test_scanlines_and_vignette_can_be_switched_off():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "scanline_alpha": 0, "vignette_strength": 0.0,
    })
    assert mode.error is None
    assert mode._finish is None
    mode.render(screen)
    assert mode.error is None


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"collector_count": 10},
    {"collector_count": 9000},
    {"collector_count": 12.5},
    {"shells": 0},
    {"shells": 5},
    {"orbit_seconds": 10},
    {"orbit_seconds": 1000},
    {"transit_chance": -1},
    {"transit_chance": 9},
    {"camera_drift": -0.5},
    {"camera_drift": 9},
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

def test_resize_rebuilds_natively_and_exit_releases_the_surfaces():
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
    assert mode._background is None and mode._star_surface is None
    assert mode._collectors == [] and mode._foreground == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._collectors)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._collectors) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["dysonswarm"]
    assert spec["entrypoint"] == "modes.dyson_swarm_mode:DysonSwarmMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "collector_count", "shells", "orbit_seconds", "transit_chance",
                "camera_drift", "glow_strength", "scanline_alpha",
                "vignette_strength", "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"collector_count": 900}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["collector_count"].widget == "number"
    assert by_key["transit_chance"].widget == "number"
    assert by_key["fill"].widget == "choice"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "27", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "32", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "71", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "14", (1920, 1080), "landscape"),
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
