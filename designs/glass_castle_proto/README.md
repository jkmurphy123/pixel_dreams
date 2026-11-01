# The Glass Castle — art-direction study

**Status:** implemented as `glasscastle` (`modes/glass_castle_mode.py` +
`glasscastle/`), with registry entries and instances in the narrow-horizontal,
portrait, vertical and canonical profiles. The stills below were reviewed
before the build; the hero stills are rendered by the **real mode**.

**Design card:** [`SLOW_WORLDS_DESIGN.md`](../SLOW_WORLDS_DESIGN.md) §5.13 —
`glasscastle` · fantasy · render H · build L · wave 3.

**The hero stills (real mode, seed 5130, t = 15 s)**

| File | Size | What it is |
|---|---|---|
| [`../../screenshots/glass_castle/hero_1280x400.png`](../../screenshots/glass_castle/hero_1280x400.png) | 1280×400 | the Pi strip; minimal HUD |
| [`../../screenshots/glass_castle/hero_1080x1920.png`](../../screenshots/glass_castle/hero_1080x1920.png) | 1080×1920 | the portrait wall; full HUD |
| [`../../screenshots/glass_castle/hero_1920x1080.png`](../../screenshots/glass_castle/hero_1920x1080.png) | 1920×1080 | the 16:9 sanity still |

The pre-code art studies remain at
[`study_1280x400.png`](../../screenshots/glass_castle/study_1280x400.png) and
[`study_1080x1920.png`](../../screenshots/glass_castle/study_1080x1920.png);
they are the reviewed composition, not the shipping renderer.

Both kinds are pinned to seed **5130** and t = **15 s**, the aurora's bright
moment, so the "lit from within" signature is visible in a single frame.

```bash
SDL_VIDEODRIVER=dummy ./.venv/bin/python scripts/glass_castle_preview.py
```

```bash
./.venv/bin/python designs/glass_castle_proto/gen_glass_castle.py
```

Only pygame and the system DejaVu fonts are used. Nothing is downloaded, and
the script writes to `screenshots/glass_castle/`.

---

## 1. What the stills show

**The strip.** The castle is the subject and the aurora is its weather. Three
depth layers, each with its own value range:

1. the far ridge and far towers (low contrast, snow caps);
2. the keep, flanking towers, curtain wall, plinth and gate towers (the glass
   read: a cool fill, a bright left rim, long internal facets, one warm gate);
3. the near cliff and rock shoulders (near-black, snow rims, a few facets).

The aurora is a low-resolution additive field of five overlapping curtains:
violet crown, teal body, mint hem, fine vertical rays. The castle's right-hand
faces carry a clipped copy of the same field, which is the "reflected inside the
glass" element from the card. Warm windows are sparse; the gate is the single
warm anchor.

The controller's lower-left 80×32 mode-number area is kept dark by composition
(both stills measure a peak of ~16/255 in that box). The title is DejaVu Serif
with tracking; the telemetry is mono, one line on the strip and one extra faint
line on the portrait.

**The portrait.** The same parts, re-anchored: a taller sky, a larger aurora
crown, a wider keep, and a cliff that occupies the lower quarter. The castle
was not scaled up from the strip; the keep, towers and wall are re-proportioned.
The strip's castle mass is scaled **1.40× horizontally / 1.18× vertically**
around its footing, in one transform at the end of the layout table
(`_scale_castle`), so a future size change stays in one place. The keep was
enlarged on review so it fills more of the 1280 px strip.

---

## 2. Palette

The study uses the **ice** variant of the shared **Aurora & Ice** family
(design doc §4.1). The semantic roles are:

| Role | Value | Use |
|---|---|---|
| background | `#050812` → `#0E172B` | sky gradient, tinted, never pure black |
| ink | `#E6F3F2` | title, crystal rims, snow highlights |
| structure | `#8E7CFF` | facet lines, shadowed violet faces |
| accent | `#58E0B8` | aurora body, live telemetry diamond |
| glow | `#BFF7E4` | aurora hem, tip glints, bloom source |
| warm | `#FFC480` | windows, gate, lantern-like warm spill |

The mode exposes three palettes, all changing mood only, never layout:

- `ice` (this study) — teal aurora, violet structure, amber windows;
- `aurora` — a hotter green/violet curtain with a rose horizon;
- `rose` — the fairy-tale variant: rose and pale gold aurora, warmer stone.

---

## 3. The card, element by element

| Card element | Still | In the mode |
|---|---|---|
| Camera drift, 0.5 px/s | static | each layer offset by a slow sine (far 0.35×, castle 0.55×, near 0.80×); 240 s cycle; the cached layers are cropped to their content bands and drift inside a wider canvas |
| Aurora, 60 s undulation | one bright frame | a reviewed base field is drifted, hue-shifted and breath-scaled at low resolution (4–6 Hz), then upscaled; the Pi never runs the per-pixel field per frame |
| Snow, two parallax layers, 8–16 px/s | two layers | 2 particle layers (far/slow, near/fast), seeded and a pure function of time; capped near the L budget |
| Windows, 3–7 s flicker | mixed on/off | per-window period and phase, deterministic from the seed; `window_lights` and `window_flicker` switches |
| Shards, 20–40 s orbit | 6 of the 8 study fragments | small polygons on elliptical paths around the keep, glint at the tip; `shard_count` 0–10 |
| Reflections | aurora clipped to the castle silhouette | the same low-res field masked by the castle silhouette and raised by the 47 s breath; `reflection_strength` 0–1 |
| Signature: aurora brightens and doubles inside | pinned at the bright moment | the 47 s breath raises both the curtain and the clipped reflection together for ~6 s |

The mode is a pure function of `(seed, elapsed)`. The still seed 5130 is only
for review; an unset seed gives a new scene on entry.

The moving sky is a drift, hue shift and breath on the reviewed base field
rather than a per-frame re-simulation of every curtain. At the 60 s timescale
it reads as the slow undulation; it is also what keeps the portrait wall inside
a sane frame budget.

---

## 4. Deliberately not in the stills

- No motion, flicker or orbit — a still is the poster-frame test, not a motion
  test. The mode needs a 10 s and a 5 min capture in review.
- No palette-variant stills (`aurora`, `rose`). The palettes are implemented;
  the review accepted the defaults, so only `ice` is shown here.
- No path, stair or other narrative furniture: an earlier switchback stair was
  cut because it turned the pure vista into a game level. The cliff stays a
  cliff.
- No external art, audio, network or data file.

---

## 5. How the mode is wired

### 5.1 Package + adapter

```text
glasscastle/
    __init__.py
    geometry.py      the reviewed reference data (1280x400 and 1080x1920)
    palette.py       ice / aurora / rose, semantic roles
    layout.py        reviewed reference -> real screen, safe rects
    aurora.py        base field, drift/hue/breath, low-res reflection source
    castle.py        towers, keep, wall, plinth, gatehouses, fins,
                     windows, shards, and the far/near/plateau layers
    snow.py          two parallax particle layers
    hud.py           title / telemetry / three corner ticks
    sprites.py       radial glows + the scaled-glow cache
    renderer.py      layer caches, composition, quality, bloom, finish
modes/glass_castle_mode.py
```

The cliff and ridge draw into `castle.py`'s layer builders; they were not
split into a separate module once the plateau, masses and buttresses became
part of the cached scene.

Adapter contract, same as every mode:

```python
class GlassCastleMode:
    def __init__(self, config: dict): ...
    def enter(self, manager): ...
    def exit(self): ...
    def handle_event(self, event): ...
    def update(self, dt): ...
    def render(self, screen): ...
```

Every layout decision lives in `layout.py`; the renderer never branches on
`W == 1280`. The orientation rule matches the other recent modes: `auto` picks
portrait when the display is taller than wide; explicit `landscape`/`portrait`
override it. The lower-left 80×32 stamp area is a reserved rect, and the tests
assert it stays below the brightness floor.

Performance shape (measured on the development host, headless):

- the far ridge, castle and near cliff are built once into three transparent
  layers, then cropped to their content bands so only the used pixels are
  blitted; each drifts at its own parallax multiplier inside a wider canvas;
- the castle's static mass, the ledge and the cliff are in those layers; the
  aurora reflection, warm windows, gate spill, shards and snow are per frame;
- the aurora field is built once, then drift/hue/breath are applied at low
  resolution and upscaled at 4–6 Hz; the scaled glow sprites are cached;
