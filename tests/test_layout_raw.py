"""
The raw JSON editor for a layout, and the way in to it.

The profile has had one since Phase 3; a layout needs one for what the boxes cannot express: paste a
whole panel in, fix a sprite id by hand, move three overlays one line each. It is deliberately NOT a
second write path — it goes through core.layout_edit.LayoutEditor, so it is validated by the
package's own loader, written atomically with a backup, and refused if the file changed underneath.
The tests below check both the way in and that the refusals leave the file alone.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel import paths as cp_paths                             # noqa: E402
from core.store import sha256_file                                     # noqa: E402
from panel.app import PageContext                                      # noqa: E402

from test_layout_page import _ui_project                               # noqa: E402
from test_transport import _bus, _click, _marked, _panel               # noqa: E402


def _copy_layout(tmp_path, monkeypatch, source="steampunk1", name="rawtest"):
    """A writable copy of a real layout, in its own directory, so a test never edits the shipped one."""
    directory = tmp_path / "layouts"
    directory.mkdir(exist_ok=True)
    target = directory / f"{name}.json"
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{source}.json", target)
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    return target


async def test_the_raw_page_shows_the_layout_document():
    async with _panel(PageContext(base_dir=BASE_DIR, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout/raw?layout=steampunk1")
        await p.user.should_see("steampunk1.png")        # a value from inside the file
        await p.user.should_see("1920x1088")             # the canvas it declares
        await p.user.should_see("Raw JSON")


async def test_json_that_does_not_parse_is_refused_and_writes_nothing(tmp_path, monkeypatch):
    target = _copy_layout(tmp_path, monkeypatch)
    before = sha256_file(str(target))
    async with _panel(PageContext(base_dir=BASE_DIR, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout/raw?layout=rawtest")
        _marked(p, "raw-layout-json").value = "{ this is not json"
        _click(_marked(p, "raw-layout-validate"))
        await p.user.should_see("not valid JSON")
        _click(_marked(p, "raw-layout-save"))
        await p.user.should_see("not valid JSON")
    assert sha256_file(str(target)) == before, "a document that will not parse must not be written"


async def test_a_layout_the_loader_rejects_is_refused_by_the_page(tmp_path, monkeypatch):
    """The page does not judge the document: the package's own loader does, and it gets the last word."""
    target = _copy_layout(tmp_path, monkeypatch)
    before = sha256_file(str(target))
    doc = json.loads(target.read_text())
    doc["controls"][0]["sprite"] = "definitely_not_a_sprite"
    async with _panel(PageContext(base_dir=BASE_DIR, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout/raw?layout=rawtest")
        _marked(p, "raw-layout-json").value = json.dumps(doc, indent=2)
        _click(_marked(p, "raw-layout-validate"))
        await p.user.should_see("Not valid")
    assert sha256_file(str(target)) == before, "an invalid layout must not be written"


async def test_saving_writes_the_change_and_keeps_a_backup(tmp_path, monkeypatch):
    target = _copy_layout(tmp_path, monkeypatch)
    before = sha256_file(str(target))
    doc = json.loads(target.read_text())
    doc["controls"][0]["at"] = [4, 4]
    async with _panel(PageContext(base_dir=BASE_DIR, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout/raw?layout=rawtest")
        _marked(p, "raw-layout-json").value = json.dumps(doc, indent=2)
        _click(_marked(p, "raw-layout-save"))
        await p.user.should_see("Saved")
        await p.user.should_see("backup:")               # the writer says it kept one, with its name
    assert json.loads(target.read_text())["controls"][0]["at"] == [4, 4]
    assert sha256_file(str(target)) != before


async def test_the_alignment_page_links_to_the_raw_editor(tmp_path):
    root = _ui_project(tmp_path)
    async with _panel(PageContext(base_dir=root, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        await p.user.should_see("raw JSON")


async def test_a_layout_that_cannot_be_opened_says_so_instead_of_raising(tmp_path, monkeypatch):
    directory = tmp_path / "layouts"
    directory.mkdir()
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    async with _panel(PageContext(base_dir=BASE_DIR, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout/raw?layout=missing_layout")
        await p.user.should_see("Could not open layout")
