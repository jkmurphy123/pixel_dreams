# tests/test_hardware.py
#
# The Pi rotary encoder wrapper, without a Pi: a fake gpiozero module lets the tests
# exercise pin mapping, optional LEDs, and the tap/hold distinction. The controller's
# threading rule is tested at the other end — these callbacks only REPORT a delta/tap/hold;
# pixel_dreams.py drains that state on the render thread.

from __future__ import annotations

import sys
import types

import pytest

from core.hardware import RotaryHardware
from pixel_dreams import parse_args


# ---------------------------------------------------------------- fakes

class FakeEncoder:
    last = None

    def __init__(self, a, b, max_steps=0):
        self.a, self.b, self.max_steps = a, b, max_steps
        self.steps = 0
        self.when_rotated = None
        self.closed = False
        FakeEncoder.last = self

    def close(self):
        self.closed = True


class FakeButton:
    last = None

    def __init__(self, pin, pull_up=False, hold_time=1.0, bounce_time=None):
        self.pin, self.pull_up = pin, pull_up
        self.hold_time, self.bounce_time = hold_time, bounce_time
        self.when_pressed = None
        self.when_released = None
        self.when_held = None
        self.closed = False
        FakeButton.last = self

    def close(self):
        self.closed = True


class FakeLED:
    instances = []
    on_calls = 0
    off_calls = 0

    def __init__(self, pin):
        self.pin = pin
        self.is_on = False
        self.closed = False
        FakeLED.instances.append(self)

    def on(self):
        FakeLED.on_calls += 1
        self.is_on = True

    def off(self):
        FakeLED.off_calls += 1
        self.is_on = False

    def close(self):
        self.closed = True


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def monotonic(self):
        return self.now


@pytest.fixture
def gpio(monkeypatch):
    module = types.ModuleType("gpiozero")
    module.RotaryEncoder = FakeEncoder
    module.Button = FakeButton
    module.LED = FakeLED
    monkeypatch.setitem(sys.modules, "gpiozero", module)
    FakeEncoder.last = None
    FakeButton.last = None
    FakeLED.instances = []
    FakeLED.on_calls = 0
    FakeLED.off_calls = 0
    return module


def _hardware(**overrides):
    kwargs = dict(encoder_pins=(5, 6), button_pin=12, led_pins=(7, 8))
    kwargs.update(overrides)
    return RotaryHardware(lambda d: None, lambda: None, lambda: None, **kwargs)


# ---------------------------------------------------------------- setup / pins

def test_setup_uses_the_configured_pins(gpio):
    hw = _hardware()
    assert hw.setup() is True

    encoder = FakeEncoder.last
    assert (encoder.a, encoder.b) == (5, 6)
    assert FakeButton.last.pin == 12
    assert [led.pin for led in hw.leds] == [7, 8]


def test_rotation_reports_the_real_delta_not_just_a_sign(gpio):
    seen = []
    hw = _hardware(led_pins=())
    hw._on_rotate = seen.append
    assert hw.setup()

    FakeEncoder.last.steps = 4
    hw._handle_rotation()
    FakeEncoder.last.steps = 1
    hw._handle_rotation()
    FakeEncoder.last.steps = 1                     # no movement -> no callback
    hw._handle_rotation()

    assert seen == [4, -3]


def test_a_bad_led_does_not_disable_the_encoder(gpio):
    class PickyLED(FakeLED):
        def __init__(self, pin):
            if pin == 8:
                raise RuntimeError("GPIO busy")
            super().__init__(pin)

    gpio.LED = PickyLED
    hw = _hardware(led_pins=(7, 8))
    assert hw.setup() is True
    assert [led.pin for led in hw.leds] == [7]


def test_leds_are_optional(gpio):
    hw = _hardware(led_pins=())
    assert hw.setup() is True
    assert hw.leds == []
    hw.set_mode(3)                                  # must not raise
    assert FakeLED.instances == []


