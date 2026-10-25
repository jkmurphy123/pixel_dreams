# core/inksheet.py
"""
The sheet: the parchment, the supersampled ink layer, and the hand that reveals it.

Phase 1 of the ink-map mode (`designs/INK_FANTASY_MAP_DESIGN.md` §4.2). Three things live here
and nothing else does:

  * `Sheet.build_paper()` — the aged parchment, built once. Every colour in it is DERIVED from
    the configured paper tone, so changing `paper_tone` changes the whole sheet rather than
    leaving blotches and fibre behind in the old colour.
  * the **ink layer** — a supersampled transparent surface. Strokes are drawn onto it at
    `supersample` x the screen and scaled down, which is the only way to anti-alias a pen
    stroke: `pygame.draw.aaline` is 1 px wide, and this pygame's `gfxdraw` has no `aaline` at
    all. Scaling the WHOLE layer every frame costs 46-58 ms (measured, §3), so only the rect
    that changed is scaled and blitted — 0.09 ms at 64x64, 0.39 ms at 256x256.
  * `Reveal` — a cursor over an ordered stroke plan, so "draw this over five minutes" is a
    rate rather than a performance problem.

Nothing here knows what a coastline is, and that is deliberate: the plan is a list of callables,
each taking the Sheet, and this module only decides how fast a hand draws them. The plan itself
is built by `core/inkplan.py` in a later phase.
"""

from __future__ import annotations

import random

import pygame


def _value_noise(rng, w, h, base=4, octaves=3, gain=0.5):
    """
    Layered value noise in 0..1, on a small grid (this runs at ~50x90 for a full sheet).

    Smoothly interpolated lattice noise, so the result is a cloudy field with no repeated shape
    and no centre. That is the property a paper texture needs: any stamped mark, however soft,
    is still a mark.
    """
    field = [0.0] * (w * h)
    amplitude, cells, total = 1.0, float(max(1, base)), 0.0
    for _ in range(octaves):
        gw = max(2, int(w / cells) + 2)
        gh = max(2, int(h / cells) + 2)
        lattice = [rng.random() for _ in range(gw * gh)]
        inv = 1.0 / cells
        for y in range(h):
            fy = y * inv
            y0 = int(fy)
            ty = fy - y0
            ty = ty * ty * (3.0 - 2.0 * ty)
            r0, r1, row = y0 * gw, (y0 + 1) * gw, y * w
            for x in range(w):
                fx = x * inv
                x0 = int(fx)
                tx = fx - x0
                tx = tx * tx * (3.0 - 2.0 * tx)
                top = lattice[r0 + x0] * (1.0 - tx) + lattice[r0 + x0 + 1] * tx
                bottom = lattice[r1 + x0] * (1.0 - tx) + lattice[r1 + x0 + 1] * tx
                field[row + x] += amplitude * (top * (1.0 - ty) + bottom * ty)
        total += amplitude
        amplitude *= gain
        cells = max(2.0, cells / 2.0)
    return [v / total for v in field]


def _screen_formatted(surface: pygame.Surface) -> pygame.Surface:
    """
    Convert to the display's pixel format when there IS a display.

    `convert()` raises without a video mode, and the tests (and the design-time probes) run under
    the dummy driver through a code path that may not have set one. Converting is the difference
    between a blit that copies bytes and one that reformats every pixel, so it is worth the guard.
    """
    try:
        if pygame.display.get_surface() is not None:
            if surface.get_flags() & pygame.SRCALPHA:
                return surface.convert_alpha()
            return surface.convert()
    except pygame.error:
        pass
    return surface


class Reveal:
    """
    A cursor over an ordered stroke plan.

    The plan is opaque on purpose: every item is a callable taking the Sheet, so the sheet can
    pace a coastline, a stipple field and a single dot with the same cursor, and does not need to
    know which is which. `advance()` is the whole model — items per second, carried across frames
    so a slow frame does not lose its share of the drawing.
    """

    def __init__(self, plan=None):
        self.plan: list = []
        self.index = 0
        self._carry = 0.0
        self.set_plan(plan or ())

    # ---------------------------------------------------------------- state

    @property
    def total(self) -> int:
        return len(self.plan)

    @property
    def done(self) -> bool:
        return self.index >= len(self.plan)

    @property
    def progress(self) -> float:
        """0.0 before the first stroke, 1.0 when the sheet is finished."""
        return 1.0 if not self.plan else self.index / len(self.plan)

    def set_plan(self, plan) -> None:
        """Start a fresh sheet: a new plan, and the pen back at its beginning."""
        self.plan = list(plan)
        self.index = 0
        self._carry = 0.0

    # ---------------------------------------------------------------- drawing

    def advance(self, dt: float, seconds_total: float, draw_one) -> int:
        """
        Draw this frame's share of the sheet. Returns how many items were drawn.

        `seconds_total <= 0` means "all at once" (the config's draw_minutes = 0), which is also
        what a frame that arrives long after the sheet should have been finished gets.
        """
        if self.done or dt <= 0:
            return 0
        if seconds_total <= 0:
            drawn = 0
            while not self.done:
                draw_one(self.plan[self.index])
                self.index += 1
                drawn += 1
            return drawn

        self._carry += dt * (len(self.plan) / float(seconds_total))
        count = int(self._carry)
        if count <= 0:
            return 0
        self._carry -= count
        count = min(count, len(self.plan) - self.index)
        for _ in range(count):
            draw_one(self.plan[self.index])
            self.index += 1
        return count


