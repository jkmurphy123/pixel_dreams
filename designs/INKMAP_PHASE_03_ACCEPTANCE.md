# Acceptance report — ink-map Phase 3 (the sea)

Date: 2026-10-16 19:35 EDT. pygame 2.6.1 / SDL 2.28.4, Python 3.10.12, no numpy and no PIL.
`/mnt/ssd/projects/pixel_dreams`, host `jetsons` (192.168.40.216). Panel facts: `xrandr` reports
`DP-1 connected primary 1080x1920+0+0 left` — the app's surface is **1080 × 1920 portrait**, and
every size below is at that, not at the panel's physical 1920 × 1080.

Scope of the phase: the sea. A line is traced parallel to each coastline, the video's four units are
hung off it, and the lakes get the same pass on their inside. Mountains, hills, rivers, desert,
forest, rock and lettering are later phases, and every control that does not draw yet says so on the
panel.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

Artifacts: `designs/inkmap_phase03_sheet.png` (the finished sheet),
`…_sea_zoom.png` (a 1.7× crop for the hatching), `…_in_progress.png` (the coast complete and the
first coast hatched — the in-progress state is the feature), and one full sheet per style:
`…_sea_hash.png`, `…_sea_squiggle.png`, `…_sea_stipple.png`, `…_sea_wave.png`.
Re-runnable: `designs/inkmap_proto/PHASE3_CHECK.py` (the phase gate),
`…_apply_check.py` (the panel apply path, kept in the scratch dir as it starts a process).
Code: `core/inkwater.py` (new), `modes/ink_map_mode.py`, `tests/test_inkwater.py` (new),
`tests/test_inkmap.py`, and three `help` strings in `modes_registry.json`.

## Automated (`SDL_VIDEODRIVER=dummy .venv/bin/python -m pytest tests/` — 762 passed, exit 0)

No network, no paid calls, nothing started that outlives the check. 51 of the 762 are new this phase
(42 in `test_inkwater.py`, 9 more in `test_inkmap.py` — the suite went from 711 to 762, collected and
counted).

| Area | Coverage |
| --- | --- |
| ring geometry | offsets count, grow outward, are physical (double the resolution, double the distance); no rings means none |
| **the sea is on the sea side** | the outward sign is TESTED against the land, not assumed from the contour's winding; an island's ring is further from its centre than its coast is |
| offsetting | every vertex moves the same distance; an OPEN coast's ends are not joined (the phase-2 chord rule, one ring further out); a single point offsets to nothing |
| smoothing | removes the fine zigzag from the interior while keeping the line's overall shape and mean; a path shorter than the window is untouched |
| **fold cutting** | a clean parallel line is not cut; an explicitly folded one is cut into runs; and cutting never loses more than 40 % of the line |
| the four units | they are the video's four, all distinct, each containing a hash |
| the four styles | hash = one straight line; stipple = dots only; squiggle = two pieces with a break; wave = one stroke of four points swinging across the line; unknown style falls back to a hash rather than drawing nothing |
| **hashes stay off the land** | a hash from the island's centre is refused outright; from the sea the full length is allowed; from the coast it is cut to the water that is there — and in a real sea **no** hash tip is on land |
| drawing | an item draws its parallel line, its hashes and its dots; an empty item draws nothing and reports no rects |
| dilate / erode | growing the mask grows the land, shrinking it shrinks it, and eroding far enough removes a thin feature entirely |
| lake placement | every lake is on land; the separation is respected **in the units it is expressed in** (this failed: a squared distance in surface units was compared against a squared threshold in cells, so two lakes 45 px apart passed a 60 px minimum); and no room means no lakes rather than a lie |
| lake shape | closed, wobbly, within 0.4–1.5 of the asked radius, squashed wider than tall; three inward rings with the innermost as dots only |
| the whole sea | no rings means no sea; more rings means more sea; ≥ 4/5 of the ring is over water; **every hash points away from the land**; both hashes and dots appear |
| reproducibility | the same seed builds the same sea, a different seed a different one, and each style its own |
| mode, phase 3 | the plan's pass order is coast-then-sea; rings 0 + lakes 0 queues no sea; lakes are drawn with no rings at all; the sea style changes the picture; an unknown style falls back; every style draws something; the canvas gains the sea after the coast and keeps the coast |
| the panel stays honest | every control's `help` names its phase and the twelve… fifteen controls whose help says "Active now" are compared both ways against the mode's `LIVE_PARAMS` |
| this repo's validators | `validate_registry` and `validate_profile`: no errors, no warnings; the parameter audit is clean |

## The phase gate (`designs/inkmap_proto/PHASE3_CHECK.py` — 15 checks, 0 failed)

At 1080 × 1920, seed 4242, everything off-screen:

| Measured | Value |
| --- | --- |
| `enter()` (paper + pour + trace + coast + sea) | 696–713 ms, of which the sea is ~260 ms |
| the plan | 898 coast + 932 sea/lake = **1 830 strokes** |
| ring vertices | 6 993, of which **89 (1.3 %)** are over land — the corners an offset cuts across in a bay |
| hashes | 1 696, **all of them ending at sea** |
| marks | 1 696 lines and 1 011 dots |
| the four styles | 4 distinct pictures; sampled ink 7 446 / 7 748 / 6 913 / 8 033 |
| the dials | rings 0 + lakes 0 → **0** sea strokes; rings 0 + lakes 3 → **12**; rings 6 → **2 067** |
| lakes | 3 asked, 3 drawn, 3 centred on land |
| a frame | **median 1.37 ms, worst 2.18 ms** over 6 001 simulated frames |
| the pen | ink on the sheet rises monotonically as the plan is drawn |

