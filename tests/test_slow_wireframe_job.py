# tests/test_slow_wireframe_job.py
#
# scripts/slow_wireframe_job.py decides whether the unattended Slow Wireframe job may
# build a mode, and it runs while nobody is watching, so the guarantees it makes are
# tested here rather than trusted:
#
#   * §9 of the design document parses into the twenty modes, in order, and a tick
#     rewrites exactly one line — the mark and a ` — done YYYY-MM-DD` suffix — and
#     nothing else;
#   * the five-runs-in-24-hours ceiling skips rather than builds, and a run that ages
#     out of the window frees the next slot;
#   * a run left open is stopped by the next tick: marked aborted, its recorded PIDs
#     signalled, a hold set, and nothing new started;
#   * a hold parks the job, a completed queue parks itself, `resume` reopens only a job
#     with no run in flight, and a hold aborts an open run rather than lying about it;
#   * only the current run can tick a box, and only its own line;
#   * a mode that fails three times parks the job instead of burning more runs on it;
#   * the brief renders for every mode with every token filled in.
#
# Everything runs against a copy of the document and a temporary state directory; the
# real runtime/slow_wireframe/ is never touched. All headless — no display required.

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "slow_wireframe_job.py"
TEMPLATE = BASE_DIR / "scripts" / "slow_wireframe_brief.md"
DOC = BASE_DIR / "designs" / "SLOW_WIREFRAME_DESIGN.MD"

#: A fixed, weekday-afternoon UTC instant: the tick's done-suffix date derives from
#: local time, and every assertion below is computed the same way.
NOW = datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc)


def load_job():
    spec = importlib.util.spec_from_file_location("slow_wireframe_job", SCRIPT)
    assert spec is not None and spec.loader is not None, "cannot load the job script"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module      # dataclasses look the module up while defining
    spec.loader.exec_module(module)
    return module


job = load_job()


@dataclass
class Env:
    doc: Path
    state_dir: Path
    now: datetime = NOW

    @property
    def state(self) -> dict:
        return job.load_state(self.state_dir)

    def lines(self) -> list[str]:
        return self.doc.read_text(encoding="utf-8").split("\n")

    def ticked_numbers(self) -> list[int]:
        return [entry.number for entry in job.load_tracker(self.doc) if entry.done]


def _unticked_copy(src: Path, dst: Path) -> None:
    """A fresh queue from the live document: every box reopened, every suffix gone."""
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"^- \[x\] (\d+ · .*?) — done \d{4}-\d{2}-\d{2}$", r"- [ ] \1", text,
                  flags=re.MULTILINE)
    dst.write_text(text, encoding="utf-8")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    doc = tmp_path / "SLOW_WIREFRAME_DESIGN.MD"
    _unticked_copy(DOC, doc)
    return Env(doc=doc, state_dir=tmp_path / "runtime" / "slow_wireframe")


def open_run(env: Env, at: datetime | None = None) -> dict:
    report = job.start(state_dir=env.state_dir, doc=env.doc, now=at or env.now)
    assert report["verdict"] == job.PROCEED, report
    return report


def close_run(env: Env, report: dict, at: datetime | None = None) -> dict:
    return job.finish(state_dir=env.state_dir, doc=env.doc,
                      run_id=report["run"]["run_id"], mode=report["entry"].number,
                      now=at or env.now)


def seed_runs(env: Env, hours_ago: list[float], outcome: str = "done") -> None:
    """A ledger with history at known offsets, for the 24-hour window tests."""
    runs = [
        {
            "run_id": f"seed-{index:02d}",
            "mode": index,
            "type_key": "seeded",
            "started_at": job._iso(NOW - timedelta(hours=hours)),
            "ended_at": job._iso(NOW - timedelta(hours=hours) + timedelta(hours=1)),
            "outcome": outcome,
        }
        for index, hours in enumerate(hours_ago, start=1)
    ]
    state = job.default_state()
    state["runs"] = runs
    env.state_dir.mkdir(parents=True, exist_ok=True)
    (env.state_dir / "state.json").write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------------------
# the document is the queue
# --------------------------------------------------------------------------------------

