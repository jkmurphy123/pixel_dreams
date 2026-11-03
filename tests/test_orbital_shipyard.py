"""tests/test_orbital_shipyard.py -- Orbital Shipyard, a hull under construction.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * `hull_stage` controls how much of the ship exists: 0 is a bare keel, 1 is a
    hulled ship, and the number of unlocked sections follows it;
  * a seed reproduces the ribs, the arches, the arms and the keel-lock schedule;
  * the signature beat exists: a keel lock travels the spine and the status says so;
  * the palette variants change the mood without moving the berth;
  * `sparks: false` empties the weld particles;
  * the camera's crane is periodic over 120 s and `camera_crane: 0` holds it;
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
from modes.orbital_shipyard_mode import (                                  # noqa: E402
    OrbitalShipyardMode,
    QUALITY,
    SECTIONS,
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
    mode = OrbitalShipyardMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["orbitalshipyard"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = OrbitalShipyardMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def lock_moment(mode) -> float:
    start, duration, _section = mode._locks[0]
    return start + duration * 0.4


def nominal_moment(mode) -> float:
    return max(start + duration for start, duration, _section in mode._locks) + 1.0


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
    assert stats["hull_percent"] == 62
    assert stats["sections_unlocked"] == 7
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_berth_sits_across_the_middle_of_the_frame():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    cx, cy = mode.stats()["centre"]
    assert 0.35 * 1280 < cx < 0.65 * 1280
    assert 0.40 * 400 < cy < 0.75 * 400
    assert mode.stats()["length"] > 0.5 * 1280


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- the stage

def test_the_hull_stage_controls_how_much_ship_exists():
    for stage, expected in ((0.0, 0), (0.5, 6), (1.0, SECTIONS)):
        mode, screen = make_mode((640, 360), {
            "seed": 5, "quality": "low", "hull_stage": stage,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        stats = mode.stats()
        assert stats["hull_percent"] == int(round(stage * 100))
        assert stats["sections_unlocked"] == expected


def test_a_low_stage_leaves_the_keel_and_the_gantry():
    bare, screen_bare = make_mode((640, 360), {"seed": 5, "quality": "low",
                                               "hull_stage": 0.0})
    full, screen_full = make_mode((640, 360), {"seed": 5, "quality": "low",
                                               "hull_stage": 1.0})
    assert bare.error is None and full.error is None
    assert pixels(screen_bare) != pixels(screen_full)
    assert len(set(pixels(screen_bare))) > 30


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_ribs_the_arches_and_the_schedule():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._sections == b._sections
    assert a._posts == b._posts
    assert a._arms == b._arms
    assert a._locks == b._locks
    assert pixels(screen_a) == pixels(screen_b)
    assert a._arms != c._arms
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_berth_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the signature beat

def test_the_keel_locks_and_the_status_reports_it():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._locks, "the schedule must have keel locks"

    mode._time = nominal_moment(mode)
    mode.render(screen)
    assert mode.stats()["lock"] is None
    assert mode._status_text()[1] is False

    mode._time = lock_moment(mode)
    mode.render(screen)
    lock = mode.stats()["lock"]
    assert lock is not None
    assert 0.0 < lock["severity"] <= 1.0
    status, alert = mode._status_text()
    assert alert is True and "KEEL LOCK" in status


def test_the_lock_schedule_repeats_over_a_pinned_span():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    assert len(mode._locks) == 6
    assert mode._lock_span > 0.0
    starts = [start for start, _duration, _section in mode._locks]
    assert starts == sorted(starts)


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["amber", "vector_blue", "mono"])
def test_palette_variants_render_and_keep_the_berth(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_berth():
    frames = {}
    framing = {}
    for palette in ("amber", "vector_blue", "mono"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["centre"]
    assert frames["amber"] != frames["vector_blue"]
    assert frames["amber"] != frames["mono"]
    assert framing["amber"] == framing["vector_blue"] == framing["mono"]


def test_sparks_can_be_switched_off():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "sparks": False, "arm_count": 8,
    })
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["sparks"] == 0


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_the_quality_tier_sets_the_arm_budget(quality):
    mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality,
                                           "arm_count": 10})
    assert mode.error is None
    assert mode.stats()["quality"] == quality
    assert QUALITY[quality]["arms"] <= 10


def test_a_fixed_quality_does_not_adapt_and_the_berth_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    arms = mode._arms
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._arms is arms


def test_auto_quality_steps_the_detail_not_the_berth():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._sections, mode._posts, mode._arms, mode._locks)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._sections, mode._posts, mode._arms, mode._locks) == before


# ---------------------------------------------------------------- camera

def test_the_camera_crane_is_periodic_and_zero_holds_it():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_crane": 2.0},
                        frames=0)
    mode._time = 0.0
    start = mode._camera_angle()
    mode._time = 30.0
    assert abs(mode._camera_angle() - start) > 1e-4
    mode._time = 120.0
    assert mode._camera_angle() == pytest.approx(start, abs=1e-9)

    still, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_crane": 0.0},
                         frames=0)
    still._time = 0.0
    base = still._camera_angle()
    still._time = 37.0
    assert still._camera_angle() == pytest.approx(base, abs=1e-9)


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
    {"hull_stage": -0.1},
    {"hull_stage": 1.5},
    {"arm_count": 1},
    {"arm_count": 12},
    {"arm_count": 6.5},
    {"camera_crane": -1},
    {"camera_crane": 9},
    {"sparks": 1},
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
    strip = mode.stats()["centre"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["centre"] != strip
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._sections == [] and mode._arms == [] and mode._posts == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._arms)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._arms) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["orbitalshipyard"]
    assert spec["entrypoint"] == "modes.orbital_shipyard_mode:OrbitalShipyardMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "hull_stage", "arm_count", "camera_crane", "sparks",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"hull_stage": 0.62}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["hull_stage"].widget == "number"
    assert by_key["arm_count"].widget == "number"
    assert by_key["sparks"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "34", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "39", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "78", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "21", (1920, 1080), "landscape"),
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
