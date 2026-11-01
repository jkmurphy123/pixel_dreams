"""Minimal vector HUD for Trench Run.

A tiny 5x7 stroke font keeps the HUD in the same visual language as the world.
The lower-left corner is deliberately left to the controller's mode-number
watermark.
"""
from __future__ import annotations

import math

import pygame


GLYPHS = {
    " ": [],
    "0": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]],
    "1": [[(2, 0), (2, 6)], [(1, 1), (2, 0)]],
    "2": [[(0, 0), (4, 0), (4, 3), (0, 3), (0, 6), (4, 6)]],
    "3": [[(0, 0), (4, 0), (4, 6), (0, 6)], [(1, 3), (4, 3)]],
    "4": [[(3, 6), (3, 0), (0, 3), (4, 3)]],
    "5": [[(4, 0), (0, 0), (0, 3), (4, 3), (4, 6), (0, 6)]],
    "6": [[(4, 0), (0, 0), (0, 6), (4, 6), (4, 3), (0, 3)]],
    "7": [[(0, 0), (4, 0), (4, 6)]],
    "8": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)], [(0, 3), (4, 3)]],
    "9": [[(4, 3), (0, 3), (0, 0), (4, 0), (4, 6), (0, 6)]],
    "A": [[(0, 6), (0, 2), (2, 0), (4, 2), (4, 6)], [(1, 3), (3, 3)]],
    "C": [[(4, 0), (0, 0), (0, 6), (4, 6)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "L": [[(0, 0), (0, 6), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]],
    "R": [[(0, 6), (0, 0), (4, 0), (4, 3), (0, 3)], [(2, 3), (4, 6)]],
    "S": [[(4, 0), (0, 0), (0, 3), (4, 3), (4, 6), (0, 6)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 6), (4, 6), (4, 0)]],
    "/": [[(4, 0), (0, 6)]],
    "-": [[(1, 3), (3, 3)]],
    "+": [[(2, 1), (2, 5)], [(0, 3), (4, 3)]],
}


class HUD:
    def __init__(self, palette, hud_mode: str = "minimal"):
        self.palette = palette
        self.mode = hud_mode if hud_mode in ("minimal", "off") else "minimal"
        self.last_scale = 2

    def _text(self, screen, text: str, x: int, y: int, scale: int,
              color) -> int:
        cursor = x
        for ch in text.upper():
            glyph = GLYPHS.get(ch, [])
            for stroke in glyph:
                pts = [(cursor + int(px * scale), y + int(py * scale))
                       for px, py in stroke]
                if len(pts) >= 2:
                    pygame.draw.lines(screen, color, False, pts, 1)
            cursor += 6 * scale
        return cursor

    def draw(self, screen, projector, ship, sector_index: int,
             action_level: int) -> None:
        if self.mode == "off":
            return
        sw, sh = screen.get_size()
        scale = 2 if min(sw, sh) >= 560 else 1
        self.last_scale = scale
        p = self.palette
        dim = tuple(max(0, int(c * 0.75)) for c in p.hud)

        label = f"TRENCH RUN // SECTOR {sector_index % 100:02d}"
        self._text(screen, label, 18, 16, scale, dim)

        # Ship-relative targeting brackets.
        sp = projector.project_point(ship.pose())
        if sp is not None:
            x, y = int(sp[0]), int(sp[1])
            r = 24 if min(sw, sh) >= 560 else 15
            arm = 8
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                cx, cy = x + sx * r, y + sy * r
                pygame.draw.line(screen, p.hud, (cx, cy),
                                 (cx - sx * arm, cy), 1)
                pygame.draw.line(screen, p.hud, (cx, cy),
                                 (cx, cy - sy * arm), 1)

        if sw >= 640:
            # Right-edge altitude ladder.  The ship's floor-to-rim range maps
            # to a short fixed ladder; no numeric clutter.
            top = int(sh * 0.30)
            bottom = int(sh * 0.70)
            lx = sw - 26
            pygame.draw.line(screen, dim, (lx, top), (lx, bottom), 1)
            for i in range(7):
                yy = top + i * (bottom - top) // 6
                pygame.draw.line(screen, dim, (lx - 5, yy), (lx, yy), 1)
            frac = max(0.0, min(1.0, (ship.y - 3.0) / 23.0))
            cy = bottom - int(frac * (bottom - top))
            pygame.draw.line(screen, p.hud, (lx - 8, cy), (lx + 2, cy), 2)
            self._text(screen, f"ALT {int(ship.y):02d}", lx - 78, top - 18,
                       scale, dim)

        # Small action-level annotation, deliberately away from lower-left.
        self._text(screen, f"ACT {action_level}", 18, 16 + 8 * scale + 8,
                   scale, dim)
