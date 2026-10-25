# modes/ink_map_mode.py
"""
Ink Map -- a fantasy map drawn as if by hand: parchment, then pen and ink.

Phase 2 draws THE COASTLINE. Rice is poured onto a field, the grains are welded into land, the
outline is traced, and the heavy `05` nib draws it -- a few pixels at a time, so you watch the hand
work. Everything after it (the sea, the land within, the forest, the rock, the lettering) is a later
phase; the registry entry already declares those controls and each one's `help` says which phase
brings it in.

What "drawn by hand" means mechanically, in one paragraph: the sheet is planned as an ordered list of
pen strokes, in the order the tutorial draws them, and a cursor paces that list so the sheet takes
`draw_minutes` to appear. Every stroke is drawn onto a supersampled layer so a 2 px pen line is
smooth, and only the part of that layer a stroke touched is composited onto the paper.

The plan is the tutorial's own order, and it is built as PASSES: `coast` (phase 2), then `sea`
(phase 3) -- the coastline, then the line traced parallel to it with the video's four units hung off
it, then the lakes inland. Later phases append their own passes at the end.

Live today: `paper_tone`, `ink_rgb`, `paper_age`, `vignette`, `supersample`, `reveal_fps`, `seed`,
`draw_minutes`, `pen_scale`, `tremor`, `land_coverage`, `grain_size_cells`, `water_style`,
`water_rings`, `lake_count`.

Config -- every key is declared in `modes_registry.json`, which is also where each one's `help`
says which phase brings it into the drawing. Declared but not yet drawn with: everything else. They
are declared up front so the schema is settled and the panel form is complete; the help text names
the phase, so a control with no effect says so on the page.

Lifecycle notes for this repo's contract:
  * the controller owns the display; this mode only ever blits its own canvas,
  * `exit()` drops every surface, because a 2x ink layer is 33 MB and a mode switch must be able
    to reclaim it,
  * the per-frame path never allocates a full-screen surface: the parchment is built once in
    `enter()`.
"""

from __future__ import annotations

import random
import time

import pygame

from core import inkdraw, inkland, inkwater
from core.inksheet import Reveal, Sheet

#: Cycles the sheet: the pen lifts, and a new page is poured (a new seed unless one is pinned).
_REDRAW_KEYS = (pygame.K_SPACE, pygame.K_r)

#: The parameters this mode DRAWS WITH today. Everything else in the registry is declared for a
#: later phase and says so in its own `help`; a test compares this tuple against the registry both
#: ways, so a control can never be live without being listed here, or listed here while its help
#: still tells the user it does nothing.
LIVE_PARAMS = ("seed", "draw_minutes", "reveal_fps",
               "paper_tone", "ink_rgb", "paper_age", "vignette", "supersample",
               "pen_scale", "tremor", "land_coverage", "grain_size_cells",
               "water_style", "water_rings", "lake_count")

#: The four sea treatments the video shows. An unknown value falls back to the main one rather than
#: drawing nothing, because a control the panel cannot set is not a reason to lose the sea.
WATER_STYLES = ("hash", "squiggle", "stipple", "wave")

#: How many clumps of rice are poured. Not a registry parameter: the approved schema has no such
#: key, so it stays an implementation constant until a later phase decides it is worth a dial.
POUR_CLUMPS = 4

#: The smallest traced outline worth a stroke, in field cells (area). Real poured rice in clumps does
#: not leave twenty isolated grains scattered far from the clumps -- those specks are an artefact of
#: the Gaussian tails, and tracing them made the sheet look like a lava lamp. The measured areas of
#: one reference pour fall 75990, 44499, 15951, 9100, then 1502, 1370, 600, 538, ... so this sits in
#: that gap: the sheet comes out as a few continents and a handful of islands.
ISLAND_MIN_CELLS = 1200.0

#: The coast is resampled to about this many ink pixels between points, then cut into runs about
#: this long for the reveal to pace. The run length is what makes the pen travel at a visible speed
#: rather than a whole island appearing at once.
COAST_RESAMPLE_INK_PX = 4.0
COAST_RUN_INK_PX = 16.0


