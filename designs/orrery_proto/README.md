# The Orrery of Small Worlds — design notes and implementation

**Status:** implemented as `orrery` (`modes/orrery_mode.py`), with registry entry
and instances in the narrow-horizontal, portrait and 1080×1920 portrait/vert
profiles. The camera and
two-orientation framing were reviewed from the stills below before the mode was
built; the plaque text and its `show_plaque` switch are the final review change.

## The stills

| File | Size | What it is |
|---|---|---|
| [`../../screenshots/orrery/orrery_1280x400.png`](../../screenshots/orrery/orrery_1280x400.png) | 1280×400 | the Pi strip; plaque off |
| [`../../screenshots/orrery/orrery_1080x1920.png`](../../screenshots/orrery/orrery_1080x1920.png) | 1080×1920 | the portrait wall; plaque on |
| [`../../screenshots/orrery/orrery_1920x1080.png`](../../screenshots/orrery/orrery_1920x1080.png) | 1920×1080 | 16:9 sanity still (not a profile entry) |
| [`../../screenshots/orrery/camera_study.png`](../../screenshots/orrery/camera_study.png) | 1080×1758 | 13° / 19° / 27° camera study from the design prototype |

The three hero stills are rendered by the **real mode**, not by the design
prototype:

```bash
SDL_VIDEODRIVER=dummy .venv/bin/python scripts/orrery_preview.py
```

`designs/orrery_proto/gen_orrery.py` remains the design study that produced the
camera sheet. It is not the shipping renderer.

## The camera

The instrument is a disc of radius 1.0; the camera sits on a sphere looking at
its centre. A circular rail seen from elevation `e` projects to an ellipse with
**minor : major = sin(e)**:

| Target | Elevation | Oval ratio | Layout |
|---|---:|---:|---|
| 1280×400 strip | **16°** | 0.28 | wide plate, very wide ovals, HUD in the top corners, no vertical arch |
| 1080×1920 portrait | **33°** | 0.54 | rounder ovals, two-line title, meridian arch, system plaque |
| 1920×1080 (16:9) | 20° | 0.34 | wide preset, tested as a sanity still |
| square | 27° | 0.45 | wide preset |

The camera fit projects the plate, rails and arch, measures their 2D bounding
box and fits it to a safe rectangle. Changing tilt, aspect or screen size never
clips the instrument; only the margins change. The elevation and azimuth are
also config-overridable (`camera_elevation`, `camera_azimuth`; default `auto`).

The strip omits the meridian arch because a 400 px frame would clip it. The
portrait adds it. That is a re-composition, not a crop, and both keep the
controller's lower-left 80×32 mode-number corner clear.

## The plaque

The plaque is now a real switch, `show_plaque`, default **false**:

- `configs/modes_config_narrow_horz.json` (slot 21): `show_plaque: false`.
- `configs/modes_config_portrait.json` (slot 26): `show_plaque: true`.
- `configs/modes_config_vert.json` (slot 66): `show_plaque: true`.

It is visible on the parameter screen as a switch in the appearance group. Its
text is a made-up description of the system on display, not a maker's mark:

```text
THE AUREL SYSTEM
SEVEN INVENTED WORLDS · ONE LAMP AT THE FOCUS
PERIODS 47–239 s · INCLINATIONS 3°–12°
```

The world count and both ranges are read from the live instance, so a five- or
nine-world profile gets a truthful plate. The plate's ground colour follows the
palette. The curved Latin dedication on the instrument also follows the count
(`SEPTEM` / `QUINQUE` / `NOVEM` MUNDI · UNA LUCERNA).

## Implementation

`modes/orrery_mode.py` is one file, following the adapter shape used by Space
Station V:

- config validation with stable ranges; an invalid config sets `self.error` once
  and draws the mode's error panel;
- `enter` / `exit` / `update(dt)` / `render` / `handle_event`;
- no disk I/O, no network and no threads in the frame loop.

Performance shape:

- the room (gradient, haze, specks, floor rings), the plate (rim, graduations,
  engraving, Latin text, armature), the near/far rail layers, the vignette +
  scanline multiply map and the HUD/plaque text are cached on layout change;
- only worlds, moons, comet, dust, labels, the sun glow and the bloom are drawn
  per frame;
- `quality` changes rail subdivision (96/144/192), moons, dust and bloom
  resolution; the camera, composition and timing never change;
- `auto` starts at medium and follows an EMA of frame time, like the other 3D
  modes.

Worlds are a pure function of `(seed, time)`. The seed chooses the entry moment,
comet phase and dust; the world rails are a fixed instrument. The review still
pins seed 2001 and t=21 s. A conjunction is detected in screen space, shown for
8 s with a cooldown, and `show_conjunctions` can disable it.

Registry keys (all in `optional`, with widgets in `params`):

```text
title, subtitle, palette, seed, quality, hud, orientation,
world_count, orbit_seconds, show_labels, show_comet, show_conjunctions,
show_plaque, camera_drift, camera_elevation, camera_azimuth,
glow_strength, scanline_alpha, vignette_strength
```

The design card's `detail` maps to the shared `quality` key.

## Wiring and verification

| Profile | Slot | Plaque | HUD |
|---|---:|---|---|
| `configs/modes_config_narrow_horz.json` | 21 | off | minimal |
| `configs/modes_config_portrait.json` | 26 | on | full |
| `configs/modes_config_vert.json` | 66 | on | full |

The other profiles are unchanged.

Checks run:

```bash
python validate_configs.py --all
SDL_VIDEODRIVER=dummy .venv/bin/python -m pytest tests/ -q
```

`tests/test_orrery.py` covers the oval-ratio camera, all four target sizes,
seed reproducibility, the plaque switch and description, label clearance from
the lower-left corner, resize/re-entry, quality adaptation, registry schema and
both real profile instances.
