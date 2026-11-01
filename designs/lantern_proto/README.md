# Lantern Procession — design prototype and built mode

**Status:** built. The shipping mode is `modes/lantern_procession_mode.py`, type
`lanternprocession`, wired at narrow slot **23**, portrait slot **28**, and the
portrait 1080x1920 variant at vert slot **67**. The previs generator in this
folder remains the art-direction record.

The design card asks for a line of paper lanterns winding through a dark forest
along the edge of a stream, with reflections, fireflies, and low mist — and one
signature moment: a lantern leaves the line, drifts down to the water, and goes
out while its reflection lingers.

## The built mode

| File | What it is |
|---|---|
| [`../../modes/lantern_procession_mode.py`](../../modes/lantern_procession_mode.py) | the mode (presets, cached forest/trail/water, lantern sprites, reflections, event, HUD) |
| [`../../scripts/lantern_preview.py`](../../scripts/lantern_preview.py) | renders the review stills from the real mode |
| [`../../tests/test_lantern_procession.py`](../../tests/test_lantern_procession.py) | framing, seed, sigil fallback, event, corner and cache tests |

Mode stills, rendered at native resolution by the mode itself:

| File | Size | What it is |
|---|---|---|
| [`../../screenshots/lantern_procession/mode_lantern_1280x400.png`](../../screenshots/lantern_procession/mode_lantern_1280x400.png) | 1280×400 | the narrow Pi strip |
| [`../../screenshots/lantern_procession/mode_lantern_1080x1920.png`](../../screenshots/lantern_procession/mode_lantern_1080x1920.png) | 1080×1920 | the portrait wall |
| [`../../screenshots/lantern_procession/mode_lantern_1280x400_lantern_out.png`](../../screenshots/lantern_procession/mode_lantern_1280x400_lantern_out.png) | 1280×400 | the signature moment, 13/14 lit |
| [`../../screenshots/lantern_procession/mode_lantern_1920x1080.png`](../../screenshots/lantern_procession/mode_lantern_1920x1080.png) | 1920×1080 | the 16:9 sanity preset (no profile entry) |

Run the mode previews with:

```bash
SDL_VIDEODRIVER=dummy .venv/bin/python scripts/lantern_preview.py
```

Built defaults: **moss** palette, 14 lanterns, 6 px/s, reflections and mist on,
a departure every ~120 s, `hud: "minimal"`. The two profile instances set
`hud: "full"` so the shipped wall keeps the eyebrow shown in the approved
stills; the type default stays minimal. The 16:9 preset is a sanity composition,
not a profile entry.

The shipping lanterns are **50% wider than the original previs study** (the
previs stills below are the reviewed 1× art-direction record). The static sky,
forest, trail, bank, water base and near framing are built once per size and
cached; only lanterns, glows, reflections, ripples, mist, fireflies and the
event are per-frame. The full-screen bloom is budgeted to frames under one
megapixel, so the strip gets it and the large portrait/16:9 frames rely on the
cached additive halos. Measured on the development machine after the size bump:
about 19–20 ms per frame at 1280×400 and 31–33 ms at 1080×1920 (the Pi
frame-time pass is still to do).

The rest of this document is the design record from before the build.

## The previs stills

| File | Size | What it is |
|---|---|---|
| [`../../screenshots/lantern_procession/lantern_1280x400.png`](../../screenshots/lantern_procession/lantern_1280x400.png) | 1280×400 | the Pi strip / ultrawide target |
| [`../../screenshots/lantern_procession/lantern_1080x1920.png`](../../screenshots/lantern_procession/lantern_1080x1920.png) | 1080×1920 | the portrait wall, re-composed |
| [`../../screenshots/lantern_procession/lantern_1280x400_lantern_out.png`](../../screenshots/lantern_procession/lantern_1280x400_lantern_out.png) | 1280×400 | the signature moment, on the strip |
| [`../../screenshots/lantern_procession/palette_study.png`](../../screenshots/lantern_procession/palette_study.png) | 1280×1260 | moss / indigo / mono, same layout |

