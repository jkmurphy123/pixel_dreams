# Acceptance report — Phase 2 (parameter schema + the generated read-only form)

Date: 2026-10-15. Jetson/Tegra aarch64, Python 3.10.12 (venv), pygame 2.6.1, NiceGUI 3.18.0,
pytest 9.1.1, pytest-asyncio 1.4.0.
Project: `/mnt/ssd/projects/pixel_dreams`, commits `236ea29`, `9a1271b`.
Display facts the checks depend on: **no display and no browser were used**; page assertions run
through NiceGUI's in-process user simulation, and the process-level checks use the SDL dummy driver.

Legend: **PASS** verified here · **PARTIAL** partly verified · **PENDING** not yet verified.

## Automated (`SDL_VIDEODRIVER=dummy python -m pytest tests/` — 336 passed)

| Area | Coverage |
| --- | --- |
| Value-shape inference | All 11 shapes present in the shipped profiles map to the intended widget (bool → switch, int/float → number, str → text, `[r,g,b]` → colour, 2-number list → range, `list[str]` → string list, list-of-lists → palette, list-of-dicts/dict → raw JSON). |
| Name inference for unset keys | Whole-token matching, with regressions pinned for the three bugs the first draft shipped: `show_*` was matching the colour rule, bare `folder` missed the path rule, `font_name` was typed as a number. |
| Schema overlay | Widget/label/group/bounds/step/choices/suggestions/default/derived/secret are applied; a malformed entry is reported and ignored; choices define the widget; suggestions never close a field; secrets are masked at the model layer. |
| Crash-safe writes | Backup holds the previous content; two saves in the same second produce two backups; prune keeps the newest N; file mode preserved; a failed `os.replace` leaves the original byte-identical with no temp file; a hash mismatch raises. |
| Code mining | Coercions, defaults, structural-key exclusion, declared `VALID_*` sets vs bare comparisons, and only genuinely derived assignments (`self.font_size = max(14, int(self.w * 0.04))`) flagged. |
| Registry merge | Additive, idempotent, never overwrites a hand-edited entry (bounds and labels survive), drift keys appended once, result is valid JSON. |
| The generated form | Every shape asserted through the real page builder with the expected widget kind; every field read-only; the secret value absent from the entire element tree; declared-but-unset params offered with their code default; local overrides badged; an undeclared config key warned about on the page; the list links into the form; unknown and non-numeric mode numbers reported without crashing. |
| Completeness sweep | **8 profiles, 167 modes, 2508 fields, 0 missing** — every key a config sets and every key the registry declares resolves to a widget the UI knows. Programmatic, not sampled. |
| Unchanged behaviour | The 141 inherited pixel_drift tests still pass; process-level panel tests still show the ping round-trip (panel → render loop → status). |

No network and no paid calls. The one test that binds `0.0.0.0` uses a sandbox secrets file and
loopback-only assertions.

## Live verification

| Check | Status | Evidence |
| --- | --- | --- |
| Drift fix — no mode hides a knob from the registry | PASS | measured drift across all 53 types is now **0** (was 23 keys over 6 types: blinkenlights, headlinesnews, penrosetiling, quotegenerator, slideshow, statusticker) |
| Schema applied to the versioned registry without loss | PASS | 53 types; entrypoints, `required`, `type_config` and `settings` identical to HEAD; `optional` arrays preserved with additions appended; second run merged 0 keys and produced the same sha256 (`b10b01bc3ddf`) |
| Configs still valid after the registry change | PASS | `validate_configs.py --all` → 0 errors, 1 warning (pre-existing: a Windows path in an inherited profile) |
| Existing process behaviour intact | PASS | Sandbox run: panel serves the live loop, `/api/ping` → `pong_count` 1, `/api/status` 200; panel-off run still reports `nicegui_imported=False` |
| Rendered form against the REAL profiles | PASS | All 167 mode pages of all 8 shipped profiles render through the real page builders (test), and the same 167 pages were swept over HTTP against a real LAN-bound process: **0 non-200**, with every one of the 1522 configured fields' labels present in the served page. This sweep is how the 500 below was found. |
| Visual sanity of the real forms | PENDING | Your check, per the design's own acceptance item ("you eyeball slideshow, status ticker, control panel and say the widgets are sane"). Nothing here has been looked at in a browser. |

