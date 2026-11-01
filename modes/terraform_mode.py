"""Terraform — a mountain overlook, changing over three minutes.

Slow Worlds §5.15.  A fixed camera on a summit looks down a valley toward a
delta.  Ice retreats, rivers branch, green spreads from the coasts and city
lights appear along the new waterways.

This file is the mode wrapper: config, the five-stage cycle, crossfades,
quality, HUD, resize and the small per-frame overlays.  The drawing lives in
`terraform/art.py`; the heavy work (sky, range, valley patchwork, ridges,
foreground) is rendered once per stage into a keyframe and cached.  Only the
river glints, birds, city lights, stage crossfade and timeline move per frame.

No disk I/O, no network, no threads in the frame loop.  The lower-left 80x32
px stays clear for the controller's mode number.
"""
from __future__ import annotations

import math
import random

import pygame

from terraform import art

TAU = math.tau

QUALITY_NAMES = ("auto", "low", "medium", "high")
HUD_MODES = ("full", "minimal", "off")
ORIENTATIONS = ("auto", "ultrawide", "landscape", "portrait", "square")
PRESETS = {
    "ultrawide": "strip",
    "landscape": "landscape",
    "portrait": "portrait",
    "square": "square",
}
# Fraction of the native frame used for the cached stage keyframes.  High is
# native; the upscale from medium is intentional: it keeps the build quick on
# the Pi and the flat colour style tolerates it.
QUALITY_SCALE = {"low": 0.55, "medium": 0.75, "high": 1.0}
QUALITY_DETAIL = {"low": 0.38, "medium": 0.68, "high": 1.0}


