# core/hardware.py
#
# Raspberry Pi rotary-encoder / button / LED hardware input.
#
# gpiozero is imported lazily inside setup() so the rest of the project
# runs fine on Windows / vanilla Linux dev machines without it installed.
#
# The callbacks below run on gpiozero's own threads. They must not touch pygame,
# the ModeManager or the Playlist: pixel_dreams.py drains the state they leave
# behind on the render thread, exactly like the panel's command queue. A fast
# spin therefore cannot corrupt a half-finished mode switch.

import threading
import time


class RotaryHardware:
    """
    Wires up:
      - rotary encoder (pins a=17, b=27 by default) -> on_rotate(delta)
      - encoder push button (pin 23 by default)     -> short press: on_tap(),
                                                       hold 2s: on_hold()
      - optional indicator LEDs                     -> set_mode(mode_index)

    Pins are configurable so a second kiosk does not have to match the first
    one's wiring. LEDs are optional: pass led_pins=() (the controller's
    --rotary-led-pins "") for a build with no LED ring. If one LED fails to
    initialise the rest still work; if the encoder itself fails, setup()
    returns False and the controller falls back to the keyboard.
    """

    LED_PINS = [5, 6, 13, 19, 26, 21, 20, 16]

    def __init__(self, on_rotate, on_tap, on_hold, *,
                 encoder_pins=(17, 27), button_pin=23, led_pins=None,
                 hold_time=2.0):
        self._on_rotate = on_rotate
        self._on_tap = on_tap
        self._on_hold = on_hold

        pins = tuple(encoder_pins if encoder_pins is not None else (17, 27))
        if len(pins) != 2:
            raise ValueError(f"encoder_pins must be (A, B), got {pins!r}")
        self.encoder_pins = (int(pins[0]), int(pins[1]))
        self.button_pin = int(button_pin)
        self.led_pins = tuple(self.LED_PINS if led_pins is None else led_pins)
        self.hold_time = float(hold_time)

        self.encoder = None
        self.button = None
        self.leds = []

        self._last_steps = 0
        self._press_t0 = 0.0
        self._led_index = -1
        self._steps_lock = threading.Lock()
        self._time = time

    # ---------- setup ----------

    def setup(self) -> bool:
        """Initialize GPIO devices. Returns False if the encoder is unavailable."""
        try:
            from gpiozero import Button, LED, RotaryEncoder
        except Exception as e:
            print(f"[Hardware] gpiozero not available ({e}); rotary input disabled")
            return False

        a, b = self.encoder_pins
        try:
            self.encoder = RotaryEncoder(a=a, b=b, max_steps=0)
        except Exception as e:
            print(f"[Hardware] Rotary encoder on GPIO {a},{b} failed: {e}")
            self.encoder = None
            return False
        self.encoder.when_rotated = self._handle_rotation
        print(f"[Hardware] Rotary encoder on GPIO {a},{b}")

        try:
            self.button = Button(self.button_pin, pull_up=True,
                                 hold_time=self.hold_time, bounce_time=0.05)
            self.button.when_pressed = self._handle_pressed
            self.button.when_released = self._handle_released
            self.button.when_held = self._handle_held
            print(f"[Hardware] Encoder button on GPIO {self.button_pin} "
                  f"(hold {self.hold_time:.0f}s reports a hold)")
        except Exception as e:
            print(f"[Hardware] Encoder button on GPIO {self.button_pin} failed: {e}; "
                  f"rotation still works")
            self.button = None

        for pin in self.led_pins:
            try:
                self.leds.append(LED(pin))
            except Exception as e:
                print(f"[Hardware] LED on GPIO {pin} failed: {e}; continuing without it")
        if self.leds:
            print(f"[Hardware] {len(self.leds)} mode LED(s) initialised")
        return True

    # ---------- callbacks ----------

    def _handle_rotation(self):
        if self.encoder is None:
            return
        with self._steps_lock:
            steps = self.encoder.steps
            delta = steps - self._last_steps
            self._last_steps = steps
        if delta != 0:
            # The real number of detents, not just a sign: a fast spin is one
            # callback with delta 5, and the controller can jump five slots.
            self._on_rotate(delta)

    def _handle_pressed(self):
        self._press_t0 = self._time.monotonic()

    def _handle_released(self):
        held = self._time.monotonic() - self._press_t0
        if held < self.hold_time:
            print(f"[Hardware] Short press ({held:.2f}s)")
            self._on_tap()

    def _handle_held(self):
        self._on_hold()

    # ---------- LEDs ----------

    def set_mode(self, mode_index: int):
        if not self.leds:
            return
        led_index = int(mode_index) % len(self.leds)
        if led_index == self._led_index:
            return
        self._led_index = led_index
        for i, led in enumerate(self.leds):
            try:
                led.on() if i == led_index else led.off()
            except Exception:
                pass

    # ---------- cleanup ----------

    def close(self):
        devices = [self.encoder, self.button, *self.leds]
        for dev in devices:
            if dev is None:
                continue
            for attr in ("when_rotated", "when_pressed", "when_released", "when_held"):
                try:
                    setattr(dev, attr, None)
                except Exception:
                    pass
        try:
            for led in self.leds:
                led.off()
        except Exception:
            pass
        for dev in devices:
            try:
                if dev is not None:
                    dev.close()
            except Exception:
                pass
        self.encoder = None
        self.button = None
        self.leds = []
