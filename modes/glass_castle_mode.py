"""The Glass Castle — a crystal keep under an aurora.

The mode adapter: it parses and refuses the config, resolves the reviewed
composition for the real screen, owns the quality controller, and hands the
frame to the cached renderer and the restrained HUD.  As with every mode here
the controller owns the display; this module never calls set_mode and never does
disk I/O on the frame loop.

The visual is the reviewed vista: a castle grown from crystal on a snow ledge,
under an aurora that moves across a minute and brightens every 47 s; two snow
layers, warm windows, detached shards, and the aurora reflected inside the
glass.

Config (all optional; the registry carries the same defaults for the panel):
  title              header line
  subtitle           optional second line, shown only when hud="full"
  seed               integer or null; null = a new scene on entry
  palette            "ice" | "aurora" | "rose"
  orientation        "auto" | "landscape" | "portrait"
  hud                "full" | "minimal" | "off"
  quality            "auto" | "low" | "medium" | "high"
  aurora             curtains and the glass reflection
  snow               both parallax snow layers
  camera_drift       lateral drift, 0..2 px/s; 0 holds the camera
  window_lights      the warm windows; the gate stays lit
  shard_count        0..10 detached shards
  aurora_period      seconds for the curtain/hue cycle, 20..180
  window_flicker     0..1; 0 holds the windows steady
  reflection_strength 0..1
  snow_speed         px/s fall multiplier, 4..24
  glow_strength      0..1 bloom
  scanline_alpha     0..40
  vignette_strength  0..1
"""
from __future__ import annotations

import math
import random

import pygame

from glasscastle.hud import GlassCastleHUD
from glasscastle.layout import ORIENTATIONS, resolve_layout
from glasscastle.palette import PALETTE_NAMES, get_palette
from glasscastle.renderer import QUALITY_NAMES, GlassCastleRenderer

_DEFAULT_TITLE = "THE GLASS CASTLE"
_DEFAULT_SUBTITLE = ""
_HUD_MODES = ("full", "minimal", "off")
_MAX_SEED = 0x7FFFFFFF


