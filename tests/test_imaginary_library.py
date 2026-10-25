# tests/test_imaginary_library.py
#
# The redesigned Imaginary Library mode: card pagination that never truncates,
# a layout that keeps its regions, orientation selection, and the generated
# placeholder cover that must not draw outside itself.
#
# Design: designs/LIBRARY_LAYOUT_DESIGN.md (advice source: book_design.md).
# All headless - no display required.

import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from core.cache import ResourceCache  # noqa: E402
from modes.imaginary_library_mode import ImaginaryLibraryMode  # noqa: E402

PORTRAIT = (1080, 1920)
LANDSCAPE = (1920, 1080)

BASE_CONFIG = {
    "image_folder": "assets/imaginary_library",
    "books_file": "data/imaginary_library/books.json",
    "dwell_seconds": 180,
}


@pytest.fixture(scope="module", autouse=True)
def pygame_init():
    pygame.init()
    pygame.font.init()
    yield
    pygame.quit()


class FakeManager:
    """The slice of ModeManager this mode is allowed to touch."""

    def __init__(self, screen):
        self.screen = screen
        self.cache = ResourceCache()
        self.width, self.height = screen.get_size()


def make(size=PORTRAIT, **overrides):
    config = dict(BASE_CONFIG)
    config.update(overrides)
    screen = pygame.display.set_mode(size)
    mode = ImaginaryLibraryMode(config)
    mode.enter(FakeManager(screen))
    return mode, screen


def card_text(card):
    """All text a card shows, in reading order."""
    out = []
    for line in card.lines:
        if line["kind"] == "tags":
            out.extend(label for row in line["rows"] for label, _ in row)
        else:
            out.append(line["text"])
    return " ".join(out)


def normalise(text):
    return " ".join(str(text).split())


def all_cards(mode, books=None):
    books = range(len(mode.books)) if books is None else books
    for index in books:
        state = mode._prepare_book(index)
        for card in state.cards:
            yield state, card


# ---------------------------------------------------------------- pagination

@pytest.mark.parametrize("size,kwargs", [
    (PORTRAIT, {}),
    (LANDSCAPE, {}),
    (PORTRAIT, {"layout": "portrait"}),
])
def test_every_card_fits_the_panel_arithmetically(size, kwargs):
    """Measured, not counted: the page height the pager used must fit the panel.

    This is the invariant that failed in the old implementation, which just
    stopped drawing at the bottom edge.
    """
    mode, _ = make(size, **kwargs)
    panel_inner = mode._layout["panel_inner"]
    footer_inner = mode._layout["footer_inner"]
    failures = []
    for state, card in all_cards(mode):
        height = mode._page_height(card.lines)
        if height > mode._avail_h:
            failures.append((mode.books[state.index]["id"], card.heading,
                             card.page_index, height, mode._avail_h))
        if mode._heading_font.size(card.heading)[0] > panel_inner.width:
            failures.append((mode.books[state.index]["id"], card.heading, "HEADING WIDE"))
        for line in card.lines:
            if line["kind"] != "text":
                continue
            if line["font"].size(line["text"])[0] > mode._inner_w:
                failures.append((mode.books[state.index]["id"], line["text"][:30], "LINE WIDE"))
    # the footer's own label must fit its band
    assert footer_inner.width > 0 and footer_inner.height > 0
    mode.exit()
    assert not failures, f"cards do not fit: {failures[:5]}"


def test_rendered_ink_stays_inside_the_panel_and_footer():
    """Pixel proof: nothing is drawn outside the panel band or the footer band."""
    mode, _ = make()
    content = mode._layout["content"]
    panel_inner = mode._layout["panel_inner"]
    footer_inner = mode._layout["footer_inner"]
    row_bytes = content.width * 3

    def local(rect):
        return pygame.Rect(rect.x - content.x, rect.y - content.y, rect.width, rect.height)

    allowed_rows = set()
    for rect in (local(panel_inner), local(footer_inner)):
        allowed_rows.update(range(rect.top, rect.bottom))

    problems = []
    for book_index in (0, 5, 22):        # rich history, bare, generated cover
        state = mode._prepare_book(book_index)
        for card in state.cards:
            surface = mode._card_surface(state, card)
            before = pygame.image.tostring(state.base.subsurface(content).copy(), "RGB")
            after = pygame.image.tostring(surface, "RGB")
            for y in range(content.height):
                start = y * row_bytes
                if before[start:start + row_bytes] == after[start:start + row_bytes]:
                    continue
                if y not in allowed_rows:
                    problems.append(("ROW", mode.books[state.index]["id"],
                                     card.heading, card.page_index, y))
                    break
            # sideways bleed at the band edges is caught by sampling the two
            # columns just outside each band on every differing row
            for rect in (local(panel_inner), local(footer_inner)):
                for x in (rect.left - 2, rect.right + 1):
                    if not 0 <= x < content.width:
                        continue
                    for y in range(rect.top, rect.bottom, 7):
                        i = y * row_bytes + x * 3
                        if before[i:i + 3] != after[i:i + 3]:
                            problems.append(("COL", mode.books[state.index]["id"],
                                             card.heading, card.page_index, x, y))
                            break
    mode.exit()
    assert not problems, f"ink outside the panel/footer bands: {problems[:5]}"


