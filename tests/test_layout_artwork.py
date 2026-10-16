"""
Which artwork the alignment page draws its boxes over.

Found by using it: the mode was showing the PNG given by its `background_image` parameter while the
page drew the boxes over the picture named in the LAYOUT file. The page was reading the layout
document's own field and calling it done — which makes every position on the page a lie, because the
boxes are only meaningful over the picture the wall is actually using.

The rule is now stated once (_artwork_in_use) and used by both the page and the asset route that feeds
its <img>, so the two can never disagree: the live display first, then the mode's parameter (asked of
the package's loader, which also decides the canvas when the layout declares none), then the layout
file's own field for a panel being prepared but not shown.
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
from core.layout_edit import LayoutEditor, resolve_background              # noqa: E402
from panel.app import PageContext, _artwork_in_use                         # noqa: E402

from test_layout_page import REAL_LAYOUT, _ui_project                      # noqa: E402
from test_transport import _bus, _panel                                    # noqa: E402

REAL_ARTWORK = str(cp_paths.BACKGROUNDS_DIR / "steampunk1.png")


class _SilentBus:
    """A bus that only has to answer 'what is on the wall?'."""

    def __init__(self, snapshot=None):
        self._snapshot = snapshot or {}

    def snapshot(self) -> dict:
        return self._snapshot

    def post(self, _command) -> None:
        pass


def _project(tmp_path, background=None):
    """A sandbox whose control panel mode points at a real layout, optionally with an artwork param."""
    root = tmp_path / "proj"
    (root / "configs").mkdir(parents=True)
    mode = {"type": "controlpanel", "layout_file": REAL_LAYOUT}
    if background is not None:
        mode["background_image"] = background
    (root / "modes_config.json").write_text(json.dumps({"modes": {"0": mode}}, indent=2) + "\n")
    return root


def _ctx(root, snapshot=None):
    return PageContext(base_dir=str(root), bus=_SilentBus(snapshot), bind="127.0.0.1")


def _art(tmp_path, name="panel.png", size=(400, 900)):
    path = tmp_path / name
    pygame.image.save(pygame.Surface(size), str(path))
    return str(path)


def test_resolve_background_follows_the_loaders_rule(tmp_path):
    assert resolve_background("steampunk1.png") == REAL_ARTWORK       # bare name: the assets dir
    outside = _art(tmp_path)
    assert resolve_background(outside) == outside                     # a path: used as given
    assert resolve_background("") == ""


def test_without_the_parameter_the_boxes_go_over_the_layouts_own_artwork(tmp_path):
    editor = LayoutEditor(REAL_LAYOUT)
    artwork, canvas, source = _artwork_in_use(_ctx(_project(tmp_path)), "modes_config.json", 0, editor)
    assert artwork == REAL_ARTWORK
    assert canvas == list(editor.canvas())
    assert source == "the layout file"


def test_the_modes_parameter_wins_over_the_layout_file(tmp_path):
    """The bug: the wall drew the parameter's PNG while the page drew the layout file's."""
    art = _art(tmp_path)
    editor = LayoutEditor(REAL_LAYOUT)
    artwork, canvas, source = _artwork_in_use(
        _ctx(_project(tmp_path, background=art)), "modes_config.json", 0, editor)
    assert artwork == art
    assert source == "this mode's background_image parameter"
    assert canvas == list(editor.canvas())          # this layout declares its canvas, so it stands


def test_what_the_live_display_reports_beats_everything(tmp_path):
    """If the wall is showing this layout, its own answer is the truth — artwork and canvas both."""
    art = _art(tmp_path)
    editor = LayoutEditor(REAL_LAYOUT)
    live = {"layout_report": {"layout_file": REAL_LAYOUT, "background_image": art,
                              "canvas": [300, 900]}}
    artwork, canvas, source = _artwork_in_use(
        _ctx(_project(tmp_path), snapshot=live), "modes_config.json", 0, editor)
    assert (artwork, canvas, source) == (art, [300, 900], "the live display")


def test_a_parameter_that_will_not_load_is_reported_rather_than_hidden(tmp_path):
    """The page still says which file it meant, and says the loader refused it."""
    editor = LayoutEditor(REAL_LAYOUT)
    artwork, _canvas, source = _artwork_in_use(
        _ctx(_project(tmp_path, background="missing_artwork.png")), "modes_config.json", 0, editor)
    assert artwork.endswith("missing_artwork.png")
    assert "missing_artwork.png" in source          # which file it meant
    assert "not found" in source                    # and the loader's own words


async def test_the_page_says_the_mode_parameter_decided_the_artwork(tmp_path):
    """The page must not just draw the right picture: it says where the picture came from."""
    root = _ui_project(tmp_path)
    art = _art(tmp_path)
    (tmp_path / "proj" / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": REAL_LAYOUT, "background_image": art}}}) + "\n")
    async with _panel(_ctx(root)) as p:
        await p.user.open("/layout")
        await p.user.should_see("from this mode's background_image parameter")
        await p.user.should_see(os.path.basename(art))


async def test_the_page_says_when_the_layout_file_decided_it(tmp_path):
    root = _ui_project(tmp_path)
    async with _panel(_ctx(root)) as p:
        await p.user.open("/layout")
        await p.user.should_see("from the layout file")
