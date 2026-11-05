"""tests/test_derelict.py -- Derelict, a dead ship with one live window.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the wreck has three sections on a broken spine, and the tear is inside the hull;
  * a seed reproduces the tear, the debris and the vents;
  * `hull_damage` changes the wreck without moving it, and 0 still leaves a ship;
  * the window flickers: it is dark for some of the cycle and lit for some of it,
    and the status line reports it;
  * `debris: false` and `flicker: false` switch their elements off;
  * the camera's drift is periodic and `camera_drift: 0` holds the angle;
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
from modes.derelict_mode import DerelictMode, aspect_preset                # noqa: E402


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
    mode = DerelictMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["derelict"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = DerelictMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def window_level_at(mode, when: float) -> float:
    mode._time = when
    return mode._window_alpha()


def find_window_peak(mode) -> float:
    best, best_level = 0.0, -1.0
    for step in range(0, 400):
        t = step * 0.05
        level = window_level_at(mode, t)
        if level > best_level:
            best, best_level = t, level
    return best


def find_window_dark(mode) -> float:
    for step in range(0, 400):
        t = step * 0.05
        if window_level_at(mode, t) < 0.01:
            return t
    return 0.0


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
    assert stats["sections"] == 3
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 30


def test_the_wreck_is_a_set_of_sections_on_a_broken_spine():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    sections = mode._sections
    assert len(sections) == 3
    # bow at the right, stern at the left, the break in the middle
    assert sections[0]["x1"] > sections[1]["x1"] > sections[2]["x1"]
    # the middle section is twisted off the axis more than the others: the break
    assert abs(sections[1]["tilt"]) > abs(sections[0]["tilt"])
    assert abs(sections[1]["tilt"]) > abs(sections[2]["tilt"])


def test_the_tear_sits_inside_the_hull():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    xs = [x for x, _y in mode._tear]
    ys = [y for _x, y in mode._tear]
    assert 0.5 < sum(xs) / len(xs) < 0.72
    assert max(xs) - min(xs) < 0.25, "the tear is a hole, not a gash across the ship"
    assert max(ys) - min(ys) < 0.12


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_tear_the_debris_and_the_vents():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._tear == b._tear
    assert a._debris == b._debris
    assert a._vents == b._vents
    assert pixels(screen_a) == pixels(screen_b)
    assert a._tear != c._tear
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_wreck_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- damage

def test_hull_damage_changes_the_wreck_without_moving_it():
    frames = {}
    framing = {}
    for damage in (0.0, 0.6, 1.0):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "hull_damage": damage,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        frames[damage] = pixels(screen)
        framing[damage] = mode.stats()["centre"]
    assert frames[0.0] != frames[0.6] != frames[1.0]
    assert framing[0.0] == framing[0.6] == framing[1.0]
    # an intact ship is still a ship
    assert len(set(frames[0.0])) > 25


# ---------------------------------------------------------------- the window

def test_the_window_flickers_and_goes_dark():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    peak = find_window_peak(mode)
    dark = find_window_dark(mode)
    assert window_level_at(mode, peak) > 0.4
    assert window_level_at(mode, dark) < 0.05

    mode._time = peak
    mode.render(screen)
    assert mode.stats()["window_level"] > 0.4
    status, alert = mode._status_text()
    assert alert is True and "WINDOW" in status

    mode._time = dark
    mode.render(screen)
    assert mode.stats()["window_level"] < 0.05
    assert mode._status_text()[1] is False


def test_flicker_can_be_switched_off():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "flicker": False})
    assert mode.error is None
    mode.render(screen)
    assert mode._window_alpha() == 0.0
    assert mode.stats()["flicker"] is False


def test_debris_can_be_switched_off():
    on, screen_on = make_mode((640, 360), {"seed": 5151, "quality": "low"})
    off, screen_off = make_mode((640, 360), {"seed": 5151, "quality": "low",
                                             "debris": False})
    assert off.error is None
    assert off.stats()["debris_on"] is False
    assert pixels(screen_on) != pixels(screen_off)


# ---------------------------------------------------------------- camera

def test_the_camera_drift_is_periodic_and_zero_holds_it():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low",
                                     "camera_drift": 2.0}, frames=0)

    def drift_at(when):
        # the angle is the drift plus the wreck's own linear tumble
        mode._time = when
        return mode._camera_angle() - (2.0 * 3.141592653589793) * when / 7200.0

    start = drift_at(0.0)
    assert abs(drift_at(90.0) - start) > 1e-4
    assert drift_at(420.0) == pytest.approx(start, abs=1e-6)

    still, _ = make_mode((640, 360), {"seed": 5, "quality": "low",
                                      "camera_drift": 0.0}, frames=0)
    still._time = 0.0
    base = still._camera_angle()
    still._time = 120.0
    assert abs(still._camera_angle() - base) > 1e-4, "the wreck's own tumble keeps turning"


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["mono", "vector_blue", "amber"])
def test_palette_variants_render_and_keep_the_wreck(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 30


def test_the_palette_changes_the_mood_but_not_the_wreck():
    frames = {}
    framing = {}
    for palette in ("mono", "vector_blue", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["centre"]
    assert frames["mono"] != frames["vector_blue"]
    assert frames["mono"] != frames["amber"]
    assert framing["mono"] == framing["vector_blue"] == framing["amber"]


def test_a_fixed_quality_does_not_adapt_and_the_wreck_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    sections = mode._sections
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._sections is sections


def test_auto_quality_steps_the_detail_not_the_wreck():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._sections, mode._debris)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._sections, mode._debris) == before


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
    assert len(set(pixels(screen))) > 25


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"hull_damage": -0.1},
    {"hull_damage": 1.5},
    {"debris": 1},
    {"flicker": 1},
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
    strip_length = mode.stats()["length"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["length"] != strip_length
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._sections == [] and mode._debris == [] and mode._tear == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._debris)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._debris) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["derelict"]
    assert spec["entrypoint"] == "modes.derelict_mode:DerelictMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "hull_damage", "debris", "flicker", "camera_drift",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"hull_damage": 0.6}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["hull_damage"].widget == "number"
    assert by_key["debris"].widget == "switch"
    assert by_key["flicker"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "39", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "43", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "83", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "25", (1920, 1080), "landscape"),
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
    assert len(set(pixels(screen))) > 30
    mode.exit()
