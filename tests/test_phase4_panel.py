"""
Phase 4: switching profiles, restoring backups, and the raw editor.

Two levels, because they prove different things:
  * PROCESS tests start the real controller and drive it over HTTP — the acceptance item is "switch
    from the laptop and the wall changes profile", which only a real process can answer, and the
    other half is that the switch SURVIVES a restart.
  * UI tests render the real pages in-process and click the real handlers.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from nicegui import core, ui
from nicegui.testing.general import nicegui_reset_globals, prepare_simulation
from nicegui.testing.user import User

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.bus import ControlBus                                    # noqa: E402
from core.config import active_profile_file, read_active_profile   # noqa: E402
from core.store import atomic_write_json, sha256_file              # noqa: E402
from panel.app import PageContext, register_pages                   # noqa: E402

from test_panel_wiring import (                                    # noqa: E402
    _env,
    _read,
    _sandbox,
    _spawn,
    _stop,
    _wait_ready,
)

TOKEN = "phase4-token"

ONE_MODE = {"type": "tiny", "font_size": 48, "name": "main-first"}
OTHER_MODE = {"type": "tiny", "font_size": 12, "name": "other-first"}

LANDSCAPE = {"profile": {"label": "Landscape sandbox", "resolution": [1280, 720]},
             "modes": {"0": dict(ONE_MODE), "1": {"type": "tiny", "font_size": 40, "name": "second"}}}
PORTRAIT = {"profile": {"label": "Portrait sandbox", "resolution": [720, 1280]},
            "modes": {"0": dict(OTHER_MODE), "1": {"type": "tiny", "font_size": 20, "name": "p2"},
                      "2": {"type": "tiny", "font_size": 22, "name": "p3"}}}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _project(tmp_path) -> Path:
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    (root / "configs").mkdir(exist_ok=True)
    (root / "modes_config.json").write_text(json.dumps(LANDSCAPE, indent=2) + "\n")
    (root / "configs" / "modes_config_portrait.json").write_text(
        json.dumps(PORTRAIT, indent=2) + "\n")
    return root


# ---------------------------------------------------------------- process level

@pytest.fixture
def kiosk(tmp_path):
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "switch.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", "--auto", "30", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        yield root, url, proc, log
    finally:
        _stop(proc)


def _post(url, path, payload=None, token=TOKEN):
    req = urllib.request.Request(url + path, data=json.dumps(payload or {}).encode(), method="POST")
    if token:
        req.add_header("X-Panel-Token", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw.decode("utf-8", "replace")}


def _get(url, path, token=TOKEN):
    req = urllib.request.Request(url + path)
    if token:
        req.add_header("X-Panel-Token", token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _status(url):
    return _get(url, "/api/status")["status"]


def _wait_for(url, predicate, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            stamp = _status(url)
        except Exception:
            time.sleep(0.25)
            continue
        if predicate(stamp):
            return stamp
        time.sleep(0.25)
    return None


def test_switching_profile_changes_what_the_wall_plays(kiosk):
    """The acceptance item: switch from the panel -> the wall changes profile, no restart."""
    root, url, proc, log = kiosk
    portrait = os.path.join(root, "configs", "modes_config_portrait.json")
    before = _status(url)
    assert before["applied_config_path"].endswith("modes_config.json")
    assert before["applied_rotation"] == [0, 1]

    code, body = _post(url, "/api/profile", {"profile": "configs/modes_config_portrait.json"})
    assert code == 200 and body["ok"], body
    assert body["profile"] == "configs/modes_config_portrait.json"

    # wait for the SWITCH to complete, not merely for the handler to have stored the path: the
    # mode is rebuilt on the next clean frame, so the digest is the honest "it is really playing"
    def switched(stamp):
        return (str(stamp.get("applied_config_path", "")).endswith("modes_config_portrait.json")
                and stamp.get("mode_config_digest")
                == _digest(portrait, str(stamp.get("mode_build_index"))))

    after = _wait_for(url, switched)
    assert after is not None, f"the app never switched:\n{_read(log)}"
    # the rotation is the OTHER profile's, and its modes are the ones playing
    assert after["applied_rotation"] == [0, 1, 2]
    assert after["enabled_modes"] == [0, 1, 2]
    assert after["uptime_s"] > before["uptime_s"] and proc.poll() is None, "the app restarted"

    # and it was recorded, one line, in the gitignored runtime file
    assert read_active_profile(str(root)) == "configs/modes_config_portrait.json"
    on_disk = json.load(open(active_profile_file(str(root))))
    assert on_disk == {"profile": "configs/modes_config_portrait.json"}


def test_a_switch_survives_a_restart(tmp_path):
    """The other half: the record is what the NEXT start loads."""
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "boot1.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", "--auto", "30", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        assert _post(url, "/api/profile", {"profile": "configs/modes_config_portrait.json"})[0] == 200
        assert _wait_for(url, lambda s: s["applied_rotation"] == [0, 1, 2]) is not None
    finally:
        _stop(proc)

    port2 = _free_port()
    proc2, log2 = _spawn(root, tmp_path, "boot2.log", "--panel-port", str(port2),
                         "--panel-bind", "127.0.0.1", "--auto", "30", env=_env())
    url2 = f"http://127.0.0.1:{port2}"
    try:
        assert _wait_ready(url2 + "/api/status", proc2, log2), _read(log2)
        # no --config this time: the recorded profile decides
        status = _status(url2)
        assert status["applied_config_path"].endswith("modes_config_portrait.json")
        assert status["applied_rotation"] == [0, 1, 2]
        assert "via runtime" in _read(log2), "startup should say WHY it chose that profile"
    finally:
        _stop(proc2)


def test_switching_back_is_possible(kiosk):
    root, url, _proc, _log = kiosk
    _post(url, "/api/profile", {"profile": "configs/modes_config_portrait.json"})
    assert _wait_for(url, lambda s: s["applied_rotation"] == [0, 1, 2]) is not None
    code, body = _post(url, "/api/profile", {"profile": "modes_config.json"})
    assert code == 200 and body["profile"] == "modes_config.json"
    after = _wait_for(url, lambda s: s["applied_rotation"] == [0, 1])
    assert after is not None
    assert after["applied_config_path"].endswith("modes_config.json")
    assert read_active_profile(str(root)) == "modes_config.json"


def test_a_switch_is_refused_for_a_missing_or_broken_profile(kiosk):
    """Nothing is written and nothing is applied when the target cannot be trusted."""
    root, url, _proc, _log = kiosk
    code, body = _post(url, "/api/profile", {"profile": "configs/nope.json"})
    assert code == 404 and "no such profile" in body["reason"]

    broken = {"profile": {"label": "broken"}, "modes": {"0": {"font_size": 10}}}   # no 'type'
    (root / "configs" / "broken.json").write_text(json.dumps(broken, indent=2) + "\n")
    code, body = _post(url, "/api/profile", {"profile": "configs/broken.json"})
    assert code == 409 and "does not validate" in body["reason"]
    assert body["errors"] and "missing 'type'" in body["errors"][0]

    code, _ = _post(url, "/api/profile", {})
    assert code == 400
    # nothing was recorded by any of the refusals
    assert not os.path.exists(active_profile_file(str(root)))
    # and the app is still playing the profile it started with
    assert _status(url)["applied_config_path"].endswith("modes_config.json")


def test_switching_is_refused_when_the_app_was_pinned_with_config(tmp_path):
    """--config outranks the record at every restart, so the panel refuses instead of pretending."""
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "pinned.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", "--auto", "30",
                       "--config", "modes_config.json", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        code, body = _post(url, "/api/profile", {"profile": "configs/modes_config_portrait.json"})
        assert code == 409
        assert "--config" in body["reason"] and "restart" in body["reason"]
        assert not os.path.exists(active_profile_file(str(root)))
    finally:
        _stop(proc)


def test_the_profiles_endpoint_reports_what_is_active_and_why(kiosk):
    root, url, _proc, _log = kiosk
    body = _get(url, "/api/profiles")
    assert body["active"] == "modes_config.json"
    assert body["source"] in ("registry", "default")
    assert body["switchable"] is True
    assert body["recorded"] == ""
    assert {p["rel"] for p in body["profiles"]} >= {"modes_config.json",
                                                   "configs/modes_config_portrait.json"}
    assert sum(1 for p in body["profiles"] if p["active"]) == 1

    _post(url, "/api/profile", {"profile": "configs/modes_config_portrait.json"})
    assert _wait_for(url, lambda s: s["applied_rotation"] == [0, 1, 2]) is not None
    body2 = _get(url, "/api/profiles")
    assert body2["active"] == "configs/modes_config_portrait.json"
    assert body2["source"] == "runtime"
    assert body2["recorded"] == "configs/modes_config_portrait.json"


def test_the_endpoints_are_gated_on_a_non_loopback_bind(tmp_path):
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "gate4.log", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0", "--auto", "30", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        assert _post(url, "/api/profile", {"profile": "modes_config.json"}, token=None)[0] == 403
        try:
            _get(url, "/api/profiles", token=None)
            raise AssertionError("ungated")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        assert _post(url, "/api/profile", {"profile": "modes_config.json"})[0] == 200
    finally:
        _stop(proc)


def _click(el):
    """
    Fire an element's click handler the way a browser would.

    NiceGUI 3.18's test harness has no click API (only open/should_see/find), so this reaches the
    registered EventListener and calls its handler. NiceGUI wraps the handler to accept an event
    argument, so one is supplied when the signature asks for it. This is the only way to exercise a
    button's real closure — and a button whose handler is never called is a button nobody has tested.
    """
    entries = list((getattr(el, "_event_listeners", {}) or {}).values())
    asserts = [e for e in entries if getattr(e, "type", "click") == "click"] or entries
    assert asserts, f"{el} has no click handler to fire"
    for entry in asserts:
        handler = getattr(entry, "handler", None) or entry
        try:
            wants = len(inspect.signature(handler).parameters)
        except (TypeError, ValueError):
            wants = 0
        if wants:
            handler(SimpleNamespace(sender=el, value=getattr(el, "value", None)))
        else:
            handler()


def _button(p, marker: str):
    found = [el for el in p.user.find().elements
             if getattr(el, "_markers", None) and marker in el._markers]
    assert found, f"no element marked {marker!r} on the page"
    return found[0]


def _digest(profile_path: str, mode_key: str) -> str:
    from core.config import config_digest

    modes = json.load(open(profile_path))["modes"]
    return config_digest(modes[mode_key])


# ---------------------------------------------------------------- pages

UI_REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {
        "gauge": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                  "required": [], "optional": ["font_size", "title"]},
    },
}


def _ui_project(tmp_path, *, landscape=None, portrait=None):
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "modes_registry.json").write_text(json.dumps(UI_REGISTRY, indent=2) + "\n")
    (tmp_path / "modes_config.json").write_text(
        json.dumps(landscape or {"profile": {"label": "L"},
                                 "modes": {"0": {"type": "Gauge", "font_size": 40}}},
                   indent=2) + "\n")
    (tmp_path / "configs" / "modes_config_portrait.json").write_text(
        json.dumps(portrait or {"profile": {"label": "P"},
                                "modes": {"0": {"type": "Gauge", "font_size": 20},
                                          "1": {"type": "Gauge", "font_size": 21}}}, indent=2) + "\n")
    return str(tmp_path)


@asynccontextmanager
async def _panel(ctx):
    with nicegui_reset_globals():
        os.environ["NICEGUI_USER_SIMULATION"] = "true"
        try:
            prepare_simulation()
            register_pages(ctx)
            ui.run(lambda: ui.label("root"), storage_secret="test storage secret")
            async with core.app.router.lifespan_context(core.app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(core.app),
                                             base_url="http://test") as client:
                    yield SimpleNamespace(user=User(client), client=client)
        finally:
            os.environ.pop("NICEGUI_USER_SIMULATION", None)


async def test_the_switch_button_offers_the_other_profile_and_does_it(tmp_path):
    base = _ui_project(tmp_path)
    bus = ControlBus()
    ctx = PageContext(base_dir=base, bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/?profile=configs/modes_config_portrait.json")
        await p.user.should_see("Switch the display to")

        # clicking the real button: the handler is the page's own closure
        _click(_button(p, "switch-profile"))
        await p.user.should_see("is now the active profile")

    assert read_active_profile(base) == "configs/modes_config_portrait.json"
    assert bus.pending() >= 1, "the switch must tell the running app to reload"
    queued = bus.drain()
    assert any(cmd.get("cmd") == "apply_config" for cmd in queued)
    applied = [c for c in queued if c.get("cmd") == "apply_config"][0]
    assert applied["config_path"].endswith("modes_config_portrait.json")
    assert sorted(applied["modes_config"]) == ["0", "1"]
    assert applied["refresh"] is True


async def test_the_active_profile_offers_no_switch_button(tmp_path):
    base = _ui_project(tmp_path)
    ctx = PageContext(base_dir=base, bus=ControlBus(), bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("This profile is active.")
        await p.user.should_not_see("Switch the display to")


async def test_a_config_pinned_app_explains_why_it_cannot_switch(tmp_path):
    base = _ui_project(tmp_path)
    ctx = PageContext(base_dir=base, bus=ControlBus(), bind="127.0.0.1",
                      config_override="modes_config.json")
    async with _panel(ctx) as p:
        await p.user.open("/?profile=configs/modes_config_portrait.json")
        await p.user.should_see("pins the profile at every restart")
        await p.user.should_not_see("Switch the display to")


async def test_the_backups_section_lists_and_restores(tmp_path):
    """Two-step restore: ask, then confirm. Clicking through both must really restore the file."""
    base = _ui_project(tmp_path)
    path = os.path.join(base, "modes_config.json")
    # a backup of an older version, written the way the store writes them
    older = {"profile": {"label": "L"}, "modes": {"0": {"type": "Gauge", "font_size": 11}}}
    atomic_write_json(path, older, backup=True)          # backups the current (font_size 40)
    current_before = sha256_file(path)

    bus = ControlBus()
    ctx = PageContext(base_dir=base, bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("Backups — restore a previous version")
        await p.user.should_see("1 backup(s) of modes_config.json")

        restore_btn = next(el for el in p.user.find().elements
                           if getattr(el, "_markers", None)
                           and any(m.startswith("restore-") for m in el._markers))
        _click(restore_btn)
        await p.user.should_see("Restore this over the live profile?")

        _click(_button(p, "confirm-restore"))
        await p.user.should_see("Restored")

    assert json.load(open(path))["modes"]["0"]["font_size"] == 40, "the backup was restored"
    assert sha256_file(path) != current_before
    assert any(cmd.get("cmd") == "apply_config" for cmd in bus.drain())


async def test_the_raw_page_renders_validates_and_saves(tmp_path):
    base = _ui_project(tmp_path)
    bus = ControlBus()
    ctx = PageContext(base_dir=base, bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/raw")
        await p.user.should_see("the whole document")
        await p.user.should_see("Validate")
        area = next(el for el in p.user.find().elements
                    if getattr(el, "_markers", None) and "raw-textarea" in el._markers)
        assert '"modes"' in area.value

        # a broken document is reported and NOT written
        area.value = json.dumps({"modes": {"0": {"font_size": 40}}})     # no 'type'
        area.update()
        _click(_button(p, "raw-validate"))
        await p.user.should_see("Not valid")
        assert json.load(open(os.path.join(base, "modes_config.json")))["modes"]["0"]["type"] \
            == "Gauge"

        # a good document saves and is applied
        area.value = json.dumps({"profile": {"label": "L"},
                                 "modes": {"0": {"type": "Gauge", "font_size": 44}}})
        area.update()
        _click(_button(p, "raw-save"))
        await p.user.should_see("Saved")

    assert json.load(open(os.path.join(base, "modes_config.json")))["modes"]["0"]["font_size"] == 44
    assert any(cmd.get("cmd") == "apply_config" for cmd in bus.drain())
