"""Render the Orbital Mirror Array review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/orbital_mirror_array/:

  orbital_mirror_array_1280x400.png           the Pi strip, the reviewed composition
  orbital_mirror_array_1280x400_lockloss.png  the signature beat: a sail loses lock
  orbital_mirror_array_1280x400_noglow.png    the same frame with glow_strength 0 (§2.7)
  orbital_mirror_array_1080x1920.png          the portrait wall, re-composed
  orbital_mirror_array_1920x1080.png          the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/orbital_mirror_array_preview.py
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
from modes.orbital_mirror_array_mode import OrbitalMirrorArrayMode         # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "orbital_mirror_array")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["orbitalmirrorarray"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = OrbitalMirrorArrayMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def lock_loss_time(profile, slot):
    """A moment inside the first lock loss, at its most legible."""
    screen = pygame.Surface((1280, 400))
    mode = OrbitalMirrorArrayMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    start, duration, _index = mode._locks[0]
    mode.exit()
    return start + duration * 0.45


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "30")
    cases = (
        (narrow, (1280, 400), "orbital_mirror_array_1280x400.png", None, 20.0),
        (("configs/modes_config_portrait.json", "35"), (1080, 1920),
         "orbital_mirror_array_1080x1920.png", None, 20.0),
        (("configs/modes_config_landscape.json", "17"), (1920, 1080),
         "orbital_mirror_array_1920x1080.png", None, 20.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"mirrors={stats['mirrors']}/{stats['mirror_cap']} "
              f"quality={stats['quality']} corner_clear={stats['corner_clear']} "
              f"focus={stats['focus_percent']:.1f}%")

    when = lock_loss_time(*narrow)
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "orbital_mirror_array_1280x400_lockloss.png"))
    print(f"orbital_mirror_array_1280x400_lockloss.png: t={when:.1f}s lock={stats['lock']}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 20.0)
    pygame.image.save(screen, os.path.join(OUT, "orbital_mirror_array_1280x400_noglow.png"))
    print(f"orbital_mirror_array_1280x400_noglow.png: mirrors={stats['mirrors']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
