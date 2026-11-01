"""The deterministic cyberspace world.

Everything is generated from ``(seed, cell, level)`` with no stored state that a
renderer could not reconstruct.  Only *nearby* cells exist as objects; the cache
is pruned as the viewpoint moves, so a kiosk can fly forever without growing.

Two kinds of structure share the lattice:

  * **towers** sit in ground cells, inset from the neon street lines so the
    camera's street-level flight never intersects one.
  * **constructs** float above the towers on a sparse 3-D lattice of their own.
    Their radius is clamped against the cell boundary, for the same reason.

The class deliberately has no pygame dependency: the tests can ask for a city
signature or a construct's edges without a display.
"""
from __future__ import annotations

import math
import random

from .detail import effective_level, volume_lattice
from .palette import Palette, mix, scale

#: Flat edge record: x1, y1, z1, x2, y2, z2, r, g, b.
Edge = tuple[float, float, float, float, float, float, int, int, int]

#: A few invented corporate names.  They are world-building, not quotations.
CORPORATE_NAMES = (
    "ZAIBATSU HEAVY", "SENSE/NET", "MITSUI-DYNE", "HOSAKA-7", "OTOMO TRUST",
    "NOVA-KANE", "KIRIN-MATSU", "HALO DYNAMICS", "BLACK LOTUS", "SYNAPSE TRUST",
    "ORBITAL GENETICS", "ZEPHYR HOLDINGS", "NEON VEIL", "KESTREL-9",
    "TURING-ASH", "HELIX NOIR", "RED ORCHID", "LOW ORBIT DATA", "JALON-ICHI",
    "VANTA CORP", "DEEP SPINDLE", "MAGLEV UNION", "MIRROR VAULT",
    "TESSIER-ARCO", "WINTERLIGHT", "SHIVA SYSTEMS",
)

CONSTRUCT_LABELS = (
    "ICE-9", "DATA HAVEN", "GHOST NODE", "ZION GATE", "BLACK ICE",
    "MIRROR VAULT", "SPINDLE CORE", "NULL CHAPEL", "SENTINEL", "DEAD CHANNEL",
)

#: Unit shapes for the floating objects: (vertices, edge index pairs).
#: Vertices are unit-radius; the renderer rotates them and scales by the
#: construct's radius.
_OCTA = (
    ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)),
    ((0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5),
     (2, 4), (2, 5), (3, 4), (3, 5)),
)
_CUBE = (
    tuple((x, y, z) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)),
    ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7),
     (0, 4), (1, 5), (2, 6), (3, 7)),
)
_SPINDLE = (
    ((0, 0, 1.7), (0, 0, -1.7), (1, 0, 0.15), (0, 1, 0.15),
     (-1, 0, 0.15), (0, -1, 0.15)),
    ((0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5),
     (2, 3), (3, 4), (4, 5), (5, 2)),
)
_PRISM = (
    tuple((math.cos(i * math.pi / 3), math.sin(i * math.pi / 3), z)
          for z in (-1, 1) for i in range(6)),
    tuple((i, (i + 1) % 6) for i in range(6)) +
    tuple((6 + i, 6 + (i + 1) % 6) for i in range(6)) +
    tuple((i, 6 + i) for i in range(6)),
)
_TETRA = (
    ((0.9, 0.9, 0.9), (-0.9, -0.9, 0.9), (-0.9, 0.9, -0.9), (0.9, -0.9, -0.9)),
    ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)),
)


def _ring_edges(n: int):
    return tuple((i, (i + 1) % n) for i in range(n))


def _gyro_shape() -> tuple[tuple, tuple]:
    """Three orthogonal circles; the group's rotation is visible because the
    planes tilt as it turns."""
    verts = []
    edges = []
    n = 12
    for plane in range(3):
        base = len(verts)
        for i in range(n):
            a = 2.0 * math.pi * i / n
            c, s = math.cos(a), math.sin(a)
            if plane == 0:
                verts.append((c, s, 0.0))
            elif plane == 1:
                verts.append((c, 0.0, s))
            else:
                verts.append((0.0, c, s))
        edges.extend((base + i, base + (i + 1) % n) for i in range(n))
    return tuple(verts), tuple(edges)


def _gate_shape() -> tuple[tuple, tuple]:
    """Two concentric rings joined by spokes: a portal around a vertical shaft."""
    verts = []
    edges = []
    n = 14
    outer_base = 0
    for radius in (1.0, 0.62):
        base = len(verts)
        for i in range(n):
            a = 2.0 * math.pi * i / n
            verts.append((math.cos(a) * radius, math.sin(a) * radius, 0.0))
        edges.extend((base + i, base + (i + 1) % n) for i in range(n))
    inner_base = n
    for i in range(0, n, 2):
        edges.append((outer_base + i, inner_base + i))
    return tuple(verts), tuple(edges)


_GYRO = _gyro_shape()
_GATE = _gate_shape()

SHAPES = {
    "octa": _OCTA,
    "cube": _CUBE,
    "spindle": _SPINDLE,
    "prism": _PRISM,
    "tetra": _TETRA,
    "gyro": _GYRO,
    "gate": _GATE,
}
SHAPE_NAMES = tuple(SHAPES)


def _rotate(x: float, y: float, z: float, ax: float, ay: float, az: float):
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return x, y, z


def _seg(x1, y1, z1, x2, y2, z2, color) -> Edge:
    return (float(x1), float(y1), float(z1),
            float(x2), float(y2), float(z2),
            int(color[0]), int(color[1]), int(color[2]))


