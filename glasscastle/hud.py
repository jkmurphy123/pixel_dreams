"""The restrained HUD for The Glass Castle.

Title and telemetry only: a serif title with a thin rule, one line of invented
aurora telemetry in the top-right, and the camera speed bottom-right.  `full`
adds an optional subtitle under the title and a second telemetry line; `off`
leaves the vista alone.  The lower-left 80x32 belongs to the controller, so the
HUD draws three corner ticks, never four.
"""
from __future__ import annotations

import pygame

from .layout import SceneLayout
from .palette import Palette, mix

TELEMETRY = "AURORA 07 // -12 C"


class GlassCastleHUD:
    def __init__(self, cache, layout: SceneLayout, palette: Palette,
                 mode: str, title: str, subtitle: str,
                 camera_drift: float = 0.5, snow_layers: int = 2):
        self.cache = cache
        self.layout = layout
        self.palette = palette
        self.mode = mode if mode in ("full", "minimal", "off") else "minimal"
        self.title = (title or "THE GLASS CASTLE").upper()[:32]
        self.subtitle = (subtitle or "").upper()[:56]
        self.camera_drift = max(0.0, float(camera_drift))
        self.snow_layers = max(0, int(snow_layers))

        self.font_title = cache.get_font("dejavuserif", layout.title_px)
        self.font_body = cache.get_font("dejavusansmono", layout.telemetry_px)
        self.font_small = cache.get_font("dejavusansmono", layout.small_px)
        self.margin = layout.margin
        self._title = self._tracked(self.title, self.font_title,
                                    palette.hud, layout.title_track)
        self._subtitle = (self.font_small.render(self.subtitle, True,
                                                 palette.hud_dim)
                          if self.subtitle else None)
        self._telemetry = self.font_body.render(TELEMETRY, True,
                                                palette.hud_dim)
        self._second = (self.font_small.render(
            self._second_text(), True, palette.hud_faint)
            if self.mode == "full" else None)
        self._footer = self.font_small.render(self._footer_text(), True,
                                              palette.hud_faint)
        self._rule_w = max(90, int(self._title.get_width() * 0.78))

    def _second_text(self) -> str:
        if self.snow_layers <= 0:
            return "WIND CALM // SNOW OFF"
        return f"WIND CALM // {self.snow_layers} SNOW LAYERS"

    def _footer_text(self) -> str:
        if self.camera_drift <= 0.05:
            return "CAMERA HOLD"
        return f"CAMERA +{self.camera_drift:.1f} PX/S"

    @staticmethod
    def _tracked(text: str, font, color, tracking: float) -> pygame.Surface:
        widths = [font.size(ch)[0] for ch in text]
        total = sum(widths) + int(round(tracking)) * max(0, len(text) - 1)
        surf = pygame.Surface((max(1, total), font.get_height()),
                              pygame.SRCALPHA)
        x = 0
        for ch, w in zip(text, widths):
            surf.blit(font.render(ch, True, color), (x, 0))
            x += w + tracking
        return surf

    @staticmethod
    def _text(screen, surface, pos, align="left"):
        rect = surface.get_rect()
        if align == "right":
            rect.topright = (int(pos[0]), int(pos[1]))
        else:
            rect.topleft = (int(pos[0]), int(pos[1]))
        screen.blit(surface, rect)
        return rect

    def _ticks(self, screen) -> None:
        m = self.margin
        arm = max(8, int(min(self.layout.width, self.layout.height) * 0.018))
        color = self.palette.hud_faint
        for x, y, dx, dy in ((m, m, 1, 1),
                             (self.layout.width - m - 1, m, -1, 1),
                             (self.layout.width - m - 1,
                              self.layout.height - m - 1, -1, -1)):
            pygame.draw.line(screen, color, (x, y), (x + dx * arm, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y + dy * arm), 1)

    def draw(self, screen: pygame.Surface) -> None:
        if self.mode == "off":
            return
        p = self.palette
        m = self.margin
        w, h = self.layout.width, self.layout.height
        self._ticks(screen)

        screen.blit(self._title, (m, m))
        rule_y = m + self._title.get_height() + 2
        pygame.draw.line(screen, p.accent_dim, (m, rule_y),
                         (m + self._rule_w, rule_y), 1)
        pygame.draw.line(screen, mix(p.accent, p.glow, 0.4),
                         (m, rule_y), (m + int(self._rule_w * 0.23),
                                       rule_y), 1)
        if self.mode == "full" and self._subtitle is not None:
            screen.blit(self._subtitle, (m, rule_y + 5))

        tr = self._text(screen, self._telemetry, (w - m, m + 1), "right")
        dx = tr.left - max(10, self.layout.telemetry_px)
        dy = tr.centery
        d = max(3, int(round(self.layout.telemetry_px * 0.26)))
        pygame.draw.polygon(screen, p.accent,
                            [(dx, dy - d), (dx + d, dy),
                             (dx, dy + d), (dx - d, dy)])
        if self.mode == "full" and self._second is not None:
            self._text(screen, self._second,
                       (w - m, tr.bottom + 5), "right")

        fy = h - m - self._footer.get_height()
        self._text(screen, self._footer, (w - m, fy), "right")
