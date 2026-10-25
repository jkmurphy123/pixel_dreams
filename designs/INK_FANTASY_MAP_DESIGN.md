# Ink Fantasy Map — a hand-drawn pen-and-ink map mode

**Status: phase 1 implemented (the sheet). Design otherwise as reviewed.**
Implementation records live in §7 (each phase is marked DONE with its measured evidence),
and each phase's acceptance report is a separate file under `designs/`.
Target: a NEW mode type (`inkmap`) in `configs/modes_config_vert.json` (and the other
profiles), drawing on the **1080 × 1920 portrait** panel.

---

## 0. Source material

Both videos in Cassandra Lynn's beginner series (Oakleaf Arrow Studios):

| | Video | Length | Transcript |
|---|---|---|---|
| **Part 1** | "how to draw mountains, trees, rivers & deserts for your fantasy map" — 75,061 views — `youtube.com/watch?v=WMgqDK_z4pA` | 22:09 | `designs/inkmap_proto/VIDEO_TRANSCRIPT.txt` |
| **Part 2** | "how to draw cliffs, canyons, waterfalls & floating islands for your fantasy map" — 8,872 views, 2026-10-09 — `youtu.be/8C3HfdrC-hQ` | 30:49 | `designs/inkmap_proto/VIDEO2_TRANSCRIPT.txt` |

Both analysed from the full transcript. Every technique below carries the timestamp it
came from, so the mapping can be checked against the video rather than against my
paraphrase. Both transcripts are auto-captioned, so a few words are mangled
("ctographer" = cartographer, "grass toughs" = grass tufts, "hashets" = hatches,
"unorganic" = organic); where a technique mattered I read the surrounding sentences
rather than the phrase.

These are **technique** tutorials: they teach a deliberate ORDER of passes with specific
pen weights. They are not generator designs. Turning them into code means answering
"what is a clump of rice, mathematically?", "what makes a line look unsteady?", and
"what is an upside-down Y, procedurally?" — sections 1 and 5.

---

## 1. Every technique in the video, and its code equivalent

Pen weights are real Sakura Pigma Micron nibs (00:39–01:11): `003 0.15 mm`, `005
0.20 mm`, `01 0.25 mm`, `02 0.30 mm`, `03 0.35 mm`, `05 0.45 mm`. On a ~200 mm wide
sheet drawn at 1080 px that is **5.4 px/mm**, so a `05` line is 2.4 px and a `003`
line is 0.8 px. All widths in the design are derived from that, not chosen by eye.

| # | Technique (timestamp) | Code equivalent |
|---|---|---|
| 1 | **Rice-clump continents** (01:37–03:21). Pour rice in clumps, nudge it, trace the outside edge with the `05`. | Each grain = a small rotated ellipse. A "pour" = a Poisson-cluster sample of grain centres around clump centres. Union of grains = a boolean mask. Trace = **marching squares** contour → chained polyline loops. |
| 2 | "Move it around and adjust what the rice looks like before you trace" (01:49–01:54) | **Morphological closing** (dilate then erode) on the mask. Welds grains that merely touch into one solid mass **without rounding the scalloped edge** — which is exactly why the traced border stays scraggly instead of becoming a blob. |
| 3 | Overlapping pencil circles, then a rough outline round the overlaps (03:29–04:02) | The same machine in a coarse mode: few, large grains; also the fallback if the rice look is wrong. |
| 4 | Trace **single grains** to get little islands (02:50–02:56) | Keep small connected components; the contour's minimum-area threshold decides what becomes an island. |
| 5 | **Scraggly line**: "hold your pen higher up away from the tip … less control … actually useful" (02:26–02:50) | A hand model: AR(1) low-frequency lateral wander (`drift = drift·0.72 + N(0,1)`) + fine tremor, applied as a perpendicular offset to every vertex. The wander is the "less control"; the tremor is the paper texture. |
| 6 | The land should **run off the page**, not float as one island (04:30–05:38) | Pour clumps deliberately partly off-canvas. Crucially, a contour that terminates at the field edge is **OPEN** and must not be closed. |
| 7 | **Water**: trace a line parallel to the coast, then alternate four patterns — `hash`, `hash+dot`, `hash-dot-hash`, `dot-hash` (05:38–07:00) | Offset rings at 13 / 21 / 29 px (measured at supersampled scale), pen a parallel line along each, then walk it placing one of the four patterns at random. The four-pattern alternation is the whole illusion; a single pattern reads as a comb. |
| 8 | Water alternatives: broken squiggles, **layered** rows, stippling, wavy lines (07:00–08:57) | The same offset-ring walker with `water_style` ∈ {`hash`, `squiggle`, `stipple`, `wave`} and `water_rings` N. |
| 9 | **Lakes** are the water pass on the inside (08:58–09:25) | The same function, run on an interior contour, with the pattern stepping inward. |
| 10 | **Mountain** (09:25–11:40), in this exact order: an organic triangle **with no bottom line** (`02`); Z zigzags near the peak (`01`); a small hatch hanging off each point on the **left** flank following its slope (`01`); shading as hairlines down the **right** slope (`005`); a few texture dashes on the left (`05`); 1–3 dots on the edges (`02`). | `mountain()` = that sequence of pen passes, each pass taking its own nib width. No bottom stroke is drawn — that omission is load-bearing, it is what makes it read as a peak rather than a triangle. |
| 11 | **Ranges**: overlap the mountains, start the next where the last one ended, add smaller outliers, taper off, then transition into hills (11:40–12:15) | Walk placement: step along a drifting heading, place a mountain at each step, size envelope `size = base + span · min(step/k, (total-step)/k, 1)`. |
| 12 | **Hills** (12:15–13:44): a curved mound (`02`), stipple or solid-shade the right, then **grass tufts** = 2–3 short vertical lines with a dot either side (`005`). | `hill()` and `grass()`. Hills are the documented transition from range to plain. |
| 13 | Grass **fills empty space** (13:44–13:58) | `grass()` again, as the last pass, over whatever ground is still bare. |
| 14 | **Rivers** (14:01–16:12): start at a high point, meander in big squiggles to the coast, thicken everywhere it curves, taper thin↔thick where they meet, and — the rule she repeats three times — **a river never splits**, tributaries only join. Deltas are extra squiggles at the flat end. | Steepest-descent walk on a distance-to-coast field from a source on high ground; control points shoved sideways for the squiggle; extra-width overdraw where curvature exceeds a threshold; taper at both ends. Never split is enforced by construction: one river = one walk. |
| 15 | **Desert** (16:16–18:20): dense `01` stipple around the edge of the region to make a dark rim, then lighter, more sporadic `005` dots inside — "because it's a smaller point, the dots give the illusion of being much lighter". Dunes: a swooping line with backward S-curves (`01`), solid shade on the right, a row of lines on the left, and **no extra dots on the dune** because the desert field already has them. | Two dot bands keyed to distance-from-region-edge: radius 1.5–2.3 px on the rim, 1.0–1.45 px in the field at lower density. `dune()` = the swooping/S recipe. |
| 16 | **Trees** (18:22–21:28): pine = two stacked zigzag triangles plus a stem; oak = a fluffy cloud plus a stem. Shade with `003` dots along the underside and up the **right** side, or solid, or hashes. | `pine()` / `oak()`, same right-side stipple. |
| 17 | **Consistency rule**: every shading pass in the whole video goes on the **right-hand side** — "you do want them to match the shading of your mountains" (20:27–20:38). | One `LIGHT` constant that every recipe obeys. A feature that shades the wrong way is the fastest way to make the sheet look machine-made. |
| 18 | The closing advice (21:34–21:53): "It's not about complex shapes … it is more about patience" — i.e. the effect comes from **how many strokes** are on the sheet, not from clever shapes. | Rule 5 in §5: **stroke density scales with feature size.** |

---

## 1b. Part 2 — cliffs, canyons, waterfalls, floating islands

The whole of part 2 is **one five-pass recipe applied to a rock face**, plus one small
recipe for falling water. That is a gift for code: one `rock_face()` routine serves
cliffs, canyons and the undersides of floating islands.

