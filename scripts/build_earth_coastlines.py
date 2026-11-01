"""Build the wireframe Earth's coastline data from Natural Earth 1:110m land.

This script is a build step, not part of the mode.  It turns the public-domain
Natural Earth ``ne_110m_land`` polygons into the small list of closed lon/lat
rings that ``data/earth_coastlines.json`` holds, so the kiosk never needs a
network connection and never carries a GIS dependency.

Run (the source may be a URL or a local GeoJSON path):

    python scripts/build_earth_coastlines.py \
        --source https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_land.geojson

The simplification is iterative Douglas-Peucker at ~0.28 degrees, followed by
a small-area filter.  At the globe sizes this mode draws that is sub-pixel to
about two pixels of error: enough to keep Africa, the Americas, Eurasia,
Australia, Greenland, Japan and New Zealand recognisable without shipping a
megabyte of coastline.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request


DEFAULT_SOURCE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                  "master/geojson/ne_110m_land.geojson")
DEFAULT_OUTPUT = os.path.join("data", "earth_coastlines.json")
TOLERANCE_DEG = 0.28
MIN_AREA_SQ_DEG = 2.0
ROUND_DIGITS = 2


def _read_source(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            return json.load(response)
    with open(source, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _perpendicular_distance(point, start, end) -> float:
    ax, ay = start
    bx, by = end
    px, py = point
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return math.hypot(px - ax, py - ay)
    return abs(dx * (ay - py) - (ax - px) * dy) / length


def simplify(points: list[tuple[float, float]], tolerance: float):
    """Iterative Douglas-Peucker, so a long coastline cannot blow the stack."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        best_distance = -1.0
        best_index = -1
        for index in range(start + 1, end):
            distance = _perpendicular_distance(points[index],
                                               points[start], points[end])
            if distance > best_distance:
                best_distance = distance
                best_index = index
        if best_distance > tolerance:
            keep[best_index] = True
            stack.append((start, best_index))
            stack.append((best_index, end))
    return [point for point, kept in zip(points, keep) if kept]


def _ring_area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


def _rings(geometry: dict):
    if geometry.get("type") == "Polygon":
        yield from geometry.get("coordinates", [])
    elif geometry.get("type") == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            yield from polygon


def build(source: str, tolerance: float, min_area: float) -> dict:
    data = _read_source(source)
    coastlines = []
    points_total = 0
    dropped = 0
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        for raw in _rings(geometry):
            if not raw:
                continue
            closed = raw[0] == raw[-1]
            ring = raw[:-1] if closed else list(raw)
            ring = [(float(x), float(y)) for x, y in ring]
            simplified = simplify(ring, tolerance)
            if len(simplified) < 4:
                dropped += 1
                continue
            if _ring_area(simplified + [simplified[0]]) < min_area:
                dropped += 1
                continue
            encoded = [[round(x, ROUND_DIGITS), round(y, ROUND_DIGITS)]
                       for x, y in simplified]
            # A ring is drawn closed, so the repeated last point is redundant.
            if encoded[0] == encoded[-1]:
                encoded = encoded[:-1]
            coastlines.append(encoded)
            points_total += len(encoded)
    coastlines.sort(key=len, reverse=True)
    return {
        "source": "Natural Earth 1:110m land (public domain)",
        "source_url": source,
        "tolerance_deg": tolerance,
        "min_area_sq_deg": min_area,
        "ring_count": len(coastlines),
        "point_count": points_total,
        "dropped_rings": dropped,
        "coastlines": coastlines,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="GeoJSON URL or path (default: Natural Earth 110m land)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help=f"output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_DEG,
                        help=f"simplify tolerance in degrees (default: {TOLERANCE_DEG})")
    parser.add_argument("--min-area", type=float, default=MIN_AREA_SQ_DEG,
                        help=f"drop rings smaller than this (default: {MIN_AREA_SQ_DEG})")
    args = parser.parse_args()

    payload = build(args.source, args.tolerance, args.min_area)
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
    print(f"wrote {output}")
    print(f"rings={payload['ring_count']} points={payload['point_count']} "
          f"dropped={payload['dropped_rings']} bytes={os.path.getsize(output)}")


if __name__ == "__main__":
    main()
