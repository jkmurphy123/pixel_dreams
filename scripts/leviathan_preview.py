"""Render the Leviathan Passage review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the
shipped profile instances (narrow slot 25, portrait slot 30), pins the review
seed and quality, seeks to the hero and eclipse moments, and writes the stills
in screenshots/leviathan/.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/leviathan_preview.py
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
from modes.leviathan_mode import LeviathanMode                             # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "leviathan")
SEED = 5140


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["leviathan"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    out["moon_arc_seconds"] = 0
    if extra:
        out.update(extra)
    return out


def render(profile, slot, size, cycle, meteor=None, extra=None):
    screen = pygame.Surface(size)
    mode = LeviathanMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode.seek(cycle(mode))
    if meteor is not None:
        mode.force_meteor(meteor)
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((64, 64))

    cases = (
        ("configs/modes_config_narrow_horz.json", "25", (1280, 400),
         "mode_1280x400.png", lambda m: m.hero_time(), 0.62, None),
        ("configs/modes_config_portrait.json", "30", (1080, 1920),
         "mode_1080x1920.png", lambda m: m.hero_time(), 0.55, None),
        ("configs/modes_config_narrow_horz.json", "25", (1280, 400),
         "mode_eclipse_1280x400.png", lambda m: m.eclipse_time(), None, None),
        ("configs/modes_config_narrow_horz.json", "25", (1920, 1080),
         "mode_1920x1080.png", lambda m: m.hero_time(), 0.58,
         {"orientation": "landscape"}),
    )
    for profile, slot, size, filename, cycle, meteor, extra in cases:
        screen, stats = render(profile, slot, size, cycle, meteor, extra)
        pygame.image.save(screen, os.path.join(OUT, filename))
        print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
              f"pod={stats['pod']} eclipse={stats['eclipse']:.2f} "
              f"meteor={stats['meteor']}")

    pygame.quit()


if __name__ == "__main__":
    main()