### The five passes (part 2, 02:43–16:10)

| Pass | What the artist does | Code equivalent |
|---|---|---|
| **5.1 Main verticals** (`05`, thickest) | Draw a near-vertical line down from every place on the edge where one *fits* — and crucially, only at **major points, where the line changes direction** (03:31–04:11). Where the edge slopes left the line slopes left; after a direction change it slopes right, "which adds dimension" (03:52–04:01). | Walk the edge; compute turning angle; emit a stroke at every local extremum of direction whose clearance to the nearest other edge is above a threshold. Sign the stroke's lean from the edge's local slope. |
| **5.2 Y's and partial lines** | Vertical lines, **upside-down Y's**, vertical Y's with a small top, fragmented pairs, and verticals that deliberately stop short of the bottom (08:23–09:40). "Poorly drawn squiggles, followed by poorly drawn straight lines, followed by poorly drawn Y's — that's the basis of the cliff" (10:31–10:40). | A Y = a 1-segment stem plus a 2-segment fork at the top. Randomise fork width, fork depth, whether the stem reaches the far edge, and whether it is a full Y, a V, or a bare line. |
| **5.3 Horizontal hashes** (`005`/`01`) | Shading, but **varying** where it goes, never on every line: into **the crevice of the Y** (first choice), **fully filled where one face hides behind another**, and **partially along the edges with breaks and gaps** (10:50–13:05). Long lines, short lines, gaps. | Hash runs keyed to a face's *occlusion* and to the interior of each Y fork; explicitly leave gaps and vary length. |
| **5.4 Sporadic verticals and dots** (`003`) | Short vertical ticks and dots, "basically whatever happens when I move my pen rapidly up and down", filling the remaining white space — thin, so it stays light (14:00–15:01). | Short random verticals + dots at low opacity, jittered. |
| **5.5 Inward hatches** | Tiny hatches pointing **inland** at every direction change, to show the face is not flat — "erosion" on a cliff (15:06–16:06), and **all the way round** on a canyon, to show the ground going inward (21:20–21:36). | Short strokes on the inland normal, probed at the edge's turning points. |

Pass ordering is the tutorial's, and the artist says twice that you can **go back to an
earlier pass** to fill gaps you notice later (13:31–13:52, 15:32). That is a real feature
request for the plan: a pass must be able to be re-opened, which is why §4.1 keeps the
plan as an ordered list of passes rather than one flat stroke stream.

### The other part-2 features

| Feature | Technique (timestamp) | Code equivalent |
|---|---|---|
| **Cliff bottom** (05:19–06:45) | Optionally leave it open (a plateau), or close it by repeating the *same* line pattern 10–20 px down and letting it run into a cliff face so the face "turns in before turning out". Where there is a break, start the new line from whichever side overlaps. | For a coastal stretch: offset the edge inward, then cut-and-join where the offset would cross another edge; the front-most face is drawn last. |
| **Canyon** (19:10–22:36) | The same five passes confined to a "gash": verticals at direction changes, Y's, horizontal hashes, vertical squiggles, inward hashes all round — plus two canyon-only moves: **shade the edges where the canyon ends**, and **thicken the bottom in a few sections only**, because thickening all the way round destroys the light/dark contrast (22:23–22:33). | A closed interior region rather than a coastal edge; the same passes with `inward = both sides`, plus a thicken pass restricted to a few arcs. |
| **Waterfall** (16:34–19:08) | "A thick upside-down tree": from where the river meets the cliff edge, a line angling out left then a second line coming back up to *nearly* the same point — leave a sliver of gap, and widen the river's mouth just before it. At the bottom, a wavy line then **swirls — two loops forming a puffy cloud** = the splash, drawn just *below* the foot of the cliff. Then a few wiggly water lines and dots, in `005`/`003`. | Attached to a river that crosses a cliff edge: two diverging strokes with a gap at the top, a mouth-widening, then two overlapping loops at the bottom offset just past the cliff foot, plus light stipple. |
| **Floating island** (22:40–30:08) | A continent outline in `005` that is **not too vertical** — "take a circle and squish it on an angle", because a flat top has no dimension (23:08–23:40). Then a large **upside-down mountain**: from the furthest point on each side, loose diagonals meeting at a point near the centre-bottom. Then the whole five-pass rock recipe on that cone. | An island loop whose convexity is biased so its longest axis is off-vertical, plus a downward cone polygon from the two extreme points; `rock_face()` on the cone. |
| **Vines** (28:59–29:49) | Thick, loose, scraggly lines; the trick is to **trace back up after drawing down, but not perfectly**, so it reads as two vines wrapped round each other. | A stroke down plus a matched stroke back up with a lateral offset that drifts. |

### Principles stated in both videos

- **Legibility beats scale.** "If we were to draw mountains and trees to scale, the trees
  would be literally microscopic … draw them as they actually visually look like trees
  compared to our mountains" (part 2, 04:37–05:16). Every feature is sized so it *reads*
  at viewing distance. This independently confirms §5's rule 5.
- **"It's less about talent and more about patience"** (part 1, 21:34; part 2,
  10:24–10:38) — the look comes from stroke count, not from clever shapes.
- **Nothing has to be perfect; the more organic the better.** Repeated at least six times
  across the two videos. In code: every straight line gets tremor, every regular polygon
  gets noise, and no two features of a kind may be identical.
- **Passes are revisitable** — an earlier pass can be re-opened later to fill gaps.

---

## 2. What already exists (checked, not assumed)

| Claim | Evidence |
|---|---|
| A fantasy-map mode **already exists**: type key `fantasymapgenerator` → `modes/fantasy_map_mode:FantasyMapMode` (1050 lines). It is an fBm/simplex **heightmap** generator: terrain classifies into coloured blocks, then bitmap feature stamps (grey triangles with snow caps, green forest blobs, huts, walled towns) drawn over it, plus settlement labels and roads. | `modes/fantasy_map_mode.py` header + `_get_bitmap`/`_place_feature_stamps`/`prerender`; `modes_registry.json` → `types.fantasymapgenerator` |
| It is **enabled** in both profiles: `modes_config.json` slot 20 and `configs/modes_config_vert.json` slot 39. | parsed both files |
| It is a *different thing from this design*: colour blocks + literal cartoon stamps, no hand-drawn line work, no progressive drawing, and no relation to the video. | read of the mode's render path and stamp bitmaps |
| `designs/mode_ideas_design.md` §4.18 "Autonomous Cartographer" (`cartographer`) is also adjacent — parchment, ink strokes revealing terrain — but it is a **fog-of-war survey simulation** with travelling surveyor icons, not a map being drawn stroke by stroke. | the ideas doc, lines 533–560 |
| The panel is already running on the wall: `.venv/bin/python pixel_dreams.py --panel-port 8090 --panel-bind 0.0.0.0 --config configs/modes_config_vert.json --start 55`, up 2 h 07 m. It is **not** a systemd unit (`deploy/*.service` are not installed). | `ps -o lstart,cmd -p 1138807`; `systemctl --user list-units` shows no pixel_dreams unit; `ss -ltnp` → 8090 |
| That process was started with `--config`, so the panel **cannot** switch its profile (409 by design) but `/api/apply` re-reads the pinned file from disk. | README "WHICH profile is active" + `/api/apply` |

**Decision (D1) — CONFIRMED by the user:** a **new mode under a new name**, `inkmap`,
beside `fantasymapgenerator`; the existing mode is left untouched. *Rejected:* replacing
`fantasymapgenerator` in place — the approach is different enough that the user wants both.
*Consequence:* the rotation will hold both, so `inkmap` was intended to ship **disabled** in the existing
profiles and the user enables it when they like it (phase-5 acceptance step).

---

## 3. Measured facts (this host, these probes)

All numbers from `designs/inkmap_proto/COST_SPIKE.py`; raw output at
`designs/inkmap_proto/cost_spike_output.txt`. Supersampled canvas 2160 × 3840
(= 2 × the panel). **MEASURED** unless marked ASSUMED.