## Design §10 Phase 2 checks

| # | Check (the doc's words) | Status |
| --- | --- | --- |
| 1 | `params` schema support in the registry (inference fallback) | PASS — 580 entries across 52 of 53 types; inference still renders a type with no schema |
| 2 | The scaffold script and its generated draft for 53 types | PASS — 53 analysed, 0 unreadable modules; draft is additive and idempotent; one type has no tunable keys, so 52 have entries |
| 3 | The drift keys added to `optional` | PASS — 23 keys; measured drift 0 |
| 4 | `/mode/<n>` rendering every param with a plausible widget (no writes) | PASS — 2508 fields, 0 missing; each shape's widget kind asserted; the page writes nothing |
| 5 | You eyeball the widgets on real modes | PENDING — needs your browser |

## Found during live verification (fixed in this phase)

**A 500 on real mode pages — `HTTP 500: ValueError: invalid literal for int() with base 10:
'cover'`** on `/mode/2` and `/mode/7`. The chain: `scale_mode` is absent from that profile, so the
widget came from the key's NAME (the tokens include "scale", which is in the numeric vocabulary);
the schema's default `"cover"` was then handed to `ui.number()`, which `int()`s its value.

Fixed at three layers so no single mistake can repeat it:
1. `core/params.py`: an unset key's widget now comes from the schema's recorded **default**, which
   is real evidence about the type, rather than from the key's name, which is a guess.
2. `core/schema_scaffold.py`: the evidence rule is restated by strength — a code coercion beats a
   name guess, and `text` only loses to `path`/`color`, where the name *refines* a string instead
   of contradicting it.
3. `panel/app.py`: a number field can no longer take a page down; a non-numeric value renders as
   an explicit note naming the key.

Two tests now cover the class of bug the fixture could not see (it exercised every value shape but
none of the real registry's schema oddities): every mode page of every real profile is rendered in
the suite, and the live HTTP sweep is part of the record above.

## Known deviations

1. `core/store.py` shipped in Phase 2 rather than Phase 3 (the schema tool rewrites a versioned
   file; the atomic-write contract belongs with the first writer).
2. `choices` vs `suggestions` split added: a declared set is a dropdown, bare comparisons are
   suggestions. Without this the draft emitted a one-option dropdown for `weather_units`.
3. Secret values are masked in the model, not just hidden in the UI.
4. The schema records only what inference cannot know (`--all-keys` opts into the explicit form).
5. `--check` now means "every type has at least one schema entry" (schema health), not "every type
   must have one".
6. `default` in the schema is the mode code's fallback, not your tuned value; the form prefers the
   profile's value.
7. Two model bugs the tests caught and fixed: a schema `choices` list did not define the widget
   (so `scale_mode` would have ignored its options), and there was no renderer branch for the plain
   text widget (so `folder` rendered as a raw-JSON box).

## Not verified at all

- **The form in a real browser.** The pages render and serve correctly (machine-checked), but
  nobody has LOOKED at them: the visual layout of the field grid, the swatches and the group cards
  is unverified, and only a browser can show it. Prerequisite: open the URLs below.
- **Editing anything.** Phase 2 is read-only by design: no Save, no enable/disable, no Refresh, no
  profile switching. The write path (`core/store.py`) is built and tested but not yet wired to a UI.
- **Whether the auto-generated schema is *right* in judgement terms.** The 81 widget corrections,
  17 derived flags and 12 suggestion sets are inferred from code patterns; they need your eye,
  and the `params` block is yours to edit (a re-run never overwrites it).
- **The real tuning loop** (change a value → refresh → look at the wall), which is Phase 3.
- **The parameter exposure audit** (Phase 5): the 17 derived keys are *labelled* but their
  hardcoded internals are still not tunable.