def _mix_int(a: int, b: int, c: int) -> int:
    """A stable 32-bit mix used for deterministic per-cell randomness.

    Deliberately not Python's ``hash``: that is salted per process, and a mode
    with a pinned seed must produce the same city on every run.
    """
    h = (a * 0x85EBCA6B + b * 0xC2B2AE35 + c * 0x27D4EB2F + 0x165667B1) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 0x2545F491) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x9E3779B1) & 0xFFFFFFFF
    h ^= h >> 16
    return h & 0xFFFFFFFF


class Cell:
    __slots__ = ("ix", "iy", "kind", "edges", "lod", "decor", "center",
                 "radius", "height", "beacon", "beacon_phase", "label",
                 "label_pos", "signature", "detail_boxes", "detail_rings",
                 "detail_cache")

    def __init__(self, ix, iy, kind, edges=(), lod=(), decor=(), center=(0, 0, 0),
                 radius=0.0, height=0.0, beacon=None, beacon_phase=0.0,
                 label="", label_pos=None, signature=(), detail_boxes=(),
                 detail_rings=(), detail_cache=None):
        self.ix = ix
        self.iy = iy
        self.kind = kind
        self.edges = edges
        self.lod = lod
        self.decor = decor
        self.center = center
        self.radius = radius
        self.height = height
        self.beacon = beacon
        self.beacon_phase = beacon_phase
        self.label = label
        self.label_pos = label_pos
        self.signature = signature
        self.detail_boxes = detail_boxes
        self.detail_rings = detail_rings
        self.detail_cache = detail_cache if detail_cache is not None else {}

    def edges_for(self, distance: float, detail_distance: float):
        return self.edges if distance < detail_distance else self.lod


class Construct:
    __slots__ = ("ix", "iy", "iz", "center", "radius", "kind", "color",
                 "spin", "phase", "label", "is_ice", "signature")

    def __init__(self, ix, iy, iz, center, radius, kind, color, spin, phase,
                 label="", is_ice=False, signature=()):
        self.ix = ix
        self.iy = iy
        self.iz = iz
        self.center = center
        self.radius = radius
        self.kind = kind
        self.color = color
        self.spin = spin
        self.phase = phase
        self.label = label
        self.is_ice = is_ice
        self.signature = signature


