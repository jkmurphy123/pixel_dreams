# tests/test_schema_scaffold.py
#
# The schema generator: what it reads out of a mode's code, what it refuses to record, and the
# merge rules that keep a hand-edited schema safe. The negative cases matter most — a wrong
# `widget` in the registry makes the form WORSE than plain inference, which is how the first
# draft shipped `accent_rgb` as a list of strings.

import json
import os
import sys
from collections import OrderedDict

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.schema_scaffold import (  # noqa: E402
    _candidate_widget,
    _clean_choices,
    _is_meaningful_correction,
    _literal,
    analyse,
    build_draft,
    merge_into_registry,
    scan_module,
)

SAMPLE = '''
"""A synthetic mode used by the tests, mirroring the shipped patterns."""
_VALID_SCALE_MODES = {"stretch", "fit", "cover"}


class SampleMode:
    def __init__(self, config: dict):
        self.folder = config.get("folder", ".")
        self.duration = int(config.get("duration", 12))
        self.pause = float(config.get("pause", 0.35))
        self.show_time = bool(config.get("show_time", True))
        self.auto_advance = bool(config.get("auto_advance", True))
        self.accent_rgb = tuple(config.get("accent_rgb", [180, 200, 255]))
        self.font_name = str(config.get("font_name", "dejavusansmono"))
        self.units = str(config.get("units", "imperial"))
        self.mode = str(config.get("mode", "fit"))
        if self.mode not in self._VALID_SCALE_MODES:
            self.mode = "fit"
        self.name = config.get("name", "")
        # reads the configured size, then OVERRIDES it from the screen: the real pattern in
        # modes/status_ticker_mode.py, which is what "derived" is meant to flag
        self.font_size = int(config.get("font_size", 48))
        self.font_size = max(14, int(self.w * 0.04))
        self.seed = config.get("seed", 1)

    def render(self, screen):
        if self.units == "imperial":
            pass
        if self.units == "metric":
            pass
'''


# ---------------------------------------------------------------- literals and scanning

@pytest.mark.parametrize("text,expected", [
    ("12", 12), ("0.35", 0.35), ("True", True), ("False", False),
    ("'fit'", "fit"), ('"cover"', "cover"), ("[255, 1, 2]", [255, 1, 2]),
    ("'fit',", "fit"), ("None", None), ("some_var", None), ("{'a': 1}", {"a": 1}),
])
def test_literal_parsing(text, expected):
    assert _literal(text) == expected


def test_scan_reads_coercions_defaults_and_choices():
    scan = scan_module(SAMPLE)
    keys = scan["keys"]
    assert keys["duration"]["coercion"] == "int"
    assert keys["pause"]["coercion"] == "float"
    assert keys["show_time"]["coercion"] == "bool"
    assert keys["font_name"]["coercion"] == "str"
    assert keys["duration"]["default"] == 12
    assert keys["accent_rgb"]["default"] == [180, 200, 255]
    # accepted values: from a declared set, and from comparisons
    assert keys["mode"]["from_set"] == ["cover", "fit", "stretch"]
    assert keys["units"]["compares"] == ["imperial", "metric"]
    assert keys["units"]["from_set"] == []


def test_scan_excludes_structural_keys():
    """'name' is the mode's display label, not a tunable parameter."""
    scan = scan_module(SAMPLE)
    assert "name" not in scan["keys"]
    assert "type" not in scan["keys"]


def test_scan_finds_only_genuinely_derived_values():
    scan = scan_module(SAMPLE)
    assert scan["derived"] == ["font_size"]      # computed from self.w
    assert "seed" not in scan["derived"]         # self.seed = seed is just storage
    assert "folder" not in scan["derived"]       # straight from config


# ---------------------------------------------------------------- widget decisions

def test_list_coercion_is_not_type_evidence():
    """`tuple(config.get("accent_rgb", [r,g,b]))` is a copy, not a list-of-strings."""
    assert _candidate_widget({"coercion": "tuple", "default": [180, 200, 255]}) == "color"
    assert _candidate_widget({"coercion": "list", "default": [1, 2, 3]}) == "range" or \
           _candidate_widget({"coercion": "list", "default": [1, 2, 3]}) == "color"


def test_a_closed_set_becomes_a_choice_but_comparisons_do_not():
    assert _candidate_widget({"coercion": "str", "from_set": ["a", "b"]}) == "choice"
    assert _candidate_widget({"coercion": "str", "compares": ["only-one"]}) == "text"
    assert _candidate_widget({"coercion": "str", "from_set": ["a", "b", "c"]}) == "choice"


def test_corrections_only_when_they_improve_on_the_name_heuristic():
    assert _is_meaningful_correction("text", "switch") is True       # a real upgrade
    assert _is_meaningful_correction("text", "number") is True
    assert _is_meaningful_correction("text", "choice") is True
    assert _is_meaningful_correction("number", "choice") is True
    assert _is_meaningful_correction("path", "text") is False        # keep the path picker
    assert _is_meaningful_correction("color", "text") is False
    assert _is_meaningful_correction("json", "text") is True         # text beats a JSON box
    assert _is_meaningful_correction("switch", "switch") is False    # nothing new


def test_choice_cleaning_drops_non_options():
    assert _clean_choices(["fit", "cover"]) == ["cover", "fit"]
    assert _clean_choices(["a/b.png", "with space", "x.y", "fit"]) == ["fit"]
    assert _clean_choices(["x" * 40, "ok"]) == ["ok"]
    assert _clean_choices([]) == []


# ---------------------------------------------------------------- end to end on a mini project

