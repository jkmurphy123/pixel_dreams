"""Parametric wireframe meshes for the Trench Run mode (Phases 1–2).

All coordinates are world units (metres-ish), +Y up, +Z forward.  Meshes are
built once and then either placed in world space (static props) or transformed
per frame (the X-wing).  Edge roles are semantic so the renderer can apply
depth colour and LOD without knowing anything about the asset.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


Point = tuple[float, float, float]
ColorRole = str

ROLES = {"primary", "secondary", "detail", "hazard", "emissive", "rebel", "ship"}
PANEL = "panel"


@dataclass(frozen=True)
class Edge:
    a: int
    b: int
    role: ColorRole = "secondary"


@dataclass(frozen=True)
class Face:
    verts: tuple[int, ...]
    role: str = PANEL


@dataclass(frozen=True)
class Mesh:
    verts: tuple[Point, ...]
    edges: tuple[Edge, ...]
    faces: tuple[Face, ...] = ()

    def lod(self, level: int) -> "Mesh":
        """0 = all, 1 = drop detail, 2 = structural only."""
        if level <= 0:
            return self
        if level == 1:
            keep = ROLES - {"detail"}
        else:
            keep = {"primary", "hazard", "emissive", "rebel", "ship"}
        edges = tuple(e for e in self.edges if e.role in keep)
        used = {i for e in edges for i in (e.a, e.b)}
        faces = tuple(f for f in self.faces if all(i in used for i in f.verts))
        return Mesh(self.verts, edges, faces)

    def bounds(self) -> tuple[Point, float]:
        if not self.verts:
            return (0.0, 0.0, 0.0), 0.0
        xs, ys, zs = zip(*self.verts)
        center = ((min(xs) + max(xs)) * 0.5,
                  (min(ys) + max(ys)) * 0.5,
                  (min(zs) + max(zs)) * 0.5)
        r2 = max((x - center[0]) ** 2 + (y - center[1]) ** 2
                 + (z - center[2]) ** 2 for x, y, z in self.verts)
        return center, math.sqrt(r2)


class MeshBuilder:
    """Deduplicating point/edge/face builder."""

    def __init__(self):
        self._verts: list[Point] = []
        self._index: dict[tuple[float, float, float], int] = {}
        self._edges: list[Edge] = []
        self._faces: list[Face] = []

    def v(self, p: Sequence[float]) -> int:
        key = (round(float(p[0]), 4), round(float(p[1]), 4), round(float(p[2]), 4))
        idx = self._index.get(key)
        if idx is None:
            idx = len(self._verts)
            self._index[key] = idx
            self._verts.append((float(p[0]), float(p[1]), float(p[2])))
        return idx

    def edge(self, a: Sequence[float] | int, b: Sequence[float] | int,
             role: ColorRole = "secondary") -> None:
        ia = a if isinstance(a, int) else self.v(a)
        ib = b if isinstance(b, int) else self.v(b)
        if ia != ib:
            self._edges.append(Edge(ia, ib, role))

    def polyline(self, points: Iterable[Sequence[float]],
                 role: ColorRole = "secondary", closed: bool = False) -> None:
        ids = [self.v(p) for p in points]
        for i in range(len(ids) - 1):
            self.edge(ids[i], ids[i + 1], role)
        if closed and len(ids) > 2:
            self.edge(ids[-1], ids[0], role)

    def face(self, points: Iterable[Sequence[float]], role: str = PANEL) -> None:
        ids = [self.v(p) for p in points]
        if len(ids) >= 3:
            self._faces.append(Face(tuple(ids), role))

    def box(self, x0: float, x1: float, y0: float, y1: float,
            z0: float, z1: float, role: ColorRole = "secondary",
            faces: bool = True) -> None:
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0),
                     (4, 5), (5, 6), (6, 7), (7, 4),
                     (0, 4), (1, 5), (2, 6), (3, 7)):
            self.edge(p[a], p[b], role)
        if faces:
            self.face((p[4], p[5], p[6], p[7]), PANEL)
            self.face((p[0], p[1], p[2], p[3]), PANEL)
            self.face((p[0], p[1], p[5], p[4]), PANEL)
            self.face((p[2], p[3], p[7], p[6]), PANEL)
            self.face((p[1], p[2], p[6], p[5]), PANEL)
            self.face((p[0], p[3], p[7], p[4]), PANEL)

    def build(self) -> Mesh:
        return Mesh(tuple(self._verts), tuple(self._edges), tuple(self._faces))


def ring_points(cx: float, cy: float, cz: float, radius: float, n: int,
                axis: str = "y") -> list[Point]:
    pts = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        if axis == "y":
            pts.append((cx + radius * ca, cy, cz + radius * sa))
        elif axis == "z":
            pts.append((cx + radius * ca, cy + radius * sa, cz))
        else:
            pts.append((cx, cy + radius * ca, cz + radius * sa))
    return pts


def cylinder(b: MeshBuilder, axis: str, cx: float, cy: float, cz: float,
             length: float, radius: float, n: int = 8,
             rail_role: ColorRole = "secondary",
             cap_role: ColorRole | None = None) -> list[Point]:
    """Cylinder starting at (cx,cy,cz) and extending along the signed axis."""
    start = (cx, cy, cz)
    if axis == "x":
        end = (cx + length, cy, cz)
    elif axis == "y":
        end = (cx, cy + length, cz)
    else:
        end = (cx, cy, cz + length)
    r0 = ring_points(*start, radius, n, axis)
    r1 = ring_points(*end, radius, n, axis)
    b.polyline(r0, rail_role, closed=True)
    b.polyline(r1, rail_role, closed=True)
    for i in range(n):
        b.edge(r0[i], r1[i], rail_role)
    if cap_role:
        for pts in (r0, r1):
            for i in range(n):
                b.edge(pts[i], pts[(i + 1) % n], cap_role)
    return r0 + r1


def dome(b: MeshBuilder, cx: float, cy: float, cz: float, radius: float,
         meridians: int = 12, rings: int = 2, primary_every: int = 3,
         hatch: bool = True) -> list[Point]:
    """Wireframe hemisphere with its base at (cx,cy,cz)."""
    base = ring_points(cx, cy, cz, radius, meridians, "y")
    b.polyline(base, "primary", closed=True)
    lat: list[list[Point]] = []
    for j in range(1, rings + 1):
        phi = (math.pi * 0.5) * j / (rings + 1)
        rr = radius * math.cos(phi)
        yy = cy + radius * math.sin(phi)
        pts = ring_points(cx, yy, cz, rr, meridians, "y")
        lat.append(pts)
        b.polyline(pts, "primary" if j == rings else "secondary", closed=True)
    top = (cx, cy + radius, cz)
    for i in range(meridians):
        role = "primary" if i % primary_every == 0 else "secondary"
        b.edge(base[i], lat[0][i], role)
        for j in range(len(lat) - 1):
            b.edge(lat[j][i], lat[j + 1][i], role)
        b.edge(lat[-1][i], top, role)
    if hatch:
        # A small access hatch on the front face, plus vent slots.
        b.polyline([(cx - radius * 0.28, cy + radius * 0.10, cz + radius * 0.88),
                    (cx + radius * 0.28, cy + radius * 0.10, cz + radius * 0.88),
                    (cx + radius * 0.28, cy + radius * 0.34, cz + radius * 0.80),
                    (cx - radius * 0.28, cy + radius * 0.34, cz + radius * 0.80)],
                   "secondary", closed=True)
        for k in range(3):
            zz = cz + radius * (0.98 - k * 0.04)
            b.edge((cx - radius * 0.18, cy + radius * 0.44, zz),
                   (cx + radius * 0.18, cy + radius * 0.44, zz), "detail")
    b.edge(top, (cx, cy + radius * 1.10, cz), "emissive")
    return base + [p for ps in lat for p in ps] + [top]


def transform_point(point: Sequence[float], pos: Sequence[float],
                    yaw_deg: float = 0.0, scale: float = 1.0,
                    pitch_deg: float = 0.0,
                    roll_deg: float = 0.0) -> Point:
    """Transform one local point (roll -> pitch -> yaw -> translate)."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    x, y, z = point[0] * scale, point[1] * scale, point[2] * scale
    x, y = x * cr - y * sr, x * sr + y * cr
    y, z = y * cp - z * sp, y * sp + z * cp
    x, z = x * cy + z * sy, -x * sy + z * cy
    return (x + pos[0], y + pos[1], z + pos[2])


