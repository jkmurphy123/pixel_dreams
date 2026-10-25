# Arcane Laboratory — an arcane variant of the control-panel mode

**Status: P1 + P2 + P3 implemented, green, and LIVE on the wall (2026-10-17) as slot `57` "Arcane
Laboratory" (12 overlays). All eight types exist.**
**Approved:** artwork is user-supplied (path A) with a grey-box placeholder built in parallel; v1 is the
full eight types (nothing deferred); registry type stays `controlpanel`; portrait 1080×1920 only;
warm-palette class defaults.
Target: a new SLOT on the wall (`configs/modes_config_vert.json`, 1080 × 1920 portrait; the profile
holds slots 0–56 today, so the new one is `"57"`), type `controlpanel`, layout `arcane_lab` over an
arcane-laboratory painting, plus a set of new arcane control TYPES in the existing `controlpanel`
package.

Wall facts this design is measured against (read from the running app, `GET /api/status`, 2026-10-17):
`display: fullscreen`, `xrandr` `DP-1 connected primary 1080x1920+0+0 left`, `fps 62.4`,
active profile `configs/modes_config_vert.json`, current mode `ControlPanelMode` showing layout
`Scifi` over `scifi_panel.png` — canvas `1080 × 1920` (identical to the screen, so the compositor does
no per-frame scaling), 32 controls, all 32 animated.

Baseline before any of this: `SDL_VIDEODRIVER=dummy pytest tests/ -k "control or layout"` → 136
passed.

---

## 0. The answer in one paragraph

**Do not build a new mode, and do not fork the package.** Add arcane control TYPES to the existing
`controlpanel` package and put them in a new freeform layout over a new painting. The layout loader,
the compositor, the mode class, and *every* tool in the panel (add-overlay dialog, colour pickers,
alignment page, nudge pad, freeze, marker, duplicate, remove, backup-on-save, `/api/layout`) are all
driven by four lookup tables, so a new type inherits the entire tool chain for free and there is no
second implementation of anything. The work is: **one new module of animation classes (~8 classes,
~900 lines with shared helpers), 8 rows in `sprite_defs.json`, 3 table entries per type, one layout
JSON, and one background PNG.** No change to `modes/control_panel_mode.py`, `controlpanel/layout.py`,
`controlpanel/compositor.py`, or `panel/app.py` is required for v1.

A second, even cheaper ladder is available: an arcane layout using **only existing types** (lamps as
candle glows, radar as an astrolabe, gauge as a dial, scope as a ley-line trace) can be on the wall in
about an hour with zero new code. The recommendation below keeps that as the first rung so the wall is
never blocked on the animation work.

---

## 1. What already exists, and why it is the growth point

### 1.1 The pipeline (one pass, measured)

```
layout JSON ──load_layout()──> Layout{design_resolution, controls:[PlacedControl(rect_px, raw spec)]}
                    │
mode.enter() ──Compositor.build()──> static canvas (background PNG, or skin sprites in grid mode)
                    │
mode.make_control(placed) ──> Control subclass instance, one per animated type
                    │
per frame: canvas.copy → control.draw_overlay(frame) → marker → blit/scale to screen
```

- Freeform layouts are exact pixel rects over a full-bleed PNG (`controlpanel/layout.py:218–297`),
  and in freeform mode **no sprites are blitted at all** — controls draw only their overlay on top of
  the artwork (`controlpanel/compositor.py:79–84`). That is exactly the model an arcane scene needs:
  the painting carries the room, the code carries the light.
- The mode is layout-driven and generic: it builds controls by index, publishes `layout_report`, and
  implements the live-edit hooks (`modes/control_panel_mode.py:77–216`). Nothing in it names a
  specific control type.
- At the wall's resolution canvas == screen, so per frame the compositor does one full-surface copy
  plus the overlays (`compositor.py:110–114`). The 62 fps figure above is with that copy and 32
  overlay draws.

### 1.2 The four tables a new type must touch (and nothing else)

| Table | File | What it decides |
|---|---|---|
| `CONTROL_TYPES` | `controlpanel/registry.py:8` | type key → default sprite ID |
| `CONTROL_CLASSES` | `controlpanel/controls/__init__.py:20` | type key → animation class |
| `COLOUR_KEYS` | `controlpanel/controls/__init__.py:61` | type key → the `*_rgb` keys its class reads (drives the panel's colour pickers) |
| `sprites` | `assets/control_panel/sprite_defs.json` | sprite ID → footprint in cells on the 2048×2048 sheet |

Everything downstream reads those tables:

- **The alignment/editor page** builds its overlay list (index, type, sprite, rect), the clickable
  boxes over the artwork, the nudge pad, freeze, marker, duplicate and remove from the layout
  document alone (`panel/app.py:1596–1700`). Type-agnostic.
- **The Add-overlay dialog** offers `sorted(set(CONTROL_CLASSES) | {"plate"})` and reads each type's
  one-line description **out of the class docstring** (`panel/app.py:1943–1961`, `_control_blurb`
  at `:2238`). New types appear in the dialog automatically, with their blurb, if the class has a
  docstring.
- **The colour pickers** come from `COLOUR_KEYS` (`panel/app.py:1688–1697`), and
  `tests/test_control_edit.py:84–98` enforces that table against the source in both directions — the
  table may not offer a key the class does not read, and must offer every key its own code reads.
- **`POST /api/layout`** (script-driven nudging) gates on the mode publishing a `layout_report`, not
  on a mode type name (`panel/app.py:800–830`), so a subclass or a same-type layout is drivable the
  same way.
- **Adding controls/colours from the page writes the layout file and posts `refresh_mode`** — the
  layout is live-editable and positional changes never need a restart.

### 1.3 The contract every control class already obeys

From `controlpanel/controls/base.py`:

- `self.rect` is the pixel box; anything derived from it (centre, radius, window) must be recomputed
  in `_recompute_geometry()`, which `__init__` *and* `set_rect()` call. Assigning `self.rect` alone
  leaves a control drawing in its old place — measured at 13/13 and 12/12 controls in the two shipped
  freeform layouts, which is why `tests/test_layout_align.py:96` walks every class in the catalogue.
- Colours resolve as `color` → type-specific `*_rgb` key → default, via `self._color(...)`.
- `update(dt)` then `draw_overlay(surface)`; the surface is the design-space frame.

---

## 2. The design

### 2.1 Decisions

**D1 — Extend `controlpanel`; do not fork a package.** A forked `arcanelab/` would need its own
layout loader, compositor, editor and mode wrapper: four copies of code that is already generic, plus
a second writer of layout files. Rejected. A same-package extension means the arcane lab and the sci-fi
panel stay behaviourally identical and both keep benefiting from fixes.

**D2 — Keep the registry type `controlpanel`; the wall's mode is a new *instance*.** The existing
profiles already do this (`modes_config.json` slots 28/29, `configs/modes_config_portrait.json` slot
20, `configs/modes_config_vert.json` slots 45 `Portrait` and 55 `Scifi`). Consequences: no new
registry type, no pinned-type-count churn in the tests, no duplicate `required`/`optional` schema to
keep in sync. The instance gets a `name` so the panel lists it as "Arcane Laboratory".
*Alternative if the type label matters in the UI:* a second registry type `arcanelab` pointing at the
same `modes.control_panel_mode:ControlPanelMode` with `type_config` defaults. That is ~1 hour plus
registry-count test updates; not recommended for v1 (see Q3).

**D3 — All arcane types draw entirely procedurally, and their default sprites are new entries in the
empty sheet rows.** A freeform layout never blits sprites, but the loader still requires every control
to name a sprite that exists in `sprite_defs.json` (`layout.py:120–136`). Appending arcane sprite IDs
in rows 12–15 (the sheet's empty region, which the file's own comment reserves for new sprites) costs
nothing and keeps the loader untouched, instead of teaching `_check_common` that `sprite` is optional
for some types. Footprints stay inside the whitelist in `geometry.py:23`.

**D4 — Palette lives in the layout document, not in code.** Every class takes its colour from `color`
or its own `*_rgb` key, so retheming the lab (candlelight amber vs. sickly green) is editing the
layout in the panel's colour pickers, not editing Python. Class defaults are the ones that read
"arcane" already (candle amber, rune violet, orb teal), so a control dropped in with no colour still
looks right.

**D5 — Artwork is an input, not part of the engine work.** The composition below fixes overlay
*slots*, not coordinates; coordinates are placed against whatever PNG is final, with the alignment
page. A placeholder painting of the same composition gets the engine shippable before the art exists;
swapping the PNG later is the instance's `background_image` key (no code, no layout rewrite — rects
survive if the composition matches).

