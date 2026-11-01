#!/usr/bin/env python3
"""
slow_wireframe_job.py — the ledger for the unattended Slow Wireframe build job.

The job is a 3-hourly timer that wakes an agent, which builds ONE mode from
`designs/SLOW_WIREFRAME_DESIGN.MD` and ticks its line in §9. This script owns every
decision that must not be left to a fresh agent's judgement:

  * which mode is next — the lowest unticked §9 line, never a guess;
  * whether a run may start at all — hold, already-running, or budget spent;
  * the move that stops a run that outlived its slot, and the hold that follows it;
  * the 5-runs-per-24-hours ceiling, so twenty modes take four days, not one night;
  * ticking the box — only `finish` writes it, and only for the run that is current.

Why a ledger and not just the document: §9 can say which modes are finished, but it
cannot say that a run is in flight, how many runs happened today, or that a human
hit the brakes. That is `runtime/slow_wireframe/state.json` (gitignored, next to the
runtime state the panel already keeps). The document stays the durable queue — the
checkboxes are the truth about completion — and this file is the truth about
operation. `start` re-reads §9 every time; a tick made by hand is respected, never
overwritten.

The four verdicts, and what the caller must do with each:

    PROCEED     one run was opened (a `current` marker + a run id); build the mode in
                the printed brief, then close the run with `finish` or `fail`
    SKIP_CAP    five runs already started inside the last 24 hours; touch nothing
    HOLD        the job is parked (previous run never closed, a mode failed three
                times, or a human parked it); touch nothing, review, then `resume`
    DONE        all twenty §9 lines are ticked; the job parked itself and a new
                design document is what unblocks it

Two invariants worth spelling out, because both are money:

  * `finish` refuses a run id that is no longer current. A run that was aborted by a
    later `start` cannot come back and tick a box behind the new run's back.
  * A run that never closes leaves `current` set, and the NEXT run does not build —
    it kills what the old run recorded, records it as aborted, and holds. The job
    never silently carries on over an unfinished run.

Usage (the timer runs exactly the first of these):

    .venv/bin/python scripts/slow_wireframe_job.py start
    .venv/bin/python scripts/slow_wireframe_job.py finish --run-id ID --mode N
    .venv/bin/python scripts/slow_wireframe_job.py fail --run-id ID --reason "..."
    .venv/bin/python scripts/slow_wireframe_job.py status
    .venv/bin/python scripts/slow_wireframe_job.py hold --reason "..." [--note "..."]
    .venv/bin/python scripts/slow_wireframe_job.py resume
    .venv/bin/python scripts/slow_wireframe_job.py abort-current --reason "..."
    .venv/bin/python scripts/slow_wireframe_job.py pid --pid 12345
    .venv/bin/python scripts/slow_wireframe_job.py rearm

Exit status is 0 for every verdict (a held or capped job is a normal outcome, not a
crash) and 2 for a refusal or a broken ledger. The verdict line is what a caller
should act on.

Env overrides, for tests and for a second checkout: SLOW_WIREFRAME_STATE_DIR,
SLOW_WIREFRAME_DOC, SLOW_WIREFRAME_NOW.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import signal
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:                                        # Windows dev box: no advisory lock available.
    import fcntl
except ImportError:                         # pragma: no cover - the current marker still guards
    fcntl = None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOC = ROOT / "designs" / "SLOW_WIREFRAME_DESIGN.MD"
DEFAULT_STATE_DIR = ROOT / "runtime" / "slow_wireframe"
BRIEF_TEMPLATE = ROOT / "scripts" / "slow_wireframe_brief.md"

MAX_RUNS_PER_WINDOW = 5                     # "not more than five times in one 24 hour period"
RUN_WINDOW = timedelta(hours=24)
RUN_SLOT = timedelta(hours=3)               # the schedule's period; older than this = overran
MAX_FAILURES = 3                            # per mode, then the job holds for a human
MAX_RUN_HISTORY = 200

SCHEDULE_TITLE = "Slow Wireframe mode builds"
SCHEDULE_INTERVAL_SECONDS = 3 * 60 * 60

# Verdicts. `start` prints exactly one of these; everything else in the output is detail.
PROCEED = "PROCEED"
SKIP_CAP = "SKIP_CAP"
HOLD = "HOLD"
DONE = "DONE"
STUCK_HOLD = "STUCK_HOLD"

# Reasons that end up in state["hold"]["reason"].
HOLD_ALL_DONE = "all_modes_complete"
HOLD_PREV_RUN = "previous_run_still_active"
HOLD_REPEATED_FAILURE = "repeated_failure"

#: Tokens the brief template may use. Any other `{{...}}` is a typo, and is refused.
BRIEF_TOKENS = (
    "RUN_ID", "MODE_NUMBER", "TOTAL", "REMAINING", "TITLE", "TYPE_KEY", "FILE",
    "CLASS_NAME", "MODULE", "TEST_FILE", "PREVIEW_SCRIPT", "STILLS_DIR",
    "CAMERA", "BUILD", "WAVE", "CARD", "DOC", "ROOT", "TODAY",
)

TRACKER_RE = re.compile(
    r"^(?P<lead>\s*-\s\[)(?P<mark>[ xX])\]"
    r"\s+(?P<number>\d+)\s+·\s+`(?P<key>[^`]+)`\s+·\s+(?P<rest>.*?)\s*$"
)
DONE_SUFFIX_RE = re.compile(r"\s+—\s+done\s+\d{4}-\d{2}-\d{2}\s*$")


class JobError(RuntimeError):
    """A refusal: bad arguments, a broken ledger, or a state that forbids the action."""


@dataclass(frozen=True)
class TrackerEntry:
    """One §9 line: number, type key, title, camera, build, wave, file and class.

    `raw` is the exact line as written; a tick rewrites only the mark and appends the
    done suffix, so nobody's formatting is lost.
    """

    number: int
    type_key: str
    title: str
    camera: str
    build: str
    wave: str
    file: str
    class_name: str
    done: bool
    line_index: int
    raw: str

    @property
    def card(self) -> str:
        """The §4 heading this line points at, e.g. `4.7 Orbital Shipyard`."""
        return f"4.{self.number} {self.title}"


# --------------------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime | None) -> datetime:
    """Aware UTC datetime; a naive one is read as UTC (never as local time)."""
    if dt is None:
        return _now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    try:
        return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError) as exc:
        raise JobError(f"bad timestamp in the ledger: {value!r}") from exc


def _local_date(dt: datetime) -> str:
    """The date a human reads on the wall clock — what the done suffix records."""
    return _utc(dt).astimezone().strftime("%Y-%m-%d")


def _human_delta(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _rel(path) -> str:
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except (ValueError, OSError):
        return str(path)


# --------------------------------------------------------------------------------------
# the design document — §9 is the queue
# --------------------------------------------------------------------------------------

def _read_doc(doc: Path) -> tuple[list[str], list[TrackerEntry]]:
    doc = Path(doc)
    if not doc.exists():
        raise JobError(f"design document not found: {doc}")
    text = doc.read_text(encoding="utf-8")
    lines = text.split("\n")
    entries: list[TrackerEntry] = []
    for index, line in enumerate(lines):
        match = TRACKER_RE.match(line)
        if match is None:
            continue
        rest = DONE_SUFFIX_RE.sub("", match.group("rest"))
        fields = [field.strip() for field in rest.split(" · ")]
        if len(fields) != 6:
            raise JobError(
                f"{_rel(doc)} line {index + 1}: the tracker line has {len(fields)} fields, "
                "expected 6 (`title · camera · build · wave · file · class`). "
                "Do not reformat §9 — the job parses it."
            )
        title, camera, build, wave, file_field, class_field = fields
        if not (file_field.startswith("`modes/") and file_field.endswith(".py`")):
            raise JobError(f"{_rel(doc)} line {index + 1}: expected a `modes/….py` file field")
        entries.append(
            TrackerEntry(
                number=int(match.group("number")),
                type_key=match.group("key"),
                title=title,
                camera=camera,
                build=build,
                wave=wave,
                file=file_field.strip("`"),
                class_name=class_field.strip("`"),
                done=match.group("mark").lower() == "x",
                line_index=index,
                raw=line,
            )
        )
    return lines, entries


def load_tracker(doc: Path = DEFAULT_DOC) -> list[TrackerEntry]:
    """Every §9 line, in document order. Raises JobError rather than guess."""
    _, entries = _read_doc(Path(doc))
    return entries


def validate_tracker(entries: list[TrackerEntry], doc: Path = DEFAULT_DOC) -> None:
    """
    The queue has to be a well-formed 1..N list before a run may open: a duplicated key
    would get built twice, a skipped number would strand a mode forever.
    """
    if not entries:
        raise JobError(f"{_rel(doc)}: no tracker lines (`- [ ] N · key · …`) found in §9")
    numbers = [entry.number for entry in entries]
    expected = list(range(1, len(entries) + 1))
    if numbers != expected:
        raise JobError(
            f"{_rel(doc)}: tracker numbers must run 1..{len(entries)} in order; got {numbers}"
        )
    for field in ("type_key", "file", "class_name"):
        values = [getattr(entry, field) for entry in entries]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise JobError(f"{_rel(doc)}: duplicate {field} in the tracker: {duplicates}")


def pending_entries(entries: list[TrackerEntry]) -> list[TrackerEntry]:
    """Unticked lines, lowest number first — the build order."""
    return sorted((entry for entry in entries if not entry.done), key=lambda entry: entry.number)


def _atomic_write_text(path: Path, text: str) -> None:
    """
    Temp sibling, fsync, os.replace, fsync the directory, re-read and compare. The design
    document is the queue and it lives in git, so a torn write here would lose tracked
    work — the same rule §7 of PIXEL_DREAMS_DESIGN.md applies to the profile JSON.
    """
    path = Path(path)
    data = text.encode("utf-8")
    mode = os.stat(path).st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        tmp = None
        try:
            directory = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, AttributeError):      # pragma: no cover - Windows
            pass
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.remove(tmp)
    if path.read_bytes() != data:
        raise JobError(f"{_rel(path)}: wrote the file but read back different bytes")


def apply_tick(doc: Path, number: int, *, when: datetime | None = None) -> dict:
    """
    Tick one §9 line: `[ ]` -> `[x]` and ` — done YYYY-MM-DD` appended. Idempotent — an
    already-ticked line is reported and left byte-identical.
    """
    doc = Path(doc)
    lines, entries = _read_doc(doc)
    validate_tracker(entries, doc)
    entry = next((item for item in entries if item.number == int(number)), None)
    if entry is None:
        raise JobError(f"{_rel(doc)}: no tracker line numbered {number}")
    if entry.done:
        return {"changed": False, "number": entry.number, "type_key": entry.type_key,
                "line": entry.raw}
    stamp = _local_date(_utc(when))
    new_line = re.sub(r"\[ \]", "[x]", entry.raw, count=1).rstrip() + f" — done {stamp}"
    lines[entry.line_index] = new_line
    _atomic_write_text(doc, "\n".join(lines))
    return {"changed": True, "number": entry.number, "type_key": entry.type_key,
            "line": new_line}


# --------------------------------------------------------------------------------------
# the ledger
# --------------------------------------------------------------------------------------

def state_path(state_dir: Path | str = DEFAULT_STATE_DIR) -> Path:
    return Path(state_dir) / "state.json"


def log_path(state_dir: Path | str = DEFAULT_STATE_DIR) -> Path:
    return Path(state_dir) / "logs" / "job.log"


def default_state() -> dict:
    return {
        "version": 1,
        "design": _rel(DEFAULT_DOC),
        "hold": None,
        "current": None,
        "runs": [],
        "failures": {},
    }


def load_state(state_dir: Path | str = DEFAULT_STATE_DIR) -> dict:
    """
    A missing ledger is a fresh job; a corrupt one is a refusal, not a reset. Silently
    starting over would forget that a run is in flight, which is how a mode gets built
    twice and a bill gets doubled.
    """
    path = state_path(state_dir)
    state = default_state()
    if not path.exists():
        return state
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JobError(
            f"{_rel(path)} is unreadable ({exc}). The job is stopped until it is fixed: "
            f"move the file aside to start a fresh ledger, or repair it by hand."
        ) from exc
    if not isinstance(loaded, dict):
        raise JobError(f"{_rel(path)}: expected a JSON object at the top level")
    state.update(loaded)
    state["runs"] = [run for run in (state.get("runs") or []) if isinstance(run, dict)]
    state["failures"] = dict(state.get("failures") or {})
    return state


def save_state(state_dir: Path | str, state: dict) -> None:
    path = state_path(state_dir)
    state["runs"] = state.get("runs", [])[-MAX_RUN_HISTORY:]
    data = (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_text(path, data.decode("utf-8"))


def log_event(state_dir: Path | str, event: str, **fields) -> None:
    """One JSON line per decision. Append-only, and never a reason to fail a run."""
    path = log_path(state_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"at": _iso(_now()), "event": event, **fields}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


@contextlib.contextmanager
def state_lock(state_dir: Path | str = DEFAULT_STATE_DIR):
    """
    An advisory lock around every read-modify-write. It is held for milliseconds (the CLI
    exits), so contention means two timers fired at once — which must not interleave
    their reads of `current`.
    """
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    handle = open(Path(state_dir) / "state.lock", "a+")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise JobError(
                    "another slow_wireframe_job.py process is holding the state lock; "
                    "treat this tick as already running"
                ) from exc
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def runs_in_window(state: dict, now: datetime) -> list[dict]:
    """
    Runs that started strictly inside the last 24 hours.

    Strict, not inclusive: a run that started exactly 24 hours ago has left the window.
    That is what lets a wave restart on its own 3-hour slot instead of slipping three
    hours later every day — five runs on day 1, five on day 2, and twenty modes in four
    days rather than four and a half.
    """
    since = _utc(now) - RUN_WINDOW
    counted = []
    for run in state.get("runs", []):
        try:
            started = _parse_iso(run.get("started_at", ""))
        except JobError:
            continue
        if started > since:
            counted.append(run)
    return counted


def next_slot_at(state: dict, now: datetime) -> datetime | None:
    """When the oldest counted run falls out of the 24-hour window."""
    counted = runs_in_window(state, now)
    if not counted:
        return None
    oldest = min(_parse_iso(run["started_at"]) for run in counted)
    return oldest + RUN_WINDOW


def _set_hold(state: dict, reason: str, note: str, now: datetime) -> dict:
    state["hold"] = {"reason": reason, "note": note, "at": _iso(_utc(now))}
    return state["hold"]


def _kill_pids(pids) -> list[int]:
    """
    Stop what the previous run recorded it started. Only recorded PIDs — never a pattern
    kill, never init, never this process. A stale run's recorded children are the only
    processes this job has any business killing.
    """
    killed: list[int] = []
    for raw in pids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid <= 1 or pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return killed


def _abort_current(state: dict, now: datetime, reason: str) -> dict:
    """Close the open run as aborted and release `current`. It counts against the budget."""
    current = state.get("current")
    if not current:
        raise JobError("no run is in progress")
    started = _parse_iso(current.get("started_at", ""))
    report = {
        "run_id": current.get("run_id"),
        "mode": current.get("mode"),
        "type_key": current.get("type_key"),
        "started_at": current.get("started_at"),
        "elapsed": _human_delta(_utc(now) - started),
        "killed": _kill_pids(current.get("pids")),
        "reason": reason,
    }
    state.setdefault("runs", []).append(
        {
            "run_id": current.get("run_id"),
            "mode": current.get("mode"),
            "type_key": current.get("type_key"),
            "started_at": current.get("started_at"),
            "ended_at": _iso(_utc(now)),
            "outcome": "aborted",
            "reason": reason,
        }
    )
    state["current"] = None
    return report


# --------------------------------------------------------------------------------------
# the brief
# --------------------------------------------------------------------------------------

def render_brief(template_path: Path, *, entry: TrackerEntry, run_id: str, doc: Path,
                 total: int, remaining: int, now: datetime) -> str:
    """
    Fill the builder brief. `{{TOKEN}}` rather than `{}` or `$`: the template is prose with
    shell snippets and JSON in it, and a stray brace must never be able to break the run.
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise JobError(f"brief template missing: {_rel(template_path)}")
    text = template_path.read_text(encoding="utf-8")
    stem = Path(entry.file).stem                       # `dyson_swarm_mode`
    base = stem[:-5] if stem.endswith("_mode") else stem
    values = {
        "RUN_ID": run_id,
        "MODE_NUMBER": str(entry.number),
        "TOTAL": str(total),
        "REMAINING": str(remaining),
        "TITLE": entry.title,
        "TYPE_KEY": entry.type_key,
        "FILE": entry.file,
        "CLASS_NAME": entry.class_name,
        "MODULE": ".".join(Path(entry.file).with_suffix("").parts),
        "TEST_FILE": f"tests/test_{base}.py",
        "PREVIEW_SCRIPT": f"scripts/{base}_preview.py",
        "STILLS_DIR": f"screenshots/slow_wireframe/{base}/",
        "CAMERA": entry.camera,
        "BUILD": entry.build,
        "WAVE": entry.wave,
        "CARD": entry.card,
        "DOC": _rel(doc),
        "ROOT": str(ROOT),
        "TODAY": _local_date(_utc(now)),
    }
    missing = [token for token in BRIEF_TOKENS if "{{" + token + "}}" not in text]
    if missing:
        raise JobError(
            f"{_rel(template_path)}: template no longer contains {missing} — the brief and "
            "the ledger have drifted apart"
        )

    def substitute(match: re.Match) -> str:
        token = match.group(1)
        if token not in values:
            raise JobError(f"{_rel(template_path)}: unknown brief token {{{{{token}}}}}")
        return values[token]

    return re.sub(r"\{\{([A-Z_]+)\}\}", substitute, text)


