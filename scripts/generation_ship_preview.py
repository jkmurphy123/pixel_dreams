"""Render the Generation Ship review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the four
shipped profile instances, pins the seed, and writes the stills into
screenshots/slow_wireframe/generation_ship/:

  generation_ship_1280x400.png           the Pi strip, the reviewed composition
  generation_ship_1280x400_bow.png       the signature beat: the name in hull lights
  generation_ship_1280x400_noglow.png    the same frame with glow_strength 0 (§2.7)
  generation_ship_1080x1920.png          the portrait wall, re-composed
  generation_ship_1920x1080.png          the 16:9 profile

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/generation_ship_preview.py
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
from modes.generation_ship_mode import GenerationShipMode                  # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "slow_wireframe", "generation_ship")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["generationship"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size, extra=None, at_time=0.0):
    screen = pygame.Surface(size)
    mode = GenerationShipMode(merged(profile, slot, extra))
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

    narrow = ("configs/modes_config_narrow_horz.json", "38")
    cases = (
        (narrow, (1280, 400), "generation_ship_1280x400.png", None, 42.0),
        (("configs/modes_config_portrait.json", "42"), (1080, 1920),
         "generation_ship_1080x1920.png", None, 42.0),
        (("configs/modes_config_landscape.json", "24"), (1920, 1080),
         "generation_ship_1920x1080.png", None, 42.0),
    )
    for (profile, slot), size, filename, extra, when in cases:
        screen, stats = still(profile, slot, size, extra, when)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"decks={stats['decks']} modules={stats['modules']} "
              f"scroll={stats['scroll']:.2f} quality={stats['quality']} "
              f"corner_clear={stats['corner_clear']}")

    # the bow: the name resolving in hull lights
    probe = GenerationShipMode(merged(*narrow))
    probe.enter(FakeManager(pygame.Surface((64, 64))))
    lap = 240.0 / max(0.15, probe._camera_speed)
    probe.exit()
    screen, stats = still(*narrow, (1280, 400), None, lap * 0.88)
    pygame.image.save(screen, os.path.join(OUT, "generation_ship_1280x400_bow.png"))
    print(f"generation_ship_1280x400_bow.png: bow={stats['at_bow']} "
          f"name={stats['name_progress']:.2f}")

    screen, stats = still(*narrow, (1280, 400), {"glow_strength": 0.0}, 42.0)
    pygame.image.save(screen, os.path.join(OUT, "generation_ship_1280x400_noglow.png"))
    print(f"generation_ship_1280x400_noglow.png: decks={stats['decks']} "
          f"glow={stats['glow_strength']}")

    pygame.quit()


if __name__ == "__main__":
    main()
