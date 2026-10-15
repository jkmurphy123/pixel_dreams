# Phase 5 — parameter exposure audit (for review)

**Nothing has been changed.** This phase produces a candidate list with a recommendation each; the
design says "reviewed before anything changes", and that review is yours. No mode module, no
registry entry and no profile was modified to produce this document.

Re-run it any time, or after a mode changes:

```bash
python3 scripts/audit_params.py                       # summary + the knobs worth reviewing
python3 scripts/audit_params.py --mode blinkenlights  # one mode in detail
python3 scripts/audit_params.py --all --json /tmp/candidates.json
```

`core/param_audit.py` does the analysis (AST, not grep) and `tests/test_param_audit.py` pins its
rules — including the three exclusions that keep the list trustworthy:

- **a literal the mode overwrites itself is not a knob.** `self.margin_x = 20` followed by
  `self.margin_x = int(self.w * 0.06)` is a default; the knob is the ratio. Reporting the 20 would
  send you to change a number with no effect.
- **a value that already comes from config is not a knob.** Exposing `col_pad_scale` again would be
  two controls for one behaviour.
- **a one-off coordinate is not a knob.** `x = w - 20` is layout arithmetic.

## The headline numbers

| | |
| --- | --- |
| mode modules scanned | 53 |
| raw values found | 487 |
| operative (not overwritten, not already a param) | 405 |
| **worth reviewing** (operative, not a one-off coordinate) | **233 values** — 216 of them in the 39 modes a profile uses, which group into **193 distinct knobs** (one row per knob, not per literal) |
| placeholders the mode itself overwrites | 82 |
| indexes/flags/state initialisers skipped (`0/1/2/-1/0.0/1.0`) | 502 |
| coordinate literals (excluded from the review list) | 172 |
| single hardcoded font size at a call site | 7 |

By kind: **56 ratios**, **146 colours**, **20 gaps/paddings**, 3 margin literals, 7 font sizes,
1 alpha.

## Tier 1 — the orientation-sensitive ones (recommended)

This is what you actually asked for: values that decide whether a wall looks right in portrait,
landscape and the narrow variants. Two patterns dominate, and both are the *same idiom repeated
across modes*, which makes them cheap to fix and easy to remember.

### 1a. The padding idiom: `_pad = int(min(w, h) * X)`

**Twenty-nine of the modes you use** compute their outer padding this way, with X between 0.02 and
0.06 — 50 of the 56 ratio knobs are in this family. The heaviest:

| mode | value(s) | X | profiles using it |
| --- | --- | --- | --- |
| retro_crt_hacker_terminal | `_pad` | 0.045 | 8 |
| system_information | `_side_margin` / `_top_pad` / `col_gap` | 0.06 / 0.02 / 0.06 | 8 |
| blinkenlights | `outer_pad` / `_subtitle_font_px` / `_tiny_font_px` | 0.035 / 0.02 / 0.015 | 7 |
| status_ticker | `margin_x` / `margin_y` | 0.06 / 0.06 | 7 |
| galactic_navigation | `_side_margin` / `_top_margin` / `bottom_margin` / `pad` | 0.05 / 0.02 / 0.03 / 0.06 | 6 |
| deep_space_signal_decoder, forgotten_space_station_directory, machine_dreamscape, retro_computer_memory_visualizer | `_pad` / `pad` | 0.04-0.06 | 4 each |
| alien_language_rosetta_console, core_memory_matrix, network_status_wall, mission_control_console, rbmk_reactor_simulation | `_pad` | 0.04-0.05 | 3 each |

**Recommendation:** expose these as a per-mode number called **`pad_scale`** (and
`margin_x_scale` / `margin_y_scale` where the mode distinguishes them), defaulting to the current
constant, in the registry's `params` block. One consistent name across modes means you learn it
once, and `"pad_scale": 0.075` in a portrait profile reads as what it is. The mode change is two
lines each (`config.get("pad_scale", 0.045)`), and the panel picks the field up automatically from
the schema.

### 1b. The font idiom: `_font_size = max(N, int(min(w, h) * X))`

| mode | as written | profiles |
| --- | --- | --- |
| retro_crt_hacker_terminal | `max(16, int(min(self.w, self.h) * 0.03))` | 8 |
| blinkenlights | `_subtitle_font_px = max(11, int(base * 0.02))`, `_tiny_font_px = max(10, int(base * 0.015))` | 7 |
| basic_prompt | `max(_, int(... * 0.03))` | 2 |
| dna_sequence_visualizer | `font_size` ratio 0.015 | 1 |
| fantasy_news | `font1` 0.05, `font2` 0.03, `foot_font` 0.72 | 1 |

