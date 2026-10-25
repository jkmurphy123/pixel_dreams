# controlpanel/controls/__init__.py
#
# Control factory + shared base. Every animated control type maps to a class
# here; "plate" deliberately has none (purely decorative static sprite).

from .base import Control, ControlContext  # noqa: F401
from .bars import BarGraphControl, LedBarControl  # noqa: F401
from .arcane import (CandleFlameControl, DriftingRunesControl,  # noqa: F401
                     EmberFieldControl, FloatingOrbControl, LightningArcControl,
                     GlowingEyesControl, PotionBubblesControl, RuneCircleControl,
                     RuneLineControl,
                     SmokeWispControl)
from .keypad import KeypadControl  # noqa: F401
from .lampgroups import LampBankControl, LedMatrixControl  # noqa: F401
from .lamps import LampControl, RectLampControl, SquareLampControl  # noqa: F401
from .mad_science import (ElectricFilamentControl, JacobsLadderControl,  # noqa: F401
                          MechanicalWheelsControl, SparkTerminalControl)
from .needles import GaugeControl, MeterControl  # noqa: F401
from .readouts import (CounterControl, DigitalReadoutControl,  # noqa: F401
                       NixieControl)
from .reels import ClockControl, RadarControl, TapeReelControl  # noqa: F401
from .stateful import (PushButtonControl, RotaryKnobControl,  # noqa: F401
                       SelectorSwitchControl, ToggleSwitchControl)
from .traces import ScopeControl, StripChartControl  # noqa: F401

# type key -> animation class (see CONTROL_PANEL_DESIGN.md section 3.3)
CONTROL_CLASSES = {
    "gauge_round": GaugeControl,
    "meter_vu": MeterControl,
    "scope": ScopeControl,
    "strip_chart": StripChartControl,
    "bar_graph": BarGraphControl,
    "led_bar": LedBarControl,
    "lamp": LampControl,
    "lamp_square": SquareLampControl,
    "lamp_rect": RectLampControl,
    "lamp_bank": LampBankControl,
    "led_matrix": LedMatrixControl,
    "push_button": PushButtonControl,
    "keypad": KeypadControl,
    "toggle_switch": ToggleSwitchControl,
    "rotary_knob": RotaryKnobControl,
    "selector_switch": SelectorSwitchControl,
    "digital_readout": DigitalReadoutControl,
    "counter": CounterControl,
    "nixie": NixieControl,
    "tape_reel": TapeReelControl,
    "radar": RadarControl,
    "clock": ClockControl,
    # arcane family — drawn entirely procedurally over freeform artwork
    "candle_flame": CandleFlameControl,
    "ember_field": EmberFieldControl,
    "floating_orb": FloatingOrbControl,
    "rune_circle": RuneCircleControl,
    "rune_line": RuneLineControl,
    "smoke_wisp": SmokeWispControl,
    "lightning_arc": LightningArcControl,
    "potion_bubbles": PotionBubblesControl,
    "drifting_runes": DriftingRunesControl,
    "glowing_eyes": GlowingEyesControl,
    # mad-science family — procedural freeform overlays
    "jacobs_ladder": JacobsLadderControl,
    "electric_filament": ElectricFilamentControl,
    "spark_terminal": SparkTerminalControl,
    "mechanical_wheels": MechanicalWheelsControl,
    # "plate": static only
}


def make_control(placed, ctx: ControlContext):
    """
    Instantiate the animation object for a validated PlacedControl, or None
    if this type is static-only (renders as its sprite).
    """
    cls = CONTROL_CLASSES.get(placed.type)
    if cls is None:
        return None
    return cls(placed, ctx)

#: Colour keys each control type actually READS, for the layout page's colour pickers. One table, next
#: to the classes it describes, because the alternative (the page guessing) is a picker that offers a
#: knob the class ignores — and tests/test_control_edit.py walks every class and its bases to prove
#: this table matches the code, in both directions.
COLOUR_KEYS = {
    "gauge_round":     ("color", "needle_rgb", "hub_rgb"),
    "meter_vu":        ("color", "needle_rgb", "hub_rgb"),
    "scope":           ("color", "trace_rgb"),
    "strip_chart":     ("color", "trace_rgb"),
    "bar_graph":       ("color", "color_rgb"),
    "led_bar":         ("color",),
    "lamp":            ("color", "color_rgb"),
    "lamp_square":     ("color", "color_rgb"),
    "lamp_rect":       ("color", "color_rgb"),
    "lamp_bank":       ("color",),
    "led_matrix":      ("color", "color_rgb"),
    "push_button":     ("color", "ring_rgb"),
    "keypad":          ("accept_rgb", "color", "entry_rgb", "reject_rgb"),
    "toggle_switch":   ("color", "lever_rgb"),
    "rotary_knob":     ("color", "pointer_rgb"),
    "selector_switch": ("color", "pointer_rgb"),
    "digital_readout": ("color", "color_rgb"),
    "counter":         ("color", "color_rgb"),
    "nixie":           ("color", "color_rgb"),
    "tape_reel":       ("color", "spoke_rgb"),
    "radar":           ("color", "trace_rgb"),
    "clock":           ("color", "hand_rgb"),
    # arcane family: one colour key each, read through _color() so the picker finds it
    "candle_flame":    ("color", "flame_rgb"),
    "ember_field":     ("color", "ember_rgb"),
    "floating_orb":    ("color", "orb_rgb"),
    "rune_circle":     ("color", "rune_rgb"),
    "rune_line":       ("color", "rune_rgb"),
    "smoke_wisp":      ("color", "smoke_rgb"),
    "lightning_arc":   ("color", "arc_rgb"),
    "potion_bubbles":  ("color", "potion_rgb"),
    "drifting_runes":  ("color", "rune_rgb"),
    "glowing_eyes":    ("color", "eye_rgb"),
    "jacobs_ladder":   ("color", "arc_rgb"),
    "electric_filament": ("color", "filament_rgb"),
    "spark_terminal":  ("color", "spark_rgb"),
    "mechanical_wheels": ("color", "wheel_rgb", "face_rgb"),
    "plate":           (),
}
