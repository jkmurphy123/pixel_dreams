"""Geometric-detail study — contact sheets, not part of the mode.

Generates comparison images for several ways of adding geometric detail to a
wireframe cube.  This script is deliberately standalone: it does not import the
cyberspace mode and changes nothing the app loads.

Run:
    python scripts/geometric_detail_study.py

Outputs (screenshots/cyberspace/detail_study/):
    detail_contact.png     six techniques × four levels
    detail_l4_compare.png  the same six at level 4, large
    detail_band_stack.png  the suggested band-stack technique, levels 1–6
"""
from __future__ import annotations

import math
import os

import pygame


OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "screenshots", "cyberspace", "detail_study")
os.makedirs(OUT, exist_ok=True)

AZIMUTH = math.radians(35.0)
ELEVATION = math.radians(22.0)
CAM_DIR = (math.sin(AZIMUTH) * math.cos(ELEVATION),
           math.cos(AZIMUTH) * math.cos(ELEVATION),
           math.sin(ELEVATION))

SIL = (100, 238, 255)
DET = (190, 112, 255)
DIAG = (255, 82, 210)
FILL = (8, 16, 30)
BG_TOP = (8, 4, 21)
BG_BOTTOM = (1, 1, 8)

FACES = (
    # (corner, u vector, v vector, normal) — u × v points outward
    ((-1, -1, 1), (2, 0, 0), (0, 2, 0), (0, 0, 1)),     # top
    ((-1, -1, -1), (2, 0, 0), (0, 2, 0), (0, 0, -1)),   # bottom
    ((1, -1, -1), (0, 2, 0), (0, 0, 2), (1, 0, 0)),     # +x
    ((-1, -1, -1), (0, 2, 0), (0, 0, 2), (-1, 0, 0)),   # -x
    ((-1, 1, -1), (2, 0, 0), (0, 0, 2), (0, 1, 0)),      # +y
    ((-1, -1, -1), (2, 0, 0), (0, 0, 2), (0, -1, 0)),    # -y
)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a, f):
    return (a[0] * f, a[1] * f, a[2] * f)


def face_point(face, u, v):
    corner, u_vec, v_vec, _normal = face
    return add(add(corner, mul(u_vec, u)), mul(v_vec, v))


def project(p, cx, cy, scale):
    x, y, z = p
    ca, sa = math.cos(AZIMUTH), math.sin(AZIMUTH)
    ce, se = math.cos(ELEVATION), math.sin(ELEVATION)
    rx = x * ca - y * sa
    ry = x * sa + y * ca
    sx = rx
    sy = z * ce - ry * se
    return (cx + sx * scale, cy - sy * scale)


def face_visible(face) -> bool:
    n = face[3]
    return n[0] * CAM_DIR[0] + n[1] * CAM_DIR[1] + n[2] * CAM_DIR[2] > 1e-6


# ---------------------------------------------------------------- techniques
#
# Every generator returns (segments, fills) where
#   segments = [(p1, p2, colour), ...]
#   fills    = [polygon, ...]
# The outer silhouette is always the same; the technique only adds detail.

