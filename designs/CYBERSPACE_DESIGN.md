# Cyberspace Matrix — design

A mode that depicts the cyberspace of Gibson's *Neuromancer*: a neon wireframe
lattice stretching in all directions, with data centres and corporations as
bright geometric solids, seen from a viewpoint that drifts along one axis at a
time.

Registry type: `cyberspace`
Entrypoint: `modes.cyberspace_mode:CyberspaceMode`

## Visual language

- **The lattice is the stage.** Streets run along X and Y on the ground plane;
  vertical trunks and gate rings make the Z routes readable. The camera's own
  street is always drawn brighter than the grid around it.
- **Solids are wireframe, not shaded.** Towers are boxes, ziggurats, spires,
  octagonal prisms, twin towers, floating slabs, pyramids and lattice cages.
  There is no depth buffer: depth is carried by distance fade, line weight and
  the bloom, which is how cyberspace is usually imagined.
- **Neon palette.** Saturated cyan streets, magenta/violet megastructures, acid
  green data and hot orange-red ICE on near-black violet. Four variants
  (`phosphor`, `magenta`, `ice`, `amber`) give the same geometry a different
  fiction.
- **The HUD is a console, not a dashboard.** Coordinates, axis vector, speed,
  altitude, node/sector, a rolling technobabble feed, a reticle and a signal
  meter. The lower-left is kept clear for the controller's mode-number
  watermark.
- **Corporate labels.** The nearest tall towers and large constructs carry
  invented names; they are projected from world space and fade with distance.

## Flight

`cyberspace/camera.py` owns both halves:

- `Route` moves a **target** at constant speed along one axis. Horizontal legs
  are a whole number of blocks, so every turn happens on an intersection; a
  vertical leg every second turn climbs or descends to the other altitude band.
  Directions and leg lengths are seeded.
- `CameraRig` lags the target slightly (so corners are rounded through the open
  intersection), eases yaw/pitch, and banks into turns. During a Z leg the view
  keeps a shallow pitch and slowly yaws, so the city, the shaft rings and the
  floating constructs all pass the lens instead of turning into a tunnel.
- The route never enters a tower: buildings are inset from the street lines and
  constructs are clamped to the free space inside their cell.
- When a landmark file is loaded, the route is softly bounded to the landmark
  district: once it wanders past a radius derived from the landmarks' spread,
  the next horizontal leg points back toward their centroid.  It still moves one
  axis at a time and turns only on intersections, but the fixed landmarks recur
  from different angles instead of being left behind.

## World

`cyberspace/matrix.py` is deterministic from `(seed, cell, level)` and imports
no pygame, so the tests can inspect it headless.

- Ground cells are cached and pruned as the viewpoint moves. Empty cells become
  plazas with a neon ground ring.
