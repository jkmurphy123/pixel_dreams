"""A restrained 2001-style console for Space Station V.

The HUD is thin type and a few rules, not a dashboard: the station is the
picture.  It keeps the lower-left corner clear for the controller's mode
number, and uses the baked dark bands from the renderer rather than drawing
its own panels, so the wireframe stays visible behind the type.
"""
from __future__ import annotations

import math

import pygame

from .palette import Palette, scale


class HUD:
    def __init__(self, cache, size: tuple[int, int], palette: Palette,
                 mode: str = "full", title: str = "SPACE STATION V",
                 subtitle: str = "EARTH ORBIT // DOCKING APPROACH"):
        self.cache = cache
        self.palette = palette
        self.mode = mode if mode in ("full", "minimal", "off") else "full"
        self.title = (title or "SPACE STATION V").upper()[:32]
        self.subtitle = (subtitle or "").upper()[:52]
        self.sw = self.sh = 0
        self.font_title = self.font_body = self.font_small = None
        self.resize(size)

    def resize(self, size: tuple[int, int]) -> None:
        self.sw, self.sh = max(1, int(size[0])), max(1, int(size[1]))
        unit = max(9, min(24, int(min(self.sw, self.sh) * 0.028)))
        self.font_small = self.cache.get_font("dejavusansmono",
                                              max(8, unit - 2), bold=False)
        self.font_body = self.cache.get_font("dejavusansmono", unit, bold=False)
        self.font_title = self.cache.get_font("dejavusansmono", unit + 4,
                                              bold=True)
        self.margin = max(12, int(min(self.sw, self.sh) * 0.036))

    # ---------------------------------------------------------------- text

    @staticmethod
    def _draw_text(screen, text: str, position, color, font,
                   align: str = "left"):
        if not text or font is None:
            return pygame.Rect(position[0], position[1], 0, 0)
        surface = font.render(text, True, color)
        rect = surface.get_rect()
        if align == "right":
            rect.topright = (int(position[0]), int(position[1]))
        elif align == "center":
            rect.midtop = (int(position[0]), int(position[1]))
        else:
            rect.topleft = (int(position[0]), int(position[1]))
        screen.blit(surface, rect)
        return rect

    def draw(self, screen: pygame.Surface, spin_deg: float,
             earth_spin_deg: float, stats: dict, time_s: float) -> None:
        if self.mode == "off":
            return
        p = self.palette
        m = self.margin
        sw, sh = self.sw, self.sh

        self._corner_ticks(screen, p, m)

        title_rect = self._draw_text(screen, self.title, (m, m), p.hud,
                                     self.font_title)
        rule_y = title_rect.bottom + max(3, self.font_body.get_height() // 5)
        pygame.draw.line(screen, p.hud_dim,
                         (m, rule_y), (m + max(80, title_rect.width * 0.72),
                                       rule_y), 1)

        if self.mode == "full" and self.subtitle and sh >= 240:
            self._draw_text(screen, self.subtitle, (m, rule_y + 4),
                            p.hud_dim, self.font_small)
            # A slow red HAL eye, deliberately small.
            eye = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(time_s * 1.4))
            ex = m + 2
            ey = rule_y + 4 + self.font_small.get_height() + 7
            pygame.draw.circle(screen, scale(p.beacon, 0.35 + 0.45 * eye),
                               (ex, ey), max(2, self.font_small.get_height() // 8))

        self._draw_telemetry(screen, p, spin_deg, stats, m, sw)

        if self.mode == "full":
            if sw >= 560 and sh >= 320:
                self._draw_attitude(screen, p, spin_deg, earth_spin_deg,
                                    m, sw, sh)
            if sw >= 560 and sh >= 300:
                self._draw_status(screen, p, m, sw, sh, time_s)

    # ---------------------------------------------------------------- parts

    def _corner_ticks(self, screen, p: Palette, m: int) -> None:
        arm = max(7, int(min(self.sw, self.sh) * 0.018))
        color = p.hud_faint
        for x, y, dx, dy in ((m, m, 1, 1),
                             (self.sw - m - 1, m, -1, 1),
                             (m, self.sh - m - 1, 1, -1),
                             (self.sw - m - 1, self.sh - m - 1, -1, -1)):
            pygame.draw.line(screen, color, (x, y), (x + dx * arm, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y + dy * arm), 1)

    def _draw_telemetry(self, screen, p: Palette, spin_deg: float,
                        stats: dict, m: int, sw: int) -> None:
        line_h = self.font_body.get_height() + 1
        rpm = float(stats.get("station_rpm", 0.0))
        lines = (
            f"ALT {stats.get('altitude_km', 402.0):04.0f} KM",
            f"VEL {stats.get('velocity_km_s', 7.71):04.2f} KM/S",
            f"PERIOD {stats.get('period_min', 92.4):05.1f} MIN",
            f"RING {rpm:04.2f} RPM",
        )
        count = len(lines) if self.mode == "full" else min(2, len(lines))
        for index, text in enumerate(lines[:count]):
            self._draw_text(screen, text, (sw - m, m + index * line_h),
                            p.hud if index < 2 else p.hud_dim,
                            self.font_body, "right")
        # Phase bars: station spin and Earth rotation as two thin tracks.
        bar_w = max(58, min(150, int(sw * 0.11)))
        bx = sw - m - bar_w
        by = m + count * line_h + 4
        for index, (fraction, color) in enumerate((
                ((spin_deg % 360.0) / 360.0, p.hull),
                ((stats.get("earth_rotation_deg", 0.0) % 360.0) / 360.0,
                 p.earth_land))):
            y = by + index * 5
            pygame.draw.line(screen, p.hud_faint, (bx, y), (bx + bar_w, y), 1)
            pygame.draw.line(screen, color, (bx, y),
                             (bx + int(bar_w * fraction), y), 1)

    def _draw_attitude(self, screen, p: Palette, spin_deg: float,
                       earth_spin_deg: float, m: int, sw: int, sh: int) -> None:
        radius = max(20, int(min(sw, sh) * 0.075))
        cx = sw - m - radius
        cy = sh - m - radius
        color = p.hud_dim
        pygame.draw.circle(screen, p.hud_faint, (cx, cy), radius, 1)
        pygame.draw.circle(screen, color, (cx, cy), max(3, radius // 4), 1)

        # Station rim ticks rotate with the habitat ring.
        spin = math.radians(spin_deg)
        for i in range(12):
            angle = spin + math.tau * i / 12
            ca, sa = math.cos(angle), math.sin(angle)
            inner = radius - max(4, radius // 6) if i % 3 else radius - max(6, radius // 3)
            pygame.draw.line(screen, p.hull if i % 3 == 0 else p.hud_faint,
                             (cx + ca * inner, cy + sa * inner),
                             (cx + ca * radius, cy + sa * radius), 1)
        # An Earth meridian inside the dial, rotating at the Earth's rate.
        angle = math.radians(earth_spin_deg)
        inner_r = max(3, radius // 4)
        ex = cx + math.cos(angle) * inner_r
        ey = cy + math.sin(angle) * inner_r
        pygame.draw.line(screen, p.earth_land, (cx, cy), (ex, ey), 1)
        pygame.draw.circle(screen, p.earth_land, (cx, cy), inner_r, 1)

        self._draw_text(screen, "ATTITUDE", (cx, cy - radius -
                                             self.font_small.get_height() - 3),
                        p.hud_dim, self.font_small, "center")

    def _draw_status(self, screen, p: Palette, m: int, sw: int, sh: int,
                     time_s: float) -> None:
        seconds = int(time_s)
        clock = f"T+ {seconds // 3600:02d}:{(seconds // 60) % 60:02d}:{seconds % 60:02d}"
        y = sh - m - self.font_body.get_height()
        self._draw_text(screen, clock, (sw // 2, y), p.hud_dim,
                        self.font_small, "center")
        status = "DOCKING CORRIDOR // CLEAR"
        rect = self._draw_text(screen, status,
                               (sw // 2, y - self.font_small.get_height() - 2),
                               p.good, self.font_small, "center")
        dot_x = rect.left - 10
        dot_y = rect.centery
        pygame.draw.circle(screen, p.good, (dot_x, dot_y), 2)
