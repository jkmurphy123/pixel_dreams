"""Screen layout for The Glass Castle.

The reviewed compositions are authored at 1280x400 (strip) and 1080x1920
(portrait).  This module transforms one of those reference scenes onto the real
screen: a uniform scale from the width, the castle's footing anchored to a
fraction of the height, and a cliff that always reaches the bottom edge.  A
16:9 display therefore gets the strip composition re-anchored with more sky,
not a stretched strip.

`geometry.py` holds the reviewed reference data.  Nothing here draws; the
renderer and the castle/cliff builders consume the transformed geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import REFERENCE_LAYOUTS

ORIENTATIONS = ("auto", "landscape", "portrait")
LANDSCAPE_REF = REFERENCE_LAYOUTS["landscape"]
PORTRAIT_REF = REFERENCE_LAYOUTS["portrait"]

#: The reviewed still was pinned to this moment; the mode's aurora is phased so
#: that the same moment is the bright peak.
REVIEW_TIME = 15.0


@dataclass
class SceneLayout:
    name: str
    width: int
    height: int
    portrait: bool
    orientation: str

    scale: float
    base_y: float
    margin: int
    layer_margin: int

    title_px: int
    telemetry_px: int
    small_px: int
    title_track: float

    star_count: int
    snow_far_hint: int
    snow_near_hint: int

    curtains: tuple
    aurora_top: float
    aurora_floor: tuple

    plateau: tuple
    lip: tuple
    ridge: tuple
    ridge_right: tuple
    mass_left: tuple
    mass_right: tuple
    buttresses: tuple
    shards: tuple
    castle: dict

    castle_bounds: tuple
    corner_rect: tuple
    hud_rect: tuple

    geometry: dict = field(repr=False, default_factory=dict)

    @property
    def center_x(self) -> float:
        return self.width * 0.5

    @property
    def drift_cap(self) -> int:
        return max(8, int(round(self.width * 0.018)))


def _triangle_area_ratio(size, ref):
    return ((size[0] * size[1]) / float(ref[0] * ref[1])) ** 0.5


def _transform(ref: dict, width: int, height: int,
               portrait: bool) -> dict:
    ref_w, ref_h = ref["size"]
    ref_cx = 540.0 if portrait else 640.0
    ref_base = float(ref["castle"]["base_y"])
    base = height * (1444.0 / 1920.0 if portrait else 0.84)

    # Uniform scale from the width, so the strip composition is never squeezed.
    scale = width / float(ref_w)

    # A very short/very wide screen could push the tallest spire off the top.
    tips = [t[4] for t in ref["castle"]["main"]]
    tips += [t[4] for t in ref["castle"]["far"]]
    tips += [t[4] for t in ref["castle"].get("gatehouse", ())]
    top_ref = min(tips) if tips else ref_base - 1.0
    above = max(1.0, ref_base - top_ref)
    scale = min(scale, max(0.2, (base - height * 0.03) / above))

    def x_of(x: float) -> float:
        return width * 0.5 + (float(x) - ref_cx) * scale

    def y_of(y: float) -> float:
        if y >= ref_h - 1.0:
            return float(height)
        return base + (float(y) - ref_base) * scale

    def pt(p):
        return (x_of(p[0]), y_of(p[1]))

    def pts(seq):
        return tuple(pt(p) for p in seq)

    castle = ref["castle"]
    towers = {}
    for group in ("far", "main"):
        towers[group] = tuple(
            (x_of(cx), bw * scale, y_of(sy), tw * scale, y_of(ty),
             lean * scale)
            for (cx, bw, sy, tw, ty, lean) in castle[group])
    towers["gatehouse"] = tuple(
        (x_of(cx), bw * scale, y_of(sy), tw * scale, y_of(ty), lean * scale)
        for (cx, bw, sy, tw, ty, lean) in castle.get("gatehouse", ()))
    wall = castle["wall"]
    plinth = castle["plinth"]
    gate = castle["gate"]
    waists = {i: (y_of(wy), ww * scale)
              for i, (wy, ww) in castle.get("waists", {}).items()}
    fins = tuple(tuple(x_of(v) if k % 2 == 0 else y_of(v)
                       for k, v in enumerate(fin))
                 for fin in castle.get("fins", ()))

    castle_out = {
        "base_y": base,
        "far": towers["far"],
        "main": towers["main"],
        "gatehouse": towers["gatehouse"],
        "wall": (x_of(wall[0]), x_of(wall[1]), y_of(wall[2]),
                 y_of(wall[3]), wall[4] * scale),
        "plinth": (x_of(plinth[0]), x_of(plinth[1]), y_of(plinth[2]),
                   y_of(plinth[3]), plinth[4] * scale),
        "gate": (x_of(gate[0]), y_of(gate[1]), gate[2] * scale,
                 gate[3] * scale),
        "waists": waists,
        "fins": fins,
    }

    # Bounding box of the main mass, used by stats and clearance tests.
    xs, ys = [], []
    for group in ("main", "gatehouse"):
        for (cx, bw, sy, tw, ty, lean) in towers[group]:
            xs.extend((cx - bw * 0.5, cx + bw * 0.5))
            ys.extend((sy, ty))
    for x0, x1, y0, y1, _ in (castle_out["wall"], castle_out["plinth"]):
        xs.extend((x0, x1))
        ys.extend((y0, y1))
    castle_bounds = (min(xs), min(ys), max(xs), max(ys))

    shards = tuple((x_of(x), y_of(y), ln * scale, wd * scale, ang, b)
                   for (x, y, ln, wd, ang, b) in ref["shards"])

    density = _triangle_area_ratio((width, height), (ref_w, ref_h))
    return {
        "castle": castle_out,
        "plateau": pts(ref["plateau"]),
        "lip": pts(ref["lip"]),
        "ridge": pts(ref["ridge"]),
        "ridge_right": pts(ref["ridge_right"]),
        "mass_left": pts(ref["mass_left"]),
        "mass_right": pts(ref["mass_right"]),
        "buttresses": tuple(pts(poly) for poly in ref.get("buttresses", ())),
        "shards": shards,
        "curtains": tuple(ref["curtains"]),
        "aurora_top": float(ref.get("aurora_top", 0.10)),
        "aurora_floor": tuple(ref.get("aurora_floor", (0.64, 0.32))),
        "castle_bounds": castle_bounds,
        "star_count": max(70, min(420, int(round(
            ref["stars"] * min(2.2, density))))),
        "snow_far_hint": ref["snow_far"],
        "snow_near_hint": ref["snow_near"],
    }


def _fonts(width: int, height: int, portrait: bool):
    if portrait:
        title = max(28, min(56, int(round(width * 0.0389))))
        telemetry = max(16, min(24, int(round(width * 0.0157))))
        small = max(12, min(18, int(round(width * 0.0120))))
        track = max(2.0, round(width * 0.0037, 2))
        margin = max(24, int(round(width * 0.0407)))
    else:
        title = max(22, min(40, int(round(width * 0.0203))))
        telemetry = max(12, min(20, int(round(width * 0.0094))))
        small = max(10, min(16, int(round(width * 0.0078))))
        track = max(1.5, round(width * 0.001875, 2))
        margin = max(18, int(round(width * 0.0203)))
    margin = max(12, min(margin, min(width, height) // 6))
    layer_margin = max(24, int(round(width * 0.020)))
    return title, telemetry, small, track, margin, layer_margin


def resolve_layout(size, orientation: str = "auto") -> SceneLayout:
    """Resolve the reviewed composition for a real screen."""
    width = max(64, int(size[0]))
    height = max(64, int(size[1]))
    if orientation not in ORIENTATIONS:
        raise ValueError("orientation must be " + ", ".join(ORIENTATIONS))
    portrait = (orientation == "portrait"
                or (orientation == "auto" and height > width * 1.20))
    ref = PORTRAIT_REF if portrait else LANDSCAPE_REF
    geo = _transform(ref, width, height, portrait)
    title, telemetry, small, track, margin, layer_margin = _fonts(
        width, height, portrait)

    corner = (0, height - 32, 80, 32)
    hud = (margin, margin, max(1, width - 2 * margin),
           max(1, height - 2 * margin))

    return SceneLayout(
        name="portrait" if portrait else "landscape",
        width=width, height=height, portrait=portrait,
        orientation=orientation,
        scale=width / float(ref["size"][0]),
        base_y=geo["castle"]["base_y"],
        margin=margin, layer_margin=layer_margin,
        title_px=title, telemetry_px=telemetry, small_px=small,
        title_track=track,
        star_count=geo["star_count"],
        snow_far_hint=geo["snow_far_hint"],
        snow_near_hint=geo["snow_near_hint"],
        curtains=geo["curtains"],
        aurora_top=geo["aurora_top"], aurora_floor=geo["aurora_floor"],
        plateau=geo["plateau"], lip=geo["lip"],
        ridge=geo["ridge"], ridge_right=geo["ridge_right"],
        mass_left=geo["mass_left"], mass_right=geo["mass_right"],
        buttresses=geo["buttresses"],
        shards=geo["shards"], castle=geo["castle"],
        castle_bounds=geo["castle_bounds"],
        corner_rect=corner, hud_rect=hud,
        geometry=geo,
    )

