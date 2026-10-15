# tests/test_bus.py
#
# ControlBus: the panel<->render-loop channel. The properties that matter are the ones
# that keep a 60fps kiosk alive: bounded work per frame, a bad command cannot kill the
# loop, and the panel can read status without ever blocking the render thread.

import os
import sys
import threading

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.bus import (  # noqa: E402
    APP_NAME,
    MAX_DRAIN_PER_FRAME,
    ControlBus,
    is_loopback,
    require_loopback_or_token,
)


# ---------------------------------------------------------------- posting / draining

def test_drain_is_bounded_per_frame():
    """A burst of clicks must not cost an unbounded frame: 20 commands = 8 + 8 + 4."""
    bus = ControlBus()
    for i in range(20):
        bus.post({"cmd": "ping", "n": i})

    assert bus.pending() == 20
    assert len(bus.drain()) == MAX_DRAIN_PER_FRAME
    assert len(bus.drain()) == MAX_DRAIN_PER_FRAME
    assert len(bus.drain()) == 4
    assert bus.drain() == []
    assert bus.pending() == 0


def test_drain_respects_explicit_limit():
    bus = ControlBus()
    for i in range(5):
        bus.post({"cmd": "ping"})
    assert len(bus.drain(limit=2)) == 2
    assert bus.pending() == 3


def test_post_rejects_non_commands():
    bus = ControlBus()
    with pytest.raises(ValueError):
        bus.post({"nope": 1})
    with pytest.raises(ValueError):
        bus.post("ping")  # type: ignore[arg-type]  # runtime guard: non-dict input


def test_post_copies_the_command():
    """The caller mutating its dict afterwards must not change what the loop applies."""
    bus = ControlBus()
    cmd = {"cmd": "ping", "value": 1}
    bus.post(cmd)
    cmd["value"] = 999
    assert bus.drain()[0]["value"] == 1


# ---------------------------------------------------------------- dispatch

def test_dispatch_applies_handlers_and_counts():
    bus = ControlBus()
    seen = []
    bus.post({"cmd": "ping"})
    bus.post({"cmd": "other", "x": 3})

    applied = bus.dispatch({"ping": lambda c: seen.append("ping"),
                            "other": lambda c: seen.append(c["x"])})

    assert applied == 2
    assert seen == ["ping", 3]
    snap = bus.snapshot()
    assert snap["commands_applied"] == 2
    assert snap["last_command"] == "other"
    assert snap["commands_unknown"] == 0


def test_unknown_command_is_counted_not_raised():
    bus = ControlBus()
    bus.post({"cmd": "from-a-newer-panel-version"})
    assert bus.dispatch({}) == 0
    assert bus.snapshot()["commands_unknown"] == 1


def test_failing_handler_does_not_kill_the_loop():
    """A handler raising is the classic way a panel action takes the display down."""
    bus = ControlBus()
    calls = []

    def boom(_cmd):
        raise RuntimeError("handler exploded")

    bus.post({"cmd": "bad"})
    bus.post({"cmd": "good"})

    applied = bus.dispatch({"bad": boom, "good": lambda c: calls.append("good")})

    assert applied == 1                 # the good command still ran
    assert calls == ["good"]
    assert bus.snapshot()["commands_applied"] == 1
    assert bus.snapshot()["last_command"] == "good"


# ---------------------------------------------------------------- status snapshot

def test_status_defaults_and_update():
    bus = ControlBus()
    snap = bus.snapshot()
    assert snap["app"] == APP_NAME
    assert snap["pid"] == os.getpid()
    assert snap["frame"] == 0
    assert snap["display"] == "off"

    bus.update_status(frame=120, fps=59.8, mode_index=3, mode_type="slideshow")
    snap = bus.snapshot()
    assert (snap["frame"], snap["fps"], snap["mode_index"]) == (120, 59.8, 3)


def test_snapshot_is_isolated_from_the_loop():
    """The panel gets a copy: a page mutating it must not corrupt the render loop's state."""
    bus = ControlBus()
    bus.update_status(fps=60.0)
    snap = bus.snapshot()
    snap["fps"] = 0.0
    snap["nested"] = {"added": True}

    fresh = bus.snapshot()
    assert fresh["fps"] == 60.0
    assert "nested" not in fresh


# ---------------------------------------------------------------- thread handoff

def test_commands_survive_a_real_thread_handoff():
    """
    The panel thread posts while the loop drains. Every command must be applied exactly
    once: no loss (panel says it worked, nothing happened) and no duplication.
    """
    bus = ControlBus(max_drain=4)
    total = 500
    applied = []
    lock = threading.Lock()

    def producer():
        for i in range(total):
            bus.post({"cmd": "ping", "n": i})

    def consumer():
        while len(applied) < total:
            for cmd in bus.drain():
                with lock:
                    applied.append(cmd["n"])

    p, c = threading.Thread(target=producer), threading.Thread(target=consumer)
    p.start(); c.start()
    p.join(timeout=10); c.join(timeout=10)

    assert not p.is_alive() and not c.is_alive()
    assert len(applied) == total
    assert sorted(applied) == list(range(total))     # no duplicates, nothing lost


# ---------------------------------------------------------------- bind safety

@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True), ("localhost", True), ("127.0.0.5", True), ("::1", True),
    ("0.0.0.0", False), ("192.168.40.216", False), ("", False),
])
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected


def test_non_loopback_bind_without_token_is_refused():
    with pytest.raises(ValueError) as e:
        require_loopback_or_token("0.0.0.0", None)
    msg = str(e.value)
    assert "panel_token" in msg and "secrets.json" in msg     # operator-actionable
    assert "0.0.0.0" in msg


def test_non_loopback_bind_allowed_with_token():
    require_loopback_or_token("0.0.0.0", "s3cret")
    require_loopback_or_token("127.0.0.1", None)              # loopback needs nothing
