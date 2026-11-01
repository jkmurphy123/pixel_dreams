"""Phase 2 static wireframe assets.

Every builder returns a near mesh; the world derives mid and far LODs from the
role tags.  Silhouette edges (primary) survive all three levels, panel and
greeble edges fall away.  Local origins are at ground contact, +Y up.
"""
from __future__ import annotations

import math

from .meshes import (Mesh, MeshBuilder, PANEL, TRENCH_RIM_WIDTH,
                     cylinder, dome, ring_points)


def _dish(b: MeshBuilder, cx: float, cy: float, cz: float, radius: float,
          axis: str = "z", feed: float = 3.0) -> None:
    """A simple parabolic dish approximated by rings and radial ribs."""
    outer = ring_points(cx, cy, cz, radius, 12, axis)
    middle = ring_points(cx, cy, cz + (0.5 if axis == "z" else 0.0),
                         radius * 0.62, 12, axis)
    inner = ring_points(cx, cy, cz + (0.8 if axis == "z" else 0.0),
                        radius * 0.28, 12, axis)
    b.polyline(outer, "primary", closed=True)
    b.polyline(middle, "secondary", closed=True)
    b.polyline(inner, "secondary", closed=True)
    for i in range(12):
        if i % 2 == 0:
            b.edge(outer[i], inner[i], "secondary")
    if axis == "z":
        feed_pt = (cx, cy, cz + feed)
    elif axis == "x":
        feed_pt = (cx + feed, cy, cz)
    else:
        feed_pt = (cx, cy + feed, cz)
    for i in (0, 3, 6, 9):
        b.edge(outer[i], feed_pt, "detail")
    b.edge(inner[0], feed_pt, "primary")


def build_defense_tower() -> Mesh:
    b = MeshBuilder()
    b.box(-4.2, 4.2, 0.0, 6.0, -4.2, 4.2, "secondary", faces=True)
    b.box(-3.4, 3.4, 6.0, 16.0, -3.4, 3.4, "secondary", faces=True)
    b.box(-2.8, 2.8, 16.0, 24.0, -2.8, 2.8, "secondary", faces=True)
    b.box(-3.1, 3.1, 24.0, 27.0, -3.1, 3.1, "primary", faces=True)
    # Chamfered silhouette corners survive the far LOD.
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            b.edge((4.2 * sx, 0.0, 4.2 * sz),
                   (2.8 * sx, 24.0, 2.8 * sz), "primary")
            b.edge((2.8 * sx, 24.0, 2.8 * sz),
                   (3.1 * sx, 27.0, 3.1 * sz), "primary")
    for y in (6.0, 16.0, 24.0, 27.0):
        half = 4.2 if y == 6.0 else (3.1 if y >= 24.0 else 3.4)
        b.polyline([(-half, y, -half), (half, y, -half),
                    (half, y, half), (-half, y, half)], "primary", closed=True)
    # Observation windows and a roof dish.
    for i in range(4):
        z = -1.8 + i * 1.2
        b.edge((-2.9, 25.4, z), (-4.0, 25.4, z), "detail")
        b.edge((2.9, 25.4, z), (4.0, 25.4, z), "detail")
    b.edge((0.0, 27.0, 0.0), (0.0, 34.0, 0.0), "primary")
    b.edge((0.0, 34.0, 0.0), (0.0, 35.0, 0.0), "emissive")
    b.polyline(ring_points(0.0, 31.0, 0.0, 1.5, 8, "y"), "secondary",
               closed=True)
    _dish(b, 3.4, 30.0, 0.0, 2.4, axis="x", feed=1.8)
    b.polyline(ring_points(0.0, 0.16, 0.0, 4.35, 16, "y"), "hazard",
               closed=True)
    return b.build()


