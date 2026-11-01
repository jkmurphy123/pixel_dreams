"""
tests/test_trench_run.py -- the trench-run mode and its registry/profile wiring.

The mode is a wireframe flythrough built from a seeded world, a camera preset chosen from the
screen's aspect ratio, and an adaptive quality controller. What is worth pinning here is the part
the mode cannot show on its own: that a seed reproduces a flight, that the trench is widened when
the X-wing would not fit, that a bad config shows the error panel instead of freezing, that the
quality controller reacts to real frame time, and that the world prunes chunks behind the ship.

The last two tests keep the wiring honest: the registry type must resolve with a typed schema,
and the portrait profile's slot 61 must validate with no warnings.
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
from core.loader import build_merged_config, load_entrypoint               # noqa: E402
from core.params import resolve_params, validate_param_value               # noqa: E402
from core.validation import validate_instance                              # noqa: E402
from modes.trench_run_mode import TrenchRunMode                            # noqa: E402
from trench_run.render import QUALITY_EDGE_CAPS                            # noqa: E402
from trench_run.world import TrenchWorld                                   # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # Initialise, but do NOT pygame.quit() here: a module-scoped quit tears the font module down
    # for every later module in the same session (it broke test_layout_align once). test_smoke's
    # session fixture owns init and quit.
    pygame.init()
    pygame.font.init()
    # Surface.convert() needs a video mode; set one only if nothing else has.
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


class FakeManager:
    """The minimum a mode reaches for: a surface, a font cache and its two size attributes."""

    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


DEFAULT_SIZE = (270, 480)      # portrait, small enough to keep the suite quick


def make_mode(size=DEFAULT_SIZE, config=None, frames=3):
    """Enter a mode on an off-screen surface and run a few real frames."""
    screen = pygame.Surface(size)
    mode = TrenchRunMode(dict(config or {}))
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


# ---------------------------------------------------------------- rendering and framing

@pytest.mark.parametrize("size,preset", [
    ((270, 480), "portrait"),
    ((480, 270), "landscape"),
    ((360, 360), "square"),
])
def test_the_orientation_preset_follows_the_screen_aspect(size, preset):
    mode, screen = make_mode(size, {"seed": 5, "orientation": "auto"})
    assert mode.error is None
    assert mode._projector.params.preset == preset
    stats = mode.stats()
    assert stats["objects"] > 0 and stats["segments"] > 0, stats

    # The frame is not a flat wash: wireframe, HUD and bloom all contribute colour.
    unique_bytes = len(set(pygame.image.tostring(screen, "RGB")))
    assert unique_bytes > 30, f"only {unique_bytes} byte values drawn"


def test_an_explicit_orientation_overrides_the_aspect_ratio():
    mode, _ = make_mode((270, 480), {"orientation": "landscape"})
    assert mode.error is None
    assert mode._projector.params.preset == "landscape"
    assert mode._projector.params.yaw_deg == pytest.approx(27.0)


def test_a_resize_rebuilds_the_projector_and_the_renderer():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 7})
    assert mode._projector.params.preset == "portrait"

    landscape = pygame.Surface((480, 270))
    mode.render(landscape)

    assert mode.error is None
    assert mode._screen_size == (480, 270)
    assert (mode._renderer.sw, mode._renderer.sh) == (480, 270)
    assert mode._projector.params.preset == "landscape"


def test_hud_off_leaves_the_mode_running_without_the_overlay():
    mode, screen = make_mode(DEFAULT_SIZE, {"seed": 7, "hud": "off"})
    assert mode.error is None
    assert mode._hud.mode == "off"
    # It still renders the world (a frame with no HUD is not a blank frame).
    assert mode.stats()["segments"] > 0
    mode.render(screen)
    assert mode.error is None


# ---------------------------------------------------------------- config handling

@pytest.mark.parametrize("bad", [
    {"quality": "ultra"},
    {"fill_mode": "glow"},
    {"palette": "neon"},
    {"hud": "full"},
    {"action_level": 3},
    {"trench_width": 5},
    {"scanline_alpha": 900},
    {"scroll_speed": float("nan")},
    {"show_stars": 1},
    {"seed": -1},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    mode, screen = make_mode((240, 400), bad)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)          # the error panel path, not the render path
    assert mode.error


def test_the_error_panel_is_drawn_when_the_config_is_refused():
    mode, screen = make_mode((240, 400), {"palette": "neon"})
    assert "palette" in mode.error
    assert mode.stats() == {}    # no renderer was built
    # 1px border of the panel, an exact colour from _draw_error().
    assert tuple(screen.get_at((40, 40)))[:3] == (52, 140, 210)


def test_a_narrow_trench_is_widened_to_fit_the_x_wing():
    mode, _ = make_mode(DEFAULT_SIZE,
                        {"trench_width": 18.0, "ship_scale": 1.8})
    assert mode.error is None
    assert mode._width == pytest.approx(11.0 * 1.8 + 10.0)
    assert "raised" in mode.diagnostic


# ---------------------------------------------------------------- simulation

def test_a_seed_reproduces_the_same_flight_and_world():
    a, _ = make_mode(DEFAULT_SIZE, {"seed": 99}, frames=0)
    b, _ = make_mode(DEFAULT_SIZE, {"seed": 99}, frames=0)
    for _ in range(90):
        a.update(1.0 / 60.0)
        b.update(1.0 / 60.0)

    assert a._ship.pose() == b._ship.pose()
    assert a._world.signature(0) == b._world.signature(0)

    different, _ = make_mode(DEFAULT_SIZE, {"seed": 100}, frames=0)
    for _ in range(90):
        different.update(1.0 / 60.0)
    assert different._world.signature(0) != a._world.signature(0)


def test_world_streaming_prunes_chunks_behind_the_ship():
    world = TrenchWorld(seed=3, width=28.0, depth=10.0, density=0.6)
    # Jump forward through several sectors; each ensure() must drop what is behind.
    for ship_z in (0.0, 400.0, 900.0, 2000.0, 5000.0):
        world.ensure(ship_z)

    assert world.object_count() > 0
    assert len(world.chunks) <= 40, f"{len(world.chunks)} chunks retained"
    lowest = min(world.sectors)
    assert all(chunk >= lowest * world.chunks_per_sector for chunk in world.chunks), \
        "a chunk from a pruned sector is still present"


def test_auto_quality_steps_down_when_frames_are_slow():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "auto"}, frames=0)
    assert mode._quality == "medium"
    assert mode.stats()["edge_cap"] == QUALITY_EDGE_CAPS["medium"]

    # 33 ms frames: the EMA crosses the downgrade threshold almost at once, then the 2 s timer
    # has to expire before the switch.
    for _ in range(120):
        mode.update(0.033)

    assert mode._quality == "low"
    assert mode._renderer.edge_cap == QUALITY_EDGE_CAPS["low"]
    assert "medium -> low" in mode.diagnostic


def test_a_fixed_quality_does_not_adapt():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "high"}, frames=0)
    for _ in range(120):
        mode.update(0.033)
    assert mode._quality == "high"
    assert mode._auto_quality is False
    assert mode.stats()["edge_cap"] == QUALITY_EDGE_CAPS["high"]


# ---------------------------------------------------------------- registry and profile wiring

def test_the_registry_entry_has_a_typed_schema():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    spec = registry["trenchrun"]

    assert spec["entrypoint"] == "modes.trench_run_mode:TrenchRunMode"
    assert load_entrypoint(spec["entrypoint"]) is TrenchRunMode
    assert spec["required"] == []
    assert set(spec["params"]) <= set(spec["optional"]), "a schema key is not declared"

    params, warnings = resolve_params({}, spec)
    assert warnings == []
    assert {p.key for p in params} == set(spec["optional"])
    # Every control has a real widget; nothing falls back to a raw JSON box.
    assert all(p.widget != "json" for p in params), \
        [p.key for p in params if p.widget == "json"]
    for p in params:
        if p.has_default:
            assert validate_param_value(p, p.default) == [], (p.key, p.default)


def test_the_portrait_profile_slot_61_validates_cleanly():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_vert.json"), {})
    cfg = profile["modes"]["61"]

    assert cfg["type"] == "trenchrun"
    assert cfg["orientation"] == "portrait"
    assert cfg["name"] == "Trench Run"
    assert validate_instance("61", cfg, registry, base_dir=BASE_DIR) == []


def test_the_profile_config_constructs_the_mode():
    """The real instance path: merge the registry defaults under the profile's slot 61."""
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_vert.json"), {})["modes"]
    merged = build_merged_config(registry["trenchrun"], profile["61"])

    screen = pygame.Surface(DEFAULT_SIZE)
    mode = TrenchRunMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.config["orientation"] == "portrait"
        assert mode.config["name"] == "Trench Run"
        assert mode.seed is not None
        assert mode._projector.params.preset == "portrait"
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_the_narrow_horizontal_profile_slot_17_is_tuned_for_1280x400():
    """The Pi wall is 3.2:1, so its slot lowers the camera and raises the zoom."""
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_narrow_horz.json"), {})["modes"]
    cfg = profile["17"]

    assert cfg["type"] == "trenchrun"
    assert cfg["name"] == "Trench Run"
    assert cfg["orientation"] == "landscape"
    assert cfg["hud"] == "minimal"
    assert cfg["view_pitch_deg"] < 24
    assert cfg["zoom"] > 0.85
    assert validate_instance("17", cfg, registry, base_dir=BASE_DIR) == []

    merged = build_merged_config(registry["trenchrun"], cfg)
    screen = pygame.Surface((1280, 400))
    mode = TrenchRunMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode._projector.params.preset == "landscape"
        assert (mode._projector.sw, mode._projector.sh) == (1280, 400)
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()