### Environment
- Panel: `DP-1 connected primary 1080x1920+0+0 left`, on a physical 1920×1080 panel.
  **The app surface is 1080 × 1920 portrait.** (`xrandr` on `DISPLAY=:0`)
- 6 ARMv8 cores, 7619 MB RAM, ~3209 MB available. (`nproc`, `free -m`)
- venv: pygame **2.6.1** (SDL 2.28.4), Python 3.10.12, **no numpy, no PIL** —
  everything here is pygame + stdlib. (`pip list`)

### Per-op cost (measured over 3000–4000 iterations each)
| Op | Cost |
|---|---|
| `pygame.draw.line` | 2.63 µs |
| tapered quad (`draw.polygon`, 4 pts) — the pen stroke | 5.87 µs |
| `draw.circle` r=2 | 1.08 µs |
| 5×5 ink-blob `blit` (stipple dot) | 1.31 µs |
| opaque vs `SRCALPHA` surface | **identical** (5.87 vs 5.81 µs) — no reason to avoid alpha |

### The whole sheet is affordable
A full-page map (400 × 700 field, 14.9 % land, 36 071 contour segments) →
**55 203 strokes** (42 083 line, 2 020 quad, 11 100 dot) drawn in **233 ms** of pure
drawing. Extrapolated per-op budget (20 k lines + 12 k quads + 14 k dots) = **0.12 s**.

> **This retires the biggest design risk.** A hand-drawn map is not a real-time
> simulation that must keep up: the entire sheet can be *planned and drawn* in well under
> a second, so "gradually being drawn" is a **presentation** choice, not a performance
> need. The reveal is therefore free to be as slow and deliberate as we like.

### Generation cost, measured end to end (`designs/inkmap_proto/SHEET.py`)
| Stage | Cost |
|---|---|
| Rice pour: 4 clumps × 20 000 grain blits + `tostring` + stride mask + closing | **503 ms** |
| Marching squares 288 × 512 | 75–94 ms |
| Chaining + resample | 3–7 ms |
| Continent border (21 masses, `05` pen) | 25 ms |
| Water illusion, 3 rings | 56 ms |
| Value-noise zoning 96 × 170, 4 octaves | 188–214 ms |
| Mountains + hills + rivers | 80 ms |
| Forest (9 masses, 329 trees) | 102 ms |
| Desert (3 regions, 7 822 dots, 18 dunes) | 239 ms |
| Grass filler (240 tufts) | 44 ms |
| Paper (blotches + fibre + vignette, 1080 × 1920) | 129 ms |
| **Total for a full sheet** | **~1.7 s** (1 704 ms measured; the remainder is the distance field and placement bookkeeping) |

### Anti-aliasing and the reveal (the two things that decide the architecture)
- `pygame.gfxdraw` **has no `aaline`** in this build (it has `arc`, `bezier`,
  `aaellipse`, `filled_polygon`, …). `pygame.draw.aaline` / `aalines` **do** exist, but
  they are 1 px only — useless for a 2–5 px pen stroke.
- **Supersample + downscale** is how a wide stroke gets AA. Full-canvas
  `smoothscale` 2160×3840 → 1080×1920 costs **46–58 ms** — 3 fps, impossible per frame.
- **Dirty-rect flush is cheap**: crop a rect of the 2× surface, `smoothscale` just that
  rect, blit it into the cached 1080×1920 canvas:

  | dirty rect | cost |
  |---|---|
  | 32 × 32 | 0.01 ms |
  | 64 × 64 | 0.09 ms |
  | 128 × 128 | 0.10 ms |
  | 256 × 256 | 0.39 ms |
  | 512 × 512 | 1.54 ms |
  | 40 small 48×48 rects in one frame | 0.79 ms |

  So the reveal can supersample **and** stay at 20 fps with ~0.1–1 ms/frame of ink work.
- Full-screen present (`screen.blit` of the 1080×1920 canvas): **9.50 ms/frame** on the
  dummy driver — `ASSUMED` that the real X/shm path is comparable or better; this is the
  floor, and it is why the reveal should run at ~20 fps rather than 60.
- Memory: a 2160×3840 `SRCALPHA` surface is **33.2 MB**; the 1080×1920 canvas is 8.3 MB.

---

## 4. Architecture

Five new `core/` modules (flat, matching the house style — `core/` is a flat module set,
not a package), one new mode, one new test file.

```
modes/ink_map_mode.py      the mode: config, lifecycle, the reveal loop, screen blit
core/inkdraw.py            drawing vocabulary: PEN sizes, Hand (tremor), pen(), curve(), dot(), hatch()
core/inkland.py            rice pour, closing, marching squares, chaining, resample, distance-to-coast
core/inkfeatures.py        mountain(), hill(), grass(), dune(), pine(), oak(), coast_water(), lake()
core/inkplan.py            value noise, zoning, Placer, build_plan() -> the ordered DrawingPlan
core/inksheet.py           the sheet: paper texture, the 2x ink surface, the dirty-rect flush, the reveal cursor
tests/test_inkmap.py       the phase-by-phase tests
```

### 4.1 The DrawingPlan — why the plan is separate from the drawing

The artist's sequence *is* the design. So the mode never draws during layout: it builds
an ordered list of **passes**, where a pass is `(kind, payload)` and drawing a pass
touches only the ink surface.

```
Passes, in the video's order:
  0  paper            the parchment (built once, 129 ms)
  1  coast_border     every land mass, 05 pen, scraggly   (25 ms of the prototype)
  2  water            offset rings + the 4 alternating patterns, outer rings first
  3  lakes            interior water passes
  4  mountains        ranges first, then tapers
  5  hills            the transition band
  6  rivers           steepest-descent squiggles
  7  desert           rim stipple, then field stipple, then dunes
  8  forest           pine and oak masses
  9  grass            the filler pass over everything still bare
```

Two reasons this shape, rather than "generate an image and reveal it":
1. **The order is the tutorial.** A future phase can reorder or repeat passes (e.g. layer
   more water rings) and the appearance follows the same rules the video gives.
2. **The reveal is a cursor over the plan**, so "draw it over 5 minutes" is
   `cursor += strokes_per_second · dt`, and pausing, fast-forwarding or skipping to the
   end are all trivial and identical to what a person would do.

### 4.2 The hand (progressive reveal)

```
ink   : 2160x3840 SRCALPHA surface (transparent; ink drawn on it, uniform colour)
paper : 1080x1920 opaque parchment, built once at enter()
canvas: 1080x1920  = paper with the flushed ink composited in
```

Per frame:
1. consume strokes from the plan until the frame's stroke budget is used;
2. each stroke draws into `ink` **and** unions its bounds into a dirty rect;
3. flush the dirty rect: crop → `smoothscale` to ½ → blit onto `canvas` with alpha;
4. `screen.blit(canvas)`;
5. clear the dirty rect.

Because only the dirty rect is downscaled, the AA is real and the per-frame cost is
~0.1–1 ms. The frame rate is a config value (`reveal_fps`, default 20) — the sheet only
needs to look like it is being drawn.

An **idle guard**: if the plan is exhausted, the mode stops flushing and only re-blits
the cached `canvas`, so a finished map costs one blit per frame and nothing else.

### 4.3 Stroke budget per frame, and why "5 minutes" is safe

The spike's full-sheet plan measured **55 203 strokes** (with the coast drawn as raw
segments there — chaining and resampling cut its share, so treat this as an upper
bound). Over 5 minutes that is ~200 strokes/s = 10 per frame at 20 fps = ~0.03 ms of
drawing and a dirty rect that a 0.1–0.4 ms flush handles. The measured worst case — all
55 203 strokes drawn in one go — is **233 ms**, so even if the whole plan were dumped
into a single frame the wall would hold. **The reveal cannot overrun the frame.**

### 4.4 Layout and resolution independence

