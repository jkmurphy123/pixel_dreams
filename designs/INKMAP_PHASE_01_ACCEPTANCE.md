# Acceptance report — ink-map Phase 1 (the sheet: the parchment)

Date: 2026-10-16 17:55 EDT. pygame 2.6.1 / SDL 2.28.4, Python 3.10.12, no numpy and no PIL.
`/mnt/ssd/projects/pixel_dreams`, host `jetsons` (192.168.40.216). Panel facts the checks depend
on: `xrandr` reports `DP-1 connected primary 1080x1920+0+0 left` — the app's surface is
**1080 × 1920 portrait**, and every size below is at that, not at the panel's physical 1920 × 1080.

Scope of the phase: the sheet only. Aged parchment fills the panel; the ink layer, the reveal hand
and the panel parameters are all in place, but the stroke plan is empty because the coastline
arrives in phase 2. **Nothing is drawn on the paper yet, deliberately.**

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

Artifacts: `designs/inkmap_phase01_sheet.png` (the full 1080 × 1920 render),
`designs/inkmap_phase01_sheet_zoom.png` (a 2× crop of the texture),
`designs/inkmap_proto/PHASE1_CHECK.py` + `ADD_TO_PROFILE.py` (re-runnable).
Code: `core/inksheet.py`, `modes/ink_map_mode.py`, `tests/test_inkmap.py`, and the `inkmap` type
in `modes_registry.json`.

## Automated (`SDL_VIDEODRIVER=dummy .venv/bin/python -m pytest tests/` — 641 passed, exit 0)

No network, no paid calls, nothing mutated outside a tmp path. 33 of the 641 are this phase's.

