# tests/test_params.py
#
# The parameter model: inference from a value's shape, inference from a key's name when there
# is no value, the registry schema overlay, and the completeness guarantee the form depends on.
# Several cases here are REGRESSIONS for bugs the first draft shipped (see the comments).

import sys
import os

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.params import (  # noqa: E402
    GROUPS,
    WIDGETS,
    coverage,
    group_params,
    humanize,
    infer_group,
    infer_type_for_absent,
    infer_widget,
    infer_widget_for_absent,
    is_secret_key,
    resolve_params,
    schema_entries,
    shape_of,
)

SLIDESHOW_SPEC = {
    "entrypoint": "modes.slideshow_mode:SlideshowMode",
    "required": ["folder", "duration"],
    "optional": ["font_size", "overlay_font_size", "show_time", "weather_units",
                 "crypto_ids", "accent_rgb", "show_weather"],
}
SLIDESHOW_INSTANCE = {
    "folder": "/images", "duration": 120, "font_size": 192, "show_time": True,
    "crypto_ids": ["bitcoin", "ethereum"], "accent_rgb": [255, 204, 132],
}


# ---------------------------------------------------------------- shape_of

@pytest.mark.parametrize("value,expected", [
    (True, "bool"), (5, "int"), (2.5, "float"), ("hi", "str"),
    ([255, 1, 2], "list[int]"), ([1.5, 3.0], "list[float]"), (["a", "b"], "list[str]"),
    ([[1, 2, 3]], "list[list[int]]"), ([{"a": 1}], "list[dict]"), ({"a": 1}, "dict"), ([], "list"),
])
def test_shape_of(value, expected):
    assert shape_of(value) == expected


# ---------------------------------------------------------------- inference from values

@pytest.mark.parametrize("value,expected", [
    (True, "switch"), (False, "switch"),
    (7, "number"), (2.5, "number"),
    ("hello", "text"),
    ([255, 204, 132], "color"),
    ([0.6, 1.4], "range"),
    ([1, 3], "range"),
    (["a", "b"], "stringlist"),
    ([[220, 150, 60], [70, 170, 210]], "palette"),
    ([{"hostname": "x"}], "json"),
    ({"nested": 1}, "json"),
])
def test_infer_widget_from_value(value, expected):
    assert infer_widget(value) == expected


def test_secret_keys_never_get_a_usable_widget():
    """A secret's value must never reach the browser, whatever shape it has."""
    assert infer_widget("sk-live-abc123", "openai_api_key") == "secret"
    assert infer_widget("sk-live", "OPENAI_API_KEY") == "secret"
    assert infer_widget_for_absent("openai_api_key") == "secret"
    assert isinstance(is_secret_key("panel_token"), bool) and is_secret_key("panel_token")
    assert not is_secret_key("font_size")


# ---------------------------------------------------------------- inference from the name

@pytest.mark.parametrize("key,expected", [
    ("show_clock", "switch"),      # regression: matched the colour rule in the first draft
    ("show_seconds", "switch"),
    ("is_portrait", "switch"),
    ("enable_grid", "switch"),
    ("grid_enabled", "switch"),
    ("labels_visible", "switch"),
    ("folder", "path"),            # regression: bare "folder" missed the path rule
    ("image_folder", "path"),
    ("data_file", "path"),
    ("cache_dir", "path"),
    ("quotes_file", "path"),
    ("font_size", "number"),
    ("cell_size_px", "number"),
    ("overlay_margin", "number"),
    ("scroll_px_per_sec", "number"),
    ("accent_rgb", "color"),
    ("status_labels", "stringlist"),
    ("crypto_ids", "stringlist"),
    ("event_interval_range", "range"),
    ("palette", "json"),           # ambiguous by name: many RGB triples OR a scheme name
    ("devices", "json"),
    ("font_name", "text"),         # regression: "font" used to imply a number
    ("weather_units", "text"),     # the schema supplies the real choices
    ("prompt", "text"),
    ("openai_api_key", "secret"),
])
def test_infer_widget_for_absent(key, expected):
    assert infer_widget_for_absent(key) == expected


