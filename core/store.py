# core/store.py
#
# Crash-safe JSON writing for files that something else reads.
#
# The profiles are read by the controller at startup and by the panel at any moment, and a
# kiosk loses power without warning: a torn or half-written config is a dead display with no
# clue why. So every write goes through here, and a write is only "done" once the bytes on
# disk have been re-read and hashed.
#
# Contract (design §7):
#   1. the CURRENT bytes are optionally backed up first (timestamped, collision-proof name)
#   2. the new bytes go to a temp sibling in the SAME directory, flushed and fsync'd
#   3. os.replace() swaps it in atomically — a reader sees the old file or the new one
#   4. the directory is fsync'd, so the rename itself survives a power cut
#   5. the file is re-read and its hash compared; a mismatch is raised, not ignored
# The temp file is removed on any failure, so a crash leaves the original untouched.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

#: Default suffix for keep-count pruning of backups (kept per target file).
DEFAULT_BACKUP_KEEP = 20


class WriteVerificationError(RuntimeError):
    """Raised when the file on disk does not match what we just wrote."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def encode_json(data, indent: int = 2) -> bytes:
    """The on-disk shape: indent=2 and a trailing newline, matching the existing files."""
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def backup_path_for(path: str, backup_dir: str | None = None, when: datetime | None = None) -> str:
    """
    A collision-proof backup name. Microseconds, not seconds: two saves inside the same
    second must not overwrite each other's backup (a test saves twice deliberately).
    """
    when = when or datetime.now(timezone.utc)
    stem = os.path.basename(path)
    directory = backup_dir or os.path.join(os.path.dirname(os.path.abspath(path)), ".backups")
    return os.path.join(directory, f"{stem}.{when.strftime('%Y%m%dT%H%M%S_%fZ')}.bak")


def prune_backups(path: str, backup_dir: str | None = None, keep: int = DEFAULT_BACKUP_KEEP) -> list:
    """Keep the newest `keep` backups of `path`; return the ones removed."""
    stem = os.path.basename(path)
    directory = backup_dir or os.path.join(os.path.dirname(os.path.abspath(path)), ".backups")
    if keep < 1 or not os.path.isdir(directory):
        return []
    prefix = f"{stem}."
    mine = sorted(f for f in os.listdir(directory) if f.startswith(prefix) and f.endswith(".bak"))
    removed = []
    for name in mine[:-keep] if len(mine) > keep else []:
        full = os.path.join(directory, name)
        try:
            os.remove(full)
            removed.append(full)
        except OSError:
            pass
    return removed


def atomic_write_json(path: str, data, *, backup: bool = False,
                      backup_dir: str | None = None, keep_backups: int = DEFAULT_BACKUP_KEEP,
                      indent: int = 2) -> dict:
    """
    Write `data` to `path` safely. Returns a small report:

        {"path", "sha256", "bytes", "backup", "previous_sha256"}
    """
    path = os.path.abspath(path)
    payload = encode_json(data, indent=indent)
    wanted = sha256_bytes(payload)

    previous_sha = sha256_file(path) if os.path.exists(path) else None
    backup_file = None
    if backup and previous_sha is not None:
        backup_file = backup_path_for(path, backup_dir)
        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
        shutil.copy2(path, backup_file)

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # Keep the target's permissions if it existed; a fresh file gets 0644.
        try:
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
        # Make the rename itself durable.
        try:
            dir_fd = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except (OSError, AttributeError):
            pass
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)

    on_disk = sha256_file(path)
    if on_disk != wanted:
        raise WriteVerificationError(
            f"{path}: wrote {wanted[:12]} but read back {on_disk[:12]}"
        )

    if backup_file:
        prune_backups(path, backup_dir, keep_backups)

    return {
        "path": path,
        "sha256": wanted,
        "bytes": len(payload),
        "backup": backup_file,
        "previous_sha256": previous_sha,
    }
