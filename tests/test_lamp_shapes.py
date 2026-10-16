"""
The lamp family, by shape — and the dialog that should have told you so.

Asked for: "a new control which is exactly like Lamp but is square instead of round". It exists:
`lamp_square` (and `lamp_rect` for the rectangular one). Both are already in the catalogue, already
documented in their own docstrings, and already take `color_rgb` and `size`. What was missing was any
way to DISCOVER them: the add dialog listed 24 type names and said nothing about what they look like, so
someone who could not tell that `lamp_square` meant the square glow would reasonably conclude it did not
exist and ask for it.

So this file does two things: it measures the three lamp shapes rather than trusting their names, and it
pins the one-line description the dialog now shows for each type.

The shape test draws one control alone on a colorkeyed surface and asks whether it fills its OWN
bounding box's corner. That question separates the shapes regardless of size — a circle never fills its
corner, a square and a rectangle always do — which is why the first attempt at this probe (sampling at a
fixed offset) proved nothing: 55px from the centre is inside the round lamp's halo and outside the
square one's.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel.controls import CONTROL_CLASSES, ControlContext, make_control   # noqa: E402
from controlpanel.layout import PlacedControl                                    # noqa: E402

from panel.app import PageContext, _control_blurb                                # noqa: E402
from test_transport import _bus, _click, _marked, _panel                         # noqa: E402

pygame.init()

RECT = (100, 100, 200, 200)
CTX = ControlContext(seed=1, accent_rgb=(255, 176, 64), trace_rgb=(80, 255, 120),
                     lamp_rgb=(200, 200, 200))


def _drawn(kind: str, sprite: str):
    """One lamp drawn alone, fully lit, on a colorkeyed surface — plus its bounding box."""
    placed = PlacedControl(kind, sprite, None, (100, 100), (200, 200),
                           {"color_rgb": [255, 255, 255],
                            "signal": {"kind": "constant", "value": 1.0}}, RECT)
    control = make_control(placed, CTX)
    control.level = 1.0
    surface = pygame.Surface((400, 400))
    surface.fill((0, 255, 0))
    surface.set_colorkey((0, 255, 0))
    control.draw_overlay(surface)
    lit = [(x, y) for x in range(400) for y in range(400)
           if surface.get_at((x, y))[:3] != (0, 255, 0)]
    assert lit, "the lamp drew nothing"
    xs, ys = [p[0] for p in lit], [p[1] for p in lit]
    box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    corner = surface.get_at((box[0] + 2, box[1] + 2))[:3] != (0, 255, 0)
    return box, corner


def test_lamp_is_round_and_lamp_square_is_square():
    """The whole question, answered by geometry instead of by name."""
    round_box, round_corner = _drawn("lamp", "LED_LAMP_RED")
    square_box, square_corner = _drawn("lamp_square", "LED_LAMP_SQUARE")

    assert round_corner is False, "the round lamp must NOT fill its bounding box's corner"
    assert square_corner is True, "the square lamp MUST fill its bounding box's corner"
    assert (square_box[2] - square_box[0]) == (square_box[3] - square_box[1]), "square means square"


def test_lamp_rect_is_the_rectangular_one():
    box, corner = _drawn("lamp_rect", "LED_LAMP_RECT")
    assert corner is True, "a rectangle fills its corner too"
    assert (box[2] - box[0]) > (box[3] - box[1]), "and it is wider than it is tall"


def test_the_square_lamp_takes_the_same_settings_as_the_round_one():
    """'Exactly like Lamp but square': same colours, same overrides, only the shape differs."""
    from controlpanel.controls import COLOUR_KEYS

    assert COLOUR_KEYS["lamp_square"] == COLOUR_KEYS["lamp"] == ("color", "color_rgb")
    assert "size" in (CONTROL_CLASSES["lamp_square"].__doc__ or ""), "its size override is documented"
    square = CONTROL_CLASSES["lamp_square"]
    assert issubclass(square, CONTROL_CLASSES["lamp"]), "it IS a lamp, differing in draw_overlay"


def test_the_dialog_describes_a_type_in_its_own_words():
    """The discovery gap: the names do not say what the shapes are, the docstrings do."""
    square = _control_blurb("lamp_square", CONTROL_CLASSES)
    assert "square" in square.lower()
    assert "overrides" in square.lower(), "the settable keys are the second thing a reader needs"
    assert "Blinking" in _control_blurb("lamp", CONTROL_CLASSES)
    assert "static sprite" in _control_blurb("plate", CONTROL_CLASSES)
    assert _control_blurb("not_a_control", CONTROL_CLASSES) == ""


async def test_the_add_dialog_shows_that_description(tmp_path, monkeypatch):
    from controlpanel import paths as cp_paths
    import json
    import shutil

    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / "steampunk1.json", directory / "editme.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    project = tmp_path / "proj"
    (project / "configs").mkdir(parents=True)
    (project / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": "editme"}}}, indent=2) + "\n")

    async with _panel(PageContext(base_dir=str(project), bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        _click(_marked(p, "layout-add"))
        note = _marked(p, "layout-add-type-note")
        assert (note.text or "").strip(), "the dialog must describe the type it is offering"
