"""Phase 2 world: themed sectors, placed props, bridges, damage, and LODs.

A sector is 384 units (eight 48-unit chunks).  It is planned atomically:
surface heights, trench module variants, bridges, wall guns, and every surface
prop are decided before a single chunk is built.  Chunks are then generated
ahead of the ship and evicted behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable

from .assets import (build_beacon, build_block_building, build_bridge,
                     build_bunker, build_command_dome, build_comm_tower,
                     build_conduit, build_crater, build_defense_tower,
                     build_dish_array, build_far, build_power_node,
                     build_wall_gun)
from .meshes import (Mesh, build_dome, build_plate, build_plate_mid,
                     build_trench_module, build_turret, transform_mesh)

CHUNK = 48.0
MODULE = 12.0
SECTOR = 384.0
RIM_WIDTH = 4.0
PLATE_WIDTH = 36.0
PLATE_START = 18.0
PLATE_COLUMNS = 8
PLATE_ROWS = 8

THEMES = ("dome_field", "gun_battery", "industrial", "damaged", "command", "mixed")

# Footprint radii in world units, used by placement only.
FOOTPRINTS = {
    "turret": 5.2,
    "dome_small": 7.5,
    "command_dome": 17.0,
    "defense_tower": 7.0,
    "comm_tower": 7.0,
    "block_building": 10.5,
    "bunker": 11.0,
    "power_node": 6.5,
    "dish_array": 8.0,
    "conduit": 10.0,
    "beacon": 2.2,
    "crater": 10.0,
    "wall_gun": 4.0,
}

THEME_WEIGHTS = {
    "dome_field": {"dome_small": 34, "block_building": 15, "comm_tower": 14,
                   "power_node": 10, "dish_array": 10, "turret": 8,
                   "beacon": 9},
    "gun_battery": {"turret": 26, "defense_tower": 22, "bunker": 20,
                    "power_node": 12, "block_building": 10, "crater": 10},
    "industrial": {"block_building": 26, "power_node": 18, "dish_array": 14,
                   "comm_tower": 12, "conduit": 14, "beacon": 8,
                   "turret": 8},
    "damaged": {"crater": 30, "bunker": 20, "turret": 14,
                "block_building": 14, "power_node": 10, "conduit": 12},
    "command": {"command_dome": 1, "comm_tower": 20, "block_building": 22,
                "dish_array": 16, "power_node": 10, "turret": 12,
                "beacon": 10},
    "mixed": {"dome_small": 18, "block_building": 18, "defense_tower": 12,
              "comm_tower": 10, "bunker": 10, "power_node": 10,
              "dish_array": 8, "turret": 8, "crater": 8, "beacon": 8},
}


def stable_seed(*parts: int) -> int:
    h = 0x9E3779B97F4A7C15
    for value in parts:
        h ^= (int(value) + 0x9E3779B97F4A7C15 + (h << 6) + (h >> 2)) & 0xFFFFFFFFFFFFFFFF
        h = (h * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        h ^= h >> 27
    return h & 0x7FFFFFFF


def _hash01(ix: int, iz: int, seed: int) -> float:
    return (stable_seed(ix, iz, seed) & 0xFFFFFF) / float(0x1000000)


def _smooth(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def terrain_noise(x: float, z: float, seed: int, scale: float = 82.0) -> float:
    gx, gz = x / scale, z / scale
    ix, iz = math.floor(gx), math.floor(gz)
    fx, fz = _smooth(gx - ix), _smooth(gz - iz)
    a = _hash01(ix, iz, seed)
    b = _hash01(ix + 1, iz, seed)
    c = _hash01(ix, iz + 1, seed)
    d = _hash01(ix + 1, iz + 1, seed)
    return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz


@dataclass(frozen=True)
class AssetLods:
    near: Mesh
    mid: Mesh
    far: Mesh
    radius: float
    height: float


@dataclass(frozen=True)
class PropSpec:
    kind: str
    x: float
    y: float
    z: float
    yaw: float
    scale: float
    variant: int
    footprint: float
    radius: float
    height: float


@dataclass(frozen=True)
class SectorPlan:
    index: int
    z0: float
    z1: float
    theme: str
    activity: float
    heights: tuple[int, ...]       # row, side, col flattened
    props: tuple[PropSpec, ...]
    bridges: tuple[float, ...]
    wall_guns: tuple[tuple[float, float], ...]  # (side, z)
    trench_variants: tuple[int, ...]



@dataclass
class Mount:
    kind: str
    lods: AssetLods
    x: float
    y: float
    z: float
    base_yaw: float
    scale: float
    radius: float
    height: float
    muzzle_local: tuple[tuple[float, float, float], ...] = ()
    yaw: float = 0.0
    cooldown: float = 0.0

    @property
    def near(self):
        return self.lods.near

    @property
    def mid(self):
        return self.lods.mid

    @property
    def far(self):
        return self.lods.far

    def center(self) -> tuple[float, float, float]:
        return (self.x, self.y + self.height * 0.45, self.z)

    def muzzle_world(self):
        from .meshes import transform_point
        return [transform_point(p, (self.x, self.y, self.z), self.yaw,
                                self.scale) for p in self.muzzle_local]


@dataclass(frozen=True)
class WorldObject:
    kind: str
    near: Mesh
    mid: Mesh
    far: Mesh
    center: tuple[float, float, float]
    radius: float


@dataclass(frozen=True)
class Chunk:
    index: int
    z0: float
    objects: tuple[WorldObject, ...]
    plate_heights: tuple[float, ...]
    theme: str = ""
    mounts: tuple[Mount, ...] = ()


class TrenchWorld:
    def __init__(self, seed: int, width: float, depth: float,
                 density: float = 0.6, far_side: float = 1.0,
                 sector_length: float = SECTOR):
        self.seed = int(seed) & 0x7FFFFFFF
        self.far_side = 1.0 if far_side >= 0 else -1.0
        self.width = float(width)
        self.depth = float(depth)
        self.density = max(0.0, min(1.0, float(density)))
        self.sector_length = max(192.0, min(768.0,
                                            round(float(sector_length) / CHUNK) * CHUNK))
        self.chunks_per_sector = int(round(self.sector_length / CHUNK))
        self.chunks: dict[int, Chunk] = {}
        self.sectors: dict[int, SectorPlan] = {}
        self._assets = self._build_assets()
        self._trench_cache: dict[int, tuple[Mesh, Mesh, Mesh]] = {}
        for variant in range(5):
            near, far = build_trench_module(self.width, self.depth, variant)
            self._trench_cache[variant] = (near, near.lod(1), far)

    # ------------------------------------------------------------------
    # Asset prototypes
    # ------------------------------------------------------------------

    def _register(self, kind: str, near: Mesh, far: Mesh | None = None,
                  mid: Mesh | None = None) -> None:
        if far is None:
            far = build_far(kind, self.width, self.depth)
        if mid is None:
            mid = near.lod(2) if len(near.edges) > 90 else near.lod(1)
        center, radius = near.bounds()
        height = max((p[1] for p in near.verts), default=0.0)
        self._assets.setdefault(kind, []).append(
            AssetLods(near, mid, far, radius, height))

    def _build_assets(self) -> dict[str, list[AssetLods]]:
        self._assets: dict[str, list[AssetLods]] = {}
        turret_far = build_far("turret")
        self._register("turret", build_turret(), turret_far, turret_far)
        dome_far = build_far("dome_small")
        self._register("dome_small", build_dome(6.0), dome_far, dome_far)
        self._register("command_dome", build_command_dome(13.0),
                       build_far("command_dome"))
        self._register("defense_tower", build_defense_tower(),
                       build_far("defense_tower"))
        self._register("comm_tower", build_comm_tower(),
                       build_far("comm_tower"))
        for variant in range(3):
            mesh = build_block_building(variant)
            self._register("block_building", mesh,
                           build_far("block_building"))
        self._register("bunker", build_bunker(), build_far("bunker"))
        self._register("power_node", build_power_node(),
                       build_far("power_node"))
        self._register("dish_array", build_dish_array(),
                       build_far("dish_array"))
        self._register("conduit", build_conduit(24.0), build_far("conduit"))
        self._register("beacon", build_beacon(), build_far("beacon"))
        self._register("crater", build_crater(10.0), build_far("crater"))
        self._register("wall_gun", build_wall_gun(), build_far("wall_gun"))
        bridge = build_bridge(self.width, self.depth)
        self._register("bridge", bridge,
                       build_far("bridge", self.width, self.depth))
        return self._assets

    # ------------------------------------------------------------------
    # Streaming API
    # ------------------------------------------------------------------

    def sector_plan(self, index: int) -> SectorPlan:
        plan = self.sectors.get(index)
        if plan is None:
            plan = self._build_plan(index)
            self.sectors[index] = plan
        return plan

    def ensure(self, ship_z: float, max_new: int | None = None) -> int:
        ahead = ship_z + 950.0
        behind = ship_z - 140.0
        first = int(math.floor(behind / self.sector_length))
        last = int(math.floor(ahead / self.sector_length))
        missing = [i for i in range(first, last + 1)
                   if i not in self.sectors]
        if max_new is not None:
            missing = missing[:max(0, max_new)]
        for index in missing:
            self.sector_plan(index)
        for index in range(first, last + 1):
            plan = self.sectors.get(index)
            if plan is not None:
                self._build_sector_chunks(plan)
        cutoff = int(math.floor((ship_z - 220.0) / self.sector_length))
        for index in [i for i in self.sectors if i < cutoff]:
            del self.sectors[index]
            for chunk_index in range(index * self.chunks_per_sector,
                                     (index + 1) * self.chunks_per_sector):
                self.chunks.pop(chunk_index, None)
        return len(missing)

    def active_objects(self) -> Iterable[WorldObject]:
        for chunk in self.chunks.values():
            yield from chunk.objects

    def active_mounts(self) -> Iterable[Mount]:
        for chunk in self.chunks.values():
            yield from chunk.mounts

    def object_count(self) -> int:
        return sum(len(c.objects) for c in self.chunks.values())

    def signature(self, index: int) -> tuple:
        chunk = self.chunks.get(index)
        if chunk is None:
            return ()
        return (round(chunk.z0, 3), chunk.theme,
                tuple((o.kind, round(o.center[0], 2), round(o.center[1], 2),
                       round(o.center[2], 2), len(o.near.edges))
                      for o in chunk.objects))

    # ------------------------------------------------------------------
    # Sector planning
    # ------------------------------------------------------------------

    def _plate_height(self, x: float, z: float) -> int:
        if abs(x) < 55.0:
            return 0
        n = terrain_noise(x, z, self.seed, 92.0)
        h = int(min(3.0, max(0.0, n * 4.2)))
        if abs(x) < 78.0:
            h = min(h, 1)
        return h

    def _height_index(self, row: int, side: int, col: int) -> int:
        return (row * 2 + side) * PLATE_COLUMNS + col

    def _build_plan(self, index: int) -> SectorPlan:
        z0 = index * self.sector_length
        z1 = z0 + self.sector_length
        rng = random.Random(stable_seed(self.seed, index, 0x5EC7))
        # A six-sector rotation guarantees every family appears in a long run,
        # while mixed sectors and prop weights still vary the composition.
        cycle = index % 6
        theme = THEMES[cycle]
        activity = rng.uniform(0.4, 1.4)

        heights = [0] * (PLATE_ROWS * 2 * PLATE_COLUMNS)
        for row in range(PLATE_ROWS):
            for side in (0, 1):
                sign = -1.0 if side == 0 else 1.0
                for col in range(PLATE_COLUMNS):
                    xc = sign * (PLATE_START + (col + 0.5) * PLATE_WIDTH)
                    zc = z0 + (row + 0.5) * CHUNK
                    heights[self._height_index(row, side, col)] = \
                        self._plate_height(xc, zc)

        trench_variants = []
        damage_theme = theme == "damaged"
        for module in range(int(self.sector_length // MODULE)):
            if damage_theme and rng.random() < 0.38:
                variant = rng.choice((3, 4))
            elif rng.random() < 0.06:
                variant = rng.choice((3, 4))
            else:
                variant = rng.choices((0, 1, 2), weights=(5, 3, 3))[0]
            trench_variants.append(variant)

        bridges: list[float] = []
        if index % 2 == 0 or rng.random() < 0.35:
            bridges.append(round(z0 + rng.uniform(90.0,
                                                  self.sector_length - 90.0), 3))

        wall_guns: list[tuple[float, float]] = []
        for z in (z0 + 75.0, z0 + self.sector_length * 0.62):
            if rng.random() < 0.72:
                wall_guns.append((self.far_side, round(z, 3)))

        props: list[PropSpec] = []
        occupied: list[tuple[float, float, float]] = []

        def height_here(x: float, z: float) -> float:
            rr = max(0, min(PLATE_ROWS - 1,
                            int((z - z0) // CHUNK)))
            ss = 0 if x < 0 else 1
            cc = max(0, min(PLATE_COLUMNS - 1,
                            int((abs(x) - PLATE_START) // PLATE_WIDTH)))
            return self.depth + heights[self._height_index(rr, ss, cc)]

        def blocked(x: float, z: float, foot: float) -> bool:
            if abs(x) - foot * 0.5 < self.width * 0.5 + RIM_WIDTH + 1.0:
                return True
            if z - foot < z0 + 16.0 or z + foot > z1 - 16.0:
                return True
            if abs(x) + foot > PLATE_START + PLATE_COLUMNS * PLATE_WIDTH - 2.0:
                return True
            for bz in bridges:
                if abs(z - bz) < 12.0 + foot:
                    return True
            for ox, oz, of in occupied:
                if math.hypot(x - ox, z - oz) < (foot + of) * 0.92:
                    return True
            return False

        def add(kind: str, x: float, z: float, *, yaw: float = 0.0,
                scale: float = 1.0, variant: int = 0,
                rim: bool = False) -> bool:
            foot = FOOTPRINTS[kind] * scale
            if blocked(x, z, foot):
                return False
            y = self.depth if rim else height_here(x, z)
            assets = self._assets[kind]
            asset = assets[variant % len(assets)]
            props.append(PropSpec(kind, x, y, z, yaw, scale, variant,
                                  foot, asset.radius * scale,
                                  asset.height * scale))
            occupied.append((x, z, foot))
            return True

        def force_place(kind: str, *, scale: float = 1.0,
                        variant: int = 0,
                        yaw_override: float | None = None) -> bool:
            """Deterministic fallback scan used for theme-family guarantees."""
            for z in range(int(z0 + 34), int(z1 - 34), 16):
                for side in (self.far_side, -self.far_side):
                    for col in range(PLATE_COLUMNS):
                        x = side * (PLATE_START + (col + 0.5) * PLATE_WIDTH)
                        yaw = (rng.uniform(0.0, 360.0)
                               if yaw_override is None else yaw_override)
                        if add(kind, x, z, yaw=yaw, scale=scale,
                               variant=variant):
                            return True
            return False

        def find_place(kind: str, *, side_bias: float | None = None,
                       z_center: float | None = None, z_spread: float = 160.0,
                       scale: float = 1.0, variant: int = 0,
                       yaw_override: float | None = None,
                       attempts: int = 90) -> bool:
            foot = FOOTPRINTS[kind] * scale
            for _ in range(attempts):
                side = side_bias if side_bias is not None else (
                    self.far_side if rng.random() < 0.68 else -self.far_side)
                # Bias toward the two inner plate columns so the visible
                # kiosk field stays populated; outer columns still appear.
                col = rng.choices(range(PLATE_COLUMNS),
                                  weights=(18, 16, 14, 12, 10, 8, 6, 4))[0]
                x = side * (PLATE_START + (col + 0.5) * PLATE_WIDTH)
                if z_center is None:
                    z = rng.uniform(z0 + 20.0, z1 - 20.0)
                else:
                    z = max(z0 + 20.0, min(z1 - 20.0,
                                           rng.uniform(z_center - z_spread,
                                                       z_center + z_spread)))
                yaw = (rng.uniform(0.0, 360.0) if yaw_override is None
                       else yaw_override)
                if add(kind, x, z, yaw=yaw, scale=scale, variant=variant):
                    return True
            return False

        # Far-bank rim turrets: the near-bank equivalent sits behind the near
        # wall from the boom camera, so Phase 2 keeps these on the far rim.
        for z in range(int(z0 + 60), int(z1 - 50), 112):
            zz = z + rng.uniform(-18.0, 18.0)
            x = self.far_side * (self.width * 0.5 + 9.0)
            if not blocked(x, zz, FOOTPRINTS["turret"]):
                add("turret", x, zz, yaw=0.0 if self.far_side > 0 else 180.0,
                    scale=1.45 + rng.uniform(-0.1, 0.1), rim=True)

        # One landmark most sectors.
        landmark_cycle = {
            "command": "command_dome",
            "gun_battery": "defense_tower",
            "industrial": "dish_array",
            "dome_field": "dome_small",
            "damaged": "bunker",
            "mixed": "comm_tower",
        }
        landmark = landmark_cycle[theme]
        find_place(landmark, z_center=z0 + self.sector_length * 0.5,
                   z_spread=110.0, attempts=140,
                   scale=1.0 if landmark == "command_dome" else 0.88,
                   variant=rng.randrange(3) if landmark == "block_building" else 0)

        weights = THEME_WEIGHTS[theme]
        kinds = list(weights)
        kind_weights = [weights[k] for k in kinds]
        count = int(round((4.0 + 6.0 * self.density) *
                          (1.15 if theme == "industrial" else 1.0)))
        for _ in range(count):
            kind = rng.choices(kinds, weights=kind_weights)[0]
            if kind == "conduit":
                scale = 1.0
            elif kind == "dome_small":
                scale = rng.uniform(0.82, 1.18)
            elif kind == "block_building":
                scale = rng.uniform(0.85, 1.12)
            elif kind in ("defense_tower", "comm_tower"):
                scale = rng.uniform(0.76, 0.90)
            else:
                scale = rng.uniform(0.92, 1.08)
            variant = 0
            if kind == "block_building":
                variant = rng.randrange(3)
            yaw_override = None
            if kind == "conduit":
                yaw_override = rng.choice((0.0, 90.0))
            find_place(kind, scale=scale, variant=variant,
                       yaw_override=yaw_override, attempts=70)

        # Guarantee at least one prop in every 48-unit chunk.  Random
        # placement alone leaves occasional empty stretches, which read as
        # holes in the kiosk flythrough.
        chunk_count = int(round(self.sector_length / CHUNK))
        for chunk_i in range(chunk_count):
            zc = z0 + (chunk_i + 0.5) * CHUNK
            if any(abs(pr.z - zc) < CHUNK * 0.5 for pr in props):
                continue
            fill_kind = ("block_building" if theme in ("industrial", "command")
                         else "dome_small" if theme in ("dome_field", "mixed")
                         else "bunker" if theme == "damaged"
                         else "defense_tower")
            if not find_place(fill_kind, z_center=zc, z_spread=10.0,
                              scale=0.85 if fill_kind in ("defense_tower",
                                                          "comm_tower") else 1.0,
                              attempts=50,
                              variant=rng.randrange(3)
                              if fill_kind == "block_building" else 0):
                find_place("beacon", z_center=zc, z_spread=10.0,
                           attempts=30)

        # Theme-family guarantees: a long run must contain every catalogue
        # family, even when rejection sampling is unlucky.
        if theme == "industrial" and not any(pr.kind == "conduit"
                                             for pr in props):
            force_place("conduit", yaw_override=0.0)
        if theme == "command" and not any(pr.kind == "command_dome"
                                          for pr in props):
            force_place("command_dome")
        if theme == "dome_field" and not any(pr.kind == "dome_small"
                                             for pr in props):
            force_place("dome_small")
        if theme == "gun_battery" and not any(pr.kind == "defense_tower"
                                              for pr in props):
            force_place("defense_tower")
        if theme == "damaged" and not any(pr.kind == "bunker"
                                          for pr in props):
            force_place("bunker")

        # Craters are surface decals, placed after buildings and kept clear of
        # everything occupied.
        for _ in range(1 + int(round(2.0 * self.density))):
            find_place("crater", scale=rng.uniform(0.85, 1.35),
                       variant=0, attempts=60)
        # At least one beacon per sector, even in sparse themes.
        find_place("beacon", scale=1.0, variant=0, attempts=40)

        return SectorPlan(index, z0, z1, theme, activity, tuple(heights),
                          tuple(props), tuple(bridges), tuple(wall_guns),
                          tuple(trench_variants))

    # ------------------------------------------------------------------
    # Chunk generation
    # ------------------------------------------------------------------

    def _build_sector_chunks(self, plan: SectorPlan) -> None:
        start = int(round(plan.z0 / CHUNK))
        for offset in range(self.chunks_per_sector):
            index = start + offset
            if index not in self.chunks:
                self.chunks[index] = self._build_chunk(plan, index)

    def _plate_height_at(self, plan: SectorPlan, row: int, side: int,
                         col: int) -> int:
        return plan.heights[self._height_index(row, side, col)]

    def _build_chunk(self, plan: SectorPlan, index: int) -> Chunk:
        z0 = index * CHUNK
        row = index - int(round(plan.z0 / CHUNK))
        objects: list[WorldObject] = []
        plate_heights: list[float] = []

        for k in range(4):
            variant = plan.trench_variants[row * 4 + k]
            near, mid, far = self._trench_cache[variant]
            zz = z0 + k * MODULE
            objects.append(WorldObject(
                "trench",
                transform_mesh(near, (0.0, 0.0, zz)),
                transform_mesh(mid, (0.0, 0.0, zz)),
                transform_mesh(far, (0.0, 0.0, zz)),
                (0.0, self.depth * 0.45, zz + MODULE * 0.5),
                math.hypot(self.width * 0.5 + RIM_WIDTH, self.depth) * 1.15))

        for side_idx, side in ((0, -1.0), (1, 1.0)):
            heights = [self._plate_height_at(plan, row, side_idx, col)
                       for col in range(PLATE_COLUMNS)]
            plate_heights.extend(float(h) for h in heights)
            col = 0
            while col < PLATE_COLUMNS:
                h = heights[col]
                start = col
                col += 1
                while col < PLATE_COLUMNS and heights[col] == h:
                    col += 1
                xa = side * (PLATE_START + start * PLATE_WIDTH)
                xb = side * (PLATE_START + col * PLATE_WIDTH)
                x0, x1 = min(xa, xb), max(xa, xb)
                xc = (x0 + x1) * 0.5
                zc = z0 + CHUNK * 0.5
                top = self.depth + h
                variant = stable_seed(self.seed, index, side_idx, start) % 97
                near = build_plate(x0, x1, z0, z0 + CHUNK, top,
                                   detail=True, variant=variant)
                mid = build_plate_mid(x0, x1, z0, z0 + CHUNK, top,
                                      variant=variant)
                far = build_plate(x0, x1, z0, z0 + CHUNK, top,
                                  detail=False)
                objects.append(WorldObject(
                    "plate", near, mid, far,
                    (xc, top - 0.4, zc),
                    math.hypot((x1 - x0) * 0.5, CHUNK * 0.5) + 2.0))

        for bz in plan.bridges:
            if z0 <= bz < z0 + CHUNK:
                assets = self._assets["bridge"][0]
                objects.append(WorldObject(
                    "bridge",
                    transform_mesh(assets.near, (0.0, 0.0, bz)),
                    transform_mesh(assets.mid, (0.0, 0.0, bz)),
                    transform_mesh(assets.far, (0.0, 0.0, bz)),
                    (0.0, self.depth + 24.0, bz),
                    self.width * 0.5 + RIM_WIDTH + 3.0))

        mounts: list[Mount] = []
        for side, gz in plan.wall_guns:
            if z0 <= gz < z0 + CHUNK:
                asset = self._assets["wall_gun"][0]
                x = side * (self.width * 0.5 - 0.3)
                y = self.depth * 0.55
                yaw = 0.0 if side > 0 else 180.0
                mounts.append(Mount(
                    "wall_gun", asset, x, y, gz, yaw, 1.0,
                    asset.radius, asset.height,
                    ((-4.8, 1.7, -0.42), (-4.8, 1.7, 0.42)),
                    yaw=yaw))

        for prop in plan.props:
            if not (z0 <= prop.z < z0 + CHUNK):
                continue
            assets = self._assets[prop.kind]
            asset = assets[prop.variant % len(assets)]
            if prop.kind == "turret":
                yaw = 0.0 if prop.x >= 0 else 180.0
                mounts.append(Mount(
                    "turret", asset, prop.x, prop.y, prop.z, yaw,
                    prop.scale, prop.radius, prop.height,
                    ((-6.2, 2.62, -0.48), (-6.2, 2.62, 0.48)),
                    yaw=yaw))
            elif prop.kind == "dish_array":
                mounts.append(Mount(
                    "dish_array", asset, prop.x, prop.y, prop.z,
                    prop.yaw, prop.scale, prop.radius, prop.height,
                    (), yaw=prop.yaw))
            else:
                near = transform_mesh(asset.near, (prop.x, prop.y, prop.z),
                                      prop.yaw, prop.scale)
                mid = transform_mesh(asset.mid, (prop.x, prop.y, prop.z),
                                     prop.yaw, prop.scale)
                far = transform_mesh(asset.far, (prop.x, prop.y, prop.z),
                                     prop.yaw, prop.scale)
                center = (prop.x, prop.y + prop.height * 0.45, prop.z)
                objects.append(WorldObject(prop.kind, near, mid, far,
                                           center, prop.radius))

        return Chunk(index, z0, tuple(objects), tuple(plate_heights),
                     plan.theme, tuple(mounts))
