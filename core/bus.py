# core/bus.py
#
# ControlBus — the ONLY channel between the panel thread and the render loop.
#
# Direction 1, panel -> loop:  post(cmd) puts a dict on a queue. The loop calls
#   dispatch(), which applies at most MAX_DRAIN_PER_FRAME commands per frame. A burst of
#   clicks can therefore delay a frame by a bounded amount, never unbounded.
#
# Direction 2, loop -> panel:  update_status(**fields) stamps a small dict under a lock;
#   the panel reads snapshot(), which returns a deep copy. The panel can read as often as
#   it likes without ever holding the render loop up.
#
# Rules (see AGENTS.md "the thread contract"):
#   * The loop never does disk I/O in dispatch(); commands carry finished data, not paths
#     to parse.
#   * The panel never calls into pygame, ModeManager or a mode object.
#   * Everything here is plain Python + stdlib: no pygame, no NiceGUI, fully testable.

import copy
import os
import queue
import threading
import time

APP_NAME = "pixel_dreams"
APP_VERSION = "0.1.0-phase1"

#: Hard cap on commands applied per frame, so the render loop stays smooth.
MAX_DRAIN_PER_FRAME = 8

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "ip6-localhost"}


def is_loopback(host: str) -> bool:
    """True for addresses that are not reachable off-machine."""
    host = (host or "").strip().lower()
    if host in LOOPBACK_HOSTS:
        return True
    return host.startswith("127.")


def require_loopback_or_token(bind: str, token: str | None) -> None:
    """
    Refuse a non-loopback bind with no token configured.

    Called at startup so the app cannot come up with an unauthenticated control surface:
    the alternative (start anyway, gate later) is a window where the panel is on the LAN
    with no gate at all. Raises ValueError with a message intended for the operator.
    """
    if is_loopback(bind):
        return
    if not token:
        raise ValueError(
            f"--panel-bind {bind} exposes the panel to the network, which requires a token. "
            f"Add {{\"panel_token\": \"<long random string>\"}} to secrets.json "
            f"(or set PANEL_TOKEN in the environment)."
        )


class ControlBus:
    """Thread-safe command queue + status snapshot."""

    def __init__(self, max_drain: int = MAX_DRAIN_PER_FRAME):
        self.max_drain = int(max_drain)
        self._queue: "queue.Queue[dict]" = queue.Queue()
        self._lock = threading.Lock()
        self._status = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "pid": os.getpid(),
            "started_at": time.time(),
            "display": "off",          # "off" | "windowed" | "fullscreen"
            "profile_abs": None,
            "profile_rel": None,
            "profile_source": None,    # "cli" | "registry" | "default"
            "mode_index": None,
            "mode_type": None,
            "mode_name": None,
            "mode_count": 0,
            "frame": 0,
            "fps": 0.0,
            "uptime_s": 0.0,
            "panel_bind": None,
            "panel_port": None,
            "nicegui_version": None,
            "commands_applied": 0,
            "commands_unknown": 0,
            "last_command": None,
            "last_command_at": None,
            "pong_count": 0,
        }

    # ---------- panel -> loop ----------

    def post(self, cmd: dict) -> None:
        """Queue one command. Safe to call from any thread."""
        if not isinstance(cmd, dict) or "cmd" not in cmd:
            raise ValueError(f"command must be a dict with a 'cmd' key, got {cmd!r}")
        self._queue.put(dict(cmd))

    def pending(self) -> int:
        return self._queue.qsize()

    def drain(self, limit: int | None = None) -> list:
        """Remove and return up to `limit` commands (default max_drain). Loop thread only."""
        limit = self.max_drain if limit is None else int(limit)
        out = []
        while len(out) < max(0, limit):
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out

    def dispatch(self, handlers: dict) -> int:
        """
        Apply every queued command whose name appears in `handlers`. Returns the number
        applied. A handler raising is logged and counted, never propagated: a bad command
        must not take the display down.
        """
        applied = 0
        for cmd in self.drain():
            name = cmd.get("cmd")
            handler = handlers.get(name)
            if handler is None:
                with self._lock:
                    self._status["commands_unknown"] += 1
                print(f"[Panel] Unknown command ignored: {name!r}")
                continue
            try:
                handler(cmd)
            except Exception as e:  # noqa: BLE001 - a command must never kill the loop
                print(f"[Panel] Command {name!r} failed: {type(e).__name__}: {e}")
                continue
            applied += 1
            with self._lock:
                self._status["commands_applied"] += 1
                self._status["last_command"] = name
                self._status["last_command_at"] = time.time()
        return applied

    # ---------- loop -> panel ----------

    def update_status(self, **fields) -> None:
        """Stamp status fields. Safe to call from the render thread every frame."""
        with self._lock:
            self._status.update(fields)

    def status(self, key: str, default=None):
        with self._lock:
            return self._status.get(key, default)

    def snapshot(self) -> dict:
        """A deep copy of the status; mutating it cannot affect the loop."""
        with self._lock:
            return copy.deepcopy(self._status)
