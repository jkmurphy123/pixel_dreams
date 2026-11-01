"""The Long Archive — a deep-space vault of monoliths.

The mode adapter: it parses and refuses the config, loads the optional lore
once, resolves the wall layout, owns the quality controller, and hands the frame
to the cached renderer and the restrained HUD.  As with every mode in this repo
the controller owns the display; this module never calls set_mode and never does
disk I/O on the frame loop.

The visual is the reviewed one: one flat archive wall, the current slab at 75%
of the display width, a light bar traveling across it, and one line of the
inscription resolving into the translation below.  The neighbouring slabs are
dim and run off the sides, so the wall continues beyond the frame.

Config (all optional; the registry carries the same defaults for the panel):
  title            header line
  subtitle         second line, shown only when hud="full"
  seed             integer or null; null = a new scene on entry
  palette          "bone" | "amber" | "verdigris"
  orientation      "auto" | "landscape" | "portrait"
  hud              "full" | "minimal" | "off"
  quality          "auto" | "low" | "medium" | "high"
  slab_count       total slabs in the vault, 7..12 (the wall shows three)
  drift_speed      camera sway, 0..4 px/s; 0 holds the wall still
  text_speed       characters per second on the translation, 4..30
  text_file        optional JSON list of one-line entries; built-in lore if absent
  show_labels      the catalog mark and the SLAB 04 label
  bar_period       seconds for a full light-bar sweep, 4..20
  glow_strength    0..1
  scanline_alpha   0..40
  vignette_strength 0..1
"""
from __future__ import annotations

import json
import math
import os
import random

import pygame

from long_archive.glyphs import LORE
from long_archive.hud import LongArchiveHUD
from long_archive.layout import build_wall, resolve_layout
from long_archive.palette import PALETTE_NAMES, get_palette
from long_archive.renderer import QUALITY_NAMES, WallRenderer

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_TITLE = "THE LONG ARCHIVE"
_DEFAULT_SUBTITLE = "VAULT 9 // MONOLITH FIELD"
_HUD_MODES = ("full", "minimal", "off")
_ORIENTATIONS = ("auto", "landscape", "portrait")
_MAX_SEED = 0x7FFFFFFF


class LongArchiveMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self.layout = None
        self.renderer = None
        self.hud = None

        self._screen_size = None
        self._time = 0.0
        self._palette = None
        self._palette_name = "bone"
        self._title = _DEFAULT_TITLE
        self._subtitle = _DEFAULT_SUBTITLE
        self._orientation = "auto"
        self._hud_mode = "full"
        self._quality_setting = "auto"
        self._quality = "medium"
        self._auto_quality = True
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._pinned_seed = None
        self._slab_count = 9
        self._drift_speed = 2.0
        self._text_speed = 14.0
        self._bar_period = 8.0
        self._show_labels = True
        self._text_file = ""
        self._glow = 0.55
        self._scanline_alpha = 6
        self._vignette = 0.42
        self._lore = list(LORE)

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
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be in {lo}..{hi}")
        return value

    @staticmethod
    def _bool(config, key, default):
        value = config.get(key, default)
        if value is None:
            value = default
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        return value

    @staticmethod
    def _text(config, key, default, max_length=64, allow_empty=False):
        value = config.get(key, default)
        if value is None:
            value = default
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        value = value.strip()
        if not value and not allow_empty:
            value = default
        return value[:max_length]

    def _read_config(self):
        cfg = self.config
        self._title = self._text(cfg, "title", _DEFAULT_TITLE, 32)
        self._subtitle = self._text(cfg, "subtitle", _DEFAULT_SUBTITLE, 52)

        palette = str(cfg.get("palette", "bone")).strip().lower()
        if palette not in PALETTE_NAMES:
            raise ValueError("palette must be " + ", ".join(PALETTE_NAMES))
        self._palette_name = palette
        self._palette = get_palette(palette)

        orientation = str(cfg.get("orientation", "auto")).strip().lower()
        if orientation not in _ORIENTATIONS:
            raise ValueError("orientation must be " + ", ".join(_ORIENTATIONS))
        self._orientation = orientation

        hud = str(cfg.get("hud", "full")).strip().lower()
        if hud not in _HUD_MODES:
            raise ValueError("hud must be " + ", ".join(_HUD_MODES))
        self._hud_mode = hud

        quality = str(cfg.get("quality", "auto")).strip().lower()
        if quality not in ("auto",) + QUALITY_NAMES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"
        self._quality = "medium" if self._auto_quality else quality
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0

        seed = cfg.get("seed")
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise ValueError("seed must be an integer or null")
            if not 0 <= seed <= _MAX_SEED:
                raise ValueError(f"seed must be in 0..{_MAX_SEED} or null")
        self._pinned_seed = seed

        self._slab_count = self._integer(cfg, "slab_count", 9, 7, 12)
        self._drift_speed = self._number(cfg, "drift_speed", 2.0, 0.0, 4.0)
        self._text_speed = self._number(cfg, "text_speed", 14.0, 4.0, 30.0)
        self._bar_period = self._number(cfg, "bar_period", 8.0, 4.0, 20.0)
        self._show_labels = self._bool(cfg, "show_labels", True)
        self._text_file = self._text(cfg, "text_file", "", 256,
                                     allow_empty=True)
        self._glow = self._number(cfg, "glow_strength", 0.55, 0.0, 1.0)
        self._scanline_alpha = int(round(
            self._number(cfg, "scanline_alpha", 6.0, 0.0, 40.0)))
        self._vignette = self._number(cfg, "vignette_strength", 0.42, 0.0, 1.0)

    def _next_seed(self):
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    def _load_lore(self):
        """Load the optional one-line entries; fall back to the built-ins."""
        if not self._text_file:
            return list(LORE), ""
        path = self._text_file
        if not os.path.isabs(path):
            path = os.path.join(_PROJECT_ROOT, path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, list):
                raise ValueError("expected a JSON list")
            lines = [str(item).strip() for item in raw
                     if isinstance(item, str) and item.strip()]
            if not lines:
                raise ValueError("the list is empty")
            return [line[:120] for line in lines], ""
        except (OSError, ValueError, TypeError) as exc:
            return list(LORE), (f"text_file {self._text_file} unavailable "
                                f"({exc}); using built-in lore")

    # ------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            size = manager.screen.get_size()
            self._screen_size = (int(size[0]), int(size[1]))
            self.layout = resolve_layout(self._screen_size, self._orientation)
            self.seed = self._next_seed()
            self._lore, note = self._load_lore()
            self.diagnostic = ""
            if note:
                self.diagnostic = note
            self._time = 0.0
            self._quality = ("medium" if self._auto_quality
                             else self._quality_setting)
            self.renderer = WallRenderer(
                self._screen_size, self._palette, self.layout,
                build_wall(self.layout, self.seed), manager.cache, self.seed,
                self._quality, self._lore, self._show_labels,
                self._bar_period, self._text_speed, self._drift_speed,
                self._glow, self._scanline_alpha, self._vignette)
            focus = min(4, self._slab_count)
            self.hud = LongArchiveHUD(
                manager.cache, self._screen_size, self.layout, self._palette,
                self._hud_mode, self._title, self._subtitle,
                entries=1204, focus_index=focus,
                slab_count=self._slab_count, bar_period=self._bar_period,
                drift_speed=self._drift_speed)
            self.error = None
            print(f"[LongArchive] seed={self.seed} "
                  f"layout={self.layout.name} "
                  f"slabs={len(self.renderer.slabs)} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]} "
                  f"lore={len(self._lore)}")
            if note:
                print(f"[LongArchive] lore: {note}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.renderer = None
            self.hud = None
            print(f"[LongArchive] configuration error: {exc}")

    def exit(self):
        self.manager = None
        self.layout = None
        self.renderer = None
        self.hud = None
        self._screen_size = None
        self._time = 0.0
        self.error = None
        self.diagnostic = ""
        self.seed = None

    def handle_event(self, event):
        """The controller owns input; the archive has no controls."""

    # ---------------------------------------------------------------- update

    def update(self, dt: float):
        if self.manager is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._time += dt
        self._update_auto_quality(dt)

    def _set_quality(self, quality: str) -> None:
        if quality == self._quality:
            return
        old = self._quality
        self._quality = quality
        if self.renderer is not None:
            self.renderer.set_quality(quality)
        self.diagnostic = f"auto quality {old} -> {quality}"
        print(f"[LongArchive] {self.diagnostic}")

    def _update_auto_quality(self, dt: float) -> None:
        """EMA frame-time controller with the same shape as the other 3D modes."""
        if not self._auto_quality:
            return
        self._quality_ema += (dt - self._quality_ema) * 0.06
        target = self._quality
        if self._quality == "high":
            if self._quality_ema > (1.0 / 40.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        elif self._quality == "medium":
            if self._quality_ema > (1.0 / 24.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "low"
            elif self._quality_ema < (1.0 / 58.0):
                self._quality_timer += dt
                if self._quality_timer >= 6.0:
                    target = "high"
            else:
                self._quality_timer = 0.0
        else:
            if self._quality_ema < (1.0 / 32.0):
                self._quality_timer += dt
                if self._quality_timer >= 4.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        if target != self._quality:
            self._quality_timer = 0.0
            self._set_quality(target)

    # ---------------------------------------------------------------- render

    def _resize(self, size) -> None:
        self._screen_size = (int(size[0]), int(size[1]))
        self.layout = resolve_layout(self._screen_size, self._orientation)
        self.renderer = WallRenderer(
            self._screen_size, self._palette, self.layout,
            build_wall(self.layout, self.seed), self.manager.cache, self.seed,
            self._quality, self._lore, self._show_labels,
            self._bar_period, self._text_speed, self._drift_speed,
            self._glow, self._scanline_alpha, self._vignette)
        focus = min(4, self._slab_count)
        self.hud = LongArchiveHUD(
            self.manager.cache, self._screen_size, self.layout, self._palette,
            self._hud_mode, self._title, self._subtitle, entries=1204,
            focus_index=focus, slab_count=self._slab_count,
            bar_period=self._bar_period, drift_speed=self._drift_speed)

    def render(self, screen):
        if self.manager is None:
            screen.fill((0, 0, 0))
            return
        size = screen.get_size()
        if tuple(size) != self._screen_size and self.error is None:
            try:
                self._resize(size)
            except (ValueError, TypeError, OSError, pygame.error) as exc:
                self.error = str(exc)
                print(f"[LongArchive] resize error: {exc}")
        if self.error:
            self._draw_error(screen)
            return
        if self.renderer is None:
            screen.fill(self._palette.bg_top if self._palette else (1, 4, 10))
            return
        self.renderer.render(screen, self._time)
        if self.hud is not None:
            self.hud.draw(screen, self.renderer.stats())

    def _draw_error(self, screen) -> None:
        p = self._palette
        bg = p.bg_top if p is not None else (1, 4, 10)
        fg = p.hud if p is not None else (198, 218, 236)
        warn = p.warm if p is not None else (242, 200, 121)
        screen.fill(bg)
        try:
            base = max(18, int(min(screen.get_width(), screen.get_height()) * 0.05))
            title = pygame.font.SysFont("dejavusansmono", base + 4, bold=True)
            body = pygame.font.SysFont("dejavusansmono", base)
            screen.blit(title.render("THE LONG ARCHIVE // SIGNAL LOST", True,
                                     fg), (24, 24))
            screen.blit(body.render((self.error or "unknown error")[:90], True,
                                    warn), (24, 24 + base + 12))
        except pygame.error:
            pass

    def stats(self) -> dict:
        if self.renderer is None or self.error:
            return {}
        data = self.renderer.stats()
        data.update({
            "seed": self.seed,
            "layout": self.layout.name if self.layout else "",
            "slabs": self._slab_count,
            "focus_slab": min(4, self._slab_count),
            "lore_lines": len(self._lore),
            "hud": self._hud_mode,
            "text_file": self._text_file,
        })
        return data
