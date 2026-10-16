"""
Editing a control: duplicating one, and setting the colours it actually draws.

Both are STRUCTURAL edits — a copy changes the control list, and a colour is resolved when the control
is built — so both write immediately and the wall rebuilds, the same way add and remove already do.

Colour keys are not guessed. controlpanel.controls.COLOUR_KEYS says which ones each type reads, and the
first test walks the classes and their bases to hold that table to the code, because a picker for a
knob the class ignores is worse than no picker at all: it looks like it worked.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from controlpanel import paths as cp_paths                                 # noqa: E402
from controlpanel.controls import COLOUR_KEYS, CONTROL_CLASSES             # noqa: E402
from controlpanel.layout import LayoutError, load_layout                   # noqa: E402
from controlpanel.registry import CONTROL_TYPES                            # noqa: E402
from core.layout_edit import LayoutEditor                                  # noqa: E402

from panel.app import PageContext                                          # noqa: E402
from test_layout_page import REAL_LAYOUT                                   # noqa: E402
from test_transport import _bus, _click, _marked, _panel                   # noqa: E402


def _copy_layout(tmp_path, monkeypatch, source=REAL_LAYOUT, name="editme"):
    """A writable copy of a real layout, so no test edits a shipped one."""
    directory = tmp_path / "layouts"
    directory.mkdir(exist_ok=True)
    shutil.copy2(cp_paths.LAYOUTS_DIR / f"{source}.json", directory / f"{name}.json")
    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", directory)
    return directory / f"{name}.json"


def _gui_reads(cls) -> set:
    """Every colour key a class or its bases resolves, read off the source rather than assumed."""
    found = set()
    for base in cls.__mro__:
        if not getattr(base, "__module__", "").startswith("controlpanel.controls"):
            continue
        source = inspect.getsource(base)
        found |= set(re.findall(r'_color\(\s*"([^"]+)"', source))
        found |= set(re.findall(r'spec\.get\(\s*"([a-z_]*rgb)"', source))
    return found


def _own_reads(cls) -> set:
    """The colour keys the class's own block reads (not its bases')."""
    source = inspect.getsource(cls)
    return (set(re.findall(r'_color\(\s*"([^"]+)"', source))
            | set(re.findall(r'spec\.get\(\s*"([a-z_]*rgb)"', source)))


def test_the_colour_key_table_matches_the_code():
    """
    Both directions, with one deliberate asymmetry: the table may not offer a key a class (or a base)
    does not read — no dead knobs — and it must offer every key the class's OWN code reads. A base may
    resolve a colour the subclass never draws (the discrete switches share a base that resolves a lever
    colour), and offering that on a knob would be the dead knob again.
    """
    for ctype, cls in CONTROL_CLASSES.items():
        if cls is None:
            continue
        declared = set(COLOUR_KEYS.get(ctype, ()))
        reads = _gui_reads(cls) | ({"color"} if _gui_reads(cls) else set())
        assert declared <= reads, f"{ctype}: table offers {sorted(declared - reads)}, unread by the class"
        assert _own_reads(cls) <= declared, f"{ctype}: reads {sorted(_own_reads(cls) - declared)}, not offered"
    assert set(COLOUR_KEYS) == set(CONTROL_TYPES), "the table must name every control type"


def test_a_gauge_offers_the_needle_and_the_clock_offers_its_hands():
    """The two the request was about, named so a rename cannot quietly drop them."""
    assert "needle_rgb" in COLOUR_KEYS["gauge_round"]
    assert "hub_rgb" in COLOUR_KEYS["gauge_round"]
    assert "hand_rgb" in COLOUR_KEYS["clock"]


def test_duplicating_copies_the_control_next_to_its_original(tmp_path, monkeypatch):
    target = _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    before = [dict(c) for c in editor.controls()]
    index = next(i for i, c in enumerate(before) if isinstance(c.get("at"), list))

    result = editor.duplicate_control(index)
    assert result["ok"], result
    assert result["index"] == index + 1                    # next to its source, not appended
    controls = editor.controls()
    assert len(controls) == len(before) + 1
    assert controls[index]["at"] != controls[index + 1]["at"], "the copy must not sit exactly on top"
    assert {k: v for k, v in controls[index + 1].items() if k != "at"} == \
           {k: v for k, v in controls[index].items() if k != "at"}, "a copy is a copy"

    # and it is a layout the loader accepts, so it can be written
    assert editor.validate()[0] == ()
    assert editor.save().ok
    assert json.loads(target.read_text())[ "controls"][index + 1]["at"] == controls[index + 1]["at"]


def test_duplicating_clamps_the_copy_inside_the_canvas(tmp_path, monkeypatch):
    """A box outside the canvas cannot be nudged back — the loader refuses it — so a copy must land in."""
    target = _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    w, h = editor.canvas()
    controls = editor.controls()
    index = next(i for i, c in enumerate(controls) if isinstance(c.get("at"), list))
    _x, _y, cw, ch = editor.rect_of(index)
    controls[index]["at"] = [w - cw - 5, h - ch - 5]       # inside, but 24px from out
    result = editor.duplicate_control(index)
    assert result["ok"], result
    x, y = editor.controls()[index + 1]["at"]
    assert 0 <= x and 0 <= y and x + (editor.rect_of(index + 1) or (0, 0, 0, 0))[2] <= w


def test_duplicating_refuses_an_index_that_is_not_there(tmp_path, monkeypatch):
    _copy_layout(tmp_path, monkeypatch)
    result = LayoutEditor("editme").duplicate_control(99)
    assert result["ok"] is False and "no control #99" in result["reason"]


def test_setting_a_colour_writes_it_and_clearing_it_puts_the_default_back(tmp_path, monkeypatch):
    target = _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    gauge = next(i for i, c in enumerate(editor.controls()) if c.get("type") == "gauge_round")

    assert editor.set_color(gauge, "needle_rgb", [255, 0, 0])["ok"]
    assert editor.save().ok
    assert json.loads(target.read_text())["controls"][gauge]["needle_rgb"] == [255, 0, 0]

    assert editor.set_color(gauge, "needle_rgb", None)["ok"]
    assert editor.save().ok
    assert "needle_rgb" not in json.loads(target.read_text())["controls"][gauge]


def test_a_bad_colour_is_refused_by_the_wall_rules_not_by_a_second_opinion(tmp_path, monkeypatch):
    _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    gauge = next(i for i, c in enumerate(editor.controls()) if c.get("type") == "gauge_round")

    for bad in ([255, 0], [255, 0, 300], ["red", 0, 0], [1.5, 0, 0], "red"):
        result = editor.set_color(gauge, "needle_rgb", bad)
        assert result["ok"] is False, bad
        assert "three whole numbers" in result["reason"], result["reason"]
    assert "needle_rgb" not in editor.controls()[gauge], "a refused colour must not be kept"
    assert editor.set_color(gauge, "not_a_colour", [1, 2, 3])["ok"] is False


def test_the_loader_refuses_a_colour_key_that_is_not_a_colour():
    """The rule lives in the loader, so hand-typed JSON faces it too — not just the page."""
    doc = json.loads((cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json").read_text())
    doc["controls"][0]["needle_rgb"] = "red"
    with open(cp_paths.LAYOUTS_DIR / f"{REAL_LAYOUT}.json") as fh:
        pass
    from controlpanel.layout import layout_from_data
    try:
        layout_from_data(doc, name="probe")
    except LayoutError as e:
        assert "needle_rgb" in str(e) and "three whole numbers" in str(e)
    else:
        raise AssertionError("a string colour must be refused")


async def test_the_page_offers_duplicate_and_the_colours_of_the_selected_control(tmp_path, monkeypatch):
    target = _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    gauge = next(i for i, c in enumerate(editor.controls()) if c.get("type") == "gauge_round")
    project = tmp_path / "proj"
    (project / "configs").mkdir(parents=True)
    (project / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": "editme"}}}, indent=2) + "\n")

    async with _panel(PageContext(base_dir=str(project), bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        await p.user.should_see("duplicate")                    # one per row
        _click(_marked(p, f"layout-select-{gauge}"))            # pick the gauge
        await p.user.should_see("needle_rgb")                   # its colours are offered
        await p.user.should_see("hub_rgb")
        before = json.loads(target.read_text())["controls"]
        _click(_marked(p, f"layout-duplicate-{gauge}"))
        after = json.loads(target.read_text())["controls"]

    assert len(after) == len(before) + 1, "the copy must be written, not just staged"


    # WHICH control, not just that one appeared: pressing a row's button and getting the bottom row
    # copied is what happened when this lambda closed over the loop variable instead of the row.
    source, copy = before[gauge], after[gauge + 1]
    assert (copy.get("type"), copy.get("sprite")) == (source.get("type"), source.get("sprite")), \
        "the copy must be a copy of the control you pressed"
    assert copy.get("at") != source.get("at"), "and nudged clear of it"
    assert after[gauge].get("type") == before[gauge].get("type"), "the source must be untouched"
    last = before[-1].get("type")
    assert [c.get("type") for c in after].count(last) == [c.get("type") for c in before].count(last), \
        "the LAST control was copied instead of the selected one"


async def test_the_pad_offers_coarse_steps_and_they_move_that_far(tmp_path, monkeypatch):
    """
    Fine steps place an overlay exactly; coarse ones cross a panel in a press or two. Both belong, and
    the button has to actually move by the number on it — a step that is offered but rounds elsewhere
    would be worse than not offering it.
    """
    from panel.app import _LAYOUT_STEPS

    _copy_layout(tmp_path, monkeypatch)
    editor = LayoutEditor("editme")
    project = tmp_path / "proj"
    (project / "configs").mkdir(parents=True)
    (project / "modes_config.json").write_text(json.dumps({"modes": {
        "0": {"type": "controlpanel", "layout_file": "editme"}}}, indent=2) + "\n")
    index = 0
    start_x = editor.rect_of(index)[0]

    async with _panel(PageContext(base_dir=str(project), bus=_bus(), bind="127.0.0.1")) as p:
        await p.user.open("/layout")
        _click(_marked(p, f"layout-select-{index}"))
        for step in (25, 50, 100):
            assert step in _LAYOUT_STEPS
            await p.user.should_see(f"{step}px")
        _click(_marked(p, "layout-step-100"))
        _click(_marked(p, "layout-right"))
        moved = _marked(p, "layout-field-x").value

    assert moved == start_x + 100, f"a 100px step must move 100px, moved {moved - start_x}"