def build_comm_tower() -> Mesh:
    b = MeshBuilder()
    base = 4.0
    top = 1.6
    height = 30.0
    # Tapered lattice legs and cross-braces.
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            b.edge((base * sx, 0.0, base * sz),
                   (top * sx, height, top * sz), "primary")
    for y in (0.0, 6.0, 12.0, 18.0, 24.0, 30.0):
        t = y / height
        half = base * (1 - t) + top * t
        b.polyline([(-half, y, -half), (half, y, -half),
                    (half, y, half), (-half, y, half)], "primary",
                   closed=True)
        if y in (6.0, 18.0):
            b.edge((-half, y, -half), (half, y, half), "detail")
            b.edge((half, y, -half), (-half, y, half), "detail")
    # Upper platform, dishes, and a beacon crown.
    b.box(-2.4, 2.4, 30.0, 32.0, -2.4, 2.4, "primary", faces=True)
    _dish(b, 4.2, 27.0, 0.0, 3.6, axis="x", feed=2.0)
    _dish(b, -4.0, 22.0, 0.0, 2.8, axis="x", feed=1.6)
    b.edge((0.0, 32.0, 0.0), (0.0, 36.0, 0.0), "primary")
    b.edge((0.0, 36.0, 0.0), (0.0, 37.0, 0.0), "emissive")
    b.polyline(ring_points(0.0, 35.0, 0.0, 0.8, 6, "y"), "secondary",
               closed=True)
    return b.build()


def build_command_dome(radius: float = 13.0) -> Mesh:
    b = MeshBuilder()
    dome(b, 0.0, 0.0, 0.0, radius, meridians=16, rings=3,
         primary_every=4, hatch=True)
    # Base skirt and eight buttresses.
    b.polyline(ring_points(0.0, -0.7, 0.0, radius * 1.06, 16, "y"),
               "primary", closed=True)
    for i in range(8):
        a = math.pi * 2 * i / 8
        x, z = radius * 1.04 * math.cos(a), radius * 1.04 * math.sin(a)
        b.edge((x, -0.7, z), (x, 0.6, z), "primary")
        b.edge((x, 0.6, z), (x * 0.90, 2.4, z * 0.90), "secondary")
    # Porthole ring and crown antenna.
    for i in range(12):
        a = math.pi * 2 * i / 12
        x, z = radius * 0.82 * math.cos(a), radius * 0.82 * math.sin(a)
        y = radius * 0.36
        b.polyline([(x - 0.5, y, z), (x + 0.5, y, z),
                    (x + 0.5, y + 0.8, z), (x - 0.5, y + 0.8, z)],
                   "detail", closed=True)
    b.edge((0.0, radius, 0.0), (0.0, radius + 7.0, 0.0), "primary")
    b.edge((0.0, radius + 7.0, 0.0), (0.0, radius + 8.0, 0.0), "emissive")
    b.polyline(ring_points(0.0, radius + 5.5, 0.0, 1.4, 8, "y"),
               "secondary", closed=True)
    return b.build()


def build_block_building(variant: int = 0) -> Mesh:
    b = MeshBuilder()
    tiers = 2 + (variant % 2)
    w = 7.0
    z = 6.0
    y = 0.0
    for i in range(tiers):
        h = 5.0 + (i % 2) * 1.5
        b.box(-w, w, y, y + h, -z, z, "secondary", faces=True)
        # Outer silhouette corners.
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                b.edge((w * sx, y, z * sz), (w * sx, y + h, z * sz),
                       "primary")
        b.polyline([(-w, y + h, -z), (w, y + h, -z),
                    (w, y + h, z), (-w, y + h, z)], "primary", closed=True)
        y += h
        w *= 0.82
        z *= 0.82
    # Roof greebles, vents, and a cable run.
    b.box(-2.2, -0.4, y, y + 1.6, -2.0, 0.8, "secondary", faces=True)
    b.box(1.0, 3.2, y, y + 1.0, -1.2, 1.6, "detail", faces=False)
    b.edge((-w, y, z), (w, y, z), "detail")
    b.edge((0.0, y, 0.0), (0.0, y + 4.0, 0.0), "primary")
    b.edge((0.0, y + 4.0, 0.0), (0.0, y + 4.8, 0.0), "emissive")
    b.polyline([(w, 0.4, 0.0), (w + 2.0, 0.4, 2.0),
                (w + 2.0, 0.0, 4.0)], "detail")
    for i in range(3):
        b.edge((-w * 0.6, 1.2 + i * 1.1, z), (-w * 0.2, 1.2 + i * 1.1, z),
               "detail")
    return b.build()


