"""Autopiloted X-wing motion for Trench Run."""
from __future__ import annotations

import math
import random

from .meshes import ShipAsset, build_xwing, transform_mesh, transform_point

WINGSPAN = 11.0


class Ship:
    """Spring-damped altitude/cross-track weave, never a flyable sim."""

    def __init__(self, seed: int, trench_width: float, trench_depth: float,
                 weave_amount: float = 0.65, scale: float = 1.0):
        self.rng = random.Random(int(seed) & 0x7FFFFFFF)
        self.width = float(trench_width)
        self.depth = float(trench_depth)
        self.weave = max(0.0, min(1.0, float(weave_amount)))
        self.scale = max(0.5, min(2.0, float(scale)))
        self.asset: ShipAsset = build_xwing()

        self.z = 0.0
        self.x = 0.0
        self.neutral_y = (3.0 + (self.depth + 16.0)) * 0.5
        self.y = self.neutral_y
        self.vx = 0.0
        self.vy = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.time = 0.0
        self._tx = 0.0
        self._ty = self.neutral_y
        self._timer_x = 0.0
        self._timer_y = 0.0
        self._pick_x()
        self._pick_y()

    @property
    def limit_x(self) -> float:
        return max(0.5, self.width * 0.5 - WINGSPAN * self.scale * 0.5 - 2.5)

    def _pick_x(self) -> None:
        if self.weave <= 0.0:
            self._tx = 0.0
        else:
            self._tx = self.rng.uniform(-self.limit_x, self.limit_x) * self.weave
        self._timer_x = self.rng.uniform(3.0, 8.0)

    def _pick_y(self) -> None:
        lo = 3.0
        hi = self.depth + 16.0
        if self.weave <= 0.0:
            self._ty = self.neutral_y
        else:
            # Bias toward the trench, with occasional rises above the rim.
            u = self.rng.random() ** 1.45
            self._ty = self.neutral_y + (u * 2.0 - 1.0) * (hi - lo) * 0.5 * self.weave
            self._ty = max(lo, min(hi, self._ty))
        self._timer_y = self.rng.uniform(2.0, 6.0)

    def update(self, dt: float, speed: float) -> None:
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self.time += dt
        self.z += speed * dt

        self._timer_x -= dt
        if self._timer_x <= 0.0:
            self._pick_x()
        self._timer_y -= dt
        if self._timer_y <= 0.0:
            self._pick_y()

        ax = (self._tx - self.x) * 2.4 - self.vx * 2.9
        ay = (self._ty - self.y) * 2.0 - self.vy * 2.8
        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.x < -self.limit_x:
            self.x, self.vx = -self.limit_x, max(0.0, self.vx)
        elif self.x > self.limit_x:
            self.x, self.vx = self.limit_x, min(0.0, self.vx)
        if self.y < 3.0:
            self.y, self.vy = 3.0, max(0.0, self.vy)
        elif self.y > self.depth + 16.0:
            self.y, self.vy = self.depth + 16.0, min(0.0, self.vy)

        target_roll = max(-25.0, min(25.0, -self.vx * 4.2))
        target_pitch = max(-12.0, min(12.0, -self.vy * 2.8))
        target_yaw = max(-6.0, min(6.0, self.vx * 1.4))
        k = 1.0 - math.exp(-dt * 7.0)
        self.roll += (target_roll - self.roll) * k
        self.pitch += (target_pitch - self.pitch) * k
        self.yaw += (target_yaw - self.yaw) * k

    def pose(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z

    def mesh(self):
        return transform_mesh(self.asset.mesh, self.pose(), self.yaw,
                              self.scale, self.pitch, self.roll)

    def engine_points(self):
        return [transform_point(p, self.pose(), self.yaw, self.scale,
                                self.pitch, self.roll)
                for p in self.asset.engines]
