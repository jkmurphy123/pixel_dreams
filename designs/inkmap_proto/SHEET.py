#!/usr/bin/env python3
"""Prototype v3: adds the piece the artist's ORDER implies but the earlier
prototypes lacked - TERRAIN ZONING and non-overlapping placement.

The video's sequence is not a bag of stamps: the artist picks where the range
goes, tapers it into hills, puts forest masses elsewhere, then a desert, and
fills the rests with grass. Without zoning every feature lands on the same
ground and the sheet becomes scribble (measured: prototype 2/4 did exactly
that). Here a low-frequency elevation + moisture noise field divides the land
into mountain / hill / forest / desert / plain, and one global occupancy grid
stops two features being drawn on top of each other.

Reuses every drawing primitive from ink_proto2.
"""
import math
import os
import random
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import PRIMITIVES as P  # noqa: E402

VW, VH, W, H = P.VW, P.VH, P.W, P.H
VW, VH = 1080, 1920
PEN = P.PEN
INK = P.INK
GW, GH = P.GW, P.GH
CELL_X, CELL_Y = P.CELL_X, P.CELL_Y

ZW, ZH = GW // 3, GH // 3          # terrain zone grid
ZCELL_X, ZCELL_Y = W / ZW, H / ZH

WATER, MOUNTAIN, HILL, FOREST, DESERT, PLAIN = range(6)
ZNAME = {WATER: "water", MOUNTAIN: "mountain", HILL: "hill",
         FOREST: "forest", DESERT: "desert", PLAIN: "plain"}


def ms(t0):
    return (time.perf_counter() - t0) * 1000.0


def value_noise(rng, w, h, base_cell, octaves=4, gain=0.5):
    """Tileable-free value noise, 0..1. Pure Python; ~120 ms at 96x170x4."""
    acc = [0.0] * (w * h)
    amp, cells, total = 1.0, float(base_cell), 0.0
    for _ in range(octaves):
        gw = max(2, int(w / cells) + 2)
        gh = max(2, int(h / cells) + 2)
        lat = [rng.random() for _ in range(gw * gh)]
        inv = 1.0 / cells
        for y in range(h):
            fy = y * inv
            y0 = int(fy)
            ty = fy - y0
            ty = ty * ty * (3 - 2 * ty)
            r0 = y0 * gw
            r1 = r0 + gw
            base = y * w
            for x in range(w):
                fx = x * inv
                x0 = int(fx)
                tx = fx - x0
                tx = tx * tx * (3 - 2 * tx)
                v = ((lat[r0 + x0] * (1 - tx) + lat[r0 + x0 + 1] * tx) * (1 - ty) +
                     (lat[r1 + x0] * (1 - tx) + lat[r1 + x0 + 1] * tx) * ty)
                acc[base + x] += amp * v
        total += amp
        amp *= gain
        cells = max(2.0, cells / 2)
    return [a / total for a in acc]


class Placer:
    """One global occupancy grid for every feature on the sheet, so two passes
    cannot draw on the same ground. The artist never overlaps a forest with a
    mountain range; neither should we."""

    def __init__(self, cell=64.0):
        self.cell = cell
        self.grid = {}

    def can(self, x, y, r):
        c = self.cell
        gx, gy = int(x / c), int(y / c)
        for ax in range(gx - 2, gx + 3):
            for ay in range(gy - 2, gy + 3):
                for (px, py, pr) in self.grid.get((ax, ay), ()):
                    if (x - px) ** 2 + (y - py) ** 2 < (r + pr) ** 2:
                        return False
        return True

    def add(self, x, y, r):
        self.grid.setdefault((int(x / self.cell), int(y / self.cell)), []).append((x, y, r))