# --------------------------------------------------------------------------------------
# start / finish / fail
# --------------------------------------------------------------------------------------

def start(*, state_dir: Path | str = DEFAULT_STATE_DIR, doc: Path = DEFAULT_DOC,
          now: datetime | None = None, brief_template: Path = BRIEF_TEMPLATE) -> dict:
    """
    Decide this tick. Returns a report whose `verdict` is the only thing a caller must act
    on: PROCEED (one run opened, brief in `report["brief"]`), SKIP_CAP, HOLD, DONE or
    STUCK_HOLD.

    The order of the checks is deliberate: a finished queue beats everything, a human's
    hold beats the timer, and an unfinished run beats the budget (it needs the budget
    anyway, and it must be stopped before anything new is considered).
    """
    now = _utc(now)
    doc = Path(doc)
    _, entries = _read_doc(doc)
    validate_tracker(entries, doc)
    state_dir = Path(state_dir)
    total = len(entries)

    with state_lock(state_dir):
        state = load_state(state_dir)
        pending = pending_entries(entries)
        slot = next_slot_at(state, now)
        report: dict = {
            "now": _iso(now),
            "done": total - len(pending),
            "total": total,
            "runs_in_window": len(runs_in_window(state, now)),
            "next_slot_at": _iso(slot) if slot else None,
        }

        if not pending:
            if state.get("hold") is None or state["hold"].get("reason") != HOLD_ALL_DONE:
                _set_hold(state, HOLD_ALL_DONE,
                          f"all {total} tracker lines are ticked; waiting for a new design document",
                          now)
                save_state(state_dir, state)
            log_event(state_dir, "done", total=total)
            return {**report, "verdict": DONE, "hold": state["hold"]}

        if state.get("hold"):
            log_event(state_dir, "skipped_hold", reason=state["hold"].get("reason"))
            return {**report, "verdict": HOLD, "hold": state["hold"]}

        if state.get("current"):
            aborted = _abort_current(state, now, "the next tick arrived before this run closed")
            hold = _set_hold(
                state, HOLD_PREV_RUN,
                f"run {aborted['run_id']} (mode {aborted['mode']}, {aborted['type_key']}) was "
                f"still open after {aborted['elapsed']}; it was marked aborted and the job "
                "parked. Review the working tree, then resume.",
                now,
            )
            save_state(state_dir, state)
            log_event(state_dir, "stuck_hold", aborted=aborted)
            return {**report, "verdict": STUCK_HOLD, "aborted": aborted, "hold": hold}

        window = runs_in_window(state, now)
        if len(window) >= MAX_RUNS_PER_WINDOW:
            log_event(state_dir, "skipped_cap", runs=len(window))
            return {**report, "verdict": SKIP_CAP}

        entry = pending[0]
        run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{entry.number:02d}-{entry.type_key}"
        current = {
            "run_id": run_id,
            "mode": entry.number,
            "type_key": entry.type_key,
            "file": entry.file,
            "class_name": entry.class_name,
            "started_at": _iso(now),
            "deadline": _iso(now + RUN_SLOT),
            "pids": [],
        }
        brief = render_brief(brief_template, entry=entry, run_id=run_id, doc=doc,
                             total=total, remaining=len(pending), now=now)
        brief_path = state_dir / "logs" / f"run-{run_id}.md"
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(brief_path, brief)
        state["current"] = current
        save_state(state_dir, state)
        log_event(state_dir, "started", run_id=run_id, mode=entry.number,
                  type_key=entry.type_key, remaining=len(pending))
        return {**report, "verdict": PROCEED, "run": current, "entry": entry,
                "remaining": len(pending), "brief": brief, "brief_path": brief_path}


