"""
The rotary encoder's whole path, in a real controller process.

The unit tests in test_hardware.py prove the gpiozero wrapper reports a delta. This file
proves the other half: that a detent reaches the Playlist on the render thread and moves
the display, and that the status line says it was the knob (not the panel or the keyboard).
A fake `gpiozero.py` in the sandbox is imported before the installed one, so no Pi is needed.
"""

from __future__ import annotations

from test_transport import _project, _read, _start, _stop, _wait_for

#: A one-detent encoder. The thread waits until the controller has attached its callback,
#: then bumps `steps` once and fires it — the same thing gpiozero does on a real Pi.
FAKE_GPIOZERO = '''\
import threading
import time


class RotaryEncoder:
    def __init__(self, a, b, max_steps=0):
        self.a, self.b, self.max_steps = a, b, max_steps
        self.steps = 0
        self.when_rotated = None
        threading.Thread(target=self._turn, daemon=True).start()

    def _turn(self):
        for _ in range(200):
            if self.when_rotated is not None:
                break
            time.sleep(0.05)
        time.sleep(0.5)
        self.steps = 1
        if self.when_rotated is not None:
            self.when_rotated()

    def close(self):
        pass


class Button:
    def __init__(self, *args, **kwargs):
        self.when_pressed = None
        self.when_released = None
        self.when_held = None

    def close(self):
        pass


class LED:
    def __init__(self, pin):
        pass

    def on(self):
        pass

    def off(self):
        pass

    def close(self):
        pass
'''


def test_a_detent_steps_the_display_and_is_reported_as_rotary(tmp_path):
    root = _project(tmp_path)
    (root / "gpiozero.py").write_text(FAKE_GPIOZERO)

    proc, url, log = _start(root, tmp_path, "rotary.log", "--input", "rotary")
    try:
        stepped = _wait_for(
            url,
            lambda s: s.get("mode_index") == 1 and "rotary" in (s.get("last_step") or ""),
            timeout=20,
        )
        assert stepped is not None, f"a detent never moved the display:\n{_read(log)}"
        assert stepped["last_step"].startswith("stepped next (rotary)"), stepped["last_step"]
        assert stepped["pending_steps"] == 0
        assert proc.poll() is None, "the app restarted instead of stepping"
    finally:
        _stop(proc)

    output = _read(log)
    assert "[Hardware] Rotary encoder on GPIO 17,27" in output, output
    assert "[Hardware] Encoder button on GPIO 23" in output, output
    assert "Falling back to keyboard" not in output, output


def test_a_rotary_app_with_no_encoder_falls_back_to_keyboard(tmp_path):
    """No gpiozero / no pin factory must not be a startup failure — the wall keeps running."""
    root = _project(tmp_path)
    # The sandbox has no fake module, but the developer venv may have gpiozero installed and
    # unable to open a pin factory (that is exactly the x86 case). Either way the app must run.
    proc, url, log = _start(root, tmp_path, "norotary.log", "--input", "rotary",
                            "--frames", "600")
    try:
        assert _wait_for(url, lambda s: s.get("frame", 0) >= 2, timeout=20) is not None, _read(log)
    finally:
        _stop(proc)
