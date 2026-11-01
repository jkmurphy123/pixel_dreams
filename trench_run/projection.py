"""Camera, projection, and framing for the trench-run mode.

The camera is one rig with a continuous blend between parallel axonometric
projection (perspective_strength = 0) and a pinhole chase camera (1).

World axes: +X across the trench, +Y up, +Z forward along the trench.  The
trench floor is Y=0; the rim is Y=trench_depth.

The projection uses a linear denominator so straight edges stay straight at
every blend value:

    den = (1 - s) * DREF + s * zv
    K   = (1 - s) * DREF + s * ZREF
    sx  = SW/2 + PPU * K * xv / den + frame_dx
    sy  = SH/2 - PPU * K * yv / den + frame_dy

K is calibrated once from the neutral ship pose.  It keeps the hero exactly
PPU pixels per unit at that depth for every perspective strength, so changing
the blend changes depth falloff rather than the ship's size.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Optional, Sequence

import pygame


DREF = 140.0
CAM_BACK = 46.0
CAM_HEIGHT = 56.0
NEAR = 1.0

# Landscape / square / portrait presets from the design doc.
PRESETS = {
    "landscape": {
        "yaw": 27.0,
        "pitch": 24.0,
        "zoom": 0.85,
        "anchor_x": 0.46,
        "anchor_y": 0.78,
    },
    "square": {
        "yaw": 27.0,
        "pitch": 24.0,
        "zoom": 0.95,
        "anchor_x": 0.48,
        "anchor_y": 0.61,
    },
    "portrait": {
        "yaw": 21.0,
        "pitch": 24.0,
        "zoom": 0.72,
        "anchor_x": 0.50,
        "anchor_y": 0.60,
    },
}


def aspect_class(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 1.2:
        return "landscape"
    if aspect <= 0.85:
        return "portrait"
    return "square"


def _number(config: dict, key: str, default: float, lo: float, hi: float) -> float:
    value = config.get(key, default)
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    value = float(value)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{key} must be finite and in {lo}..{hi}")
    return value


@dataclass(frozen=True)
class CameraParams:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    perspective: float
    zoom: float
    anchor_x: float
    anchor_y: float
    diagonal_flip: bool
    preset: str
    width: int
    height: int


def resolve_camera(config: dict, size: tuple[int, int]) -> CameraParams:
    """Resolve orientation presets plus explicit per-key overrides."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("screen size must be positive")

    requested = str(config.get("orientation", "auto")).lower()
    if requested not in ("auto", "landscape", "portrait", "square"):
        raise ValueError("orientation must be auto, landscape, portrait, or square")
    preset_name = aspect_class(width, height) if requested == "auto" else requested
    preset = PRESETS[preset_name]

    yaw = _number(config, "view_yaw_deg", preset["yaw"], -70.0, 70.0)
    pitch = _number(config, "view_pitch_deg", preset["pitch"], 8.0, 70.0)
    roll = _number(config, "view_roll_deg", 0.0, -30.0, 30.0)
    perspective = _number(config, "perspective_strength", 0.8, 0.0, 1.0)
    zoom = _number(config, "zoom", preset["zoom"], 0.35, 2.5)
    anchor_x = _number(config, "ship_anchor_x", preset["anchor_x"], 0.15, 0.85)
    anchor_y = _number(config, "ship_anchor_y", preset["anchor_y"], 0.15, 0.85)
    flip = bool(config.get("diagonal_flip", False))

    if flip:
        yaw = -yaw
    return CameraParams(
        yaw_deg=yaw,
        pitch_deg=pitch,
        roll_deg=roll,
        perspective=perspective,
        zoom=zoom,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        diagonal_flip=flip,
        preset=preset_name,
        width=width,
        height=height,
    )


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _basis(yaw_deg: float, pitch_deg: float, roll_deg: float):
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)

    f = (math.sin(yaw) * math.cos(pitch),
         -math.sin(pitch),
         math.cos(yaw) * math.cos(pitch))
    r = (math.cos(yaw), 0.0, -math.sin(yaw))
    u = (math.sin(yaw) * math.sin(pitch),
         math.cos(pitch),
         math.cos(yaw) * math.sin(pitch))

    if roll:
        cr, sr = math.cos(roll), math.sin(roll)
        r2 = tuple(r[i] * cr + u[i] * sr for i in range(3))
        u2 = tuple(-r[i] * sr + u[i] * cr for i in range(3))
        return f, r2, u2
    return f, r, u


def parallel_angle_deg(yaw_deg: float, pitch_deg: float) -> float:
    """On-screen trench angle above horizontal for the parallel projection."""
    if abs(yaw_deg) < 1e-9:
        return 90.0
    return math.degrees(math.atan(math.sin(math.radians(pitch_deg))
                                  / math.tan(math.radians(yaw_deg))))