def _project(tmp_path):
    (tmp_path / "modes").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "modes" / "sample_mode.py").write_text(SAMPLE)
    registry = {
        "types": {
            "sample": {
                "entrypoint": "modes.sample_mode:SampleMode",
                "required": ["folder"],
                "optional": ["duration", "show_time", "accent_rgb"],
            }
        }
    }
    (tmp_path / "modes_registry.json").write_text(json.dumps(registry, indent=2))
    modes = {"0": {"type": "sample", "folder": "/x", "duration": 30, "show_time": True,
                   "accent_rgb": [1, 2, 3]}}
    return str(tmp_path), registry, [modes]


def test_drift_is_reported_for_code_keys_the_registry_lacks(tmp_path):
    base, registry, modes = _project(tmp_path)
    analysis = analyse(base, registry["types"], modes)
    drift = set(analysis["types"]["sample"]["drift"])
    assert {"pause", "font_name", "units", "mode", "font_size"} <= drift
    assert "folder" not in drift          # declared
    assert "name" not in drift            # structural, not a parameter


def test_draft_records_only_what_inference_cannot_know(tmp_path):
    base, registry, modes = _project(tmp_path)
    draft, analysis = build_draft(base, registry["types"], modes)
    entries = draft["sample"]

    # a bool the NAME already reveals (show_*) needs no schema entry...
    assert "widget" not in entries.get("show_time", {})
    # ...but one whose name looks like free text does
    assert entries["auto_advance"]["widget"] == "switch"
    assert entries["pause"]["widget"] == "number"            # float coercion
    assert entries["mode"]["choices"] == ["cover", "fit", "stretch"]
    assert entries["units"]["suggestions"] == ["imperial", "metric"]
    assert "choices" not in entries["units"]                 # not a closed set
    assert entries["font_size"]["derived"] is True
    assert entries["duration"]["default"] == 12
    assert entries["folder"]["default"] == "."
    # accent_rgb: no widget correction (colour is what inference says anyway)
    assert "widget" not in entries.get("accent_rgb", {})


def test_merge_is_additive_and_never_overwrites_hand_edits():
    registry = {"types": {"sample": {
        "entrypoint": "x:Y",
        "optional": ["duration"],
        "params": {"duration": {"min": 1, "max": 600, "label": "My label"}},
    }}}
    draft = {"sample": {"duration": {"min": 99, "default": 12}, "pause": {"widget": "number"}}}
    report = merge_into_registry(registry, draft)

    params = registry["types"]["sample"]["params"]
    assert params["duration"]["min"] == 1                      # yours wins
    assert params["duration"]["label"] == "My label"           # untouched
    assert params["duration"]["default"] == 12                 # a NEW key is added
    assert params["pause"] == {"widget": "number"}
    assert report["added_params"]["sample"] == ["duration", "pause"]


def test_merge_is_idempotent():
    registry = {"types": {"sample": {"entrypoint": "x:Y", "optional": []}}}
    draft = {"sample": {"pause": {"widget": "number"}}}
    merge_into_registry(registry, draft)
    snapshot = json.dumps(registry, sort_keys=True)
    report = merge_into_registry(registry, draft)
    assert json.dumps(registry, sort_keys=True) == snapshot
    assert report["added_params"] == {}
    assert report["skipped_existing"]["sample"] == ["pause"]


def test_fix_optional_appends_drift_keys_once():
    registry = {"types": {"sample": {"entrypoint": "x:Y", "optional": ["duration"]}}}
    drift = {"sample": ["pause", "font_name", "duration"]}      # duration already declared
    report = merge_into_registry(registry, {}, drift_keys=drift, fix_optional=True)
    assert registry["types"]["sample"]["optional"] == ["duration", "font_name", "pause"]
    assert report["added_optional"]["sample"] == ["font_name", "pause"]

    again = merge_into_registry(registry, {}, drift_keys=drift, fix_optional=True)
    assert again["added_optional"] == {}


def test_draft_is_json_serialisable(tmp_path):
    base, registry, modes = _project(tmp_path)
    draft, _ = build_draft(base, registry["types"], modes)
    assert json.loads(json.dumps(draft)) == draft
    assert isinstance(draft, dict)
    assert all(isinstance(v, dict) for v in draft.values())


# ---------------------------------------------------------------- the real project

def test_real_project_analysis_is_sane():
    """Smoke the analysis against the shipped tree, and pin the drift fix from this phase."""
    from core.config import load_json
    from core.profiles import profile_modes

    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    modes = []
    for path in [os.path.join(BASE_DIR, "modes_config.json")] + [
            os.path.join(BASE_DIR, "configs", f)
            for f in sorted(os.listdir(os.path.join(BASE_DIR, "configs")))
            if f.endswith(".json")]:
        profile, _ = profile_modes(path)
        if profile:
            modes.append(profile)

    analysis = analyse(BASE_DIR, registry, modes)
    assert analysis["totals"]["types"] == len(registry) == 53
    assert analysis["totals"]["types_without_module"] == 0

    # The drift fix landed: every key the shipped mode code reads is now declared, so a form
    # built from the registry cannot silently hide a knob any more.
    still_drifted = {t: i["drift"] for t, i in analysis["types"].items() if i["drift"]}
    assert still_drifted == {}, still_drifted

    # the keys that used to be undeclared are declared now
    slideshow = set(registry["slideshow"]["optional"])
    assert {"scale_mode", "overlay_margin", "dow_symbol", "scaled_cache_items"} <= slideshow
    assert "font_name" in registry["statusticker"]["optional"]

    # structural keys must never appear as drift
    for info in analysis["types"].values():
        assert not set(info["drift"]) & {"type", "name", "title"}

    # every type that has a module is analysed, and nothing is reported as a conflict without
    # a reason to believe the code over the name heuristic
    assert analysis["totals"]["widget_conflicts"] >= 1