def build_bunker() -> Mesh:
    b = MeshBuilder()
    b.box(-8.0, 8.0, 0.0, 4.2, -9.0, 9.0, "secondary", faces=True)
    # Sloped roof ridge.
    b.edge((-8.0, 4.2, -9.0), (0.0, 5.4, 0.0), "primary")
    b.edge((8.0, 4.2, -9.0), (0.0, 5.4, 0.0), "primary")
    b.edge((-8.0, 4.2, 9.0), (0.0, 5.4, 0.0), "primary")
    b.edge((8.0, 4.2, 9.0), (0.0, 5.4, 0.0), "primary")
    # Blast door with warning chevrons and a ramp.
    b.polyline([(-3.2, 0.0, 9.05), (3.2, 0.0, 9.05),
                (3.2, 3.0, 9.05), (-3.2, 3.0, 9.05)], "primary",
               closed=True)
    for i in range(3):
        b.edge((-3.2, 2.4 - i * 0.8, 9.06), (3.2, 1.6 - i * 0.8, 9.06),
               "hazard")
    b.edge((-4.0, 0.0, 9.0), (-6.0, 0.0, 13.0), "secondary")
    b.edge((4.0, 0.0, 9.0), (6.0, 0.0, 13.0), "secondary")
    # Roof turret and antenna.
    b.box(-1.2, 1.2, 5.4, 6.6, -0.8, 0.8, "primary", faces=False)
    b.edge((0.0, 6.6, 0.0), (0.0, 8.6, 0.0), "primary")
    b.edge((0.0, 8.6, 0.0), (0.0, 9.2, 0.0), "emissive")
    b.polyline(ring_points(0.0, 0.18, 9.0, 8.2, 12, "y"), "hazard",
               closed=True)
    return b.build()


def build_power_node() -> Mesh:
    b = MeshBuilder()
    cylinder(b, "y", 0.0, 0.0, 0.0, 5.0, 4.4, 8,
             rail_role="primary", cap_role="secondary")
    b.face(ring_points(0.0, 5.0, 0.0, 4.4, 8, "y"), PANEL)
    for y, r in ((1.4, 5.0), (2.8, 5.2), (4.2, 5.0)):
        b.polyline(ring_points(0.0, y, 0.0, r, 12, "y"), "secondary",
                   closed=True)
    b.edge((0.0, 0.4, 0.0), (0.0, 4.8, 0.0), "emissive")
    for i in range(4):
        a = math.pi * 2 * i / 4 + 0.3
        x, z = 5.0 * math.cos(a), 5.0 * math.sin(a)
        b.edge((x, 0.6, z), (x * 1.5, 0.2, z * 1.5), "primary")
        b.edge((x * 1.5, 0.2, z * 1.5), (x * 2.0, 0.2, z * 2.0), "detail")
    return b.build()


def build_dish_array() -> Mesh:
    b = MeshBuilder()
    cylinder(b, "y", 0.0, 0.0, 0.0, 3.0, 3.2, 8,
             rail_role="primary", cap_role="secondary")
    b.box(-1.0, 1.0, 3.0, 6.0, -1.0, 1.0, "primary", faces=False)
    _dish(b, 0.0, 8.0, 0.0, 6.0, axis="z", feed=3.0)
    for sx in (-1.0, 1.0):
        b.edge((2.6 * sx, 3.0, 0.0), (5.0 * sx, 6.3, 0.0), "primary")
    b.edge((0.0, 6.0, 0.0), (0.0, 8.0, 3.0), "detail")
    b.polyline(ring_points(0.0, 0.12, 0.0, 3.4, 12, "y"), "hazard",
               closed=True)
    return b.build()