## Design §7 Phase 3 checks (the doc's own acceptance list) — all PASS

| The doc asks | Measured |
| --- | --- |
| all four patterns appear | 1 696 hashes and 1 011 dots across one sea, so both mark kinds occur in bulk; the four units are the video's own and rotate along every ring |
| the four patterns are distinguishable | the four sea styles draw four DIFFERENT pictures (byte-compared), each with its own ink count |
| changing `water_style` changes the drawn sea | **PASS, end to end through the panel.** Ran the real app off-display on a throwaway profile bound to loopback, started with `water_style: hash`, edited the profile to `stipple`, POSTed the panel's own `/api/apply` (200, queued), and read the app's log for the re-entered mode: `['hash', 'stipple']` — the second line is the new style actually built. The same mechanism ran on the wall in phase 2 (an apply at 18:35:19 re-poured the sheet), so the "no restart" half is the app's own verified behaviour |
| the water hatching appears after the border | the plan's pass order is asserted (`['coast', 'sea']`) and the in-progress render shows the coast complete with one coast hatched and the others still bare |
| plus: lakes are the same pass on the inside | three lakes, each a closed outline with three inward rings and dots, all centred on land |
| plus: `water_rings` layers | 1 ring < 3 rings < 6 rings, monotone in queued strokes |

## Known deviations, and why

1. **The ring offsets are WIDER than the doc's numbers.** The doc carried 13/21/29 ink px. Rendered,
   that band is 6.5–14.5 screen px on a continent 500 px across — narrower than three line widths, so
   the sea read as a fringe trimming the coast rather than water the land sits in. Now 2.0 mm out and
   1.6 mm per ring. Recorded at the constant with the reason, and in the design doc's phase-3 record.
2. **The doc never said how to make a parallel line, and the obvious way does not work here.** A
   vertex-normal offset folds wherever the coast is concave by more than the offset, and this coast's
   scallops are the same order of size as the offsets — so at the design's own distances the sea is a
   ruffle and at a readable width it is a braid of doubled lines with dark knots at the folds
   (rendered and looked at, three times). Two mechanisms fix it: averaging the ring's SOURCE over
   ~10 mm before offsetting (what a hand traces), and cutting the curve where its direction reverses
   against the coast's (what a pen lift is). Both are tested directly.
3. **The rejected alternative is recorded rather than built:** dilating the mask and tracing each
   level is exact and cannot fold, and it reuses phase 2's tracer — but it costs 540 ms against 10 ms
   for every mass, because each ring needs a full marching-squares pass over 400 × 711 cells.
4. **Hashes are clipped to the water.** 162 of 1 696 overshot onto the continent before that, because
   across a narrow inlet the outward normal points at the far shore. Now zero.
5. **`FRINGE`/`RING`/`HASH`/`UNIT_PITCH`/`ARC` are module constants, not panel controls.** The
   approved schema has `water_style`, `water_rings` and `lake_count` and no key for the band's
   geometry or the mark rhythm, so they stay implementation constants with their measured reasons
   attached, exactly as phase 2's `ISLAND_MIN_CELLS` does.
6. **"Ring by ring" is implemented mass-by-mass.** The plan draws every ring of the largest mass, then
   the next mass — the order the artist works in, finishing the water around one coast before moving
   on. The doc's phrase describes the layering, which is preserved within each mass.
7. **The sea adds its own hand.** Phase 2's test asserted the whole plan shares one `Hand`; the sea is
   its own pass with its own hand seeded off the sheet's seed, so the wander within a pass is
   continuous but the sea's does not depend on how many strokes the coast needed. The test now asserts
   one hand PER PASS (two in total), which is the honest contract.
8. **A phase-2 measurement error was found and corrected.** The phase-2 gate flushed the dirty rect
   before timing `render()`, so its 1.47 ms was the blit alone. Re-measured as the app runs, phase 2
   is **2.07 ms worst / 1.33 ms median**, and both gates and both acceptance records now say so. Left
   unfixed it would have hidden a real cost: a single flush after 900 items composites nearly the whole
   sheet and costs 61.76 ms, which is the phase-1 full-canvas downscale (46–58 ms) seen from the other
   side.

## Not verified at all

- **Nothing has run on the wall.** Every number here is off-screen with the dummy driver. The kiosk on
  :8090 — started at 18:30:10 with `--play 56`, still serving — was left alone throughout and is
  running the code as it stood at 18:30, which does not include any of this phase.
- **So the wall needs a restart to show the sea**, and until it gets one it is running phase 2's code
  in memory (parchment + coastline). Same lesson as last time: the app picks up a new mode TYPE live,
  but never reloads a module it has already imported.
- **The panel form has not been opened in a browser** this phase; what is verified is the data behind
  it (the three controls' live `help` text, the two-way agreement with `LIVE_PARAMS`) and the apply
  route driven over HTTP.
- **The `enter()` cost has not been timed inside the running app** — 696–713 ms in isolation, against
  440 ms in phase 2, so the stall when the mode comes up is now noticeably longer.
