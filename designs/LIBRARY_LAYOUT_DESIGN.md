# Imaginary Library — reference-catalogue layout (redesign)

Status: **DRAFT FOR REVIEW**
Supersedes: §8 ("Display layout") of `designs/LIBRARY_DESIGN.md`. Everything else in that document
(data schema, catalogue, LLM prompt, image matching) stays.
Advice source: `book_design.md` (the Book Reference Kiosk brief).
Scope: `modes/imaginary_library_mode.py` (visual layout + card model + timing), the
`imaginarylibrary` registry entry, and one new test module. No data-file changes.

---

## 0. The complaint, measured

The wall is a 1080×1920 portrait panel (DP-1, xrandr `left`). The running instance
(`/api/status`, pid 1897240, profile `configs/modes_config_vert.json`, mode_index 48) is showing this
mode right now. Screenshot of the wall, plus a headless probe at the same size
(`SDL_VIDEODRIVER=dummy`, real assets, real `books.json`):

```
cover rect  (54, 717, 324, 486)     <- 324x486 image floating mid-screen
panel rect  (405, 27, 648, 1866)    <- 648px-wide text column on a 1080px wall
body font   36px -> 32 chars/line
```

What that looks like: a postage-stamp cover halfway down a black screen, a narrow text column to its
right, and the bottom half of the wall empty. The mode is running its **landscape** branch on a
**portrait** panel, because `portrait_layout` defaults to `False` (line 57) and the `vert` profile
does not set it. The `portrait` profile sets it, so the two profiles disagree about the same display.

Five distinct failures, each one a rule `book_design.md` states outright:

| # | Today | The brief says |
|---|-------|----------------|
| 1 | Orientation comes from a config flag, so the wrong branch can run on a portrait wall (§0 above) | Layout is chosen by aspect ratio (`aspect-ratio` media query) |
| 2 | One surface per book holds **everything**: title, author/year/publisher, meta line, review quote, publication history, synopsis, one history segment, tags (lines 489–611) | Header keeps title + author; the panel shows **one card at a time** |
| 3 | The ~570-character metadata block is re-rendered identically on all six history cards | "Present the complete description over time instead of placing all the text on screen simultaneously" |
| 4 | Overflow is silently clipped — `break` at lines 567, 573, 582, 604 | "**Never truncate** reference material to make it fit… create another card instead" |
| 5 | No header, no footer, no section label, no progress. Card time = `dwell_seconds / n_fields` (line 204), identical for a 451-char segment and a 1089-char one | "Footer such as 'Publication History · 2 of 6' and a subtle progress line"; "Reading time scales with the amount of text" |

Measured content that makes #4 and #5 bite:

```
25 books.  5 of them carry detailed_history_1..6 (lib_001..005), the other 20 have none.
history segment lengths: min 420, max 1089 chars.   publication_history: 159..266.   synopsis: 108..153.
longest single card today: 1089 + 266 + 143 chars of text + 6 headings in a 648x1866 panel.
```

And a separate, simpler bug visible in the same screenshot: the generated placeholder cover
(`_build_placeholder_cover`, lines 433–485) centres the **author** line and the **year/genre** footer
without wrapping either, so on a 324px-wide cover the author (`"Unknown; first words are the middle of
a sentence"`) and footer (`"1337 • Acephalous Grimoire"`) are drawn past the surface edge and clipped.
Three books are affected on the wall right now — `lib_023`, `lib_024`, `lib_025` have no
`assets/imaginary_library/0NN.png`. (Not a layout bug, but it is the first thing you see in that
corner, and it is in scope for "the visual layout doesn't work".)

---

## 1. What maps, and what does not

`book_design.md` is an HTML/kiosk brief for a different app. It is advice, not a spec to port
literally:

| Brief | Here |
|-------|------|
| CSS Grid / Flexbox, `aspect-ratio` media query | `_layout()` returns named `pygame.Rect`s once per resolution; orientation from `w > h` |
| "Measure text against the actual panel dimensions… word counts alone cannot guarantee fit" | real `font.size()` line-fill against the panel rect; pagination happens once per book, never per frame |
| JS timer per card, started after the transition | `dt` accumulator; the card clock starts when the crossfade finishes |
| "Fill surrounding space with a blurred, darkened copy of the cover" | a downscale-then-upscale copy (cheap pseudo-blur), built once per book, cached, static while reading |
| "Keep the complete cover visible, preserve aspect" | already true (`_fit_cover`) — keep it |
| JSON content separate from presentation | already true (`books.json`) — keep it |

