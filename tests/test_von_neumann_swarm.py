"""tests/test_von_neumann_swarm.py -- Von Neumann Swarm, a machine ecology.

Pinned here:

  * the mode renders at all four aspect targets and keeps the controller's
    lower-left 80x32 mode-number corner clear;
  * the swarm is a loose lattice of probes around a seed, with links;
  * a seed reproduces the lattice, the links, the rock and the parts;
  * the population climbs with `replication_rate` and is capped by `swarm_count`;
  * a new copy unfolds and the status says so, then it settles;
  * `link_lasers: false` drops the links;
  * the palette variants change the mood without moving the swarm;
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
from modes.von_neumann_swarm_mode import (                                 # noqa: E402
    VonNeumannSwarmMode,
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
    mode = VonNeumannSwarmMode(config)
    mode.enter(FakeManager(screen))
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    return mode, screen


def registry():
    return load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]


def profile_mode(profile, slot, size):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry()["vonneumannswarm"], cfg)
    merged["quality"] = "low"
    merged["seed"] = 5151
    screen = pygame.Surface(size)
    mode = VonNeumannSwarmMode(merged)
    mode.enter(FakeManager(screen))
    mode.render(screen)
    return mode, screen, merged


def pixels(screen):
    return pygame.image.tostring(screen, "RGB")


def interval(mode) -> float:
    return 60.0 / max(0.05, mode._replication_rate)


def unfold_moment(mode) -> float:
    return interval(mode) * 1.04


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
    assert stats["catalogue"] == 128
    assert stats["slots"] >= 30
    assert stats["corner_clear"] is True
    corner = pygame.Rect(0, size[1] - 32, 80, 32)
    for rect in stats["hud_rects"]:
        assert not pygame.Rect(rect).colliderect(corner)
    assert len(set(pixels(screen))) > 40


def test_the_swarm_spreads_around_its_centre():
    mode, _ = make_mode((1280, 400), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    cx, _cy = mode.stats()["centre"]
    xs = [slot["x"] for slot in mode._slots]
    ys = [slot["y"] for slot in mode._slots]
    assert max(xs) - min(xs) > 0.5 * mode._radius
    assert max(ys) - min(ys) > 0.2 * mode._radius
    assert 0.35 * 1280 < cx < 0.65 * 1280


def test_the_links_are_between_near_units():
    mode, _ = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    assert mode.error is None
    assert mode._links
    reach = mode._radius * 0.30
    for i, j, _phase, _period in mode._links[:50]:
        a, b = mode._slots[i], mode._slots[j]
        assert (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 < reach ** 2


def test_an_explicit_orientation_beats_the_aspect_ratio():
    mode, _ = make_mode((1080, 1920), {
        "seed": 1, "quality": "low", "orientation": "landscape",
    })
    assert mode.error is None
    assert mode.stats()["preset"] == "landscape"


# ---------------------------------------------------------------- seed / determinism

def test_a_seed_reproduces_the_lattice_the_links_and_the_parts():
    a, screen_a = make_mode((640, 360), {"seed": 99}, frames=0)
    b, screen_b = make_mode((640, 360), {"seed": 99}, frames=0)
    c, screen_c = make_mode((640, 360), {"seed": 100}, frames=0)
    for mode in (a, b, c):
        assert mode.error is None
        mode.render(mode.manager.screen)

    assert a._slots == b._slots
    assert a._links == b._links
    assert a._rock == b._rock
    assert pixels(screen_a) == pixels(screen_b)
    assert a._slots != c._slots
    assert pixels(screen_a) != pixels(screen_c)


def test_an_unpinned_seed_gives_a_new_swarm_each_entry():
    a, _ = make_mode((320, 200), {"seed": None}, frames=0)
    b, _ = make_mode((320, 200), {"seed": None}, frames=0)
    assert a.error is None and b.error is None
    assert a.seed != b.seed


# ---------------------------------------------------------------- population

def test_the_population_climbs_with_the_replication_rate():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "replication_rate": 0.5}, frames=0)
    period = interval(mode)
    mode._time = 0.0
    mode.render(screen)
    start = mode.stats()["units"]
    mode._time = period * 3.0 + 1.0
    mode.render(screen)
    assert mode.stats()["units"] == start + 3


def test_the_catalogue_caps_the_population():
    mode, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "swarm_count": 20,
                                          "replication_rate": 10.0}, frames=0)
    mode._time = 10_000.0
    mode.render(screen)
    assert mode.stats()["units"] == 20
    assert mode.stats()["catalogue"] == 20


def test_a_faster_rate_reaches_the_catalogue_sooner():
    slow, screen = make_mode((640, 360), {"seed": 5, "quality": "low",
                                          "replication_rate": 0.5}, frames=0)
    fast, _ = make_mode((640, 360), {"seed": 5, "quality": "low",
                                     "replication_rate": 2.0}, frames=0)
    slow._time = 600.0
    slow.render(screen)
    fast._time = 600.0
    assert fast._visible_units() > slow.stats()["units"]


# ---------------------------------------------------------------- the signature beat

def test_a_new_copy_unfolds_and_the_status_says_so():
    mode, screen = make_mode((640, 360), {"seed": 5151, "quality": "low"}, frames=0)
    mode._time = interval(mode) * 5.5    # five intervals in, halfway between copies
    mode.render(screen)
    assert mode.stats()["newest"] is None
    assert mode._status_text()[1] is False

    mode._time = unfold_moment(mode)
    mode.render(screen)
    newest = mode.stats()["newest"]
    assert newest is not None
    assert 0.0 <= newest["unfold"] <= 1.0
    status, alert = mode._status_text()
    assert alert is True and "UNFOLD" in status


# ---------------------------------------------------------------- palette / links

@pytest.mark.parametrize("palette", ["phosphor", "vector_blue", "amber"])
def test_palette_variants_render_and_keep_the_swarm(palette):
    mode, screen = make_mode((640, 360), {
        "seed": 5151, "quality": "low", "palette": palette,
    }, frames=0)
    assert mode.error is None
    mode.render(screen)
    assert mode.stats()["palette"] == palette
    assert len(set(pixels(screen))) > 40


def test_the_palette_changes_the_mood_but_not_the_swarm():
    frames = {}
    framing = {}
    for palette in ("phosphor", "vector_blue", "amber"):
        mode, screen = make_mode((640, 360), {
            "seed": 5151, "quality": "low", "palette": palette,
        }, frames=0)
        mode.render(screen)
        frames[palette] = pixels(screen)
        framing[palette] = mode.stats()["centre"]
    assert frames["phosphor"] != frames["vector_blue"]
    assert frames["phosphor"] != frames["amber"]
    assert framing["phosphor"] == framing["vector_blue"] == framing["amber"]


def test_the_lasers_can_be_switched_off():
    on, screen_on = make_mode((640, 360), {"seed": 5151, "quality": "low"})
    off, screen_off = make_mode((640, 360), {"seed": 5151, "quality": "low",
                                             "link_lasers": False})
    assert off.error is None
    assert off.stats()["link_lasers"] is False
    assert pixels(screen_on) != pixels(screen_off)


def test_the_draw_cap_follows_the_quality_tier():
    for quality in ("low", "medium", "high"):
        mode, screen = make_mode((1280, 400), {"seed": 5151, "quality": quality})
        assert mode.error is None
        assert mode.stats()["quality"] == quality
        assert QUALITY[quality]["probes"] <= 96


def test_a_fixed_quality_does_not_adapt_and_the_swarm_is_not_rebuilt():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "medium"}, frames=0)
    slots = mode._slots
    for _ in range(200):
        mode.update(0.08)
    assert mode.stats()["quality"] == "medium"
    assert mode.stats()["auto_quality"] is False
    assert mode._slots is slots


def test_auto_quality_steps_the_detail_not_the_swarm():
    mode, _ = make_mode((640, 360), {"seed": 3, "quality": "auto"}, frames=0)
    before = (mode._slots, mode._links)
    for _ in range(120):
        mode.update(0.2)
    assert mode.stats()["auto_quality"] is True
    assert mode.stats()["quality"] in ("low", "medium")
    assert (mode._slots, mode._links) == before


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


# ---------------------------------------------------------------- config errors

@pytest.mark.parametrize("bad", [
    {"palette": "neon"},
    {"quality": "ultra"},
    {"hud": "everything"},
    {"fill": "solid"},
    {"orientation": "diagonal"},
    {"swarm_count": 4},
    {"swarm_count": 999},
    {"swarm_count": 128.5},
    {"replication_rate": 0.01},
    {"replication_rate": 20},
    {"link_lasers": 1},
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
    strip_radius = mode.stats()["radius"]
    portrait = pygame.Surface((540, 960))
    mode.render(portrait)
    assert mode.error is None
    assert mode._screen_size == (540, 960)
    assert mode.stats()["preset"] == "portrait"
    assert mode.stats()["radius"] != strip_radius
    mode.exit()
    assert mode.manager is None
    assert mode._background is None
    assert mode._slots == [] and mode._links == [] and mode._glyphs == {}
    assert mode._hud_title is None and mode._metrics is None
    assert mode.stats() == {}


def test_a_repeated_entry_does_not_leak_builds():
    mode, _ = make_mode((640, 360), {"seed": 7, "quality": "low"}, frames=0)
    before = len(mode._slots)
    mode.enter(FakeManager(pygame.Surface((640, 360))))
    assert len(mode._slots) == before
    assert mode.error is None


# ---------------------------------------------------------------- registry / profiles

def test_the_registry_entry_resolves_and_the_schema_is_complete():
    spec = registry()["vonneumannswarm"]
    assert spec["entrypoint"] == "modes.von_neumann_swarm_mode:VonNeumannSwarmMode"
    assert spec["required"] == []
    for key in ("palette", "quality", "hud", "fill", "orientation", "seed",
                "swarm_count", "replication_rate", "link_lasers", "camera_drift",
                "glow_strength", "scanline_alpha", "vignette_strength",
                "title", "subtitle"):
        assert key in spec["optional"]
        assert key in spec["params"]
    params, _warnings = resolve_params({"swarm_count": 128}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["palette"].widget == "choice"
    assert by_key["quality"].widget == "choice"
    assert by_key["swarm_count"].widget == "number"
    assert by_key["link_lasers"].widget == "switch"


@pytest.mark.parametrize("profile,slot,size,preset", [
    ("configs/modes_config_narrow_horz.json", "41", (1280, 400), "ultrawide"),
    ("configs/modes_config_portrait.json", "45", (1080, 1920), "portrait"),
    ("configs/modes_config_vert.json", "85", (1080, 1920), "portrait"),
    ("configs/modes_config_landscape.json", "27", (1920, 1080), "landscape"),
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
