"""The Long Archive: wall geometry, clocks, config refusals and wiring.

The reviewed frame is a flat archive wall with the current slab at 75% of the
display width, a light bar crossing it, and one translation line resolving
below.  What a single still cannot show, and what is worth pinning here:

  * the active panel really is 75% of the width in both target aspects;
  * all three panels share one top line and one bottom line;
  * the bar phase, the caption reveal and the wall sway are deterministic;
  * a seed reproduces the frame, and a different seed does not;
  * a missing or malformed text_file falls back to the built-in lore once;
  * bad configs show the error panel instead of taking down the kiosk;
  * the registry schema and both profile instances construct.

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
from core.loader import build_merged_config, load_entrypoint               # noqa: E402
from core.params import resolve_params, validate_param_value               # noqa: E402
from core.validation import validate_instance                              # noqa: E402
from long_archive.glyphs import LORE                                       # noqa: E402
from long_archive.palette import PALETTE_NAMES                             # noqa: E402
from modes.long_archive_mode import LongArchiveMode                        # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
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


def make_mode(size=(640, 300), config=None, frames=1, render=True):
    screen = pygame.Surface(size)
    mode = LongArchiveMode(dict(config if config is not None
                                else {"seed": 5709, "quality": "high"}))
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        if render:
            mode.render(screen)
    return mode, screen


# ---------------------------------------------------------------- the wall

@pytest.mark.parametrize("size,layout_name", [
    ((1280, 400), "landscape"),
    ((1080, 1920), "portrait"),
])
def test_the_reviewed_wall_renders_at_the_two_targets(size, layout_name):
    mode, screen = make_mode(size, {"seed": 5709, "quality": "high"})
    try:
        assert mode.error is None
        stats = mode.stats()
        assert stats["layout"] == layout_name
        assert stats["visible_slabs"] == 3
        assert stats["active_width"] == round(size[0] * 0.75)
        assert stats["active_fraction"] == pytest.approx(0.75, abs=0.002)
        assert stats["glyphs"] > 10
        assert 0.0 <= stats["bar_fraction"] <= 1.0
        # The first frame is the composed hold, not an empty bar at the edge.
        assert stats["caption_chars"] == len(LORE[0])
        assert stats["caption_index"] == 0
        assert stats["offset"] == 0
        unique = len(set(pygame.image.tostring(screen, "RGB")))
        assert unique > 40, f"only {unique} byte values drawn"
        # The controller's lower-left mode number area stays dark.
        corner = screen.get_at((4, size[1] - 4))[:3]
        assert max(corner) < 40, corner
    finally:
        mode.exit()


def test_16_9_reuses_the_landscape_wall():
    mode, screen = make_mode((1920, 1080), {"seed": 11, "quality": "low"})
    try:
        assert mode.error is None
        assert mode.layout.name == "landscape"
        assert mode.stats()["active_fraction"] == pytest.approx(0.75, abs=0.002)
        unique = len(set(pygame.image.tostring(screen, "RGB")))
        assert unique > 40
    finally:
        mode.exit()


def test_the_three_panels_share_one_top_and_bottom_line():
    mode, _ = make_mode((1280, 400), {"seed": 2, "quality": "low"})
    try:
        assert mode.error is None
        slabs = mode.renderer.slabs
        assert [s.focus for s in slabs] == [False, True, False]
        assert len({(s.top, s.bottom) for s in slabs}) == 1
        active = mode.renderer.active
        assert active.x == pytest.approx(160)
        assert active.width == 960
        # The side panels are deliberately wider than the visible slivers.
        left, right = slabs[0], slabs[2]
        assert left.x < 0 and right.x + right.width > 1280
        assert left.x + left.width < active.x
        assert active.x + active.width < right.x
    finally:
        mode.exit()


def test_the_bar_and_caption_clock_advance_and_cycle():
    mode, _ = make_mode((640, 300), {"seed": 4, "quality": "low"}, frames=0)
    try:
        assert mode.error is None
        first = mode.renderer.stats()
        assert first["caption_index"] == 0
        mode.update(1.0)
        mode.render(pygame.Surface((640, 300)))
        later = mode.stats()
        assert later["bar_fraction"] != pytest.approx(first["bar_fraction"])
        mode._time = 3.0
        mode.render(pygame.Surface((640, 300)))
        after_wrap = mode.stats()
        assert after_wrap["caption_index"] == 1
        assert after_wrap["caption_chars"] == 0
    finally:
        mode.exit()


def test_the_wall_sways_without_changing_the_panel_hierarchy():
    mode, _ = make_mode((640, 300), {"seed": 6, "quality": "low",
                                     "drift_speed": 2.0}, frames=0)
    try:
        mode._time = 30.0
        mode.render(pygame.Surface((640, 300)))
        assert mode.stats()["offset"] != 0
        assert mode.stats()["active_fraction"] == pytest.approx(0.75, abs=0.002)
        mode._time = 0.0
        mode.render(pygame.Surface((640, 300)))
        assert mode.stats()["offset"] == 0
    finally:
        mode.exit()


# ---------------------------------------------------------------- seeds / data

def test_a_seed_reproduces_the_frame():
    one, screen_one = make_mode((640, 300), {"seed": 5709, "quality": "high"})
    two, screen_two = make_mode((640, 300), {"seed": 5709, "quality": "high"})
    other, screen_other = make_mode((640, 300), {"seed": 5710, "quality": "high"})
    try:
        first = pygame.image.tostring(screen_one, "RGB")
        second = pygame.image.tostring(screen_two, "RGB")
        third = pygame.image.tostring(screen_other, "RGB")
        assert first == second
        assert first != third
    finally:
        for mode in (one, two, other):
            mode.exit()


def test_a_missing_text_file_falls_back_to_built_in_lore():
    mode, screen = make_mode((640, 300), {
        "seed": 7, "quality": "low",
        "text_file": "data/long-archive-does-not-exist.json",
    })
    try:
        assert mode.error is None
        assert "text_file" in mode.diagnostic
        assert mode.stats()["lore_lines"] == len(LORE)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_a_text_file_supplies_the_translation_lines(tmp_path):
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(["a custom first line",
                                "a custom second line"]), encoding="utf-8")
    mode, screen = make_mode((640, 300), {
        "seed": 8, "quality": "low", "text_file": str(path),
    })
    try:
        assert mode.error is None
        assert mode.stats()["lore_lines"] == 2
        assert mode.renderer._caption[0].text == "a custom first line"
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_a_malformed_text_file_falls_back(tmp_path):
    path = tmp_path / "archive.json"
    path.write_text("{\"not\": \"a list\"}", encoding="utf-8")
    mode, _ = make_mode((480, 270), {"seed": 9, "quality": "low",
                                     "text_file": str(path)})
    try:
        assert mode.error is None
        assert "text_file" in mode.diagnostic
        assert mode.stats()["lore_lines"] == len(LORE)
    finally:
        mode.exit()


# ---------------------------------------------------------------- configs

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"orientation": "diagonal"},
    {"slab_count": 3},
    {"slab_count": 13},
    {"slab_count": 9.0},
    {"drift_speed": -1.0},
    {"drift_speed": float("nan")},
    {"text_speed": 0},
    {"bar_period": 2},
    {"seed": -1},
    {"seed": "42"},
    {"show_labels": 1},
    {"glow_strength": 2.0},
    {"scanline_alpha": 900},
    {"vignette_strength": 2.0},
    {"text_file": 42},
    {"title": 42},
])
def test_a_bad_value_reports_an_error_and_does_not_crash(bad):
    case = dict(bad)
    if "seed" not in case:
        case["seed"] = 7
    mode, screen = make_mode((480, 270), case)
    try:
        assert mode.error, f"{bad!r} was accepted"
        mode.render(screen)
        assert mode.error
    finally:
        mode.exit()


def test_the_error_panel_is_drawn_when_the_config_is_refused():
    mode, screen = make_mode((480, 270), {"palette": "neon"})
    try:
        assert "palette" in mode.error
        assert mode.stats() == {}
        unique = len(set(pygame.image.tostring(screen, "RGB")))
        assert unique > 2
    finally:
        mode.exit()


def test_every_palette_draws_a_frame():
    for palette in PALETTE_NAMES:
        mode, screen = make_mode((480, 270), {
            "seed": 7, "quality": "low", "palette": palette,
        })
        try:
            assert mode.error is None, (palette, mode.error)
            assert mode.stats()["visible_slabs"] == 3
            unique = len(set(pygame.image.tostring(screen, "RGB")))
            assert unique > 30, palette
        finally:
            mode.exit()


def test_hud_off_leaves_the_wall_and_translation_running():
    mode, screen = make_mode((480, 270), {"seed": 7, "quality": "low",
                                          "hud": "off"})
    try:
        assert mode.error is None
        assert mode.hud.mode == "off"
        assert mode.stats()["caption_chars"] > 0
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()


def test_show_labels_off_removes_the_catalogue_mark():
    mode, _ = make_mode((480, 270), {"seed": 7, "quality": "low",
                                     "show_labels": False})
    try:
        assert mode.error is None
        assert mode.renderer.show_labels is False
        assert mode.stats()["visible_slabs"] == 3
    finally:
        mode.exit()


# ---------------------------------------------------------------- resize / quality

def test_a_resize_rebuilds_the_wall_and_hud_for_the_new_aspect():
    mode, screen = make_mode((640, 300), {"seed": 7, "quality": "low"})
    try:
        assert mode.layout.name == "landscape"
        assert mode.renderer.sw == 640
        portrait = pygame.Surface((360, 640))
        mode.render(portrait)
        assert mode.error is None
        assert mode.layout.name == "portrait"
        assert mode.renderer.sw == 360
        assert mode.hud.sw == 360
        assert mode.stats()["active_fraction"] == pytest.approx(0.75, abs=0.005)
    finally:
        mode.exit()


def test_pinned_quality_does_not_move_and_auto_quality_steps_down():
    pinned, _ = make_mode((480, 270), {"seed": 7, "quality": "high"})
    try:
        for _ in range(80):
            pinned.update(0.1)
        assert pinned._quality == "high"
    finally:
        pinned.exit()

    auto, _ = make_mode((480, 270), {"seed": 7, "quality": "auto"})
    try:
        for _ in range(200):
            auto.update(0.1)
        assert auto._quality == "low"
        assert auto.renderer.quality == "low"
    finally:
        auto.exit()


def test_exit_releases_every_surface_and_reference():
    mode, _ = make_mode((480, 270), {"seed": 7, "quality": "low"})
    mode.exit()
    assert mode.manager is None
    assert mode.renderer is None and mode.hud is None and mode.layout is None
    assert mode._screen_size is None


# ---------------------------------------------------------------- wiring

def test_the_registry_entry_has_a_typed_schema():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    spec = registry["longarchive"]

    assert spec["entrypoint"] == "modes.long_archive_mode:LongArchiveMode"
    assert load_entrypoint(spec["entrypoint"]) is LongArchiveMode
    assert spec["required"] == []
    assert set(spec["params"]) <= set(spec["optional"])
    assert set(spec["params"]) == set(spec["optional"])

    params, warnings = resolve_params({}, spec)
    assert warnings == []
    assert {p.key for p in params} == set(spec["optional"])
    assert all(p.widget != "json" for p in params)
    for p in params:
        if p.has_default:
            assert validate_param_value(p, p.default) == [], (p.key, p.default)


@pytest.mark.parametrize("profile_name,slot,size,layout_name", [
    ("configs/modes_config_narrow_horz.json", "22", (1280, 400), "landscape"),
    ("configs/modes_config_portrait.json", "27", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "65", (1080, 1920), "portrait"),
])
def test_the_profile_instances_validate_and_construct(profile_name, slot, size,
                                                      layout_name):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    profile = load_json(os.path.join(BASE_DIR, profile_name), {})["modes"]
    cfg = profile[slot]
    assert cfg["type"] == "longarchive"
    assert cfg["name"] == "The Long Archive"
    assert validate_instance(slot, cfg, registry, base_dir=BASE_DIR) == []

    merged = build_merged_config(registry["longarchive"], cfg)
    screen = pygame.Surface(size)
    mode = LongArchiveMode(merged)
    mode.enter(FakeManager(screen))
    try:
        assert mode.error is None
        assert mode.layout.name == layout_name
        assert mode.stats()["active_fraction"] == pytest.approx(0.75, abs=0.002)
        mode.update(1.0 / 60.0)
        mode.render(screen)
        assert mode.error is None
    finally:
        mode.exit()