def test_tracker_parses_the_twenty_modes_in_order(env):
    entries = job.load_tracker(env.doc)
    job.validate_tracker(entries, env.doc)

    assert [entry.number for entry in entries] == list(range(1, 21))
    assert entries[0].type_key == "dysonswarm"
    assert entries[0].title == "Dyson Swarm"
    assert entries[0].file == "modes/dyson_swarm_mode.py"
    assert entries[0].class_name == "DysonSwarmMode"
    assert entries[0].camera == "survey"
    assert entries[0].wave == "wave 1"
    assert entries[-1].type_key == "artifactscan"
    assert len({entry.file for entry in entries}) == 20
    assert not [entry for entry in entries if entry.done]


def test_a_tick_rewrites_one_line_and_appends_the_done_suffix(env):
    before = env.lines()
    report = job.apply_tick(env.doc, 3, when=NOW)
    after = env.lines()

    assert report["changed"] is True
    assert len(after) == len(before), "a tick must not add or remove document lines"
    changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
    assert len(changed) == 1, "a tick must touch exactly one line"

    line = after[changed[0]]
    assert line.startswith("- [x] 3 · `orbitalmirrorarray`")
    stamp = NOW.astimezone().strftime("%Y-%m-%d")
    assert line.endswith(f"— done {stamp}")
    # The rest of the line is preserved character for character.
    assert line.replace("[x]", "[ ]").removesuffix(f" — done {stamp}") == before[changed[0]]


def test_a_tick_is_idempotent(env):
    job.apply_tick(env.doc, 7, when=NOW)
    once = env.doc.read_bytes()
    again = job.apply_tick(env.doc, 7, when=NOW)
    assert again["changed"] is False
    assert env.doc.read_bytes() == once


def test_a_reformatted_tracker_is_refused_not_guessed(env):
    text = env.doc.read_text(encoding="utf-8").replace(
        "- [ ] 4 · `planetcracker` · Planet Cracker · orbit · L · wave 3",
        "- [ ] 4 planetcracker Planet Cracker orbit L wave 3",
        1,
    )
    env.doc.write_text(text, encoding="utf-8")
    with pytest.raises(job.JobError):
        job.validate_tracker(job.load_tracker(env.doc), env.doc)
    with pytest.raises(job.JobError):
        job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)


# --------------------------------------------------------------------------------------
# start: the happy path
# --------------------------------------------------------------------------------------

def test_start_opens_the_lowest_unchecked_mode_with_its_brief(env):
    report = open_run(env)

    assert report["entry"].number == 1
    assert report["run"]["run_id"].endswith("-01-dysonswarm")
    assert report["remaining"] == 20
    assert report["done"] == 0 and report["total"] == 20

    brief = report["brief"]
    assert "{{" not in brief and "}}" not in brief
    assert "Dyson Swarm" in brief
    assert "modes/dyson_swarm_mode.py" in brief
    assert "modes.dyson_swarm_mode:DysonSwarmMode" in brief
    assert "tests/test_dyson_swarm.py" in brief
    assert "scripts/dyson_swarm_preview.py" in brief
    assert report["run"]["run_id"] in brief
    assert "--mode 1" in brief
    assert report["brief_path"].exists()
    assert report["brief_path"].read_text(encoding="utf-8") == brief

    state = env.state
    assert state["current"]["run_id"] == report["run"]["run_id"]
    assert state["current"]["mode"] == 1


def test_finish_ticks_only_its_own_line_and_advances_the_queue(env):
    report = open_run(env)
    completed = close_run(env, report)

    assert completed["ticked"] is True
    assert completed["done"] == 1 and completed["total"] == 20
    assert completed["next"].number == 2
    assert completed["hold"] is None
    assert env.ticked_numbers() == [1]
    assert sum(1 for line in env.lines() if line.startswith("- [x]")) == 1

    state = env.state
    assert state["current"] is None
    assert state["runs"][-1]["outcome"] == "done"
    assert state["runs"][-1]["mode"] == 1

    second = open_run(env)
    assert second["entry"].number == 2
    assert second["remaining"] == 19


# --------------------------------------------------------------------------------------
# a run that never closed
# --------------------------------------------------------------------------------------

