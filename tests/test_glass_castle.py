"""The Glass Castle: composition, determinism, switches and wiring.

What a still cannot show, and what is worth pinning here:

  * the reviewed composition re-anchors at the strip, the portrait and 16:9;
  * the controller's lower-left 80x32 corner stays dark;
  * a seed reproduces a frame; a different seed does not;
  * a palette changes colour only, not the castle geometry;
  * aurora/snow/window switches actually remove their elements;
  * bad configs show the error panel instead of taking down the kiosk;
  * quality changes detail without moving the composition;
  * the registry schema and the new profile instances construct.

The module does not quit pygame: test_smoke owns the session's init/quit.
"""
from __future__ import annotations

import json
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
from core.params import resolve_params, validate_param_value               # noqa: E402
from core.validation import validate_instance, validate_registry           # noqa: E402
from glasscastle.layout import ORIENTATIONS                                # noqa: E402
from glasscastle.palette import PALETTE_NAMES                              # noqa: E402
from modes.glass_castle_mode import GlassCastleMode                        # noqa: E402


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


def make_mode(size=(640, 300), config=None, hud="minimal"):
    cfg = {"seed": 5130, "quality": "medium", "hud": hud,
           "camera_drift": 0.5, "shard_count": 6}
    if config:
        cfg.update(config)
    screen = pygame.Surface(size)
    mode = GlassCastleMode(cfg)
    mode.enter(FakeManager(screen))
    return mode, screen


def draw(mode, screen, time_s=15.0):
    mode._time = float(time_s)
    mode.render(screen)
    return screen


def image_bytes(screen):
    return pygame.image.tostring(screen, "RGB")


def corner_peak(screen, size):
    w, h = size
    rect = pygame.Rect(0, h - 32, min(80, w), min(32, h))
    corner = screen.subsurface(rect)
    return max(sum(corner.get_at((x, y))[:3]) / 3.0
               for x in range(0, rect.w, 4)
               for y in range(0, rect.h, 4))


# ---------------------------------------------------------------- composition

@pytest.mark.parametrize("size,layout_name", [
    ((1280, 400), "landscape"),
    ((1080, 1920), "portrait"),
])
def test_the_reviewed_stills_render_at_the_two_targets(size, layout_name):
    mode, screen = make_mode(size, {"quality": "high", "hud":
                                    "minimal" if size[0] > size[1] else "full"})
    try:
        assert mode.error is None
        stats = mode.stats()
        assert stats["layout"] == layout_name
        assert stats["shards"] == 6
        assert stats["windows"] >= 20
        assert stats["snow"] is True
        x0, y0, x1, y1 = stats["castle_bounds"]
        assert 0 <= x0 < x1 <= size[0]
        assert 0 <= y0 < y1 <= size[1]
        draw(mode, screen)
        assert len(set(image_bytes(screen))) > 40
        assert corner_peak(screen, size) < 40
    finally:
        mode.exit()


def test_16_9_uses_the_landscape_composition():
    mode, screen = make_mode((1920, 1080), {"quality": "low"})
    try:
        assert mode.error is None
        assert mode.stats()["layout"] == "landscape"
        draw(mode, screen)
        assert len(set(image_bytes(screen))) > 40
    finally:
        mode.exit()


def test_the_lower_left_corner_is_clear_at_three_aspects():
    for size in ((640, 300), (360, 640), (640, 360)):
        mode, screen = make_mode(size, {"quality": "low"})
        try:
            assert mode.error is None
            draw(mode, screen)
            assert corner_peak(screen, size) < 40, size
        finally:
            mode.exit()


# ---------------------------------------------------------------- determinism

def test_a_seed_reproduces_the_frame_and_a_different_seed_does_not():
    one, s1 = make_mode((640, 300), {"seed": 5130, "quality": "medium"})
    two, s2 = make_mode((640, 300), {"seed": 5130, "quality": "medium"})
    other, s3 = make_mode((640, 300), {"seed": 5131, "quality": "medium"})
    try:
        assert one.error is None and two.error is None and other.error is None
        a = image_bytes(draw(one, s1))
        b = image_bytes(draw(two, s2))
        c = image_bytes(draw(other, s3))
        assert a == b
        assert a != c
    finally:
        for mode in (one, two, other):
            mode.exit()


def test_unset_seed_chooses_one():
    mode, _ = make_mode((320, 200), {"seed": None, "quality": "low"})
    try:
        assert mode.error is None
        assert isinstance(mode.seed, int)
        assert 0 <= mode.seed <= 0x7FFFFFFF
    finally:
        mode.exit()


# ---------------------------------------------------------------- appearance

def test_palette_changes_mood_not_geometry():
    ice, ice_screen = make_mode((640, 300), {"palette": "ice"})
    rose, rose_screen = make_mode((640, 300), {"palette": "rose"})
    try:
        assert ice.error is None and rose.error is None
        assert ice.stats()["castle_bounds"] == rose.stats()["castle_bounds"]
        assert image_bytes(draw(ice, ice_screen)) != image_bytes(
            draw(rose, rose_screen))
    finally:
        ice.exit()
        rose.exit()


