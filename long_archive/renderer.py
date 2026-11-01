"""The cached renderer for The Long Archive.

The wall, its faces, its etched text, the caption, the star field and the
finish are all built once per resolution/quality.  A frame is then: blit the
background, blit the three cached panels, draw only the glyphs inside the
moving light bar's reach, add the bar and the caption, then one downscaled
additive bloom and the baked finish.

That division is deliberate.  Drawing every glyph every frame would be ~2,000
line calls on the strip and over 3,000 on portrait; the cached face makes the
lit column the only per-frame text work.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .glyphs import GLYPHS, Slab
from .palette import Palette, mix, scale
from .layout import Layout

QUALITY = {
    "low": {"row_stride": 2, "mote_fraction": 0.35, "glow_div": 8,
            "foreground": False},
    "medium": {"row_stride": 1, "mote_fraction": 0.70, "glow_div": 6,
               "foreground": True},
    "high": {"row_stride": 1, "mote_fraction": 1.0, "glow_div": 4,
             "foreground": True},
}
QUALITY_NAMES = tuple(QUALITY)

#: The clock starts just past the middle of the first sweep, so the first
#: frame is the composed "held" frame rather than an empty bar at the edge.
BAR_START_PHASE = 0.655
CAPTION_REVEAL_START = 0.24
CAPTION_FADE_START = 0.86
CAPTION_FADE_END = 0.985

SLIDE_SECONDS = 120.0


@dataclass
class CaptionLine:
    text: str
    surface: pygame.Surface
    prefix_widths: list


class WallRenderer:
    def __init__(self, size, palette: Palette, layout: Layout, slabs: list[Slab],
                 cache, seed: int, quality: str, lore, show_labels: bool,
                 bar_period: float, text_speed: float, drift_speed: float,
                 glow_strength: float, scanline_alpha: int,
                 vignette_strength: float):
        self.sw, self.sh = int(size[0]), int(size[1])
        self.palette = palette
        self.layout = layout
        self.slabs = list(slabs)
        self.active = next(s for s in self.slabs if s.focus)
        self.cache = cache
        self.seed = int(seed)
        self.quality = quality if quality in QUALITY else "medium"
        self.lore = list(lore) or [""]
        self.show_labels = bool(show_labels)
        self.bar_period = max(1.0, float(bar_period))
        self.text_speed = max(1.0, float(text_speed))
        self.drift_speed = max(0.0, float(drift_speed))
        self.glow_strength = max(0.0, min(1.0, float(glow_strength)))
        self.scanline_alpha = max(0, min(80, int(scanline_alpha)))
        self.vignette = max(0.0, min(1.0, float(vignette_strength)))

        self._radials: dict = {}
        self._bases: dict = {}
        self._bar = None
        self._bar_outer = layout.bar_outer
        self._bar_spill = layout.bar_spill
        self._background = None
        self._finish = None
        self._bloom = self._bloom_mid = self._bloom_up = None
        self._caption: list[CaptionLine] = []
        self._caption_font = None
        self._catalog_font = None
        self._motes: list = []
        self._stars: list = []
        self.last_stats = {}

        self._build_background()
        self._build_finish()
        self._build_glow()
        self._build_bases()
        self._build_bar()
        self._build_caption()
        self._build_motes()

    # ---------------------------------------------------------------- caches

    def _radial(self, size: int, power: float) -> pygame.Surface:
        key = (int(size), round(float(power), 3))
        surf = self._radials.get(key)
        if surf is not None:
            return surf
        w = h = max(8, int(size))
        surf = pygame.Surface((w, h)).convert()
        surf.fill((0, 0, 0))
        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(h):
            for x in range(w):
                r = math.hypot(x - cx, y - cy) / maxd
                v = max(0.0, 1.0 - r) ** power
                k = int(255 * v)
                surf.set_at((x, y), (k, k, k))
        self._radials[key] = surf
        return surf

    def _build_background(self) -> None:
        p = self.palette
        surf = pygame.Surface((self.sw, self.sh)).convert()
        for y in range(self.sh):
            t = (y / max(1, self.sh - 1)) ** 1.35
            pygame.draw.line(surf, mix(p.bg_top, p.bg_bottom, t),
                             (0, y), (self.sw, y))

        clouds = pygame.Surface((self.sw, self.sh)).convert()
        clouds.fill((0, 0, 0))
        sprite = self._radial(256, 3.0)
        if self.layout.portrait:
            blobs = (
                ((self.active.center_x, self.sh * 0.49),
                 int(self.sh * 0.58), mix(p.bg_top, p.haze, 0.95)),
                ((self.sw * 0.22, self.sh * 0.14),
                 int(self.sh * 0.30), mix(p.bg_top, p.haze, 0.55)),
                ((self.sw * 0.82, self.sh * 0.88),
                 int(self.sh * 0.32), mix(p.bg_top, p.haze, 0.45)),
            )
        else:
            blobs = (
                ((self.active.center_x, self.active.center_y),
                 int(self.sw * 0.61), mix(p.bg_top, p.haze, 0.95)),
                ((self.sw * 0.19, self.sh * 0.50),
                 int(self.sw * 0.40), mix(p.bg_top, p.haze, 0.50)),
                ((self.sw * 0.84, self.sh * 0.50),
                 int(self.sw * 0.40), mix(p.bg_top, p.haze, 0.50)),
            )
        for (cx, cy), size, tint in blobs:
            tinted = sprite.copy()
            tinted.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
            scaled = pygame.transform.smoothscale(tinted, (size, size))
            clouds.blit(scaled, (int(cx - size / 2), int(cy - size / 2)),
                        special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(clouds, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        # Stars are baked into the background: the only motion in the void is
        # the data motes, which are drawn separately.
        rng = random.Random(self.seed ^ 0x51AB)
        count = max(80, min(680, (self.sw * self.sh) // 3000))
        self._stars = [(rng.random(), rng.random(),
                        rng.choice((1, 1, 1, 1, 2, 2, 3)),
                        rng.uniform(0.14, 0.90))
                       for _ in range(count)]
        for fx, fy, size, bright in self._stars:
            x = int(fx * (self.sw - 1))
            y = int(fy * (self.sh - 1))
            color = scale(p.star, bright * 0.58)
            if size >= 3:
                pygame.draw.circle(surf, color, (x, y), 1)
            elif size == 2:
                surf.set_at((x, y), color)
            else:
                surf.set_at((x, y), color)
        self._background = surf

    def _build_finish(self) -> None:
        """Vignette, scanlines and the HUD bands, as one multiply map."""
        if self.vignette <= 0.0 and self.scanline_alpha <= 0:
            self._finish = None
            return
        qw = max(2, self.sw // 4)
        qh = max(2, self.sh // 4)
        small = pygame.Surface((qw, qh)).convert()
        cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(qh):
            for x in range(qw):
                r = math.hypot(x - cx, y - cy) / maxd
                dark = self.vignette * (max(0.0, r - 0.24) / 0.76) ** 1.5
                k = int(255 * max(0.08, 1.0 - dark))
                small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (self.sw, self.sh))
        if self.scanline_alpha > 0:
            k = int(255 * (1.0 - self.scanline_alpha / 255.0))
            for y in range(0, self.sh, 3):
                pygame.draw.line(finish, (k, k, k), (0, y),
                                 (self.sw, y), 1)
        top_h = max(44, int(self.sh * 0.11))
        for y in range(top_h):
            t = (y / max(1, top_h - 1)) ** 2.1
            k = int(32 + 223 * t)
            pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
        bot_h = max(52, int(self.sh * (0.13 if self.layout.portrait else 0.18)))
        for y in range(bot_h):
            k = int(255 - 232 * (y / max(1, bot_h - 1)))
            pygame.draw.line(finish, (k, k, k),
                             (0, self.sh - bot_h + y),
                             (self.sw, self.sh - bot_h + y), 1)
        self._finish = finish

    def _build_glow(self) -> None:
        if self.glow_strength <= 0.0:
            self._bloom = self._bloom_mid = self._bloom_up = None
            return
        div = QUALITY[self.quality]["glow_div"]
        self._bloom = pygame.Surface(
            (max(1, self.sw // div), max(1, self.sh // div))).convert()
        self._bloom_mid = pygame.Surface(
            (max(1, self.sw // 2), max(1, self.sh // 2))).convert()
        self._bloom_up = pygame.Surface((self.sw, self.sh)).convert()

    def _composite_glow(self, screen: pygame.Surface) -> None:
        if self._bloom is None or self.glow_strength <= 0.0:
            return
        pygame.transform.smoothscale(screen, self._bloom.get_size(),
                                     self._bloom)
        k = int(20 + 86 * self.glow_strength)
        self._bloom.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self._bloom, self._bloom_mid.get_size(),
                                     self._bloom_mid)
        pygame.transform.scale(self._bloom_mid, (self.sw, self.sh),
                               self._bloom_up)
        screen.blit(self._bloom_up, (0, 0),
                    special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------------------- the wall

    def _row_geometry(self, slab: Slab):
        inner_w = slab.width - 2.0 * slab.pad_x
        inner_h = slab.height - slab.pad_y - slab.pad_bottom
        return inner_w, max(1.0, inner_h)

    def _draw_glyphs(self, target: pygame.Surface, slab: Slab,
                     lit: bool = False, origin=(0, 0),
                     bar_local: float = 0.0, sigma: float = 100.0) -> None:
        """Draw rows of glyphs.  In `lit` mode only the bar's reach is drawn."""
        stride = QUALITY[self.quality]["row_stride"]
        inner_w, inner_h = self._row_geometry(slab)
        if inner_w <= 8 or inner_h <= 4:
            return
        ox, oy = origin
        radius = 2.4 * sigma
        if lit:
            base_col = mix(self.palette.ink_dim, self.palette.ink, 0.145)
        elif slab.focus:
            base_col = mix(self.palette.ink_dim, self.palette.ink, 0.145)
        else:
            base_col = mix(self.palette.bg_bottom, self.palette.ink_dim,
                           0.05 + 0.24 * slab.brightness)

        for row_index, (v, indent, cells, glyphs, wear) in enumerate(slab.rows):
            if stride > 1 and row_index % stride:
                continue
            y = slab.pad_y + v * inner_h
            cell_w = inner_w / max(1, cells)
            start = slab.pad_x + indent * cell_w
            for i, glyph in enumerate(glyphs):
                gx = start + i * cell_w
                if lit:
                    center = gx + cell_w * 0.31
                    if abs(center - bar_local) > radius:
                        continue
                    near = math.exp(-((center - bar_local) / sigma) ** 2)
                    col = mix(base_col, self.palette.ink,
                              min(1.0, 0.80 * near))
                else:
                    col = base_col
                if wear < 1.0:
                    col = scale(col, 0.45 + 0.55 * wear)
                for stroke in GLYPHS[glyph]:
                    (ax, ay), (bx, by) = stroke
                    x1 = int(ox + gx + ax * cell_w * 0.62)
                    x2 = int(ox + gx + bx * cell_w * 0.62)
                    y1 = int(oy + y + (ay - 0.5) * slab.pitch * 0.62)
                    y2 = int(oy + y + (by - 0.5) * slab.pitch * 0.62)
                    pygame.draw.line(target, col, (x1, y1), (x2, y2), 1)

    def _build_base(self, slab: Slab) -> pygame.Surface:
        p = self.palette
        w = max(2, int(round(slab.width)))
        h = max(2, int(round(slab.height)))
        surf = pygame.Surface((w, h)).convert()
        dim = slab.brightness
        if slab.focus:
            top = mix(p.face_top, p.haze, 0.10)
            bottom = mix(p.face_bottom, p.bg_bottom, 0.25)
        else:
            top = mix(p.bg_top, p.face_top, 0.10 + 0.45 * dim)
            bottom = mix(p.bg_bottom, p.face_bottom, 0.12 + 0.42 * dim)
        for y in range(h):
            t = y / max(1, h - 1)
            col = mix(top, bottom, t ** 0.82)
            if not slab.focus:
                col = mix(col, p.bg_top, 0.22 * (1.0 - dim))
            pygame.draw.line(surf, col, (0, y), (w - 1, y))

        # Vertical seams: worked stone, not a screen.
        seam = mix(p.bg_bottom, p.detail, 0.10 + 0.35 * dim)
        for frac in (0.32, 0.71):
            x = int(w * frac)
            pygame.draw.aaline(surf, seam, (x, 3), (x, h - 4))

        # Edge and inset border.
        edge = mix(p.bg_bottom, p.structure, 0.06 + 0.62 * dim ** 1.15)
        hi = mix(p.detail, p.ink, 0.10 + 0.62 * dim ** 1.2)
        pygame.draw.aaline(surf, edge, (0, 0), (0, h - 1))
        pygame.draw.aaline(surf, hi, (w - 1, 0), (w - 1, h - 1))
        pygame.draw.aaline(surf, mix(p.detail, p.structure, 0.4),
                           (0, 0), (w - 1, 0))
        pygame.draw.aaline(surf, mix(p.bg_bottom, p.detail, 0.25 + 0.35 * dim),
                           (0, h - 1), (w - 1, h - 1))
        inset = max(3, int(round(w * 0.02)))
        inner = mix(p.bg_top, p.detail, 0.10 + 0.32 * dim)
        pygame.draw.aaline(surf, inner, (inset, inset),
                           (w - 1 - inset, inset))
        pygame.draw.aaline(surf, inner, (inset, inset),
                           (inset, h - 1 - inset))
        pygame.draw.aaline(surf, inner, (w - 1 - inset, inset),
                           (w - 1 - inset, h - 1 - inset))

        self._draw_glyphs(surf, slab)

        if slab.focus and self.show_labels and self._catalog_font is not None:
            label = slab.label or "TL-0000"
            mark = self._catalog_font.render(
                label, True, mix(p.structure, p.warm, 0.35))
            rect = mark.get_rect()
            rect.bottomright = (w - 8, h - 7)
            surf.blit(mark, rect)
        return surf

    def _build_bases(self) -> None:
        self._catalog_font = self.cache.get_font(
            "dejavusansmono", max(8, self.layout.catalog_px))
        self._bases = {slab.id: self._build_base(slab) for slab in self.slabs}

    def _build_bar(self) -> None:
        """One vertical light profile, low-res built and smooth-upscaled."""
        outer = max(12, self.layout.bar_outer)
        core = max(1.5, self.layout.bar_core)
        spill = max(4, self.layout.bar_spill)
        bh = int(self.layout.band_height) + spill * 2
        bw = outer * 2 + 1
        lw = max(8, int(bw / 4))
        lh = max(8, int(bh / 4))
        low = pygame.Surface((lw, lh)).convert()
        low.fill((0, 0, 0))
        for xi in range(lw):
            dx = (xi - (lw - 1) * 0.5) * (bw / lw)
            r = abs(dx)
            profile = (
                math.exp(-(r / core) ** 2) * 0.52
                + math.exp(-(r / (core * 4.0)) ** 2) * 0.27
                + math.exp(-(r / (core * 14.0)) ** 2) * 0.12
            )
            if profile < 0.0015:
                continue
            col = mix(self.palette.bar_edge, self.palette.bar_hot,
                      min(1.0, profile * 1.45))
            for yi in range(lh):
                wy = (yi / max(1, lh - 1)) * (bh - 1)
                if wy < spill:
                    fade = max(0.0, 1.0 - (spill - wy) / max(1, spill))
                elif wy > bh - spill:
                    fade = max(0.0, 1.0 - (wy - (bh - spill)) / max(1, spill))
                else:
                    fade = 1.0
                if fade <= 0.0:
                    continue
                low.set_at((xi, yi), scale(col, profile * fade))
        self._bar = pygame.transform.smoothscale(low, (bw, bh))
        self._bar_outer = outer
        self._bar_spill = spill

    # ------------------------------------------------------------- captions

    def _build_caption(self) -> None:
        max_w = max(120, self.layout.caption_max_w)
        px = max(9, min(32, self.layout.caption_px))
        font = self.cache.get_font("dejavuserif", px)
        while px > 9 and max(font.size(line)[0] for line in self.lore) > max_w:
            px -= 1
            font = self.cache.get_font("dejavuserif", px)
        self._caption_font = font
        self._caption_font_px = px
        self._caption = []
        for line in self.lore:
            text = str(line)
            surface = font.render(text, True, self.palette.lore)
            widths = [font.size(text[:i])[0] for i in range(len(text) + 1)]
            self._caption.append(CaptionLine(text, surface, widths))

    def _draw_caption(self, screen: pygame.Surface, offset: int,
                      cycle: int, phase: float, visible: int,
                      alpha: float) -> None:
        if alpha <= 0.01 or visible <= 0 or not self._caption:
            return
        p = self.palette
        line = self._caption[cycle % len(self._caption)]
        surf = line.surface
        cx = int(self.active.center_x + offset)
        top = int(self.layout.band_bottom + self.layout.caption_gap)
        half = surf.get_width() // 2 + max(12, self.layout.caption_px // 2)
        top_y = top - max(6, self._caption_font_px // 3)
        bot_y = top + surf.get_height() + max(5, self._caption_font_px // 4)
        if self.show_labels:
            label = f"SLAB 04 // TRANSLATION"
            label_surf = self._catalog_font.render(
                label, True, scale(mix(p.warm, p.accent_dim, 0.55), alpha))
            screen.blit(label_surf, (cx - half, top_y - label_surf.get_height() - 2))
            pygame.draw.line(screen, scale(mix(p.accent_dim, p.detail, 0.35),
                                           alpha),
                             (cx, int(self.active.bottom + 3)),
                             (cx, top_y - 7), 1)
            pygame.draw.line(screen, scale(mix(p.accent_dim, p.detail, 0.35),
                                           alpha),
                             (cx, top_y - 7), (cx - 4, top_y - 7), 1)
            pygame.draw.line(screen, scale(mix(p.accent_dim, p.detail, 0.35),
                                           alpha),
                             (cx, top_y - 7), (cx + 4, top_y - 7), 1)

        for yy in (top_y, bot_y):
            pygame.draw.line(screen, scale(mix(p.accent_dim, p.accent, 0.22),
                                           alpha),
                             (cx - half, yy), (cx + half, yy), 1)
        for xx in (cx - half, cx + half):
            for yy, direction in ((top_y, 1), (bot_y, -1)):
                pygame.draw.line(screen,
                                 scale(mix(p.accent_dim, p.accent, 0.30),
                                       alpha),
                                 (xx, yy), (xx, yy + direction * 3), 1)

        cut = line.prefix_widths[min(visible, len(line.text))]
        if cut <= 0:
            return
        surf.set_alpha(int(255 * max(0.0, min(1.0, alpha))))
        screen.blit(surf, (cx - surf.get_width() // 2, top),
                    area=pygame.Rect(0, 0, cut, surf.get_height()))

    # ---------------------------------------------------------------- motes

    def _build_motes(self) -> None:
        rng = random.Random(self.seed ^ 0x91F3)
        self._motes = []
        count = 260 if self.layout.portrait else 140
        for _ in range(count):
            if rng.random() < 0.70:
                x = self.active.center_x + rng.gauss(0, self.active.width * 0.55)
                y = self.active.center_y + rng.gauss(0, self.active.height * 0.75)
            else:
                x = rng.uniform(0, self.sw)
                y = rng.uniform(0, self.sh)
            size = rng.choice((1, 1, 1, 1, 2, 2, 2, 3))
            bright = rng.uniform(0.10, 0.72)
            warm = rng.random() < 0.18
            vx = rng.uniform(-1.4, 1.4)
            vy = rng.uniform(-2.0, 0.6)
            front = rng.random() < 0.26
            self._motes.append((x, y, size, bright, warm, vx, vy, front))

    def _draw_motes(self, screen: pygame.Surface, time_s: float,
                    front: bool) -> None:
        p = self.palette
        frac = QUALITY[self.quality]["mote_fraction"]
        if front and not QUALITY[self.quality]["foreground"]:
            return
        limit = int(len(self._motes) * frac)
        caption_centres = (self.active.center_x, self.layout.band_bottom)
        for i, (x, y, size, bright, warm, vx, vy, is_front) in enumerate(self._motes[:limit]):
            if is_front != front:
                continue
            mx = (x + vx * time_s + 10.0) % (self.sw + 20.0) - 10.0
            my = (y + vy * time_s + 10.0) % (self.sh + 20.0) - 10.0
            if front:
                # Keep the caption plate and the lower-left mode number clear.
                if (abs(mx - caption_centres[0])
                        < self.layout.active_w * 0.42
                        and my > self.layout.band_bottom + self.layout.caption_gap - 18):
                    continue
                if mx < 90 and my > self.sh - 50:
                    continue
                if my > self.sh - self.layout.margin - 24 and mx > self.sw - 280:
                    continue
            color = scale(p.accent if not warm else p.warm, bright * 0.52)
            if size >= 3:
                pygame.draw.line(screen, scale(color, 0.45),
                                 (int(mx - 2), int(my)), (int(mx + 2), int(my)), 1)
            elif size == 2:
                pygame.draw.circle(screen, color, (int(mx), int(my)), 1)
            else:
                screen.set_at((int(mx), int(my)), color)

    # ---------------------------------------------------------------- clock

    def _clock(self, time_s: float):
        """(cycle, phase, bar sweep fraction, wall offset)."""
        t = float(time_s) + self.bar_period * BAR_START_PHASE
        cycle = int(t // self.bar_period)
        phase = (t % self.bar_period) / self.bar_period
        sweep = (2.0 * phase) if phase < 0.5 else (2.0 - 2.0 * phase)
        fraction = 0.08 + 0.84 * sweep
        if self.drift_speed <= 0.0:
            offset = 0
        else:
            amp = self.layout.slide_amp * (self.drift_speed / 2.0)
            offset = int(round(amp * math.sin(
                math.tau * float(time_s) / SLIDE_SECONDS)))
        return cycle, phase, fraction, offset

    def _caption_state(self, phase: float):
        if phase < CAPTION_REVEAL_START or phase >= CAPTION_FADE_END:
            return 0, 0.0
        visible = int(max(0.0, phase - CAPTION_REVEAL_START)
                      * self.bar_period * self.text_speed)
        if phase <= CAPTION_FADE_START:
            alpha = 1.0
        else:
            alpha = 1.0 - ((phase - CAPTION_FADE_START)
                           / (CAPTION_FADE_END - CAPTION_FADE_START))
        return visible, max(0.0, min(1.0, alpha))

    # ---------------------------------------------------------------- frame

    def _stats_for(self, cycle: int, phase: float, fraction: float,
                   offset: int, visible: int) -> dict:
        caption_index = cycle % len(self._caption) if self._caption else 0
        caption_len = (len(self._caption[caption_index].text)
                       if self._caption else 0)
        return {
            "visible_slabs": len(self.slabs),
            "active_width": self.active.width,
            "active_fraction": self.active.width / max(1, self.sw),
            "bar_fraction": fraction,
            "caption_chars": min(visible, caption_len),
            "caption_index": caption_index,
            "caption_len": caption_len,
            "quality": self.quality,
            "glyphs": sum(len(s.rows) for s in self.slabs),
            "offset": offset,
            "phase": phase,
        }

    def snapshot(self, time_s: float) -> dict:
        cycle, phase, fraction, offset = self._clock(time_s)
        visible, _alpha = self._caption_state(phase)
        return self._stats_for(cycle, phase, fraction, offset, visible)

    def render(self, screen: pygame.Surface, time_s: float) -> None:
        cycle, phase, fraction, offset = self._clock(time_s)
        visible, alpha = self._caption_state(phase)
        self.last_stats = self._stats_for(cycle, phase, fraction, offset,
                                          visible)

        screen.blit(self._background, (0, 0))
        self._draw_motes(screen, time_s, front=False)
        for slab in self.slabs:
            base = self._bases.get(slab.id)
            if base is not None:
                screen.blit(base, (int(round(slab.x + offset)),
                                   int(round(slab.top))))

        bar_local = fraction * self.active.width
        self._draw_glyphs(screen, self.active, lit=True,
                          origin=(int(round(self.active.x + offset)),
                                  int(round(self.active.top))),
                          bar_local=bar_local, sigma=self.layout.lit_sigma)

        bar_x = self.active.x + offset + bar_local
        if self._bar is not None:
            screen.blit(self._bar,
                        (int(round(bar_x - self._bar_outer)),
                         int(round(self.active.top - self._bar_spill))),
                        special_flags=pygame.BLEND_RGB_ADD)
        self._draw_caption(screen, offset, cycle, phase, visible, alpha)
        self._draw_motes(screen, time_s, front=True)
        self._composite_glow(screen)
        if self._finish is not None:
            screen.blit(self._finish, (0, 0),
                        special_flags=pygame.BLEND_RGB_MULT)

    # ---------------------------------------------------------------- control

    def set_quality(self, quality: str) -> None:
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        self._build_bases()
        self._build_glow()

    def stats(self) -> dict:
        if not self.last_stats:
            self.last_stats = self.snapshot(0.0)
        return dict(self.last_stats)
