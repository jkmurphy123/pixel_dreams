# tests/test_control_panel_all.py
#
# Phase 4 tests: every control type in the catalog animates.
#
# Run headless:
#   SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/test_control_panel_all.py -q

import json
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from controlpanel import seven_seg  # noqa: E402
from controlpanel.controls import (CONTROL_CLASSES, ControlContext,  # noqa: E402
                                   make_control)
from controlpanel.geometry import CELL_SIZE  # noqa: E402
from controlpanel.layout import load_layout  # noqa: E402
from controlpanel.registry import CONTROL_TYPES  # noqa: E402
from controlpanel.skin import load_sprite_defs  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pygame_init():
    pygame.init()
    pygame.font.init()
    yield
    pygame.quit()


# One layout exercising every animated type (plate is static by design).
#
# FREEFORM, not grid: a grid layout has to find an unoccupied 15x8 cell block for every type it
# adds, so adding a control meant re-packing the fixture. Freeform takes a pixel rect with no
# overlap rule, which makes adding a type one line — the same path the real layouts use.
_DEFS = load_sprite_defs()["sprites"]


def _control(ctype, sprite=None, col=0, row=0, **extra):
    """A freeform control at a grid-ish coordinate, sized by the type's default sprite."""
    sid = sprite or CONTROL_TYPES[ctype]
    geo = _DEFS[sid]
    doc = {"type": ctype, "sprite": sid,
           "at": [col * CELL_SIZE, row * CELL_SIZE],
           "size": [geo["w"] * CELL_SIZE, geo["h"] * CELL_SIZE]}
    doc.update(extra)
    return doc


ALL_TYPES_LAYOUT = {
    "name": "all_types",
    "mode": "freeform",
    "design_resolution": [1920, 1400],
    "controls": [
        _control("scope",           "SCOPE_H_1",    0, 0),
        _control("strip_chart",     "STRIP_CHART",  4, 0),
        _control("radar",           "RADAR_ROUND",  10, 0),
        _control("gauge_round",     "GAUGE_ROUND_SMALL_1", 0, 2),
        _control("meter_vu",        "METER_VU_H_1", 1, 2),
        _control("bar_graph",       "BAR_GRAPH_V_1", 3, 2),
        _control("led_bar",         "LED_BAR",      4, 2),
        _control("lamp",            "LED_LAMP_RED", 0, 3),
        _control("lamp_rect",       "LED_LAMP_RECT", 8, 3),
        _control("lamp_square",     "LED_LAMP_SQUARE", 14, 3),
        _control("lamp_bank",       "LAMP_BANK",    1, 3),
        _control("led_matrix",      "LED_MATRIX",   4, 3),
        _control("keypad",          "KEYPAD",       6, 3),
        _control("push_button",     "PUSH_BUTTON_1", 0, 4),
        _control("digital_readout", "READOUT_DIGITAL", 8, 4),
        _control("clock",           "CLOCK_FACE",   12, 4),
        _control("meter_vu",        "METER_VU_V_1", 14, 4),
        _control("toggle_switch",   "TOGGLE_SWITCH_1", 0, 5),
        _control("rotary_knob",     "ROTARY_KNOB_1", 1, 5),
        _control("selector_switch", "SELECTOR_SWITCH", 2, 5),
        _control("counter",         "COUNTER",      8, 5),
        _control("nixie",           "NIXIE_PAIR",   4, 5),
        _control("tape_reel",       "TAPE_REEL",    6, 5),
        # arcane family (designs/ARCANE_LAB_DESIGN.md) — phases 2 and 3 append here
        _control("candle_flame",    col=0, row=6, count=2),
        _control("ember_field",     col=2, row=6, count=24),
        _control("floating_orb",    col=6, row=6),
        _control("rune_circle",     col=8, row=6),
        _control("rune_line",       "ARCANE_RUNE_LINE", 10, 6),
        _control("smoke_wisp",      col=12, row=6),
        _control("lightning_arc",   col=0, row=7),
        _control("potion_bubbles",  col=2, row=7),
        _control("drifting_runes",  col=4, row=7),
        _control("glowing_eyes",    col=6, row=7),
        # mad-science family — electrical/mechanical freeform overlays
        _control("jacobs_ladder",   col=8, row=7),
        _control("electric_filament", col=10, row=7),
        _control("spark_terminal",  col=11, row=7),
        _control("mechanical_wheels", col=12, row=7),

    ],
}


@pytest.fixture(scope="module")
def all_controls(tmp_path_factory):
    path = tmp_path_factory.mktemp("layouts") / "all_types.json"
    path.write_text(json.dumps(ALL_TYPES_LAYOUT))
    layout = load_layout(str(path))
    ctx = ControlContext(seed=3)
    return [make_control(p, ctx) for p in layout.controls]


def test_every_type_except_plate_has_a_class():
    assert set(CONTROL_CLASSES) == set(CONTROL_TYPES) - {"plate"}


def test_all_types_construct(all_controls):
    assert all(c is not None for c in all_controls)
    assert len(all_controls) == len(ALL_TYPES_LAYOUT["controls"])


def test_all_types_update_and_draw_60s(all_controls):
    surface = pygame.Surface((1920, 1080))
    for _ in range(360):  # 6 simulated seconds at 60 fps
        for c in all_controls:
            c.update(1 / 60)
    for c in all_controls:
        c.draw_overlay(surface)  # must not raise


def test_keypad_types_and_submits(all_controls):
    keypad = next(c for c in all_controls if c.type == "keypad")
    seen_states = set()
    for _ in range(60 * 60):  # one simulated minute
        keypad.update(1 / 60)
        seen_states.add(keypad.state)
        assert len(keypad.entry) <= keypad.code_len
    # idle/press/hold/accept-or-reject all reached within a minute
    assert len(seen_states) >= 4


def test_counter_counts_up(all_controls):
    counter = next(c for c in all_controls if c.type == "counter")
    before = counter.value
    for _ in range(600):
        counter.update(1 / 60)
    assert counter.value > before


def test_seven_seg_draws_all_digits():
    surface = pygame.Surface((400, 100))
    seven_seg.draw_text(surface, "0123456789", (0, 0, 400, 100), (0, 255, 0))
    lit = sum(1 for x in range(0, 400, 4) for y in range(0, 100, 4)
              if surface.get_at((x, y))[1] > 0)
    assert lit > 100, "7-seg rendering drew nothing"


def test_readout_formats_value(all_controls):
    readout = next(c for c in all_controls if c.type == "digital_readout")
    readout.signal.value = 0.5
    readout.signal.update = lambda dt: None  # freeze the drift for the assertion
    readout._acc = readout.refresh  # force a refresh on next update
    readout.update(1 / 60)
    mid = (readout.lo + readout.hi) / 2
    assert readout.text == f"{mid:.0f}"
