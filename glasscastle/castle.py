"""The castle, its windows and its orbiting shards.

The static mass is built once into a transparent mid-ground layer: the snow
ledge, the curtain wall, the keep and flanking towers, the plinth, the gate
towers and the gate arch.  The warm windows, the gate spill and the shards are
drawn per frame, because they are the only parts of the castle that move.  The
silhouette polygons are returned with the scene so the renderer can clip the
aurora reflection to the glass.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .palette import Palette, mix, scale, smoothstep
from .layout import SceneLayout, REVIEW_TIME

TAU = math.tau


# --------------------------------------------------------------------- tower

class Tower:
    """One crystal tower: a tapered body (optionally with a keep waist), a spire."""

    def __init__(self, cx, base_y, base_w, shoulder_y, top_w, tip_y, lean=0.0,
                 *, dim=1.0, far=False, waist=None):
        self.cx = cx
        self.base_y = base_y
        self.base_w = base_w
        self.shoulder_y = shoulder_y
        self.top_w = top_w
        self.tip_y = tip_y
        self.lean = lean
        self.dim = dim
        self.far = far
        self.waist_y = waist[0] if waist else None
        self.waist_w = waist[1] if waist else None
        if waist:
            wy, ww = waist
            self.poly = (
                (cx - base_w * 0.5, base_y),
                (cx - ww * 0.5, wy),
                (cx - top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + lean, tip_y),
                (cx + top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + ww * 0.5, wy),
                (cx + base_w * 0.5, base_y),
            )
        else:
            self.poly = (
                (cx - base_w * 0.5, base_y),
                (cx + base_w * 0.5, base_y),
                (cx + top_w * 0.5 + lean * 0.22, shoulder_y),
                (cx + lean, tip_y),
                (cx - top_w * 0.5 + lean * 0.22, shoulder_y),
            )

    def _t_waist(self) -> float:
        return ((self.base_y - self.waist_y)
                / max(1.0, self.base_y - self.shoulder_y))

    def edges_at(self, t: float) -> tuple[float, float]:
        t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
        if self.waist_y is None:
            width = self.base_w * (1.0 - t) + self.top_w * t
        else:
            tw = self._t_waist()
            if t <= tw:
                width = self.base_w + (self.waist_w - self.base_w) * (t / tw)
            else:
                u = (t - tw) / max(0.001, 1.0 - tw)
                width = self.waist_w + (self.top_w - self.waist_w) * u
        cx = self.cx + self.lean * 0.22 * t
        return cx - width * 0.5, cx + width * 0.5

    def window_anchor(self, v: float, u: float) -> tuple[float, float]:
        xl, xr = self.edges_at(v)
        return (xl + (xr - xl) * u,
                self.base_y - (self.base_y - self.shoulder_y) * v)


@dataclass
class Window:
    x: float
    y: float
    w: float
    base: float
    period: float
    phase: float
    dim: float
    great: bool = False


@dataclass
class Shard:
    x: float
    y: float
    length: float
    width: float
    angle: float
    bright: float
    period: float
    phase: float
    rx: float
    ry: float
    spin: float
    a0: float = 0.0

    def at(self, time_s: float):
        a = self.phase + TAU * time_s / self.period
        x = self.x + self.rx * (math.cos(a) - math.cos(self.a0))
        y = self.y + self.ry * (math.sin(a) - math.sin(self.a0))
        angle = self.angle + self.spin * (time_s - REVIEW_TIME)
        return x, y, angle


@dataclass
class CastleScene:
    far_towers: list
    towers: list
    gatehouses: list
    windows: list
    shards: list
    silhouette: list
    wall_poly: list
    plinth_poly: list
    tips: list
    shard_count: int = 0

    def silhouette_shifted(self, dx: float):
        return [tuple((x + dx, y) for x, y in poly)
                for poly in self.silhouette]


# ------------------------------------------------------------------ geometry

def _wall_points(layout: SceneLayout, ox: float = 0.0) -> list:
    x0, x1, base_y, top_y, spike = layout.castle["wall"]
    x0 += ox
    x1 += ox
    points = [(x0, base_y)]
    x = x0
    step = (x1 - x0) / 9.0
    i = 0
    while x <= x1 + 0.1:
        h = spike + (7.0 * (spike / 16.0) if i % 2 == 0 else 0.0)
        points.append((x, top_y))
        points.append((x + step * 0.26, top_y - h))
        points.append((x + step * 0.52, top_y))
        x += step
        i += 1
    points.append((x1, base_y))
    return points


def _plinth_points(layout: SceneLayout, ox: float = 0.0) -> list:
    x0, x1, base_y, top_y, spike = layout.castle["plinth"]
    x0 += ox
    x1 += ox
    points = [(x0, base_y)]
    x = x0
    step = (x1 - x0) / 11.0
    i = 0
    while x <= x1 + 0.1:
        h = spike + (4.0 * (spike / 12.0) if i % 2 == 0 else 0.0)
        points.append((x, top_y))
        points.append((x + step * 0.30, top_y - h))
        points.append((x + step * 0.60, top_y))
        x += step
        i += 1
    points.append((x1, base_y))
    return points


def _extend_x(points, x0: float, x1: float):
    pts = list(points)
    if pts and pts[0][0] > x0:
        pts.insert(0, (x0, pts[0][1]))
    if pts and pts[-1][0] < x1:
        pts.append((x1, pts[-1][1]))
    return pts


def _pad_poly(points, x0: float, x1: float):
    """Extend a silhouette polygon to the canvas sides for drift overscan."""
    pts = list(points)
    if not pts:
        return pts
    if pts[0][0] > x0:
        pts.insert(0, (x0, pts[0][1]))
    if pts[-1][0] < x1:
        pts.append((x1, pts[-1][1]))
    ymax = max(p[1] for p in pts)
    pts.append((x1, ymax))
    pts.append((x0, ymax))
    return pts


def build_castle(layout: SceneLayout, seed: int,
                 shard_count: int = 6) -> CastleScene:
    cfg = layout.castle
    far_towers = [
        Tower(cx, cfg["base_y"], bw, sy, tw, ty, lean,
              dim=0.46, far=True)
        for (cx, bw, sy, tw, ty, lean) in cfg["far"]]

    towers = []
    dims = (1.0, 0.92, 0.92, 0.74, 0.74, 0.82, 0.82)
    for i, (cx, bw, sy, tw, ty, lean) in enumerate(cfg["main"]):
        towers.append(Tower(
            cx, cfg["base_y"], bw, sy, tw, ty, lean,
            dim=dims[i % len(dims)],
            waist=cfg.get("waists", {}).get(i)))

    gatehouses = [
        Tower(cx, cfg["base_y"], bw, sy, tw, ty, lean, dim=0.86)
        for (cx, bw, sy, tw, ty, lean) in cfg.get("gatehouse", ())]

    scale_ = max(0.25, float(layout.scale))
    windows: list[Window] = []
    for i, tower in enumerate(towers):
        rng = random.Random(seed * 17 + i + 1)
        if i == 0:
            cols, rows = 4, 4
        elif i in (1, 2):
            cols, rows = 3, 3
        else:
            cols, rows = 2, 2
        for row in range(rows):
            v = 0.14 + 0.19 * row
            for col in range(cols):
                if rng.random() < 0.16:
                    continue
                u = 0.30 + 0.40 * (col / max(1, cols - 1))
                x, y = tower.window_anchor(v, u)
                windows.append(Window(
                    x=x, y=y,
                    w=(3.6 if i == 0 else 3.0) * scale_,
                    base=rng.uniform(0.55, 1.0),
                    period=rng.uniform(2.8, 7.2),
                    phase=rng.uniform(0.0, TAU),
                    dim=tower.dim))
        if i == 0:
            for u, w, b, great in ((0.50, 7.4, 0.98, True),
                                   (0.30, 3.6, 0.76, False),
                                   (0.70, 3.6, 0.76, False)):
                x, y = tower.window_anchor(0.24, u)
                windows.append(Window(
                    x=x, y=y, w=w * scale_, base=b,
                    period=rng.uniform(4.0, 7.0),
                    phase=rng.uniform(0.0, TAU),
                    dim=tower.dim, great=great))

    for i, tower in enumerate(gatehouses):
        rng = random.Random(seed * 41 + i)
        for v in (0.18, 0.44, 0.68):
            x, y = tower.window_anchor(v, 0.5)
            windows.append(Window(
                x=x, y=y, w=2.6 * scale_,
                base=rng.uniform(0.55, 0.9),
                period=rng.uniform(3.0, 7.0),
                phase=rng.uniform(0.0, TAU),
                dim=tower.dim))

    # A quiet line of wall windows between the towers.
    x0, x1, _, top_y, _ = cfg["wall"]
    for i in range(7):
        windows.append(Window(
            x=x0 + (x1 - x0) * (i + 0.5) / 7.0,
            y=top_y + 16.0 * scale_,
            w=2.6 * scale_,
            base=0.5, period=3.4 + i * 0.37, phase=i * 1.7,
            dim=0.82))

    # Shards: the reviewed positions are the anchor; the orbit returns there at
    # REVIEW_TIME, so the preview still matches the study.
    shards = []
    for i, (x, y, ln, wd, ang, bright) in enumerate(layout.shards[:max(0, shard_count)]):
        rng = random.Random(seed * 53 + i)
        period = rng.uniform(20.0, 40.0)
        phase = rng.uniform(0.0, TAU)
        a0 = phase + TAU * REVIEW_TIME / period
        shards.append(Shard(
            x=x, y=y, length=ln, width=wd, angle=ang, bright=bright,
            period=period, phase=phase,
            rx=rng.uniform(6.0, 14.0) * scale_,
            ry=rng.uniform(3.0, 8.0) * scale_,
            spin=rng.uniform(-14.0, 14.0), a0=a0))

    wall_poly = _wall_points(layout)
    plinth_poly = _plinth_points(layout)
    silhouette = [t.poly for t in towers] + [t.poly for t in gatehouses]
    silhouette.append(tuple(wall_poly))
    silhouette.append(tuple(plinth_poly))
    for fin in layout.castle.get("fins", ()):
        silhouette.append(((fin[0], fin[1]), (fin[2], fin[3]),
                           (fin[4], fin[5])))

    tips = [(t.cx + t.lean, t.tip_y, (0.55 if i == 0 else
                                      0.34 if i in (1, 2) else 0.22))
            for i, t in enumerate(towers)]

    return CastleScene(
        far_towers=far_towers, towers=towers, gatehouses=gatehouses,
        windows=windows, shards=shards, silhouette=silhouette,
        wall_poly=wall_poly, plinth_poly=plinth_poly, tips=tips,
        shard_count=shard_count)


# ------------------------------------------------------------------- drawing

def _tower_colors(tower: Tower, t: float, p: Palette):
    base = mix(p.face_base, p.face_hi, t ** 0.75)
    if tower.far:
        base = mix(p.bg_mid, base, 0.55)
    base = scale(base, tower.dim)
    lit = mix(base, p.face_lit, 0.26 * tower.dim)
    dark = scale(base, 0.62)
    return base, lit, dark


def draw_tower(screen, tower: Tower, p: Palette, ox: float = 0.0) -> None:
    base_y = tower.base_y
    sh_y = tower.shoulder_y
    for y in range(int(sh_y), int(base_y) + 1):
        t = (base_y - y) / max(1.0, base_y - sh_y)
        xl, xr = tower.edges_at(t)
        base, lit, dark = _tower_colors(tower, t, p)
        x1, x2 = int(xl + ox), int(xr + ox)
        if x2 <= x1:
            continue
        pygame.draw.line(screen, base, (x1, y), (x2, y))
        pygame.draw.line(screen, lit, (x1, y),
                         (x1 + int((x2 - x1) * 0.26), y))
        pygame.draw.line(screen, dark,
                         (x1 + int((x2 - x1) * 0.74), y), (x2, y))

    apex = (tower.cx + tower.lean + ox, tower.tip_y)
    for y in range(int(tower.tip_y), int(sh_y) + 1):
        t = 1.0 - (y - tower.tip_y) / max(1.0, sh_y - tower.tip_y)
        half = (tower.top_w * 0.5) * (1.0 - t)
        cx = tower.cx + tower.lean * t
        xl, xr = cx - half, cx + half
        base, lit, dark = _tower_colors(tower, 0.85 + 0.15 * t, p)
        base = mix(base, p.edge_dim, 0.10 + 0.22 * t)
        x1, x2 = int(xl + ox), int(xr + ox)
        if x2 <= x1:
            x2 = x1 + 1
        pygame.draw.line(screen, base, (x1, y), (x2, y))
        if t < 0.55:
            pygame.draw.line(screen, lit, (x1, y),
                             (x1 + max(1, int((x2 - x1) * 0.30)), y))

    left = [(tower.cx - tower.base_w * 0.5 + ox, base_y),
            (tower.cx - tower.top_w * 0.5 + tower.lean * 0.22 + ox, sh_y),
            apex]
    right = [(tower.cx + tower.base_w * 0.5 + ox, base_y),
             (tower.cx + tower.top_w * 0.5 + tower.lean * 0.22 + ox, sh_y),
             apex]
    rim = mix(p.edge, p.glow, 0.30) if not tower.far else p.edge_dim
    pygame.draw.aalines(screen, scale(rim, 0.40 + 0.60 * tower.dim),
                        False, left)
    pygame.draw.aalines(screen, scale(p.edge_dim, 0.24 + 0.5 * tower.dim),
                        False, right)
    pygame.draw.line(screen, scale(p.edge_dim, 0.35 * tower.dim),
                     (tower.cx - tower.top_w * 0.5 + ox, sh_y),
                     (tower.cx + tower.top_w * 0.5 + ox, sh_y), 1)

    # Facets: long lines to the apex, three seams, three slanted cuts.
    for u in (0.34, 0.68):
        xb = tower.cx + (u - 0.5) * tower.base_w + ox
        pygame.draw.aaline(screen,
                           scale(mix(p.face_hi, p.ink, 0.30),
                                 0.40 + 0.50 * tower.dim),
                           (xb, base_y), apex)
    xl, xr = tower.edges_at(0.08)
    hx = xl + (xr - xl) * 0.20 + ox
    pygame.draw.aaline(screen, scale(mix(p.glow, p.ink, 0.30),
                                     0.30 * tower.dim),
                       (hx, base_y),
                       (hx + tower.lean * 0.5, sh_y))
    for v in (0.32, 0.58, 0.80):
        xl, xr = tower.edges_at(v)
        yy = tower.base_y - (tower.base_y - tower.shoulder_y) * v
        pygame.draw.aaline(screen,
                           scale(mix(p.face_hi, p.ink, 0.25),
                                 0.18 + 0.25 * tower.dim),
                           (xl + ox, yy), (xr + ox, yy))
        pygame.draw.aaline(screen, scale(p.face_lit, 0.22 * tower.dim),
                           (xl + (xr - xl) * 0.12 + ox, yy - 2),
                           (xl + (xr - xl) * 0.30 + ox, yy - 2))
    for (u0, v0, u1, v1) in ((0.26, 0.10, 0.58, 0.48),
                             (0.74, 0.10, 0.42, 0.48),
                             (0.34, 0.56, 0.56, 0.84)):
        xa0, xa1 = tower.edges_at(v0)
        xb0, xb1 = tower.edges_at(v1)
        xa = xa0 + (xa1 - xa0) * u0
        xb = xb0 + (xb1 - xb0) * u1
        ya = tower.base_y - (tower.base_y - tower.shoulder_y) * v0
        yb = tower.base_y - (tower.base_y - tower.shoulder_y) * v1
        pygame.draw.aaline(screen, scale(mix(p.face_hi, p.glow, 0.30),
                                         0.44 * tower.dim),
                           (xa + ox, ya), (xb + ox, yb))


def _soft_ellipse(screen, cx, cy, w, h, color, alpha):
    surf = pygame.Surface((max(2, int(w)), max(2, int(h))), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    pygame.draw.ellipse(surf, (*color, alpha), surf.get_rect())
    screen.blit(surf, (int(cx - w * 0.5), int(cy - h * 0.5)))


def draw_plateau(screen, layout: SceneLayout, p: Palette, ox: float,
                 seed: int) -> None:
    cw, ch = screen.get_size()
    top = _extend_x([(x + ox, y) for x, y in layout.plateau], 0, cw)
    lip = _extend_x([(x + ox, y) for x, y in layout.lip], 0, cw)
    poly = top + list(reversed(lip))
    pygame.draw.polygon(screen, mix(p.plateau_bottom, p.plateau_top, 0.5), poly)

    y0 = min(y for _, y in top)
    y1 = max(y for _, y in lip)
    band = pygame.Surface((cw, ch), pygame.SRCALPHA)
    for y in range(int(y0), int(y1) + 1):
        t = (y - y0) / max(1.0, y1 - y0)
        col = mix(p.plateau_top, p.plateau_bottom, smoothstep(t))
        pygame.draw.line(band, (*col, 255), (0, y), (cw, y))
    mask = pygame.Surface((cw, ch), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(int(x), int(y)) for x, y in poly])
    band.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(band, (0, 0))

    pygame.draw.aalines(screen, mix(p.snow_dim, p.snow, 0.55), False, top)
    pygame.draw.lines(screen, scale(p.snow, 0.62), False, top, 1)

    rng = random.Random(seed ^ 0x77A1)
    count = 80 if not layout.portrait else 210
    for _ in range(count):
        x = rng.uniform(0, cw)
        y = rng.uniform(y0 + 4, y1 - 2)
        length = rng.uniform(8, 38)
        col = mix(p.plateau_bottom, p.snow_dim, rng.uniform(0.08, 0.30))
        pygame.draw.line(screen, col, (x, y), (x + length, y), 1)
    for _ in range(14 if not layout.portrait else 36):
        x = rng.uniform(0, cw)
        y = rng.uniform(y0 + (y1 - y0) * 0.62, y1 - 2)
        pygame.draw.line(screen, scale(p.glow, rng.uniform(0.18, 0.42)),
                         (x - 2, y), (x + 2, y), 1)
        pygame.draw.line(screen, scale(p.glow, rng.uniform(0.12, 0.30)),
                         (x, y - 2), (x, y + 2), 1)
    pygame.draw.aalines(screen, mix(p.cliff_edge, p.snow_dim, 0.45), False, lip)


def draw_ground_shadows(screen, layout: SceneLayout, scene: CastleScene,
                        ox: float) -> None:
    x0, x1, base_y, _, _ = layout.castle["wall"]
    _soft_ellipse(screen, (x0 + x1) * 0.5 + ox, base_y - 2,
                  (x1 - x0) * 1.05, 12, (2, 4, 9), 110)
    for tower in scene.towers:
        _soft_ellipse(screen, tower.cx + ox, tower.base_y - 1,
                      tower.base_w * 1.5, 12, (2, 4, 9), 150)
    for tower in scene.far_towers:
        _soft_ellipse(screen, tower.cx + ox, tower.base_y - 1,
                      tower.base_w * 1.7, 8, (2, 4, 9), 90)


def draw_wall(screen, layout: SceneLayout, p: Palette, ox: float) -> None:
    x0, x1, base_y, top_y, spike = layout.castle["wall"]
    points = _wall_points(layout, ox)
    pygame.draw.polygon(screen, mix(p.bg_top, p.face_base, 0.55),
                        [(px, py) for px, py in points])
    for y in range(int(top_y), int(base_y)):
        t = (y - top_y) / max(1.0, base_y - top_y)
        col = mix(mix(p.face_hi, p.snow_dim, 0.18),
                  mix(p.face_base, p.bg_top, 0.25), smoothstep(t))
        pygame.draw.line(screen, col, (x0 + ox, y), (x1 + ox, y))
    pygame.draw.aalines(screen, mix(p.edge_dim, p.edge, 0.40), False,
                        [(px, py) for px, py in points[1:-1]])
    for i in range(8):
        bx = x0 + (x1 - x0) * (i + 0.5) / 8.0 + ox
        pygame.draw.line(screen, mix(p.bg_top, p.face_base, 0.35),
                         (bx, top_y), (bx, base_y), 1)
        pygame.draw.aaline(screen, scale(p.edge_dim, 0.35),
                           (bx, top_y), (bx, base_y))


def draw_plinth(screen, layout: SceneLayout, p: Palette, ox: float) -> None:
    x0, x1, base_y, top_y, spike = layout.castle["plinth"]
    points = _plinth_points(layout, ox)
    pygame.draw.polygon(screen, mix(p.bg_top, p.face_base, 0.6),
                        [(px, py) for px, py in points])
    for y in range(int(top_y), int(base_y)):
        t = (y - top_y) / max(1.0, base_y - top_y)
        col = mix(mix(p.face_hi, p.snow_dim, 0.22),
                  mix(p.face_base, p.bg_top, 0.2), smoothstep(t))
        pygame.draw.line(screen, col, (x0 + ox, y), (x1 + ox, y))
    pygame.draw.aalines(screen, mix(p.edge_dim, p.edge, 0.55), False,
                        [(px, py) for px, py in points[1:-1]])
    for i in range(5):
        bx = x0 + (x1 - x0) * (i + 0.5) / 5.0 + ox
        pygame.draw.line(screen, mix(p.bg_top, p.face_base, 0.3),
                         (bx, top_y), (bx, base_y), 1)


def draw_fins(screen, layout: SceneLayout, p: Palette, ox: float) -> None:
    for (x1, y1, x2, y2, x3, y3) in layout.castle.get("fins", ()):
        pts = [(x1 + ox, y1), (x2 + ox, y2), (x3 + ox, y3)]
        pygame.draw.polygon(screen, mix(p.bg_top, p.face_base, 0.5), pts)
        pygame.draw.aalines(screen, scale(p.edge_dim, 0.55), True, pts)
        pygame.draw.aaline(screen, scale(p.face_lit, 0.55),
                           (x1 + ox, y1), (x2 + ox, y2))


def draw_gate(screen, layout: SceneLayout, p: Palette, ox: float) -> None:
    gx, gy, gw, gh = layout.castle["gate"]
    gx += ox
    rect = pygame.Rect(int((gx - gw * 0.5)), int(gy - gh),
                       max(2, int(gw)), max(2, int(gh)))
    pygame.draw.rect(screen, p.warm_dim, rect,
                     border_radius=max(1, int(gw * 0.20)))
    outer = rect.inflate(max(1, int(gw * 0.18)), max(1, int(gw * 0.18)))
    pygame.draw.rect(screen, p.warm, outer, 1,
                     border_radius=max(1, int(gw * 0.22)))
    inner_w = max(2, int(rect.w * 0.40))
    inner_h = max(2, int(rect.h * 0.58))
    inner = pygame.Rect(rect.centerx - inner_w // 2,
                        rect.bottom - inner_h - max(1, rect.h // 12),
                        inner_w, inner_h)
    pygame.draw.rect(screen, mix(p.warm, p.warm_hi, 0.30), inner,
                     border_radius=max(1, int(inner_w * 0.35)))


def draw_tips(screen, scene: CastleScene, p: Palette, ox: float) -> None:
    for i, (x, y, brightness) in enumerate(scene.tips):
        x += ox
        d = 2 if i == 0 else 1
        pygame.draw.polygon(screen,
                            scale(mix(p.edge, p.glow, 0.5),
                                  0.55 + brightness),
                            [(x, y - d), (x + d, y), (x, y + d),
                             (x - d, y)])
    for i in range(min(3, len(scene.tips))):
        x, y, _ = scene.tips[i]
        x += ox
        arm = 6
        pygame.draw.line(screen, scale(p.glow, 0.28),
                         (x - arm, y), (x + arm, y), 1)
        pygame.draw.line(screen, scale(p.glow, 0.28),
                         (x, y - arm), (x, y + arm), 1)


def draw_mid_layer(surface, layout: SceneLayout, p: Palette,
                   scene: CastleScene, seed: int, ox: float) -> None:
    draw_plateau(surface, layout, p, ox, seed)
    draw_ground_shadows(surface, layout, scene, ox)
    draw_wall(surface, layout, p, ox)
    for tower in scene.towers:
        draw_tower(surface, tower, p, ox)
    draw_fins(surface, layout, p, ox)
    draw_plinth(surface, layout, p, ox)
    for tower in scene.gatehouses:
        draw_tower(surface, tower, p, ox)
    draw_gate(surface, layout, p, ox)
    draw_tips(surface, scene, p, ox)


# ------------------------------------------------------------------ far/near

def draw_far_layer(surface, layout: SceneLayout, p: Palette,
                   scene: CastleScene, ox: float) -> None:
    cw, _ = surface.get_size()
    for points in (layout.ridge, layout.ridge_right):
        pts = _pad_poly([(x + ox, y) for x, y in points], 0, cw)
        pygame.draw.polygon(surface, p.ridge, pts)
        pygame.draw.aalines(surface, scale(p.ridge_snow, 0.40), True, pts)
        for (x, y), (nx, ny) in zip(points[1:], points[2:]):
            if ny > y:
                continue
            pygame.draw.aaline(surface, scale(p.ridge_snow, 0.55),
                               (x + ox, y), (nx + ox, ny))
    for tower in scene.far_towers:
        draw_tower(surface, tower, p, ox)
        # One distant warm light; static, so it stays in the cached layer.
        w = max(1.0, 2.2 * layout.scale)
        x, y = tower.window_anchor(0.28, 0.5)
        pygame.draw.rect(surface, p.warm_dim,
                         (int(x + ox - w * 0.5), int(y - w),
                          max(1, int(w)), max(1, int(w * 2))))
        pygame.draw.circle(surface, p.warm,
                           (int(x + ox), int(y)), 1)


def draw_near_layer(surface, layout: SceneLayout, p: Palette,
                    seed: int, ox: float) -> None:
    cw, ch = surface.get_size()
    lip = _extend_x([(x + ox, y) for x, y in layout.lip], 0, cw)
    face = lip + [(cw, ch), (0, ch)]
    pygame.draw.polygon(surface, p.cliff_face, face)
    y0 = min(y for _, y in lip)
    for y in range(int(y0), ch):
        t = (y - y0) / max(1.0, ch - y0)
        col = mix(p.cliff_top, p.cliff_bottom, smoothstep(t))
        pygame.draw.line(surface, col, (0, y), (cw, y))

    rng = random.Random(seed ^ 0x1CE)
    for _ in range(42 if not layout.portrait else 96):
        x = rng.uniform(0, cw)
        top = rng.uniform(y0 + 2, y0 + (ch - y0) * 0.30)
        length = rng.uniform((ch - y0) * 0.18, (ch - y0) * 0.55)
        drift = rng.uniform(-34, 34)
        col = mix(p.cliff_face, p.cliff_edge, rng.uniform(0.10, 0.40))
        pygame.draw.aaline(surface, col, (x, top),
                           (x + drift, min(ch, top + length)))
    for _ in range(18 if not layout.portrait else 52):
        y = rng.uniform(y0 + 8, ch - 10)
        x = rng.uniform(0, cw)
        w = rng.uniform(14, 96)
        col = mix(p.cliff_face, p.snow_dim, rng.uniform(0.12, 0.34))
        pygame.draw.line(surface, col, (x, y),
                         (x + w, y + rng.uniform(-2, 2)), 1)
    for _ in range(3 if not layout.portrait else 7):
        x = rng.uniform(cw * 0.05, cw * 0.95)
        top = rng.uniform(y0 + 6, y0 + 24)
        bottom = rng.uniform(top + 30, ch - 12)
        col = mix(p.cliff_face, p.accent_dim, rng.uniform(0.12, 0.26))
        pygame.draw.line(surface, col, (x, top),
                         (x + rng.uniform(-3, 3), bottom), 1)

    pygame.draw.aalines(surface, mix(p.snow_dim, p.snow, 0.35), False, lip)
    for (xa, ya), (xb, yb) in zip(lip, lip[1:]):
        pygame.draw.line(surface, mix(p.bg_top, p.face_base, 0.3),
                         (xa, ya + 2), (xb, yb + 2), 1)

    # Near rock shoulders.
    for points in (layout.mass_left, layout.mass_right):
        pts = [(x + ox, y) for x, y in points]
        pygame.draw.polygon(surface, mix(p.bg_top, p.cliff_face, 0.55), pts)
        pygame.draw.aalines(surface, scale(p.cliff_edge, 0.58), False, pts)
        top = pts[:-2]
        pygame.draw.aalines(surface, scale(p.snow_dim, 0.58), False, top)
        for (x, y), (nx, ny) in zip(points[:-2], points[1:-1]):
            if ny < y:
                pygame.draw.aaline(surface, scale(p.snow, 0.42),
                                   (x + ox, y), (nx + ox, ny))

    for points in layout.buttresses:
        raw = [(x + ox, y) for x, y in points]
        pts = _pad_poly(raw, 0, cw)
        pygame.draw.polygon(surface, mix(p.bg_top, p.cliff_face, 0.65), pts)
        top = raw[:-2] if len(raw) > 4 else raw
        pygame.draw.aalines(surface, scale(p.snow_dim, 0.58), False, top)
        for (x, y), (nx, ny) in zip(points[:-2], points[1:-1]):
            if ny < y:
                pygame.draw.aaline(surface, scale(p.snow, 0.58),
                                   (x + ox, y), (nx + ox, ny))
        for _ in range(8):
            x = rng.uniform(points[0][0], points[len(points) // 2][0])
            y = rng.uniform(points[0][1], ch - 20)
            pygame.draw.aaline(surface, scale(p.cliff_edge, 0.34),
                               (x + ox, y),
                               (x + ox + rng.uniform(-30, 30),
                                min(ch, y + rng.uniform(30, 120))))


# ------------------------------------------------------------------ dynamics

def draw_windows(screen, scene: CastleScene, p: Palette, time_s: float,
                 ox: float, glow: pygame.Surface, window_lights: bool,
                 flicker: float, glow_cache=None) -> None:
    if not window_lights:
        return
    flicker = max(0.0, min(1.0, float(flicker)))
    for win in scene.windows:
        if flicker <= 0.01:
            b = win.base * win.dim * 0.75
        else:
            osc = (0.5 + 0.5 * math.sin(
                TAU * time_s / win.period + win.phase)) ** 1.6
            live = win.base * win.dim * (0.18 + 0.82 * osc)
            steady = win.base * win.dim * 0.70
            b = steady + (live - steady) * flicker
        if b < 0.08:
            continue
        x = win.x + ox
        y = win.y
        w = max(1.0, win.w)
        h = w * 2.7
        if b > 0.24:
            g = int(max(4.0, w * 3.2))
            sprite = (glow_cache.get(glow, g) if glow_cache is not None
                      else pygame.transform.smoothscale(glow, (g, g)))
            screen.blit(sprite, (int(x - g * 0.5), int(y - h * 0.5 - g * 0.15)),
                        special_flags=pygame.BLEND_RGB_ADD)
        col = mix(p.warm_dim, p.warm_hi, 0.35 + 0.65 * b)
        rect = pygame.Rect(int(x - w * 0.5), int(y - h * 0.5),
                           max(1, int(w)), max(1, int(h)))
        pygame.draw.rect(screen, col, rect,
                         border_radius=max(1, int(w * 0.4)))
        if b > 0.7:
            inner = rect.inflate(-max(1, rect.w // 2), -max(1, rect.h // 3))
            pygame.draw.rect(screen, mix(p.warm, p.warm_hi, 0.55), inner,
                             border_radius=max(1, rect.w // 3))


def draw_gate_glow(screen, layout: SceneLayout, p: Palette, ox: float,
                   glow: pygame.Surface, glow_cache=None) -> None:
    gx, gy, gw, gh = layout.castle["gate"]
    gx += ox
    pool_size = (max(4, int(gw * 1.8)), max(4, int(gw * 0.9)))
    pool = (glow_cache.get(glow, pool_size) if glow_cache is not None
            else pygame.transform.smoothscale(glow, pool_size))
    screen.blit(pool, (int(gx - gw * 1.2),
                       int(gy - 2 - gw * 0.6)),
                special_flags=pygame.BLEND_RGB_ADD)
    sprite_size = max(4, int(gw * 1.0))
    sprite = (glow_cache.get(glow, sprite_size) if glow_cache is not None
              else pygame.transform.smoothscale(glow, (sprite_size,
                                                       sprite_size)))
    screen.blit(sprite, (int(gx - gw * 0.5),
                         int(gy - gh * 0.5 - gw * 0.5)),
                special_flags=pygame.BLEND_RGB_ADD)


def draw_shards(screen, scene: CastleScene, p: Palette, time_s: float,
                ox: float, glow: pygame.Surface, glow_cache=None) -> None:
    for shard in scene.shards:
        x, y, angle = shard.at(time_s)
        x += ox
        a = math.radians(angle)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        tip = (x + ux * shard.length * 0.5, y + uy * shard.length * 0.5)
        tail = (x - ux * shard.length * 0.5, y - uy * shard.length * 0.5)
        mid = (x + ux * shard.length * 0.05, y + uy * shard.length * 0.05)
        left = (mid[0] + px * shard.width * 0.5,
                mid[1] + py * shard.width * 0.5)
        right = (mid[0] - px * shard.width * 0.5,
                 mid[1] - py * shard.width * 0.5)
        poly = [tip, left, tail, right]
        fill = mix(p.face_base, p.glow, 0.20 * shard.bright)
        pygame.draw.polygon(screen, fill, poly)
        pygame.draw.aalines(
            screen, scale(mix(p.edge, p.glow, 0.55), shard.bright),
            True, poly)
        pygame.draw.aaline(screen, scale(p.face_lit, shard.bright * 0.85),
                           tail, tip)
        pygame.draw.aaline(screen, scale(p.glow, shard.bright * 0.35),
                           left, ((tail[0] + tip[0]) * 0.5,
                                  (tail[1] + tip[1]) * 0.5))
        g = max(2, int(shard.width * 1.8))
        sprite = (glow_cache.get(glow, g) if glow_cache is not None
                  else pygame.transform.smoothscale(glow, (g, g)))
        screen.blit(sprite, (int(tip[0] - g * 0.5), int(tip[1] - g * 0.5)),
                    special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(screen, scale(p.glow, shard.bright),
                           (int(tip[0]), int(tip[1])), 1)
