"""
Process-level proof of the Phase 3 promise: a config change reaches a RUNNING kiosk.

The in-process tests prove the editor writes correctly and the panel posts the right command.
These tests start the REAL controller and talk to it over HTTP, because the acceptance item is
"change a parameter, save, and the mode on the wall changes with no restart" — and only a real
process with a real render loop can answer that.

The chain under test, end to end:
    ProfileEditor.save()  ->  the profile file on disk
    POST /api/apply       ->  reload from disk, apply to the loop, refresh the mode
    GET  /api/status      ->  mode_config_digest proves WHICH config the live mode was built from

The digest is what makes this checkable rather than hopeful: the controller records a hash of the
config it BUILT the current mode from, so comparing it with the file's hash says whether the wall is
running the edit. Without that, "it should have picked it up" is all anyone could say.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.config import config_digest                      # noqa: E402
from core.editor import ProfileEditor                      # noqa: E402
from core.store import sha256_file                         # noqa: E402

from test_panel_wiring import (                            # noqa: E402
    _args,
    _env,
    _read,
    _sandbox,
    _spawn,
    _stop,
    _wait_ready,
)

TOKEN = "apply-test-token"
PASSWORD = "x" * 44

#: Three modes, so a rotation can be seen to skip one.
THREE_PROFILE = {
    "profile": {"label": "ApplySandbox", "resolution": [1280, 720]},
    "modes": {
        "0": {"type": "tiny", "font_size": 48, "name": "first"},
        "1": {"type": "tiny", "font_size": 48, "name": "second"},
        "2": {"type": "tiny", "font_size": 48, "name": "third"},
    },
}


def _project(tmp_path, profile=None):
    root = _sandbox(tmp_path, secrets={"panel_token": TOKEN})
    (root / "modes_config.json").write_text(
        json.dumps(profile or THREE_PROFILE, indent=2) + "\n")
    return root


def _post(url, token=TOKEN, payload=None, timeout=5.0):
    body = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Panel-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _wait_for(predicate, url, *, timeout=15.0, interval=0.25):
    """Poll the live status until `predicate(status)` is true. Returns the status or None."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = _status(url)
        except Exception:
            time.sleep(interval)
            continue
        if predicate(last["status"]):
            return last["status"]
        time.sleep(interval)
    return None


@pytest.fixture
def kiosk(tmp_path):
    """A running controller with the panel on, and its URL."""
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "apply.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", "--auto", "1", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), \
            f"panel never came up:\n{_read(log)}"
        yield root, url, proc, log
    finally:
        _stop(proc)


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _edit(root, number, key, value):
    """Change one parameter through the REAL write path (the same code the Save button calls)."""
    registry = json.load(open(os.path.join(root, "modes_registry.json")))["types"]
    editor = ProfileEditor(str(root), os.path.join(root, "modes_config.json"), registry)
    editor.stage_set(number, key, value)
    result = editor.save()
    assert result.ok, (result.reason, result.errors)
    return result


# ---------------------------------------------------------------- the headline promise

def test_save_and_apply_reaches_the_running_loop_without_a_restart(kiosk):
    """
    The acceptance item, spelled out: edit a parameter, apply, and the LIVE mode is rebuilt from
    the new config — same process, no restart.
    """
    root, url, proc, log = kiosk
    before = _status(url)["status"]
    assert before["refresh_count"] == 0
    assert before["mode_index"] == 0

    # the digest of what the loop is currently running for mode 0
    def current_config():
        return json.load(open(os.path.join(root, "modes_config.json")))["modes"]["0"]

    assert before["mode_config_digest"] == config_digest(current_config())

    _edit(root, 0, "font_size", 96)
    assert config_digest(current_config()) != before["mode_config_digest"], \
        "the edit did not change the config, so this test proves nothing"

    code, body = _post(url + "/api/apply", payload={"refresh": True})
    assert code == 200 and body["ok"], body
    assert body["refresh"] is True
    assert body["config_sha256"] == sha256_file(os.path.join(root, "modes_config.json"))

    after = _wait_for(lambda s: s.get("refresh_count", 0) >= 1
                      and s.get("mode_config_digest") == config_digest(current_config()),
                      url)
    assert after is not None, f"the loop never rebuilt from the new config:\n{_read(log)}"

    # and it is the NEW value it built from, not merely a rebuild
    assert after["mode_config_digest"] == config_digest(current_config())
    assert after["mode_config_digest"] != before["mode_config_digest"]
    assert after["mode_build_index"] == 0
    assert after["applies_count"] >= 1
    assert after["applied_config_sha256"] == sha256_file(
        os.path.join(root, "modes_config.json"))
    # the app never restarted: same uptime clock, monotonic
    assert after["uptime_s"] > before["uptime_s"]
    assert proc.poll() is None