@pytest.mark.parametrize("key,widget,expected", [
    ("font_size", "number", "int"),
    ("refresh_hz", "number", "float"),
    ("scroll_px_per_sec", "number", "float"),
    ("typing_cps", "number", "float"),
    ("duration", "number", "int"),
    ("accent_rgb", "color", "list[int]"),
    ("folder", "path", "str"),
    ("show_time", "switch", "bool"),
    ("crypto_ids", "stringlist", "list"),
])
def test_infer_type_for_absent(key, widget, expected):
    assert infer_type_for_absent(key, widget) == expected


@pytest.mark.parametrize("key,widget,expected", [
    ("font_size", "number", "appearance"),
    ("accent_rgb", "color", "appearance"),
    ("palette", "palette", "appearance"),
    ("folder", "path", "data"),
    ("overlay_margin", "number", "layout"),
    ("portrait_layout", "text", "layout"),
    ("duration", "number", "behaviour"),
    ("seed", "number", "behaviour"),
])
def test_infer_group(key, widget, expected):
    assert infer_group(key, widget) == expected


@pytest.mark.parametrize("key,expected", [
    ("overlay_font_size", "Overlay font size"),
    ("accent_rgb", "Accent RGB"),
    ("crt_vignette", "CRT vignette"),        # regression: .capitalize() lowercased "CRT"
    ("api_update_interval_min", "API update interval min"),
    ("crypto_ids", "Crypto IDs"),
    ("x", "X"),
    ("", ""),
])
def test_humanize(key, expected):
    assert humanize(key) == expected


# ---------------------------------------------------------------- schema overlay

def test_schema_entry_overrides_inference():
    spec = dict(SLIDESHOW_SPEC)
    spec["params"] = {
        "font_size": {"widget": "number", "min": 8, "max": 400, "step": 2,
                      "label": "Clock font px", "group": "layout", "help": "192 on the wall"},
        "weather_units": {"choices": ["imperial", "metric"]},
    }
    params, warnings = resolve_params(SLIDESHOW_INSTANCE, spec)
    assert warnings == []
    by_key = {p.key: p for p in params}

    fs = by_key["font_size"]
    assert (fs.min, fs.max, fs.step) == (8, 400, 2)
    assert fs.label == "Clock font px"
    assert fs.group == "layout"
    assert fs.source == "schema"
    assert fs.help == "192 on the wall"

    # a plain string with a known closed set becomes a dropdown
    wu = by_key["weather_units"]
    assert wu.widget == "choice"
    assert wu.choices == ("imperial", "metric")


def test_schema_bad_entries_are_reported_and_ignored():
    spec = dict(SLIDESHOW_SPEC)
    spec["params"] = {
        "font_size": {"widget": "slider9000"},
        "duration": {"group": "nonsense"},
        "show_time": "not an object",
    }
    spec_entry, warnings = schema_entries(spec)
    assert len(warnings) == 3
    assert any("unknown widget" in w for w in warnings)
    assert any("unknown group" in w for w in warnings)
    assert any("expected object" in w for w in warnings)

    # the fields still resolve — inference covers what the schema could not say
    params, resolve_warnings = resolve_params(SLIDESHOW_INSTANCE, spec)
    by_key = {p.key: p for p in params}
    assert by_key["font_size"].widget == "number"
    assert by_key["duration"].group in GROUPS
    assert by_key["show_time"].widget == "switch"