def finish(*, state_dir: Path | str = DEFAULT_STATE_DIR, doc: Path = DEFAULT_DOC,
           run_id: str, mode: int, now: datetime | None = None,
           commit: str | None = None) -> dict:
    """
    Close the current run and tick its line. This is the only path that writes §9, and it
    only writes the line belonging to the run that is current right now.
    """
    now = _utc(now)
    doc = Path(doc)
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        current = state.get("current")
        if not current:
            raise JobError(
                "no run is in progress, so there is nothing to finish. If the box is already "
                "ticked the run was closed; if it is not, the run was aborted — start again."
            )
        if current.get("run_id") != str(run_id):
            raise JobError(
                f"run {run_id} is not the current run (current: {current.get('run_id')}). "
                "A later tick superseded it; it must not tick a box now."
            )
        _, entries = _read_doc(doc)
        validate_tracker(entries, doc)
        entry = next((item for item in entries if item.number == int(mode)), None)
        if entry is None:
            raise JobError(f"{_rel(doc)}: no tracker line numbered {mode}")
        if entry.number != int(current.get("mode", 0)):
            raise JobError(
                f"the open run is mode {current.get('mode')} ({current.get('type_key')}), "
                f"not mode {mode} — refusing to tick the wrong line"
            )
        if entry.type_key != current.get("type_key"):
            raise JobError(
                f"the open run is `{current.get('type_key')}` but line {mode} is "
                f"`{entry.type_key}` — the document changed under the run"
            )

        ticked = apply_tick(doc, entry.number, when=now)
        started = _parse_iso(current.get("started_at", ""))
        elapsed = _utc(now) - started
        state["runs"].append(
            {
                "run_id": current.get("run_id"),
                "mode": entry.number,
                "type_key": entry.type_key,
                "started_at": current.get("started_at"),
                "ended_at": _iso(now),
                "outcome": "done",
                "elapsed_seconds": int(elapsed.total_seconds()),
                "commit": commit or "",
            }
        )
        state["failures"].pop(entry.type_key, None)
        state["current"] = None

        remaining = pending_entries(load_tracker(doc))
        if not remaining:
            _set_hold(state, HOLD_ALL_DONE,
                      f"all {len(entries)} tracker lines are ticked; waiting for a new design "
                      "document", now)
        save_state(state_dir, state)
        log_event(state_dir, "finished", run_id=current.get("run_id"), mode=entry.number,
                  type_key=entry.type_key, ticked=ticked["changed"],
                  elapsed_seconds=int(elapsed.total_seconds()))
        return {
            "verdict": "FINISHED",
            "run_id": current.get("run_id"),
            "mode": entry.number,
            "type_key": entry.type_key,
            "ticked": ticked["changed"],
            "line": ticked["line"],
            "elapsed": _human_delta(elapsed),
            "overran_slot": elapsed > RUN_SLOT,
            "done": len(entries) - len(remaining),
            "total": len(entries),
            "next": remaining[0] if remaining else None,
            "hold": state.get("hold"),
            "runs_in_window": len(runs_in_window(state, now)),
        }


