"""
The "size" key means two different things, and one collision blacked out a panel.

Every control in a layout takes its box from `size`: [w, h] in PIXELS. The lamp family also reads
`size` as ITS own fraction of the shorter side. The add dialog wrote the pixel form into a
SquareLampControl, which did float([160, 160]) — the TypeError escaped the mode's enter(), which caught
only SkinError and LayoutError — and the whole panel went black. One overlay, no panel, reported from
the wall rather than from a test.

So there are guards at three levels now, and this file pins each of them:

  * the lamps read BOTH forms, so a control the dialog wrote always builds;
  * the loader refuses a bare number where it needs a box, in words, rather than raising TypeError;
  * the mode shows ANY failure on the screen, so the next one of these is readable instead of black.

and one guard above them: every control type in the catalogue builds and draws with the layout's pixel
size present, which is the contract the add dialog relies on.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel import paths as cp_paths                                 # noqa: E402
from controlpanel.controls import CONTROL_CLASSES, ControlContext, make_control   # noqa: E402
from controlpanel.layout import (LayoutError, PlacedControl,               # noqa: E402
                                 layout_from_data, load_layout)
from controlpanel.registry import CONTROL_TYPES                            # noqa: E402
from core.layout_edit import LayoutEditor                                  # noqa: E402

from test_layout_page import REAL_LAYOUT                                   # noqa: E402

pygame.init()

RECT = (100, 100, 200, 200)
CTX = ControlContext(seed=1, accent_rgb=(255, 176, 64), trace_rgb=(80, 255, 120),
                     lamp_rgb=(200, 200, 200))


def test_every_control_type_builds_and_draws_with_the_layouts_pixel_size():
    """
    The contract the add dialog depends on: `size: [w, h]` in pixels must be acceptable to every type,
    including the ones that give `size` a second meaning of their own.
    """
    built, failed = 0, []
    for ctype, cls in CONTROL_CLASSES.items():
        if cls is None:
            continue
        placed = PlacedControl(ctype, CONTROL_TYPES[ctype], None, (100, 100), (200, 200),
                               {"size": [160, 160], "at": [100, 100]}, RECT)
        try:
            control = make_control(placed, CTX)
            surface = pygame.Surface((400, 400))
            surface.fill((0, 255, 0))
            surface.set_colorkey((0, 255, 0))
            control.level = 1.0
            control.update(0.016)
            control.draw_overlay(surface)
            built += 1
        except Exception as e:                                 # noqa: BLE001 - that is the point
            failed.append(f"{ctype}: {type(e).__name__}: {e}")
    assert not failed, "these types could not cope with the layout's size key:\n  " + "\n  ".join(failed)
    assert built >= 20, f"expected the whole catalogue, built only {built}"


def test_the_square_lamp_reads_either_form_of_size():
    """A pixel box and a glow fraction are both legal, and they mean different sizes of glow."""
    from controlpanel.controls import make_control as build

    def half(size):
        placed = PlacedControl("lamp_square", "LED_LAMP_SQUARE", None, (0, 0), (200, 200),
                               {"size": size}, RECT)
        return build(placed, CTX).half

    assert half([160, 160]) == 80                 # the layout's box: half of it
    assert half([0.30]) == 30                     # a fraction inside a list, too
    assert half(0.30) == 30                       # the lamp's own fraction: 0.30 * min(200, 200) / 2


def test_the_loader_refuses_a_bare_number_where_it_needs_a_box():
    """`size: 0.3` gives the layout no box to place, so it says that instead of raising TypeError."""
    doc = json.loads((cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json").read_text())
    doc["controls"][0]["size"] = 0.3
    try:
        layout_from_data(doc, name="probe")
    except LayoutError as e:
        assert "'size' must be [w, h]" in str(e)
    else:
        raise AssertionError("a bare number must be refused by the freeform loader")


def test_a_failing_control_is_reported_instead_of_blacking_out_the_panel(tmp_path, monkeypatch):
    """
    The mode's fallback used to catch SkinError and LayoutError only, so anything else escaped and the
    panel went black with no reason on it. Found the hard way: one lamp with a list where a number was
    expected. A kiosk should show the reason where the operator is standing.
    """
    from modes.control_panel_mode import ControlPanelMode

    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json", directory / "blowup.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)

    def boom(*_args, **_kwargs):
        raise TypeError("float() argument must be a string or a real number, not 'list'")

    # patch it where the MODE looks it up: it imported the name directly, so patching the catalogue
    # module's attribute would leave the mode calling the original and the test proving nothing
    monkeypatch.setattr("modes.control_panel_mode.make_control", boom)

    mode = ControlPanelMode({"layout_file": "blowup"})
    mode.enter(_Manager((320, 480)))

    assert mode.compositor is None, "a failed build must not pretend to have a compositor"
    assert "float() argument must be" in (mode._error or ""), mode._error
    surface = pygame.Surface((320, 480))
    mode.render(surface)                                      # and it must draw the reason, not nothing


class _Manager:
    """The smallest thing enter()/render() need (see test_layout_align for the full one)."""

    def __init__(self, size):
        self.size = size

        class _Cache:
            @staticmethod
            def get_font(*_args, **_kwargs):
                return pygame.font.SysFont(None, 16)

        self.cache = _Cache()