def test_an_open_run_is_stopped_by_the_next_tick_and_the_job_holds(env):
    first = open_run(env)
    killed = None
    if os.name == "posix":
        child = subprocess.Popen(["sleep", "60"])
        job.record_pid(state_dir=env.state_dir, pid=child.pid)
        killed = child

    try:
        second = job.start(state_dir=env.state_dir, doc=env.doc,
                           now=NOW + timedelta(minutes=10))
    finally:
        if killed is not None and killed.poll() is None:
            killed.kill()
            killed.wait(timeout=5)

    assert second["verdict"] == job.STUCK_HOLD
    assert second["aborted"]["run_id"] == first["run"]["run_id"]
    assert second["aborted"]["mode"] == 1
    assert second["hold"]["reason"] == job.HOLD_PREV_RUN
    if killed is not None:
        assert second["aborted"]["killed"] == [killed.pid], "a recorded PID must be stopped"

    state = env.state
    assert state["current"] is None, "the abandoned run must be released"
    assert state["runs"][-1]["outcome"] == "aborted"
    assert state["runs"][-1]["run_id"] == first["run"]["run_id"]
    assert env.ticked_numbers() == [], "an aborted run never ticks a box"

    # And the hold stands until a human looks.
    third = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW + timedelta(hours=1))
    assert third["verdict"] == job.HOLD


def test_a_superseded_run_cannot_tick_a_box(env):
    first = open_run(env)
    job.start(state_dir=env.state_dir, doc=env.doc, now=NOW + timedelta(minutes=5))

    with pytest.raises(job.JobError):
        close_run(env, first)
    assert env.ticked_numbers() == []


def test_finish_refuses_a_mode_that_is_not_the_open_run(env):
    report = open_run(env)
    before = env.doc.read_bytes()

    with pytest.raises(job.JobError):
        job.finish(state_dir=env.state_dir, doc=env.doc,
                   run_id=report["run"]["run_id"], mode=2, now=NOW)

    assert env.doc.read_bytes() == before, "a refused finish must not touch the document"
    assert env.state["current"]["run_id"] == report["run"]["run_id"]

    close_run(env, report)                      # still closable, still correct
    assert env.ticked_numbers() == [1]


def test_a_double_finish_is_refused(env):
    report = open_run(env)
    close_run(env, report)
    with pytest.raises(job.JobError):
        close_run(env, report)


# --------------------------------------------------------------------------------------
# the 5-per-24-hours ceiling
# --------------------------------------------------------------------------------------

def test_five_runs_in_a_day_skip_and_touch_nothing(env):
    seed_runs(env, [1, 4, 7, 10, 13])
    before = env.doc.read_bytes()

    report = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)

    assert report["verdict"] == job.SKIP_CAP
    assert report["runs_in_window"] == 5
    assert report["next_slot_at"] == job._iso(NOW - timedelta(hours=13) + job.RUN_WINDOW)
    assert env.state["current"] is None, "a skip must not open a run"
    assert env.doc.read_bytes() == before


def test_a_run_that_ages_out_of_the_window_frees_a_slot(env):
    seed_runs(env, [25, 4, 7, 10, 13])          # one is outside the 24 hours
    report = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert report["verdict"] == job.PROCEED
    assert report["runs_in_window"] == 4


def test_a_run_that_started_exactly_24h_ago_has_left_the_window(env):
    """The boundary is exclusive on purpose: the daily wave restarts on its own 3-hour
    slot, so the day is five runs and the twenty modes take four days, not five."""
    seed_runs(env, [24.0, 21, 18, 15, 12])
    report = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert report["verdict"] == job.PROCEED
    assert report["runs_in_window"] == 4


def test_aborted_and_failed_runs_count_against_the_budget(env):
    seed_runs(env, [1, 2, 3, 4, 5], outcome="aborted")
    assert job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)["verdict"] == job.SKIP_CAP


def test_twenty_modes_take_four_days_at_five_a_day(env):
    """The whole point of the ceiling, played out on the real 3-hour cadence: every tick
    either builds the next mode or is skipped, five runs land in each day, and the twenty
    boxes are ticked inside four days."""
    cursor = NOW
    opened: list[datetime] = []
    for _ in range(40):                         # 40 slots = five days of 3-hour ticks
        if len(env.ticked_numbers()) == 20:
            break
        report = job.start(state_dir=env.state_dir, doc=env.doc, now=cursor)
        if report["verdict"] == job.PROCEED:
            opened.append(cursor)
            job.finish(state_dir=env.state_dir, doc=env.doc,
                       run_id=report["run"]["run_id"], mode=report["entry"].number,
                       now=cursor + timedelta(minutes=50))
        else:
            assert report["verdict"] == job.SKIP_CAP, report["verdict"]
        cursor += timedelta(hours=3)

    assert env.ticked_numbers() == list(range(1, 21))
    assert len(opened) == 20
    assert cursor <= NOW + timedelta(days=4), f"twenty modes took {cursor - NOW}"
    for moment in opened:                       # never six runs in any rolling 24 hours
        in_window = [t for t in opened if moment - timedelta(hours=24) < t <= moment]
        assert len(in_window) <= 5
    assert sum(1 for t in opened if t < NOW + timedelta(days=1)) == 5