class GlassCastleMode:
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
        self._palette_name = "ice"
        self._title = _DEFAULT_TITLE
        self._subtitle = _DEFAULT_SUBTITLE
        self._orientation = "auto"
        self._hud_mode = "minimal"
        self._quality_setting = "auto"
        self._quality = "medium"
        self._auto_quality = True
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._pinned_seed = None

        self._settings = {}

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

    def _read_config(self) -> None:
        cfg = self.config
        self._title = self._text(cfg, "title", _DEFAULT_TITLE, 32)
        self._subtitle = self._text(cfg, "subtitle", _DEFAULT_SUBTITLE, 56,
                                    allow_empty=True)

        palette = str(cfg.get("palette", "ice")).strip().lower()
        if palette not in PALETTE_NAMES:
            raise ValueError("palette must be " + ", ".join(PALETTE_NAMES))
        self._palette_name = palette
        self._palette = get_palette(palette)

        orientation = str(cfg.get("orientation", "auto")).strip().lower()
        if orientation not in ORIENTATIONS:
            raise ValueError("orientation must be " + ", ".join(ORIENTATIONS))
        self._orientation = orientation

        hud = str(cfg.get("hud", "minimal")).strip().lower()
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

        self._settings = {
            "aurora": self._bool(cfg, "aurora", True),
            "snow": self._bool(cfg, "snow", True),
            "window_lights": self._bool(cfg, "window_lights", True),
            "camera_drift": self._number(cfg, "camera_drift", 0.5, 0.0, 2.0),
            "shard_count": self._integer(cfg, "shard_count", 6, 0, 10),
            "aurora_period": self._number(cfg, "aurora_period", 60.0,
                                          20.0, 180.0),
            "window_flicker": self._number(cfg, "window_flicker", 1.0,
                                           0.0, 1.0),
            "reflection_strength": self._number(cfg, "reflection_strength",
                                                0.72, 0.0, 1.0),
            "snow_speed": self._number(cfg, "snow_speed", 12.0, 4.0, 24.0),
            "glow_strength": self._number(cfg, "glow_strength", 0.36,
                                          0.0, 1.0),
            "scanline_alpha": int(round(
                self._number(cfg, "scanline_alpha", 4.0, 0.0, 40.0))),
            "vignette_strength": self._number(cfg, "vignette_strength",
                                              0.34, 0.0, 1.0),
        }

    def _next_seed(self) -> int:
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    # ------------------------------------------------------------- lifecycle

    def enter(self, manager) -> None:
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            size = manager.screen.get_size()
            self._screen_size = (int(size[0]), int(size[1]))
            self.layout = resolve_layout(self._screen_size, self._orientation)
            self.seed = self._next_seed()
            self._time = 0.0
            self._quality = ("medium" if self._auto_quality
                             else self._quality_setting)
            self.renderer = GlassCastleRenderer(
                self._screen_size, self._palette, self.layout, self.seed,
                self._quality, self._settings)
            self.hud = GlassCastleHUD(
                manager.cache, self.layout, self._palette, self._hud_mode,
                self._title, self._subtitle,
                camera_drift=self._settings["camera_drift"],
                snow_layers=2 if self._settings["snow"] else 0)
            self.error = None
            self.diagnostic = ""
            print(f"[GlassCastle] seed={self.seed} "
                  f"layout={self.layout.name} "
                  f"palette={self._palette_name} "
                  f"shards={len(self.renderer.scene.shards)} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={self._screen_size[0]}x{self._screen_size[1]}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            self.renderer = None
            self.hud = None
            print(f"[GlassCastle] configuration error: {exc}")

    def exit(self) -> None:
        self.manager = None
        if self.renderer is not None:
            self.renderer.close()
        self.layout = None
        self.renderer = None
        self.hud = None
        self._screen_size = None
        self._time = 0.0
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self._settings = {}

    def handle_event(self, event) -> None:
        """The controller owns input; the vista has no controls."""

    # ---------------------------------------------------------------- update

    def update(self, dt: float) -> None:
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
        print(f"[GlassCastle] {self.diagnostic}")

    def _update_auto_quality(self, dt: float) -> None:
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
        self.renderer = GlassCastleRenderer(
            self._screen_size, self._palette, self.layout, self.seed,
            self._quality, self._settings)
        self.hud = GlassCastleHUD(
            self.manager.cache, self.layout, self._palette, self._hud_mode,
            self._title, self._subtitle,
            camera_drift=self._settings["camera_drift"],
            snow_layers=2 if self._settings["snow"] else 0)

    def render(self, screen) -> None:
        if self.manager is None:
            screen.fill((0, 0, 0))
            return
        size = screen.get_size()
        if tuple(size) != self._screen_size and self.error is None:
            try:
                self._resize(size)
            except (ValueError, TypeError, OSError, pygame.error) as exc:
                self.error = str(exc)
                print(f"[GlassCastle] resize error: {exc}")
        if self.error:
            self._draw_error(screen)
            return
        if self.renderer is None:
            screen.fill(self._palette.bg_top if self._palette else (3, 5, 13))
            return
        self.renderer.render(screen, self._time)
        if self.hud is not None:
            self.hud.draw(screen)

    def _draw_error(self, screen) -> None:
        p = self._palette
        bg = p.bg_top if p is not None else (3, 5, 13)
        fg = p.hud if p is not None else (214, 234, 238)
        warn = p.warm if p is not None else (255, 196, 128)
        screen.fill(bg)
        try:
            base = max(18, int(min(screen.get_width(),
                                   screen.get_height()) * 0.05))
            title = pygame.font.SysFont("dejavusansmono", base + 4, bold=True)
            body = pygame.font.SysFont("dejavusansmono", base)
            screen.blit(title.render("THE GLASS CASTLE // SIGNAL LOST", True,
                                     fg), (24, 24))
            screen.blit(body.render((self.error or "unknown error")[:90],
                                    True, warn), (24, 24 + base + 12))
        except pygame.error:
            pass

    def stats(self) -> dict:
        if self.renderer is None or self.error:
            return {}
        data = self.renderer.stats()
        data.update({
            "seed": self.seed,
            "layout": self.layout.name if self.layout else "",
            "palette": self._palette_name,
            "hud": self._hud_mode,
            "quality_setting": self._quality_setting,
            "shard_count": self._settings.get("shard_count", 0),
            "aurora": self._settings.get("aurora", True),
            "snow": self._settings.get("snow", True),
            "camera_drift": self._settings.get("camera_drift", 0.0),
        })
        return data
