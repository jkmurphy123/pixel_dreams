"""Trench Run — Phases 1–4.

Registered as type `trenchrun` (slot 61 in configs/modes_config_vert.json).  The
mode owns no display; the controller/mode manager owns the one pygame window.
This adapter validates config, builds the seeded world, drives the
X-wing/action simulation, and renders through the vector renderer + HUD.
"""
from __future__ import annotations

import math
import random

import pygame

from trench_run.effects import ActionSystem
from trench_run.hud import HUD
from trench_run.projection import Projector, resolve_camera
from trench_run.render import VectorRenderer
from trench_run.ship import Ship
from trench_run.world import TrenchWorld


class TrenchRunMode:
    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.manager = None
        self.error = None
        self.diagnostic = ""
        self.seed = None
        self._screen_size = None
        self._projector = None
        self._renderer = None
        self._world = None
        self._ship = None
        self._action = None
        self._hud = None
        self._action_level = 1
        self._hud_mode = "minimal"
        self._phosphor = 0.10
        self._time = 0.0
        self._cam_x = 0.0
        self._cam_y = 0.0
        self._scroll_speed = 30.0
        self._camera_follow = 0.30
        self._neutral_y = 14.5
        self._width = 28.0
        self._depth = 10.0
        self._weave = 0.65
        self._ship_scale = 1.0
        self._density = 0.6
        self._sector_length = 384.0
        self._quality = "medium"
        self._quality_setting = "auto"
        self._auto_quality = True
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0
        self._fill_mode = "panel"
        self._palette = "vector_blue"
        self._glow = 0.55
        self._depth_fade = 0.75
        self._vignette = 0.30
        self._scanlines = 0
        self._show_stars = True
        self._pinned_seed = None

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
    def _bool(config, key, default):
        value = config.get(key, default)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false")
        return value

    def _read_config(self):
        cfg = self.config
        seed = cfg.get("seed")
        if seed is not None:
            if type(seed) is not int or not 0 <= seed <= 0x7FFFFFFF:
                raise ValueError("seed must be an integer in 0..2147483647 or null")
        self._pinned_seed = seed
        self._width = self._number(cfg, "trench_width", 28.0, 18.0, 48.0)
        self._depth = self._number(cfg, "trench_depth", 10.0, 4.0, 22.0)
        self._ship_scale = self._number(cfg, "ship_scale", 1.20, 0.5, 2.0)
        min_width = 11.0 * self._ship_scale + 10.0
        if self._width < min_width:
            self.diagnostic = (f"trench_width raised from {self._width:.1f} "
                               f"to {min_width:.1f} to fit the X-wing")
            self._width = min_width
        self._weave = self._number(cfg, "weave_amount", 0.65, 0.0, 1.0)
        self._scroll_speed = self._number(cfg, "scroll_speed", 30.0, 4.0, 120.0)
        self._camera_follow = self._number(cfg, "camera_follow", 0.30, 0.0, 0.80)
        self._density = self._number(cfg, "terrain_density", 0.6, 0.0, 1.0)
        self._sector_length = self._number(cfg, "sector_length", 384.0,
                                           192.0, 768.0)
        self._glow = self._number(cfg, "glow_strength", 0.75, 0.0, 1.0)
        self._depth_fade = self._number(cfg, "depth_fade", 0.75, 0.0, 1.0)
        self._vignette = self._number(cfg, "vignette_strength", 0.30, 0.0, 1.0)
        self._scanlines = int(self._number(cfg, "scanline_alpha", 0.0, 0.0, 80.0))
        self._show_stars = self._bool(cfg, "show_stars", True)

        fill = str(cfg.get("fill_mode", "panel")).lower()
        if fill not in ("xray", "panel", "solid"):
            raise ValueError("fill_mode must be xray, panel, or solid")
        self._fill_mode = fill

        palette = str(cfg.get("palette", "vector_blue")).lower()
        if palette not in ("vector_blue", "phosphor_green", "arcade", "amber", "mono"):
            raise ValueError("palette must be vector_blue, phosphor_green, arcade, amber, or mono")
        self._palette = palette

        quality = str(cfg.get("quality", "auto")).lower()
        if quality not in ("auto", "low", "medium", "high"):
            raise ValueError("quality must be auto, low, medium, or high")
        self._quality_setting = quality
        self._auto_quality = quality == "auto"
        self._quality = "medium" if self._auto_quality else quality
        self._quality_ema = 1.0 / 60.0
        self._quality_timer = 0.0

        # Parsed here so an invalid value is caught even though Phase 1 does
        # not yet draw action or a HUD.
        action = cfg.get("action_level", 1)
        if type(action) is not int or not 0 <= action <= 2:
            raise ValueError("action_level must be 0, 1, or 2")
        self._action_level = action
        hud = str(cfg.get("hud", "minimal")).lower()
        if hud not in ("off", "minimal"):
            raise ValueError("hud must be off or minimal")
        self._hud_mode = hud
        self._phosphor = self._number(cfg, "phosphor_trail", 0.10, 0.0, 0.5)

    def _next_seed(self):
        if self._pinned_seed is not None:
            return self._pinned_seed
        return random.SystemRandom().randrange(2**31)

    def enter(self, manager):
        self.exit()
        self.manager = manager
        try:
            self._read_config()
            size = manager.screen.get_size()
            self._screen_size = size
            self.seed = self._next_seed()
            self._neutral_y = (3.0 + (self._depth + 16.0)) * 0.5

            params = resolve_camera(self.config, size)
            self._projector = Projector(size, params)
            self._ship = Ship(self.seed, self._width, self._depth,
                              self._weave, self._ship_scale)
            self._cam_x = self._ship.x
            self._cam_y = self._ship.y
            self._projector.recalibrate((self._ship.x, self._neutral_y,
                                         self._ship.z))
            self._projector.set_camera(self._cam_x, self._cam_y, self._ship.z)

            self._renderer = VectorRenderer(
                size,
                palette_name=self._palette,
                depth_fade=self._depth_fade,
                glow_strength=self._glow,
                fill_mode=self._fill_mode,
                vignette=self._vignette,
                scanline_alpha=self._scanlines,
                quality=self._quality,
                show_stars=self._show_stars,
                seed=self.seed,
                phosphor_trail=self._phosphor,
            )
            far_side = 1.0 if params.yaw_deg >= 0 else -1.0
            self._world = TrenchWorld(self.seed, self._width, self._depth,
                                      self._density, far_side=far_side,
                                      sector_length=self._sector_length)
            self._world.ensure(self._ship.z)
            self._action = ActionSystem(self._world, self.seed,
                                        self._action_level)
            self._hud = HUD(self._renderer.palette, self._hud_mode)
            self._time = 0.0
            self.error = None
            print(f"[Trench] seed={self.seed} preset={params.preset} "
                  f"yaw={params.yaw_deg:.1f} pitch={params.pitch_deg:.1f} "
                  f"perspective={params.perspective:.2f} quality={self._quality}"
                  f"{' (auto)' if self._auto_quality else ''}")
            if self.diagnostic:
                print(f"[Trench] {self.diagnostic}")
        except (ValueError, TypeError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Trench] configuration error: {exc}")

    def exit(self):
        self.manager = None
        self._projector = None
        self._renderer = None
        self._world = None
        self._ship = None
        self._action = None
        self._hud = None
        self._screen_size = None
        self.error = None
        self.diagnostic = ""

    def handle_event(self, event):
        """The controller owns keyboard/rotary input."""

    def update(self, dt: float):
        if self._ship is None or self._world is None or self.error:
            return
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self._ship.update(dt, self._scroll_speed)
        self._world.ensure(self._ship.z, max_new=1)
        self._action.update(dt, self._ship)
        self._update_auto_quality(dt)
        self._time += dt

        # Partial camera follow: 0 leaves the rig fixed and shows the full
        # weave; 0.8 follows most of it.  The low-pass keeps target changes
        # from snapping.
        follow = self._camera_follow
        desired_x = self._ship.x * follow
        desired_y = self._neutral_y + (self._ship.y - self._neutral_y) * follow
        k = 1.0 - math.exp(-dt / 2.5)
        self._cam_x += (desired_x - self._cam_x) * k
        self._cam_y += (desired_y - self._cam_y) * k
        self._projector.set_camera(self._cam_x, self._cam_y, self._ship.z)

    def _set_quality(self, quality: str) -> None:
        if quality == self._quality:
            return
        old = self._quality
        self._quality = quality
        if self._renderer is not None:
            self._renderer.set_quality(quality)
        self.diagnostic = f"auto quality {old} -> {quality}"
        print(f"[Trench] {self.diagnostic}")

    def _update_auto_quality(self, dt: float) -> None:
        """EMA frame-time controller with separate downgrade/upgrade timers."""
        if not self._auto_quality:
            return
        alpha = 0.06
        self._quality_ema += (dt - self._quality_ema) * alpha
        target = self._quality
        if self._quality == "high":
            if self._quality_ema > (1.0 / 52.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        elif self._quality == "medium":
            if self._quality_ema > (1.0 / 50.0):
                self._quality_timer += dt
                if self._quality_timer >= 2.0:
                    target = "low"
            elif self._quality_ema < (1.0 / 74.0):
                self._quality_timer += dt
                if self._quality_timer >= 6.0:
                    target = "high"
            else:
                self._quality_timer = 0.0
        else:
            if self._quality_ema < (1.0 / 72.0):
                self._quality_timer += dt
                if self._quality_timer >= 4.0:
                    target = "medium"
            else:
                self._quality_timer = 0.0
        if target != self._quality:
            self._quality_timer = 0.0
            self._set_quality(target)

    def _resize(self, size: tuple[int, int]):
        if size == self._screen_size:
            return
        self._screen_size = size
        params = resolve_camera(self.config, size)
        self._projector = Projector(size, params)
        # Calibrate against the live ship pose, exactly as enter() does. Calibrating against
        # x=0 here shifted the framing by the ship's current cross-track offset on a resize.
        self._projector.recalibrate((self._ship.x, self._neutral_y, self._ship.z))
        self._projector.set_camera(self._cam_x, self._cam_y, self._ship.z)
        self._renderer.resize(size)

    def render(self, screen):
        if self.manager is None:
            screen.fill((2, 4, 10))
            return
        if self.error:
            self._draw_error(screen)
            return
        try:
            self._resize(screen.get_size())
            self._renderer.render(screen, self._projector, self._world,
                                  self._ship, self._time, action=self._action)
            # The world rounds sector_length to a whole number of chunks; use its value so the
            # HUD's sector number cannot disagree with the sector actually being streamed.
            sector = int(self._ship.z // self._world.sector_length)
            self._hud.draw(screen, self._projector, self._ship, sector,
                           self._action_level)
        except (ValueError, pygame.error) as exc:
            self.error = str(exc)
            print(f"[Trench] render error: {exc}")
            self._draw_error(screen)

    def _draw_error(self, screen):
        screen.fill((2, 4, 10))
        rect = pygame.Rect(40, 40, max(80, screen.get_width() - 80),
                           max(80, screen.get_height() - 80))
        pygame.draw.rect(screen, (52, 140, 210), rect, 1)
        pygame.draw.line(screen, (255, 150, 70),
                         (rect.left + 16, rect.top + 16),
                         (rect.left + 56, rect.top + 16), 1)
        if pygame.font.get_init():
            font = pygame.font.Font(None, 26)
            title = font.render("TRENCH RUN // UNAVAILABLE", True,
                                (190, 235, 255))
            body = font.render((self.error or "unknown error")[:90], True,
                               (255, 170, 120))
            screen.blit(title, (rect.left + 20, rect.top + 28))
            screen.blit(body, (rect.left + 20, rect.top + 62))

    def stats(self):
        if self._renderer is None:
            return {}
        return {
            "objects": self._renderer.last_objects,
            "segments": self._renderer.last_segments,
            "faces": self._renderer.last_faces,
            "world_edges": self._renderer.last_world_edges,
            "edge_cap": self._renderer.edge_cap,
            "chunks": len(self._world.chunks) if self._world else 0,
            "ship": self._ship.pose() if self._ship else None,
            "quality": self._quality,
            "auto_quality": self._auto_quality,
        }
