# modes/imaginary_library_mode.py
#
# Imaginary Library mode for pixel_dreams.
#
# Presents one forbidden medieval manuscript at a time as an atmospheric
# reference-catalogue plate: a persistent cover, a persistent title header, one
# information card at a time, and a footer that says where you are in the
# sequence.  Layout follows designs/LIBRARY_LAYOUT_DESIGN.md (which takes its
# advice from book_design.md); all textual data lives in
# data/imaginary_library/books.json.  No network calls at runtime.
#
# Config keys (see designs/LIBRARY_LAYOUT_DESIGN.md):
#   - image_folder          folder containing 800x1200 cover images
#   - books_file            path to books.json (default: data/imaginary_library/books.json)
#   - dwell_seconds         seconds per book (default 180); spread evenly over the
#                           book's cards until P2 gives each card its own reading time
#   - match_by              "filename" uses cover_image field; "index" uses alpha sort
#   - layout                "auto" (default) / "portrait" / "landscape"
#   - portrait_layout       DEPRECATED - only consulted when layout == "auto"
#   - portrait_cover_height_frac  cover band height fraction in the portrait grid
#                           (default 0.35; the cover itself is fitted inside it)
#   - header_frac           header band height fraction, portrait (default 0.15)
#   - footer_frac           footer band height fraction, portrait (default 0.07)
#   - max_line_chars        landscape line-length cap, in characters (default 62)
#   - panel_opacity         card panel darkness over the backdrop (default 0.92)
#   - text_align            "center" (default) or "left": header block, card
#                           heading, body lines and tag rows
#   - placeholder_color     [r,g,b] base color for generated missing covers
#   - show_tags             render tag pills on the introduction card (default True)
#   - show_review           render review excerpt on the introduction card (default True)
#   - font_name             shared font (system family name or .ttf/.otf path)
#   - title_font_name       font for title/headings (default font_name or dejavuserif)
#   - body_font_name        font for body text (default font_name or dejavusans)
#   - title_font_size       default 48
#   - body_font_size        default 48 (this is the paragraph size)
#   - small_font_size       default 36
#   - tag_font_size         default 32
#
# Book JSON fields:
#   - detailed_history_1 .. detailed_history_6
#     Each non-empty segment becomes its own "Historical Reference" section,
#     labelled I..VI, paginated across as many cards as the text needs.  Blank
#     segments are skipped.  Sections are never truncated: text that does not
#     fit starts another card.

import hashlib
import json
import os

import pygame

# End-of-sentence detection for pagination backups.  A card prefers to break at
# a paragraph, then at a sentence, and only then mid-sentence.
_SENTENCE_ENDS = ".!?…"
_CLOSERS = "”\"')]»"
_ROMAN = ("I", "II", "III", "IV", "V", "VI")


class _Card:
    """One screenful of one section: a heading plus the lines that fit."""

    __slots__ = ("heading", "label", "ordinal", "page_index", "page_count",
                 "lines", "index", "total", "surface")

    def __init__(self, heading, label, ordinal, page_index, page_count, lines):
        self.heading = heading
        self.label = label
        self.ordinal = ordinal
        self.page_index = page_index
        self.page_count = page_count
        self.lines = lines
        self.index = 0     # position in the whole book's sequence
        self.total = 1     # number of cards in the whole book
        self.surface = None

    def drop_surfaces(self):
        self.surface = None


class _BookState:
    """Everything cached for one book: cover, backdrop glow, header, cards."""

    __slots__ = ("index", "cover", "glow", "header", "base", "cards")

    def __init__(self, index):
        self.index = index
        self.cover = None
        self.glow = None
        self.header = None
        self.base = None
        self.cards = []

    def drop(self):
        for card in self.cards:
            card.drop_surfaces()
        self.cards = []
        self.cover = None
        self.glow = None
        self.header = None
        self.base = None


