"""The cyberspace console overlay.

Everything here is deliberately thin neon type on the dark frame, with the
lower-left corner kept clear for the controller's mode-number watermark.  The
HUD owns the technobabble feed and the axis-change announcement; the renderer
owns the world-space landmark labels (the HUD just projects them).
"""
from __future__ import annotations

import math
import random

import pygame

from .palette import Palette, mix, scale

#: Feed lines.  All invented; the tone is the point, not a quotation.
_EVENTS = (
    ("routing through zaibatsu relay", "ok"),
    ("handshake accepted: sense/net", "ok"),
    ("ghost channel open", "ok"),
    ("construct integrity 99.4%", "ok"),
    ("ice: passive scan only", "ok"),
    ("matrix latency 3.8 ms", "ok"),
    ("mirror vault key rotated", "ok"),
    ("spindle queue drained", "ok"),
    ("simstim buffer clean", "ok"),
    ("orbital uplink re-acquired", "ok"),
    ("black ice kept its distance", "ok"),
    ("dead channel sampled, null", "ok"),
    ("tessier-arco lease renewed", "ok"),
    ("packet loss 0.02% / nominal", "ok"),
    ("counter-intrusion: no traces", "ok"),
    ("data haven node synced", "ok"),
    ("low orbit cache warmed", "ok"),
    ("construct geometry verified", "ok"),
    ("ice signature in sector 04", "warn"),
    ("trace attempt detected", "warn"),
    ("route perturbation: rerouting", "warn"),
    ("unknown process on ghost node", "warn"),
    ("sense/net packet captured", "ok"),
    ("kestrel-9 beacon answered", "ok"),
)

_WARN_WORDS = ("ice", "trace", "intrusion", "unknown", "perturbation")


def _short_hash(text: str) -> int:
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


