"""
The artwork a control panel is drawn over: the MODE's background_image parameter.

Where it lives, and why here: the PNG was neither hard-coded nor a mode parameter — it was a field in
the LAYOUT file (background_image), resolved under assets/control_panel/backgrounds/, so changing it
meant hand-editing layout JSON. Now the layout names a DEFAULT and the mode overrides it. That
direction matters: the artwork is what an author changes often and per mode (one layout reused over
different pictures), while the layout stays the drawing spec the alignment page edits.

Resolution follows the same rule as every other asset path in this package (skin, layout_file): a bare
name looks under assets/control_panel/backgrounds/, and a path with a separator — absolute, or
./pics/panel.png — is used as given, which is how you point at artwork living anywhere on disk.

Two details this file is careful about, because they are the traps:

  * the canvas. When a layout declares no design_resolution its canvas is the artwork's own size, so
    the parameter does not only change the picture — it changes the coordinate space every overlay is
    measured in. A small PNG over a layout placed for a 1920x1088 canvas is REFUSED by the loader
    ("rect exceeds the canvas"), which is the loader working. So the fixtures here say which canvas
    they mean instead of discovering it.
  * the refusals. A missing file is named with the path you typed, and a GRID layout refuses an
    artwork override outright: it draws its panels from the skin and has no background image at all,
    so accepting the override would leave you looking at the wrong picture and believing it worked.

Off-display throughout (SDL dummy): the kiosk's screen belongs to whatever is already on it.
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402
import pytest                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel import paths as cp_paths                                 # noqa: E402
from controlpanel.layout import LayoutError, load_layout                   # noqa: E402
from modes.control_panel_mode import ControlPanelMode                      # noqa: E402

from test_layout_align import _Manager                                     # noqa: E402

REAL_LAYOUT = "steampunk1"                      # the project's real freeform layout
GRID_LAYOUT = "demo_console"                    # the project's real grid layout

pygame.init()


def _png(path, size):
    """A real PNG on disk: the loader reads its size, so a fake file would prove nothing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface(size), str(path))
    return str(path)