def transform_mesh(mesh: Mesh, pos: Sequence[float], yaw_deg: float = 0.0,
                   scale: float = 1.0, pitch_deg: float = 0.0,
                   roll_deg: float = 0.0) -> Mesh:
    """Transform a local mesh into world space (roll -> pitch -> yaw)."""
    out = [transform_point(p, pos, yaw_deg, scale, pitch_deg, roll_deg)
           for p in mesh.verts]
    return Mesh(tuple(out), mesh.edges, mesh.faces)


@dataclass(frozen=True)
class ShipAsset:
    mesh: Mesh
    engines: tuple[Point, ...]
    cannons: tuple[Point, ...]


def build_xwing() -> ShipAsset:
    b = MeshBuilder()

    # Fuselage: rear box, mid box, and a pyramidal nose.
    b.box(-0.80, 0.80, -0.55, 0.60, -4.60, 1.40, "primary", faces=False)
    b.box(-0.62, 0.62, -0.45, 0.70, 1.40, 3.30, "primary", faces=False)
    nose = (0.0, 0.05, 6.30)
    for x, y in ((-0.62, -0.45), (0.62, -0.45), (0.62, 0.70), (-0.62, 0.70)):
        b.edge((x, y, 3.30), nose, "primary")
    b.edge((-0.62, 0.70, 3.30), (0.62, 0.70, 3.30), "primary")
    b.edge((-0.62, -0.45, 3.30), (0.62, -0.45, 3.30), "primary")

    # Cockpit canopy, slightly raised and slanted forward.
    b.box(-0.42, 0.42, 0.60, 1.18, -0.65, 1.55, "primary", faces=False)
    b.edge((-0.42, 1.18, 1.55), (0.0, 1.10, 2.30), "secondary")
    b.edge((0.42, 1.18, 1.55), (0.0, 1.10, 2.30), "secondary")
    b.edge((-0.42, 0.60, 1.55), (0.0, 0.58, 2.30), "secondary")
    b.edge((0.42, 0.60, 1.55), (0.0, 0.58, 2.30), "secondary")
    b.edge((0.0, 1.10, 2.30), (0.0, 0.58, 2.30), "detail")

    # Astromech dome behind the cockpit.
    dome(b, 0.0, 0.60, -2.35, 0.48, meridians=8, rings=1,
         primary_every=2, hatch=False)

    # Four S-foils.  Upper/lower wings are mirrored in Y; left/right in X.
    engines: list[Point] = []
    cannons: list[Point] = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            root_f = (0.80 * sx, 0.36 * sy, -1.20)
            root_b = (0.80 * sx, 0.46 * sy, -4.30)
            tip_f = (5.35 * sx, 2.55 * sy, -3.05)
            tip_b = (5.35 * sx, 2.70 * sy, -4.55)
            off = (0.0, 0.075, 0.0)
            top = [(root_f[0], root_f[1] + off[1], root_f[2]),
                   (tip_f[0], tip_f[1] + off[1], tip_f[2]),
                   (tip_b[0], tip_b[1] + off[1], tip_b[2]),
                   (root_b[0], root_b[1] + off[1], root_b[2])]
            bot = [(root_f[0], root_f[1] - off[1], root_f[2]),
                   (tip_f[0], tip_f[1] - off[1], tip_f[2]),
                   (tip_b[0], tip_b[1] - off[1], tip_b[2]),
                   (root_b[0], root_b[1] - off[1], root_b[2])]
            b.polyline(top, "primary", closed=True)
            b.polyline(bot, "secondary", closed=True)
            for p, q in zip(top, bot):
                b.edge(p, q, "secondary")
            b.edge(top[0], top[2], "detail")
            b.edge(bot[1], bot[3], "detail")
            # Rebel stripe along the leading edge.
            b.edge(top[0], top[1], "rebel")

            # Wingtip cannon: two rails and a muzzle ring forward of the tip.
            base = (tip_f[0], tip_f[1], -2.90)
            muzzle = (tip_f[0], tip_f[1], 4.55)
            b.edge(base, muzzle, "primary")
            b.edge((base[0], base[1] + 0.10, base[2]),
                   (muzzle[0], muzzle[1] + 0.10, muzzle[2]), "secondary")
            ring = ring_points(muzzle[0], muzzle[1], muzzle[2], 0.16, 6, "z")
            b.polyline(ring, "primary", closed=True)
            cannons.append(muzzle)

            # Engine at the wing root, plus a pylon to the fuselage.
            ex, ey = 2.65 * sx, 1.10 * sy
            cylinder(b, "z", ex, ey, -4.90, 3.35, 0.42, 8,
                     rail_role="secondary", cap_role="primary")
            b.edge((ex, ey, -4.90), (0.85 * sx, 0.45 * sy, -3.10), "secondary")
            b.edge((ex, ey, -1.55), (0.85 * sx, 0.45 * sy, -1.20), "secondary")
            nose_ring = ring_points(ex, ey, -4.90, 0.42, 8, "z")
            b.polyline(nose_ring, "emissive", closed=True)
            engines.append((ex, ey, -5.02))

    # A few fuselage panel lines to keep the hull from reading as a plain box.
    b.edge((-0.80, 0.10, -1.00), (0.80, 0.10, -1.00), "detail")
    b.edge((-0.80, 0.10, -3.40), (0.80, 0.10, -3.40), "detail")
    b.edge((0.0, 0.60, -4.60), (0.0, 0.60, -3.20), "detail")

    return ShipAsset(b.build(), tuple(engines), tuple(cannons))


