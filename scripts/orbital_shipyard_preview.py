"""Render the Orbital Shipyard review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/orbital_shipyard/:

  orbital_shipyard_1280x400.png            the Pi strip, the reviewed composition
  orbital_shipyard_1280x400_keellock.png   the signature beat: the keel locks
  orbital_shipyard_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  orbital_shipyard_1080x1920.png           the portrait wall, re-composed
  orbital_shipyard_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/orbital_shipyard_preview.py
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
from modes.orbital_shipyard_mode import OrbitalShipyardMode                # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "orbital_shipyard")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["orbitalshipyard"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0, frames=3):
    screen = pygame.Surface(size)
    mode = OrbitalShipyardMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    for _ in range(frames):
        mode.update(1.0 / 60.0)
        mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "34")
    cases = (
        (narrow, (1280, 400), "orbital_shipyard_1280x400.png", None, 26.0),
        (("configs/modes_config_portrait.json", "39"), (1080, 1920),
         "orbital_shipyard_1080x1920.png", None, 26.0),
        (("configs/modes_config_landscape.json", "21"), (1920, 1080),
         "orbital_shipyard_1920x1080.png", None, 26.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"hull={stats['hull_percent']}% sections={stats['sections_unlocked']} "
              f"sparks={stats['sparks']} quality={stats['quality']} "
              f"corner_clear={stats['corner_clear']}")

    # the keel lock: the gantry lights run along the spine
    probe = OrbitalShipyardMode(merged(*narrow))
    probe.enter(FakeManager(pygame.Surface((64, 64))))
    start, duration, _section = probe._locks[0]
    probe.exit()
    screen, stats = still(*narrow, (1280, 400), None, start + duration * 0.4)
    pygame.image.save(screen, os.path.join(OUT, "orbital_shipyard_1280x400_keellock.png"))
    print(f"orbital_shipyard_1280x400_keellock.png: lock={stats['lock']}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 26.0)
    pygame.image.save(screen, os.path.join(OUT, "orbital_shipyard_1280x400_noglow.png"))
    print(f"orbital_shipyard_1280x400_noglow.png: hull={stats['hull_percent']}% "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
