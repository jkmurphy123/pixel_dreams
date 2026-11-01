#!/usr/bin/env python3
"""Time-of-day lighting ramp for the sunrise forest study.

Reuses the four-season art in gen_forest.py and drives it from a solar
altitude (sin of the day phase), so the same five layers can be rendered at
night, first light, sunrise, noon, sunset and dusk.

    python designs/sunrise_proto/gen_ramp.py --season autumn
    python designs/sunrise_proto/gen_ramp.py --season autumn --video

Outputs:
    ramp_<season>.png         12-frame contact sheet (half size)
    seasons/<season>_ramp_*.png  full-size key frames
    sunrise_<season>.mp4      optional preview (rendered via PNG frames)
"""

from __future__ import annotations

import argparse
import math
import os
import random
import subprocess
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame
import gen_forest as art

W, H, SS = art.W, art.H, art.SS
TAU = math.tau


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smoothstep(edge0, edge1, x):
    """0 below edge0, 1 above edge1; edges may be reversed."""
    t = clamp01((x - edge0) / (edge1 - edge0)) if edge1 != edge0 else (1.0 if x >= edge1 else 0.0)
    return t * t * (3.0 - 2.0 * t)


def mixf(a, b, t):
    """mix() for 0..1 colour multipliers (art.mix truncates, which zeroes them)."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def sun_altitude(phase):
    """1 at noon, 0 at 06:00/18:00, -1 at midnight."""
    return math.sin((phase - 0.25) * TAU)


class RampScene:
    def __init__(self, season):
        self.season = season
        self.pal = art._PALETTES[season]
        self.layout = art.Layout()
        self.layers = art.build_layers(self.layout, season)
        self.clouds = self._cloud_layer()
        self.stars = self._stars()
        self._grad_cache = {}

    # ------------------------------------------------------------------
    # static pieces
    # ------------------------------------------------------------------
    def _cloud_layer(self):
        surf = pygame.Surface((art.SW, art.SH), pygame.SRCALPHA)
        for c in self.layout.clouds:
            art.draw_cloud(surf, c, self.pal)
        return surf

    def _stars(self):
        rng = random.Random(991)
        out = []
        for _ in range(150):
            x, y = rng.uniform(0, W), rng.uniform(0, 278)
            fade = max(0.0, 1.0 - y / 340.0)
            out.append((x, y, rng.uniform(0.3, 1.5),
                        rng.choice([(208, 222, 255), (255, 244, 226)]),
                        (0.2 + 0.8 * fade)))
        return out

    # ------------------------------------------------------------------
    # lighting state
    # ------------------------------------------------------------------
    def mood(self, phase):
        alt = sun_altitude(phase)
        rising = phase < 0.5
        # 1 at/below the horizon, 0 once the sun is well up
        warm = smoothstep(0.30, 0.005, alt)
        night = smoothstep(-0.04, -0.24, alt)

        day = [(t, art._sample(self.pal["sky"], t)) for t in (0.0, 0.45, 0.72, 0.90)]
        dawn = art._DAWN[self.season]["stops"]
        horizon = dawn[-1][1]
        if not rising:
            horizon = art.mix(horizon, (255, 108, 66), 0.50)
        warm_top = art.mix(day[0][1], (34, 28, 62), 0.55)
        warm_mid = art.mix(day[1][1], horizon, 0.55)
        warm_stops = [(0.0, warm_top), (0.45, warm_mid),
                      (0.72, horizon), (0.90, horizon)]
        night_stops = [(0.0, (6, 9, 22)), (0.45, (10, 18, 40)),
                       (0.72, (20, 30, 52)), (0.90, (34, 44, 68))]

        stops = blend_stops(day, warm_stops, warm)
        stops = blend_stops(stops, night_stops, night)

        sun = self.pal["sun"]
        # a little leftward drift as the sun climbs; returns to the gap at dusk
        sun_x = art.SUN_X - 70.0 * max(0.0, min(1.0, alt))
        sun_y = art.HORIZON + 8 - max(-0.15, min(1.0, alt)) * 240
        sun_r = sun[2] * 1.45 * (1.0 + 0.22 * warm)
        sun_col = art.mix(self.pal["sun_color"],
                          art.mix(horizon, (255, 255, 240), 0.35), 0.65 * warm)
        glow_col = art.mix(self.pal["glow_color"], horizon, 0.70 * warm)
        glow_col = art.mix(glow_col, (44, 58, 96), night * 0.80)
        glow_strength = (0.75 + 0.65 * warm) * (1.0 - 0.55 * night)
        return dict(alt=alt, rising=rising, warm=warm, night=night, stops=stops,
                    sun_x=sun_x, sun_y=sun_y, sun_r=sun_r, sun_col=sun_col,
                    glow_col=glow_col, glow_strength=glow_strength,
                    horizon=horizon)

    # ------------------------------------------------------------------
    # sky
    # ------------------------------------------------------------------
    def sky(self, phase, mood):
        sky = pygame.Surface((art.SW, art.SH))
        art.vgrad(sky, (0, 0, art.SW, art.SH), mood["stops"])

        # stars fade out as first light arrives
        if mood["night"] > 0.01:
            stars = pygame.Surface((art.SW, art.SH), pygame.SRCALPHA)
            for x, y, r, col, bright in self.stars:
                a = int(220 * mood["night"] * bright)
                if a <= 2:
                    continue
                art.circle(stars, x, y, r, col, a)
            sky.blit(stars, (0, 0))

        # horizon bloom + solar halo + disc (disc is occluded by the treeline)
        sx = mood["sun_x"]
        art.radial_glow(sky, sx, art.HORIZON + 24, 470, mood["glow_col"],
                        mood["glow_strength"] * 0.75, squash=0.32)
        art.radial_glow(sky, sx, mood["sun_y"], 220, mood["glow_col"],
                        mood["glow_strength"], squash=0.95)
        if mood["alt"] > -0.04:
            art.circle(sky, sx, mood["sun_y"], mood["sun_r"], mood["sun_col"])
            art.circle(sky, sx - mood["sun_r"] * 0.1,
                       mood["sun_y"] - mood["sun_r"] * 0.1, mood["sun_r"] * 0.78,
                       art.mix(mood["sun_col"], (255, 255, 255), 0.55))

        # horizon mist, warmer at dawn/dusk
        mist_col = art.mix(self.pal["horizon_mist"], mood["horizon"], mood["warm"])
        mist_col = art.mix(mist_col, (74, 88, 112), mood["night"] * 0.8)
        mist = pygame.Surface((art.SW, art.SH), pygame.SRCALPHA)
        mh = art._i(46)
        for row in range(mh):
            t = row / max(1, mh - 1)
            a = int((56 - 24 * mood["night"]) * math.sin(math.pi * t))
            y = art._i(art.HORIZON - 26) + row
            pygame.draw.line(mist, art._c(mist_col, a), (0, y), (art.SW, y))
        sky.blit(mist, (0, 0))

        # clouds: white at noon, peach at dawn, dark at night
        cloud_rgb = art.mix((255, 255, 255),
                            art.mix(mood["horizon"], (255, 255, 255), 0.15),
                            0.65 * mood["warm"])
        cloud_rgb = art.mix(cloud_rgb, (26, 32, 50), mood["night"])
        clouds = art.tint(self.clouds, tuple(c / 255.0 for c in cloud_rgb))
        a = int(255 * (1.0 - 0.62 * mood["night"]))
        clouds.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
        sky.blit(clouds, (0, 0))

        # birds only in daylight
        if mood["alt"] > 0.10:
            bird_col = art.mix(mood["stops"][0][1], (24, 28, 38), 0.72)
            for bx, by in self.layout.birds:
                for k in (-1, 1):
                    pygame.draw.lines(
                        sky, bird_col, False,
                        [(art._i(bx - 9 * k), art._i(by)),
                         (art._i(bx - 3 * k), art._i(by + 3)),
                         (art._i(bx), art._i(by)),
                         (art._i(bx + 3 * k), art._i(by + 3)),
                         (art._i(bx + 9 * k), art._i(by))],
                        max(1, art._i(0.55)))
        return sky

    # ------------------------------------------------------------------
    # forest lighting
    # ------------------------------------------------------------------
    def _gradient(self, top, bottom):
        key = (tuple(int(c * 255) for c in top), tuple(int(c * 255) for c in bottom))
        g1 = self._grad_cache.get(key)
        if g1 is None:
            g1 = pygame.Surface((1, art.SH))
            for y in range(art.SH):
                t = y / (art.SH - 1)
                g1.set_at((0, y), art.mix(key[0], key[1], t))
            self._grad_cache[key] = g1
        return pygame.transform.scale(g1, (art.SW, art.SH))

    def lit_layer(self, name, mood):
        alt = mood["alt"]
        level = 0.050 + 0.950 * smoothstep(0.0, 0.34, alt)
        # foreground reads a little darker than the distance
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

    def render(self, phase):
        mood = self.mood(phase)
        canvas = pygame.Surface((art.SW, art.SH), pygame.SRCALPHA)
        canvas.blit(self.sky(phase, mood), (0, 0))
        for name in ("far", "mid", "ground", "near"):
            canvas.blit(self.lit_layer(name, mood), (0, 0))
        final = pygame.Surface((W, H))
        final.blit(pygame.transform.smoothscale(canvas, (W, H)), (0, 0))
        return final, mood


def blend_stops(a, b, t):
    return [(a[i][0], art.mix(a[i][1], b[i][1], t)) for i in range(4)]


def label_for(hour, mood):
    alt = math.degrees(math.asin(max(-1.0, min(1.0, mood["alt"]))))
    tod = "day" if mood["alt"] > 0.32 else (
        "golden" if mood["alt"] > 0.06 else (
            "sunrise" if mood["alt"] > -0.03 else (
                "first light" if mood["alt"] > -0.26 else "night")))
    if not mood["rising"] and mood["alt"] <= 0.32:
        tod = {"day": "day", "golden": "golden", "sunrise": "sunset",
               "first light": "dusk", "night": "night"}[tod]
    return f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}   {tod.upper()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="autumn",
                    choices=["spring", "summer", "autumn", "winter"])
    ap.add_argument("--video", action="store_true", help="also render an MP4 preview")
    ap.add_argument("--frames", type=int, default=360, help="video frame count")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--from", dest="start", type=float, default=4.0, help="start hour")
    ap.add_argument("--to", dest="end", type=float, default=21.0, help="end hour")
    args = ap.parse_args()

    pygame.init()
    scene = RampScene(args.season)

    times = [2.0, 5.15, 5.45, 5.75, 6.08, 6.42, 6.83, 9.0, 12.0, 17.5, 18.25, 19.0]
    tiles, labels = [], []
    for hour in times:
        phase = (hour / 24.0) % 1.0
        img, mood = scene.render(phase)
        path = os.path.join(HERE, "seasons", f"{args.season}_ramp_{hour:05.2f}.png")
        pygame.image.save(img, path)
        small = pygame.transform.smoothscale(img, (W // 2, H // 2))
        tiles.append(small)
        labels.append(label_for(hour, mood))
        print("wrote", path)

    art.make_sheet(tiles, labels, os.path.join(HERE, f"ramp_{args.season}.png"),
                   cols=4, pad=16, label_h=28)
    print("wrote", os.path.join(HERE, f"ramp_{args.season}.png"))

    if args.video:
        frames_dir = os.path.join(HERE, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        n = args.frames
        for i in range(n):
            hour = args.start + (args.end - args.start) * (i / max(1, n - 1))
            phase = (hour / 24.0) % 1.0
            img, _ = scene.render(phase)
            pygame.image.save(img, os.path.join(frames_dir, f"f{i:05d}.png"))
            if i % 20 == 0:
                print(f"frame {i}/{n}")
        out = os.path.join(HERE, f"sunrise_{args.season}.mp4")
        enc = os.path.join(HERE, "encode_video.py")
        subprocess.check_call(["/usr/bin/python3", enc, frames_dir, out, str(args.fps)])
        print("wrote", out)


if __name__ == "__main__":
    main()
