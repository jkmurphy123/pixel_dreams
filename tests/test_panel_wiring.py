# tests/test_panel_wiring.py
#
# Process-level checks: they start the REAL controller and talk to it over HTTP. These pin
# the Phase 1 acceptance items that only a real process can prove:
#   * with the panel off, nicegui is never imported (the kiosk stays lean)
#   * with the panel on, it serves the live render loop and a command reaches it
#   * --panel-only serves with NO display initialised
#   * a non-loopback bind without a token refuses to start; with a token it is gated
#
# Each test spawns a bounded run (--frames) and cleans up its process. Child output goes to
# a log FILE (not a pipe): a failure can then print exactly what the app said, which is the
# only way these tests are debuggable.

import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _env(**extra) -> dict:
    """
    The environment a spawned controller gets.

    Two inherited variables MUST go, or the child behaves as though it were still inside the
    parent test run:

    * ``PYTHONPATH`` — under a Hermes tool session it points at Hermes's own site-packages (a
      different Python version), whose modules shadow the project venv's pinned deps; the child
      then dies on an ABI mismatch (e.g. pydantic_core) before it can bind anything.
    * ``PYTEST_CURRENT_TEST`` — this is exactly how NiceGUI decides it is under pytest
      (``nicegui.helpers.is_pytest``), and its ``ui.run()`` then takes the screen-test branch,
      which reads ``NICEGUI_SCREEN_TEST_PORT`` and raises KeyError. A real app started by a test
      must be started as a real app.
    """
    env = dict(os.environ)
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
                "PYTEST_CURRENT_TEST", "NICEGUI_USER_SIMULATION"):
        env.pop(var, None)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PANEL_TOKEN", None)
    env.update(extra)
    return env


def _args(*extra) -> list:
    return [sys.executable, "pixel_dreams.py", *extra]


def _get(url: str, token: str | None = None, timeout: float = 2.0):
    req = urllib.request.Request(url)
    if token:
        req.add_header("X-Panel-Token", token)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _spawn(tmp_path: Path, log_name: str, *args, env=None) -> tuple:
    """Start the controller with its output in a file; returns (proc, log_path)."""
    log_path = Path(tmp_path) / log_name
    handle = open(log_path, "w")
    proc = subprocess.Popen(_args(*args), cwd=BASE_DIR, env=env or _env(),
                            stdout=handle, stderr=subprocess.STDOUT, text=True)
    return proc, log_path


def _read(path: Path) -> str:
    try:
        return Path(path).read_text()
    except Exception:
        return ""


def _wait_ready(url: str, proc, log_path: Path, timeout: float = 25.0, token: str | None = None):
    """Wait until the server answers at all (403 counts: up, just gated). Returns True/False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            _get(url, token=token, timeout=1.0)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _stop(proc) -> None:
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def _summary(output: str) -> dict:
    """Parse the controller's one-line summary into a dict."""
    line = next((ln for ln in output.splitlines() if "Summary:" in ln), None)
    assert line, f"no summary line in output:\n{output}"
    fields = {}
    for part in line.split("Summary:")[1].strip().split():
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    return fields


# ---------------------------------------------------------------- panel off

