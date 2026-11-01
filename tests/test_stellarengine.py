"""tests/test_stellarengine.py -- Stellar Engine, the star-with-mirror engine.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * a seed reproduces the exact still; a different seed gives a different one;
  * the mirror mesh, truss, starfield and dust all derive from the seed;
  * the palette variants and the quality settings are accepted without
    changing the composition;
  * the signature keys (mirror_span, precession_seconds, beam_width, show_star)
    are accepted, and beam_width 0 removes the beam;
  * bad values are refused once, and the error panel draws;
  * the registry entry resolves and the four shipped profile instances
    (narrow 28, portrait 33, vert 72, landscape 15) are valid and build through
    build_merged_config.

Most cases use quality="low": the mirror mesh and the star surface are cached
on entry, and the tests do not need the finest facet count.
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
from modes.stellar_engine_mode import StellarEngineMode, aspect_preset     # noqa: E402


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
    mode = StellarEngineMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["stellarengine"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = StellarEngineMode(merged)
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
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    # A composed frame has real tonal range: more than a flat fill.
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 40


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_exact_still():
    a, screen_a = make_mode((640, 360), {"seed": 99, "quality": "low"}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99, "quality": "low"}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed == b.seed == 99
    assert a._mirror_grid == b._mirror_grid
    assert a._truss == b._truss
    assert a._dust == b._dust
    # Pinned time -> pinned pixels.
    for mode, screen in ((a, screen_a), (b, screen_b)):
        mode._time = 12.5
        mode.render(screen)
    assert pygame.image.tostring(screen_a, "RGB") == pygame.image.tostring(screen_b, "RGB")


def test_a_different_seed_gives_a_different_scene():
    a, _ = make_mode((640, 360), {"seed": 100, "quality": "low"}, frames=0)
    b, _ = make_mode((640, 360), {"seed": 101, "quality": "low"}, frames=0)
    assert a.error is None and b.error is None
    assert a._dust != b._dust or a._convection != b._convection


# ---------------------------------------------------------------- palette / quality

@pytest.mark.parametrize("palette", ["amber", "vector_blue", "mono"])
def test_palette_variants_render(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 40


@pytest.mark.parametrize("quality", ["auto", "low", "medium", "high"])
def test_quality_variants_are_accepted(quality):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": quality,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["quality"] in ("auto", "low", "medium", "high")


def test_fixed_quality_does_not_adapt_and_is_reported():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "high"}, frames=0)
    assert mode.error is None
    assert mode._auto_quality is False
    for _ in range(100):
        mode.update(0.08)
    assert mode.stats()["quality"] == "high"
    assert mode.stats()["auto_quality"] is False


# ---------------------------------------------------------------- signature keys

def test_signature_parameters_are_accepted():
    mode, screen = make_mode((640, 360), {
        "seed": 5, "quality": "low",
        "mirror_span": 0.9, "precession_seconds": 240,
        "beam_width": 0.6, "show_star": False,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    stats = mode.stats()
    assert stats["mirror_span"] == 0.9
    assert stats["precession_seconds"] == 240
    assert stats["beam_width"] == 0.6
    assert stats["show_star"] is False


def test_beam_width_zero_removes_the_beam():
    mode, screen = make_mode((640, 360), {
        "seed": 5, "quality": "low", "beam_width": 0.0,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["beam_width"] == 0.0


def test_hud_can_be_minimal_or_off():
    for hud in ("minimal", "off", "full"):
        mode, screen = make_mode((640, 360), {
            "seed": 5, "quality": "low", "hud": hud,
        }, frames=0)
        assert mode.error is None
        mode.render(screen)
        assert mode.stats()["hud"] == hud
        assert mode.stats()["corner_clear"] is True


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"mirror_span": 0.1},
    {"mirror_span": 2.0},
    {"precession_seconds": 10},
    {"precession_seconds": 1000},
    {"beam_width": -0.5},
    {"beam_width": 9.0},
    {"show_star": 1},
    {"glow_strength": 1.5},
    {"scanline_alpha": 100},
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

def test_resize_rebuilds_and_exit_releases_surfaces():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"})
    assert mode.error is None
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    mode.exit()
    assert mode.manager is None
    assert mode._mirror_grid == [] and mode._rim_pts == [] and mode._truss == []
    assert mode._star_surface is None and mode._background is None
    assert mode._bloom is None and mode._finish is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["stellarengine"]
    assert spec["entrypoint"] == "modes.stellar_engine_mode:StellarEngineMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "seed", "glow_strength",
                "scanline_alpha", "mirror_span", "precession_seconds",
                "beam_width", "show_star", "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, warnings = resolve_params({"mirror_span": 0.7}, spec)
    assert not [w for w in warnings if "not declared" in w]
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["mirror_span"].widget == "number"
    assert by_key["precession_seconds"].widget == "number"
    assert by_key["show_star"].widget == "switch"
    assert by_key["quality"].widget == "choice"


def test_the_four_profiles_are_wired_and_valid():
    reg = registry()
    for profile, slot, size, preset in (
            ("configs/modes_config_narrow_horz.json", "28", (1280, 400), "ultrawide"),
            ("configs/modes_config_portrait.json", "33", (1080, 1920), "portrait"),
            ("configs/modes_config_vert.json", "72", (1080, 1920), "portrait"),
            ("configs/modes_config_landscape.json", "15", (1920, 1080), "landscape")):
        cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
        issues = validate_instance(slot, cfg, reg, base_dir=BASE_DIR)
        assert not [i for i in issues if i.is_error], issues
        mode, screen, merged = profile_mode(profile, slot, size)
        assert mode.error is None
        assert mode.stats()["preset"] == preset
        assert mode.stats()["corner_clear"] is True
        assert len(set(pygame.image.tostring(screen, "RGB"))) > 40
        mode.exit()
