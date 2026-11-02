"""tests/test_orbital_mirror_array.py -- Orbital Mirror Array, the night-side focus.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the limb sits low in the frame and the focus sits where `focus` says, on
    every aspect;
  * a seed reproduces the field, the city and the lock-loss schedule exactly;
  * the signature beat exists: a sail loses lock, its beam leaves the focus and
    the city dims, then it comes back;
  * the palette variants change the mood without moving the limb or the focus;
  * the quality tiers cap the drawn sails and `auto` never rebuilds the field;
  * the camera's glide is periodic, so a wall left running for a week cannot
    slide out of the array;
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
from modes.orbital_mirror_array_mode import (                              # noqa: E402
    OrbitalMirrorArrayMode,
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
    mode = OrbitalMirrorArrayMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["orbitalmirrorarray"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = OrbitalMirrorArrayMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def lock_moment(mode) -> float:
    """A time in the first lock loss, at its worst."""
    start, duration, _index = mode._locks[0]
    return start + duration * 0.45


def nominal_moment(mode) -> float:
    """A time with every lock held: past the last window of the first cycle."""
    return max(start + duration for start, duration, _index in mode._locks) + 1.0


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
    assert stats["mirrors"] > 8
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_limb_runs_low_and_the_focus_lands_where_it_is_asked():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low", "focus": 0.6},
                        frames=0)
    assert mode.error is None
    assert 0.72 * 400 < mode.stats()["limb_y"] < 0.92 * 400
    # the limb curves down toward the corners: the apex is the middle
    assert mode._limb_y(640) < mode._limb_y(60)
    target = mode._focus_target(0.0)
    assert target == pytest.approx(0.6 * 1280, abs=0.02 * 1280)


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_field_the_city_and_the_locks():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._mirrors == b._mirrors
    assert a._locks == b._locks
    assert a._city == b._city
    assert pixels(screen_a) == pixels(screen_b)
    assert a._mirrors != c._mirrors
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_array_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the signature beat

def test_a_sail_loses_lock_and_the_city_dips():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._locks, "the schedule must have lock losses"
    mode._time = nominal_moment(mode)
    mode.render(screen)
    nominal = mode.stats()["focus_percent"]
    assert mode.stats()["lock"] is None

    mode._time = lock_moment(mode)
    mode.render(screen)
    lock = mode.stats()["lock"]
    assert lock is not None
    assert 0.0 < lock["severity"] <= 1.0
    assert mode.stats()["focus_percent"] < nominal - 2.0, "the focus readout must dip"


def test_the_focus_target_drifts_while_the_lock_is_lost():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    mode._time = nominal_moment(mode)
    assert mode._lock_state() is None
    normal = mode._focus_target(mode._time)

    mode._time = lock_moment(mode)
    mode._lock = mode._lock_state()
    assert mode._lock is not None
    drifting = mode._focus_target(mode._time)
    assert abs(drifting - normal) > 0.02 * 640, "the beam must leave the focus"


def test_the_lock_schedule_repeats_over_a_pinned_span():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    assert len(mode._locks) == 8
    assert mode._lock_span > 0.0
    starts = [start for start, _duration, _index in mode._locks]
    assert starts == sorted(starts)


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["ice", "amber", "vector_blue"])
def test_palette_variants_render_and_keep_the_framing(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_limb_or_the_focus():
    frames = {}
    framing = {}
    for palette in ("ice", "vector_blue", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = (mode.stats()["limb_y"], mode._focus_target(0.0))
    assert frames["ice"] != frames["amber"]
    assert frames["ice"] != frames["vector_blue"]
    assert framing["ice"] == framing["vector_blue"] == framing["amber"]


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_the_quality_tier_caps_the_drawn_sails(quality):
    mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality})
    assert mode.error is None
    stats = mode.stats()
    assert stats["quality"] == quality
    assert stats["mirror_cap"] == QUALITY[quality]["mirrors"]
    assert stats["mirrors"] <= QUALITY[quality]["mirrors"]
    assert len(mode._tier_indices[quality]) <= QUALITY[quality]["mirrors"]


def test_a_fixed_quality_does_not_adapt_and_the_field_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    mirrors = mode._mirrors
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._mirrors is mirrors


def test_auto_quality_steps_the_detail_not_the_field():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._mirrors, mode._locks, mode._city)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._mirrors, mode._locks, mode._city) == before


# ---------------------------------------------------------------- camera

def test_the_camera_glide_is_periodic_not_a_runaway():
    mode, _ = make_mode((1280, 400), {"seed": 5, "quality": "low", "camera_drift": 2.0},
                        frames=0)
    mode._time = 0.0
    start = mode._camera_offset()
    mode._time = 300.0
    assert mode._camera_offset() == pytest.approx(start, abs=1e-6)
    mode._time = 86400.0
    assert abs(mode._camera_offset()) <= 1280 * 0.030 * 2.0 + 0.001


def test_zero_drift_holds_the_camera_still():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_drift": 0.0},
                        frames=0)
    mode._time = 0.0
    assert mode._camera_offset() == 0.0
    mode._time = 137.0
    assert mode._camera_offset() == 0.0


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


def test_no_beams_leaves_a_complete_mirror_scene():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "beam_strength": 0.0,
    })
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["beam_strength"] == 0.0
    assert mode.stats()["mirrors"] > 8


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"mirror_count": 5},
    {"mirror_count": 120},
    {"mirror_count": 12.5},
    {"focus": -0.1},
    {"focus": 1.5},
    {"beam_strength": 2},
    {"beam_strength": -0.5},
    {"camera_drift": -1},
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

def test_resize_recomposes_natively_and_exit_releases_the_surfaces():
    mode, _ = make_mode((1280, 400), {"seed": 7, "quality": "low"})
    assert mode.error is None
    strip_limb = mode.stats()["limb_y"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["limb_y"] != strip_limb
    mode.exit()
    assert mode.manager is None
    assert mode._background is None and mode._planet is None
    assert mode._mirrors == [] and mode._city == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._mirrors)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._mirrors) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["orbitalmirrorarray"]
    assert spec["entrypoint"] == "modes.orbital_mirror_array_mode:OrbitalMirrorArrayMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "mirror_count", "focus", "beam_strength", "camera_drift",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"mirror_count": 47}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["mirror_count"].widget == "number"
    assert by_key["focus"].widget == "number"
    assert by_key["fill"].widget == "choice"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "30", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "35", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "74", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "17", (1920, 1080), "landscape"),
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