@pytest.mark.parametrize("size,kwargs", [
    (PORTRAIT, {}),
    (LANDSCAPE, {}),
])
def test_pagination_never_drops_text(size, kwargs):
    """Every character of every section appears on some card of that section."""
    mode, _ = make(size, **kwargs)
    romans = ("I", "II", "III", "IV", "V", "VI")
    failures = []
    for index, book in enumerate(mode.books):
        state = mode._prepare_book(index)
        seen = {}
        for card in state.cards:
            seen.setdefault(card.heading, []).append(card_text(card))
        expected = {}
        review = str(book.get("review_excerpt", "") or "").strip()
        if mode.show_review and review:
            expected["Introduction"] = f"“{review}”"
        for name, key in (("Synopsis", "synopsis"),
                          ("Publication History", "publication_history")):
            text = str(book.get(key, "") or "").strip()
            if text:
                expected[name] = text
        for i in range(1, 7):
            text = str(book.get(f"detailed_history_{i}", "") or "").strip()
            if text:
                expected[f"Historical Reference  ·  {romans[i - 1]}"] = text
        for heading, source in expected.items():
            got = normalise(" ".join(seen.get(heading, [])))
            if normalise(source) not in got:
                failures.append((book["id"], heading))
    mode.exit()
    assert not failures, f"sections lost text: {failures[:5]}"


def test_sections_appear_only_when_they_have_content():
    """A book with no history gets three cards; an enriched book gets six sections."""
    mode, _ = make()
    bare = mode.books[5]          # lib_006: no detailed_history_* fields
    assert not any(str(bare.get(f"detailed_history_{i}", "")).strip() for i in range(1, 7))
    state = mode._prepare_book(5)
    assert [card.label for card in state.cards] == \
        ["Introduction", "Synopsis", "Publication History"]

    enriched = mode._prepare_book(0)   # lib_001: all six segments
    labels = [card.label for card in enriched.cards]
    for roman in ("I", "II", "III", "IV", "V", "VI"):
        assert f"Historical Reference  ·  {roman}" in [c.heading for c in enriched.cards], roman
    assert labels[0] == "Introduction"
    # Order is the brief's: intro, synopsis, publication history, then reference.
    order = [labels.index(name) for name in
             ("Introduction", "Synopsis", "Publication History")]
    assert order == sorted(order)
    assert labels.index("Historical Reference") > order[-1]
    mode.exit()


def test_no_widow_cards():
    """A long section must not leave its last card holding one or two lines."""
    mode, _ = make()
    for index in range(len(mode.books)):
        state = mode._prepare_book(index)
        sections = {}
        for card in state.cards:
            sections.setdefault(card.heading, []).append(len(card.lines))
        for heading, counts in sections.items():
            if len(counts) < 2:
                continue
            assert counts[-1] >= 2, f"{heading} ends on a {counts[-1]}-line card: {counts}"
            assert counts[-1] >= 0.25 * max(counts), f"{heading} widow: {counts}"
    mode.exit()


# ------------------------------------------------------------------- layout

@pytest.mark.parametrize("size", [PORTRAIT, LANDSCAPE])
def test_regions_are_inside_the_screen_and_do_not_overlap(size):
    mode, _ = make(size)
    lay = mode._layout
    screen = pygame.Rect(0, 0, size[0], size[1])
    order = ["header_band", "cover_band", "panel", "footer_band"]
    rects = [lay[key] for key in order]

    for name, rect in zip(order, rects):
        assert screen.contains(rect), f"{name} leaves the screen: {rect}"
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not a.colliderect(b), f"{order[i]} overlaps: {a} {b}"

    assert lay["cover_band"].contains(lay["cover"])
    assert lay["panel"].contains(lay["panel_inner"])
    cover = lay["cover"]
    assert abs(cover.width / cover.height - 800 / 1200) < 0.02, "cover aspect changed"
    mode.exit()