**D6 — No engine changes in v1.** The one thing that is genuinely scene-wide (a warm flicker that
lights the whole room as the candles gutter) would need a compositor hook. It is deliberately deferred
(§12, backlog): per-control halos already read as light spill, and a full-canvas additive blit is the
most expensive thing on a Jetson we could add.

### 2.2 Sequencing ladder (so the wall is never blocked)

| Rung | What is on the wall | Cost |
|---|---|---|
| 0 | `arcane_lab` layout using ONLY existing types (candle glows = `lamp`, astrolabe = `radar`, dial = `gauge_round`, ley trace = `scope`), over the new (or placeholder) art | ~1 h, zero code |
| 1 | + `candle_flame`, `ember_field`, `floating_orb` | phase 1 |
| 2 | + `rune_circle`, `rune_line`, `smoke_wisp` | phase 2 |
| 3 | + `lightning_arc`, `potion_bubbles`, real art, profile slot | phase 3 |

Rung 0 is worth doing first even if the new types land the same week: it proves the layout, the
artwork and the placement workflow before any animation code exists, and it gives a visual reference
for judging the new types against.

---

## 3. The animation catalogue

Cost is implementation + tuning effort: **S** ≈ half a day, **M** ≈ a day, **L** ≈ two days or more.

### 3.1 Fire and light

| # | Type key | What it looks like | Implementation | Overrides | Cost |
|---|---|---|---|---|---|
| 1 | `candle_flame` | Guttering teardrop flame: 3 nested ellipses (smoky edge, warm body, white-hot core) + additive halo; height/brightness/lean all flicker on separate incommensurate frequencies so it never strobes; `count` spreads a row of candles across the rect with independent phases (a rack, a chandelier, a candelabra arm) | polygon+ellipse draws + cached radial halo, additive blit | `flame_rgb`, `count`, `flicker`, `glow`, `lean` | M |
| 2 | `ember_field` | Slow motes rising and swaying, brightening then dying; a canvas-sized rect makes the whole room dusty with magic | fixed particle pool (no allocation), 3 cached dot sizes, additive | `ember_rgb`, `count`, `rise`, `sway`, `size` | S |
| 3 | `brazier` | A wide, violent flame bed | covered by `candle_flame` with `count: 1` and a wide rect — no new class | — | 0 |
| 4 | `candle_glow` | Warm light pool with no flame shape (behind painted candles, inside lanterns, on the floor) | **reuse `lamp`** with a warm `color` and a slow `noise`/`sine` signal | existing | 0 |
| 5 | `fireflies` | Fewer, larger, drifting | `ember_field` with `count: 12` | — | 0 |

### 3.2 Runes and sigils

| # | Type key | What it looks like | Implementation | Overrides | Cost |
|---|---|---|---|---|---|
| 6 | `rune_circle` | 1–3 concentric rings of glyphs counter-rotating at different speeds; brightness runs a travelling wave around each ring; a faint additive ring glow underneath | 10–14 glyph polylines from a shared unit-space table, rotated + scaled per glyph; line draws only | `rune_rgb`, `rings`, `glyphs`, `radius`, `spin`, `pulse` | M |
| 7 | `rune_line` | A row (or column) of runes lighting in sequence with a travelling flare and a short hold — an inscription being read | same glyph table; per-glyph brightness from a moving phase | `rune_rgb`, `count`, `speed`, `orient`, `hold` | S |
| 8 | `sigil_flare` | One large glyph that draws itself stroke by stroke, flares, fades, repeats | glyph polylines revealed by progress + additive flare | `rune_rgb`, `glyph`, `period` | S |
| 9 | `ward_ring` | Hexagonal barrier that ripples when "struck" | rune_circle variant with a polygon ring + pulse | — | M |
| 10 | `lit_rune_point` | A single glowing rune node in a chain | **reuse `lamp`** with a violet `color` | existing | 0 |

### 3.3 Floating and orbital

