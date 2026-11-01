"""Render the Stellar Engine review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the
shipped profile instances (narrow slot 28, portrait slot 33, landscape slot 15),
pins the seed, and writes the stills into screenshots/slow_wireframe/stellarengine/.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/stellarengine_preview.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.cache import ResourceCache                                       # noqa: E402
from core.config import load_json                                          # noqa: E402
from core.loader import build_merged_config                                # noqa: E402
from modes.stellar_engine_mode import StellarEngineMode                    # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "stellarengine")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["stellarengine"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size):
    screen = pygame.Surface(size)
    mode = StellarEngineMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = 0.0
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    cases = (
        ("configs/modes_config_narrow_horz.json", "28", (1280, 400),
         "stellarengine_1280x400.png"),
        ("configs/modes_config_portrait.json", "33", (1080, 1920),
         "stellarengine_1080x1920.png"),
        ("configs/modes_config_landscape.json", "15", (1920, 1080),
         "stellarengine_1920x1080.png"),
    )
    for profile, slot, size, filename in cases:
        screen, stats = still(profile, slot, size)
        path = os.path.join(OUT, filename)
        pygame.image.save(screen, path)
        print(f"{filename}: {size[0]}x{size[1]} "
              f"preset={stats['preset']} palette={stats['palette']} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']}")

    pygame.quit()


if __name__ == "__main__":
    main()
