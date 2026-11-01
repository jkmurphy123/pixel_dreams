"""Render the Terraform review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the two
shipped profile instances (narrow slot 26 and portrait slot 31), pins the seed
and the CITIES stage, and writes the stills in screenshots/terraform/.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/terraform_preview.py
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
from modes.terraform_mode import TerraformMode                             # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "terraform")
SEED = 5151


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["terraform"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    out["start_stage"] = 4
    out["hud"] = "full"
    if extra:
        out.update(extra)
    return out


def still(profile, slot, size):
    screen = pygame.Surface(size)
    mode = TerraformMode(merged(profile, slot))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = 0.0
    mode.render(screen)
    stats = mode.stats()
    mode.exit()
    return screen, stats


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    cases = (
        ("configs/modes_config_narrow_horz.json", "26", (1280, 400),
         "terraform_1280x400.png"),
        ("configs/modes_config_portrait.json", "31", (1080, 1920),
         "terraform_1080x1920.png"),
    )
    for profile, slot, size, filename in cases:
        screen, stats = still(profile, slot, size)
        path = os.path.join(OUT, filename)
        pygame.image.save(screen, path)
        print(f"{filename}: {size[0]}x{size[1]} "
              f"preset={stats['preset']} stage={stats['stage_name']} "
              f"year={stats['year']} quality={stats['quality']} "
              f"corner_clear={stats['corner_clear']}")

    # 16:9 sanity still from the same narrow instance.  It is not a profile
    # entry; the landscape preset is tuned with this check.
    cfg = merged("configs/modes_config_narrow_horz.json", "26",
                 {"orientation": "landscape"})
    screen = pygame.Surface((1920, 1080))
    mode = TerraformMode(cfg)
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    mode._time = 0.0
    mode.render(screen)
    pygame.image.save(screen, os.path.join(OUT, "terraform_1920x1080.png"))
    print("terraform_1920x1080.png")
    mode.exit()

    pygame.quit()


if __name__ == "__main__":
    main()
