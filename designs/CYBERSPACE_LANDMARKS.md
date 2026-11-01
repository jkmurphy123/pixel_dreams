# Cyberspace landmarks — data format

The landmark layer is data, not code. `modes/cyberspace_mode.py` loads a JSON
file and `cyberspace/landmarks.py` turns each entry into wireframe geometry. To
add, remove, move or restyle a landmark, edit the JSON and refresh the mode. No
Python changes are needed.

Default file: `data/cyberspace_landmarks.json`
Mode parameter: `landmarks_file` (relative paths are from the project root)
Toggle: `show_landmarks`

## Coordinates

* `sector` is a ground cell `[ix, iy]`. The landmark origin is the **centre of
  that cell** at height `altitude`. With the default `street_spacing` of 80, the
  cell centre is 40 units from each of its four streets.
* Every part's `offset` is relative to that origin, and its `z` offset is the
  **base** of the part. A box grows upward from `offset.z`; a 120-unit cube at
  `[0, 0, 180]` hangs from z=180 to z=300.
* `clear_radius` (0–2, default 0) reserves a square of ground cells around the
  landmark as a plaza. Procedural towers and floating constructs are suppressed
  there, so a big form has an open silhouette. 0 reserves only the landmark's
  own cell.
* Keep a **ground** footprint inside one cell: roughly `|offset.x| + width/2 <=
  30` and the same for y at the default spacing. The camera flies along the cell
  boundaries, and that rule leaves the street corridor clear. A landmark high
  above the camera's maximum altitude can be much larger, because the camera
  never reaches it.

## Landmark fields

| field | meaning |
| --- | --- |
| `name` | full name, used in logs and the proximity feed |
| `label` | short HUD/world label (default: `name`; capped at 48 chars) |
| `sector` | `[ix, iy]` cell |
| `altitude` | base z of the landmark's local origin |
| `color` | `[r,g,b]` or `"#rrggbb"`; default colour for parts and the label |
| `glow` | neon intensity multiplier, 0.2–3.0 (default 1.25) |
| `spin` | degrees/second around the landmark origin (default 0) |
| `label_height` | label z relative to the origin; clamped to at least the top of the geometry |
| `clear_radius` | 0, 1 or 2 cells of reserved plaza (default 0) |
| `enabled` | `false` skips the entry |
| `parts` | one or more part objects (below) |

If `parts` is omitted, top-level `shape`, `size`, `offset` etc. can define a
single-part landmark.

## Part fields

Every part:

| field | meaning |
| --- | --- |
| `shape` | `box`, `pyramid`, `stepped_pyramid`, `octahedron`, `prism`, `ring`, `cage` |
| `offset` | `[x, y, z]` from the landmark origin; z is the part's base |
| `size` | `[width, depth, height]` for box/pyramid/stepped/octahedron/prism/cage |
| `color` | optional override of the landmark colour |
| `rotation_deg` | spin around the part's own vertical axis |

Shape-specific:

| shape | extra fields |
| --- | --- |
| `stepped_pyramid` | `steps` (1–16), `step_shrink` (0.35–0.97) |
| `prism` | `sides` (3–32) |
| `ring` | `radius`, `inner_radius`, `segments` (4–96), `spokes` (0–32) |
| `cage` | a box with face diagonals |

Bad entries are skipped with a warning in the log; one malformed part cannot
take down the whole mode. A missing file simply means no landmarks.

## Example

```json
{
  "name": "Eastern Seaboard Fission Authority",
  "label": "EASTERN SEABOARD",
  "sector": [5, 0],
  "altitude": 0,
  "color": [255, 64, 72],
  "glow": 1.35,
  "clear_radius": 1,
  "label_height": 180,
  "parts": [
    {"shape": "stepped_pyramid", "size": [62, 62, 160],
     "steps": 8, "step_shrink": 0.84},
    {"shape": "octahedron", "offset": [0, 0, 162],
     "size": [18, 18, 20], "color": [255, 180, 120]},
    {"shape": "ring", "offset": [0, 0, 2], "radius": 30,
     "inner_radius": 20, "segments": 24, "spokes": 6,
     "color": [255, 150, 100]}
  ]
}
```

## Detail

`geometric_detail` (1–4) controls the city.  Landmarks are loaded one level
higher (`min(5, geometric_detail + 1)`), so they always look more resolved than
their surroundings.  For boxes, stepped pyramids and cages that means the
volume lattice from the study.  Prisms get extra horizontal rings and a cap
star; octahedra get latitude rings; pyramids get additional latitude rings; and
rings get concentric sub-rings between the inner and outer radius.  Small parts
use a reduced effective level so a tiny accent box cannot dominate the budget.

## The ten shipped landmarks

| landmark | location | form |
| --- | --- | --- |
| Eastern Seaboard Fission Authority | `[5, 0]`, ground | stepped red pyramid with an octahedral cap and ground ring |
| Mitsubishi Bank of America | `[6, 0]`, z=120 | three green cubes with a wide halo ring, hanging above the street |
| Sense/Net | `[3, 0]`, ground | cyan octagonal double prism with a ring and a small cap |
| Tessier-Ashpool | `[2, -1]`, z=40 | violet twin towers, bridge and ring |
| Villa Straylight | `[5, 1]`, z=90 | amber stepped pyramid with a spire and ring |
| Wintermute | `[4, -2]`, z=70 | slowly turning white octahedron, cage cap and ring |
| Neuromancer | `[7, 1]`, z=240 | two gold concentric gate rings around an octahedron |
| Zion | `[1, 0]`, z=10 | green cluster of three boxes with a top ring |
| Maas Biolabs | `[6, -2]`, z=100 | magenta hexagonal double prism with a ring |
| Freeside | `[7, 5]`, z=300 | huge pale-gold double orbital ring with a hub |

Eastern, Mitsubishi, Sense/Net, Tessier-Ashpool and Zion clear a plaza
(`clear_radius: 1`) along the opening corridor, so their silhouettes are not
buried in procedural towers.

## How the camera uses them

When landmarks load, the route is softly bounded to the landmark district: past
a radius derived from their spread, the next horizontal leg points back toward
their centroid. It still moves one axis at a time and turns only on
intersections. This makes fixed-sector landmarks recur from different angles
instead of being left behind after the first minute.

The renderer draws landmarks before the procedural skyline, with bolder
anti-aliased lines and a stronger bloom. The three nearest visible landmarks are
listed in the HUD's `NAV // LANDMARKS` card, and the nearest one is announced in
the feed; world labels appear when their anchor is on screen.

When `landmark_overlay` is on (default), a bottom-right HUD inset shows the
**nearest** landmark within 420 units: its own edges are projected orthographically
and slowly rotated, with a floor ring, its short label, sector and range.  The
toggle is `landmark_overlay` in the control panel; switching it off leaves the
NAV card, feed announcements and world labels in place.  The inset is suppressed
on very small screens and in `minimal`/`off` HUD modes.