| # | Type key | What it looks like | Implementation | Overrides | Cost |
|---|---|---|---|---|---|
| 11 | `floating_orb` | Sphere with a pre-rendered radial gradient, rim light and specular highlight, drifting on a Lissajous path inside the rect, breathing ±4%; `count` gives a swarm of independent orbs | one cached 128 px RGBA sphere, scaled once per size, blitted per frame; drift is pure math | `orb_rgb`, `count`, `drift`, `pulse`, `glow` | S–M |
| 12 | `orrery` | Tilted elliptical rings with motes riding them, each at its own rate | could be new (M) — **v1 reuses `radar`** with a gold/violet palette, which already gives a rotating ring + blips | see radar | 0 |
| 13 | `astrolabe_dial` | Tick-marked dial whose pointers creep | **reuse `gauge_round`** (needle + hub + sweep) | existing | 0 |
| 14 | `pendulum` | Swinging glowing bob with a fading trail | new, M | `trace_rgb`, `period` | M |
| 15 | `scrying_eye` | Eyelid that blinks, iris that dilates and tracks slowly | new, M | `iris_rgb`, `blink` | M |

### 3.4 Alchemy

| # | Type key | What it looks like | Implementation | Overrides | Cost |
|---|---|---|---|---|---|
| 16 | `potion_bubbles` | Liquid body with a shimmering meniscus and bubbles rising, wobbling and popping at the surface; a faint glow inside the glass | small bubble pool, ellipse draws + a surface shimmer line | `potion_rgb`, `bubbles`, `rise`, `surface` | S–M |
| 17 | `cauldron_surface` | Churning surface: overlapping ripples + steam puffs | new, M (or `potion_bubbles` with `surface: false`) | — | M |
| 18 | `smoke_wisp` | 2–3 curling ribbons of smoke, widening and fading upward | parametric polylines on a cached SRCALPHA layer, drawn with alpha falloff | `smoke_rgb`, `wisps`, `drift`, `fade` | M |
| 19 | `crystal_shard` | Faceted crystal with internal light pulses | `floating_orb` variant (polygon facets) | — | M |
| 20 | `hourglass` | Glowing sand falling, pile growing, then flips | new, M | `sand_rgb`, `period` | M |

### 3.5 Energy, ink and paper

| # | Type key | What it looks like | Implementation | Overrides | Cost |
|---|---|---|---|---|---|
| 21 | `lightning_arc` | A jagged arc between two electrodes, restriking every 0.5–3 s with 2–3 fading echoes; bright core over a wide dim glow | midpoint-displacement polyline, cached per strike, afterglow layer | `arc_rgb`, `strike`, `branches`, `jag` | M |
| 22 | `ley_line` | A living oscilloscope trace — ley-line resonance | **reuse `scope`** with a violet `trace_rgb` | existing | 0 |
| 23 | `portal_vortex` | Concentric spiral arcs rotating inward | new, M | `portal_rgb`, `rings`, `swirl` | M |
| 24 | `spellbook_page` | Page edges fluttering, ink rewriting itself | new, L (the hard one; skip) | — | L |
| 25 | `tarot_card` | A card flips, revealing a glyph | new, M | — | M |

### 3.6 What the catalogue tells us

Nineteen ideas; **eight** of them are worth writing code for in v1. The rest are either covered by a
spec on another type (`count`, `orient`, `surface`) or belong to a later phase. Every idea that is
"another kind of light in the same box" is a `count` or a colour, not a class — that is where the
work stays small.

---

## 4. v1 set: eight new types, four reuses

| New class | Type key | Why it earns its code |
|---|---|---|
| `FlameControl` | `candle_flame` | The soul of the scene; nothing existing has a flame silhouette, and `count` makes it a rack/chandelier |
| `EmberFieldControl` | `ember_field` | Turns a static painting into a room with air in it; one control covers the whole canvas |
| `OrbControl` | `floating_orb` | Second-most iconic; the cached-sphere approach is cheap and gives swarms for free |
| `RuneCircleControl` | `rune_circle` | The centrepiece ritual circle; also the reason the glyph table exists |
| `RuneLineControl` | `rune_line` | Inscriptions along shelves, walls, page edges, rim of the cauldron — highest places-per-line-of-code |
| `SmokeControl` | `smoke_wisp` | Incense and cauldron steam; the only soft, non-point light effect |
| `ArcControl` | `lightning_arc` | Movement and danger; the only type that draws *between* two points (apparatus wiring) |
| `PotionControl` | `potion_bubbles` | Reads "alchemy" instantly, and it is the cheapest of the liquid family |

| Reuse | As | Palette |
|---|---|---|
| `radar` | astrolabe / orrery on the wall or ceiling — **only over artwork with a painted dial face** | gold + violet |
| `gauge_round` | alchemical dial on the apparatus — same caveat | brass + amber |
| `scope` | ley-line trace in a crystal frame — same caveat | violet |
| `lamp` | lit rune nodes in a DARK region — note its halo is an opaque dim disc, which over a bright painting reads as a dark hole | candle amber, rune violet |

**P1 corrected this table with a render** (see §11): in a freeform layout these four draw *only* their
overlay — a needle, a sweep, a trace, a disc — because no sprite is blitted over artwork. Dropped on a
painting that has no painted dial or frame beneath them they read as a floating stick or a dark hole
(measured: a `radar` and a `gauge_round` on the arcane placeholder looked like two stray diagonal
lines; a `lamp` at each candle looked like a black ring around the flame). They are free reuses only
where the artwork already draws the instrument's face — which the arcane placeholder does not, so
`arcane_lab.json` uses none of them until phase 2 adds `rune_circle` for the floor.

Backlog (documented, not built): `pendulum`, `scrying_eye`, `ward_ring`, `portal_vortex`,
`cauldron_surface`, `crystal_shard`, `hourglass`, `tarot_card`, `sigil_flare`, `spellbook_page`,
plus the engine-level ambient warmth (§12).

---

## 5. Shared infrastructure: one new module

`controlpanel/controls/arcane.py` holds the eight classes **and** four helpers they share. Splitting
into `arcane_fire.py`, `arcane_runes.py`, … would only duplicate the helpers.

**P0 measured these helpers before the design was finalised** — the numbers below are from
`designs/arcane_proto/arcane_spike.py` (pygame 2.6.1 / SDL 2.28.4, dummy driver, 1080×1920), with
artifacts `arcane_p0_sheet.png` (shapes at layout sizes, glyphs at 14/22/34/60 px) and
`arcane_p0_scene.png` (a full scene). Three of the four helpers were WRONG in their first form and the
measurements are what fixed them:

| Measurement | First form | Final form |
|---|---|---|
| 120 additive embers | **493 ms/frame** — the glow cache was keyed by the exact colour, and a mote dimming individually produced a new key, so every one was a cache miss and rebuilt a 64 px gradient | **0.90 ms/frame** — quantise the colour to 32-level steps in the cache key |
| 240 additive embers | — | 2.29 ms/frame |
| orb body | blitted additively: **clipped to a flat white disc with a hard ring** | alpha-blended body with limb darkening + specular: 0.36 ms at 240 px, reads as a sphere |
| one additive halo, r=120 / r=260 | peak = full colour → overlapping halos clipped to white | peak capped at 0.42 of the colour: 0.11 / 0.19 ms |
| 8 flame racks (16 candles, halo + 3 profiles each) | — | 1.89 ms |
| rune ring, 3 rings × 18 glyphs | — | 0.65 ms |
| rune line, 12 glyphs | — | 0.15 ms |
| canvas copy alone (what the compositor does per frame) | 1.25 ms | — |
| **full scene** (copy + embers + flames + orb + ring + line + ambient halo) | — | **6.8 ms/frame** |

Glyph legibility, judged from the contact sheet: legible and clearly "writing" at 22 px and up;
**14 px is marginal** (strokes thin out), so the rune ring's glyph size has a floor of ~18 px, which
`r * 0.20` only clears for rings of radius ≥ 90 px.

| Helper | Purpose | Why it matters |
|---|---|---|
| `GLYPHS` | 12 rune polylines in unit space (each a list of `(x, y)` point lists), authored once | `rune_circle`, `rune_line` and any future sigil type share one glyph vocabulary; glyphs are drawn, never font-dependent |
| `glow_surface(rgb, radius)` | Radial-gradient RGBA surface, interpolated from a **small** 64 px master, cached by `(quantised rgb, size bucket)` in a module-level LRU (≤256 entries) | Two rules from P0: bucket the radius (70 px and 74 px halos share one surface) and **quantise the colour**, or a per-mote dimmed colour is a cache miss every call (493 ms → 0.9 ms) |
| `sphere_surface(rgb, diameter)` | A BODY: radial limb darkening, specular highlight, antialiased limb — alpha-blended, never additive | Additive is for light, not for objects; an additive "sphere" clips to a white disc with a hard ring (measured) |
| `flicker(t, phase, rate, depth)` | Deterministic brightness in `[1-depth, 1]` = 3 incommensurate sines + a seeded sample-and-hold "gutter" | Reads as fire rather than as a sine wave; deterministic under the mode's `seed`, so a screenshot is reproducible |
| `ParticlePool(n, rect, rng)` | Fixed list of dicts recycled in place, `step(dt)` + iteration | Zero allocation in `update()`; the rule that keeps the Jetson at 60 fps |

Reused from the existing package: `Control`, `ControlContext`, `_color`, `_anchor`, `_window`,
`_recompute_geometry`, and `signals.build_signal` (`pulse` for flares, `noise`/`sine` for slow
breathing). No new signal system.

### 5.1 Rules every new class must follow

1. **Colour keys must be named `color` or end in `_rgb`, and must be read through a scannable idiom**
   (`self._color("x_rgb", default)`, `self.spec.get("x_rgb", …)`, `self.spec["x_rgb"]`, or
   `"x_rgb" in self.spec`). The picker table is verified by a source scan
   (`tests/test_control_edit.py:50–98`); a key read any other way is a knob the page will not offer.
2. **Never assign `self.rect` internally.** Cache derived geometry in `_recompute_geometry()`, call
   `super()._recompute_geometry()` first, guard with `getattr` (the base calls the hook before the
   subclass body runs) and call it again at the end of `__init__`.
3. **No allocation in `update()`/`draw_overlay()`.** Surfaces are built in `__init__` /
   `_recompute_geometry()` and rebuilt only on `set_rect()`; per-frame state changes are numbers.
4. **Draw something on frame 0.** The mode may render before the first `update()`; a class whose
   first frame is blank reads as "the overlay is broken" while you are positioning it.
5. **Never raise on a spec value.** Coerce and clamp (`int(float(...))` in a `try`, defaults on
   failure) — an exception inside `enter()` blacks out the whole mode, and one of these values may be
   something the panel's own form just wrote.
6. **No per-frame logging.**
7. **Docstring with a "Layout overrides:" paragraph** — that is the text the Add-overlay dialog shows.
8. **Additive is for light, not for objects.** Halos, glows and motes blit with `BLEND_RGB_ADD`; a
   sphere, a flame body or a liquid body is alpha-blended (or drawn opaque). Blitting a body additively
   clips it to a flat white shape with a hard edge — measured on the orb in P0.
9. **Every cached surface is keyed by bucketed, quantised inputs** (radius bucket + colour quantised to
   32-level steps). A cache keyed by an exact per-particle colour is a cache miss per particle: that
   one mistake cost 493 ms/frame for 120 motes.

### 5.2 Table, defs and registration changes (exact)

`controlpanel/registry.py` — eight rows, default sprite each:

```
"candle_flame": "ARCANE_FLAME", "ember_field": "ARCANE_EMBERS",
"floating_orb": "ARCANE_ORB",  "rune_circle": "ARCANE_RUNE_RING",
"rune_line": "ARCANE_RUNE_LINE", "smoke_wisp": "ARCANE_SMOKE",
"lightning_arc": "ARCANE_ARC", "potion_bubbles": "ARCANE_POTION",
```

`controlpanel/controls/__init__.py` — imports, eight `CONTROL_CLASSES` rows, eight `COLOUR_KEYS` rows
(exactly the keys each class reads; the test fails otherwise).

`assets/control_panel/sprite_defs.json` — append in the empty rows 12–15, all whitelisted footprints:

| Sprite | Rect (cells) | Footprint |
|---|---|---|
| `ARCANE_FLAME` | `0,12` | 1×1 |
| `ARCANE_ORB` | `1,12` | 1×1 |
| `ARCANE_RUNE_RING` | `2,12` | 2×2 |
| `ARCANE_RUNE_LINE` | `4,12` | 4×1 |
| `ARCANE_EMBERS` | `8,12` | 4×2 |
| `ARCANE_SMOKE` | `12,12` | 2×2 |
| `ARCANE_ARC` | `0,14` | 2×2 |
| `ARCANE_POTION` | `2,14` | 1×2 |

The placeholder skin is 2048×2048 (`assets/control_panel/skins/placeholder/sheet.png`), so appended
defs stay inside every skin's sheet and `load_skin` keeps passing. Re-run
`scripts/make_placeholder_skin.py` afterwards so the new cells exist in the generated sheet.

