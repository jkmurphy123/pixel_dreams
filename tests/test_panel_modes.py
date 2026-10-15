# tests/test_panel_modes.py
#
# The generated parameter form (/mode/<n>). Two different proofs live here:
#   1. RENDERING: a fixture profile carrying every value shape the shipped modes use, rendered
#      through the real page builders in-process, asserting each field appears with the right
#      widget and that every field is read-only.
#   2. COVERAGE: a pure check over ALL 8 real profiles and every mode in them, asserting the
#      resolver offers every key the config sets and every key the registry declares. That is
#      the Phase 2 acceptance item (100% of params rendered) and it runs without a browser.
#
# Run standalone first when it fails (a page that raises can hang the whole suite):
#   timeout 90 python -m pytest tests/test_panel_modes.py -q

import json
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from nicegui import core, ui
from nicegui.testing.general import nicegui_reset_globals, prepare_simulation
from nicegui.testing.user import User

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.params import WIDGETS, coverage, resolve_params   # noqa: E402
from core import profiles as profiles_mod                   # noqa: E402
from core.bus import ControlBus                             # noqa: E402
from panel.app import PageContext, _hex_from_rgb, register_pages  # noqa: E402

#: A profile exercising every shape the shipped modes actually contain, plus a secret and a
#: declared-but-absent key.
ALL_SHAPES = {
    "0": {
        "type": "EveryShape",
        "name": "Everything",
        "duration": 120,                      # int      -> number
        "refresh_hz": 2.5,                    # float    -> number
        "folder": "/tmp",                     # str+d    -> path
        "weather_units": "imperial",          # str      -> text (+suggestions)
        "show_time": True,                    # bool     -> switch
        "accent_rgb": [255, 204, 132],        # rgb      -> color
        "event_interval_range": [1.5, 3.0],   # 2 floats -> range
        "crypto_ids": ["bitcoin", "doge"],    # list[str]-> stringlist
        "palette": [[220, 150, 60], [70, 170, 210]],   # palette
        "devices": [{"hostname": "x.local", "name": "X", "role": "kiosk"}],   # json
        "api_key": "SECRET-VALUE-MUST-NOT-APPEAR",
    }
}

ALL_SHAPES_REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {
        "everyshape": {
            "entrypoint": "modes.slideshow_mode:SlideshowMode",   # not imported by the panel
            "required": ["folder"],
            "optional": ["duration", "refresh_hz", "weather_units", "show_time", "accent_rgb",
                         "event_interval_range", "crypto_ids", "palette", "devices",
                         "api_key", "scale_mode", "never_set_here"],
            "params": {
                "weather_units": {"suggestions": ["imperial", "metric"]},
                "scale_mode": {"choices": ["contain", "cover", "stretch"]},
                "never_set_here": {"default": 42, "help": "comes from the code"},
                "refresh_hz": {"min": 0, "max": 60, "step": 0.5},
            },
        }
    },
}


def _project(tmp_path, *, registry=None, modes=None):
    """A project with a profile that carries every value shape (plus a local override)."""
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "modes_registry.json").write_text(
        json.dumps(registry or ALL_SHAPES_REGISTRY, indent=2) + "\n")
    (tmp_path / "modes_config.json").write_text(
        json.dumps({"profile": {"label": "Shapes"}, "modes": modes or ALL_SHAPES}, indent=2) + "\n")
    return str(tmp_path)


def _ctx(tmp_path, **kw):
    return PageContext(base_dir=_project(tmp_path), bus=ControlBus(), bind="127.0.0.1", **kw)


@asynccontextmanager
async def _panel(ctx):
    with nicegui_reset_globals():
        os.environ["NICEGUI_USER_SIMULATION"] = "true"
        try:
            prepare_simulation()
            register_pages(ctx)
            ui.run(lambda: ui.label("root"), storage_secret="test storage secret")
            async with core.app.router.lifespan_context(core.app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(core.app), base_url="http://test"
                ) as client:
                    yield SimpleNamespace(user=User(client), client=client)
        finally:
            os.environ.pop("NICEGUI_USER_SIMULATION", None)


