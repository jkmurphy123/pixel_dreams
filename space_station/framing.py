"""Framing presets for Space Station V.

The same drawing has to work on the 1280x400 Pi wall, a 16:9 desktop and a
portrait panel.  A preset only chooses the two anchors and the two radii;
station and Earth remain separate so the station can sit in front of the
planet's limb without either one being resized to fit the other.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


PRESETS = {
    # 16:9 and similar.  Station left of centre, Earth below/right of it.
    "landscape": {
        "station_anchor_x": 0.380, "station_anchor_y": 0.490,
        "station_radius": 0.335,
        "earth_anchor_x": 0.735, "earth_anchor_y": 0.845,
        "earth_radius": 0.660,
    },
    # The 1280x400 kiosk (3.2:1): the station gets more of the height and the
    # Earth becomes a big arc behind its right shoulder.
    "ultrawide": {
        "station_anchor_x": 0.380, "station_anchor_y": 0.490,
        "station_radius": 0.340,
        "earth_anchor_x": 0.755, "earth_anchor_y": 0.865,
        "earth_radius": 0.700,
    },
    "square": {
        "station_anchor_x": 0.420, "station_anchor_y": 0.445,
        "station_radius": 0.300,
        "earth_anchor_x": 0.650, "earth_anchor_y": 0.820,
        "earth_radius": 0.580,
    },
    # Portrait: station above, Earth filling the lower half.
    "portrait": {
        "station_anchor_x": 0.450, "station_anchor_y": 0.350,
        "station_radius": 0.330,
        "earth_anchor_x": 0.550, "earth_anchor_y": 0.825,
        "earth_radius": 0.660,
    },
}

ORIENTATIONS = ("auto", "landscape", "ultrawide", "portrait", "square")


@dataclass(frozen=True)
class Framing:
    preset: str
    width: int
    height: int
    station_anchor_x: float
    station_anchor_y: float
    station_radius_px: float
    earth_anchor_x: float
    earth_anchor_y: float
    earth_radius_px: float


def aspect_class(width: int, height: int) -> str:
    aspect = width / max(1, height)
    if aspect >= 2.2:
        return "ultrawide"
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


def resolve_framing(config: dict, size: tuple[int, int]) -> Framing:
    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0:
        raise ValueError("screen size must be positive")

    requested = str(config.get("orientation", "auto")).lower()
    if requested not in ORIENTATIONS:
        raise ValueError("orientation must be auto, landscape, ultrawide, "
                         "portrait, or square")
    preset_name = aspect_class(width, height) if requested == "auto" else requested
    preset = PRESETS[preset_name]

    station_scale = _number(config, "station_scale", 1.0, 0.35, 1.8)
    earth_scale = _number(config, "earth_scale", 1.0, 0.35, 1.8)
    station_x = _number(config, "station_anchor_x", preset["station_anchor_x"],
                        0.05, 0.95)
    station_y = _number(config, "station_anchor_y", preset["station_anchor_y"],
                        0.05, 0.95)
    earth_x = _number(config, "earth_anchor_x", preset["earth_anchor_x"],
                      0.05, 0.95)
    earth_y = _number(config, "earth_anchor_y", preset["earth_anchor_y"],
                      0.05, 0.95)
    shortest = min(width, height)
    return Framing(
        preset=preset_name,
        width=width,
        height=height,
        station_anchor_x=station_x,
        station_anchor_y=station_y,
        station_radius_px=preset["station_radius"] * shortest * station_scale,
        earth_anchor_x=earth_x,
        earth_anchor_y=earth_y,
        earth_radius_px=preset["earth_radius"] * shortest * earth_scale,
    )