class Matrix:
    """The procedural city and the floating constructs above it."""

    def __init__(self, seed: int, palette: Palette, cell: float = 80.0,
                 density: float = 0.78, height_scale: float = 1.0,
                 construct_density: float = 0.55, level: float = 56.0,
                 draw_distance: float = 420.0, detail_level: int = 1):
        self.seed = int(seed) & 0x7FFFFFFF
        self.palette = palette
        self.cell = float(cell)
        self.density = max(0.0, min(1.0, float(density)))
        self.height_scale = max(0.2, float(height_scale))
        self.construct_probability = max(0.0, min(1.0, float(construct_density))) * 0.150
        self.level = float(level)
        self.draw_distance = float(draw_distance)
        self.detail_level = max(1, min(5, int(detail_level)))
        self.max_z = self.level * 7.0

        self._cells: dict[tuple[int, int], Cell] = {}
        self._constructs: dict[tuple[int, int, int], Construct | None] = {}
        self._reserved: set[tuple[int, int]] = set()
        self._cell_prune_at = 2200
        self._construct_prune_at = 3800

    # ------------------------------------------------------------- randomness

    def _rng(self, *values) -> random.Random:
        h = _mix_int(self.seed, 0, 0)
        for value in values:
            h = _mix_int(h, int(value), 0x5F3759DF)
        return random.Random(h)

    # ------------------------------------------------------------- street grid

    def roads(self, camera, radius: float) -> list[Edge]:
        """Cell-sized street segments on the z=0 plane."""
        cell = self.cell
        x0 = int(math.floor((camera.pos[0] - radius) / cell))
        x1 = int(math.floor((camera.pos[0] + radius) / cell))
        y0 = int(math.floor((camera.pos[1] - radius) / cell))
        y1 = int(math.floor((camera.pos[1] + radius) / cell))
        r2 = radius * radius
        p = self.palette
        out: list[Edge] = []
        for j in range(y0, y1 + 1):
            y = j * cell
            major = (j % 4 == 0)
            color = p.street_major if major else p.street
            shade = 1.0 if major else 0.74
            color = scale(color, shade)
            for i in range(x0, x1 + 1):
                mx = (i + 0.5) * cell - camera.pos[0]
                my = y - camera.pos[1]
                if mx * mx + my * my > r2:
                    continue
                out.append(_seg(i * cell, y, 0.0, (i + 1) * cell, y, 0.0, color))
                if abs(y - camera.pos[1]) < cell * 2.2:
                    dash = scale(mix(p.street, p.hud, 0.45), 0.8)
                    out.append(_seg(i * cell + cell * 0.26, y + 3.0, 0.2,
                                    i * cell + cell * 0.56, y + 3.0, 0.2, dash))
                    out.append(_seg(i * cell + cell * 0.66, y - 3.0, 0.2,
                                    i * cell + cell * 0.94, y - 3.0, 0.2, dash))
        for i in range(x0, x1 + 1):
            x = i * cell
            major = (i % 4 == 0)
            color = p.street_major if major else p.street
            color = scale(color, 1.0 if major else 0.84)
            for j in range(y0, y1 + 1):
                mx = x - camera.pos[0]
                my = (j + 0.5) * cell - camera.pos[1]
                if mx * mx + my * my > r2:
                    continue
                out.append(_seg(x, j * cell, 0.0, x, (j + 1) * cell, 0.0, color))
                if abs(x - camera.pos[0]) < cell * 2.2:
                    dash = scale(mix(p.street, p.hud, 0.45), 0.8)
                    out.append(_seg(x + 3.0, j * cell + cell * 0.26, 0.2,
                                    x + 3.0, j * cell + cell * 0.56, 0.2, dash))
                    out.append(_seg(x - 3.0, j * cell + cell * 0.66, 0.2,
                                    x - 3.0, j * cell + cell * 0.94, 0.2, dash))
        return out

    def floor_grid(self, camera, radius: float) -> list[Edge]:
        """A fine data-lattice flush with the street: the city floor, not just
        its avenues.  It only exists near the viewpoint, where it fills the
        otherwise empty foreground."""
        cell = self.cell
        spacing = cell / 4.0
        extent = min(radius, cell * 2.8)
        if extent <= spacing:
            return []
        x0 = int(math.floor((camera.pos[0] - extent) / spacing))
        x1 = int(math.floor((camera.pos[0] + extent) / spacing))
        y0 = int(math.floor((camera.pos[1] - extent) / spacing))
        y1 = int(math.floor((camera.pos[1] + extent) / spacing))
        r2 = extent * extent
        color = scale(self.palette.grid, 0.75)
        out: list[Edge] = []
        for i in range(x0, x1 + 1):
            x = i * spacing
            if abs(x / cell - round(x / cell)) < 1e-6:
                continue
            j0 = int(math.floor((camera.pos[1] - extent) / cell))
            j1 = int(math.floor((camera.pos[1] + extent) / cell))
            for j in range(j0, j1 + 1):
                ya = max(camera.pos[1] - extent, j * cell)
                yb = min(camera.pos[1] + extent, (j + 1) * cell)
                mx = x - camera.pos[0]
                my = (ya + yb) * 0.5 - camera.pos[1]
                if mx * mx + my * my > r2:
                    continue
                out.append(_seg(x, ya, 0.12, x, yb, 0.12, color))
        for j in range(y0, y1 + 1):
            y = j * spacing
            if abs(y / cell - round(y / cell)) < 1e-6:
                continue
            i0 = int(math.floor((camera.pos[0] - extent) / cell))
            i1 = int(math.floor((camera.pos[0] + extent) / cell))
            for i in range(i0, i1 + 1):
                xa = max(camera.pos[0] - extent, i * cell)
                xb = min(camera.pos[0] + extent, (i + 1) * cell)
                mx = (xa + xb) * 0.5 - camera.pos[0]
                my = y - camera.pos[1]
                if mx * mx + my * my > r2:
                    continue
                out.append(_seg(xa, y, 0.12, xb, y, 0.12, color))
        return out

    def nodes(self, camera, radius: float) -> list[Edge]:
        """Small diamonds and masts at intersections: the grid's pulse points."""
        cell = self.cell
        limit = min(radius, cell * 3.4)
        x0 = int(math.floor((camera.pos[0] - limit) / cell))
        x1 = int(math.floor((camera.pos[0] + limit) / cell))
        y0 = int(math.floor((camera.pos[1] - limit) / cell))
        y1 = int(math.floor((camera.pos[1] + limit) / cell))
        r2 = limit * limit
        p = self.palette
        out: list[Edge] = []
        for ix in range(x0, x1 + 1):
            x = ix * cell
            for iy in range(y0, y1 + 1):
                y = iy * cell
                dx = x - camera.pos[0]
                dy = y - camera.pos[1]
                if dx * dx + dy * dy > r2:
                    continue
                if (ix + iy) % 2:
                    continue
                r = 2.8
                c = p.node
                out.append(_seg(x - r, y, 0.6, x, y + r, 0.6, c))
                out.append(_seg(x, y + r, 0.6, x + r, y, 0.6, c))
                out.append(_seg(x + r, y, 0.6, x, y - r, 0.6, c))
                out.append(_seg(x, y - r, 0.6, x - r, y, 0.6, c))
                out.append(_seg(x, y, 0.6, x, y, 5.0, scale(c, 0.7)))
        return out

    def shafts(self, camera, radius: float) -> list[Edge]:
        """Vertical neon trunks at selected intersections."""
        cell = self.cell
        limit = min(radius, cell * 3.2)
        x0 = int(math.floor((camera.pos[0] - limit) / cell))
        x1 = int(math.floor((camera.pos[0] + limit) / cell))
        y0 = int(math.floor((camera.pos[1] - limit) / cell))
        y1 = int(math.floor((camera.pos[1] + limit) / cell))
        r2 = limit * limit
        p = self.palette
        out: list[Edge] = []
        current_ix = int(round(camera.pos[0] / cell))
        current_iy = int(round(camera.pos[1] / cell))
        z_top = self.max_z
        for ix in range(x0, x1 + 1):
            x = ix * cell
            for iy in range(y0, y1 + 1):
                y = iy * cell
                dx = x - camera.pos[0]
                dy = y - camera.pos[1]
                near = dx * dx + dy * dy < (cell * 0.8) ** 2
                if not near and (ix * 3 + iy * 5) % 7 != 0:
                    continue
                if dx * dx + dy * dy > r2:
                    continue
                is_current = (ix == current_ix and iy == current_iy)
                color = p.trunk if not is_current else mix(p.trunk, p.hud, 0.25)
                # Split the trunk at level planes so the fog varies along it.
                z = 0.0
                while z < z_top - 0.01:
                    z_next = min(z_top, z + self.level)
                    out.append(_seg(x, y, z, x, y, z_next, color))
                    z = z_next
                if near:
                    for level in range(1, 6):
                        zz = level * self.level
                        if abs(zz - camera.pos[2]) > 140.0:
                            continue
                        r = 3.2
                        out.append(_seg(x - r, y, zz, x + r, y, zz,
                                        scale(color, 0.6)))
                        out.append(_seg(x, y - r, zz, x, y + r, zz,
                                        scale(color, 0.6)))
        return out

    def gate_rings(self, camera, radius: float) -> list[Edge]:
        """Rings around the shafts nearest the camera.

        When the route goes vertical at an intersection, these are the arches
        the viewpoint climbs through.
        """
        cell = self.cell
        limit = min(radius, cell * 1.15)
        x0 = int(math.floor((camera.pos[0] - limit) / cell))
        x1 = int(math.floor((camera.pos[0] + limit) / cell))
        y0 = int(math.floor((camera.pos[1] - limit) / cell))
        y1 = int(math.floor((camera.pos[1] + limit) / cell))
        p = self.palette
        out: list[Edge] = []
        n = 18
        r = cell * 0.215
        for ix in range(x0, x1 + 1):
            x = ix * cell
            for iy in range(y0, y1 + 1):
                y = iy * cell
                dx = x - camera.pos[0]
                dy = y - camera.pos[1]
                if dx * dx + dy * dy > limit * limit:
                    continue
                for level in range(1, 7):
                    z = level * self.level
                    if abs(z - camera.pos[2]) > radius * 0.85:
                        continue
                    color = p.trunk if level % 2 else mix(p.trunk, p.node, 0.45)
                    pts = [(x + math.cos(2 * math.pi * i / n) * r,
                            y + math.sin(2 * math.pi * i / n) * r, z)
                           for i in range(n)]
                    for i in range(n):
                        a = pts[i]
                        b = pts[(i + 1) % n]
                        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
        return out

    # ------------------------------------------------------------- buildings

    def _add_box(self, out: list, x0, y0, x1, y1, z0, z1, color, top_color,
                 bottom: bool = False) -> None:
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        for (x, y) in corners:
            out.append(_seg(x, y, z0, x, y, z1, color))
        for i in range(4):
            a = corners[i]
            b = corners[(i + 1) % 4]
            out.append(_seg(a[0], a[1], z1, b[0], b[1], z1, top_color))
            if bottom:
                out.append(_seg(a[0], a[1], z0, b[0], b[1], z0, color))

    def _add_ring(self, out: list, cx, cy, z, r, color, n=8, phase=0.0) -> None:
        pts = [(cx + math.cos(phase + 2 * math.pi * i / n) * r,
                cy + math.sin(phase + 2 * math.pi * i / n) * r, z)
               for i in range(n)]
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))

    def _add_pyramid(self, out: list, x0, y0, x1, y1, z0, z1, color,
                     top_color) -> None:
        corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        apex = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, z1)
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            out.append(_seg(a[0], a[1], z0, b[0], b[1], z0, color))
            out.append(_seg(a[0], a[1], z0, apex[0], apex[1], apex[2], top_color))

    def _add_windows(self, out: list, x0, y0, x1, y1, z0, z1, color,
                     rng: random.Random, count: int) -> None:
        """Short horizontal dashes on the faces: a tower's data windows."""
        for _ in range(count):
            z = rng.uniform(z0 + (z1 - z0) * 0.12, z1 - (z1 - z0) * 0.06)
            face = rng.randrange(4)
            width = (x1 - x0) if face in (0, 1) else (y1 - y0)
            if face in (0, 1):
                wx = rng.uniform(x0 + width * 0.15, x1 - width * 0.3)
                wy = y0 if face == 0 else y1
                out.append(_seg(wx, wy, z, min(x1, wx + width * 0.18), wy, z, color))
            else:
                wy = rng.uniform(y0 + width * 0.15, y1 - width * 0.3)
                wx = x0 if face == 2 else x1
                out.append(_seg(wx, wy, z, wx, min(y1, wy + width * 0.18), z, color))

    def _make_cell(self, ix: int, iy: int) -> Cell:
        cell = self.cell
        rng = self._rng(ix, iy, 0x11)
        cx = (ix + 0.5) * cell
        cy = (iy + 0.5) * cell
        if (ix, iy) in self._reserved or rng.random() > self.density:
            decor = []
            if rng.random() < 0.55:
                p = self.palette
                color = scale(p.node, 0.55)
                r = cell * rng.uniform(0.10, 0.18)
                self._add_ring(decor, cx, cy, 0.4, r, color,
                               n=10, phase=rng.uniform(0, math.pi))
                if rng.random() < 0.35:
                    decor.append(_seg(cx, cy, 0.4, cx, cy, cell * 0.10,
                                      scale(p.trunk, 0.75)))
            return Cell(ix, iy, "plaza", decor=tuple(decor),
                        center=(cx, cy, 0.0), radius=cell * 0.1,
                        signature=("plaza", 0, 0))

        inset = cell * rng.uniform(0.13, 0.20)
        x0 = ix * cell + inset
        x1 = (ix + 1) * cell - inset
        y0 = iy * cell + inset
        y1 = (iy + 1) * cell - inset
        w, d = x1 - x0, y1 - y0

        height = rng.uniform(0.24, 1.05) * cell * self.height_scale
        if rng.random() < 0.22:
            height *= rng.uniform(1.6, 3.25)
        height = max(cell * 0.12, min(height, cell * 7.4))

        base = self.palette.buildings[rng.randrange(len(self.palette.buildings))]
        base = mix(base, (255, 255, 255), rng.uniform(0.0, 0.04))
        dim = scale(base, 0.92)
        bright = mix(base, (255, 255, 255), 0.22)
        hot = mix(base, (255, 255, 255), 0.7)

        style = rng.choices(
            ("block", "ziggurat", "spire", "octagon", "twin", "stack",
             "pyramid", "cage"),
            weights=(27, 14, 15, 9, 10, 10, 8, 7), k=1)[0]

        full: list[Edge] = []
        lod: list[Edge] = []
        detail_boxes: list[tuple] = []
        detail_rings: list[tuple] = []
        # The distant silhouette is a plain box for every style; the full mesh
        # below replaces or enriches it according to the style.
        self._add_box(lod, x0, y0, x1, y1, 0.0, height, dim, bright)

        if style == "block":
            self._add_box(full, x0, y0, x1, y1, 0.0, height, dim, bright)
            detail_boxes.append((x0, y0, x1, y1, 0.0, height, base))
            for frac in (0.30, 0.62):
                self._add_ring(full, cx, cy, height * frac,
                               min(w, d) * 0.52, scale(base, 0.75))
            for face in range(4):
                if face == 0:
                    fx, fy = (x0 + x1) * 0.5, y0
                elif face == 1:
                    fx, fy = (x0 + x1) * 0.5, y1
                elif face == 2:
                    fx, fy = x0, (y0 + y1) * 0.5
                else:
                    fx, fy = x1, (y0 + y1) * 0.5
                full.append(_seg(fx, fy, height * 0.15, fx, fy, height * 0.9,
                                 scale(base, 0.55)))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height,
                              mix(base, (255, 255, 255), 0.55), rng, 10)

        elif style == "ziggurat":
            steps = 3
            for step in range(steps):
                f0 = step / steps
                f1 = (step + 0.86) / steps
                shrink = 1.0 - step * 0.19
                sx0 = cx + (x0 - cx) * shrink
                sx1 = cx + (x1 - cx) * shrink
                sy0 = cy + (y0 - cy) * shrink
                sy1 = cy + (y1 - cy) * shrink
                self._add_box(full, sx0, sy0, sx1, sy1, height * f0,
                              height * f1, dim, bright)
                detail_boxes.append((sx0, sy0, sx1, sy1,
                                     height * f0, height * f1, base))
                if step < steps - 1:
                    self._add_box(lod, sx0, sy0, sx1, sy1, height * f0,
                                  height * f1, dim, bright)
                full.append(_seg(sx0, sy0, height * f1, sx1, sy1, height * f1,
                                 bright))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height,
                              mix(base, (255, 255, 255), 0.5), rng, 7)

        elif style == "spire":
            shoulder = height * 0.62
            self._add_box(full, x0, y0, x1, y1, 0.0, shoulder, dim, bright)
            detail_boxes.append((x0, y0, x1, y1, 0.0, shoulder, base))
            self._add_pyramid(full, x0, y0, x1, y1, shoulder, height, base, bright)
            self._add_ring(full, cx, cy, shoulder, min(w, d) * 0.5,
                           mix(base, (255, 255, 255), 0.4), n=8)
            self._add_windows(full, x0, y0, x1, y1, 0.0, shoulder,
                              mix(base, (255, 255, 255), 0.55), rng, 8)

        elif style == "octagon":
            r = min(w, d) * 0.5
            self._add_octagon(full, cx, cy, r * 0.82, height * 0.78,
                              base, bright)
            self._add_octagon(lod, cx, cy, r * 0.82, height, base, bright)
            self._add_pyramid(full, cx - r * 0.5, cy - r * 0.5,
                              cx + r * 0.5, cy + r * 0.5,
                              height * 0.78, height, base, bright)
            detail_rings.append(("octagon", cx, cy, r * 0.82,
                                 height * 0.78, base))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height * 0.7,
                              mix(base, (255, 255, 255), 0.5), rng, 6)

        elif style == "twin":
            gap = w * 0.09
            split = x0 + w * 0.5
            h_left = height * rng.uniform(0.7, 1.0)
            h_right = height * rng.uniform(0.7, 1.0)
            self._add_box(full, x0, y0, split - gap, y1, 0.0,
                          h_left, dim, bright)
            self._add_box(full, split + gap, y0, x1, y1, 0.0,
                          h_right, dim, bright)
            detail_boxes.append((x0, y0, split - gap, y1, 0.0, h_left, base))
            detail_boxes.append((split + gap, y0, x1, y1, 0.0, h_right, base))
            self._add_box(lod, x0, y0, split - gap, y1, 0.0, height * 0.9,
                          dim, bright)
            self._add_box(lod, split + gap, y0, x1, y1, 0.0, height * 0.8,
                          dim, bright)
            full.append(_seg(x0, cy, height * 0.55, x1, cy, height * 0.55,
                             scale(base, 0.65)))
            self._add_windows(full, x0, y0, split - gap, y1, 0.0, height * 0.9,
                              mix(base, (255, 255, 255), 0.5), rng, 6)

        elif style == "stack":
            slabs = 3
            for slab in range(slabs):
                z0 = height * slab / slabs
                z1 = z0 + height / slabs * 0.62
                grow = 1.0 - slab * 0.08
                sx0 = cx + (x0 - cx) * grow
                sx1 = cx + (x1 - cx) * grow
                sy0 = cy + (y0 - cy) * grow
                sy1 = cy + (y1 - cy) * grow
                self._add_box(full, sx0, sy0, sx1, sy1, z0, z1, dim, bright)
                self._add_box(lod, sx0, sy0, sx1, sy1, z0, z1, dim, bright)
                detail_boxes.append((sx0, sy0, sx1, sy1, z0, z1, base))
            for (a, b) in ((cx - w * 0.12, cy - d * 0.12),
                           (cx + w * 0.12, cy - d * 0.12),
                           (cx + w * 0.12, cy + d * 0.12),
                           (cx - w * 0.12, cy + d * 0.12)):
                full.append(_seg(a, b, 0.0, a, b, height, scale(base, 0.8)))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height,
                              mix(base, (255, 255, 255), 0.55), rng, 9)

        elif style == "pyramid":
            self._add_pyramid(full, x0, y0, x1, y1, 0.0, height, base, bright)
            self._add_pyramid(lod, x0, y0, x1, y1, 0.0, height, base, bright)
            for frac in (0.35, 0.68):
                self._add_ring(full, cx, cy, height * frac,
                               min(w, d) * 0.5 * (1.0 - frac),
                               scale(base, 0.7))
            detail_rings.append(("pyramid", x0, y0, x1, y1, height, base))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height * 0.85,
                              mix(base, (255, 255, 255), 0.5), rng, 6)

        else:  # cage
            self._add_box(full, x0, y0, x1, y1, 0.0, height, scale(base, 0.72),
                          bright)
            self._add_box(lod, x0, y0, x1, y1, 0.0, height, scale(base, 0.72),
                          bright)
            detail_boxes.append((x0, y0, x1, y1, 0.0, height, base))
            for frac in (0.2, 0.5, 0.8):
                z = height * frac
                self._add_ring(full, cx, cy, z, min(w, d) * 0.5,
                               scale(base, 0.55), n=4, phase=math.pi / 4)
            for (a, b) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                full.append(_seg(a, b, 0.0, a, b, height, scale(base, 0.35)))
            full.append(_seg(x0, y0, 0.0, x1, y0, height, scale(base, 0.5)))
            full.append(_seg(x1, y0, 0.0, x1, y1, height, scale(base, 0.5)))
            self._add_windows(full, x0, y0, x1, y1, 0.0, height,
                              mix(base, (255, 255, 255), 0.6), rng, 5)

        # A mast and a blinking beacon crown every tower.
        mast = cell * rng.uniform(0.05, 0.14)
        beacon_pos = (cx, cy, height + mast)
        mast_color = scale(bright, 0.8)
        full.append(_seg(cx, cy, height, cx, cy, height + mast, mast_color))
        lod.append(_seg(cx, cy, height, cx, cy, height + mast, mast_color))
        if rng.random() < 0.35:
            r = min(w, d) * 0.32
            self._add_ring(full, cx, cy, height + mast * 0.4, r,
                           scale(base, 0.65), n=4, phase=math.pi / 4)

        label = ""
        if height > cell * 1.7 and rng.random() < 0.5:
            label = CORPORATE_NAMES[rng.randrange(len(CORPORATE_NAMES))]
        signature = (style, round(height, 2), round(w, 2), round(d, 2), label)

        return Cell(
            ix, iy, style, edges=tuple(full), lod=tuple(lod), decor=(),
            center=(cx, cy, height * 0.5),
            radius=math.sqrt((w * 0.5) ** 2 + (d * 0.5) ** 2 +
                             (height * 0.5) ** 2),
            height=height, beacon=beacon_pos,
            beacon_phase=rng.uniform(0.0, math.tau),
            label=label, label_pos=(cx, cy, height + mast + 4.0),
            signature=signature, detail_boxes=tuple(detail_boxes),
            detail_rings=tuple(detail_rings),
        )

    def _add_octagon(self, out: list, cx, cy, r, height, base, bright) -> None:
        n = 8
        phase = math.pi / 8
        bottom = [(cx + math.cos(phase + 2 * math.pi * i / n) * r,
                   cy + math.sin(phase + 2 * math.pi * i / n) * r, 0.0)
                  for i in range(n)]
        top = [(p[0], p[1], height) for p in bottom]
        for i in range(n):
            a, b = bottom[i], bottom[(i + 1) % n]
            out.append(_seg(a[0], a[1], 0.0, b[0], b[1], 0.0, scale(base, 0.5)))
            ta, tb = top[i], top[(i + 1) % n]
            out.append(_seg(ta[0], ta[1], height, tb[0], tb[1], height, bright))
            out.append(_seg(a[0], a[1], 0.0, ta[0], ta[1], height, base))

    # ------------------------------------------------------------- constructs

    def _make_construct(self, ix: int, iy: int, iz: int) -> Construct | None:
        if (ix, iy) in self._reserved:
            return None
        if self.construct_probability <= 0.0:
            return None
        rng = self._rng(ix, iy, iz, 0xC0DE)
        if rng.random() > self.construct_probability:
            return None
        cell = self.cell
        clearance = cell * 0.5
        jx = rng.uniform(-0.22, 0.22) * cell
        jy = rng.uniform(-0.22, 0.22) * cell
        cx = (ix + 0.5) * cell + jx
        cy = (iy + 0.5) * cell + jy
        cz = iz * self.level + rng.uniform(-0.16, 0.16) * self.level
        radius = cell * rng.uniform(0.15, 0.42)
        radius = min(radius, clearance - max(abs(jx), abs(jy)) - 8.0)
        if radius < 5.0:
            return None

        is_ice = rng.random() < 0.16
        if is_ice:
            kind = rng.choice(("octa", "spindle", "tetra"))
            color = self.palette.warn
        else:
            kind = rng.choices(
                ("octa", "cube", "spindle", "prism", "tetra", "gyro", "gate"),
                weights=(16, 13, 12, 10, 8, 20, 21), k=1)[0]
            color = self.palette.constructs[rng.randrange(
                len(self.palette.constructs))]
        label = ""
        if (is_ice or radius > cell * 0.24) and rng.random() < 0.65:
            label = (CONSTRUCT_LABELS[rng.randrange(len(CONSTRUCT_LABELS))]
                     if not is_ice else "ICE // " +
                     CONSTRUCT_LABELS[rng.randrange(len(CONSTRUCT_LABELS))])
        spin = (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5),
                rng.uniform(-0.7, 0.7))
        phase = (rng.uniform(0, math.tau), rng.uniform(0, math.tau),
                 rng.uniform(0, math.tau))
        signature = (kind, round(radius, 2), is_ice, label)
        return Construct(ix, iy, iz, (cx, cy, cz), radius, kind, color,
                         spin, phase, label, is_ice, signature)

    def construct_edges(self, c: Construct, time_s: float) -> list[Edge]:
        verts, pairs = SHAPES[c.kind]
        ax = c.phase[0] + c.spin[0] * time_s
        ay = c.phase[1] + c.spin[1] * time_s
        az = c.phase[2] + c.spin[2] * time_s
        r = c.radius
        cx, cy, cz = c.center
        projected = []
        for (x, y, z) in verts:
            rx, ry, rz = _rotate(x, y, z, ax, ay, az)
            projected.append((cx + rx * r, cy + ry * r, cz + rz * r))
        color = c.color
        if c.is_ice:
            color = mix(color, (255, 255, 255), 0.12)
        return [_seg(projected[a][0], projected[a][1], projected[a][2],
                     projected[b][0], projected[b][1], projected[b][2], color)
                for (a, b) in pairs]

    # ------------------------------------------------------------- scene queries

    def reserve_cells(self, cells) -> None:
        """Mark ground cells as landmark territory: no tower, no construct.

        The landmark loader runs before the first render, but a caller can also
        reserve after some cells were cached; drop those so the change is
        visible rather than silently ignored.
        """
        for ix, iy in cells:
            key = (int(ix), int(iy))
            self._reserved.add(key)
            self._cells.pop(key, None)
            for ckey in [k for k in self._constructs if k[:2] == key]:
                self._constructs.pop(ckey, None)

    def detail_edges(self, cell: Cell, level: int | None = None):
        """The full mesh plus volume lattices, built lazily for near cells."""
        level = self.detail_level if level is None else int(level)
        if level <= 1 or not cell.detail_boxes:
            return cell.edges
        cached = cell.detail_cache.get(level)
        if cached is not None:
            return cached
        out = list(cell.edges)
        for x0, y0, x1, y1, z0, z1, base in cell.detail_boxes:
            local = effective_level(level, (x1 - x0, y1 - y0, z1 - z0), 5)
            if local <= 1:
                continue
            color = scale(mix(base, self.palette.hud, 0.30), 0.80)
            out.extend(volume_lattice(x0, y0, x1, y1, z0, z1, local, color))
        for spec in cell.detail_rings:
            color = scale(mix(spec[-1], self.palette.hud, 0.30), 0.80)
            n = min(4, level)
            if spec[0] == "octagon":
                _, cx, cy, radius, height, _base = spec
                for layer in range(1, n):
                    z = height * layer / n
                    pts = [(cx + math.cos(math.pi / 8 + 2 * math.pi * i / 8) * radius,
                            cy + math.sin(math.pi / 8 + 2 * math.pi * i / 8) * radius,
                            z) for i in range(8)]
                    for i in range(8):
                        a, b = pts[i], pts[(i + 1) % 8]
                        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
            else:
                _, x0, y0, x1, y1, height, _base = spec
                for layer in range(1, n):
                    frac = layer / n
                    scale_f = 1.0 - frac
                    ring = [(cx0, cy0, height * frac) for cx0, cy0 in (
                        (x0 + (x1 - x0) * (1 - scale_f) * 0.5,
                         y0 + (y1 - y0) * (1 - scale_f) * 0.5),
                        (x1 - (x1 - x0) * (1 - scale_f) * 0.5,
                         y0 + (y1 - y0) * (1 - scale_f) * 0.5),
                        (x1 - (x1 - x0) * (1 - scale_f) * 0.5,
                         y1 - (y1 - y0) * (1 - scale_f) * 0.5),
                        (x0 + (x1 - x0) * (1 - scale_f) * 0.5,
                         y1 - (y1 - y0) * (1 - scale_f) * 0.5))]
                    for i in range(4):
                        a, b = ring[i], ring[(i + 1) % 4]
                        out.append(_seg(a[0], a[1], a[2], b[0], b[1], b[2], color))
        cached = tuple(out)
        cell.detail_cache[level] = cached
        return cached

    def cell_at(self, ix: int, iy: int) -> Cell:
        key = (int(ix), int(iy))
        cell = self._cells.get(key)
        if cell is None:
            cell = self._make_cell(key[0], key[1])
            self._cells[key] = cell
        return cell

    def construct_at(self, ix: int, iy: int, iz: int) -> Construct | None:
        key = (int(ix), int(iy), int(iz))
        if key in self._constructs:
            return self._constructs[key]
        c = self._make_construct(key[0], key[1], key[2])
        self._constructs[key] = c
        return c

    def city_signature(self, ix: int, iy: int) -> tuple:
        return self.cell_at(ix, iy).signature

    def construct_signature(self, ix: int, iy: int, iz: int) -> tuple:
        c = self.construct_at(ix, iy, iz)
        return c.signature if c is not None else ()

    def buildings(self, camera, radius: float) -> list[tuple[float, Cell]]:
        cell = self.cell
        x0 = int(math.floor((camera.pos[0] - radius) / cell))
        x1 = int(math.floor((camera.pos[0] + radius) / cell))
        y0 = int(math.floor((camera.pos[1] - radius) / cell))
        y1 = int(math.floor((camera.pos[1] + radius) / cell))
        out = []
        r2 = radius * radius
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                c = self.cell_at(ix, iy)
                if not c.edges:
                    continue
                dx = c.center[0] - camera.pos[0]
                dy = c.center[1] - camera.pos[1]
                dz = c.center[2] - camera.pos[2]
                d2 = dx * dx + dy * dy + dz * dz
                if d2 > r2:
                    continue
                out.append((math.sqrt(d2), c))
        out.sort(key=lambda item: item[0])
        self._prune_cells(camera, radius)
        return out

    def constructs(self, camera, radius: float) -> list[tuple[float, Construct]]:
        cell = self.cell
        x0 = int(math.floor((camera.pos[0] - radius) / cell))
        x1 = int(math.floor((camera.pos[0] + radius) / cell))
        y0 = int(math.floor((camera.pos[1] - radius) / cell))
        y1 = int(math.floor((camera.pos[1] + radius) / cell))
        z = camera.pos[2]
        out = []
        r2 = radius * radius
        for ix in range(x0, x1 + 1):
            for iy in range(y0, y1 + 1):
                for iz in range(1, 7):
                    cz = iz * self.level
                    if abs(cz - z) > radius:
                        continue
                    c = self.construct_at(ix, iy, iz)
                    if c is None:
                        continue
                    dx = c.center[0] - camera.pos[0]
                    dy = c.center[1] - camera.pos[1]
                    dz = c.center[2] - camera.pos[2]
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 > r2:
                        continue
                    out.append((math.sqrt(d2), c))
        out.sort(key=lambda item: item[0])
        self._prune_constructs(camera, radius)
        return out

    def traffic(self, camera, time_s: float, radius: float,
                limit: int = 180) -> list[Edge]:
        cell = self.cell
        limit = max(0, int(limit))
        if limit == 0:
            return []
        extent = min(radius, cell * 4.2)
        x0 = int(math.floor((camera.pos[0] - extent) / cell))
        x1 = int(math.floor((camera.pos[0] + extent) / cell))
        y0 = int(math.floor((camera.pos[1] - extent) / cell))
        y1 = int(math.floor((camera.pos[1] + extent) / cell))
        r2 = extent * extent
        out: list[Edge] = []
        p = self.palette
        seed = self.seed

        def maybe(ix, iy, h):
            lane = -2.2 if h & 4 else 2.2
            phase = ((h >> 8) & 1023) / 1023.0
            speed = 0.55 + (((h >> 14) & 255) / 255.0) * 0.9
            frac = (time_s * speed * 0.42 + phase) % 1.0
            direction = 1.0 if h & 1 else -1.0
            color = p.traffic
            if h & 32:
                color = mix(p.traffic, p.node, 0.45)
            return lane, frac, direction, color

        for j in range(y0, y1 + 1):
            y = j * cell
            if abs(y - camera.pos[1]) > extent:
                continue
            for i in range(x0, x1 + 1):
                if abs((i + 0.5) * cell - camera.pos[0]) > extent:
                    continue
                h = _mix_int(seed, i * 31 + 7, j * 57 + 3)
                if h % 100 > 82:
                    continue
                lane, frac, direction, color = maybe(i, j, h)
                x = (i + frac) * cell
                dx = x - camera.pos[0]
                dy = y + lane - camera.pos[1]
                if dx * dx + dy * dy > r2:
                    continue
                out.append(_seg(x, y + lane, 0.55,
                                x + direction * cell * 0.150, y + lane, 0.55,
                                color))
                if len(out) >= limit:
                    return out
        for i in range(x0, x1 + 1):
            x = i * cell
            if abs(x - camera.pos[0]) > extent:
                continue
            for j in range(y0, y1 + 1):
                if abs((j + 0.5) * cell - camera.pos[1]) > extent:
                    continue
                h = _mix_int(seed + 17, i * 43 + 5, j * 29 + 11)
                if h % 100 > 82:
                    continue
                lane, frac, direction, color = maybe(i, j, h)
                y = (j + frac) * cell
                dx = x + lane - camera.pos[0]
                dy = y - camera.pos[1]
                if dx * dx + dy * dy > r2:
                    continue
                out.append(_seg(x + lane, y, 0.55,
                                x + lane, y + direction * cell * 0.150, 0.55,
                                color))
                if len(out) >= limit:
                    return out

        # Vertical traffic on the nearest shaft: cargo riding the trunk.
        cx = round(camera.pos[0] / cell) * cell
        cy = round(camera.pos[1] / cell) * cell
        for k in range(6):
            h = _mix_int(seed + 91, k, 0xBEEF)
            phase = (h & 1023) / 1023.0
            speed = 0.35 + ((h >> 10) & 255) / 255.0 * 0.6
            z = (time_s * speed * self.level + phase * self.max_z) % self.max_z
            lane = -2.6 if k % 2 else 2.6
            color = mix(p.traffic, p.trunk, 0.45)
            out.append(_seg(cx + lane, cy, z, cx + lane, cy, z + 4.0, color))
        return out

    # ------------------------------------------------------------- cache hygiene

    def _prune_cells(self, camera, radius: float) -> None:
        if len(self._cells) <= self._cell_prune_at:
            return
        cell = self.cell
        keep = radius * 1.8
        x, y = camera.pos[0], camera.pos[1]
        doomed = []
        for (ix, iy), c in self._cells.items():
            cx = (ix + 0.5) * cell
            cy = (iy + 0.5) * cell
            if abs(cx - x) > keep or abs(cy - y) > keep:
                doomed.append((ix, iy))
        for key in doomed:
            self._cells.pop(key, None)

    def _prune_constructs(self, camera, radius: float) -> None:
        if len(self._constructs) <= self._construct_prune_at:
            return
        keep = radius * 1.8
        doomed = []
        for (ix, iy, iz) in self._constructs:
            if (abs((ix + 0.5) * self.cell - camera.pos[0]) > keep or
                    abs((iy + 0.5) * self.cell - camera.pos[1]) > keep or
                    abs(iz * self.level - camera.pos[2]) > keep):
                doomed.append((ix, iy, iz))
        for key in doomed:
            self._constructs.pop(key, None)

    def stats(self) -> dict:
        return {"cell_cache": len(self._cells), "construct_cache": len(self._constructs),
                "reserved_cells": len(self._reserved)}

    def signature(self) -> tuple:
        """A cheap fingerprint of the seeded world, for tests and logging."""
        return (self.city_signature(0, 0), self.city_signature(3, -2),
                self.city_signature(-5, 7), self.construct_signature(2, 3, 2),
                self.construct_signature(-1, 4, 4))
