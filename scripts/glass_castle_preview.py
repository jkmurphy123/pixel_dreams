"""Render the Glass Castle hero frames from the real mode.

Verification script, not part of the mode.  It loads the profile instances
(narrow 24 and portrait 29), pins the review seed and the reviewed moment, and
writes the 1280x400, 1080x1920 and 1920x1080 stills.  The 16:9 frame uses the
narrow-horizontal instance at a 1920x1080 surface to prove the re-anchoring; it
is not a fourth profile entry.

Run:
    SDL_VIDEODRIVER=dummy ./.venv/bin/python scripts/glass_castle_preview.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.cache import ResourceCache                                        # noqa: E402
from core.config import load_json                                           # noqa: E402
from core.loader import build_merged_config                                 # noqa: E402
from modes.glass_castle_mode import GlassCastleMode                         # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "glass_castle")
SEED = 5130
REVIEW_TIME = 15.0


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(registry, profile, slot, *, orientation=None, hud=None):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry[cfg["type"]], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    # The camera phase is zero at REVIEW_TIME, so the still is the reviewed
    # composition; the footer still reports the live 0.5 px/s setting.
    out.setdefault("camera_drift", 0.5)
    if orientation is not None:
        out["orientation"] = orientation
    if hud is not None:
        out["hud"] = hud
    return out


def render(cfg, size):
    screen = pygame.Surface(size)
    mode = GlassCastleMode(cfg)
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = REVIEW_TIME
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((64, 64))
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"),
                         {})["types"]

    cases = (
        ("configs/modes_config_narrow_horz.json", "24", (1280, 400),
         "hero_1280x400.png", None, None),
        ("configs/modes_config_portrait.json", "29", (1080, 1920),
         "hero_1080x1920.png", None, None),
        ("configs/modes_config_narrow_horz.json", "24", (1920, 1080),
         "hero_1920x1080.png", "landscape", "full"),
    )
    for profile, slot, size, name, orientation, hud in cases:
        cfg = merged(registry, profile, slot, orientation=orientation, hud=hud)
        screen, stats = render(cfg, size)
        pygame.image.save(screen, os.path.join(OUT, name))
        print(f"{name}: {size[0]}x{size[1]} "
              f"layout={stats['layout']} shards={stats['shards']} "
              f"windows={stats['windows']} snow={stats['snow']} "
              f"quality={stats['quality']} drift={stats['drift']}")
    pygame.quit()


if __name__ == "__main__":
    main()
