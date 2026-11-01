"""The cyberspace renderer.

Draws the world straight onto the controller's surface, and a smaller copy of
the same lines onto a low-resolution bloom buffer which is scaled up and added
back.  There is no depth buffer: neon wireframes read as transparent, and depth
is carried by distance fade plus the near/far line weight.
"""
from __future__ import annotations

import math
import random

import pygame

from .camera import CameraRig
from .matrix import Matrix
from .palette import Palette, mix, scale

#: Per-quality budgets.  ``edge_budget`` is a hard ceiling on projected world
#: segments, which is what keeps a Pi's frame time bounded.  ``glow_div`` is the
#: bloom downscale factor: bigger is cheaper and blurrier.
QUALITY = {
    "low": {"edges": 2200, "glow_div": 7, "draw_scale": 0.82, "detail": 95.0,
            "traffic": 120, "constructs": 22, "specks": False},
    "medium": {"edges": 3600, "glow_div": 5, "draw_scale": 1.0, "detail": 170.0,
               "traffic": 200, "constructs": 36, "specks": True},
    "high": {"edges": 5400, "glow_div": 4, "draw_scale": 1.2, "detail": 260.0,
             "traffic": 300, "constructs": 52, "specks": True},
}

_NEAR = 1.1
_MAX_COORD = 80000.0


class Budget:
    __slots__ = ("left",)

    def __init__(self, total: int):
        self.left = int(total)


