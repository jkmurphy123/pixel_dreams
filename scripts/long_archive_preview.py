"""Render the Long Archive hero frames and a motion sheet.

Design/verification script, not part of the mode.  It loads the real profile
instances (narrow 22 and portrait 27), pins the review seed and quality, and
writes the stills plus four moments of the bar/caption clocks.

Run:
    SDL_VIDEODRIVER=dummy ./.venv/bin/python scripts/long_archive_preview.py
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
from modes.long_archive_mode import LongArchiveMode                        # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "long_archive")
SEED = 5709


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(registry, profile, slot, quality="high"):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry[cfg["type"]], cfg)
    out["seed"] = SEED
    out["quality"] = quality
    return out


def render(cfg, size, time_s=0.0):
    screen = pygame.Surface(size)
    mode = LongArchiveMode(cfg)
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = float(time_s)
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.font.init()
    pygame.display.set_mode((64, 64))
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})["types"]

    cases = (
        ("configs/modes_config_narrow_horz.json", "22", (1280, 400),
         "hero_1280x400.png"),
        ("configs/modes_config_portrait.json", "27", (1080, 1920),
         "hero_1080x1920.png"),
        ("configs/modes_config_narrow_horz.json", "22", (1920, 1080),
         "hero_1920x1080.png"),
    )
    for profile, slot, size, name in cases:
        cfg = merged(registry, profile, slot)
        screen, stats = render(cfg, size, 0.0)
        pygame.image.save(screen, os.path.join(OUT, name))
        print(f"{name}: {size[0]}x{size[1]} "
              f"active={stats['active_width']}px "
              f"bar={stats['bar_fraction']:.2f} "
              f"caption={stats['caption_chars']}/{stats['caption_len']}")

    # Four moments of the strip: hold, fade, new entry, reveal.
    cfg = merged(registry, "configs/modes_config_narrow_horz.json", "22")
    frames = []
    for seconds in (0.0, 2.5, 5.0, 7.0):
        screen, stats = render(cfg, (1280, 400), seconds)
        frames.append((seconds, screen.copy(), stats))

    sheet = pygame.Surface((1280, 444))
    sheet.fill((2, 5, 12))
    font = pygame.font.SysFont("dejavusansmono", 15, bold=True)
    for index, (seconds, screen, stats) in enumerate(frames):
        small = pygame.transform.smoothscale(screen, (640, 200))
        x = (index % 2) * 640
        y = (index // 2) * 222 + 22
        sheet.blit(small, (x, y))
        label = (f"T+{seconds:03.1f}s   BAR {stats['bar_fraction']:0.2f}   "
                 f"ENTRY {stats['caption_index']:02d}   "
                 f"TEXT {stats['caption_chars']:02d}/{stats['caption_len']:02d}")
        sheet.blit(font.render(label, True, (180, 208, 228)), (x + 10, y - 18))
    path = os.path.join(OUT, "motion_sheet.png")
    pygame.image.save(sheet, path)
    print("motion_sheet.png")
    pygame.quit()


if __name__ == "__main__":
    main()