---

## 6. The layout and the composition

`assets/control_panel/layouts/arcane_lab.json`, freeform, `design_resolution: [1080, 1920]`,
`background_image: "arcane_lab.png"`. Name the artwork in the LAYOUT (not only the instance) so the
layout is self-describing; the instance can still override it.

Composition slots — what to place where, independent of the final art (counts are the target for
v1; ≈30 overlays, roughly the density of the shipped Scifi layout):

| Region | Contents | Types |
|---|---|---|
| Ceiling / hanging light | chandelier ring + 6–8 flames | `candle_flame` (count 7), `lamp` glow, `rune_circle` (small, hanging ring) |
| Left shelving | jars and bottles | 3–4 `potion_bubbles`, 2 `lamp` glows, `rune_line` across the shelf edge |
| Right desk | grimoire + incense | `rune_line` on the page, `smoke_wisp` from the burner, `floating_orb` hovering |
| Centre apparatus | electrodes + dial + astrolabe | `lightning_arc` between the electrodes, `gauge_round`, `radar`, `floating_orb` (large) |
| Floor | ritual circle | `rune_circle` (300–420 px), 2–3 `lamp` rune nodes |
| Whole canvas | dust/embers | `ember_field` at `0,0,1080,1920` (draw it before the local effects in the document so it sits underneath) |

Draw order is the document's control order (later controls draw on top), which is why the ambient
`ember_field` goes first and the flame racks last.

---

## 7. Artwork

Two paths; both end with overlays placed by the alignment page against the real PNG.

- **A (taken) — the painting is `assets/control_panel/backgrounds/arcane_gate.png`**, 816×1440
  (aspect 0.567 vs the wall's 0.5625, so the instance uses `scale_mode: cover` and crops ~1% of the
  width). It is a vaulted stone library with a glowing portal. Layout `arcane_gate.json` is authored in
  the PNG's OWN pixels (816×1440, `design_resolution` omitted so the loader adopts the native size) and
  the wall scales it; the anchors, read off a 100 px grid overlay:
  left candelabra flames x 145..219, wicks y≈755 · right-hand candles x 619..661, wicks y≈799 · the
  glowing gate x 330..500, y 615..880 (centre 415,747) · arch band above the gate y 566..592 ·
  hanging lamp bowl 410,310 · rose window 345..455, 350..445 · lit floor from y≈1120 down.
- **The wall-size copy:** `arcane_gate.png` is upscaled ONCE to
  `assets/control_panel/backgrounds/arcane_gate_wall.png` (1080×1920: uniform 4/3, centred, 4 px cropped
  per side) and the layout is authored in WALL pixels. This is not cosmetic — see §9: a canvas smaller
  than the screen costs a per-frame smoothscale.
- **The earlier placeholder** (`arcane_lab_placeholder.png` + `arcane_lab.json`, generated by
  `scripts/make_arcane_placeholder.py`) is kept as a fixture: it is the geometry harness for a layout
  of a different composition, and it is what phase 1 was built against. Any 1080×1920 image; drop it in
  `assets/control_panel/backgrounds/` (or point `background_image` at a path anywhere). The existing
  backgrounds are painterly AI art; matching that quality procedurally is a project of its own.
  Guidance for the generator prompt: portrait, dark stone-and-wood laboratory, one clear lit region in
  the middle, visible candlesticks (so flames land on wicks), a floor circle or rug, an apparatus with
  two vertical posts near the top-centre, empty shelf space at the sides.
- **B — placeholder first.** I generate a grey-box `arcane_lab_placeholder.png` of the same
  composition (blocks where the shelves/desk/circle are), with the same 1080×1920 geometry, so the
  engine and the overlay count are testable immediately. Overlay rects survive the swap roughly intact
  if the composition matches; the alignment page fixes the rest.

Either way, the layout is created once the PNG exists (`create_freeform` in the panel, seeded from
`Scifi` so the control list starts populated, then retyped and re-placed).

---

## 8. Instance and the tuning loop

Add a slot to `configs/modes_config_vert.json` (57 modes today, slots 0–56; slots 45 and 55 are the
existing control panels) **through the panel**, never by hand — `core/editor.py` is the only writer:

```json
"57": {"type": "controlpanel", "name": "Arcane Laboratory",
       "layout_file": "arcane_gate", "seed": 7, "scale_mode": "cover",
       "accent_rgb": [255, 176, 64], "lamp_rgb": [255, 150, 60]}
```

`background_image` is left empty so the layout's own artwork is used; set it only to point the same
layout at a different PNG.

The loop that follows is entirely existing machinery:

1. Panel → profile card → switch the wall to the new slot (or `--play N` on a sandbox for tuning
   without touching the wall).
2. Panel → layout page → pick `arcane_lab` → the wall rebuilds showing it.
3. Click a box over the artwork (or a row in the overlay list: index, type, sprite, rect), nudge with
   the pad, resize with `w±`/`h±`, `freeze` to hold animations still, set colours from the pickers.
4. Save (timestamped backup under `.backups/`), or let structural edits save themselves; the wall
   picks each change up through `refresh_mode`.

**One restart per phase.** New code in an already-imported module is not reloaded by a live apply —
adding classes to `controlpanel.controls` needs the app restarted to be seen. Layout edits never do.

---

## 9. Performance budget

Measured in P0 (§5) at the wall's real size, dummy driver:

| | ms/frame |
|---|---|
| canvas copy (the compositor's per-frame baseline, already paid today) | 1.25 |
| 90 embers + 16 candles + orb + 3×18 rune ring + 12-rune line + ambient halo | 5.5 (6.8 with the copy) |
| **ceiling implied** | **≈ 147 fps** for the overlay layer alone |

The wall runs at 62 fps today (16.1 ms/frame total) with 32 control overlays, so ~6.8 ms of overlay
work fits with headroom — but not double it. Design constraints that follow:

- **≤ 12 flame-equivalents** (a `count: 3` rack is three): 1.9 ms for 16 candles, so ~0.12 ms each.
- **embers ≤ 160** (0.9 ms at 120, 2.3 ms at 240 — it scales linearly, as a pool should).
- **rune rings ≤ 3 layers, ≤ 24 glyphs per layer** (0.65 ms at 3×18).
- **halos are cheap** (0.11–0.19 ms even at r=260) but they must stay capped: overlapping additive
  layers clip to white long before they cost anything.
- The expensive shape is a **full-rect SRCALPHA layer**; keep scratch layers at the control's own rect
  and never at canvas size.

**Measured on the wall (2026-10-17), and it changed the layout:** with the artwork at its native
816×1440 the canvas did not match the screen, so the compositor smoothscaled EVERY frame —
**36.4 fps, steady** (not warm-up; 27.5 ms/frame). Pre-scaling the art to 1080×1920 and authoring the
rects at `×4/3 − 4 px` restored **62.4 fps**. Off-display the same comparison reads 6.2 ms (816-wide
canvas) vs 9.9 ms (1080×1920) per frame, because there are simply 2.4× more pixels to copy and blend.

Rules that follow:
- **Author a layout at the screen's own resolution.** A canvas that differs costs a scaled blit of the
  whole frame per frame, which is the single most expensive thing the compositor can do.
- Pre-scale the artwork once, offline, rather than letting the compositor do it 60 times a second.
- `scale_mode` then becomes a no-op (canvas == screen) and the instance can keep `cover`.

Measurement method for the acceptance run: `SDL_VIDEODRIVER=dummy`, the real mode over the real
layout, timing `update`+`draw` around the control loop with `--frames N`; control measurement = the
shipped `Scifi` layout (32 controls) in the same harness. **Snapshot the frame for the screenshot
BEFORE any per-piece benchmark runs** — P0's own benchmarks drew 120 additive halos onto the frame it
later saved, fabricating a white disc that looked like a rendering bug.

---

## 10. Tests

Extend, don't duplicate:

1. `tests/test_control_panel_all.py` — the "every type still animates" gate. Its `ALL_TYPES_LAYOUT`
   fixture is **grid** mode, which means every added control must find free cells in a 15×8 grid. Switch
   that fixture to **freeform** (each type at its own rect) so adding a type is one list entry, then add
   the eight arcane rows. This keeps the existing assertions (`set(CONTROL_CLASSES) == set(CONTROL_TYPES)
   - {"plate"}`, 6 simulated seconds of update + a draw for every type) and removes a per-type
   bookkeeping chore.
2. `tests/test_control_edit.py` — no edit needed: `COLOUR_KEYS` ↔ source equality now covers the new
   classes automatically, in both directions.
3. `tests/test_layout_align.py::test_every_control_class_survives_a_move` — no edit needed; the new
   classes are walked automatically. They must pass it by construction (§5.1 rule 2).
4. **New** `tests/test_arcane.py`:
   - each class constructs from a `PlacedControl` and **draws inside its own rect** after 0 updates and
     after 60 simulated seconds (containment, not exact pixels);
   - determinism: same seed → identical bounding rect and identical pixel count over a fixed frame;
   - **no per-frame allocation**: monkeypatch `pygame.Surface` and assert zero constructions across 600
     `update`+`draw` calls (this is the anti-jank test that keeps the wall at 60 fps);
   - `set_rect` moves the drawing (the existing contract, narrowed per class);
   - spec robustness: junk values (`"glow": "big"`, `count: 0`, `color: "red"`) must fall back to
     defaults rather than raise.
5. Layout-level: `load_layout("arcane_lab")` succeeds, every rect is inside the canvas, and the mode
   builds under the dummy driver. The existing smoke test that constructs **every configured mode**
   covers the profile slot once it is added.
6. `python validate_configs.py --all` clean; full suite green.

---

## 11. Phases

Each phase ends with: off-display measurement → a rendered PNG I look at → the feature on the wall →
the suite green → commit with the measured evidence. Acceptance reports as separate files under
`designs/` (house style).

**P0 — spike (off-display, no wall changes). DONE 2026-10-17.** Evidence:
`designs/arcane_proto/arcane_spike.py` + `arcane_p0_sheet.png` + `arcane_p0_scene.png`. Measured and
decided: glow cache keyed by (quantised colour, radius bucket) — 493 → 0.9 ms for 120 embers; bodies
alpha-blended, never additive (an additive orb clipped to a white disc); halos capped at 0.42 peak;
glyph floor ~18 px; full scene 6.8 ms/frame. Flame, orb, rune ring, rune line and the ember pool all
render and were judged from the contact sheet: flames read as candle flames, the orb reads as a sphere,
the glyphs read as writing. **P1 inherits:** the helper shapes above, `GLYPHS` as authored (12 runes),
and the constraints in §9.

**P1 — helpers + first three types + placeholder art + layout skeleton. DONE 2026-10-17.**
Evidence: `controlpanel/controls/arcane.py` (`candle_flame`, `ember_field`, `floating_orb` + the four
helpers), three rows in `controlpanel/registry.py`, `CONTROL_CLASSES` and `COLOUR_KEYS`, three sprite
defs appended at rows 12 (`ARCANE_FLAME`, `ARCANE_ORB`, `ARCANE_EMBERS`), `tests/test_arcane.py` (11
tests, including the steady-state allocation test), the `ALL_TYPES` fixture moved from grid to
freeform so a new type is one line, `scripts/make_arcane_placeholder.py` +
`assets/control_panel/backgrounds/arcane_lab_placeholder.png`, and
`assets/control_panel/layouts/arcane_lab.json` (7 controls).
Measured: `render_layout.py arcane_lab` → 7 controls, **6.66 ms/frame, ≈150 fps ceiling**;
full suite `773 passed`; `validate_configs.py --all` 0 errors (1 pre-existing windows-path warning).
Render: `designs/arcane_proto/arcane_lab_render.png` — flames land on the painted wicks, orbs read as
spheres, the floor node glows; the scene is deliberately sparse until phase 2 supplies the runes.
Two design corrections came out of the render (§4): **sprite-less types are not free over artwork**,
and a **`lamp` over bright art reads as a dark hole** — both removed from the layout.
**P2 inherits:** the glyph table + `flicker` for runes, and the `mote` (not `size`) naming rule.

**P2 — runes + smoke. DONE 2026-10-17.** `rune_circle` (rings/glyphs/radius/spin/pulse/glow),
`rune_line` (count/speed/orient/hold/glow) and `smoke_wisp` (wisps/drift/speed/fade) in `arcane.py`,
with the 12-glyph table and `draw_glyph` shared by both rune types; three rows in each of
`registry.py`, `CONTROL_CLASSES` and `COLOUR_KEYS`; three sprite defs at rows 12; `tests/test_arcane.py`
now walks six arcane types (construction, frame-0 and 60 s containment, move, seed reproducibility,
steady-state zero allocations, junk specs, count clamps).
Measured: **773 tests pass**; `validate_configs.py --all` 0 errors (1 pre-existing windows-path
warning); `render_layout.py arcane_gate` → 9 controls, **6.22 ms/frame, ≈161 fps ceiling** on the
816×1440 canvas.
Render: `designs/arcane_proto/arcane_gate_render.png` — the five candelabra flames sit on the arms,
the three right-hand candles are lit, the rune ring frames the portal without fighting it, the arch
inscription reads as carved, the two orbs hang against dark stone.
**P3 inherits:** the gate's interior as the `lightning_arc` target, and the jars/vessels as
`potion_bubbles`.

**Install (done 2026-10-17):** slot `57` "Arcane Laboratory" (`type: controlpanel`,
`layout_file: arcane_gate`, `scale_mode: cover`, `seed: 7`) added to `configs/modes_config_vert.json`
through `core/editor.py` (timestamped backup taken), the panel applied the profile, and the kiosk was
restarted to load the new control classes. Wall verified: `layout_report` = `arcane_gate`, 9/9 animated,
canvas 1080×1920, **62.4 fps**, and a root-window capture shows the flames on the candelabra and the
right-hand candles, the rune ring framing the portal, both orbs and the arch inscription.

**P3 — arc + potion + real art + slot. DONE 2026-10-17.** `lightning_arc` (midpoint-displacement bolt
with branches, restrike interval, afterglow decay, `blend: add|over`) and `potion_bubbles` (fixed bubble
pool + meniscus on a scratch layer) in `arcane.py`; registered in all three tables; sprite defs at rows
14; `tests/test_arcane.py` walks all eight types; the layout gained the arc inside the portal and two
potions (the alembic globe on the right desk, a flask on the left). Wall: slot `57`, 12/12 animated,
**62.5 fps**, verified by an amplified frame-difference of two live captures — the bolt is drawn, jagged
and branched, down the portal centre. Cost: 10.6 ms/frame off-display at 1080×1920 with 12 overlays.

Two lessons from P3, both now rules elsewhere in this doc:
- **Additive light is invisible over something already bright.** The bolt added nothing to the white-hot
  portal; it read only when drawn `over` in a colour darker than the background. Hence the `blend` key.
- **A screenshot almost never catches a momentary effect.** The arc is lit ~15% of the time (strike
  ~1/s, decay 4), so 14 live captures showed nothing; the proof was an amplified DIFFERENCE of two
  frames. Judge transient effects that way, not by eyeballing single frames.

**P4 — backlog (not built).** `pendulum`, `scrying_eye`, `portal_vortex`, `ward_ring`, `hourglass`,
`crystal_shard`, `tarot_card`, `sigil_flare`, `spellbook_page`, plus the engine-level ambient-warmth
compositor hook and an optional second layout over `arcane_pixel.png`.

### Added after review: glowing_eyes

A tenth arcane type for dark corners: **a pair of eyes that fade in, hold, and fade away again.**
`GlowingEyesControl` draws two slanted almond lenses with a bright iris and a **slit pupil** (the slit is
what makes them sinister rather than cute), an additive halo per eye, and an optional blink that closes
them for ~0.2 s — a pair that never blinks reads as a painted sign.

Spec keys: `eye_rgb` (or `color`), `pairs` (1–3), **`eye`** (eye width as a fraction of the box's short
side — NOT `size`, which is the box), `gap` (eye spacing in eye-widths), `slant`, `period` (one full
fade in/hold/out cycle, seconds), `hold` (fraction of the cycle fully lit), `blink` (seconds between
blinks, 0 = never), `glow`.

Two details worth keeping:
- **The cycle starts inside its lit phase** (`t = period · U(0.38, 0.62)`), because at t=0 a control you
  just placed must be visible — otherwise it looks broken while you are aligning it. The jitter also
  desynchronises two instances.
- Eyes must be placed in genuine shadow. The first placement at the gate sat on the lit portal edge (it
  read as a sticker) and the second had the floating orb in front of it; both were moved into dark stone
  and re-verified on the wall.

Live: one pair under the left desk in `arcane_circle` (green, 11 s cycle, blinks) and two pairs in
`arcane_gate` (green in the upper-left vault, red on the right, 12 s, blinks) — gate 16 overlays at
**60.7 fps**, circle 14 at **62.4 fps**.

### Second layout: arcane_circle (2026-10-18)

`assets/control_panel/backgrounds/arcane_circle.png` (816×1440, a library with a **painted pentagram on
the floor**) became `assets/control_panel/layouts/arcane_circle.json` — the same `controlpanel` type,
so no new mode code: 13 overlays, authored in wall pixels over `arcane_circle_wall.png` (upscaled once
to 1080×1920 exactly like the gate). Profile slot `58` "Arcane Circle", applied and live at **62.2 fps**.

Placements (wall pixels; source coordinates × 4/3 − 4 px, which is what the layout's comment records):

| Overlay | Where | Why |
|---|---|---|
| `ember_field` | whole canvas, 70 motes | air in the room |
| `rune_circle` | `[250, 1266, 570, 222]`, `aspect 0.39`, `upright`, `glyphs 20`, `glyph 0.13`, `guides false` | centred on the PAINTED floor sigil so the circle looks alive instead of doubled |
| `candle_flame` ×3 racks | left desk `[76,800]`, mid-left `[349,787]`, right desk `[916,787]` (counts 2/2/3) | the candles the painting draws |
| `candle_flame` ×1 | `[536,267]` | the flame inside the hanging lantern |
| `drifting_runes` ×2 | `[169,840]`, `[636,813]` | rising off the two open books, violet and pale blue |
| `potion_bubbles` ×2 | green flask `[856,840]`, blue flask `[623,860]` | the vessels on the right desk |
| `floating_orb` ×2 | `[396,440]`, `[743,507]` | magical lights on the dark stone by the window |
| `smoke_wisp` | `[276,1200,507,400]` | mist lifting off the sigil |

**Finding: a floor sigil is an ELLIPSE, and a circular ring cannot sit on it.** The first attempt matched
the painted circle only by accident — perspective squashes it vertically (ry/rx ≈ 0.39 here), so half the
glyphs landed on bare floor. `rune_circle` gained four keys for this: `aspect` (vertical squash),
`upright` (keep glyphs vertical instead of turning them to face outward, which is how floor runes read),
`glyph` (glyph size as a fraction of the shorter axis — a floor band needs smaller glyphs than a big
upright ring) and `guides` (the faint ring outlines, turned off over painted art to avoid two rings).

### Added after review: drifting_runes

A ninth arcane type, requested for placing above books and apparatus: **a sequence of glowing symbols
that fade in low in the box, drift upward, and fade out near the top.** `DriftingRunesControl` keeps
`count` glyphs staggered in time (life offset `i/count`), so they pass upward as a sequence rather than
as one block; each has its own glyph, size jitter and sway, all fixed at construction from the mode's
seed, so nothing is randomised per frame and a pinned seed reproduces the frame. Drawing is two stroke
passes (wide dim beneath a thin bright core) on a scratch layer plus two scales of additive halo — a
tight one that hugs the strokes and a broad bloom — because on a dark background a single stroke reads
as chalk rather than as light.

Spec keys: `rune_rgb`, `count` (1–12), `glyph` (glyph size as a fraction of the box's short side,
0.06–0.6), `rise` (seconds to cross the box, 1–40), `sway`, `fade` (portion of the life spent fading),
`glow`. The size key is **`glyph`, not `size`** — in a freeform layout `size` is the control's box (the
same two-meanings trap as the ember field's `mote`).

Registered in the three tables, sprite `ARCANE_RUNE_DRIFT` at cell `3,14`, walked by
`tests/test_arcane.py` (nine types now). Two instances sit in `arcane_gate.json` as starting points —
one above the open book on the left desk `[255, 990, 190, 190]`, one above the alembic `[686, 940, 160,
190]` — both to be re-placed by the author. Wall: 14/14 animated, **62.5 fps**.

### Fix after review: the smoke did nothing

Reported from the wall: "the smoke wisp doesn't seem to do anything". It WAS drawing — a probe measured
its brightest pixel at **(26, 27, 33)** on black, about 11% opacity, invisible over stone. Two causes,
both worth remembering:

1. **The alpha maths multiplied a low alpha by a lower one.** Four stroke passes at alpha 16/30/52/90
   were each scaled by `(1 - fade*0.6)` = 0.49, so the brightest stroke was alpha 44 — then drawn as
   1–9 px lines over a busy floor.
2. **`pygame.draw.*` REPLACES alpha on an SRCALPHA surface.** Overlapping circles therefore do not
   accumulate, so a plume built from drawn circles comes out as thin wires rather than a soft column.
   The fix is to BLIT a cached soft dot (`soft_dot()`, radial alpha falloff) along the plume's spine:
   blits blend, so overlapping puffs thicken into smoke.

The rewrite draws 22 soft puffs per wisp along a wandering spine, flaring as they rise, with `fade`
controlling how much of the column's height survives. Verified on the wall by an amplified DIFFERENCE of
two live captures 1.2 s apart (449 changed samples in the smoke box, two ragged plumes that moved), not
by eyeballing one frame — a static plume and a static light shaft look the same in a still.

---

## 12. Risks and things that will bite

- **Don't reuse a key name with a second meaning.** The `size` key already means three different things
  across the lamp family (fraction of the box vs. layout pixels, split by value); one added overlay
  that set a pixel `size` on a type reading it as a fraction blacked out the whole panel. Arcane types
  must avoid `size` entirely — the ember field's mote radius is `mote` precisely because `size` is the
  box in a freeform layout (this was caught in review of the first layout, not by a test).
- **A build-time exception leaves the mode black**, not frozen. Coerce every spec value (§5.1 rule 5)
  and keep `__init__` allocation cheap.
- **Frame 0.** The mode can render before any `update()`; a type that draws nothing until its first
  update looks broken while being positioned.
- **Colour-key scan.** A key the class reads through an idiom the scan does not recognise silently
  disappears from the pickers (this is how lamps shipped with "no colours" for a while).
- **Additive light clips.** Overlapping additive halos reach white long before they look "bright", and
  a body blitted additively loses its form entirely. Cap the halo's peak (0.42 of the colour measured
  well) and keep bodies alpha-blended.
- **A benchmark's residue ends up in your screenshot.** P0's own per-piece benchmarks drew 120 additive
  halos onto the frame it later saved, producing a white disc that read as a rendering bug for two
  iterations. Snapshot before measuring.
- **A canvas that is not the screen's size is the biggest cost there is.** 816×1440 art on a 1080×1920
  wall ran at 36 fps because every frame was smoothscaled; pre-scaling the art and authoring in wall
  pixels gave 62 fps. Measure on the WALL, not only off-display: the dummy-driver number for the
  native-canvas case (6.2 ms) says nothing about the scaled case.
- **Full-canvas effects are the budget risk**, not the number of controls. `ember_field` over
  1080×1920 is the thing to measure first.
- **Pygame `draw.*` ignores alpha** on the frame surface. Translucency must come from blitting cached
  SRCALPHA surfaces (or additive blits), then the alpha layer must be cleared per frame, not rebuilt.
- **Restart, not refresh, after code changes.** A `refresh_mode` re-enters the mode but cannot reload
  `controlpanel.controls`; a phase's new types are invisible until the process restarts. Verify which
  revision is on the wall (process start time vs. file mtime) before diagnosing "nothing changed".
- **The wall is the user's.** Tune on a sandbox instance on a free port; only the final look goes on
  the display.

---

## 13. Open questions (answer these before P1)

1. **Artwork — do you generate the painting, or should I build a procedural placeholder first?**
   Recommended: you generate (path A), I ship the placeholder in parallel so nothing blocks; if you'd
   rather I attempt a painted background procedurally, say so and it becomes its own phase.
2. **Which existing layout is the reference for density/placement — `Scifi` (on the wall now, 32
   overlays, 1080×1920) or `Portrait` (slot 45)?** Recommended: `Scifi` — same canvas as the wall, all
   controls animated, and it is the newest. (Note `Scifi.json` has `"name": "Portrait"` inside it — a
   copy-paste slip worth fixing while we are in there.)
3. **Type identity: keep `controlpanel` (recommended) or add an `arcanelab` alias type** so the mode's
   type label reads as its own and it can carry its own defaults?
4. **v1 scope: the eight types above, or trim to six** (flame, orb, rune circle, rune line, embers,
   smoke — dropping arc and potion to P4) to get it on the wall sooner?
5. **Palette: firelit amber + violet runes + teal orbs (recommended), or a colder sickly-green
   grimoire look?** Either is cheap (D4), but it decides the class defaults.
6. **One lab, or a lab per orientation?** The wall is portrait, so v1 is portrait only; landscape and
   the narrow profiles would each need their own layout and re-placement.
