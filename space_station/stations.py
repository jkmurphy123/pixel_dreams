"""Procedural wireframe geometry for Space Station V.

The station is a double habitat wheel: two segmented torus rings on one axis,
each tied by eight truss spokes to a central hub, with a docking spine through
the middle, a docking module at the front, an antenna boom and dish at the
back, radiator fins, service pods and a band of habitat windows around each
rim.  Every edge carries a semantic role so the renderer can colour by role
and depth without knowing what part it belongs to.

Coordinates are station-local: +Z is the spin axis, +X/+Y span the ring plane,
and the rings sit at z = +/- RING_SEPARATION / 2.  One station unit is the ring
radius.  The mesh is built once per detail level (1-4) at mode entry; changing
quality only selects a different prebuilt mesh.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass

Point = tuple[float, float, float]
Role = str

#: Ring radius is 1.0; these are the other proportions.
RING_RADIUS = 1.0
RING_TUBE = 0.077
RING_SEPARATION = 1.00
HUB_RADIUS = 0.150
SPOKE_INNER = 0.170
SPOKE_OUTER = RING_RADIUS - RING_TUBE * 0.86

ROLES = ("hull_hi", "hull", "structure", "detail", "window", "beacon", "dock")


@dataclass(frozen=True)
class Edge:
    a: int
    b: int
    role: Role


@dataclass(frozen=True)
class StationMesh:
    verts: tuple[Point, ...]
    edges: tuple[Edge, ...]
    detail: int

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def role_count(self, role: str) -> int:
        return sum(1 for edge in self.edges if edge.role == role)

    def bounds(self) -> tuple[Point, float]:
        xs, ys, zs = zip(*self.verts)
        center = ((min(xs) + max(xs)) * 0.5,
                  (min(ys) + max(ys)) * 0.5,
                  (min(zs) + max(zs)) * 0.5)
        radius = max(math.dist(center, point) for point in self.verts)
        return center, radius


class Builder:
    """Accumulates points and role-tagged edges (no dedupe: each part owns its verts)."""

    def __init__(self) -> None:
        self.verts: list[Point] = []
        self.edges: list[Edge] = []

    def point(self, x: float, y: float, z: float) -> int:
        index = len(self.verts)
        self.verts.append((float(x), float(y), float(z)))
        return index

    def line(self, a: int, b: int, role: Role) -> None:
        if a != b:
            self.edges.append(Edge(a, b, role))

    def segment(self, p: Point, q: Point, role: Role) -> None:
        self.line(self.point(*p), self.point(*q), role)

    def loop(self, points: list[Point], role: Role) -> None:
        indices = [self.point(*p) for p in points]
        for index in range(len(indices)):
            self.line(indices[index], indices[(index + 1) % len(indices)], role)

    def build(self, detail: int) -> StationMesh:
        return StationMesh(tuple(self.verts), tuple(self.edges), int(detail))


# ---------------------------------------------------------------- primitives

def _circle_points(radius: float, z: float, segments: int,
                   phase: float = 0.0) -> list[Point]:
    return [(radius * math.cos(phase + math.tau * i / segments),
             radius * math.sin(phase + math.tau * i / segments), z)
            for i in range(segments)]


def _ring(b: Builder, radius: float, z: float, segments: int,
          role: Role, phase: float = 0.0) -> list[int]:
    indices = [b.point(*p) for p in _circle_points(radius, z, segments, phase)]
    for i in range(segments):
        b.line(indices[i], indices[(i + 1) % segments], role)
    return indices


def _rungs(b: Builder, a: list[int], c: list[int], role: Role,
           stride: int = 1) -> None:
    for i in range(0, min(len(a), len(c)), max(1, stride)):
        b.line(a[i], c[i], role)


def _cylinder(b: Builder, z0: float, z1: float, radius: float, segments: int,
              ring_role: Role, long_role: Role, collars: int = 1,
              phase: float = 0.0, long_stride: int = 1) -> None:
    stations = [z0 + (z1 - z0) * i / max(1, collars) for i in range(collars + 1)]
    rings = [_ring(b, radius, z, segments, ring_role, phase) for z in stations]
    for left, right in zip(rings, rings[1:]):
        _rungs(b, left, right, long_role, long_stride)


def _torus(b: Builder, z: float, major: int, minor: int, phase: float,
           tube: float = RING_TUBE, radius: float = RING_RADIUS,
           window_step: int = 0) -> None:
    """A wireframe torus with one bright equator and dimmer cross-sections."""
    grid: list[list[int]] = []
    for i in range(major):
        u = phase + math.tau * i / major
        cu, su = math.cos(u), math.sin(u)
        row = []
        for j in range(minor):
            v = math.tau * j / minor
            rr = radius + tube * math.cos(v)
            row.append(b.point(rr * cu, rr * su, z + tube * math.sin(v)))
        grid.append(row)

    outer = minor // 2
    for i in range(major):
        nxt = (i + 1) % major
        for j in range(minor):
            if j == 0:
                role = "hull_hi"
            elif j == outer:
                role = "structure"
            else:
                role = "hull"
            b.line(grid[i][j], grid[nxt][j], role)
            b.line(grid[i][j], grid[i][(j + 1) % minor], "detail")

    # Habitat windows: short dashes along the outer equator, between the
    # longitudinal lines, so the band reads as lit windows rather than a
    # continuous rail.
    if window_step > 0:
        half = math.tau / major * 0.28
        for i in range(0, major, window_step):
            u = phase + math.tau * i / major
            rr = radius + tube * 1.004
            b.segment((rr * math.cos(u - half), rr * math.sin(u - half), z),
                      (rr * math.cos(u + half), rr * math.sin(u + half), z),
                      "window")


def _spoke(b: Builder, angle: float, z: float, r0: float, r1: float,
           half_width: float, divisions: int, role: Role = "hull") -> None:
    """A twin-rail truss spoke with alternating diagonal bracing."""
    cu, su = math.cos(angle), math.sin(angle)
    rail_a: list[Point] = []
    rail_b: list[Point] = []
    for k in range(divisions + 1):
        t = k / divisions
        r = r0 + (r1 - r0) * t
        rail_a.append((r * cu, r * su, z - half_width))
        rail_b.append((r * cu, r * su, z + half_width))
    a_idx = [b.point(*p) for p in rail_a]
    b_idx = [b.point(*p) for p in rail_b]
    for k in range(divisions):
        b.line(a_idx[k], a_idx[k + 1], role)
        b.line(b_idx[k], b_idx[k + 1], role)
        if k % 2 == 0:
            b.line(a_idx[k], b_idx[k + 1], "structure")
        else:
            b.line(b_idx[k], a_idx[k + 1], "structure")
    # End caps tie the rails into the hub and the ring.
    b.line(a_idx[0], b_idx[0], "structure")
    b.line(a_idx[-1], b_idx[-1], "structure")
    # A thin service conduit down the middle of the truss.
    conduit_idx = [b.point((r0 + (r1 - r0) * k / divisions) * cu,
                           (r0 + (r1 - r0) * k / divisions) * su, z)
                   for k in range(divisions + 1)]
    for k in range(divisions):
        b.line(conduit_idx[k], conduit_idx[k + 1], "detail")


def _box(b: Builder, center: Point, ex: Point, ey: Point, ez: Point,
         half: Point, role: Role, detail_role: Role = "detail") -> None:
    cx, cy, cz = center
    hx, hy, hz = half
    corners: list[Point] = []
    for sz in (-1, 1):
        for sy in (-1, 1):
            for sx in (-1, 1):
                corners.append((
                    cx + ex[0] * sx * hx + ey[0] * sy * hy + ez[0] * sz * hz,
                    cy + ex[1] * sx * hx + ey[1] * sy * hy + ez[1] * sz * hz,
                    cz + ex[2] * sx * hx + ey[2] * sy * hy + ez[2] * sz * hz,
                ))
    idx = [b.point(*p) for p in corners]
    # corner order: (sx,sy,sz) -> index 4*sz + 2*sy + sx
    for a, c in ((0, 1), (2, 3), (4, 5), (6, 7),
                 (0, 2), (1, 3), (4, 6), (5, 7),
                 (0, 4), (1, 5), (2, 6), (3, 7)):
        b.line(idx[a], idx[c], role)
    # A single panel rib on the outward face gives a small box some read.
    b.line(idx[1], idx[3], detail_role)
    b.line(idx[3], idx[7], detail_role)


def _radial_box(b: Builder, angle: float, radius: float, z: float,
                radial: float, tangential: float, axial: float,
                role: Role = "hull") -> None:
    cu, su = math.cos(angle), math.sin(angle)
    center = (radius * cu, radius * su, z)
    _box(b, center, (cu, su, 0.0), (-su, cu, 0.0), (0.0, 0.0, 1.0),
         (radial, tangential, axial), role)


def _fin(b: Builder, angle: float, r0: float, r1: float,
         z0: float, z1: float, ribs: int = 3) -> None:
    cu, su = math.cos(angle), math.sin(angle)
    corners = [(r * cu, r * su, z) for r, z in
               ((r0, z0), (r1, z0), (r1, z1), (r0, z1))]
    idx = [b.point(*p) for p in corners]
    for i in range(4):
        b.line(idx[i], idx[(i + 1) % 4], "structure")
    for i in range(1, ribs + 1):
        r = r0 + (r1 - r0) * i / (ribs + 1)
        b.line(b.point(r * cu, r * su, z0),
               b.point(r * cu, r * su, z1), "detail")


# ---------------------------------------------------------------- assembly

@dataclass(frozen=True)
class DetailSpec:
    major: int
    minor: int
    spokes: int
    spoke_divisions: int
    hub_segments: int
    windows: int          # 0 = no window band; else every N major segments
    pods: int
    fins: int
    railing: bool         # outer rim handrail / inspection ring
    antenna: int          # 0 simple boom, 1 dish + masts, 2 full array
    collars: int


SPECS = {
    1: DetailSpec(40, 5, 6, 3, 12, 0, 0, 0, False, 0, 3),
    2: DetailSpec(52, 6, 8, 4, 16, 4, 2, 0, False, 1, 5),
    3: DetailSpec(64, 8, 8, 5, 20, 2, 4, 4, True, 2, 7),
    4: DetailSpec(80, 8, 12, 5, 24, 1, 6, 4, True, 2, 9),
}


def build_station(detail: int = 3, seed: int = 0) -> StationMesh:
    """Build one detail level of the station mesh.

    The seed only drives minor cosmetic choices (window phase and which pods
    carry a beacon); the silhouette is always the same station.
    """
    detail = max(1, min(4, int(detail)))
    spec = SPECS[detail]
    seed = int(seed) & 0x7FFFFFFF
    b = Builder()

    ring_z = (RING_SEPARATION * 0.5, -RING_SEPARATION * 0.5)
    # A little phase offset puts the rings' spoke sets at different angles,
    # which is what makes the two wheels legible as two wheels.
    ring_phase = (0.0, math.pi / spec.spokes)

    # ---- habitat rings
    for ring_index, (z, phase) in enumerate(zip(ring_z, ring_phase)):
        _torus(b, z, spec.major, spec.minor, phase,
               window_step=spec.windows)
        for spoke in range(spec.spokes):
            angle = phase + math.tau * spoke / spec.spokes
            _spoke(b, angle, z, SPOKE_INNER, SPOKE_OUTER,
                   0.021 + 0.002 * ring_index, spec.spoke_divisions)
        # Rim service pods, deliberately not evenly spaced: even spacing reads
        # as a pattern, uneven spacing reads as machinery.
        if spec.pods:
            for pod in range(spec.pods):
                angle = phase + math.tau * pod / spec.pods + 0.19 * (pod % 3)
                _radial_box(b, angle, RING_RADIUS + RING_TUBE + 0.055, z,
                            0.070, 0.048, 0.052, "hull")
                if detail >= 3 and pod % 2 == 0:
                    # A lit hatch on the outward face of the pod.
                    cu, su = math.cos(angle), math.sin(angle)
                    r = RING_RADIUS + RING_TUBE + 0.128
                    b.segment((r * cu - su * 0.018, r * su + cu * 0.018,
                               z - 0.018),
                              (r * cu + su * 0.018, r * su - cu * 0.018,
                               z + 0.018), "window")
        # Beacons on the rim.
        if detail >= 2:
            for beacon in (0, 2):
                angle = phase + math.tau * beacon / 4 + 0.11
                cu, su = math.cos(angle), math.sin(angle)
                rr = RING_RADIUS + RING_TUBE * 1.22
                b.segment((rr * cu, rr * su, z - 0.018),
                          (rr * cu, rr * su, z + 0.018), "beacon")
                b.segment(((rr - 0.012) * cu, (rr - 0.012) * su, z),
                          ((rr + 0.012) * cu, (rr + 0.012) * su, z), "beacon")

        # An inspection rail just outside the rim, tied back every few bays.
        if spec.railing:
            rail_r = RING_RADIUS + RING_TUBE + 0.022
            rail = _ring(b, rail_r, z, spec.major, "detail", phase)
            for i in range(0, spec.major, 4):
                angle = phase + math.tau * i / spec.major
                cu, su = math.cos(angle), math.sin(angle)
                b.segment((rail_r * cu, rail_r * su, z),
                          ((RING_RADIUS + RING_TUBE * 0.9) * cu,
                           (RING_RADIUS + RING_TUBE * 0.9) * su, z),
                          "detail")

    # ---- central hub
    hub_len = 0.50
    _cylinder(b, -hub_len, hub_len, HUB_RADIUS, spec.hub_segments,
              "structure", "structure", collars=min(5, spec.collars),
              long_stride=2)
    # The wider central drum and its end flanges.
    _cylinder(b, -0.17, 0.17, HUB_RADIUS * 1.38, spec.hub_segments,
              "hull_hi", "structure", collars=2)
    for z, radius in ((-0.505, HUB_RADIUS * 1.46), (0.505, HUB_RADIUS * 1.46)):
        flange = _ring(b, radius, z, spec.hub_segments, "hull_hi")
        inner = _ring(b, HUB_RADIUS, z, spec.hub_segments, "detail")
        for i in range(spec.hub_segments):
            b.line(inner[i], flange[i], "structure")
    # Eight structural ribs down the drum.
    for rib in range(8):
        angle = math.tau * rib / 8 + math.pi / 16
        cu, su = math.cos(angle), math.sin(angle)
        b.segment((HUB_RADIUS * 1.38 * cu, HUB_RADIUS * 1.38 * su, -0.17),
                  (HUB_RADIUS * 1.38 * cu, HUB_RADIUS * 1.38 * su, 0.17),
                  "hull_hi")
    # Hub windows: a short, irregular band of lit cells around the drum.
    if detail >= 2:
        for i in range(0, spec.hub_segments, 2):
            angle = math.tau * i / spec.hub_segments + 0.025
            cu, su = math.cos(angle), math.sin(angle)
            rr = HUB_RADIUS * 1.385
            z0 = -0.012
            z1 = 0.030 + 0.010 * ((i + seed) % 3)
            b.segment((rr * cu, rr * su, z0), (rr * cu, rr * su, z1), "window")

    # ---- axial spine and docking module
    _cylinder(b, -0.74, 0.72, 0.036, 8, "detail", "detail",
              collars=max(3, spec.collars))
    for collar in range(-3, 4):
        z = collar * 0.20
        if abs(z) > 0.68:
            continue
        ring = _ring(b, 0.076, z, 8, "structure")
        for i in range(8):
            angle = math.tau * i / 8
            b.line(ring[i], b.point(0.036 * math.cos(angle),
                                    0.036 * math.sin(angle), z), "detail")

    # Front docking module: a flared collar, a short barrel, a docking ring.
    _cylinder(b, 0.50, 0.72, 0.195, spec.hub_segments, "hull_hi", "hull",
              collars=2)
    _cylinder(b, 0.72, 0.86, 0.125, 8, "hull_hi", "structure", collars=1)
    port = _ring(b, 0.122, 0.885, 8, "dock")
    center = b.point(0.0, 0.0, 0.885)
    for i in range(8):
        b.line(port[i], center, "dock")
    b.segment((-0.175, 0.0, 0.885), (0.175, 0.0, 0.885), "dock")
    b.segment((0.0, -0.175, 0.885), (0.0, 0.175, 0.885), "dock")
    # Four docking arms with pads, angled out from the collar.
    for arm in range(4):
        angle = math.tau * arm / 4 + math.pi / 4
        cu, su = math.cos(angle), math.sin(angle)
        start = (0.18 * cu, 0.18 * su, 0.62)
        elbow = (0.32 * cu, 0.32 * su, 0.74)
        end = (0.32 * cu, 0.32 * su, 0.83)
        b.segment(start, elbow, "dock")
        b.segment(elbow, end, "dock")
        _radial_box(b, angle, 0.32, 0.83, 0.035, 0.032, 0.025, "dock")
    # Approach beacons on the port rim.
    for i in range(0, 8, 2):
        angle = math.tau * i / 8
        b.segment((0.122 * math.cos(angle), 0.122 * math.sin(angle), 0.886),
                  (0.162 * math.cos(angle), 0.162 * math.sin(angle), 0.886),
                  "beacon")

    # ---- rear antenna boom and dish
    if spec.antenna:
        _cylinder(b, -0.50, -0.72, 0.060, 8, "structure", "detail", collars=2)
        dish_z = -0.78
        dish = _ring(b, 0.165, dish_z, 16, "hull_hi")
        hub = b.point(0.0, 0.0, dish_z - 0.045)
        for i in range(0, 16, 2):
            b.line(dish[i], hub, "detail")
        b.segment((-0.165, 0.0, dish_z), (0.165, 0.0, dish_z), "structure")
        b.segment((0.0, -0.165, dish_z), (0.0, 0.165, dish_z), "structure")
        b.segment((0.0, 0.0, dish_z - 0.045), (0.0, 0.0, dish_z + 0.10),
                  "structure")
        # Feed horn at the focus of the dish.
        b.segment((-0.018, 0.0, dish_z + 0.10), (0.018, 0.0, dish_z + 0.10),
                  "window")
        b.segment((0.0, -0.018, dish_z + 0.10), (0.0, 0.018, dish_z + 0.10),
                  "window")
        if spec.antenna >= 2:
            # Three outrigger masts around the boom.
            for mast in range(3):
                angle = math.tau * mast / 3 + 0.4
                cu, su = math.cos(angle), math.sin(angle)
                base = (0.10 * cu, 0.10 * su, -0.58)
                tip = (0.26 * cu, 0.26 * su, -0.84)
                b.segment(base, tip, "detail")
                b.segment((tip[0] - 0.014 * su, tip[1] + 0.014 * cu, tip[2]),
                          (tip[0] + 0.014 * su, tip[1] - 0.014 * cu, tip[2]),
                          "beacon")
                b.segment((tip[0], tip[1], tip[2] - 0.014),
                          (tip[0], tip[1], tip[2] + 0.014), "beacon")

    # ---- radiator fins between the spokes
    if spec.fins:
        for fin in range(spec.fins):
            angle = math.tau * fin / spec.fins + math.pi / spec.fins + 0.07
            _fin(b, angle, 0.255, 0.50, -0.145, 0.145, ribs=3)

    # ---- a few external equipment boxes on the hub end rings
    if detail >= 3:
        for item in range(6):
            angle = math.tau * item / 6 + 0.21
            _radial_box(b, angle, HUB_RADIUS * 1.72, -0.505,
                        0.045, 0.040, 0.045, "structure")

    return b.build(detail)


#: Four levels for the current seed, and maybe one previous seed.  This is an
#: LRU, not an unbounded dict: a random seed on every entry used to leave four
#: meshes behind per visit to the mode.
_LEVEL_CACHE: "OrderedDict[tuple[int, int], StationMesh]" = OrderedDict()
_CACHE_LIMIT = 8


def station_mesh(detail: int, seed: int = 0) -> StationMesh:
    """Cached immutable mesh: the mode builds four of these at most."""
    key = (max(1, min(4, int(detail))), int(seed) & 0x7FFFFFFF)
    mesh = _LEVEL_CACHE.pop(key, None)
    if mesh is None:
        mesh = build_station(key[0], key[1])
    _LEVEL_CACHE[key] = mesh
    while len(_LEVEL_CACHE) > _CACHE_LIMIT:
        _LEVEL_CACHE.popitem(last=False)
    return mesh
