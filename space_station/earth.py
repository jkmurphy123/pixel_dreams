"""The wireframe Earth under the station.

The coastline file is built from Natural Earth 1:110m land by
``scripts/build_earth_coastlines.py``: closed lon/lat rings, simplified to
about 0.28 degrees.  This module turns them into unit-sphere points once, then
draws the visible hemisphere per frame with a parallel projection that matches
the pre-rendered planet disc.

Ocean and land are separate line sets.  The graticule is rebuilt when the
quality tier changes; the coastlines never are.
"""
from __future__ import annotations

import json
import math
import os

import pygame

from .palette import Palette, mix

TAU = math.tau

#: Colour-by-depth is a precomputed ramp: a visible hemisphere is ~1,300 land
#: segments plus ~700 graticule segments a frame, and calling mix() for each
#: one dominated the frame time.
_BUCKET_MAX = 32


def coastlines_path(base_dir: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value if os.path.isabs(value) else os.path.join(base_dir, value)


def _unit(lon_deg: float, lat_deg: float) -> tuple[float, float, float]:
    """Lon 0 faces the viewer (+Z); +Y is north."""
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    cos_lat = math.cos(lat)
    return (cos_lat * math.sin(lon), math.sin(lat), cos_lat * math.cos(lon))


def load_coastlines(path: str):
    """Read the built coastline file.

    Returns ``(rings, notes)``.  A missing or malformed file is not fatal: the
    mode still draws the graticule, which is a sphere you can read, and the
    note is logged once by the adapter.
    """
    notes: list[str] = []
    if not path:
        return [], ["no coastline file configured; drawing the graticule only"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return [], [f"coastline file not found: {path}"]
    except (OSError, ValueError) as exc:
        return [], [f"coastline file unreadable: {exc}"]

    raw = payload.get("coastlines") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return [], ["coastline file has no 'coastlines' list"]

    rings = []
    skipped = 0
    for ring in raw:
        if not isinstance(ring, list) or len(ring) < 3:
            skipped += 1
            continue
        points = []
        try:
            for pair in ring:
                lon, lat = float(pair[0]), float(pair[1])
                if not (math.isfinite(lon) and math.isfinite(lat)):
                    raise ValueError("non-finite coordinate")
                points.append(_unit(lon, lat))
        except (TypeError, ValueError, IndexError):
            skipped += 1
            continue
        if len(points) >= 3:
            rings.append(tuple(points))
    if skipped:
        notes.append(f"skipped {skipped} malformed coastline ring(s)")
    if not rings:
        notes.append("coastline file held no usable rings")
    return rings, notes


def _graticule(step_deg: int):
    """Precompute the graticule as unit-sphere polylines.

    A meridian is sampled every 6 degrees, a parallel every ~6 degrees of
    longitude.  The equator is its own brighter line.
    """
    step = max(10, min(45, int(step_deg)))
    lines: list[tuple[tuple[tuple[float, float, float], ...], str]] = []

    meridian_step = max(2, 360 // step)
    for index in range(meridian_step):
        lon = 360.0 * index / meridian_step
        points = tuple(_unit(lon, lat)
                       for lat in range(-90, 91, 6))
        lines.append((points, "meridian"))

    lines.append((tuple(_unit(lon, 0.0) for lon in range(0, 361, 4)),
                  "equator"))
    parallel_lat = step
    while parallel_lat < 90:
        for sign in (-1, 1):
            lat = sign * parallel_lat
            points = tuple(_unit(lon, lat) for lon in range(0, 361, 4))
            lines.append((points, "parallel"))
        parallel_lat += step
    return tuple(lines)


class EarthGeometry:
    """Unit-sphere lines plus the cached planet disc."""

    def __init__(self, coastlines, graticule_step: int = 20):
        self.land: tuple[tuple[tuple[float, float, float], ...], ...] = \
            tuple(coastlines or ())
        self.point_count = sum(len(ring) for ring in self.land)
        self.ring_count = len(self.land)
        self._step = 0
        self.grid: tuple = ()
        self.set_graticule(graticule_step)
        self._disc = None
        self._disc_key = None
        self._palette_name = ""
        self._ramps: dict = {}
        self.last_land_segments = 0
        self.last_grid_segments = 0

    def set_graticule(self, step_deg: int) -> None:
        step = max(10, min(45, int(step_deg)))
        if step == self._step:
            return
        self._step = step
        self.grid = _graticule(step)

    def _build_ramps(self, palette: Palette) -> None:
        self._palette_name = palette.name
        ocean = []
        equator = []
        land = []
        equator_base = mix(palette.earth_ocean, palette.earth_land, 0.22)
        for bucket in range(_BUCKET_MAX + 1):
            depth = bucket / _BUCKET_MAX
            ocean.append(mix(palette.earth_ocean_dim, palette.earth_ocean,
                             min(1.0, depth ** 0.55)))
            equator.append(mix(palette.earth_ocean_dim, equator_base,
                               min(1.0, depth ** 0.55)))
            land.append(mix(palette.earth_land_dim, palette.earth_land,
                            min(1.0, depth ** 0.62)))
        self._ramps = {
            "land": tuple(land),
            "equator": tuple(equator),
            "grid": tuple(ocean),
        }

    def resize(self, radius: int, palette: Palette) -> None:
        if palette.name != self._palette_name:
            self._build_ramps(palette)
        key = (int(radius), palette.name)
        if key == self._disc_key:
            return
        self._disc_key = key
        self._disc = self._build_disc(max(2, int(radius)), palette)

    @staticmethod
    def _build_disc(radius: int, palette: Palette) -> pygame.Surface:
        """A dark, slightly lit planet disc with a soft atmosphere rim.

        The radial gradient is built at a capped resolution and smoothscaled to
        the target size; drawing every concentric circle at native 4K size was
        a visible one-off hitch.  The few atmosphere outlines are then drawn at
        native size on the scaled surface, so the limb stays crisp instead of
        becoming a wide blurry halo.  The disc is opaque on purpose: without it
        the starfield reads through the planet and the wireframe stops looking
        like a sphere.
        """
        build_radius = max(2, min(int(radius), 280))
        scale = radius / build_radius
        pad = max(10, int(build_radius * 0.083))
        size = build_radius * 2 + pad * 2
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2

        steps = max(12, build_radius // 3)
        for index in range(steps):
            t = index / steps
            r = build_radius * (1.0 - t)
            color = mix(palette.earth_edge, palette.earth_center,
                        min(1.0, (t ** 0.72) * 1.08))
            pygame.draw.circle(surface, (*color, 255), (center, center),
                               int(r))
        if scale > 1.0:
            target = max(4, int(round(size * scale)))
            surface = pygame.transform.smoothscale(surface, (target, target))
        center = surface.get_width() // 2

        # Native-size atmosphere outlines: thin rings only, so the disc below
        # stays opaque.
        atmo = palette.earth_atmo
        native_pad = max(6, int(round(pad * scale)))
        for extra, alpha, width in ((native_pad - 2, 8, 3),
                                    (native_pad - 6, 16, 2),
                                    (native_pad - 10, 30, 2),
                                    (3, 52, 2)):
            if radius + extra <= 0:
                continue
            pygame.draw.circle(surface, (*atmo, alpha), (center, center),
                               radius + extra, width=width)
        # A thin lit limb just inside the edge.
        pygame.draw.circle(surface, (*mix(atmo, palette.earth_land, 0.30), 120),
                           (center, center), max(1, radius - 1), width=1)
        return surface

    def draw(self, screen: pygame.Surface, center: tuple[float, float],
             radius: float, spin_deg: float, tilt_deg: float,
             palette: Palette, show_land: bool = True,
             show_graticule: bool = True) -> None:
        self.resize(int(radius), palette)
        if self._disc is not None:
            rect = self._disc.get_rect(center=(int(center[0]), int(center[1])))
            screen.blit(self._disc, rect)

        spin = math.radians(spin_deg)
        tilt = math.radians(tilt_deg)
        cs, ss = math.cos(spin), math.sin(spin)
        ct, st = math.cos(tilt), math.sin(tilt)
        cx, cy = float(center[0]), float(center[1])
        rr = float(radius)

        self.last_grid_segments = 0
        self.last_land_segments = 0

        if show_graticule:
            for points, role in self.grid:
                self._polyline(screen, points, cx, cy, rr, cs, ss, ct, st,
                               palette, role)
        if show_land:
            for ring in self.land:
                self._polyline(screen, ring, cx, cy, rr, cs, ss, ct, st,
                               palette, "land")

    def _polyline(self, screen, points, cx, cy, radius, cs, ss, ct, st,
                  palette: Palette, role: str) -> None:
        count = len(points)
        if count < 2:
            return
        previous = None
        for index in range(count + 1):
            point = points[index % count]
            x, y, z = point
            x1 = x * cs + z * ss
            z1 = -x * ss + z * cs
            y2 = y * ct - z1 * st
            z2 = y * st + z1 * ct
            current = (x1, y2, z2)
            if previous is not None:
                self._segment(screen, previous, current, cx, cy, radius,
                              palette, role)
            previous = current

    def _segment(self, screen, a, b, cx, cy, radius, palette: Palette,
                 role: str) -> None:
        ax, ay, az = a
        bx, by, bz = b
        if az <= 0.0 and bz <= 0.0:
            return
        if az <= 0.0:
            t = az / (az - bz)
            ax += (bx - ax) * t
            ay += (by - ay) * t
            az = 0.0
        elif bz <= 0.0:
            t = bz / (bz - az)
            bx += (ax - bx) * t
            by += (ay - by) * t
            bz = 0.0
        x1 = int(cx + ax * radius)
        y1 = int(cy - ay * radius)
        x2 = int(cx + bx * radius)
        y2 = int(cy - by * radius)
        if x1 == x2 and y1 == y2:
            return
        depth = (az + bz) * 0.5
        bucket = int(depth * _BUCKET_MAX)
        if bucket < 0:
            bucket = 0
        elif bucket > _BUCKET_MAX:
            bucket = _BUCKET_MAX
        if role == "land":
            color = self._ramps["land"][bucket]
        elif role == "equator":
            color = self._ramps["equator"][bucket]
        else:
            color = self._ramps["grid"][bucket]
        pygame.draw.line(screen, color, (x1, y1), (x2, y2), 1)
        if role == "land":
            self.last_land_segments += 1
        else:
            self.last_grid_segments += 1