- `quality` changes snow density, aurora refresh, star count and bloom
  resolution — never camera, composition or timing;
- `auto` starts at medium and follows an EMA of frame time, like the other 3D
  modes.
- the 1280×400 strip runs ~13 ms/frame at medium (~75 fps) and ~14 ms at high
  on the development host; the 1080×1920 portrait runs ~42 ms at medium and
  ~21 ms at low, so `auto` settles on low for the wall. The Pi target is the
  strip; the portrait is the larger secondary target.

### 5.2 Registry entry

Type key `glasscastle`; `required: []`; `optional` exactly the keys the mode
reads (so the validator catches typos):

```text
title, subtitle, seed, palette, orientation, hud, quality,
aurora, snow, camera_drift, window_lights, shard_count,
aurora_period, window_flicker, reflection_strength, snow_speed,
glow_strength, scanline_alpha, vignette_strength
```

The design card's `detail` maps to the shared `quality` key, as in Long Archive.
The `params` block would give the panel: a `choice` for palette/orientation/hud/
quality, switches for aurora/snow/window lights, numbers for camera drift
(0–2 px/s), shard count (0–10), aurora period (20–180 s), window flicker
(0–1) and reflection strength (0–1), plus text for title/subtitle.

### 5.3 Profile slots

No renumbering; the next free slots at the time of writing:

| Profile | Next free | Proposed instance |
|---|---:|---|
| `configs/modes_config_narrow_horz.json` | **24** | `glasscastle`, orientation `landscape`, hud `minimal`, duration 150 |
| `configs/modes_config_portrait.json` | **29** | `glasscastle`, orientation `portrait`, hud `full`, duration 150 |
| `modes_config.json` | **36** | `glasscastle`, orientation `auto`, hud `full` |
| `configs/modes_config_vert.json` | **68** | the active portrait kiosk profile; `glasscastle`, orientation `portrait`, hud `full` |
| 16:9 profiles | — | not mirrored; the 1920×1080 sanity still comes from the preview script |

The profiles stay separate files, as the repo requires.

### 5.4 Preview and tests

- `scripts/glass_castle_preview.py` renders the hero stills **from the real
  mode**, pinning seed 5130 and t = 15 s so the review stills can be compared
  with the studies.
- `tests/test_glass_castle.py` pins:
  - both aspects construct and the composition is re-anchored, not stretched;
  - the controller's 80×32 corner stays dark;
  - seed reproducibility, and a different seed changes the scene;
  - palette variants change colour only, not geometry/timing;
  - aurora/snow/window switches actually remove their elements;
  - bad configs show the error panel instead of taking down the kiosk;
  - `quality` low/high leaves the camera and clocks unchanged;
  - registry schema and the new profile instances construct;
  - `exit()` releases surfaces and any caches (no thread exists).
- `python validate_configs.py --all` is green (0 errors; one pre-existing
  Windows-path warning in the status ticker).
- `SDL_VIDEODRIVER=dummy python -m pytest tests/test_glass_castle.py -q` is
  green (35 tests). The full suite has one unrelated, pre-existing failure in
  the untracked Lantern Procession mode's corner test.

### 5.5 Acceptance checklist

The stills cover the 1280×400 strip, the 1080×1920 portrait and the 1920×1080
sanity frame. Still to capture for final acceptance: a 10-second motion check
and a five-minute loop check, on the Pi strip and the portrait wall.

---

## 6. Review decisions

The review settled the open questions:

1. **Castle scale on the strip.** The keep was enlarged so the castle fills more
   of the frame: **1.40× / 1.18×** around its footing. Approved look for the
   build.
2. **Aurora brightness.** Lowered a little: the field gain moved from 0.90 to
   **0.78** and the airglow from 0.50 to 0.42. The castle now holds the frame
   against the sky.
3. **Portrait foreground.** The layered dark cliff is enough; no extra
   furniture (the switchback stair stays cut).
4. **Defaults accepted** for palette variants, 16:9 and shards. The `ice`
   palette is the review palette; `aurora` and `rose` are implemented but not
   stilled; the 1920×1080 sanity still is in the hero set; the shard count stays
   at the design card's 6.
5. **HUD.** Minimal on the strip, full on the portrait, as stilled.