class Projector:
    """Projects world points and clips segments for one screen size."""

    def __init__(self, size: tuple[int, int], params: CameraParams):
        self.params = params
        self.sw, self.sh = int(size[0]), int(size[1])
        self.f, self.r, self.u = _basis(params.yaw_deg, params.pitch_deg,
                                        params.roll_deg)
        self.ppu = params.zoom * 9.0 * (self.sh / 720.0)
        self.k = DREF
        self.zref = DREF
        self.frame_dx = 0.0
        self.frame_dy = 0.0
        self.eye = (0.0, 0.0, 0.0)
        self.rect = pygame.Rect(0, 0, self.sw, self.sh)

    def recalibrate(self, neutral_ship: Sequence[float]) -> None:
        """Calibrate K and the constant framing offset from a neutral pose.

        This is deliberately not done per frame: recentering on the live ship
        would cancel the weave that this mode exists to show.
        """
        # Boom camera: directly behind/above the ship's heading, then panned
        # by yaw/pitch.  Placing the eye along the *view ray* instead would
        # slide it sideways over the near bank and let the bank occlude the
        # trench, which is exactly what the first look-proof frame did.
        self.eye = (neutral_ship[0],
                    neutral_ship[1] + CAM_HEIGHT,
                    neutral_ship[2] - CAM_BACK)
        self.zref = _dot(_sub(neutral_ship, self.eye), self.f)
        self.zref = max(self.zref, 1.0)
        self.k = ((1.0 - self.params.perspective) * DREF
                  + self.params.perspective * self.zref)

        self.frame_dx = 0.0
        self.frame_dy = 0.0
        p = self.project_point(neutral_ship)
        if p is None:
            raise ValueError("neutral ship pose is behind the camera")
        self.frame_dx = self.params.anchor_x * self.sw - p[0]
        self.frame_dy = self.params.anchor_y * self.sh - p[1]

    def set_camera(self, x: float, y: float, z: float) -> None:
        """Place the boom camera on a smoothed flight-director position."""
        self.eye = (x, y + CAM_HEIGHT, z - CAM_BACK)

    def view(self, point: Sequence[float]) -> tuple[float, float, float]:
        d = _sub(point, self.eye)
        return _dot(d, self.r), _dot(d, self.u), _dot(d, self.f)

    def scale_at(self, zv: float) -> float:
        den = (1.0 - self.params.perspective) * DREF \
            + self.params.perspective * zv
        if den <= 1e-6:
            return 0.0
        return self.ppu * self.k / den

    def _project_views(self, xv: float, yv: float,
                       zv: float) -> Optional[tuple[float, float, float]]:
        if zv < NEAR:
            return None
        den = (1.0 - self.params.perspective) * DREF \
            + self.params.perspective * zv
        if den <= 1e-6:
            return None
        scale = self.ppu * self.k / den
        return (self.sw * 0.5 + scale * xv + self.frame_dx,
                self.sh * 0.5 - scale * yv + self.frame_dy,
                zv)

    def project_point(self, point: Sequence[float]) -> Optional[tuple[float, float, float]]:
        xv, yv, zv = self.view(point)
        return self._project_views(xv, yv, zv)

    def project_segment(self, a: Sequence[float], b: Sequence[float]):
        """Return ((x1,y1),(x2,y2),depth) clipped to near plane and screen."""
        return self.project_view_segment(self.view(a), self.view(b))

    def project_view_segment(self, va: Sequence[float], vb: Sequence[float]):
        """Same as project_segment for already computed view coordinates."""
        za, zb = va[2], vb[2]
        if za < NEAR and zb < NEAR:
            return None
        if za < NEAR:
            t = (NEAR - za) / (zb - za)
            va = (va[0] + (vb[0] - va[0]) * t,
                  va[1] + (vb[1] - va[1]) * t,
                  NEAR)
        elif zb < NEAR:
            t = (NEAR - zb) / (za - zb)
            vb = (vb[0] + (va[0] - vb[0]) * t,
                  vb[1] + (va[1] - vb[1]) * t,
                  NEAR)
        pa = self._project_views(*va)
        pb = self._project_views(*vb)
        if pa is None or pb is None:
            return None
        clipped = self.rect.clipline((pa[0], pa[1]), (pb[0], pb[1]))
        if not clipped:
            return None
        return ((clipped[0][0], clipped[0][1]),
                (clipped[1][0], clipped[1][1]),
                (pa[2] + pb[2]) * 0.5)

    def _clip_near(self, points: Iterable[Sequence[float]]):
        pts = list(points)
        out = []
        count = len(pts)
        for i in range(count):
            cur = pts[i]
            nxt = pts[(i + 1) % count]
            cz, nz = cur[2], nxt[2]
            cin = cz >= NEAR
            nin = nz >= NEAR
            if cin:
                out.append(cur)
            if cin != nin:
                t = (NEAR - cz) / (nz - cz)
                out.append((cur[0] + (nxt[0] - cur[0]) * t,
                            cur[1] + (nxt[1] - cur[1]) * t,
                            NEAR))
        return out

    def project_polygon(self, points: Sequence[Sequence[float]]):
        """Project a world polygon, clipping it at the near plane."""
        return self.project_view_polygon([self.view(p) for p in points])

    def project_view_polygon(self, view_points: Sequence[Sequence[float]]):
        """Project a polygon from already computed view coordinates."""
        if len(view_points) < 3:
            return None
        view_pts = self._clip_near(view_points)
        if len(view_pts) < 3:
            return None
        out = []
        for xv, yv, zv in view_pts:
            p = self._project_views(xv, yv, zv)
            if p is None:
                return None
            out.append((p[0], p[1]))
        return out

    def visible(self, center: Sequence[float], radius: float) -> bool:
        """Cheap bounding-sphere cull for one object."""
        xv, yv, zv = self.view(center)
        if zv + radius < NEAR:
            return False
        scale = self.scale_at(max(zv, NEAR))
        px = self.sw * 0.5 + scale * xv + self.frame_dx
        py = self.sh * 0.5 - scale * yv + self.frame_dy
        r = max(4.0, abs(scale) * radius)
        return (-r <= px <= self.sw + r) and (-r <= py <= self.sh + r)

    def screen_angle_deg(self) -> float:
        return parallel_angle_deg(abs(self.params.yaw_deg),
                                  self.params.pitch_deg)
