# designs/arcane_proto/render_layout.py
#
# Render a freeform control-panel layout OFF the display and save a PNG, with the real mode
# class, the real loader and the real control classes. The point is to judge a layout — and
# measure it — without taking the wall from the user.
#
#   SDL_VIDEODRIVER=dummy python designs/arcane_proto/render_layout.py arcane_lab out.png 300
#
# Prints ms/frame for update+draw over the run, which is the number the design's budget (§9)
# is stated in. Snapshot happens BEFORE the timing loop's final frame is reused, so the image
# is a composed frame and not a benchmark's residue.

import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from controlpanel.layout import load_layout  # noqa: E402
from modes.control_panel_mode import ControlPanelMode  # noqa: E402


class _Cache:
    def get_font(self, name=None, size=20, bold=False):
        return pygame.font.Font(None, int(size))


class _Manager:
    """The minimum a mode needs: a screen, a font cache, an index."""

    def __init__(self, screen):
        self.screen = screen
        self.cache = _Cache()
        self.mode_index = 0
        self.registry = {}
        self.modes_config = {}
        self.width, self.height = screen.get_size()


def main():
    layout_arg = sys.argv[1] if len(sys.argv) > 1 else "arcane_lab"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "arcane_lab_render.png")
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    layout = load_layout(layout_arg)                 # also proves the document validates
    w, h = layout.design_resolution

    pygame.init()
    screen = pygame.display.set_mode((w, h))
    mode = ControlPanelMode({"layout_file": layout_arg, "scale_mode": "fit", "seed": 5})
    mode.enter(_Manager(screen))
    if mode.compositor is None:
        raise SystemExit(f"the mode failed to build: {mode._error}")

    for _ in range(60):                              # warm-up: caches, first-frame state
        mode.update(1 / 60)
        mode.render(screen)

    t0 = time.perf_counter()
    for _ in range(frames):
        mode.update(1 / 60)
        mode.render(screen)
    ms = (time.perf_counter() - t0) / frames * 1000.0

    pygame.image.save(screen, out)
    report = mode.layout_report()
    print(f"layout        {report['layout']} ({report['layout_file']}) mode={report['mode']}")
    print(f"artwork       {report['background_image']}")
    print(f"canvas        {report['canvas'][0]} x {report['canvas'][1]}")
    print(f"controls      {report['controls']} ({report['animated']} animated, "
          f"static-only {report['static_only']})")
    print(f"frame         {ms:.2f} ms/frame over {frames} frames -> {1000 / max(ms, 0.001):.0f} fps ceiling")
    print(f"wrote         {out}")


if __name__ == "__main__":
    main()