class Sheet:
    """
    One sheet of paper and the ink being drawn on it, at a given screen size.

    Sizes are all derived from the screen, and the paper is built at 1x while the ink layer is
    built at `supersample` x, so the mode works in any orientation without new constants.
    """

    def __init__(self, width: int, height: int, *, paper_tone=(232, 217, 184),
                 ink_rgb=(43, 33, 26), paper_age: float = 1.0, vignette: float = 1.0,
                 supersample: int = 2, seed: int = 1):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.paper_tone = tuple(int(c) for c in paper_tone[:3])
        self.ink_rgb = tuple(int(c) for c in ink_rgb[:3])
        self.paper_age = max(0.0, float(paper_age))
        self.vignette = max(0.0, float(vignette))
        self.supersample = max(1, min(3, int(supersample)))
        self.seed = int(seed)
        self.rng = random.Random(self.seed)

        self.paper: pygame.Surface | None = None
        self.canvas: pygame.Surface | None = None      # paper + the flushed ink
        self.ink: pygame.Surface | None = None         # supersampled strokes, transparent
        self._dirty: pygame.Rect | None = None
        #: How many times ink has actually been composited onto the canvas. Public so a test can
        #: prove the idle guard (a finished sheet stops doing work) instead of assuming it.
        self.composites = 0

        #: Stipple blobs and other per-radius sprites belong to the phases that draw them, but a
        #: cache dict lives here so a later phase does not have to add state to this class again.
        self.sprites: dict = {}

    # ---------------------------------------------------------------- geometry

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)

    @property
    def ink_size(self) -> tuple:
        return self.width * self.supersample, self.height * self.supersample

    def to_ink(self, point) -> tuple:
        """Screen coordinates -> ink-layer coordinates."""
        return point[0] * self.supersample, point[1] * self.supersample

    def to_screen(self, point) -> tuple:
        return point[0] / self.supersample, point[1] / self.supersample

    def ink_rect(self, rect) -> pygame.Rect:
        """A screen-space pygame.Rect in ink-layer space."""
        s = self.supersample
        return pygame.Rect(int(rect[0] * s), int(rect[1] * s), int(rect[2] * s), int(rect[3] * s))

    # ---------------------------------------------------------------- tones

    def tone(self, delta: float) -> tuple:
        """
        A lighter (delta > 0) or darker (delta < 0) variant of the paper tone.

        Every texture colour on the sheet comes through here. A hardcoded blotch colour would both
        ignore `paper_tone` and show up in the parameter audit as a knob nobody meant to expose.
        """
        r, g, b = self.paper_tone
        if delta >= 0:
            return tuple(min(255, int(c + (255 - c) * delta)) for c in (r, g, b))
        return tuple(max(0, int(c * (1.0 + delta))) for c in (r, g, b))

    # ---------------------------------------------------------------- the paper

    def build_paper(self) -> pygame.Surface:
        """
        The aged parchment: base tone, uneven blotching, fibre, and a vignette.

        Both texture layers are built on a transparent surface and BLITTED once, because
        `pygame.draw` with an RGBA colour REPLACES the destination pixel rather than blending
        into it -- drawing a soft layer straight onto the paper produces opaque bands instead of
        a wash. Each layer was also measured, not guessed: the blotching is rendered at about a
        twelfth of the size and scaled up, which is what makes it soft mottling rather than a
        scatter of hard discs, and it is the only reason a low alpha is visible at all (a 4/255
        disc composited once moves a pixel by one level, which no one can see).
        """
        w, h = self.width, self.height
        short = self.short_side
        rng = self.rng
        paper = pygame.Surface((w, h))
        paper.fill(self.paper_tone)

        age = self.paper_age
        if age > 0:
            # 1. uneven ageing: a low-frequency NOISE FIELD, not stamped discs.
            #    Measured twice before landing here: a stamped disc is visible whatever its alpha
            #    or softness, because it has a centre -- at a low alpha the sheet looks flat, and
            #    at a high alpha the discs' silhouettes become a field of bubbles. A noise field
            #    has no preferred centre, which is what makes it read as paper rather than dots.
            lw, lh = max(48, w // 14), max(48, h // 14)
            field = _value_noise(rng, lw, lh, base=max(3, min(lw, lh) // 18), octaves=3)
            mottle = pygame.Surface((lw, lh))
            darker, lighter = self.tone(-0.17), self.tone(0.07)
            for y in range(lh):
                row = y * lw
                for x in range(lw):
                    v = field[row + x]
                    mottle.set_at((x, y), (
                        int(lighter[0] + (darker[0] - lighter[0]) * v),
                        int(lighter[1] + (darker[1] - lighter[1]) * v),
                        int(lighter[2] + (darker[2] - lighter[2]) * v)))
            mottle.set_alpha(max(0, min(255, int(96 * age))))
            paper.blit(pygame.transform.smoothscale(mottle, (w, h)), (0, 0))

            # 2. fibre: fine dark strokes and single darker pixels, so a magnified sheet still has
            #    texture rather than a flat wash. Also area-scaled, for the same reason.
            dark = self.tone(-0.16)
            darker = self.tone(-0.10)
            for _ in range(max(40, int(w * h * 0.0010 * age))):
                x, y = rng.uniform(0, w), rng.uniform(0, h)
                if rng.random() < 0.5:
                    pygame.draw.line(paper, dark, (x, y),
                                     (x + rng.gauss(0, short * 0.003),
                                      y + rng.gauss(0, short * 0.0009)), 1)
                else:
                    paper.set_at((int(x), int(y)), darker)

        # 3. vignette: the edge of an old page is darker than its middle. Non-overlapping 1 px
        #    rings drawn from the innermost (weakest) outward, so each pixel receives one alpha.
        if self.vignette > 0:
            shade = self.tone(-0.48)
            veil = pygame.Surface((w, h), pygame.SRCALPHA)
            reach = max(4, int(short * 0.10))
            for i in range(reach, 0, -1):
                f = i / reach
                alpha = int(52 * self.vignette * (1.0 - f) ** 2)
                if alpha <= 0:
                    continue
                pygame.draw.rect(veil, shade + (min(255, alpha),),
                                 (i, i, w - 2 * i, h - 2 * i), 1)
            paper.blit(veil, (0, 0))

        ready = _screen_formatted(paper)
        self.paper = ready
        self.canvas = ready.copy()
        return ready

    # ---------------------------------------------------------------- the ink layer

    def ensure_ink(self) -> pygame.Surface:
        """Create the supersampled transparent layer the strokes are drawn onto."""
        if self.ink is None:
            ink = pygame.Surface(self.ink_size, pygame.SRCALPHA)
            ink.fill((0, 0, 0, 0))
            self.ink = _screen_formatted(ink)
        return self.ink

    def ink_colour(self, alpha: int = 255) -> tuple:
        return self.ink_rgb + (max(0, min(255, int(alpha))),)

    def mark_dirty(self, rect) -> None:
        """Record the screen-space area whose ink changed, so only that is scaled and composited."""
        rect = pygame.Rect(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        rect.inflate_ip(2, 2)
        rect = rect.clip(pygame.Rect(0, 0, self.width, self.height))
        if rect.w <= 0 or rect.h <= 0:
            return
        self._dirty = rect if self._dirty is None else self._dirty.union(rect)

    def pending_dirty(self) -> pygame.Rect | None:
        return self._dirty

    def mark_dirty_ink(self, rect) -> None:
        """Record a rect given in INK units (a stroke's own bounds) as screen-space dirty area."""
        s = self.supersample
        self.mark_dirty((rect[0] / s, rect[1] / s, rect[2] / s, rect[3] / s))

    def flush(self) -> None:
        """Composite whatever ink changed onto the canvas. Cheap: the dirty rect, not the frame."""
        if self._dirty is not None and self.ink is not None and self.canvas is not None:
            s = self.supersample
            rect = pygame.Rect(0, 0, self.width, self.height).clip(self._dirty)
            if rect.w > 0 and rect.h > 0:
                source = self.ink.subsurface(self.ink_rect(rect))
                if s == 1:
                    self.canvas.blit(source, rect.topleft)
                else:
                    small = pygame.transform.smoothscale(source, (rect.w, rect.h))
                    self.canvas.blit(small, rect.topleft)
                # Counted so "the finished sheet does no work" is something a caller can ASSERT
                # rather than believe: with nothing dirty this number stops rising.
                self.composites += 1
        self._dirty = None

    def clear_ink(self) -> None:
        """Wipe the ink and start the canvas again from a clean sheet of paper."""
        if self.ink is not None:
            self.ink.fill((0, 0, 0, 0))
        if self.paper is not None:
            self.canvas = self.paper.copy()
        self._dirty = None

    def release(self) -> None:
        """Drop the surfaces so the next mode switch can reclaim the memory (exit())."""
        self.paper = None
        self.canvas = None
        self.ink = None
        self._dirty = None
        self.sprites.clear()
