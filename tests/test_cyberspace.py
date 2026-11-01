"""
tests/test_cyberspace.py -- the cyberspace mode and its registry/profile wiring.

The mode is a seeded neon matrix: a street-lattice route that moves one axis at
a time, a wireframe city, floating constructs, and an adaptive glow/edge budget.
What is worth pinning here is the part a single frame cannot show:

  * the route only ever turns on an intersection, and every axis is visited;
  * a seed reproduces the same city and the same flight;
  * a bad config shows the error panel instead of crashing the kiosk;
  * auto quality steps down on slow frames and a pinned quality does not;
  * the registry schema is typed and the live portrait profile constructs.

The first render is also allowed to be slow, so the timing test warms the
renderer before measuring.
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
from cyberspace.camera import AXIS_X, AXIS_Y, AXIS_Z, CameraRig, Route     # noqa: E402
from cyberspace.landmarks import load_landmarks, landmark_path             # noqa: E402
from cyberspace.matrix import Matrix                                       # noqa: E402
from cyberspace.palette import get_palette                                 # noqa: E402
from cyberspace.render import QUALITY                                      # noqa: E402
from modes.cyberspace_mode import CyberspaceMode                           # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    # Initialise, but do NOT quit at module scope: a quit tears the font module
    # down for later test modules.  test_smoke owns init/quit for the session.
    pygame.init()
    pygame.font.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((64, 64))
    yield


class FakeManager:
    """The minimum a mode reaches for: a surface, a font cache and its sizes."""

    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


DEFAULT_SIZE = (270, 480)      # portrait, small enough to keep the suite quick


def make_mode(size=DEFAULT_SIZE, config=None, frames=3):
    screen = pygame.Surface(size)
    mode = CyberspaceMode(dict(config or {"seed": 20261029}))
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


# ---------------------------------------------------------------- rendering and framing

@pytest.mark.parametrize("size", [(270, 480), (480, 270), (360, 360)])
def test_the_mode_renders_a_form_in_every_aspect(size):
    mode, screen = make_mode(size, {"seed": 5})
    assert mode.error is None
    stats = mode.stats()
    assert stats["objects"] > 0 and stats["segments"] > 100, stats
    assert stats["quality"] in QUALITY
    # The frame is not a flat wash: neon edges, HUD type and the glow all
    # contribute byte values.
    unique = len(set(pygame.image.tostring(screen, "RGB")))
    assert unique > 30, f"only {unique} byte values drawn"


def test_a_resize_rebuilds_the_camera_renderer_and_hud():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 7})
    assert mode.renderer.sw == 270 and mode.renderer.sh == 480
    assert mode.camera.sw == 270

    landscape = pygame.Surface((480, 270))
    mode.render(landscape)

    assert mode.error is None
    assert mode._screen_size == (480, 270)
    assert (mode.renderer.sw, mode.renderer.sh) == (480, 270)
    assert (mode.camera.sw, mode.camera.sh) == (480, 270)
    assert mode.hud.sw == 480


def test_hud_off_leaves_the_world_running():
    mode, screen = make_mode(DEFAULT_SIZE, {"seed": 7, "hud": "off"})
    assert mode.error is None
    assert mode.hud.mode == "off"
    assert mode.renderer.last_segments > 100
    mode.render(screen)
    assert mode.error is None


def test_exit_releases_every_surface_and_reference():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 7})
    mode.exit()
    assert mode.manager is None
    assert mode.matrix is None and mode.route is None and mode.camera is None
    assert mode.renderer is None and mode.hud is None


# ---------------------------------------------------------------- config handling

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"scanline_alpha": 900},
    {"travel_speed": float("nan")},
    {"blocks_per_leg": 1},
    {"seed": -1},
    {"show_labels": 1},
    {"crisp_lines": 1},
    {"show_landmarks": 1},
    {"landmark_overlay": 1},
    {"geometric_detail": 0},
    {"geometric_detail": 5},
    {"geometric_detail": 2.5},
    {"landmarks_file": 42},
    {"street_spacing": 5},
    {"fov": 10},
    {"event_rate_per_min": 99},
    {"title": 42},
    {"blocks_per_leg": 5.5},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    mode, screen = make_mode((240, 400), bad)
    assert mode.error, f"{bad!r} was accepted"
    mode.render(screen)          # the error-panel path, not the render path
    assert mode.error


def test_the_error_panel_is_drawn_when_the_config_is_refused():
    mode, screen = make_mode((240, 400), {"palette": "neon"})
    assert "palette" in mode.error
    assert mode.stats() == {}
    # 1 px border from _draw_error(), an exact colour.
    assert tuple(screen.get_at((40, 40)))[:3] == (52, 140, 210)


# ---------------------------------------------------------------- route invariants

def test_the_route_visits_all_three_axes_and_never_leaves_the_street_lattice():
    route = Route(seed=11, cell=80.0, speed=16.0, blocks_min=4, blocks_max=6,
                  z_low=26.0, z_high=216.0, level=56.0)
    axes = set()
    high = low = False
    for _ in range(int(320 / 0.02)):
        before = list(route.target)
        old_axis = route.axis
        old_leg = route.leg_id
        route.advance(0.02)
        axes.add(route.axis)
        if route.axis == AXIS_Z:
            high = high or route.direction > 0
            low = low or route.direction < 0
        if route.leg_id == old_leg:
            changed = [i for i in range(3)
                       if abs(route.target[i] - before[i]) > 1e-9]
            assert changed in ([old_axis], []), (old_axis, changed)
        # At every vertical leg the horizontal position must be exactly on an
        # intersection; at every horizontal leg the fixed coordinate must be.
        if route.axis == AXIS_Z:
            assert route.target[0] / 80.0 == pytest.approx(round(route.target[0] / 80.0))
            assert route.target[1] / 80.0 == pytest.approx(round(route.target[1] / 80.0))
        else:
            fixed = 1 if route.axis == AXIS_X else 0
            assert route.target[fixed] / 80.0 == pytest.approx(
                round(route.target[fixed] / 80.0))
            assert route.target[2] in (26.0, 216.0)

    assert axes == {AXIS_X, AXIS_Y, AXIS_Z}
    assert high and low, "the vertical legs must both climb and descend"
    assert route.axis_changes >= 4
    assert route.travelled > 0.0


def test_a_seed_reproduces_the_route_and_the_city():
    a = Route(99, cell=80.0, speed=16.0, blocks_min=4, blocks_max=6)
    b = Route(99, cell=80.0, speed=16.0, blocks_min=4, blocks_max=6)
    for _ in range(2000):
        a.advance(0.05)
        b.advance(0.05)
    assert a.target == b.target
    assert a.axis == b.axis and a.leg_id == b.leg_id

    palette = get_palette("neuromancer")
    city_a = Matrix(99, palette, cell=80.0)
    city_b = Matrix(99, palette, cell=80.0)
    city_c = Matrix(100, palette, cell=80.0)
    assert city_a.signature() == city_b.signature()
    assert city_a.signature() != city_c.signature()


def test_crisp_lines_can_be_turned_off():
    mode, screen = make_mode(DEFAULT_SIZE, {"seed": 7, "crisp_lines": False})
    assert mode.error is None
    assert mode.renderer.crisp_lines is False
    mode.render(screen)
    assert mode.error is None
    assert mode.renderer.last_segments > 100


def test_the_camera_basis_stays_orthonormal_while_following_a_turn():
    route = Route(7, cell=80.0, speed=16.0)
    camera = CameraRig(74.0)
    camera.set_size(DEFAULT_SIZE)
    camera.snap(route)
    for _ in range(1200):
        route.advance(1.0 / 60.0)
        camera.update(1.0 / 60.0, route)
        f, r, u = camera._fwd, camera._right, camera._up
        assert abs(sum(v * v for v in f) - 1.0) < 1e-9
        assert abs(sum(v * v for v in r) - 1.0) < 1e-9
        assert abs(sum(v * v for v in u) - 1.0) < 1e-9
        assert abs(sum(f[i] * r[i] for i in range(3))) < 1e-9
        assert abs(sum(f[i] * u[i] for i in range(3))) < 1e-9
    # The camera lags the planned point a little, but never enough to leave the
    # street corridor.
    assert math.dist(camera.pos, route.target) < 20.0


def test_construct_edges_rotate_and_reproduce():
    matrix = Matrix(7, get_palette("neuromancer"), cell=80.0)
    found = None
    for ix in range(-3, 4):
        for iy in range(-3, 4):
            for iz in range(1, 7):
                c = matrix.construct_at(ix, iy, iz)
                if c is not None:
                    found = c
                    break
            if found:
                break
        if found:
            break
    assert found is not None, "seed 7 generated no construct at all"

    first = matrix.construct_edges(found, 0.0)
    again = matrix.construct_edges(found, 0.0)
    later = matrix.construct_edges(found, 4.0)
    assert first == again
    assert first != later
    assert all(len(edge) == 9 for edge in first)


# ---------------------------------------------------------------- landmarks

def test_the_shipped_landmark_file_has_ten_drawable_landmarks():
    path = os.path.join(BASE_DIR, "data", "cyberspace_landmarks.json")
    landmarks, warnings = load_landmarks(path, cell=80.0)
    assert warnings == [], warnings
    assert len(landmarks) == 10
    names = {lm.name for lm in landmarks}
    assert "Eastern Seaboard Fission Authority" in names
    assert "Mitsubishi Bank of America" in names
    for lm in landmarks:
        assert lm.parts, lm.name
        assert lm.static_edges, lm.name
        assert lm.label and lm.label == lm.label[:48]
        assert lm.radius > 0
        assert len(lm.cells) == (9 if lm.clear_radius else 1)
    # unique sectors: two landmarks must not fight over the same reserved cell
    assert len({lm.sector for lm in landmarks}) == 10
    eastern = next(lm for lm in landmarks
                   if lm.name == "Eastern Seaboard Fission Authority")
    mitsubishi = next(lm for lm in landmarks
                      if lm.name == "Mitsubishi Bank of America")
    assert any(part.shape == "stepped_pyramid" for part in eastern.parts)
    assert sum(1 for part in mitsubishi.parts if part.shape == "box") == 3
    assert eastern.clear_radius == 1 and mitsubishi.clear_radius == 1


def test_a_landmark_can_be_added_from_json_alone(tmp_path):
    """The point of the file: a new form and name are data, not code."""
    path = tmp_path / "custom_landmarks.json"
    path.write_text(json.dumps({
        "landmarks": [{
            "name": "Test Arcology",
            "label": "TEST ARC",
            "sector": [2, 0],
            "altitude": 0,
            "color": [255, 120, 40],
            "parts": [{"shape": "box", "size": [40, 40, 90]}],
        }]
    }), encoding="utf-8")
    landmarks, warnings = load_landmarks(str(path), cell=80.0)
    assert warnings == []
    assert len(landmarks) == 1
    assert landmarks[0].name == "Test Arcology"
    assert landmarks[0].label == "TEST ARC"
    assert landmarks[0].static_edges

    screen = pygame.Surface(DEFAULT_SIZE)
    mode = CyberspaceMode({"seed": 7, "quality": "medium",
                           "landmarks_file": str(path)})
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert len(mode.landmarks) == 1
        # the ground cell is cleared so the landmark is not buried in a tower
        assert mode.matrix.cell_at(2, 0).kind == "plaza"
        for _ in range(120):
            mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.renderer.last_landmarks >= 1
        assert mode.renderer.nearest_landmark_object is not None
        assert any(item["text"] == "TEST ARC"
                   for item in mode.renderer.last_labels)
    finally:
        mode.exit()


def test_bad_landmark_entries_are_reported_and_skipped(tmp_path):
    path = tmp_path / "bad_landmarks.json"
    path.write_text(json.dumps({
        "landmarks": [
            {"name": "No sector", "parts": [{"shape": "box", "size": [10, 10, 10]}]},
            {"name": "Bad shape", "sector": [0, 0],
             "parts": [{"shape": "hypercube", "size": [10, 10, 10]}]},
            {"name": "Good", "sector": [1, 0],
             "parts": [{"shape": "octahedron", "size": [20, 20, 30]}]},
        ]
    }), encoding="utf-8")
    landmarks, warnings = load_landmarks(str(path), cell=80.0)
    assert [lm.name for lm in landmarks] == ["Good"]
    assert len(warnings) >= 2
    assert any("No sector" in warning for warning in warnings)
    assert any("hypercube" in warning for warning in warnings)


def test_a_missing_landmark_file_does_not_break_the_mode(tmp_path):
    screen = pygame.Surface(DEFAULT_SIZE)
    mode = CyberspaceMode({"seed": 7,
                           "landmarks_file": str(tmp_path / "absent.json")})
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.landmarks == []
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_landmarks_can_be_switched_off_without_loading_the_file(tmp_path):
    path = tmp_path / "custom_landmarks.json"
    path.write_text(json.dumps({
        "landmarks": [{"name": "Hidden", "sector": [1, 0],
                       "parts": [{"shape": "box", "size": [10, 10, 10]}]}]
    }), encoding="utf-8")
    screen = pygame.Surface(DEFAULT_SIZE)
    mode = CyberspaceMode({"seed": 7, "show_landmarks": False,
                           "landmarks_file": str(path)})
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.landmarks == []
        assert mode.matrix.stats()["reserved_cells"] == 0
    finally:
        mode.exit()


def test_landmark_cells_are_reserved_from_the_procedural_city():
    matrix = Matrix(3, get_palette("neuromancer"), cell=80.0)
    matrix.reserve_cells({(1, 0)})
    cell = matrix.cell_at(1, 0)
    assert cell.kind == "plaza"
    assert cell.edges == ()
    for iz in range(1, 7):
        assert matrix.construct_at(1, 0, iz) is None
    assert matrix.stats()["reserved_cells"] == 1


def test_the_route_turns_back_toward_a_landmark_district():
    route = Route(1, cell=80.0, speed=16.0, home=(0.0, 0.0), home_radius=150.0)
    route.target = [1000.0, 0.0, 26.0]
    route._begin_horizontal(axis=AXIS_Y, direction=1)
    assert route.axis == AXIS_X
    assert route.direction == -1, "outside the district the next leg points home"


def test_the_landmark_inset_is_optional_and_still_renders(tmp_path):
    path = tmp_path / "custom_landmarks.json"
    path.write_text(json.dumps({
        "landmarks": [{
            "name": "Inset Test",
            "label": "INSET TEST",
            "sector": [2, 0],
            "parts": [{"shape": "stepped_pyramid", "size": [40, 40, 60],
                       "steps": 4}],
        }]
    }), encoding="utf-8")
    screen = pygame.Surface((540, 960))
    mode = CyberspaceMode({"seed": 7, "landmarks_file": str(path),
                           "landmark_overlay": False})
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.hud.show_landmark_overlay is False
        for _ in range(120):
            mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_the_landmark_inset_draws_the_nearest_geometry(tmp_path):
    """With the same seed and time, only the inset should differ between frames."""
    path = tmp_path / "custom_landmarks.json"
    path.write_text(json.dumps({
        "landmarks": [{
            "name": "Inset Test",
            "label": "INSET TEST",
            "sector": [2, 0],
            "color": [255, 100, 40],
            "parts": [{"shape": "stepped_pyramid", "size": [40, 40, 60],
                       "steps": 4}],
        }]
    }), encoding="utf-8")

    def frame(overlay: bool) -> bytes:
        screen = pygame.Surface((540, 960))
        mode = CyberspaceMode({"seed": 7, "landmarks_file": str(path),
                               "landmark_overlay": overlay, "quality": "medium"})
        mode.enter(FakeManager(screen))
        try:
            assert mode.error is None
            for _ in range(120):
                mode.update(1.0 / 60.0)
            mode.render(screen)
            assert mode.error is None
            assert mode.renderer.nearest_landmark_object is not None
            return pygame.image.tostring(screen, "RGB")
        finally:
            mode.exit()

    assert frame(overlay=True) != frame(overlay=False), \
        "toggling landmark_overlay made no difference to the frame"


def test_geometric_detail_adds_volume_lattice_and_landmarks_are_one_higher(tmp_path):
    path = os.path.join(BASE_DIR, "data", "cyberspace_landmarks.json")
    base, _ = load_landmarks(path, cell=80.0, detail_level=1)
    detailed, _ = load_landmarks(path, cell=80.0, detail_level=2)
    assert all(lm.detail_level == 1 for lm in base)
    assert all(lm.detail_level == 2 for lm in detailed)
    eastern_base = next(lm for lm in base
                        if lm.name == "Eastern Seaboard Fission Authority")
    eastern_detailed = next(lm for lm in detailed
                            if lm.name == "Eastern Seaboard Fission Authority")
    assert len(eastern_detailed.static_edges) > len(eastern_base.static_edges)

    mode, screen = make_mode((540, 960), {"seed": 7, "geometric_detail": 1},
                             frames=0)
    try:
        assert mode.error is None
        assert mode.matrix.detail_level == 1
        assert all(lm.detail_level == 2 for lm in mode.landmarks)
    finally:
        mode.exit()

    mode, screen = make_mode((540, 960), {"seed": 7, "geometric_detail": 4},
                             frames=0)
    try:
        assert mode.error is None
        assert mode.matrix.detail_level == 4
        assert all(lm.detail_level == 5 for lm in mode.landmarks)
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_procedural_cells_build_detail_lazily_and_cache_it():
    matrix = Matrix(3, get_palette("neuromancer"), cell=80.0, detail_level=3)
    cell = None
    for ix in range(-3, 4):
        for iy in range(-3, 4):
            candidate = matrix.cell_at(ix, iy)
            if candidate.detail_boxes:
                cell = candidate
                break
        if cell is not None:
            break
    assert cell is not None
    simple = matrix.detail_edges(cell, 1)
    detailed = matrix.detail_edges(cell, 3)
    assert simple is cell.edges
    assert len(detailed) > len(cell.edges)
    assert matrix.detail_edges(cell, 3) is detailed, "detail mesh is cached"


def test_landmark_cores_are_drawn_without_bloom():
    """Crisp core rendering must include hero lines, not just ordinary ones."""
    mode, screen = make_mode((270, 480), {"seed": 7, "glow_strength": 0.0},
                             frames=0)
    try:
        renderer = mode.renderer
        renderer._core = []
        renderer._hero_core = [(10, 10, 50, 10, (255, 255, 255), 2, 1.0)]
        screen.fill((0, 0, 0))
        renderer._draw_core(screen)
        lit = any(screen.get_at((x, y))[:3] != (0, 0, 0)
                  for x in range(10, 51) for y in (9, 10, 11))
        assert lit, "landmark core disappeared when bloom was disabled"
    finally:
        mode.exit()


# ---------------------------------------------------------------- adaptive quality

def test_auto_quality_steps_down_when_frames_are_slow():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "auto"}, frames=0)
    assert mode._quality == "medium"
    assert mode.stats()["edge_cap"] == QUALITY["medium"]["edges"]

    # 50 ms frames are 20 fps: slow enough that even the detail-first
    # controller has to drop a level.
    for _ in range(80):
        mode.update(0.05)
    assert mode._quality == "low"
    assert mode.renderer.edge_cap == QUALITY["low"]["edges"]
    assert "medium -> low" in mode.diagnostic


def test_a_fixed_quality_does_not_adapt():
    mode, _ = make_mode(DEFAULT_SIZE, {"seed": 3, "quality": "high"}, frames=0)
    for _ in range(120):
        mode.update(0.033)
    assert mode._quality == "high"
    assert mode._auto_quality is False
    assert mode.renderer.edge_cap == QUALITY["high"]["edges"]


# ---------------------------------------------------------------- registry and profile wiring

def test_the_registry_entry_has_a_typed_schema():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    spec = registry["cyberspace"]

    assert spec["entrypoint"] == "modes.cyberspace_mode:CyberspaceMode"
    assert load_entrypoint(spec["entrypoint"]) is CyberspaceMode
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


def test_the_vertical_profile_slot_62_validates_cleanly():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_vert.json"), {})
    cfg = profile["modes"]["62"]

    assert cfg["type"] == "cyberspace"
    assert cfg["name"] == "Cyberspace Matrix"
    assert validate_instance("62", cfg, registry, base_dir=BASE_DIR) == []


def test_the_profile_config_constructs_and_renders():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_vert.json"), {})["modes"]
    merged = build_merged_config(registry["cyberspace"], profile["62"])

    screen = pygame.Surface(DEFAULT_SIZE)
    mode = CyberspaceMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.config["name"] == "Cyberspace Matrix"
        assert mode.seed is not None
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
        assert mode.stats()["segments"] > 0
        assert mode.stats()["landmark_count"] == 10
    finally:
        mode.exit()


def test_the_narrow_horizontal_profile_slot_18_is_tuned_for_1280x400():
    """The Pi wall: a wider fov and a shorter draw distance, with the big inset off."""
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, "configs",
                                     "modes_config_narrow_horz.json"), {})["modes"]
    cfg = profile["18"]

    assert cfg["type"] == "cyberspace"
    assert cfg["name"] == "Cyberspace Matrix"
    assert cfg["hud"] == "minimal"
    assert cfg["landmark_overlay"] is False
    assert cfg["fov"] > 74
    assert cfg["draw_distance"] < 620
    assert validate_instance("18", cfg, registry, base_dir=BASE_DIR) == []

    merged = build_merged_config(registry["cyberspace"], cfg)
    screen = pygame.Surface((1280, 400))
    mode = CyberspaceMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert (mode.camera.sw, mode.camera.sh) == (1280, 400)
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
        assert mode.stats()["segments"] > 0
    finally:
        mode.exit()