def outer_edges():
    c = (-1, -1, -1)
    verts = [(x, y, z) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
    edges = []
    for i, a in enumerate(verts):
        for j, b in enumerate(verts):
            if j <= i:
                continue
            diff = sum(1 for k in range(3) if a[k] != b[k])
            if diff == 1:
                edges.append((a, b, SIL))
    return edges


def face_grid_segments(n: int):
    out = []
    for face in FACES:
        if n <= 1:
            continue
        for i in range(1, n):
            f = i / n
            out.append((face_point(face, f, 0.0), face_point(face, f, 1.0), DET))
            out.append((face_point(face, 0.0, f), face_point(face, 1.0, f), DET))
    return out


def band_stack(n: int):
    """The suggested technique: horizontal slices, one seam ring per cut."""
    seg = outer_edges()
    for i in range(1, n):
        z = -1 + 2 * i / n
        ring = [(-1, -1, z), (1, -1, z), (1, 1, z), (-1, 1, z)]
        for k in range(4):
            seg.append((ring[k], ring[(k + 1) % 4], DET))
    return seg, []


def face_grid(n: int):
    return outer_edges() + face_grid_segments(n), []


def floor_mullion(n: int):
    """Floor bands plus vertical ribs on the four walls, with a roof grid."""
    seg = outer_edges()
    for i in range(1, n):
        z = -1 + 2 * i / n
        ring = [(-1, -1, z), (1, -1, z), (1, 1, z), (-1, 1, z)]
        for k in range(4):
            seg.append((ring[k], ring[(k + 1) % 4], DET))
    for i in range(1, n):
        f = -1 + 2 * i / n
        for x, y in ((1, f), (-1, f), (f, 1), (f, -1)):
            seg.append(((x, y, -1), (x, y, 1), DET))
    # roof grid only — the walls are bands and ribs, not a full mesh
    top = FACES[0]
    for i in range(1, n):
        f = i / n
        seg.append((face_point(top, f, 0.0), face_point(top, f, 1.0), DET))
        seg.append((face_point(top, 0.0, f), face_point(top, 1.0, f), DET))
    return seg, []


def volume_lattice(n: int):
    """N×N×N cells: a full internal grid, with interior edges dimmed."""
    seg = outer_edges()
    for axis in range(3):
        for i in range(n + 1):
            for j in range(n + 1):
                p0 = [0.0, 0.0, 0.0]
                p1 = [0.0, 0.0, 0.0]
                p0[axis] = -1.0
                p1[axis] = 1.0
                other = [k for k in range(3) if k != axis]
                p0[other[0]] = p1[other[0]] = -1 + 2 * i / n
                p0[other[1]] = p1[other[1]] = -1 + 2 * j / n
                interior = not (i in (0, n) and j in (0, n))
                seg.append((tuple(p0), tuple(p1), DET if interior else SIL))
    return seg, []


def truss_grid(n: int):
    seg = face_grid(n)[0]
    for face in FACES:
        for i in range(n):
            for j in range(n):
                u0, u1 = i / n, (i + 1) / n
                v0, v1 = j / n, (j + 1) / n
                if (i + j) % 2 == 0:
                    a = face_point(face, u0, v0)
                    b = face_point(face, u1, v1)
                else:
                    a = face_point(face, u1, v0)
                    b = face_point(face, u0, v1)
                seg.append((a, b, DIAG))
    return seg, []


def veil_panels(n: int):
    """Only the visible faces are filled and gridded: the solid option."""
    if n <= 1:
        return outer_edges(), []
    seg = []
    fills = []
    for face in FACES:
        if not face_visible(face):
            continue
        poly = [face_point(face, 0.0, 0.0), face_point(face, 1.0, 0.0),
                face_point(face, 1.0, 1.0), face_point(face, 0.0, 1.0)]
        fills.append(poly)
        for i in range(1, n):
            f = i / n
            seg.append((face_point(face, f, 0.0), face_point(face, f, 1.0), DET))
            seg.append((face_point(face, 0.0, f), face_point(face, 1.0, f), DET))
        for k in range(4):
            seg.append((poly[k], poly[(k + 1) % 4], SIL))
    return seg, fills


TECHNIQUES = (
    ("BAND STACK", "one seam ring per floor — closest to the suggestion", band_stack),
    ("FACE GRID", "every face divided N × N", face_grid),
    ("VOLUME LATTICE", "N × N × N cells, interior edges dimmed", volume_lattice),
    ("FLOOR & MULLION", "floor rings + wall ribs + roof grid", floor_mullion),
    ("TRUSS GRID", "face grid plus alternating diagonals", truss_grid),
    ("VEIL PANELS", "visible faces filled, then gridded — solid", veil_panels),
)


# ---------------------------------------------------------------- rendering

def gradient(size, top, bottom):
    surf = pygame.Surface(size).convert()
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        c = (int(top[0] + (bottom[0] - top[0]) * t),
             int(top[1] + (bottom[1] - top[1]) * t),
             int(top[2] + (bottom[2] - top[2]) * t))
        pygame.draw.line(surf, c, (0, y), (size[0], y))
    return surf


def draw_cube(surface, center, scale, technique, level, labels=True, cell=None):
    """Draw one cube; returns the number of line segments."""
    cx, cy = center
    seg, fills = technique(level)

    # translucent visible faces
    if fills:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for poly in fills:
            pts = [project(p, cx, cy, scale) for p in poly]
            pygame.draw.polygon(overlay, (*FILL, 208), pts)
        surface.blit(overlay, (0, 0))

    projected = []
    for a, b, color in seg:
        p1 = project(a, cx, cy, scale)
        p2 = project(b, cx, cy, scale)
        projected.append((p1, p2, color))

    # wide, dim halo first, then the crisp core
    for p1, p2, color in projected:
        halo = (color[0] // 7, color[1] // 7, color[2] // 7)
        pygame.draw.line(surface, halo, p1, p2, 4)
    for p1, p2, color in projected:
        pygame.draw.aaline(surface, color, p1, p2)
    return len(seg)


def label(surface, font, text, pos, color, anchor="left"):
    surf = font.render(text, True, color)
    rect = surf.get_rect()
    if anchor == "center":
        rect.center = pos
    elif anchor == "right":
        rect.topright = pos
    else:
        rect.topleft = pos
    surface.blit(surf, rect)
    return rect


def contact_sheet():
    W, H = 2200, 1740
    canvas = gradient((W, H), BG_TOP, BG_BOTTOM)
    title_font = pygame.font.SysFont("dejavusansmono", 40, bold=True)
    sub_font = pygame.font.SysFont("dejavusansmono", 21)
    name_font = pygame.font.SysFont("dejavusansmono", 23, bold=True)
    note_font = pygame.font.SysFont("dejavusansmono", 14)
    level_font = pygame.font.SysFont("dejavusansmono", 16, bold=True)
    count_font = pygame.font.SysFont("dejavusansmono", 13)

    label(surface=canvas, font=title_font,
          text="CYBERSPACE  //  GEOMETRIC DETAIL STUDY",
          pos=(44, 32), color=(210, 250, 255))
    label(canvas, sub_font,
          "Same unit cube at four detail levels.  Cyan = silhouette.  "
          "Violet = added geometry.  Magenta = bracing.",
          (46, 82), (110, 190, 210))

    left = 390
    col_w = (W - left - 36) / 4
    top = 145
    row_h = (H - top - 52) / 6
    cube_scale = min(row_h * 0.33, col_w * 0.17)

    for c, header in enumerate(("LEVEL 1  ·  BASIC", "LEVEL 2",
                                "LEVEL 3", "LEVEL 4")):
        x = left + col_w * c + col_w / 2
        label(canvas, level_font, header, (x, top - 34),
              (120, 220, 240) if c else (235, 255, 255), "center")
        pygame.draw.line(canvas, (28, 74, 96),
                         (left + col_w * c + 14, top - 8),
                         (left + col_w * (c + 1) - 14, top - 8), 1)

    for r, (name, note, technique) in enumerate(TECHNIQUES):
        y0 = top + r * row_h
        cy = y0 + row_h / 2 - 8
        label(canvas, name_font, f"{r + 1:02d}  {name}", (48, y0 + 38),
              (220, 250, 255))
        label(canvas, note_font, note, (48, y0 + 70), (100, 150, 175))
        for c, level in enumerate((1, 2, 3, 4)):
            cx = left + col_w * c + col_w / 2
            pygame.draw.rect(canvas, (18, 38, 54),
                             (left + col_w * c + 12, y0 + 8,
                              col_w - 24, row_h - 18), 1)
            count = draw_cube(canvas, (cx, cy), cube_scale, technique, level,
                              cell=(left + col_w * c, y0, col_w, row_h))
            label(canvas, count_font,
                  f"{count} edges" + ("  ·  filled" if technique is veil_panels and level > 1 else ""),
                  (cx, y0 + row_h - 20), (90, 150, 175), "center")

    footer = ("Detail is the number of divisions along an axis.  "
              "Level 1 is the existing basic cube for every technique.")
    label(canvas, note_font, footer, (48, H - 34), (90, 145, 165))
    pygame.image.save(canvas, os.path.join(OUT, "detail_contact.png"))
    print("wrote detail_contact.png")


def l4_compare():
    W, H = 2000, 1180
    canvas = gradient((W, H), BG_TOP, BG_BOTTOM)
    title_font = pygame.font.SysFont("dejavusansmono", 36, bold=True)
    sub_font = pygame.font.SysFont("dejavusansmono", 19)
    name_font = pygame.font.SysFont("dejavusansmono", 22, bold=True)
    count_font = pygame.font.SysFont("dejavusansmono", 14)
    label(canvas, title_font, "LEVEL 4  //  TECHNIQUE COMPARISON",
          (42, 28), (210, 250, 255))
    label(canvas, sub_font,
          "Pick a technique.  The same level-4 cube is shown large enough to judge the surface.",
          (44, 74), (110, 190, 210))

    cols, rows = 3, 2
    cell_w, cell_h = W / cols, (H - 120) / rows
    for i, (name, note, technique) in enumerate(TECHNIQUES):
        cx = cell_w * (i % cols) + cell_w / 2
        cy = 120 + cell_h * (i // cols) + cell_h / 2 - 16
        pygame.draw.rect(canvas, (18, 38, 54),
                         (cell_w * (i % cols) + 10, 120 + cell_h * (i // cols) + 6,
                          cell_w - 20, cell_h - 20), 1)
        count = draw_cube(canvas, (cx, cy), 122, technique, 4)
        label(canvas, name_font, f"{i + 1:02d}  {name}", (cell_w * (i % cols) + 28,
                                                          120 + cell_h * (i // cols) + 28),
              (220, 250, 255))
        label(canvas, count_font,
              f"{count} edges" + ("  ·  visible faces filled" if technique is veil_panels else ""),
              (cx, 120 + cell_h * (i // cols) + cell_h - 34), (100, 160, 185), "center")
        label(canvas, count_font, note, (cell_w * (i % cols) + 28,
                                         120 + cell_h * (i // cols) + 56),
              (95, 145, 170))
    pygame.image.save(canvas, os.path.join(OUT, "detail_l4_compare.png"))
    print("wrote detail_l4_compare.png")


def band_stack_sheet():
    W, H = 1800, 520
    canvas = gradient((W, H), BG_TOP, BG_BOTTOM)
    title_font = pygame.font.SysFont("dejavusansmono", 30, bold=True)
    sub_font = pygame.font.SysFont("dejavusansmono", 18)
    label(canvas, title_font, "BAND STACK  //  THE SUGGESTED TECHNIQUE",
          (36, 24), (210, 250, 255))
    label(canvas, sub_font,
          "N horizontal slices, one seam ring per cut.  This is the cheapest way to add vertical read.",
          (38, 64), (110, 190, 210))
    cell_w = W / 6
    for i, level in enumerate((1, 2, 3, 4, 5, 6)):
        cx = cell_w * i + cell_w / 2
        count = draw_cube(canvas, (cx, 300), 94, band_stack, level)
        label(canvas, sub_font, f"N={level}", (cx, 430), (220, 250, 255), "center")
        label(canvas, sub_font, f"{count} edges", (cx, 458), (90, 150, 175), "center")
    pygame.image.save(canvas, os.path.join(OUT, "detail_band_stack.png"))
    print("wrote detail_band_stack.png")


def main():
    pygame.init()
    pygame.display.set_mode((64, 64))
    contact_sheet()
    l4_compare()
    band_stack_sheet()
    pygame.quit()


if __name__ == "__main__":
    main()
