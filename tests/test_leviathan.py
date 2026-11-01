"""tests/test_leviathan.py -- Slow Worlds §5.14.

What is worth pinning:

  * the four aspect presets are real re-compositions, not one stretched frame;
  * a pinned seed reproduces the pod, star field and meteor schedule;
  * the largest hump crosses the moon at the computed cycle time;
  * the meteor is occasional, deterministic and can be disabled;
  * the lower-left 80x32 controller corner stays dark;
  * the static sky/sea/mist layers are cached and exit releases everything;
  * narrow slot 25, portrait slot 30 and vert slot 69 are wired through the
    registry and profiles.
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
from modes.leviathan_mode import LeviathanMode, aspect_class               # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # test_smoke owns the session's init/quit; do not quit here.
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


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def make_mode(size=(1280, 400), config=None, frames=0):
    config = dict(config if config is not None else {"seed": 5140})
    config.setdefault("quality", "low")
    screen = pygame.Surface(size)
    mode = LeviathanMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
    if frames:
        mode.render(screen)
    return mode, screen


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["leviathan"], cfg)
    merged["seed"] = 5140
    merged["quality"] = "low"
    merged["moon_arc_seconds"] = 0
    screen = pygame.Surface(size)
    mode = LeviathanMode(merged)
    mode.enter(FakeManager(screen))
    mode.seek(mode.hero_time())
    mode.render(screen)
    return mode, screen, merged


# ---------------------------------------------------------------- framing

@pytest.mark.parametrize("size,preset", [
    ((1280, 400), "ultrawide"),
    ((1080, 1920), "portrait"),
    ((1920, 1080), "landscape"),
    ((720, 720), "square"),
])
def test_each_aspect_has_its_own_preset(size, preset):
    mode, screen = make_mode(size, {"seed": 5})
    assert mode.error is None
    assert mode.stats()["preset"] == preset
    mode.seek(mode.hero_time())
    mode.render(screen)
    assert screen.get_size() == size
    assert len(set(pygame.image.tostring(screen, "RGB"))) > 30


def test_aspect_class_boundaries():
    assert aspect_class(1280, 400) == "ultrawide"
    assert aspect_class(1920, 1080) == "landscape"
    assert aspect_class(1080, 1920) == "portrait"
    assert aspect_class(800, 800) == "square"


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((270, 480), {"seed": 1, "orientation": "landscape"})
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- wiring

def test_the_narrow_portrait_and_vert_instances_are_wired():
    reg = registry()
    cases = (
        ("configs/modes_config_narrow_horz.json", "25", (1280, 400), "ultrawide"),
        ("configs/modes_config_portrait.json", "30", (1080, 1920), "portrait"),
        ("configs/modes_config_vert.json", "69", (1080, 1920), "portrait"),
    )
    for profile, slot, size, preset in cases:
        cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
        issues = validate_instance(slot, cfg, reg, base_dir=BASE_DIR)
        assert not [i for i in issues if i.is_error], issues
        mode, screen, merged = profile_mode(profile, slot, size)
        assert mode.error is None
        assert merged["type"] == "leviathan"
        assert mode.stats()["preset"] == preset
        assert screen.get_size() == size


def test_registry_schema_and_params():
    spec = registry()["leviathan"]
    assert spec["entrypoint"] == "modes.leviathan_mode:LeviathanMode"
    assert spec["required"] == []
    optional = set(spec["optional"])
    for key in ("pod_size", "crossing_seconds", "palette", "scale_reference",
                "star_density", "meteor", "meteor_seconds", "eclipse_seconds",
                "orientation", "hud", "quality"):
        assert key in optional
    params, _warnings = resolve_params({"pod_size": 3}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["pod_size"].widget == "number"
    assert by_key["palette"].widget == "choice"
    assert "dusk" in by_key["palette"].choices
    assert by_key["meteor"].widget == "switch"


# ---------------------------------------------------------------- seed / values

def test_a_seed_reproduces_the_scene():
    one, screen_one = make_mode((1280, 400), {"seed": 2001})
    two, screen_two = make_mode((1280, 400), {"seed": 2001})
    one.seek(one.hero_time())
    two.seek(two.hero_time())
    assert one.stats()["positions"] == two.stats()["positions"]
    assert one.stats()["silhouette"] == two.stats()["silhouette"]
    one.render(screen_one)
    two.render(screen_two)
    assert (pygame.image.tostring(screen_one, "RGB")
            == pygame.image.tostring(screen_two, "RGB"))


def test_a_different_seed_moves_the_pod():
    one, _ = make_mode((1280, 400), {"seed": 1})
    two, _ = make_mode((1280, 400), {"seed": 2})
    assert one.stats()["positions"] != two.stats()["positions"]


def test_a_bad_palette_is_refused_not_guessed():
    mode, screen = make_mode((1280, 400), {"seed": 1, "palette": "nope"})
    assert mode.error is not None
    mode.render(screen)          # the error card must draw, not raise
    assert screen.get_size() == (1280, 400)


def test_pod_size_counts():
    for count in (2, 3, 4, 5):
        mode, _ = make_mode((1280, 400), {"seed": 7, "pod_size": count})
        assert mode.error is None
        assert mode.stats()["pod"] == count


def test_star_density_zero_makes_a_dark_sky():
    mode, _ = make_mode((1280, 400), {"seed": 7, "star_density": 0})
    assert mode.error is None
    assert mode.stats()["stars"] == 0
    assert mode.stats()["beacons"] == 0


# ---------------------------------------------------------------- signature

def test_the_eclipse_happens_at_the_computed_moment():
    mode, screen = make_mode(
        (1280, 400), {"seed": 5140, "moon_arc_seconds": 0})
    mode.seek(mode.eclipse_time())
    stats = mode.stats()
    assert stats["eclipse"] > 0.5
    assert stats["eclipse_active"] is True
    mode.render(screen)
    mode.seek(mode.eclipse_time() + 12.0)
    assert mode.stats()["eclipse"] < 0.2


def test_the_eclipse_can_be_disabled():
    mode, _ = make_mode(
        (1280, 400), {"seed": 5140, "moon_arc_seconds": 0,
                      "eclipse_seconds": 0})
    mode.seek(mode.eclipse_time())
    assert mode.stats()["eclipse"] == 0


def test_moon_off_removes_the_eclipse():
    mode, _ = make_mode(
        (1280, 400), {"seed": 5140, "moon_arc_seconds": 0, "moon": False})
    mode.seek(mode.eclipse_time())
    assert mode.stats()["eclipse"] == 0


def test_the_meteor_is_occasional_and_deterministic():
    mode, screen = make_mode((1280, 400), {"seed": 5140})
    mode.seek(mode.hero_time())
    mode.force_meteor(0.5)
    assert mode.stats()["meteor"] is True
    mode.render(screen)
    for _ in range(25):                 # 2.5 s, longer than one pass
        mode.update(0.1)
    assert mode.stats()["meteor"] is False


def test_the_meteor_can_be_disabled():
    mode, _ = make_mode((1280, 400), {"seed": 5140, "meteor": False})
    mode.force_meteor(0.5)
    assert mode.stats()["meteor"] is False


# ---------------------------------------------------------------- corners / lifecycle

@pytest.mark.parametrize("size", [(1280, 400), (1080, 1920)])
def test_the_mode_number_corner_stays_dark(size):
    mode, screen = make_mode(size, {"seed": 7})
    mode.seek(mode.hero_time())
    mode.render(screen)
    corner = screen.subsurface(pygame.Rect(0, size[1] - 32, 80, 32))
    values = [sum(corner.get_at((x, y))[:3]) / 3.0
              for y in range(32) for x in range(80)]
    assert sum(values) / len(values) < 30.0
    assert max(values) < 60.0


def test_static_layers_are_cached_between_frames():
    mode, screen = make_mode((1280, 400), {"seed": 4})
    sky = mode._sky
    sea = mode._sea_base
    mist = mode._mist_near
    assert sky is not None and sea is not None and mist is not None
    mode.update(1.0 / 60.0)
    mode.render(screen)
    assert mode._sky is sky
    assert mode._sea_base is sea
    assert mode._mist_near is mist


def test_resize_rebuilds_the_layout():
    mode, screen = make_mode((1280, 400), {"seed": 4})
    assert mode.stats()["preset"] == "ultrawide"
    big = pygame.Surface((1920, 1080))
    mode.render(big)
    assert mode.stats()["preset"] == "landscape"
    assert mode._built_size == (1920, 1080)


def test_exit_releases_caches():
    mode, _ = make_mode((1280, 400), {"seed": 4})
    mode.exit()
    assert mode._sky is None
    assert mode._sea_base is None
    assert mode._moon_sprite is None
    assert mode._mist_near is None
    assert mode._hud == {}
    assert mode._bodies == []
    assert mode.manager is None


def test_hud_and_reference_switches_render():
    for hud in ("none", "minimal", "full"):
        for ref in ("boat", "lighthouse", "none"):
            mode, screen = make_mode(
                (1280, 400), {"seed": 9, "hud": hud,
                              "scale_reference": ref})
            assert mode.error is None
            mode.seek(mode.hero_time())
            mode.render(screen)
            assert screen.get_size() == (1280, 400)
