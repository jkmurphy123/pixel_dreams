"""Data-driven landmarks for the cyberspace matrix.

A landmark file is a list of named, fixed-position structures.  Nothing here
knows the names in `data/cyberspace_landmarks.json`: the mode hands this module
a path and gets back `Landmark` objects, so a new landmark is a config edit.

Coordinate convention
---------------------
* A landmark's ``sector`` is a ground cell ``[ix, iy]``.  Its origin is the
  centre of that cell, at height ``altitude``.
* Every part's ``offset`` is relative to that origin.  The part's ``z`` offset
  is its BASE: boxes/pyramids/prisms grow upward from it.  A part with a high
  z offset therefore hangs in the air.
* Parts are composed.  A stepped pyramid is one primitive; a cluster of cubes is
  several box parts with different offsets.

The renderer only has to ask for ``edges_at(time_s)``; spinning landmarks do the
rotation here, static landmarks return precomputed world edges.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

from .detail import effective_level, volume_lattice
from .matrix import Edge, _seg
from .palette import RGB, mix


SHAPES = ("box", "pyramid", "stepped_pyramid", "octahedron", "prism",
          "ring", "cage")

#: Default shape size when a part omits ``size``.
_DEFAULT_SIZE = (24.0, 24.0, 48.0)


@dataclass
class LandmarkPart:
    shape: str
    offset: tuple[float, float, float]
    size: tuple[float, float, float]
    color: RGB
    local_edges: tuple[Edge, ...]
    top: float
    radius: float


@dataclass
class Landmark:
    name: str
    label: str
    sector: tuple[int, int]
    altitude: float
    color: RGB
    glow: float
    spin: float
    clear_radius: int
    detail_level: int
    origin: tuple[float, float, float]
    parts: tuple[LandmarkPart, ...]
    local_edges: tuple[Edge, ...]
    static_edges: tuple[Edge, ...]
    center: tuple[float, float, float]
    radius: float
    local_center: tuple[float, float, float]
    local_radius: float
    label_pos: tuple[float, float, float]

    def edges_at(self, time_s: float) -> tuple[Edge, ...]:
        if abs(self.spin) < 1e-9:
            return self.static_edges
        angle = math.radians(self.spin) * time_s
        ca, sa = math.cos(angle), math.sin(angle)
        ox, oy, oz = self.origin
        out = []
        for x1, y1, z1, x2, y2, z2, r, g, b in self.local_edges:
            out.append((ox + x1 * ca - y1 * sa,
                        oy + x1 * sa + y1 * ca,
                        oz + z1,
                        ox + x2 * ca - y2 * sa,
                        oy + x2 * sa + y2 * ca,
                        oz + z2,
                        r, g, b))
        return tuple(out)

    @property
    def cells(self) -> set[tuple[int, int]]:
        # The landmark footprint is deliberately kept inside one cell, but a
        # larger clear_radius gives a big form a plaza instead of letting
        # procedural towers crowd its outline.
        r = max(0, min(2, int(self.clear_radius)))
        ix, iy = self.sector
        return {(ix + dx, iy + dy)
                for dx in range(-r, r + 1) for dy in range(-r, r + 1)}

    def label_color(self) -> RGB:
        return mix(self.color, (255, 255, 255), 0.28)


# ---------------------------------------------------------------- values

def _number(value, default: float, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    if not math.isfinite(value):
        return default
    return lo if value < lo else hi if value > hi else value


def _int(value, default: int, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return lo if value < lo else hi if value > hi else value


def _vec3(value, default) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return tuple(float(v) for v in default)
    out = []
    for i in range(3):
        try:
            out.append(float(value[i]))
        except (TypeError, ValueError, OverflowError):
            out.append(float(default[i]))
    return tuple(out)


def _size(value) -> tuple[float, float, float]:
    out = _vec3(value, _DEFAULT_SIZE)
    return tuple(max(1.0, v) for v in out)


def _color(value, default: RGB) -> RGB:
    """Accept [r,g,b] or '#rrggbb'; clamp rather than fail."""
    if isinstance(value, str):
        body = value.strip().lstrip("#")
        if len(body) == 6:
            try:
                return tuple(int(body[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        out = []
        for i in range(3):
            try:
                v = int(value[i])
            except (TypeError, ValueError, OverflowError):
                v = default[i]
            out.append(0 if v < 0 else 255 if v > 255 else v)
        return tuple(out)
    return tuple(default)


# ---------------------------------------------------------------- primitives

def _add_box(out: list, ox: float, oy: float, z0: float, z1: float,
             w: float, d: float, color: RGB, *, bottom: bool = True,
             mid: bool = True) -> None:
    x0, x1 = ox - w * 0.5, ox + w * 0.5
    y0, y1 = oy - d * 0.5, oy + d * 0.5
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for (x, y) in corners:
        out.append(_seg(x, y, z0, x, y, z1, color))
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        out.append(_seg(a[0], a[1], z1, b[0], b[1], z1, color))
        if bottom:
            out.append(_seg(a[0], a[1], z0, b[0], b[1], z0, color))
    if mid and z1 - z0 > max(w, d) * 1.2:
        z = (z0 + z1) * 0.5
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            out.append(_seg(a[0], a[1], z, b[0], b[1], z, color))


def _add_pyramid(out: list, ox: float, oy: float, z0: float, z1: float,
                 w: float, d: float, color: RGB) -> None:
    x0, x1 = ox - w * 0.5, ox + w * 0.5
    y0, y1 = oy - d * 0.5, oy + d * 0.5
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    apex = (ox, oy, z1)
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        out.append(_seg(a[0], a[1], z0, b[0], b[1], z0, color))
        out.append(_seg(a[0], a[1], z0, apex[0], apex[1], apex[2], color))
    for frac in (1.0 / 3.0, 2.0 / 3.0):
        ring = []
        for (x, y) in corners:
            ring.append((ox + (x - ox) * (1 - frac), oy + (y - oy) * (1 - frac),
                         z0 + (z1 - z0) * frac))
        for i in range(4):
            a, b = ring[i], ring[(i + 1) % 4]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))


def _add_stepped(out: list, ox: float, oy: float, z0: float, z1: float,
                 w: float, d: float, color: RGB, steps: int,
                 shrink: float, detail_level: int = 1) -> None:
    height = (z1 - z0) / steps
    for step in range(steps):
        scale = shrink ** step
        sw, sd = max(2.0, w * scale), max(2.0, d * scale)
        sz0, sz1 = z0 + step * height, z0 + (step + 1) * height
        _add_box(out, ox, oy, sz0, sz1, sw, sd, color,
                 bottom=(step == 0), mid=False)
        if detail_level > 1:
            level = effective_level(detail_level, (sw, sd, sz1 - sz0), 5)
            if level > 1:
                out.extend(volume_lattice(ox - sw / 2, oy - sd / 2,
                                          ox + sw / 2, oy + sd / 2,
                                          sz0, sz1, level, color))


def _add_octahedron(out: list, ox: float, oy: float, z0: float, z1: float,
                    w: float, d: float, color: RGB) -> None:
    cz = (z0 + z1) * 0.5
    rx, ry, rz = w * 0.5, d * 0.5, (z1 - z0) * 0.5
    verts = ((ox + rx, oy, cz), (ox - rx, oy, cz),
             (ox, oy + ry, cz), (ox, oy - ry, cz),
             (ox, oy, z1), (ox, oy, z0))
    pairs = ((0, 2), (0, 3), (0, 4), (0, 5),
             (1, 2), (1, 3), (1, 4), (1, 5),
             (2, 4), (2, 5), (3, 4), (3, 5))
    for a, b in pairs:
        pa, pb = verts[a], verts[b]
        out.append(_seg(pa[0], pa[1], pa[2], pb[0], pb[1], pb[2], color))
    # Equator ring makes the rotation readable even when the silhouette is
    # momentarily a diamond.
    for i in range(4):
        a, b = verts[i], verts[(i + 1) % 4]
        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))


def _add_prism(out: list, ox: float, oy: float, z0: float, z1: float,
               w: float, d: float, color: RGB, sides: int,
               rotation_deg: float = 0.0) -> None:
    sides = max(3, min(32, sides))
    rx, ry = w * 0.5, d * 0.5
    phase = math.radians(rotation_deg)
    base = []
    top = []
    for i in range(sides):
        a = phase + 2 * math.pi * i / sides
        x, y = ox + math.cos(a) * rx, oy + math.sin(a) * ry
        base.append((x, y, z0))
        top.append((x, y, z1))
    for i in range(sides):
        a, b = base[i], base[(i + 1) % sides]
        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
        a, b = top[i], top[(i + 1) % sides]
        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
        a, b = base[i], top[i]
        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))


def _add_ring(out: list, ox: float, oy: float, z: float, radius: float,
              inner: float, segments: int, spokes: int, color: RGB) -> None:
    segments = max(4, min(96, segments))
    radius = max(1.0, radius)
    outer = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        outer.append((ox + math.cos(a) * radius, oy + math.sin(a) * radius, z))
    for i in range(segments):
        a, b = outer[i], outer[(i + 1) % segments]
        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
    inner = max(0.0, min(radius * 0.92, inner))
    if inner > 0.5:
        inn = []
        for i in range(segments):
            a = 2 * math.pi * i / segments
            inn.append((ox + math.cos(a) * inner, oy + math.sin(a) * inner, z))
        for i in range(segments):
            a, b = inn[i], inn[(i + 1) % segments]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
        spokes = max(0, min(32, spokes))
        for i in range(spokes):
            a = 2 * math.pi * i / max(1, spokes)
            out.append(_seg(ox + math.cos(a) * inner, oy + math.sin(a) * inner, z,
                            ox + math.cos(a) * radius, oy + math.sin(a) * radius, z,
                            color))


def _add_cage(out: list, ox: float, oy: float, z0: float, z1: float,
              w: float, d: float, color: RGB) -> None:
    _add_box(out, ox, oy, z0, z1, w, d, color)
    x0, x1 = ox - w * 0.5, ox + w * 0.5
    y0, y1 = oy - d * 0.5, oy + d * 0.5
    # Two crossing face diagonals on each vertical face.
    for (a, b) in (((x0, y0), (x0, y1)), ((x1, y0), (x1, y1)),
                   ((x0, y0), (x1, y0)), ((x0, y1), (x1, y1))):
        out.append(_seg(a[0], a[1], z0, b[0], b[1], z1, color))
        out.append(_seg(a[0], a[1], z1, b[0], b[1], z0, color))


def _add_prism_detail(out: list, ox: float, oy: float, z0: float, z1: float,
                      w: float, d: float, color: RGB, sides: int,
                      rotation_deg: float, level: int) -> None:
    n = max(2, min(5, int(level)))
    sides = max(3, min(32, sides))
    rx, ry = w * 0.5, d * 0.5
    phase = math.radians(rotation_deg)
    for layer in range(1, n):
        z = z0 + (z1 - z0) * layer / n
        pts = []
        for i in range(sides):
            a = phase + 2 * math.pi * i / sides
            pts.append((ox + math.cos(a) * rx, oy + math.sin(a) * ry, z))
        for i in range(sides):
            a, b = pts[i], pts[(i + 1) % sides]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
    # A roof/cap star makes the top face read as a surface rather than a hole.
    for z in (z0, z1):
        for i in range(sides):
            a = phase + 2 * math.pi * i / sides
            out.append(_seg(ox, oy, z, ox + math.cos(a) * rx,
                            oy + math.sin(a) * ry, z, color))


def _add_octa_detail(out: list, ox: float, oy: float, z0: float, z1: float,
                     w: float, d: float, color: RGB, level: int) -> None:
    n = max(2, min(5, int(level)))
    cz = (z0 + z1) * 0.5
    for layer in range(1, n):
        t = layer / n
        z = z0 + (z1 - z0) * t
        scale_r = 1.0 - abs(2.0 * t - 1.0)
        rx, ry = w * 0.5 * scale_r, d * 0.5 * scale_r
        if rx < 0.5 or ry < 0.5:
            continue
        pts = []
        for i in range(8):
            a = 2 * math.pi * i / 8
            pts.append((ox + math.cos(a) * rx, oy + math.sin(a) * ry, z))
        for i in range(8):
            a, b = pts[i], pts[(i + 1) % 8]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))


def _add_ring_detail(out: list, ox: float, oy: float, z: float, radius: float,
                     inner: float, color: RGB, level: int,
                     segments: int = 32) -> None:
    n = max(2, min(5, int(level)))
    if radius <= inner + 0.5:
        return
    nseg = max(12, min(96, int(segments)))
    for layer in range(1, n):
        r = inner + (radius - inner) * layer / n
        pts = []
        for i in range(nseg):
            a = 2 * math.pi * i / nseg
            pts.append((ox + math.cos(a) * r, oy + math.sin(a) * r, z))
        for i in range(nseg):
            a, b = pts[i], pts[(i + 1) % nseg]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))


def _rotate_xy(edges: list, cx: float, cy: float, degrees: float) -> list:
    if abs(degrees) < 1e-6:
        return edges
    a = math.radians(degrees)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x1, y1, z1, x2, y2, z2, r, g, b in edges:
        x1, y1 = x1 - cx, y1 - cy
        x2, y2 = x2 - cx, y2 - cy
        out.append((cx + x1 * ca - y1 * sa,
                    cy + x1 * sa + y1 * ca, z1,
                    cx + x2 * ca - y2 * sa,
                    cy + x2 * sa + y2 * ca, z2,
                    r, g, b))
    return out


# ---------------------------------------------------------------- parts

def _part(raw: dict, default_color: RGB, warnings: list, where: str,
          detail_level: int = 1):
    shape = str(raw.get("shape", "")).strip().lower()
    if shape not in SHAPES:
        warnings.append(f"{where}: unknown shape {shape!r} — skipped")
        return None
    color = _color(raw.get("color"), default_color)
    offset = _vec3(raw.get("offset"), (0.0, 0.0, 0.0))
    ox, oy, oz = offset
    rotation = _number(raw.get("rotation_deg"), 0.0, -360.0, 360.0)
    size = _size(raw.get("size"))
    w, d, h = size
    edges: list[Edge] = []

    if shape == "box":
        _add_box(edges, ox, oy, oz, oz + h, w, d, color)
        if detail_level > 1:
            level = effective_level(detail_level, (w, d, h), 5)
            if level > 1:
                edges.extend(volume_lattice(ox - w * 0.5, oy - d * 0.5,
                                            ox + w * 0.5, oy + d * 0.5,
                                            oz, oz + h, level, color))
    elif shape == "pyramid":
        _add_pyramid(edges, ox, oy, oz, oz + h, w, d, color)
        if detail_level > 1:
            # Add the in-between latitude rings; the base already has 1/3 and 2/3.
            n = max(2, min(5, int(detail_level)))
            for layer in range(1, n):
                frac = layer / n
                if frac in (1.0 / 3.0, 2.0 / 3.0):
                    continue
                ring = []
                for (x, y) in ((ox - w / 2, oy - d / 2), (ox + w / 2, oy - d / 2),
                               (ox + w / 2, oy + d / 2), (ox - w / 2, oy + d / 2)):
                    ring.append((ox + (x - ox) * (1 - frac),
                                 oy + (y - oy) * (1 - frac),
                                 oz + (oz + h - oz) * frac))
                for i in range(4):
                    a, b = ring[i], ring[(i + 1) % 4]
                    edges.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
    elif shape == "stepped_pyramid":
        steps = _int(raw.get("steps"), 5, 1, 16)
        shrink = _number(raw.get("step_shrink"), 0.8, 0.35, 0.97)
        _add_stepped(edges, ox, oy, oz, oz + h, w, d, color, steps, shrink,
                     detail_level)
    elif shape == "octahedron":
        _add_octahedron(edges, ox, oy, oz, oz + h, w, d, color)
        if detail_level > 1:
            _add_octa_detail(edges, ox, oy, oz, oz + h, w, d, color,
                             detail_level)
    elif shape == "prism":
        sides = _int(raw.get("sides"), 8, 3, 32)
        _add_prism(edges, ox, oy, oz, oz + h, w, d, color, sides, rotation)
        if detail_level > 1:
            _add_prism_detail(edges, ox, oy, oz, oz + h, w, d, color, sides,
                              rotation, detail_level)
        rotation = 0.0         # applied inside the prism
    elif shape == "ring":
        radius = _number(raw.get("radius"), max(w, d) * 0.5, 1.0, 400.0)
        inner = _number(raw.get("inner_radius"), radius * 0.68, 0.0, 399.0)
        segments = _int(raw.get("segments"), 32, 4, 96)
        spokes = _int(raw.get("spokes"), 8, 0, 32)
        _add_ring(edges, ox, oy, oz, radius, inner, segments, spokes, color)
        if detail_level > 1:
            _add_ring_detail(edges, ox, oy, oz, radius, inner, color,
                             detail_level, segments)
    else:  # cage
        _add_cage(edges, ox, oy, oz, oz + h, w, d, color)
        if detail_level > 1:
            level = effective_level(detail_level, (w, d, h), 5)
            if level > 1:
                edges.extend(volume_lattice(ox - w * 0.5, oy - d * 0.5,
                                            ox + w * 0.5, oy + d * 0.5,
                                            oz, oz + h, level, color))

    if abs(rotation) > 1e-6:
        edges = _rotate_xy(edges, ox, oy, rotation)

    if not edges:
        return None
    top = max(max(e[2], e[5]) for e in edges) - oz
    radius = 0.0
    for e in edges:
        for i in (0, 3):
            dx, dy, dz = e[i] - ox, e[i + 1] - oy, e[i + 2] - oz
            radius = max(radius, math.sqrt(dx * dx + dy * dy + dz * dz))
    return LandmarkPart(shape, offset, size, color, tuple(edges), top, radius)


# ---------------------------------------------------------------- loading

def load_landmarks(path: str, cell: float = 80.0, *, default_color: RGB =
                   (200, 240, 255), detail_level: int = 1
                   ) -> tuple[list[Landmark], list[str]]:
    """Read a landmark file. Never raises: a bad file or entry is reported."""
    warnings: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except OSError as exc:
        return [], [f"cannot read {os.path.basename(path)}: {exc}"]
    except (ValueError, TypeError) as exc:
        return [], [f"{os.path.basename(path)} is not valid JSON: {exc}"]

    items = raw.get("landmarks") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return [], [f"{os.path.basename(path)} has no 'landmarks' list"]

    landmarks: list[Landmark] = []
    for index, item in enumerate(items):
        where = f"landmark #{index + 1}"
        if not isinstance(item, dict):
            warnings.append(f"{where}: not an object — skipped")
            continue
        if item.get("enabled") is False:
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            warnings.append(f"{where}: no name — skipped")
            continue
        where = f"landmark '{name}'"
        sector_raw = item.get("sector")
        if (not isinstance(sector_raw, (list, tuple)) or len(sector_raw) < 2
                or isinstance(sector_raw[0], bool) or isinstance(sector_raw[1], bool)):
            warnings.append(f"{where}: sector must be [ix, iy] — skipped")
            continue
        try:
            sector = (int(sector_raw[0]), int(sector_raw[1]))
        except (TypeError, ValueError, OverflowError):
            warnings.append(f"{where}: sector must be whole numbers — skipped")
            continue
        altitude = _number(item.get("altitude"), 0.0, -2000.0, 4000.0)
        color = _color(item.get("color"), default_color)
        glow = _number(item.get("glow"), 1.25, 0.2, 3.0)
        spin = _number(item.get("spin"), 0.0, -60.0, 60.0)
        clear_radius = _int(item.get("clear_radius"), 0, 0, 2)
        label = str(item.get("label") or name).strip()[:48] or name[:48]

        raw_parts = item.get("parts")
        if not isinstance(raw_parts, list) or not raw_parts:
            if item.get("shape"):
                raw_parts = [item]
            else:
                warnings.append(f"{where}: no parts and no shape — skipped")
                continue
        parts = []
        for p_index, raw_part in enumerate(raw_parts):
            if not isinstance(raw_part, dict):
                warnings.append(f"{where}: part #{p_index + 1} is not an object")
                continue
            part = _part(raw_part, color, warnings, f"{where} part #{p_index + 1}",
                         detail_level)
            if part is not None:
                parts.append(part)
        if not parts:
            warnings.append(f"{where}: no drawable parts — skipped")
            continue

        origin = ((sector[0] + 0.5) * cell, (sector[1] + 0.5) * cell, altitude)
        local_edges = tuple(e for part in parts for e in part.local_edges)
        if not local_edges:
            continue
        xs = [v for e in local_edges for v in (e[0], e[3])]
        ys = [v for e in local_edges for v in (e[1], e[4])]
        zs = [v for e in local_edges for v in (e[2], e[5])]
        local_center = ((min(xs) + max(xs)) * 0.5,
                        (min(ys) + max(ys)) * 0.5,
                        (min(zs) + max(zs)) * 0.5)
        center = (origin[0] + local_center[0],
                  origin[1] + local_center[1],
                  origin[2] + local_center[2])
        radius = max(math.dist((local_center[0], local_center[1], local_center[2]),
                               (e[i], e[i + 1], e[i + 2]))
                     for e in local_edges for i in (0, 3))
        local_radius = max(1.0, radius)
        max_top = max(zs)
        label_height = _number(item.get("label_height"), max_top + 12.0,
                               max_top, 5000.0) if item.get("label_height") is not None \
            else max_top + 12.0
        static = tuple((origin[0] + e[0], origin[1] + e[1], origin[2] + e[2],
                        origin[0] + e[3], origin[1] + e[4], origin[2] + e[5],
                        e[6], e[7], e[8]) for e in local_edges)
        landmarks.append(Landmark(
            name=name, label=label, sector=sector, altitude=altitude,
            color=color, glow=glow, spin=spin, clear_radius=clear_radius,
            detail_level=max(1, int(detail_level)), origin=origin,
            parts=tuple(parts), local_edges=local_edges,
            static_edges=static, center=center, radius=radius,
            local_center=local_center, local_radius=local_radius,
            label_pos=(origin[0], origin[1], origin[2] + max(0.0, label_height)),
        ))

    return landmarks, warnings


def landmark_path(base_dir: str, value: str) -> str:
    """Resolve a configured landmark file against the project root."""
    value = (value or "").strip()
    if not value:
        return ""
    return value if os.path.isabs(value) else os.path.join(base_dir, value)
