"""
A field with known values becomes a dropdown you can still type into.

The schema said the value is free text with known examples (suggestions). The page offered those as a
line of text you then had to copy by hand. For a layout that is the wrong shape of help: the layouts
on disk are the obvious answers, and a layout file living anywhere else is still legal — so the field
has to be a picker AND a text box.

The name of the source travels in the schema; the values are resolved in the panel, because that is
where the asset paths are known and core.params must not read the disk.
"""

from __future__ import annotations

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.params import ParamSpec, resolve_params                         # noqa: E402
from panel.app import _suggestions_for                                    # noqa: E402


def _field(source):
    p = ParamSpec("layout_file", "text", "layout_file", "layout")
    p.suggestions_from = source
    return p


def test_the_registry_names_a_source_for_both_pickers():
    registry = json.loads(open(os.path.join(BASE_DIR, "modes_registry.json")).read())
    params = registry["types"]["controlpanel"]["params"]
    assert params["layout_file"]["suggestions_from"] == "layouts"
    assert params["background_image"]["suggestions_from"] == "backgrounds"


def test_the_spec_carries_the_name_without_touching_the_disk():
    """params.py stays pure: it passes the NAME along, it does not resolve it."""
    registry = json.loads(open(os.path.join(BASE_DIR, "modes_registry.json")).read())
    specs, _warnings = resolve_params({"layout_file": "steampunk1"},
                                      registry["types"]["controlpanel"])
    spec = next(s for s in specs if s.key == "layout_file")
    assert spec.suggestions_from == "layouts"
    assert spec.suggestions == ()


def test_the_panel_turns_the_name_into_the_layouts_on_disk():
    values = _suggestions_for(_field("layouts"), extra=("steampunk1",))
    assert "steampunk1" in values
    assert len(values) == len(set(values)), "the current value must not be offered twice"


def test_a_path_outside_the_assets_tree_stays_a_legal_answer():
    """A closed set would hide every layout that does not live under assets/control_panel/layouts/."""
    values = _suggestions_for(_field("layouts"), extra=("/home/ubuntu/my_panel.json",))
    assert "/home/ubuntu/my_panel.json" in values


def test_a_source_with_nothing_to_read_yields_nothing_rather_than_failing(tmp_path, monkeypatch):
    """
    No assets on disk (or no package at all, as in a test sandbox): a missing picker is not an error,
    and the field must still render — the current value is all it offers.
    """
    from controlpanel import paths as cp_paths

    monkeypatch.setattr(cp_paths, "LAYOUTS_DIR", tmp_path / "not_here")
    assert _suggestions_for(_field("layouts"), extra=("keep_me",)) == ("keep_me",)


def test_an_unknown_source_name_is_harmless():
    assert _suggestions_for(_field("nowhere"), extra=("x",)) == ("x",)
