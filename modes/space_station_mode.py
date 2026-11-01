"""Space Station V — a double-ring wireframe station above a wireframe Earth.

The adapter parses and refuses the config, loads the coastline data once, owns
the two clocks (station spin and Earth rotation), and hands each frame to the
renderer/HUD.  As with every mode in this repo the controller owns the display;
this mode never touches disk during a frame and never calls set_mode().

The station is entirely procedural.  The Earth's coastlines come from a small
built JSON file generated from public-domain Natural Earth data by
``scripts/build_earth_coastlines.py`` — a missing file leaves the graticule
and the planet, never a blank screen.
"""
from __future__ import annotations

import math
import os
import random

import pygame

from space_station.earth import coastlines_path, load_coastlines
from space_station.framing import resolve_framing
from space_station.hud import HUD
from space_station.palette import PALETTE_NAMES, get_palette
from space_station.render import StationRenderer, effective_detail

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_COASTLINES = "data/earth_coastlines.json"
_DEFAULT_TITLE = "SPACE STATION V"
_DEFAULT_SUBTITLE = "EARTH ORBIT // DOCKING APPROACH"
_HUD_MODES = ("full", "minimal", "off")
_QUALITY_MODES = ("auto", "low", "medium", "high")


class SpaceStationMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self.renderer = None
        self.hud = None
        self._framing = None
        self._screen_size = None
        self._time = 0.0
        self._spin = 0.0
        self._earth_spin = 0.0
        self._palette_name = "orbital_white"
        self._quality = "medium"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._pinned_seed = None
        self._station_detail = 3
        self._station_rpm = 0.85
        self._earth_rotation_seconds = 300.0
        self._earth_tilt_deg = 23.4
        self._earth_spin_offset_deg = 0.0
        self._station_tilt_deg = 62.0
        self._station_yaw_deg = 26.0
        self._perspective = 0.72
        self._glow = 0.72
        self._scanlines = 8
        self._vignette = 0.30
        self._show_stars = True
        self._show_graticule = True
        self._show_continents = True
        self._hud_mode = "full"
        self._title = _DEFAULT_TITLE
        self._subtitle = _DEFAULT_SUBTITLE
        self._coastlines_file = _DEFAULT_COASTLINES

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
    def _text(config, key, default, max_length=48):
        value = config.get(key, default)
        if value is None:
            value = default
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        value = value.strip()
        if not value:
            value = default
        return value[:max_length]

    def _read_config(self):
        cfg = self.config
        seed = cfg.get("seed")
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
                raise ValueError("seed must be an integer in 0..2147483647 or null")
        self._pinned_seed = seed

        self._title = self._text(cfg, "title", _DEFAULT_TITLE, 32)
        self._subtitle = self._text(cfg, "subtitle", _DEFAULT_SUBTITLE, 52)
        self._station_detail = self._integer(cfg, "station_detail", 3, 1, 4)
        self._station_rpm = self._number(cfg, "station_spin_rpm", 0.85, 0.0, 3.0)
        self._earth_rotation_seconds = self._number(
            cfg, "earth_rotation_seconds", 300.0, 30.0, 3600.0)
        self._earth_tilt_deg = self._number(cfg, "earth_tilt_deg", 23.4, 0.0, 45.0)
        self._earth_spin_offset_deg = self._number(
            cfg, "earth_spin_offset_deg", 0.0, -180.0, 180.0)
        self._station_tilt_deg = self._number(
            cfg, "station_tilt_deg", 62.0, 15.0, 80.0)
        self._station_yaw_deg = self._number(
            cfg, "station_yaw_deg", 26.0, -60.0, 60.0)
        self._perspective = self._number(
            cfg, "perspective_strength", 0.72, 0.0, 1.0)
        self._glow = self._number(cfg, "glow_strength", 0.72, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 8.0, 0.0, 80.0))
        self._vignette = self._number(cfg, "vignette_strength", 0.30, 0.0, 1.0)
        self._show_stars = self._bool(cfg, "show_stars", True)
        self._show_graticule = self._bool(cfg, "show_graticule", True)
        self._show_continents = self._bool(cfg, "show_continents", True)
        self._coastlines_file = self._text(cfg, "coastlines_file",
                                           _DEFAULT_COASTLINES, 128)

        palette = str(cfg.get("palette", "orbital_white")).lower()
        if palette not in PALETTE_NAMES:
            raise ValueError("palette must be " + ", ".join(PALETTE_NAMES))
        self._palette_name = palette

        hud = str(cfg.get("hud", "full")).lower()
        if hud not in _HUD_MODES:
            raise ValueError("hud must be full, minimal, or off")
        self._hud_mode = hud

        quality = str(cfg.get("quality", "auto")).lower()
        if quality not in _QUALITY_MODES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"
        self._quality = "medium" if self._auto_quality else quality

        # The anchors and orientation are validated by resolve_framing, which
        # needs the screen size; enter() calls it and reports its error.

    def _next_seed(self):
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2 ** 31)

    # ---------------------------------------------------------------- lifecycle

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            size = manager.screen.get_size()
            self._screen_size = size
            self._framing = resolve_framing(self.config, size)
            self.seed = self._next_seed()
            palette = get_palette(self._palette_name)

            path = coastlines_path(_PROJECT_ROOT, self._coastlines_file)
            coastlines, notes = load_coastlines(path)
            for note in notes:
                print(f"[SpaceStation] coastline: {note}")
            if coastlines:
                print(f"[SpaceStation] coastlines={len(coastlines)} rings "
                      f"points={sum(len(ring) for ring in coastlines)} "
                      f"from {self._coastlines_file}")
            else:
                self.diagnostic = ("no coastlines loaded; drawing the graticule "
                                   "only")

            self.renderer = StationRenderer(
                size, palette, coastlines,
                station_detail=self._station_detail,
                station_tilt_deg=self._station_tilt_deg,
                station_yaw_deg=self._station_yaw_deg,
                earth_tilt_deg=self._earth_tilt_deg,
                perspective=self._perspective,
                glow_strength=self._glow,
                scanline_alpha=self._scanlines,
                vignette=self._vignette,
                quality=self._quality,
                seed=self.seed,
                show_stars=self._show_stars,
                show_graticule=self._show_graticule,
                show_continents=self._show_continents,
                hud_bands=self._hud_mode != "off",
            )
            self.hud = HUD(manager.cache, size, palette, mode=self._hud_mode,
                           title=self._title, subtitle=self._subtitle)
            # Start with a slightly turned wheel so the first frame is not a
            # perfectly symmetrical face-on view.
            self._spin = ((self.seed % 360) * 0.35) % 360.0
            self._earth_spin = self._earth_spin_offset_deg % 360.0
            self._time = 0.0
            self._quality_ema = 1.0 / 60.0
            self._quality_timer = 0.0
            self.error = None
            print(f"[SpaceStation] seed={self.seed} "
                  f"preset={self._framing.preset} "
                  f"detail={self._station_detail} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"rpm={self._station_rpm:.2f} "
                  f"earth_period={self._earth_rotation_seconds:.0f}s "
                  f"size={size[0]}x{size[1]}")
            if self.diagnostic:
                print(f"[SpaceStation] {self.diagnostic}")
        except (ValueError, TypeError, OSError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[SpaceStation] configuration error: {exc}")

    def exit(self):
        self.manager = None
        self.renderer = None
        self.hud = None
        self._framing = None
        self._screen_size = None
        self.error = None
        self.diagnostic = ""
        self._time = 0.0
        self._spin = 0.0
        self._earth_spin = 0.0

    def handle_event(self, event):
        """The controller owns keyboard/rotary input; this mode has none."""

    # ---------------------------------------------------------------- update

    def update(self, dt: float):
        if self.renderer is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._spin = (self._spin + self._station_rpm * 6.0 * dt) % 360.0
        self._earth_spin = (self._earth_spin
                            + 360.0 / self._earth_rotation_seconds * dt) % 360.0
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
        print(f"[SpaceStation] {self.diagnostic}")

    def _update_auto_quality(self, dt: float) -> None:
        """EMA frame-time controller with the same shape as the other 3D modes."""
        if not self._auto_quality:
            return
        self._quality_ema += (dt - self._quality_ema) * 0.06
        target = self._quality
        # Detail-first thresholds, tuned for this mode's slow motion: a
        # 1080p frame at about 47 ms keeps the medium wheel rather than
        # dropping to level 1 for four more frames per second.  Low is for a
        # genuinely slow host, and high is for a screen that can afford it.
        if self._quality == "high":
            if self._quality_ema > (1.0 / 26.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        elif self._quality == "medium":
            if self._quality_ema > (1.0 / 16.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "low"
            elif self._quality_ema < (1.0 / 30.0):
                self._quality_timer += dt
                if self._quality_timer >= 6.0:
                    target = "high"
            else:
                self._quality_timer = 0.0
        else:
            if self._quality_ema < (1.0 / 30.0):
                self._quality_timer += dt
                if self._quality_timer >= 4.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        if target != self._quality:
            self._quality_timer = 0.0
            self._set_quality(target)

    def _resize(self, size: tuple[int, int]) -> None:
        if size == self._screen_size or self.renderer is None:
            return
        self._screen_size = size
        self._framing = resolve_framing(self.config, size)
        self.renderer.resize(size, self._framing)
        if self.hud is not None:
            self.hud.resize(size)

    # ---------------------------------------------------------------- render

    def render(self, screen):
        if self.manager is None:
            screen.fill((2, 5, 13))
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            detail = effective_detail(self._station_detail, self._quality)
            self.renderer.render(screen, self._framing, self._spin,
                                 self._earth_spin, self._time, detail)
            self.hud.draw(screen, self._spin, self._earth_spin,
                          self._hud_stats(), self._time)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[SpaceStation] render error: {exc}")
            self._draw_error(screen)

    def _hud_stats(self) -> dict:
        return {
            "station_rpm": self._station_rpm,
            "earth_rotation_deg": self._earth_spin,
            "altitude_km": 402.0,
            "velocity_km_s": 7.71,
            "period_min": 92.4,
        }

    def _draw_error(self, screen):
        screen.fill((2, 5, 13))
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, (52, 140, 210), rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("SPACE STATION V // SIGNAL LOST", True,
                                (198, 232, 255))
            body = font.render((self.error or "unknown error")[:90], True,
                               (255, 170, 120))
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    def stats(self):
        if self.renderer is None or self.error:
            return {}
        result = self.renderer.stats()
        result.update({
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "station_detail": effective_detail(self._station_detail,
                                               self._quality),
            "framing": self._framing.preset if self._framing else "",
            "spin_deg": self._spin,
            "earth_rotation_deg": self._earth_spin,
        })
        return result
