"""Vector renderer for the Trench Run mode (Phases 1–4).

Draws opaque dark panel fills followed by depth-coloured lines, then a single
screen-space additive bloom pass.  There is no depth buffer: objects are
sorted far-to-near, and each object's faces are drawn before its edges.  That
is enough for non-intersecting surface plates, trench modules, and props.
"""
from __future__ import annotations

import math
import random

import pygame

from .palette import DepthRamp, Palette, make_palette, mix, scale
from .projection import Projector
from .meshes import transform_mesh


QUALITY_EDGE_CAPS = {"low": 1700, "medium": 2100, "high": 3500}


class VectorRenderer:
    def __init__(self, size: tuple[int, int], palette_name: str = "vector_blue",
                 depth_fade: float = 0.75, glow_strength: float = 0.55,
                 fill_mode: str = "panel", vignette: float = 0.30,
                 scanline_alpha: int = 0, quality: str = "auto",
                 show_stars: bool = True, seed: int = 1,
                 phosphor_trail: float = 0.10):
        self.palette: Palette = make_palette(palette_name)
        self.ramp = DepthRamp(self.palette, depth_fade)
        self.glow_strength = max(0.0, min(1.0, float(glow_strength)))
        self.fill_mode = fill_mode if fill_mode in ("xray", "panel", "solid") else "panel"
        self.phosphor_trail = max(0.0, min(0.5, float(phosphor_trail)))
        self.vignette = max(0.0, min(1.0, float(vignette)))
        self.scanline_alpha = max(0, min(80, int(scanline_alpha)))
        self.quality = quality if quality in ("low", "medium", "high") else "medium"
        self.show_stars = bool(show_stars)
        self.seed = int(seed) & 0x7FFFFFFF
        self.sw = self.sh = 0
        self.vignette_surf = None
        self.scanlines = None
        self.stars: list[tuple[float, float, int, float]] = []
        self.last_objects = 0
        self.last_segments = 0
        self.last_faces = 0
        self.last_world_edges = 0
        self.edge_cap = QUALITY_EDGE_CAPS[self.quality]
        self._resize(size)

    # ------------------------------------------------------------------
    # Screen-dependent caches
    # ------------------------------------------------------------------

    def _resize(self, size: tuple[int, int]) -> None:
        self.sw, self.sh = int(size[0]), int(size[1])
        if self.sw <= 0 or self.sh <= 0:
            raise ValueError("screen size must be positive")
        div = {"low": 8, "medium": 5, "high": 3}[self.quality]
        self.bloom_div = div
        self.bloom_small = None
        self.bloom_up = None
        self.trail_small = None
        if self.glow_strength > 0.0:
            self.bloom_small = pygame.Surface(
                (max(1, self.sw // div), max(1, self.sh // div))).convert()
            self.bloom_up = pygame.Surface((self.sw, self.sh)).convert()
            if self.phosphor_trail > 0.0:
                self.trail_small = pygame.Surface(
                    self.bloom_small.get_size()).convert()
                self.trail_small.fill((0, 0, 0))
        self._build_stars()
        self._build_vignette()
        self._build_scanlines()

    def resize(self, size: tuple[int, int]) -> None:
        if int(size[0]) != self.sw or int(size[1]) != self.sh:
            self._resize(size)

    def set_quality(self, quality: str) -> None:
        """Switch quality budgets without rebuilding the mode.

        Adaptive auto uses this at most a few times per session.  Rebuilding
        the glow/trail surfaces on a change is cheaper than carrying all three
        resolutions permanently.
        """
        quality = quality if quality in ("low", "medium", "high") else "medium"
        if quality == self.quality:
            return
        self.quality = quality
        # Keep the published budget in step with the new quality immediately: render() recomputes
        # `cap` anyway, but stats() reads edge_cap between frames and used to report the old one.
        self.edge_cap = QUALITY_EDGE_CAPS[quality]
        self._resize((self.sw, self.sh))

    def _build_stars(self) -> None:
        rng = random.Random(self.seed ^ 0x57A2)
        self.stars = [(rng.random(), rng.random(),
                       rng.choice((1, 1, 1, 2, 2)), rng.uniform(0.35, 0.95))
                      for _ in range(120)]

    def _build_vignette(self) -> None:
        self.vignette_surf = None
        if self.vignette <= 0.0:
            return
        w = max(2, self.sw // 4)
        h = max(2, self.sh // 4)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
        maxd = math.hypot(cx, cy)
        for y in range(h):
            for x in range(w):
                r = math.hypot(x - cx, y - cy) / maxd
                a = int(255 * self.vignette * (max(0.0, r - 0.30) / 0.70) ** 1.7)
                if a > 0:
                    surf.set_at((x, y), (0, 0, 0, a))
        self.vignette_surf = pygame.transform.smoothscale(surf, (self.sw, self.sh))

    def _build_scanlines(self) -> None:
        self.scanlines = None
        if self.scanline_alpha <= 0:
            return
        s = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        for y in range(0, self.sh, 3):
            pygame.draw.line(s, (0, 0, 0, self.scanline_alpha),
                             (0, y), (self.sw, y))
        self.scanlines = s

    # ------------------------------------------------------------------
    # Frame
    # ------------------------------------------------------------------

    def render(self, screen: pygame.Surface, projector: Projector,
               world, ship, time_s: float = 0.0, action=None) -> None:
        haze = mix(self.palette.bg, self.palette.ink_mid, 0.10)
        screen.fill(haze)
        self._draw_stars(screen, time_s)

        far, mid, near = {
            "low": (340.0, 220.0, 110.0),
            "medium": (390.0, 225.0, 115.0),
            "high": (600.0, 420.0, 250.0),
        }[self.quality]

        drawables = []
        for obj in world.active_objects():
            if not projector.visible(obj.center, obj.radius):
                continue
            depth = projector.view(obj.center)[2]
            if depth < -obj.radius or depth > far:
                continue
            if depth <= near:
                mesh = obj.near
            elif depth <= mid:
                mesh = obj.mid
            else:
                mesh = obj.far
            drawables.append([depth, obj, mesh])

        for mount in world.active_mounts():
            center = mount.center()
            if not projector.visible(center, mount.radius):
                continue
            depth = projector.view(center)[2]
            if depth < -mount.radius or depth > far:
                continue
            if depth <= near:
                lod = mount.near
            elif depth <= mid:
                lod = mount.mid
            else:
                lod = mount.far
            mesh = transform_mesh(lod, (mount.x, mount.y, mount.z),
                                  mount.yaw, mount.scale)
            drawables.append([depth, mount, mesh])

        drawables.sort(key=lambda item: item[0], reverse=True)

        # Enforce a hard edge budget by dropping far prop detail first, then
        # the farthest non-structural props.  The trench, plates, and bridges
        # are never removed.
        cap = QUALITY_EDGE_CAPS[self.quality]
        total = sum(len(item[2].edges) for item in drawables)
        if total > cap:
            for item in sorted(drawables, key=lambda it: it[0], reverse=True):
                if item[1].kind in ("trench", "plate", "bridge"):
                    continue
                far_mesh = item[1].far
                if item[2] is not far_mesh:
                    total += len(far_mesh.edges) - len(item[2].edges)
                    item[2] = far_mesh
        if total > cap:
            removed = set()
            for orig_index, (depth, obj, mesh) in sorted(
                    enumerate(drawables), key=lambda pair: pair[1][0],
                    reverse=True):
                if total <= cap:
                    break
                if obj.kind in ("trench", "plate", "bridge"):
                    continue
                total -= len(mesh.edges)
                removed.add(orig_index)
            drawables = [item for i, item in enumerate(drawables)
                         if i not in removed]

        self.last_objects = len(drawables)
        self.last_segments = 0
        self.last_faces = 0
        self.last_world_edges = sum(len(item[2].edges) for item in drawables)
        self.edge_cap = cap

        for depth, obj, mesh in drawables:
            self._draw_mesh(screen, projector, mesh, depth, ship=False)

        ship_mesh = ship.mesh()
        self._draw_mesh(screen, projector, ship_mesh,
                        projector.view(ship.pose())[2], ship=True)
        self._draw_engines(screen, projector, ship, time_s)
        if action is not None:
            action.draw_overlay(screen, projector, self.palette, self.ramp)

        self._composite_glow(screen)
        if self.vignette_surf is not None:
            screen.blit(self.vignette_surf, (0, 0))
        if self.scanlines is not None:
            screen.blit(self.scanlines, (0, 0))

    def _draw_stars(self, screen: pygame.Surface, time_s: float) -> None:
        if not self.show_stars:
            return
        for fx, fy, size, bright in self.stars:
            x = int(fx * self.sw)
            y = int(fy * self.sh)
            # Very slow twinkle; no per-star allocation.
            tw = 1.0 + 0.20 * math.sin(time_s * 0.7 + fx * 31.0 + fy * 17.0)
            c = scale(self.palette.star, max(0.08, min(1.0, bright * tw)))
            if size == 1:
                screen.set_at((x, y), c)
            else:
                pygame.draw.line(screen, c, (x - 1, y), (x + 1, y))
                pygame.draw.line(screen, c, (x, y - 1), (x, y + 1))

    def _draw_mesh(self, screen: pygame.Surface, projector: Projector,
                   mesh, depth: float, ship: bool) -> None:
        if not mesh.edges and not mesh.faces:
            return

        views = [projector.view(v) for v in mesh.verts]

        if (self.fill_mode == "solid" and mesh.faces and not ship
                and depth <= 260.0):
            roles = {}
            face_edges = set()
            for edge in mesh.edges:
                roles[(min(edge.a, edge.b), max(edge.a, edge.b))] = edge.role
            faces = []
            for face in mesh.faces:
                vp = [views[i] for i in face.verts]
                poly = projector.project_view_polygon(vp)
                if poly is None or len(poly) < 3:
                    continue
                z = sum(p[2] for p in vp) / len(vp)
                faces.append((z, poly, face))
                count = len(face.verts)
                for i in range(count):
                    a, b = face.verts[i], face.verts[(i + 1) % count]
                    face_edges.add((min(a, b), max(a, b)))
            faces.sort(key=lambda item: item[0], reverse=True)
            for z, poly, face in faces:
                pygame.draw.polygon(screen, self.ramp.panel(z), poly)
                self.last_faces += 1
                count = len(face.verts)
                for i in range(count):
                    a, b = face.verts[i], face.verts[(i + 1) % count]
                    p = projector.project_view_segment(views[a], views[b])
                    if p is None:
                        continue
                    (x1, y1), (x2, y2), zz = p
                    role = roles.get((min(a, b), max(a, b)), "secondary")
                    pygame.draw.line(screen, self.ramp.role(role, zz),
                                     (x1, y1), (x2, y2), 1)
                    self.last_segments += 1
            # Edges that are not part of a face (antennas, beacons) still show.
            for edge in mesh.edges:
                key = (min(edge.a, edge.b), max(edge.a, edge.b))
                if key in face_edges:
                    continue
                p = projector.project_view_segment(views[edge.a], views[edge.b])
                if p is None:
                    continue
                (x1, y1), (x2, y2), zz = p
                pygame.draw.line(screen, self.ramp.role(edge.role, zz),
                                 (x1, y1), (x2, y2), 1)
                self.last_segments += 1
            return

        if (self.fill_mode == "panel" and mesh.faces
                and (ship or depth <= 150.0)):
            faces = []
            for face in mesh.faces:
                vp = [views[i] for i in face.verts]
                poly = projector.project_view_polygon(vp)
                if poly is None or len(poly) < 3:
                    continue
                z = sum(p[2] for p in vp) / len(vp)
                faces.append((z, poly))
            faces.sort(key=lambda item: item[0], reverse=True)
            for z, poly in faces:
                pygame.draw.polygon(screen, self.ramp.panel(z), poly)
                self.last_faces += 1

        for edge in mesh.edges:
            p = projector.project_view_segment(views[edge.a], views[edge.b])
            if p is None:
                continue
            (x1, y1), (x2, y2), z = p
            if ship:
                color = self._ship_color(edge.role, z)
            else:
                color = self.ramp.role(edge.role, z)
            pygame.draw.line(screen, color, (x1, y1), (x2, y2), 1)
            self.last_segments += 1

    def _ship_color(self, role: str, z: float):
        p = self.palette
        if role == "rebel":
            return p.rebel
        if role == "emissive":
            return p.accent
        if role == "detail":
            return mix(p.ship, p.bg, 0.72)
        if role == "secondary":
            return mix(p.ship, p.bg, 0.50)
        return p.ship

    def _draw_engines(self, screen: pygame.Surface, projector: Projector,
                      ship, time_s: float) -> None:
        p = self.palette
        for i, point in enumerate(ship.engine_points()):
            pp = projector.project_point(point)
            if pp is None:
                continue
            x, y, _ = pp
            pulse = 0.75 + 0.25 * math.sin(time_s * 7.0 + i * 1.7)
            core = scale(p.accent, 0.85 * pulse)
            x, y = int(x), int(y)
            pygame.draw.line(screen, core, (x - 1, y), (x + 1, y))
            pygame.draw.line(screen, core, (x, y - 1), (x, y + 1))

    def _composite_glow(self, screen: pygame.Surface) -> None:
        """Single screen-space bloom.

        Downscaling the finished frame and adding it back is much cheaper than
        drawing every bright edge twice, and it blooms only what is actually
        visible after panel fills.
        """
        if self.bloom_small is None or self.glow_strength <= 0.0:
            return
        pygame.transform.smoothscale(screen, self.bloom_small.get_size(),
                                     self.bloom_small)
        if self.trail_small is not None:
            fade = int(255 * max(0.0, 1.0 - 3.0 * self.phosphor_trail))
            self.trail_small.fill((fade, fade, fade),
                                  special_flags=pygame.BLEND_RGB_MULT)
            self.trail_small.blit(self.bloom_small, (0, 0),
                                  special_flags=pygame.BLEND_RGB_ADD)
            self.bloom_small.blit(self.trail_small, (0, 0),
                                  special_flags=pygame.BLEND_RGB_ADD)
        k = int(45 + 110 * self.glow_strength)
        self.bloom_small.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
        pygame.transform.smoothscale(self.bloom_small,
                                     (self.sw, self.sh), self.bloom_up)
        screen.blit(self.bloom_up, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
