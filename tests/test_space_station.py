"""
tests/test_space_station.py -- Space Station V and its registry/profile wiring.

The mode is a double-ring wireframe station over a wireframe Earth.  What is
worth pinning here is the part one frame cannot show:

  * the two habitat rings really are two rings, and the geometry gets denser
    with detail level;
  * the two clocks advance at the configured rates;
  * a seed reproduces the star field and the starting wheel angle;
  * a missing coastline file degrades to a graticule instead of a blank screen;
  * auto quality steps down on slow frames while a pinned quality does not;
  * the registry schema is typed and the profile instances construct.

The portrait profile's slot 63 and the 1280x400 kiosk's slot 19 are the real
wiring; those tests render through the merged config, not just the class.
"""

from __future__ import annotations

import json
import math
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
from modes.space_station_mode import SpaceStationMode                      # noqa: E402
from space_station.earth import EarthGeometry, load_coastlines             # noqa: E402
from space_station.palette import get_palette                              # noqa: E402
from space_station.render import QUALITY, effective_detail                 # noqa: E402
from space_station.stations import build_station                           # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # Do not quit at module scope: a quit tears the font module down for later
    # modules. test_smoke owns the session's init/quit.
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


DEFAULT_SIZE = (270, 480)


def make_mode(size=DEFAULT_SIZE, config=None, frames=2):
    screen = pygame.Surface(size)
    mode = SpaceStationMode(dict(config if config is not None
                                 else {"seed": 2001}))
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
    ((1280, 400), "ultrawide"),
])
def test_the_mode_renders_a_form_in_every_aspect(size, preset):
    mode, screen = make_mode(size, {"seed": 5})
    assert mode.error is None
    assert mode._framing.preset == preset
    stats = mode.stats()
    assert stats["segments"] > 2000, stats
    assert stats["station_segments"] > 1000, stats
    assert stats["earth_segments"] > 500, stats
    assert stats["quality"] in QUALITY
    unique = len(set(pygame.image.tostring(screen, "RGB")))
    assert unique > 30, f"only {unique} byte values drawn"


def test_an_explicit_orientation_overrides_the_aspect_ratio():
    mode, _ = make_mode((270, 480), {"orientation": "landscape"})
    assert mode.error is None
    assert mode._framing.preset == "landscape"


def test_a_resize_rebuilds_the_framing_renderer_and_hud():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 7})
    assert mode._framing.preset == "portrait"
    assert (mode.renderer.sw, mode.renderer.sh) == DEFAULT_SIZE

    landscape = pygame.Surface((480, 270))
    mode.render(landscape)

    assert mode.error is None
    assert mode._screen_size == (480, 270)
    assert mode._framing.preset == "landscape"
    assert (mode.renderer.sw, mode.renderer.sh) == (480, 270)
    assert (mode.hud.sw, mode.hud.sh) == (480, 270)


def test_hud_off_leaves_the_world_running():
    mode, screen = make_mode(DEFAULT_SIZE, {"seed": 7, "hud": "off"})
    assert mode.error is None
    assert mode.hud.mode == "off"
    assert mode.stats()["segments"] > 1000
    mode.render(screen)
    assert mode.error is None


def test_exit_releases_every_surface_and_reference():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 7})
    mode.exit()
    assert mode.manager is None
    assert mode.renderer is None and mode.hud is None and mode._framing is None
    assert mode._screen_size is None


# ---------------------------------------------------------------- config handling

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"orientation": "diagonal"},
    {"station_detail": 0},
    {"station_detail": 5},
    {"station_detail": 2.5},
    {"station_spin_rpm": -1.0},
    {"station_spin_rpm": float("nan")},
    {"earth_rotation_seconds": 5},
    {"earth_tilt_deg": 90},
    {"station_tilt_deg": 90},
    {"station_yaw_deg": 90},
    {"perspective_strength": 2.0},
    {"station_scale": 0.1},
    {"earth_scale": 2.0},
    {"station_anchor_x": 2.0},
    {"earth_anchor_y": -1.0},
    {"show_stars": 1},
    {"show_graticule": 1},
    {"seed": -1},
    {"scanline_alpha": 900},
    {"vignette_strength": 2.0},
    {"coastlines_file": 42},
    {"title": 42},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    mode, screen = make_mode((240, 400), bad)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)
    assert mode.error


