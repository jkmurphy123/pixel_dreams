# tests/test_store.py
#
# Crash-safe JSON writing. The point of these tests is the failure directions: a write that
# cannot complete must leave the ORIGINAL file exactly as it was, with no temp file behind.

import json
import os
import stat
import sys
from datetime import datetime, timezone

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.store import (  # noqa: E402
    WriteVerificationError,
    atomic_write_json,
    backup_path_for,
    encode_json,
    prune_backups,
    sha256_file,
)


def test_encode_json_shape_matches_the_existing_files():
    payload = encode_json({"a": 1})
    assert payload.endswith(b"\n")
    assert payload == b'{\n  "a": 1\n}\n'


def test_atomic_write_roundtrip(tmp_path):
    target = tmp_path / "x.json"
    report = atomic_write_json(str(target), {"modes": {"1": {"type": "a"}}})

    assert report["sha256"] == sha256_file(str(target))
    assert report["previous_sha256"] is None
    assert report["backup"] is None
    assert json.loads(target.read_text()) == {"modes": {"1": {"type": "a"}}}
    # no temp siblings left behind
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "x.json"]
    assert leftovers == []


def test_backup_holds_the_previous_content(tmp_path):
    target = tmp_path / "cfg.json"
    atomic_write_json(str(target), {"v": 1})
    report = atomic_write_json(str(target), {"v": 2}, backup=True)

    assert report["backup"] and os.path.exists(report["backup"])
    assert json.loads(open(report["backup"]).read()) == {"v": 1}     # the OLD content
    assert json.loads(target.read_text()) == {"v": 2}                # the new one


def test_two_writes_in_the_same_second_get_two_backups(tmp_path):
    """Second-resolution stamps would silently overwrite one backup with the other."""
    target = tmp_path / "cfg.json"
    atomic_write_json(str(target), {"v": 1})
    a = atomic_write_json(str(target), {"v": 2}, backup=True)["backup"]
    b = atomic_write_json(str(target), {"v": 3}, backup=True)["backup"]
    assert a != b
    assert sorted(json.load(open(p))["v"] for p in (a, b)) == [1, 2]


def test_backup_names_are_collision_proof_by_construction(tmp_path):
    when = datetime(2026, 10, 15, 12, 0, 0, 123456, tzinfo=timezone.utc)
    p1 = backup_path_for(str(tmp_path / "a.json"), when=when)
    when2 = datetime(2026, 10, 15, 12, 0, 0, 123457, tzinfo=timezone.utc)
    p2 = backup_path_for(str(tmp_path / "a.json"), when=when2)
    assert p1 != p2
    assert p1.endswith(".bak") and "20261015T120000_123456Z" in p1


def test_prune_keeps_the_newest(tmp_path):
    target = tmp_path / "cfg.json"
    atomic_write_json(str(target), {"v": 0})
    for v in range(1, 6):
        atomic_write_json(str(target), {"v": v}, backup=True, keep_backups=3)

    # backups live in a .backups/ directory beside the file
    backup_dir = tmp_path / ".backups"
    remaining = sorted(p for p in backup_dir.iterdir() if p.name.startswith("cfg.json."))
    assert len(remaining) == 3
    values = sorted(json.load(open(p))["v"] for p in remaining)
    assert values == [2, 3, 4]


def test_file_mode_is_preserved(tmp_path):
    """A 0600 config must not become world-readable just because we rewrote it."""
    target = tmp_path / "secret-ish.json"
    target.write_text("{}\n")
    os.chmod(target, 0o600)
    atomic_write_json(str(target), {"a": 1})
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_failed_replace_leaves_the_original_and_no_temp(tmp_path, monkeypatch):
    """
    The failure direction that matters: if the swap fails, the old file must still be there,
    intact, and no .tmp sibling may be left for the next reader to trip over.
    """
    target = tmp_path / "cfg.json"
    atomic_write_json(str(target), {"v": "original"})
    before = target.read_bytes()

    def boom(src, dst):
        raise OSError("simulated power loss between write and rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(str(target), {"v": "new"})

    assert target.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["cfg.json"]


def test_write_verification_failure_is_raised(tmp_path, monkeypatch):
    """
    A hash mismatch must be an error, not a shrug. (The first version of this test patched a
    counter that never ran, because the pre-write hash is only taken when the file exists.)
    """
    target = tmp_path / "cfg.json"
    target.write_text("{}\n")
    monkeypatch.setattr("core.store.sha256_file", lambda path: "0" * 64)
    with pytest.raises(WriteVerificationError):
        atomic_write_json(str(target), {"a": 1})


def test_directory_is_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "deeper" / "cfg.json"
    report = atomic_write_json(str(target), {"a": 1})
    assert os.path.exists(report["path"])