class ImaginaryLibraryMode:
    """Scene-style mode that cycles through imaginary books/manuscripts."""

    # Supported image extensions for index matching.
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

    # Transition between books, in seconds.
    CROSSFADE_SECONDS = 0.8

    # Transition between cards of the same book, in seconds.
    CARD_FADE_SECONDS = 0.7

    # How many cards of a book keep a rendered surface at any one time.
    CARD_SURFACE_WINDOW = 3

    def __init__(self, config: dict):
        # --- behavior ---
        self.dwell_seconds = float(config.get("dwell_seconds", 180.0))
        self.image_folder = str(config.get("image_folder", "assets/books"))
        self.books_file = str(config.get("books_file", "data/imaginary_library/books.json"))
        self.match_by = str(config.get("match_by", "filename")).lower()
        self.collection_label = str(config.get("collection_label", "The Imaginary Library"))
        self.show_tags = bool(config.get("show_tags", True))
        self.show_review = bool(config.get("show_review", True))

        # --- layout ---
        self.layout_mode = str(config.get("layout", "auto")).lower()
        if self.layout_mode not in ("auto", "portrait", "landscape"):
            print(f"[ImaginaryLibrary] Unknown layout '{self.layout_mode}'; using auto")
            self.layout_mode = "auto"
        # Deprecated flag: honored only inside "auto", for profiles written before
        # the layout key existed.
        self.legacy_portrait = bool(config.get("portrait_layout", False))
        self.cover_band_frac = float(config.get("portrait_cover_height_frac", 0.35))
        self.header_frac = float(config.get("header_frac", 0.15))
        self.footer_frac = float(config.get("footer_frac", 0.07))
        self.max_line_chars = int(config.get("max_line_chars", 62))
        self.panel_opacity = float(config.get("panel_opacity", 0.92))
        # "center" justifies the header block and the card text; "left" is the
        # reference-catalogue default and reverts this in one word.
        self.text_align = str(config.get("text_align", "center")).lower()
        if self.text_align not in ("center", "left"):
            print(f"[ImaginaryLibrary] Unknown text_align '{self.text_align}'; using center")
            self.text_align = "center"

        # --- presentation ---
        self.font_name = config.get("font_name", None)
        self.title_family = config.get("title_font_name") or self.font_name or "dejavuserif"
        self.body_family = config.get("body_font_name") or self.font_name or "dejavusans"
        self.title_font_size = int(config.get("title_font_size", 48))
        self.body_font_size = int(config.get("body_font_size", 48))
        self.small_font_size = int(config.get("small_font_size", 36))
        self.tag_font_size = int(config.get("tag_font_size", 32))

        raw_color = config.get("placeholder_color", [40, 35, 55])
        self.placeholder_color = tuple(int(c) for c in raw_color)

        # --- colors (dark parchment / forbidden-library theme) ---
        self._bg = (22, 18, 15)
        self._bg_top = (28, 23, 19)
        self._bg_bottom = (12, 10, 9)
        self._title = (228, 218, 190)
        self._subtitle = (168, 158, 138)
        self._body = (208, 201, 183)
        self._dim = (128, 120, 108)
        self._accent = (180, 145, 80)
        self._rule = (74, 64, 52)
        self._tag_bg = (55, 48, 42)
        self._tag_fg = (186, 179, 166)
        self._shadow = (6, 5, 4)
        self._panel = (26, 22, 18)

        # --- runtime ---
        self.manager = None
        self.w = 0
        self.h = 0
        self._portrait = True
        self._layout = {}
        self._backdrop = None
        self._panel_bg = None
        self._fade_buf = None

        self.books = []
        self._image_files = []
        self._error_message = None

        self._cur = None            # _BookState on screen
        self._next = None           # _BookState fading in
        self.book_index = 0

        self._book_transition = 0.0  # 1.0 -> 0.0 while cross-fading books
        self._card_transition = 0.0  # 1.0 -> 0.0 while cross-fading cards
        self._card_index = 0
        self._pending_card = 0
        self._card_timer = 0.0
        self._card_duration = 1.0

        # Font cache, keyed by (family, size, bold, italic).
        self._font_cache = {}

    # ---------------- lifecycle ----------------

    def enter(self, manager):
        self.manager = manager
        self.w, self.h = manager.screen.get_size()
        self._build_fonts()
        self._rebuild_layout()
        self._load_books()
        self._scan_image_folder()

        self.book_index = 0
        self._book_transition = 0.0
        self._card_transition = 0.0
        self._card_index = 0
        self._card_timer = 0.0
        self._cur = None
        self._next = None

        if self.books:
            self._cur = self._prepare_book(0)
            self._reset_card_clock()
            self._ensure_card_surface(self._cur, 0)

    def exit(self):
        # Release all surfaces and references so GC can reclaim memory.
        if self._cur is not None:
            self._cur.drop()
        if self._next is not None:
            self._next.drop()
        self._cur = None
        self._next = None
        self._backdrop = None
        self._panel_bg = None
        self._fade_buf = None
        self._font_cache.clear()
        self.books = []
        self._image_files = []
        self.manager = None

    def handle_event(self, event):
        # In single-mode test runs the controller passes arrow keys through.
        if event.type == pygame.KEYDOWN:
            if self._book_transition > 0.0 or self._card_transition > 0.0:
                return
            if event.key == pygame.K_RIGHT:
                self._advance_book(+1)
                return
            if event.key == pygame.K_LEFT:
                self._advance_book(-1)
                return

    def update(self, dt: float):
        if self.manager is None:
            return

        # Handle resolution changes (hotplug, rotation, resize in windowed mode).
        w2, h2 = self.manager.screen.get_size()
        if (w2, h2) != (self.w, self.h):
            # Remember where the reader was so the rebuild can stay on the same
            # section (and page) instead of snapping back to the introduction.
            keep_heading = keep_label = None
            keep_page = 0
            if self._cur is not None and self._cur.cards:
                here = self._cur.cards[min(self._card_index, len(self._cur.cards) - 1)]
                keep_heading, keep_label, keep_page = here.heading, here.label, here.page_index

            self.w, self.h = w2, h2
            self._rebuild_layout()
            self._card_transition = 0.0
            self._book_transition = 0.0
            if self._next is not None:
                self._next.drop()
                self._next = None
            if self.books:
                index = self._cur.index if self._cur is not None else self.book_index
                if self._cur is not None:
                    self._cur.drop()
                self._cur = self._prepare_book(index)
                self._card_index = self._restore_position(keep_heading, keep_label, keep_page)
                self._reset_card_clock()
                self._ensure_card_surface(self._cur, self._card_index)
            return

        if not self.books or self._cur is None:
            return

        # Cross-fade between books.
        if self._book_transition > 0.0:
            self._book_transition -= dt / self.CROSSFADE_SECONDS
            if self._book_transition <= 0.0:
                self._book_transition = 0.0
                if self._cur is not None:
                    self._cur.drop()
                self._cur = self._next
                self._next = None
                self._card_index = 0
                self._card_transition = 0.0
                self._reset_card_clock()
                self._ensure_card_surface(self._cur, 0)
            return

        # Cross-fade between cards.
        if self._card_transition > 0.0:
            self._card_transition -= dt / self.CARD_FADE_SECONDS
            if self._card_transition <= 0.0:
                self._card_transition = 0.0
                self._card_index = self._pending_card
                self._reset_card_clock()
                self._ensure_card_surface(self._cur, self._card_index)
                self._trim_card_surfaces(self._cur, self._card_index)
            return

        # Card dwell.
        cards = self._cur.cards
        if not cards:
            return
        self._card_timer += dt
        if self._card_timer >= self._card_duration:
            self._advance_card()

    def render(self, screen: pygame.Surface):
        if self._error_message or not self.books or self._cur is None:
            self._render_error(screen, self._error_message or "No books loaded")
            return

        # One opaque blit for everything that does not change while a card is read.
        screen.blit(self._cur.base, (0, 0))

        if self._book_transition > 0.0 and self._next is not None:
            incoming_base = self._next.base
            incoming_base.set_alpha(int(255 * (1.0 - self._book_transition)))
            try:
                screen.blit(incoming_base, (0, 0))
            finally:
                incoming_base.set_alpha(None)
            self._blit_card_fade(screen, self._cur, self._card_index, self._next, 0,
                                 self._book_transition)
            return

        if self._card_transition > 0.0:
            self._blit_card_fade(screen, self._cur, self._card_index,
                                 self._cur, self._pending_card, self._card_transition)
        else:
            self._blit_card(screen, self._cur, self._card_index)

    # ---------------- data loading ----------------

    def _load_books(self):
        """Load the JSON catalog.  On failure store an error message and empty list."""
        path = self._resolve_path(self.books_file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.books = data.get("books", [])
            if not isinstance(self.books, list):
                raise ValueError("'books' must be a list")
            self._error_message = None
        except Exception as e:
            self.books = []
            self._error_message = f"Cannot load books:\n{path}\n{e}"
            print(f"[ImaginaryLibrary] {self._error_message}")

    def _scan_image_folder(self):
        """Build a sorted list of image files for index-based matching."""
        self._image_files = []
        folder = self._resolve_path(self.image_folder)
        if not os.path.isdir(folder):
            return
        files = []
        for name in os.listdir(folder):
            low = name.lower()
            if low.endswith(self.IMAGE_EXTS) and not name.startswith("."):
                files.append(name)
        self._image_files = sorted(files)

    def _resolve_path(self, path: str) -> str:
        """Return absolute path; if relative, resolve from the project root."""
        if os.path.isabs(path):
            return path
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, path)

    def _resolve_image_path(self, book: dict) -> str | None:
        """Return the filesystem path for a book's cover image, or None."""
        folder = self._resolve_path(self.image_folder)
        if not os.path.isdir(folder):
            return None

        if self.match_by == "index":
            idx = self.books.index(book)
            if idx < len(self._image_files):
                return os.path.join(folder, self._image_files[idx])
            return None

        # filename matching (default)
        filename = book.get("cover_image", "")
        if not filename:
            return None
        full = os.path.join(folder, filename)
        if os.path.isfile(full):
            return full
        return None

    # ---------------- layout ----------------

    def _build_fonts(self):
        body = self.body_font_size
        small = self.small_font_size
        self._label_font = self._get_font(max(12, int(small * 0.66)), bold=True, family=self.title_family)
        self._author_font = self._get_font(max(12, int(small * 0.95)), italic=True, family=self.title_family)
        self._heading_font = self._get_font(max(14, int(body * 0.62)), bold=True, family=self.title_family)
        self._body_font = self._get_font(body, family=self.body_family)
        self._quote_font = self._get_font(max(12, int(body * 0.90)), italic=True, family=self.title_family)
        self._meta_font = self._get_font(small, family=self.body_family)
        self._footer_font = self._get_font(max(11, int(small * 0.72)), family=self.body_family)
        self._tag_font = self._get_font(max(11, self.tag_font_size), family=self.body_family)

    def _resolve_orientation(self) -> bool:
        """True when the screen should use the portrait stack."""
        if self.layout_mode == "portrait":
            return True
        if self.layout_mode == "landscape":
            return False
        if self.legacy_portrait:
            return True
        return self.h >= self.w

    def _rebuild_layout(self):
        """Compute every region once per resolution, then the cached backdrops."""
        self._portrait = self._resolve_orientation()
        w, h = self.w, self.h
        margin = max(24, int(min(w, h) * 0.037))
        self._text_margin = margin
        self._line_gap = max(2, int(self.body_font_size * 0.10))

        if self._portrait:
            pad = margin
            header_h = int(h * max(0.08, min(0.30, self.header_frac)))
            footer_h = int(h * max(0.04, min(0.14, self.footer_frac)))
            cover_band_h = int(h * max(0.15, min(0.60, self.cover_band_frac)))
            panel_h = max(1, h - header_h - cover_band_h - footer_h)

            header_band = pygame.Rect(0, 0, w, header_h)
            cover_band = pygame.Rect(0, header_h, w, cover_band_h)
            panel = pygame.Rect(margin, header_h + cover_band_h, w - 2 * margin, panel_h)
            footer_band = pygame.Rect(0, h - footer_h, w, footer_h)

            header_inner = header_band.inflate(-2 * margin, 0)
            header_inner.y = int(margin * 0.6)
            header_inner.height = max(1, header_h - header_inner.y - int(margin * 0.5))

            inner_pad = max(14, int(margin * 0.75))
            cover_area = cover_band.inflate(-2 * pad, -2 * int(pad * 0.5))
            footer_inner = footer_band.inflate(-2 * margin, 0)
            footer_inner.y = footer_band.y + int(footer_h * 0.22)
            # Reserve room at the bottom: the controller stamps the mode number
            # in the bottom-left corner, and the progress bar must clear it.
            footer_inner.height = max(1, footer_band.bottom - footer_inner.y - int(footer_h * 0.30))
            panel_inner = panel.inflate(-2 * inner_pad, -2 * inner_pad)
        else:
            pad = margin
            left_w = int(w * 0.38)
            header_h = int(h * 0.24)
            footer_h = int(h * 0.11)

            header_band = pygame.Rect(left_w, 0, w - left_w, header_h)
            cover_band = pygame.Rect(0, 0, left_w, h)
            panel = pygame.Rect(left_w, header_h, w - left_w, max(1, h - header_h - footer_h))
            footer_band = pygame.Rect(left_w, h - footer_h, w - left_w, footer_h)

            header_inner = header_band.inflate(-2 * margin, 0)
            header_inner.y = int(margin * 0.6)
            header_inner.height = max(1, header_h - header_inner.y - int(margin * 0.4))

            cover_area = cover_band.inflate(-2 * pad, -2 * pad)
            inner_pad = max(14, int(margin * 0.75))
            panel_inner = panel.inflate(-2 * inner_pad, -2 * inner_pad)
            footer_inner = footer_band.inflate(-2 * margin, 0)
            footer_inner.y = footer_band.y + int(footer_h * 0.18)
            footer_inner.height = max(1, footer_band.bottom - footer_inner.y - int(footer_h * 0.30))

        cover = self._fit_rect(cover_area, 800 / 1200)
        # The card + footer strip is drawn as ONE opaque surface per card: on this
        # host an alpha blit costs ~7x an opaque one of the same size, so the card
        # and its footer share a rect that can be copied out of the book's base.
        content_rect = panel.union(footer_band)
        self._layout = {
            "header_band": header_band,
            "header_inner": header_inner,
            "cover_band": cover_band,
            "cover_area": cover_area,
            "cover": cover,
            "panel": panel,
            "panel_inner": panel_inner,
            "footer_band": footer_band,
            "footer_inner": footer_inner,
            "content": content_rect,
        }
        # Heading block reserved at the top of every card.
        self._heading_h = self._heading_font.get_height() + max(10, int(self.body_font_size * 0.45))
        self._avail_h = max(1, panel_inner.height - self._heading_h)
        self._inner_w = min(panel_inner.width, self._measure_cap(self._body_font))

        self._backdrop = self._build_backdrop()
        self._panel_bg = self._build_panel_bg()
        # Reusable opaque buffer for cross-fading two cards.
        self._fade_buf = pygame.Surface(content_rect.size)

    @staticmethod
    def _fit_rect(area: pygame.Rect, aspect: float) -> pygame.Rect:
        """Largest rect of the given aspect (w/h) centred inside area."""
        aw, ah = max(1, area.width), max(1, area.height)
        cw = min(aw, int(ah * aspect))
        ch = min(ah, int(aw / aspect))
        return pygame.Rect(area.x + (aw - cw) // 2, area.y + (ah - ch) // 2, cw, ch)

    def _measure_cap(self, font: pygame.font.Font) -> int:
        """Pixel width that keeps a line near max_line_chars characters."""
        sample = "the quick brown fox jumps over the lazy dog"
        avg = max(1.0, font.size(sample)[0] / len(sample))
        return int(avg * max(20, self.max_line_chars))

    def _build_backdrop(self) -> pygame.Surface:
        """Static vertical wash, built once per resolution."""
        surf = pygame.Surface((self.w, self.h))
        top, bottom = self._bg_top, self._bg_bottom
        for y in range(self.h):
            t = y / max(1, self.h - 1)
            color = (
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            )
            pygame.draw.line(surf, color, (0, y), (self.w, y))
        return surf

    def _build_panel_bg(self) -> pygame.Surface:
        """Static card panel: mostly opaque, hairline border, built once."""
        rect = self._layout["panel"]
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        alpha = int(255 * max(0.0, min(1.0, self.panel_opacity)))
        body = pygame.Rect(0, 0, rect.width, rect.height)
        pygame.draw.rect(surf, (*self._panel, alpha), body, border_radius=6)
        pygame.draw.rect(surf, (*self._rule, min(255, alpha + 20)), body, width=1, border_radius=6)
        return surf

    # ---------------- book preparation ----------------

    def _prepare_book(self, index: int) -> _BookState:
        """Build the cached state (cover, glow, header, cards) for a book."""
        state = _BookState(index)
        if not self.books:
            return state
        index = index % len(self.books)
        state.index = index
        book = self.books[index]

        state.cover = self._load_cover(book)
        state.glow = self._build_glow(state.cover)
        state.header = self._build_header(book, index)
        state.base = self._build_base(state)
        state.cards = self._build_cards(book)
        return state

    def _build_base(self, state: _BookState) -> pygame.Surface:
        """Compose every book-level layer once into one OPAQUE full-screen surface.

        Backdrop, panel plate, cover glow, cover and header never change while a
        card is being read, so they are baked together: the frame loop then costs
        one opaque blit instead of six blended ones.
        """
        base = self._backdrop.copy()
        lay = self._layout
        base.blit(self._panel_bg, lay["panel"].topleft)

        prev_clip = base.get_clip()
        base.set_clip(lay["cover_band"])
        try:
            if state.glow is not None:
                base.blit(state.glow, state.glow.get_rect(center=lay["cover"].center).topleft)
            if state.cover is not None:
                base.blit(state.cover, lay["cover"].topleft)
        finally:
            base.set_clip(prev_clip)

        if state.cover is not None:
            pygame.draw.rect(base, self._shadow, lay["cover"].inflate(6, 6), width=1)
        if state.header is not None:
            base.blit(state.header, lay["header_inner"].topleft)
        return base

    def _advance_book(self, delta: int):
        """Start a cross-fade to the next/previous book."""
        if not self.books or self._book_transition > 0.0:
            return
        if self._card_transition > 0.0:
            self._card_transition = 0.0
        next_index = (self.book_index + delta) % len(self.books)
        if self._next is not None:
            self._next.drop()
        self._next = self._prepare_book(next_index)
        self.book_index = next_index
        self._book_transition = 1.0
        self._ensure_card_surface(self._next, 0)

    def _restore_position(self, heading, label, page) -> int:
        """Find the card closest to where the reader was, after a rebuild."""
        if self._cur is None or not self._cur.cards:
            return 0
        cards = self._cur.cards
        if heading:
            for i, card in enumerate(cards):
                if card.heading == heading and card.page_index == page:
                    return i
            for i, card in enumerate(cards):
                if card.heading == heading:
                    return i
        if label:
            for i, card in enumerate(cards):
                if card.label == label:
                    return i
        return 0

    def _reset_card_clock(self):
        cards = self._cur.cards if self._cur is not None else []
        n = max(1, len(cards))
        self._card_timer = 0.0
        # P1 keeps the dwell split evenly across cards; P2 replaces this with a
        # per-card reading time.
        self._card_duration = max(1.0, self.dwell_seconds / n)

    def _advance_card(self):
        cards = self._cur.cards if self._cur is not None else []
        if not cards:
            return
        if self._card_index + 1 < len(cards):
            self._pending_card = self._card_index + 1
            self._ensure_card_surface(self._cur, self._pending_card)
            self._card_transition = 1.0
        else:
            self._advance_book(+1)

    def _trim_card_surfaces(self, state: _BookState, keep: int):
        """Keep rendered card surfaces only around the card on screen."""
        low = keep - 1
        high = keep + self.CARD_SURFACE_WINDOW
        for i, card in enumerate(state.cards):
            if i < low or i > high:
                card.drop_surfaces()

    # ---------------- cover rendering ----------------

    def _load_cover(self, book: dict):
        """Return a cover surface sized to the cover rect, loaded or generated."""
        path = self._resolve_image_path(book)
        if path:
            try:
                img = self.manager.cache.get_image(path, convert_alpha=True)
                return self._fit_cover(img)
            except Exception as e:
                print(f"[ImaginaryLibrary] Failed to load cover '{path}': {e}")
        return self._build_placeholder_cover(book)

    def _fit_cover(self, img: pygame.Surface) -> pygame.Surface:
        """Scale an image to fit the cover rect, preserving aspect ratio."""
        rect = self._layout["cover"]
        if rect.width <= 0 or rect.height <= 0:
            return img
        iw, ih = img.get_width(), img.get_height()
        scale = min(rect.width / max(1, iw), rect.height / max(1, ih))
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        scaled = pygame.transform.smoothscale(img, (nw, nh))
        out = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        out.fill((0, 0, 0, 0))
        out.blit(scaled, ((rect.width - nw) // 2, (rect.height - nh) // 2))
        return out

    def _build_glow(self, cover: pygame.Surface | None):
        """Soft halo of the cover's own colours, built once per book."""
        rect = self._layout["cover"]
        if cover is None or rect.width < 4 or rect.height < 4:
            return None
        small_w = max(2, rect.width // 12)
        small_h = max(2, int(rect.height / 12))
        try:
            tiny = pygame.transform.smoothscale(cover, (small_w, small_h))
        except Exception:
            return None
        band = self._layout["cover_band"]
        target = self._fit_rect(band.inflate(-int(band.width * 0.12), 0), rect.width / max(1, rect.height))
        try:
            glow = pygame.transform.smoothscale(tiny, (target.width, target.height))
        except Exception:
            return None
        glow.set_alpha(70)
        return glow

    def _placeholder_text_pieces(self, book: dict, w: int, h: int) -> list:
        """[(surface, rect), ...] for every text block a generated cover draws.

        Kept separate from the drawing so a test can prove each block fits: the
        previous version centred the author and footer unwrapped, and both ran
        off the cover.
        """
        margin = max(18, w // 9)
        max_text_w = w - 2 * margin
        pieces = []

        title_font, title_lines = self._fit_text(
            str(book.get("title", "?") or "?"), max_text_w, max_lines=3,
            start_size=max(self.title_font_size, int(w * 0.11)),
            family=self.title_family, bold=True,
        )
        y = int(h * 0.22)
        for line in title_lines:
            glyphs = title_font.render(line, True, self._title)
            pieces.append((glyphs, pygame.Rect((w - glyphs.get_width()) // 2, y,
                                               glyphs.get_width(), glyphs.get_height())))
            y += glyphs.get_height() + 4

        author = str(book.get("author", "") or "").strip()
        if author:
            author_font, author_lines = self._fit_text(
                author, max_text_w, max_lines=3,
                start_size=max(14, int(self.body_font_size * 0.62)),
                family=self.title_family, italic=True,
            )
            y += 10
            for line in author_lines:
                glyphs = author_font.render(line, True, self._subtitle)
                pieces.append((glyphs, pygame.Rect((w - glyphs.get_width()) // 2, y,
                                                   glyphs.get_width(), glyphs.get_height())))
                y += glyphs.get_height() + 2

        footer = "  •  ".join(str(x) for x in (book.get("year", ""), book.get("genre", "")) if x)
        if footer:
            foot_font, foot_lines = self._fit_text(
                footer, max_text_w, max_lines=2,
                start_size=max(12, int(self.small_font_size * 0.68)), family=self.body_family,
            )
            if foot_lines:
                block_h = len(foot_lines) * (foot_font.get_height() + 2)
                fy = h - margin - block_h
                for line in foot_lines:
                    glyphs = foot_font.render(line, True, self._dim)
                    pieces.append((glyphs, pygame.Rect((w - glyphs.get_width()) // 2, fy,
                                                       glyphs.get_width(), glyphs.get_height())))
                    fy += glyphs.get_height() + 2
        return pieces

    def _build_placeholder_cover(self, book: dict) -> pygame.Surface:
        """Generate a stylized fallback cover for missing images."""
        rect = self._layout["cover"]
        w, h = max(1, rect.width), max(1, rect.height)

        # Derive a slightly varied color from the book id so each cover differs.
        seed = int(hashlib.sha1(str(book.get("id", "x")).encode()).hexdigest(), 16)
        variation = (seed % 41) - 20
        base = self.placeholder_color
        color = tuple(max(0, min(255, c + variation)) for c in base)

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill(color)

        # Decorative border.
        border = max(6, w // 40)
        pygame.draw.rect(surf, self._accent, (border, border, w - 2 * border, h - 2 * border), 2)

        # Decorative corners.
        corner = max(16, w // 14)
        for ox, oy in [(0, 0), (w - corner, 0), (0, h - corner), (w - corner, h - corner)]:
            pygame.draw.line(surf, self._accent, (ox + border, oy + border + corner // 2),
                             (ox + border + corner, oy + border + corner // 2), 2)
            pygame.draw.line(surf, self._accent, (ox + border + corner // 2, oy + border),
                             (ox + border + corner // 2, oy + border + corner), 2)

        for glyphs, glyph_rect in self._placeholder_text_pieces(book, w, h):
            surf.blit(glyphs, glyph_rect.topleft)
        return surf

    def _fit_text(self, text, max_w, max_lines=2, start_size=48, family=None,
                  bold=False, italic=False):
        """Shrink a font until text fits max_lines, then wrap it. Never overflows."""
        size = max(10, int(start_size))
        font = self._get_font(size, bold=bold, italic=italic, family=family)
        lines = self._wrap_lines(font, text, max_w)
        while len(lines) > max_lines and size > 10:
            size = int(size * 0.92)
            font = self._get_font(size, bold=bold, italic=italic, family=family)
            lines = self._wrap_lines(font, text, max_w)
        return font, lines[:max_lines]

    # ---------------- header / cards ----------------

    def _line_x(self, glyph_w: int, column_x: int, column_w: int) -> int:
        """Left edge for a glyph run inside a text column, honouring text_align."""
        if self.text_align == "center":
            return column_x + max(0, (column_w - glyph_w) // 2)
        return column_x

    def _build_header(self, book: dict, index: int) -> pygame.Surface:
        """Persistent header: collection label, title, author+year, hairline."""
        rect = self._layout["header_inner"]
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        label = self.collection_label.upper()
        if self.books:
            label = f"{label}   ·   No. {index + 1} of {len(self.books)}"
        lab = self._label_font.render(label, True, self._dim)
        y = 0
        surf.blit(lab, (self._line_x(lab.get_width(), 0, rect.width), y))
        y += lab.get_height() + max(6, int(rect.height * 0.06))

        title_font, title_lines = self._fit_text(
            str(book.get("title", "?") or "?"), rect.width, max_lines=2,
            start_size=self.title_font_size, family=self.title_family, bold=True,
        )
        for line in title_lines:
            ts = title_font.render(line, True, self._title)
            if y + ts.get_height() > rect.height - 2:
                break
            surf.blit(ts, (self._line_x(ts.get_width(), 0, rect.width), y))
            y += ts.get_height() + 2

        author = str(book.get("author", "") or "").strip()
        year = book.get("year")
        if author and year:
            author = f"{author}, {year}"
        elif year:
            author = str(year)
        if author:
            afont, alines = self._fit_text(
                author, rect.width, max_lines=1,
                start_size=max(12, int(self.small_font_size * 0.95)),
                family=self.title_family, italic=True,
            )
            if alines and y + afont.get_height() + 6 <= rect.height - 2:
                asurf = afont.render(alines[0], True, self._subtitle)
                surf.blit(asurf, (self._line_x(asurf.get_width(), 0, rect.width), y + 6))

        pygame.draw.line(surf, self._rule, (0, rect.height - 1), (rect.width, rect.height - 1), 1)
        return surf

    def _sections(self, book: dict) -> list[dict]:
        """Ordered sections for a book, skipping the ones with no content."""
        sections = []

        intro = []
        review = str(book.get("review_excerpt", "") or "").strip()
        if self.show_review and review:
            intro.append({"kind": "text", "text": f"“{review}”",
                          "font": self._quote_font, "color": self._accent,
                          "gap": 0, "para_gap": max(12, int(self.body_font_size * 0.35))})
        publisher = str(book.get("publisher", "") or "").strip()
        if publisher:
            intro.append({"kind": "text", "text": publisher,
                          "font": self._meta_font, "color": self._subtitle,
                          "gap": max(10, int(self.body_font_size * 0.4)),
                          "para_gap": max(10, int(self.body_font_size * 0.3))})
        meta = "  ·  ".join(str(x) for x in (
            book.get("language"), book.get("genre"),
            f"{book.get('pages')} pp." if book.get("pages") else None,
        ) if x)
        if meta:
            intro.append({"kind": "text", "text": meta,
                          "font": self._meta_font, "color": self._dim,
                          "gap": max(8, int(self.body_font_size * 0.3)),
                          "para_gap": max(8, int(self.body_font_size * 0.3))})
        if self.show_tags and book.get("tags"):
            intro.append({"kind": "tags", "tags": list(book["tags"]), "font": self._tag_font,
                          "gap": max(12, int(self.body_font_size * 0.45))})
        if intro:
            sections.append({"label": "Introduction", "ordinal": "", "paras": intro})

        for label, key in (("Synopsis", "synopsis"), ("Publication History", "publication_history")):
            text = str(book.get(key, "") or "").strip()
            if text:
                sections.append({"label": label, "ordinal": "", "paras": [
                    {"kind": "text", "text": text, "font": self._body_font,
                     "color": self._body, "gap": 0,
                     "para_gap": max(12, int(self.body_font_size * 0.35))}]})

        history = []
        for i in range(1, 7):
            text = str(book.get(f"detailed_history_{i}", "") or "").strip()
            if text:
                history.append((_ROMAN[i - 1], text))
        if not history:
            # Backwards compatibility with the old single detailed_history field.
            text = str(book.get("detailed_history", "") or "").strip()
            if text:
                history.append(("", text))
        for ordinal, text in history:
            sections.append({"label": "Historical Reference", "ordinal": ordinal, "paras": [
                {"kind": "text", "text": text, "font": self._body_font,
                 "color": self._body, "gap": 0,
                 "para_gap": max(12, int(self.body_font_size * 0.35))}]})

        return sections

    def _build_cards(self, book: dict) -> list[_Card]:
        """Paginate every section into cards that provably fit the panel."""
        cards = []
        for section in self._sections(book):
            lines = []
            for para in section["paras"]:
                if para["kind"] == "tags":
                    rows = self._tag_rows(para["tags"], para["font"], self._inner_w)
                    pill_h = para["font"].get_height() + max(10, int(self.body_font_size * 0.2))
                    lines.append({"kind": "tags", "rows": rows, "font": para["font"],
                                  "color": self._tag_fg, "gap": para.get("gap", 0),
                                  "h": max(1, len(rows)) * pill_h,
                                  "para_end": True, "sent_end": True})
                else:
                    lines.extend(self._text_lines(
                        para["text"], para["font"], para["color"], self._inner_w,
                        para.get("gap", 0), para.get("para_gap", 0)))

            pages = self._paginate(lines, self._avail_h)
            heading = section["label"]
            if section["ordinal"]:
                heading = f"{heading}  ·  {section['ordinal']}"
            for page_index, page in enumerate(pages):
                cards.append(_Card(heading, section["label"], section["ordinal"],
                                   page_index, len(pages), page))

        if not cards:
            cards.append(_Card("Catalogue", "Catalogue", "", 0, 1, []))
        for i, card in enumerate(cards):
            card.index = i
            card.total = len(cards)
        return cards

    def _text_lines(self, text: str, font: pygame.font.Font, color, max_w: int,
                    gap: int, para_gap: int) -> list[dict]:
        """Wrap text into line records with paragraph and sentence flags."""
        out = []
        paragraphs = [p for p in str(text).split("\n\n") if p.strip()]
        for pi, para in enumerate(paragraphs):
            flat = " ".join(para.split())
            wrapped = self._wrap_lines(font, flat, max_w)
            for li, line in enumerate(wrapped):
                last = li == len(wrapped) - 1
                if pi == 0 and li == 0:
                    line_gap = gap
                elif li == 0:
                    line_gap = para_gap
                else:
                    line_gap = 0
                stripped = line.rstrip()
                out.append({
                    "kind": "text",
                    "text": line,
                    "font": font,
                    "color": color,
                    "gap": line_gap,
                    # The advance INCLUDES the inter-line gap, so the height the
                    # pager measures is exactly the height the renderer consumes.
                    "h": font.get_height() + self._line_gap,
                    "para_end": last,
                    "sent_end": last or (bool(stripped) and stripped[-1] in _SENTENCE_ENDS + _CLOSERS),
                })
        return out

    def _tag_rows(self, tags, font: pygame.font.Font, max_w: int) -> list[list[tuple]]:
        """Lay tags out as pill rows: [(text, width), ...] per row."""
        pad_x = max(8, int(self.body_font_size * 0.25))
        gap = max(6, int(self.body_font_size * 0.18))
        rows, cur, cur_w = [], [], 0
        for tag in tags:
            label = str(tag)
            tw = font.size(label)[0] + 2 * pad_x
            if cur and cur_w + tw + gap > max_w:
                rows.append(cur)
                cur, cur_w = [], 0
            cur.append((label, tw))
            cur_w += tw + gap
        if cur:
            rows.append(cur)
        return rows

    def _paginate(self, lines: list[dict], avail_h: int) -> list[list[dict]]:
        """Greedy measured fill, preferring to break at paragraph then sentence ends.

        Invariant: every line lands on exactly one card, so no text is ever lost.
        """
        pages = []
        i = 0
        n = len(lines)
        while i < n:
            height = 0
            j = i
            while j < n:
                step = (0 if j == i else lines[j]["gap"]) + lines[j]["h"]
                if height + step > avail_h:
                    break
                height += step
                j += 1
            if j == i:          # a single line taller than the card (cannot happen)
                j = i + 1
            if j < n:
                # Prefer a clean paragraph break, then a sentence break, keeping
                # at least one line on this card.
                for k in range(j, i + 1, -1):
                    if lines[k - 1]["para_end"]:
                        j = k
                        break
                else:
                    for k in range(j, i + 1, -1):
                        if lines[k - 1]["sent_end"]:
                            j = k
                            break
            pages.append(lines[i:j])
            i = j
        if not pages:
            pages.append([])
        return self._balance_pages(pages, avail_h)

    @staticmethod
    def _page_height(page: list[dict]) -> int:
        return sum((0 if i == 0 else line["gap"]) + line["h"] for i, line in enumerate(page))

    def _balance_pages(self, pages: list[list[dict]], avail_h: int) -> list[list[dict]]:
        """Move lines forward so no card is a widow.

        Greedy filling can leave a last card holding one or two lines, which reads
        as a mistake on a wall that gives every card the same time. Distribute the
        tail backwards until each card carries a reasonable share, never exceeding
        the card height.
        """
        if len(pages) < 2:
            return pages
        pages = [list(p) for p in pages]
        target = max(1, int(avail_h * 0.45))
        for i in range(len(pages) - 1, 0, -1):
            prev, cur = pages[i - 1], pages[i]
            while len(prev) > 1 and self._page_height(cur) < target:
                candidate = [prev[-1]] + cur
                if self._page_height(candidate) > avail_h:
                    break
                prev.pop()
                pages[i] = cur = candidate
        return pages

    # ---------------- card / footer surfaces ----------------

    def _card_surface(self, state: _BookState, card: _Card) -> pygame.Surface:
        """Render one card + its footer into ONE opaque surface.

        The surface starts as a copy of the book's content region, so the panel
        plate and the backdrop margin beside it are already in place: drawing on
        it stays a plain opaque blit, which is ~7x cheaper than an alpha one.
        Cached on the card and dropped when the card leaves the window.
        """
        if card.surface is not None:
            return card.surface
        content = self._layout["content"]
        panel_inner = self._layout["panel_inner"]
        footer_inner = self._layout["footer_inner"]
        base = state.base if state.base is not None else self._backdrop
        surf = base.subsurface(content).copy()

        ox = panel_inner.x - content.x
        oy = panel_inner.y - content.y
        # The text column: full panel width in portrait, capped measure in landscape.
        col_w = self._inner_w
        col_x = ox + max(0, (panel_inner.width - col_w) // 2)

        heading = self._heading_font.render(card.heading, True, self._accent)
        surf.blit(heading, (self._line_x(heading.get_width(), col_x, col_w), oy))
        rule_y = oy + self._heading_h - max(6, int(self.body_font_size * 0.22))
        pygame.draw.line(surf, self._rule, (col_x, rule_y), (col_x + col_w, rule_y), 1)

        y = oy + self._heading_h
        bottom = oy + panel_inner.height
        for line in card.lines:
            if y >= bottom:
                break
            y += line["gap"]
            if line["kind"] == "tags":
                y = self._draw_tags(surf, line, y, col_x, col_w)
            else:
                glyphs = line["font"].render(line["text"], True, line["color"])
                surf.blit(glyphs, (self._line_x(glyphs.get_width(), col_x, col_w), y))
                y += line["h"]

        self._draw_footer(surf, card, footer_inner.x - content.x, footer_inner.y - content.y)
        card.surface = surf
        return surf

    def _draw_tags(self, surf: pygame.Surface, line: dict, y: int,
                   x0: int = 0, column_w: int | None = None) -> int:
        """Draw tag pills; returns the y after the last row."""
        font = line["font"]
        pad_x = max(8, int(self.body_font_size * 0.25))
        gap = max(6, int(self.body_font_size * 0.18))
        pill_h = font.get_height() + max(10, int(self.body_font_size * 0.2))
        for row in line["rows"]:
            row_w = sum(width for _, width in row) + gap * max(0, len(row) - 1)
            x = self._line_x(row_w, x0, column_w if column_w is not None else row_w)
            for label, width in row:
                pill = pygame.Rect(x, y, width, pill_h)
                pygame.draw.rect(surf, self._tag_bg, pill, border_radius=4)
                glyphs = font.render(label, True, self._tag_fg)
                surf.blit(glyphs, (x + pad_x, y + (pill_h - glyphs.get_height()) // 2))
                x += width + gap
            y += pill_h
        return y

    def _draw_footer(self, surf: pygame.Surface, card: _Card, x: int, y: int):
        """Footer for one card: section/page on the left, sequence on the right."""
        width = self._layout["footer_inner"].width
        height = self._layout["footer_inner"].height

        label = card.label
        if card.ordinal:
            label = f"{label} · {card.ordinal}"
        if card.page_count > 1:
            label = f"{label}   ·   page {card.page_index + 1} of {card.page_count}"
        left = self._footer_font.render(label, True, self._subtitle)
        right = self._footer_font.render(f"card {card.index + 1} of {card.total}", True, self._dim)
        surf.blit(left, (x, y))
        surf.blit(right, (x + width - right.get_width(), y))

        bar_y = y + height - 5
        pygame.draw.line(surf, self._rule, (x, bar_y - 4), (x + width, bar_y - 4), 1)
        pygame.draw.rect(surf, (54, 46, 38), pygame.Rect(x, bar_y, width, 3), border_radius=2)
        frac = (card.index + 1) / max(1, card.total)
        filled = pygame.Rect(x, bar_y, int(width * frac), 3)
        if filled.width > 0:
            pygame.draw.rect(surf, self._accent, filled, border_radius=2)

    def _ensure_card_surface(self, state: _BookState, index: int):
        if state is None or not state.cards:
            return
        if 0 <= index < len(state.cards):
            self._card_surface(state, state.cards[index])

    # ---------------- drawing ----------------

    def _blit_card(self, screen: pygame.Surface, state: _BookState, index: int):
        """Steady state: one opaque blit of the whole content region."""
        if state is None or not state.cards:
            return
        index = max(0, min(index, len(state.cards) - 1))
        screen.blit(self._card_surface(state, state.cards[index]),
                    self._layout["content"].topleft)

    def _blit_card_fade(self, screen: pygame.Surface, state_a: _BookState, index_a: int,
                        state_b: _BookState, index_b: int, alpha: float):
        """Cross-fade two cards through one opaque buffer.

        Two alpha blits into a buffer plus one opaque blit out is still cheaper
        than blending both cards straight onto the screen, and it keeps the
        backdrop margin around the panel intact during the fade.
        """
        if state_a is None or state_b is None or not state_a.cards or not state_b.cards:
            self._blit_card(screen, state_b, index_b)
            return
        incoming = max(0, min(index_b, len(state_b.cards) - 1))
        outgoing = max(0, min(index_a, len(state_a.cards) - 1))
        buf = self._fade_buf
        buf.blit(self._card_surface(state_a, state_a.cards[outgoing]), (0, 0))
        fade = self._card_surface(state_b, state_b.cards[incoming])
        fade.set_alpha(int(255 * (1.0 - max(0.0, min(1.0, alpha)))))
        try:
            buf.blit(fade, (0, 0))
        finally:
            fade.set_alpha(None)
        screen.blit(buf, self._layout["content"].topleft)

    # ---------------- font / text utilities ----------------

    def _get_font(self, size: int, bold: bool = False, italic: bool = False,
                  family: str | None = None) -> pygame.font.Font:
        """Return a cached font, supporting either a system family or a font file path."""
        use = family if family else self.font_name
        key = (use, int(size), bool(bold), bool(italic))
        font = self._font_cache.get(key)
        if font is not None:
            return font

        try:
            if use and os.path.isfile(str(use)):
                # File-based fonts are loaded fresh each time so bold/italic
                # styling never leaks through the shared manager cache.
                font = pygame.font.Font(use, size)
                font.set_bold(bold)
                font.set_italic(italic)
            else:
                font = pygame.font.SysFont(use if use else None, size, bold=bold, italic=italic)
        except Exception as e:
            print(f"[ImaginaryLibrary] Font load failed ({use}, {size}px): {e}; falling back")
            font = pygame.font.Font(None, size)
            font.set_bold(bold)
            font.set_italic(italic)

        self._font_cache[key] = font
        return font

    def _wrap_lines(self, font: pygame.font.Font, text: str, max_width: int) -> list[str]:
        """Wrap text into lines that fit within max_width using the given font."""
        text = text or ""
        words = text.split()
        if not words:
            return []
        lines, cur = [], ""
        for word in words:
            test = word if not cur else cur + " " + word
            if font.size(test)[0] <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _render_error(self, screen: pygame.Surface, message: str):
        """Render a friendly error screen when the catalog cannot load."""
        screen.fill(self._bg)
        try:
            font = self._get_font(self.body_font_size, family=self.body_family)
        except Exception:
            font = pygame.font.Font(None, self.body_font_size)
        lines = message.splitlines()
        y = self.h // 4
        for line in lines:
            surf = font.render(line, True, self._body)
            x = (self.w - surf.get_width()) // 2
            screen.blit(surf, (x, y))
            y += surf.get_height() + 8