def test_schema_secret_flag_and_default():
    spec = dict(SLIDESHOW_SPEC)
    spec["optional"] = list(spec["optional"]) + ["api_endpoint"]
    spec["params"] = {"api_endpoint": {"secret": True, "default": "https://x/api"}}
    params, _ = resolve_params({}, spec)
    by_key = {p.key: p for p in params}
    assert by_key["api_endpoint"].widget == "secret"
    assert by_key["api_endpoint"].secret is True
    assert by_key["api_endpoint"].has_default is True
    assert by_key["api_endpoint"].default == "https://x/api"


def test_suggestions_stay_free_text():
    """Comparison-only evidence must not become a closed dropdown."""
    spec = dict(SLIDESHOW_SPEC)
    spec["params"] = {"weather_units": {"suggestions": ["imperial"]}}
    params, _ = resolve_params(SLIDESHOW_INSTANCE, spec)
    wu = {p.key: p for p in params}["weather_units"]
    assert wu.widget == "text"
    assert wu.suggestions == ("imperial",)
    assert wu.choices == ()


# ---------------------------------------------------------------- resolution and origin

def test_present_and_absent_params_are_both_offered():
    params, _ = resolve_params(SLIDESHOW_INSTANCE, SLIDESHOW_SPEC)
    keys = [p.key for p in params]
    # every key the profile sets, and every key the registry declares
    for key in list(SLIDESHOW_INSTANCE) + SLIDESHOW_SPEC["optional"] + SLIDESHOW_SPEC["required"]:
        assert key in keys, f"{key} missing from the form"
    by_key = {p.key: p for p in params}
    assert by_key["folder"].present is True and by_key["folder"].origin == "profile"
    assert by_key["overlay_font_size"].present is False and by_key["overlay_font_size"].origin == "absent"
    assert by_key["overlay_font_size"].value is None
    assert by_key["folder"].required is True
    assert by_key["overlay_font_size"].required is False


def test_override_origin_is_reported():
    params, _ = resolve_params(SLIDESHOW_INSTANCE, SLIDESHOW_SPEC,
                              overridden_keys=("folder", "font_size"))
    by_key = {p.key: p for p in params}
    assert by_key["folder"].origin == "local override"
    assert by_key["show_time"].origin == "profile"


def test_undeclared_config_key_is_warned_about_and_still_rendered():
    instance = dict(SLIDESHOW_INSTANCE, made_up_key=1)
    params, warnings = resolve_params(instance, SLIDESHOW_SPEC)
    assert "made_up_key" in [p.key for p in params]
    assert any("made_up_key" in w for w in warnings)
    assert any("not declared" in w for w in warnings)


def test_grouping_and_order_put_set_values_first():
    params, _ = resolve_params(SLIDESHOW_INSTANCE, SLIDESHOW_SPEC)
    groups = group_params(params)
    names = [g for g, _ in groups]
    # empty groups are omitted, and what is returned follows the GROUPS order
    assert names == [g for g in GROUPS if g in names]
    assert names, "no groups produced"
    for group, items in groups:
        present_flags = [i.present for i in items]
        assert present_flags == sorted(present_flags, reverse=True), f"{group} not ordered"


def test_coverage_is_complete_for_the_form():
    cov = coverage(SLIDESHOW_INSTANCE, SLIDESHOW_SPEC)
    assert cov["missing_present"] == []
    assert cov["missing_declared"] == []
    declared = set(SLIDESHOW_SPEC["required"]) | set(SLIDESHOW_SPEC["optional"])
    present = set(SLIDESHOW_INSTANCE)
    assert cov["rendered"] == len(declared | present)


def test_widgets_are_all_known():
    """Every widget the resolver can emit must be one the UI knows how to draw."""
    samples = [True, 1, 1.5, "s", [255, 1, 2], [1, 2], ["a"], [[1, 2, 3]], [{"a": 1}],
               {"a": 1}, [], None]
    for value in samples:
        assert infer_widget(value, "k") in WIDGETS
    for key in ("show_x", "folder", "accent_rgb", "crypto_ids", "whatever_empty"):
        assert infer_widget_for_absent(key) in WIDGETS