def _real_canvas():
    """
    The canvas the real layout's overlays are placed for, read from the file rather than through
    the loader: the loader resolves the layout's own artwork name, and the bare-name test
    monkeypatches the backgrounds directory this fixture would then fail to find.
    """
    doc = json.loads((cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json").read_text())
    return [int(v) for v in doc["design_resolution"]]


def _freeform_doc(tmp_path, name="art", background=None, resolution="declared"):
    """
    The project's own freeform layout, adjusted, so the controls are real and the only thing a test
    varies is the artwork. resolution="declared" pins the canvas to the real one (controls fit);
    resolution="drop" removes it, which is the case where the artwork decides the canvas.
    """
    doc = json.loads((cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json").read_text())
    assert doc.get("mode") == "freeform", "this fixture assumes a freeform layout"
    doc.pop("design_resolution", None)
    if resolution == "declared":
        doc["design_resolution"] = _real_canvas()
    if background is None:
        doc.pop("background_image", None)
    else:
        doc["background_image"] = background
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return str(path)


def test_without_the_parameter_the_layouts_own_artwork_is_used(tmp_path):
    """The layout's field is a default, not dead config: unset the mode's param and it still rules."""
    art = _png(tmp_path / "from_layout.png", (11, 5))
    layout = load_layout(_freeform_doc(tmp_path, background=art))
    assert layout.background_image == art


def test_the_mode_parameter_overrides_the_layouts_artwork(tmp_path):
    """One layout, a different picture — the point of the parameter."""
    own = _png(tmp_path / "layout_art.png", (11, 5))
    mode_art = _png(tmp_path / "mode_art.png", (13, 7))
    doc = _freeform_doc(tmp_path, background=own)

    assert load_layout(doc).background_image == own
    assert load_layout(doc, background_override=mode_art).background_image == mode_art


def test_the_canvas_follows_the_artwork_the_mode_points_at(tmp_path):
    """
    The case this parameter is really for on this host: a tall PNG over a layout that declares no
    canvas. The artwork decides the coordinate space every overlay is measured in.
    """
    w, h = _real_canvas()
    art = _png(tmp_path / "tall.png", (w, h + 200))
    doc = _freeform_doc(tmp_path, resolution="drop")

    assert list(load_layout(doc).design_resolution) == [1920, 1080]   # no artwork, no declared one
    assert list(load_layout(doc, background_override=art).design_resolution) == [w, h + 200]


def test_the_override_is_not_used_when_it_is_blank(tmp_path):
    """A blank string is "unset", not "no artwork" — clearing the box must not blank the panel."""
    art = _png(tmp_path / "layout_art.png", (11, 5))
    doc = _freeform_doc(tmp_path, background=art)
    for blank in ("", "   ", None):
        assert load_layout(doc, background_override=blank).background_image == art


def test_a_bare_name_is_looked_up_under_the_backgrounds_directory(tmp_path, monkeypatch):
    """Same rule as skin and layout_file: a bare name is a name in the backgrounds directory."""
    directory = tmp_path / "backgrounds"
    directory.mkdir()
    (directory / "mine.png").write_bytes((cp_paths.BACKGROUNDS_DIR / "steampunk1.png").read_bytes())
    monkeypatch.setattr(cp_paths, "BACKGROUNDS_DIR", directory)

    layout = load_layout(_freeform_doc(tmp_path), background_override="mine.png")
    assert layout.background_image == str(directory / "mine.png")


def test_a_path_with_a_separator_is_used_as_given(tmp_path):
    """How you point at artwork anywhere on disk — no copying into the assets tree."""
    outside = _png(tmp_path / "elsewhere" / "panel.png", (5, 5))
    layout = load_layout(_freeform_doc(tmp_path), background_override=outside)
    assert layout.background_image == outside


def test_a_missing_file_is_refused_and_named(tmp_path):
    """The author typed a path; the refusal has to contain it, or they cannot fix it."""
    with pytest.raises(LayoutError) as e:
        load_layout(_freeform_doc(tmp_path), background_override="not_here.png")
    assert "not_here.png" in str(e.value)
    assert "background" in str(e.value).lower()


def test_a_grid_layout_refuses_an_artwork_override(tmp_path):
    """Refused, not ignored: a grid layout has no background image for the override to replace."""
    art = _png(tmp_path / "art.png", (5, 5))
    with pytest.raises(LayoutError) as e:
        load_layout(GRID_LAYOUT, background_override=art)
    message = str(e.value)
    assert "grid layout" in message and "no background image" in message
    # and the same grid layout still loads fine when nobody asks for artwork
    assert load_layout(GRID_LAYOUT).mode == "grid"


def test_the_mode_passes_it_to_the_loader_and_reports_what_is_in_use(tmp_path):
    """The path the panel shows and the path the wall draws are the same one — read off the mode."""
    # Note what does NOT move here: this layout declares its canvas, so overriding the artwork
    # changes the picture and not the coordinate space. (When none is declared the artwork decides,
    # which is the case covered above.)
    w, h = _real_canvas()
    layout_art = _png(tmp_path / "layout_art.png", (11, 5))
    mode_art = _png(tmp_path / "mode_art.png", (w, h + 120))
    doc = _freeform_doc(tmp_path, background=layout_art)

    mode = ControlPanelMode({"layout_file": doc, "background_image": mode_art})
    assert mode.background_param == mode_art
    mode.enter(_Manager((320, 480)))
    report = mode.layout_report()
    assert report["background_param"] == mode_art
    assert report["background_image"] == mode_art
    assert list(report["canvas"]) == [w, h]

    # unset: the report still says which artwork is in use, because it is the layout's own
    plain = ControlPanelMode({"layout_file": doc})
    plain.enter(_Manager((320, 480)))
    assert plain.layout_report()["background_param"] == ""
    assert plain.layout_report()["background_image"] == layout_art


def test_an_unreadable_artwork_file_fails_the_mode_loudly(tmp_path):
    """A bad path must not draw an empty panel: the mode keeps its error instead of the compositor."""
    mode = ControlPanelMode({"layout_file": _freeform_doc(tmp_path),
                             "background_image": "no_such_artwork.png"})
    mode.enter(_Manager((320, 480)))
    assert mode.compositor is None
    assert "no_such_artwork.png" in (mode._error or "")


def test_the_registry_offers_it_as_an_optional_field_with_help():
    """
    Optional (a panel with no artwork of its own must keep validating) and text-shaped with an empty
    default, so the params page shows a box for it even when the profile has never set it — the
    Phase 3 rule that an unset key's widget comes from the schema, not from its name.
    """
    registry = json.loads(open(os.path.join(BASE_DIR, "modes_registry.json")).read())
    entry = registry["types"]["controlpanel"]
    assert "background_image" in entry["optional"]
    assert "background_image" not in entry["required"]
    spec = entry["params"]["background_image"]
    assert spec["default"] == "" and len(spec["help"]) > 40
