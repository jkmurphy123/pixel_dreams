# tests/test_add_imaginary_book.py
#
# scripts/add_imaginary_book.py is the only writer for
# data/imaginary_library/books.json, and it runs unattended (nightly job), so the
# guarantees it makes are tested here rather than trusted:
#   - it refuses a payload the mode could not display;
#   - it keeps the catalog's formatting (a diff of books.json shows the new book
#     and nothing else);
#   - it writes a cover the layout can actually fit (800x1200) and crops the
#     backend's watermark band;
#   - a dry run touches nothing.
#
# All headless - no display required.

import importlib.util
import json
import os
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

SCRIPT = os.path.join(BASE_DIR, "scripts", "add_imaginary_book.py")


def load_script():
    spec = importlib.util.spec_from_file_location("add_imaginary_book", SCRIPT)
    assert spec is not None and spec.loader is not None, "cannot load the add-book script"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


add_book = load_script()


def book(**overrides):
    """A minimal payload the mode renders: required fields plus one history segment."""
    payload = {
        "id": "lib_900",
        "title": "Codex Testis",
        "author": "Brother Nobody",
        "year": 1200,
        "publisher": "A scriptorium that never existed",
        "language": "Latin",
        "pages": 100,
        "genre": "Test Volume",
        "cover_image": "900.png",
        "publication_history": "Nobody ever wrote it.",
        "synopsis": "A book that exists only in tests.",
        "review_excerpt": "It was not there before. Now it is. — Anon",
        "tags": ["test"],
        "detailed_history_1": "It begins, as these things do, in a scriptorium.",
        "detailed_history_2": "",
        "detailed_history_3": "",
        "detailed_history_4": "",
        "detailed_history_5": "",
        "detailed_history_6": "",
    }
    payload.update(overrides)
    return payload


def write_catalog(path, books=None):
    """A catalog in exactly the formatting the real one uses."""
    data = {"books": books if books is not None else []}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path


# ------------------------------------------------------------------ refusals

@pytest.mark.parametrize("field", ["title", "author", "synopsis", "publication_history",
                                   "review_excerpt", "language", "genre", "publisher",
                                   "cover_image", "id"])
def test_missing_required_text_is_refused(field):
    payload = book(**{field: "   "})
    with pytest.raises(SystemExit):
        add_book.validate_payload(payload, [], "/tmp")


@pytest.mark.parametrize("value", [None, "1200", 0, -5, 3000, True])
def test_bad_year_is_refused(value):
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(year=value), [], "/tmp")


@pytest.mark.parametrize("value", [0, -1, 9000, None, "144"])
def test_bad_pages_is_refused(value):
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(pages=value), [], "/tmp")


@pytest.mark.parametrize("tags", [[], "tag", [""], ["ok", " "]])
def test_bad_tags_are_refused(tags):
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(tags=tags), [], "/tmp")


@pytest.mark.parametrize("cover", ["../outside.png", "sub/dir/900.png", "900", "900.gif"])
def test_cover_must_be_a_bare_image_filename(cover):
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(cover_image=cover), [], "/tmp")


def test_duplicate_id_is_refused():
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(), [book()], "/tmp")


def test_cover_filename_collision_is_refused():
    other = book(id="lib_901")
    with pytest.raises(SystemExit):
        add_book.validate_payload(book(), [other], "/tmp")


def test_all_blank_histories_is_allowed_but_reported(capsys):
    payload = book(**{f"detailed_history_{i}": "" for i in range(1, 7)})
    add_book.validate_payload(payload, [], "/tmp")
    assert "no detailed_history segments" in capsys.readouterr().out


# ------------------------------------------------------------- catalog shape

def test_append_keeps_the_catalog_formatting(tmp_path):
    catalog = write_catalog(tmp_path / "books.json", [book(id="lib_001", cover_image="001.png")])
    before = open(catalog, encoding="utf-8").read()

    module_data = add_book.load_catalog(catalog)
    module_data["books"].append(book())
    text = add_book.dump_catalog(module_data)

    # The dump of the original is byte-identical, so an append is a pure addition:
    # every line before the closing brackets of the old file is untouched.
    original_dump = add_book.dump_catalog({"books": [book(id="lib_001",
                                                          cover_image="001.png")]})
    assert original_dump == before

    before_lines, after_lines = before.splitlines(), text.splitlines()
    assert after_lines[:len(before_lines) - 3] == before_lines[:-3]
    assert len(after_lines) > len(before_lines)
    json.loads(text)