def test_portrait_stack_covers_most_of_the_screen():
    """The old layout left half the wall empty; the stack must not."""
    mode, _ = make(PORTRAIT)
    lay = mode._layout
    used = lay["footer_band"].bottom
    assert used >= mode.h - 1
    assert lay["cover"].height >= int(0.30 * mode.h), "cover is a postage stamp again"
    assert lay["panel_inner"].height >= int(0.35 * mode.h)
    mode.exit()


@pytest.mark.parametrize("size,expected", [
    (PORTRAIT, True),
    (LANDSCAPE, False),
    ((1000, 1000), True),
])
def test_orientation_is_automatic(size, expected):
    mode, _ = make(size)
    assert mode._portrait is expected
    mode.exit()


@pytest.mark.parametrize("size,forced,expected", [
    (LANDSCAPE, "portrait", True),
    (PORTRAIT, "landscape", False),
])
def test_explicit_layout_overrides_the_aspect_ratio(size, forced, expected):
    mode, _ = make(size, layout=forced)
    assert mode._portrait is expected
    mode.exit()


def test_unknown_layout_value_falls_back_to_auto():
    mode, _ = make(PORTRAIT, layout="sideways")
    assert mode.layout_mode == "auto"
    assert mode._portrait is True
    mode.exit()


def test_text_alignment_defaults_to_center_and_can_be_reverted():
    """Center justification is the wall owner's choice; one key reverts it."""
    mode, _ = make()
    assert mode.text_align == "center"

    column_x, column_w = 68, 944
    for glyph_w in (40, 200, 500):
        assert mode._line_x(glyph_w, column_x, column_w) == column_x + (column_w - glyph_w) // 2
    # a run wider than the column is pinned to the column's left edge, never negative
    assert mode._line_x(column_w + 10, column_x, column_w) == column_x
    mode.exit()

    left, _ = make(text_align="left")
    assert left.text_align == "left"
    assert left._line_x(200, column_x, column_w) == column_x
    left.exit()

    bogus, _ = make(text_align="justified")
    assert bogus.text_align == "center"
    bogus.exit()


def test_centered_header_and_body_ink_are_horizontally_balanced():
    """Pixel proof of centring on the introduction card and the header block.

    Measured as the ink band's left/right margins being equal within a few pixels -
    the failure this guards is 'the key was read but nothing moved'. Each row is
    compared against the same row of the surface underneath (the panel sits on a
    vertical gradient, so one background colour for the whole band would find
    phantom ink).
    """
    mode, _ = make()
    content = mode._layout["content"]
    state = mode._cur

    def ink_columns(surface, rect, base=None):
        raw = pygame.image.tostring(surface, "RGB")
        pitch = surface.get_width() * 3
        base_raw = pygame.image.tostring(base, "RGB") if base is not None else None
        left, right = None, None
        for y in range(rect.top, rect.bottom):
            start = y * pitch
            bg = base_raw[start + rect.left * 3:start + rect.left * 3 + 3] \
                if base_raw is not None else b"\x00\x00\x00"
            row = raw[start:start + pitch]
            for x in range(rect.left, rect.right):
                if row[x * 3:x * 3 + 3] != bg:
                    if left is None or x < left:
                        left = x
                    if right is None or x > right:
                        right = x
        return left, right

    pool = state.base.subsurface(content).copy()
    panel_inner = mode._layout["panel_inner"]
    local_panel = pygame.Rect(panel_inner.x - content.x, panel_inner.y - content.y,
                              panel_inner.width, panel_inner.height)
    body = pygame.Rect(local_panel.left, local_panel.top + mode._heading_h,
                       local_panel.width, local_panel.height - mode._heading_h - 2)
    surface = mode._card_surface(state, state.cards[0])
    left, right = ink_columns(surface, body, pool)
    assert left is not None and right is not None, "no ink found in the body band"
    left_margin = left - body.left
    right_margin = body.right - right
    assert abs(left_margin - right_margin) <= 8, \
        f"body text is not centred: {left_margin}px left vs {right_margin}px right"

    header = state.header
    hrect = pygame.Rect(0, 0, header.get_width(), header.get_height())
    hleft, hright = ink_columns(header, hrect)
    assert hleft is not None and hright is not None
    assert abs((hleft - hrect.left) - (hrect.right - hright)) <= 8, \
        f"header text is not centred: {hleft} left vs {hrect.right - hright} right"
    mode.exit()


