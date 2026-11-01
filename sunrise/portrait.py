"""Portrait composition for the sunrise mode (1080x1920 and similar).

The landscape art is a 1280x400 strip.  Portrait does not crop that strip: it
keeps the forest as a band across the bottom (scaled to the screen width) and
grows a tall sky above it, with its own sun path, clouds and star field.  HUD
placement stays in the mode; this module only draws the scene.
"""

from __future__ import annotations

import math
import random

import pygame

from . import art
from .lighting import RampScene, mixf, smoothstep, TAU


def _c(col, a=255):
    return (int(col[0]), int(col[1]), int(col[2]), a)


def _circle(dst, x, y, r, col, alpha=255):
    pygame.draw.circle(dst, _c(col, alpha), (int(x), int(y)), max(1, int(r)))


def _line(dst, a, b, col, width=1, alpha=255):
    pygame.draw.line(dst, _c(col, alpha), (int(a[0]), int(a[1])),
                     (int(b[0]), int(b[1])), max(1, int(width)))


def _vgrad(dst, rect, stops):
    x, y, w, h = rect
    for row in range(h):
        t = row / max(1, h - 1)
        col = art._sample(stops, t)
        pygame.draw.line(dst, col, (x, y + row), (x + w - 1, y + row))


def _glow(dst, cx, cy, radius, col, strength=1.0, squash=1.0, steps=44):
    gw = max(2, int(radius * 2))
    gh = max(2, int(radius * squash * 2))
    g = pygame.Surface((gw, gh), pygame.SRCALPHA)
    for i in range(steps):
        f = 1.0 - i / steps
        t = 1.0 - f
        a = int(255 * (t ** 2.3) * min(1.0, strength) * 0.85)
        if a <= 0:
            continue
        rx = radius * f
        ry = radius * squash * f
        rect = pygame.Rect(gw // 2 - int(rx), gh // 2 - int(ry),
                           max(2, int(rx * 2)), max(2, int(ry * 2)))
        pygame.draw.ellipse(g, _c(col, a), rect)
    dst.blit(g, (int(cx - radius), int(cy - radius * squash)))