def test_next_number_counts_the_highest_id(tmp_path):
    books = [book(id="lib_007"), book(id="lib_025"), book(id="custom")]
    assert add_book.next_number(books) == 26
    assert add_book.next_number([]) == 1


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    catalog = write_catalog(tmp_path / "books.json")
    before = open(catalog, encoding="utf-8").read()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(book()), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["add_imaginary_book.py", "--payload", str(payload_path),
                                      "--books", str(catalog), "--image-folder",
                                      str(tmp_path / "images"), "--dry-run"])
    assert add_book.main() == 0
    assert open(catalog, encoding="utf-8").read() == before
    assert not os.path.exists(tmp_path / "images")


def test_entry_is_written_with_every_field_the_mode_reads(tmp_path, monkeypatch):
    catalog = write_catalog(tmp_path / "books.json")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(book()), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["add_imaginary_book.py", "--payload", str(payload_path),
                                      "--books", str(catalog), "--image-folder",
                                      str(tmp_path / "images"), "--no-image"])
    assert add_book.main() == 0

    stored = json.load(open(catalog, encoding="utf-8"))["books"]
    assert len(stored) == 1
    entry = stored[0]
    assert list(entry) == ["id", "title", "author", "year", "publisher", "language", "pages",
                           "genre", "cover_image", "publication_history", "synopsis",
                           "review_excerpt", "tags"] + list(add_book.HISTORY_KEYS)
    # private prompt keys never reach the catalog
    assert not any(key.startswith("_") for key in entry)


# --------------------------------------------------------------------- cover

def test_fit_cover_crops_the_watermark_band_and_hits_800x1200(tmp_path):
    import pygame

    pygame.init()
    try:
        raw = tmp_path / "raw.png"
        source = pygame.Surface((616, 956))
        source.fill((40, 50, 90))
        pygame.draw.rect(source, (250, 250, 250), pygame.Rect(500, 940, 110, 14))  # watermark
        pygame.image.save(source, str(raw))

        out = tmp_path / "900.png"
        size, cropped, final = add_book.fit_cover(str(raw), str(out))

        assert size == (616, 956)
        assert final == (800, 1200)
        assert cropped[0] == 616 and cropped[1] < 956

        saved = pygame.image.load(str(out))
        assert saved.get_size() == (800, 1200)
        # The bright watermark block lived inside the cropped band, so it is gone.
        assert saved.get_at((760, 1180))[0] < 200
    finally:
        pygame.quit()


def test_prompt_falls_back_to_the_book_when_none_is_given():
    payload = book()
    prompt = add_book.build_prompt(payload)
    assert "Codex Testis" in prompt


def test_prompt_is_used_verbatim_when_present():
    payload = book(_image_prompt="a blue book on dark wood")
    assert add_book.build_prompt(payload) == "a blue book on dark wood"


def test_image_url_asks_for_800x1200_plus_the_crop_band():
    url = add_book.build_url("a book", 7, "flux")
    assert "width=800" in url
    assert f"height={add_book.COVER_H + add_book.WATERMARK_BAND}" in url
    assert "seed=7" in url and "model=flux" in url
    assert " " not in url                      # the prompt is URL-encoded


def test_retry_delay_obeys_the_retry_after_header():
    import urllib.error
    from email.message import Message

    headers = Message()
    headers["Retry-After"] = "30"
    error = urllib.error.HTTPError("u", 402, "Payment Required", headers, None)
    assert add_book.retry_delay(error, 1) >= 30

    # A malformed request is not worth a second attempt.
    bad = urllib.error.HTTPError("u", 400, "Bad Request", Message(), None)
    assert add_book.retry_delay(bad, 1) == 0
