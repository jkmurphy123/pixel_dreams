#!/usr/bin/env python3
# scripts/make_arcane_placeholder.py
#
# Generates assets/control_panel/backgrounds/arcane_lab_placeholder.png — a grey-box
# arcane-laboratory painting at the wall's 1080x1920 portrait, so the arcane control
# types and the arcane_lab layout can be built, rendered and aligned BEFORE the real
# artwork exists (designs/ARCANE_LAB_DESIGN.md §7, path B).
#
# It is deliberately a composition, not a diagram: stone wall, shelf, apparatus with two
# posts, desk, floor circle, warm candle pools. Overlay rects placed against it survive a
# swap to real art of the same composition, and the alignment page fixes the rest.
#
# The printed SLOTS block is the recipe for arcane_lab.json: each overlay's box is a
# feature of this painting, so the numbers in the layout are not guesses.
#
# Run headless:
#   SDL_VIDEODRIVER=dummy python scripts/make_arcane_placeholder.py

import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from controlpanel import paths  # noqa: E402

W, H = 1080, 1920

# Composition constants. The layout JSON uses these numbers.
SHELF_Y = 430                 # top surface of the shelf
SHELF_X0, SHELF_X1 = 70, 1010
DESK_Y = 1270                 # top surface of the desk
DESK_X0, DESK_X1 = 90, 990
POSTS = (430, 660)            # the two apparatus posts (x)
POST_TOP, POST_BOTTOM = 560, 830
CIRCLE = (540, 1650, 240)     # centre + radius of the floor circle

STONE_TOP = (38, 32, 40)
STONE_BOTTOM = (17, 14, 19)
WOOD = (52, 38, 28)
WOOD_LIGHT = (74, 54, 38)
BRASS = (150, 116, 62)
BRASS_DARK = (86, 66, 36)
CANDLE_WAX = (206, 194, 172)
WARM = (255, 168, 88)


def vertical_gradient(size, top, bottom):
    surf = pygame.Surface(size)
    w, h = size
    for y in range(h):
        k = y / max(1, h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3))
        pygame.draw.line(surf, c, (0, y), (w, y))
    return surf


def masonry(wall, rng):
    """Brick courses: a slightly varied fill per block, a darker mortar line around it."""
    row_h, brick_w = 78, 210
    y = 0
    row = 0
    while y < H:
        offset = -brick_w // 2 if row % 2 else 0
        x = offset
        while x < W:
            tone = rng.randint(-4, 4)
            rect = pygame.Rect(x + 3, y + 3, brick_w - 6, row_h - 6)
            fill = (max(0, min(255, STONE_TOP[0] + tone)),
                    max(0, min(255, STONE_TOP[1] + tone)),
                    max(0, min(255, STONE_TOP[2] + tone)))
            pygame.draw.rect(wall, fill, rect)
            pygame.draw.rect(wall, (10, 8, 12), rect, 3)
            x += brick_w
        y += row_h
        row += 1


def stains(wall, rng):
    """Age: a few big soft dark blotches, drawn as stacked translucent circles."""
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(14):
        cx, cy = rng.randint(0, W), rng.randint(0, H)
        r = rng.randint(60, 260)
        for k in range(6):
            radius = int(r * (1 - k / 7))
            pygame.draw.circle(layer, (8, 6, 10, 10), (cx, cy), radius)
    wall.blit(layer, (0, 0))


