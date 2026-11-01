"""Cyberspace Matrix — a neon wireframe expanse inspired by Gibson's Neuromancer.

The mode adapter.  It parses and refuses the config, builds the seeded world and
route, owns the adaptive-quality controller, and hands the frame to the
renderer/HUD.  As with every mode in this repo, the controller owns the display
and the adapter never touches disk or a display mode.

Config is intentionally a small set of dials: the seed, the flight speed and leg
length, the lattice spacing, city and construct density, draw distance, field of
view, palette, HUD flavour, glow, scanlines, vignette, traffic, labels and the
technobabble event rate.  The registry (`modes_registry.json`) carries the same
defaults and help text the panel shows.
"""
from __future__ import annotations

import math
import os
import random

import pygame

from cyberspace.camera import CameraRig, Route
from cyberspace.hud import HUD
from cyberspace.landmarks import landmark_path, load_landmarks
from cyberspace.matrix import Matrix
from cyberspace.palette import PALETTE_NAMES, get_palette
from cyberspace.render import CyberspaceRenderer

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_LANDMARKS = "data/cyberspace_landmarks.json"
_DEFAULT_TITLE = "CYBERSPACE MATRIX"
_DEFAULT_SUBTITLE = "ICEBREAKER DECK // PASSIVE SCAN"
_HUD_MODES = ("full", "minimal", "off")
_QUALITY_MODES = ("auto", "low", "medium", "high")


class CyberspaceMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self.matrix = None
        self.route = None
        self.camera = None
        self.renderer = None
        self.hud = None
        self.landmarks = None
        self._last_landmark_label = None
        self._screen_size = None
        self._time = 0.0
        self._speed = 16.0
        self._cell = 80.0
        self._z_max = 392.0
        self._quality = "medium"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._pinned_seed = None
        self._last_label_count = 0

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

        self._speed = self._number(cfg, "travel_speed", 16.0, 3.0, 60.0)
        self._blocks = self._integer(cfg, "blocks_per_leg", 5, 2, 12)
        self._cell = self._number(cfg, "street_spacing", 80.0, 48.0, 160.0)
        self._city_density = self._number(cfg, "city_density", 0.85, 0.10, 1.0)
        self._geometric_detail = self._integer(cfg, "geometric_detail", 2, 1, 4)
        self._height_scale = self._number(cfg, "building_height", 1.0, 0.30, 2.50)
        self._construct_density = self._number(cfg, "construct_density", 0.55,
                                               0.0, 1.0)
        self._draw_distance = self._number(cfg, "draw_distance", 620.0,
                                           180.0, 900.0)
        self._fov = self._number(cfg, "fov", 74.0, 50.0, 110.0)
        self._glow = self._number(cfg, "glow_strength", 0.90, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 12.0, 0.0, 80.0))
        self._vignette = self._number(cfg, "vignette_strength", 0.35, 0.0, 1.0)
        self._show_labels = self._bool(cfg, "show_labels", True)
        self._show_traffic = self._bool(cfg, "show_traffic", True)
        self._show_reticle = self._bool(cfg, "show_reticle", True)
        self._crisp_lines = self._bool(cfg, "crisp_lines", True)
        self._show_landmarks = self._bool(cfg, "show_landmarks", True)
        self._show_landmark_overlay = self._bool(cfg, "landmark_overlay", True)
        path = cfg.get("landmarks_file", _DEFAULT_LANDMARKS)
        if path is None:
            path = _DEFAULT_LANDMARKS
        if not isinstance(path, str):
            raise ValueError("landmarks_file must be a path")
        self._landmarks_file = path.strip()
        self._event_rate = self._number(cfg, "event_rate_per_min", 7.0, 0.0, 20.0)

        palette = str(cfg.get("palette", "neuromancer")).strip().lower()
        if palette not in PALETTE_NAMES:
            raise ValueError("palette must be one of: " + ", ".join(PALETTE_NAMES))
        self._palette_name = palette

        hud = str(cfg.get("hud", "full")).strip().lower()
        if hud not in _HUD_MODES:
            raise ValueError("hud must be full, minimal, or off")
        self._hud_mode = hud

        quality = str(cfg.get("quality", "auto")).strip().lower()
        if quality not in _QUALITY_MODES:
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"
        self._quality = "medium" if self._auto_quality else quality
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0

        self._title = self._text(cfg, "title", _DEFAULT_TITLE, 40)
        self._subtitle = self._text(cfg, "subtitle", _DEFAULT_SUBTITLE, 56)

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
            self.seed = self._next_seed()
            palette = get_palette(self._palette_name)
            z_low = self._cell * 0.32
            z_high = self._cell * 2.70
            level = self._cell * 0.70
            self._z_max = z_high
            blocks_min = max(2, self._blocks - 1)
            blocks_max = min(12, self._blocks + 1)

            self.matrix = Matrix(
                self.seed, palette, cell=self._cell,
                density=self._city_density,
                height_scale=self._height_scale,
                construct_density=self._construct_density,
                level=level, draw_distance=self._draw_distance,
                detail_level=self._geometric_detail,
            )
            self.landmarks = []
            self._last_landmark_label = None
            if self._show_landmarks and self._landmarks_file:
                path = landmark_path(_PROJECT_ROOT, self._landmarks_file)
                loaded, notes = load_landmarks(
                    path, self._cell,
                    detail_level=min(5, self._geometric_detail + 1))
                self.landmarks = loaded
                for note in notes:
                    print(f"[Cyberspace] landmark: {note}")
                if loaded:
                    self.matrix.reserve_cells(
                        cell for landmark in loaded for cell in landmark.cells)
                    print(f"[Cyberspace] landmarks={len(loaded)} "
                          f"from {self._landmarks_file}")
            home = None
            home_radius = 0.0
            if self.landmarks:
                xs = [lm.center[0] for lm in self.landmarks]
                ys = [lm.center[1] for lm in self.landmarks]
                home = (sum(xs) / len(xs), sum(ys) / len(ys))
                spread = max(math.hypot(lm.center[0] - home[0],
                                        lm.center[1] - home[1])
                             for lm in self.landmarks)
                home_radius = max(520.0, spread + 120.0)
            self.route = Route(
                self.seed, cell=self._cell, speed=self._speed,
                blocks_min=blocks_min, blocks_max=blocks_max,
                z_low=z_low, z_high=z_high, level=level,
                home=home, home_radius=home_radius,
            )
            self.camera = CameraRig(self._fov)
            self.camera.set_size(size)
            self.camera.snap(self.route)
            if self._auto_quality:
                # Detail is the point of this mode, so auto starts at medium on
                # every screen and only steps down if the frame really cannot
                # carry it.  The old pixel-count shortcut made a 1080p wall
                # start at the low-detail budget, which read as a resolution
                # drop even though the surface was native.
                self._quality = "medium"
                self._quality_ema = 1.0 / 60.0
                self._quality_timer = 0.0
            self.renderer = CyberspaceRenderer(
                size, palette, glow_strength=self._glow,
                scanline_alpha=self._scanlines, vignette=self._vignette,
                quality=self._quality, seed=self.seed,
                draw_distance=self._draw_distance,
                show_traffic=self._show_traffic,
                hud_bands=self._hud_mode != "off",
                crisp_lines=self._crisp_lines,
            )
            self.hud = HUD(
                manager.cache, size, mode=self._hud_mode, seed=self.seed,
                title=self._title, subtitle=self._subtitle,
                event_rate_per_min=self._event_rate,
                show_labels=self._show_labels, show_reticle=self._show_reticle,
                show_landmark_overlay=self._show_landmark_overlay,
            )
            self.hud.note_axis(self.route, initial=True)
            self._time = 0.0
            self.error = None
            self._last_label_count = 0
            print(f"[Cyberspace] seed={self.seed} palette={self._palette_name} "
                  f"speed={self._speed:.1f} cell={self._cell:.0f} "
                  f"detail={self._geometric_detail} "
                  f"quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''} "
                  f"size={size[0]}x{size[1]}")
            if self.diagnostic:
                print(f"[Cyberspace] {self.diagnostic}")
        except (ValueError, TypeError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Cyberspace] configuration error: {exc}")

    def exit(self):
        self.manager = None
        self.matrix = None
        self.route = None
        self.camera = None
        self.renderer = None
        self.hud = None
        self.landmarks = None
        self._last_landmark_label = None
        self._screen_size = None
        self.error = None
        self.diagnostic = ""
        self._time = 0.0
        self._last_label_count = 0

    def handle_event(self, event):
        """The controller owns keyboard/rotary input; this mode has none."""

    # ---------------------------------------------------------------- update

    def update(self, dt: float):
        if self.route is None or self.camera is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self.route.advance(dt)
        self.camera.update(dt, self.route)
        self.hud.update(dt, self.route, self.renderer.ice_distance)
        nearest = self.renderer.nearest_landmark
        if nearest is not None and nearest[2] < 420.0:
            label = nearest[0]
            if label != self._last_landmark_label:
                self.hud.push(f"LANDMARK // {label}", "ok")
                self._last_landmark_label = label
        elif nearest is None:
            self._last_landmark_label = None
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
        print(f"[Cyberspace] {self.diagnostic}")

    def _update_auto_quality(self, dt: float) -> None:
        """EMA frame-time controller, with the same shape as the other 3D mode."""
        if not self._auto_quality:
            return
        self._quality_ema += (dt - self._quality_ema) * 0.06
        target = self._quality
        # Detail-first thresholds: medium is allowed down to about 24 fps, and
        # only a genuinely slow frame drops to low.  The previous 60 fps target
        # spent a 1080p wall in the low-detail budget even when it looked fine.
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

    def _resize(self, size: tuple[int, int]) -> None:
        if size == self._screen_size or self.camera is None:
            return
        self._screen_size = size
        self.camera.set_size(size)
        if self.renderer is not None:
            self.renderer.resize(size)
        if self.hud is not None:
            self.hud.resize(size)

    # ---------------------------------------------------------------- render

    def render(self, screen):
        if self.manager is None:
            screen.fill((3, 2, 10))
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            self.renderer.render(screen, self.camera, self.matrix,
                                 self.route, self._time,
                                 landmarks=self.landmarks)
            hud_stats = {
                "palette": self.renderer.palette,
                "speed": self._speed,
                "cell": self._cell,
                "z_max": self._z_max,
                "ice_distance": self.renderer.ice_distance,
                "nearest_landmark": self.renderer.nearest_landmark,
                "nearest_landmarks": self.renderer.nearest_landmarks,
                "nearest_landmark_object": self.renderer.nearest_landmark_object,
                "quality": self._quality,
                "segments": self.renderer.last_segments,
                "objects": self.renderer.last_objects,
                "constructs": self.renderer.last_constructs,
            }
            self._last_label_count = len(self.renderer.last_labels)
            self.hud.draw(screen, self.camera, self.route, hud_stats,
                          self.renderer.last_labels, self._time)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Cyberspace] render error: {exc}")
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill((4, 2, 12))
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, (52, 140, 210), rect, 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("CYBERSPACE // LINK REFUSED", True,
                                (190, 235, 255))
            body = font.render((self.error or "unknown error")[:90], True,
                               (255, 170, 120))
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    # ---------------------------------------------------------------- reporting

    def stats(self):
        if self.renderer is None:
            return {}
        stats = {
            "segments": self.renderer.last_segments,
            "objects": self.renderer.last_objects,
            "constructs": self.renderer.last_constructs,
            "landmarks": self.renderer.last_landmarks,
            "landmark_count": len(self.landmarks or ()),
            "nearest_landmark": self.renderer.nearest_landmark,
            "nearest_landmarks": self.renderer.nearest_landmarks,
            "landmarks_file": self._landmarks_file,
            "geometric_detail": self._geometric_detail,
            "labels": self._last_label_count,
            "quality": self._quality,
            "auto_quality": self._auto_quality,
            "edge_cap": self.renderer.edge_cap,
            "seed": self.seed,
            "axis": self.route.axis_name if self.route else None,
            "axis_changes": self.route.axis_changes if self.route else 0,
            "camera": self.camera.pose() if self.camera else None,
            "ice_distance": self.renderer.ice_distance,
        }
        if self.matrix is not None:
            stats.update(self.matrix.stats())
        return stats
