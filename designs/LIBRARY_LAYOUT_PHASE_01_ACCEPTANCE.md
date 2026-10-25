# Acceptance report — Imaginary Library layout redesign, Phase 1

Scope: `designs/LIBRARY_LAYOUT_DESIGN.md` §11 **P1** — layout regions, the card model with measured
pagination, header/footer/progress, the backdrop, and the placeholder-cover fix. Timing semantics
(computed per-card reading time) and the registry `params` block are **P2, not in this phase**.

Files:
- `modes/imaginary_library_mode.py` — rewritten rendering half (layout, pagination, header, cards,
  footer, backdrop, generated cover). Data loading, image matching and font utilities kept.
- `modes_registry.json` — `imaginarylibrary.optional` now declares the keys the mode reads
  (`layout`, `header_frac`, `footer_frac`, `max_line_chars`, `panel_opacity`, `collection_label`,
  `title_font_name`, `body_font_name`). `tests/test_schema_scaffold.py::test_real_project_analysis_is_sane`
  asserts zero drift between code-read keys and the registry, so this was required, not optional.
- `tests/test_imaginary_library.py` — 24 tests, new.
- `designs/LIBRARY_LAYOUT_DESIGN.md` — design, decisions, and one corrected measurement table.

## Automated

```
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/test_imaginary_library.py  ->  24 passed
python validate_configs.py --all                                                              ->  0 errors, 1 pre-existing warning (mode 1 Windows path)
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m pytest tests/                           ->  811 collected, all green
```

Suite-level honesty: three full runs were made. Two of them reported a failure in a *process-spawning
timing* test (`test_phase4_panel::test_a_switch_survives_a_restart` once — a 60 s timeout;
`test_panel_wiring` + `test_transport::test_a_manual_step_restarts_the_auto_timer` once — the latter
waits 12–14 s on a real 6 s auto-cycle). Every one of those passes in isolation on the same tree, and
none of them touches a mode; they are load flakes on this busy Jetson, not this change. The clean run
is the third.

The 24 tests cover: fit (arithmetic + pixel containment), lossless pagination, section presence/
absence, widow-free tails, region geometry (inside the screen, pairwise non-overlapping), orientation
selection
(automatic, explicit override, legacy flag, unknown value), render in both orientations, the card clock
and the book hand-off, resize rebuild with reader position preserved, generated-cover text containment,
`exit()` releasing everything, and the missing-catalogue error screen.

## Measured (this host, off-display, real assets)

Layout at the wall's resolution, 1080×1920 portrait:

```
header_band (0,0,1080,288)     cover (329,307,422,634)      panel (39,960,1002,826)
footer_band (0,1786,1080,134)  panel_inner (68,989,944,768) inner_w 944  avail_h 712
```

(old layout on the same wall: cover 324×486 at (54,717), text column 648px, body 36px, bottom half of
the screen empty)

Cards per book: **3 … 18, mean 5.7** (was: 1 card, or 6 identical-metadata cards).
Fullest card: **11 lines / 383 chars / 54 words** at 48px body.
Zero cards whose measured height exceeds the panel; zero cards with lost text; zero widow cards (tail
cards ≥ 25% of their section's fullest card).

Frame cost, measured with the display driver at the wall's size (software surfaces, same harness for
both revisions):

| | previous implementation | this one |
|---|---:|---:|
| `render()` steady state, 1080×1920 | 8.16 ms | **2.02 ms** |
| `render()`, 1920×1080 | 9.82 ms | **2.09 ms** |
| advance to the next book (build) | 90.0 ms | **30.2 ms** |
| card cross-fade | n/a (card swap was instant) | 6.0 ms/frame |
| book cross-fade | n/a | 12.4 ms/frame |

How: every book-level layer (backdrop, panel plate, glow, cover, header) is composited once into one
**opaque** full-screen surface per book, and each card is rendered into one opaque surface that starts
as a copy of that book's content region. An alpha blit costs ~7× an opaque one on this host
(9.48 ms vs 1.25 ms full-screen), so the frame loop is now 1 opaque blit + 1 opaque card blit.

