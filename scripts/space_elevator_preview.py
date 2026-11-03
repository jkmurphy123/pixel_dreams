"""Render the Space Elevator review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/space_elevator/:

  space_elevator_1280x400.png            the Pi strip, the reviewed composition
  space_elevator_1280x400_pass.png       the signature beat: the station pass
  space_elevator_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  space_elevator_1080x1920.png           the portrait wall, re-composed
  space_elevator_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/space_elevator_preview.py
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
from modes.space_elevator_mode import SpaceElevatorMode                    # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "space_elevator")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["spaceelevator"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = SpaceElevatorMode(merged(profile, slot, extra))
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

    narrow = ("configs/modes_config_narrow_horz.json", "33")
    cases = (
        (narrow, (1280, 400), "space_elevator_1280x400.png", None, 64.0),
        (("configs/modes_config_portrait.json", "38"), (1080, 1920),
         "space_elevator_1080x1920.png", None, 64.0),
        (("configs/modes_config_landscape.json", "20"), (1920, 1080),
         "space_elevator_1920x1080.png", None, 64.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"alt={stats['altitude_km']:,}km phase={stats['cycle']['phase']} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']}")

    # the station pass: the ring fills the frame as the car goes through it
    when = 0.815 * 104.0
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "space_elevator_1280x400_pass.png"))
    print(f"space_elevator_1280x400_pass.png: t={when:.1f}s phase={stats['cycle']['phase']} "
          f"ring={stats['ring'][0]:.0f}px")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 64.0)
    pygame.image.save(screen, os.path.join(OUT, "space_elevator_1280x400_noglow.png"))
    print(f"space_elevator_1280x400_noglow.png: alt={stats['altitude_km']:,}km "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