def fail(*, state_dir: Path | str = DEFAULT_STATE_DIR, doc: Path = DEFAULT_DOC,
         run_id: str, reason: str, now: datetime | None = None) -> dict:
    """
    Close the current run without ticking. The mode is retried next tick unless it has now
    failed MAX_FAILURES times, in which case the job holds for a human instead of burning
    runs on the same wall.
    """
    now = _utc(now)
    reason = (reason or "").strip()
    if not reason:
        raise JobError("a failure needs a reason (`--reason`), because it is the review note")
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        current = state.get("current")
        if not current:
            raise JobError("no run is in progress, so there is nothing to fail")
        if current.get("run_id") != str(run_id):
            raise JobError(
                f"run {run_id} is not the current run (current: {current.get('run_id')})"
            )
        entry = next((item for item in load_tracker(Path(doc))
                      if item.number == int(current.get("mode", 0))), None)
        type_key = (entry.type_key if entry else current.get("type_key")) or "unknown"
        started = _parse_iso(current.get("started_at", ""))
        elapsed = _utc(now) - started
        state["runs"].append(
            {
                "run_id": current.get("run_id"),
                "mode": current.get("mode"),
                "type_key": type_key,
                "started_at": current.get("started_at"),
                "ended_at": _iso(now),
                "outcome": "failed",
                "elapsed_seconds": int(elapsed.total_seconds()),
                "reason": reason,
            }
        )
        record = state["failures"].setdefault(type_key, {"count": 0, "reasons": []})
        record["count"] = int(record.get("count", 0)) + 1
        record["last_at"] = _iso(now)
        record["reasons"] = (record.get("reasons") or [])[-4:] + [reason]
        state["current"] = None
        hold = None
        if record["count"] >= MAX_FAILURES:
            hold = _set_hold(
                state, HOLD_REPEATED_FAILURE,
                f"mode {current.get('mode')} (`{type_key}`) failed {record['count']} times; "
                f"last reason: {reason}", now)
        save_state(state_dir, state)
        log_event(state_dir, "failed", run_id=current.get("run_id"), type_key=type_key,
                  attempt=record["count"], reason=reason)
        retry = None
        if hold is None:
            pending = pending_entries(load_tracker(Path(doc)))
            retry = pending[0] if pending else None
        return {
            "verdict": "FAILED",
            "run_id": current.get("run_id"),
            "mode": current.get("mode"),
            "type_key": type_key,
            "attempt": record["count"],
            "max_attempts": MAX_FAILURES,
            "reason": reason,
            "elapsed": _human_delta(elapsed),
            "box_ticked": bool(entry.done) if entry else None,
            "hold": hold,
            "retry": retry,
        }


