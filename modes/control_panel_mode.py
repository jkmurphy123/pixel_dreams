# modes/control_panel_mode.py
#
# control_panel mode: an old-fashioned make-believe control panel — gauges,
# switches, lamps, scopes and readouts arranged by a JSON layout file and
# drawn from a swappable sprite-sheet skin. See CONTROL_PANEL_DESIGN.md.
#
# Phase 2: signals + animated gauge_round / lamp / scope controls. Other
# types render as their static sprite until their phase lands.
#
# Config keys (see modes_registry.json "controlpanel" entry):
#   layout_file (required) — layout name under assets/control_panel/layouts/
#                            or a full path
#   background_image (optional) — the artwork the overlays are drawn over: a
#                            bare name under assets/control_panel/backgrounds/,
#                            or a path (absolute, or with a separator) used as
#                            given. OVERRIDES the layout file's own
#                            background_image; blank = use the layout's.
#   skin        (optional) — skin name under assets/control_panel/skins/
#                            or a full path (default "placeholder")
#   seed        (optional) — int; fixes the random choreography for debugging
#   accent_rgb  (optional) — needle/overlay color (default amber)
#   trace_rgb   (optional) — scope trace color (default green)
#   lamp_rgb    (optional) — fallback lamp color when the sprite ID doesn't
#                            name one (default red)

import pygame

from controlpanel.compositor import Compositor
from controlpanel.controls import ControlContext, make_control
from controlpanel.layout import LayoutError, load_layout
from controlpanel.skin import SkinError, load_skin