Regenerate with:

```bash
SDL_VIDEODRIVER=dummy .venv/bin/python designs/lantern_proto/gen_lantern.py
# or one target:
SDL_VIDEODRIVER=dummy .venv/bin/python designs/lantern_proto/gen_lantern.py --only portrait
```

`gen_lantern.py` renders at 2× and downsamples; thin paper rims, sigils and the
reflection slices need the supersampling for a fair review. The mode itself
renders at native resolution and caches the static forest, the water and the
lantern sprites (see the implementation plan below).

## What the two orientations are doing

### The strip (1280×400)

The design card's schematic is a flat row of lanterns over a stream. On a
1280×400 strip that row reads as a shelf. The still instead uses the width as
distance:

- the trail enters at the left in mist, winds twice, and comes forward to the
  right;
- lanterns grow from about 10 px to about 45 px wide along that trail, so the
  procession is walking **towards** the viewer;
- the stream occupies the bottom band; the near lanterns' reflections are the
  brightest, the distant ones are only a smear;
- a near-black trunk at about 70 % width passes in front of the line, giving
  the eye something to go behind;
- the title sits top-left, telemetry top-right, and the lower-left 80×32 px
  stays dark for the controller's mode-number watermark.

This is a **re-composition, not a crop**: the portrait is not the strip
letterboxed.

### The portrait (1080×1920)

The portrait uses height as the path:

- the trail comes out of the trees near the top-right and descends in an S to
  the near bank at the bottom-left;
- the line is read top-to-bottom, with the largest lanterns at the water;
- the stream is a wide foreground band; the near bank is the reflecting edge, so
  the last few lanterns get a full, legible reflection instead of a tiny smear
  at the bottom of the frame;
- the title becomes a two-line serif lockup (`LANTERN` / `PROCESSION`);
- tall trunks frame the left and right edges, and the lower-left watermark
  corner stays clear.

This is the part worth reviewing first: if the portrait feels too tall or the
trail too dominant, the descent can be shortened or the waterline raised.

## The lantern

A lantern is a **sprite**, not a live drawing:

- a rounded paper body (a superellipse) with a vertical paper gradient, an
  amber core that is brightest low-centre, faint pleat ribs and a horizontal
  seam;
- a wooden top and bottom cap, a hanging ring, a thread and a tassel;
- an invented sigil stamped on the paper (eight procedural glyphs, no font or
  asset);
- a paper rim that catches a little moon-light on the upper-left;
- two additive glows — a tight hot core and a wide amber halo — plus a soft
  pool of light on the path and a warm streak in the water;
- a phase-offset bob and a few degrees of tilt.

The reflection is the same sprite, flipped, blurred, squashed, alpha-faded, and
sliced into horizontal bands that are offset by a sine ripple. On the strip it
is mirrored across the waterline. In the portrait it is anchored just past the
near bank (a screen-space cheat that keeps the reflection under its lantern,
where a literal mirror across the far waterline would throw the high lanterns'
reflections to the bottom of the frame).

## Palettes

`moss` is the design default and is keyed to the *Moon & Moss* family in
SLOW_WORLDS §4.1: near-black green, moss structure, amber accent, pale glow.
The variants change the mood, not the layout:

- **indigo** — cold moonlight, blue-green forest; the lanterns keep their
  warmth;
- **mono** — a sepia silver print with no green or blue;
- **moss** — the default.

## Things to review

1. **Strip composition.** The card says "a line of paper lanterns winds through
   the trees." The still turns that into a receding diagonal so the strip has
   depth. Is the diagonal right, or should it stay a flatter row across the
   frame like the card's schematic?
2. **Portrait reflections.** The portrait anchors reflections at the near bank
   instead of mirroring across the far waterline. It reads better; it is not
   physically literal. Keep it?
3. **The trail.** It is deliberately a dark, warm-lit trail rather than a bright
   path. Is it too visible, or not visible enough, on the Pi strip?