# --------------------------------------------------------------------------------------
# holds
# --------------------------------------------------------------------------------------

def test_a_hold_parks_the_job_and_resume_reopens_it(env):
    job.hold(state_dir=env.state_dir, reason="review the art direction", note="human check",
             now=NOW)

    held = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert held["verdict"] == job.HOLD
    assert held["hold"]["reason"] == "review the art direction"
    assert env.state["current"] is None

    job.resume(state_dir=env.state_dir, now=NOW)
    assert job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)["verdict"] == job.PROCEED


def test_a_hold_aborts_the_open_run(env):
    report = open_run(env)
    job.hold(state_dir=env.state_dir, reason="stop", now=NOW)

    state = env.state
    assert state["current"] is None
    assert state["runs"][-1]["outcome"] == "aborted"
    assert state["runs"][-1]["run_id"] == report["run"]["run_id"]


def test_resume_refuses_while_a_run_is_open(env):
    open_run(env)
    with pytest.raises(job.JobError):
        job.resume(state_dir=env.state_dir, now=NOW)


def test_twenty_ticks_park_the_job_by_themselves(env):
    for number in range(1, 21):
        job.apply_tick(env.doc, number, when=NOW)

    report = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert report["verdict"] == job.DONE
    assert report["hold"]["reason"] == job.HOLD_ALL_DONE
    assert report["done"] == 20

    # Repeating the tick does not reopen anything.
    assert job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)["verdict"] == job.DONE
    assert env.state["current"] is None


def test_finishing_the_last_box_parks_the_job(env):
    for number in range(1, 20):
        job.apply_tick(env.doc, number, when=NOW)
    report = open_run(env)
    assert report["entry"].number == 20

    completed = close_run(env, report)
    assert completed["done"] == 20
    assert completed["next"] is None
    assert completed["hold"]["reason"] == job.HOLD_ALL_DONE
    assert job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)["verdict"] == job.DONE


# --------------------------------------------------------------------------------------
# failures
# --------------------------------------------------------------------------------------

def test_a_failure_is_retried_next_tick(env):
    first = open_run(env)
    report = job.fail(state_dir=env.state_dir, doc=env.doc,
                      run_id=first["run"]["run_id"], reason="the still did not read",
                      now=NOW)

    assert report["attempt"] == 1
    assert report["hold"] is None
    assert report["retry"].number == 1, "the same mode is retried, not skipped"
    assert env.ticked_numbers() == []

    again = open_run(env, at=NOW + timedelta(hours=3))
    assert again["entry"].number == 1


def test_three_failures_park_the_job_instead_of_burning_runs(env):
    for attempt in (1, 2):
        report = open_run(env, at=NOW + timedelta(hours=3 * (attempt - 1)))
        closed = job.fail(state_dir=env.state_dir, doc=env.doc,
                          run_id=report["run"]["run_id"], reason=f"attempt {attempt}",
                          now=NOW + timedelta(hours=3 * (attempt - 1)))
        assert closed["hold"] is None

    third = open_run(env, at=NOW + timedelta(hours=6))
    closed = job.fail(state_dir=env.state_dir, doc=env.doc,
                      run_id=third["run"]["run_id"], reason="attempt 3",
                      now=NOW + timedelta(hours=6))

    assert closed["hold"]["reason"] == job.HOLD_REPEATED_FAILURE
    assert "attempt 3" in closed["hold"]["note"]
    assert job.start(state_dir=env.state_dir, doc=env.doc,
                     now=NOW + timedelta(hours=9))["verdict"] == job.HOLD


def test_failing_a_superseded_run_is_refused(env):
    first = open_run(env)
    job.start(state_dir=env.state_dir, doc=env.doc, now=NOW + timedelta(minutes=5))
    with pytest.raises(job.JobError):
        job.fail(state_dir=env.state_dir, doc=env.doc,
                 run_id=first["run"]["run_id"], reason="late", now=NOW)


# --------------------------------------------------------------------------------------
# taking the ledger back from the duplicate orchestrator
# --------------------------------------------------------------------------------------