def test_apply_does_not_modify_the_file(kiosk):
    """Apply is a read: it must not rewrite the profile it just read."""
    root, url, _proc, _log = kiosk
    path = os.path.join(root, "modes_config.json")
    before = sha256_file(path)
    code, _ = _post(url + "/api/apply", payload={"refresh": False})
    assert code == 200
    assert sha256_file(path) == before


def test_refresh_rebuilds_the_mode_from_the_config_already_held(kiosk):
    """Refresh alone must rebuild without reloading or changing anything."""
    root, url, _proc, _log = kiosk
    before = _status(url)["status"]
    code, _ = _post(url + "/api/refresh")
    assert code == 200
    after = _wait_for(lambda s: s.get("refresh_count", 0) >= 1, url)
    assert after is not None
    assert after["mode_config_digest"] == before["mode_config_digest"]
    assert after["applied_config_sha256"] == before["applied_config_sha256"]


# ---------------------------------------------------------------- the enable switch

def test_disabling_a_mode_takes_it_out_of_the_rotation_without_a_restart(kiosk):
    root, url, _proc, log = kiosk
    before = _status(url)["status"]
    assert before["enabled_modes"] == [0, 1, 2]
    assert before["applied_rotation"] == [0, 1, 2]

    registry = json.load(open(os.path.join(root, "modes_registry.json")))["types"]
    editor = ProfileEditor(str(root), os.path.join(root, "modes_config.json"), registry)
    editor.stage_enabled(1, False)
    assert editor.save().ok

    assert _post(url + "/api/apply", payload={"refresh": False})[0] == 200
    after = _wait_for(lambda s: s.get("enabled_modes") == [0, 2], url)
    assert after is not None, f"the rotation never dropped mode 1:\n{_read(log)}"
    assert after["disabled_modes"] == [1]
    # The rotation keeps its place: it carries on from the mode on screen when that mode is still
    # allowed, and starts at the next allowed one when it is the mode that was just disabled.
    assert sorted(after["applied_rotation"]) == [0, 2]
    assert after["applied_rotation"][0] == before["mode_index"] or before["mode_index"] == 1
    assert after["enabled_fell_back"] is False
    # written as a real JSON boolean, and read back as one
    assert json.load(open(os.path.join(root, "modes_config.json")))["modes"]["1"]["enabled"] is False


def test_a_disabled_mode_is_skipped_by_the_actual_rotation(kiosk):
    """
    The rotation LIST is what drives switching, but this observes the loop itself: over several
    seconds of --auto 1 the display must visit only the enabled modes.
    """
    root, url, _proc, _log = kiosk
    registry = json.load(open(os.path.join(root, "modes_registry.json")))["types"]
    editor = ProfileEditor(str(root), os.path.join(root, "modes_config.json"), registry)
    editor.stage_enabled(1, False)
    assert editor.save().ok
    assert _post(url + "/api/apply", payload={"refresh": False})[0] == 200
    assert _wait_for(lambda s: s.get("enabled_modes") == [0, 2], url) is not None
    # A switch that was already in flight when the apply landed still COMPLETES — the app is right to
    # finish what it started — so sampling immediately can catch the old transition arriving on the
    # disabled mode. Wait until the loop is on an enabled mode before observing the rotation.
    assert _wait_for(lambda s: s.get("mode_index") in (0, 2), url) is not None

    seen = set()
    deadline = time.time() + 6.0
    while time.time() < deadline:
        try:
            seen.add(_status(url)["status"]["mode_index"])
        except Exception:
            pass
        time.sleep(0.2)
    assert seen, "never sampled the loop"
    assert 1 not in seen, f"the disabled mode was shown: {sorted(seen)}"
    assert seen <= {0, 2}, sorted(seen)