4. **The signature.** The third still shows one lantern below the line, dimmed,
   with a reflection that is still bright. The mode would play this over about
   18 s every 90–160 s. Is that the right frequency and emphasis?
5. **Forest density.** The forest is layered silhouettes, not individual
   leaves. It is deliberately quiet; does it need more trunk/branch detail on
   the portrait wall?
6. **Title face.** The title is DejaVu Serif Bold (the design suggests serif for
   fantasy); telemetry is mono. Keep the serif, or use the console mono for
   consistency with the other scenic modes?
7. **HUD.** The stills show the `SLOW WORLDS · FANTASY` eyebrow. The design
   recommendation is `minimal` by default; the eyebrow would move behind
   `hud: "full"`. Which default do you want?
8. **The moon.** There is no moon disc — only a faint cool glow behind the
   tree-line, so the lanterns remain the only bright objects. Is that the right
   call, or should a veiled moon be added?

## Implementation plan (after approval)

### 1. `modes/lantern_procession_mode.py`

One file to start, following the `OrreryMode` / `SunriseMode` adapter shape:

```python
class LanternProcessionMode:
    def __init__(self, config): ...
    def enter(self, manager): ...
    def handle_event(self, event): ...
    def update(self, dt): ...
    def render(self, screen): ...
    def exit(self): ...
```

No disk I/O, no network, no audio, no threads. The world is a pure function of
`(seed, layout, palette, elapsed time)`.

The module owns:

- **Layout presets** — `ultrawide` (1280×400), `landscape` (1920×1080),
  `portrait` (1080×1920), `square` (720×720). Each preset provides the path
  control points in fractions of the frame, the waterline, the lantern size
  range, the HUD sizes and the safe rectangles. `orientation: auto` picks by
  aspect, as the orrery does.
- **Palettes** — the three tables above, with five semantic roles each.
- **A seeded scene builder** — one `random.Random(seed)` for tree placement,
  firefly phases and the event schedule; Python's salted `hash` is never used.
- **A cached layer set** — sky, far tree-line, canopy, mid trunks, near frame,
  the path surface, the water base and the ripple overlay. Rebuilt only when
  the frame size, palette or quality changes.
- **Lantern sprites** — cached by `(sigil, half-width rounded to 2 px,
  palette)`; reflection sprites are the same cache entry flipped and faded.
- **A small event scheduler** — seeded departure times, never a per-frame
  random choice.

### 2. Rendering order (and what is cached)

1. cached sky gradient + pale mist behind the tree-line;
2. cached far tree-line and blurred far trunks;
3. cached mid trunks, canopy and understory;
4. cached path/trail surface (already masked at the ends);
5. cached water base + cached ripple strips, scrolled slowly;
6. reflections: flipped, sliced, rippled, clipped to the water (only the
   lanterns near the near bank in portrait);
7. cached mist bands, drifting at 0.5 px/s;
8. additive glows: pools on the trail, then each lantern's halo and core;
9. lantern sprites, depth-sorted far to near, with bob and tilt;
10. fireflies (cached glow sprites, blinking at 4–9 s periods);
11. cached near frame / boughs / ferns;
12. one half-resolution additive bloom, vignette + a very light grain;
13. crisp HUD text last.

The static forest is **never redrawn per frame**. The animated set is
lanterns, their glows and reflections, mist, fireflies, ripples and the bloom.

### 3. Motion

All motion accumulates in `update(dt)`; nothing assumes 60 fps.

- **Walk:** arc-length position `(offset + speed × t) mod length`. At 6 px/s on
  the strip (path ≈ 1,500 px) a full loop is about 250 s, and the spacing is
  arc-length even, so the line never visibly repeats.
- **Bob:** `sin(2π t / 3 + phase)` × 2–4 px, phase per lantern.
- **Tilt:** ±3°, phase-offset.
- **Flame:** the core glow's strength breathes at 1–2 Hz by a few percent;
  `flicker: false` removes it. No strobe, no full-frame flash.