---

## 2. The new layout

One function computes the geometry from `(w, h)` and the frac keys. Proportions are the brief's
starting values, exposed as two config keys (§6) so they can be tuned on the real monitor.

**Portrait (h > w)** — vertical stack. At 1080×1920 with the defaults:

```
+--------------------------------------------------+  0
| THE IMAGINARY LIBRARY            No. 23 of 25    |  header 288px (15%)
| Das Buch ohne Anfang                             |    small-caps label, serif title,
| Unknown; first words are the middle of a sentence|    italic author, hairline rule
+--------------------------------------------------+  288
|      ......................................      |
|      .                                    .      |  cover 672px (35%)
|      .        [ cover 448x672 ]           .      |    centred, aspect preserved,
|      .      blurred dark copy behind      .      |    shadow + 1px frame
|      ......................................      |
+--------------------------------------------------+  960
|  PUBLICATION HISTORY                 2 of 3      |  panel 825px (43%)
|                                                  |    mostly opaque, one card,
|  Bound in wood from a gallows. Scholars have     |    heading + body, left aligned
|  identified the same anonymous hand in…          |
+--------------------------------------------------+  1785
| Publication History        •        3 of 11      |  footer 135px (7%)
| ██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  |    section label, card n of N,
+--------------------------------------------------+  1920   progress line
```

**Landscape (w > h)** — two columns, same content order: left column 38% of width holds the cover
vertically centred in the full height; right column stacks header / card / footer. Body measure is
capped at `max_line_chars` (62) instead of stretching to the column width, per the brief's landscape
rule. At 1920×1080: cover 666×999 at x≈32, text column 1100px wide but the paragraph block capped at
~62 characters.

Rules for the layout function:

- Regions are computed once per resolution change and cached; no Rect arithmetic in `render()`.
- The mode number overlay the manager draws bottom-left (`core/manager.py:197`, 18px, 8px margin) sits
  inside the footer band, so the footer's left text starts at `margin + 44px`.
- Every region is clipped to its own rect when its content is drawn; nothing may spill into a
  neighbour (this is what makes the "keeps its regions" test in §10 meaningful).

**Backdrop.** `screen.fill(self._bg)` stays as the base, then: a vertical gradient wash (baked once
per resolution into one surface, not per frame), then — behind the cover box only — a darkened,
downscaled copy of the current cover (1/8 scale, scaled back up, `set_alpha`ed to ~55, multiplied by
a flat dark fill). Both are built in `_prepare_book`, so the background is **static while a card is
being read**, as the brief requires.

---

## 3. The card model

Replace "one surface per history field, everything on it" with:

```
SECTION -> [CARD, CARD, ...]        built once per book, at the current resolution
CARD   = heading, blocks[], page_index, page_count, duration_s
BLOCK  = kind (label | para | quote | meta | rule), text, font, colour, gap
```

