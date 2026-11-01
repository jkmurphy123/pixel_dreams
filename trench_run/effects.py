"""Phase 3 action layer: turret tracking, bolts, impacts, TIE flybys, vents.

Everything here is decorative.  The ship cannot be damaged or destroyed; bolts
are rate-limited and impacts are local vector effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

from .assets import build_tie
from .meshes import transform_mesh, transform_point


@dataclass
class Bolt:
    pos: tuple[float, float, float]
    direction: tuple[float, float, float]
    speed: float
    life: float
    color: str
    length: float = 7.0


@dataclass
class Explosion:
    center: tuple[float, float, float]
    age: float = 0.0
    life: float = 0.65


@dataclass
class TieFlyby:
    pos: tuple[float, float, float]
    vel: tuple[float, float, float]
    age: float = 0.0
    life: float = 4.5
    yaw: float = 0.0


@dataclass
class Vent:
    origin: tuple[float, float, float]
    age: float = 0.0
    life: float = 2.6


@dataclass
class Flash:
    pos: tuple[float, float, float]
    age: float = 0.0
    life: float = 0.16


class ActionSystem:
    def __init__(self, world, seed: int, level: int = 1):
        self.world = world
        self.rng = random.Random((int(seed) ^ 0xA7C1) & 0x7FFFFFFF)
        self.level = int(level)
        self.time = 0.0
        self.bolts: list[Bolt] = []
        self.explosions: list[Explosion] = []
        self.flashes: list[Flash] = []
        self.tie: TieFlyby | None = None
        self.vents: list[Vent] = []
        self._tie_timer = self.rng.uniform(12.0, 24.0)
        self._vent_timer = self.rng.uniform(1.0, 3.0)
        self._ship_fire_timer = self.rng.uniform(2.0, 4.0)
        self._tie_mesh = build_tie()
        for mount in world.active_mounts():
            mount.cooldown = self.rng.uniform(1.5, 5.5)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def _sector_activity(self, ship_z: float) -> float:
        index = int(math.floor(ship_z / self.world.sector_length))
        plan = self.world.sectors.get(index)
        return plan.activity if plan is not None else 1.0

    def _aim_yaw(self, mount, ship_pos) -> float:
        dx = ship_pos[0] - mount.x
        dz = ship_pos[2] - mount.z
        if abs(dx) < 1e-6 and abs(dz) < 1e-6:
            return mount.base_yaw
        return math.degrees(math.atan2(dz, -dx))

    def _slew(self, current: float, target: float, rate: float) -> float:
        diff = (target - current + 180.0) % 360.0 - 180.0
        step = max(-rate, min(rate, diff))
        return current + step

    def _fire(self, mount, ship_pos, activity: float) -> None:
        muzzles = mount.muzzle_world()
        if not muzzles:
            return
        ox, oy, oz = muzzles[self.rng.randrange(len(muzzles))]
        miss = (self.rng.uniform(-3.0, 3.0) if self.level >= 2
                else self.rng.uniform(24.0, 80.0))
        side = -1.0 if self.rng.random() < 0.5 else 1.0
        tx = ship_pos[0] + side * miss
        ty = ship_pos[1] + self.rng.uniform(-4.0, 6.0)
        tz = ship_pos[2] + self.rng.uniform(-8.0, 8.0)
        dx, dy, dz = tx - ox, ty - oy, tz - oz
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-3:
            return
        direction = (dx / length, dy / length, dz / length)
        speed = self.rng.uniform(120.0, 170.0)
        life = min(1.4, length / speed)
        self.bolts.append(Bolt((ox, oy, oz), direction, speed, life,
                               "imperial"))
        self.flashes.append(Flash((ox, oy, oz)))
        mount.cooldown = (self.rng.uniform(1.2, 3.2) if self.level >= 2
                          else self.rng.uniform(3.8, 8.0)) / max(0.4, activity)

    def _spawn_tie(self, ship_pos) -> None:
        side = -1.0 if self.rng.random() < 0.5 else 1.0
        self.tie = TieFlyby(
            (ship_pos[0] - side * 150.0, self.world.depth + 18.0,
             ship_pos[2] + 220.0),
            (side * self.rng.uniform(24.0, 38.0), 0.0,
             -self.rng.uniform(2.0, 8.0)),
            yaw=self.rng.uniform(0.0, 360.0))

    def _spawn_vent(self, ship_z: float) -> None:
        index = int(math.floor(ship_z / self.world.sector_length))
        plan = self.world.sectors.get(index)
        if plan is None:
            return
        craters = [p for p in plan.props if p.kind == "crater"]
        if not craters:
            return
        c = self.rng.choice(craters)
        self.vents.append(Vent((c.x, c.y + 0.2, c.z)))

    def update(self, dt: float, ship) -> None:
        dt = max(0.0, min(0.1, float(dt)))
        if dt <= 0.0:
            return
        self.time += dt
        ship_pos = ship.pose()
        activity = self._sector_activity(ship_pos[2])

        for mount in self.world.active_mounts():
            if mount.kind == "dish_array":
                mount.yaw = (mount.yaw + 7.0 * dt * activity) % 360.0
                continue
            if mount.kind not in ("turret", "wall_gun"):
                continue
            if self.level <= 0:
                mount.yaw = (mount.base_yaw
                             + 12.0 * math.sin(self.time * 0.5 + mount.z))
                continue
            target = self._aim_yaw(mount, ship_pos)
            rate = (42.0 if self.level >= 2 else 20.0) * dt
            mount.yaw = self._slew(mount.yaw, target, rate)
            if self.level >= 1:
                mount.cooldown -= dt
                if mount.cooldown <= 0.0 and len(self.bolts) < 24:
                    self._fire(mount, ship_pos, activity)

        # Bolts, muzzle flashes, and local impacts.
        for bolt in self.bolts:
            bolt.pos = (bolt.pos[0] + bolt.direction[0] * bolt.speed * dt,
                        bolt.pos[1] + bolt.direction[1] * bolt.speed * dt,
                        bolt.pos[2] + bolt.direction[2] * bolt.speed * dt)
            bolt.life -= dt
        expired = [b for b in self.bolts if b.life <= 0.0]
        self.bolts = [b for b in self.bolts if b.life > 0.0]
        for b in expired:
            if len(self.explosions) < 2 and self.rng.random() < 0.55:
                self.explosions.append(Explosion(b.pos))
        for f in self.flashes:
            f.age += dt
        self.flashes = [f for f in self.flashes if f.age < f.life]
        for e in self.explosions:
            e.age += dt
        self.explosions = [e for e in self.explosions if e.age < e.life]

        # X-wing cannon fire at the busier level.
        if self.level >= 2:
            self._ship_fire_timer -= dt
            if self._ship_fire_timer <= 0.0:
                self._ship_fire_timer = self.rng.uniform(1.4, 3.0)
                cannons = [transform_point(p, ship.pose(), ship.yaw,
                                          ship.scale, ship.pitch, ship.roll)
                           for p in ship.asset.cannons]
                if cannons:
                    ox, oy, oz = cannons[self.rng.randrange(len(cannons))]
                    tx = ship_pos[0] + self.rng.uniform(-30.0, 30.0)
                    ty = self.world.depth
                    tz = ship_pos[2] + self.rng.uniform(80.0, 150.0)
                    dx, dy, dz = tx - ox, ty - oy, tz - oz
                    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                    self.bolts.append(Bolt(
                        (ox, oy, oz),
                        (dx / length, dy / length, dz / length),
                        190.0, 0.8, "rebel", length=5.0))

        self._tie_timer -= dt
        if self.level >= 2 and self.tie is None and self._tie_timer <= 0.0:
            self._spawn_tie(ship_pos)
            self._tie_timer = self.rng.uniform(18.0, 38.0)
        if self.tie is not None:
            t = self.tie
            t.pos = (t.pos[0] + t.vel[0] * dt,
                     t.pos[1] + t.vel[1] * dt,
                     t.pos[2] + t.vel[2] * dt)
            t.age += dt
            if t.age >= t.life:
                self.tie = None

        self._vent_timer -= dt
        if self._vent_timer <= 0.0:
            self._vent_timer = self.rng.uniform(2.5, 5.0)
            if len(self.vents) < 4:
                self._spawn_vent(ship_pos[2])
        for v in self.vents:
            v.age += dt
        self.vents = [v for v in self.vents if v.age < v.life]

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def draw_overlay(self, screen, projector, palette, ramp) -> None:
        # Bolts.
        for bolt in self.bolts:
            end = (bolt.pos[0] + bolt.direction[0] * bolt.length,
                   bolt.pos[1] + bolt.direction[1] * bolt.length,
                   bolt.pos[2] + bolt.direction[2] * bolt.length)
            p = projector.project_segment(bolt.pos, end)
            if p is None:
                continue
            (x1, y1), (x2, y2), z = p
            c = (palette.rebel if bolt.color == "rebel"
                 else palette.imperial)
            pygame_draw_line(screen, c, x1, y1, x2, y2, 2)
            hx = int(x2)
            hy = int(y2)
            pygame_draw_line(screen, (255, 255, 255), hx - 1, hy,
                             hx + 1, hy, 1)
            pygame_draw_line(screen, (255, 255, 255), hx, hy - 1,
                             hx, hy + 1, 1)

        # Muzzle flashes.
        for f in self.flashes:
            p = projector.project_point(f.pos)
            if p is None:
                continue
            x, y = int(p[0]), int(p[1])
            t = 1.0 - f.age / f.life
            c = palette.accent
            pygame_draw_line(screen, c, x - 4, y, x + 4, y, 1)
            pygame_draw_line(screen, c, x, y - 4, x, y + 4, 1)
            if t > 0.5:
                pygame_draw_line(screen, c, x - 2, y - 2, x + 2, y + 2, 1)
                pygame_draw_line(screen, c, x - 2, y + 2, x + 2, y - 2, 1)

        # Expanding vector explosions.
        for e in self.explosions:
            p = projector.project_point(e.center)
            if p is None:
                continue
            t = e.age / e.life
            scale = abs(projector.scale_at(max(1.0, p[2])))
            radius = int((6.0 + t * 55.0) * min(1.0, scale / 8.0))
            if radius < 2:
                continue
            color = tuple(max(0, int(c * (1.0 - t)))
                          for c in palette.accent)
            x, y = int(p[0]), int(p[1])
            pygame_draw_circle(screen, color, (x, y), radius, 1)
            if radius > 8:
                pygame_draw_circle(screen, color, (x, y), int(radius * 0.6), 1)
            for i in range(6):
                a = math.pi * 2 * i / 6 + t
                r2 = radius + 10
                pygame_draw_line(screen, color,
                                 x + int(math.cos(a) * radius),
                                 y + int(math.sin(a) * radius),
                                 x + int(math.cos(a) * r2),
                                 y + int(math.sin(a) * r2), 1)

        # TIE flyby.
        if self.tie is not None:
            t = self.tie
            mesh = transform_mesh(self._tie_mesh, t.pos, t.yaw, 1.15)
            for edge in mesh.edges:
                p = projector.project_segment(mesh.verts[edge.a],
                                              mesh.verts[edge.b])
                if p is None:
                    continue
                (x1, y1), (x2, y2), z = p
                pygame_draw_line(screen, palette.imperial, x1, y1, x2, y2, 1)

        # Vent plumes.
        for v in self.vents:
            t = v.age / v.life
            for k in range(3):
                x = v.origin[0] + (k - 1) * 1.4
                z = v.origin[2] + (k - 1) * 0.8
                for seg in range(4):
                    y0 = v.origin[1] + seg * 2.6 + t * 3.0
                    y1 = y0 + 1.4
                    p = projector.project_segment(
                        (x + math.sin(v.age * 2 + seg) * 0.5, y0, z),
                        (x + math.sin(v.age * 2 + seg + 0.7) * 0.5, y1, z))
                    if p is not None:
                        (x1, y1p), (x2, y2p), zz = p
                        c = ramp.role("detail", zz)
                        pygame_draw_line(screen, c, x1, y1p, x2, y2p, 1)

        # Beacon pulses: small vector crosses over static beacon posts.
        for obj in self.world.active_objects():
            if obj.kind != "beacon":
                continue
            p = projector.project_point((obj.center[0],
                                         obj.center[1] + 3.0,
                                         obj.center[2]))
            if p is None or p[2] > 260.0:
                continue
            phase = (self.time * 1.1 + obj.center[2] * 0.01) % 1.0
            if phase > 0.35:
                continue
            x, y = int(p[0]), int(p[1])
            pygame_draw_line(screen, palette.accent, x - 2, y, x + 2, y, 1)
            pygame_draw_line(screen, palette.accent, x, y - 2, x, y + 2, 1)


# Tiny wrappers keep the pygame import optional for pure simulation tests.
def pygame_draw_line(screen, color, x1, y1, x2, y2, width=1):
    import pygame
    pygame.draw.line(screen, color, (int(x1), int(y1)),
                     (int(x2), int(y2)), width)


def pygame_draw_circle(screen, color, center, radius, width=1):
    import pygame
    pygame.draw.circle(screen, color, center, radius, width)