- **Fireflies:** slow blink at 4–9 s and a 1–3 px/s drift.
- **Mist:** horizontal bands at 0.5 px/s.
- **Signature:** every `departure_seconds` (default 120, 0 disables) one
  lantern eases off the path over ~12 s, drifts to the water, dims to black over
  the last 6 s, and leaves its reflection for ~3 s. It then rejoins the line's
  far end. The decision is seeded, so `seed` reproduces the whole sequence.
- **Steps:** the HUD's fictional step count advances slowly with the
  procession; it is not tied to the real clock.

### 4. Registry, config and panel

Type key: **`lanternprocession`** (lowercase, no spaces/underscores), matching
SLOW_WORLDS Appendix C.

`modes_registry.json` (top-level `types.lanternprocession`):

```json
{
  "entrypoint": "modes.lantern_procession_mode:LanternProcessionMode",
  "required": [],
  "optional": [
    "title", "subtitle", "palette", "seed", "quality", "hud", "orientation",
    "lantern_count", "speed", "sigil_set", "reflection", "mist",
    "departure_seconds", "flicker", "glow_strength", "scanline_alpha",
    "vignette_strength"
  ],
  "params": { "...": "widget, group, default, range/choices, help" }
}
```

Signature parameters:

| Key | Default | Panel widget | Notes |
|---|---|---|---|
| `lantern_count` | 14 | number 8–20 | fewer reads as a lost line, more crowds the strip |
| `speed` | 6.0 | number 1–12 | px/s at 1280 wide; scaled by width/1280 |
| `sigil_set` | built-in | text/list | optional list of 1–3-character strings; malformed → built-in + one log |
| `reflection` | true | switch | stream reflections |
| `mist` | true | switch | low fog bands |
| `palette` | moss | choice | `moss`, `indigo`, `mono` |
| `quality` | auto | choice | `auto`, `low`, `medium`, `high`; the design card calls this `detail` |
| `seed` | null | number | unset = a new scene on entry, pinned = reproducible |
| `hud` | minimal | choice | `none`, `minimal`, `full` |
| `orientation` | auto | choice | `auto`, `ultrawide`, `landscape`, `portrait`, `square` |
| `departure_seconds` | 120 | number 0–600 | 0 disables the signature |
| `flicker` | true | switch | 1–2 Hz flame breath, no strobe |
| `title` / `subtitle` | per mode | text | portrait splits the default title at the space |
| `glow_strength`, `scanline_alpha`, `vignette_strength` | tuned | number | finish controls, same as the orrery |

Built placement (no existing slots were renumbered):

- `configs/modes_config_narrow_horz.json` — slot **23**
  (22 is the Long Archive entry);
- `configs/modes_config_portrait.json` — slot **28** (27 is Long Archive);
- `modes_config.json` — not added; the mode is in the two wall profiles only.
- `configs/modes_config_vert.json` — slot **67** (the "Portrait 1080x1920"
  variant), added after the first two walls were reviewed. The strip, portrait
  and vert profiles stay separate files.

Shipped instance (narrow slot 23; the portrait instance is identical with
`orientation: "portrait"`):

```json
"23": {
  "type": "lanternprocession",
  "name": "Lantern Procession",
  "palette": "moss",
  "hud": "full",
  "quality": "auto",
  "orientation": "ultrawide",
  "lantern_count": 14,
  "speed": 6.0,
  "reflection": true,
  "mist": true,
  "departure_seconds": 120,
  "duration": 150
}
```

`duration` is a real parameter (not structural) and 150 s matches the design's
"90–180 seconds for the scenic modes" rule rather than the 30 s console cycle.

### 5. Quality and the Pi

| Tier | Changes | Never changes |
|---|---|---|
| `low` | half the leaves/fluff, 8 reflection slices, no bloom, fewer fireflies, no grain | composition, palette, timing, lantern positions |
| `medium` | full geometry, 16 reflection slices, half-res bloom | composition, palette, timing |
| `high` | extra leaf clusters, 24 reflection slices, 4× bloom, grain | composition, palette, timing |