def vignette(scene):
    """A smooth edge darkening, built small and scaled up (per-pixel at full size is slow)."""
    small = pygame.Surface((270, 480), pygame.SRCALPHA)
    small.fill((0, 0, 0, 0))
    cx, cy = 135.0, 240.0
    for y in range(480):
        for x in range(270):
            d = ((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2
            a = int(120 * min(1.0, max(0.0, (d - 0.35) / 0.9)))
            if a:
                small.set_at((x, y), (0, 0, 0, a))
    scene.blit(pygame.transform.smoothscale(small, (W, H)), (0, 0))


def grain(scene, rng):
    """Film grain from a tiled 96x96 noise square, added at low strength."""
    tile = pygame.Surface((96, 96), pygame.SRCALPHA)
    for y in range(96):
        for x in range(96):
            v = rng.randint(0, 13)
            tile.set_at((x, y), (v, v, v, 255))
    for ty in range(0, H, 96):
        for tx in range(0, W, 96):
            scene.blit(tile, (tx, ty), special_flags=pygame.BLEND_RGB_ADD)


def glow(scene, center, radius, color, strength=1.0):
    """A soft light pool baked into the painting (the overlays add their own on top)."""
    small = pygame.Surface((128, 128), pygame.SRCALPHA)
    small.fill((0, 0, 0, 0))
    half = 64.0
    for y in range(128):
        for x in range(128):
            d = ((x - half) ** 2 + (y - half) ** 2) ** 0.5 / half
            if d >= 1.0:
                continue
            # PREMULTIPLIED and capped: BLEND_RGB_ADD ignores alpha, so an un-premultiplied
            # colour at full strength is a hard bright disc (the same trap as arcane.py's halos).
            k = 0.5 * strength * (1.0 - d) ** 2.2
            small.set_at((x, y), (int(color[0] * k), int(color[1] * k), int(color[2] * k), 255))
    big = pygame.transform.smoothscale(small, (radius * 2, radius * 2))
    scene.blit(big, (center[0] - radius, center[1] - radius), special_flags=pygame.BLEND_RGB_ADD)


def plank(board, rect, rng, vertical=False):
    """A wooden board with grain lines and a darker edge."""
    pygame.draw.rect(board, WOOD, rect)
    x, y, w, h = rect
    pygame.draw.rect(board, WOOD_LIGHT, (x, y, w, max(2, h // 6)))
    for _ in range(max(3, (h if not vertical else w) // 12)):
        if vertical:
            gx = x + rng.randint(4, max(4, w - 4))
            pygame.draw.line(board, (40, 29, 21), (gx, y + 3), (gx, y + h - 3), 1)
        else:
            gy = y + rng.randint(4, max(4, h - 4))
            pygame.draw.line(board, (40, 29, 21), (x + 3, gy), (x + w - 3, gy), 1)
    pygame.draw.rect(board, (24, 17, 12), rect, 2)


def candle_stick(scene, x, base_y, height=64, width=26):
    """A candlestick: a brass holder, a wax cylinder, a wick. The flame overlay lands on top."""
    pygame.draw.rect(scene, BRASS_DARK, (x - width // 2 - 8, base_y - 10, width + 16, 12))
    pygame.draw.rect(scene, BRASS, (x - width // 2, base_y - height, width, height))
    pygame.draw.rect(scene, CANDLE_WAX, (x - width // 2 + 3, base_y - height + 4, width - 6, height - 8))
    pygame.draw.line(scene, (25, 22, 20), (x, base_y - height + 4), (x, base_y - height - 6), 2)


def jar(scene, x, base_y, w=54, h=86, liquid=(96, 42, 118)):
    """A stoppered jar with a faintly glowing liquid."""
    body = pygame.Rect(x - w // 2, base_y - h, w, h)
    pygame.draw.rect(scene, (30, 40, 46), body, border_radius=10)
    inner = body.inflate(-8, -10)
    pygame.draw.rect(scene, liquid, (inner.x, inner.y + inner.h // 3, inner.w, inner.h - inner.h // 3),
                     border_radius=8)
    pygame.draw.rect(scene, (120, 150, 160), body, 2, border_radius=10)
    pygame.draw.rect(scene, BRASS_DARK, (x - w // 4, base_y - h - 10, w // 2, 12))
    glow(scene, (x, base_y - h // 3), w * 2, (min(255, liquid[0] + 90), min(255, liquid[1] + 70),
                                              min(255, liquid[2] + 70)), 0.55)


def book(scene, x, y, w=300, h=110):
    """An open grimoire: two angled pages, a spine shadow, a couple of ink lines."""
    left = [(x, y + h), (x + w // 2, y + h - 26), (x + w // 2, y), (x, y + 18)]
    right = [(x + w, y + h), (x + w // 2, y + h - 26), (x + w // 2, y), (x + w, y + 18)]
    pygame.draw.polygon(scene, (206, 196, 172), left)
    pygame.draw.polygon(scene, (188, 178, 156), right)
    pygame.draw.polygon(scene, (120, 108, 92), left, 2)
    pygame.draw.polygon(scene, (120, 108, 92), right, 2)
    pygame.draw.line(scene, (90, 80, 70), (x + w // 2, y + 4), (x + w // 2, y + h - 24), 3)
    for k in range(4):
        yy = y + 26 + k * 16
        pygame.draw.line(scene, (140, 130, 116), (x + 18, yy + 8), (x + w // 2 - 16, yy - 4), 1)
        pygame.draw.line(scene, (140, 130, 116), (x + w // 2 + 16, yy - 4), (x + w - 18, yy + 8), 1)


def floor_circle(scene):
    """The ritual circle on the floor: two rings and a tick ring, worn brass on stone."""
    cx, cy, r = CIRCLE
    for radius, width, colour in ((r, 2, (128, 104, 70)),
                                  (int(r * 0.86), 1, (104, 86, 60)),
                                  (int(r * 0.62), 1, (96, 80, 58))):
        pygame.draw.circle(scene, colour, (cx, cy), radius, width)
    for k in range(36):
        import math
        a = math.tau * k / 36
        r0, r1 = r * 0.86, r
        pygame.draw.line(scene, (118, 96, 66),
                         (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                         (cx + math.cos(a) * r1, cy + math.sin(a) * r1), 1)


def main():
    rng = random.Random(20261017)
    pygame.init()
    pygame.display.set_mode((1, 1))          # a surface context for convert()/blits, never shown

    scene = vertical_gradient((W, H), STONE_TOP, STONE_BOTTOM)
    masonry(scene, rng)
    stains(scene, rng)

    # ---- shelf
    plank(scene, (SHELF_X0, SHELF_Y, SHELF_X1 - SHELF_X0, 34), rng)
    pygame.draw.rect(scene, (26, 19, 14), (SHELF_X0, SHELF_Y + 34, SHELF_X1 - SHELF_X0, 12))
    for bx in (SHELF_X0 + 40, (SHELF_X0 + SHELF_X1) // 2, SHELF_X1 - 80):
        pygame.draw.polygon(scene, (30, 22, 16),
                            [(bx, SHELF_Y + 46), (bx + 18, SHELF_Y + 46), (bx + 9, SHELF_Y + 92)])

    # ---- things on the shelf
    jar(scene, 150, SHELF_Y, 54, 92, (86, 44, 116))
    jar(scene, 236, SHELF_Y, 44, 70, (44, 96, 88))
    jar(scene, 320, SHELF_Y, 60, 104, (120, 60, 40))
    candle_stick(scene, 620, SHELF_Y, 74, 28)
    candle_stick(scene, 720, SHELF_Y, 88, 28)
    candle_stick(scene, 820, SHELF_Y, 66, 26)

    # ---- apparatus: two posts connected by an arc of brass, a dark void between them
    for px in POSTS:
        plank(scene, (px - 14, POST_TOP, 28, POST_BOTTOM - POST_TOP), rng, vertical=True)
        pygame.draw.rect(scene, BRASS, (px - 20, POST_BOTTOM - 8, 40, 14))
        pygame.draw.rect(scene, BRASS_DARK, (px - 20, POST_TOP - 6, 40, 12))
    pygame.draw.arc(scene, BRASS_DARK,
                    pygame.Rect(POSTS[0] - 14, POST_TOP - 70, POSTS[1] - POSTS[0] + 28, 140),
                    0.15, 3.0, 8)
    glow(scene, ((POSTS[0] + POSTS[1]) // 2, POST_TOP + 60), 120, (90, 70, 140), 0.45)

    # ---- desk
    plank(scene, (DESK_X0, DESK_Y, DESK_X1 - DESK_X0, 40), rng)
    pygame.draw.rect(scene, (30, 22, 16), (DESK_X0, DESK_Y + 40, DESK_X1 - DESK_X0, 120))
    for lx in (DESK_X0 + 30, DESK_X1 - 60):
        plank(scene, (lx, DESK_Y + 160, 30, 210), rng, vertical=True)

    book(scene, 300, DESK_Y - 96, 320, 100)
    candle_stick(scene, 200, DESK_Y, 60, 24)
    jar(scene, 760, DESK_Y, 62, 88, (40, 70, 120))

    # ---- floor circle
    floor_circle(scene)

    # ---- light: warm pools under the candles, cool spill from the apparatus
    for cx, cy, radius in ((620, SHELF_Y - 100, 190), (720, SHELF_Y - 130, 220),
                           (820, SHELF_Y - 90, 180), (200, DESK_Y - 60, 150)):
        glow(scene, (cx, cy), radius, WARM, 0.85)
    glow(scene, (CIRCLE[0], CIRCLE[1]), 300, (70, 54, 110), 0.30)

    vignette(scene)
    grain(scene, rng)

    out = paths.BACKGROUNDS_DIR / "arcane_lab_placeholder.png"
    pygame.image.save(scene, str(out))
    print(f"wrote {out}")
    print(f"canvas          {W} x {H}")
    print(f"shelf surface   y={SHELF_Y}   x {SHELF_X0}..{SHELF_X1}")
    print(f"desk surface    y={DESK_Y}   x {DESK_X0}..{DESK_X1}")
    print(f"apparatus posts x={POSTS[0]}, {POSTS[1]}   y {POST_TOP}..{POST_BOTTOM}")
    print(f"floor circle    centre {CIRCLE[0]},{CIRCLE[1]}  radius {CIRCLE[2]}")


if __name__ == "__main__":
    main()