def build_turret() -> Mesh:
    """Twin turbolaser, base at origin, barrels pointing toward -X."""
    b = MeshBuilder()
    cylinder(b, "y", 0.0, 0.0, 0.0, 1.20, 2.35, 8,
             rail_role="primary", cap_role="primary")
    b.face(ring_points(0.0, 1.20, 0.0, 2.35, 8, "y"), PANEL)
    # Yoke posts and pivot.
    for z in (-1.15, 1.15):
        b.box(-0.55, 0.55, 1.20, 2.45, z - 0.18, z + 0.18, "primary", faces=False)
    b.edge((0.0, 2.45, -1.15), (0.0, 2.45, 1.15), "primary")
    # Head.
    b.box(-1.15, 1.15, 2.15, 3.15, -1.15, 1.15, "primary", faces=False)
    b.box(-0.55, 0.55, 2.80, 3.35, -0.55, 0.55, "secondary", faces=False)
    # Twin barrels with muzzle rings.
    for z in (-0.48, 0.48):
        b.edge((-0.80, 2.72, z), (-6.20, 2.72, z), "primary")
        b.edge((-0.80, 2.52, z), (-6.20, 2.52, z), "secondary")
        b.edge((-0.80, 2.72, z), (-0.80, 2.52, z), "secondary")
        b.edge((-6.20, 2.72, z), (-6.20, 2.52, z), "primary")
        ring = ring_points(-6.20, 2.62, z, 0.22, 6, "x")
        b.polyline(ring, "primary", closed=True)
    # A short mast and beacon make the silhouette readable at kiosk scale.
    b.edge((0.0, 3.15, 0.0), (0.0, 5.05, 0.0), "primary")
    b.polyline(ring_points(0.0, 4.65, 0.0, 0.42, 6, "y"), "secondary",
               closed=True)
    b.edge((0.0, 5.05, 0.0), (0.0, 5.45, 0.0), "emissive")
    # Power cable and a hazard ring around the base.
    b.polyline([(2.05, 0.25, 0.80), (2.55, 1.10, 1.25), (1.20, 2.10, 1.00),
                (0.75, 2.55, 0.60)], "detail")
    b.polyline(ring_points(0.0, 0.14, 0.0, 2.48, 12, "y"), "hazard", closed=True)
    return b.build()