class PortraitScene:
    def __init__(self, season: str, width: int, height: int):
        self.season = season
        self.pal = art._PALETTES[season]
        self.w = int(width)
        self.h = int(height)
        self.horizon = self.h * 0.80

        self._make_layout()
        self.layers = {
            "far": self._render_layer(self._draw_far),
            "mid": self._render_layer(self._draw_mid),
            "ground": self._render_layer(self._draw_ground),
            "near": self._render_layer(self._draw_near),
        }
        self.clouds = self._build_clouds()
        self.stars = self._build_stars()
        self._grad_cache = {}

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def _make_layout(self):
        w, h, hz = self.w, self.h, self.horizon
        rng = random.Random(20261101)

        self.far_trees = []
        x, i = -15.0, 0
        while x < w + 20:
            th = rng.uniform(22, 52)
            self.far_trees.append(dict(
                x=x, base=hz + 4, h=th, w=th * rng.uniform(0.5, 0.65),
                kind="pine" if rng.random() < 0.70 else "blob", seed=8000 + i))
            x += rng.uniform(14, 27)
            i += 1

        self.mid_trees = []
        x, i = -20.0, 0
        while x < w + 20:
            dip = 1.0 - 0.55 * math.exp(-((x - 785.0) / 190.0) ** 2)
            th = rng.uniform(90, 220) * dip
            self.mid_trees.append(dict(
                x=x, base=hz + rng.uniform(12, 45), h=th, w=th * rng.uniform(0.55, 0.72),
                kind="pine" if rng.random() < 0.52 else "deciduous", seed=7000 + i))
            x += rng.uniform(38, 85)
            i += 1

        self.ridge_trees = []
        x, i = 240.0, 0
        while x < w - 100:
            dip = 1.0 - 0.72 * math.exp(-((x - 785.0) / 140.0) ** 2)
            th = rng.uniform(150, 300) * dip
            self.ridge_trees.append(dict(
                x=x, base=hz + rng.uniform(90, 150), h=th, w=th * rng.uniform(0.55, 0.70),
                kind="pine" if rng.random() < 0.42 else "deciduous", seed=6000 + i))
            x += rng.uniform(70, 130)
            i += 1

        near_specs = [
            (-80, 1990, 600, "pine"), (30, 1950, 500, "deciduous"),
            (150, 1910, 420, "pine"), (260, 1960, 360, "deciduous"),
            (350, 1910, 300, "pine"),
            (960, 1950, 320, "deciduous"), (1040, 1900, 420, "pine"),
            (1130, 1960, 500, "deciduous"), (1210, 1900, 620, "pine"),
        ]
        self.near_trees = [
            dict(x=x, base=b, h=th, w=th * 0.62, seed=5000 + i, accent=False)
            for i, (x, b, th, kind) in enumerate(near_specs)
            for kind in (kind,)
        ]
        for t, (_, _, _, kind) in zip(self.near_trees, near_specs):
            t["kind"] = kind

        self.bushes = [
            dict(x=210, y=1660, rx=46, ry=20, seed=91, accent=False),
            dict(x=420, y=1690, rx=36, ry=16, seed=92, accent=False),
            dict(x=650, y=1665, rx=42, ry=18, seed=93, accent=False),
            dict(x=850, y=1685, rx=50, ry=22, seed=94, accent=False),
            dict(x=1010, y=1650, rx=34, ry=15, seed=95, accent=False),
        ]

        self.scatter = []
        for _ in range(700):
            self.scatter.append((rng.uniform(0, w), rng.uniform(hz + 55, h),
                                 rng.uniform(0.5, 1.6), rng.uniform(0, math.tau)))

        self.ground_top = lambda x: hz + 52 + 7 * math.sin(0.006 * x + 1.2) + 3 * math.sin(0.018 * x + 0.4)
        self.mid_top = lambda x: hz - 16 + 7 * math.sin(0.005 * x + 2.2) + 3 * math.sin(0.016 * x + 1.1)
        self.ridge_a = lambda x: hz - 58 + 9 * math.sin(0.004 * x + 0.7) + 4 * math.sin(0.011 * x + 2.0)
        self.ridge_b = lambda x: hz - 30 + 7 * math.sin(0.005 * x + 2.0) + 3 * math.sin(0.013 * x + 0.3)

    # ------------------------------------------------------------------
    # layer construction
    # ------------------------------------------------------------------
    def _render_layer(self, draw):
        ss = art.SS
        surf = pygame.Surface((self.w * ss, self.h * ss), pygame.SRCALPHA)
        draw(surf)
        return pygame.transform.smoothscale(surf, (self.w, self.h))

    def _draw_far(self, surf):
        w, h = self.w, self.h
        for fn, col in ((self.ridge_a, self.pal["ridge_far"]),
                        (self.ridge_b, self.pal["ridge_near"])):
            pts = [(x, fn(x)) for x in range(-10, w + 20, 8)]
            pts += [(w + 20, h), (-10, h)]
            art.poly(surf, pts, col)

        for t in self.far_trees:
            col = self.pal["far_tree"]
            if t["kind"] == "pine":
                for i in range(3):
                    frac = i / 3
                    art.poly(surf, art._pine_tier(
                        t["x"], t["base"] - t["h"] * (0.16 + 0.60 * frac),
                        t["base"] - t["h"] * (0.64 + 0.60 * frac),
                        t["w"] * 0.5 * (1 - 0.6 * frac), 0.08),
                        art.mix(col, self.pal["ridge_far"], 0.10 + 0.28 * frac))
            else:
                art.circle(surf, t["x"], t["base"] - t["h"] * 0.60, t["h"] * 0.44, col)
                art.circle(surf, t["x"] - t["h"] * 0.22, t["base"] - t["h"] * 0.46,
                           t["h"] * 0.30, art.shade(col, 0.94))

        haze = pygame.Surface((w * art.SS, h * art.SS), pygame.SRCALPHA)
        for row in range(art._i(70)):
            t = row / max(1, art._i(70) - 1)
            a = int(80 * t)
            y = art._i(self.horizon - 60) + row
            pygame.draw.line(haze, art._c(self.pal["horizon_mist"], a),
                             (0, y), (art._i(w), y))
        surf.blit(haze, (0, 0))

    def _draw_mid(self, surf):
        w, h = self.w, self.h
        pts = [(x, self.mid_top(x)) for x in range(-10, w + 20, 8)]
        pts += [(w + 20, h), (-10, h)]
        art.poly(surf, pts, self.pal["mid_hill"])
        crest = [(x, self.mid_top(x)) for x in range(-10, w + 20, 8)]
        for a, b in zip(crest, crest[1:]):
            art.line(surf, a, b, art.mix(self.pal["mid_hill"], (255, 255, 255), 0.40), 0.8)

        tones = self.pal.get("canopy_list")
        if tones:
            tones = [art.mix(c, self.pal["mid_tree"], 0.45) for c in tones]
        for t in self.mid_trees:
            if t["kind"] == "pine":
                art.draw_pine(surf, {**t, "color": self.pal["mid_tree"]}, self.pal, far=True)
            elif self.pal["style"] == "bare":
                art.draw_tree(surf, t, self.pal, leafy=False, far=True)
            else:
                art.draw_tree(surf, t, self.pal, leafy=True, far=True,
                              tone=art.mix(self.pal["canopy"], self.pal["mid_tree"], 0.55),
                              cluster_list=tones)

    def _draw_ground(self, surf):
        w, h = self.w, self.h
        mask = pygame.Surface((w * art.SS, h * art.SS), pygame.SRCALPHA)
        pts = [(x, self.ground_top(x)) for x in range(-10, w + 20, 8)]
        pts += [(w + 20, h + 20), (-10, h + 20)]
        art.poly(mask, pts, (255, 255, 255, 255))

        grad = pygame.Surface((w * art.SS, h * art.SS), pygame.SRCALPHA)
        art.vgrad(grad, (0, 0, w * art.SS, h * art.SS), [
            (0.78, self.pal["ground_top"]),
            (0.90, art.mix(self.pal["ground_top"], self.pal["ground_bottom"], 0.55)),
            (1.0, self.pal["ground_bottom"])])
        surf.blit(art.clip_to(mask, grad), (0, 0))

        detail = pygame.Surface((w * art.SS, h * art.SS), pygame.SRCALPHA)
        rng = random.Random(5150)
        for _ in range(16):
            cx = rng.uniform(-40, w + 40)
            cy = rng.uniform(self.horizon + 70, h)
            rx = rng.uniform(120, 300)
            ry = rng.uniform(6, 17)
            col = art.mix(self.pal["ground_top"], self.pal["ground_bottom"],
                          rng.uniform(0.15, 0.7))
            art.ellipse(detail, cx, cy, rx, ry, col, 70)
        surf.blit(art.clip_to(mask, detail), (0, 0))

        crest = [(x, self.ground_top(x)) for x in range(-10, w + 20, 8)]
        for a, b in zip(crest, crest[1:]):
            art.line(surf, a, b, self.pal["ground_rim"], 1.3)

        bare = self.pal["style"] == "bare"
        rng = random.Random(5250)
        for gx, gy, s, _ in self.scatter:
            if gy < self.ground_top(gx) + 2:
                continue
            if bare:
                col = self.pal["grass"] if rng.random() < 0.5 else self.pal["grass_light"]
                hgt = 5.0 * s
                for k in (-1, 0, 1):
                    art.line(surf, (gx + k * 1.2 * s, gy),
                             (gx + k * 2.4 * s, gy - hgt), col, 0.5)
            else:
                col = self.pal["grass"] if rng.random() < 0.72 else self.pal["grass_light"]
                hgt = 6.5 * s
                for k in (-1, 0, 1, 2):
                    sway = rng.uniform(-1.5, 1.5)
                    art.line(surf, (gx + k * 1.2 * s, gy),
                             (gx + k * 2.5 * s + sway, gy - hgt * rng.uniform(0.65, 1.0)),
                             col, 0.55)

        # seasonal ground cover
        if self.pal is art._PALETTES["autumn"]:
            for _ in range(110):
                x, y = rng.uniform(0, w), rng.uniform(self.horizon + 60, h)
                art.ellipse(surf, x, y, rng.uniform(1.4, 3.0), rng.uniform(0.7, 1.5),
                            rng.choice([(212, 118, 46), (188, 74, 38),
                                        (234, 160, 58), (158, 92, 44)]))
        elif self.pal is art._PALETTES["spring"]:
            for _ in range(80):
                x, y = rng.uniform(0, w), rng.uniform(self.horizon + 65, h)
                stem = y - rng.uniform(3, 7)
                art.line(surf, (x, y), (x, stem), self.pal["grass"], 0.5)
                art.circle(surf, x, stem, rng.uniform(1.0, 1.9),
                           rng.choice([(255, 255, 255), (255, 226, 238),
                                       (255, 236, 160)]))
        elif self.pal is art._PALETTES["summer"]:
            for _ in range(50):
                x, y = rng.uniform(0, w), rng.uniform(self.horizon + 65, h)
                art.circle(surf, x, y, rng.uniform(1.0, 1.8), (250, 250, 240))
        else:
            for _ in range(8):
                x, y = rng.uniform(0, w), rng.uniform(self.horizon + 70, h)
                art.ellipse(surf, x, y, rng.uniform(50, 130), rng.uniform(6, 14),
                            art.mix(self.pal["ground_top"], (255, 255, 255), 0.35))
            for _ in range(60):
                x, y = rng.uniform(0, w), rng.uniform(self.horizon + 60, h)
                hgt = rng.uniform(5, 12)
                for k in (-1, 0, 1):
                    art.line(surf, (x, y), (x + k * 2.2, y - hgt), (118, 108, 96), 0.4)

    def _draw_near(self, surf):
        w, h = self.w, self.h
        tones = self.pal.get("canopy_list")

        for t in self.ridge_trees:
            if t["kind"] == "pine":
                art.draw_pine(surf, {**t, "color": art.mix(self.pal["near_tree"],
                                                           self.pal["mid_tree"], 0.35)},
                              self.pal)
            elif self.pal["style"] == "bare":
                art.draw_tree(surf, t, self.pal, leafy=False)
            else:
                art.draw_tree(surf, t, self.pal, leafy=True,
                              tone=art.mix(self.pal["canopy"], self.pal["canopy_shadow"], 0.38),
                              cluster_list=tones)

        for t in self.near_trees:
            if t["kind"] == "pine":
                art.draw_pine(surf, {**t, "color": self.pal["near_tree"]}, self.pal)
            elif self.pal["style"] == "bare":
                art.draw_tree(surf, t, self.pal, leafy=False)
            else:
                art.draw_tree(surf, t, self.pal, leafy=True,
                              tone=art.mix(self.pal["canopy"], self.pal["canopy_shadow"], 0.25),
                              cluster_list=tones)

        for b in self.bushes:
            if self.pal["style"] == "bare":
                art.ellipse(surf, b["x"] + 2, b["y"] + 5, b["rx"] * 1.5, b["ry"] * 0.55,
                            art.mix(self.pal["ground_bottom"], self.pal["ground_top"], 0.45))
                art.ellipse(surf, b["x"], b["y"], b["rx"] * 1.25, b["ry"] * 0.45,
                            art.mix(self.pal["ground_top"], (255, 255, 255), 0.4))
            else:
                art.draw_bush(surf, b, self.pal)

        # a few foreground grass clumps at the very bottom edge
        rng = random.Random(5350)
        for _ in range(26):
            gx = rng.uniform(0, w)
            gy = h + 4
            for k in range(6):
                bx = gx + rng.uniform(-9, 9)
                art.line(surf, (bx, gy), (bx + rng.uniform(-7, 7), gy - rng.uniform(10, 26)),
                         art.shade(self.pal["ground_bottom"], 0.62), 0.9)

    # ------------------------------------------------------------------
    # clouds / stars / mood / lighting
    # ------------------------------------------------------------------
    def _build_clouds(self):
        ss = art.SS
        surf = pygame.Surface((self.w * ss, self.h * ss), pygame.SRCALPHA)
        specs = (
            (0.18, 0.18, 0.85), (0.74, 0.12, 0.60), (0.46, 0.32, 1.00),
            (0.84, 0.43, 0.50), (0.22, 0.52, 0.65), (0.62, 0.62, 0.48),
        )
        for fx, fy, scale in specs:
            art.draw_cloud(surf, {"cx": fx * self.w, "base": fy * self.h,
                                  "s": scale}, self.pal)
        return pygame.transform.smoothscale(surf, (self.w, self.h))

    def _build_stars(self):
        rng = random.Random(991)
        out = []
        for _ in range(240):
            x = rng.uniform(0, self.w)
            y = rng.uniform(0, max(40, self.horizon - 120))
            fade = max(0.0, 1.0 - y / max(1.0, self.horizon))
            out.append((x, y, rng.uniform(0.35, 1.55),
                        rng.choice([(208, 222, 255), (255, 244, 226)]),
                        0.2 + 0.8 * fade))
        return out

    def mood(self, phase):
        m = RampScene.mood(self, phase)
        alt = m["alt"]
        up = max(0.0, min(1.0, alt))
        m["sun_x"] = art.SUN_X * (self.w / art.W) - 80.0 * up
        m["sun_y"] = self.horizon + 10 - max(-0.15, up) * (self.horizon - 140)
        m["sun_r"] = 42.0 * (self.w / 1080.0) * (1.0 + 0.22 * m["warm"])
        return m

    def _gradient(self, top, bottom):
        key = (tuple(int(c * 255) for c in top), tuple(int(c * 255) for c in bottom))
        g1 = self._grad_cache.get(key)
        if g1 is None:
            g1 = pygame.Surface((1, self.h))
            for y in range(self.h):
                t = y / max(1, self.h - 1)
                g1.set_at((0, y), art.mix(key[0], key[1], t))
            self._grad_cache[key] = g1
        return pygame.transform.scale(g1, (self.w, self.h))

    def _lit_layer(self, name, mood):
        alt = mood["alt"]
        level = 0.05 + 0.95 * smoothstep(0.0, 0.34, alt)
        depth = {"far": 1.10, "mid": 1.0, "ground": 0.94, "near": 0.89}[name]
        level *= 1.0 - (1.0 - depth) * (1.0 - level)

        warm_tint = mixf((1.0, 1.0, 1.0), (1.02, 0.87, 0.73), mood["warm"])
        tint = mixf(warm_tint, (0.56, 0.64, 0.98), mood["night"])
        grad_amt = 0.40 * mood["warm"] + 0.18 * mood["night"]

        top = [min(1.0, level * (1.0 + grad_amt) * tint[i]) for i in range(3)]
        bottom = [min(1.0, level * (1.0 - grad_amt) * tint[i]) for i in range(3)]

        out = self.layers[name].copy()
        out.blit(self._gradient(top, bottom), (0, 0),
                 special_flags=pygame.BLEND_RGB_MULT)
        return out

    # ------------------------------------------------------------------
    # sky
    # ------------------------------------------------------------------
    def _sky(self, phase, mood):
        sky = pygame.Surface((self.w, self.h))
        stops = [
            (0.00, mood["stops"][0][1]),
            (0.55, mood["stops"][1][1]),
            (0.82, mood["stops"][2][1]),
            (0.96, mood["stops"][3][1]),
        ]
        _vgrad(sky, (0, 0, self.w, self.h), stops)

        if mood["night"] > 0.01:
            stars = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            for x, y, r, col, bright in self.stars:
                a = int(220 * mood["night"] * bright)
                if a > 2:
                    _circle(stars, x, y, r, col, a)
            sky.blit(stars, (0, 0))

        sx = mood["sun_x"]
        _glow(sky, sx, self.horizon + 30, self.w * 0.80,
              mood["glow_col"], mood["glow_strength"] * 0.75, squash=0.20)
        _glow(sky, sx, mood["sun_y"], self.w * 0.32,
              mood["glow_col"], mood["glow_strength"], squash=0.95)
        _glow(sky, sx, mood["sun_y"], self.w * 0.10,
              mood["sun_col"], mood["glow_strength"] * 1.10, squash=0.95)
        if mood["alt"] > -0.04:
            r = mood["sun_r"]
            _circle(sky, sx, mood["sun_y"], r, mood["sun_col"])
            _circle(sky, sx - r * 0.10, mood["sun_y"] - r * 0.10,
                    r * (0.78 - 0.16 * mood["sun_warm"]), mood["sun_core"])

        mist_col = art.mix(self.pal["horizon_mist"], mood["horizon"], mood["warm"])
        mist_col = art.mix(mist_col, (74, 88, 112), mood["night"] * 0.8)
        mist = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        mh = max(60, int(self.h * 0.05))
        for row in range(mh):
            t = row / max(1, mh - 1)
            a = int((60 - 28 * mood["night"]) * math.sin(math.pi * t))
            y = int(self.horizon - mh * 0.6) + row
            _line(mist, (0, y), (self.w, y), mist_col, 1, a)
        sky.blit(mist, (0, 0))

        cloud_rgb = art.mix((255, 255, 255),
                            art.mix(mood["horizon"], (255, 255, 255), 0.15),
                            0.65 * mood["warm"])
        cloud_rgb = art.mix(cloud_rgb, (26, 32, 50), mood["night"])
        clouds = art.tint(self.clouds, tuple(c / 255.0 for c in cloud_rgb))
        alpha = int(255 * (1.0 - 0.62 * mood["night"]))
        clouds.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        sky.blit(clouds, (0, 0))

        if mood["alt"] > 0.10:
            bird_col = art.mix(mood["stops"][0][1], (24, 28, 38), 0.72)
            for bx, by in ((0.30 * self.w, 0.36 * self.h),
                           (0.35 * self.w, 0.33 * self.h),
                           (0.66 * self.w, 0.30 * self.h)):
                for k in (-1, 1):
                    pygame.draw.lines(
                        sky, bird_col, False,
                        [(int(bx - 10 * k), int(by)), (int(bx - 3 * k), int(by + 3)),
                         (int(bx), int(by)), (int(bx + 3 * k), int(by + 3)),
                         (int(bx + 10 * k), int(by))], 1)
        return sky

    # ------------------------------------------------------------------
    def render(self, phase):
        mood = self.mood(phase)
        canvas = pygame.Surface((self.w, self.h))
        canvas.blit(self._sky(phase, mood), (0, 0))
        for name in ("far", "mid", "ground", "near"):
            canvas.blit(self._lit_layer(name, mood), (0, 0))
        return canvas, mood
