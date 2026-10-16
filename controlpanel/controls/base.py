# controlpanel/controls/base.py
#
# Control base class + the shared context every control gets.
#
# Controls are created from a validated PlacedControl (position/sprite/raw
# spec from the layout file) plus a ControlContext (rng + palette from the
# mode config). The static sprite background is blitted by the compositor;
# controls only draw their animated overlay primitives on top, in
# design-canvas coordinates.

import random

from ..geometry import CELL_SIZE, cell_rect  # noqa: F401  (cell_rect re-exported)


class ControlContext:
    """Shared per-mode state handed to every control."""

    def __init__(self, seed=None, accent_rgb=(255, 176, 64),
                 trace_rgb=(80, 255, 120), lamp_rgb=None):
        self.rng = random.Random(seed)
        self.accent_rgb = tuple(accent_rgb)
        self.trace_rgb = tuple(trace_rgb)
        # default lamp color when the sprite ID doesn't name one
        self.lamp_rgb = tuple(lamp_rgb) if lamp_rgb else (255, 60, 50)


class Control:
    """
    Base class for animated controls.

    rect: pixel rect on the design canvas (static sprite area).
    The layout's raw control dict is available as self.spec for per-control
    overrides (signal, wave, colors, ...).

    Color override chain for any drawn color: the generic "color" key wins,
    then the type-specific key ("needle_rgb", "trace_rgb", ...), then the
    control's built-in default. Use self._color() to resolve.
    """

    def __init__(self, placed, ctx: ControlContext):
        self.ctx = ctx
        self.spec = placed.raw
        self.type = placed.type
        self.sprite_id = placed.sprite_id
        # pixel rect on the design canvas — computed by the layout loader
        # for both grid (cells -> px) and freeform (explicit px) modes
        self.rect = placed.rect_px
        self._recompute_geometry()

    # ---------------------------------------------------------------- layout editing (design §Phase 6)

    def _recompute_geometry(self):
        """
        Recompute anything DERIVED from self.rect. Called from __init__ and from set_rect().

        Why this exists: a control that computes its centre/pivot/radius from the rect once and caches
        it will NOT move when something assigns `self.rect` — measured on the real freeform layouts,
        assigning the rect alone left 13/13 and 12/12 controls drawing in their old position, so a
        layout editor that did that would look broken while doing everything "right".

        Contract for subclasses: if you cache a value derived from the rect, override this, recompute
        it here, and call super()._recompute_geometry() first (the base handles self.window). Depend
        only on what base __init__ sets (`self.rect`, `self.spec`, class constants) OR guard with
        getattr — base __init__ calls this BEFORE your own __init__ body runs, and call it again at
        the end of your __init__ if you need something set there.
        tests/test_layout_align.py::test_every_control_class_survives_a_move enforces this.
        """
        # any control that draws through _window() gets its window kept in step automatically
        if "_window_default" in self.__dict__:
            self.window = self._window()
        return None

    def set_rect(self, rect):
        """
        Move and/or resize a LIVE control, the way the alignment editor's nudges do.

        Preserves animation state on purpose: the overlay keeps animating in its new place, which is
        what you want while judging alignment. (Replacing the control object would work too, but a
        lamp, readout or scope draws nothing until it has been updated — it would blink blank on every
        single button press.)
        """
        self.rect = tuple(int(v) for v in rect)
        self._recompute_geometry()

    def _color(self, key: str, default):
        """
        Resolve a drawn color: layout "color" overrides everything, then
        the type-specific layout key (e.g. "needle_rgb"), then default.
        """
        return tuple(self.spec.get("color", self.spec.get(key, default)))

    def _anchor(self, key: str, default):
        """
        Anchor point as a fraction of the sprite rect, overridable per
        control in the layout (e.g. "pivot": [0.5, 0.62]). Fractions keep
        anchors valid across footprints (design section 7).
        """
        fx, fy = self.spec.get(key, default)
        x, y, w, h = self.rect
        return (x + fx * w, y + fy * h)

    def _window(self, default=(0.08, 0.18, 0.84, 0.64)):
        """
        Sub-rect of the sprite to draw into, as fractions
        (fx, fy, fw, fh) — used by scopes/readouts. Overridable via
        the layout's "window" key.

        The default is REMEMBERED the first time it is used, so _recompute_geometry() can keep the
        window in step with the rect without every subclass having to declare its default twice.
        """
        if "_window_default" not in self.__dict__:
            self._window_default = default
        fx, fy, fw, fh = self.spec.get("window", self._window_default)
        x, y, w, h = self.rect
        return (x + fx * w, y + fy * h, fw * w, fh * h)

    def update(self, dt: float):
        pass

    def draw_overlay(self, surface):
        pass
