"""
The alignment page and its writer (design Phase 6B).

Two halves: the writer's RULES (what it refuses, what it validates with, what it leaves alone on
disk), and the PAGE (does the list render, does a nudge move the document and post the right command,
does Save write, does a nudge refuse when the display is showing a different layout).

The writer's tests work on a COPY of a real layout, so the shipped layouts are never touched; the
page tests render against a sandbox project with its own profile.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest                                                                 # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.layout_edit import LayoutEditor, create_freeform, list_backgrounds   # noqa: E402
from core.store import sha256_file                                            # noqa: E402
from controlpanel import paths as cp_paths                                    # noqa: E402
from controlpanel.layout import LayoutError                                   # noqa: E402
from panel.app import PageContext                                             # noqa: E402

from test_transport import _bus, _click, _marked, _panel                      # noqa: E402

REAL_LAYOUT = "steampunk1"


@pytest.fixture
def layout_copy(tmp_path, monkeypatch):
    """
    A layout file the tests may write to: the real one is copied into a temp dir that stands in for
    the package's layouts directory, so nothing shipped is modified.
    """
    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json", directory / f"{REAL_LAYOUT}.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    return directory / f"{REAL_LAYOUT}.json"


def _document(path):
    return json.load(open(path))


# ---------------------------------------------------------------- the writer's rules

def test_it_reads_a_real_layout_and_validates_with_the_loader(layout_copy):
    editor = LayoutEditor(REAL_LAYOUT)
    assert editor.path == str(layout_copy)
    assert editor.mode == "freeform"
    assert len(editor.controls()) == 17
    assert editor.validate() == ((), ()), "a shipped layout must pass the loader's own validation"
    assert editor.canvas() == tuple(_document(layout_copy)["design_resolution"])


def test_set_rect_changes_the_document_only_until_saved(layout_copy):
    """The property the whole page depends on: dozens of nudges, no writes until Save."""
    editor = LayoutEditor(REAL_LAYOUT)
    before = sha256_file(str(layout_copy))
    old = editor.rect_of(3)
    report = editor.set_rect(3, (old[0] + 25, old[1] + 15, old[2], old[3]))
    assert report["ok"] and report["rect"] == [old[0] + 25, old[1] + 15, old[2], old[3]]
    assert editor.is_dirty() is True
    assert sha256_file(str(layout_copy)) == before, "a nudge wrote to the file"

    saved = editor.save()
    assert saved.ok and saved.backup, "a save must keep a backup"
    assert sha256_file(str(layout_copy)) != before
    assert _document(layout_copy)["controls"][3]["at"] == [old[0] + 25, old[1] + 15]
    assert editor.is_dirty() is False


def test_a_rect_that_would_not_load_is_refused_and_changes_nothing(layout_copy):
    editor = LayoutEditor(REAL_LAYOUT)
    before = json.dumps(editor.document, sort_keys=True)
    report = editor.set_rect(0, (99999, 99999, 100, 100))         # off the canvas
    assert report["ok"] is False and "does not fit" in report["reason"]
    assert json.dumps(editor.document, sort_keys=True) == before
    assert editor.set_rect(0, (10, 10, 0, 40))["ok"] is False      # not a real size
    assert editor.set_rect(999, (10, 10, 40, 40))["ok"] is False   # not a real overlay
    assert editor.set_rect(0, ("x", 1, 2, 3))["ok"] is False       # not numbers


def test_a_grid_layout_refuses_to_be_nudged(tmp_path, monkeypatch):
    """demo_console is the grid flavour: cells, no pixels — the reason is worth saying."""
    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / "demo_console.json", directory / "demo_console.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    editor = LayoutEditor("demo_console")
    assert editor.mode == "grid"
    report = editor.set_rect(0, (10, 10, 10, 10))
    assert report["ok"] is False and "grid layout" in report["reason"]


def test_add_and_remove_are_validated_and_reversible(layout_copy):
    editor = LayoutEditor(REAL_LAYOUT)
    count = len(editor.controls())
    added = editor.add_control({"type": "lamp", "sprite": "LED_LAMP_RED", "size": [80, 80]})
    assert added["ok"] and added["index"] == count
    assert editor.rect_of(count) is not None, "a placed control needs a box"

    # a bad type or sprite must be refused by the loader, and must not stay in the document
    before = json.dumps(editor.document, sort_keys=True)
    assert editor.add_control({"type": "lamp", "sprite": "NOT_A_SPRITE"})["ok"] is False
    assert editor.add_control({"type": "nonsense", "sprite": "LED_LAMP_RED"})["ok"] is False
    assert editor.add_control({"sprite": "LED_LAMP_RED"})["ok"] is False
    assert json.dumps(editor.document, sort_keys=True) == before

    removed = editor.remove_control(count)
    assert removed["ok"] and removed["removed"]["type"] == "lamp"
    assert len(editor.controls()) == count


def test_it_never_empties_a_layout(layout_copy):
    """One overlay left: removing it is refused, because an empty layout is not a layout."""
    editor = LayoutEditor(REAL_LAYOUT)
    while len(editor.controls()) > 1:
        assert editor.remove_control(0)["ok"] is True
    report = editor.remove_control(0)
    assert report["ok"] is False and "last overlay" in report["reason"]


def test_save_refuses_when_the_file_changed_underneath(layout_copy):
    editor = LayoutEditor(REAL_LAYOUT)
    editor.set_rect(0, (11, 12, 13, 14))
    document = _document(layout_copy)
    document["controls"][1]["at"] = [33, 44]
    with open(layout_copy, "w") as handle:
        json.dump(document, handle, indent=2)

    result = editor.save()
    assert result.ok is False and "changed on disk" in result.reason
    assert _document(layout_copy)["controls"][0]["at"] != [11, 12], "it wrote anyway"
    editor.reload()
    assert editor.is_dirty() is False


def test_centre_moves_a_control_to_the_middle(layout_copy):
    editor = LayoutEditor(REAL_LAYOUT)
    assert editor.centre_rect(0)["ok"] is True
    x, y, w, h = editor.rect_of(0)
    cw, ch = editor.canvas()
    assert (x, y) == ((cw - w) // 2, (ch - h) // 2)


# ---------------------------------------------------------------- creating a new panel

def test_create_freeform_over_a_background_with_a_seed(tmp_path, monkeypatch):
    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json", directory / f"{REAL_LAYOUT}.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    backgrounds = list_backgrounds()
    assert backgrounds, "the project must ship at least one background PNG"

    result = create_freeform("try_panel", backgrounds[0], seed_from=REAL_LAYOUT)
    assert result["ok"] is True, result
    assert result["controls"] == 17, "the seed's overlays should come across"
    document = _document(result["path"])
    assert document["mode"] == "freeform" and document["background_image"] == backgrounds[0]
    assert document["name"] == "try_panel"
    # and it loads through the package's loader, which is the only opinion that counts
    assert LayoutEditor("try_panel").validate() == ((), ())


def test_create_freeform_refuses_bad_input(tmp_path, monkeypatch):
    directory = tmp_path / "layouts"
    directory.mkdir()
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    assert create_freeform("", list_backgrounds()[0])["ok"] is False
    assert create_freeform("../escape", list_backgrounds()[0])["ok"] is False
    assert create_freeform("ok_name", "not_a_picture.png")["ok"] is False
    first = create_freeform("dupe", list_backgrounds()[0])
    assert first["ok"] is True
    second = create_freeform("dupe", list_backgrounds()[0])
    assert second["ok"] is False and "already exists" in second["reason"]


def test_create_freeform_reports_a_seed_it_had_to_move(tmp_path, monkeypatch):
    """
    Seeding from a layout whose controls do not fit the new canvas clamps them and says so — a
    control outside the canvas is invisible, and silent clamping would hide that.
    """
    directory = tmp_path / "layouts"
    directory.mkdir()
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)

    # a seed with a control placed right at the bottom-right of a canvas much larger than the artwork
    big = directory / "big_seed.json"
    background = list_backgrounds()[0]
    import pygame
    pygame.init()
    width, height = pygame.image.load(
        str(cp_paths.BACKGROUNDS_DIR / background)).get_size()
    big.write_text(json.dumps({
        "name": "big_seed", "mode": "freeform",
        "design_resolution": [width * 4, height * 4],
        "controls": [{"type": "lamp", "sprite": "LED_LAMP_RED",
                      "at": [width * 3, height * 3], "size": [80, 80]}],
    }) + "\n")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)

    result = create_freeform("clamped", background, seed_from="big_seed")
    assert result["ok"] is True, result
    assert "clamped" in result["seeded"], result["seeded"]
    placed = _document(result["path"])["controls"][0]["at"]
    assert placed[0] + 80 <= width and placed[1] + 80 <= height, placed


# ---------------------------------------------------------------- the page

def _ui_project(tmp_path):
    """A sandbox project whose control panel mode points at a real layout."""
    root = tmp_path / "proj"
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "modes_registry.json").write_text(json.dumps({
        "settings": {"modes_config_file": "modes_config.json"},
        "types": {"controlpanel": {"entrypoint": "modes.control_panel_mode:ControlPanelMode",
                                   "required": ["layout_file"],
                                   "optional": ["scale_mode", "skin"]}},
    }, indent=2) + "\n")
    (root / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": REAL_LAYOUT, "scale_mode": "fit"},
    }}, indent=2) + "\n")
    return str(root)


def _live(layout=REAL_LAYOUT, frozen=True):
    return _bus(display="fullscreen", mode_index=0, applied_rotation=[0], pending_steps=0,
                layout_report={"layout_file": layout, "layout": layout, "mode": "freeform",
                               "canvas": [1920, 1088], "controls": 17, "animated": 17,
                               "static_only": [], "selected": None, "frozen": frozen,
                               "rects": {}})


async def test_the_page_lists_the_overlays_with_nudge_controls(tmp_path):
    root = _ui_project(tmp_path)
    ctx = PageContext(base_dir=root, bus=_live(), bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/layout")
        await p.user.should_see("Align a control panel's overlays to its artwork")
        await p.user.should_see("Overlays (17)")
        assert _marked(p, "layout-box-0") is not None
        assert _marked(p, "layout-save") is not None
        assert _marked(p, "layout-create") is not None


async def test_selecting_then_nudging_updates_the_document_and_the_wall(tmp_path):
    """
    The core loop of the page: pick an overlay, nudge it, and the command that reaches the render
    loop carries the new rect — while the FILE is untouched until Save.
    """
    root = _ui_project(tmp_path)
    bus = _live()
    ctx = PageContext(base_dir=root, bus=bus, bind="127.0.0.1")
    layout_file = cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json"
    before = sha256_file(str(layout_file))

    async with _panel(ctx) as p:
        await p.user.open("/layout")
        _click(_marked(p, "layout-select-2"))

        # a 5px step, then right, then check both the document and the queued command
        _click(_marked(p, "layout-step-5"))
        _click(_marked(p, "layout-right"))
    commands = [c for c in bus.drain() if c.get("cmd") == "layout_edit"]
    kinds = [c["op"] for c in commands]
    assert kinds[0] == "select" and "set_rect" in kinds, kinds
    moved = [c for c in commands if c["op"] == "set_rect"][-1]
    assert moved["index"] == 2 and moved["layout"] == REAL_LAYOUT
    original = json.load(open(layout_file))["controls"][2]["at"]
    assert moved["rect"][0] == original[0] + 5, f"{moved['rect']} vs {original}"
    assert sha256_file(str(layout_file)) == before, "a nudge wrote to the file"


async def test_saving_writes_the_file(tmp_path, monkeypatch):
    root = _ui_project(tmp_path)
    directory = tmp_path / "layouts"
    directory.mkdir()
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json", directory / f"{REAL_LAYOUT}.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    bus = _live()
    ctx = PageContext(base_dir=root, bus=bus, bind="127.0.0.1")
    target = directory / f"{REAL_LAYOUT}.json"
    before = sha256_file(str(target))

    async with _panel(ctx) as p:
        await p.user.open("/layout")
        _click(_marked(p, "layout-select-1"))
        _click(_marked(p, "layout-step-10"))
        _click(_marked(p, "layout-down"))
        _click(_marked(p, "layout-save"))
        assert "saved" in _marked(p, "layout-outcome").text
    assert sha256_file(str(target)) != before
    assert len(os.listdir(directory)) >= 2, "a save must leave a backup next to the layout"


async def test_a_nudge_is_refused_when_the_display_shows_another_layout(tmp_path):
    """
    The safety property, at the page level: the document may be edited (it is only a file), but
    nothing is sent to the wall, and the page says why.
    """
    root = _ui_project(tmp_path)
    bus = _live(layout="freeform_demo")
    ctx = PageContext(base_dir=root, bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/layout")
        await p.user.should_see("a DIFFERENT layout")
        _click(_marked(p, "layout-select-0"))
        _click(_marked(p, "layout-right"))
        outcome = _marked(p, "layout-outcome")
        assert "not showing this layout" in outcome.text
    ops = [c["op"] for c in bus.drain() if c.get("cmd") == "layout_edit"]
    assert "set_rect" not in ops, ops


async def test_the_page_explains_a_grid_layout(tmp_path, monkeypatch):
    root = _ui_project(tmp_path)
    (tmp_path / "proj" / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": "demo_console"}}}) + "\n")
    async with _panel(PageContext(base_dir=root, bus=_live(layout="demo_console"),
                                  bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        await p.user.should_see("This is a grid layout")


async def test_the_page_says_when_the_mode_is_not_a_control_panel(tmp_path):
    root = _ui_project(tmp_path)
    (tmp_path / "proj" / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "systeminformation"}}}) + "\n")
    async with _panel(PageContext(base_dir=root, bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        await p.user.should_see("No control panel mode")