`manager.width/height` is read at `enter()`; the mode scales from a normalised
canvas (0..1 in both axes) so portrait and landscape profiles both work. The
supersample factor and the field grid are derived from the screen size, so the mode is
not hard-wired to 1080 × 1920. Pen widths come from the mm table scaled by
`screen_width / 200 mm`, so a bigger screen gets proportionally heavier lines — the
sheet stays the same drawing.

---

## 5. Calibration rules (each one cost a prototype iteration)

These are the rules the design passes to the implementation. Each was found by rendering
and looking, not by reasoning — the earlier prototypes are kept so this isn't assertion.

1. **Express a rice grain in FIELD CELLS, not pixels.** A grain smaller than a grid cell
   makes the pour a porous speckle: land reads 75 % by cell count while the contour
   explodes into hundreds of fragments and the coast degenerates into a thin scraggly
   band. Calibrate from the video: real rice ≈ 2.5 mm on a 200 mm sheet = 1.25 % of the
   width = ~13.5 px on a 1080-wide sheet = ~27 px at 2× ⇒ **4–7 field cells** at a
   288 × 512 field.
2. **Morphological closing is the "adjust the rice" step** (§1.2). Without it the union is
   grainy and the border is broken. With it the mass is solid and the *scalloped* edge
   survives. Do it with pygame blits (`BLEND_RGB_MAX` dilate; invert, dilate, invert to
   erode) — a Python pixel loop over 147 k cells is ~50× slower.
3. **Stamp the grains with pygame's C rasteriser.** 12 000 ellipses drawn = **38 ms** into a
   32-bit surface (46 ms into an 8-bit palette one), and reading the mask back is one
   `pygame.image.tostring(surf,'RGB')` plus a stride-3 pass = **89 ms** for 331 776 cells.
   A per-cell Python ellipse test — the first attempt — is far slower and no better.
   (In the composed prototype, where each grain is a *rotated sprite* blitted with
   `BLEND_RGB_MAX`, 80 000 grains plus the closing cost 503 ms, i.e. ~6 µs a grain.)
4. **Feature COUNTS come from area, not a global cap.** `n = packing · zone_area_px /
   footprint_px`, where `footprint ≈ (1.4·size)²/2`. A global cap of 150 mountains put
   151 peaks into 8 % of the sheet and they meshed into a **wireframe web** — the single
   worst artefact produced, and it looked like a rendering bug.
5. **Stroke density scales with feature size.** A mountain drawn with 12 strokes looks
   right at 25 px and looks like a bare triangle at 100 px. The artist's own summary
   (21:34) is the rule: the effect is stroke COUNT. Every recipe takes `size` and
   multiplies its stroke counts by `size / reference_size`.
6. **Placement needs one global occupancy grid.** Zone classification alone still lets a
   forest draw on top of a mountain range: each pass needs `can(x,y,r)` / `add(x,y,r)`
   with **per-type radii**. Distinct radii are what let a forest clump internally
   (small radius, trees close) while never landing on a range (large radius).
7. **Zone thresholds must be QUANTILES of the realised field.** Value noise is
   centre-heavy, so an absolute cut put 58 % of the sheet in "mountain" while looking
   like a sensible constant. Quantiles (e.g. mountains = top 10 % of land elevation,
   hills = next 18 %, then moisture splits the rest into desert / forest / plain) give
   the intended mix for any seed.
8. **Minimum-separation sampling needs an occupancy hash and a small try cap.** With a
   plain `any(...)` scan over the accepted list, a restrictive `min_sep` thrashes against
   the cap: measured **4 603 ms for 128 grass tufts** — a 4.4 s stall in the middle of a
   build, which on the wall is a frozen frame. The hash version made the same pass 44 ms.
9. **A strip that runs off the traced field is an OPEN contour — never close it.** The
   original chainer appended the first point to every chain, which drew a **ruler-straight
   line across the sea** (clearly visible in the second prototype). Store `closed` with
   each loop and skip the closing vertex; the coast then simply exits the sheet, which is
   what §1.6 asks for anyway.
10. **Marching-squares saddles need the two DIFFERENT pairings.** Using the same segment
    pair for cases 5 and 10 creates crossings and degree-4 nodes, and the chainer then
    hops between unrelated loops — straight lines jumping across the map. Disambiguate
    the saddle by the cell's average.
11. **Do not supersample-then-downscale per frame.** 46 ms/frame: this is the difference
    between a smooth reveal and a slideshow. Flush dirty rects (§2).
12. **`LIGHT = left` is a single constant, obeyed by every recipe**, or the shading
    contradicts itself between mountains and trees.
13. **Rivers never split.** Enforced structurally (one river = one descent walk), not by
    a post-check, because the video is emphatic and a split is instantly wrong to the eye.
14. **Rock strokes are placed at DIRECTION CHANGES of an edge, never evenly spaced along
    it.** The artist is explicit that the major points come first and texture fills in
    afterwards (part 2, 03:31–04:11) — and her reason is visible: strokes at regular
    intervals read as a comb or a fence, not as rock. Walk the edge, find the turning
    points, and put the verticals there.
15. **Occlusion decides the FULL shading, and the front-most face is drawn last.** A face
    partly hidden behind another is filled solid; a face with nothing in front of it only
    gets partial edge hatching (part 2, 11:50–12:07). Without an occlusion test, cliffs
    and floating islands read flat, because the depth cue *is* the asymmetry.
16. **Thicken and darken selectively.** A canyon's bottom is thickened in a few sections
    only — thickening the whole rim destroys the light/dark contrast that produces the
    depth in the first place (part 2, 22:23–22:33). Same discipline as §5.3's "not on
    every line".
17. **A rock face is five short-stroke passes, not an outline.** A cliff drawn as one
    wiggly parallel line reads as a road. This is rule 5 with the stakes raised: the
    artist's own summary of a cliff is "squiggles, then straight lines, then Y's"
    (part 2, 10:31–10:40), i.e. ~60 short marks for a hand-sized face.
