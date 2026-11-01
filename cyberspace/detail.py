"""Volume-lattice detail for axis-aligned boxes.

The chosen technique from the geometric-detail study: split a box into an
N x N x N grid and draw the grid lines that cross the volume (the outer box
edges are already in the base mesh).  Surface lines are brighter than interior
lines, which is what makes the box read as a solid volume rather than a cage.

This module is pure geometry (no pygame) so both the procedural city and the
landmark loader can use it.
"""
from __future__ import annotations

from .palette import scale

Edge = tuple[float, float, float, float, float, float, int, int, int]


def _seg(x1, y1, z1, x2, y2, z2, color):
    return (float(x1), float(y1), float(z1),
            float(x2), float(y2), float(z2),
            int(color[0]), int(color[1]), int(color[2]))


def volume_lattice(x0: float, y0: float, x1: float, y1: float,
                   z0: float, z1: float, level: int, color) -> list[Edge]:
    """Grid lines inside/on a box. Level 1/0 returns nothing (base mesh only).

    The other two coordinates index the grid; a line with both of them on the
    box surface is skipped because the base mesh already draws that boundary
    edge.  Lines with one surface coordinate read as surface detail and are
    kept brighter; fully interior lines are dimmed.
    """
    n = int(level)
    if n < 2 or x1 <= x0 or y1 <= y0 or z1 <= z0:
        return []
    face = tuple(color)
    inner = scale(color, 0.55)
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    ys = [y0 + (y1 - y0) * i / n for i in range(n + 1)]
    zs = [z0 + (z1 - z0) * i / n for i in range(n + 1)]
    out: list[Edge] = []
    # X-directed lines: vary y and z.
    for j in range(n + 1):
        y_surface = j in (0, n)
        for k in range(n + 1):
            z_surface = k in (0, n)
            if y_surface and z_surface:
                continue
            out.append(_seg(x0, ys[j], zs[k], x1, ys[j], zs[k],
                            face if (y_surface or z_surface) else inner))
    # Y-directed lines: vary x and z.
    for i in range(n + 1):
        x_surface = i in (0, n)
        for k in range(n + 1):
            z_surface = k in (0, n)
            if x_surface and z_surface:
                continue
            out.append(_seg(xs[i], y0, zs[k], xs[i], y1, zs[k],
                            face if (x_surface or z_surface) else inner))
    # Z-directed lines: vary x and y.
    for i in range(n + 1):
        x_surface = i in (0, n)
        for j in range(n + 1):
            y_surface = j in (0, n)
            if x_surface and y_surface:
                continue
            out.append(_seg(xs[i], ys[j], z0, xs[i], ys[j], z1,
                            face if (x_surface or y_surface) else inner))
    return out


def effective_level(level: int, dimensions, base_cap: int = 5) -> int:
    """Reduce detail on small parts so an accent cube cannot cost as much as a tower."""
    width, depth, height = (max(1.0, float(v)) for v in dimensions)
    smallest = min(width, depth, height)
    level = max(1, min(base_cap, int(level)))
    if smallest < 12.0:
        return max(1, level - 3)
    if smallest < 24.0:
        return max(1, level - 2)
    if smallest < 44.0:
        return max(1, level - 1)
    return level