class CyberspaceRenderer:
    def __init__(self, size: tuple[int, int], palette: Palette,
                 glow_strength: float = 0.8, scanline_alpha: int = 12,
                 vignette: float = 0.35, quality: str = "medium",
                 seed: int = 1, draw_distance: float = 420.0,
                 show_traffic: bool = True, hud_bands: bool = True,
                 crisp_lines: bool = True):
        self.palette = palette
        self.glow_strength = max(0.0, min(1.0, float(glow_strength)))
        self.scanline_alpha = max(0, min(80, int(scanline_alpha)))
        self.vignette = max(0.0, min(1.0, float(vignette)))
        self.quality = quality if quality in QUALITY else "medium"
        self.seed = int(seed) & 0x7FFFFFFF
        self.draw_distance = max(120.0, float(draw_distance))
        self.show_traffic = bool(show_traffic)
        self.hud_bands = bool(hud_bands)
        self.crisp_lines = bool(crisp_lines)
        self.edge_cap = QUALITY[self.quality]["edges"]
        self.last_segments = 0
        self.last_objects = 0
        self.last_constructs = 0
        self.last_labels: list[dict] = []
        self.last_landmarks = 0
        self.nearest_landmark: tuple[str, str, float] | None = None
        self.nearest_landmarks: list[tuple[str, str, float]] = []
        self.nearest_landmark_object = None
        self.ice_distance: float | None = None
        self._core: list[tuple] = []
        self._hero_core: list[tuple] = []
        self.aa_distance = min(240.0, self.draw_distance * 0.40)
        self.sw = self.sh = 0
        self.background = None
        self.finish = None
        self.bloom = None
        self.bloom_up = None
        self.specks: list[tuple[float, float, float, float]] = []
        self._specks_built = False
        self._resize(size)

    # ---------------------------------------------------------------- surfaces

    def _resize(self, size: tuple[int, int]) -> None:
        self.sw, self.sh = max(1, int(size[0])), max(1, int(size[1]))
        q = QUALITY[self.quality]
        self.edge_cap = q["edges"]
        self._build_background()
        self._build_finish()
        self._build_glow()
        if not self._specks_built:
            self._build_specks()
            self._specks_built = True

    def resize(self, size: tuple[int, int]) -> None:
        if int(size[0]) != self.sw or int(size[1]) != self.sh:
            self._resize(size)

    def set_quality(self, quality: str) -> None:
        # The background, finish map and specks do not depend on the quality
        # budget, and rebuilding them mid-flight caused a visible hitch when
        # auto stepped down.  Only the bloom resolution changes.
        quality = quality if quality in QUALITY else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        self.edge_cap = QUALITY[quality]["edges"]
        self._build_glow()

    def _build_background(self) -> None:
        p = self.palette
        surf = pygame.Surface((self.sw, self.sh)).convert()
        # A vertical gradient with a soft haze band around the lower-middle:
        # the matrix has no sky, but a lit depth does.
        horizon = 0.56
        haze_strength = 0.34
        for y in range(self.sh):
            t = (y / max(1, self.sh - 1)) ** 1.55
            base = mix(p.bg_top, p.bg_bottom, t)
            band = math.exp(-(((y / max(1, self.sh - 1)) - horizon) /
                              max(0.01, 0.16)) ** 2)
            band = band * haze_strength * (0.35 + 0.65 * math.sin(
                math.pi * min(1.0, y / max(1, self.sh - 1))))
            color = mix(base, p.haze, band)
            pygame.draw.line(surf, color, (0, y), (self.sw, y))
        self.background = surf

    def _build_finish(self) -> None:
        """A single multiply map for the vignette and scanlines.

        Two full-screen SRCALPHA blits were the most expensive thing in the
        frame (about 20 ms at 1080x1920 on the reference machine).  Baking both
        effects into one opaque map and multiplying once costs about 4 ms, and
        it also darkens the world lines rather than only the background.  The
        HUD is drawn afterwards, so it stays crisp.
        """
        if self.vignette <= 0.0 and self.scanline_alpha <= 0:
            self.finish = None
            return
        qw = max(2, self.sw // 4)
        qh = max(2, self.sh // 4)
        small = pygame.Surface((qw, qh)).convert()
        if self.vignette <= 0.0:
            small.fill((255, 255, 255))
        else:
            cx, cy = (qw - 1) * 0.5, (qh - 1) * 0.5
            maxd = math.hypot(cx, cy)
            for y in range(qh):
                for x in range(qw):
                    r = math.hypot(x - cx, y - cy) / maxd
                    dark = self.vignette * (max(0.0, r - 0.28) / 0.72) ** 1.8
                    k = int(255 * max(0.08, 1.0 - dark))
                    small.set_at((x, y), (k, k, k))
        finish = pygame.transform.smoothscale(small, (self.sw, self.sh))
        if self.scanline_alpha > 0:
            k = int(255 * (1.0 - self.scanline_alpha / 255.0))
            for y in range(0, self.sh, 3):
                pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
        # Darken the top and bottom bands here, while we already have a
        # full-screen multiply map: this is what keeps the HUD legible over a
        # bright wireframe without a second full-screen blit or a haze panel.
        if self.hud_bands:
            top_h = max(58, int(self.sh * 0.085))
            for y in range(top_h):
                t = (y / max(1, top_h - 1)) ** 2
                k = int(40 + 215 * t)
                pygame.draw.line(finish, (k, k, k), (0, y), (self.sw, y), 1)
            # Landscape HUD text occupies a shallower strip than portrait, so
            # the dark band is a little shorter there.
            ratio = 0.22
            bot_h = max(110, int(self.sh * ratio))
            for y in range(bot_h):
                k = int(255 - 240 * (y / max(1, bot_h - 1)))
                pygame.draw.line(finish, (k, k, k), (0, self.sh - bot_h + y),
                                 (self.sw, self.sh - bot_h + y), 1)
        self.finish = finish

    def _build_glow(self) -> None:
        self.bloom = None
        self.bloom_mid = None
        self.bloom_up = None
        if self.glow_strength <= 0.0:
            return
        div = QUALITY[self.quality]["glow_div"]
        self.bloom = pygame.Surface(
            (max(1, self.sw // div), max(1, self.sh // div))).convert()
        self.bloom.fill((0, 0, 0))
        self.bloom_mid = pygame.Surface(
            (max(1, self.sw // 2), max(1, self.sh // 2))).convert()
        self.bloom_up = pygame.Surface((self.sw, self.sh)).convert()

    def _build_specks(self) -> None:
        rng = random.Random(self.seed ^ 0xD474)
        count = 150
        self.specks = [(rng.random(), rng.random() * 0.72,
                        rng.uniform(0.0, math.tau), rng.uniform(0.20, 0.70))
                       for _ in range(count)]

    # ---------------------------------------------------------------- frame

    def render(self, screen, camera: CameraRig, matrix: Matrix,
               route, time_s: float = 0.0, landmarks=()) -> None:
        p = self.palette
        q = QUALITY[self.quality]
        radius = self.draw_distance * q["draw_scale"]
        self.last_segments = 0
        self.last_objects = 0
        self.last_constructs = 0
        self.last_landmarks = 0
        self.nearest_landmark = None
        self.nearest_landmarks = []
        self.nearest_landmark_object = None
        self.ice_distance = None
        self._core = []
        self._hero_core = []

        if self.background is not None:
            screen.blit(self.background, (0, 0))
        else:
            screen.fill(p.bg_bottom)

        if q["specks"]:
            self._draw_specks(screen, time_s, camera)

        if self.bloom is not None:
            self.bloom.fill((0, 0, 0))

        budget = Budget(self.edge_cap)
        drawn = [0]

        def draw_edges(edges, fog_distance: float, intensity: float = 1.0,
                       width_near: float = 0.0, hero: bool = False) -> None:
            if budget.left <= 0:
                return
            drawn[0] += self._draw_edges(
                camera, edges, budget, fog_distance, intensity, width_near,
                hero=hero)

        # The ground lattice comes first: it establishes the vanishing points.
        draw_edges(matrix.floor_grid(camera, radius), radius, 0.9)
        draw_edges(matrix.roads(camera, radius), radius, 1.2)
        draw_edges(matrix.nodes(camera, radius), radius, 1.15)
        draw_edges(matrix.shafts(camera, radius), radius, 1.0)
        if route.axis == 2 or route.axis_changes == 0:
            draw_edges(matrix.gate_rings(camera, radius), radius, 1.1)

        # Fixed landmarks first: they are the recognizable geography of this
        # matrix, so they get the edge budget before the procedural skyline.
        landmark_labels = []
        seen_landmarks = []
        for lm in landmarks:
            if not camera.sphere_visible(lm.center, lm.radius):
                continue
            dx = lm.center[0] - camera.pos[0]
            dy = lm.center[1] - camera.pos[1]
            dz = lm.center[2] - camera.pos[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist > self.draw_distance * 1.35 + lm.radius:
                continue
            edges = lm.edges_at(time_s)
            if not edges:
                continue
            draw_edges(edges, radius, getattr(lm, "glow", 1.25),
                       width_near=280.0, hero=True)
            self.last_landmarks += 1
            label = getattr(lm, "label", lm.name)
            seen_landmarks.append((dist, label, lm.name, lm))
            if label:
                landmark_labels.append((dist, label, lm.label_pos,
                                        lm.label_color(), True))
        seen_landmarks.sort(key=lambda item: item[0])
        self.nearest_landmarks = [(label, name, dist)
                                  for dist, label, name, _lm in seen_landmarks[:3]]
        # The inset and feed ask "which landmark is closest", not "which one
        # happens to be in the frustum" — a huge form just behind the camera
        # is still the nearest one while it passes.
        if landmarks:
            nearest_total = None
            for lm in landmarks:
                dx = lm.center[0] - camera.pos[0]
                dy = lm.center[1] - camera.pos[1]
                dz = lm.center[2] - camera.pos[2]
                d = math.sqrt(dx * dx + dy * dy + dz * dz)
                if nearest_total is None or d < nearest_total[0]:
                    nearest_total = (d, lm)
            lm = nearest_total[1]
            self.nearest_landmark_object = lm
            self.nearest_landmark = (getattr(lm, "label", lm.name), lm.name,
                                     nearest_total[0])
        else:
            self.nearest_landmark_object = None
            self.nearest_landmark = None

        # Towers, nearest first, then the floating constructs.  The renderer
        # stops at the budget; the mode's auto-quality lowers that budget when
        # the frame time climbs.
        buildings = matrix.buildings(camera, radius)
        # Higher lattice levels cost more per tower, so shrink the near-LOD
        # radius a little; the closest buildings still get the dense mesh.
        detail = q["detail"] * (1.0 - 0.07 * (matrix.detail_level - 1))
        detail = max(70.0, detail)
        beacon_candidates = []
        labels = []
        for dist, cell in buildings:
            if budget.left <= 10:
                break
            if not camera.sphere_visible(cell.center, cell.radius):
                continue
            if matrix.detail_level > 1 and dist < detail:
                edges = matrix.detail_edges(cell, matrix.detail_level)
            else:
                edges = cell.edges_for(dist, detail)
            draw_edges(edges, radius, 1.18, width_near=95.0)
            self.last_objects += 1
            if cell.beacon is not None and dist < radius * 0.78:
                beacon_candidates.append((dist, cell))
            if cell.label and dist < radius * 0.8:
                labels.append((dist, cell.label, cell.label_pos, cell_center_color(cell, p)))

        constructs = matrix.constructs(camera, radius * 0.95)
        ice_dist = None
        drawn_constructs = 0
        for dist, c in constructs:
            if drawn_constructs >= q["constructs"] or budget.left <= 6:
                break
            if not camera.sphere_visible(c.center, c.radius):
                continue
            drawn_constructs += 1
            edges = matrix.construct_edges(c, time_s)
            color = c.color
            draw_edges(edges, radius, 1.28, width_near=120.0)
            self.last_constructs += 1
            if c.is_ice:
                if ice_dist is None or dist < ice_dist:
                    ice_dist = dist
            if c.label and dist < radius * 0.75:
                labels.append((dist, c.label, c.center, color))

        if self.show_traffic:
            draw_edges(matrix.traffic(camera, time_s,
                                      min(radius, matrix.cell * 4.2),
                                      q["traffic"]), radius, 1.45,
                       width_near=80.0)

        beacons = self._beacon_points(camera, beacon_candidates, time_s)
        if self.bloom is not None:
            self._bloom_beacons(beacons)

        labels.sort(key=lambda item: item[0])
        landmark_labels.sort(key=lambda item: item[0])
        self.last_labels = [
            {"text": text, "pos": pos, "color": color, "distance": dist,
             "landmark": True}
            for (dist, text, pos, color, _mark) in landmark_labels[:6]
        ] + [
            {"text": text, "pos": pos, "color": color, "distance": dist,
             "landmark": False}
            for (dist, text, pos, color) in labels[:6]
        ]
        self.ice_distance = ice_dist
        self.last_segments = drawn[0]

        if self.bloom is not None and self.bloom_up is not None:
            if self.quality == "high":
                # At high quality, pay for a direct smooth upscale: the halo
                # is part of the look, and a two-stage scale leaves 2 px steps.
                pygame.transform.smoothscale(self.bloom, (self.sw, self.sh),
                                             self.bloom_up)
            else:
                # Two-stage upscale: smooth the low-res bloom to half size,
                # then a cheap nearest-neighbour scale to full.
                pygame.transform.smoothscale(
                    self.bloom, self.bloom_mid.get_size(), self.bloom_mid)
                pygame.transform.scale(self.bloom_mid, (self.sw, self.sh),
                                       self.bloom_up)
            screen.blit(self.bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        # The crisp core goes ON TOP of the glow.  Drawing it before the bloom
        # let the additive pass wash the edges; on top, the line stays sharp
        # and the bloom reads as a halo behind it.
        self._draw_core(screen)
        self._draw_screen_beacons(screen, beacons)
        if self.finish is not None:
            screen.blit(self.finish, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # ---------------------------------------------------------------- pieces

    def _draw_specks(self, screen, time_s: float, camera: CameraRig) -> None:
        p = self.palette
        for fx, fy, phase, brightness in self.specks:
            tw = 0.55 + 0.45 * math.sin(time_s * 0.8 + phase)
            a = brightness * tw * 0.55
            color = scale(p.hud, a)
            if color == (0, 0, 0):
                continue
            # A little parallax from the camera heading keeps the specks from
            # looking like a decal on the lens.
            x = int((fx + camera.yaw * 0.02) % 1.0 * self.sw)
            y = int(fy * self.sh)
            screen.set_at((max(0, min(self.sw - 1, x)),
                           max(0, min(self.sh - 1, y))), color)

    def _beacon_points(self, camera, candidates, time_s: float) -> list[tuple]:
        if not candidates:
            return []
        p = self.palette
        points = []
        for dist, cell in candidates[:70]:
            pos = camera.project(cell.beacon)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if not (-8 < x < self.sw + 8 and -8 < y < self.sh + 8):
                continue
            blink = 0.5 + 0.5 * math.sin(time_s * 2.3 + cell.beacon_phase)
            fade = max(0.0, 1.0 - dist / max(1.0, self.draw_distance))
            a = (0.25 + 0.75 * blink) * fade
            if a <= 0.03:
                continue
            color = scale(mix(p.hud, p.warn, 0.12), a)
            points.append((x, y, color, a, dist))
        return points

    def _bloom_beacons(self, points) -> None:
        if self.bloom is None:
            return
        inv_w = self.bloom.get_width() / self.sw
        inv_h = self.bloom.get_height() / self.sh
        bw, bh = self.bloom.get_width(), self.bloom.get_height()
        for x, y, color, a, _dist in points:
            if a <= 0.12:
                continue
            bx = max(0, min(bw - 1, int(x * inv_w)))
            by = max(0, min(bh - 1, int(y * inv_h)))
            self.bloom.set_at((bx, by), scale(color, 0.9))

    def _draw_screen_beacons(self, screen, points) -> None:
        for x, y, color, _a, dist in points:
            screen.set_at((x, y), color)
            if dist < self.draw_distance * 0.34:
                arm = 2 if dist < 80 else 1
                pygame.draw.line(screen, scale(color, 0.7),
                                 (x - arm, y), (x + arm, y), 1)
                pygame.draw.line(screen, scale(color, 0.7),
                                 (x, y - arm), (x, y + arm), 1)

    # ---------------------------------------------------------------- lines

    def _draw_edges(self, camera: CameraRig, edges, budget: Budget,
                    fog_distance: float, intensity: float,
                    width_near: float, hero: bool = False) -> int:
        if not edges:
            return 0
        p = self.palette
        cx, cy, focal = camera.cx, camera.cy, camera.focal
        sw, sh = self.sw, self.sh
        margin = 4
        inv_w = self.bloom.get_width() / sw if self.bloom is not None else 0.0
        inv_h = self.bloom.get_height() / sh if self.bloom is not None else 0.0
        near_width = self.quality != "low"
        glow_on = self.bloom is not None and self.glow_strength > 0.0
        glow_scale = 1.20 * self.glow_strength
        fog_distance = max(1.0, fog_distance)
        draw_line = pygame.draw.line
        core = self._hero_core if hero else self._core
        count = 0

        # Local bindings matter here: this loop is the frame's hot path.
        right, up, fwd = camera._right, camera._up, camera._fwd
        px, py, pz = camera.pos

        for e in edges:
            if budget.left <= 0:
                break
            x1, y1, z1, x2, y2, z2, r, g, b = e
            dx1 = x1 - px
            dy1 = y1 - py
            dz1 = z1 - pz
            dx2 = x2 - px
            dy2 = y2 - py
            dz2 = z2 - pz
            vx1 = dx1 * right[0] + dy1 * right[1] + dz1 * right[2]
            vy1 = dx1 * up[0] + dy1 * up[1] + dz1 * up[2]
            vz1 = dx1 * fwd[0] + dy1 * fwd[1] + dz1 * fwd[2]
            vx2 = dx2 * right[0] + dy2 * right[1] + dz2 * right[2]
            vy2 = dx2 * up[0] + dy2 * up[1] + dz2 * up[2]
            vz2 = dx2 * fwd[0] + dy2 * fwd[1] + dz2 * fwd[2]
            if vz1 <= _NEAR and vz2 <= _NEAR:
                continue
            if vz1 < _NEAR:
                t = (_NEAR - vz1) / (vz2 - vz1)
                vx1 += (vx2 - vx1) * t
                vy1 += (vy2 - vy1) * t
                vz1 = _NEAR
            elif vz2 < _NEAR:
                t = (_NEAR - vz2) / (vz1 - vz2)
                vx2 += (vx1 - vx2) * t
                vy2 += (vy1 - vy2) * t
                vz2 = _NEAR

            sx1 = cx + focal * vx1 / vz1
            sy1 = cy - focal * vy1 / vz1
            sx2 = cx + focal * vx2 / vz2
            sy2 = cy - focal * vy2 / vz2

            # Cheap whole-segment reject: both ends off the same side.
            if ((sx1 < -margin and sx2 < -margin) or
                    (sx1 > sw + margin and sx2 > sw + margin) or
                    (sy1 < -margin and sy2 < -margin) or
                    (sy1 > sh + margin and sy2 > sh + margin)):
                continue
            if -_MAX_COORD > sx1 or sx1 > _MAX_COORD:
                sx1 = -_MAX_COORD if sx1 < 0 else _MAX_COORD
            if -_MAX_COORD > sx2 or sx2 > _MAX_COORD:
                sx2 = -_MAX_COORD if sx2 < 0 else _MAX_COORD
            if -_MAX_COORD > sy1 or sy1 > _MAX_COORD:
                sy1 = -_MAX_COORD if sy1 < 0 else _MAX_COORD
            if -_MAX_COORD > sy2 or sy2 > _MAX_COORD:
                sy2 = -_MAX_COORD if sy2 < 0 else _MAX_COORD

            mx = (x1 + x2) * 0.5 - px
            my = (y1 + y2) * 0.5 - py
            mz = (z1 + z2) * 0.5 - pz
            dist = math.sqrt(mx * mx + my * my + mz * mz)
            fade = 1.0 - dist / fog_distance
            if fade <= 0.0:
                continue
            fade = fade ** 1.15
            bright = fade * intensity
            if bright <= 0.012:
                continue
            cr = int(r * bright)
            cg = int(g * bright)
            cb = int(b * bright)
            if cr > 255:
                cr = 255
            if cg > 255:
                cg = 255
            if cb > 255:
                cb = 255
            color = (cr, cg, cb)
            px1, py1 = int(sx1), int(sy1)
            px2, py2 = int(sx2), int(sy2)
            width = 1
            if hero:
                width = 2
            elif near_width and dist < width_near and (abs(px2 - px1) +
                                                       abs(py2 - py1) > 6):
                width = 2
                color = (min(255, int(cr * 1.18)), min(255, int(cg * 1.18)),
                         min(255, int(cb * 1.18)))
            # Anti-aliasing spreads a one-pixel line across two pixels, so
            # lift the ink slightly here; the core stays crisp and the bloom
            # behind it supplies the neon weight.
            hr = cr * 13 // 10
            hg = cg * 13 // 10
            hb = cb * 13 // 10
            core.append((px1, py1, px2, py2,
                         (hr if hr < 255 else 255,
                          hg if hg < 255 else 255,
                          hb if hb < 255 else 255), width, dist))
            if glow_on and bright > 0.035:
                # Bloom distant lines a little harder than their core: that is
                # what makes the far city read as luminous rather than as a
                # diagram.  A power below 1 lifts the dim end of the ramp.
                grow = bright ** 0.55
                gr = int(r * glow_scale * grow)
                gg = int(g * glow_scale * grow)
                gb = int(b * glow_scale * grow)
                if gr > 255:
                    gr = 255
                if gg > 255:
                    gg = 255
                if gb > 255:
                    gb = 255
                if gr or gg or gb:
                    draw_line(self.bloom,
                              (gr, gg, gb),
                              (int(px1 * inv_w), int(py1 * inv_h)),
                              (int(px2 * inv_w), int(py2 * inv_h)),
                              2 if hero else 1)
            count += 1
            budget.left -= 1
        return count


    def _draw_core(self, screen) -> None:
        if not self._core and not self._hero_core:
            return
        draw_line = pygame.draw.line
        if self.crisp_lines:
            # Anti-alias the near lines, where a staircase would be obvious.
            # Far lines are faded by the fog and already covered by bloom, so
            # the cheaper aliased raster is indistinguishable there and keeps
            # the 1080p frame affordable.
            aaline = pygame.draw.aaline
            aa_near = self.aa_distance
            for x1, y1, x2, y2, color, _width, dist in self._core:
                # A short dash gains nothing from anti-aliasing and aaline is
                # the expensive call, so only long near lines pay for it.
                long_enough = (abs(x2 - x1) + abs(y2 - y1)) >= 5
                if dist <= aa_near and long_enough:
                    aaline(screen, color, (x1, y1), (x2, y2))
                else:
                    draw_line(screen, color, (x1, y1), (x2, y2), 1)
            # Hero lines are landmarks. They are deliberately drawn on top of
            # the ordinary core and with a wider, dim underlay so they survive
            # even when glow_strength is 0 and there is no bloom to reveal them.
            for x1, y1, x2, y2, color, width, dist in self._hero_core:
                long_enough = (abs(x2 - x1) + abs(y2 - y1)) >= 5
                if dist <= aa_near and long_enough:
                    if width > 1:
                        draw_line(screen, (color[0] * 5 // 12,
                                           color[1] * 5 // 12,
                                           color[2] * 5 // 12),
                                  (x1, y1), (x2, y2), 2)
                    aaline(screen, color, (x1, y1), (x2, y2))
                else:
                    draw_line(screen, color, (x1, y1), (x2, y2), width)
            return
        for x1, y1, x2, y2, color, width, _dist in (
                self._core + self._hero_core):
            draw_line(screen, color, (x1, y1), (x2, y2), width)


def cell_center_color(cell, palette: Palette):
    """A label colour for a tower: its brightest edge colour would be better,
    but a stable accent per label reads cleanly at 12 px."""
    if cell.label:
        h = sum(ord(ch) for ch in cell.label)
        return palette.hud if h % 3 else mix(palette.hud, palette.node, 0.5)
    return palette.hud