def test_disabling_everything_keeps_the_wall_showing_something(kiosk):
    root, url, _proc, log = kiosk
    registry = json.load(open(os.path.join(root, "modes_registry.json")))["types"]
    editor = ProfileEditor(str(root), os.path.join(root, "modes_config.json"), registry)
    for number in (0, 1, 2):
        editor.stage_enabled(number, False)
    assert editor.save().ok
    assert _post(url + "/api/apply", payload={"refresh": False})[0] == 200

    after = _wait_for(lambda s: s.get("enabled_fell_back") is True, url)
    assert after is not None, f"the fallback never fired:\n{_read(log)}"
    assert after["enabled_modes"] == [0, 1, 2], "an all-disabled profile must not go blank"
    assert after["disabled_modes"] == [0, 1, 2]
    assert "every mode is disabled" in _read(log)


def test_a_mode_disabled_before_startup_is_never_rotated_in(tmp_path):
    """The flag must hold ACROSS a restart too, not only after a live apply."""
    profile = json.loads(json.dumps(THREE_PROFILE))
    profile["modes"]["1"]["enabled"] = False
    root = _project(tmp_path, profile=profile)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "startup.log", "--panel-port", str(port),
                       "--panel-bind", "127.0.0.1", "--auto", "1", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        status = _status(url)["status"]
        assert status["enabled_modes"] == [0, 2]
        assert status["disabled_modes"] == [1]
        assert status["applied_rotation"] == [0, 2]
        assert "Rotation: 2 of 3 mode(s) enabled" in _read(log)
    finally:
        _stop(proc)


# ---------------------------------------------------------------- gating and refusals

def test_apply_and_refresh_are_gated_like_everything_else(tmp_path):
    """
    The token gate exists for a NON-loopback bind (a loopback panel needs no token — it is only
    reachable from the machine itself). So this spawns its own instance on 0.0.0.0, which is the
    only configuration where the gate is installed at all.
    """
    root = _project(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "gate.log", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0", "--auto", "1", env=_env())
    url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(url + "/api/status", proc, log), _read(log)
        assert _post(url + "/api/apply", token=None, payload={"refresh": True})[0] == 403
        assert _post(url + "/api/apply", token="wrong", payload={"refresh": True})[0] == 403
        assert _post(url + "/api/refresh", token=None)[0] == 403
        assert _post(url + "/api/apply", payload={"refresh": True})[0] == 200
        assert _post(url + "/api/refresh")[0] == 200
    finally:
        _stop(proc)


def test_apply_refuses_an_unknown_profile_and_bad_bodies(kiosk):
    _root, url, _proc, _log = kiosk
    code, body = _post(url + "/api/apply", payload={"profile": "configs/nope.json"})
    assert code == 404 and body["ok"] is False and "unknown profile" in body["reason"]

    req = urllib.request.Request(url + "/api/apply", data=b"not json", method="POST")
    req.add_header("X-Panel-Token", TOKEN)
    try:
        urllib.request.urlopen(req, timeout=5)
        raise AssertionError("a bad body was accepted")
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_apply_of_a_second_profile_does_not_change_the_first(kiosk):
    """Two profiles, one at a time: the other file must be untouched by an apply."""
    root, url, _proc, _log = kiosk
    other = json.loads(json.dumps(THREE_PROFILE))
    other["profile"]["label"] = "Other"
    other["modes"] = {"0": {"type": "tiny", "font_size": 12, "name": "other-first"}}
    (root / "configs" / "modes_other.json").write_text(json.dumps(other, indent=2) + "\n")
    main_before = sha256_file(str(root / "modes_config.json"))

    code, body = _post(url + "/api/apply", payload={"profile": "configs/modes_other.json",
                                                    "refresh": True})
    assert code == 200 and body["ok"], body
    assert body["profile"] == "configs/modes_other.json"
    after = _wait_for(lambda s: s.get("applied_config_path", "").endswith("modes_other.json"), url)
    assert after is not None
    assert after["enabled_modes"] == [0]
    assert after["applied_rotation"] == [0]
    assert sha256_file(str(root / "modes_config.json")) == main_before