def build_dome(radius: float = 6.0) -> Mesh:
    b = MeshBuilder()
    dome(b, 0.0, 0.0, 0.0, radius, meridians=12, rings=2,
         primary_every=3, hatch=True)
    # Base skirt and a couple of pipe stubs make it read as an installation.
    b.polyline(ring_points(0.0, -0.55, 0.0, radius * 1.04, 12, "y"),
               "secondary", closed=True)
    for i in range(4):
        a = math.pi * 2 * i / 4 + 0.4
        x = radius * 1.06 * math.cos(a)
        z = radius * 1.06 * math.sin(a)
        b.edge((x, 0.0, z), (x * 1.10, -0.55, z * 1.10), "detail")
    return b.build()


TRENCH_RIM_WIDTH = 4.0


def build_trench_module(width: float, depth: float,
                        variant: int = 0) -> tuple[Mesh, Mesh]:
    """One 12-unit trench module with a near and a far LOD."""
    w = width * 0.5
    z0, z1 = 0.0, 12.0
    b = MeshBuilder()

    # Floor panels.
    for x in (-w, -w * 0.5, 0.0, w * 0.5, w):
        role = "primary" if abs(x) == w else "secondary"
        b.edge((x, 0.0, z0), (x, 0.0, z1), role)
    for z in (0.0, 6.0, 12.0):
        b.edge((-w, 0.0, z), (w, 0.0, z), "primary" if z in (z0, z1) else "secondary")
    b.face(((-w, 0.0, z0), (w, 0.0, z0), (w, 0.0, z1), (-w, 0.0, z1)), PANEL)

    # Dashed centre guide.
    for z in range(2, 12, 4):
        b.edge((0.0, 0.02, z), (0.0, 0.02, z + 1.6), "detail")

    # Walls, rims, and ribs on both sides.
    for sx in (-1.0, 1.0):
        x = w * sx
        for y in (0.0, depth * 0.5, depth):
            role = "primary" if y in (0.0, depth) else "secondary"
            b.edge((x, y, z0), (x, y, z1), role)
        for z in (0.0, 6.0, 12.0):
            b.edge((x, 0.0, z), (x, depth, z),
                   "primary" if z in (0.0, 12.0) else "secondary")
        b.face(((x, 0.0, z0), (x, 0.0, z1),
                (x, depth, z1), (x, depth, z0)), PANEL)

        # Buttress ribs and sparse diagonal braces.  Keeping these mostly
        # detail prevents the wall from reading as a picket fence.
        for z in (0.0, 6.0, 12.0):
            b.edge((x, depth * 0.22, z), (x, depth * 0.78, z + 3.0), "detail")
        # Rim cap.
        outer = (w + TRENCH_RIM_WIDTH) * sx
        b.edge((x, depth, z0), (outer, depth, z0), "primary")
        b.edge((x, depth, z1), (outer, depth, z1), "primary")
        b.edge((outer, depth, z0), (outer, depth, z1), "primary")
        for z in (6.0,):
            b.edge((x, depth, z), (outer, depth, z), "secondary")
        b.face(((x, depth, z0), (outer, depth, z0),
                (outer, depth, z1), (x, depth, z1)), PANEL)

        # Pipe run near the rim and hazard strip near the floor.
        px = (w - 1.10) * sx
        b.edge((px, depth - 1.55, z0), (px, depth - 1.55, z1), "detail")
        b.edge((px, depth - 1.25, z0), (px, depth - 1.25, z1), "detail")
        for z in (3.0, 9.0):
            b.edge((px, depth - 1.55, z), (px, depth - 1.25, z), "detail")
        hx = (w - 0.25) * sx
        b.edge((hx, 1.05, z0 + 0.4), (hx, 1.05, z1 - 0.4), "hazard")

        # Rim warning lights: one short strobe per module, not a fence.
        b.edge((x, depth, 6.0), (x, depth + 0.7, 6.0), "emissive")

        # Variant details add a ladder or alcove without breaking the seams.
        if variant == 1 and sx > 0:
            for k in range(5):
                z = 7.0 + k * 0.9
                b.edge((x - 0.45, 1.0 * k, z), (x - 0.05, 1.0 * k, z), "detail")
        if variant == 2 and sx < 0:
            b.polyline([(x + 0.02, 3.0, 4.2), (x + 0.02, 5.4, 4.2),
                        (x + 0.02, 5.4, 8.8), (x + 0.02, 3.0, 8.8)],
                       "secondary", closed=True)
            b.face(((x + 0.02, 3.0, 4.2), (x + 0.02, 3.0, 8.8),
                    (x + 0.02, 5.4, 8.8), (x + 0.02, 5.4, 4.2)), PANEL)

    # Damage variants overlay a broken wall section and debris.  The
    # continuous floor rails and rim edges are never removed, so module seams
    # remain valid.
    if variant >= 3:
        sx = 1.0 if variant % 2 == 0 else -1.0
        x = (w - 0.04) * sx
        hole = [(x, 2.2, 3.6), (x, 6.8, 3.6), (x, 7.6, 5.2),
                (x, 5.0, 7.0), (x, 2.4, 8.4), (x, 2.2, 6.0)]
        b.polyline(hole, "hazard", closed=True)
        b.face(hole, PANEL)
        for z in (4.0, 6.0, 8.0):
            b.edge((x, 1.8, z), (x, 3.0, z + 0.6), "primary")
        b.box((w - 4.2) * sx, (w - 0.8) * sx, 0.0, 0.6, 8.2, 10.4,
              "secondary", faces=False)
        b.box((w - 3.0) * sx, (w - 1.4) * sx, 0.0, 0.4, 6.6, 7.8,
              "detail", faces=False)
        if variant == 4:
            for k in range(3):
                z = 4.4 + k * 1.4
                b.edge((x, 4.2, z), (x - 0.8 * sx, 5.0, z + 0.4),
                       "emissive")

    near = b.build()
    return near, near.lod(2)