**Recommendation:** same treatment — **`font_scale`** (number), with the floor kept as a separate
optional `font_floor` only where the mode has a meaningful minimum (the ticker's `max(14, ...)` is
the one that already has a partial knob; the others do not need one).

### 1c. Seven literal font sizes at the call site

`cache.get_font(None, 14)` in penrose_tiling; `28` in control_panel, quote_slideshow, chat_replay and
dungeon; `18` in puppet_theatre; `12` in global_threat_map (a mode no profile currently uses). These
are not computed at all — the number *is* the size.

**Recommendation:** expose as **`font_size`** (the name the registry already uses elsewhere). These
are the cheapest wins in the whole audit: one line to read the config, one schema entry, and the
panel shows a number box.

## Tier 2 — colours (146 values, the largest group)

Colours are the biggest group and the one where "expose everything" is the wrong answer: a mode's
palette is often its identity, and a hundred colour fields would make the form unusable. The data
suggests three classes:

| class | example | recommendation |
| --- | --- | --- |
| **state accents** — one attribute assigned several different colours per state | retro_crt_hacker_terminal's `_accent` (3 values), basic_prompt (4) | **expose one colour** (`accent`), or an accent plus named variants if the states matter to you |
| **fixed palettes** — many distinct colour attributes in one mode | retro_crt_hacker_terminal (16 colour values), basic_prompt (14), wargames (10), imaginary_library (9), satellite_tracker (9) | **expose foreground + accent + background**; leave the semantic warn/error colours alone |
| **one-offs** — a single colour literal used once | a progress-bar tint, a cursor | **leave it** unless you have ever wanted to change that specific thing |

Those five modes carry the most colour values; I would take them first, and only the three knobs per
mode. Everything else stays as it is.

## Tier 3 — gaps, alpha (21 values)

- **Gaps/paddings as literals** (20): `core_memory_matrix` is the extreme case with `left_pad 56`,
  `top_pad 32`, `right_pad 22`, `bottom_pad 22`, `bar_gap 10`; also `headlines_news` `box_pad 18`,
  `mission_control_console` `cell_gap 8` and `gap 8`, `alien_star_map_cartographer` `pad 10`,
  `chat_replay` `gap_y 10`, `retro_computer_memory_visualizer` `gap 10`. These are a layout's internal
  spacing: worth exposing exactly in the modes you tune by eye, not by default.
- **Alpha** (1): `set_alpha(70)` in retro_crt_hacker_terminal. Expose it with the colour it belongs
  to rather than on its own.
- **Timings: none.** An earlier pass reported four, and every one was a state initialiser
  (`self._fade_t = 0.0`) rather than a knob — which is why the auditor now skips `0.0`/`1.0` as well
  as `0/1/2/-1`. If a mode later needs a pacing knob, it will appear here.

## Not recommended

**172 coordinate literals** (`x = w - 20`, `baseline = 480`, …). They are recorded in the JSON output
for completeness but kept out of the review list: a one-off coordinate is an implementation detail,
and exposing them would add knobs nobody would ever move while burying the ones that matter.

**82 placeholders** — literals the mode immediately overwrites (`self.font_size = 16` in `__init__`,
recomputed in `enter()`). They are not dead code: they are the value a mode has before its first
resize, and they are correct as defaults. Recommendation: **leave them.**

## One decision worth your input

There are two ways to make orientation tuning cheap, and they are not mutually exclusive:

1. **Per-mode params (recommended, uses today's machinery).** `pad_scale` / `font_scale` / colour
   params per mode, edited in the panel, per profile. Nothing new is needed anywhere: the schema
   renders the field, the profile stores the value, the panel saves it. Cost: one entry per mode
   (~20 modes for Tier 1), and a value that must be set per mode per orientation.
2. **A profile-level scale factor (new plumbing).** A `render: {scale: 1.1}` block in a profile that
   every mode multiplies its ratios by — one knob for the whole wall. It is a better *user*
   experience for "make everything 10% bigger on the portrait wall", but it needs new config
   plumbing, a new convention every mode must follow, and the panel gains a profile-level form.
   That is a design change, not an audit outcome, so it belongs in a design review of its own.

My recommendation: do **(1) now** for the Tier-1 ratios and the seven literal font sizes — it is
mechanical, it is verifiable, and it immediately unlocks the tuning you described. Consider (2)
separately, after you have used (1) enough to know whether you are setting the same scale in every
mode (which is the signal that a global factor would be worth its plumbing).

## What happens after you approve

Nothing here is scheduled. If you approve, the work splits cleanly:

- **Step 1** — the Tier-1 ratios and the seven literal font sizes: mode reads `config.get(...)` with
  today's value as the default, plus the registry `params` entry. Test each: the rendered value with
  no config set is unchanged (that is the regression that matters — a tuning knob must not change
  the wall until you move it).
- **Step 2** — Tier-2 colours for the five heaviest modes, limited to foreground / accent /
  background.
- **Step 3** — Tier-3 gaps in the modes you name, timings and the alpha if you want them.

Each step is a small, reviewable diff, and the audit can be re-run to show the list shrinking.

## How this was produced and verified

- The tool is `core/param_audit.py` (AST-based) with 18 tests pinning its rules, including the three
  exclusions above and one check against the real tree that the design's own example (the ticker's
  derived font/margins) is found.
- Every number in this document is generated output: the tables in the tiers were taken from the
  tool, and the appendix below is its report verbatim.
- One false-positive class was FOUND BY CHECKING THE DRAFT against that output: an earlier pass
  reported four "timing" knobs, and every one was a state initialiser rather than a knob
  (`self._fade_t = 0.0`). The auditor now skips `0.0`/`1.0` as well as `0/1/2/-1`, which removed 243
  junk candidates and dropped timings to zero.
- **Nothing was changed to produce this.** No mode, registry entry or profile differs from the
  commit before this document; re-running the audit reproduces it.
- Not verified: whether any of these knobs is one YOU would actually move. That is the review, and it
  is the judgement this document cannot make for you.

---

## Appendix — the machine scan (generated by `scripts/audit_params.py`)

Produced by `python3 scripts/audit_params.py --report ...` on the current tree; the numbers above are this output, and re-running it after any change regenerates both.

### Machine scan

- modules scanned: **53**
- raw candidate values: **487** (405 operative, 82 placeholders the mode itself overwrites, 502 trivial 0/1/2/-1 values skipped)
- **worth reviewing** (operative, not a one-off coordinate): **233**, of which 216 are in modes a profile actually uses
- modes with at least one candidate: 50

| kind | operative values |
| --- | --- |
| geometry | 172 |
| colour | 146 |
| ratio | 56 |
| gap | 20 |
| font_size | 7 |
| margin | 3 |
| alpha | 1 |

### Knobs worth reviewing, by reach and kind (weight = kind x profiles using the mode)

