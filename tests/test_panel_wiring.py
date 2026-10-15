# tests/test_panel_wiring.py
#
# Process-level checks: they start the REAL controller and talk to it over HTTP. These pin the
# acceptance items that only a real process can prove:
#   * with the panel off, nicegui is never imported (the kiosk stays lean)
#   * with the panel on, it serves the live render loop and a command reaches it
#   * --panel-only serves with NO display initialised
#   * a non-loopback bind without a token refuses to start; with a token it is gated
#
# HERMETIC BY CONSTRUCTION: each test runs the app in a sandbox copy of the code tree with its
# own registry, profile and (optionally) secrets.json. An earlier version of this file ran
# against the real project, which made every test depend on whether the machine happened to
# have a secrets.json — the moment one existed for real LAN use, two tests broke. A test that
# reads the developer's runtime state is not a test.
#
# Child output goes to a log FILE (not a pipe) so a failure can print exactly what the app said.

import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

#: The smallest possible mode: enough for a real render loop, no assets, no network.
TINY_MODE = '''\
"""A do-nothing mode, so the sandbox needs no assets or network."""


class TinyMode:
    def __init__(self, config: dict):
        self.config = config

    def enter(self, manager):
        pass

    def exit(self):
        pass

    def handle_event(self, event):
        pass

    def update(self, dt):
        pass

    def render(self, screen):
        screen.fill((0, 0, 0))
'''

TINY_REGISTRY = {
    "settings": {"modes_config_file": "modes_config.json"},
    "types": {
        "tiny": {
            "entrypoint": "modes.tiny_mode:TinyMode",
            "required": [],
            "optional": ["show_clock", "font_size", "accent_rgb", "folder", "duration"],
            "params": {"font_size": {"min": 8, "max": 400}},
        }
    },
}

