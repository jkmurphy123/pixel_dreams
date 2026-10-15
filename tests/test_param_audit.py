"""
core/param_audit.py — the parameter exposure audit.

The auditor makes claims about OTHER code ("this value is hardcoded and worth a knob"), so its rules
are pinned here against synthetic sources where the answer is known, plus one check against the real
tree to prove it finds the case the design named.

The rules that matter most are the NEGATIVE ones: a placeholder the mode overwrites itself is not a
knob, and a value that already comes from config is not one either. Getting those wrong is how an
audit turns into a list nobody trusts.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_json                              # noqa: E402
from core.param_audit import (                                 # noqa: E402
    audit,
    audit_source,
    group_candidates,
    render_report,
    usage_by_mode,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARDCODED = '''
class Mode:
    def __init__(self, config):
        self.config = config
        self.fg = (235, 235, 235)
        self.bg = (0, 0, 0)
        self.accent = (255, 200, 90)
        self.margin_x = 20
        self.alpha = 255

    def enter(self, manager):
        self.w = manager.width
        self.margin_x = int(self.w * 0.06)
        self.font_size = max(16, int(min(self.w, self.h) * 0.03))

    def render(self, screen):
        font = manager.cache.get_font(None, 14, bold=False)
        overlay = pygame.Surface((10, 10), pygame.SRCALPHA)
        overlay.set_alpha(128)
        time.sleep(2)
        screen.blit(font.render("x", True, self.fg), (self.margin_x, 0))
'''

ALREADY_TUNABLE = '''
class Mode:
    def __init__(self, config):
        self.font_size_cfg = config.get("font_size", None)
        self.col_pad_scale = float(config.get("col_pad_scale", 0.02))
        self.burst_range = config.get("burst_duration_range", [0.6, 1.4])
        self.fg = config.get("fg_color", (200, 200, 200))

    def enter(self, manager):
        self.w = manager.width
        self.refresh_hz = int(config.get("refresh_hz", 2))
        self._refresh_period = 1.0 / max(0.1, self.refresh_hz)
        self.font_size = int(self.font_size_cfg) if self.font_size_cfg else max(14, int(self.w * 0.04))
'''

INDEX_NOISE = '''
class Mode:
    def __init__(self, config):
        self.count = 0
        self.index = 1
        self.offset = -1
'''


def _by_attr(result, attr):
    return [c for c in result.candidates if c.attr == attr]


def _group(result, attr, kind=None):
    return next((g for g in group_candidates(result, used_only=False)
                 if g["attr"] == attr and (kind is None or g["kind"] == kind)), None)


# ---------------------------------------------------------------- what IS a candidate

def test_a_plain_hardcoded_colour_is_a_candidate():
    result = audit_source(HARDCODED, mode="m")
    fg = _by_attr(result, "fg")
    assert fg and fg[0].kind == "colour" and fg[0].status == "operative"
    assert "'(235, 235, 235)'" in fg[0].literal or "(235, 235, 235)" in fg[0].literal
    assert "colour" in fg[0].suggestion


def test_black_and_white_are_still_colours():
    """0/1/2/-1 are index noise, but (0, 0, 0) is a colour someone may well want to change."""
    result = audit_source(HARDCODED, mode="m")
    assert _by_attr(result, "bg"), "a black background is a colour candidate"


def test_a_literal_font_size_at_the_call_site_is_a_candidate():
    result = audit_source(HARDCODED, mode="m")
    found = [c for c in result.candidates if c.kind == "font_size"]
    assert found, [c.__dict__ for c in result.candidates]
    assert "get_font" in found[0].code


def test_an_alpha_and_a_sleep_are_candidates():
    result = audit_source(HARDCODED, mode="m")
    assert _by_attr(result, "alpha") or [c for c in result.candidates if c.kind == "alpha"]
    assert [c for c in result.candidates if c.kind == "timing"], "sleep(2) is pacing"


def test_a_ratio_behind_a_derived_size_is_a_candidate_with_its_value():
    result = audit_source(HARDCODED, mode="m")
    group = _group(result, "font_size")
    assert group is not None, [c.__dict__ for c in result.candidates]
    assert group["values"] == ["0.03"]
    assert "0.03" in group["suggestion"]
    assert "max(16, ...)" in group["detail"], group["detail"]


# ---------------------------------------------------------------- what is NOT

def test_a_literal_the_mode_overwrites_itself_is_a_placeholder_not_a_knob():
    """
    `self.margin_x = 20` followed by `self.margin_x = int(self.w * 0.06)` is a default, not a knob.
    Reporting the 20 would send the reviewer to change a number that has no effect.
    """
    result = audit_source(HARDCODED, mode="m")
    margins = _by_attr(result, "margin_x")
    assert len(margins) == 2, margins
    literal = next(c for c in margins if c.literal == "20")
    assert literal.status == "placeholder"
    assert "int(self.w * 0.06)" in literal.detail
    # and it is not in the reviewed list
    assert not any(g["attr"] == "margin_x" and g["values"] == ["20"]
                   for g in group_candidates(result, used_only=False))


def test_a_value_that_already_comes_from_config_is_not_a_candidate():
    result = audit_source(ALREADY_TUNABLE, mode="m")
    assert not _by_attr(result, "col_pad_scale"), "config-driven ratio proposed again"
    assert not _by_attr(result, "burst_range"), "config-driven list proposed again"
    assert not [c for c in result.candidates if c.attr == "fg"], "config-driven colour proposed"


def test_a_ratio_derived_from_another_attribute_is_not_a_new_knob():
    """`1.0 / max(0.1, self.refresh_hz)` is a consequence of refresh_hz, which is already a param."""
    result = audit_source(ALREADY_TUNABLE, mode="m")
    assert not _by_attr(result, "_refresh_period"), \
        [c.__dict__ for c in result.candidates if c.attr == "_refresh_period"]


def test_index_and_flag_literals_are_skipped():
    result = audit_source(INDEX_NOISE, mode="m")
    assert result.candidates == []
    assert result.trivial == 3


def test_one_off_coordinates_are_kept_out_of_the_review_list():
    """A coordinate is recorded but never ranked: it is layout arithmetic, not a knob."""
    source = '''
class Mode:
    def render(self, screen):
        self.right_edge = 1440
        self.baseline = 480
        pad = 10
'''
    result = audit_source(source, mode="m")
    kinds = {c.attr: c.kind for c in result.candidates}
    assert kinds["right_edge"] == "geometry" and kinds["baseline"] == "geometry"
    # the coordinates are excluded from the review list, the padding is not
    assert [g["attr"] for g in group_candidates(result, used_only=False)] == ["pad"]
    assert {g["attr"] for g in group_candidates(result, used_only=False,
                                                include_geometry=True)} == {"right_edge",
                                                                            "baseline", "pad"}
    # a knob-named local IS in scope (padding is a tuning value), a coordinate local is not
    assert kinds.get("pad") in ("gap", "margin"), kinds


def test_a_bare_coordinate_local_is_out_of_scope():
    result = audit_source("class M:\n    def r(self):\n        x = 480\n        y = 720\n", mode="m")
    assert result.candidates == [], "locals with coordinate names are not appearance knobs"


# ---------------------------------------------------------------- grouping and reach

def test_the_same_knob_at_several_lines_is_one_row_with_its_values():
    source = '''
class Mode:
    def a(self):
        self._accent = (140, 255, 170)
    def b(self):
        self._accent = (255, 200, 90)
    def c(self):
        self._accent = (255, 200, 90)
'''
    result = audit_source(source, mode="m")
    groups = [g for g in group_candidates(result, used_only=False) if g["attr"] == "_accent"]
    assert len(groups) == 1
    assert groups[0]["count"] == 3 and groups[0]["values"] == ["(140, 255, 170)", "(255, 200, 90)"]
    assert "state accent" in groups[0]["suggestion"], groups[0]["suggestion"]


def test_usage_by_mode_counts_profiles_per_type():
    profiles = {"a.json": {"0": {"type": "StatusTicker"}, "1": {"type": "slideshow"}},
                "b.json": {"0": {"type": "status_ticker"}}}
    usage = usage_by_mode(profiles)
    assert usage["statusticker"] == ("a.json", "b.json")
    assert usage["slideshow"] == ("a.json",)


def test_a_mode_a_profile_uses_outranks_an_identical_unused_one():
    src = '''
class Mode:
    def __init__(self, config):
        self.fg = (10, 10, 10)
'''
    used = audit_source(src, mode="used", profiles=("a.json", "b.json"))
    unused = audit_source(src, mode="unused", profiles=())
    blended = {"candidates": used.candidates + unused.candidates, "modes": [], "totals": {}}
    ranked = group_candidates(blended, used_only=True)
    assert [g["mode"] for g in ranked] == ["used"]
    assert len(group_candidates(blended, used_only=False)) == 2


# ---------------------------------------------------------------- the real tree

@pytest.fixture(scope="module")
def real():
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {}).get("types", {})

    def _profile_modes(rel):
        from core import profiles as profiles_mod

        modes, _meta = profiles_mod.profile_modes(os.path.join(BASE_DIR, rel))
        return modes

    profiles = {"modes_config.json": _profile_modes("modes_config.json")}
    for name in sorted(os.listdir(os.path.join(BASE_DIR, "configs"))):
        if name.endswith(".json"):
            profiles[f"configs/{name}"] = _profile_modes(f"configs/{name}")
    return audit(BASE_DIR, registry, profiles)


def test_the_real_tree_audits_without_crashing(real):
    assert real["totals"]["modules"] >= 50, real["totals"]
    assert not [c for c in real["candidates"] if c.attr == "(unparsable)"], \
        [c.detail for c in real["candidates"] if c.attr == "(unparsable)"]


def test_the_audit_finds_the_case_the_design_named(real):
    """
    Design §10 Phase 5 names it explicitly: "the derived sizes (ticker font from self.w)". If the
    auditor cannot find that, it cannot find anything.
    """
    ticker = [g for g in group_candidates(real) if "status_ticker" in g["mode"]]
    assert ticker, [g["mode"] for g in group_candidates(real)][:10]
    attrs = {g["attr"] for g in ticker}
    assert "margin_x" in attrs and "margin_y" in attrs, attrs
    assert all(g["kind"] == "ratio" for g in ticker if g["attr"].startswith("margin"))


def test_the_real_numbers_are_the_ones_the_report_quotes(real):
    totals = real["totals"]
    groups = group_candidates(real)
    # the shape of the result, so a change in the rules is visible here rather than in a document
    assert totals["worth_reviewing"] >= 100, totals
    assert len(groups) >= 100
    assert totals["placeholder"] > 50, "places that overwrite their own literals should be numerous"
    kinds = {g["kind"] for g in groups}
    assert {"ratio", "colour", "font_size"} <= kinds, kinds


def test_the_report_renders_a_table_of_knobs(real):
    text = render_report(real, top=5)
    assert "Machine scan" in text and "worth reviewing" in text
    assert text.count("\n|") >= 8, text
    assert "status_ticker" in text or "ratio" in text
