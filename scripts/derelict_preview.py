"""Render the Derelict review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/derelict/:

  derelict_1280x400.png            the Pi strip, the reviewed composition
  derelict_1280x400_window.png     the signature beat: the window flickering
  derelict_1280x400_noglow.png     the same frame with glow_strength 0 (§2.7)
  derelict_1080x1920.png           the portrait wall, re-composed
  derelict_1920x1080.png           the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/derelict_preview.py
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
from modes.derelict_mode import DerelictMode                               # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "derelict")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["derelict"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = DerelictMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = at_time
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def window_moment(mode) -> float:
    """A time inside the window's bright pass, on a flicker peak."""
    best, best_level = 0.0, -1.0
    for step in range(0, 300):
        t = step * 0.1
        mode._time = t
        level = mode._window_alpha()
        if level > best_level:
            best, best_level = t, level
    return best


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    narrow = ("configs/modes_config_narrow_horz.json", "39")
    cases = (
        (narrow, (1280, 400), "derelict_1280x400.png", None, 9.0),
        (("configs/modes_config_portrait.json", "43"), (1080, 1920),
         "derelict_1080x1920.png", None, 9.0),
        (("configs/modes_config_landscape.json", "25"), (1920, 1080),
         "derelict_1920x1080.png", None, 9.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"sections={stats['sections']} debris={stats['debris']} "
              f"window={stats['window_level']:.2f} quality={stats['quality']} "
              f"corner_clear={stats['corner_clear']}")

    probe = DerelictMode(merged(*narrow))
    probe.enter(FakeManager(pygame.Surface((64, 64))))
    when = window_moment(probe)
    probe.exit()
    screen, stats = still(*narrow, (1280, 400), None, when)
    pygame.image.save(screen, os.path.join(OUT, "derelict_1280x400_window.png"))
    print(f"derelict_1280x400_window.png: t={when:.1f}s window={stats['window_level']:.2f}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 9.0)
    pygame.image.save(screen, os.path.join(OUT, "derelict_1280x400_noglow.png"))
    print(f"derelict_1280x400_noglow.png: sections={stats['sections']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