TINY_PROFILE = {
    "profile": {"label": "Sandbox", "resolution": [1280, 720]},
    "modes": {"0": {"type": "tiny", "font_size": 48, "show_clock": True,
                    "accent_rgb": [255, 0, 0]}},
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _sandbox(tmp_path, *, secrets: dict | None = None) -> Path:
    """A self-contained copy of the app: code + minimal registry/profile (+ secrets if asked)."""
    root = Path(tmp_path) / "app"
    (root / "modes").mkdir(parents=True)
    (root / "configs").mkdir()
    shutil.copy2(Path(BASE_DIR) / "pixel_dreams.py", root / "pixel_dreams.py")
    shutil.copytree(Path(BASE_DIR) / "core", root / "core",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(Path(BASE_DIR) / "panel", root / "panel",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (root / "modes" / "__init__.py").write_text("")
    (root / "modes" / "tiny_mode.py").write_text(TINY_MODE)
    (root / "modes_registry.json").write_text(json.dumps(TINY_REGISTRY, indent=2) + "\n")
    (root / "modes_config.json").write_text(json.dumps(TINY_PROFILE, indent=2) + "\n")
    if secrets is not None:
        (root / "secrets.json").write_text(json.dumps(secrets, indent=2) + "\n")
        os.chmod(root / "secrets.json", 0o600)
    return root


def _env(**extra) -> dict:
    """
    The environment a spawned controller gets.

    Three inherited things MUST go, or the child behaves as though it were still inside the
    parent test run:

    * ``PYTHONPATH`` — under a Hermes tool session it points at Hermes's own site-packages (a
      different Python version), whose modules shadow the project venv's pinned deps; the child
      then dies on an ABI mismatch (e.g. pydantic_core) before it can bind anything.
    * ``PYTEST_CURRENT_TEST`` — this is exactly how NiceGUI decides it is under pytest
      (``nicegui.helpers.is_pytest``), and its ``ui.run()`` then takes the screen-test branch,
      which reads ``NICEGUI_SCREEN_TEST_PORT`` and raises KeyError. A real app started by a test
      must be started as a real app.
    * ``PANEL_TOKEN`` — so a stray export in the developer's shell cannot silently arm or disarm
      the token gate a test is asserting about.
    """
    env = dict(os.environ)
    for var in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTEST_CURRENT_TEST",
                "NICEGUI_USER_SIMULATION", "PANEL_TOKEN"):
        env.pop(var, None)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONUNBUFFERED"] = "1"
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


def _spawn(root: Path, tmp_path, log_name: str, *args, env=None) -> tuple:
    """Start the controller inside the sandbox with its output in a file."""
    log_path = Path(tmp_path) / log_name
    handle = open(log_path, "w")
    proc = subprocess.Popen(_args(*args), cwd=str(root), env=env or _env(),
                            stdout=handle, stderr=subprocess.STDOUT, text=True)
    return proc, log_path


def _read(path) -> str:
    try:
        return Path(path).read_text()
    except Exception:
        return ""


def _wait_ready(url: str, proc, log_path, timeout: float = 25.0):
    """Wait until the server answers at all (403 counts: up, just gated). True/False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            _get(url, timeout=1.0)
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
    core.* is used by the panel AND by the controller, so importing it must not drag in the web
    stack (or pygame): that is what keeps the panel usable headless and the kiosk lean.
    """
    code = ("import sys; sys.path.insert(0, '.'); "
            "import core.bus, core.profiles, core.params, core.store, core.schema_scaffold; "
            "leaks = [m for m in ('nicegui', 'pygame', 'fastapi', 'uvicorn') "
            "if m in sys.modules]; print('LEAKS=' + ','.join(leaks))")
    proc = subprocess.run([sys.executable, "-c", code], cwd=BASE_DIR, env=_env(),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "LEAKS=" in proc.stdout, proc.stdout
    leaks = proc.stdout.split("LEAKS=")[1].strip()
    assert leaks == "", f"core modules pulled in: {leaks}"


def test_panel_off_never_imports_nicegui(tmp_path):
    root = _sandbox(tmp_path)
    proc = subprocess.run(_args("--frames", "90", "--windowed", "--input", "none"),
                          cwd=str(root), env=_env(), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    fields = _summary(proc.stdout)
    assert fields["nicegui_imported"] == "False", fields
    assert fields["panel"] == "off", fields
    assert float(fields["avg_fps"]) > 30, fields


# ---------------------------------------------------------------- panel on

def test_panel_serves_the_live_render_loop_and_receives_commands(tmp_path):
    root = _sandbox(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "panel_on.log", "--auto", "2", "--windowed",
                       "--input", "none", "--panel-port", str(port), "--frames", "300")
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
        assert snap["mode_index"] == 0
        assert [p["rel"] for p in payload["profiles"]] == ["modes_config.json"]
        assert payload["profiles"][0]["active"] is True

        # panel -> render loop -> back out through the panel
        _get(f"{base}/api/ping")
        deadline = time.time() + 6
        while time.time() < deadline:
            snap = json.loads(_get(f"{base}/api/status")[1])["status"]
            if snap["pong_count"] >= 1:
                break
            time.sleep(0.2)
        assert snap["pong_count"] >= 1, \
            f"the render loop never applied the panel's command. Output:\n{_read(log)}"
        assert snap["commands_applied"] >= 1
        assert snap["last_command"] == "ping"

        # fps is published on the ~4 Hz status cadence, NOT per frame, so seeing the pong does
        # not imply it has been stamped yet. Wait for it instead of racing the publish.
        deadline = time.time() + 5
        while time.time() < deadline and not snap.get("fps"):
            time.sleep(0.2)
            snap = json.loads(_get(f"{base}/api/status")[1])["status"]
        assert snap["fps"] > 0, f"fps never published. Output:\n{_read(log)}"
        assert snap["frame"] > 0, "no frames counted"

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
    root = _sandbox(tmp_path)
    port = _free_port()
    env = _env(SDL_VIDEODRIVER="definitely-not-a-real-driver")
    proc, log = _spawn(root, tmp_path, "panel_only.log", "--panel-only", "--panel-port",
                       str(port), env=env)
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


def test_panel_only_requires_a_port(tmp_path):
    root = _sandbox(tmp_path)
    proc = subprocess.run(_args("--panel-only"), cwd=str(root), env=_env(),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "--panel-port" in (proc.stderr + proc.stdout)


# ---------------------------------------------------------------- bind safety

def test_non_loopback_bind_without_token_refuses_to_start(tmp_path):
    """No token anywhere: the app must refuse rather than expose an unauthenticated panel."""
    root = _sandbox(tmp_path)
    port = _free_port()
    proc = subprocess.run(
        _args("--panel-only", "--panel-port", str(port), "--panel-bind", "0.0.0.0"),
        cwd=str(root), env=_env(), capture_output=True, text=True, timeout=60,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 2, output
    assert "panel_token" in output and "secrets.json" in output, output


def test_loopback_bind_still_needs_no_token(tmp_path):
    """The same sandbox WITHOUT secrets.json must serve happily on the default binding."""
    root = _sandbox(tmp_path)
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "loopback.log", "--panel-only", "--panel-port", str(port))
    try:
        assert _wait_ready(f"http://127.0.0.1:{port}/api/status", proc, log), _read(log)
        assert _get(f"http://127.0.0.1:{port}/api/status")[0] == 200
    finally:
        _stop(proc)


def test_non_loopback_bind_with_token_is_gated(tmp_path):
    """
    A token in the SANDBOX's secrets.json (never the developer's). Bound to 0.0.0.0 for a few
    seconds, so it is briefly reachable off-box — which is exactly the property under test:
    without the token every route refuses, with it the panel answers.
    """
    token = "sandbox-token-not-a-real-secret"
    root = _sandbox(tmp_path, secrets={"panel_token": token})
    port = _free_port()
    proc, log = _spawn(root, tmp_path, "lan_bind.log", "--panel-only", "--panel-port", str(port),
                       "--panel-bind", "0.0.0.0")
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
