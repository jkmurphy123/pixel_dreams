#!/usr/bin/env python3
"""Phase 1 verification: run the ink-map mode off-display at the panel's real size.

Measures the DRAWN output, not the config: builds the real mode through the registry's merged
config, runs frames, saves what actually landed on the screen, and times the two costs that
matter (the one-off paper build and the per-frame blit).

Run from the repo root:
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python designs/inkmap_proto/PHASE1_CHECK.py
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

pygame.init()
pygame.font.init()
W, H = 1080, 1920                     # the panel's real surface (a 1920x1080 panel, rotated)
pygame.display.set_mode((64, 64))

from core.cache import ResourceCache                                  # noqa: E402
from core.config import load_json                                     # noqa: E402
from core.loader import build_merged_config, load_entrypoint           # noqa: E402


class FakeManager:
    def __init__(self, w, h):
        self.screen = pygame.Surface((w, h))
        self.cache = ResourceCache()
        self.width = w
        self.height = h


def ms(t0):
    return (time.perf_counter() - t0) * 1000.0


def main():
    failures = []
    registry = load_json(os.path.join(BASE, "modes_registry.json"), {})
    spec = registry["types"]["inkmap"]

    # an instance exactly as a profile would hold it, plus one pinned seed
    instance = {"type": "inkmap", "seed": 20261016}
    merged = build_merged_config(spec, instance, None)
    mode = load_entrypoint(spec["entrypoint"])(merged)

    manager = FakeManager(W, H)
    t0 = time.perf_counter()
    mode.enter(manager)
    build_ms = ms(t0)
    print(f"enter() at {W}x{H}: {build_ms:.0f} ms  (the parchment, built once)")

    sheet = mode.sheet
    print(f"  paper      {sheet.paper.get_size()}   canvas {sheet.canvas.get_size()}")
    print(f"  ink layer  {sheet.ink.get_size()}  = {sheet.ink.get_width()*sheet.ink.get_height()*4/1e6:.1f} MB")
    print(f"  status     {mode.status()}")

    # 120 frames as the controller would drive them
    t0 = time.perf_counter()
    for _ in range(120):
        mode.update(1.0 / 60.0)
        manager.screen.fill((0, 0, 0))
        mode.render(manager.screen)
    frame_ms = ms(t0) / 120.0
    print(f"per-frame update+render: {frame_ms:.2f} ms  ({1000/frame_ms:.0f} fps ceiling)")

    # what is actually on the screen?
    centre = manager.screen.get_at((W // 2, H // 2))[:3]
    corner = manager.screen.get_at((2, 2))[:3]
    data = pygame.image.tostring(manager.screen, "RGB")
    distinct = len(set(data[i:i + 3] for i in range(0, len(data), 3)))
    print(f"screen: centre {centre}  corner {corner}  distinct colours {distinct}")

    if centre == (0, 0, 0) or corner == (0, 0, 0):
        failures.append("the panel is blank")
    if distinct < 100:
        failures.append(f"only {distinct} distinct colours: not a parchment")
    if sum(centre) <= sum(corner):
        failures.append("the middle is not lighter than the corner: no vignette")
    if sheet.ink.get_size() != (W * 2, H * 2):
        failures.append("the ink layer is not supersampled")
    if mode.status()["planned"] != 0:
        failures.append("phase 1 should plan no strokes")
    if sheet.composites != 0:
        failures.append(f"a sheet with nothing drawn composited {sheet.composites} times")

    # a zoomed crop, so the fibre and mottling can be judged rather than asserted
    crop = manager.screen.subsurface(pygame.Rect(300, 700, 320, 320)).copy()
    zoom = pygame.transform.scale(crop, (640, 640))

    out = os.path.join(BASE, "designs", "inkmap_phase01_sheet.png")
    pygame.image.save(manager.screen, out)
    zoom_path = os.path.join(BASE, "designs", "inkmap_phase01_sheet_zoom.png")
    pygame.image.save(zoom, zoom_path)
    print(f"saved {out}\nsaved {zoom_path}")

    # reproducibility: the same pinned seed must give byte-identical paper
    again = load_entrypoint(spec["entrypoint"])(build_merged_config(spec, instance, None))
    again.enter(FakeManager(W, H))
    same = pygame.image.tostring(again.sheet.paper, "RGB") == \
        pygame.image.tostring(sheet.paper, "RGB")
    print(f"same seed reproduces the sheet byte for byte: {same}")
    if not same:
        failures.append("a pinned seed did not reproduce the sheet")

    mode.exit()
    again.exit()

    print()
    for f in failures:
        print("FAIL:", f)
    print("VERDICT:", "PASS" if not failures else "FAIL")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
