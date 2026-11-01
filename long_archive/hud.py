"""The restrained console for The Long Archive.

Title, vault, entries, focus and the bar clock; one thin progress track and a
quiet camera line.  The lower-left 80x32 belongs to the controller and is never
drawn on.  `hud="off"` leaves the wall and the translation alone.
"""
from __future__ import annotations

import pygame

from .layout import Layout
from .palette import Palette, mix


class LongArchiveHUD:
    def __init__(self, cache, size, layout: Layout, palette: Palette, mode: str,
                 title: str, subtitle: str, entries: int = 1204,
                 focus_index: int = 4, slab_count: int = 9,
                 bar_period: float = 8.0, drift_speed: float = 2.0):
        self.cache = cache
        self.layout = layout
        self.palette = palette
        self.mode = mode if mode in ("full", "minimal", "off") else "full"
        self.sw, self.sh = int(size[0]), int(size[1])
        self.entries = max(0, int(entries))
        self.slab_count = max(1, int(slab_count))
        self.focus_index = max(1, min(self.slab_count, int(focus_index)))
        self.bar_period = max(0.0, float(bar_period))
        self.drift_speed = max(0.0, float(drift_speed))
        self.title = (title or "THE LONG ARCHIVE").upper()[:32]
        self.subtitle = (subtitle or "").upper()[:52]

        self.font_title = cache.get_font("dejavusansmono",
                                         layout.title_px, bold=True)
        self.font_body = cache.get_font("dejavusansmono", layout.body_px)
        self.font_small = cache.get_font("dejavusansmono", layout.small_px)
        self.margin = layout.margin
        self._title_surf = self.font_title.render(self.title, True,
                                                  palette.hud)
        self._subtitle_surf = self.font_small.render(self.subtitle, True,
                                                     palette.hud_dim)

    # ---------------------------------------------------------------- text

    @staticmethod
    def _text(screen, text, pos, color, font, align="left"):
        if not text:
            return pygame.Rect(pos[0], pos[1], 0, 0)
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if align == "right":
            rect.topright = (int(pos[0]), int(pos[1]))
        elif align == "center":
            rect.midtop = (int(pos[0]), int(pos[1]))
        else:
            rect.topleft = (int(pos[0]), int(pos[1]))
        screen.blit(surf, rect)
        return rect

    # --------------------------------------------------------------- parts

    def _corner_ticks(self, screen) -> None:
        m = self.margin
        arm = max(8, int(min(self.sw, self.sh) * 0.018))
        color = self.palette.hud_faint
        for x, y, dx, dy in ((m, m, 1, 1),
                             (self.sw - m - 1, m, -1, 1),
                             (self.sw - m - 1, self.sh - m - 1, -1, -1)):
            pygame.draw.line(screen, color, (x, y), (x + dx * arm, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y + dy * arm), 1)

    def _draw_title(self, screen) -> None:
        p = self.palette
        m = self.margin
        screen.blit(self._title_surf, (m, m))
        rule_y = m + self._title_surf.get_height() + 4
        pygame.draw.line(screen, p.hud_dim, (m, rule_y),
                         (m + max(90, int(self._title_surf.get_width() * 0.74)),
                          rule_y), 1)
        if self.mode == "full" and self.subtitle:
            screen.blit(self._subtitle_surf, (m, rule_y + 5))

    def _draw_telemetry(self, screen, stats: dict) -> None:
        p = self.palette
        m = self.margin
        focus = f"{self.focus_index:02d}"
        lines = (
            (f"ENTRIES {self.entries:,}", p.hud, self.font_body),
            (f"FOCUS SLAB {focus} / {self.slab_count:02d}", p.hud_dim,
             self.font_small),
            (f"LIGHT BAR {self.bar_period:04.1f} S", p.hud_faint,
             self.font_small),
        )
        y = m
        for text, color, font in lines:
            self._text(screen, text, (self.sw - m, y), color, font, "right")
            y += font.get_height() + 2

        track_w = max(72, min(170, int(self.sw * 0.10)))
        tx = self.sw - m - track_w
        ty = y + 3
        pygame.draw.line(screen, p.hud_faint, (tx, ty), (tx + track_w, ty), 1)
        frac = max(0.0, min(1.0, float(stats.get("bar_fraction", 0.0))))
        pygame.draw.line(screen, p.accent, (tx, ty),
                         (tx + int(track_w * frac), ty), 1)
        pygame.draw.line(screen, mix(p.accent_dim, p.accent, 0.5),
                         (tx + int(track_w * frac), ty - 2),
                         (tx + int(track_w * frac), ty + 2), 1)

    def _draw_footer(self, screen) -> None:
        p = self.palette
        m = self.margin
        fy = self.sh - m - self.font_small.get_height()
        if self.drift_speed > 0.05:
            camera = f"CAMERA +{self.drift_speed:.1f} PX/S"
        else:
            camera = "CAMERA HOLD"
        self._text(screen, camera, (self.sw - m, fy), p.hud_faint,
                   self.font_small, "right")
        if self.layout.portrait:
            self._text(screen, f"{self.slab_count:02d} SLABS // NO READER",
                       (self.sw - m, fy - self.font_small.get_height() - 2),
                       p.hud_faint, self.font_small, "right")

    # --------------------------------------------------------------- frame

    def draw(self, screen: pygame.Surface, stats: dict) -> None:
        if self.mode == "off":
            return
        self._corner_ticks(screen)
        self._draw_title(screen)
        self._draw_telemetry(screen, stats)
        if self.mode == "full":
            self._draw_footer(screen)