def aspect_preset(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
    if aspect <= 0.82:
        return "portrait"
    if aspect >= 1.25:
        return "landscape"
    return "square"


class TerraformMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.error_message = ""
        self.seed = None
        self._pinned_seed = None

        self._palette_name = "biosphere"
        self._palette = art.get_palette("biosphere")
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality = "medium"
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._overlay_detail = QUALITY_DETAIL["medium"]
        self._hud_mode = "full"
        self._orientation = "auto"
        self._cycle_seconds = 180.0
        self._start_stage = 0
        self._show_timeline = True
        self._city_lights = True
        self._lighthouse = True
        self._foreground = True
        self._mist = True
        self._title = "TERRAFORM"
        self._subtitle = "A WORLD IN PROGRESS · SITE 07"

        self._time = 0.0
        self._stage = 0
        self._stage_name = "ICE"
        self._progress = 0.0
        self._year = 0
        self._hud_stage = 0
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._stage_surfaces = []
        self._stage_scaled = []
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        self._hud = None
        self._river_glints = []
        self._city_points = []
        self._birds = []
        self._last_error_logged = False
        self._clear()

    # ---------------------------------------------------------------- config

    @staticmethod
    def _number(config, key, default, lo, hi):
        value = config.get(key, default)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        value = float(value)
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be finite and in {lo}..{hi}")
        return value

    @staticmethod
    def _integer(config, key, default, lo, hi):
        value = config.get(key, default)
        if value is None:
            value = default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a whole number")
        if float(value) != int(value):
            raise ValueError(f"{key} must be a whole number")
        value = int(value)
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be in {lo}..{hi}")
        return value

    @staticmethod
    def _bool(config, key, default):
        value = config.get(key, default)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false")
        return value

    @staticmethod
    def _text(config, key, default, max_length=72):
        value = config.get(key, default)
        if value is None:
            value = default
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        return value.strip()[:max_length]

    def _read_config(self):
        cfg = self.config
        seed = cfg.get("seed")
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
                raise ValueError("seed must be an integer in 0..2147483647 or null")
        self._pinned_seed = seed

        palette = str(cfg.get("palette", "biosphere")).lower()
        if palette not in art.PALETTES:
            raise ValueError("palette must be " + ", ".join(sorted(art.PALETTES)))
        self._palette_name = palette
        self._palette = art.get_palette(palette)

        quality = str(cfg.get("quality", "auto")).lower()
        if quality not in QUALITY_NAMES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"

        hud = str(cfg.get("hud", "full")).lower()
        if hud not in HUD_MODES:
            raise ValueError("hud must be full, minimal, or off")
        self._hud_mode = hud

        orientation = str(cfg.get("orientation", "auto")).lower()
        if orientation not in ORIENTATIONS:
            raise ValueError("orientation must be " + ", ".join(ORIENTATIONS))
        self._orientation = orientation

        self._cycle_seconds = self._number(cfg, "cycle_seconds", 180.0, 45.0, 900.0)
        self._start_stage = self._integer(cfg, "start_stage", 0, 0, 4)
        self._show_timeline = self._bool(cfg, "show_timeline", True)
        self._city_lights = self._bool(cfg, "show_city_lights", True)
        self._lighthouse = self._bool(cfg, "show_lighthouse", True)
        self._foreground = self._bool(cfg, "show_foreground", True)
        self._mist = self._bool(cfg, "mist", True)

        self._title = self._text(cfg, "title", "TERRAFORM", 48) or "TERRAFORM"
        self._subtitle = self._text(
            cfg, "subtitle", "A WORLD IN PROGRESS · SITE 07", 72)

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            self.seed = self._next_seed()
            self._time = 0.0
            self._quality = "medium" if self._auto_quality else self._quality_setting
            self._quality_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self._overlay_detail = QUALITY_DETAIL.get(
                self._quality, QUALITY_DETAIL["medium"])
            self._build(manager.screen.get_size())
            self.error = None
            print(f"[Terraform] seed={self.seed} preset={self._preset} "
                  f"cycle={self._cycle_seconds:.0f}s start_stage={self._start_stage} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"palette={self._palette_name}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.error_message = str(exc)
            print(f"[Terraform] configuration error: {exc}")

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def exit(self):
        self.manager = None
        self.error = None
        self._screen_size = None
        self._preset = None
        self._layout = None
        self._stage_surfaces = []
        self._stage_scaled = []
        self._hud_title = None
        self._hud_title_rect = None
        self._hud = None
        self._hud_rects = []
        self._river_glints = []
        self._city_points = []
        self._birds = []
        self._time = 0.0
        self._stage = 0
        self._progress = 0.0
        self._year = 0
        self._hud_stage = 0
        self._last_error_logged = False

    def _clear(self):
        self._stage_surfaces = []
        self._stage_scaled = []
        self._hud_title = None
        self._hud = None
        self._hud_rects = []
        self._river_glints = []
        self._city_points = []
        self._birds = []

    def handle_event(self, event):
        """The controller owns input; this mode has none."""

    # ---------------------------------------------------------------- layout / build

    def _resolve_preset(self, size):
        width, height = int(size[0]), int(size[1])
        if self._orientation == "auto":
            return aspect_preset(width, height)
        return self._orientation

    def _build(self, size):
        width, height = int(size[0]), int(size[1])
        preset = self._resolve_preset((width, height))
        self._screen_size = (width, height)
        self._preset = preset
        self._layout = art.layout_for((width, height), PRESETS[preset])
        self._build_stage_surfaces()
        self._build_overlays()
        self._build_hud()
        self._last_error_logged = False

    def _build_stage_surfaces(self):
        width, height = self._screen_size
        scale = QUALITY_SCALE.get(self._quality, 0.75)
        iw = max(360, int(width * scale))
        ih = max(220, int(height * scale))
        layout = art.layout_for((iw, ih), PRESETS[self._preset])
        surfaces = []
        for stage in range(5):
            scene = art.render_static(
                layout, self.seed, stage, self._palette_name,
                city_lights=self._city_lights,
                lighthouse=self._lighthouse,
                foreground=self._foreground,
                mist=self._mist,
            )
            surfaces.append(pygame.transform.smoothscale(
                scene, (width, height)).convert())
        self._stage_surfaces = surfaces
        self._stage_scaled = surfaces
        art.use_palette(self._palette)

    def _build_overlays(self):
        width, height = self._screen_size
        layout = art.layout_for((width, height), PRESETS[self._preset])
        art.use_palette(self._palette)
        view = art.View(layout)
        pts = art._river_points(view)
        widths = [art._river_width(view, y) for _, y in pts]
        step = max(1, len(pts) // 26)
        lip = min(y for _, y in layout["ledge"]["top"]) * height - 6
        self._river_glints = [
            (pts[i][0], pts[i][1], widths[i])
            for i in range(0, len(pts) - 1, step)
            if pts[i][1] < lip
        ]

        rng = random.Random(self.seed ^ 0x7E44A)
        delta = layout["delta"]
        town = layout["town"]
        farm = layout["farm"]
        points = []
        for _ in range(16):
            points.append((
                (delta["x"] + rng.gauss(0, 0.05)) * width,
                (delta["y"] + rng.uniform(-0.012, 0.040)) * height,
                rng.uniform(0.0, TAU), rng.uniform(0.7, 1.6),
            ))
        for cx, cy, count in ((town["x"], town["y"], 5),
                               (farm["x"], farm["y"], 4)):
            for _ in range(count):
                points.append((
                    (cx + rng.uniform(-0.045, 0.045)) * width,
                    (cy + rng.uniform(-0.020, 0.035)) * height,
                    rng.uniform(0.0, TAU), rng.uniform(0.5, 1.2),
                ))
        self._city_points = points

        self._birds = [
            (rng.uniform(0.02, 0.98), rng.uniform(0.06, 0.24),
             rng.uniform(0.5, 1.4), rng.uniform(0.002, 0.006))
            for _ in range(4)
        ]

    # ---------------------------------------------------------------- HUD

    def _hud_metrics(self):
        width, height = self._screen_size
        preset = self._preset
        if preset == "portrait":
            return dict(
                title_x=max(20, int(width * 0.052)),
                title_y=max(20, int(height * 0.054)),
                eyebrow_y=max(10, int(height * 0.035)),
                subtitle_y=max(30, int(height * 0.098)),
                title_px=max(18, int(height * 0.029)),
                eyebrow_px=max(8, int(height * 0.0068)),
                sub_px=max(8, int(height * 0.0068)),
                tele_x=width - max(20, int(width * 0.052)),
                tele_y=max(18, int(height * 0.035)),
                tele_px=max(9, int(height * 0.0073)),
                stage_px=max(8, int(height * 0.0060)),
                year_px=max(8, int(height * 0.0060)),
                timeline_x0=max(140, int(width * 0.139)),
                timeline_x1=min(width - 20, int(width * 0.861)),
                timeline_y=height - max(22, int(height * 0.044)),
                label_y=height - max(44, int(height * 0.062)),
                title_track=max(2, int(width * 0.0093)),
            )
        if preset == "landscape":
            return dict(
                title_x=max(20, int(width * 0.023)),
                title_y=max(20, int(height * 0.042)),
                eyebrow_y=max(10, int(height * 0.020)),
                subtitle_y=max(30, int(height * 0.080)),
                title_px=max(18, int(height * 0.038)),
                eyebrow_px=max(8, int(height * 0.0093)),
                sub_px=max(8, int(height * 0.0093)),
                tele_x=width - max(20, int(width * 0.023)),
                tele_y=max(18, int(height * 0.024)),
                tele_px=max(9, int(height * 0.0102)),
                stage_px=max(8, int(height * 0.0093)),
                year_px=max(8, int(height * 0.0093)),
                timeline_x0=max(140, int(width * 0.180)),
                timeline_x1=min(width - 20, int(width * 0.820)),
                timeline_y=height - max(18, int(height * 0.026)),
                label_y=height - max(38, int(height * 0.046)),
                title_track=max(2, int(height * 0.0074)),
            )
        if preset == "square":
            return dict(
                title_x=max(16, int(width * 0.040)),
                title_y=max(16, int(height * 0.043)),
                eyebrow_y=max(8, int(height * 0.022)),
                subtitle_y=max(28, int(height * 0.086)),
                title_px=max(16, int(height * 0.038)),
                eyebrow_px=max(7, int(height * 0.010)),
                sub_px=max(7, int(height * 0.010)),
                tele_x=width - max(16, int(width * 0.040)),
                tele_y=max(16, int(height * 0.028)),
                tele_px=max(8, int(height * 0.011)),
                stage_px=max(7, int(height * 0.010)),
                year_px=max(7, int(height * 0.010)),
                timeline_x0=max(140, int(width * 0.160)),
                timeline_x1=min(width - 16, int(width * 0.840)),
                timeline_y=height - max(16, int(height * 0.030)),
                label_y=height - max(34, int(height * 0.055)),
                title_track=max(1, int(height * 0.0075)),
            )
        return dict(
            title_x=max(16, int(width * 0.023)),
            title_y=max(14, int(height * 0.075)),
            eyebrow_y=max(8, int(height * 0.037)),
            subtitle_y=max(28, int(height * 0.160)),
            title_px=max(14, int(height * 0.0675)),
            eyebrow_px=max(7, int(height * 0.020)),
            sub_px=max(7, int(height * 0.020)),
            tele_x=width - max(16, int(width * 0.023)),
            tele_y=max(14, int(height * 0.0475)),
            tele_px=max(8, int(height * 0.0225)),
            stage_px=max(7, int(height * 0.020)),
            year_px=max(7, int(height * 0.020)),
            timeline_x0=max(140, int(width * 0.212)),
            timeline_x1=min(width - 20, int(width * 0.788)),
            timeline_y=height - max(16, int(height * 0.0425)),
            label_y=height - max(34, int(height * 0.090)),
            title_track=max(2, int(height * 0.015)),
        )

    def _font(self, size, bold=False):
        return self.manager.cache.get_font("dejavusansmono", max(7, int(size)),
                                           bold=bold)

    def _build_hud(self):
        self._hud = self._hud_metrics()
        self._hud_title = None
        self._hud_title_rect = None
        self._hud_rects = []
        if self._hud_mode == "off":
            return
        m = self._hud
        width, height = self._screen_size
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        title_font = self._font(m["title_px"], bold=True)
        eyebrow_font = self._font(m["eyebrow_px"])
        sub_font = self._font(m["sub_px"])
        y = m["title_y"]
        if self._hud_mode == "full":
            art.draw_tracked(
                layer, "SLOW WORLDS · SCIENCE FICTION", eyebrow_font,
                art.PAL["accent"], (m["title_x"], m["eyebrow_y"]),
                tracking=m["eyebrow_px"] * 0.20, alpha=238)
        title_w = art.draw_tracked(
            layer, self._title, title_font, art.PAL["ink"],
            (m["title_x"], y), tracking=m["title_track"], alpha=246)
        rule_y = int(y + m["title_px"] * 1.20)
        pygame.draw.line(layer, art.mix(art.PAL["accent"], art.PAL["sky_top"], 0.55),
                         (m["title_x"], rule_y),
                         (m["title_x"] + int(title_w * 0.74), rule_y), 1)
        pygame.draw.line(layer, art.mix(art.PAL["ink_dim"], art.PAL["sky_top"], 0.65),
                         (m["title_x"], rule_y + 4),
                         (m["title_x"] + int(title_w * 0.32), rule_y + 4), 1)
        if self._hud_mode == "full":
            art.draw_tracked(
                layer, self._subtitle, sub_font, art.PAL["ink_dim"],
                (m["title_x"], m["subtitle_y"]),
                tracking=m["sub_px"] * 0.12, alpha=205)
        self._hud_title = layer
        self._hud_title_rect = pygame.Rect(
            m["title_x"], m["eyebrow_y"], max(60, int(title_w) + 8),
            max(36, m["subtitle_y"] + m["sub_px"] * 2 - m["eyebrow_y"]))

    def _draw_text_right(self, screen, text, font, color, x, y, alpha=255):
        surf = font.render(text, True, color)
        if alpha < 255:
            surf.set_alpha(alpha)
        rect = surf.get_rect()
        rect.topright = (int(x), int(y))
        screen.blit(surf, rect)
        self._hud_rects.append(rect.copy())
        return rect

    def _draw_text_center(self, screen, text, font, color, x, y, alpha=255):
        surf = font.render(text, True, color)
        if alpha < 255:
            surf.set_alpha(alpha)
        rect = surf.get_rect()
        rect.midtop = (int(x), int(y))
        screen.blit(surf, rect)
        return rect

    def _draw_text_left(self, screen, text, font, color, x, y, alpha=255):
        surf = font.render(text, True, color)
        if alpha < 255:
            surf.set_alpha(alpha)
        rect = surf.get_rect()
        rect.topleft = (int(x), int(y))
        screen.blit(surf, rect)
        return rect

    def _draw_hud(self, screen, stage, progress, year):
        if self._hud_mode == "off" or self._hud is None:
            return
        m = self._hud
        width, height = self._screen_size
        self._hud_rects = []
        if self._hud_title is not None:
            screen.blit(self._hud_title, (0, 0))
            if self._hud_title_rect is not None:
                self._hud_rects.append(self._hud_title_rect)
        tele_font = self._font(m["tele_px"], bold=True)
        tele_small = self._font(max(7, m["tele_px"] - 1))
        stage_font = self._font(m["stage_px"], bold=True)
        year_font = self._font(m["year_px"])
        stage_name = art.STAGE_NAMES[stage]
        x = m["tele_x"]
        y = m["tele_y"]
        self._draw_text_right(screen, f"STAGE {stage:02d} / {stage_name}",
                              tele_font, art.PAL["ink"], x, y, 210)
        self._draw_text_right(screen, f"YEAR {year:03d} / 120",
                              tele_small, art.PAL["ink_dim"], x,
                              y + int(m["tele_px"] * 1.55), 195)
        if self._hud_mode == "full":
            self._draw_text_right(screen, "MEAN SURFACE +12.4 °C",
                                  tele_small, art.PAL["ink_faint"], x,
                                  y + int(m["tele_px"] * 3.10), 150)
            self._draw_text_right(screen, "ALT 2,140 M · N 072°",
                                  tele_small, art.PAL["ink_faint"], x,
                                  y + int(m["tele_px"] * 4.65), 135)

        if not self._show_timeline:
            return
        x0, x1 = m["timeline_x0"], m["timeline_x1"]
        ty = m["timeline_y"]
        label_y = m["label_y"]
        if x1 <= x0:
            return
        # a soft footer band keeps the timeline legible over the dark ledge
        band_h = max(34, int(height * 0.11))
        band = pygame.Surface((width, band_h), pygame.SRCALPHA)
        for row in range(band_h):
            t = row / max(1, band_h - 1)
            pygame.draw.line(band, art.rgba(art.PAL["shadow"],
                                            int(58 * t ** 1.25)),
                             (0, row), (width, row))
        screen.blit(band, (0, height - band_h))
        track = art.mix(art.PAL["ink_dim"], art.PAL["haze"], 0.28)
        pygame.draw.line(screen, track, (x0, ty), (x1, ty), 1)
        px = x0 + (x1 - x0) * progress
        pygame.draw.line(screen, art.mix(art.PAL["accent"], art.PAL["sky_low"], 0.35),
                         (x0, ty), (int(px), ty), 2)
        for i, name in enumerate(art.STAGE_NAMES):
            tick_x = x0 + (x1 - x0) * i / 4
            active = i == stage
            passed = i <= stage
            pygame.draw.line(screen, (art.PAL["ink"] if active else track),
                             (int(tick_x), ty - 3), (int(tick_x), ty + 3),
                             1 if not active else 2)
            rect = self._draw_text_center(
                screen, name, stage_font,
                art.PAL["ink"] if active else (
                    art.PAL["ink_dim"] if passed else art.PAL["ink_faint"]),
                tick_x, label_y, 235 if active else 155)
            self._hud_rects.append(rect)
        pygame.draw.polygon(screen, art.PAL["accent"], [
            (int(px), ty - 4), (int(px + 4), ty),
            (int(px), ty + 4), (int(px - 4), ty)])
        pygame.draw.line(screen, art.mix(art.PAL["accent"], art.PAL["sky_low"], 0.2),
                         (px, ty - 8), (px, ty - 13), 1)
        rect = self._draw_text_left(screen, "YEAR 000", year_font,
                                    art.PAL["ink_dim"], x0, ty + 4, 195)
        self._hud_rects.append(rect)
        self._draw_text_right(screen, "YEAR 120", year_font,
                              art.PAL["ink_dim"], x1, ty + 4, 195)
        self._hud_rects.append(pygame.Rect(x0, ty - 14, max(1, x1 - x0), 28))

    # ---------------------------------------------------------------- animation

    def _stage_state(self):
        stage_seconds = self._cycle_seconds / 5.0
        elapsed = self._time + self._start_stage * stage_seconds
        cycle = elapsed % self._cycle_seconds
        progress = cycle / self._cycle_seconds
        pos = progress * 5.0
        stage = int(pos) % 5
        frac = pos - int(pos)
        blend = min(0.30, 10.0 / max(1.0, stage_seconds))
        nxt = (stage + 1) % 5
        alpha = 0
        if frac > 1.0 - blend:
            alpha = int(255 * ((frac - (1.0 - blend)) / blend))
        hud_stage = nxt if alpha > 127 else stage
        return stage, nxt, alpha, progress, hud_stage

    def _draw_overlays(self, screen, stage, detail):
        width, height = self._screen_size
        if detail <= 0.05:
            return
        # birds
        for i, (bx, by, speed, size) in enumerate(self._birds):
            x = (bx + self._time * speed * 0.002) % 1.02 * width
            y = by * height + math.sin(self._time * 0.25 + i) * height * 0.004
            s = max(1.6, 4.6 * size * (width / 1280.0))
            col = art.mix(art.PAL["sky_top"], (24, 44, 54), 0.45)
            for k in (-1, 1):
                pygame.draw.lines(screen, col, False, [
                    (x - s * 1.5 * k, y), (x - s * 0.5 * k, y + s * 0.55),
                    (x, y), (x + s * 0.5 * k, y + s * 0.55),
                    (x + s * 1.5 * k, y),
                ], max(1, int(1.0 * (width / 1280.0))))
        if stage < 1:
            return
        # river glints drift downstream
        count = int(len(self._river_glints) * detail)
        for i in range(count):
            x, y, w = self._river_glints[i]
            phase = (self._time * 0.10 + i * 0.17) % 1.0
            yy = y + (phase - 0.5) * max(2.0, w * 0.8)
            ln = max(1.0, w * (0.18 + 0.14 * math.sin(self._time * 0.9 + i)))
            alpha = 55 + int(45 * (0.5 + 0.5 * math.sin(self._time * 1.3 + i)))
            art.line(screen, (x - ln / 2, yy), (x + ln / 2, yy),
                     art.PAL["foam"], max(1, int(max(1.0, w * 0.06))), alpha)
        if stage < 4 or not self._city_lights:
            return
        # warm city/town/farm lights twinkle
        count = int(len(self._city_points) * detail)
        for i in range(count):
            x, y, phase, size = self._city_points[i]
            a = 110 + int(80 * (0.5 + 0.5 * math.sin(self._time * 0.9 + phase)))
            r = max(1, int(size * (width / 1280.0) * 1.8))
            pygame.draw.circle(screen, art.PAL["city"], (int(x), int(y)), r)
            art.circle(screen, x, y, r * 2.4, art.PAL["city"], min(80, a))

    # ---------------------------------------------------------------- update / render

    def update(self, dt: float):
        if self.manager is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._time += dt
        if self._auto_quality:
            self._quality_ema += (dt - self._quality_ema) * 0.06
            if self._quality_ema > (1.0 / 18.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    self._overlay_detail = max(0.32, self._overlay_detail - 0.22)
                    self._quality_timer = 0.0
            elif self._quality_ema < (1.0 / 30.0):
                self._quality_timer += dt
                if self._quality_timer >= 5.0:
                    self._overlay_detail = min(1.0, self._overlay_detail + 0.16)
                    self._quality_timer = 0.0
            else:
                self._quality_timer = 0.0

    def _resize(self, size):
        if self.manager is None or size == self._screen_size:
            return
        self._build(size)

    def render(self, screen):
        if self.manager is None:
            screen.fill(self._palette.get("sky_top", (20, 40, 60)))
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            if not self._stage_scaled:
                screen.fill(self._palette["sky_top"])
                return
            stage, nxt, alpha, progress, hud_stage = self._stage_state()
            self._stage, self._progress = stage, progress
            self._year = int(round(progress * 120))
            self._hud_stage = hud_stage
            base = self._stage_scaled[stage]
            screen.blit(base, (0, 0))
            if alpha > 0:
                other = self._stage_scaled[nxt]
                other.set_alpha(alpha)
                screen.blit(other, (0, 0))
                other.set_alpha(255)
            self._draw_overlays(screen, stage if alpha < 128 else nxt,
                                self._overlay_detail)
            self._draw_hud(screen, hud_stage, progress, self._year)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            if not self._last_error_logged:
                print(f"[Terraform] render error: {exc}")
                self._last_error_logged = True
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill(self._palette["sky_top"])
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, self._palette["accent"], rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("TERRAFORM // CONFIGURATION REFUSED", True,
                                self._palette["ink"])
            body = font.render((self.error or "unknown error")[:90], True,
                               self._palette["accent"])
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- stats

    def stats(self):
        if self.error or not self._stage_scaled:
            return {}
        width, height = self._screen_size
        corner = pygame.Rect(0, max(0, height - 32), 80, 32)
        corner_clear = all(not r.colliderect(corner) for r in self._hud_rects)
        return {
            "preset": self._preset,
            "layout": self._preset,
            "stage": self._stage,
            "stage_name": art.STAGE_NAMES[self._stage],
            "hud_stage": self._hud_stage,
            "year": self._year,
            "progress": self._progress,
            "cycle_seconds": self._cycle_seconds,
            "start_stage": self._start_stage,
            "time": self._time,
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "overlay_detail": self._overlay_detail,
            "seed": self.seed,
            "palette": self._palette_name,
            "hud": self._hud_mode,
            "show_timeline": self._show_timeline,
            "city_lights": self._city_lights,
            "lighthouse": self._lighthouse,
            "foreground": self._foreground,
            "mist": self._mist,
            "stages": len(self._stage_scaled),
            "stage_size": self._stage_scaled[0].get_size() if self._stage_scaled else (0, 0),
            "screen_size": self._screen_size,
            "hud_rects": [tuple(r) for r in self._hud_rects],
            "corner_clear": corner_clear,
        }
