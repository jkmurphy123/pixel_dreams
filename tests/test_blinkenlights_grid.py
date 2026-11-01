"""
The blinkenlights grid is columns x registers_per_column — the label list only names it.

The panel used to draw by iterating `register_labels`, so a profile that asked for 2 columns of 16
registers and named 12 of them got one populated column of twelve rows (the layout spacing was
already 16 rows, so the registers also looked sparse), and the second column drew as an empty box
whatever `columns` said. Nothing refused the config: the mode simply drew fewer registers than the
profile described, which reads as "it won't let me have more than 12 per column".

It was also a latent crash: per-slot animation state was sized by the LABEL list while the draw loop
walked the SLOTS, so any grid larger than the label list indexed past the end of `_phases`. The
controller swallows a mode's per-frame exception, so that would have shown up as a frozen panel
rather than a traceback.

This file pins the grid behaviour, the label padding, the per-slot state, and the two sizing rules
that keep a tripled label legible (capped by its row) and the lamp dots from merging into a bar.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame                                                              # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modes.blinkenlights_mode import BlinkenlightsPanelMode                # noqa: E402

pygame.init()
pygame.font.init()

W, H = 1080, 1920
LABEL_RGB = (220, 220, 220)


class _Manager:
    """The minimum a mode reaches for: a surface, a font cache and its size."""

    def __init__(self, screen):
        from core.cache import ResourceCache
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def _render(config, size=(W, H), frames=4):
    # Other test modules call pygame.quit(), which shuts the font module down; re-arm it here
    # rather than depending on the order pytest happens to run this file in.
    if not pygame.font.get_init():
        pygame.font.init()
    screen = pygame.Surface(size)
    mode = BlinkenlightsPanelMode(config)
    mode.enter(_Manager(screen))
    for _ in range(frames):
        mode.update(1 / 60.0)
    mode.render(screen)
    return mode, screen


def _label_runs(screen, x0, x1, y0, y1):
    """How many separate horizontal bands of label ink this x-range holds."""
    buf = pygame.image.tostring(screen, "RGB")
    stride = screen.get_width() * 3
    needle = bytes(LABEL_RGB)
    runs = 0
    previous = None
    for y in range(y0, y1):
        if needle in buf[y * stride + x0 * 3: y * stride + x1 * 3]:
            if previous is None or y != previous + 1:
                runs += 1
            previous = y
    return runs


SHORT_LABELS = ["CLK", "IPTR", "ACC", "IR", "SP", "TMP",
                "MAR", "MDR", "PC", "FLAG", "ALU", "MMIO"]


def test_grid_size_not_the_label_list_decides_how_many_registers_exist():
    mode = BlinkenlightsPanelMode({"computer_name": "T", "columns": 2,
                                   "registers_per_column": 16,
                                   "register_labels": SHORT_LABELS})
    assert mode.register_slots == 32
    assert len(mode._slot_labels) == 32
    assert mode._slot_labels[11] == "MMIO"          # last supplied name, end of column 0
    assert mode._slot_labels[12] == "R12"           # padded, not blank
    assert mode._slot_labels[16] == "R16"           # column 1 starts here
    assert mode._slot_labels[31] == "R31"


def test_every_slot_gets_animation_state():
    """Sized by the grid: the draw loop walks slots, so state sized by labels indexes off the end."""
    mode = BlinkenlightsPanelMode({"computer_name": "T", "columns": 4,
                                   "registers_per_column": 16,
                                   "register_labels": SHORT_LABELS})
    assert mode.register_slots == 64
    assert len(mode._phases) == mode.register_slots * 8
    assert len(mode._register_bias) == mode.register_slots


def test_bursts_reach_registers_past_the_label_list():
    mode = BlinkenlightsPanelMode({"computer_name": "T", "columns": 2,
                                   "registers_per_column": 16,
                                   "register_labels": SHORT_LABELS,
                                   "burst_registers_range": [32, 32]})
    mode._start_burst(0.0)
    assert mode._burst_register_set == set(range(32))


def test_both_columns_are_drawn_with_sixteen_labelled_registers():
    """The reported symptom, measured on the drawn frame rather than inferred from the config."""
    mode, screen = _render({"computer_name": "T", "columns": 2, "registers_per_column": 16,
                            "label_font_scale": 0.09, "register_labels": SHORT_LABELS})
    geo = mode._panel_geometry()
    inner = geo["inner"]
    for col in range(mode.columns):
        x0 = inner.left + col * geo["col_width"]
        runs = _label_runs(screen, x0, x0 + geo["col_width"], inner.top, inner.bottom)
        assert runs == mode.registers_per_column, f"column {col} drew {runs} label runs"


def test_status_lamp_captions_have_their_own_size_and_stay_inside_the_lamp():
    """The RUN/MEM/... captions are their own scale, and never spill out of their lamp."""
    plain = BlinkenlightsPanelMode({"computer_name": "T"})
    plain.w, plain.h = W, H
    plain._recompute_scaled_metrics()
    assert plain._status_font_px == 16            # 0.015 x 1080: the size they always had
    assert plain._tiny_font_px == 16              # and the panel-ID/footer type is untouched

    big = BlinkenlightsPanelMode({"computer_name": "T", "status_font_scale": 0.045})
    big.w, big.h = W, H
    big._recompute_scaled_metrics()
    big.enter(_Manager(pygame.Surface((W, H))))
    geo = big._panel_geometry()
    lamp_h = geo["status"].height - 18
    lamp_w = 150
    font, px = big._status_font(lamp_w, lamp_h)
    assert px == 48                               # 0.045 x 1080 = 3 x the 16 px default
    assert max(font.size(lbl)[0] for lbl in big.status_labels) <= lamp_w - 12

    # A size the lamp cannot hold is capped rather than drawn over the neighbouring lamp.
    font, px = big._status_font(lamp_w, 40)
    assert px <= int(40 * 0.78)


def test_label_font_is_capped_by_the_row_it_sits_in():
    mode = BlinkenlightsPanelMode({"computer_name": "T", "label_font_scale": 0.09})
    mode.w, mode.h = W, H
    mode._recompute_scaled_metrics()
    assert mode._label_font_px == 97              # 0.09 x 1080: the "3x" the wall profile asks for
    assert mode._label_px_for_row(81) == 97       # 1.2 x 81 caps just above it: allowed
    assert mode._label_px_for_row(60) == 72       # a shorter row caps it, so rows never overlap
    assert mode._label_px_for_row(30) == 36

    tight = BlinkenlightsPanelMode({"computer_name": "T", "label_font_scale": 0.09,
                                    "label_font_row_fill": 1.0})
    tight.w, tight.h = W, H
    tight._recompute_scaled_metrics()
    assert tight._label_px_for_row(81) == 81


def test_lamp_dots_never_merge():
    """Spacing tightens first and stops at 2.15 radii; only then do the dots shrink."""
    mode = BlinkenlightsPanelMode({"computer_name": "T"})
    for avail in (40, 60, 100, 150, 200, 300, 600):
        dot_r, spacing = mode._fit_leds(avail, 15)
        assert spacing >= int(dot_r * 2.15), f"dots merge at avail={avail}"
        assert 7 * spacing + 2 * dot_r <= avail, f"bit row overflows at avail={avail}"
    # A wide row keeps the configured radius; a narrow one shrinks the dots.
    assert mode._fit_leds(600, 15)[0] == 15
    assert mode._fit_leds(100, 15)[0] < 15
