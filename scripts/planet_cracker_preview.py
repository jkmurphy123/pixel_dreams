"""Render the Planet Cracker review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/planet_cracker/:

  planet_cracker_1280x400.png            the Pi strip, the reviewed composition
  planet_cracker_1280x400_separation.png the signature beat: a plate lets go
  planet_cracker_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  planet_cracker_1080x1920.png           the portrait wall, re-composed
  planet_cracker_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/planet_cracker_preview.py
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
from modes.planet_cracker_mode import PlanetCrackerMode                    # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "planet_cracker")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["planetcracker"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = PlanetCrackerMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def separation_time(profile, slot):
    screen = pygame.Surface((1280, 400))
    mode = PlanetCrackerMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    start, duration, _plate = mode._separations[0]
    mode.exit()
    return start + duration * 0.5


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "31")
    cases = (
        (narrow, (1280, 400), "planet_cracker_1280x400.png", None, 24.0),
        (("configs/modes_config_portrait.json", "36"), (1080, 1920),
         "planet_cracker_1080x1920.png", None, 24.0),
        (("configs/modes_config_landscape.json", "18"), (1920, 1080),
         "planet_cracker_1920x1080.png", None, 24.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"plates={stats['plates']}/{stats['plate_cap']} rigs={stats['rigs']} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']}")

    when = separation_time(*narrow)
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "planet_cracker_1280x400_separation.png"))
    print(f"planet_cracker_1280x400_separation.png: t={when:.1f}s sep={stats['separation']}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 24.0)
    pygame.image.save(screen, os.path.join(OUT, "planet_cracker_1280x400_noglow.png"))
    print(f"planet_cracker_1280x400_noglow.png: plates={stats['plates']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