class HUD:
    def __init__(self, cache, size: tuple[int, int], mode: str = "full",
                 seed: int = 1, title: str = "CYBERSPACE MATRIX",
                 subtitle: str = "ICEBREAKER DECK // PASSIVE SCAN",
                 event_rate_per_min: float = 7.0, show_labels: bool = True,
                 show_reticle: bool = True, show_landmark_overlay: bool = True):
        self.cache = cache
        self.mode = mode if mode in ("full", "minimal", "off") else "full"
        self.seed = int(seed) & 0x7FFFFFFF
        self.title = str(title or "CYBERSPACE MATRIX")
        self.subtitle = str(subtitle or "ICEBREAKER DECK // PASSIVE SCAN")
        self.event_rate = max(0.0, float(event_rate_per_min))
        self.show_labels = bool(show_labels)
        self.show_reticle = bool(show_reticle)
        self.show_landmark_overlay = bool(show_landmark_overlay)
        self.rng = random.Random(self.seed ^ 0xC0FFEE)
        self.events: list[dict] = []
        self._next_event = 2.2
        self._last_axis = None
        self._axis_flash = 0.0
        self._ice_announced = 0.0
        self._ice_was_near = False
        self._time = 0.0
        self.sw = self.sh = 0
        self.font_small = self.font_body = self.font_title = self.font_landmark = None
        self.nav_panel = None
        self.inset_panel = None
        self._inset_rect = None
        self.resize(size)

    # ---------------------------------------------------------------- fonts

    def resize(self, size: tuple[int, int]) -> None:
        self.sw, self.sh = max(1, int(size[0])), max(1, int(size[1]))
        unit = max(9, min(22, int(min(self.sw, self.sh) * 0.026)))
        self.font_small = self.cache.get_font("dejavusansmono",
                                              max(9, unit - 2), bold=False)
        self.font_body = self.cache.get_font("dejavusansmono", unit, bold=False)
        self.font_title = self.cache.get_font("dejavusansmono", unit + 3, bold=True)
        self.font_landmark = self.cache.get_font("dejavusansmono",
                                                  max(9, unit - 2), bold=True)
        self.scale = max(1, min(2, unit // 9))
        self._nav_panel_size = (max(190, min(340, int(self.sw * 0.36))),
                                self.font_small.get_height() * 4 + 14)
        panel = pygame.Surface(self._nav_panel_size, pygame.SRCALPHA)
        panel.fill((0, 0, 0, 218))
        self.nav_panel = panel
        inset_w = max(150, min(230, int(min(self.sw, self.sh) * 0.30)))
        inset_h = int(inset_w * 1.12)
        self._inset_size = (inset_w, inset_h)
        inset = pygame.Surface((inset_w, inset_h), pygame.SRCALPHA)
        inset.fill((0, 0, 0, 222))
        self.inset_panel = inset

    # ---------------------------------------------------------------- feed

    def note_axis(self, route, initial: bool = False) -> None:
        if initial:
            self._last_axis = route.axis
            return
        if route.axis == self._last_axis:
            return
        self._last_axis = route.axis
        direction = "+" if route.direction > 0 else "-"
        self.push(f"VECTOR ACQUIRED // {direction}{route.axis_name}", "ok")
        self._axis_flash = 2.4

    def push(self, text: str, kind: str = "ok") -> None:
        self.events.append({"text": str(text), "kind": kind, "age": 0.0})
        if len(self.events) > 5:
            del self.events[0]

    def update(self, dt: float, route, ice_distance: float | None) -> None:
        if dt <= 0.0:
            return
        self._time += dt
        self._axis_flash = max(0.0, self._axis_flash - dt)
        self.note_axis(route)
        for event in self.events:
            event["age"] += dt
        if self.event_rate > 0.0:
            self._next_event -= dt
            if self._next_event <= 0.0:
                self._emit_random_event()
                self._next_event = max(1.2, self.rng.uniform(
                    0.55, 1.55) * 60.0 / self.event_rate)
        near = ice_distance is not None and ice_distance < 95.0
        if near and not self._ice_was_near and self._ice_announced <= 0.0:
            self.push("ICE PROXIMITY // HOLD VECTOR", "warn")
            self._ice_announced = 12.0
        self._ice_was_near = near
        self._ice_announced = max(0.0, self._ice_announced - dt)

    def _emit_random_event(self) -> None:
        text, kind = _EVENTS[self.rng.randrange(len(_EVENTS))]
        if any(word in text for word in _WARN_WORDS):
            kind = "warn"
        self.push(text.upper(), kind)

    # ---------------------------------------------------------------- drawing

    def draw(self, screen, camera, route, stats: dict,
             labels=(), time_s: float = 0.0) -> None:
        if self.mode == "off":
            return
        p: Palette = stats.get("palette")
        if p is None:
            return
        sw, sh = self.sw, self.sh
        self._inset_rect = None
        margin = max(12, int(min(sw, sh) * 0.035))
        self._draw_corners(screen, p, margin)

        self._text(screen, self.title, (margin, margin), p.hud,
                   self.font_title, "left")
        if self.mode == "full" and self.sw >= 420:
            self._text(screen, self.subtitle, (margin, margin +
                                               self.font_title.get_height() + 2),
                       p.hud_dim, self.font_small, "left")
            self._draw_landmark_nav(screen, p, margin, stats)

        x, y, z = camera.pos
        coord_lines = (f"X {x:+09.2f}", f"Y {y:+09.2f}", f"Z {z:+09.2f}")
        line_h = self.font_body.get_height() + 1
        for i, line in enumerate(coord_lines):
            self._text(screen, line,
                       (sw - margin, margin + i * line_h), p.hud,
                       self.font_body, "right")

        vector = route.axis_vector()
        sign = "+" if route.direction > 0 else "-"
        speed = stats.get("speed", 0.0)
        vec_text = f"VEC {sign}{route.axis_name}   SPD {speed:04.1f}"
        self._text(screen, vec_text,
                   (sw - margin, margin + 3 * line_h + 4), p.hud_dim,
                   self.font_small, "right")
        self._draw_axis_bars(screen, p, sw - margin,
                             margin + 4 * line_h + 7, route)

        if self.mode == "full":
            self._draw_altitude(screen, p, margin, z, stats)
            self._draw_reticle(screen, p, camera)

        # Bottom-left telemetry, lifted clear of the controller's slot number.
        base_y = sh - margin - max(48, self.font_body.get_height() * 2 + 8)
        cell = max(1.0, float(stats.get("cell", 80.0)))
        sector = _short_hash(f"{int(round(x / cell))}:{int(round(y / cell))}") & 0xFFFF
        self._text(screen, f"NODE 0x{sector:04X}   GRID {cell:03.0f}",
                   (margin, base_y), mix(p.hud_dim, p.hud, 0.45),
                   self.font_small, "left")
        self._text(screen, f"DEC K+{self.seed & 0xFFF:03X}   TRACE CLEAN",
                   (margin, base_y + self.font_small.get_height() + 2),
                   mix(p.hud_dim, p.hud, 0.28), self.font_small, "left")

        if self.mode == "full":
            self._draw_feed(screen, p, margin, base_y)
            self._draw_signal(screen, p, sw - margin, sh - margin)
            self._draw_landmark_banner(screen, p, stats)
            self._draw_landmark_overlay(screen, p, stats, time_s)
            if self._axis_flash > 0.0:
                self._draw_axis_flash(screen, p, route)

        if self.show_labels and self.mode != "off":
            self._draw_labels(screen, camera, labels, p)

        if self.mode == "full" and stats.get("ice_distance") is not None \
                and stats["ice_distance"] < 95.0:
            self._draw_ice_warning(screen, p, stats["ice_distance"])

    # ---------------------------------------------------------------- pieces

    def _text(self, screen, text: str, pos, color, font, anchor: str = "left",
              shadow: bool = True):
        if font is None or not text:
            return None
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if anchor == "right":
            rect.topright = pos
        elif anchor == "center":
            rect.center = pos
        else:
            rect.topleft = pos
        if shadow:
            dark = font.render(text, True, (0, 0, 0))
            screen.blit(dark, (rect.x + 1, rect.y + 1))
        screen.blit(surf, rect)
        return rect

    def _draw_corners(self, screen, p: Palette, margin: int) -> None:
        sw, sh = self.sw, self.sh
        arm = max(10, int(min(sw, sh) * 0.028))
        color = p.hud_faint
        for (x, y, dx, dy) in ((margin, margin, 1, 1),
                               (sw - margin, margin, -1, 1),
                               (margin, sh - margin, 1, -1),
                               (sw - margin, sh - margin, -1, -1)):
            pygame.draw.line(screen, color, (x, y), (x + arm * dx, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y + arm * dy), 1)

    def _draw_axis_bars(self, screen, p: Palette, right: int, top: int,
                        route) -> None:
        labels = ("X", "Y", "Z")
        width = max(26, int(min(self.sw, self.sh) * 0.075))
        gap = 5
        total = width * 3 + gap * 2
        x = right - total
        y = top
        for i, label in enumerate(labels):
            active = route.axis == i
            color = p.hud if active else p.hud_faint
            pygame.draw.rect(screen, color, (x, y, width, 3), 1)
            if active:
                pygame.draw.line(screen, color, (x + 2, y + 1),
                                 (x + width - 2, y + 1), 1)
            self._text(screen, label, (x, y + 5), color, self.font_small, "left")
            x += width + gap

    def _draw_altitude(self, screen, p: Palette, margin: int, z: float,
                       stats: dict) -> None:
        if self.sw < 400:
            return
        top = int(self.sh * 0.28)
        bottom = int(self.sh * 0.72)
        x = self.sw - margin - 4
        pygame.draw.line(screen, p.hud_faint, (x, top), (x, bottom), 1)
        for i in range(9):
            yy = top + (bottom - top) * i // 8
            pygame.draw.line(screen, p.hud_faint, (x - 4, yy), (x, yy), 1)
        zmax = max(1.0, float(stats.get("z_max", 336.0)))
        frac = max(0.0, min(1.0, z / zmax))
        cy = bottom - int(frac * (bottom - top))
        pygame.draw.line(screen, p.hud, (x - 8, cy), (x + 1, cy), 2)
        self._text(screen, f"ALT {z:05.0f}", (x - 76, top - 18),
                   p.hud_dim, self.font_small, "left")

    def _draw_reticle(self, screen, p: Palette, camera) -> None:
        if not self.show_reticle:
            return
        cx, cy = self.sw // 2, self.sh // 2
        r = max(10, int(min(self.sw, self.sh) * 0.022))
        arm = max(4, r // 2)
        color = p.hud_faint
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x, y = cx + sx * r, cy + sy * r
            pygame.draw.line(screen, color, (x, y), (x - sx * arm, y), 1)
            pygame.draw.line(screen, color, (x, y), (x, y - sy * arm), 1)
        # A tiny diamond at the centre, with a horizon tick that leans with roll.
        pygame.draw.line(screen, color, (cx - 3, cy), (cx + 3, cy), 1)
        pygame.draw.line(screen, color, (cx, cy - 3), (cx, cy + 3), 1)
        roll = max(-0.5, min(0.5, camera.roll))
        dx = int(r * 0.55)
        dy = int(dx * roll * 1.4)
        pygame.draw.line(screen, p.hud_dim, (cx - dx, cy + dy),
                         (cx + dx, cy + dy), 1)

    def _draw_feed(self, screen, p: Palette, margin: int, base_y: int) -> None:
        lines = self.events[-3:]
        if not lines:
            return
        y = base_y - (self.font_small.get_height() + 2) * len(lines) - 6
        for event in lines:
            age = event["age"]
            fade = max(0.28, 1.0 - age / 14.0)
            base = p.warn if event["kind"] == "warn" else mix(p.hud_dim, p.hud, 0.35)
            color = scale(base, fade)
            self._text(screen, event["text"], (margin, y), color,
                       self.font_small, "left", shadow=True)
            y += self.font_small.get_height() + 2

    def _draw_signal(self, screen, p: Palette, right: int, bottom: int) -> None:
        bars = 7
        bar_w = 3
        gap = 3
        height = max(10, int(self.sh * 0.018))
        x0 = right - bars * (bar_w + gap) + gap
        for i in range(bars):
            wobble = 0.55 + 0.45 * math.sin(self._time * 1.7 + i * 0.9 +
                                            self.seed * 0.13)
            h = max(2, int(height * wobble))
            color = p.hud if i < bars - 2 else p.hud_faint
            pygame.draw.rect(screen, color,
                             (x0 + i * (bar_w + gap), bottom - h, bar_w, h))

    def _draw_axis_flash(self, screen, p: Palette, route) -> None:
        alpha = min(1.0, self._axis_flash / 0.7)
        color = mix(p.hud, p.hud_faint, 1.0 - alpha)
        text = f"VECTOR ACQUIRED // {route.axis_name}"
        rect = self.font_body.render(text, True, color).get_rect()
        rect.midtop = (self.sw // 2, int(self.sh * 0.16))
        surf = self.font_body.render(text, True, color)
        shadow = self.font_body.render(text, True, (0, 0, 0))
        screen.blit(shadow, (rect.x + 1, rect.y + 1))
        screen.blit(surf, rect)
        pygame.draw.line(screen, color, (rect.left, rect.bottom + 3),
                         (rect.right, rect.bottom + 3), 1)

    def _draw_landmark_nav(self, screen, p: Palette, margin: int,
                           stats: dict) -> None:
        nav = stats.get("nearest_landmarks") or ()
        if not nav:
            return
        y = margin + self.font_title.get_height() + self.font_small.get_height() + 12
        if self.nav_panel is not None:
            screen.blit(self.nav_panel, (margin - 6, y - 4))
            pygame.draw.rect(screen, p.hud_dim,
                             (margin - 6, y - 4, self.nav_panel.get_width(),
                              self.nav_panel.get_height()), 1)
        self._text(screen, "NAV // LANDMARKS", (margin, y + 2), p.hud,
                   self.font_small, "left")
        y += self.font_small.get_height() + 6
        for index, (label, _name, distance) in enumerate(nav[:3]):
            color = p.hud if index == 0 else mix(p.hud_dim, p.hud, 0.35)
            text = f"{label}  {distance:03.0f}"
            self._text(screen, text, (margin + 9, y), color,
                       self.font_small, "left", shadow=True)
            cy = y + self.font_small.get_height() // 2
            pygame.draw.polygon(screen, color,
                                ((margin + 2, cy - 3), (margin + 5, cy),
                                 (margin + 2, cy + 3), (margin - 1, cy)), 1)
            y += self.font_small.get_height() + 1

    def _draw_landmark_overlay(self, screen, p: Palette, stats: dict,
                               time_s: float) -> None:
        if not self.show_landmark_overlay or min(self.sw, self.sh) < 420:
            return
        lm = stats.get("nearest_landmark_object")
        nearest = stats.get("nearest_landmark")
        if lm is None or not nearest or nearest[2] > 420.0:
            return
        label, _name, distance = nearest
        color = lm.label_color()
        w, h = self._inset_size
        margin = max(12, int(min(self.sw, self.sh) * 0.035))
        x = self.sw - margin - w
        y = self.sh - margin - 24 - h
        self._inset_rect = pygame.Rect(x, y, w, h)
        if self.inset_panel is not None:
            screen.blit(self.inset_panel, (x, y))
        border = mix(color, p.hud_dim, 0.35)
        pygame.draw.rect(screen, border, (x, y, w, h), 1)

        fh = self.font_small.get_height()
        self._text(screen, "LANDMARK", (x + 9, y + 5), p.hud,
                   self.font_small, "left")
        self._text(screen, f"RNG {distance:03.0f}", (x + w - 9, y + 5),
                   color, self.font_small, "right")
        pygame.draw.line(screen, scale(color, 0.45),
                         (x + 8, y + fh + 6), (x + w - 8, y + fh + 6), 1)

        vx, vy = x + 9, y + fh + 11
        vw, vh = w - 18, h - (fh * 3 + 24)
        if vw <= 8 or vh <= 8:
            return
        self._draw_landmark_model(screen, lm, (vx, vy, vw, vh), time_s, p)

        self._text(screen, self._fit_text(self.font_landmark, label, w - 18),
                   (x + 9, y + h - fh * 2 - 9), color,
                   self.font_landmark, "left", shadow=True)
        sx, sy = lm.sector
        self._text(screen, f"SECTOR {sx:+03d},{sy:+03d}",
                   (x + 9, y + h - fh - 6), p.hud_dim,
                   self.font_small, "left")

    def _draw_landmark_model(self, screen, lm, viewport, time_s: float,
                             p: Palette) -> None:
        vx, vy, vw, vh = viewport
        lc = lm.local_center
        radius = max(1.0, lm.local_radius)
        scale_px = min(vw, vh) * 0.42 / radius
        angle = time_s * 0.22 + (lm.sector[0] * 0.7 + lm.sector[1] * 1.1)
        ca, sa = math.cos(angle), math.sin(angle)
        elevation = math.radians(20.0)
        ce, se = math.cos(elevation), math.sin(elevation)
        cx, cy = vx + vw * 0.5, vy + vh * 0.5

        def project(x, y, z):
            x -= lc[0]
            y -= lc[1]
            z -= lc[2]
            rx = x * ca - y * sa
            ry = x * sa + y * ca
            sx = rx
            sy = z * ce - ry * se
            depth = ry * ce + z * se
            return cx + sx * scale_px, cy - sy * scale_px, depth

        # A faint floor ring at the model's base: it gives the rotation
        # something to read against and frames the form.
        zmin = min(min(e[2], e[5]) for e in lm.local_edges)
        ring = []
        for i in range(24):
            a = 2 * math.pi * i / 24
            ring.append(project(lc[0] + math.cos(a) * radius * 0.88,
                                lc[1] + math.sin(a) * radius * 0.88, zmin))
        for i in range(24):
            a, b = ring[i], ring[(i + 1) % 24]
            pygame.draw.line(screen, p.hud_faint, (a[0], a[1]), (b[0], b[1]), 1)
        pygame.draw.line(screen, p.hud_faint, (cx - 4, cy), (cx + 4, cy), 1)
        pygame.draw.line(screen, p.hud_faint, (cx, cy - 4), (cx, cy + 4), 1)

        aaline = pygame.draw.aaline
        for x1, y1, z1, x2, y2, z2, r, g, b in lm.local_edges:
            p1 = project(x1, y1, z1)
            p2 = project(x2, y2, z2)
            depth = (p1[2] + p2[2]) * 0.5
            fade = 0.58 + 0.42 * (1.0 - (depth / (2 * radius) + 0.5))
            if fade < 0.28:
                fade = 0.28
            aaline(screen, (min(255, int(r * fade)),
                            min(255, int(g * fade)),
                            min(255, int(b * fade))),
                   (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])))

    @staticmethod
    def _fit_text(font, text: str, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + "..")[0] > max_width:
            text = text[:-1]
        return (text + "..") if text else ""

    def _draw_landmark_banner(self, screen, p: Palette, stats: dict) -> None:
        # On wide HUDs the NAV list under the title carries the names; the
        # bottom banner is for narrow screens where that list is hidden.
        if self.sw >= 420:
            return
        nearest = stats.get("nearest_landmark")
        if not nearest:
            return
        label, _name, distance = nearest
        if distance > 420.0:
            return
        text = f"LANDMARK // {label}  {distance:03.0f}"
        font = self.font_landmark
        surf = font.render(text, True, p.hud)
        margin = max(12, int(min(self.sw, self.sh) * 0.035))
        if surf.get_width() > self.sw - margin * 2:
            text = label
            surf = font.render(text, True, p.hud)
        rect = surf.get_rect()
        rect.midbottom = (self.sw // 2, int(self.sh * 0.76))
        shadow = font.render(text, True, (0, 0, 0))
        screen.blit(shadow, (rect.x + 1, rect.y + 1))
        screen.blit(surf, rect)
        cy = rect.centery
        x = rect.left - 9
        pygame.draw.polygon(screen, p.hud,
                            ((x, cy - 4), (x + 4, cy),
                             (x, cy + 4), (x - 4, cy)), 1)

    def _draw_ice_warning(self, screen, p: Palette, distance: float) -> None:
        if int(self._time * 3.0) % 2:
            color = p.warn
        else:
            color = scale(p.warn, 0.45)
        text = f"ICE PROXIMITY {distance:03.0f}"
        surf = self.font_body.render(text, True, color)
        rect = surf.get_rect()
        rect.midbottom = (self.sw // 2, int(self.sh * 0.80))
        shadow = self.font_body.render(text, True, (0, 0, 0))
        screen.blit(shadow, (rect.x + 1, rect.y + 1))
        screen.blit(surf, rect)

    def _draw_labels(self, screen, camera, labels, p: Palette) -> None:
        if not labels:
            return
        margin = max(12, int(min(self.sw, self.sh) * 0.035))
        used = []
        for item in labels[:4]:
            pos = camera.project(item["pos"])
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if not (margin < x < self.sw - margin and
                    margin < y < self.sh * 0.82):
                continue
            fade = max(0.5, 1.0 - item["distance"] / 420.0)
            color = scale(item["color"], fade)
            landmark = bool(item.get("landmark"))
            font = self.font_landmark if landmark else self.font_small
            surf = font.render(item["text"], True, color)
            rect = surf.get_rect()
            text_x = x + (9 if landmark else 0)
            rect.midbottom = (text_x, y - 6)
            if (rect.left - (9 if landmark else 0)) < margin or \
                    rect.right > self.sw - margin:
                continue
            if self._inset_rect is not None and rect.colliderect(self._inset_rect):
                continue
            if any(rect.colliderect(other) for other in used):
                continue
            used.append(rect)
            pygame.draw.line(screen, scale(color, 0.6), (x, y),
                             (x, y - 5), 1)
            pygame.draw.line(screen, scale(color, 0.6),
                             (x - 4, y), (x + 4, y), 1)
            if landmark:
                cy = rect.centery
                pygame.draw.polygon(screen, color,
                                    ((x, cy - 4), (x + 4, cy),
                                     (x, cy + 4), (x - 4, cy)), 1)
            shadow = font.render(item["text"], True, (0, 0, 0))
            screen.blit(shadow, (rect.x + 1, rect.y + 1))
            screen.blit(surf, rect)