| Area | Coverage |
| --- | --- |
| paper geometry | the sheet is built at the screen size; `paper_age=0` still yields a usable canvas |
| ageing strength | **low-frequency** contrast via 8×8 block averages, sampled clear of the vignette: an aged sheet must beat a plain one by ≥ 8 levels. This is the assertion that catches "the code paints texture and the viewer sees none" — it failed at 7.0 before the value-noise rewrite and passes at 9.1 after |
| tone derivation | every texture colour must move with `paper_tone` (darkening the tone darkens blotch, fibre and vignette) — otherwise the panel's control would change the fill and leave the texture in the old colour |
| vignette shape | the brightness distribution along a radius must be a **continuum**: ≥ 10 distinct steps with no gap ≥ 20 between them, edge ≥ 15 darker than the middle. Hard bands (drawn with `pygame.draw`'s replace semantics) fail this on both counts |
| seed reproducibility | the same seed reproduces the sheet byte for byte; a different seed does not |
| ink layer | the layer is `width × supersample`; `ink_rect` maps screen→ink space |
| dirty-rect compositing | **containment**: after one small flush, ink is inside that rect and a sampled region outside it is byte-identical to the untouched paper and to the pre-flush bytes |
| the idle guard | a sheet with nothing dirty composites 0 times over 5 frames |
| supersample = 1 | composites correctly (the no-scaling path) |
| empty dirty rect | ignored rather than compositing a zero-area rect |
| wipe | `clear_ink()` leaves the canvas byte-identical to the paper |
| release | `exit()`/`release()` drop all three surfaces, and `render()` after exit does not raise |
| reveal pacing | 100 items over 10 s advance ~10 per 1 s step; a sub-item frame **carries** instead of dropping its share; `seconds_total = 0` draws everything at once; it never runs past the end; `set_plan` resets the cursor |
| mode lifecycle | constructs from the registry's merged config; `enter()` builds the sheet and leaves the plan empty; `render()` puts the configured parchment family on screen (not black); the redraw key re-pours (new seed when unpinned, identical sheet when pinned); `status()` is JSON-safe |
| registry entry | `optional` and `params` are the same 54 keys; every widget and group is one the panel knows; every field carries a recorded default; **and every field's `help` names its phase**, so no control is silently inert |
| this repo's validators | `validate_registry(check_imports=False)`, `validate_profile` on an instance: no errors **and no warnings** |
| the parameter audit | `audit_source` over `modes/ink_map_mode.py` and `core/inksheet.py`: no operative `colour`, `alpha` or `font_size` candidate, and nothing of those kinds in the review list either |

## Live verification

"Live" here means: a real process, the module's real path, the real display size — **off-display**,
because the wall belongs to the user and was never touched (see "Not verified at all").

| Check | Status | Evidence |
| --- | --- | --- |
| the mode renders at the panel's real size | PASS | `PHASE1_CHECK.py`: `VERDICT: PASS`, all six assertions met |
| the parchment's build cost | PASS | `enter()` at 1080 × 1920: **141 ms** this run (128–154 ms across five runs) — a one-off, once per sheet |
| the ink layer's size | PASS | **2160 × 3840 = 33.2 MB**, i.e. exactly 2× in each axis |
| per-frame cost | PASS (off-screen) | `update()` + `render()` = **2.75 ms/frame** against a plain Surface — see the caveat in "Not verified at all" |
| the drawn output is parchment, not a fill | PASS | 275 distinct colours; centre `(226, 211, 179)` against corner `(207, 194, 164)`; visual check of both PNGs |
| reproducibility | PASS | the same pinned seed reproduces the paper **byte for byte** (`True`) |
| nothing is drawn in phase 1 | PASS | `status()` = `{'planned': 0, 'drawn': 0, 'composites': 0}` |
| landing in the profile | PASS | `ProfileEditor` wrote `configs/modes_config_vert.json` **slot 56, `enabled: false`**; backup `configs/.backups/modes_config_vert.json.20261016T214650_104138Z.bak`; read back from disk `{"type": "inkmap", "name": "Ink Map", "enabled": false, "seed": 0}` |
| the write changed nothing else | PASS | structural diff against the pre-write copy: modes 56 → 57, added slots `['56']`, removed `[]`, **no other slot changed**, top-level keys unchanged |
| config validation | PASS | `validate_configs.py --all` → **0 errors**, 1 warning (pre-existing: a Windows path in `modes_config_windows.json`) |
| the mode appears to the controller | PASS | `--show_modes --config configs/modes_config_vert.json` → `[Modes] Found 57 configured mode(s)`, `56: inkmap - Ink Map` |
| the panel's parameter form for the new type | PASS | sandbox `--panel-only` on a free port: `GET /mode/56?profile=configs/modes_config_vert.json` → **HTTP 200, 109,588 bytes**, containing the mode name, `paper_tone`/Paper tone, Supersample, the phase-1 notice, and **47** "becomes live in phase N" notices — exactly the 47 fields that are not live yet |
| the registry entry against the app's own validators | PASS | `REGISTRY_CHECK.py`: `validate_registry` 0 errors/0 warnings; `resolve_params` 54 fields/0 warnings; `validate_profile` clean; with `check_imports=True` the only error is the not-yet-written class (this run predates the class) |
| the live kiosk is undisturbed | PASS | pid 1138807 still up since 15:01:52 holding `0.0.0.0:8090`; the sandbox bound a different port and left **no listener** behind (`ss -ltnp`) |

**Zero live/paid calls this phase** — nothing here costs money or touches a third party, and no unit
test makes one either.

## Design §7 Phase 1 checks (the doc's own acceptance list)

| # | Check | Status |
| --- | --- | --- |
| 1 | mode skeleton | PASS — `modes/ink_map_mode.py`; constructs from the merged config, `exit()` drops every surface |
| 2 | registry entry | PASS — `inkmap` in `modes_registry.json`, 54 fields, accepted by `validate_registry` / `resolve_params` / `validate_profile` with no errors or warnings |
| 3 | `core/inksheet.py` paper pass | PASS — 353 lines; parchment, tone derivation, fibre, vignette |
| 4 | the reveal plumbing (idle) | PASS for the machinery: `Reveal` paces, carries, clamps and resets, covered by 6 tests. Idle **by design**: the plan is empty until phase 2 |
| 5 | "landed **disabled** in the profiles" | **FAILED as written, corrected here** — the slot landed in the **active** profile only (the other nine were deliberately not touched, deviation 2), but it landed **ENABLED**, not disabled. `enabled` is the profile schema's *default*: `core/config.py` disables a mode only when the key is explicitly `False`, and the editor writes the key only to disable. The slot was written without the key, so it has been in the rotation since it was added. Verified against the running app's own status, not by reading the file: `disabled_modes = [0, 5, 40, 46, 47, 54]` (56 absent) and `applied_rotation` contains 56. This is also how the mode reached the wall at 17:58:49 without anyone asking it to |
| 6 | **Visible:** aged parchment filling the portrait panel — warm tone, uneven blotches, paper fibre, a vignette at the edges | PASS — 1080 × 1920 render inspected; mean tone warm cream, low-frequency unevenness, fibre specks, smooth edge shading |
| 7 | nothing drawn on it | PASS — `planned: 0`, `composites: 0`, and the render is bare paper |
| 8 | the mode survives `--show_modes` | PASS — listed at slot 56 |
| 9 | panel param form | PASS — the page renders over HTTP with all 54 fields (Not verified: an actual browser) |
| 10 | the smoke tests and `validate_configs.py` | PASS — full suite 641 passed; `validate_configs.py --all` 0 errors |
| 11 | the param audit must be clean for the new type | PASS — pinned by a test: no operative colour/alpha/font_size candidate in either new module |
| 12 | **Not in this phase:** any land, any strokes | PASS — no coastline, no plan, no ink on the paper |

## Known deviations

1. **The full 54-param schema is declared now, not grown per phase.** The design (§6) was approved
   with the whole entry, so the schema is settled and the panel form is complete from the start. The
   cost is 47 controls that do nothing yet. They are not silent: each field's `help` names the phase
   that draws with it, and the panel page shows 47 such notices (verified above). *Rejected:* growing
   the registry one phase at a time — fewer dead controls, but it contradicts the approved entry and
   churns the file six more times.
2. **Landed in the active profile only, and enabled.** The design says "the profiles" (plural); the
   slot went into the active portrait profile alone. It also landed ENABLED rather than disabled: see
   check 5 — the schema treats an absent `enabled` key as enabled, so "add a slot" and "add a
   disabled slot" are different operations and only the first one happened. Adding a disabled
   slot to all ten — including `modes_config_windows.json` — is noise the user did not ask for, and
   nine of them are for orientations this panel does not use. The mode is available to any profile
   through the panel's **New config**, which already includes every type the registry knows.
3. **The parchment's ageing is a value-noise field, not blotches.** Two earlier implementations were
   shipped, rendered and rejected on looking at them: stamped discs at alpha 3–9/255 measured **7.0**
   levels of low-frequency contrast (flat paper with speckles), and raising the alpha made each disc
   readable as a disc — soft-edged, then a field of bubbles as the count grew. A stamped mark is
   visible whatever its alpha *because it has a centre*. Value noise measures **9.1** against 0.0 for
   a plain sheet and has no shape to see. This is a departure from the design's wording ("uneven
   blotches") in mechanism only, not in intent.
4. **The mode allocates the 33.2 MB ink layer while drawing nothing on it.** The reveal plumbing is
   part of phase 1 by design, and the layer is what phase 2 draws onto; allocating it now means phase
   2 has nothing to add to the lifecycle. The cost is 33 MB resident per sheet.
5. **`map_title`, not `title`.** `title` is one of the app's `COMMON_INSTANCE_KEYS` and reads as an
   on-screen label; this is the name written *on the sheet*. Two different things.
6. **Two repo tests pinned the registry's type count and were updated**:
   `test_new_config.py::test_the_real_registry_yields_a_valid_profile_with_the_leftovers_named`
   (49 → 50 includeable, 53 → 54 types) and
   `test_schema_scaffold.py::test_real_project_analysis_is_sane` (53 → 54). A new type legitimately
   moves a number that pins the registry; what those tests actually guard is that no type vanishes
   quietly, and that every type has a module and a schema — both still asserted.
7. **A self-inflicted test bug, found by the suite and fixed.** This phase's test module initialised
   pygame in a *module*-scoped fixture and called `pygame.quit()` on teardown, which tore down the
   font module for every later module in the same session —
   `tests/test_layout_align.py::test_the_marker_is_drawn_on_the_wall_for_the_selected_control` then
   failed with `pygame.error: font not initialized`. It passed 4/4 in isolation and failed 3/3 when
   run after this file, which is how it was diagnosed. The fixture now leaves the teardown to
   `test_smoke`'s session fixture and only sets a video mode if none exists.

## Not verified at all

- **Anything on the real display.** The kiosk process is the user's: it was started by hand at
  15:01:52 with `--config configs/modes_config_vert.json --start 55`, and this phase never started,
  stopped, nudged or restarted it. Prerequisite: the user restarts it (or applies from the panel) so
  the new registry type and slot 56 are read, then enables slot 56.
- **Whether the RUNNING process picks up a NEW TYPE without a restart.** The design flagged this as
  ASSUMED (§8). It cannot be settled without disturbing the wall, and a fresh process is not
  evidence about a running one. Prerequisite: either the user presses Refresh/apply on the panel, or
  a sandbox instance with a display is started on a free port and probed the same way.
- **The on-wall frame cost.** 2.75 ms/frame is measured against a plain Surface while the display
  mode is 64 × 64; the one direct measurement of a *display-surface* blit at 1080 × 1920 was
  **9.50 ms/frame** (≈ 105 fps), so the on-wall figure is expected to land near that, not near 2.75.
  Prerequisite: a run on the panel.
- **The parameter form in an actual browser.** Verified over HTTP (status, size, content), not
  visually. Prerequisite: open the page.
- **The paper's appearance on the panel's own colour and gamma.** Judged from the saved PNG.
- **The other nine profiles.** Untouched, so nothing there is verified.