def hold(*, state_dir: Path | str = DEFAULT_STATE_DIR, reason: str, note: str = "",
         now: datetime | None = None) -> dict:
    """Park the job. An open run is aborted first — parking while work continues would
    leave the ledger lying about what is running."""
    now = _utc(now)
    if not (reason or "").strip():
        raise JobError("a hold needs a reason")
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        aborted = _abort_current(state, now, f"job held: {reason}") if state.get("current") else None
        record = _set_hold(state, reason.strip(), note.strip() or "held by hand", now)
        save_state(state_dir, state)
        log_event(state_dir, "held", reason=reason, aborted=aborted)
        return {"verdict": "HELD", "hold": record, "aborted": aborted}


def resume(*, state_dir: Path | str = DEFAULT_STATE_DIR, now: datetime | None = None) -> dict:
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        if state.get("current"):
            raise JobError(
                "a run is still open; abort it first (`abort-current`) so two runs cannot "
                "build over each other"
            )
        previous = state.get("hold")
        state["hold"] = None
        save_state(state_dir, state)
        log_event(state_dir, "resumed", previous=previous)
        return {"verdict": "RESUMED", "previous_hold": previous}


def abort_current(*, state_dir: Path | str = DEFAULT_STATE_DIR, reason: str = "aborted by hand",
                  now: datetime | None = None) -> dict:
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        report = _abort_current(state, _utc(now), reason)
        save_state(state_dir, state)
        log_event(state_dir, "aborted", **{k: report[k] for k in ("run_id", "mode")})
        return {"verdict": "ABORTED", **report}


def record_pid(*, state_dir: Path | str = DEFAULT_STATE_DIR, pid: int) -> dict:
    """Remember a child process this run started, so a later tick can stop it."""
    state_dir = Path(state_dir)
    with state_lock(state_dir):
        state = load_state(state_dir)
        current = state.get("current")
        if not current:
            raise JobError("no run is in progress")
        pids = current.setdefault("pids", [])
        if int(pid) not in pids:
            pids.append(int(pid))
        save_state(state_dir, state)
        return {"verdict": "RECORDED", "run_id": current.get("run_id"), "pids": pids}


def _adopt_foreign_run(raw: dict, entries: list[TrackerEntry], now: datetime) -> dict | None:
    """
    Translate one entry from another orchestrator's ledger into this job's schema.

    The duplicate job on this machine (a hermes `slow-wireframe` cron job) wrote
    `{num, mode, started, started_epoch, status, pid, prompt_token}`.  Only a mode
    number, a start time and whether the box is ticked matter for the budget and
    the queue — everything else is provenance.
    """
    if not isinstance(raw, dict) or raw.get("run_id") and raw.get("started_at"):
        return None                                   # already ours
    key = raw.get("mode") if isinstance(raw.get("mode"), str) else None
    number = raw.get("num")
    if not isinstance(number, int) and key is not None:
        match = next((entry for entry in entries if entry.type_key == key), None)
        number = match.number if match else None
    if not isinstance(number, int) or not 1 <= number <= len(entries):
        return None
    stamp = raw.get("started") or raw.get("started_epoch")
    if stamp is None:
        return None
    try:
        started = _parse_iso(stamp) if isinstance(stamp, str) else \
            datetime.fromtimestamp(float(stamp), tz=timezone.utc)
    except (JobError, TypeError, ValueError, OverflowError):
        return None
    entry = entries[number - 1]
    return {
        "run_id": f"{_utc(started).strftime('%Y%m%dT%H%M%SZ')}-{number:02d}-{entry.type_key}",
        "mode": number,
        "type_key": entry.type_key,
        "started_at": _iso(started),
        "ended_at": _iso(now),
        "outcome": "done" if entry.done else "failed",
        "adopted": True,
        "reason": f"imported from the duplicate hermes job ({raw.get('prompt_token') or 'run'})",
    }