`auto` starts at medium and follows an EMA of frame time with hysteresis, the
pattern already used by Space Station V and Cyberspace. Draw budget target:
under ~2,500 blits/frame at 1280×400, 60 fps where possible and a 30 fps floor
on the Pi. The expensive pieces are the bloom and the sliced reflections; both
are tier-controlled and both degrade by detail, never by moving a lantern.

### 6. HUD, fonts and the controller's corner

- Cache every text surface; only the step counter changes (once per second).
- `hud: minimal` = title, subtitle, `NIGHT // N STEPS`, `LANTERNS 13 / 14`.
  `full` adds the `SLOW WORLDS · FANTASY` eyebrow. `none` leaves the scene.
- The title uses `manager.cache.get_font("dejavuserif", …, bold=True)`; the
  telemetry uses `dejavusansmono`, tracked +2. The portrait's default title is
  split into two lines; a custom title with `\n` is respected.
- The lower-left **80×32** stays free of detail and bright reflections. The
  previs keeps that corner as dark water/foreground reed.

### 7. Failure behaviour

- Missing/ill-typed keys fall back to the defaults; each fallback logs **once**
  with the `[Lantern]` prefix.
- A malformed `sigil_set` falls back to the built-in glyphs; a missing font
  falls back to the manager's default font; the scene is still complete.
- No network, no audio, no external asset, no file required.
- `exit()` drops the caches and any surfaces; no threads to join.

### 8. Tests and validation

Add `tests/test_lantern_procession.py`:

- default config, palette fallback and `sigil_set` fallback (log once);
- `seed` reproduces the same lantern positions and event schedule;
- a headless smoke render at 1280×400 and 1080×1920 under
  `SDL_VIDEODRIVER=dummy`, correct surface size, no exception;
- the lower-left 80×32 corner stays below a luminance threshold;
- `exit()` releases cache references.

Then:

```bash
SDL_VIDEODRIVER=dummy .venv/bin/python -m pytest tests/ -q
python validate_configs.py --all
python pixel_dreams.py --play 22 --windowed \
  --config configs/modes_config_narrow_horz.json
```

The panel needs no UI work: parameters are inferred from the instance config;
the registry `params` block supplies ranges, choices and help text.

### 9. Acceptance checklist

- [x] Composed still at 1280×400 with an empty mode-number corner.
- [x] Native 1080×1920 and 1920×1080, re-anchored rather than stretched or
      cropped from the strip.
- [ ] Ten-second glance shows motion; five minutes does not reveal an obvious
      loop.
- [ ] Every motion is inside the §2.1 envelope (walk ≤ 12 px/s, bob, 1–2 Hz
      flame, no flash).
- [ ] `seed` reproduces the scene; unset gives a new one.
- [ ] Palette variants change the mood, not the layout.
- [ ] `auto` quality changes detail, not composition or timing.
- [ ] `reflection`, `mist`, `flicker` and `departure_seconds` all work.
- [x] `validate_configs.py --all` is green.
- [x] Preview stills attached; a short motion capture is still to be made.

## Validation

`python validate_configs.py --all` is green (0 errors, the one pre-existing
`statusticker` missing-Windows-file warning). The earlier uncommitted orrery
type that was nested inside `types.sunrise` has since been lifted to a
top-level entry; the lantern entry was added at the top level too.

## Status / next steps

The mode, registry entry, two profile instances, preview script and tests are
in place. The remaining work is a **Pi frame-time pass**:

```bash
python pixel_dreams.py --play 23 --windowed \
  --config configs/modes_config_narrow_horz.json
python pixel_dreams.py --play 28 --windowed \
  --config configs/modes_config_portrait.json
```

If the Pi needs more headroom, the quality tiers and the bloom budget are the
first knobs; composition, lantern positions and timing are fixed.