Sections for this data, in order, each **skipped entirely when empty** (the brief's rule):

| Section | Source fields | Cards |
|---------|---------------|-------|
| `Introduction` | `review_excerpt` (as the intriguing sentence), `publisher` + `year` as source line, `genre`/`language`/`pages` meta line, `tags` | 1 (short: `intro_seconds`) |
| `Synopsis` | `synopsis` | 1 (paginate if long) |
| `Publication History` | `publication_history` | 1–2 |
| `Historical Reference` | `detailed_history_1..6`, in order, one sub-section per segment labelled `I`–`VI` | 1–2 per segment |

The title/author/publisher no longer appear in a card — they live in the header, drawn once. That is
the brief's "keep the title and cover visible throughout" and it is what removes the repeated
~570-character block from every history card.

**Pagination algorithm** (measured, not counted):

1. Flatten the section's text into paragraph blocks, keeping paragraph boundaries; split any single
   paragraph that cannot fit a whole card at **sentence** boundaries (`[.!?]` followed by space, with
   a guard against "St." / initials — fall back to word split only if a "sentence" is longer than a
   card).
2. Greedy line-fill each block with `font.size()` against `panel.width - 2*margin`.
3. Walk the lines accumulating height; when the next line would pass `panel.bottom - margin`, start a
   new card. Back up to the last paragraph boundary if there is one on the card (the brief prefers
   paragraph breaks).
4. Continuation cards repeat the heading and carry `page_index + 1 / page_count`.
5. Assert (dev-time, and in a test) that joining a section's card blocks reproduces the source text
   word-for-word. **Lossless is a property, not a hope** — it is the whole point of #4 in §0.

The reading-order invariant: `sum(len(section.cards) for section) == total_cards`, and the footer's
progress line is `card_ordinal / total_cards`.

---

## 4. Timing

Per card, straight from the brief:

```
duration = max(min_card_seconds, 5 + words / reading_wpm * 60)      # defaults: 15, 180
intro card: intro_seconds (12)                                       # short by design
```

The card clock starts when the crossfade finishes (`CARD_FADE_SECONDS = 0.7`, inside the brief's
0.5–1s). `dwell_seconds` changes meaning:

- `dwell_seconds: 0` (new default) → cards run on their computed times; the book advances after the
  last card. Enriched books (lib_001..005) come to ~9–11 cards ≈ 4.4–5.5 minutes; the 20 books with
  no history run ~3 cards ≈ 50 seconds.
- `dwell_seconds: N > 0` → the computed durations are **scaled** so one full pass of the book equals
  N seconds (`scale = N / sum(computed)`), with `min_card_seconds` still floored. Existing profiles
  set 180, so their behaviour stays "three minutes per book", now spread in proportion to how much
  text each card actually carries instead of an even split.

Measured card counts for the enriched books, from the probe (48px body, 1080×1920):
`lib_001 11 cards / 5.0 min`, `lib_002 9 / 4.8`, `lib_003 9 / 4.6`, `lib_004 9 / 4.4`, `lib_005 10 / 5.5`.

---

## 5. Typography and colour

Measured at the design panel with the fonts actually used (DejaVu Serif/DejaVu Sans, inner width
944px, 712px of text height):

| body px | chars/line | lines/card | words/card |
|--------:|-----------:|-----------:|-----------:|
| 48 (default) | 35 | 11 | 54 |
| 40 | ~42 | 13 | ~65 |

**Correction to the first draft of this section**: the numbers originally tabled here (34 chars/line,
20 lines, 123 words at 48px) were measured with pygame's *default* font, which is markedly narrower and
shorter than DejaVu Sans. With the real font the brief's 70–110 words per card is *not* reached at 48px
— a full card holds ~54–60 words, and the line height (56px + 4px leading) not the width is what limits
it. That is a deliberate deviation: at the wall's viewing distance a 48px body is the right size, the
brief calls its word count "a starting point, subject to actual available space and type size", and P2
gives each card its own reading time so a short card is shown for less long rather than the type being
shrunk to fill a quota. Dropping to 40px would buy ~65 words/card at the cost of legibility across a
room — the trade is yours to make after seeing it on the wall.

### Alignment (owner decision, 2026-10-24)

The brief says "left-aligned body text". **The wall owner asked for centred text**, so the default is
`text_align: "center"`: the collection label, title and author in the header, the card heading, every
body line, and each row of tag pills are centred on the text column (and in landscape the column itself
is centred inside the panel, then the lines inside the column). The footer stays anchored — section and
page on the left, card count on the right — because those are position labels, not prose.

`text_align: "left"` restores the brief's alignment in one word; nothing else changes, pagination and
line counts are unaffected because only the x of each glyph run moves. Any other value falls back to
`center` with a one-line log.

Measured consequence to be aware of: centred paragraphs have a ragged edge on **both** sides, so the
eye has no fixed left margin to return to — fine for a plate read at a glance, harder for a long
paragraph than the brief's left alignment would be. Looking at it on the wall is the test.

Fonts: there is no `assets/fonts/` in the repo, but `pygame.font.match_font` resolves on this host —
`dejavuserif → DejaVuSerif.ttf`, `liberationserif → LiberationSerif-Regular.ttf`, `dejavusans →
DejaVuSans.ttf` (checked). Resolution order, resolved once in `__init__`:

1. `title_font_name` / `body_font_name` config path (`.ttf`/`.otf`) or system family name;
2. `font_name` (existing key) as the shared fallback;
3. DejaVu Serif for title/headings, DejaVu Sans for body;
4. `pygame.font.Font(None, size)` and a one-line log.

Restrained decoration, per the brief: a small-caps collection label, one hairline rule under the
header, one hairline under the footer text, the progress line. The bright gold 3px box around the
cover is dropped in favour of a soft shadow plus a 1px dark frame, so the cover reads as a museum
plate rather than a UI element.

---

## 6. Config and registry changes

| Key | Default | Notes |
|-----|---------|-------|
| `layout` | `"auto"` | `choice`: `auto` / `portrait` / `landscape`. Replaces the flag-based branch; same convention as the `dungeon` mode's `layout` key |
| `portrait_layout` | — | still read, but **deprecated**: only consulted when `layout` is `"auto"`; `validate_configs` warns; keeps both existing profiles working unchanged |
| `portrait_cover_height_frac` | 0.35 | re-scoped: now the *cover band* height in the portrait grid (was the cover height inside a 0.34 band, i.e. it produced 398×598; the new band gives 448×672). Renamed in the doc, same key name so no profile edits are needed |
| `header_frac` | 0.15 | new — header band (portrait) / header block (landscape) |
| `footer_frac` | 0.07 | new |
| `reading_wpm` | 180 | new |
| `min_card_seconds` | 15 | new |
| `intro_seconds` | 12 | new |
| `card_fade_seconds` | 0.7 | new; replaces the hard-coded `FIELD_FADE_SECONDS` |
| `max_line_chars` | 62 | new — landscape measure cap |
| `panel_opacity` | 0.92 | new — the card panel's darkness over the backdrop |
| `text_align` | `"center"` | new — `center` / `left` for the header block, card heading, body lines and tag rows (§5) |
| `body_font_size` | 48 | unchanged value, now used as the paragraph size |
| `title_font_name`, `body_font_name` | `null` | new |
| `dwell_seconds` | 180 → **0** | semantics change (§4). Registry `type_config` drops the 180; the two profiles that set 180 keep working (scaled mode) |
| `crossfade_seconds` | 0.8 | new key mirroring `CROSSFADE_SECONDS`, so book-to-book timing is tunable too |

Registry work: add every new key to `optional` (the validator catches typos against that list), keep
`required: ["image_folder"]`, and add `params` entries with `group` (`layout` / `appearance` /
`behaviour`) and `help` text for anything whose behaviour is not obvious (`dwell_seconds`' new
scaling meaning especially — a control whose meaning changed and does not say so reads as a bug).

---

## 7. The placeholder cover bug

`_build_placeholder_cover` draws the author line and the year/genre footer centred with no wrap. Fix,
in the same pass as the layout work:

- title, author and footer all wrapped with `_wrap_lines` against `w - 2*margin`;
- the footer additionally shrunk step-wise from `small_font_size` until it fits on one line, and
  dropped entirely if it still will not fit at 60% of that size (a cover never draws text it cannot
  fit);
- a test over all 25 books asserting every drawn glyph is inside the surface.

Separately noted, not in scope: three books have no cover art (`023`, `024`, `025`). The mode handles
that gracefully; if you want real covers there it is a data/asset job.

---

## 8. Module structure

The class keeps its public contract (`__init__/enter/exit/handle_event/update/render`). Internals:

```
_load_books, _scan_image_folder, _resolve_*        unchanged
_layout()                    -> dict of named Rects (header, cover, panel, footer, backdrop)
_build_cards(book)           -> list[Card]         (pagination, §3)
_build_card_surface(card)    -> Surface            (one per card, per resolution)
_prepare_book(i)             -> cover, backdrop, cards, card surfaces
_warm_next()                 -> build book i+1 during the LAST card's dwell (no load inside a fade)
render()                     -> backdrop, cover, header strip, current card, footer  (+ crossfades)
```

Per-frame cost after this: 3–5 blits and one progress-line `draw.line`, which is *less* than today
(one 648×1866 alpha blit per card). No `Font.render()` in the frame loop; no blur; no disk I/O.

`exit()` drops: covers, backdrop, card surfaces, cards, fonts, manager — as today, extended to the new
caches.

---

## 9. Tests (`tests/test_imaginary_library.py`)

1. **No overflow**: for every book, every card, at 1080×1920 and 1920×1080, the card surface's ink
   bounding box fits inside the panel rect (containment, not exact offset).
2. **Lossless pagination**: per book and per section, the concatenated card text equals the source
   text (whitespace-normalised). This is the test that would have caught §0#4.
3. **Sections**: a section with content yields ≥1 card; an empty one yields none; `lib_006`
   (no history) yields exactly Introduction + Synopsis + Publication History.
4. **Timing**: `duration == max(min_card_seconds, 5 + words/180*60)`; `dwell_seconds > 0` scales the
   pass to exactly that total, floored per card.
5. **Regions**: header/cover/panel/footer are inside the screen, pairwise non-overlapping, and sum to
   the screen height (portrait) / width (landscape); cover aspect is 3:4 within 1px.
6. **Orientation**: `layout: "auto"` picks portrait at 1080×1920 and landscape at 1920×1080;
   `layout: "portrait"` wins on a landscape screen (explicit override).
7. **Placeholder**: for all 25 books incl. the three missing covers, no glyph is drawn outside the
   cover surface.
8. **Rebuild on resize**: change the screen size mid-run → cards rebuilt, still no overflow, current
   section preserved.
9. **exit()** releases surfaces and fonts (no references retained).
10. The existing `tests/test_smoke.py` still constructs the mode; `validate_configs.py --all` clean.

---

## 10. Verification plan

1. Off-display: render every book's every card at both orientations; assemble a contact sheet of
   stills and measure each card. Numbers in the report, not adjectives.
2. Look at the stills myself (portrait intro, a continuation card, the landscape branch, a
   placeholder cover) before touching the wall.
3. The wall: the running process imported the old module, so **a restart is required** — mode code
   edits are never live (the registry is; the module is not). I will hand the restart to you rather
   than taking the screen: `systemctl --user restart pixel_dreams` (or your usual route), then I
   screenshot and check that mode 48 in `configs/modes_config_vert.json` now shows the portrait
   stack.
4. Panel: the new keys must render as real controls — fetch the mode's params page from a sandbox
   instance on a free port and confirm every new key appears with its group and default.
5. `python validate_configs.py --all`, `SDL_VIDEODRIVER=dummy pytest tests/ -q`, `git status` clean of
   strays, no leftover listener.

---

## 11. Phases

- **P1 — layout + cards** (the substance): `_layout()`, the card model with measured pagination,
  header/footer/progress, backdrop, the placeholder-cover fix, tests 1–3, 5–9, contact sheet.
- **P2 — timing + config surface**: computed durations, `dwell_seconds` scaling, the new registry
  keys with `params`/`help`, tests 4 and 10, panel params page check.
- **P3 — polish, after you have seen it on the wall**: typography/colour tuning from the real panel,
  landscape tuning, and whatever the first look changes (it always changes something).

---

## 12. Decisions (answered 2026-10-24)

1. **`dwell_seconds`** — `0` = computed per card; `> 0` scales the whole pass to that total. (Chosen.)
2. **History split** — one card group per `detailed_history_N`, labelled `Historical Reference · I … VI`,
   paginated within a segment when long. (Chosen.)
3. **Orientation** — auto from aspect ratio, `layout` as explicit override, `portrait_layout` kept as a
   deprecated fallback. The `vert` profile changes appearance with no config edit. (Chosen.)
4. **Phasing** — P1 (layout + cards + placeholder fix) lands first for review on the wall; P2 (timing +
   registry keys + panel controls) after. While P1 is on the wall, card pacing stays the *old* even
   split across the new card list, so pacing is the one thing P1 deliberately does not fix.

Now closed. Implementing in that order.