def classify(land, rng):
    """Elevation + moisture -> one zone per cell.

    Thresholds come from QUANTILES of the realised field, not from absolute
    numbers: raw value-noise has a centre-heavy distribution, so a fixed cut
    put 58% of the sheet in one zone. Quantiles give the intended mix whatever
    the noise happens to look like.
    """
    elev = value_noise(rng, ZW, ZH, 26)
    moist = value_noise(rng, ZW, ZH, 19, octaves=3)
    e_land, m_land = [], []
    for y in range(ZH):
        for x in range(ZW):
            i = y * ZW + x
            dx, dy = (x + 0.5) * ZCELL_X, (y + 0.5) * ZCELL_Y
            if not land.on_land(dx, dy):
                continue
            inland = min(1.0, land.elevation(dx, dy) / 9.0)
            e = elev[i] * 0.80 + inland * 0.20
            elev[i] = e
            e_land.append(e)
            m_land.append(moist[i])
    if not e_land:
        return [WATER] * (ZW * ZH)
    e_land.sort()
    m_land.sort()

    def q(vals, p):
        return vals[min(len(vals) - 1, int(p * (len(vals) - 1)))]

    mtn_t, hill_t = q(e_land, 0.90), q(e_land, 0.72)
    dry_t, wet_t = q(m_land, 0.28), q(m_land, 0.66)

    zone = [WATER] * (ZW * ZH)
    for y in range(ZH):
        for x in range(ZW):
            i = y * ZW + x
            dx, dy = (x + 0.5) * ZCELL_X, (y + 0.5) * ZCELL_Y
            if not land.on_land(dx, dy):
                continue
            e, m = elev[i], moist[i]
            if e >= mtn_t:
                zone[i] = MOUNTAIN
            elif e >= hill_t:
                zone[i] = HILL
            elif m < dry_t:
                zone[i] = DESERT
            elif m > wet_t:
                zone[i] = FOREST
            else:
                zone[i] = PLAIN
    return zone


def cells_of(zone, which, rng):
    out = []
    for y in range(ZH):
        for x in range(ZW):
            if zone[y * ZW + x] == which:
                out.append(((x + 0.5) * ZCELL_X, (y + 0.5) * ZCELL_Y,
                            x, y))
    rng.shuffle(out)
    return out