def test_a_missing_encoder_falls_back_instead_of_crashing(gpio):
    class BrokenEncoder:
        def __init__(self, *a, **kw):
            raise RuntimeError("no pin factory")

    gpio.RotaryEncoder = BrokenEncoder
    assert _hardware().setup() is False


def test_a_missing_button_still_allows_rotation(gpio):
    class BrokenButton:
        def __init__(self, *a, **kw):
            raise RuntimeError("pin in use")

    gpio.Button = BrokenButton
    hw = _hardware()
    assert hw.setup() is True
    assert hw.button is None
    FakeEncoder.last.steps = 2
    hw._handle_rotation()                            # no crash without a button


# ---------------------------------------------------------------- LEDs

def test_set_mode_lights_one_led_and_is_idempotent(gpio):
    hw = _hardware(led_pins=(7, 8, 9))
    assert hw.setup()

    hw.set_mode(4)                                   # 4 % 3 == 1
    assert [led.is_on for led in hw.leds] == [False, True, False]
    calls = (FakeLED.on_calls, FakeLED.off_calls)

    hw.set_mode(4)                                   # same position: no GPIO churn
    assert (FakeLED.on_calls, FakeLED.off_calls) == calls

    hw.set_mode(0)
    assert [led.is_on for led in hw.leds] == [True, False, False]


# ---------------------------------------------------------------- button semantics

def test_short_press_is_a_tap(gpio):
    taps, holds = [], []
    hw = RotaryHardware(lambda d: None, lambda: taps.append("tap"),
                        lambda: holds.append("hold"),
                        encoder_pins=(5, 6), button_pin=12, led_pins=())
    assert hw.setup()
    hw._time = FakeClock(100.0)

    hw.button.when_pressed()
    hw._time.now = 100.4
    hw.button.when_released()

    assert taps == ["tap"]
    assert holds == []


def test_holding_past_the_threshold_is_a_hold_not_a_tap(gpio):
    taps, holds = [], []
    hw = RotaryHardware(lambda d: None, lambda: taps.append("tap"),
                        lambda: holds.append("hold"),
                        encoder_pins=(5, 6), button_pin=12, led_pins=())
    assert hw.setup()
    hw._time = FakeClock(100.0)

    hw.button.when_pressed()
    hw._time.now = 102.1
    hw.button.when_held()
    hw.button.when_released()                        # release after a hold must not tap

    assert holds == ["hold"]
    assert taps == []


# ---------------------------------------------------------------- cleanup

def test_close_detaches_callbacks_and_closes_every_device(gpio):
    hw = _hardware()
    assert hw.setup()
    encoder, button = hw.encoder, hw.button
    leds = list(hw.leds)

    hw.close()

    assert encoder.when_rotated is None
    assert button.when_pressed is None and button.when_released is None and button.when_held is None
    assert encoder.closed and button.closed and all(led.closed for led in leds)
    assert hw.encoder is None and hw.button is None and hw.leds == []


# ---------------------------------------------------------------- CLI surface

def test_rotary_pin_flags_parse():
    args = parse_args(["prog", "--input", "rotary", "--rotary-pins", "5,6",
                       "--rotary-button-pin", "12", "--rotary-led-pins", ""])
    assert args.rotary_pins == (5, 6)
    assert args.rotary_button_pin == 12
    assert args.rotary_led_pins == ()


@pytest.mark.parametrize("argv", [
    ["--rotary-pins", "5"],
    ["--rotary-pins", "5,5"],
    ["--rotary-button-pin", "27"],                  # collides with the default B pin
    ["--rotary-led-pins", "17"],                    # collides with the default A pin
    ["--rotary-led-pins", "5,5"],
    ["--rotary-pins", "5,99"],
])
def test_bad_rotary_pin_maps_are_refused(argv):
    with pytest.raises(SystemExit):
        parse_args(["prog", *argv])
