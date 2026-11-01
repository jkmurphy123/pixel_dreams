"""Geometry and type scale for The Long Archive.

One wall, one plane.  The current slab is always 75% of the display width; the
remaining quarter is split between two narrow neighbours whose outer halves
run off-screen.  All panels share the same top and bottom line.

The layout is resolved from the real screen size, so the mode re-composes for
a 1280x400 strip, a 1080x1920 wall or a 1920x1080 display instead of cropping
one into another.
"""
from __future__ import annotations

from dataclasses import dataclass

from .glyphs import Slab, build_rows


@dataclass(frozen=True)
class Layout:
    name: str
    width: int
    height: int
    portrait: bool

    band_top: int
    band_bottom: int
    band_height: int

    active_x: int
    active_w: int
    gap: int
    side_visible: int
    side_full: int

    caption_gap: int
    caption_px: int
    caption_max_w: int

    margin: int
    title_px: int
    body_px: int
    small_px: int
    catalog_px: int

    glyph_cell: int
    glyph_pitch: int
    side_cell: int
    side_pitch: int

    bar_outer: int
    bar_core: float
    bar_spill: int
    lit_sigma: int
    slide_amp: int


def resolve_layout(size: tuple[int, int], orientation: str = "auto") -> Layout:
    """Build the layout for a screen and an orientation preference."""
    w = max(64, int(size[0]))
    h = max(64, int(size[1]))
    portrait = (orientation == "portrait"
                or (orientation == "auto" and h > w * 1.20))
    name = "portrait" if portrait else "landscape"

    active_w = max(80, int(round(w * 0.75)))
    gap = max(8, int(round(w * 0.019)))
    # 75% + two gaps must leave something for the neighbours.
    if active_w + 2 * gap >= w:
        gap = max(4, (w - active_w) // 3)
    side_visible = max(12, (w - active_w - 2 * gap) // 2)
    side_full = max(side_visible + 12, int(round(side_visible * 1.45)))
    active_x = side_visible + gap

    if portrait:
        band_top = int(round(h * 0.1875))
        band_bottom = int(round(h * 0.802))
        caption_gap = max(28, int(round(h * 0.030)))
        caption_px = max(12, min(30, int(round(min(w, h) * 0.026))))
        title_px = max(16, min(26, int(round(min(w, h) * 0.0235))))
        body_px = max(10, min(16, int(round(min(w, h) * 0.0140))))
        small_px = max(8, min(13, int(round(min(w, h) * 0.0112))))
        catalog_px = max(9, min(12, int(round(min(w, h) * 0.0103))))
        cell = max(7, min(22, int(round(active_w / 40.0))))
        pitch = max(9, int(round(cell * 1.27)))
        side_cell = max(7, int(round(cell * 0.72)))
        side_pitch = max(9, int(round(side_cell * 1.55)))
        bar_outer = max(36, int(round(w * 0.14)))
        bar_spill = max(10, int(round(h * 0.014)))
        slide_amp = max(0, int(round(w * 0.018)))
    else:
        band_top = int(round(h * 0.16))
        band_bottom = int(round(h * 0.82))
        caption_gap = max(18, int(round(h * 0.060)))
        caption_px = max(12, min(30, int(round(min(w, h) * 0.045))))
        title_px = max(16, min(26, int(round(min(w, h) * 0.040))))
        body_px = max(10, min(16, int(round(min(w, h) * 0.026))))
        small_px = max(8, min(13, int(round(min(w, h) * 0.020))))
        catalog_px = max(9, min(12, int(round(min(w, h) * 0.0225))))
        cell = max(7, min(22, int(round(active_w / 66.0))))
        pitch = max(9, int(round(cell * 1.07)))
        side_cell = max(7, int(round(cell * 0.72)))
        side_pitch = max(9, int(round(side_cell * 1.08)))
        bar_outer = max(36, int(round(w * 0.06)))
        bar_spill = max(10, int(round(h * 0.035)))
        slide_amp = max(0, int(round(w * 0.020)))

    band_top = max(24, min(h - 60, band_top))
    band_bottom = max(band_top + 40, min(h - 20, band_bottom))
    band_height = band_bottom - band_top

    # Pad values are derived in build_wall, where the slab is known; the
    # layout only carries what the renderer and HUD need.

    return Layout(
        name=name, width=w, height=h, portrait=portrait,
        band_top=band_top, band_bottom=band_bottom, band_height=band_height,
        active_x=active_x, active_w=active_w, gap=gap,
        side_visible=side_visible, side_full=side_full,
        caption_gap=caption_gap, caption_px=caption_px,
        caption_max_w=max(120, int(w * 0.86)),
        margin=max(16, int(min(w, h) * 0.036)),
        title_px=title_px, body_px=body_px, small_px=small_px,
        catalog_px=catalog_px,
        glyph_cell=cell, glyph_pitch=pitch,
        side_cell=side_cell, side_pitch=side_pitch,
        bar_outer=bar_outer, bar_core=max(3.0, round(bar_outer * 0.08, 1)),
        bar_spill=bar_spill,
        lit_sigma=max(60, min(150, int(round(active_w * 0.135)))),
        slide_amp=slide_amp,
    )


def build_wall(layout: Layout, seed: int) -> list[Slab]:
    """The three visible panels, in draw order (left, active, right)."""
    band_top = float(layout.band_top)
    band_bottom = float(layout.band_bottom)

    active = Slab(id=4, x=float(layout.active_x), width=layout.active_w,
                  top=band_top, bottom=band_bottom, brightness=1.0,
                  text_density=1.0, focus=True, label="TL-0447")
    left = Slab(id=3, x=float(layout.active_x - layout.gap - layout.side_full),
                width=layout.side_full, top=band_top, bottom=band_bottom,
                brightness=0.24, text_density=0.55)
    right = Slab(id=5,
                 x=float(layout.active_x + layout.active_w + layout.gap),
                 width=layout.side_full, top=band_top, bottom=band_bottom,
                 brightness=0.24, text_density=0.55)

    if layout.portrait:
        a_px = max(12, int(round(active.width * 0.032)))
        a_py = max(18, int(round(active.height * 0.025)))
        a_pb = max(30, int(round(active.height * 0.050)))
        s_px = max(6, int(round(left.width * 0.060)))
        s_py = max(8, int(round(left.height * 0.022)))
        s_pb = s_py
    else:
        a_px = max(10, int(round(active.width * 0.019)))
        a_py = max(10, int(round(active.height * 0.060)))
        a_pb = max(16, int(round(active.height * 0.130)))
        s_px = max(6, int(round(left.width * 0.060)))
        s_py = max(8, int(round(left.height * 0.050)))
        s_pb = s_py

    build_rows(active, seed, layout.glyph_cell, layout.glyph_pitch,
               a_px, a_py, a_pb)
    for slab in (left, right):
        build_rows(slab, seed, layout.side_cell, layout.side_pitch,
                   s_px, s_py, s_pb)
    return [left, active, right]
