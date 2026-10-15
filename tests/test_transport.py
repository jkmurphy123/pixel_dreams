"""
Next / Prev mode: the panel's manual step control.

The claim being tested is not "a button exists" but "a press moves the display exactly one mode" —
including the two behaviours the docs promise: a burst of presses during a fade all land (queued,
not dropped), and a manual step restarts the --auto timer so the mode you picked gets a full
interval. Both are process-level facts, so the first half of this file drives a real controller.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from nicegui import core, ui
from nicegui.testing.general import nicegui_reset_globals, prepare_simulation
from nicegui.testing.user import User

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.bus import ControlBus                    # noqa: E402
from panel.app import PageContext, register_pages   # noqa: E402

from test_panel_wiring import (                    # noqa: E402
    _env,
    _read,
    _sandbox,
    _spawn,
    _stop,
    _wait_ready,
)

TOKEN = "transport-token"

#: Six modes, so stepping and wrapping are unambiguous.
PROFILE = {
    "profile": {"label": "Transport sandbox", "resolution": [1280, 720]},
    "modes": {str(n): {"type": "tiny", "font_size": 20 + n, "name": f"mode-{n}"}
              for n in range(6)},
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _project(tmp_path):
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    (root / "modes_config.json").write_text(json.dumps(PROFILE, indent=2) + "\n")
    return root


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


def _status(url, token=TOKEN):
    req = urllib.request.Request(url + "/api/status")
    if token:
        req.add_header("X-Panel-Token", token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["status"]


def _wait_for(url, predicate, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            stamp = _status(url)
        except Exception:
            time.sleep(0.2)
            continue
        if predicate(stamp):
            return stamp
        time.sleep(0.2)
    return None


def _start(root, tmp_path, name, *extra):
    port = _free_port()
    proc, log = _spawn(root, tmp_path, name, "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", *extra, env=_env())
    url = f"http://127.0.0.1:{port}"
    assert _wait_ready(url + "/api/status", proc, log), _read(log)
    return proc, url, log


@pytest.fixture
def kiosk(tmp_path):
    """A running controller with NO --auto: nothing should move unless we ask."""
    root = _project(tmp_path)
    proc, url, log = _start(root, tmp_path, "transport.log")
    try:
        yield root, url, proc, log
    finally:
        _stop(proc)


# ---------------------------------------------------------------- the core behaviour

def test_next_and_prev_move_one_mode_each_way(kiosk):
    root, url, proc, log = kiosk
    before = _status(url)
    assert before["mode_index"] == 0
    rotation = before["applied_rotation"]
    assert rotation == [0, 1, 2, 3, 4, 5]

    code, body = _post(url, "/api/step", {"delta": 1})
    assert code == 200 and body["ok"] and body["queued"] == 1
    after = _wait_for(url, lambda s: s["mode_index"] == 1)
    assert after is not None, f"next did not advance:\n{_read(log)}"
    assert after["last_step"] == "stepped next"

    code, body = _post(url, "/api/step", {"delta": -1})
    assert code == 200
    back = _wait_for(url, lambda s: s["mode_index"] == 0)
    assert back is not None, f"prev did not go back:\n{_read(log)}"
    assert back["last_step"] == "stepped prev"
    assert proc.poll() is None, "the app restarted instead of switching"


def test_stepping_wraps_in_both_directions(kiosk):
    _root, url, _proc, _log = kiosk
    assert _post(url, "/api/step", {"delta": -1})[0] == 200
    wrapped = _wait_for(url, lambda s: s["mode_index"] == 5)
    assert wrapped is not None, "prev from the first mode should wrap to the last"
    assert _post(url, "/api/step", {"delta": 1})[0] == 200
    forward = _wait_for(url, lambda s: s["mode_index"] == 0)
    assert forward is not None, "next from the last mode should wrap to the first"


def test_a_burst_of_presses_all_land(kiosk):
    """
    The documented behaviour: a step during a fade is QUEUED, not dropped. Clicking Next three times
    quickly must land on mode 3, not mode 1 — the fade is 0.2s, so a burst is guaranteed to overlap
    it.
    """
    _root, url, _proc, log = kiosk
    for _ in range(3):
        code, _ = _post(url, "/api/step", {"delta": 1})
        assert code == 200
    landed = _wait_for(url, lambda s: s["mode_index"] == 3 and not s.get("pending_steps"), timeout=20)
    assert landed is not None, f"three presses did not land on mode 3:\n{_read(log)}"
    assert landed["pending_steps"] == 0, landed


def test_a_manual_step_restarts_the_auto_timer(tmp_path):
    """
    With --auto running, picking a mode by hand should give you MOST OF A FULL interval on it, not
    whatever was left of the old one.

    Measured as a gap, because that is what distinguishes the two behaviours: with a 6s interval and
    a step taken 3s into one, a timer that was NOT reset would fire ~3s later, and a reset timer
    takes ~6s. So the assertion is on the gap between the manual step landing and the next automatic
    change — not on a momentary reading, which is how the first version of this test managed to
    measure the step completing rather than the timer.
    """
    root = _project(tmp_path)
    proc, url, log = _start(root, tmp_path, "auto.log", "--auto", "6")
    try:
        first = _wait_for(url, lambda s: s["mode_index"] != 0, timeout=12)
        assert first is not None, f"auto never cycled:\n{_read(log)}"
        time.sleep(3.0)                                   # halfway into the current interval

        start_mode = _status(url)["mode_index"]
        assert _post(url, "/api/step", {"delta": 1})[0] == 200
        stepped = _wait_for(url, lambda s: s["mode_index"] != start_mode, timeout=10)
        assert stepped is not None, "the manual step never landed"
        landed_mode = stepped["mode_index"]
        landed_at = time.time()

        nxt = _wait_for(url, lambda s: s["mode_index"] != landed_mode, timeout=14)
        assert nxt is not None, "the auto-cycle stopped after a manual step"
        gap = time.time() - landed_at
        assert gap >= 4.5, (
            f"the manual step did not restart the auto timer: the next automatic change came "
            f"{gap:.1f}s after it, and an un-reset timer would be ~3s (half of the 6s interval)")
    finally:
        _stop(proc)


def test_a_single_mode_app_refuses_a_step_and_says_why(tmp_path):
    root = _project(tmp_path)
    proc, url, log = _start(root, tmp_path, "locked.log", "--play", "2")
    try:
        status = _wait_for(url, lambda s: s.get("single_mode") is True)
        assert status is not None, f"single_mode never reported:\n{_read(log)}"
        assert status["applied_rotation"] == [2]
        code, body = _post(url, "/api/step", {"delta": 1})
        assert code == 409 and body["ok"] is False
        assert "--play" in body["reason"]
        time.sleep(1.0)
        assert _status(url)["mode_index"] == 2, "a refused step moved the single mode"
    finally:
        _stop(proc)


def test_a_step_is_gated_on_a_non_loopback_bind(tmp_path):
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "gate.log", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        assert _post(url, "/api/step", {"delta": 1}, token=None)[0] == 403
        assert _post(url, "/api/step", {"delta": 1}, token="wrong")[0] == 403
        assert _post(url, "/api/step", {"delta": 1})[0] == 200
        assert _wait_for(url, lambda s: s["mode_index"] == 1) is not None
    finally:
        _stop(proc)


def test_a_junk_delta_is_rejected(kiosk):
    _root, url, _proc, _log = kiosk
    req = urllib.request.Request(url + "/api/step", data=json.dumps({"delta": "sideways"}).encode(),
                                method="POST")
    req.add_header("X-Panel-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("a junk delta was accepted")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    assert _status(url)["mode_index"] == 0, "a rejected request moved the display"


# ---------------------------------------------------------------- the page

UI_REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {"tiny": {"entrypoint": "modes.system_information_mode:SystemInformationMode",
                       "required": [], "optional": ["font_size"]}},
}


def _ui_project(tmp_path):
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "modes_registry.json").write_text(json.dumps(UI_REGISTRY, indent=2) + "\n")
    (tmp_path / "modes_config.json").write_text(json.dumps(PROFILE, indent=2) + "\n")
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


def _bus(**fields):
    bus = ControlBus()
    bus.update_status(**fields)
    return bus


def _marked(p, marker):
    found = [el for el in p.user.find().elements
             if getattr(el, "_markers", None) and marker in el._markers]
    assert found, f"no element marked {marker!r}"
    return found[0]


def _click(el):
    import inspect

    for entry in (getattr(el, "_event_listeners", {}) or {}).values():
        handler = getattr(entry, "handler", None) or entry
        wants = len(inspect.signature(handler).parameters) if callable(handler) else 0
        handler(SimpleNamespace(sender=el, value=None)) if wants else handler()


async def test_the_main_page_offers_next_and_prev_under_the_status(tmp_path):
    ctx = PageContext(base_dir=_ui_project(tmp_path),
                      bus=_bus(display="fullscreen", mode_index=1, single_mode=False,
                               applied_rotation=[0, 1, 2, 3, 4, 5], enabled_modes=[0, 1, 2, 3, 4, 5],
                               max_modes=6, pending_steps=0),
                      bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("Mode control")
        await p.user.should_see("Next")
        await p.user.should_see("Prev")
        # the hint says where we are and what is either side
        await p.user.should_see("showing mode 1 — 2 of 6")
        await p.user.should_see("next 2, prev 0")


async def test_clicking_next_posts_exactly_one_step(tmp_path):
    bus = _bus(display="fullscreen", mode_index=1, single_mode=False,
               applied_rotation=[0, 1, 2], enabled_modes=[0, 1, 2], max_modes=3, pending_steps=0)
    ctx = PageContext(base_dir=_ui_project(tmp_path), bus=bus, bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        _click(_marked(p, "next-mode"))
        _click(_marked(p, "prev-mode"))

    queued = bus.drain()
    assert [c for c in queued if c.get("cmd") == "step_mode"] == [
        {"cmd": "step_mode", "delta": 1}, {"cmd": "step_mode", "delta": -1}]


async def test_the_buttons_are_disabled_when_a_step_cannot_work(tmp_path):
    """Single mode (--play) and no display are both real cases; each says why rather than lying."""
    ctx = PageContext(base_dir=_ui_project(tmp_path),
                      bus=_bus(display="fullscreen", mode_index=2, single_mode=True,
                               applied_rotation=[2], enabled_modes=[2], max_modes=6,
                               pending_steps=0),
                      bind="127.0.0.1")
    async with _panel(ctx) as p:
        await p.user.open("/")
        await p.user.should_see("started with --play")
        assert _marked(p, "next-mode").enabled is False
        assert _marked(p, "prev-mode").enabled is False

    ctx2 = PageContext(base_dir=_ui_project(tmp_path),
                       bus=_bus(display="off", mode_index=0, single_mode=False,
                                applied_rotation=[0, 1], enabled_modes=[0, 1], max_modes=6,
                                pending_steps=0),
                       bind="127.0.0.1")
    async with _panel(ctx2) as p:
        await p.user.open("/")
        await p.user.should_see("no display is attached to this panel")
        assert _marked(p, "next-mode").enabled is False