def test_the_error_panel_is_drawn_when_the_config_is_refused():
    mode, screen = make_mode((240, 400), {"palette": "neon"})
    assert "palette" in mode.error
    assert mode.stats() == {}
    assert tuple(screen.get_at((40, 40)))[:3] == (52, 140, 210)


def test_a_missing_coastline_file_degrades_to_the_graticule():
    mode, screen = make_mode((270, 480), {
        "seed": 7,
        "coastlines_file": "data/does-not-exist.json",
    })
    assert mode.error is None
    assert "coastline" in mode.diagnostic
    stats = mode.stats()
    assert stats["earth_rings"] == 0
    assert stats["land_segments"] == 0
    assert stats["grid_segments"] > 0
    mode.render(screen)
    assert mode.error is None


# ---------------------------------------------------------------- clocks

def test_both_clocks_advance_at_the_configured_rates():
    mode, _ = make_mode(DEFAULT_SIZE, {
        "seed": 3, "station_spin_rpm": 1.0, "earth_rotation_seconds": 360.0,
    }, frames=0)
    spin0, earth0 = mode._spin, mode._earth_spin
    for _ in range(60):
        mode.update(1.0 / 60.0)
    assert mode._spin == pytest.approx((spin0 + 6.0) % 360.0, abs=1e-6)
    assert mode._earth_spin == pytest.approx((earth0 + 1.0) % 360.0, abs=1e-6)


def test_the_visual_dials_reach_the_renderer():
    mode, _ = make_mode(DEFAULT_SIZE, {
        "seed": 1,
        "earth_tilt_deg": 5.0,
        "station_tilt_deg": 40.0,
        "station_yaw_deg": -11.0,
        "perspective_strength": 0.3,
        "glow_strength": 0.2,
        "vignette_strength": 0.1,
        "scanline_alpha": 0,
    }, frames=0)
    assert mode.error is None
    renderer = mode.renderer
    assert renderer.earth_tilt_deg == pytest.approx(5.0)
    assert renderer.tilt_deg == pytest.approx(40.0)
    assert renderer.yaw_deg == pytest.approx(-11.0)
    assert renderer.perspective == pytest.approx(0.3)
    assert renderer.glow_strength == pytest.approx(0.2)
    assert renderer.vignette == pytest.approx(0.1)
    assert renderer.scanline_alpha == 0


def test_a_seed_reproduces_the_stars_and_the_starting_wheel_angle():
    a, _ = make_mode(DEFAULT_SIZE, {"seed": 99}, frames=0)
    b, _ = make_mode(DEFAULT_SIZE, {"seed": 99}, frames=0)
    c, _ = make_mode(DEFAULT_SIZE, {"seed": 100}, frames=0)
    assert a.seed == b.seed == 99
    assert a._spin == b._spin
    assert a.renderer.stars == b.renderer.stars
    assert c.seed == 100
    assert c.renderer.stars != a.renderer.stars


# ---------------------------------------------------------------- quality control

def test_auto_quality_steps_down_when_frames_are_slow():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "auto"}, frames=0)
    assert mode._quality == "medium"
    assert mode.stats()["edge_cap"] == QUALITY["medium"]["edges"]
    assert effective_detail(mode._station_detail, "medium") == 3

    # 80 ms frames are 12.5 fps: slow enough that even this detail-first
    # controller has to drop a level.
    for _ in range(80):
        mode.update(0.08)

    assert mode._quality == "low"
    assert mode.renderer.edge_cap == QUALITY["low"]["edges"]
    assert effective_detail(mode._station_detail, "low") == 1
    assert "medium -> low" in mode.diagnostic


def test_a_fixed_quality_does_not_adapt():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "high"}, frames=0)
    for _ in range(120):
        mode.update(0.033)
    assert mode._quality == "high"
    assert mode._auto_quality is False
    assert mode.stats()["edge_cap"] == QUALITY["high"]["edges"]
    assert effective_detail(mode._station_detail, "high") == 4


# ---------------------------------------------------------------- geometry and data

def test_the_station_has_two_rings_and_more_detail_at_each_level():
    meshes = [build_station(level, seed=7) for level in (1, 2, 3, 4)]
    counts = [mesh.edge_count for mesh in meshes]
    assert counts == sorted(counts) and len(set(counts)) == 4, counts
    for level, mesh in zip((1, 2, 3, 4), meshes):
        assert mesh.detail == level
        assert all(math.isfinite(c) for vert in mesh.verts for c in vert)
        # Both ring planes carry a rim: the station is a double wheel, not a
        # single torus with a decorative second loop.
        front = [v for v in mesh.verts if v[2] > 0.40]
        back = [v for v in mesh.verts if v[2] < -0.40]
        assert len(front) > 100 and len(back) > 100, (level, len(front), len(back))
        roles = {edge.role for edge in mesh.edges}
        assert {"hull", "hull_hi", "structure", "dock"} <= roles
        assert "window" in roles or level == 1
        assert "beacon" in roles


