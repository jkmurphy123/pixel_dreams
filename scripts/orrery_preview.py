"""Render the Orrery review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the two
shipped profile instances (narrow slot 21 and portrait slot 26), pins a seed
and a review moment, and writes the stills in screenshots/orrery/.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/orrery_preview.py
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
from modes.orrery_mode import OrreryMode                                   # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "orrery")
SEED = 2001
TIME = 21.0


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["orrery"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size):
    screen = pygame.Surface(size)
    mode = OrreryMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    # Pin the review moment, then clear and re-arm the signature event so the
    # still shows the conjunction the design asked for.
    mode._time = TIME
    mode._start_time = TIME
    mode._conj_pair = None
    mode._conj_until = 0.0
    mode._conj_cooldown = 0.0
    mode._conj_pair_cooldown = {}
    mode._update_conjunction(force=True)
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    cases = (
        ("configs/modes_config_narrow_horz.json", "21", (1280, 400),
         "orrery_1280x400.png"),
        ("configs/modes_config_portrait.json", "26", (1080, 1920),
         "orrery_1080x1920.png"),
    )
    for profile, slot, size, filename in cases:
        screen, stats = still(profile, slot, size)
        path = os.path.join(OUT, filename)
        pygame.image.save(screen, path)
        print(f"{filename}: {size[0]}x{size[1]} "
              f"preset={stats['preset']} elevation={stats['elevation']:.0f} "
              f"plaque={stats['plaque']} labels={stats['labels']} "
              f"conjunction={stats['conjunction']}")

    # 16:9 sanity still from the same narrow instance.  It is not a profile
    # entry yet; the landscape preset is tuned with this check.
    cfg = merged("configs/modes_config_narrow_horz.json", "21",
                 {"orientation": "landscape", "hud": "full",
                  "show_plaque": False})
    screen = pygame.Surface((1920, 1080))
    mode = OrreryMode(cfg)
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = TIME
    mode._start_time = TIME
    mode._update_conjunction(force=True)
    mode.render(screen)
    pygame.image.save(screen, os.path.join(OUT, "orrery_1920x1080.png"))
    print("orrery_1920x1080.png")
    mode.exit()

    pygame.quit()


if __name__ == "__main__":
    main()
