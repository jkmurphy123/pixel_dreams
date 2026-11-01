# Space Station V — design

A slowly turning double-ring station in front of a slowly turning wireframe Earth.
The visual reference is the orbital station in *2001: A Space Odyssey*: white
structural lines, amber habitat windows, black space, and a blue planet with
recognisable continents.  The film's station has one habitat wheel; this mode
uses the requested two rings on a shared hub, which also makes the rotation
read more clearly at kiosk sizes.

Registered as type `spacestation`, entrypoint
`modes.space_station_mode:SpaceStationMode`.  The drawing lives in the
`space_station/` package:

| module | role |
| --- | --- |
| `palette.py` | five palettes, one colour per semantic role |
| `stations.py` | procedural station mesh, four detail levels |
| `earth.py` | coastline loader, graticule, visible-hemisphere projection, planet disc |
| `framing.py` | aspect presets and anchor/radius resolution |
| `render.py` | frame composition, depth ramps, bloom, vignette/scanlines |
| `hud.py` | orbital telemetry, attitude dial, mission clock |
| `modes/space_station_mode.py` | config, clocks, adaptive quality, lifecycle |

## Composition

The station and Earth are framed independently, not as one 3D scene.  That is
deliberate: the station must stay large enough to show its detail while the
Earth is a background body whose limb runs off-frame.  `framing.py` has four
presets:

| preset | aspect | station | Earth |
| --- | --- | --- | --- |
| `ultrawide` | ≥ 2.2:1 | left, 0.34 of the short side | right, 0.70, limb below frame |
| `landscape` | ≥ 1.2:1 | left, 0.335 | lower right, 0.66 |
| `square` | 0.85–1.2:1 | left of centre, 0.30 | lower right, 0.58 |
| `portrait` | ≤ 0.85:1 | upper centre, 0.33 | lower half, 0.66 |

`orientation` pins a preset; `auto` chooses from the real screen aspect.
`station_scale` / `earth_scale` multiply the preset radii, and the four anchor
keys override the preset anchors when set.  The 1280x400 Pi profile pins
`orientation: "ultrawide"`, `hud: "minimal"` and a slower Earth.

## Station geometry

All coordinates are in ring radii; the rings sit at `z = ±0.5`, the spin axis
is `+Z`.  A `Builder` accumulates points and role-tagged edges:

* **Habitat rings** — two torus meshes, one bright outer equator, a dimmer
  inner equator, longitudinal and cross-section lines, and a band of short
  window dashes along the rim.  Major/minor counts come from the detail level.
* **Spokes** — six to twelve per ring, twin rails with alternating diagonal
  bracing, a service conduit, end caps into the hub and the rim.  The two
  rings' spoke sets are phase-offset so the wheels read separately.
* **Hub** — a ribbed cylinder across the ring separation, a wider central drum,
  end flanges with radial spiders, and an irregular band of lit windows.
* **Axial spine and docking module** — a thin service spine, a flared docking
  collar, four docking arms with pads, and a lit approach port with a crosshair.
* **Antenna boom and dish** — a rear dish with feed horn, plus three outrigger
  masts whose tips are beacons at the higher detail levels.
* **Rim detail** — service pods at uneven angles, a rim inspection rail with
  ties, four radiator fins between the spokes, and equipment boxes on the hub.

Four prebuilt levels:

| level | ring segments | extras | edges |
| --- | --- | --- | ---: |
| 1 | 40 × 5 | structural wheel only | 1,512 |
| 2 | 52 × 6 | windows, 2 pods, simple dish | 2,413 |
| 3 | 64 × 8 | rail, 4 pods, fins, full antenna | 3,788 |
| 4 | 80 × 8 | denser windows, 6 pods, all detail | 4,802 |

`station_detail` selects the base level.  Auto quality shifts it by −2/+1
(low/high), so a Pi in `low` draws the 1,512-edge wheel while a fast desktop in
`high` draws all 4,802 edges.

## Earth

`data/earth_coastlines.json` is generated from the public-domain Natural Earth
1:110m land polygons by `scripts/build_earth_coastlines.py`:

```bash
python scripts/build_earth_coastlines.py
```

The script simplifies each polygon ring with iterative Douglas–Peucker at
0.28°, drops rings below 2 square degrees, and stores 64 closed lon/lat rings
(2,189 points, about 32 KB).  That is enough for Africa, the Americas, Eurasia,
Australia, Greenland, Japan and New Zealand to be recognisable at every preset
size.  Relative paths resolve from the project root.