def reconcile(*, state_dir: Path | str = DEFAULT_STATE_DIR, doc: Path = DEFAULT_DOC,
              now: datetime | None = None, dry_run: bool = False,
              clear_hold: bool = False) -> dict:
    """
    Take the ledger back from the duplicate orchestrator without losing history.

    The document is the queue, so the boxes decide what an imported run achieved:
    a ticked line means the run finished, an unticked one means it failed and the
    mode is retried.  Imported runs keep counting against the 24-hour budget —
    they cost real money.  Nothing is deleted: this job's own runs stay, and the
    foreign `current` marker is closed so `start` can decide again.
    """
    now = _utc(now)
    doc = Path(doc)
    state_dir = Path(state_dir)
    _, entries = _read_doc(doc)
    validate_tracker(entries, doc)
    with state_lock(state_dir):
        state = load_state(state_dir)
        held = state.get("hold")
        if held and not clear_hold:
            return {"verdict": "REFUSED", "reason": "the ledger is on hold",
                    "hold": held,
                    "hint": "reconcile --clear-hold, after the hold has been reviewed"}
        runs = [run for run in state.get("runs", [])
                if isinstance(run.get("started_at"), str) and run.get("started_at")]
        imported = []
        seen = {(run.get("mode"), run.get("started_at")) for run in runs}
        for raw in list(state.get("runs", [])) + ([state["current"]] if state.get("current") else []):
            adopted = _adopt_foreign_run(raw, entries, now)
            if adopted is None:
                continue
            if (adopted["mode"], adopted["started_at"]) in seen:
                continue
            seen.add((adopted["mode"], adopted["started_at"]))
            runs.append(adopted)
            imported.append(adopted)
        runs.sort(key=lambda run: run.get("started_at", ""))
        failures = {key: value for key, value in (state.get("failures") or {}).items()
                    if isinstance(value, dict) and isinstance(value.get("count"), int)}
        for adopted in imported:
            if adopted["outcome"] == "failed":
                record = failures.setdefault(adopted["type_key"], {"count": 0, "reasons": []})
                record["count"] = int(record.get("count", 0)) + 1
                record["last_at"] = _iso(now)
                record["reasons"] = (record.get("reasons") or [])[-3:] + [adopted["reason"]]
        pending = pending_entries(entries)
        rebuilt = {
            "version": 1,
            "design": _rel(doc),
            "hold": None,
            "current": None,
            "runs": runs[-MAX_RUN_HISTORY:],
            "failures": failures,
        }
        if not pending:
            _set_hold(rebuilt, HOLD_ALL_DONE,
                      f"all {len(entries)} tracker lines are ticked; waiting for a new design "
                      "document", now)
        report = {
            "verdict": "RECONCILED",
            "imported": imported,
            "kept": len(runs) - len(imported),
            "closed_current": bool(state.get("current")),
            "cleared_hold": held is not None,
            "next": pending[0] if pending else None,
            "done": len(entries) - len(pending),
            "total": len(entries),
            "runs_in_window": len(runs_in_window(rebuilt, now)),
            "hold": rebuilt["hold"],
            "dry_run": dry_run,
        }
        if dry_run:
            return report
        save_state(state_dir, state=rebuilt)
        log_event(state_dir, "reconciled", imported=len(imported), kept=report["kept"],
                  next_mode=report["next"].number if report["next"] else None)
        return report


# --------------------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------------------

def status(*, state_dir: Path | str = DEFAULT_STATE_DIR, doc: Path = DEFAULT_DOC,
           now: datetime | None = None) -> str:
    now = _utc(now)
    doc = Path(doc)
    entries = load_tracker(doc)
    validate_tracker(entries, doc)
    state = load_state(state_dir)
    pending = pending_entries(entries)
    done = len(entries) - len(pending)
    window = runs_in_window(state, now)
    lines = [
        f"Slow Wireframe job — {now.astimezone():%Y-%m-%d %H:%M} local ({_iso(now)})",
        f"  doc        {_rel(doc)} — {done} of {len(entries)} modes ticked",
        f"  state      {_rel(state_path(state_dir))}",
    ]
    if state.get("hold"):
        held = state["hold"]
        lines.append(f"  hold       {held.get('reason')} since {held.get('at')} — {held.get('note')}")
    else:
        lines.append("  hold       none")
    current = state.get("current")
    if current:
        elapsed = now - _parse_iso(current.get("started_at", ""))
        state_word = "OVERRAN ITS SLOT" if elapsed > RUN_SLOT else "inside its slot"
        lines.append(
            f"  running    {current.get('run_id')} — mode {current.get('mode')} "
            f"({current.get('type_key')}), {_human_delta(elapsed)} in, {state_word}"
        )
    else:
        lines.append("  running    nothing")
    lines.append(
        f"  budget     {len(window)} of {MAX_RUNS_PER_WINDOW} runs in the last 24 hours"
        + (f"; next slot {_iso(next_slot_at(state, now))}" if len(window) >= MAX_RUNS_PER_WINDOW else "")
    )
    if pending:
        nxt = pending[0]
        lines.append(f"  next mode  {nxt.number} · `{nxt.type_key}` · {nxt.title} → {nxt.file}")
    else:
        lines.append("  next mode  none — all twenty are ticked")
    if state.get("failures"):
        for key, record in sorted(state["failures"].items()):
            reason = (record.get("reasons") or ["—"])[-1]
            lines.append(f"  failures   {key} × {record.get('count')} (last: {reason})")
    else:
        lines.append("  failures   none")
    recent = sorted(state.get("runs", []), key=lambda run: run.get("started_at", ""))[-3:]
    for run in recent:
        lines.append(
            f"  run        {run.get('run_id')} — mode {run.get('mode')} {run.get('outcome')}"
            f" {run.get('started_at')} → {run.get('ended_at')}"
            + (f" ({run.get('reason')})" if run.get("reason") else "")
        )
    if not recent:
        lines.append("  runs       none yet")
    return "\n".join(lines)


