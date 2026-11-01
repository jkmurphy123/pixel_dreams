"""The invented script, the built-in lore and the wall's slab model.

The glyphs are deliberately made of line segments: they read as etching, not
as corrupted Latin.  Each slab keeps its rows in local 0..1 space so the same
data can be rendered into a cached face surface at whatever size the screen
gives us.

Nothing here imports pygame.  The renderer owns the surfaces; this module owns
the geometry and the deterministic random choices.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

#: A small alphabet of invented strokes, in a unit cell.  Kept stable: the
#: seed reproduces a scene, so this table must not be reshuffled casually.
GLYPHS = (
    (((0.5, 0.12), (0.5, 0.88)),),
    (((0.18, 0.5), (0.82, 0.5)),),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.3), (0.8, 0.3))),
    (((0.25, 0.12), (0.25, 0.88)), ((0.25, 0.5), (0.8, 0.5))),
    (((0.2, 0.18), (0.8, 0.82)), ((0.2, 0.82), (0.8, 0.18))),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.3, 0.12), (0.7, 0.12))),
    (((0.2, 0.15), (0.2, 0.85)), ((0.2, 0.85), (0.8, 0.85))),
    (((0.2, 0.15), (0.8, 0.15)), ((0.2, 0.15), (0.5, 0.5)),
     ((0.8, 0.15), (0.5, 0.5)), ((0.5, 0.5), (0.5, 0.88))),
    (((0.25, 0.25), (0.75, 0.25)), ((0.25, 0.5), (0.75, 0.5)),
     ((0.25, 0.75), (0.75, 0.75))),
    (((0.5, 0.1), (0.5, 0.55)), ((0.5, 0.55), (0.25, 0.9)),
     ((0.5, 0.55), (0.75, 0.9))),
    (((0.2, 0.2), (0.2, 0.8)), ((0.2, 0.2), (0.8, 0.2)),
     ((0.8, 0.2), (0.8, 0.8))),
    (((0.2, 0.5), (0.8, 0.5)), ((0.5, 0.2), (0.5, 0.8)),
     ((0.2, 0.2), (0.8, 0.8))),
    (((0.3, 0.15), (0.7, 0.15)), ((0.3, 0.4), (0.7, 0.4)),
     ((0.5, 0.4), (0.5, 0.88))),
    (((0.2, 0.15), (0.2, 0.85)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.8, 0.2), (0.8, 0.8))),
    (((0.5, 0.15), (0.5, 0.85)), ((0.2, 0.7), (0.8, 0.3))),
    (((0.25, 0.2), (0.75, 0.5)), ((0.75, 0.5), (0.25, 0.8))),
    (((0.2, 0.2), (0.8, 0.2)), ((0.2, 0.5), (0.8, 0.5)),
     ((0.2, 0.8), (0.8, 0.8))),
    (((0.35, 0.15), (0.35, 0.85)), ((0.65, 0.15), (0.65, 0.85)),
     ((0.2, 0.5), (0.8, 0.5))),
    (((0.5, 0.12), (0.5, 0.88)), ((0.2, 0.8), (0.8, 0.8))),
    (((0.2, 0.3), (0.8, 0.3)), ((0.2, 0.3), (0.2, 0.8)),
     ((0.2, 0.8), (0.5, 0.55))),
    (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8)),
     ((0.2, 0.5), (0.8, 0.5))),
    (((0.5, 0.15), (0.5, 0.5)), ((0.2, 0.85), (0.8, 0.85))),
    (((0.25, 0.5), (0.75, 0.5)), ((0.5, 0.15), (0.5, 0.85)),
     ((0.25, 0.15), (0.25, 0.85))),
    (((0.15, 0.35), (0.85, 0.35)), ((0.15, 0.65), (0.85, 0.65)),
     ((0.5, 0.15), (0.5, 0.85))),
    (((0.2, 0.2), (0.5, 0.5)), ((0.5, 0.5), (0.8, 0.2)),
     ((0.5, 0.5), (0.5, 0.85))),
    (((0.5, 0.1), (0.5, 0.9)), ((0.2, 0.1), (0.8, 0.1)),
     ((0.2, 0.9), (0.8, 0.9))),
    (((0.2, 0.5), (0.8, 0.5)), ((0.65, 0.2), (0.8, 0.5)),
     ((0.65, 0.8), (0.8, 0.5))),
    (((0.3, 0.2), (0.7, 0.2)), ((0.3, 0.2), (0.3, 0.55)),
     ((0.7, 0.2), (0.7, 0.55)), ((0.3, 0.55), (0.7, 0.9))),
)

#: Original one-line entries, used when `text_file` is unset, missing or
#: malformed.  The first line is the one in the reviewed still.  No quotation
#: from anywhere else; these are written for this mode.
LORE = (
    "we kept the light on for whoever came next",
    "the sea remembered us for a thousand years",
    "all our songs fit into three lines",
    "we made the vault and then we made the dark",
    "if you are reading this, the door was open",
    "do not look for us in the instruments",
    "the garden closed its eyes at noon",
    "we counted the stars and lost the argument",
    "tell the next ones the water was clean",
    "this is the last entry and it is enough",
)


def stable_seed(seed: int, salt: int) -> int:
    """A stable integer mix; never Python's salted hash."""
    return (int(seed) * 7349 + int(salt) * 911) & 0x7FFFFFFF