def test_switches_remove_their_elements():
    base, base_screen = make_mode((640, 300))
    plain, plain_screen = make_mode((640, 300), {
        "aurora": False, "snow": False, "window_lights": False})
    try:
        assert base.error is None and plain.error is None
        base_bytes = image_bytes(draw(base, base_screen))
        plain_bytes = image_bytes(draw(plain, plain_screen))
        assert base_bytes != plain_bytes
        assert plain.stats()["aurora"] is False
        assert plain.stats()["snow"] is False
        assert plain.stats()["snow_flakes"] == 0
        # The gate is not a window: it stays lit with window_lights off.
        assert plain.renderer.scene.windows
    finally:
        base.exit()
        plain.exit()


def test_quality_changes_detail_not_composition():
    mode, screen = make_mode((640, 300), {"quality": "medium"})
    try:
        assert mode.error is None
        bounds = mode.stats()["castle_bounds"]
        draw(mode, screen)
        for quality in ("low", "high", "medium"):
            mode.renderer.set_quality(quality)
            assert mode.stats()["quality"] == quality
            assert mode.stats()["castle_bounds"] == bounds
            draw(mode, screen)
    finally:
        mode.exit()


# ---------------------------------------------------------------- refusals

@pytest.mark.parametrize("config", [
    {"palette": "pink"},
    {"shard_count": 11},
    {"shard_count": -1},
    {"camera_drift": 3.0},
    {"reflection_strength": 2.0},
    {"window_flicker": -0.1},
    {"quality": "maximum"},
    {"hud": "loud"},
    {"orientation": "diagonal"},
    {"seed": -1},
    {"snow": "yes"},
    {"title": 7},
])
def test_bad_configs_refuse_and_draw_the_error_panel(config):
    mode, screen = make_mode((320, 200), config)
    try:
        assert mode.error
        mode.render(screen)
        assert mode.error
        assert len(set(image_bytes(screen))) > 2
    finally:
        mode.exit()


# ---------------------------------------------------------------- orientation

@pytest.mark.parametrize("size,orientation,expected", [
    ((640, 300), "auto", "landscape"),
    ((300, 640), "auto", "portrait"),
    ((640, 360), "auto", "landscape"),
    ((640, 300), "portrait", "portrait"),
    ((300, 640), "landscape", "landscape"),
])
def test_orientation_auto_and_override(size, orientation, expected):
    mode, _ = make_mode(size, {"orientation": orientation, "quality": "low",
                               "hud": "off"})
    try:
        assert mode.error is None
        assert mode.stats()["layout"] == expected
        assert mode.layout.orientation == orientation
    finally:
        mode.exit()


def test_resizing_rebuilds_the_composition():
    mode, _ = make_mode((640, 300), {"quality": "low"})
    try:
        assert mode.stats()["layout"] == "landscape"
        other = pygame.Surface((360, 640))
        mode.render(other)
        assert mode.error is None
        assert mode.stats()["layout"] == "portrait"
        assert mode.stats()["size"] == (360, 640)
    finally:
        mode.exit()


# ---------------------------------------------------------------- wiring

def test_the_registry_schema_is_complete_and_defaults_validate():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    entry = registry["types"]["glasscastle"]
    assert entry["entrypoint"] == "modes.glass_castle_mode:GlassCastleMode"
    assert validate_registry({"types": {"glasscastle": entry}},
                             check_imports=True) == []
    assert set(entry["params"]) == set(entry["optional"])
    params, warnings = resolve_params({}, entry)
    assert warnings == []
    assert {p.key for p in params} == set(entry["optional"])
    assert all(p.widget != "json" for p in params)
    for param in params:
        if param.has_default:
            assert validate_param_value(param, param.default) == [], (
                param.key, param.default)


@pytest.mark.parametrize("profile_name,slot,size,layout_name", [
    ("configs/modes_config_narrow_horz.json", "24", (640, 300), "landscape"),
    ("configs/modes_config_portrait.json", "29", (360, 640), "portrait"),
    ("modes_config.json", "36", (640, 300), "landscape"),
    ("configs/modes_config_vert.json", "68", (360, 640), "portrait"),
])
def test_profile_instances_validate_and_construct(profile_name, slot, size,
                                                  layout_name):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, profile_name), {})["modes"]
    cfg = profile[slot]
    assert cfg["type"] == "glasscastle"
    assert cfg["name"] == "The Glass Castle"
    assert validate_instance(slot, cfg, registry, base_dir=BASE_DIR) == []
    merged = build_merged_config(registry["glasscastle"], cfg)
    screen = pygame.Surface(size)
    mode = GlassCastleMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.stats()["layout"] == layout_name
    finally:
        mode.exit()


def test_hud_modes_all_render_and_off_differs_from_full():
    off, off_screen = make_mode((640, 300), {"hud": "off"})
    full, full_screen = make_mode((640, 300), {"hud": "full"})
    try:
        assert off.error is None and full.error is None
        assert image_bytes(draw(off, off_screen)) != image_bytes(
            draw(full, full_screen))
        for screen in (off_screen, full_screen):
            assert corner_peak(screen, (640, 300)) < 40
    finally:
        off.exit()
        full.exit()


def test_exit_releases_surfaces_and_renders_black():
    mode, screen = make_mode((320, 200))
    mode.exit()
    assert mode.renderer is None
    assert mode.layout is None
    mode.render(screen)
    assert screen.get_at((0, 0))[:3] == (0, 0, 0)