def test_legacy_portrait_flag_still_works_only_in_auto():
    """Profiles written before the layout key existed keep their appearance."""
    mode, _ = make(LANDSCAPE, portrait_layout=True)
    assert mode._portrait is True
    mode.exit()
    mode, _ = make(PORTRAIT, portrait_layout=False, layout="auto")
    assert mode._portrait is True     # auto wins from the aspect ratio
    mode.exit()


# ---------------------------------------------------------------- rendering

def test_render_draws_both_orientations_without_error():
    for size in (PORTRAIT, LANDSCAPE):
        mode, screen = make(size)
        screen.fill((0, 0, 0))
        mode.render(screen)
        assert screen.get_bounding_rect(min_alpha=1).width > 0
        # the card must change pixels where the panel is
        panel = mode._layout["panel_inner"]
        assert screen.get_at(panel.center)[:3] != (0, 0, 0)
        mode.exit()


def test_card_clock_advances_and_book_advances_after_the_last_card():
    mode, screen = make(PORTRAIT, dwell_seconds=2.0)
    cards = len(mode._cur.cards)
    assert cards >= 3
    step = max(0.01, mode._card_duration / 6.0)
    # The card clock runs the dwell, then a cross-fade promotes the next card.
    for _ in range(200):
        mode.update(step)
        mode.render(screen)
        if mode._card_index == 1:
            break
    assert mode._card_index == 1, "the card clock did not advance"
    # Run out the whole book: every card, then the cross-fade into the next book.
    for _ in range(2000):
        mode.update(step)
        mode.render(screen)
        if mode._book_transition > 0.0:
            break
    assert mode._book_transition > 0.0, "the book never advanced after its last card"
    assert mode._next is not None and mode._next.index == 1
    mode.exit()


def test_resize_rebuilds_cards_and_keeps_the_reader_in_place():
    mode, screen = make(PORTRAIT)
    # step to a history card
    history_index = next(i for i, c in enumerate(mode._cur.cards)
                         if c.label == "Historical Reference")
    mode._card_index = history_index
    heading = mode._cur.cards[history_index].heading

    screen = pygame.display.set_mode(LANDSCAPE)
    mode.manager.screen = screen
    mode.update(0.016)

    assert (mode.w, mode.h) == LANDSCAPE
    assert mode._portrait is False
    assert mode._cur.cards, "cards were not rebuilt"
    assert mode._cur.cards[mode._card_index].heading == heading, \
        "the reader was thrown back to the introduction"
    # and the rebuilt cards still fit
    for card in mode._cur.cards:
        assert mode._page_height(card.lines) <= mode._avail_h
        mode._card_surface(mode._cur, card)     # builds without error
    mode.exit()


def test_placeholder_cover_keeps_its_text_inside():
    """The old generator drew the author and footer past the cover edge."""
    mode, _ = make()
    cover_w, cover_h = mode._layout["cover"].size
    inner = pygame.Rect(0, 0, cover_w, cover_h)
    checked = 0
    for book in mode.books:
        pieces = mode._placeholder_text_pieces(book, cover_w, cover_h)
        assert pieces, f"{book['id']} drew no text at all"
        for glyphs, rect in pieces:
            assert inner.contains(rect), \
                f"{book['id']}: '{glyphs}' at {tuple(rect)} leaves the {cover_w}x{cover_h} cover"
        mode._build_placeholder_cover(book)     # and the whole cover still builds
        checked += 1
    assert checked == len(mode.books)
    mode.exit()


def test_exit_releases_everything():
    mode, _ = make()
    mode.exit()
    assert mode.manager is None
    assert mode.books == []
    assert mode._cur is None and mode._next is None
    assert mode._font_cache == {}
    assert mode._backdrop is None and mode._panel_bg is None


def test_missing_catalogue_renders_a_message_instead_of_raising():
    mode, screen = make(PORTRAIT, books_file="data/imaginary_library/does_not_exist.json")
    assert mode._error_message
    screen.fill((0, 0, 0))
    mode.render(screen)          # must not raise
    assert screen.get_bounding_rect(min_alpha=1).width > 0
    mode.exit()
