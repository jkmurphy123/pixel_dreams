# Acceptance report — ink-map Phase 2 (the coastline)

Date: 2026-10-16 18:14 EDT. pygame 2.6.1 / SDL 2.28.4, Python 3.10.12, no numpy and no PIL.
`/mnt/ssd/projects/pixel_dreams`, host `jetsons` (192.168.40.216). Panel facts: `xrandr` reports
`DP-1 connected primary 1080x1920+0+0 left` — the app's surface is **1080 × 1920 portrait**, and
every size below is at that, not at the panel's physical 1920 × 1080.

Scope of the phase: the coastline. Rice is poured onto a field, the grains are welded into land, the
outline is traced, and the heavy `05` nib draws it in short runs so you watch the hand travel. Sea,
mountains, rivers, desert, forest, rock and lettering are later phases; every control that does not
draw yet says which phase brings it in, and twelve that now do draw say so instead.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

Artifacts: `designs/inkmap_phase02_coast.png` (the finished 1080 × 1920 sheet),
`…_coast_zoom.png` (a 1.8× crop, for the line), `…_in_progress.png` (40 % of the pen strokes —
the in-progress state is the feature, so it gets its own render).
Re-runnable: `designs/inkmap_proto/PHASE2_CHECK.py` (the phase gate),
`…/SYNC_DOC_REGISTRY.py` (regenerates the design doc's §6 block from the registry).
Code: `core/inkdraw.py`, `core/inkland.py`, `modes/ink_map_mode.py`, `tests/test_inkdraw.py`,
`tests/test_inkland.py`, `tests/test_inkmap.py`, and twelve `help` strings in `modes_registry.json`.

## Automated (`SDL_VIDEODRIVER=dummy .venv/bin/python -m pytest tests/` — 711 passed, exit 0)

No network, no paid calls, nothing mutated outside a tmp path. 70 of the tests are new this phase
(25 in `test_inkdraw.py`, 36 in `test_inkland.py`, 9 more in `test_inkmap.py` — the suite went from
641 to 711, collected and counted).

| Area | Coverage |
| --- | --- |
| nib sizes | the table is the real Micron millimetres, heaviest last; widths scale with the **sheet**, not the screen (2× the surface, 2× the width); `pen_scale` multiplies every nib equally; a nib never rounds away below 0.6 px |
| nib pressure | light at both ends, full in the middle, clamped outside 0–1 |
| the hand | zero tremor is a straight line; a shakier hand wanders further; the amplitude is in **millimetres** so it is the same wobble at any resolution; the same seed gives the same hand |
| the wander is an AR(1) walk | successive offsets correlate **above 0.4** (white noise would be ~0). This is the property that makes sharing one hand across the runs of an outline necessary rather than a nicety |
| jitter direction | displacement is perpendicular to the direction of travel, along x and along y |
| strokes | ink lands; a longer stroke draws proportionally more; taper thins **both** ends and no-taper does not; a stroke reports bounds it actually stayed inside (see deviation 3); zero-length segments do not break it; undrawable input returns `None`; the colour is used; **drawing advances the hand** so the next run carries on |
| the tracing grid | doubling both the surface and the resolution gives the same grid; the grid covers the surface exactly; the resolution does **not** move when the grain-size dial does |
| grains | 3 thicknesses × 24 angles, pre-rendered; a grain is an ellipse, wider across than at its end |
| marching squares | a lone block traces one closed loop of the measured area; **uniform ground produces no contour at all**; the two saddle cases take opposite pairings and neither pairing shares an endpoint (a shared endpoint is a four-way node, and the walk then jumps between unrelated outlines) |
| chaining | an open chain stays open with no repeated endpoint; a chain returning to its start closes; fragments below the minimum are dropped; a closed loop's final segment is a real edge and not a chord across the map; a small closed island survives the walk (it did not before — deviation 4) |
| closing | grains with a 3-cell gap become one mass; grains 29 cells apart do not; radius 0 changes nothing |
| resample / split | points are evenly spaced with the ends preserved; a path shorter than the step is left alone; splitting keeps **every** vertex with no duplicates and run lengths near the target |
| outlines leaving the sheet | a band of land across the field traces outlines that are **open**, with no vertex on the field's edge rows |
| the coverage dial | lands within 0.06 of 0.30, 0.55 and 0.75 on a single attempt; more asked-for land stays more land across the dial; the response is monotone |
| grain size | `grain_px` is the physical size claimed; coarser rice measurably reduces the outline's direction reversals per unit length |
| the pour | the same seed pours the same mask bytes and the same outlines; a different seed does not; `on_land` agrees with the mask and is false off the field |
| what the pour reports | outlines biggest first; the trace runs **once** and is reused; the size filter keeps and drops the right outlines; `traced_loops` counts what the filter would drop; areas are in cells and points are in surface units |
| mode, phase 2 | `enter()` queues the coastline without drawing it; the pen marks the paper; ink increases monotonically through the plan; a seed reproduces the **whole** sheet (paper + pour + coast), not just the paper; the land dial moves the sheet between land and sea; the whole plan is drawn by **one** hand and only outline ends are tapered; an outline leaving the sheet is never closed with a straight line; `status()` reports grains, masses and coverage; the update path paces at `reveal_fps` and an empty plan is finished immediately |
| the panel stays honest | every control's `help` names its phase, **and** the set of controls whose help says "Active now" is compared both ways against the mode's own `LIVE_PARAMS` — a control can neither stop working unnoticed nor claim to work |
| this repo's validators | `validate_registry(check_imports=False)` and `validate_profile` on an instance: no errors and no warnings |
| the parameter audit | `audit_source` over `modes/ink_map_mode.py` and `core/inksheet.py`: clean |

## The phase gate (`designs/inkmap_proto/PHASE2_CHECK.py` — 13 checks, 0 failed)

At 1080 × 1920, seed 4242, everything off-screen:

| Measured | Value |
| --- | --- |
| `enter()` (paper + pour + trace + plan) | 436–450 ms, of which the paper is 141 ms |
| the pour | 20 672 grains, **1 attempt**, **54.9 %** land against 55 % asked |
| the trace | 29 outlines found → **6 land masses** |
| the plan | **898 pen strokes** at `draw_minutes=5` |
| a frame (draw + composite + blit) | **2.07 ms worst, 1.33 ms median** over 6 001 simulated frames — CORRECTED. The 1.47 ms first reported here timed `render()` AFTER flushing the dirty rect, so the composite was never counted. Re-measured the way the app runs (one composite per frame's worth of drawing) the number is the one above; the mistake was found while measuring phase 3, and it would have hidden a real cost, because a flush after hundreds of items composites nearly the whole sheet and costs 46–58 ms |
| the pen is visibly working | sampled ink pixels at 0 / 25 / 50 / 100 %: **0 → 699 → 1386 → 3027** |
| the grain dial | direction reversals per 1000 px of coast: **12.8** at 1.5 mm rice → **8.8** at 6 mm |

## Design §7 Phase 2 checks (the doc's own acceptance list) — all PASS

| The doc asks | Measured |
| --- | --- |
| the outline is open where it leaves the sheet | all **6** masses are open (`closed=False`); **0** segments are drawn *along* the sheet's edge; the **4** vertices that touch the edge are exactly the ends of open outlines — indices 0 and `len-1` |
| no ruler lines | no outline repeats its first point when it is open, and every closed outline does. The straight chord that closing an off-sheet outline would draw is structurally impossible: the flag is carried through and the mode respects it |
| the scallop scale matches the grain size | 12.8 → 8.8 reversals per 1000 px as the rice goes 1.5 mm → 6 mm |
| the pour is reproducible from a seed | same seed → identical mask bytes, identical coverage, identical plan length; a different seed → a different mask |

## Known deviations, and why

1. **`ISLAND_MIN_CELLS` is a module constant, not a panel control.** The approved schema (§6) has no
   island-count key and this phase did not add one. Its value (1200 cells²) is tuned to the measured
   gap in the pour's outlined areas — 75 990, 44 499, 15 951, 9 100, then 1 502, 1 370, 600, 538 …
   The first value tried (40) kept 24 masses, about twenty of them single grains traced out where the
   Gaussian clumps' tails scattered them, which read as a lava lamp rather than a map. Real poured
   rice in clumps does not leave twenty isolated grains far from the clumps, so the filter is a
   fidelity fix, not a stylistic one.
2. **`POUR_CLUMPS = 4` and the coast resample/run lengths (4 px, 16 px) are constants too**, for the
   same reason. The run length is what sets the pen's visible speed: 898 strokes × 16 px over five
   minutes is ~33 screen px/s, a careful crawl.
3. **`inkdraw.stroke` had to be fixed mid-phase.** It assumed which pair of a segment's four corners
   was "top", which is backwards for horizontal and vertical strokes, so it under-reported its own
   bounds. The caller composites **only** what those bounds cover, so a length of ink would have
   silently never reached the paper — no exception, no visible error, just missing ink. A test that
   walks the reported rect and checks everything drawn is inside it caught it. It is the one bug this
   phase that would have been genuinely hard to find by looking.
4. **`chain_loops`'s `min_len` default dropped small islands silently.** It was 10, tested against the
   chain *before* the closing point was appended, so a 2 × 2 island's nine-point contour was thrown
   away before the caller's own size filter ever saw it. Now 4, and the area filter is the only thing
   that decides what counts as an island.
5. **`FOOTPRINT_RESPONSE` is calibrated at the reference grain size (5 cells).** At other grain sizes
   the pour still lands within ~0.04 of target rather than ~0.015, and the mode reports the coverage
   it actually achieved. This is a measured table, not a model: it was fitted by pouring single
   attempts across the dial, and it is only valid for this clump count.
6. **The line is 2.43 screen px wide at the default `pen_scale`** — 0.45 mm on a 200 mm sheet, which
   is proportionally **heavier** than the tutorial's own border line on A4. It reads as a fine but
   confident line on the wall. If it turns out too faint at viewing distance, `pen_scale` is the dial
   and no code change is needed.
7. **`enter()` is now 436–450 ms**, up from 141 ms: the pour, the trace and the plan all happen
   synchronously when the mode comes up, so there is a visible stall when it appears. It is bounded
   (one pour in the common case; the correction pass only runs when the coverage is more than 0.045
   off) and it is not threaded — the design's threading note is about network I/O, not generation.
   Phase 1's honest limitation is retired by this: the sheet is no longer empty.
8. **Twelve registry `help` strings changed** (the parameters that draw now say so), and the design
   doc's §6 block was regenerated **from the registry** by `SYNC_DOC_REGISTRY.py` rather than edited,
   because a hand-copied schema drifts. A structural diff of the registry before/after shows 12
   changed leaves and all of them are `help` strings.
9. **The coastline's detail is uniform in scale** — one bump size everywhere, because the grain is
   one size. Real coastlines and the tutorial's maps mix long sweeping curves with tight wiggles.
   There is no parameter for varying the grain scale across the pour and this phase did not invent
   one. Recorded in the design doc as this phase's known limitation.

## Not verified at all

- **Nothing has run on the real display.** Every number here is off-screen
  (`SDL_VIDEODRIVER=dummy`) or against a plain surface. The live kiosk on :8090 was left alone
  throughout and still holds slot 55.
- **The panel form has not been opened in a browser** this phase. What the tests do verify is the
  data behind it: the twelve live controls' help text, and the two-way agreement with `LIVE_PARAMS`.
  The form itself was exercised over HTTP in phase 1, not since.
- **The mode is NOT disabled** in `configs/modes_config_vert.json` (slot 56) — phase 1's report of
  that was wrong and is corrected in the phase-1 record. The schema treats an absent `enabled` key as
  enabled, and the slot has no such key, so the mode is in the rotation. It is also how the mode came
  to be on the wall: the app auto-applied the profile the moment the slot was saved.
- **A running app picks up a new mode TYPE but not new CODE.** Measured, not inferred. The kiosk that
  was already running when `inkmap` appeared (up since 15:01:53) rebuilt its mode list and created an
  `InkMapMode` at 17:58:49 — Python had never imported the module before, so it took the copy on disk
  at that moment. Phase 2's drawing code was written at 18:01–18:12, *after* that import, and the
  process kept the phase-1 module in `sys.modules`: it drew the parchment and an empty plan, exactly
  as phase 1 specifies, and no restart or re-apply would have changed that. Reaching phase 2 on the
  wall therefore REQUIRES a restart. This closes phase 1's open question ("whether a running process
  can pick up a new type without a restart is still unproven"): yes it can, and separately, a module
  it has already imported never reloads.
- **The stall on entry has not been timed inside the running app**, only in isolation.
