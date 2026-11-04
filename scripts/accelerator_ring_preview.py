"""Render the Accelerator Ring review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/accelerator_ring/:

  accelerator_ring_1280x400.png           the Pi strip, the reviewed composition
  accelerator_ring_1280x400_pulse.png     the signature beat: a hall lighting up
  accelerator_ring_1280x400_noglow.png    the same frame with glow_strength 0 (§2.7)
  accelerator_ring_1080x1920.png          the portrait wall, re-composed
  accelerator_ring_1920x1080.png          the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/accelerator_ring_preview.py
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
from modes.accelerator_ring_mode import AcceleratorRingMode                # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "accelerator_ring")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["acceleratorring"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = AcceleratorRingMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def hall_moment(mode) -> float:
    """A time when the pulse is inside the second hall."""
    hall = mode._halls[1]
    lap = mode.stats() and 18.0 / mode._pulse_speed
    return hall["angle"] / (2 * 3.141592653589793) * lap


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "37")
    cases = (
        (narrow, (1280, 400), "accelerator_ring_1280x400.png", None, 6.0),
        (("configs/modes_config_portrait.json", "41"), (1080, 1920),
         "accelerator_ring_1080x1920.png", None, 6.0),
        (("configs/modes_config_landscape.json", "23"), (1920, 1080),
         "accelerator_ring_1920x1080.png", None, 6.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"halls={stats['detectors']} lit={stats['lit_hall']} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']}")

    probe = AcceleratorRingMode(merged(*narrow))
    probe.enter(FakeManager(pygame.Surface((64, 64))))
    when = hall_moment(probe)
    probe.exit()
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "accelerator_ring_1280x400_pulse.png"))
    print(f"accelerator_ring_1280x400_pulse.png: t={when:.2f}s lit={stats['lit_hall']}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 6.0)
    pygame.image.save(screen, os.path.join(OUT, "accelerator_ring_1280x400_noglow.png"))
    print(f"accelerator_ring_1280x400_noglow.png: halls={stats['detectors']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