def build_conduit(length: float = 24.0) -> Mesh:
    b = MeshBuilder()
    z0, z1 = -length * 0.5, length * 0.5
    for x in (-1.6, -0.5, 0.6):
        b.edge((x, 1.35, z0), (x, 1.35, z1), "primary")
        b.edge((x, 1.15, z0), (x, 1.15, z1), "secondary")
        for z in (z0 + 2, z0 + length * 0.5, z1 - 2):
            b.edge((x, 1.15, z), (x, 1.35, z), "secondary")
    for z in (z0 + 3, z0 + length * 0.5, z1 - 3):
        b.edge((-2.2, 0.0, z), (-2.2, 1.3, z), "primary")
        b.edge((2.2, 0.0, z), (2.2, 1.3, z), "primary")
        b.edge((-2.2, 1.25, z), (2.2, 1.25, z), "secondary")
    b.polyline(ring_points(0.6, 1.25, z0 + 5, 0.5, 6, "z"), "hazard",
               closed=True)
    return b.build()


def build_beacon() -> Mesh:
    b = MeshBuilder()
    b.edge((0.0, 0.0, 0.0), (0.0, 4.6, 0.0), "primary")
    for y, r in ((1.2, 0.8), (2.8, 0.6), (4.2, 0.9)):
        b.polyline(ring_points(0.0, y, 0.0, r, 6, "y"), "secondary",
                   closed=True)
    b.edge((0.0, 4.6, 0.0), (0.0, 5.4, 0.0), "emissive")
    b.edge((-0.5, 5.0, 0.0), (0.5, 5.0, 0.0), "emissive")
    return b.build()


def build_crater(radius: float = 10.0) -> Mesh:
    b = MeshBuilder()
    for ring_i, rr in enumerate((radius * 0.35, radius * 0.68, radius)):
        pts = []
        for i in range(14):
            a = math.pi * 2 * i / 14
            jitter = 1.0 + 0.08 * math.sin(i * 2.7 + ring_i)
            pts.append((math.cos(a) * rr * jitter, 0.04 + ring_i * 0.02,
                        math.sin(a) * rr * jitter))
        b.polyline(pts, "primary" if ring_i == 2 else "secondary",
                   closed=True)
    for i in range(8):
        a = math.pi * 2 * i / 8 + 0.2
        b.edge((math.cos(a) * radius * 0.35, 0.05,
                math.sin(a) * radius * 0.35),
               (math.cos(a) * radius * 1.08, 0.03,
                math.sin(a) * radius * 1.08), "detail")
    for i in range(4):
        a = math.pi * 2 * i / 4 + 0.7
        x, z = math.cos(a) * radius * 0.8, math.sin(a) * radius * 0.8
        b.box(x - 1.2, x + 1.2, 0.0, 0.8, z - 1.2, z + 1.2,
              "secondary", faces=False)
    return b.build()


def build_wall_gun() -> Mesh:
    b = MeshBuilder()
    b.box(-0.8, 1.0, 0.0, 1.2, -1.4, 1.4, "secondary", faces=True)
    b.box(-0.7, 0.7, 1.2, 2.3, -1.0, 1.0, "primary", faces=False)
    for z in (-0.42, 0.42):
        b.edge((-0.6, 1.8, z), (-4.8, 1.8, z), "primary")
        b.edge((-0.6, 1.6, z), (-4.8, 1.6, z), "secondary")
        b.polyline(ring_points(-4.8, 1.7, z, 0.16, 6, "x"), "primary",
                   closed=True)
    b.edge((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), "detail")
    b.polyline(ring_points(0.0, 0.12, 0.0, 1.3, 8, "y"), "hazard",
               closed=True)
    return b.build()


