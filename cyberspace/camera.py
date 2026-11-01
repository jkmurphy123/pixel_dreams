"""The viewpoint: a route that flies one axis at a time, and a camera that
follows it with a little lag and bank.

The route deliberately moves on the street lattice.  A leg is a whole number of
blocks, so every turn happens exactly on an intersection and the camera never
flies through a building.  Directions alternate between the two horizontal
axes, with a vertical leg every second turn to change altitude.
"""
from __future__ import annotations

import math
import random

AXIS_X, AXIS_Y, AXIS_Z = 0, 1, 2
AXIS_NAMES = ("X", "Y", "Z")
_AXIS_LETTER = ("X", "Y", "Z")


def _wrap_angle(a: float) -> float:
    """Shortest signed representation of an angle, in (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


class Route:
    """An endless orthogonal flight path over the street lattice.

    The target position is exact and moves at a constant speed; the camera can
    lag behind it a little to round off the corners.  ``advance`` is the only
    thing that mutates the route, which makes it straightforward to test.
    """

    def __init__(self, seed: int, cell: float = 80.0, speed: float = 16.0,
                 blocks_min: int = 4, blocks_max: int = 7,
                 z_low: float = 26.0, z_high: float = 216.0,
                 level: float = 56.0, home: tuple[float, float] | None = None,
                 home_radius: float = 0.0):
        self.seed = int(seed) & 0x7FFFFFFF
        self.rng = random.Random(self.seed ^ 0x51A7E)
        self.cell = float(cell)
        self.speed = float(speed)
        self.blocks_min = max(1, int(blocks_min))
        self.blocks_max = max(self.blocks_min, int(blocks_max))
        self.level = float(level)
        self.z_low = float(z_low)
        self.z_high = float(z_high)
        if self.z_high < self.z_low:
            self.z_low, self.z_high = self.z_high, self.z_low
        self.home = (float(home[0]), float(home[1])) if home is not None else None
        self.home_radius = max(0.0, float(home_radius or 0.0))

        self.target = [0.0, 0.0, self.z_low]
        self.axis = AXIS_X
        self.direction = 1
        self.leg_kind = "horizontal"
        self.leg_total = 1.0
        self.leg_remaining = 1.0
        self.leg_id = 0
        self.axis_changes = 0
        self.clock = 0.0
        self.travelled = 0.0

        self.aim_yaw = 0.0
        self.aim_pitch = -0.18
        self._leg_yaw = 0.0
        self._view_offset = 0.0
        self._pitch_offset = 0.0
        self._spin_rate = 0.0

        self._begin_horizontal(first=True, axis=AXIS_X, direction=1)

    # ------------------------------------------------------------------ legs

    def _begin_horizontal(self, first: bool = False, axis: int | None = None,
                          direction: int | None = None) -> None:
        if axis is None:
            # Coming out of a vertical leg: pick either horizontal axis, so the
            # route does not always turn the same way.
            axis = self.rng.choice((AXIS_X, AXIS_Y))
        if direction is None:
            direction = self.rng.choice((-1, 1))
        # With landmarks, the flight is softly bounded to their district:
        # once it wanders past home_radius, the next leg points back toward
        # the centroid instead of continuing away forever.  The axis-by-axis
        # lattice movement is preserved.
        if self.home is not None and math.hypot(
                self.home[0] - self.target[0],
                self.home[1] - self.target[1]) > self.home_radius:
            dx = self.home[0] - self.target[0]
            dy = self.home[1] - self.target[1]
            if abs(dx) >= abs(dy):
                axis = AXIS_X
                direction = 1 if dx > 0 else -1
            else:
                axis = AXIS_Y
                direction = 1 if dy > 0 else -1
        previous_axis = self.axis
        self.axis = int(axis)
        self.direction = int(direction)
        self.leg_kind = "horizontal"
        blocks = self.rng.randint(self.blocks_min, self.blocks_max)
        self.leg_total = max(self.cell, blocks * self.cell)
        self.leg_remaining = self.leg_total
        self.leg_id += 1
        if not first and self.axis != previous_axis:
            self.axis_changes += 1

        # The camera looks a little off the direction of travel, and the offset
        # is chosen per leg: a centred vanishing point looks like a diagram.
        self._leg_yaw = math.atan2(1.0 if self.axis == AXIS_Y else 0.0,
                                   1.0 if self.axis == AXIS_X else 0.0)
        if direction < 0:
            self._leg_yaw += math.pi
        self._view_offset = self.rng.uniform(-0.10, 0.10)
        self._pitch_offset = self.rng.uniform(-0.035, 0.035)
        self._spin_rate = 0.0
        self.aim_yaw = self._leg_yaw + self._view_offset
        self.aim_pitch = self._horizontal_pitch() + self._pitch_offset

    def _begin_vertical(self) -> None:
        self.axis = AXIS_Z
        going_up = self.target[2] < (self.z_low + self.z_high) * 0.5
        self.direction = 1 if going_up else -1
        destination = self.z_high if going_up else self.z_low
        self.leg_kind = "vertical"
        self.leg_total = max(1.0, abs(destination - self.target[2]))
        self.leg_remaining = self.leg_total
        self.leg_id += 1
        self.axis_changes += 1

        # The climb is where the camera gets to show off: a slow yaw drift while
        # the rings of the shaft pass the lens.  Descending turns the other way.
        self._spin_rate = self.direction * self.rng.uniform(0.09, 0.20)
        self.aim_pitch = self.direction * math.radians(24.0)

    def _horizontal_pitch(self) -> float:
        span = max(1.0, self.z_high - self.z_low)
        altitude = _clamp((self.target[2] - self.z_low) / span, 0.0, 1.0)
        # Street level looks gently down the canyon; high altitude looks further
        # down on the lattice.  Both keep the horizon high in frame.
        return -0.145 - 0.085 * altitude

    def _finish_leg(self) -> None:
        # Snap the target to the exact end of the leg.  The target is advanced
        # in exact increments, so this only removes accumulated float dust.
        if self.leg_kind == "horizontal":
            index = AXIS_X if self.axis == AXIS_X else AXIS_Y
            self.target[index] = round(self.target[index] / self.cell) * self.cell
        else:
            self.target[2] = self.z_high if self.direction > 0 else self.z_low
        self.leg_remaining = 0.0
        if self.leg_kind == "horizontal":
            self._horizontals_done = getattr(self, "_horizontals_done", 0) + 1
            if self._horizontals_done % 2 == 0:
                self._begin_vertical()
            else:
                other = AXIS_Y if self.axis == AXIS_X else AXIS_X
                self._begin_horizontal(axis=other,
                                       direction=self.rng.choice((-1, 1)))
        else:
            self._begin_horizontal()

    def advance(self, dt: float) -> None:
        """Move the target along the current leg; dt is clamped by the mode."""
        if dt <= 0.0:
            return
        self.clock += dt
        step = self.speed * dt

        # A very large dt can finish more than one short leg; loop so the state
        # stays coherent instead of overshooting into the next one.
        guard = 0
        while step > 1e-9 and guard < 8:
            guard += 1
            if step >= self.leg_remaining:
                step -= self.leg_remaining
                index = self.axis
                self.target[index] += self.direction * self.leg_remaining
                self.travelled += self.leg_remaining
                self._finish_leg()
            else:
                self.target[self.axis] += self.direction * step
                self.leg_remaining -= step
                self.travelled += step
                step = 0.0

        if self.axis == AXIS_Z:
            # Keep the spin going while the target is vertical.
            self.aim_yaw += self._spin_rate * dt
            self.aim_pitch = self.direction * math.radians(24.0) + \
                0.02 * math.sin(self.clock * 0.7)
        else:
            self.aim_yaw = (self._leg_yaw + self._view_offset +
                            0.035 * math.sin(self.clock * 0.11 + self.seed))
            self.aim_pitch = self._horizontal_pitch() + self._pitch_offset + \
                0.012 * math.sin(self.clock * 0.17)

    # ------------------------------------------------------------------ info

    @property
    def axis_name(self) -> str:
        return _AXIS_LETTER[self.axis]

    def axis_vector(self) -> tuple[float, float, float]:
        if self.axis == AXIS_X:
            return (float(self.direction), 0.0, 0.0)
        if self.axis == AXIS_Y:
            return (0.0, float(self.direction), 0.0)
        return (0.0, 0.0, float(self.direction))

    @property
    def altitude_frac(self) -> float:
        span = max(1.0, self.z_high - self.z_low)
        return _clamp((self.target[2] - self.z_low) / span, 0.0, 1.0)

    @property
    def leg_fraction(self) -> float:
        return 1.0 - _clamp(self.leg_remaining / max(1e-6, self.leg_total),
                            0.0, 1.0)


class CameraRig:
    """A pinhole camera with world Z up, eased yaw/pitch and a bank on turns."""

    def __init__(self, fov_deg: float = 74.0):
        self.fov = math.radians(_clamp(float(fov_deg), 30.0, 120.0))
        self.pos = [0.0, 0.0, 0.0]
        self.prev_pos = [0.0, 0.0, 0.0]
        self.velocity = [0.0, 0.0, 0.0]
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.sw = 1
        self.sh = 1
        self.cx = 0.5
        self.cy = 0.5
        self.focal = 1.0
        self._fwd = (1.0, 0.0, 0.0)
        self._right = (0.0, 1.0, 0.0)
        self._up = (0.0, 0.0, 1.0)
        self._recalc_focal()
        self._recalc_basis()

    def set_size(self, size: tuple[int, int]) -> None:
        self.sw = max(1, int(size[0]))
        self.sh = max(1, int(size[1]))
        self.cx = self.sw * 0.5
        self.cy = self.sh * 0.5
        self._recalc_focal()

    def _recalc_focal(self) -> None:
        # Use the screen diagonal, so the same fov feels similar in portrait and
        # landscape instead of cropping one axis to a tunnel.
        diagonal = math.hypot(self.sw, self.sh)
        self.focal = 0.5 * diagonal / math.tan(0.5 * self.fov)

    def _recalc_basis(self) -> None:
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        fwd = (cp * cy, cp * sy, sp)
        right0 = (sy, -cy, 0.0)
        up0 = (-sp * cy, -sp * sy, cp)
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        right = (right0[0] * cr + up0[0] * sr,
                 right0[1] * cr + up0[1] * sr,
                 right0[2] * cr + up0[2] * sr)
        up = (-right0[0] * sr + up0[0] * cr,
              -right0[1] * sr + up0[1] * cr,
              -right0[2] * sr + up0[2] * cr)
        self._fwd, self._right, self._up = fwd, right, up

    def snap(self, route: Route) -> None:
        """Place the camera exactly on the route, aimed where the route aims."""
        self.pos = list(route.target)
        self.prev_pos = list(route.target)
        self.velocity = [0.0, 0.0, 0.0]
        self.yaw = route.aim_yaw
        self.pitch = route.aim_pitch
        self.roll = 0.0
        self._recalc_basis()

    def update(self, dt: float, route: Route) -> None:
        if dt <= 0.0:
            return
        self.prev_pos = list(self.pos)

        # Position lag: enough to round a corner through the open intersection,
        # not enough to clip a building on either side of the street.
        k = 1.0 - math.exp(-dt / 0.42)
        for i in (0, 1, 2):
            self.pos[i] += (route.target[i] - self.pos[i]) * k

        # Yaw and pitch chase the route's aim.  Yaw uses the shortest path so a
        # turn never spins the long way around.
        self.yaw += _wrap_angle(route.aim_yaw - self.yaw) * \
            (1.0 - math.exp(-dt / 1.15))
        self.pitch += (route.aim_pitch - self.pitch) * \
            (1.0 - math.exp(-dt / 1.05))

        # Bank into the turn, with a small idle sway so the camera reads as a
        # drone rather than a tripod.
        yaw_error = _wrap_angle(route.aim_yaw - self.yaw)
        roll_target = _clamp(-yaw_error * 0.55, -0.26, 0.26)
        roll_target += 0.018 * math.sin(route.clock * 0.37 + 1.3)
        self.roll += (roll_target - self.roll) * \
            (1.0 - math.exp(-dt / 0.55))

        inv = 1.0 / dt
        self.velocity = [(self.pos[i] - self.prev_pos[i]) * inv
                         for i in (0, 1, 2)]
        self._recalc_basis()

    # ------------------------------------------------------------------ view

    def view(self, p) -> tuple[float, float, float]:
        dx = p[0] - self.pos[0]
        dy = p[1] - self.pos[1]
        dz = p[2] - self.pos[2]
        r, u, f = self._right, self._up, self._fwd
        return (dx * r[0] + dy * r[1] + dz * r[2],
                dx * u[0] + dy * u[1] + dz * u[2],
                dx * f[0] + dy * f[1] + dz * f[2])

    def project_view(self, v) -> tuple[float, float]:
        inv = self.focal / max(1e-4, v[2])
        return (self.cx + v[0] * inv, self.cy - v[1] * inv)

    def project(self, p) -> tuple[float, float] | None:
        v = self.view(p)
        if v[2] <= 1e-4:
            return None
        return self.project_view(v)

    def sphere_visible(self, center, radius: float) -> bool:
        """Cheap frustum reject for whole objects.

        Not exact, but it only has to reject objects clearly behind or beside
        the camera; the line pass still clips against the near plane and the
        screen.
        """
        v = self.view(center)
        if v[2] + radius < 0.5:
            return False
        if v[2] <= 0.5:
            return True
        half_w = self.cx / max(1e-4, self.focal) * v[2] + radius
        half_h = self.cy / max(1e-4, self.focal) * v[2] + radius
        return abs(v[0]) <= half_w and abs(v[1]) <= half_h

    def pose(self) -> dict:
        return {
            "pos": tuple(round(v, 3) for v in self.pos),
            "yaw_deg": round(math.degrees(self.yaw), 2),
            "pitch_deg": round(math.degrees(self.pitch), 2),
            "roll_deg": round(math.degrees(self.roll), 2),
            "velocity": tuple(round(v, 3) for v in self.velocity),
        }
