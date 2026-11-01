"""Render the Space Station V preview frames in screenshots/space_station/.

This is a design/verification script, not part of the mode.  It loads the real
profile instances, pins a seed and a quality, advances the clocks without
rendering (so the auto controller cannot change level mid-timelapse), and
writes the hero frames plus a four-frame motion sheet.

Run:
    SDL_VIDEODRIVER=dummy python scripts/space_station_preview.py
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
from modes.space_station_mode import SpaceStationMode                      # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "space_station")
SEED = 2001
TIME_S = 12.0


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def _merged(registry, profile, slot, quality):
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    merged = build_merged_config(registry, cfg)
    merged["seed"] = SEED
    merged["quality"] = quality
    return merged


def render(merged, size, seconds=TIME_S):
    screen = pygame.Surface(size)
    mode = SpaceStationMode(merged)
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    for _ in range(int(round(seconds * 60.0))):
        mode.update(1.0 / 60.0)
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def label(sheet, font, text, position):
    sheet.blit(font.render(text, True, (180, 232, 255)), position)


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"),
                         {})["types"]

    hero_cases = (
        ("configs/modes_config_narrow_horz.json", "19", (1280, 400),
         "hero_1280x400.png"),
        ("configs/modes_config_landscape.json", "13", (1920, 1080),
         "hero_1920x1080.png"),
        ("configs/modes_config_vert.json", "63", (1080, 1920),
         "hero_1080x1920.png"),
        ("modes_config.json", "35", (480, 270),
         "hero_480x270.png"),
    )
    for profile, slot, size, name in hero_cases:
        merged = _merged(registry, profile, slot, "high")
        screen, stats = render(merged, size)
        path = os.path.join(OUT, name)
        pygame.image.save(screen, path)
        print(f"{name}: {size[0]}x{size[1]} "
              f"segments={stats['segments']} detail={stats['station_detail']} "
              f"framing={stats['framing']}")

    # Motion sheet: the narrow kiosk's real clocks, four moments.
    merged = _merged(registry, "configs/modes_config_narrow_horz.json", "19",
                     "medium")
    frames = []
    for seconds in (0.0, 20.0, 45.0, 90.0):
        screen, stats = render(merged, (1280, 400), seconds)
        frames.append((seconds, screen.copy(), stats))
    sheet = pygame.Surface((1280, 444))
    sheet.fill((2, 5, 13))
    font = pygame.font.SysFont("dejavusansmono", 15, bold=True)
    for index, (seconds, screen, stats) in enumerate(frames):
        small = pygame.transform.smoothscale(screen, (640, 200))
        x = (index % 2) * 640
        y = (index // 2) * 222 + 22
        sheet.blit(small, (x, y))
        label(sheet, font,
              f"T+{seconds:03.0f}s   STATION {stats['spin_deg']:05.1f}deg"
              f"   EARTH {stats['earth_rotation_deg']:05.1f}deg",
              (x + 10, y - 18))
    path = os.path.join(OUT, "motion_sheet.png")
    pygame.image.save(sheet, path)
    print("motion_sheet.png")

    pygame.quit()


if __name__ == "__main__":
    main()