def write_foreign_ledger(env: Env, *, mode: int, type_key: str, started: str) -> None:
    """The hermes `slow-wireframe` job's shape, as found on disk after its run."""
    mine = {
        "commit": "3518293", "elapsed_seconds": 1415, "ended_at": "2026-11-01T16:40:52Z",
        "mode": 1, "outcome": "done", "run_id": "20261101T161717Z-01-dysonswarm",
        "started_at": "2026-11-01T16:17:17Z", "type_key": "dysonswarm",
    }
    foreign_run = {
        "log": "runtime/slow_wireframe/logs/run-sw.log", "mode": type_key, "num": mode,
        "pid": 123206, "started": started, "started_epoch": 1793559417.37,
        "status": "running",
    }
    state = {
        "completed": [],
        "current": {**foreign_run, "prompt": "prompt.md", "prompt_token": "sw-1",
                    "title": "Stellar Engine"},
        "design": "designs/SLOW_WIREFRAME_DESIGN.MD",
        "failures": {},
        "hold": None,
        "mode_failures": {},
        "runs": [mine, foreign_run],
        "version": 1,
    }
    env.state_dir.mkdir(parents=True, exist_ok=True)
    (env.state_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n",
                                              encoding="utf-8")
    job.apply_tick(env.doc, 1, when=NOW)          # this job's own run is done and ticked


def test_reconcile_imports_a_finished_foreign_run(env):
    write_foreign_ledger(env, mode=2, type_key="stellarengine",
                         started="2026-11-01T13:56:57-05:00")
    job.apply_tick(env.doc, 2, when=NOW)                    # the hermes worker ticked it

    report = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW)

    assert report["verdict"] == "RECONCILED"
    assert len(report["imported"]) == 1
    adopted = report["imported"][0]
    assert adopted["mode"] == 2 and adopted["type_key"] == "stellarengine"
    assert adopted["outcome"] == "done"
    assert adopted["started_at"] == "2026-11-01T18:56:57Z"   # -05:00 -> Z
    assert adopted["adopted"] is True
    assert report["kept"] == 1, "this job's own run must survive"
    assert report["next"].number == 3
    assert report["runs_in_window"] == 2, "an imported run still costs budget"

    state = env.state
    assert state["current"] is None
    assert state["hold"] is None
    assert [run["mode"] for run in state["runs"]] == [1, 2]
    assert len(state["failures"]) == 0

    started = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert started["verdict"] == job.PROCEED
    assert started["entry"].number == 3


def test_reconcile_records_an_unfinished_foreign_run_as_a_failure(env):
    write_foreign_ledger(env, mode=2, type_key="stellarengine",
                         started="2026-11-01T13:56:57-05:00")

    report = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW)

    assert report["imported"][0]["outcome"] == "failed"
    assert report["next"].number == 2, "an unticked box is retried, not skipped"
    state = env.state
    assert state["failures"]["stellarengine"]["count"] == 1
    assert state["current"] is None

    started = job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert started["verdict"] == job.PROCEED
    assert started["entry"].number == 2


def test_reconcile_is_idempotent(env):
    write_foreign_ledger(env, mode=2, type_key="stellarengine",
                         started="2026-11-01T13:56:57-05:00")
    job.apply_tick(env.doc, 2, when=NOW)
    job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW)
    first = (env.state_dir / "state.json").read_bytes()

    second = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW)

    assert second["imported"] == []
    assert second["kept"] == 2
    assert (env.state_dir / "state.json").read_bytes() == first


def test_reconcile_dry_run_changes_nothing(env):
    write_foreign_ledger(env, mode=2, type_key="stellarengine",
                         started="2026-11-01T13:56:57-05:00")
    before = (env.state_dir / "state.json").read_bytes()

    report = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW, dry_run=True)

    assert report["verdict"] == "RECONCILED" and report["dry_run"] is True
    assert len(report["imported"]) == 1
    assert (env.state_dir / "state.json").read_bytes() == before


def test_reconcile_leaves_a_review_hold_in_place_unless_asked(env):
    write_foreign_ledger(env, mode=2, type_key="stellarengine",
                         started="2026-11-01T13:56:57-05:00")
    state = json.loads((env.state_dir / "state.json").read_text(encoding="utf-8"))
    state["hold"] = {"reason": "overrun", "note": "worker stopped",
                     "at": job._iso(NOW)}
    (env.state_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n",
                                              encoding="utf-8")

    refused = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert refused["verdict"] == "REFUSED"
    assert env.state["current"] is not None

    cleared = job.reconcile(state_dir=env.state_dir, doc=env.doc, now=NOW, clear_hold=True)
    assert cleared["verdict"] == "RECONCILED"
    assert cleared["cleared_hold"] is True
    assert env.state["hold"] is None
    assert env.state["current"] is None