@dataclass
class Slab:
    """One frontal panel of the wall.

    `width` and the horizontal extents are in screen pixels.  A side slab is
    deliberately wider than the part the camera can see; the renderer blits it
    partly off-screen so the wall continues past the frame.
    """

    id: int
    x: float
    width: int
    top: float
    bottom: float
    brightness: float
    text_density: float
    focus: bool = False
    label: str = ""

    rows: list = field(default_factory=list)
    pad_x: float = 0.0
    pad_y: float = 0.0
    pad_bottom: float = 0.0
    cell: float = 12.0
    pitch: float = 13.0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return self.x + self.width * 0.5

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) * 0.5


def build_rows(slab: Slab, seed: int, cell: float, pitch: float,
               pad_x: float, pad_y: float, pad_bottom: float) -> None:
    """Lay out the etched rows in the slab's local space.

    The active slab is dense; the peripheral slabs are allowed to weather away.
    Quality does not change these rows (the cached face can draw a stride over
    them), so a quality change never moves a glyph.
    """
    slab.pad_x = float(pad_x)
    slab.pad_y = float(pad_y)
    slab.pad_bottom = float(pad_bottom)
    slab.cell = float(cell)
    slab.pitch = float(pitch)
    slab.rows = []

    inner_w = slab.width - 2.0 * pad_x
    inner_h = slab.height - pad_y - pad_bottom
    if inner_w <= 8 or inner_h <= 8 or slab.text_density <= 0.0:
        return

    cells = max(3, int(inner_w / max(1.0, cell)))
    count = max(2, int(inner_h / max(1.0, pitch)))
    rng = random.Random(stable_seed(seed, slab.id))
    focus = slab.focus

    row = 0
    while row < count:
        # Paragraph breaks give the inscription a rhythm; the monument stays
        # denser than the side panels.
        if row and rng.random() < (0.05 if focus else 0.20):
            row += rng.choice((1, 1, 2))
            continue
        if rng.random() > slab.text_density:
            row += 1
            continue
        v = (row + 0.5) / count
        indent = rng.choice((0, 0, 0, 1, 1, 2, 3, 4, 5))
        if focus:
            trim = rng.choice((0, 0, 1, 1, 2, 3, 6))
        else:
            trim = rng.choice((0, 1, 2, 4, 7, 10, 14))
        length = cells - indent - trim
        if length < 3:
            row += 1
            continue
        glyphs = [rng.randrange(len(GLYPHS)) for _ in range(length)]
        if focus:
            wear = rng.choice((1.0, 1.0, 1.0, 1.0, 1.0, 0.92))
        else:
            wear = rng.choice((1.0, 0.85, 0.65, 0.45, 0.28))
        slab.rows.append((v, indent, cells, glyphs, wear))
        row += 2 if rng.random() < (0.03 if focus else 0.12) else 1