def build_bridge(width: float, depth: float) -> Mesh:
    """A truss bridge spanning the trench; local origin at the trench centre."""
    b = MeshBuilder()
    span = width * 0.5 + TRENCH_RIM_WIDTH + 2.0
    deck_y = depth + 22.0
    top_y = depth + 26.0
    z0, z1 = -3.6, 3.6
    for z in (z0, z1):
        b.edge((-span, deck_y, z), (span, deck_y, z), "primary")
        b.edge((-span, top_y, z), (span, top_y, z), "primary")
        b.edge((-span, deck_y, z), (-span, top_y, z), "primary")
        b.edge((span, deck_y, z), (span, top_y, z), "primary")
        for i in range(1, 8):
            x = -span + i * (2 * span / 8)
            b.edge((x, deck_y, z), (x, top_y, z), "secondary")
            b.edge((x, deck_y, z), (x + span / 8, top_y, z), "detail")
    for x in (-span, -span * 0.5, 0.0, span * 0.5, span):
        b.edge((x, deck_y, z0), (x, deck_y, z1), "secondary")
        b.edge((x, top_y, z0), (x, top_y, z1), "primary")
    # Supports land on the rim, not in the ship lane.
    for x in (-(width * 0.5 + 1.5), width * 0.5 + 1.5):
        for z in (-2.0, 2.0):
            b.edge((x, depth, z), (x, deck_y, z), "primary")
            b.edge((x - 1.0, depth, z), (x + 1.0, deck_y, z), "detail")
    # Hazard strips and deck lights.
    for x in (-span, span):
        b.edge((x, deck_y - 0.4, z0), (x, deck_y - 0.4, z1), "hazard")
    for x in (-span * 0.5, 0.0, span * 0.5):
        b.edge((x, deck_y + 0.2, z0), (x, deck_y + 0.2, z0 + 0.8),
               "emissive")
    return b.build()


