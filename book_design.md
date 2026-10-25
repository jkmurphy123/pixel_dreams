# Book Reference Kiosk — Design

## Purpose

Create an HTML display that presents a book cover, title, source, publication history, synopsis, and detailed reference material. The display runs unattended, with no clicking or scrolling, and adapts to portrait and landscape screens. Portrait is the primary orientation.

## Core Concept

Use a persistent book display alongside automatically rotating information cards. Present the complete description over time instead of placing all the text on screen simultaneously.

The visual character should resemble an atmospheric museum exhibit or an arcane library catalogue: prominent artwork, elegant typography, restrained decoration, and comfortably readable text.

A full-screen cover can provide an introductory scene. During the reading sequence, use a separate, mostly opaque text panel to ensure the artwork never interferes with readability.

## Portrait Layout

Stack the following regions vertically. These proportions are starting points and should be adjusted on the actual monitor.

| Region | Content | Approximate height |
| --- | --- | ---: |
| Header | Collection label, book title, author | 15% |
| Book display | Centered cover with subtle shadow | 35% |
| Information panel | One text card at a time | 43% |
| Footer | Section label, card count, progress indicator | 7% |

Preserve the cover's original aspect ratio and show the complete image. Fill surrounding space with a subdued texture or a blurred, darkened copy of the cover. Keep background effects static while viewers read.

## Landscape Layout

Use two columns:

- Left: book cover, occupying approximately 35–40% of the available width.
- Right: title, author, current information card, and footer, occupying the remaining width.

Retain the same content sequence in both orientations. Use CSS Grid or Flexbox and an aspect-ratio media query to switch layouts. Recalculate pagination when the viewport changes.

## Automatic Presentation Sequence

| Card | Content | Initial timing |
| --- | --- | --- |
| Introduction | Cover, title, author, source, and one intriguing sentence | 10–15 seconds |
| Synopsis | Concise overview of the book | 20–30 seconds |
| Publication history | Dates, editions, translations, surviving copies | 20–30 seconds |
| Provenance / source | Origin of this copy and how it was acquired | 20–30 seconds |
| Historical reference | Detailed history, divided across as many cards as needed | 25–40 seconds per card |
| Contents | Notable chapters, illustrations, annotations, or discoveries | 25–40 seconds per card |

Treat these times as starting values. Long cards need longer durations. After the final card, restart the book or advance to the next book when a collection is configured.

Skip sections with no content rather than showing empty cards. If “source” refers to a citation or catalogue record rather than ownership history, label it accordingly and retain that distinction in the data.

## Pagination and Reading Time

- Keep text stationary during each card's display period.
- Split long sections into discrete cards; do not automatically scroll.
- Aim initially for about 70–110 words per card, subject to actual available space and type size.
- Prefer paragraph boundaries when splitting text. Split unusually long paragraphs at sentence boundaries.
- Repeat the section heading on continuation cards and show a page indicator.
- Never truncate reference material to make it fit.
- If a card overflows, create another card instead of shrinking the text below the chosen readable size.

A configurable initial duration formula is:

`display_seconds = max(15, 5 + word_count / 180 * 60)`

This assumes 180 words per minute plus five seconds to notice the card and orient to it. It is a design starting point, not a fixed requirement. Apply a separate 10–15 second duration to the short introduction and tune reading speed on the physical kiosk.

## Visual Treatment

- Keep the title and cover visible throughout the reading sequence.
- Use a mostly opaque dark or parchment-colored text panel with strong text contrast.
- Reserve decorative serif typography for the title and headings; use a highly readable body face.
- Use generous margins, comfortable line spacing, and left-aligned body text.
- In landscape, constrain line length rather than stretching paragraphs across the entire panel.
- Keep ornamentation outside the reading area.
- Use a short, gentle crossfade between cards, approximately 0.5–1 second.
- Show a footer such as “Publication History · 2 of 6” and a subtle progress line. Make clear whether the count refers to the overall sequence or pages within a section.

Avoid placing long descriptions directly over detailed cover artwork. The optional introduction may use full-screen artwork with a dark gradient behind a short title treatment.

## HTML Implementation Guidance

Use a viewport-sized application shell with distinct header, cover, information, and footer elements. The document itself should not scroll.

Store book content separately from presentation, for example in JSON with fields for title, author, cover image, source, synopsis, publication history, provenance, historical reference, and contents. Preserve paragraph boundaries in long sections.

Build the card sequence after fonts and images have loaded. Measure text against the actual panel dimensions to confirm that each card fits; word counts alone cannot guarantee fit. Repaginate after orientation or size changes and preserve the current section where practical.

A JavaScript timer controls card advancement. Start each reading interval after its transition finishes. Preload the next book cover when cycling through a collection. Keep content and assets local if offline operation is required.

Use a neutral placeholder if a cover cannot load. Missing optional fields should not interrupt the presentation.

## Acceptance Checklist

- Both portrait and landscape layouts fit within the viewport without scrolling.
- The complete cover remains visible without distortion.
- Every supplied section appears during the automatic cycle.
- Long text is paginated without clipping or omission.
- Body text is readable at the intended viewing distance.
- Reading time scales with the amount of text.
- Transitions leave text still during reading.
- A viewer arriving mid-cycle can identify the book and current section.
- Missing images or optional sections do not stop playback.
- Orientation changes rebuild cards without producing overflow.

## Recommended First Version

Implement the persistent cover and paginated information panel first. Validate it with one book containing unusually long text and a long title in both orientations. Add the full-screen introductory scene after the reading layout works reliably.
