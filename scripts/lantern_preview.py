"""Render the Lantern Procession review stills from the real mode.

This is a design/verification script, not part of the mode.  It loads the two
shipped profile instances (narrow slot 23 and portrait slot 28), pins a seed and
a review moment, and writes the stills in screenshots/lantern_procession/.

Run:
    SDL_VIDEODRIVER=dummy .venv/bin/python scripts/lantern_preview.py
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
from modes.lantern_procession_mode import LanternProcessionMode            # noqa: E402

OUT = os.path.join(BASE_DIR, "screenshots", "lantern_procession")
SEED = 412


class FakeManager:
    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def merged(profile, slot, extra=None):
    registry = load_json(os.path.join(BASE_DIR, "modes_registry.json"), {})
    cfg = load_json(os.path.join(BASE_DIR, profile), {})["modes"][slot]
    out = build_merged_config(registry["types"]["lanternprocession"], cfg)
    out["seed"] = SEED
    out["quality"] = "high"
    if extra:
        out.update(extra)
    return out


def best_moment(mode, span=None):
    """A time where the line is well framed: most lanterns visible, none cut."""
    if span is None:
        span = max(240.0, 2.0 * mode._path_len / max(1.0, mode._speed))
    best_t, best_score = 0.0, -1e9
    t = 0.0
    while t < span:
        mode._time = t
        states = mode._compute_states(t, with_event=False)
        visible = [s for s in states
                   if -20 < s.x < mode._layout["width"] + 20
                   and 0 < s.y < mode._layout["height"]]
        edge = sum(1 for s in states
                   if s.dim > 0.2
                   and (s.x - s.half_w * 1.15 < 0
                        or s.x + s.half_w * 1.15 > mode._layout["width"]))
        score = len(visible) * 12 - edge * 30 + sum(s.scale for s in visible)
        if score > best_score:
            best_score, best_t = score, t
        t += 2.0
    return best_t


def still(profile, slot, size, filename, extra=None, event=False):
    screen = pygame.Surface(size)
    mode = LanternProcessionMode(merged(profile, slot, extra))
    mode.enter(FakeManager(screen))
    if mode.error:
        raise SystemExit(f"mode refused its config: {mode.error}")
    moment = best_moment(mode)
    mode._time = moment
    mode._start_time = moment
    mode._event = None
    mode._next_event = float("inf")
    if event:
        states = mode._compute_states(moment, with_event=False)
        candidates = [s for s in states if 0.22 < s.u < 0.72 and s.dim > 0.6]
        if not candidates:
            raise SystemExit("no lantern available for the signature still")
        target = max(candidates, key=lambda s: s.scale)
        mode.start_departure(target.index)
        mode._time += 14.0          # late in the drift, the paper is dimming
    mode.render(screen)
    path = os.path.join(OUT, filename)
    pygame.image.save(screen, path)
    stats = mode.stats()
    print(f"{filename}: {size[0]}x{size[1]} preset={stats['preset']} "
          f"time={stats['time']:.1f} lit={stats['lit']} "
          f"event={stats['event']} ms_quality={stats['quality']}")
    mode.exit()


def main():
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    still("configs/modes_config_narrow_horz.json", "23", (1280, 400),
          "mode_lantern_1280x400.png")
    still("configs/modes_config_portrait.json", "28", (1080, 1920),
          "mode_lantern_1080x1920.png")
    still("configs/modes_config_narrow_horz.json", "23", (1280, 400),
          "mode_lantern_1280x400_lantern_out.png", event=True)

    # 16:9 sanity still from the same narrow instance; no profile entry yet.
    still("configs/modes_config_narrow_horz.json", "23", (1920, 1080),
          "mode_lantern_1920x1080.png",
          extra={"orientation": "landscape"})

    pygame.quit()


if __name__ == "__main__":
    main()