# --------------------------------------------------------------------------------------
# a broken ledger is a stop, not a reset
# --------------------------------------------------------------------------------------

def test_a_corrupt_ledger_refuses_rather_than_forgetting_an_open_run(env):
    env.state_dir.mkdir(parents=True)
    (env.state_dir / "state.json").write_text("{ this is not json", encoding="utf-8")
    before = env.doc.read_bytes()

    with pytest.raises(job.JobError):
        job.start(state_dir=env.state_dir, doc=env.doc, now=NOW)
    assert env.doc.read_bytes() == before


# --------------------------------------------------------------------------------------
# the brief
# --------------------------------------------------------------------------------------

def test_the_brief_template_covers_every_mode(env):
    template = TEMPLATE.read_text(encoding="utf-8")
    for token in job.BRIEF_TOKENS:
        assert "{{" + token + "}}" in template, f"the brief forgot {{{{{token}}}}}"

    entries = job.load_tracker(env.doc)
    for entry in entries:
        brief = job.render_brief(TEMPLATE, entry=entry, run_id="run-1", doc=env.doc,
                                 total=len(entries), remaining=1, now=NOW)
        assert "{{" not in brief and "}}" not in brief
        assert entry.file in brief
        assert entry.class_name in brief
        assert entry.title in brief
        assert "scripts/slow_wireframe_job.py finish --run-id run-1" in brief
        assert f"--mode {entry.number}" in brief


def test_an_unknown_brief_token_is_refused(tmp_path):
    template = tmp_path / "brief.md"
    template.write_text("{{NOT_A_TOKEN}}\n", encoding="utf-8")
    with pytest.raises(job.JobError):
        job.render_brief(template, entry=job.load_tracker(DOC)[0], run_id="r",
                         doc=DOC, total=20, remaining=20, now=NOW)


# --------------------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------------------

def test_the_cli_prints_the_verdict_and_status(env):
    env_vars = {
        **os.environ,
        "SLOW_WIREFRAME_STATE_DIR": str(env.state_dir),
        "SLOW_WIREFRAME_DOC": str(env.doc),
        "SLOW_WIREFRAME_NOW": job._iso(NOW),
    }
    started = subprocess.run([sys.executable, str(SCRIPT), "start"], cwd=str(BASE_DIR),
                             capture_output=True, text=True, env=env_vars)
    assert started.returncode == 0, started.stderr
    assert "VERDICT: PROCEED" in started.stdout
    assert "mode 1 · `dysonswarm`" in started.stdout
    assert "--- begin brief ---" in started.stdout

    status = subprocess.run([sys.executable, str(SCRIPT), "status"], cwd=str(BASE_DIR),
                            capture_output=True, text=True, env=env_vars)
    assert status.returncode == 0, status.stderr
    assert "0 of 20 modes ticked" in status.stdout
    assert "running" in status.stdout and "-01-dysonswarm" in status.stdout

    held = subprocess.run([sys.executable, str(SCRIPT), "hold", "--reason", "operator"],
                          cwd=str(BASE_DIR), capture_output=True, text=True, env=env_vars)
    assert held.returncode == 0, held.stderr
    assert "VERDICT: HELD" in held.stdout


def test_the_cli_refuses_a_bad_run_id(env):
    open_run(env)
    env_vars = {
        **os.environ,
        "SLOW_WIREFRAME_STATE_DIR": str(env.state_dir),
        "SLOW_WIREFRAME_DOC": str(env.doc),
    }
    refused = subprocess.run(
        [sys.executable, str(SCRIPT), "finish", "--run-id", "nope", "--mode", "1"],
        cwd=str(BASE_DIR), capture_output=True, text=True, env=env_vars,
    )
    assert refused.returncode == 2
    assert "REFUSED" in refused.stderr
    assert env.ticked_numbers() == []


def test_rearm_documents_the_schedule_it_belongs_to():
    text = job.rearm()
    assert job.SCHEDULE_TITLE in text
    assert "10800" in text
    assert "slow_wireframe_job.py start" in text
    assert "schedule_delete" in text