18. **Size for legibility, never for true scale** (part 2, 04:37–05:16: "the trees would be
    literally microscopic"). This is the artist's own statement of rule 5, and it applies
    to every feature: a settlement's houses and a forest's trees are drawn at the size
    that reads at viewing distance.

---

## 6. Registry entry (live in modes_registry.json)

**The live entry is in `modes_registry.json`** (type key `inkmap`); the block below is
generated from it, so the two always agree. Each field's `help` text says which phase
actually draws with it — a control that does nothing yet says so in the panel, because
a knob with no effect is the trap this repo's docs keep warning about. Accepted by the
application's own validators (see the note after the block).

Built from the schema `core/params.py` actually implements: widgets are
`switch, number, text, choice, path, color, range, stringlist, palette, json, secret`;
a param entry may also carry `group` (`appearance`, `layout`, `behaviour`, `data`),
`help`, `label`, `min`, `max`, `step`, `choices` (a closed set, which also forces the
widget) and `suggestions` (known-but-open values). The repo already uses `help` on the
control-panel params, so every field below that is not self-evident carries one.

```json
{
  "types": {
    "inkmap": {
      "entrypoint": "modes.ink_map_mode:InkMapMode",
      "required": [],
      "optional": [
        "seed",
        "draw_minutes",
        "hold_minutes",
        "reveal_fps",
        "paper_tone",
        "ink_rgb",
        "paper_age",
        "vignette",
        "supersample",
        "land_coverage",
        "grain_size_cells",
        "pen_scale",
        "tremor",
        "feature_scale",
        "water_style",
        "water_rings",
        "lake_count",
        "show_mountains",
        "mountain_packing",
        "show_hills",
        "hill_packing",
        "show_rivers",
        "river_count",
        "show_desert",
        "desert_regions",
        "show_forest",
        "forest_masses",
        "show_grass",
        "grass_density",
        "show_cliffs",
        "cliff_coverage",
        "show_canyons",
        "canyon_count",
        "show_waterfalls",
        "waterfall_count",
        "show_islands",
        "floating_islands",
        "show_vines",
        "rock_detail",
        "map_title",
        "settlements",
        "show_roads",
        "road_style",
        "road_count",
        "show_region_labels",
        "region_labels",
        "label_font",
        "label_scale",
        "show_compass",
        "compass_placement",
        "compass_points",
        "show_cartouche",
        "show_border",
        "border_inset"
      ],
      "params": {
        "seed": {
          "widget": "number",
          "group": "behaviour",
          "default": 0,
          "help": "0 = pick one at random and print it in the log. Any other value reproduces that exact sheet, so a map you like can be kept. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "draw_minutes": {
          "widget": "number",
          "group": "behaviour",
          "default": 5.0,
          "min": 0.1,
          "help": "How long the pen takes to draw the whole sheet. 0 = draw it all at once. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "hold_minutes": {
          "widget": "number",
          "group": "behaviour",
          "default": 2.0,
          "min": 0,
          "help": "How long the finished map stays up before the sheet is wiped and a new one poured. 0 = keep it until the mode changes. Not drawn yet - this control becomes live in phase 5 of the design."
        },
        "reveal_fps": {
          "widget": "number",
          "group": "behaviour",
          "default": 20,
          "min": 1,
          "max": 60,
          "help": "Frame rate of the drawing. The reveal only touches the part of the ink layer it changed, so this is about how smooth the pen looks, not about cost. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "paper_tone": {
          "widget": "color",
          "group": "appearance",
          "default": [
            232,
            217,
            184
          ],
          "help": "Base colour of the parchment. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "ink_rgb": {
          "widget": "color",
          "group": "appearance",
          "default": [
            43,
            33,
            26
          ],
          "help": "The ink. A warm near-black reads as pen on paper; pure black reads as printed. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "paper_age": {
          "widget": "number",
          "group": "appearance",
          "default": 1.0,
          "min": 0,
          "max": 3,
          "help": "How much blotching and fibre speckle to work into the paper. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "vignette": {
          "widget": "number",
          "group": "appearance",
          "default": 1.0,
          "min": 0,
          "max": 3,
          "help": "Darkening toward the edges of the sheet. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "supersample": {
          "widget": "number",
          "group": "appearance",
          "default": 2,
          "min": 1,
          "max": 3,
          "help": "The ink is drawn at this multiple of the screen resolution and scaled down, which is what anti-aliases the pen strokes. 1 turns it off (faster, visibly jagged). Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "pen_scale": {
          "widget": "number",
          "group": "appearance",
          "default": 1.0,
          "min": 0.4,
          "max": 2.5,
          "help": "Multiplies every pen width. Nib sizes are the real Pigma Micron millimetres, so this is a fair way to make the whole drawing lighter or heavier. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "tremor": {
          "widget": "number",
          "group": "appearance",
          "default": 0.55,
          "min": 0,
          "max": 3,
          "help": "How unsteady the hand is. The video's own trick is holding the pen higher up, which gives a less controlled line. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "feature_scale": {
          "widget": "number",
          "group": "appearance",
          "default": 1.0,
          "min": 0.4,
          "max": 2,
          "help": "Size of every drawn feature (mountains, trees, hills). Counts follow automatically, because how many fit is derived from the area each one covers. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "land_coverage": {
          "widget": "number",
          "group": "layout",
          "default": 0.55,
          "min": 0.1,
          "max": 0.95,
          "help": "How much of the sheet is land, as opposed to sea. The pour is deliberately pushed off the edges, so the land runs off the page. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "grain_size_cells": {
          "widget": "number",
          "group": "layout",
          "default": 5,
          "min": 2,
          "max": 14,
          "help": "Size of one grain of rice, in field cells. This sets the scale of the scalloped coastline, so it is the single most important dial. Active now: the sheet (phase 1) and the coastline (phase 2)."
        },
        "water_style": {
          "widget": "choice",
          "group": "layout",
          "default": "hash",
          "choices": [
            "hash",
            "squiggle",
            "stipple",
            "wave"
          ],
          "help": "How the sea is indicated. hash = straight hashes and dots, which is the video's main method. squiggle, stipple and wave are the three alternates it shows. Active now: the sheet (phase 1), the coastline (phase 2) and the sea (phase 3)."
        },
        "water_rings": {
          "widget": "number",
          "group": "layout",
          "default": 3,
          "min": 0,
          "max": 6,
          "help": "How many parallel rows of water detail to layer outside the coast. More rows make the land stand out more. Active now: the sheet (phase 1), the coastline (phase 2) and the sea (phase 3)."
        },
        "lake_count": {
          "widget": "number",
          "group": "layout",
          "default": 3,
          "min": 0,
          "max": 12,
          "help": "Lakes inland, drawn with the same water pass on the inside. Active now: the sheet (phase 1), the coastline (phase 2) and the sea (phase 3)."
        },
        "show_mountains": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "mountain_packing": {
          "widget": "number",
          "group": "layout",
          "default": 0.25,
          "min": 0.05,
          "max": 0.6,
          "help": "How much of the mountainous ground is covered by peaks. This is what decides how many mountains to draw. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "show_hills": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "hill_packing": {
          "widget": "number",
          "group": "layout",
          "default": 0.3,
          "min": 0.05,
          "max": 0.6,
          "help": "How much of the hilly ground is covered by hills. Hills are the transition from the ranges down to the plain. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "show_rivers": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "river_count": {
          "widget": "number",
          "group": "layout",
          "default": 8,
          "min": 0,
          "max": 30,
          "help": "Rivers, each running from high ground down to the coast. A river never splits - that is a rule of the technique, not a setting. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "show_desert": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "desert_regions": {
          "widget": "number",
          "group": "layout",
          "default": 2,
          "min": 0,
          "max": 8,
          "help": "Deserts. Each is poured like the land is, stippled dark at the rim and light in the middle, with a few dunes. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "show_forest": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 5 of the design."
        },
        "forest_masses": {
          "widget": "number",
          "group": "layout",
          "default": 6,
          "min": 0,
          "max": 20,
          "help": "Forests. Each is a clump of pines and oaks, still shaded on the right like everything else. Not drawn yet - this control becomes live in phase 5 of the design."
        },
        "show_grass": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "grass_density": {
          "widget": "number",
          "group": "layout",
          "default": 1.0,
          "min": 0,
          "max": 3,
          "help": "How much grass tuft detail is scattered over the ground left bare by everything else. Not drawn yet - this control becomes live in phase 4 of the design."
        },
        "show_cliffs": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "cliff_coverage": {
          "widget": "number",
          "group": "layout",
          "default": 0.35,
          "min": 0,
          "max": 1,
          "help": "How much of the coastline is cliff rather than beach. Cliffs use the vertical-line, Y and hash technique from the second tutorial. Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "show_canyons": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "canyon_count": {
          "widget": "number",
          "group": "layout",
          "default": 3,
          "min": 0,
          "max": 10,
          "help": "Canyons cut inland. Same rock technique as the cliffs, but on their own closed region, shaded all the way round to show the ground dropping inward. Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "show_waterfalls": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "waterfall_count": {
          "widget": "number",
          "group": "layout",
          "default": 2,
          "min": 0,
          "max": 8,
          "help": "Waterfalls, drawn only where a river actually crosses a cliff edge, each with a two-loop splash at the foot. Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "show_islands": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "floating_islands": {
          "widget": "number",
          "group": "layout",
          "default": 2,
          "min": 0,
          "max": 8,
          "help": "Floating islands: a squashed landmass with an upside-down mountain under it. A fantasy element - switch off for a map that stays plausible. Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "show_vines": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "rock_detail": {
          "widget": "number",
          "group": "appearance",
          "default": 1.0,
          "min": 0.3,
          "max": 3,
          "help": "Multiplies the stroke count texturing every cliff, canyon and island. This is the patience dial both tutorials keep coming back to. Not drawn yet - this control becomes live in phase 6 of the design."
        },
        "map_title": {
          "widget": "text",
          "group": "data",
          "default": "",
          "help": "The name written on the sheet. Blank lets the mode invent one from the same word lists the other map mode uses. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "settlements": {
          "widget": "number",
          "group": "layout",
          "default": 6,
          "min": 0,
          "max": 24,
          "help": "Towns and villages, placed on flat ground away from mountains and water, and labelled. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "show_roads": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "road_style": {
          "widget": "choice",
          "group": "layout",
          "default": "dashed",
          "choices": [
            "solid",
            "dashed",
            "double"
          ],
          "help": "How a road is drawn between two settlements. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "road_count": {
          "widget": "number",
          "group": "layout",
          "default": 5,
          "min": 0,
          "max": 20,
          "help": "How many roads to try to build. A road bends around rivers and mountains and refuses to cross a cliff. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "show_region_labels": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "region_labels": {
          "widget": "number",
          "group": "layout",
          "default": 4,
          "min": 0,
          "max": 12,
          "help": "Names written across large regions, smaller and more widely spaced than the settlement labels, as a real map does. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "label_font": {
          "widget": "text",
          "group": "appearance",
          "default": "dejavuserif",
          "help": "Any font name the system knows. A serif reads as a hand-lettered sheet. Lettering is drawn glyph by glyph with a little jitter in position, size and angle, because perfectly set text is the fastest way to make a hand-drawn map look printed. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "label_scale": {
          "widget": "number",
          "group": "appearance",
          "default": 0.024,
          "min": 0.008,
          "max": 0.06,
          "help": "Label size as a fraction of the sheet's short side. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "show_compass": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "compass_placement": {
          "widget": "choice",
          "group": "layout",
          "default": "bottom_right",
          "choices": [
            "bottom_right",
            "bottom_left",
            "top_right",
            "top_left"
          ],
          "help": "Which corner the compass rose takes. That corner is kept clear of terrain so the rose never lands on a mountain. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "compass_points": {
          "widget": "number",
          "group": "layout",
          "default": 8,
          "min": 4,
          "max": 32,
          "help": "Points on the rose: 4 is a plain cross, 8 the classic star, more for an ornate one. Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "show_cartouche": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "show_border": {
          "widget": "switch",
          "group": "layout",
          "default": true,
          "help": "Not drawn yet - this control becomes live in phase 7 of the design."
        },
        "border_inset": {
          "widget": "number",
          "group": "layout",
          "default": 0.035,
          "min": 0.005,
          "max": 0.12,
          "help": "How far in from the edge the ruled border sits. The sheet is drawn a little larger than the screen, so the border is the map's own edge, not the panel's. Not drawn yet - this control becomes live in phase 7 of the design."
        }
      }
    }
  }
}

```
`seed: 0` means "pick one and report it" — the mode prints the seed it used, the same
convention `fantasymapgenerator` already uses, so a good map is reproducible.

`map_title` rather than plain `title` is deliberate: `title` is one of the app's
`COMMON_INSTANCE_KEYS` (`core/config.py`), meaning it is allowed on any mode and reads as
an *on-screen label*, whereas this is the name written **on the sheet**. Two different
things, two keys — do not "tidy" one into the other.

**This block is verified, not proposed.** Extracted from this document and injected into
the real registry, it passes the application's own validator:
`core/validation.validate_registry(check_imports=False)` → **0 errors, 0 warnings**;
`core/params.resolve_params` → **54 fields, 0 warnings**, no field left without a default;
a profile holding an `inkmap` instance → `validate_profile` **0 errors, 0 warnings**; and
with `check_imports=True` the **only** error is the not-yet-written class
(`cannot import module 'modes.ink_map_mode'`). The panel's `validate_param_value` refuses
a bad closed-set value (`water_style='not-a-style'` → *must be one of: hash, squiggle,
stipple, wave*) and an out-of-range number (`draw_minutes=-1` → *must be at least 0.1*)
while accepting good ones — so those schema keys have teeth rather than being decoration.
Reproduce: `SDL_VIDEODRIVER=dummy .venv/bin/python designs/inkmap_proto/REGISTRY_CHECK.py`
(output saved at `designs/inkmap_proto/registry_check_output.txt`).

---

## 7. Phases

Each phase ends with something visible on the wall that the user can judge, and each is
independently verifiable. Riskiest mechanism first (§3 shows it is already measured, so
the risk is retired before phase 1).

### Phase 1 — The sheet — **DONE**
Mode skeleton + registry entry + `core/inksheet.py` paper pass + the reveal plumbing
(idle), landed in the active profile.
**Visible:** aged parchment filling the portrait panel — warm tone, uneven blotches,
paper fibre, a vignette at the edges. Nothing drawn on it.
**Includes:** the mode must survive `--show_modes`, panel param form, the smoke tests and
`validate_configs.py`; and the param audit must be clean for the new type.
**Not in this phase:** any land, any strokes.

**Implementation record (measured, not asserted).** Files: `core/inksheet.py` (353 lines),
`modes/ink_map_mode.py`, `tests/test_inkmap.py` (33 tests), the `inkmap` entry in
`modes_registry.json`. Acceptance report: **`designs/INKMAP_PHASE_01_ACCEPTANCE.md`**;
renders: `designs/inkmap_phase01_sheet.png` and `…_zoom.png`. At the panel's real
1080 × 1920: the parchment takes **141 ms** to build once in `enter()` (128–154 ms across
runs); the ink layer is **2160 × 3840 = 33.2 MB** (allocated but unused this phase);
`update()`+`render()` run at **2.75 ms/frame** to an off-screen surface (the earlier
measurement of a *display-surface* blit at this size was 9.50 ms, so the on-wall ceiling is
~105 fps — the acceptance record says which of the two is actually verified). The
rendered sheet measures 275 distinct colours, centre `(226, 211, 179)` against corner
`(207, 194, 164)`, and the same pinned seed reproduces it byte for byte. Landed in
`configs/modes_config_vert.json` **slot 56** through `ProfileEditor` (validated, atomic, backup
at `configs/.backups/…`); a structural diff of the profile before/after shows that one slot
added and nothing else changed. **Correction:** this record originally said the slot landed
*disabled*. It did not. The profile schema treats an ABSENT `enabled` key as enabled (only an
explicit `false` disables, `core/config.py`), and the slot was written without the key, so the
mode has been in the rotation since 17:58:49 — which is also how it reached the wall without
anyone asking. Verified against the running app's own status rather than by reading the file. `validate_configs.py --all`: 0 errors.

**Two texture failures found by looking at the render, and kept in the code as comments:**
stamped discs at a low alpha are invisible (measured 7 levels of low-frequency contrast on a
540 × 960 sheet — flat paper), and raising the alpha only makes each disc readable as a disc
(soft-edged, then a field of bubbles as the count grew). A stamped mark is visible whatever
its alpha, because it has a centre. The ageing is therefore a **value-noise field**, which
measures 9.1 levels of contrast against 0.0 for a plain sheet and has no shape to see.

### Phase 2 — The coastline — **DONE**
`core/inkland.py` (grain pour → closing → marching squares → chain → resample) +
`core/inkdraw.py` (`Hand`, `pen`) + the `05` continent border, revealed progressively.
**Visible:** the continent outline drawing itself, scraggly, off the edges of the sheet.
**Acceptance:** the outline is open where it leaves the sheet (no ruler lines), the
scallop scale matches the grain size, and the pour is reproducible from a seed.

**Implementation record (measured, not asserted).** Files: `core/inkdraw.py` (165 lines),
`core/inkland.py` (415), `modes/ink_map_mode.py` (294); tests `tests/test_inkdraw.py` (25),
`tests/test_inkland.py` (36) and 9 more in `tests/test_inkmap.py` (42). Gate:
`designs/inkmap_proto/PHASE2_CHECK.py` — **13 checks, 0 failed**. Acceptance report:
**`designs/INKMAP_PHASE_02_ACCEPTANCE.md`**; renders: `designs/inkmap_phase02_coast.png`,
`…_coast_zoom.png` and `…_in_progress.png`. At 1080 × 1920, seed 4242: **`enter()` now costs
436–450 ms** (141 ms of paper + ~300 ms of pour, trace and plan); the pour lays **20 672
grains in one attempt** for **54.9 % land against the 55 % asked**; the trace finds 29
outlines, of which **6 survive as land masses**; the plan is **898 pen strokes**, and a frame
that draws, composites and blits costs **2.07 ms worst / 1.33 ms median** (corrected: the 1.47 ms
first recorded here timed `render()` after the flush, so the composite went uncounted — see the
phase-3 record). The pen is visible immediately: sampled
ink pixels at 0/25/50/100 % of the plan run **0 → 699 → 1386 → 3027**. The grain dial
measures as the design claims — direction reversals per 1000 px of coast fall **12.8 → 8.8**
as the grain goes 1.5 mm → 6 mm.

**Five mechanism failures found by measuring, all recorded as comments in the code:**
(1) the `land_coverage` dial **saturated** — it drove the *number of grains*, and pouring more
rice into a clump that is already full adds no area at all, so it asked for 55 % and reported
**77 % on every attempt** however hard it scaled the count down; it now drives the clumps'
*footprint*, and inverts a measured response table, which lands every target inside **0.015**
on the first attempt (the un-inverted version was out by 0.4 at the low end: asking for 0.20
produced 0.40). (2) Its correction pass **re-rolled the dice** — a fresh layout per attempt —
so "correcting" asking-for-0.30 produced 0.42, 0.15 and 0.60 in three tries: noise, not
refinement. The layout is now drawn once and only rescaled. (3) `inkdraw.stroke` assumed
**which pair of a segment's four corners was "top"**, which is backwards for horizontal and
vertical strokes, so it under-reported its own bounds — and the caller composites only what
those bounds cover, so a length of ink would have silently never reached the paper. A test
that walks the rect and checks everything drawn is inside it caught this. (4) `chain_loops`
defaulted to **`min_len=10`** and compared it against the chain *before* it appended the
closing point, so a small island's nine-point contour was thrown away before the size filter
ever saw it — a second, invisible filter on top of the one that is supposed to decide what
counts as an island. (5) The grain sprites lost area to **integer rounding at small surface
sizes** (a 5-cell grain is only a 6 × 2 px ellipse on a 240 × 400 test sheet), which quietly
changed the pour's coverage at small sizes and nowhere else; they are oversampled now.

**One tuning decision worth naming.** The first size filter (40 cells²) kept **24 land
masses**, about twenty of them single grains traced out where the Gaussian clumps' tails
scattered them. Real poured rice does not leave twenty isolated grains far from the
clumps, and the sheet read as a lava lamp rather than a map. The measured areas of one
reference pour fall 75 990, 44 499, 15 951, 9 100, then 1 502, 1 370, 600, 538 …, so the
filter sits in that gap: a few continents and a handful of islands.

**Known limitation of this phase, stated plainly.** The coastline's detail is uniform in
scale — one bump size everywhere — because the grain is one size. Real coastlines and the
tutorial's maps mix long sweeping curves with tight wiggles. Varying the grain scale across
the pour is not in the approved schema (there is no such parameter) and is not attempted
here; it is noted for whatever phase wants it.

### Phase 3 — The sea — **DONE**
`coast_water()`: offset rings, the four alternating patterns, layering; plus lakes.
`water_style` / `water_rings` become live panel parameters.
**Visible:** the water hatching appearing after the border, ring by ring.
**Acceptance:** all four patterns appear and are distinguishable; changing `water_style`
in the panel changes the drawn sea without a restart.

**Implementation record (measured, not asserted).** New file `core/inkwater.py` (535 lines);
`modes/ink_map_mode.py` grew to 356; tests `tests/test_inkwater.py` (42) and 9 more in
`tests/test_inkmap.py` (51). Gate: `designs/inkmap_proto/PHASE3_CHECK.py` — **15 checks, 0
failed**. Strategy probes: `designs/inkmap_proto/WATER_SPIKE.py` and `WATER_SPIKE2.py`.
Acceptance report: **`designs/INKMAP_PHASE_03_ACCEPTANCE.md`**; renders:
`inkmap_phase03_sheet.png`, `…_sea_zoom.png`, `…_in_progress.png` and one per style
(`…_sea_{hash,squiggle,stipple,wave}.png`). At 1080 × 1920, seed 4242: **`enter()` is now
696–713 ms** (the sea adds ~260 ms to phase 2's 440 ms); the plan is **898 coast + 932
sea/lake = 1830 strokes**, so the coast is 49 % of the drawing time rather than all of it.
The sea is **6 993 ring vertices of which 89 (1.3 %) fall over land** — the corners an offset
cuts across in a tight bay — and after clipping the hashes to the water, **all 1 696 of them
end at sea**. A frame measured the way the app runs (one composite per frame's worth of
drawing, 6 001 frames simulated): **median 1.37 ms, worst 2.18 ms**.

**Three things the design did not anticipate, all found by rendering and measuring:**

1. **A parallel curve of this coastline folds.** The design specified the rings and the
   patterns but not how a ring is produced, and the honest answer turned out to be that the
   coastline's scallops are the *same order of size* as the ring offsets, so a true parallel
   curve doubles back at nearly every concave wiggle. Measured: at the design's own 13/21/29
   ink px the sea is a ruffled fringe; widened to a readable band (2 mm and out) the same code
   gives a braid of doubled lines and dark knots. Two mechanisms fix it and both are
   load-bearing: the ring's SOURCE is averaged over ~10 mm before it is offset (a hand traces
   the shape it sees, not every scallop again), and a fold cutter splits the curve wherever its
   local direction reverses against the coast's — which reads as the pen lift the artist
   describes when she says the line "does not have to be perfect".
2. **The ring offsets had to be widened, against the doc.** 13/21/29 ink px is 6.5–14.5 screen
   px on a continent 500 px across: narrower than three line widths, so the sea read as a
   fringe trimming the coast. Widened to **2.0 mm out and 1.6 mm per ring** (recorded in
   `inkwater.RING_FIRST_MM` / `RING_STEP_MM` with the reason). The tutorial's own maps hatch a
   band around 5–10 % of the land's width, which is 4–9 mm here.
3. **Hashes overshot onto the continent.** Measured on a whole sea: 162 of 1 696 hashes ended
   ON the land, because across a narrow inlet the outward normal points at the far shore. Each
   hash is now clipped to the water it can reach (`water_length`), and the count is zero.

**Two decisions worth naming.** The **rejected alternative for the rings** is a morphological
dilation of the mask (exact, cannot fold, reuses phase 2's tracer) — rejected on cost, measured
at 540 ms against 10 ms for every mass, because it needs a full marching-squares pass per ring.
And **"ring by ring" is implemented mass-by-mass**: the artist finishes the water around one
coast before moving to the next, so that is what the plan does, and the in-progress render shows
one coast hatched while the others wait.

**A phase-2 measurement error, found while re-measuring frames here.** The phase-2 gate flushed
the dirty rect *before* timing `render()`, so its "1.47 ms" was the blit alone and the composite
was never counted — and the same mistake would have shipped a 61.76 ms number in this phase's
gate, which is what a flush after 900 items really costs (it composites nearly the whole sheet:
the 46–58 ms full-canvas downscale from phase 1). Both gates now measure one composite per
frame's worth of drawing, which is what the app does. The corrected phase-2 figure is in its
acceptance record.

### Phase 4 — The land within
`core/inkplan.py` zoning + `Placer`, and `core/inkfeatures.py` mountains, ranges, hills,
rivers, desert, dunes, and the grass filler.
**Visible:** mountains appearing in ranges tapering into hills, rivers running from the
high ground to the coast, a desert with a dark rim, all filled in with grass.
**Acceptance:** no two features overlap; the mountain count follows `mountain_packing`
against the zone area; rivers reach the coast and never split; shading is right-handed
everywhere.

### Phase 5 — The forest, and the cycle
Pines and oaks, forest masses, then the sheet's life cycle: draw → hold → wipe → redraw
with a new seed, driven by `draw_minutes` / `hold_minutes`. Enabled in the profiles.
**Visible:** trees appearing last over the bare ground, then the finished sheet holding,
then a clean parchment and a new map.
**Acceptance:** a full map draws in `draw_minutes ±10 %`; the finished sheet holds without
the mode burning CPU (the idle guard); wipe-and-redraw is clean with no residue.

### Phase 6 — The rock (part 2 of the series)
`rock_face()` — the five passes of §1b — plus cliffs along the coast, canyons inland,
waterfalls where a river crosses a cliff edge, floating islands, and vines.
**Visible:** the coastline gaining vertical cliff faces with Y's and hatch shading,
gashes opening inland, a waterfall with a splash at its foot, and one or two islands
floating over the sea.
**Acceptance:** cliff strokes sit at direction changes and not at regular intervals; a
cliff face's five passes are all present and in order; a face hidden behind another is
fully shaded and the front-most face is drawn last; a canyon's bottom is thickened in a
few sections only; a waterfall only appears where a river meets a cliff.
**Risk to watch:** this is the densest feature in the design (a hand-sized rock face is
~60 strokes) and there can be many along a coast. Measure the stroke count and the build
time against §3's budget before accepting the defaults, and lean on `rock_detail`.

### Phase 7 — The map as a document
Settlements, roads, labels, a compass rose, a title cartouche and the ruled border — the
things that turn a drawn landscape into a map someone made. None of it is in either
video; it comes from the wider tradition and from what makes a kiosk image worth looking
at twice.
**Visible:** named towns joined by dashed roads, region names across the empty ground, a
compass rose in a corner, a title, and a ruled border.
**Acceptance:** labels never overlap each other, a road, or a mountain; the compass
corner really is clear of terrain; every placename is reproducible from the seed; the
label lettering is jittered so it does not read as set type.
**Needs from the user (see §9):** the title text, and whether the naming should be
invented fantasy names or something themed.

### Deferred (named, not scheduled)
- Multi-sheet maps that continue on a second page (mentioned at part 1, 05:10–05:32, but
  it is a physical-paper affordance — on a single panel it has no meaning).
- A third tutorial in the series, if the artist publishes one; the technique tables in
  §1 and §1b are the place to extend.

---

## 8. Verification plan

- **Already done at design time (do not redo it):** the registry entry in §6 passes the
  app's own validator, the panel's param resolver, and the profile validator — see the
  evidence note under the registry block.
- **Automated:** a new `tests/test_inkmap.py` beside the repo's existing mode tests —
  the class constructs from a merged config; the plan builder is deterministic for a
  seed; the pour mask has one dominant component; every contour loop records `closed`
  correctly; the Placer refuses an overlapping feature and accepts a clear one; a stroke
  plan's pass order matches §4.1; the reveal cursor never runs past the plan.
- **Off-display:** run the mode headless (`SDL_VIDEODRIVER=dummy`) for N frames with a
  frame-time budget assertion, and measure the drawn output on the ink surface (not the
  config) — the repo's rendered-output measurement approach.
- **Suite gate:** `SDL_VIDEODRIVER=dummy python -m pytest tests/` must pass, plus
  `python validate_configs.py --all` (0 errors; it reports 1 pre-existing warning about a
  Windows path in `modes_config_windows.json`).
  **Known pre-existing flake, not caused by this design:** on the first full run while
  writing this doc, `tests/test_panel_apply.py::test_disabling_a_mode_takes_it_out_of_the_rotation_without_a_restart`
  failed once inside the 200 s suite (`1 failed, 607 passed`) and then passed **4 / 4 runs
  in isolation** (2.5–3.1 s each). It is a wall-clock race: the test samples
  `before["mode_index"]` and then applies a profile while the kiosk runs `--auto 1`, so
  under load the on-screen mode advances before the apply lands and the app *correctly*
  starts the new rotation at the next allowed mode — while the test's escape hatch only
  covers `before["mode_index"] == 1`. It did **not** recur on the phase-1 runs. A later
  phase should still fix the test's window (sample the index immediately before the apply,
  or wait for a stable state) rather than the assertion.
- **On the wall:** the user's own check, per phase — that is the acceptance that counts.
  The running process was started with `--config configs/modes_config_vert.json`, so
  after the new slot is added to that file the panel's **Refresh**/apply re-reads it and
  the new mode can be stepped to without a restart. **ASSUMED**: that `/api/apply`
  re-reads `modes_registry.json` for a *new type* as well as the profile — the panel
  token is required for the API, and this must be probed in phase 1 before it is promised.
  If it does not, the mode is verified by a separate app instance on a free port rather
  than by disturbing the wall.

---

## 9. Decisions (answered, plus three still open)

Answered by the user, and folded into this document:

| # | Decision | Answer | Where it lands |
|---|---|---|---|
| D1 | Relationship to `fantasymapgenerator` | **A whole new mode under a new name** — `inkmap`, beside it | §2, §6 |
| D2 | Labels, settlements, roads, compass rose, cartouche | **In scope** — a labels-and-settlements phase | §7 phase 7 |
| D3 | After the sheet finishes | **Draw, hold 2 min, wipe, redraw on a new seed** | §6 `hold_minutes`, §7 phase 5 |
| D4 | Ink and paper tone | **Warm sepia (43,33,26) on aged parchment (232,217,184)** | §6 `ink_rgb` / `paper_tone` |
| D5 | Second video's terrain (cliffs, canyons, waterfalls, floating islands) | **In scope** | §1b, §6, §7 phase 6 |

Settled in this document, not put to the user (each is recorded with its rejected
alternative in §2, §3 and §5): right-side shading as a single `LIGHT` constant (§1.17);
anti-aliasing by supersample plus dirty-rect downscale (§3); pen widths from real nib
millimetres (§1); the plan/reveal split (§4.1); feature counts from zone area (§5.4).

**Still open — three things only the user can supply:**

1. **The title.** `map_title` defaults to blank, which makes the mode invent a name. If
   you want a fixed title on every sheet, that is a string only you can give.
2. **The naming flavour.** Settlement and region names can be invented fantasy words (as
   `fantasymapgenerator` already does) or themed to something specific. Phase 7 needs the
   answer before it writes a word list.
3. **Whether floating islands belong by default.** They are a fantasy flourish; a world
   with them reads as high fantasy, without them as low. Ships as `true` in §6 — say if
   you would rather they were off unless asked for.

---

## 10. Design-time evidence in this repo

`designs/inkmap_proto/` — throwaway prototypes, **not** wired into the app:

| File | What it is |
|---|---|
| `COST_SPIKE.py`, `cost_spike_output.txt` | the measurements in §3 |
| `PRIMITIVES.py` | the drawing vocabulary + land/water/feature recipes, as prototyped |
| `SHEET.py` | the composed sheet: pour → contour → border → water → zoning → features |
| `ref_render.png` | the last render (`SHEET.py` output) |
| `VIDEO_TRANSCRIPT.txt` | the part 1 transcript §1 was built from |
| `VIDEO2_TRANSCRIPT.txt` | the part 2 transcript §1b was built from |
| `REGISTRY_CHECK.py`, `registry_check_output.txt` | the probe proving §6's registry entry passes the app's own validators |
| `PHASE1_CHECK.py` | phase 1's own verification: renders at 1080 × 1920 off-display and asserts the drawn output (not the config), saving the PNGs |
| `ADD_TO_PROFILE.py` | lands the mode in a profile through `ProfileEditor` — validated, atomic, backed up. This is the script that DOES write `"enabled": False` and asserts it; the slot actually in the profile was added without the key and so is enabled |

Phase evidence outside this folder: `designs/INKMAP_PHASE_01_ACCEPTANCE.md`,
`designs/inkmap_phase01_sheet.png`, `designs/inkmap_phase01_sheet_zoom.png`.

`ref_render.png` is **honest but incomplete**: the coast, the sea and the paper read as
hand-drawn (that was the point of building it), while the inland features are still too
sparse and too uniform — which is rules 4, 5 and 6 of §5 not yet applied. The prototypes
exist to settle feasibility and calibration; the phases implement it properly.