def main():
    t_all = time.perf_counter()
    rng = random.Random(20261016)
    hand = P.Hand(seed=7)
    P.build_grains()

    print("1. land mass")
    t = time.perf_counter()
    mask, surf = P.pour_rice(rng, clumps=4, grain_target=20000,
                             sigma=(0.13, 0.22))
    land = P.Land(mask, surf)
    print(f"   pour rice: {ms(t):.0f} ms  land {sum(mask)/len(mask)*100:.1f}%")

    t = time.perf_counter()
    shapes = P.loops_sorted(mask)
    dev = [(a, P.to_dev(l), c) for a, l, c in shapes]
    print(f"   trace contour: {ms(t):.0f} ms  {len(dev)} masses, "
          f"{sum(1 for _,_,c in dev if not c)} running off the page")

    ink = pygame.Surface((W, H), pygame.SRCALPHA)
    ink.fill((0, 0, 0, 0))

    t = time.perf_counter()
    for _, l, _ in dev:
        P.pen(ink, P.resample(l, 3.6), PEN["05"], hand, taper=True)
    print(f"   continent border: {ms(t):.0f} ms")

    t = time.perf_counter()
    for _, l, _ in dev[:3]:
        P.coast_water(ink, P.resample(l, 5.0), hand)
    print(f"   water illusion: {ms(t):.0f} ms")

    print("2. terrain zoning (elevation + moisture)")
    t = time.perf_counter()
    zone = classify(land, rng)
    hist = {}
    for z in zone:
        hist[ZNAME[z]] = hist.get(ZNAME[z], 0) + 1
    print(f"   classify: {ms(t):.0f} ms  {hist}")

    placer = Placer(cell=72.0)

    # ── mountains, in ranges that follow the mountainous zone ──
    print("3. mountains -> hills (the transition the video describes)")
    t = time.perf_counter()
    n_mtn = 0
    # COUNT FROM AREA, not a global cap: a mountain's footprint is ~(1.4*size)^2/2,
    # and a range wants ~25% of its zone covered. Capping globally instead put 151
    # mountains into 8% of the sheet and they meshed into a wireframe web.
    zone_px = ZCELL_X * ZCELL_Y
    n_mtn_zone = sum(1 for c in zone if c == MOUNTAIN)
    mean_size = 64.0
    target_mtn = int(0.25 * (n_mtn_zone * zone_px) / ((1.4 * mean_size) ** 2 / 2))
    target_mtn = max(6, min(40, target_mtn))
    peaks = [c for c in cells_of(zone, MOUNTAIN, rng)]
    for (cx0, cy0, zx, zy) in peaks:
        if n_mtn >= target_mtn:
            break
        ang = rng.uniform(0, math.tau)
        cx, cy = cx0, cy0
        total = rng.randint(7, 13)
        for step in range(1, total + 1):
            ang += rng.gauss(0, 0.20)
            cx += math.cos(ang) * rng.uniform(70, 105)
            cy += math.sin(ang) * rng.uniform(70, 105)
            if not (20 < cx < VW - 20 and 20 < cy < VH - 20):
                break
            if not land.on_land(cx, cy):
                continue
            f = min(step / 3.5, (total - step) / 3.5, 1.0)
            size = 34 + 60 * max(0.08, f)
            if not placer.can(cx, cy, size * 0.60):
                continue
            placer.add(cx, cy, size * 0.60)
            P.mountain(ink, cx, cy, size, hand, tall=(rng.random() < 0.15))
            n_mtn += 1
    print(f"   mountains: {ms(t):.0f} ms ({n_mtn})")

    t = time.perf_counter()
    n_hill = 0
    n_hill_zone = sum(1 for c in zone if c == HILL)
    target_hill = max(6, min(90, int(0.30 * (n_hill_zone * zone_px) / ((1.7 * 55.0) ** 2 / 2))))
    for (cx, cy, zx, zy) in cells_of(zone, HILL, rng):
        if n_hill >= target_hill:
            break
        if not placer.can(cx, cy, 34):
            continue
        placer.add(cx, cy, 34)
        P.hill(ink, cx, cy, rng.uniform(40, 70), hand)
        n_hill += 1
    print(f"   hills: {ms(t):.0f} ms ({n_hill})")

    print("4. forest masses, desert regions")
    t = time.perf_counter()
    n_tree, n_clump = 0, 0
    fcells = cells_of(zone, FOREST, rng)
    step = max(1, len(fcells) // 9) if fcells else 1
    for (fx, fy, zx, zy) in fcells[::step]:
        if n_clump >= 9 or n_tree >= 900:
            break
        n_clump += 1
        for _ in range(320):
            x = fx + rng.gauss(0, 170)
            y = fy + rng.gauss(0, 215)
            if not (24 < x < VW - 24 and 24 < y < VH - 24):
                continue
            if not land.on_land(x, y):
                continue
            r = 8
            if not placer.can(x, y, r):
                continue
            placer.add(x, y, r)
            if rng.random() < 0.78:
                P.pine(ink, x, y, rng.uniform(21, 32), hand)
            else:
                P.oak(ink, x, y, rng.uniform(19, 28), hand)
            n_tree += 1
    print(f"   forest: {ms(t):.0f} ms ({n_clump} masses, {n_tree} trees)")

    t = time.perf_counter()
    n_dot, n_dune, DW, DH = 0, 0, GW // 3, GH // 3
    dcell = (VW / DW, VH / DH)
    dcells = cells_of(zone, DESERT, rng)
    step = max(1, len(dcells) // 3) if dcells else 1
    n_des = 0
    for (dx0, dy0, zx, zy) in dcells[::step]:
        if n_des >= 3:
            break
        reg = P.pour_region(rng, DW, DH, clumps=2, grain_target=700)

        def in_desert(x, y):
            gx, gy = int(x / dcell[0]), int(y / dcell[1])
            return (0 <= gx < DW and 0 <= gy < DH and reg[gy * DW + gx] == 1)

        pts = [(x * dcell[0], y * dcell[1])
               for y in range(0, DH, 2) for x in range(0, DW, 2)
               if reg[y * DW + x] and land.on_land(x * dcell[0], y * dcell[1])]
        if len(pts) < 60:
            continue
        n_des += 1
        for (x, y) in pts:
            for _ in range(6):
                px = x + rng.gauss(0, dcell[0] * 1.3)
                py = y + rng.gauss(0, dcell[1] * 1.3)
                if in_desert(px, py) and land.on_land(px, py) and rng.random() < 0.13:
                    P.dot(ink, px, py, rng.uniform(1.0, 1.45))
                    n_dot += 1
            for _ in range(7):
                a = rng.uniform(0, math.tau)
                px = x + math.cos(a) * dcell[0] * rng.uniform(0.7, 1.5)
                py = y + math.sin(a) * dcell[1] * rng.uniform(0.7, 1.5)
                if not in_desert(px, py) and land.on_land(px, py):
                    P.dot(ink, px, py, rng.uniform(1.5, 2.2))
                    n_dot += 1
        for _ in range(6):
            cand = sorted(pts, key=lambda q: rng.random())[:40]
            for (x, y) in cand:
                if placer.can(x, y, 30):
                    placer.add(x, y, 30)
                    P.dune(ink, x, y, rng.uniform(38, 56), hand)
                    n_dune += 1
                    break
    print(f"   desert: {ms(t):.0f} ms ({n_des} regions, {n_dot} dots, {n_dune} dunes)")

    print("5. rivers from the mountains down to the coast")
    t = time.perf_counter()
    n_riv = 0
    srcs = [(a, b) for (a, b, _, _) in cells_of(zone, MOUNTAIN, rng)][:40]
    for (sx, sy) in srcs:
        if n_riv >= 10:
            break
        pts = [(sx, sy)]
        x, y = sx, sy
        for _ in range(300):
            best, bp = land.elevation(x, y), None
            for _ in range(18):
                a = rng.uniform(0, math.tau)
                d = rng.uniform(26.0, 42.0)
                nx_, ny_ = x + math.cos(a) * d, y + math.sin(a) * d
                if not (8 < nx_ < VW - 8 and 8 < ny_ < VH - 8):
                    continue
                if not land.on_land(nx_, ny_):
                    pts.append((nx_, ny_))
                    bp, best = (nx_, ny_), -1
                    break
                e = land.elevation(nx_, ny_)
                if e < best:
                    best, bp = e, (nx_, ny_)
            if bp is None:
                break
            pts.append(bp)
            x, y = bp
            if best <= 0:
                break
        if len(pts) < 10:
            continue
        squig = [pts[0]]
        for i in range(1, len(pts)):
            px, py = pts[i - 1]
            dx_, dy_ = pts[i][0] - px, pts[i][1] - py
            L = math.hypot(dx_, dy_) or 1.0
            o = rng.gauss(0, 12)
            squig.append((pts[i][0] - dy_ / L * o, pts[i][1] + dx_ / L * o))
        P.curve(ink, squig, PEN["02"], hand, n_sub=4, taper=True)
        for i in range(1, len(squig) - 1):
            p0, p1, p2 = squig[i - 1], squig[i], squig[i + 1]
            a1 = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
            a2 = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
            if abs(a2 - a1) > 0.5 and rng.random() < 0.4:
                P.pen(ink, [p1, ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)],
                      PEN["03"], hand, taper=True)
        n_riv += 1
    print(f"   rivers: {ms(t):.0f} ms ({n_riv})")

    print("6. grass as the filler, only where nothing else went")
    t = time.perf_counter()
    n_g = 0
    pc = cells_of(zone, PLAIN, rng)
    if hi := cells_of(zone, HILL, rng):
        pc += hi
    if f := cells_of(zone, FOREST, rng):
        pc += f
    rng.shuffle(pc)
    for (x, y, zx, zy) in pc:
        if n_g >= 240:
            break
        if not placer.can(x, y, 24):
            continue
        placer.add(x, y, 24)
        P.grass(ink, x, y, rng.uniform(14, 22), hand)
        n_g += 1
    print(f"   tufts: {ms(t):.0f} ms ({n_g})")

    t = time.perf_counter()
    paper = P.make_paper()
    paper.blit(pygame.transform.smoothscale(ink, (VW, VH)), (0, 0))
    print(f"7. paper + flatten: {ms(t):.0f} ms")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ref_render.png")
    pygame.image.save(paper, out)
    print(f"\nTOTAL {ms(t_all):.0f} ms -> {out}")


if __name__ == "__main__":
    main()
