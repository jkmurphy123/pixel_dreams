#!/usr/bin/env python3
# scripts/add_imaginary_book.py
#
# Add ONE book to the Imaginary Library catalog, cover image included, in a
# single checked step.  This is the writer for data/imaginary_library/books.json:
# the mode only ever reads that file (modes/imaginary_library_mode.py, _load_books),
# so a book that is not in here does not exist as far as the wall is concerned.
#
# Why a script and not a JSON edit by hand: the three parts of a book have to
# agree with each other, and two of them are easy to get subtly wrong.
#   - the entry's cover_image must name a file that really exists in the image
#     folder, or the mode silently falls back to a generated placeholder;
#   - the cover image must be 800x1200, because the layout fits that aspect and
#     anything else is letterboxed inside the cover rect;
#   - the appended JSON must keep the file's formatting, or every later diff of
#     books.json is noise.
#
# Usage
#   scripts/add_imaginary_book.py --payload book.json
#   scripts/add_imaginary_book.py --payload book.json --dry-run
#   scripts/add_imaginary_book.py --payload book.json --no-image
#   scripts/add_imaginary_book.py --payload book.json --force-new-image
#
# Payload = one book object with the mode's fields (designs/LIBRARY_DESIGN.md §4)
# plus these optional, script-only keys.  They are stripped before the entry is
# written, so they never reach the JSON the mode reads:
#   _image_prompt     text-to-image prompt for the cover.  Omit it and the
#                     prompt is built from title/author/genre/synopsis.
#   _image_seed       integer seed, so a re-run reproduces the same picture.
#                     (There is no negative-prompt field: the backend has no such
#                     parameter, and a list of things to avoid tends to pull them in.)
#
# The image backend is Pollinations (keyless HTTP GET).  It stamps a small
# watermark into the bottom-right corner that only an account can remove, so the
# picture is requested 40px taller than the cover and that band is cropped away.
#
# Run it with the repo venv (pygame does the JPEG decode and the PNG encode):
#   .venv/bin/python scripts/add_imaginary_book.py --payload book.json

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import NoReturn

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DEFAULT_BOOKS = os.path.join("data", "imaginary_library", "books.json")
DEFAULT_IMAGES = os.path.join("assets", "imaginary_library")

COVER_W, COVER_H = 800, 1200
# Extra height requested so the backend's watermark can be cropped off.
WATERMARK_BAND = 40

IMAGE_ENDPOINT = "https://image.pollinations.ai/prompt/"
IMAGE_MODEL = "flux"

# Fields the mode reads and the design doc requires (LIBRARY_DESIGN.md §4).
REQUIRED_TEXT = ("id", "title", "author", "publisher", "language", "genre",
                 "cover_image", "publication_history", "synopsis", "review_excerpt")
HISTORY_KEYS = tuple(f"detailed_history_{i}" for i in range(1, 7))
ALL_KEYS = REQUIRED_TEXT + ("year", "pages", "tags") + HISTORY_KEYS

STYLE = ("museum photograph of a single antique book standing on dark walnut, near-black "
         "background, warm candlelight from the upper left, deep shadow, blank unlettered cover")


# --------------------------------------------------------------------- helpers