class ControlPanelMode:
    # Valid scaling strategies for the design canvas -> screen blit.
    #   stretch — legacy fill-the-screen behavior (may distort aspect ratio)
    #   fit     — uniform scale to fit inside the screen, letterboxing if needed
    #   cover   — uniform scale to cover the screen, cropping if needed
    _VALID_SCALE_MODES = {"stretch", "fit", "cover"}

    def __init__(self, config: dict):
        # Keep __init__ cheap and asset-free: tests construct every mode
        # without a display. All file/graphics work happens in enter().
        self.layout_file = config.get("layout_file", "")
        # The artwork is the MODE's business, not the layout's: the layout file names a default and
        # this overrides it, so one layout can be reused over different PNGs.
        self.background_param = str(config.get("background_image", "") or "").strip()
        self.background_image = None                    # resolved path, set in enter()
        self.skin_name = str(config.get("skin", "placeholder")).strip()
        self.seed = config.get("seed")
        self.accent_rgb = tuple(config.get("accent_rgb", [255, 176, 64]))
        self.trace_rgb = tuple(config.get("trace_rgb", [80, 255, 120]))
        lamp_rgb = config.get("lamp_rgb")
        self.lamp_rgb = tuple(lamp_rgb) if lamp_rgb else None

        scale_mode = str(config.get("scale_mode", "fit")).strip().lower()
        if scale_mode not in self._VALID_SCALE_MODES:
            scale_mode = "fit"
        self.scale_mode = scale_mode

        self.manager = None
        self.compositor: Compositor | None = None
        self.controls: list = []
        self._error: str | None = None

        # Live layout-editing state, driven by the alignment page through the bus (design Phase 6).
        # The mode owns it; the panel only ever sees what the loop publishes in the status.
        self.layout_name = ""
        self.layout_mode = ""
        self.canvas_size = (0, 0)
        self.selected: int | None = None
        self.frozen = False
        self._by_index: dict = {}          # the LAYOUT's control index -> live control object
        self._static_only: list = []       # indices whose type has no animated overlay
        self._placed: list = []            # the layout's PlacedControl list, for marker geometry

    def enter(self, manager):
        self.manager = manager
        self._error = None
        self.controls = []
        try:
            layout = load_layout(self.layout_file,
                                 background_override=self.background_param or None)
            # freeform layouts carry their own full-panel artwork; grid
            # layouts are built from skin sprites (decision D6)
            skin = None if layout.mode == "freeform" else load_skin(self.skin_name)
            self.compositor = Compositor(layout, skin, scale_mode=self.scale_mode)
            self.compositor.build()

            ctx = ControlContext(seed=self.seed, accent_rgb=self.accent_rgb,
                                 trace_rgb=self.trace_rgb, lamp_rgb=self.lamp_rgb)
            self.layout_name = layout.name
            self.layout_mode = layout.mode
            self.background_image = layout.background_image    # the artwork actually in use
            self.canvas_size = tuple(layout.design_resolution)
            self._placed = list(layout.controls)
            self._by_index = {}
            self.selected = None
            for index, placed in enumerate(layout.controls):
                control = make_control(placed, ctx)
                if control is not None:
                    self.controls.append(control)
                    # Keyed by the LAYOUT's index, not by the position in self.controls: a type with
                    # no animated overlay returns None, and the two numbering schemes would then drift
                    # apart — the editor would move the wrong overlay and be believed.
                    self._by_index[index] = control
            self._static_only = [i for i in range(len(layout.controls)) if i not in self._by_index]

            skin_name = skin.name if skin is not None else "(background image)"
            art = f" background='{layout.background_image}'" if layout.background_image else ""
            print(f"[ControlPanel] skin='{skin_name}' layout='{layout.name}' "
                  f"mode={layout.mode}{art} "
                  f"({len(layout.panels)} panels, {len(layout.controls)} controls, "
                  f"{len(self.controls)} animated)")
        except Exception as e:                       # a kiosk shows the reason, it does not vanish
            # kiosk-friendly: log once, show the reason on screen
            self._error = str(e)
            self.compositor = None
            print(f"[ControlPanel] failed to load: {self._error}")

    def exit(self):
        # drop surfaces so GC can reclaim them
        self.compositor = None
        self.controls = []
        self._by_index = {}
        self._placed = []
        self.selected = None
        self.frozen = False
        self.manager = None

    def handle_event(self, event):
        pass

    # ---------------------------------------------------------------- live layout editing (Phase 6)
    #
    # The alignment page posts commands on the control bus; the loop calls these on the render
    # thread. Every one returns a report instead of raising: a refusal here is a fact to publish,
    # not an exception to throw through a frame. Nothing touches the disk, and nothing rebuilds the
    # compositor — a nudge is a geometry update on one live object.

    def edit_rect(self, index, rect) -> dict:
        """
        Move and/or resize one overlay in the running instance.

        Refusals are explicit and name the reason, because "nothing happened" is the most confusing
        possible answer: an index this layout does not have, and a static-only type (which draws
        nothing at all in a freeform layout, so there is no animated overlay to move).
        """
        control = self._by_index.get(index)
        if control is None:
            if index in self._static_only:
                return {"ok": False, "index": index, "reason":
                        f"control #{index} is a static-only type: in a freeform layout it has no "
                        f"animated overlay, so there is nothing on the wall to move"}
            return {"ok": False, "index": index, "reason": f"this layout has no control #{index}"}
        try:
            control.set_rect(rect)
        except (TypeError, ValueError) as e:
            return {"ok": False, "index": index, "reason": f"bad rect {rect!r}: {e}"}
        return {"ok": True, "index": index, "rect": tuple(int(v) for v in control.rect),
                "type": type(control).__name__}

    def select(self, index) -> dict:
        """Mark the control being positioned (it gets the marker on the wall), or clear it."""
        if index is None:
            self.selected = None
            return {"ok": True, "selected": None}
        index = int(index)
        if index not in self._by_index and index not in self._static_only:
            return {"ok": False, "reason": f"this layout has no control #{index}"}
        self.selected = index
        return {"ok": True, "selected": index}

    def freeze(self, on) -> dict:
        """
        Stop the overlays animating so the thing being positioned holds still.

        Implemented as "skip update()", not as dt=0: several control types advance off the wall clock
        or on randomness, so a zero timestep does not actually hold them still.
        """
        self.frozen = bool(on)
        return {"ok": True, "frozen": self.frozen}

    def marker_rects(self) -> list:
        """The (rect, label) pairs the compositor should outline this frame."""
        if self.selected is None:
            return []
        control = self._by_index.get(self.selected)
        if control is not None:
            rect = tuple(control.rect)
        elif 0 <= self.selected < len(self._placed):
            rect = tuple(self._placed[self.selected].rect_px)
        else:
            return []
        return [(rect, f"#{self.selected}")]

    def layout_report(self) -> dict:
        """
        What the alignment page needs to know about the LIVE instance: the layout it is showing, the
        canvas, how many overlays are animated, the live rects (so the page can confirm what the wall
        is showing rather than trusting its own copy), and the editor state.
        """
        return {
            "layout_file": self.layout_file,
            "layout": self.layout_name,
            "mode": self.layout_mode,
            "background_param": self.background_param,
            "background_image": self.background_image,
            "canvas": list(self.canvas_size),
            "controls": len(self._placed),
            "animated": len(self._by_index),
            "static_only": sorted(self._static_only),
            "selected": self.selected,
            "frozen": self.frozen,
            "rects": {str(i): [int(v) for v in c.rect] for i, c in sorted(self._by_index.items())},
        }

    def update(self, dt: float):
        if self.frozen:
            # hold still for alignment; see freeze()
            return
        for control in self.controls:
            control.update(dt)

    def render(self, screen: pygame.Surface):
        if self.compositor is not None:
            self.compositor.render(screen, self.controls, self.marker_rects())
            return

        # error fallback: plain background + one-line reason
        screen.fill((18, 20, 24))
        if self.manager is not None and self._error:
            font = self.manager.cache.get_font("dejavusansmono", 28)
            surf = font.render(f"ControlPanel: {self._error}", True, (255, 120, 120))
            screen.blit(surf, (40, 40))
