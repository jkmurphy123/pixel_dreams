"""Render the Ramjet review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/ramjet/:

  ramjet_1280x400.png            the Pi strip, the reviewed composition
  ramjet_1280x400_clump.png      the signature beat: a clump ingested, core flared
  ramjet_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  ramjet_1080x1920.png           the portrait wall, re-composed
  ramjet_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/ramjet_preview.py
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
from modes.ramjet_mode import RamjetMode                                   # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "ramjet")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["ramjet"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = RamjetMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "40")
    cases = (
        (narrow, (1280, 400), "ramjet_1280x400.png", None, 4.0),
        (("configs/modes_config_portrait.json", "44"), (1080, 1920),
         "ramjet_1080x1920.png", None, 4.0),
        (("configs/modes_config_landscape.json", "26"), (1920, 1080),
         "ramjet_1920x1080.png", None, 4.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"rings={stats['dust']} core={stats['core_level']:.2f} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']}")

    probe = RamjetMode(merged(*narrow))
    probe.enter(FakeManager(pygame.Surface((64, 64))))
    start, duration = probe._clumps[0]
    probe.exit()
    screen, stats = still(*narrow, (1280, 400), None, start + duration * 0.5)
    pygame.image.save(screen, os.path.join(OUT, "ramjet_1280x400_clump.png"))
    print(f"ramjet_1280x400_clump.png: clump={stats['clump']} core={stats['core_level']:.2f}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 4.0)
    pygame.image.save(screen, os.path.join(OUT, "ramjet_1280x400_noglow.png"))
    print(f"ramjet_1280x400_noglow.png: core={stats['core_level']:.2f} glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