At runtime the rings become unit-sphere points once.  Each frame the points are
rotated by the Earth clock and its axial tilt, clipped to the visible
hemisphere (`z > 0`, with a horizon interpolation), and projected parallel to
the planet disc.  The disc is a one-off cached surface: opaque dark blue so
stars do not read through the planet, a limb atmosphere, and a thin lit edge.
Its radial gradient is built at a capped resolution and smoothscaled, then the
few atmosphere outlines are drawn at native size on top, which keeps entry
cheap at 1080p/4K without turning the limb into a wide blur.  The graticule is
rebuilt when the quality changes (30°/20°/15°).

A missing or malformed coastline file is not fatal: the mode logs one note,
draws the graticule and disc, and keeps running.  That is tested.

## Clocks

* `station_spin_rpm` — ring rotation, default 0.85 rpm (~71 s per revolution).
* `earth_rotation_seconds` — one full Earth rotation, default 300 s.

Both clocks run from `update(dt)` and wrap at 360°.  At the defaults the
station has turned about 1.2° and the Earth about 1.2° in one 60 fps frame;
the motion is slow enough to be a screensaver but visible whenever the mode
returns after a minute.

## Rendering

One frame:

1. vertical space gradient;
2. seeded starfield with a slow twinkle;
3. cached planet disc;
4. Earth graticule then coastlines, depth-coloured by a 33-entry ramp;
5. station at its effective detail, dim structure pass then bright
   hull/window/beacon pass;
6. one downscale-and-add bloom pass;
7. one baked multiply map for vignette, scanlines and the darker HUD bands;
8. HUD, drawn after the multiply map so the type stays crisp.

The station transform is a spin about `Z`, a tilt about `X` and a yaw about
`Y`, then a perspective divide with a configurable blend.  Depth is carried by
a per-role colour ramp, not a depth buffer: the wireframe is transparent by
design, and sorting thousands of edges every frame cost more than it added.
Beacons are the only per-edge pulse (there are 18 of them).

An Earth disc is cached per radius/palette; the station keeps four prebuilt
meshes in a small LRU cache keyed by detail and seed, so entering the mode with
a new random seed cannot leak meshes.

## Configuration

The registry entry in `modes_registry.json` lists every key with a widget,
range and help text.  The shape:

* **identity** — `title`, `subtitle`, `seed`, `palette`, `hud`
* **framing** — `orientation`, `station_scale`, `earth_scale`, four anchors
* **station** — `station_detail`, `station_spin_rpm`, `station_tilt_deg`,
  `station_yaw_deg`, `perspective_strength`
* **Earth** — `earth_rotation_seconds`, `earth_tilt_deg`,
  `earth_spin_offset_deg`, `show_continents`, `show_graticule`,
  `coastlines_file`
* **frame** — `show_stars`, `glow_strength`, `scanline_alpha`,
  `vignette_strength`
* **quality** — `quality` (auto/low/medium/high)

Profiles carrying an instance: `modes_config.json` slot 35,
`configs/modes_config_landscape.json` slot 13, `…_portrait.json` slot 25,
`…_vert.json` slot 63 (portrait, active profile) and
`…_narrow_horz.json` slot 19 (1280x400, minimal HUD, slower Earth).

## Performance and verification

At 1280x400 the medium tier draws about 5,800 visible segments in roughly
26 ms on the development host (about 38 fps; the full-screen finish and bloom
passes dominate, as they do in the existing wireframe modes).  At 1080p the
same tier is about 47 ms, or 21 fps, and the controller deliberately keeps the
medium wheel there rather than trading the whole drawing for four more frames:
it drops to low only below about 16 fps.  Low quality drops to the 1,512-edge
wheel, 30° graticule and an 8× bloom buffer; the bloom is upscaled in two
stages (smoothscale to half, nearest to native), which is visually clean and
much cheaper than a direct smoothscale to 1080p.

```bash
python pixel_dreams.py --play 63 --windowed
python pixel_dreams.py --config configs/modes_config_narrow_horz.json \
    --play 19 --windowed --width 1280 --height 400
python validate_configs.py --all
SDL_VIDEODRIVER=dummy python -m pytest tests/test_space_station.py -q
```

Preview frames: `screenshots/space_station/hero_1280x400.png`,
`hero_1920x1080.png`, `hero_1080x1920.png` and `motion_sheet.png`.

The data is Natural Earth (public domain); the station, HUD copy, palettes and
all other geometry are original to this project.
