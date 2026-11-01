"""Render the Dyson Swarm review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/dysonswarm/:

  dysonswarm_1280x400.png            the Pi strip, the reviewed composition
  dysonswarm_1280x400_transit.png    the signature beat: a sail crossing the star
  dysonswarm_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  dysonswarm_1080x1920.png           the portrait wall, re-composed
  dysonswarm_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/dyson_swarm_preview.py
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
from modes.dyson_swarm_mode import DysonSwarmMode                          # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "dysonswarm")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["dysonswarm"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = DysonSwarmMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    # Advance the clock the way the controller does: in frame-sized steps.
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def first_transit_time(profile, slot):
    """The moment a transit is at its most legible: a sail over the star, band out."""
    screen = pygame.Surface((1280, 400))
    mode = DysonSwarmMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    start, duration, _index = mode._transits[0]
    mode.exit()
    return start + duration * 0.5


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "27")
    cases = (
        (narrow, (1280, 400), "dysonswarm_1280x400.png", None, 60.0),
        (("configs/modes_config_portrait.json", "32"), (1080, 1920),
         "dysonswarm_1080x1920.png", None, 60.0),
        (("configs/modes_config_landscape.json", "14"), (1920, 1080),
         "dysonswarm_1920x1080.png", None, 60.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"sails={stats['sails']}/{stats['sail_cap']} quality={stats['quality']} "
              f"corner_clear={stats['corner_clear']} star_r={stats['star'][1]:.0f}px")

    # the signature beat
    when = first_transit_time(*narrow)
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "dysonswarm_1280x400_transit.png"))
    print(f"dysonswarm_1280x400_transit.png: t={when:.1f}s transit={stats['transit']}")

    # and the reviewed frame with no bloom at all, for a like-for-like check
    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 60.0)
    pygame.image.save(screen, os.path.join(OUT, "dysonswarm_1280x400_noglow.png"))
    print(f"dysonswarm_1280x400_noglow.png: sails={stats['sails']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