def _readonly(el) -> bool:
    """A field is read-only if the widget is disabled or marked readonly."""
    if getattr(el, "enabled", None) is False:
        return True
    props = getattr(el, "_props", {}) or {}
    if props.get("disable") is True:
        return True
    return "readonly" in str(props.get("readonly", "")).lower() or props.get("readonly") is True


# ---------------------------------------------------------------- rendering

async def test_every_value_shape_renders_with_its_widget(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        # identity and provenance
        await p.user.should_see("Everything")
        await p.user.should_see("EveryShape")
        await p.user.should_see("READ-ONLY")
        # each field label is present
        for label in ("Duration", "Refresh Hz", "Folder", "Weather units", "Show time",
                      "Accent RGB", "Event interval range", "Crypto IDs", "Palette",
                      "Devices", "API key"):
            await p.user.should_see(label)

        widgets = {}
        for el in p.user.find().elements:
            mark = getattr(el, "_markers", None) or []
            for m in mark:
                if m.startswith("param-widget-"):
                    widgets[m[len("param-widget-"):]] = (type(el).__name__, el)

        # the mapping table, as rendered
        expected = {
            "duration": "Number", "refresh_hz": "Number", "folder": "Input",
            "weather_units": "Input", "show_time": "Switch", "accent_rgb": "Input",
            "crypto_ids": "Textarea", "palette": "Textarea", "devices": "Textarea",
            # a range renders as two number fields, [min, max]
            "event_interval_range-min": "Number", "event_interval_range-max": "Number",
            # declared but unset: the schema's choices make it a dropdown
            "scale_mode": "Select",
            # declared but unset, no name hint: a plain text field carrying the code default
            "never_set_here": "Input",
        }
        for key, kind in expected.items():
            assert key in widgets, f"{key} did not render (got {sorted(widgets)})"
            assert widgets[key][0] == kind, f"{key} rendered as {widgets[key][0]}, expected {kind}"

        # a secret field exists and carries NO value widget at all
        assert "api_key" not in widgets
        await p.user.should_see("secret")


async def test_every_field_is_read_only_in_phase_2(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        fields = []
        for el in p.user.find().elements:
            for m in (getattr(el, "_markers", None) or []):
                if m.startswith("param-widget-") or m.endswith("-min") or m.endswith("-max"):
                    fields.append((m, el))
        assert fields, "no field widgets found at all"
        editable = [name for name, el in fields if not _readonly(el)]
        assert editable == [], f"Phase 2 must be read-only; these are editable: {editable}"


async def test_secret_value_never_reaches_the_page(tmp_path):
    """The strongest form of this check: the value is not even in the element tree."""
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        await p.user.should_see("API key")
        dumped = str(p.user.current_layout)
        assert "SECRET-VALUE-MUST-NOT-APPEAR" not in dumped, "a secret value reached the page"
        # and a pure check of the model agrees
        params, _ = resolve_params(ALL_SHAPES["0"], ALL_SHAPES_REGISTRY["types"]["everyshape"])
        secret = {p.key: p for p in params}["api_key"]
        assert secret.widget == "secret" and secret.value is None and secret.secret is True


async def test_declared_but_unset_params_are_still_offered(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        await p.user.should_see("Scale mode")          # declared, not set, choices from schema
        await p.user.should_see("Never set here")      # declared, not set, has a code default
        await p.user.should_see("not set in this profile")


async def test_undeclared_config_key_is_warned_about_on_the_page(tmp_path):
    modes = {"0": dict(ALL_SHAPES["0"], mystery_key=7)}
    ctx = PageContext(base_dir=_project(tmp_path, modes=modes), bus=ControlBus())
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        await p.user.should_see("mystery_key")
        await p.user.should_see("warning:")


async def test_local_override_is_visible_on_the_form(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / "modes_config.local.json").write_text(json.dumps(
        {"modes": {"0": {"folder": "/override/path"}}}, indent=2) + "\n")
    async with _panel(ctx) as p:
        await p.user.open("/mode/0")
        await p.user.should_see("local override")
        await p.user.should_see("/override/path")


async def test_mode_list_links_into_the_form(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/")
        links = [el for el in p.user.find().elements
                 if type(el).__name__ == "Link" and "params" in str(getattr(el, "text", ""))]
        assert links, "no link from the mode list into a mode's form"
        assert any(str(getattr(el, "text", "")).strip() for el in links)


async def test_unknown_mode_number_is_reported_not_fatal(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/99")
        await p.user.should_see("No mode 99 in this profile")
        await p.user.should_see("SLOTS within a profile")


async def test_non_numeric_mode_number_is_reported(tmp_path):
    ctx = _ctx(tmp_path)
    async with _panel(ctx) as p:
        await p.user.open("/mode/abc")
        await p.user.should_see("must be an integer")


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("value,expected", [
    ([255, 204, 132], "#ffcc84"),
    ([0, 0, 0], "#000000"),
    ([300, -5, 10], "#ff000a"),      # clamped into range rather than raising
    ("not a list", "#000000"),
    (None, "#000000"),
])
def test_hex_conversion_is_defensive(value, expected):
    assert _hex_from_rgb(value) == expected


# ---------------------------------------------------------------- exhaustive coverage

def _real_profiles():
    paths = [os.path.join(BASE_DIR, "modes_config.json")] + [
        os.path.join(BASE_DIR, "configs", f)
        for f in sorted(os.listdir(os.path.join(BASE_DIR, "configs")))
        if f.endswith(".json")
    ]
    out = []
    for path in paths:
        modes, _meta = profiles_mod.profile_modes(path)
        if modes:
            out.append((os.path.basename(path), modes))
    return out


def test_every_param_in_every_real_profile_is_rendered():
    """
    The Phase 2 acceptance item, checked exhaustively rather than on a sample: for all 8
    profiles and every mode in them, the resolver must offer every key the config sets and
    every key the registry declares, with a widget the UI knows how to draw.
    """
    from core.config import load_json

    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    problems = []
    fields = 0
    modes_checked = 0
    for profile_name, modes in _real_profiles():
        for number, cfg in modes.items():
            type_key = str(cfg.get("type", "")).lower().replace(" ", "").replace("_", "")
            spec = registry.get(type_key)
            if spec is None:
                problems.append(f"{profile_name}/{number}: unknown type {cfg.get('type')!r}")
                continue
            instance = {k: v for k, v in cfg.items() if k not in ("type", "name", "title")}
            modes_checked += 1
            cov = coverage(instance, spec)
            if cov["missing_present"] or cov["missing_declared"]:
                problems.append(f"{profile_name}/{number}: {cov}")
            params, _warnings = resolve_params(instance, spec)
            fields += len(params)
            for p in params:
                if p.widget not in WIDGETS:
                    problems.append(f"{profile_name}/{number}.{p.key}: unknown widget {p.widget}")

    assert not problems, problems[:8]
    assert modes_checked >= 150, f"expected to sweep every mode, checked {modes_checked}"
    assert fields >= 2000, f"expected thousands of fields, saw {fields}"


def test_secret_params_never_carry_a_value_anywhere_in_the_real_tree():
    """No real profile may hand a credential to the renderer."""
    from core.config import load_json

    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]
    leaked = []
    for profile_name, modes in _real_profiles():
        for number, cfg in modes.items():
            type_key = str(cfg.get("type", "")).lower().replace(" ", "").replace("_", "")
            spec = registry.get(type_key, {})
            instance = {k: v for k, v in cfg.items() if k not in ("type", "name", "title")}
            params, _ = resolve_params(instance, spec)
            for p in params:
                if p.secret and p.value is not None:
                    leaked.append(f"{profile_name}/{number}.{p.key}")
    assert leaked == [], f"secret values reached the model: {leaked}"