SCHEDULE_PROMPT = """\
Slow Wireframe scheduled run (every 3 hours).

This arrives on a timer. Nobody is asking you a question: you either drive one run of the
unattended build job or you stop it. Work in /mnt/ssd/projects/pixel_dreams.

STEP 1 — ask the ledger what to do:
    cd /mnt/ssd/projects/pixel_dreams && .venv/bin/python scripts/slow_wireframe_job.py start
It prints one `VERDICT: <name>` line and, when it proceeds, the full builder brief.

STEP 2 — obey that verdict, and nothing else:
  PROCEED      Build exactly the one mode the brief names, following it literally. When the
               still, the validator and the tests pass, close the run with
                   .venv/bin/python scripts/slow_wireframe_job.py finish --run-id <ID> --mode <N>
               If you cannot finish it, close it with
                   .venv/bin/python scripts/slow_wireframe_job.py fail --run-id <ID> --reason "<one sentence>"
               Never tick a box in the design document by hand: `finish` is the only thing
               that ticks it. Never `git add -A`. Never touch a mode other than the one named.
  SKIP_CAP     The five-runs-per-24-hours budget is spent. Reply with one line saying so and
               do nothing else: no build, no tick, no state change.
  STUCK_HOLD   A previous run never closed. The ledger has already marked it aborted, killed
               the PIDs it had recorded and put the job on hold. Call `job_list` and
               `job_kill` anything a previous run left running, then delete this schedule
               (`schedule_list`, then `schedule_delete` on the one titled
               "Slow Wireframe mode builds") and report the hold reason. Build nothing.
  HOLD         The job is parked. Build nothing. Delete this schedule as above and report the
               reason plus how to re-arm.
  DONE         All twenty modes are ticked. Delete this schedule as above and report it.
  Any other verdict, a traceback, or a non-zero exit: stop, build nothing, report it.

STEP 3 — rules for this turn:
  - The run budget is 2.5 hours of wall clock; check `date` at the start. Past that, `fail`
    the run instead of continuing — a runaway run costs real money.
  - Do not create a schedule, do not edit this prompt, do not delete runtime/slow_wireframe/.
  - Do not run `start` twice in one turn.
  - When the verdict is SKIP_CAP, HOLD, STUCK_HOLD or DONE, end with a 2–3 line report: the
    verdict, what you did about the schedule, and what a human should do next."""


def rearm() -> str:
    return "\n".join([
        f"schedule title : {SCHEDULE_TITLE}",
        f"interval       : every {SCHEDULE_INTERVAL_SECONDS // 3600} hours "
        f"({SCHEDULE_INTERVAL_SECONDS} seconds)",
        f"working dir    : {ROOT}",
        "create it      : in the agent harness (schedule_create) with the prompt below — the",
        "                 job never creates a schedule itself, so a parked job cannot wake up",
        "",
        SCHEDULE_PROMPT,
    ])


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _print_start(report: dict) -> None:
    verdict = report["verdict"]
    print(f"Slow Wireframe job — start {report['now']}")
    print(f"  doc        {report['done']} of {report['total']} modes ticked")
    print(f"  budget     {report['runs_in_window']} of {MAX_RUNS_PER_WINDOW} runs in the last 24 hours")
    print(f"VERDICT: {verdict}")
    if verdict == PROCEED:
        run, entry = report["run"], report["entry"]
        print(f"  run        {run['run_id']}")
        print(f"  build      mode {entry.number} · `{entry.type_key}` · {entry.title} → {entry.file}")
        print(f"  remaining  {report['remaining']} modes unchecked after this one")
        print(f"  brief      {_rel(report['brief_path'])}")
        print()
        print("--- begin brief ---")
        print(report["brief"].rstrip())
        print("--- end brief ---")
    elif verdict == SKIP_CAP:
        print(f"  five runs already started in the last 24 hours; next slot {report['next_slot_at']}")
        print("  nothing was started and nothing was changed.")
    elif verdict == HOLD:
        held = report["hold"]
        print(f"  hold reason  {held.get('reason')}")
        print(f"  held since   {held.get('at')}")
        print(f"  note         {held.get('note')}")
        print("  nothing was started. `resume` clears the hold after a human has looked.")
    elif verdict == STUCK_HOLD:
        aborted = report["aborted"]
        print(f"  stopped      run {aborted['run_id']} (mode {aborted['mode']}, "
              f"{aborted['type_key']}) after {aborted['elapsed']}")
        print(f"  killed       {aborted['killed'] or 'no recorded PIDs were alive'}")
        print(f"  hold reason  {report['hold'].get('reason')}")
        print("  nothing new was started. Review the working tree, then `resume`.")
    elif verdict == DONE:
        print(f"  all {report['total']} modes are ticked; the job parked itself.")
        print("  write the next design document, then `resume` and re-arm the schedule.")


def _print_finish(report: dict) -> None:
    print(f"  run        {report['run_id']} ({report['elapsed']})")
    print(f"  ticked     {'yes' if report['ticked'] else 'the line was already ticked'}")
    print(f"  line       {report['line']}")
    print(f"  progress   {report['done']} of {report['total']} modes")
    if report["next"]:
        nxt = report["next"]
        print(f"  next mode  {nxt.number} · `{nxt.type_key}` · {nxt.title}")
    if report["overran_slot"]:
        print(f"  WARNING    the run took longer than the {RUN_SLOT.seconds // 3600}-hour slot; "
              "the next tick would have stopped it")
    if report.get("hold"):
        print(f"  hold       {report['hold'].get('reason')} — delete the schedule and report it")
    else:
        print(f"  budget     {report['runs_in_window']} of {MAX_RUNS_PER_WINDOW} runs in the last 24 hours")