def test_backend_modules_are_ui_free():
    """
    core.bus / core.profiles are used by the panel AND by the controller, so importing them
    must not drag in the web stack (or pygame): that is what keeps the panel usable headless
    and the kiosk lean.
    """
    code = ("import sys; sys.path.insert(0, '.'); import core.bus, core.profiles; "
            "leaks = [m for m in ('nicegui', 'pygame', 'fastapi', 'uvicorn') if m in sys.modules]; "
            "print('LEAKS=' + ','.join(leaks))")
    proc = subprocess.run([sys.executable, "-c", code], cwd=BASE_DIR, env=_env(),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "LEAKS=" in proc.stdout, proc.stdout
    leaks = proc.stdout.split("LEAKS=")[1].strip()
    assert leaks == "", f"core modules pulled in: {leaks}"


def test_panel_off_never_imports_nicegui():
    proc = subprocess.run(_args("--frames", "90", "--windowed", "--input", "none"),
                          cwd=BASE_DIR, env=_env(), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    fields = _summary(proc.stdout)
    assert fields["nicegui_imported"] == "False", fields
    assert fields["panel"] == "off", fields
    assert float(fields["avg_fps"]) > 30, fields


# ---------------------------------------------------------------- panel on

def test_panel_serves_the_live_render_loop_and_receives_commands(tmp_path):
    port = _free_port()
    proc, log = _spawn(tmp_path, "panel_on.log", "--auto", "2", "--windowed", "--input", "none",
                       "--panel-port", str(port), "--frames", "300")
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(f"{base}/api/status", proc, log), \
            f"panel never became reachable (rc={proc.poll()}). Output:\n{_read(log)}"

        status, body = _get(f"{base}/api/status")
        assert status == 200
        payload = json.loads(body)
        snap = payload["status"]
        assert snap["display"] == "windowed"
        assert snap["panel_port"] == port and snap["panel_bind"] == "127.0.0.1"
        assert snap["nicegui_version"], "nicegui version not recorded"
        assert snap["mode_index"] is not None
        assert len(payload["profiles"]) >= 8
        assert [p for p in payload["profiles"] if p["active"]], payload["profiles"]

        # panel -> render loop -> back out through the panel
        _get(f"{base}/api/ping")
        deadline, snap = time.time() + 6, snap
        while time.time() < deadline:
            snap = json.loads(_get(f"{base}/api/status")[1])["status"]
            if snap["pong_count"] >= 1:
                break
            time.sleep(0.2)
        assert snap["pong_count"] >= 1, \
            f"the render loop never applied the panel's command. Output:\n{_read(log)}"
        assert snap["commands_applied"] >= 1
        assert snap["last_command"] == "ping"
        assert snap["fps"] > 0, "fps never published"

        # the page itself renders
        status, html = _get(f"{base}/")
        assert status == 200
        text = html.decode("utf-8", "replace")
        assert "control panel" in text and "Profiles" in text

        proc.wait(timeout=60)
    finally:
        _stop(proc)

    assert proc.returncode == 0, _read(log)[-2000:]
    fields = _summary(_read(log))
    assert fields["nicegui_imported"] == "True", fields
    assert fields["panel"].startswith("http://127.0.0.1:"), fields


# ---------------------------------------------------------------- panel only

def test_panel_only_serves_without_initialising_a_display(tmp_path):
    """
    No display may be touched: run with an INVALID SDL video driver, which makes any display
    initialisation raise. Serving anyway is the proof.
    """
    port = _free_port()
    env = _env(SDL_VIDEODRIVER="definitely-not-a-real-driver")
    proc, log = _spawn(tmp_path, "panel_only.log", "--panel-only", "--panel-port", str(port),
                       env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(f"{base}/api/status", proc, log), \
            f"panel-only never became reachable. Output:\n{_read(log)}"
        snap = json.loads(_get(f"{base}/api/status")[1])["status"]
        assert snap["display"] == "off"
        assert snap["frame"] == 0, "a render loop ran in panel-only mode"

        status, html = _get(f"{base}/")
        assert status == 200
        text = html.decode("utf-8", "replace")
        assert "not attached" in text or "panel-only" in text, text[:400]
    finally:
        _stop(proc)

    output = _read(log)
    assert "Traceback" not in output, output[-2000:]
    assert "pygame.error" not in output, output[-2000:]
    assert "definitely-not-a-real-driver" not in output, output[-2000:]


def test_panel_only_requires_a_port():
    proc = subprocess.run(_args("--panel-only"), cwd=BASE_DIR, env=_env(),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "--panel-port" in (proc.stderr + proc.stdout)


# ---------------------------------------------------------------- bind safety

def test_non_loopback_bind_without_token_refuses_to_start():
    port = _free_port()
    proc = subprocess.run(
        _args("--panel-only", "--panel-port", str(port), "--panel-bind", "0.0.0.0"),
        cwd=BASE_DIR, env=_env(), capture_output=True, text=True, timeout=60,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 2, output
    assert "panel_token" in output and "secrets.json" in output, output


def test_non_loopback_bind_with_token_is_gated(tmp_path):
    """
    Bound to 0.0.0.0 for a few seconds on this machine, so it is briefly reachable off-box —
    which is exactly the property under test: without the token every route refuses, with it
    the panel answers.
    """
    port = _free_port()
    token = "test-token-not-a-real-secret"
    proc, log = _spawn(tmp_path, "lan_bind.log", "--panel-only", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0", env=_env(PANEL_TOKEN=token))
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_ready(f"{base}/api/status", proc, log), \
            f"panel never came up. Output:\n{_read(log)}"

        # without the token: refused, not a rendered panel
        try:
            status, _ = _get(f"{base}/")
            assert status == 403, f"expected 403 without a token, got {status}"
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code

        # with the token: served, and it knows it is on the network
        payload = json.loads(_get(f"{base}/api/status", token=token)[1])
        assert payload["status"]["panel_bind"] == "0.0.0.0"

        # the browser path works too: the auth route sets a cookie and redirects to /,
        # which only succeeds if the cookie is sent on the follow-up request. urllib keeps
        # no cookies by default, so use a jar — that IS the browser behaviour under test.
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with opener.open(f"{base}/_panel/auth?token={token}", timeout=5) as r:
            assert r.status == 200, r.status
            body = r.read().decode("utf-8", "replace")
        assert "control panel" in body, body[:300]
        assert any(c.name == "pd_panel_token" for c in jar), [c.name for c in jar]
    finally:
        _stop(proc)