def _rgb(value, fallback) -> tuple:
    """A 3-tuple of ints from config, tolerating a hex string or a short/garbled list."""
    if isinstance(value, str):
        body = value.lstrip("#")
        if len(body) == 6:
            try:
                return tuple(int(body[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(c))) for c in value[:3])
        except (TypeError, ValueError):
            pass
    return tuple(fallback)


class InkMapMode:
    """The ink-map mode: one sheet of paper, and the hand drawing on it."""

    def __init__(self, config: dict):
        self.config = config or {}

        # -- the sheet's appearance (live in phase 1)
        self.paper_tone = _rgb(self.config.get("paper_tone", [232, 217, 184]), (232, 217, 184))
        self.ink_rgb = _rgb(self.config.get("ink_rgb", [43, 33, 26]), (43, 33, 26))
        self.paper_age = _number(self.config.get("paper_age"), 1.0, 0.0, 3.0)
        self.vignette = _number(self.config.get("vignette"), 1.0, 0.0, 3.0)
        self.supersample = int(_number(self.config.get("supersample"), 2.0, 1.0, 3.0))

        # -- pacing
        self.reveal_fps = _number(self.config.get("reveal_fps"), 20.0, 1.0, 60.0)
        self.draw_minutes = _number(self.config.get("draw_minutes"), 5.0, 0.0, None)
        # seed 0 means "pick one and report it"; any other value reproduces that exact sheet. The
        # pin has to be remembered separately from the seed itself, because `enter()` replaces a
        # 0 with a real seed -- reading `self.seed <= 0` afterwards would then mean "pinned", and
        # pressing R would pour the SAME sheet again instead of a new one.
        self.seed = int(_number(self.config.get("seed"), 0.0, 0.0, None))
        self._seed_pinned = self.seed > 0

        # -- the pen and the pour (live in phase 2)
        self.pen_scale = _number(self.config.get("pen_scale"), 1.0, 0.4, 2.5)
        self.tremor = _number(self.config.get("tremor"), 0.55, 0.0, 3.0)
        self.land_coverage = _number(self.config.get("land_coverage"), 0.55, 0.1, 0.95)
        self.grain_size_cells = _number(self.config.get("grain_size_cells"), 5.0, 2.0, 14.0)

        # -- the sea (live in phase 3)
        style = str(self.config.get("water_style", "hash") or "hash").strip().lower()
        self.water_style = style if style in WATER_STYLES else "hash"
        self.water_rings = int(_number(self.config.get("water_rings"), 3, 0, 6))
        self.lake_count = int(_number(self.config.get("lake_count"), 3, 0, 12))

        # -- runtime
        self.manager = None
        self.sheet: Sheet | None = None
        self.reveal = Reveal()
        self.land = None                 # the Pour this sheet's coast was traced from
        self.masses: list = []           # its outlines, biggest first
        self._since_step = 0.0
        self._size = (0, 0)

    # ── life cycle ──────────────────────────────────────────────────────────

    def enter(self, manager):
        self.manager = manager
        self._size = (manager.width, manager.height)
        if not self._seed_pinned:
            self.seed = random.randrange(1, 2 ** 31 - 1)
        print(f"[InkMap] sheet seed={self.seed} "
              f"{self._size[0]}x{self._size[1]} supersample={self.supersample}x")
        self._new_sheet()

    def exit(self):
        if self.sheet is not None:
            self.sheet.release()
        self.sheet = None
        self.manager = None

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in _REDRAW_KEYS:
            # A fresh page. With no seed pinned the new sheet is a different sheet; with a seed
            # pinned it is the same sheet drawn again, which is what a pinned seed is for.
            if not self._seed_pinned:
                self.seed = random.randrange(1, 2 ** 31 - 1)
            print(f"[InkMap] new sheet seed={self.seed}")
            self._new_sheet()

    def update(self, dt: float):
        if self.sheet is None or dt <= 0:
            return
        # The drawing runs at reveal_fps, not at the controller's frame rate: a hand-drawn sheet
        # looks no better at 60 fps, and this leaves the frame loop to the rest of the app.
        self._since_step += dt
        period = 1.0 / self.reveal_fps
        if self._since_step < period:
            return
        step, self._since_step = self._since_step, 0.0
        self._draw_step(step)

    def render(self, screen):
        sheet = self.sheet
        if sheet is None:
            screen.fill(self.paper_tone)
            return
        sheet.flush()                       # only the rect whose ink changed
        screen.blit(sheet.canvas, (0, 0))

    # ── internals ───────────────────────────────────────────────────────────

    @property
    def draw_seconds(self) -> float:
        return max(0.0, self.draw_minutes) * 60.0

    def _new_sheet(self):
        """Pour a new page, trace its coast, and hand the pen the strokes to draw."""
        if self.sheet is not None:
            self.sheet.release()
        self.sheet = Sheet(
            self._size[0], self._size[1],
            paper_tone=self.paper_tone, ink_rgb=self.ink_rgb,
            paper_age=self.paper_age, vignette=self.vignette,
            supersample=self.supersample, seed=self.seed,
        )
        self.sheet.build_paper()
        self.sheet.ensure_ink()
        self.reveal.set_plan([])
        self._pour_and_plan()
        self._since_step = 0.0

    # ── the pour, the trace, the plan ───────────────────────────────────────

    @property
    def ink_px_per_mm(self) -> float:
        """
        Pixels per millimetre ON THE INK LAYER.

        The nibs and the grain of rice are physical sizes, so both scale with the sheet: the same
        drawing on a bigger screen gets proportionally heavier lines and bigger grain rather than
        just more of them.
        """
        return min(self.sheet.ink_size) / inkdraw.REFERENCE_SHEET_MM

    def _pour_and_plan(self):
        """Pour the rice, trace what it covers, and queue the coastline as pen strokes."""
        sheet = self.sheet
        if sheet is None:
            return
        started = time.perf_counter()
        rng = random.Random(self.seed)
        self.land = inkland.pour_land(
            rng, sheet.ink_size[0], sheet.ink_size[1], self.ink_px_per_mm,
            coverage=self.land_coverage, grain_cells=self.grain_size_cells,
            clumps=POUR_CLUMPS)
        self.masses = self.land.loops(min_area_cells=ISLAND_MIN_CELLS)
        coast = self._coast_plan(self.masses)
        sea = self._sea_plan()
        self.reveal.set_plan(coast + sea)
        # The pass order is the tutorial's, and it is the plan's whole reason for being a list: the
        # coast first, then the sea. Recorded alongside the plan so a test can assert the ORDER rather
        # than infer it, and so the later phases have one place to add their own pass names.
        self.pass_kinds = ['coast'] * len(coast) + ['sea'] * len(sea)
        self.coast_strokes = len(coast)
        self.sea_strokes = len(sea)
        print(f"[InkMap] poured {self.land.grains} grains in {self.land.attempts} attempt(s)"
              f" -> land {self.land.coverage * 100:.1f}% (asked {self.land_coverage * 100:.0f}%),"
              f" {self.land.traced_loops} outlines traced -> {len(self.masses)} land masses,"
              f" {len(coast)} coast + {len(sea)} water/lake = {self.reveal.total} strokes queued"
              f" ({self.water_style}, {self.water_rings} rings, {self.lake_count} lakes)"
              f" ({(time.perf_counter() - started) * 1000:.0f} ms)")

    def _coast_plan(self, masses) -> list:
        """
        The coast, biggest mass first, drawn the way the tutorial draws it: one continuous heavy
        line round each land mass with the `05` nib, cut into short runs so the reveal can pace it.

        ONE `Hand` for the whole plan. Its wander is an AR(1) walk, so a fresh Hand per run would
        restart the drift at every join and the outline would develop a kink there; sharing it means
        the line wanders continuously from one run to the next, which is what a hand does.
        """
        sheet = self.sheet
        if sheet is None:
            return []
        width = inkdraw.pen_widths(min(sheet.ink_size), self.pen_scale)["05"]
        hand = inkdraw.Hand(seed=self.seed, tremor=self.tremor, px_per_mm=self.ink_px_per_mm)
        colour = sheet.ink_colour()
        plan = []
        for points, _closed, _area in masses:
            runs = inkland.split_run(inkland.resample(points, COAST_RESAMPLE_INK_PX),
                                     COAST_RUN_INK_PX)
            last = len(runs) - 1
            for index, run in enumerate(runs):
                # The nib lands at the start of an outline and lifts at the end. Every run in
                # between keeps its full weight, or the whole edge would come out beaded.
                plan.append(_stroke_item(run, width, hand, colour,
                                         taper=(index == 0 or index == last)))
        return plan

    def _sea_plan(self) -> list:
        """
        The sea, after the coast and before anything inland: rings parallel to the coast with the
        video's four units hung off them, then the lakes.

        Its own `Hand`, seeded off the sheet's seed, so the sea's wander is reproducible and does not
        depend on how many strokes the coast happened to need.
        """
        sheet = self.sheet
        if sheet is None or self.land is None:
            return []
        pens = inkdraw.pen_widths(min(sheet.ink_size), self.pen_scale)
        hand = inkdraw.Hand(seed=self.seed ^ 0x5EA, tremor=self.tremor,
                            px_per_mm=self.ink_px_per_mm)
        colour = sheet.ink_colour()
        items = inkwater.coast_water(
            self.masses, self.land, pens=pens, hand=hand, style=self.water_style,
            rings=self.water_rings, px_per_mm=self.ink_px_per_mm)
        items.extend(inkwater.lake_items(
            self.land, random.Random(self.seed ^ 0x1A4E), self.lake_count,
            pens=pens, hand=hand, style=self.water_style, px_per_mm=self.ink_px_per_mm))
        return [self._water_item(item, hand, pens, colour) for item in items]

    @staticmethod
    def _water_item(item, hand, pens, colour):
        """A plan item for one arc of sea: the line, its marks, and the dirty rects they touched."""
        def draw(sheet):
            for rect in item.draw(sheet.ink, hand, pens, colour):
                sheet.mark_dirty_ink(rect)
        return draw

    def _draw_step(self, dt: float):
        self.reveal.advance(dt, self.draw_seconds, self._draw_one)

    def _draw_one(self, item):
        """Draw one planned stroke, and record where on the sheet it landed."""
        item(self.sheet)

    def status(self) -> dict:
        """What the mode is doing, for the log and for a test to assert on."""
        reveal = self.reveal
        return {
            "seed": self.seed,
            "planned": reveal.total,
            "drawn": reveal.index,
            "progress": round(reveal.progress, 4),
            "finished": reveal.done,
            "composites": self.sheet.composites if self.sheet is not None else 0,
            "masses": len(self.masses),
            "land_coverage": round(self.land.coverage, 4) if self.land is not None else None,
            "grains": self.land.grains if self.land is not None else 0,
            "water_style": self.water_style,
            "water_rings": self.water_rings,
            "lakes": self.lake_count,
            "coast_strokes": getattr(self, "coast_strokes", 0),
            "sea_strokes": getattr(self, "sea_strokes", 0),
            "passes": list(dict.fromkeys(getattr(self, "pass_kinds", ()))),
        }


def _stroke_item(points, width, hand, colour, taper):
    """One plan item: a run of the outline, drawn when the reveal cursor reaches it."""
    def draw(sheet):
        rect = inkdraw.stroke(sheet.ink, points, width, hand, taper=taper, colour=colour)
        if rect is not None:
            sheet.mark_dirty_ink(rect)
    return draw


def _number(value, fallback: float, low=None, high=None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(fallback)
    if low is not None:
        result = max(low, result)
    if high is not None:
        result = min(high, result)
    return result