def _print_fail(report: dict) -> None:
    print(f"  run        {report['run_id']} ({report['elapsed']}) — failed, box not ticked")
    print(f"  reason     {report['reason']}")
    print(f"  attempt    {report['attempt']} of {report['max_attempts']} for `{report['type_key']}`")
    if report.get("hold"):
        print(f"  hold       {report['hold'].get('reason')}")
        print(f"             {report['hold'].get('note')}")
        print("  the job is parked: review, then `resume`. Delete the schedule and report it.")
    elif report.get("retry"):
        nxt = report["retry"]
        print(f"  next       the next tick retries {nxt.number} · `{nxt.type_key}` · {nxt.title}")


def _print_reconcile(report: dict) -> None:
    if report["verdict"] == "REFUSED":
        held = report.get("hold") or {}
        print(f"REFUSED: {report['reason']} — {held.get('reason')}: {held.get('note')}")
        print(f"  {report['hint']}")
        return
    suffix = " (dry run, nothing written)" if report["dry_run"] else ""
    print(f"VERDICT: RECONCILED{suffix}")
    for run in report["imported"]:
        print(f"  imported   mode {run['mode']:02d} {run['outcome']:6s} {run['started_at']} → "
              f"{run['ended_at']}  `{run['type_key']}`")
    if not report["imported"]:
        print("  imported   nothing (the ledger was already this job's)")
    print(f"  kept       {report['kept']} run(s) already in this ledger")
    print(f"  progress   {report['done']} of {report['total']} modes")
    if report["next"]:
        nxt = report["next"]
        print(f"  next mode  {nxt.number} · `{nxt.type_key}` · {nxt.title}")
    print(f"  budget     {report['runs_in_window']} of {MAX_RUNS_PER_WINDOW} runs in the last 24 hours")
    if report.get("hold"):
        print(f"  hold       {report['hold'].get('reason')} — the queue is complete")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slow_wireframe_job.py",
        description="The ledger for the unattended Slow Wireframe build job.",
        epilog="Every command exits 0 for a normal verdict (including HOLD and SKIP_CAP), "
               "and 2 for a refusal.",
    )
    parser.add_argument("--state-dir", type=Path,
                        default=Path(os.environ.get("SLOW_WIREFRAME_STATE_DIR") or DEFAULT_STATE_DIR))
    parser.add_argument("--doc", type=Path,
                        default=Path(os.environ.get("SLOW_WIREFRAME_DOC") or DEFAULT_DOC))
    parser.add_argument("--now", default=os.environ.get("SLOW_WIREFRAME_NOW"),
                        help="ISO timestamp to treat as now (testing and replays)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="decide this tick: PROCEED, SKIP_CAP, HOLD, DONE or STUCK_HOLD")
    sub.add_parser("status", help="the ledger, in plain text")
    sub.add_parser("rearm", help="the schedule spec and the prompt to re-create it with")

    finish = sub.add_parser("finish", help="close the current run and tick its line")
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--mode", required=True, type=int)
    finish.add_argument("--commit", default=None)

    fail = sub.add_parser("fail", help="close the current run without ticking")
    fail.add_argument("--run-id", required=True)
    fail.add_argument("--reason", required=True)

    hold_cmd = sub.add_parser("hold", help="park the job (aborts an open run first)")
    hold_cmd.add_argument("--reason", required=True)
    hold_cmd.add_argument("--note", default="")

    sub.add_parser("resume", help="clear a hold after a human has reviewed")

    abort = sub.add_parser("abort-current", help="stop an open run without starting another")
    abort.add_argument("--reason", default="aborted by hand")

    pid = sub.add_parser("pid", help="record a child process so a later tick can stop it")
    pid.add_argument("--pid", type=int, required=True)

    rec = sub.add_parser(
        "reconcile", help="take the ledger back from the duplicate hermes job")
    rec.add_argument("--dry-run", action="store_true", help="print, change nothing")
    rec.add_argument("--clear-hold", action="store_true",
                     help="clear a hold too (only after a human has reviewed it)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        now = _parse_iso(args.now) if args.now else None
        if args.command == "start":
            report = start(state_dir=args.state_dir, doc=args.doc, now=now)
            _print_start(report)
        elif args.command == "status":
            print(status(state_dir=args.state_dir, doc=args.doc, now=now))
        elif args.command == "rearm":
            print(rearm())
        elif args.command == "finish":
            report = finish(state_dir=args.state_dir, doc=args.doc, run_id=args.run_id,
                            mode=args.mode, now=now, commit=args.commit)
            _print_finish(report)
        elif args.command == "fail":
            report = fail(state_dir=args.state_dir, doc=args.doc, run_id=args.run_id,
                          reason=args.reason, now=now)
            _print_fail(report)
        elif args.command == "hold":
            report = hold(state_dir=args.state_dir, reason=args.reason, note=args.note, now=now)
            print(f"VERDICT: {report['verdict']}")
            print(f"  hold       {report['hold'].get('reason')} — {report['hold'].get('note')}")
            if report.get("aborted"):
                print(f"  aborted    {report['aborted']['run_id']} (mode {report['aborted']['mode']})")
        elif args.command == "resume":
            report = resume(state_dir=args.state_dir, now=now)
            print(f"VERDICT: {report['verdict']}")
            if report.get("previous_hold"):
                print(f"  cleared    {report['previous_hold'].get('reason')}")
            print("  the job will proceed on the next tick.")
        elif args.command == "abort-current":
            report = abort_current(state_dir=args.state_dir, reason=args.reason, now=now)
            print(f"VERDICT: {report['verdict']}")
            print(f"  stopped    {report['run_id']} (mode {report['mode']}, {report['type_key']}) "
                  f"after {report['elapsed']}")
            print(f"  killed     {report['killed'] or 'no recorded PIDs were alive'}")
        elif args.command == "pid":
            report = record_pid(state_dir=args.state_dir, pid=args.pid)
            print(f"VERDICT: {report['verdict']}")
            print(f"  pids       {report['pids']}")
        elif args.command == "reconcile":
            report = reconcile(state_dir=args.state_dir, doc=args.doc, now=now,
                               dry_run=args.dry_run, clear_hold=args.clear_hold)
            _print_reconcile(report)
            if report["verdict"] == "REFUSED":
                return 2
        return 0
    except JobError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