| mode | value | kind | literals | as written | suggested param | profiles |
| --- | --- | --- | --- | --- | --- | --- |
| `modes.penrose_tiling_mode` | `get_font size` | font_size | 14 | `font = self.manager.cache.get_font(None, 14, bold=False)` | get_font size (number; int pixels) | 6 |
| `modes.retro_crt_hacker_terminal_mode` | `_font_size` | ratio | 0.03 | `_font_size = max(16, int(min(self.w, self.h) * 0.03))` | _font_size scale (number; current 0.03) | 8 |
| `modes.retro_crt_hacker_terminal_mode` | `_pad` | ratio | 0.045 | `_pad = int(min(self.w, self.h) * 0.045)` | _pad scale (number; current 0.045) | 8 |
| `modes.system_information_mode` | `_side_margin` | ratio | 0.06 | `_side_margin = int(w * 0.06)` | _side_margin scale (number; current 0.06) | 8 |
| `modes.system_information_mode` | `_top_pad` | ratio | 0.02 | `_top_pad = int(h * 0.02)` | _top_pad scale (number; current 0.02) | 8 |
| `modes.system_information_mode` | `col_gap` | ratio | 0.06 | `col_gap = int(w * 0.06)` | col_gap scale (number; current 0.06) | 8 |
| `modes.blinkenlights_mode` | `_subtitle_font_px` | ratio | 0.02 | `_subtitle_font_px = max(11, int(base * 0.02))` | _subtitle_font_px scale (number; current 0.02) | 7 |
| `modes.blinkenlights_mode` | `_tiny_font_px` | ratio | 0.015 | `_tiny_font_px = max(10, int(base * 0.015))` | _tiny_font_px scale (number; current 0.015) | 7 |
| `modes.blinkenlights_mode` | `outer_pad` | ratio | 0.035 | `outer_pad = int(min(w, h) * 0.035)` | outer_pad scale (number; current 0.035) | 7 |
| `modes.status_ticker_mode` | `margin_x` | ratio | 0.06 | `margin_x = int(self.w * 0.06)` | margin_x scale (number; current 0.06) | 7 |
| `modes.status_ticker_mode` | `margin_y` | ratio | 0.06 | `margin_y = int(self.h * 0.06)` | margin_y scale (number; current 0.06) | 7 |
| `modes.galactic_navigation_mode` | `_side_margin` | ratio | 0.05 | `_side_margin = int(self.w * 0.05)` | _side_margin scale (number; current 0.05) | 6 |
| `modes.galactic_navigation_mode` | `_top_margin` | ratio | 0.02 | `_top_margin = int(self.h * 0.02)` | _top_margin scale (number; current 0.02) | 6 |
| `modes.galactic_navigation_mode` | `bottom_margin` | ratio | 0.03 | `bottom_margin = int(self.h * 0.03)` | bottom_margin scale (number; current 0.03) | 6 |
| `modes.galactic_navigation_mode` | `pad` | ratio | 0.06 | `pad = max(10, int(panel.width * 0.06))` | pad scale (number; current 0.06) | 6 |
| `modes.retro_crt_hacker_terminal_mode` | `_accent` | colour | (140, 255, 170), (255, 200, 90), (120, 240, 255) +more | `self._accent = (140, 255, 170)` | _accent (colour widget) — 4 different values here, so this is a state accent: expose it as a colour, or as an accent + variants | 8 |
| `modes.retro_crt_hacker_terminal_mode` | `_bg` | colour | (0, 0, 0) | `self._bg = (0, 0, 0)` | _bg (colour widget; current (0, 0, 0)) | 8 |
| `modes.retro_crt_hacker_terminal_mode` | `_dim` | colour | (120, 160, 120), (170, 130, 70), (120, 170, 170) +more | `self._dim = (120, 160, 120)` | _dim (colour widget) — 4 different values here, so this is a state accent: expose it as a colour, or as an accent + variants | 8 |
| `modes.retro_crt_hacker_terminal_mode` | `_fg` | colour | (220, 255, 220), (255, 220, 140), (200, 255, 255) +more | `self._fg = (220, 255, 220)` | _fg (colour widget) — 4 different values here, so this is a state accent: expose it as a colour, or as an accent + variants | 8 |
| `modes.system_information_mode` | `_accent` | colour | (80, 200, 255) | `self._accent = (80, 200, 255)` | _accent (colour widget; current (80, 200, 255)) | 8 |
| `modes.system_information_mode` | `_bg` | colour | (0, 0, 0) | `self._bg = (0, 0, 0)` | _bg (colour widget; current (0, 0, 0)) | 8 |
| `modes.system_information_mode` | `_dim` | colour | (160, 160, 160) | `self._dim = (160, 160, 160)` | _dim (colour widget; current (160, 160, 160)) | 8 |
| `modes.system_information_mode` | `_fg` | colour | (235, 235, 235) | `self._fg = (235, 235, 235)` | _fg (colour widget; current (235, 235, 235)) | 8 |
| `modes.blinkenlights_mode` | `_led_off` | colour | (60, 0, 0) | `self._led_off = (60, 0, 0)` | _led_off (colour widget; current (60, 0, 0)) | 7 |
| `modes.blinkenlights_mode` | `_led_on_base` | colour | (255, 40, 40) | `self._led_on_base = (255, 40, 40)` | _led_on_base (colour widget; current (255, 40, 40)) | 7 |
| `modes.status_ticker_mode` | `bg` | colour | (0, 0, 0) | `self.bg = (0, 0, 0)` | bg (colour widget; current (0, 0, 0)) | 7 |
| `modes.status_ticker_mode` | `dim` | colour | (90, 180, 110) | `self.dim = (90, 180, 110)` | dim (colour widget; current (90, 180, 110)) | 7 |
| `modes.status_ticker_mode` | `err_base` | colour | (255, 120, 120) | `self.err_base = (255, 120, 120)` | err_base (colour widget; current (255, 120, 120)) | 7 |
| `modes.status_ticker_mode` | `fg` | colour | (120, 255, 140) | `self.fg = (120, 255, 140)` | fg (colour widget; current (120, 255, 140)) | 7 |
| `modes.status_ticker_mode` | `ok_base` | colour | (80, 220, 140) | `self.ok_base = (80, 220, 140)` | ok_base (colour widget; current (80, 220, 140)) | 7 |