def build_far(kind: str, width: float = 28.0, depth: float = 10.0) -> Mesh:
    """Cheap silhouette for the far LOD.

    Structural LODs of towers still carry many box rings; at 400+ units those
    lines only add noise.  These silhouettes keep a readable outline at roughly
    10-20 edges.
    """
    b = MeshBuilder()
    if kind == "turret":
        b.polyline(ring_points(0.0, 0.0, 0.0, 2.4, 8, "y"), "primary",
                   closed=True)
        b.polyline(ring_points(0.0, 1.2, 0.0, 2.4, 8, "y"), "primary",
                   closed=True)
        b.box(-1.2, 1.2, 2.2, 3.2, -1.2, 1.2, "primary", faces=False)
        b.edge((-1.0, 2.7, -0.5), (-6.2, 2.7, -0.5), "primary")
        b.edge((-1.0, 2.7, 0.5), (-6.2, 2.7, 0.5), "primary")
        b.edge((0.0, 3.2, 0.0), (0.0, 5.5, 0.0), "primary")
        b.edge((0.0, 5.5, 0.0), (0.0, 5.9, 0.0), "emissive")
    elif kind == "dome_small":
        b.polyline(ring_points(0.0, 0.0, 0.0, 6.0, 8, "y"), "primary",
                   closed=True)
        for i in range(0, 8, 2):
            a = math.pi * 2 * i / 8
            x, z = math.cos(a) * 6.0, math.sin(a) * 6.0
            b.edge((x, 0.0, z), (x * 0.7, 4.2, z * 0.7), "primary")
            b.edge((x * 0.7, 4.2, z * 0.7), (0.0, 6.0, 0.0), "primary")
        b.edge((0.0, 6.0, 0.0), (0.0, 6.9, 0.0), "emissive")
    elif kind == "defense_tower":
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                b.edge((4.2 * sx, 0.0, 4.2 * sz),
                       (2.8 * sx, 24.0, 2.8 * sz), "primary")
        b.polyline([(-3.1, 27.0, -3.1), (3.1, 27.0, -3.1),
                    (3.1, 27.0, 3.1), (-3.1, 27.0, 3.1)], "primary",
                   closed=True)
        b.edge((0.0, 27.0, 0.0), (0.0, 35.0, 0.0), "primary")
        b.edge((0.0, 35.0, 0.0), (0.0, 35.8, 0.0), "emissive")
    elif kind == "comm_tower":
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                b.edge((4.0 * sx, 0.0, 4.0 * sz),
                       (1.6 * sx, 30.0, 1.6 * sz), "primary")
        b.polyline([(-2.4, 30.0, -2.4), (2.4, 30.0, -2.4),
                    (2.4, 30.0, 2.4), (-2.4, 30.0, 2.4)], "primary",
                   closed=True)
        b.edge((0.0, 32.0, 0.0), (0.0, 37.0, 0.0), "primary")
        b.edge((0.0, 37.0, 0.0), (0.0, 37.8, 0.0), "emissive")
        b.edge((2.4, 28.0, 0.0), (5.5, 28.0, 0.0), "secondary")
        b.edge((-2.4, 23.0, 0.0), (-5.0, 23.0, 0.0), "secondary")
    elif kind == "command_dome":
        r = 13.0
        b.polyline(ring_points(0.0, 0.0, 0.0, r, 8, "y"), "primary",
                   closed=True)
        for i in range(0, 8, 2):
            a = math.pi * 2 * i / 8
            x, z = math.cos(a) * r, math.sin(a) * r
            b.edge((x, 0.0, z), (x * 0.7, r * 0.7, z * 0.7), "primary")
            b.edge((x * 0.7, r * 0.7, z * 0.7), (0.0, r, 0.0), "primary")
        b.edge((0.0, r, 0.0), (0.0, r + 8.0, 0.0), "primary")
    elif kind == "dish_array":
        b.polyline(ring_points(0.0, 8.0, 0.0, 6.0, 8, "z"), "primary",
                   closed=True)
        for i in range(0, 8, 2):
            a = math.pi * 2 * i / 8
            x, y = math.cos(a) * 6.0, 8.0 + math.sin(a) * 6.0
            b.edge((x, y, 0.0), (0.0, 8.0, 3.0), "secondary")
        for sx in (-1.0, 1.0):
            b.edge((1.5 * sx, 0.0, 0.0), (1.5 * sx, 3.0, 0.0), "primary")
        b.edge((-1.5, 3.0, 0.0), (1.5, 3.0, 0.0), "primary")
        b.edge((0.0, 3.0, 0.0), (0.0, 8.0, 0.0), "primary")
    elif kind == "block_building":
        b.box(-7.0, 7.0, 0.0, 12.0, -6.0, 6.0, "primary", faces=False)
        b.box(-5.0, 5.0, 12.0, 16.0, -4.0, 4.0, "primary", faces=False)
        b.edge((0.0, 16.0, 0.0), (0.0, 20.0, 0.0), "primary")
        b.edge((0.0, 20.0, 0.0), (0.0, 20.7, 0.0), "emissive")
    elif kind == "bunker":
        b.box(-8.0, 8.0, 0.0, 4.2, -9.0, 9.0, "primary", faces=False)
        b.edge((-8.0, 4.2, -9.0), (0.0, 5.4, 0.0), "primary")
        b.edge((8.0, 4.2, -9.0), (0.0, 5.4, 0.0), "primary")
        b.edge((-8.0, 4.2, 9.0), (0.0, 5.4, 0.0), "primary")
        b.edge((8.0, 4.2, 9.0), (0.0, 5.4, 0.0), "primary")
        b.edge((0.0, 5.4, 0.0), (0.0, 8.6, 0.0), "primary")
    elif kind == "power_node":
        b.polyline(ring_points(0.0, 0.0, 0.0, 4.4, 8, "y"), "primary",
                   closed=True)
        b.polyline(ring_points(0.0, 5.0, 0.0, 4.4, 8, "y"), "primary",
                   closed=True)
        for i in range(0, 8, 2):
            a = math.pi * 2 * i / 8
            x, z = math.cos(a) * 4.4, math.sin(a) * 4.4
            b.edge((x, 0.0, z), (x, 5.0, z), "primary")
    elif kind == "conduit":
        for x in (-1.6, 0.6):
            b.edge((x, 1.35, -12.0), (x, 1.35, 12.0), "primary")
        for z in (-9.0, 0.0, 9.0):
            b.edge((-2.2, 0.0, z), (-2.2, 1.3, z), "primary")
            b.edge((2.2, 0.0, z), (2.2, 1.3, z), "primary")
    elif kind == "beacon":
        b.edge((0.0, 0.0, 0.0), (0.0, 4.6, 0.0), "primary")
        b.edge((0.0, 4.6, 0.0), (0.0, 5.4, 0.0), "emissive")
    elif kind == "crater":
        b.polyline(ring_points(0.0, 0.04, 0.0, 10.0, 8, "y"), "primary",
                   closed=True)
        for i in range(0, 8, 2):
            a = math.pi * 2 * i / 8
            b.edge((math.cos(a) * 3.5, 0.05, math.sin(a) * 3.5),
                   (math.cos(a) * 10.8, 0.03, math.sin(a) * 10.8),
                   "secondary")
    elif kind == "wall_gun":
        b.box(-0.8, 1.0, 0.0, 1.2, -1.4, 1.4, "primary", faces=False)
        b.box(-0.7, 0.7, 1.2, 2.3, -1.0, 1.0, "primary", faces=False)
        b.edge((-0.6, 1.7, 0.0), (-4.8, 1.7, 0.0), "primary")
    elif kind == "bridge":
        span = width * 0.5 + TRENCH_RIM_WIDTH + 2.0
        deck_y = depth + 22.0
        top_y = depth + 26.0
        for z in (-3.6, 3.6):
            b.edge((-span, deck_y, z), (span, deck_y, z), "primary")
            b.edge((-span, top_y, z), (span, top_y, z), "primary")
            for x in (-span, 0.0, span):
                b.edge((x, deck_y, z), (x, top_y, z), "primary")
        for x in (-span, 0.0, span):
            b.edge((x, deck_y, -3.6), (x, deck_y, 3.6), "secondary")
        for x in (-(width * 0.5 + 1.5), width * 0.5 + 1.5):
            b.edge((x, depth, -2.0), (x, deck_y, -2.0), "primary")
            b.edge((x, depth, 2.0), (x, deck_y, 2.0), "primary")
    else:
        b.edge((-2.0, 0.0, 0.0), (2.0, 0.0, 0.0), "primary")
        b.edge((0.0, 0.0, 0.0), (0.0, 4.0, 0.0), "primary")
    return b.build()