- A cell's tower style, height, colour, rings, mullions, windows, mast and
  beacon come from a `random.Random` seeded by a stable integer mix (not
  Python's salted `hash`).
- Floating constructs (octahedra, cubes, spindles, prisms, gyroscopes, gates)
  live on a sparse 3-D lattice above the towers; their radius is clamped against
  the cell boundary so a horizontal leg cannot fly through one.
- Traffic packets, lane dashes, street nodes, vertical shafts, gate rings and
  the fine floor lattice are generated from the camera position each frame.
  Only the per-cell objects and constructs are cached.

## Geometric detail

`geometric_detail` selects a volume-lattice level for the procedural city:
level 1 is the original wireframe, and levels 2–4 split each box tower volume
into 2×2×2, 3×3×3 or 4×4×4 cells, drawing the surface and interior grid lines.
The dense mesh is built lazily and used only for towers inside the near-detail
radius; the radius shrinks a little at higher levels, and small landmark parts
get an effective level reduced by size so an accent cube cannot cost as much as
a tower.  Prisms, pyramids and octagonal towers get matching in-between ring
detail instead of a volume lattice.

Landmarks are loaded at `min(5, geometric_detail + 1)`: with the selected level
they always get one extra subdivision step.  The same detailed geometry feeds
the bottom-right landmark inset, so the inset shows the extra lattice too.

## Landmarks

Named, fixed-position structures come from a JSON file, not from code:
`data/cyberspace_landmarks.json` by default, overridable with the
`landmarks_file` parameter.  `cyberspace/landmarks.py` parses a small primitive
schema (box, pyramid, stepped pyramid, octahedron, prism, ring, cage) and parts
can be composed at offsets, so new landmarks are a config edit.  The format,
placement rules and the ten shipped forms are in
[`CYBERSPACE_LANDMARKS.md`](CYBERSPACE_LANDMARKS.md).

Landmarks reserve their ground cell (and optionally a plaza radius) so a
procedural tower cannot grow through them.  They are drawn before the
procedural skyline with bolder anti-aliased lines and a stronger bloom.  The
three nearest visible landmarks are listed in the HUD's `NAV // LANDMARKS`
card; the nearest is announced in the feed, and world-space labels appear when
their anchor is on screen.

## Rendering and budget

`cyberspace/render.py` draws at the display's native resolution; the HUD is
never upscaled, and there is no whole-scene supersampling buffer. The one
low-resolution surface is the bloom, which is smoothed to half size, scaled to
full, and added *behind* the line pass. The core wireframe is then drawn on top:
near edges go through `pygame.draw.aaline` (anti-aliased 1 px) with a small ink
lift to offset AA coverage, while far edges use the cheaper aliased raster. This
is the crispness trick: the bloom supplies the neon weight, the line supplies a
sharp edge, and the additive pass can no longer wash that edge out.

| quality | edge ceiling | bloom divisor | detail distance | traffic | constructs |
| --- | ---: | ---: | ---: | ---: | ---: |
| low | 2200 | 7 | 95 | 120 | 22 |
| medium | 3600 | 5 | 170 | 200 | 36 |
| high | 5400 | 4 | 260 | 300 | 52 |

`auto` starts at **medium on every screen** — the old pixel-count shortcut put a
1080p wall in the low-detail budget, which read as a resolution drop even though
the surface was native. An EMA of frame time steps down to low only below about
24 fps, and up to high above about 58 fps, with hysteresis. The screen finish
(vignette, scanlines and the darkened HUD bands) is baked into **one** multiply
map per resize; two full-screen alpha blits were the most expensive thing in the
first draft. Off-screen segments are rejected with a tight margin, which roughly
halved the draw calls at 1080x1920.

`crisp_lines` is a live switch: off uses plain 1–2 px lines for the whole core
and is slightly cheaper. It defaults on because the anti-aliased core is the
look. The crisp pass draws both the ordinary core and the hero (landmark) core,
with hero last and a wider dim underlay — bloom is optional, so landmarks and
their geometric detail must remain visible with `glow_strength: 0`.

Measured warm on the Jetson-class reference machine (2026-10, dummy video),
medium quality with the ten landmarks, by geometric-detail level:

| detail | 540x960 | 1080x1920 |
| --- | ---: | ---: |
| 1 | 25.3 ms | 36.3 ms |
| 2 | 26.2 ms | 37.2 ms |
| 4 | 30.7 ms | 41.5 ms |

## Parameters

The registry schema is the source of truth (`modes_registry.json` →
`cyberspace`). The dials are:

- **behaviour** — seed, travel speed, blocks per leg, quality, event rate
- **layout** — street spacing, city density, building height, construct
  density, draw distance, field of view
- **appearance** — palette, glow, scanlines, vignette, HUD mode, labels,
  traffic, reticle, crisp_lines, show_landmarks, landmark_overlay,
  geometric_detail
- **data** — title, subtitle, landmarks_file

Every control is live and typed: no raw JSON fields. `seed` is unset by default
so each entry is a different city; pinning a value reproduces one exactly and
the value in use is logged on entry.

## Lifecycle

- `enter()` builds the matrix, route, camera, renderer and HUD; the controller
  owns the display.
- No threads, no network and no disk I/O in the frame loop.
- `render()` rebuilds on resize and falls back to a themed error panel when a
  config is refused.
- `exit()` drops every surface and reference.

## Tests

`tests/test_cyberspace.py` pins the route invariants (all three axes, turns on
intersections, both altitude directions), seed reproduction, the orthonormal
camera basis, construct rotation, config refusal, auto/fixed quality, the typed
registry schema, the portrait profile slot, the shipped ten-landmark file,
data-only landmark addition, bad-entry skipping, reserved cells, the
district home bias, the inset toggle, volume-lattice detail and the landmark
level bump.