def test_the_shipped_coastline_file_is_recognisable_earth():
    path = os.path.join(BASE_DIR, "data", "earth_coastlines.json")
    payload = json.load(open(path, encoding="utf-8"))
    assert payload["ring_count"] >= 60
    assert payload["point_count"] > 1800
    assert payload["tolerance_deg"] <= 0.35
    lons = [pair[0] for ring in payload["coastlines"] for pair in ring]
    lats = [pair[1] for ring in payload["coastlines"] for pair in ring]
    # The Americas, Eurasia, Africa and Antarctica are all in there.
    assert min(lons) < -150 and max(lons) > 150
    assert min(lats) < -60 and max(lats) > 70

    rings, notes = load_coastlines(path)
    assert notes == []
    earth = EarthGeometry(rings, graticule_step=20)
    assert earth.ring_count >= 60
    assert earth.point_count > 1800
    assert len(earth.grid) > 20


def test_the_earth_draws_only_the_visible_hemisphere():
    path = os.path.join(BASE_DIR, "data", "earth_coastlines.json")
    rings, _ = load_coastlines(path)
    earth = EarthGeometry(rings, graticule_step=20)
    screen = pygame.Surface((360, 360))
    earth.draw(screen, (180, 180), 150, 0.0, 23.4,
               get_palette("orbital_white"))
    # Roughly half the coastline points face the camera; the clipping must not
    # draw the whole globe through itself.
    assert 0 < earth.last_land_segments < earth.point_count
    assert 0 < earth.last_grid_segments


# ---------------------------------------------------------------- registry and profile wiring

def test_the_registry_entry_has_a_typed_schema():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    spec = registry["spacestation"]

    assert spec["entrypoint"] == "modes.space_station_mode:SpaceStationMode"
    assert load_entrypoint(spec["entrypoint"]) is SpaceStationMode
    assert spec["required"] == []
    assert set(spec["params"]) <= set(spec["optional"]), "a schema key is not declared"

    params, warnings = resolve_params({}, spec)
    assert warnings == []
    assert {p.key for p in params} == set(spec["optional"])
    assert all(p.widget != "json" for p in params), \
        [p.key for p in params if p.widget == "json"]
    for p in params:
        if p.has_default:
            assert validate_param_value(p, p.default) == [], (p.key, p.default)


def test_the_portrait_profile_slot_63_validates_and_constructs():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_vert.json"), {})
    cfg = profile["modes"]["63"]

    assert cfg["type"] == "spacestation"
    assert cfg["name"] == "Space Station V"
    assert cfg["orientation"] == "portrait"
    assert validate_instance("63", cfg, registry, base_dir=BASE_DIR) == []

    merged = build_merged_config(registry["spacestation"], cfg)
    screen = pygame.Surface(DEFAULT_SIZE)
    mode = SpaceStationMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode._framing.preset == "portrait"
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
        assert mode.stats()["station_detail"] >= 1
    finally:
        mode.exit()


def test_the_narrow_kiosk_slot_19_is_tuned_for_1280x400():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_narrow_horz.json"), {})["modes"]
    cfg = profile["19"]

    assert cfg["type"] == "spacestation"
    assert cfg["orientation"] == "ultrawide"
    assert cfg["hud"] == "minimal"
    assert cfg["earth_rotation_seconds"] >= 300
    assert validate_instance("19", cfg, registry, base_dir=BASE_DIR) == []

    merged = build_merged_config(registry["spacestation"], cfg)
    screen = pygame.Surface((1280, 400))
    mode = SpaceStationMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode._framing.preset == "ultrawide"
        assert (mode.renderer.sw, mode.renderer.sh) == (1280, 400)
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_every_palette_draws_a_frame():
    for palette in ("orbital_white", "vector_blue", "phosphor_green",
                    "amber", "mono"):
        mode, screen = make_mode((240, 400), {"seed": 7, "palette": palette},
                                 frames=1)
        assert mode.error is None, (palette, mode.error)
        assert mode.stats()["segments"] > 1000, palette
        mode.exit()