Two of those numbers are **budget-tight rather than comfortable**: the 12.4 ms book cross-fade eats 74%
of a 16.7 ms frame for 0.8 s, and the 30 ms build lands inside one frame when a book hands over. Both
are transient and were not visible in the stills, but they are the first thing P2 should pre-empt (build
the next book during the last card's dwell).

## Visual check (off-display stills, inspected)

`/home/ubuntu/.hermes/cache/scratch/library_shots/` — portrait intro, portrait continuation card,
portrait full history card, portrait last card, portrait generated cover, landscape intro, landscape
history card. Checked by eye: title/author persist in the header, the cover is a plate not a postage
stamp, text sits inside the panel with a real margin, the footer reads
`Historical Reference · I · page 2 of 3   |   card 5 of 18`, and the generated cover's title, author and
year/genre now wrap inside it instead of running off the edge.

## Live verification — NOT DONE, and it cannot be done without a restart

The wall (pid 1897240, `configs/modes_config_vert.json`, mode 48) **imported the old module at
startup**: `sys.modules` never reloads it, so what is on the wall right now is the previous revision
regardless of what is on disk. Restarting the kiosk is the owner's decision, not mine — I did not take
the screen.

After a restart, mode 48 in the vert profile should show the portrait stack and **not** need any config
edit: `layout` defaults to `auto`, and 1080×1920 portrait resolves to the stack even though the profile
never set `portrait_layout`.

## Known deviations and deliberate choices in P1

1. **Words per card (54–60) is below the brief's 70–110.** See `LIBRARY_LAYOUT_DESIGN.md` §5: the
   original table was measured with pygame's default font and was wrong; with DejaVu Sans at 48px, 11
   lines is what the 43% panel holds. Kept 48px for legibility at distance. `body_font_size: 40` would
   give ~65 words/card if you prefer denser cards.
2. **Card pacing is still the old even split** (`dwell_seconds / cards`). With 18 cards that is ~10 s
   per card, which is *too fast* — this is the one thing P1 knowingly leaves broken; P2 makes each card
   `max(15, 5 + words/180*60)` and scales the whole pass to `dwell_seconds` when it is > 0.
3. **Page balancing is heuristic**: greedy fill, then move trailing lines forward until each tail card
   is ≥45% of the panel. It removes widow cards; it does not aim for equal thirds.
4. **`max_line_chars` does not bind at 48px** on this font: the landscape column is 1133px and 62
   characters of DejaVu Sans 48px is ~1364px, so the measure is naturally under the cap. The key stays
   for smaller body sizes and narrower panels.
5. **The mode-number stamp** the controller draws bottom-left (18px, 8px margin) sits inside the footer
   band, so the footer's progress bar now stops 30% of the band above the screen bottom to clear it.

## Amendment — centred text (2026-10-24, same session)

Requested change: header block and main text centre-justified instead of left.

Implemented as one key, `text_align` (default `"center"`, `"left"` reverts), covering the collection
label, title, author, card heading, every body line, and each tag row. The footer stays anchored
(section/page left, card count right) — it is position labelling, not prose. In landscape the text
column is centred inside the panel first, then each run inside the column, so the capped measure stays
centred rather than hugging one edge. Pagination is untouched: only the x of each glyph run moves, so
the earlier fit/lossless measurements still hold.

Evidence:
- 2 tests added (26 total in the module): one pins the `_line_x` contract for `center`, `left` and an
  unknown value, and one is a pixel-level check that the body band's left and right ink margins are
  equal within 8 px and the header's are too — the failure it catches is "the key was read but nothing
  moved". Both pass.
- `validate_configs.py --all`: 0 errors. `tests/test_schema_scaffold.py` (the registry-vs-code drift
  gate) passes: `text_align` is declared in `imaginarylibrary.optional`.
- Stills re-rendered and inspected in both orientations: `/home/ubuntu/.hermes/cache/scratch/library_shots/`
  (`p1_intro` header + intro card, `p3_card4` full body card, `l2_card2` landscape).

Deviation noted honestly: centred paragraphs are ragged on both sides, which is harder to track than
the brief's left-aligned text for long paragraphs; it is the owner's aesthetic call and one key reverts
it. Still unverified on the wall — the restart note above stands.

## Not verified at all

- Anything on the real display (needs the restart above).
- Portrait/landscape switching on a live rotation event (tested only by resizing off-display).
- Long-run memory behaviour of the card-surface window (`CARD_SURFACE_WINDOW = 3`, ~4.1 MB per surface
  at the wall's size) across many books.
