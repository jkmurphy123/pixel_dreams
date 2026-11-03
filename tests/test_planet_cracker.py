"""tests/test_planet_cracker.py -- Planet Cracker, a world being taken apart.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the planet sits off-centre and reads at the radius the preset asks for;
  * a seed reproduces the plates, the cuts, the rigs and the separation
    schedule exactly;
  * the signature beat exists: a plate lets go and the status reports it;
  * the palette variants change the mood without moving the work site;
  * the quality tiers cap the drawn plates and `auto` never rebuilds them;
  * the camera's tilt is a 180 s arc, and `camera_orbit: 0` holds it still;
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
from modes.planet_cracker_mode import (                                    # noqa: E402
    PlanetCrackerMode,
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
    mode = PlanetCrackerMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["planetcracker"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = PlanetCrackerMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def separation_moment(mode) -> float:
    """A time inside the first separation, at its worst."""
    start, duration, _plate = mode._separations[0]
    return start + duration * 0.5


def nominal_moment(mode) -> float:
    return max(start + duration for start, duration, _plate in mode._separations) + 1.0


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
    assert stats["plates"] > 0
    assert stats["rigs"] == 8
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_work_site_sits_off_centre_and_reads_at_the_preset_radius():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    cx, cy = mode.stats()["centre"]
    assert 0.20 * 1280 < cx < 0.45 * 1280
    assert 0.35 * 400 < cy < 0.65 * 400
    assert 0.22 * 400 < mode.stats()["radius"] < 0.55 * 400


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_plates_the_cuts_and_the_rigs():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._plates == b._plates
    assert a._cuts == b._cuts
    assert a._separations == b._separations
    assert pixels(screen_a) == pixels(screen_b)
    assert a._plates != c._plates
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_work_site_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- the signature beat

def test_a_plate_lets_go_and_the_status_reports_it():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode._separations, "the schedule must have separations"

    mode._time = nominal_moment(mode)
    mode.render(screen)
    assert mode.stats()["separation"] is None
    assert mode._status_text()[1] is False

    mode._time = separation_moment(mode)
    mode.render(screen)
    separation = mode.stats()["separation"]
    assert separation is not None
    assert 0.0 < separation["severity"] <= 1.0
    status, alert = mode._status_text()
    assert alert is True and "SEPARATING" in status


def test_the_fracture_stage_puts_the_plates_further_out():
    low, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "fracture_stage": 0.0},
                       frames=0)
    high, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "fracture_stage": 1.0},
                        frames=0)
    low_drift = sum(plate["drift"] for plate in low._plates) / len(low._plates)
    high_drift = sum(plate["drift"] for plate in high._plates) / len(high._plates)
    assert high_drift > low_drift * 2.0


def test_the_separation_schedule_repeats_over_a_pinned_span():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    assert len(mode._separations) == 6
    assert mode._separation_span > 0.0
    starts = [start for start, _duration, _plate in mode._separations]
    assert starts == sorted(starts)


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["amber", "vector_blue", "mono"])
def test_palette_variants_render_and_keep_the_framing(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_work_site():
    frames = {}
    framing = {}
    for palette in ("amber", "vector_blue", "mono"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["centre"]
    assert frames["amber"] != frames["vector_blue"] != frames["mono"]
    assert framing["amber"] == framing["vector_blue"] == framing["mono"]


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_the_quality_tier_caps_the_drawn_plates(quality):
    mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality})
    assert mode.error is None
    stats = mode.stats()
    assert stats["quality"] == quality
    assert stats["plate_cap"] == QUALITY[quality]["plates"]
    assert stats["plates"] <= QUALITY[quality]["plates"]


def test_a_fixed_quality_does_not_adapt_and_the_site_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    plates = mode._plates
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._plates is plates


def test_auto_quality_steps_the_detail_not_the_site():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._plates, mode._cuts, mode._separations)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._plates, mode._cuts, mode._separations) == before


# ---------------------------------------------------------------- camera

def test_the_camera_arcs_over_180_seconds_and_zero_holds_it_still():
    mode, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_orbit": 2.0},
                        frames=0)
    mode._time = 0.0
    start_tilt = mode._camera()[2]
    mode._time = 45.0                      # the peak of the sine, not its zero crossing
    quarter = mode._camera()[2]
    mode._time = 180.0
    again = mode._camera()[2]
    assert quarter != pytest.approx(start_tilt, abs=1e-6)
    assert again == pytest.approx(start_tilt, abs=1e-6)

    still, _ = make_mode((640, 360), {"seed": 5, "quality": "low", "camera_orbit": 0.0},
                         frames=0)
    still._time = 0.0
    base = still._camera()[2]
    still._time = 90.0
    assert still._camera()[2] == pytest.approx(base, abs=1e-9)


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


def test_a_zero_drift_holds_the_plates_in_place():
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "chunk_drift": 0.0,
    })
    assert mode.error is None
    assert mode.stats()["chunk_drift"] == 0.0
    mode.render(screen)
    assert mode.stats()["plates"] > 0


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"rig_count": 2},
    {"rig_count": 20},
    {"rig_count": 8.5},
    {"fracture_stage": -0.1},
    {"fracture_stage": 1.5},
    {"chunk_drift": -1},
    {"chunk_drift": 9},
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
    assert mode._plates == [] and mode._cuts == [] and mode._rigs == []
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._plates)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._plates) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["planetcracker"]
    assert spec["entrypoint"] == "modes.planet_cracker_mode:PlanetCrackerMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "rig_count", "fracture_stage", "chunk_drift", "camera_orbit",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"rig_count": 8}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["rig_count"].widget == "number"
    assert by_key["fracture_stage"].widget == "number"
    assert by_key["fill"].widget == "choice"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "31", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "36", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "75", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "18", (1920, 1080), "landscape"),
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