def fail(message: str) -> NoReturn:
    print(f"[add_book] ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def atomic_write(path: str, data: bytes) -> None:
    """Temp sibling, flush, fsync, os.replace — never a half-written file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_catalog(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"catalog not found: {path}")
    except json.JSONDecodeError as e:
        # Refuse rather than rewrite: a broken catalog is the operator's to fix.
        fail(f"catalog is not valid JSON ({e}); refusing to touch it")
    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        fail("catalog must be an object with a 'books' list")
    return data


def dump_catalog(data: dict) -> str:
    """The exact formatting books.json already uses (indent 2, UTF-8, newline)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def next_number(books: list) -> int:
    """Highest lib_NNN number in the catalog, plus one."""
    highest = 0
    for book in books:
        ident = str(book.get("id", ""))
        if ident.startswith("lib_") and ident[4:].isdigit():
            highest = max(highest, int(ident[4:]))
    return highest + 1


# ------------------------------------------------------------------ validation

def validate_payload(payload: dict, books: list, images_dir: str,
                     allow_existing_id: bool = False) -> None:
    if not isinstance(payload, dict):
        fail("payload must be a JSON object holding one book")

    for key in REQUIRED_TEXT:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            fail(f"missing or empty field: {key}")
    for key in HISTORY_KEYS:
        payload.setdefault(key, "")
        if not isinstance(payload[key], str):
            fail(f"{key} must be a string (blank segments are skipped)")

    year = payload.get("year")
    if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 2100:
        fail(f"year must be an integer between 1 and 2100, got {year!r}")
    pages = payload.get("pages")
    if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= 5000:
        fail(f"pages must be an integer between 1 and 5000, got {pages!r}")
    tags = payload.get("tags")
    if not isinstance(tags, list) or not tags or not all(
            isinstance(t, str) and t.strip() for t in tags):
        fail("tags must be a non-empty list of non-empty strings")

    cover = payload["cover_image"]
    if os.path.basename(cover) != cover or not cover.lower().endswith(
            (".png", ".jpg", ".jpeg")):
        fail(f"cover_image must be a bare filename with an image extension: {cover!r}")

    for book in books:
        if book.get("id") == payload["id"] and not allow_existing_id:
            fail(f"id already in the catalog: {payload['id']}")
        if book.get("cover_image") == cover and book.get("id") != payload["id"]:
            fail(f"cover_image already used by {book.get('id')}: {cover}")

    # A book with no history segments still displays (intro + synopsis cards);
    # an all-blank set is legal but worth saying out loud.
    if not any(payload[k].strip() for k in HISTORY_KEYS):
        print("[add_book] note: no detailed_history segments; the book shows only "
              "its introduction and synopsis")


# ----------------------------------------------------------------------- image

def build_prompt(payload: dict) -> str:
    prompt = str(payload.get("_image_prompt") or "").strip()
    if prompt:
        return prompt
    bits = [STYLE]
    title = payload["title"]
    bits.insert(0, f"an antique book titled {title}")
    bits.append(f"associated with {payload['author']}, {payload['genre'].lower()}")
    bits.append(str(payload.get("synopsis", ""))[:220])
    return ", ".join(b.strip(" ,.") for b in bits if b.strip())


def build_url(prompt: str, seed: int | None, model: str) -> str:
    # No negative-prompt support: things the picture must NOT contain are best
    # described positively in the prompt ("blank unlettered cover"), because a
    # "no text, no letters" tail can pull lettering into the picture instead.
    query = {
        "width": str(COVER_W),
        "height": str(COVER_H + WATERMARK_BAND),
        "model": model,
        "nologo": "true",
    }
    if seed is not None:
        query["seed"] = str(seed)
    return IMAGE_ENDPOINT + urllib.parse.quote(prompt, safe="") + "?" + urllib.parse.urlencode(query)


def retry_delay(error: Exception, attempt: int) -> float:
    """How long to wait after a failed attempt.

    The free tier answers 402 FREE_LIMIT with the waiting time in Retry-After
    (1 image per 45s per IP), so obey the header instead of guessing: a fixed
    backoff turns one slow minute into a failed run.
    """
    if isinstance(error, urllib.error.HTTPError):
        header = error.headers.get("Retry-After") if error.headers else None
        try:
            if header is not None:
                return max(5.0, float(header) + 2.0)
        except ValueError:
            pass
        if error.code in (402, 429):
            return 45.0 + 2.0 * attempt
        if error.code in (400, 401, 403, 404):
            return 0.0          # our request is wrong; retrying will not fix it
    return 5.0 * attempt


def download(url: str, dest_raw: str, attempts: int = 6, timeout: int = 240) -> None:
    last = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "pixel_dreams/add_book"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            if len(body) < 4096:
                raise ValueError(f"response too small ({len(body)} bytes)")
            with open(dest_raw, "wb") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            return
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
            last = e
            # The body carries the machine-readable reason (FREE_LIMIT vs a model
            # that needs an account); read it so the log says which.
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = e.read()[:300].decode("utf-8", "replace")
                except Exception:
                    detail = ""
            print(f"[add_book] image attempt {attempt}/{attempts} failed: {e} {detail}")
            if attempt < attempts:
                delay = retry_delay(e, attempt)
                if delay <= 0:
                    fail(f"image request rejected ({e}); not retrying")
                print(f"[add_book] waiting {delay:.0f}s before retrying")
                time.sleep(delay)
    fail(f"image generation failed after {attempts} attempts: {last}")


def fit_cover(raw_path: str, out_path: str) -> tuple:
    """Crop the watermark band, then scale to exactly COVER_W x COVER_H."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    pygame.init()
    try:
        image = pygame.image.load(raw_path)
        width, height = image.get_size()
        if width < 64 or height < 64:
            fail(f"generated image is implausibly small: {width}x{height}")
        # Crop the bottom band (watermark) and any transparent surround.
        keep_h = height - int(round(WATERMARK_BAND * height / (COVER_H + WATERMARK_BAND)))
        if keep_h < 64:
            keep_h = height
        cropped = pygame.Surface((width, keep_h))
        cropped.blit(image, (0, 0), pygame.Rect(0, 0, width, keep_h))
        scaled = pygame.transform.smoothscale(cropped, (COVER_W, COVER_H))
        tmp = out_path + ".tmp.png"
        pygame.image.save(scaled, tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        atomic_write(out_path, data)
        os.unlink(tmp)
        return (width, height), cropped.get_size(), (COVER_W, COVER_H)
    finally:
        pygame.quit()


# ------------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add one book (entry + 800x1200 cover) to the Imaginary Library.")
    parser.add_argument("--payload", required=True,
                        help="JSON file holding one book object (with optional _image_* keys)")
    parser.add_argument("--books", default=DEFAULT_BOOKS, help="catalog path")
    parser.add_argument("--image-folder", default=DEFAULT_IMAGES, help="cover image folder")
    parser.add_argument("--model", default=IMAGE_MODEL, help=f"image model (default {IMAGE_MODEL})")
    parser.add_argument("--seed", type=int, default=None,
                        help="image seed (overrides _image_seed; varied per book otherwise)")
    parser.add_argument("--image-file", default=None,
                        help="use an existing local image instead of generating one "
                             "(cropped and scaled to 800x1200 the same way)")
    parser.add_argument("--no-image", action="store_true",
                        help="write the entry only (mode shows a placeholder cover)")
    parser.add_argument("--force-new-image", action="store_true",
                        help="regenerate the cover and overwrite the target file")
    parser.add_argument("--allow-existing-id", action="store_true",
                        help="replace an entry that already has this id")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and print what would happen; write nothing")
    args = parser.parse_args()

    books_path = resolve(args.books)
    images_dir = resolve(args.image_folder)

    try:
        with open(args.payload, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail(f"cannot read payload {args.payload}: {e}")

    catalog = load_catalog(books_path)
    books = catalog["books"]

    # Fill in the numbered id/cover from the catalog when the payload omits them,
    # so a daily job never has to know how many books exist.
    number = next_number(books)
    payload.setdefault("id", f"lib_{number:03d}")
    payload.setdefault("cover_image", f"{number:03d}.png")

    validate_payload(payload, books, images_dir, allow_existing_id=args.allow_existing_id)

    entry = {key: payload[key] for key in ALL_KEYS if key in payload}
    entry.setdefault("year", payload.get("year"))
    entry.setdefault("pages", payload.get("pages"))
    entry.setdefault("tags", payload["tags"])
    for key in HISTORY_KEYS:
        entry.setdefault(key, "")

    # Keep the catalog's own key order so the file stays readable.
    order = ["id", "title", "author", "year", "publisher", "language", "pages", "genre",
             "cover_image", "publication_history", "synopsis", "review_excerpt", "tags"] + \
            list(HISTORY_KEYS)
    entry = {key: entry[key] for key in order if key in entry}

    image_path = os.path.join(images_dir, entry["cover_image"])
    prompt = build_prompt(payload)
    seed = args.seed if args.seed is not None else payload.get("_image_seed")

    print(f"[add_book] book      : {entry['id']} — {entry['title']}")
    print(f"[add_book] cover     : {image_path}")
    print(f"[add_book] prompt    : {prompt[:160]}{'...' if len(prompt) > 160 else ''}")
    print(f"[add_book] seed      : {seed if seed is not None else '(none)'}")

    if args.dry_run:
        print("[add_book] dry run: nothing written")
        return 0

    # ---- image ----
    wanted_image = not args.no_image
    if os.path.exists(image_path) and not args.force_new_image and wanted_image:
        print(f"[add_book] cover already exists, keeping it: {image_path}")

    if wanted_image and not os.path.exists(image_path):
        os.makedirs(images_dir, exist_ok=True)
        if args.image_file:
            src = resolve(args.image_file)
            if not os.path.isfile(src):
                fail(f"--image-file not found: {src}")
            size, cropped, final = fit_cover(src, image_path)
            print(f"[add_book] image     : {size} -> cropped {cropped} -> {final}")
            dest = image_path
        else:
            raw = os.path.join(images_dir, ".incoming-" + entry["id"] + ".jpg")
            download(build_url(prompt, seed, args.model), raw)
            size, cropped, final = fit_cover(raw, image_path)
            os.unlink(raw)
            print(f"[add_book] image     : {size} -> cropped {cropped} -> {final}")
            dest = image_path

        # Prove the mode will find it: same extension/dir match it uses at runtime.
        if not os.path.isfile(dest):
            fail(f"cover file missing after write: {dest}")

    # ---- catalog ----
    if args.allow_existing_id:
        books = [b for b in books if b.get("id") != entry["id"]]
    books.append(entry)
    catalog["books"] = books

    text = dump_catalog(catalog)
    json.loads(text)  # never write something we cannot read back

    backup_dir = os.path.join(os.path.dirname(books_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(books_path, os.path.join(backup_dir, f"books-{stamp}.json"))

    atomic_write(books_path, text.encode("utf-8"))

    # ---- verify by re-reading ----
    check = load_catalog(books_path)
    added = [b for b in check["books"] if b.get("id") == entry["id"]]
    if len(added) != 1:
        fail(f"wrote the catalog but cannot find {entry['id']} in it")
    if not os.path.isfile(os.path.join(images_dir, added[0]["cover_image"])):
        print(f"[add_book] warning: {added[0]['cover_image']} is missing; the mode will "
              f"draw a placeholder cover for this book")

    print(f"[add_book] catalog   : {len(check['books'])} books, backup in "
          f"{os.path.relpath(backup_dir, BASE_DIR)}")
    print("[add_book] done. The running kiosk still holds the old catalog: "
          "POST /api/refresh to the panel, or restart the service, to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