def build_tie() -> Mesh:
    """TIE fighter: ball cockpit, two hex wing panels, pylons, engine glow."""
    b = MeshBuilder()
    # Cockpit ball.
    b.polyline(ring_points(0.0, 0.0, 0.0, 1.8, 12, "x"), "primary",
               closed=True)
    b.polyline(ring_points(0.0, 0.0, 0.0, 1.8, 12, "y"), "secondary",
               closed=True)
    b.edge((0.0, 1.8, 0.0), (0.0, -1.8, 0.0), "secondary")
    b.edge((0.0, 0.0, 1.8), (0.0, 0.0, -1.8), "secondary")
    # Hex wing panels.
    for sx in (-1.0, 1.0):
        cx = 5.2 * sx
        hex_pts = [(cx, 4.4, 0.0), (cx, 2.2, 0.0), (cx, -2.2, 0.0),
                   (cx, -4.4, 0.0), (cx, -2.2, 0.0), (cx, 2.2, 0.0)]
        # A true hexagon in the YZ plane.
        hex_pts = []
        for i in range(6):
            a = math.pi * 2 * i / 6 + math.pi / 6
            hex_pts.append((cx, 4.6 * math.sin(a), 4.6 * math.cos(a)))
        b.polyline(hex_pts, "primary", closed=True)
        for i in range(6):
            b.edge((cx, 0.0, 0.0), hex_pts[i], "secondary")
        b.edge((cx * 0.55, 0.0, 0.0), (cx, 0.0, 0.0), "primary")
    b.edge((0.0, 0.0, -1.8), (0.0, 0.0, -3.2), "emissive")
    return b.build()