def build_plate_mid(x0: float, x1: float, z0: float, z1: float, top: float,
                    variant: int = 0) -> Mesh:
    """Middle surface LOD: top outline, short corner sides, and two seams."""
    b = MeshBuilder()
    corners = [(x0, top, z0), (x1, top, z0), (x1, top, z1), (x0, top, z1)]
    b.polyline(corners, "secondary", closed=True)
    b.face(corners, PANEL)
    for x, _, z in corners:
        b.edge((x, top, z), (x, top - 1.2, z), "secondary")
    mx = (x0 + x1) * 0.5
    mz = (z0 + z1) * 0.5
    b.edge((mx, top, z0), (mx, top, z1), "detail")
    b.edge((x0, top, mz), (x1, top, mz), "detail")
    return b.build()


def build_plate(x0: float, x1: float, z0: float, z1: float, top: float,
                detail: bool = True, variant: int = 0) -> Mesh:
    """A panel with a deep enough skirt to show height steps between plates."""
    b = MeshBuilder()
    skirt = 3.20
    corners = [(x0, top, z0), (x1, top, z0), (x1, top, z1), (x0, top, z1)]
    low = [(x, top - skirt, z) for x, _, z in corners]
    b.polyline(corners, "secondary", closed=True)
    b.face(corners, PANEL)
    if not detail:
        mx = (x0 + x1) * 0.5
        mz = (z0 + z1) * 0.5
        b.edge((mx, top, z0), (mx, top, z1), "detail")
        b.edge((x0, top, mz), (x1, top, mz), "detail")
        return b.build()
    for i in range(4):
        j = (i + 1) % 4
        b.edge(corners[i], low[i], "secondary")
        b.edge(low[i], low[j], "detail")
        b.face((corners[i], corners[j], low[j], low[i]), PANEL)
    if detail:
        mz = (z0 + z1) * 0.5
        # Wide merged panels get a deeper seam rhythm instead of one huge
        # outline.  All of this is detail-role so the trench stays dominant.
        width = x1 - x0
        n = max(1, int(round(width / 36.0)))
        for i in range(1, n):
            xx = x0 + width * i / n
            b.edge((xx, top, z0), (xx, top, z1), "detail")
        b.edge((x0, top, mz), (x1, top, mz), "detail")
        # A small access hatch and, on some variants, a raised vent.
        hw, hd = min(6.0, width * 0.18), 4.5
        hx = x0 + 5.0 + (variant % 4) * 2.0
        hz = z0 + 6.0 + (variant % 3) * 3.0
        if variant % 2 == 0 and hx + hw < x1 and hz + hd < z1:
            b.polyline([(hx, top + 0.02, hz), (hx + hw, top + 0.02, hz),
                        (hx + hw, top + 0.02, hz + hd),
                        (hx, top + 0.02, hz + hd)], "detail", closed=True)
            b.edge((hx, top + 0.02, hz), (hx + hw, top + 0.02, hz + hd),
                   "detail")
        if width >= 90.0 and variant % 5 == 0:
            vx, vz = x0 + 12.0, z0 + 12.0
            b.box(vx, vx + 7.0, top, top + 1.0, vz, vz + 6.0,
                  "detail", faces=False)
    return b.build()
